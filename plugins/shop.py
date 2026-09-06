"""
Shop plugin — paid/free content categories, coupon redemption, and
manual-confirm crypto payments. Ported from the sale-engine project's
access model onto the file-store bot's existing MongoDB layer.

Telegram Stars / card payments are intentionally NOT included here:
hydrogram (the library this bot runs on) has no support for the
Telegram Payments API (no send_invoice / successful_payment /
pre_checkout_query). Only crypto (manual confirm), coupons, and
admin-granted access are wired up.
"""

from hydrogram import Client, filters
from hydrogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from hydrogram.errors import RPCError
from config import ADMINS, OWNER_ID


def is_admin(user_id: int) -> bool:
    return user_id == OWNER_ID or user_id in ADMINS


# ---------------------------------------------------------------- admin: categories

@Client.on_message(filters.command("addcat") & filters.private)
async def add_category(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    usage = (
        "<b>Usage:</b> /addcat Name|price_cents|access_days\n\n"
        "<b>Example:</b> /addcat Premium|499|30\n"
        "(499 cents = $4.99, access lasts 30 days. Use 0 for access_days = lifetime, "
        "0 for price_cents = free category.)"
    )
    if len(message.command) < 2:
        return await message.reply_text(usage)

    raw = message.text.split(None, 1)[1]
    parts = raw.split("|")
    if len(parts) != 3:
        return await message.reply_text(usage)

    name = parts[0].strip()
    try:
        price_cents = int(parts[1].strip())
        access_days = int(parts[2].strip())
    except ValueError:
        return await message.reply_text(usage)

    if not name:
        return await message.reply_text(usage)

    existing = await client.mongodb.get_category_by_name(name)
    if existing:
        return await message.reply_text(f"A category named '{name}' already exists.")

    cat_id = await client.mongodb.create_category(name, price_cents, access_days)
    price_text = "Free" if price_cents == 0 else f"${price_cents / 100:.2f}"
    access_text = "Lifetime" if access_days == 0 else f"{access_days} days"
    await message.reply_text(
        f"✅ Catalog pack created.\n\n"
        f"<b>Name:</b> {name}\n<b>ID:</b> <code>{cat_id}</code>\n"
        f"<b>Price:</b> {price_text}\n<b>Access:</b> {access_text}\n\n"
        f"<b>Next steps (no /addcontent needed):</b>\n"
        f"1. Create a private Telegram channel\n"
        f"2. Add this bot as admin (Invite Users + Ban Users)\n"
        f"3. Post your files in that channel yourself\n"
        f"4. Run: <code>/linkchannel {cat_id} -100YOUR_CHANNEL_ID</code>\n\n"
        f"Users pay in the bot → get a join link → expire → auto removed."
    )


@Client.on_message(filters.command("listcat") & filters.private)
async def list_categories_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    show_inactive = len(message.command) > 1 and message.command[1].lower() == "all"
    categories = await client.mongodb.list_categories(active_only=not show_inactive)

    if not categories:
        return await message.reply_text(
            "No categories found." if not show_inactive else "No categories found (including inactive)."
        )

    lines = ["<b>📂 Categories</b>\n"]
    for cat in categories:
        price = int(cat.get("price_cents") or 0)
        days = int(cat.get("access_days") or 0)
        price_text = "Free" if price == 0 else f"${price / 100:.2f}"
        access_text = "Lifetime" if days == 0 else f"{days}d"
        status = "" if cat.get("active", True) else " ❌ inactive"
        linked = "📺" if cat.get("access_channel_id") else "⚠️ no channel"
        lines.append(
            f"• <b>{cat['name']}</b>{status}\n"
            f"  ID: <code>{cat['_id']}</code>\n"
            f"  {price_text} / {access_text} — {linked}"
        )

    lines.append("\nUse <code>/listcat all</code> to include inactive ones.")
    lines.append("Use <code>/delcat CATEGORY_ID</code> to remove one.")
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("delcat") & filters.private)
async def delete_category_cmd(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    usage = (
        "<b>Usage:</b> /delcat CATEGORY_ID [hard]\n\n"
        "Without <code>hard</code>, the category is just deactivated (hidden from "
        "/shop, but existing orders/coupons/access records referencing it are kept).\n"
        "With <code>hard</code>, the category document is permanently deleted.\n\n"
        "Run <code>/listcat</code> to find a CATEGORY_ID."
    )
    if len(message.command) < 2:
        return await message.reply_text(usage)

    category_id = message.command[1]
    hard = len(message.command) > 2 and message.command[2].lower() == "hard"

    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await message.reply_text("No category found with that ID. Check /listcat.")

    ok = await client.mongodb.delete_category(category_id, hard=hard)
    if not ok:
        return await message.reply_text("Could not delete that category. Check the ID and try again.")

    if hard:
        await message.reply_text(f"🗑 Permanently deleted category '{cat['name']}' (<code>{category_id}</code>).")
    else:
        await message.reply_text(
            f"✅ Deactivated category '{cat['name']}' (<code>{category_id}</code>).\n"
            f"It's hidden from /shop now. Use <code>/delcat {category_id} hard</code> to fully delete it."
        )


@Client.on_message(filters.command("setprice") & filters.private)
async def set_price(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if len(parts) != 2:
        return await message.reply_text("<b>Usage:</b> /setprice category_id price_cents")

    category_id, price_raw = parts
    try:
        price_cents = int(price_raw)
    except ValueError:
        return await message.reply_text("price_cents must be a whole number of cents.")

    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await message.reply_text("No category found with that ID.")

    await client.mongodb.set_category_price(category_id, price_cents)
    price_text = "Free" if price_cents == 0 else f"${price_cents / 100:.2f}"
    await message.reply_text(f"✅ Price for '{cat['name']}' updated to {price_text}.")


@Client.on_message(filters.command("addcontent") & filters.private)
async def add_content(client: Client, message: Message):
    """Not required. Files are uploaded manually in the catalog channel."""
    if not is_admin(message.from_user.id):
        return
    await message.reply_text(
        "<b>/addcontent is not needed.</b>\n\n"
        "Post files yourself in the private catalog channel.\n"
        "The bot only handles: price → pay → join link → kick on expiry.\n\n"
        "Setup:\n"
        "1. /addcat Name|price_cents|days\n"
        "2. Create private channel + bot admin\n"
        "3. Upload files in that channel\n"
        "4. /linkchannel CATEGORY_ID -100CHANNEL_ID"
    )


# ---------------------------------------------------------------- catalog / buy

def _catalog_markup(categories):
    buttons = []
    for cat in categories:
        price_text = "Free" if cat["price_cents"] == 0 else f"${cat['price_cents'] / 100:.2f}"
        buttons.append([InlineKeyboardButton(
            f"{cat['name']} — {price_text}",
            callback_data=f"cat_view_{cat['_id']}"
        )])
    return InlineKeyboardMarkup(buttons) if buttons else None


async def _send_catalog(client: Client, chat_id: int, edit_message: Message = None, photo: str = None):
    categories = await client.mongodb.list_categories()
    text = (
        "<b>🛒 Catalog</b>\n\n"
        "Price is for the whole catalog (the channel), not each file.\n"
        "Pick a pack:"
    )
    if not categories:
        msg = "The catalog is empty right now."
        if edit_message:
            try:
                return await edit_message.edit_text(msg)
            except Exception:
                pass
        if photo:
            try:
                return await client.send_photo(chat_id, photo=photo, caption=msg)
            except Exception as e:
                client.LOGGER(__name__, client.name).warning(f"catalog photo failed: {e}")
        return await client.send_message(chat_id, msg)

    markup = _catalog_markup(categories)
    if edit_message:
        try:
            return await edit_message.edit_text(text, reply_markup=markup)
        except Exception:
            pass
    if photo:
        try:
            return await client.send_photo(chat_id, photo=photo, caption=text, reply_markup=markup)
        except Exception as e:
            client.LOGGER(__name__, client.name).warning(f"catalog photo failed: {e}")
    await client.send_message(chat_id, text, reply_markup=markup)


@Client.on_message(filters.command(["shop", "catalog"]) & filters.private)
async def shop_catalog(client: Client, message: Message):
    await _send_catalog(client, message.chat.id)


@Client.on_message(
    filters.private
    & (
        filters.regex(r"^🛒 Open Catalog$")
        | filters.regex(r"^Open Catalog$")
        | filters.regex(r"^🛒 Catalog$")
        | filters.regex(r"^Catalog$")
        | filters.regex(r"^Shop$")
    )
)
async def shop_catalog_btn(client: Client, message: Message):
    """Bottom keyboard — no /shop command needed."""
    await _send_catalog(client, message.chat.id)


@Client.on_callback_query(filters.regex(r"^open_catalog$"))
async def open_catalog_cb(client: Client, cq: CallbackQuery):
    """Always send a new catalog message (editing start photos often fails)."""
    await cq.answer()
    await _send_catalog(client, cq.from_user.id, edit_message=None)


@Client.on_callback_query(filters.regex(r"^cat_view_"))
async def view_category(client: Client, cq: CallbackQuery):
    category_id = cq.data.split("cat_view_", 1)[1]
    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await cq.answer("This category no longer exists.", show_alert=True)

    price = int(cat.get("price_cents") or 0)
    has_access = True if price == 0 else await client.mongodb.has_category_access(cq.from_user.id, category_id)
    linked = bool(cat.get("access_channel_id"))
    days = int(cat.get("access_days") or 0)
    days_label = "lifetime" if days == 0 else f"{days} days"
    price_text = "Free" if price == 0 else f"${price / 100:.2f} / {days_label}"

    text = (
        f"<b>{cat['name']}</b>\n"
        f"Price: {price_text}\n"
        f"{'📺 Private channel linked' if linked else '⚠️ Admin: run /linkchannel for this pack'}\n\n"
        f"You upload files in the channel yourself.\n"
        f"After pay, the bot sends a join link.\n"
        f"When access ends, you are removed automatically."
    )

    if not linked:
        buttons = [[InlineKeyboardButton("« Back to Catalog", callback_data="cat_back")]]
    elif has_access:
        buttons = [
            [InlineKeyboardButton("📺 Get join link", callback_data=f"cat_open_{category_id}")],
            [InlineKeyboardButton("« Back to Catalog", callback_data="cat_back")],
        ]
    else:
        buttons = [
            [InlineKeyboardButton("💳 Choose payment method", callback_data=f"cat_paymenu_{category_id}")],
            [InlineKeyboardButton("🎟 Redeem coupon", callback_data=f"cat_redeem_{category_id}")],
            [InlineKeyboardButton("« Back to Catalog", callback_data="cat_back")],
        ]

    await cq.message.edit_text(text, reply_markup=InlineKeyboardMarkup(buttons))
    await cq.answer()


@Client.on_callback_query(filters.regex(r"^cat_back$"))
async def back_to_catalog(client: Client, cq: CallbackQuery):
    await cq.answer()
    await _send_catalog(client, cq.from_user.id, edit_message=cq.message)


@Client.on_callback_query(filters.regex(r"^cat_open_"))
async def open_category(client: Client, cq: CallbackQuery):
    """Only action after unlock: send single-use invite to the private catalog channel."""
    category_id = cq.data.split("cat_open_", 1)[1]
    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await cq.answer("This category no longer exists.", show_alert=True)

    price = int(cat.get("price_cents") or 0)
    if price > 0 and not await client.mongodb.has_category_access(cq.from_user.id, category_id):
        return await cq.answer("Pay first to get the join link.", show_alert=True)

    if not cat.get("access_channel_id"):
        return await cq.answer(
            "Admin has not linked a channel yet (/linkchannel).",
            show_alert=True,
        )

    # Free pack: record grant so expiry/kick logic stays consistent
    if price == 0 and not await client.mongodb.has_category_access(cq.from_user.id, category_id):
        expiry = None
        days = int(cat.get("access_days") or 0)
        if days > 0:
            from datetime import datetime, timedelta
            expiry = datetime.now() + timedelta(days=days)
        await client.mongodb.grant_category_access(cq.from_user.id, category_id, expiry)

    await cq.answer("Sending join link…")
    ok = await grant_channel_invite(client, cq.from_user.id, category_id)
    if not ok:
        await cq.message.reply_text(
            "Could not create the invite.\n"
            "Admin: bot must be channel admin with <b>Invite Users</b> + <b>Ban Users</b>, "
            "then /linkchannel CATEGORY_ID -100CHANNEL_ID"
        )


# ---------------------------------------------------------------- coupons

@Client.on_message(filters.command("redeem") & filters.private)
async def redeem_command(client: Client, message: Message):
    parts = message.command[1:]
    if len(parts) != 1:
        return await message.reply_text("<b>Usage:</b> /redeem CODE")

    result = await client.mongodb.redeem_coupon(parts[0], message.from_user.id)
    if not result["ok"]:
        return await message.reply_text(f"❌ {result['error']}")

    cat = await client.mongodb.get_category(result["category_id"])
    name = cat["name"] if cat else "your catalog"
    await message.reply_text(
        f"✅ Coupon redeemed! You now have access to <b>{name}</b>.",
        reply_markup=InlineKeyboardMarkup(
            [[InlineKeyboardButton("🛒 Open Catalog", callback_data="open_catalog")]]
        ),
    )
    await grant_channel_invite(client, message.from_user.id, result["category_id"])


@Client.on_callback_query(filters.regex(r"^cat_redeem_"))
async def redeem_prompt(client: Client, cq: CallbackQuery):
    await cq.answer()
    await cq.message.reply_text("Send the coupon code with:\n<code>/redeem CODE</code>")


@Client.on_message(filters.command("createcoupon") & filters.private)
async def create_coupon(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    usage = (
        "<b>Usage:</b> /createcoupon CODE|category_id|uses|access_days\n\n"
        "<b>Example:</b> /createcoupon LAUNCH50|&lt;category_id&gt;|10|30"
    )
    if len(message.command) < 2:
        return await message.reply_text(usage)

    raw = message.text.split(None, 1)[1]
    parts = raw.split("|")
    if len(parts) != 4:
        return await message.reply_text(usage)

    code, category_id, uses_raw, days_raw = [p.strip() for p in parts]
    try:
        uses_left = int(uses_raw)
        access_days = int(days_raw)
    except ValueError:
        return await message.reply_text(usage)

    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await message.reply_text("No category found with that ID.")

    ok = await client.mongodb.create_coupon(code, category_id, uses_left, access_days)
    if not ok:
        return await message.reply_text("A coupon with that code already exists.")

    await message.reply_text(f"✅ Coupon <code>{code.upper()}</code> created for '{cat['name']}' ({uses_left} uses).")


# ---------------------------------------------------------------- multi-method payments (manual admin confirm)
# hydrogram cannot do Telegram Stars / native card checkout.
# All methods: user pays outside → admin /confirm ORDER_ID → join link.
# Card works via your Stripe / Razorpay / PayLink URL (/setpay card https://...).

PAYMENT_METHODS = {
    # Cards & payment links
    "card":   {"label": "💳 Card / Stripe / Razorpay link"},
    "paytm":  {"label": "📱 Paytm"},
    "razor":  {"label": "🇮🇳 Razorpay link"},
    # India
    "upi":    {"label": "🇮🇳 UPI / GPay / PhonePe"},
    "bank":   {"label": "🏦 Bank transfer"},
    # Global wallets
    "paypal": {"label": "💙 PayPal"},
    "wise":   {"label": "🌍 Wise"},
    "revolut":{"label": "💸 Revolut"},
    "skrill": {"label": "💜 Skrill"},
    "neteller":{"label": "💚 Neteller"},
    "cashapp":{"label": "💵 Cash App"},
    "venmo":  {"label": "💙 Venmo"},
    "zelle":  {"label": "⚡ Zelle"},
    # Crypto
    "crypto": {"label": "🪙 USDT / crypto wallet"},
    "binance":{"label": "🟡 Binance Pay"},
    "btc":    {"label": "₿ Bitcoin"},
    "eth":    {"label": "Ξ Ethereum"},
    # Asia
    "alipay": {"label": "🔵 Alipay"},
    "wechat": {"label": "💬 WeChat Pay"},
    # Fallback
    "other":  {"label": "💸 Other / custom"},
}

# short keys only — callback_data must stay under 64 bytes
_METHOD_RE = "|".join(PAYMENT_METHODS.keys())


async def _payment_instructions(client: Client, method: str) -> str:
    if method == "crypto":
        wallet = await client.mongodb.get_bot_setting("pay_crypto", "") \
            or await client.mongodb.get_bot_setting("crypto_wallet", "")
        currency = await client.mongodb.get_bot_setting("crypto_currency", "USDT")
        network = await client.mongodb.get_bot_setting("crypto_network", "TRC20")
        if wallet:
            return f"Send <b>{currency}</b> ({network}) to:\n<code>{wallet}</code>"
        return "Admin has not set a crypto wallet yet. Use /setpay crypto …"

    text = await client.mongodb.get_bot_setting(f"pay_{method}", "")
    if text and str(text).strip():
        return str(text).strip()
    label = PAYMENT_METHODS.get(method, {}).get("label", method)
    return f"Admin has not configured <b>{label}</b> yet.\nThey can run: /setpay {method} …"


async def _enabled_methods(client: Client) -> list:
    """Only show methods the admin has configured (plus crypto if legacy wallet exists)."""
    enabled = []
    for mid in PAYMENT_METHODS:
        if mid == "crypto":
            val = await client.mongodb.get_bot_setting("pay_crypto", "") \
                or await client.mongodb.get_bot_setting("crypto_wallet", "")
        else:
            val = await client.mongodb.get_bot_setting(f"pay_{mid}", "")
        if val and str(val).strip():
            enabled.append(mid)
    return enabled


@Client.on_callback_query(filters.regex(r"^cat_paymenu_"))
async def pay_menu(client: Client, cq: CallbackQuery):
    category_id = cq.data.split("cat_paymenu_", 1)[1]
    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await cq.answer("This category no longer exists.", show_alert=True)

    methods = await _enabled_methods(client)
    if not methods:
        await cq.answer()
        return await cq.message.edit_text(
            "⚠️ No payment methods configured yet.\n\n"
            "Admin must run e.g.:\n"
            "<code>/setpay upi name@oksbi</code>\n"
            "<code>/setpay card https://buy.stripe.com/...</code>\n"
            "<code>/setpay crypto TXwallet USDT TRC20</code>\n"
            "<code>/setpay paypal https://paypal.me/you</code>\n\n"
            "See all options: /setpay",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("« Back", callback_data=f"cat_view_{category_id}")]
            ]),
        )

    buttons = []
    row = []
    for mid in methods:
        row.append(InlineKeyboardButton(
            PAYMENT_METHODS[mid]["label"],
            callback_data=f"cat_buy_{mid}_{category_id}",
        ))
        if len(row) == 1:  # one big button per row — easier to tap
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton("« Back", callback_data=f"cat_view_{category_id}")])

    days = int(cat.get("access_days") or 0)
    days_label = "lifetime" if days == 0 else f"{days} days"
    await cq.message.edit_text(
        f"<b>Pay for {cat['name']}</b>\n"
        f"Amount: <b>${cat['price_cents'] / 100:.2f}</b> · Access: {days_label}\n\n"
        f"Choose a payment method:",
        reply_markup=InlineKeyboardMarkup(buttons),
    )
    await cq.answer()


@Client.on_callback_query(filters.regex(rf"^cat_buy_({_METHOD_RE})_"))
async def buy_with_method(client: Client, cq: CallbackQuery):
    rest = cq.data[len("cat_buy_"):]
    method, category_id = rest.split("_", 1)
    if method not in PAYMENT_METHODS:
        return await cq.answer("Unknown method.", show_alert=True)

    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await cq.answer("This category no longer exists.", show_alert=True)

    order_id = await client.mongodb.create_order(
        cq.from_user.id, category_id, cat["price_cents"], method
    )
    instructions = await _payment_instructions(client, method)
    label = PAYMENT_METHODS[method]["label"]

    # If instructions contain a URL, add an Open link button
    url_btn = None
    for token in instructions.replace("\n", " ").split():
        if token.startswith("http://") or token.startswith("https://"):
            url_btn = token.strip("<>")
            break

    kb = []
    if url_btn:
        kb.append([InlineKeyboardButton("🔗 Open payment link", url=url_btn)])
    kb.append([InlineKeyboardButton("« Payment methods", callback_data=f"cat_paymenu_{category_id}")])
    kb.append([InlineKeyboardButton("🛒 Catalog", callback_data="open_catalog")])

    await cq.answer()
    await cq.message.reply_text(
        f"<b>{label}</b>\n"
        f"Pack: <b>{cat['name']}</b>\n"
        f"Amount: <b>${cat['price_cents'] / 100:.2f}</b>\n"
        f"Order ID: <code>{order_id}</code>\n\n"
        f"{instructions}\n\n"
        f"After paying, send <b>Order ID</b> + screenshot to admin.\n"
        f"Admin: <code>/confirm {order_id}</code>\n"
        f"→ you get the private channel join link.",
        reply_markup=InlineKeyboardMarkup(kb),
        disable_web_page_preview=True,
    )


@Client.on_message(filters.command("setpay") & filters.private)
async def set_payment_details(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    if len(message.command) < 3:
        lines = [
            "<b>Set payment details</b>",
            "Only methods you set appear to users.\n",
            "<b>Examples:</b>",
            "<code>/setpay card https://buy.stripe.com/xxxx</code>",
            "<code>/setpay razor https://rzp.io/xxxx</code>",
            "<code>/setpay upi name@oksbi</code>",
            "<code>/setpay bank A/C 123 · IFSC SBIN0 · Name You</code>",
            "<code>/setpay paypal https://paypal.me/you</code>",
            "<code>/setpay wise email@you.com</code>",
            "<code>/setpay crypto TXwallet USDT TRC20</code>",
            "<code>/setpay binance Pay ID 123456789</code>",
            "<code>/setpay btc bc1q...</code>",
            "<code>/setpay eth 0x...</code>",
            "<code>/setpay paytm 9876543210</code>",
            "<code>/setpay cashapp $yourcashtag</code>",
            "<code>/setpay other Any instructions…</code>",
            "\n<b>All method keys:</b>",
            ", ".join(PAYMENT_METHODS.keys()),
            "\nClear one: <code>/setpay upi -</code>",
            "List saved: /payinfo",
        ]
        return await message.reply_text("\n".join(lines))

    method = message.command[1].lower().strip()
    details = message.text.split(None, 2)[2].strip()
    if method not in PAYMENT_METHODS:
        return await message.reply_text(
            f"Unknown method <code>{method}</code>.\n"
            f"Use one of: {', '.join(PAYMENT_METHODS.keys())}"
        )

    # Clear
    if details in ("-", "off", "clear", "none"):
        await client.mongodb.update_bot_setting(f"pay_{method}", "")
        if method == "crypto":
            await client.mongodb.update_bot_setting("crypto_wallet", "")
            await client.mongodb.update_bot_setting("pay_crypto", "")
        return await message.reply_text(f"🗑 {PAYMENT_METHODS[method]['label']} removed.")

    if method == "crypto":
        parts = details.split()
        wallet = parts[0]
        currency = parts[1] if len(parts) > 1 else "USDT"
        network = parts[2] if len(parts) > 2 else "TRC20"
        await client.mongodb.update_bot_setting("pay_crypto", wallet)
        await client.mongodb.update_bot_setting("crypto_wallet", wallet)
        await client.mongodb.update_bot_setting("crypto_currency", currency)
        await client.mongodb.update_bot_setting("crypto_network", network)
        return await message.reply_text(
            f"✅ Crypto saved\n<code>{wallet}</code>\n{currency} · {network}"
        )

    await client.mongodb.update_bot_setting(f"pay_{method}", details)
    await message.reply_text(
        f"✅ {PAYMENT_METHODS[method]['label']} saved:\n{details}\n\n"
        f"Users will see this option in the payment menu."
    )


@Client.on_message(filters.command("payinfo") & filters.private)
async def pay_info(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")
    enabled = await _enabled_methods(client)
    if not enabled:
        return await message.reply_text(
            "No payment methods configured.\nRun /setpay to add some."
        )
    lines = ["<b>Active payment methods</b> (shown to users):\n"]
    for mid in enabled:
        text = await _payment_instructions(client, mid)
        lines.append(f"<b>{PAYMENT_METHODS[mid]['label']}</b>\n{text}\n")
    lines.append("Add/change: /setpay · Remove: /setpay METHOD -")
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("cleardata") & filters.private)
async def clear_shop_data_cmd(client: Client, message: Message):
    """Admin: wipe test/sample shop data from Telegram.
    /cleardata orders  — only payment orders
    /cleardata access  — orders + unlocks + memberships + coupons
    /cleardata all     — everything above + catalog packs
    """
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    mode = (message.command[1] if len(message.command) > 1 else "").lower().strip()
    if mode not in ("orders", "access", "all"):
        return await message.reply_text(
            "<b>Clear shop test data</b>\n\n"
            "<code>/cleardata orders</code> — payment orders only\n"
            "<code>/cleardata access</code> — orders + user unlocks + channel memberships + coupons\n"
            "<code>/cleardata all</code> — all of the above + catalog packs\n\n"
            "Does <b>not</b> delete users or payment method settings (/setpay)."
        )

    counts = await client.mongodb.clear_shop_data(mode)
    lines = [f"✅ Cleared (<code>{mode}</code>):"]
    for k, v in counts.items():
        lines.append(f"• {k}: <b>{v}</b>")
    if mode == "all":
        lines.append("\nRecreate packs with /addcat and /linkchannel.")
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("confirm") & filters.private)
async def confirm_order(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if len(parts) != 1:
        return await message.reply_text("<b>Usage:</b> /confirm order_id")

    order = await client.mongodb.get_order(parts[0])
    if not order:
        return await message.reply_text("No order found with that ID.")
    if order["status"] != "pending":
        return await message.reply_text(f"Order is already '{order['status']}'.")

    cat = await client.mongodb.get_category(order["category_id"])
    expiry_date = None
    if cat and cat.get("access_days"):
        from datetime import datetime, timedelta
        expiry_date = datetime.now() + timedelta(days=cat["access_days"])

    await client.mongodb.mark_order_paid(parts[0])
    await client.mongodb.grant_category_access(order["user_id"], order["category_id"], expiry_date)

    await message.reply_text(f"✅ Order confirmed. Access granted to user {order['user_id']}.")
    try:
        await client.send_message(
            order["user_id"],
            "✅ Your payment was confirmed! Tap Catalog to join your channel.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🛒 Catalog", callback_data="open_catalog")]]
            ),
        )
    except Exception:
        pass
    await grant_channel_invite(client, order["user_id"], order["category_id"])


@Client.on_message(filters.command("pending") & filters.private)
async def list_pending(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    orders = await client.mongodb.get_pending_orders()
    if not orders:
        return await message.reply_text("No pending payment orders.")

    lines = ["<b>Pending payments:</b>\nConfirm with <code>/confirm ORDER_ID</code>\n"]
    for o in orders:
        method = o.get("method") or o.get("provider") or "?"
        lines.append(
            f"• <code>{o['_id']}</code> — user <code>{o['user_id']}</code> — "
            f"${o['amount_cents']/100:.2f} — {method}"
        )
    await message.reply_text("\n".join(lines))


# ---------------------------------------------------------------- storage / catalog admin

@Client.on_message(filters.command("checkstorage") & filters.private)
async def check_storage(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if not parts:
        return await message.reply_text("<b>Usage:</b> /checkstorage <channel_id>")

    try:
        channel_id = int(parts[0])
    except ValueError:
        return await message.reply_text("channel_id must be a number like -100xxxxxxxxxx.")

    try:
        member = await client.get_chat_member(channel_id, "me")
        if member.status.name.lower() in ("administrator", "creator", "owner"):
            await message.reply_text(f"✅ Bot is admin of <code>{channel_id}</code>.")
        else:
            await message.reply_text(f"⚠️ Bot is a member but NOT admin of <code>{channel_id}</code>. Make it admin.")
    except RPCError as e:
        await message.reply_text(f"❌ Can't access <code>{channel_id}</code>: {e}\nMake sure the bot is added there.")


@Client.on_message(filters.command("listvideos") & filters.private)
async def list_videos(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if not parts:
        return await message.reply_text("<b>Usage:</b> /listvideos category_id")

    items = await client.mongodb.list_content_items(parts[0])
    if not items:
        return await message.reply_text("No content items in this category (or category doesn't exist).")

    lines = ["<b>Content items:</b>\n"]
    for it in items:
        trial = " 🎁trial" if it.get("is_free_trial") else ""
        name = it.get("name") or "(untitled)"
        lines.append(f"• <code>{it['item_id']}</code> — {name}{trial}")
    await message.reply_text("\n".join(lines))


@Client.on_message(filters.command("delvideo") & filters.private)
async def delete_video(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if len(parts) != 2:
        return await message.reply_text("<b>Usage:</b> /delvideo category_id item_id")

    ok = await client.mongodb.deactivate_content_item(parts[0], parts[1])
    if ok:
        await message.reply_text("✅ Item hidden from catalog.")
    else:
        await message.reply_text("Item not found.")


# ---------------------------------------------------------------- search / my videos

@Client.on_message(filters.command("search") & filters.private)
async def search_shop(client: Client, message: Message):
    if len(message.command) < 2:
        return await message.reply_text("<b>Usage:</b> /search keyword")

    keyword = message.text.split(None, 1)[1]
    results = await client.mongodb.search_categories(keyword)
    if not results:
        return await message.reply_text("No matching categories found.")

    buttons = []
    for cat in results:
        price_text = "Free" if cat["price_cents"] == 0 else f"${cat['price_cents'] / 100:.2f}"
        buttons.append([InlineKeyboardButton(
            f"{cat['name']} — {price_text}", callback_data=f"cat_view_{cat['_id']}"
        )])
    await message.reply_text(f"Results for '{keyword}':", reply_markup=InlineKeyboardMarkup(buttons))


@Client.on_message(filters.command("myvideos") & filters.private)
async def my_videos(client: Client, message: Message):
    cats = await client.mongodb.get_user_unlocked_categories(message.from_user.id)
    if not cats:
        return await message.reply_text("You haven't unlocked anything yet. Tap Catalog to browse.")


    buttons = [[InlineKeyboardButton(cat["name"], callback_data=f"cat_open_{cat['_id']}")] for cat in cats]
    await message.reply_text("<b>Your unlocked categories:</b>", reply_markup=InlineKeyboardMarkup(buttons))


# ---------------------------------------------------------------- free trial (per item)

@Client.on_callback_query(filters.regex(r"^trial_"))
async def use_free_trial(client: Client, cq: CallbackQuery):
    category_id, item_id = cq.data.split("trial_", 1)[1].split(":", 1)
    items = await client.mongodb.list_content_items(category_id)
    item = next((i for i in items if i["item_id"] == item_id), None)
    if not item or not item.get("is_free_trial"):
        return await cq.answer("Free trial not available for this item.", show_alert=True)

    if await client.mongodb.has_used_free_trial(cq.from_user.id, item_id):
        return await cq.answer("You've already used your free trial for this item.", show_alert=True)

    await client.mongodb.mark_free_trial_used(cq.from_user.id, item_id)
    await cq.answer("🎁 Enjoy your free trial!")
    try:
        await client.copy_message(
            chat_id=cq.from_user.id,
            from_chat_id=item["chat_id"],
            message_id=item["message_id"],
            protect_content=True
        )
    except Exception as e:
        client.LOGGER(__name__, client.name).warning(f"Trial delivery failed for {item}: {e}")


# ---------------------------------------------------------------- automated channel access

@Client.on_message(filters.command("linkchannel") & filters.private)
async def link_channel(client: Client, message: Message):
    """One-time setup: link a category to a private access channel.
    After this, paid/coupon/crypto-confirmed access automatically creates
    a single-use invite link, and expired access automatically kicks the user."""
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    parts = message.command[1:]
    if len(parts) != 2:
        return await message.reply_text("<b>Usage:</b> /linkchannel category_id channel_id")

    category_id, channel_raw = parts
    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await message.reply_text("No category found with that ID.")

    try:
        channel_id = int(channel_raw)
    except ValueError:
        return await message.reply_text("channel_id must be a number like -100xxxxxxxxxx.")

    try:
        member = await client.get_chat_member(channel_id, "me")
        if member.status.name.lower() not in ("administrator", "creator", "owner"):
            return await message.reply_text(
                "⚠️ Bot must be admin in that channel (with Invite Users + Ban Users) before linking."
            )
    except RPCError as e:
        return await message.reply_text(f"❌ Can't access that channel: {e}")

    await client.mongodb.set_category_channel(category_id, channel_id)
    await message.reply_text(
        f"✅ '{cat['name']}' is now linked to <code>{channel_id}</code>.\n"
        f"Paid/coupon/crypto-confirmed users will now get an automatic single-use invite link, "
        f"and access is auto-revoked (kicked) when it expires."
    )


async def grant_channel_invite(client: Client, user_id: int, category_id) -> bool:
    """Call this after any access grant (coupon, crypto confirm, admin grant) to
    automatically invite the user into the category's linked access channel, if any."""
    from datetime import datetime, timedelta

    cat = await client.mongodb.get_category(category_id)
    if not cat or not cat.get("access_channel_id"):
        return False  # no channel linked — nothing to automate

    channel_id = cat["access_channel_id"]
    days = int(cat.get("access_days") or 0)
    expires_at = datetime.now() + timedelta(days=days) if days > 0 else None

    try:
        try:
            await client.unban_chat_member(channel_id, user_id)
        except Exception:
            pass

        link = await client.create_chat_invite_link(
            chat_id=channel_id,
            name=f"u{user_id}-c{category_id}"[:32],
            member_limit=1,
            expire_date=expires_at
        )
    except RPCError as e:
        client.LOGGER(__name__, client.name).warning(f"Invite link creation failed: {e}")
        try:
            await client.send_message(
                user_id,
                f"✅ Access granted for {cat['name']}, but the automatic invite failed. "
                f"Contact an admin for a manual invite."
            )
        except Exception:
            pass
        return False

    await client.mongodb.save_channel_membership(user_id, category_id, channel_id, link.invite_link, expires_at)

    days_label = "lifetime" if days == 0 else f"{days} days"
    try:
        await client.send_message(
            user_id,
            f"✅ <b>Access granted: {cat['name']}</b>\nDuration: {days_label}\n\n"
            f"Join your private channel now (single-use link):\n{link.invite_link}",
            disable_web_page_preview=True
        )
    except Exception:
        pass
    return True


async def kick_expired_channel_members(client: Client) -> int:
    """Background sweep: kick users from linked access channels whose grant expired.
    Call this periodically (e.g. every 10 minutes) from bot.py's startup."""
    rows = await client.mongodb.list_expired_memberships()
    kicked = 0
    for row in rows:
        try:
            await client.ban_chat_member(row["channel_id"], row["user_id"])
            try:
                await client.unban_chat_member(row["channel_id"], row["user_id"])
            except Exception:
                pass
            await client.mongodb.mark_membership_kicked(row["user_id"], row["category_id"])
            kicked += 1
            try:
                await client.send_message(
                    row["user_id"],
                    "⏰ Your timed channel access expired and you were removed. Tap Catalog to renew."

                )
            except Exception:
                pass
        except RPCError as e:
            client.LOGGER(__name__, client.name).warning(
                f"kick failed user={row['user_id']} ch={row['channel_id']}: {e}"
            )
    return kicked

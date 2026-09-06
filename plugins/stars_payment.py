"""
Telegram Stars payments for the shop plugin.

WHY THIS FILE EXISTS
---------------------
hydrogram's *high-level* API does not implement send_invoice / successful_payment /
pre_checkout_query — open helper/../hydrogram/types/messages_and_media/message.py
and you'll find a literal "TODO: Add ... invoice, successful_payment" left in the
Message parser. That's why /setpay never had a "stars" option and buying with
Stars silently did nothing.

hydrogram *does* still ship the raw MTProto layer those features are built on
(hydrogram.raw.functions.messages.{SendMedia,SetBotPrecheckoutResults} and
hydrogram.raw.types.{InputMediaInvoice,Invoice,LabeledPrice,DataJSON,
UpdateBotPrecheckoutQuery,MessageActionPaymentSentMe}), so this module talks to
Telegram directly through that raw layer instead of waiting for hydrogram to add
convenience wrappers.

HOW A STAR PURCHASE FLOWS
---------------------------
1. User taps "⭐ Pay with Stars" in the pay menu (cat_buy_stars_<category_id>).
2. We build an Invoice(currency="XTR", prices=[LabeledPrice(...)]) and send it as
   InputMediaInvoice via raw messages.SendMedia. Telegram renders a native Pay
   button — no external provider token needed for Stars.
3. User pays. Telegram immediately sends us an UpdateBotPrecheckoutQuery. We MUST
   answer within 10 seconds via raw messages.SetBotPrecheckoutResults(success=True)
   or the payment is cancelled client-side.
4. Once we approve, Telegram delivers a service message whose action is
   MessageActionPaymentSentMe. That's the actual "money received" signal — we
   grant category access there (mirrors what /confirm does for manual payments)
   and record the order as paid.

Registration: this plugin only needs `Client.on_raw_update`, which hydrogram
does still support, so no changes to bot.py are required — importing this file
as a plugin (same as every other file in plugins/) is enough.
"""

import random

from hydrogram import Client, filters, raw
from hydrogram.types import Message, CallbackQuery

from plugins.shop import PAYMENT_METHODS, is_admin

STARS_CURRENCY = "XTR"  # Telegram's fixed currency code for Stars invoices

# Make "stars" a selectable method everywhere shop.py builds the payment menu.
PAYMENT_METHODS["stars"] = {"label": "⭐ Pay with Telegram Stars"}

# in-memory de-dup so a retried/duplicate successful_payment update
# (Telegram occasionally redelivers updates) can't double-grant access
_processed_charges: set[str] = set()


def _category_star_price(cat: dict) -> int:
    """
    Stars have no concept of cents, so we reuse the category's price_cents
    value as the Star amount 1:1 (i.e. a category priced at 499 -> 499 Stars).
    Override per-category with /setstarprice CATEGORY_ID STARS if you want a
    different conversion than price_cents.
    """
    return int(cat.get("price_stars") or cat.get("price_cents") or 0)


@Client.on_message(filters.command("setstarprice") & filters.private)
async def set_star_price(client: Client, message: Message):
    if not is_admin(message.from_user.id):
        return await message.reply_text("Only admins can use this command.")

    usage = "<b>Usage:</b> /setstarprice CATEGORY_ID STARS\n\n<b>Example:</b> /setstarprice 66f2... 150"
    if len(message.command) != 3:
        return await message.reply_text(usage)

    category_id, stars_raw = message.command[1], message.command[2]
    try:
        stars = int(stars_raw)
        if stars <= 0:
            raise ValueError
    except ValueError:
        return await message.reply_text(usage)

    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await message.reply_text("No category found with that ID. Check /listcat.")

    from bson import ObjectId
    await client.mongodb.categories.update_one(
        {"_id": ObjectId(category_id)}, {"$set": {"price_stars": stars}}
    )
    await message.reply_text(f"✅ '{cat['name']}' now costs ⭐ {stars} Stars.")


@Client.on_callback_query(filters.regex(r"^cat_buy_stars_"))
async def buy_with_stars(client: Client, cq: CallbackQuery):
    category_id = cq.data.split("cat_buy_stars_", 1)[1]
    cat = await client.mongodb.get_category(category_id)
    if not cat:
        return await cq.answer("This category no longer exists.", show_alert=True)

    stars = _category_star_price(cat)
    if stars <= 0:
        return await cq.answer(
            "Admin hasn't set a Stars price for this category yet.", show_alert=True
        )

    if await client.mongodb.has_category_access(cq.from_user.id, category_id):
        return await cq.answer("You already have access to this category.", show_alert=True)

    order_id = await client.mongodb.create_order(
        cq.from_user.id, category_id, stars, "stars", status="pending"
    )

    peer = await client.resolve_peer(cq.from_user.id)
    invoice = raw.types.Invoice(currency=STARS_CURRENCY, prices=[
        raw.types.LabeledPrice(label=cat["name"], amount=stars)
    ])
    media = raw.types.InputMediaInvoice(
        title=cat["name"][:32],
        description=f"Access to '{cat['name']}' for "
                     f"{'lifetime' if not cat.get('access_days') else str(cat['access_days']) + ' days'}.",
        invoice=invoice,
        payload=order_id.encode(),
        provider_data=raw.types.DataJSON(data="{}"),
    )

    try:
        await client.invoke(
            raw.functions.messages.SendMedia(
                peer=peer,
                media=media,
                message="",
                random_id=random.randrange(-(2 ** 63), 2 ** 63 - 1),
            )
        )
        await cq.answer("Invoice sent — check the chat to pay.")
    except Exception as e:
        client.LOGGER(__name__, client.name).warning(f"stars invoice failed: {e}")
        await cq.answer("Could not create the Stars invoice. Try again later.", show_alert=True)


@Client.on_raw_update()
async def stars_raw_handler(client: Client, update, users, chats):
    # Step 3: approve the pre-checkout query so Telegram actually charges the user.
    if isinstance(update, raw.types.UpdateBotPrecheckoutQuery):
        try:
            await client.invoke(
                raw.functions.messages.SetBotPrecheckoutResults(
                    query_id=update.query_id, success=True
                )
            )
        except Exception as e:
            client.LOGGER(__name__, client.name).warning(f"precheckout answer failed: {e}")
        return

    # Step 4: the money has actually landed — grant access.
    if isinstance(update, raw.types.UpdateNewMessage):
        msg = update.message
        action = getattr(msg, "action", None)
        if not isinstance(action, raw.types.MessageActionPaymentSentMe):
            return

        order_id = action.payload.decode(errors="ignore")
        charge_id = getattr(action.charge, "id", None) or f"{order_id}:{action.total_amount}"
        if charge_id in _processed_charges:
            return
        _processed_charges.add(charge_id)

        order = await client.mongodb.get_order(order_id)
        if order:
            await client.mongodb.mark_order_paid(order_id, status="paid")

        user_id = getattr(msg.peer_id, "user_id", None)
        if not order or not user_id:
            client.LOGGER(__name__, client.name).warning(
                f"stars payment received but order/user not resolved (payload={order_id!r})"
            )
            return

        category_id = order["category_id"]
        cat = await client.mongodb.get_category(category_id)
        if not cat:
            return

        expiry = None
        days = int(cat.get("access_days") or 0)
        if days > 0:
            from datetime import datetime, timedelta
            expiry = datetime.now() + timedelta(days=days)

        await client.mongodb.grant_category_access(user_id, category_id, expiry)

        try:
            from plugins.shop import grant_channel_invite
            await client.send_message(user_id, f"✅ Payment received — ⭐ {action.total_amount} Stars.")
            ok = await grant_channel_invite(client, user_id, category_id)
            if not ok:
                await client.send_message(
                    user_id,
                    "Payment confirmed, but the join link couldn't be created yet. "
                    "An admin needs to run /linkchannel for this category.",
                )
        except Exception as e:
            client.LOGGER(__name__, client.name).warning(f"post-payment notify failed: {e}")

# Modifications copyright push2006. Original notices and LICENSE retained.
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
    if not is_admin(message.from_user.id, client):
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
async def buy_with_stars(client, cq):
    uid=cq.from_user.id
    category_id=cq.data.split("cat_buy_stars_",1)[1]
    if await client.mongodb.is_banned(uid): return await cq.answer("Access restricted.",show_alert=True)
    cat=await client.mongodb.get_category(category_id)
    if not cat or not cat.get('active') or not cat.get('access_channel_id'):
        return await cq.answer("Listing unavailable.",show_alert=True)
    stars=_category_star_price(cat)
    if not 1<=stars<=100000: return await cq.answer("Invalid Stars price.",show_alert=True)
    if await client.mongodb.has_category_access(uid,category_id): return await cq.answer("You already have access.",show_alert=True)
    seller=cat.get('seller_id')
    from plugins.business import approved
    if seller and (seller==uid or not await approved(client,seller,'seller')):
        return await cq.answer("Listing unavailable for this account.",show_alert=True)
    from helper.business_rules import split_stars
    rates=await client.mongodb.get_bot_setting('business_rates',{'platform':15,'affiliate':0})
    ref=await client.mongodb.db.business_referrals.find_one({'_id':uid})
    affiliate=ref.get('affiliate_id') if ref else None
    if affiliate in (uid,seller) or not affiliate or not await approved(client,affiliate,'affiliate'): affiliate=None
    allocation=split_stars(stars,int(rates['platform']) if seller else 100,int(rates['affiliate']) if affiliate and seller else 0)
    if not seller: affiliate=None
    from datetime import datetime
    row=await client.mongodb.orders.insert_one({'user_id':uid,'category_id':category_id,'method':'stars','amount_cents':stars,'status':'pending','created_at':datetime.utcnow(),'access_days':int(cat.get('access_days') or 0),'seller_id':seller,'affiliate_id':affiliate,'fulfilled':False,**allocation})
    order_id=str(row.inserted_id)
    try:
        peer=await client.resolve_peer(uid)
        invoice=raw.types.Invoice(currency='XTR',prices=[raw.types.LabeledPrice(label=cat['name'][:32],amount=stars)])
        media=raw.types.InputMediaInvoice(title=cat['name'][:32],description='Private channel access. See /paysupport for assistance.',invoice=invoice,payload=order_id.encode(),provider_data=raw.types.DataJSON(data='{}'))
        await client.invoke(raw.functions.messages.SendMedia(peer=peer,media=media,message='',random_id=random.randrange(-(2**63),2**63-1)))
        await cq.answer('Invoice sent.')
    except Exception as e:
        client.LOGGER(__name__,client.name).warning('Invoice failed: %s',type(e).__name__)
        await cq.answer('Could not send invoice. Check /purchases.',show_alert=True)


async def fulfill_order(client, order):
    if order.get('fulfilled') or order.get('status')!='paid': return
    cat=await client.mongodb.get_category(order['category_id'])
    if not cat: return
    from datetime import timedelta
    days=int(order.get('access_days',cat.get('access_days') or 0))
    expiry=order['paid_at']+timedelta(days=days) if days else None
    # Fixed payment timestamp, no extension on replay; preserve lifetime/longer grants.
    await client.mongodb.category_access.update_one({'user_id':order['user_id'],'category_id':order['category_id']},[{ '$set':{'user_id':order['user_id'],'category_id':order['category_id'],'granted_at':{'$ifNull':['$granted_at',order['paid_at']]},'expiry_date':{'$cond':[{'$or':[{'$eq':[{'$type':'$expiry_date'},'null']}, {'$eq':[expiry,None]}]},None,{'$max':['$expiry_date',expiry]}]}}}],upsert=True)
    # Fulfillment means access recorded, not successful delivery. /myvideos can recover link.
    result=await client.mongodb.orders.update_one({'_id':order['_id'],'fulfilled':False,'status':'paid'},{'$set':{'fulfilled':True}})
    if result.modified_count:
        try:
            from plugins.shop import grant_channel_invite
            await client.send_message(order['user_id'],'Payment recorded. Use /myvideos to recover access.')
            await grant_channel_invite(client,order['user_id'],order['category_id'])
        except Exception: pass


@Client.on_raw_update()
async def stars_raw_handler(client, update, users, chats):
    from helper.business_rules import matches_payment
    from datetime import datetime
    from bson import ObjectId
    if isinstance(update,raw.types.UpdateBotPrecheckoutQuery):
        ok=False
        try:
            order=await client.mongodb.get_order(update.payload.decode())
            if matches_payment(order,update.user_id,update.total_amount,update.currency) and not await client.mongodb.is_banned(update.user_id):
                cat=await client.mongodb.get_category(order['category_id'])
                if cat and cat.get('active') and cat.get('access_channel_id') and not await client.mongodb.has_category_access(update.user_id,order['category_id']):
                    result=await client.mongodb.orders.update_one({'_id':order['_id'],'$or':[{'status':'pending'},{'status':'checkout','checkout_id':str(update.query_id)}]},{'$set':{'status':'checkout','checkout_id':str(update.query_id)}})
                    ok=bool(result.matched_count)
        except Exception: pass
        try:
            kw={} if ok else {'error':'Order unavailable. Open the catalog and create a new invoice.'}
            await client.invoke(raw.functions.messages.SetBotPrecheckoutResults(query_id=update.query_id,success=ok,**kw))
        except Exception as e: client.LOGGER(__name__,client.name).warning('Checkout response failed: %s',type(e).__name__)
        return
    if not isinstance(update,raw.types.UpdateNewMessage): return
    msg=update.message
    action=getattr(msg,'action',None)
    if not isinstance(action,raw.types.MessageActionPaymentSentMe): return
    try:
        order=await client.mongodb.get_order(action.payload.decode())
        uid=getattr(msg.peer_id,'user_id',None)
        charge=getattr(action.charge,'id',None)
        if not charge or not matches_payment(order,uid,action.total_amount,action.currency):
            client.LOGGER(__name__,client.name).warning('Unmatched payment; owner reconciliation required.')
            return
        # Persist charge, and prevent one invoice from being counted twice.
        await client.mongodb.orders.update_one({'_id':order['_id'],'status':{'$in':['pending','checkout']},'charge_id':{'$exists':False}},{'$set':{'status':'paid','paid_at':datetime.utcnow(),'charge_id':charge,'fulfilled':False}})
        saved=await client.mongodb.orders.find_one({'_id':order['_id']})
        if saved.get('charge_id')==charge:
            await fulfill_order(client,saved)
        else:
            await client.mongodb.db.business_payment_exceptions.update_one({'_id':charge},{'$setOnInsert':{'order_id':str(order['_id']),'user_id':uid,'amount':action.total_amount,'at':datetime.utcnow()}},upsert=True)
            client.LOGGER(__name__,client.name).warning('Duplicate invoice charge; manual reconciliation required.')
    except Exception as e: client.LOGGER(__name__,client.name).warning('Payment processing failed: %s',type(e).__name__)

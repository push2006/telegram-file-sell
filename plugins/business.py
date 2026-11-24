"""Copyright push2006. Telegram chat marketplace extension."""
import asyncio
from datetime import datetime, timedelta
from html import escape
from io import BytesIO
import csv
import aiohttp
from bson import ObjectId
from hydrogram import Client, filters
from hydrogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from hydrogram.enums import ParseMode
from config import TOKEN
from helper.business_rules import can_manage, split_stars


def db(c): return c.mongodb.db

def now(): return datetime.utcnow()

def oid(x):
    if not ObjectId.is_valid(x): raise ValueError('Invalid ID')
    return ObjectId(x)

async def say(m, text, **kw):
    return await m.reply_text(str(text)[:3900], parse_mode=ParseMode.DISABLED, **kw)

async def audit(c, uid, action, target=''):
    await db(c).business_audit.insert_one({'actor':uid,'action':action,'target':str(target),'at':now()})

async def approved(c, uid, role):
    return uid == c.owner or bool(await db(c).business_roles.find_one({'_id':f'{uid}:{role}','status':'approved'}))

async def register_referral(c, uid, ref):
    if not ref.isdecimal(): return
    ref=int(ref)
    if uid == ref or not await approved(c,ref,'affiliate'): return
    # Only first attribution; do not replace referrals or attribute existing purchasers.
    if await c.mongodb.orders.find_one({'user_id':uid}): return
    await db(c).business_referrals.update_one({'_id':uid},{'$setOnInsert':{'affiliate_id':ref,'at':now()}},upsert=True)

async def dashboard(c,m,uid):
    rows=[[InlineKeyboardButton('Catalog',callback_data='open_catalog'),InlineKeyboardButton('Buyer',callback_data='biz_buyer')],
          [InlineKeyboardButton('Seller',callback_data='biz_seller'),InlineKeyboardButton('Affiliate',callback_data='biz_affiliate')],
          [InlineKeyboardButton('Advertiser',callback_data='biz_advertiser'),InlineKeyboardButton('Support',callback_data='biz_support')]]
    if uid==c.owner: rows.append([InlineKeyboardButton('Owner controls',callback_data='biz_owner'),InlineKeyboardButton('Settings',callback_data='settings')])
    return await say(m,'push2006 Business OS\nChoose your dashboard.',reply_markup=InlineKeyboardMarkup(rows))

HELP={
'buyer':'Buyer\n/catalog — browse\n/myvideos — purchased access\n/purchases — payments\n/wishlist ID — toggle saved product\n/wishlist — list saved products\n/review ID|1-5|text — verified purchase review\n/buyerrequest text — submit request\n/ticket text — support\n/mytickets — view replies\n/campaigns — approved promotions',
'seller':'Seller\n/applyseller Store name\n/sellerstore — your storefront\n/addproduct Name|Stars|Days|ChannelID — submit listing\n/myproducts — list your products\n/hideproduct ID — hide listing\n/earnings — sales ledger\n/payout ORDER_ID — request manual settlement\n/store USER_ID — browse storefront',
'affiliate':'Affiliate\n/applyaffiliate — request approval\n/referral — referral link\n/affiliateearnings — commissions\n/payout ORDER_ID — request manual settlement',
'advertiser':'Advertiser\n/applyadvertiser — request approval\n/newcampaign Text|URL|Days — submit promotion\n/mycampaigns — review status\n/campaigns — approved promotions',
'support':'Support\n/ticket text — open ticket\n/mytickets — ticket replies\n/paysupport — payment assistance',
'owner':'Owner\n/applications — review accounts\n/role USER_ID role approve|reject\n/productqueue — pending products\n/approveproduct ID — publish\n/commission PLATFORM% AFFILIATE%\n/payouts — settlement requests\n/settle ID paid|rejected reference\n/campaignqueue — review ads\n/campaignaction ID approve|reject\n/promotions on|off — display toggle\n/tickets — support queue\n/ticketreply ID|reply\n/analytics — Stars sales\n/exportorders — CSV\n/audit — audit trail\n/setprofile name|description|about TEXT\n/resetbranding — neutral defaults\n/commands — original admin commands\n/db — storage channels\n/settings via dashboard — legacy settings'
}

@Client.on_message(filters.private & filters.command(['business','admin','market','seller','buyer','affiliate','advertiser','paysupport']))
async def biz_menu(c,m):
    uid=m.from_user.id
    if await c.mongodb.is_banned(uid): return await say(m,'Access restricted.')
    cmd=m.command[0].lower()
    if cmd=='admin' and uid!=c.owner: return await say(m,'Owner only.')
    if cmd=='market':
        from plugins.shop import _send_catalog
        return await _send_catalog(c,uid)
    if cmd in ('business','admin'): return await dashboard(c,m,uid)
    return await say(m,HELP.get(cmd,HELP['support']))

@Client.on_callback_query(filters.regex(r'^biz_(home|buyer|seller|affiliate|advertiser|support|owner)$'))
async def biz_callback(c,q):
    uid=q.from_user.id
    page=q.data[4:]
    if await c.mongodb.is_banned(uid) or (page=='owner' and uid!=c.owner): return await q.answer('Not permitted.',show_alert=True)
    await q.answer()
    if page=='home': return await dashboard(c,q.message,uid)
    return await say(q.message,HELP[page])

CMDS='applyseller applyaffiliate applyadvertiser applications role addproduct approveproduct productqueue myproducts hideproduct sellerstore store commission referral earnings affiliateearnings payout payouts settle newcampaign mycampaigns campaignqueue campaignaction promotions campaigns ticket mytickets tickets ticketreply purchases wishlist review buyerrequest requests analytics exportorders audit setprofile resetbranding'.split()

@Client.on_message(filters.private & filters.command(CMDS))
async def biz_action(c,m):
    uid=m.from_user.id
    cmd=m.command[0].lower()
    arg=(m.text or '').partition(' ')[2].strip()
    D=db(c)
    owner=uid==c.owner
    staff=owner or await approved(c,uid,'moderator')
    support=staff or await approved(c,uid,'support')
    if await c.mongodb.is_banned(uid): return await say(m,'Access restricted.')
    try:
        if cmd in {'applications','role','commission','payouts','settle','promotions','analytics','exportorders','audit','setprofile','resetbranding'} and not owner: return await say(m,'Owner only.')
        if cmd in {'approveproduct','productqueue','campaignqueue','campaignaction','requests'} and not staff: return await say(m,'Moderator only.')
        if cmd in {'tickets','ticketreply'} and not support: return await say(m,'Support staff only.')
        if cmd.startswith('apply'):
            role=cmd[5:]
            if role=='seller' and not (1<=len(arg)<=60): raise ValueError('Usage: /applyseller Store name (1–60 characters)')
            await D.business_roles.update_one({'_id':f'{uid}:{role}'},{'$setOnInsert':{'user_id':uid,'role':role,'name':arg[:60],'status':'pending','at':now()}},upsert=True)
            return await say(m,'Application recorded. Owner approval is required.')
        if cmd=='applications':
            rows=await D.business_roles.find({'status':'pending'}).limit(30).to_list(30)
            return await say(m,'Applications\n'+'\n'.join(f"{r['user_id']} {r['role']} {r.get('name','')}" for r in rows) or 'No applications')
        if cmd=='role':
            u,r,decision=arg.split(); u=int(u)
            if u==c.owner or r not in {'seller','affiliate','advertiser','moderator','support'} or decision not in {'approve','reject'}: raise ValueError('Invalid role or decision')
            status='approved' if decision=='approve' else 'rejected'
            await D.business_roles.update_one({'_id':f'{u}:{r}'},{'$set':{'user_id':u,'role':r,'status':status,'updated_at':now()}},upsert=True)
            if r=='seller' and status=='rejected': await c.mongodb.categories.update_many({'seller_id':u},{'$set':{'active':False}})
            await audit(c,uid,'role',f'{u}:{r}:{status}'); return await say(m,status)
        if cmd=='addproduct':
            if not await approved(c,uid,'seller'): return await say(m,'Approved sellers only.')
            name,stars,days,ch=map(str.strip,arg.split('|')); stars,days,ch=int(stars),int(days),int(ch)
            if not 1<=len(name)<=60 or not 1<=stars<=100000 or not 0<=days<=3650 or ch>=0: raise ValueError('Invalid name, Stars, days or channel ID')
            seller_member=await c.get_chat_member(ch,uid); bot_member=await c.get_chat_member(ch,(await c.get_me()).id)
            if seller_member.status.name not in {'OWNER','CREATOR'} or bot_member.status.name!='ADMINISTRATOR': raise ValueError('Seller must own channel and bot must be administrator.')
            if not getattr(bot_member.privileges,'can_invite_users',False) or not getattr(bot_member.privileges,'can_restrict_members',False): raise ValueError('Bot needs invite and restrict permissions.')
            if await c.mongodb.categories.find_one({'access_channel_id':ch}): raise ValueError('Channel already used in catalog.')
            row=await c.mongodb.categories.insert_one({'name':escape(name),'seller_id':uid,'price_stars':stars,'price_cents':stars,'access_days':days,'access_channel_id':ch,'active':False,'approval':'pending','created_at':now()})
            return await say(m,f'Product {row.inserted_id} submitted for review.')
        if cmd=='productqueue':
            rows=await c.mongodb.categories.find({'approval':'pending'}).limit(30).to_list(30)
            return await say(m,'Pending products\n'+'\n'.join(f"{r['_id']} | {r['name']} | seller {r['seller_id']} | {r['price_stars']} Stars" for r in rows))
        if cmd=='approveproduct':
            row=await c.mongodb.categories.find_one({'_id':oid(arg),'approval':'pending'})
            if not row or not await approved(c,row.get('seller_id'), 'seller'): raise ValueError('Pending product not found or seller inactive.')
            await c.mongodb.categories.update_one({'_id':row['_id'],'approval':'pending'},{'$set':{'active':True,'approval':'approved'}}); await audit(c,uid,cmd,arg); return await say(m,'Published.')
        if cmd in {'myproducts','sellerstore','store'}:
            u=int(arg) if cmd=='store' else uid
            q={'seller_id':u}
            if u!=uid: q['active']=True
            rows=await c.mongodb.categories.find(q).limit(30).to_list(30)
            return await say(m,'Store products\n'+'\n'.join(f"{x['_id']} | {x['name']} | {x.get('price_stars')} Stars | {'active' if x.get('active') else 'hidden'}" for x in rows))
        if cmd=='hideproduct':
            x=await c.mongodb.categories.find_one({'_id':oid(arg)})
            if not x or not can_manage(x.get('seller_id'),uid,c.owner): return await say(m,'Not permitted.')
            await c.mongodb.categories.update_one({'_id':x['_id']},{'$set':{'active':False}}); return await say(m,'Hidden; past purchase access retained.')
        if cmd=='commission':
            p,a=map(int,arg.split()); split_stars(100,p,a)
            await c.mongodb.update_bot_setting('business_rates',{'platform':p,'affiliate':a}); await audit(c,uid,cmd,arg); return await say(m,'Rates saved for new invoices.')
        if cmd=='referral':
            if not await approved(c,uid,'affiliate'): return await say(m,'Apply using /applyaffiliate.')
            return await say(m,f'https://t.me/{c.username}?start=ref_{uid}')
        if cmd in {'earnings','affiliateearnings','payout'}:
            fields=['seller','affiliate'] if cmd=='payout' else ['seller' if cmd=='earnings' else 'affiliate']
            if cmd=='payout':
                order=await c.mongodb.orders.find_one({'_id':oid(arg),'status':'paid','fulfilled':True})
                if not order: raise ValueError('Paid, fulfilled order not found.')
                result=[]
                for role in fields:
                    if order.get(role+'_id')!=uid or order.get(role+'_stars',0)<1: continue
                    key=f'{arg}:{role}'
                    await D.business_payouts.update_one({'_id':key},{'$setOnInsert':{'user_id':uid,'order_id':arg,'role':role,'stars':order[role+'_stars'],'status':'requested','at':now()}},upsert=True); result.append(key)
                return await say(m,'Requested: '+', '.join(result) if result else 'No eligible earnings for this order.')
            role=fields[0]; rows=await c.mongodb.orders.find({role+'_id':uid,'status':'paid','fulfilled':True}).sort('paid_at',-1).limit(30).to_list(30)
            return await say(m,'Recent gross allocation (not withdrawable Stars)\n'+'\n'.join(f"{r['_id']}: {r.get(role+'_stars',0)} Stars" for r in rows))
        if cmd=='payouts':
            rows=await D.business_payouts.find({'status':'requested'}).limit(30).to_list(30)
            return await say(m,'Manual settlement requests\n'+'\n'.join(f"{r['_id']} | user {r['user_id']} | {r['stars']} Stars" for r in rows))
        if cmd=='settle':
            key,decision,reference=arg.split(' ',2)
            if decision not in {'paid','rejected'} or not reference: raise ValueError('Usage: /settle ID paid|rejected reference')
            r=await D.business_payouts.update_one({'_id':key,'status':'requested'},{'$set':{'status':decision,'reference':reference[:200],'settled_at':now(),'by':uid}})
            if not r.modified_count: raise ValueError('Not pending.')
            await audit(c,uid,cmd,key); return await say(m,'Settlement record updated. No money was transferred by this command.')
        if cmd=='newcampaign':
            if not await approved(c,uid,'advertiser'): return await say(m,'Apply first: /applyadvertiser')
            from urllib.parse import urlparse
            text,url,days=map(str.strip,arg.split('|')); days=int(days); parsed=urlparse(url)
            if not 1<=len(text)<=500 or parsed.scheme!='https' or not parsed.hostname or not 1<=days<=90: raise ValueError('Invalid text, HTTPS URL or duration.')
            r=await D.business_campaigns.insert_one({'user_id':uid,'text':text,'url':url,'days':days,'status':'pending','at':now()}); return await say(m,f'Submitted {r.inserted_id}. No payment collected.')
        if cmd=='campaignaction':
            key,decision=arg.split(); status={'approve':'approved','reject':'rejected'}.get(decision)
            if not status: raise ValueError('Use approve or reject.')
            r=await D.business_campaigns.find_one({'_id':oid(key)})
            if not r: raise ValueError('Not found.')
            await D.business_campaigns.update_one({'_id':r['_id']},{'$set':{'status':status,'expires_at':now()+timedelta(days=r['days'])}}); await audit(c,uid,cmd,key); return await say(m,status)
        if cmd=='promotions':
            if arg not in {'on','off'}: raise ValueError('Use on or off.')
            await c.mongodb.update_bot_setting('business_promotions',arg=='on'); return await say(m,'Promotion display '+arg)
        if cmd in {'campaignqueue','mycampaigns','campaigns'}:
            if cmd=='campaigns' and not await c.mongodb.get_bot_setting('business_promotions',False): return await say(m,'No promotions.')
            q={'status':'pending'} if cmd=='campaignqueue' else {'user_id':uid} if cmd=='mycampaigns' else {'status':'approved','expires_at':{'$gt':now()}}
            rows=await D.business_campaigns.find(q).limit(15).to_list(15)
            return await say(m,'Promotions\n'+'\n'.join(f"{x['_id']} | {x['status']} | {x['text']}\n{x['url']}" for x in rows),disable_web_page_preview=True)
        if cmd in {'ticket','buyerrequest'}:
            if not 1<=len(arg)<=1500: raise ValueError('Include a message, maximum 1500 characters.')
            col=D.business_tickets if cmd=='ticket' else D.business_requests
            r=await col.insert_one({'user_id':uid,'text':arg,'status':'open','at':now()}); return await say(m,f'Received: {r.inserted_id}')
        if cmd=='ticketreply':
            key,text=arg.split('|',1)
            if not 1<=len(text)<=1500: raise ValueError('Invalid reply.')
            r=await D.business_tickets.find_one_and_update({'_id':oid(key)},{'$set':{'status':'answered','reply':text,'by':uid,'answered_at':now()}})
            if not r: raise ValueError('Ticket not found.')
            try: await c.send_message(r['user_id'],text,parse_mode=ParseMode.DISABLED)
            except Exception: pass
            return await say(m,'Reply saved.')
        if cmd in {'tickets','mytickets','requests'}:
            col=D.business_requests if cmd=='requests' else D.business_tickets
            rows=await col.find({'user_id':uid} if cmd=='mytickets' else {'status':'open'}).limit(20).to_list(20)
            return await say(m,'\n'.join(f"{r['_id']} | {r['status']} | {r['text']} | {r.get('reply','')}" for r in rows) or 'No records.')
        if cmd=='purchases':
            rows=await c.mongodb.orders.find({'user_id':uid}).sort('created_at',-1).limit(30).to_list(30)
            return await say(m,'\n'.join(f"{r['_id']} | {r['status']} | {r['amount_cents']} {r['method']}" for r in rows) or 'No purchases.')
        if cmd=='wishlist':
            if arg:
                cat=await c.mongodb.categories.find_one({'_id':oid(arg),'active':True})
                if not cat: raise ValueError('Active listing not found.')
                key=f'{uid}:{arg}'
                if not (await D.business_wishlist.delete_one({'_id':key})).deleted_count: await D.business_wishlist.update_one({'_id':key},{'$setOnInsert':{'user_id':uid,'category_id':arg,'name':cat['name']}},upsert=True)
                return await say(m,'Wishlist updated.')
            rows=await D.business_wishlist.find({'user_id':uid}).limit(30).to_list(30); return await say(m,'\n'.join(f"{x['category_id']} {x['name']}" for x in rows) or 'Empty.')
        if cmd=='review':
            key,rating,text=arg.split('|',2); rating=int(rating); oid(key)
            if not 1<=rating<=5 or len(text)>500 or not await c.mongodb.orders.find_one({'user_id':uid,'category_id':key,'status':'paid'}): raise ValueError('Verified purchase and rating 1–5 required.')
            await D.business_reviews.update_one({'_id':f'{uid}:{key}'},{'$set':{'category_id':key,'user_id':uid,'rating':rating,'text':text,'at':now()}},upsert=True); return await say(m,'Review saved.')
        if cmd=='analytics':
            rows=await c.mongodb.orders.aggregate([{'$match':{'status':'paid','method':'stars'}},{'$group':{'_id':None,'gross':{'$sum':'$amount_cents'},'orders':{'$sum':1},'platform':{'$sum':'$platform_stars'},'seller':{'$sum':'$seller_stars'},'affiliate':{'$sum':'$affiliate_stars'}}}]).to_list(1)
            return await say(m,'Stars gross accounting (before refunds/fees)\n'+str(rows[0] if rows else 'No sales'))
        if cmd=='exportorders':
            buf=__import__('io').StringIO(); w=csv.writer(buf); w.writerow(['order','buyer','category','method','status','amount','seller_stars','platform_stars','affiliate_stars'])
            async for r in c.mongodb.orders.find({}).limit(10000): w.writerow([str(r.get(k,'')) for k in ['_id','user_id','category_id','method','status','amount_cents','seller_stars','platform_stars','affiliate_stars']])
            f=BytesIO(buf.getvalue().encode()); f.name='orders.csv'; return await m.reply_document(f)
        if cmd=='audit':
            rows=await D.business_audit.find({}).sort('at',-1).limit(25).to_list(25); return await say(m,'\n'.join(f"{x['at']} {x['actor']} {x['action']} {x['target']}" for x in rows) or 'No activity.')
        if cmd=='setprofile':
            field,txt=arg.split(' ',1); mapping={'name':('setMyName','name',64),'description':('setMyDescription','description',512),'about':('setMyShortDescription','short_description',120)}
            if field not in mapping: raise ValueError('Use name, description or about.')
            method,key,limit=mapping[field]
            if txt=='-': txt=''
            if len(txt)>limit: raise ValueError(f'Maximum {limit} characters.')
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.post(f'https://api.telegram.org/bot{TOKEN}/{method}',json={key:txt}) as response:
                    result=await response.json()
            if not result.get('ok'): raise ValueError('Telegram rejected profile update.')
            await audit(c,uid,cmd,field); return await say(m,'Profile updated. Other language variants and profile photo may require BotFather.')
        if cmd=='resetbranding':
            from config import MESSAGES
            await c.mongodb.set_messages_settings(dict(MESSAGES)); c.messages=dict(MESSAGES); c.reply_text=MESSAGES['REPLY']; await c.mongodb.set_shortner_status(False); c.shortner_enabled=False; await c.mongodb.update_bot_setting('business_promotions',False); await audit(c,uid,cmd); return await say(m,'Neutral chat branding restored; Telegram profile must be updated separately.')
    except ValueError as e: return await say(m,str(e) if str(e) else 'Invalid input. Check /business.')
    except Exception as e:
        c.LOGGER(__name__,c.name).warning('Business operation failed: %s',type(e).__name__)
        return await say(m,'Operation failed. Check permissions, input and connection. No payment should be repeated without checking /purchases.')

async def maintenance_loop(c):
    while True:
        try:
            from plugins.stars_payment import fulfill_order
            async for order in c.mongodb.orders.find({'method':'stars','status':'paid','fulfilled':False}).limit(50):
                try: await fulfill_order(c,order)
                except Exception: pass
        except Exception as e: c.LOGGER(__name__,c.name).warning('Maintenance: %s',type(e).__name__)
        await asyncio.sleep(300)

"""Copyright push2006 (modifications). Button-first chat interface."""
from datetime import datetime, timedelta, timezone
from secrets import token_hex
from hydrogram import Client, filters
from hydrogram.enums import ParseMode
from hydrogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as K
from helper.easy_forms import FORMS, validate, assemble, choice_label, page_options
from html import unescape
import re
from plugins import business as biz

MENUS={
 'home': [('Browse catalog','@easy:catalog:0'),('Search','search'),('Buyer account','#buyer'),('Seller account','#seller'),('Affiliate account','#affiliate'),('Advertiser account','#advertiser'),('Support','#support'),('My profile','profile')],
 'buyer':[('My purchases','purchases'),('My access','myvideos'),('Search','search'),('Redeem coupon','redeem'),('Wishlist','wishlist_list'),('Save / remove product','wishlist'),('Write review','review'),('Request a product','buyerrequest'),('Promotions','campaigns')],
 'seller':[('Apply to sell','applyseller'),('Add channel product','addproduct'),('My products','myproducts'),('My storefront','sellerstore'),('Hide product','hideproduct'),('Earnings','earnings'),('Request settlement','payout')],
 'affiliate':[('Apply as affiliate','applyaffiliate'),('My referral link','referral'),('My earnings','affiliateearnings'),('Request settlement','payout')],
 'advertiser':[('Apply as advertiser','applyadvertiser'),('Submit promotion','newcampaign'),('My campaigns','mycampaigns')],
 'support':[('Open ticket','ticket'),('My tickets','mytickets')],
 'owner':[('Accounts','#accounts'),('Products & coupons','#products'),('Revenue & settlements','#finance'),('Promotions','#ads'),('Support & requests','#staff'),('Channels & files','#channels'),('Customization','#branding'),('Users & access','#users'),('Advanced settings','@settings')],
 'accounts':[('Review applications','reviewapplication'),('Application list','applications'),('Assign / change role','role'),('Admin permissions','@admins')],
 'products':[('Pending products','productqueue'),('Approve product','approveproduct'),('Set Stars price','setstarprice'),('Create coupon','createcoupon'),('All categories','listcat'),('Link access channel','linkchannel')],
 'finance':[('Sales analytics','analytics'),('Set commissions','commission'),('Payout requests','payouts'),('Record settlement','settle'),('Export transactions','exportorders'),('Audit log','audit')],
 'ads':[('Pending campaigns','campaignqueue'),('Approve / reject campaign','campaignaction'),('Display on / off','promotions')],
 'staff':[('Open tickets','tickets'),('Reply to ticket','ticketreply'),('Buyer requests','requests')],
 'channels':[('Storage channels','@db_channels'),('Add storage channel','adddb'),('Remove storage channel','removedb'),('Required channels','@fsub'),('Create file link','genlink'),('Create batch link','batch')],
 'branding':[('Edit Telegram profile','setprofile'),('Edit chat messages','settext'),('Edit photos','@photos'),('Restore neutral defaults','resetbranding')],
 'users':[('Statistics','stats'),('Ban user','ban'),('Unban user','unban'),('Grant premium','addpremium'),('Remove premium','delpremium'),('Premium members','premiumusers')],
 'moderator':[('Pending products','productqueue'),('Approve product','approveproduct'),('Pending campaigns','campaignqueue'),('Review campaign','campaignaction'),('Buyer requests','requests'),('Open tickets','tickets'),('Reply to ticket','ticketreply')],
 'agent':[('Open tickets','tickets'),('Reply to ticket','ticketreply')],
}
OWNER_PAGES={'owner','accounts','products','finance','ads','staff','channels','branding','users'}
OWNER_ACTIONS={a for p in OWNER_PAGES for _,a in MENUS[p] if not a.startswith(('#','@'))} - {'productqueue','approveproduct','campaignqueue','campaignaction','requests','tickets','ticketreply'}
MOD_ACTIONS={'productqueue','approveproduct','campaignqueue','campaignaction','requests'}
SUP_ACTIONS={'tickets','ticketreply'}
ALL_ACTIONS={a for rows in MENUS.values() for _,a in rows if not a.startswith(('#','@'))}

def col(c): return c.mongodb.db.easy_ui_sessions
async def allowed(c,uid,action):
    if await c.mongodb.is_banned(uid): return False
    if action in OWNER_ACTIONS or action in OWNER_PAGES: return uid==c.owner
    if action in MOD_ACTIONS or action=='moderator': return await biz.approved(c,uid,'moderator')
    if action in SUP_ACTIONS or action=='agent': return await biz.approved(c,uid,'moderator') or await biz.approved(c,uid,'support')
    return True

PARENT={p:'owner' for p in OWNER_PAGES if p!='owner'}
PARENT.update({p:'home' for p in ('buyer','seller','affiliate','advertiser','support','owner','moderator','agent')})
TITLES={'home':'🏠 Main menu','owner':'⚙️ Admin panel','agent':'Support staff','staff':'Support & requests','ads':'Promotions','finance':'Revenue & settlements','branding':'Customization','channels':'Channels & files','users':'Users & access','products':'Products & coupons','accounts':'Accounts'}
NAV_TEXT={'Main menu':'home','🛒 Browse':'catalog','🔍 Search':'search','My purchases':'purchases','Seller account':'seller','Support':'support','Resume form':'resume','Cancel form':'cancel','Admin panel':'owner','Account':'buyer'}

def nav(page='home'):
    rows=[]
    if page!='home': rows.append([B('Back to '+TITLES.get(page,page.title()),callback_data='easy:page:'+page)])
    rows.append([B('🏠 Main menu',callback_data='easy:page:home')])
    return K(rows)

def action_page(action):
    return next((p for p,rows in MENUS.items() if any(a==action for _,a in rows)), 'home')
async def send(c,uid,text,markup=None):
    return await c.send_message(uid,text,parse_mode=ParseMode.DISABLED,reply_markup=markup)

async def menu(c,uid,page='home'):
    if page not in MENUS or not await allowed(c,uid,page): return await send(c,uid,'Access restricted.')
    await col(c).update_one({'_id':uid},{'$set':{'paused':True}})
    rows=list(MENUS[page])
    if page=='home':
        if uid==c.owner: rows.append(('Admin panel','#owner'))
        elif await biz.approved(c,uid,'moderator'): rows.append(('Moderator panel','#moderator'))
        elif await biz.approved(c,uid,'support'): rows.append(('Support staff','#agent'))
    buttons=[]
    for title,a in rows:
        cb=a[1:] if a.startswith('@') else 'easy:page:'+a[1:] if a.startswith('#') else 'easy:act:'+a
        buttons.append(B(title,callback_data=cb))
    keyboard=[buttons[i:i+2] for i in range(0,len(buttons),2)]
    draft=await col(c).find_one({'_id':uid,'expires':{'$gt':datetime.now(timezone.utc)}})
    if draft: keyboard.append([B('▶ Resume unfinished form',callback_data='easy:resume:form'),B('Discard',callback_data='easy:discard:'+draft['token'])])
    if page!='home': keyboard.append([B('‹ Back',callback_data='easy:page:'+PARENT.get(page,'home')),B('🏠 Home',callback_data='easy:page:home')])
    await send(c,uid,TITLES.get(page,page.title())+'\nChoose an action.',K(keyboard))

class CommandContext:
    """Adapt an authenticated private update to the existing command functions only."""
    def __init__(self,message,user,action,arg):
        self._message=message
        self.from_user=user
        self.chat=message.chat
        self.text='/'+action+(' '+arg if arg else '')
        self.command=[action]+arg.split()
        self.reply_to_message=None
    def __getattr__(self,name): return getattr(self._message,name)

async def execute(c,message,user,action,arg=''):
    if not await allowed(c,user.id,action): return await send(c,user.id,'Access restricted.',nav())
    if action in ('ban','unban') and arg==str(c.owner): return await send(c,user.id,'Owner cannot be modified.',nav())
    from plugins import shop, stars_payment, others, pro_users, admins, start, link_generator
    legacy={'search':shop.search_shop,'myvideos':shop.my_videos,'redeem':shop.redeem_command,'listcat':shop.list_categories_cmd,'setstarprice':stars_payment.set_star_price,'createcoupon':shop.create_coupon,'ban':others.ban,'unban':others.unban,'adddb':others.quick_add_db,'addpremium':pro_users.add_admin_command,'delpremium':pro_users.remove_admin_command,'premiumusers':pro_users.admin_list_command,'stats':admins.usage_cmd,'profile':start.my_plan,'removedb':others.quick_remove_db,'linkchannel':shop.link_channel}
    if action in ('genlink','batch'):
        from helper.helper_func import encode
        refs=[tuple(map(int,v.split(':'))) for v in arg.split()]
        channels={int(x) for x,v in getattr(c,'db_channels',{}).items() if v.get('is_active',True)}
        if c.db: channels.add(int(c.db))
        if any(ch not in channels for ch,_ in refs): return await send(c,user.id,'Storage channel is no longer available.',nav('channels'))
        payload='get-'+'-'.join(str(mid*abs(ch)) for ch,mid in refs)
        link=f'https://t.me/{c.username}?start={await encode(payload)}'
        return await send(c,user.id,'Your share link:\n'+link,nav('channels'))
    if action=='reviewapplication':
        target,role,decision=arg.split()
        if not await c.mongodb.db.business_roles.find_one({'_id':f'{target}:{role}','status':'pending'}): return await send(c,user.id,'Application is no longer pending.',nav('accounts'))
        action='role'
    if action=='removedb' and int(arg)==int(getattr(c,'primary_db_channel',None) or c.db or 0):
        return await send(c,user.id,'Switch to another primary storage channel before removing this one.',nav('channels'))
    if action=='linkchannel':
        key,ch=arg.split(); ch=int(ch)
        cat=await c.mongodb.get_category(key)
        if not cat: return await send(c,user.id,'Product no longer exists.',nav('products'))
        if cat.get('access_channel_id') and cat['access_channel_id']!=ch: return await send(c,user.id,'This product already has a channel. Changing existing access requires a reviewed migration.',nav('products'))
        if await c.mongodb.categories.find_one({'_id':{'$ne':cat['_id']},'access_channel_id':ch}): return await send(c,user.id,'That channel is already linked to another product.',nav('products'))
        member=await c.get_chat_member(ch,'me')
        privileges=getattr(member,'privileges',None)
        if not (getattr(privileges,'can_invite_users',False) and getattr(privileges,'can_restrict_members',False)):
            return await send(c,user.id,'Give the bot invite and restrict permissions first.',nav('products'))
    if action=='settext':
        key,text=arg.split('|',1)
        await c.mongodb.update_message_setting(key,text)
        c.messages[key]=text
        if key=='REPLY': c.reply_text=text
        await send(c,user.id,'Message saved.',nav())
        return
    if action=='search':
        key=token_hex(6)
        await c.mongodb.db.easy_ui_search.replace_one({'_id':user.id},{'_id':user.id,'token':key,'keyword':arg,'expires':datetime.now(timezone.utc)+timedelta(hours=24)},upsert=True)
        return await browse(c,user.id,0,arg,key)
    if action=='wishlist_list': action='wishlist'
    ctx=CommandContext(message,user,action,arg)
    try:
        if action in legacy: await legacy[action](c,ctx)
        elif action in biz.CMDS: await biz.biz_action(c,ctx)
        else: await send(c,user.id,'Action not available.')
    except Exception as exc:
        c.LOGGER(__name__,c.name).warning('Menu action %s: %s',action,type(exc).__name__)
        await send(c,user.id,'Operation failed. Check permissions and input before retrying.')
    page=action_page(action)
    if not await allowed(c,user.id,page): page='home'
    await send(c,user.id,'Choose your next action.',nav(page))

async def browse(c,uid,offset=0,keyword='',key=''):
    if not await allowed(c,uid,'home'): return await send(c,uid,'Access restricted.')
    offset=max(0,min(offset,1000000))
    query={'active':True}
    if keyword: query['name']={'$regex':re.escape(keyword),'$options':'i'}
    docs=await c.mongodb.categories.find(query).sort('_id',1).skip(offset).limit(9).to_list(9)
    page,more=page_options(docs)
    rows=[]
    for cat in page:
        price=cat.get('price_stars') or cat.get('price_cents') or 0
        name=unescape(str(cat.get('name','Product')))[:40]
        rows.append([B(f'{name} — {price} Stars' if price else f'{name} — Free',callback_data='cat_view_'+str(cat['_id']))])
    prefix='easy:results:'+key+':' if keyword else 'easy:catalog:'
    paging=[]
    if offset: paging.append(B('‹ Previous',callback_data=prefix+str(max(0,offset-8))))
    if more: paging.append(B('Next ›',callback_data=prefix+str(offset+8)))
    if paging: rows.append(paging)
    rows.append([B('🔍 Search',callback_data='easy:act:search'),B('🏠 Home',callback_data='easy:page:home')])
    title=f'Search: {keyword}' if keyword else '🛒 Catalog'
    await send(c,uid,f'{title} — Page {offset//8+1}\n'+('Choose a product.' if page else 'No products found.'),K(rows))

async def selections(c,uid,source,offset=0):
    limit=9
    def cursor(collection,query): return collection.find(query).sort('_id',1).skip(offset).limit(limit)
    D=c.mongodb.db
    cats=c.mongodb.categories
    if source in ('active','mine','pending','purchased'):
        query={'active':True} if source=='active' else {'seller_id':uid} if source=='mine' else {'approval':'pending'}
        if source=='purchased':
            from bson import ObjectId
            ids=await c.mongodb.orders.distinct('category_id',{'user_id':uid,'status':'paid'})
            query={'_id':{'$in':[ObjectId(str(x)) for x in ids if ObjectId.is_valid(str(x))]}}
        rows=await cursor(cats,query).to_list(limit)
        return [(str(x['_id']),unescape(str(x.get('name','Product')))[:45]) for x in rows]
    if source in ('applicants','application_roles'):
        rows=await cursor(D.business_roles,{'status':'pending'}).to_list(limit)
        return [(str(x['user_id'])+(':'+x['role'] if source=='application_roles' else ''),f"{x.get('name') or x['user_id']} ({x['role']})"[:45]) for x in rows]
    if source=='storage':
        return [(str(k),str(v.get('name') or k)[:45]) for k,v in sorted(getattr(c,'db_channels',{}).items())][offset:offset+limit]
    if source=='earnings':
        rows=await cursor(c.mongodb.orders,{'status':'paid','fulfilled':True,'$or':[{'seller_id':uid,'seller_stars':{'$gt':0}},{'affiliate_id':uid,'affiliate_stars':{'$gt':0}}]}).to_list(limit)
        return [(str(x['_id']),str(x['_id'])+' • '+str(x.get('seller_stars',0) if x.get('seller_id')==uid else x.get('affiliate_stars',0))+' Stars') for x in rows]
    table={'payouts':(D.business_payouts,{'status':'requested'}),'campaigns':(D.business_campaigns,{'status':'pending'}),'tickets':(D.business_tickets,{'status':'open'})}
    if source in table:
        collection,query=table[source]; rows=await cursor(collection,query).to_list(limit)
        return [(str(x['_id']),str(x.get('text') or x['_id'])[:45]) for x in rows]
    return []

async def prompt(c,uid,state):
    action=state['action']; values=state['values']; token=state['token']; fields=FORMS[action][1]
    title=next((title for rows in MENUS.values() for title,a in rows if a==action),action)
    labels=state.get('labels',[])
    controls=[B('‹ Back',callback_data=f'easy:back:{token}'),B('Cancel',callback_data=f'easy:cancel:{token}'),B('Home',callback_data='easy:page:home')]
    if len(values)==len(fields):
        try: assemble(action,values)
        except ValueError as e:
            await send(c,uid,str(e),K([controls])); return
        preview='\n'.join(f'{fields[i][0].split(".")[0][:65]}: {labels[i] if i<len(labels) else choice_label(fields[i][1],v)}' for i,v in enumerate(values)) or 'Restore default messages and disable promotions.'
        msg=await send(c,uid,f'{title} — Review\n\n'+preview[:3100],K([[B('✓ Confirm',callback_data=f'easy:confirm:{token}')],controls]))
    else:
        label,kind,choices,source=fields[len(values)]
        offset=state.get('offset',0)
        options=[(v,choice_label(kind,v)) for v in choices]
        more=False
        if source:
            page,more=page_options(await selections(c,uid,source,offset))
            options+=page
        rows=[[B(t,callback_data=f'easy:pick:{token}:{i}')] for i,(_,t) in enumerate(options)]
        paging=[]
        if offset: paging.append(B('‹ Previous',callback_data=f'easy:prev:{token}'))
        if more: paging.append(B('Next ›',callback_data=f'easy:next:{token}'))
        if paging: rows.append(paging)
        rows.append(controls)
        await col(c).update_one({'_id':uid,'token':token},{'$set':{'options':[v for v,_ in options],'option_labels':[t for _,t in options],'more':more}})
        hint='Tap an option or type your answer normally.' if options else 'Send your answer directly in this chat.'
        if source and not options: hint='No matching records on this page. Go back or enter the ID if you know it.'
        msg=await send(c,uid,f'{title} — Step {len(values)+1} of {len(fields)}\n\n{label}\n\n{hint}',K(rows))
    await col(c).update_one({'_id':uid,'token':token},{'$set':{'prompt_id':msg.id}})

async def begin(c,message,user,action,replace=False):
    uid=user.id
    if action not in ALL_ACTIONS or not await allowed(c,uid,action): return await send(c,uid,'Access restricted.',nav())
    if action=='addproduct' and not await biz.approved(c,uid,'seller'): return await send(c,uid,'Apply for a seller account first.',K([[B('Apply',callback_data='easy:act:applyseller')],[B('Main menu',callback_data='easy:page:home')]]))
    if action=='newcampaign' and not await biz.approved(c,uid,'advertiser'): return await send(c,uid,'Apply as advertiser first.',K([[B('Apply',callback_data='easy:act:applyadvertiser')]]))
    if action not in FORMS:
        await col(c).update_one({'_id':uid},{'$set':{'paused':True}})
        return await execute(c,message,user,action)
    old=await col(c).find_one({'_id':uid,'expires':{'$gt':datetime.now(timezone.utc)}})
    if old and not replace:
        await col(c).update_one({'_id':uid,'token':old['token']},{'$set':{'paused':True}})
        return await send(c,uid,'You have an unfinished form. Resume it or start a new one.',K([[B('Resume form',callback_data='easy:resume:form')],[B('Discard & start new',callback_data=f'easy:replace:{old["token"]}:{action}')],[B('Home',callback_data='easy:page:home')]]))
    state={'_id':uid,'action':action,'values':[],'labels':[],'offset':0,'paused':False,'token':token_hex(6),'expires':datetime.now(timezone.utc)+timedelta(hours=24)}
    await col(c).replace_one({'_id':uid},state,upsert=True)
    await prompt(c,uid,state)

async def change(c,uid,state,values,labels=None,offset=0):
    new={**state,'values':values,'labels':labels if labels is not None else state.get('labels',[])[:len(values)],'offset':offset,'paused':False,'token':token_hex(6),'expires':datetime.now(timezone.utc)+timedelta(hours=24)}
    new.pop('options',None); new.pop('option_labels',None); new.pop('prompt_id',None); new.pop('more',None)
    r=await col(c).replace_one({'_id':uid,'token':state['token']},new)
    if r.modified_count: await prompt(c,uid,new)

async def accept(c,uid,state,value,label=None):
    if not await allowed(c,uid,state['action']): return await send(c,uid,'Access restricted.',nav())
    fields=FORMS[state['action']][1]; values=state['values']
    if len(values)>=len(fields): return
    try:
        value=validate(fields[len(values)][1],value)
        if state['action']=='batch' and values: assemble('batch',values+[value])
        if state['action']=='commission' and values and int(values[0])+int(value)>100: raise ValueError('Combined commissions must be 100% or less.')
    except ValueError as e: return await send(c,uid,str(e)+' Try again in this chat or use the buttons.')
    await change(c,uid,state,values+[value],state.get('labels',values[:])+[label or choice_label(fields[len(values)][1],value)])

@Client.on_callback_query(filters.regex(r'^easy:'),group=-2)
async def easy_callback(c,q):
    if not q.message or q.message.chat.id!=q.from_user.id: return await q.answer('Private chat only.',show_alert=True)
    uid=q.from_user.id
    if await c.mongodb.is_banned(uid): return await q.answer('Access restricted.',show_alert=True)
    await q.answer()
    try:
        parts=q.data.split(':'); op=parts[1]; key=parts[2]
        if op=='page': return await menu(c,uid,key)
        if op=='act': return await begin(c,q.message,q.from_user,key)
        if op=='catalog':
            await col(c).update_one({'_id':uid},{'$set':{'paused':True}})
            return await browse(c,uid,int(key))
        if op=='results':
            search=await c.mongodb.db.easy_ui_search.find_one({'_id':uid,'token':key,'expires':{'$gt':datetime.now(timezone.utc)}})
            if not search: return await send(c,uid,'Search expired. Start another search.',nav())
            await col(c).update_one({'_id':uid},{'$set':{'paused':True}})
            return await browse(c,uid,int(parts[3]),search['keyword'],key)
        if op in ('resume','discard'):
            state=await col(c).find_one({'_id':uid,'expires':{'$gt':datetime.now(timezone.utc)}})
            if op=='discard':
                if state and state['token']==key: await col(c).delete_one({'_id':uid,'token':key})
                return await menu(c,uid)
            if state and await allowed(c,uid,state['action']): return await change(c,uid,state,state['values'])
            return await menu(c,uid)
        state=await col(c).find_one({'_id':uid,'token':key,'expires':{'$gt':datetime.now(timezone.utc)}})
        if op=='replace' and state: return await begin(c,q.message,q.from_user,parts[3],replace=True)
        if not state: return await send(c,uid,'This menu has expired or was already used.',nav())
        if not await allowed(c,uid,state['action']): return await send(c,uid,'Access restricted.',nav())
        if state.get('paused'): return await send(c,uid,'Form paused. Use Resume form.',nav())
        if op in ('next','prev'):
            if op=='next' and not state.get('more'): return
            return await change(c,uid,state,state['values'],offset=max(0,state.get('offset',0)+(8 if op=='next' else -8)))
        if op=='cancel':
            await col(c).delete_one({'_id':uid,'token':key}); return await menu(c,uid)
        if op=='back':
            if not state['values']: return await menu(c,uid)
            return await change(c,uid,state,state['values'][:-1])
        if op=='pick':
            i=int(parts[3]); opts=state.get('options',[])
            if 0<=i<len(opts): return await accept(c,uid,state,opts[i],(state.get('option_labels') or opts)[i])
        if op=='confirm':
            arg=assemble(state['action'],state['values'])
            # Atomically consume the confirmation before calling legacy code.
            if (await col(c).delete_one({'_id':uid,'token':key,'paused':{'$ne':True}})).deleted_count:
                return await execute(c,q.message,q.from_user,state['action'],arg)
    except Exception as e:
        c.LOGGER(__name__,c.name).warning('Menu callback: %s',type(e).__name__)
        await send(c,uid,'Unable to complete action. Open the main menu and try again.',nav())

@Client.on_message(filters.private & (filters.command(['menu','cancel','resume']) | (filters.regex(r'^(Main menu|🛒 Browse|🔍 Search|My purchases|Seller account|Support|Resume form|Cancel form|Admin panel|Account)$') & ~filters.reply)),group=-2)
async def easy_navigation(c,m):
    uid=m.from_user.id
    if await c.mongodb.is_banned(uid):
        await send(c,uid,'Access restricted.'); return m.stop_propagation()
    action=NAV_TEXT.get(m.text,m.command[0] if m.text.startswith('/') else 'home')
    if action=='resume':
        state=await col(c).find_one({'_id':uid,'expires':{'$gt':datetime.now(timezone.utc)}})
        if state and await allowed(c,uid,state['action']): await change(c,uid,state,state['values'])
        else: await menu(c,uid)
    elif action=='cancel':
        await col(c).delete_one({'_id':uid}); await menu(c,uid)
    elif action=='catalog':
        await col(c).update_one({'_id':uid},{'$set':{'paused':True}})
        await browse(c,uid,0)
    elif action in ('search','purchases'): await begin(c,m,m.from_user,action)
    else: await menu(c,uid,action if action in MENUS else 'home')
    m.stop_propagation()

@Client.on_message(filters.private & (filters.text | filters.forwarded | filters.reply) & ~filters.regex(r'^/'),group=-1)
async def easy_reply(c,m):
    if not m.from_user: return
    uid=m.from_user.id; replied=getattr(m,'reply_to_message',None)
    state=await col(c).find_one({'_id':uid,'expires':{'$gt':datetime.now(timezone.utc)},'paused':{'$ne':True}})
    if not state: return
    # Replies to older prompts must never be treated as answers to a newer step.
    if replied and replied.id!=state.get('prompt_id'):
        await send(c,uid,'This is not the current question. Use Resume form for the latest step.')
        return m.stop_propagation()
    if not await allowed(c,uid,state['action']):
        await send(c,uid,'Access restricted.'); return m.stop_propagation()
    fields=FORMS[state['action']][1]; index=len(state['values'])
    if index>=len(fields):
        await send(c,uid,'Tap Confirm, Back or Cancel on your review message.'); return m.stop_propagation()
    try:
        kind=fields[index][1]; value=m.text or ''; label=None
        forwarded=getattr(m,'forward_from_chat',None)
        if kind=='channel' and forwarded: value=str(forwarded.id); label=forwarded.title or value
        elif kind=='post':
            from helper.helper_func import get_message_id
            result=await get_message_id(c,m)
            if not result or not all(result): raise ValueError('Forward a post from a registered storage channel or paste its post link.')
            mid,ch=result; value=f'{ch}:{mid}'; label=f'Post {mid} in {getattr(forwarded,"title",None) or ch}'
        elif kind=='user' and getattr(m,'forward_from',None): value=str(m.forward_from.id)
        if state['action']=='search':
            value=validate(kind,value)
            if (await col(c).delete_one({'_id':uid,'token':state['token']})).deleted_count: await execute(c,m,m.from_user,'search',value)
        else: await accept(c,uid,state,value,label)
    except ValueError as e: await send(c,uid,str(e)+' Try again.')
    except Exception as e:
        c.LOGGER(__name__,c.name).warning('Form input: %s',type(e).__name__)
        await send(c,uid,'Could not save input. Tap Resume form.')
    m.stop_propagation()


@Client.on_message(filters.private & filters.regex(r'^/'),group=-3)
async def pause_on_command(c,m):
    if not m.from_user: return
    text=m.text or ''
    if not text: return
    name=text.split(maxsplit=1)[0].partition('@')[0].lower()
    if name not in ('/resume','/cancel','/menu'):
        await col(c).update_one({'_id':m.from_user.id},{'$set':{'paused':True}})

@Client.on_callback_query(~filters.regex(r'^easy:'),group=-3)
async def pause_on_legacy_button(c,q):
    if q.message and q.message.chat.id==q.from_user.id:
        await col(c).update_one({'_id':q.from_user.id},{'$set':{'paused':True}})

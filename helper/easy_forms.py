"""Copyright push2006 (modifications). Pure validation and form definitions."""
import re
from urllib.parse import urlparse

# Each field: prompt, validator, optional choices, optional selection source.
def field(prompt, kind='text', choices=(), source=''):
    return (prompt,kind,choices,source)
F=field
FORMS={
 'applyseller': ('|', [F('Enter your store name','name')]),
 'addproduct': ('|',[F('Enter the product name','name'),F('Set the price in Stars','stars',('50','100','250','500','1000')),F('Choose access duration in days (0 = lifetime)','days',('0','7','30','90','365')),F('Forward a post from your private channel, or enter its numeric ID. You must own the channel; the bot needs invite and ban permissions.','channel')]),
 'search': (' ',[F('Enter a search keyword','name')]),
 'redeem': (' ',[F('Enter the coupon code','word')]),
 'wishlist': (' ',[F('Select a product to save or remove','oid',source='active')]),
 'review': ('|',[F('Select a purchased product','oid',source='purchased'),F('Choose a rating','rating',('1','2','3','4','5')),F('Write your review','review')]),
 'buyerrequest': (' ',[F('Describe what you need','long')]),
 'ticket': (' ',[F('Describe your issue','long')]),
 'hideproduct': (' ',[F('Select the product to hide','oid',source='mine')]),
 'payout': (' ',[F('Select an eligible order','oid',source='earnings')]),
 'newcampaign': ('|',[F('Enter promotional text','review'),F('Enter the HTTPS destination URL','url'),F('Choose campaign duration (days)','campaign_days',('1','7','14','30','90'))]),
 'role': (' ',[F('Select an applicant or enter their Telegram user ID','user',source='applicants'),F('Select account role','role',('seller','affiliate','advertiser','moderator','support')),F('Choose a decision','decision',('approve','reject'))]),
 'approveproduct': (' ',[F('Select a pending product','oid',source='pending')]),
 'commission': (' ',[F('Platform commission percentage','percent',('0','10','15','20','30')),F('Affiliate commission percentage','percent',('0','5','10','15','20'))]),
 'settle': (' ',[F('Select a payout request','payoutid',source='payouts'),F('Record the outcome (this does not transfer money)','settle',('paid','rejected')),F('Enter settlement reference or rejection reason','reference')]),
 'campaignaction': (' ',[F('Select a submitted campaign','oid',source='campaigns'),F('Choose a decision','decision',('approve','reject'))]),
 'promotions': (' ',[F('Show approved promotions?','toggle',('on','off'))]),
 'ticketreply': ('|',[F('Select an open ticket','oid',source='tickets'),F('Enter your reply','long')]),
 'settext': ('|',[F('Choose the message to edit','textkey',('START','ABOUT','REPLY','FSUB','SHORT_MSG')),F('Enter new message text','long')]),
 'setprofile': (' ',[F('Select Telegram profile field','profile',('name','description','about')),F('Enter the new text (a dash clears description/about)','review')]),
 'setstarprice': (' ',[F('Select a catalog product','oid',source='active'),F('Choose Stars price','stars',('50','100','250','500','1000'))]),
 'createcoupon': ('|',[F('Enter coupon code','word'),F('Select a catalog product','oid',source='active'),F('Number of uses','uses',('1','5','10','50','100')),F('Access duration in days (0 = lifetime)','days',('0','7','30','90','365'))]),
 'ban': (' ',[F('Enter the Telegram user ID to ban','user')]),
 'unban': (' ',[F('Enter the Telegram user ID to unban','user')]),
 'adddb': (' ',[F('Forward a storage-channel post or enter its numeric ID','channel')]),
 'addpremium': (' ',[F('Enter Telegram user ID','user'),F('Choose membership duration','duration',('1 day','1 week','1 month','1 year','permanent'))]),
 'delpremium': (' ',[F('Enter Telegram user ID','user')]),
 'resetbranding': (' ',[]),
 'genlink': (' ',[F('Forward a post from a configured storage channel, or paste its Telegram post link.','post')]),
 'batch': (' ',[F('Forward the FIRST post or paste its Telegram post link.','post'),F('Forward the LAST post from the same channel or paste its Telegram post link.','post')]),
 'reviewapplication': (' ',[F('Select a pending application','application',source='application_roles'),F('Choose a decision','decision',('approve','reject'))]),
 'removedb': (' ',[F('Select the storage channel to remove','channel',source='storage')]),
 'linkchannel': (' ',[F('Select a catalog product','oid',source='active'),F('Forward a post from the access channel or enter its numeric ID','channel')]),
}

def validate(kind, value):
    v=str(value).strip()
    if not v or '\x00' in v: raise ValueError('Enter a value.')
    # Reject separators used by the legacy command parser, rather than reinterpret input.
    if '|' in v: raise ValueError('Please remove the | character.')
    limits={'name':60,'review':500,'long':1500,'reference':200,'word':60}
    if kind in limits:
        if len(v)>limits[kind] or (kind=='word' and not re.fullmatch(r'[A-Za-z0-9_-]+',v)): raise ValueError('Invalid or overly long text.')
        return v
    ranges={'stars':(1,100000),'days':(0,3650),'campaign_days':(1,90),'rating':(1,5),'percent':(0,100),'uses':(1,100000),'user':(1,2**63-1),'channel':(-2**63+1,-1)}
    if kind in ranges:
        lo,hi=ranges[kind]
        if not re.fullmatch(r'-?[0-9]{1,19}',v) or not lo<=int(v)<=hi: raise ValueError(f'Enter a whole number from {lo} to {hi}.')
        return str(int(v))
    if kind=='post' and re.fullmatch(r'-[0-9]{1,19}:[0-9]{1,10}',v):
        channel,mid=map(int,v.split(':'))
        if -2**63<channel<0 and 0<mid<=2147483647: return f'{channel}:{mid}'
    if kind=='application' and re.fullmatch(r'[0-9]{1,19}:(seller|affiliate|advertiser|moderator|support)',v):
        uid,role=v.split(':'); return validate('user',uid)+':'+role
    if kind=='oid' and re.fullmatch(r'[0-9a-fA-F]{24}',v): return v.lower()
    if kind=='payoutid' and re.fullmatch(r'[0-9a-fA-F]{24}:(seller|affiliate)',v): return v.lower()
    if kind=='url':
        parsed=urlparse(v)
        if parsed.scheme=='https' and parsed.hostname and not parsed.username and not parsed.password and not any(c.isspace() for c in v) and len(v)<=1000: return v
    enums={'textkey':('START','ABOUT','REPLY','FSUB','SHORT_MSG'),'role':('seller','affiliate','advertiser','moderator','support'),'decision':('approve','reject'),'settle':('paid','rejected'),'toggle':('on','off'),'profile':('name','description','about'),'duration':('1 day','1 week','1 month','1 year','permanent')}
    if v in enums.get(kind,()): return v
    raise ValueError('Invalid value. Choose an available option or check your input.')

def assemble(action, values):
    sep, fields=FORMS[action]
    if len(fields)!=len(values): raise ValueError('Incomplete form.')
    clean=[validate(f[1],v) for f,v in zip(fields,values)]
    if action=='commission' and sum(map(int,clean))>100: raise ValueError('Combined commissions cannot exceed 100%.')
    if action=='addpremium' and clean[-1]=='permanent': clean.pop()
    if action=='setprofile' and len(clean[1])>{'name':64,'description':500,'about':120}[clean[0]]: raise ValueError('Text is too long for this profile field.')
    if action=='batch':
        first,last=[tuple(map(int,v.split(':'))) for v in clean]
        if first[0]!=last[0] or not 0<=last[1]-first[1]<100: raise ValueError('Use the same channel, in order, with at most 100 posts per batch.')
    if action=='reviewapplication': return clean[0].replace(':',' ',1)+' '+clean[1]
    return sep.join(clean)


def neutralize(text):
    cleaned=re.sub(r'(?i)\b(?:push2006|business\s+os)\b','',text)
    return cleaned.strip(' \t•–—') if cleaned!=text else text


CHOICE_LABELS={'0':'0','approve':'Approve','reject':'Reject','paid':'Mark paid','rejected':'Reject','on':'Enable','off':'Disable','START':'Welcome message','ABOUT':'About message','REPLY':'Default reply','FSUB':'Required channel message','SHORT_MSG':'Short link message','name':'Bot display name','description':'Bot description','about':'Short About text'}

def choice_label(kind,value):
    if kind=='days': return 'Lifetime' if value=='0' else value+' days'
    if kind=='campaign_days': return value+' days'
    if kind=='stars': return value+' Stars'
    if kind=='percent': return value+'%'
    if kind=='rating': return value+' / 5'
    return CHOICE_LABELS.get(value,value)

def page_options(items, size=8):
    return items[:size], len(items)>size

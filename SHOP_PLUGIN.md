# Catalog = private channel (simple model)

You upload files **yourself** in a private channel.
The bot does **not** need `/addcontent`.

## Flow

### Admin (once per pack)
1. `/addcat Premium|499|30` → $4.99 for 30 days (`0` price = free, `0` days = lifetime)
2. Create a **private** Telegram channel
3. Add the bot as **admin** (Invite Users + Ban Users)
4. Post all your files in that channel (manually)
5. `/linkchannel CATEGORY_ID -100CHANNEL_ID`

### User
1. `/start` → tap **Catalog**
2. Pick a pack → pay (crypto) or free
3. Bot sends a **one-time join link**
4. When time ends, bot **removes** them from the channel

## Commands

| Who | Command | Meaning |
|-----|---------|---------|
| Admin | `/addcat Name\|cents\|days` | Create priced pack |
| Admin | `/setprice ID cents` | Change price |
| Admin | `/linkchannel ID -100…` | Bind pack → your channel |
| Admin | `/pending` + `/confirm ORDER` | Crypto payments |
| User | Catalog button / `/catalog` | Browse packs |
| User | `/redeem CODE` | Coupon |

`/addcontent` is **not used**. Reply to it and the bot tells you the setup above.

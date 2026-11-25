# Telegram Marketplace — Easy UI

Full source-tree upgrade of the supplied Telegram file-store project. Modifications copyright push2006; existing upstream attribution and GPL license retained. This is a GitHub-uploadable **integration-test candidate**, not a verified production release.

## Install on Render
1. Extract the ZIP. Upload **all extracted files and folders**, including `plugins`, `helper`, `tests`, `.github`, Dockerfile and hidden configuration files, to a new private GitHub repository. Do not mix with earlier previews.
2. Keep the old service and repository. Use a separate test bot token and a copied MongoDB database first. Revoke any previously exposed tokens, credentials, shortener keys and MTProto sessions.
3. Create a Render Docker Web Service from the new repository (free plan). Health path `/`. Environment variables below. No manual start/build command needed. The HTTP endpoint only checks the web service; Telegram login can still fail. Free service may sleep; background jobs are not reliable 24/7.

| Variable | Value |
|---|---|
| TOKEN | fresh bot token from BotFather |
| API_ID / API_HASH | your Telegram application credentials (original Hydrogram architecture) |
| OWNER_ID | your numeric Telegram user ID |
| DB_URI | MongoDB connection URI |
| DB_NAME | database name; use a copy first, exact original name only after testing |
| DB_CHANNEL | optional existing storage channel ID, or 0 to set up in chat |
| ADMINS | optional trusted numeric IDs separated by spaces |
| ENABLE_EXPIRY | 0 initially; 1 only after testing channel-expiry behavior |
| PORT | Render supplies this; default 10000 |

4. Deploy; check logs for Bot Started. Run `/start`, `/admin`, `/business`, `/db`. Give the bot the necessary channel rights before configuring channels. Use `/adddb` or Settings to manage file storage. Never put paid content in a legacy publicly linkable file-storage channel.
5. Test actual invoices, join approvals, expiry, old file and batch links, coupon redemption, permissions, redeployment persistence and seller accounting before switching live traffic. Do not run two instances using the same token.

## Easy chat interface
After `/start`, tap Main menu. The owner sees Admin panel. Buyers, sellers, affiliates, advertisers and approved staff have separate menus. Tap an action, select a listed option or reply to the answer prompt, then confirm. A form lasts 24 hours; Resume form restores it after a restart. Back and Cancel work on new forms. The first 12 matching records are shown, with manual ID entry for others. Forward a channel post at the channel step or enter its ID. Product creation is for private-channel access, not individual paid file upload. The original file and batch link workflows and advanced settings remain available. Some legacy actions (e.g. media broadcast) still use commands; commands below remain optional shortcuts. No new environment variables are needed.

Default chat branding is neutral; prior occurrences of the two old brand labels in stored message text are removed on startup and originals archived. User-supplied product/channel names, URLs and official Telegram profile are not comprehensively rewritten. Use Admin panel → Customization → Edit Telegram profile to set a name, description or About. If the username, profile photo, or localized description still contains the old name, update those through BotFather. Existing sent messages are not rewritten. Source copyright and upstream license are retained.

## Optional command shortcuts
- `/business` opens role menus; `/admin` is owner dashboard. `/catalog`, `/myvideos`, `/batch`, `/genlink`, `/nbatch`, `/db`, `/redeem`, `/createcoupon`, `/broadcast`, `/profile` and original plugins remain in the tree.
- `/applyseller Store name`, `/applyaffiliate`, `/applyadvertiser`; owner `/applications`, `/role USER_ID seller|affiliate|advertiser|moderator|support approve|reject`.
- `/addproduct Name|Stars|Days|ChannelID` submits a private-channel product. Seller must own channel and bot must be admin with invite/restrict rights. `/productqueue`, `/approveproduct ID`, `/myproducts`, `/store USER_ID`, `/hideproduct ID`.
- `/commission PLATFORM% AFFILIATE%`; `/referral`, `/earnings`, `/affiliateearnings`, `/payout ORDER_ID`, `/payouts`, `/settle ID paid|rejected reference`. Earnings are gross Stars allocation, not transferable balances. Owner records external/manual settlements only after actual funds, fees, refunds, taxes and compliance are checked. No automated payout.
- `/newcampaign Text|HTTPS_URL|Days`, `/campaignqueue`, `/campaignaction ID approve|reject`, `/promotions on|off`, `/campaigns`, `/mycampaigns`. Promotions disabled by default; campaign payment not implemented.
- `/ticket MESSAGE`, `/mytickets`, `/tickets`, `/ticketreply ID|reply`, `/buyerrequest MESSAGE`, `/requests`, `/purchases`, `/wishlist [ID]`, `/review ID|1-5|text`, `/analytics`, `/exportorders`, `/audit`.
- `/setprofile name|description|about TEXT` changes Telegram profile default language using Bot API; `-` clears text where Telegram supports it. Other language variants, username, and profile picture may require BotFather. `/resetbranding` restores neutral chat text, disables shortener and promotions. Settings buttons edit saved start/about/FSUB/reply text. Owner can manage admins; initial DB setup can be done through chat.

## Data and safety
Existing collections and IDs retained. On first start the old saved welcome settings, force-subscription list and admins are archived in `business_settings_archive`, and neutral defaults, environment admins and disabled force-subscription/shortener settings are installed. Existing DB channels, categories, orders, coupons, user records and membership records are retained. Review all existing channels/catalogs for authorized ownership and content. No embedded credentials or session files included. Automated cleanup and destructive chat cleanup are disabled. Existing legacy file links are **not cryptographically authenticated**; keep storage separate from paid channels; old links remain dependent on their original storage channels and bot username. New Stars checkout validates invoice buyer, amount, currency and status; charge IDs persisted. Repeated payment access grant uses fixed payment timestamp. Manual reconciliation may be needed for duplicate or unmatched charges and refunds. Historic payments and existing invites require review. Digital goods new payments use Stars only. Legacy non-Stars order confirmation is owner-only. No guaranteed refund automation.

## Verification and limitations
See TEST_REPORT.txt. Dependency install was blocked by DNS/network restrictions in the execution environment; live Hydrogram, Telegram Stars, MongoDB migration and Render tests were not performed. The original MTProto authentication dependency remains (with in-memory sessions); authentication failures can recur. CI runs dependency install and an import check on GitHub. Syntax and pure-rule tests passed; neither proves live behavior. No claim of every requested feature implemented: remaining work includes automated refunds, paid advertisements, recurring native subscription billing, full backup/restore through chat, per-file paid marketplace products, carts, auctions, flash sales, full multilingual support, campaign metrics, seller membership plans, a full service bidding marketplace, all-channel-role configuration and complete button-only workflows for remaining legacy commands. No public seller registration or payments should be enabled on production before live tests. Sell only authorized lawful content.


### Easy UI incremental update

Send `/start` to refresh the bottom keyboard. Browse and search show eight results at a time. Enter answers directly into chat; no reply gesture is needed. Use Back, Home, Resume form or Cancel form. Home pauses a draft, which expires after 24 hours. A new form asks before replacing an existing draft. Product and channel choices show readable labels. Batch links accept two posts from the same storage channel, up to 100 posts. Approval selects the specific pending role. Legacy commands remain available. No new environment variables.

This patch does not add missing payment, payout or advertising infrastructure, and does not change the legacy share-link encoding. Test on a copied database before deploying. Existing official Telegram profile names must still be changed separately through the customization menu or BotFather.

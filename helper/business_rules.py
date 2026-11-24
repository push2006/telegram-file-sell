"""Copyright push2006. Pure validation and accounting rules."""

def split_stars(amount, platform_pct, affiliate_pct=0):
    if not all(type(v) is int for v in (amount, platform_pct, affiliate_pct)) or amount < 1 or min(platform_pct, affiliate_pct) < 0 or platform_pct + affiliate_pct > 100:
        raise ValueError('Invalid amount or rates')
    platform = amount * platform_pct // 100
    affiliate = amount * affiliate_pct // 100
    return {'seller_stars': amount-platform-affiliate, 'platform_stars': platform, 'affiliate_stars': affiliate}


def matches_payment(order, user_id, amount, currency):
    return bool(order and order.get('method') == 'stars' and order.get('user_id') == user_id and order.get('amount_cents') == amount and currency == 'XTR' and type(amount) is int and amount > 0)


def can_manage(seller, user, owner):
    return user == owner or (seller is not None and seller == user)

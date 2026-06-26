"""
FinanceAI Insights Engine
16 insight templates across 6 categories:
Behavior, Trend, Anomaly, Optimization, Fixed, Win
"""

from collections import defaultdict
from statistics import mean, stdev
from datetime import date, datetime, timedelta
import re

# ── Seasonal context for US ──
SEASONAL_CONTEXT = {
    1:  {'label': 'January',  'notes': ['Insurance renewals common', 'Gym memberships spike (New Year)']},
    2:  {'label': 'February', 'notes': ['Valentines Day spending']},
    3:  {'label': 'March',    'notes': ['Tax prep services appear', 'Spring travel begins']},
    4:  {'label': 'April',    'notes': ['Tax season', 'Spring cleaning purchases']},
    5:  {'label': 'May',      'notes': ['Memorial Day travel', 'Summer prep']},
    6:  {'label': 'June',     'notes': ['Summer begins', 'AC bills rise', 'Travel peaks']},
    7:  {'label': 'July',     'notes': ['Peak summer spending', 'Utility bills highest']},
    8:  {'label': 'August',   'notes': ['Back to school', 'AC bills still high']},
    9:  {'label': 'September','notes': ['Fall transition', 'Streaming spikes (new seasons)']},
    10: {'label': 'October',  'notes': ['Halloween', 'Streaming subscriptions spike']},
    11: {'label': 'November', 'notes': ['Holiday shopping begins', 'Black Friday']},
    12: {'label': 'December', 'notes': ['Peak holiday spending', 'Annual fee renewals']},
}

SUBSCRIPTION_OVERLAPS = [
    (['spotify', 'apple music', 'youtube music', 'tidal'], 'music streaming', 'You only need one music service'),
    (['netflix', 'hulu', 'disney', 'hbo', 'paramount', 'peacock'], 'video streaming', 'Disney Bundle covers Disney+, Hulu and ESPN+ for $13.99/mo'),
    (['spotify', 'apple'], 'Apple One bundle', 'Apple One includes Apple Music, TV+, Arcade and iCloud'),
    (['youtube', 'spotify'], 'YouTube Premium', 'YouTube Premium includes YouTube Music — Spotify may be redundant'),
]

fmt = lambda n: '$' + str(round(abs(n or 0)))

def get_month_num(month_str):
    try:
        return int(month_str.split('-')[1])
    except:
        return 0

def group_by_month(transactions):
    monthly = defaultdict(list)
    for t in transactions:
        m = str(t.get('transaction_date') or '')[:7]
        if m:
            monthly[m].append(t)
    return dict(monthly)

def group_by_category(transactions):
    cats = defaultdict(list)
    for t in transactions:
        cats[t.get('category') or 'Other'].append(t)
    return dict(cats)

def group_by_merchant(transactions):
    merchants = defaultdict(list)
    for t in transactions:
        key = (t.get('description') or '')[:12].lower().strip()
        if key:
            merchants[key].append(t)
    return dict(merchants)

def total_spend(txs):
    return sum(abs(t.get('amount', 0) or 0) for t in txs
               if t.get('transaction_type') == 'expense' and (t.get('amount') or 0) < 0)

def var_spend(txs):
    return sum(abs(t.get('amount', 0) or 0) for t in txs
               if t.get('transaction_type') == 'expense'
               and (t.get('amount') or 0) < 0
               and not t.get('is_fixed')
               and t.get('category') not in ('Transfer','Payment','Income'))

def var_txs(txs):
    return [t for t in txs
            if t.get('transaction_type') == 'expense'
            and (t.get('amount') or 0) < 0
            and not t.get('is_fixed')
            and t.get('category') not in ('Transfer','Payment','Income')]

def expense_txs(txs):
    return [t for t in txs
            if t.get('transaction_type') == 'expense'
            and (t.get('amount') or 0) < 0]

def is_sub(t):
    cat = (t.get('category') or '').lower()
    desc = (t.get('description') or '').lower()
    sub_keywords = ['netflix','spotify','hulu','disney','apple','youtube','hbo',
                    'paramount','peacock','amazon prime','audible','dropbox',
                    'icloud','adobe','microsoft','google one','runna','paddle',
                    'wmt plus','walmart plus']
    return cat in ('subscriptions','subscription','streaming') or \
           any(k in desc for k in sub_keywords)


def generate_insights(all_txs, budget, selected_month=None):
    """
    Main entry point. Returns ranked list of insights.
    all_txs: list of transaction dicts
    budget: monthly budget amount
    selected_month: "2026-03" format, defaults to latest
    """
    insights = []

    exp = expense_txs(all_txs)
    if not exp:
        return []

    monthly = group_by_month(exp)
    all_months = sorted(monthly.keys())
    n_months = len(all_months)

    # Determine current month
    current_month = selected_month or (all_months[-1] if all_months else None)
    if not current_month:
        return []

    prev_month = all_months[all_months.index(current_month) - 1] \
        if current_month in all_months and all_months.index(current_month) > 0 else None

    current_txs = monthly.get(current_month, [])
    prev_txs = monthly.get(prev_month, []) if prev_month else []

    if not current_txs:
        return []

    # Detect partial data — compare transaction count to previous month
    today = date.today()
    is_current_month = today.strftime('%Y-%m') == current_month
    current_tx_count = len(current_txs)
    prev_tx_count = len(prev_txs) if prev_txs else 0

    # Partial if: current month has < 40% of previous month's transactions
    # OR current month has fewer than 10 transactions total
    is_partial = (
        current_tx_count < 10 or
        (prev_tx_count > 0 and current_tx_count < prev_tx_count * 0.4)
    )

    # For partial months — only show upload nudge
    if is_partial:
        return [{
            'id': 'PARTIAL',
            'type': 'info',
            'color': '#475569',
            'icon': '📅',
            'title': f'Only {current_tx_count} transactions found for this month',
            'body': 'Upload your complete statement for accurate insights and spending comparisons.',
            'score': 10,
            'action': 'Upload complete statement',
            'action_filter': None,
        }]

    current_var = var_spend(current_txs)
    prev_var = var_spend(prev_txs) if prev_txs else 0
    current_month_num = get_month_num(current_month)

    # Category maps
    curr_cats = group_by_category(current_txs)
    prev_cats = group_by_category(prev_txs) if prev_txs else {}

    # Merchant maps
    curr_merchants = group_by_merchant(current_txs)
    hist_merchants = group_by_merchant(exp)  # all time

    # ── B1: Delivery frequency ──
    dining_txs = [t for t in current_txs
                  if t.get('category') in ('Food & Dining',)]
    dining_count = len(dining_txs)
    today_day2 = date.today().day if date.today().strftime('%Y-%m') == current_month else 28
    dining_threshold = max(4, round(6 * today_day2 / 30))  # scale by days elapsed
    if dining_count >= dining_threshold:
        dining_total = total_spend(dining_txs)
        avg_per_order = dining_total / dining_count if dining_count else 0
        target = max(dining_count - 3, int(dining_count * 0.75))
        savings = (dining_count - target) * avg_per_order
        freq_days = round(30/dining_count)
        if freq_days <= 1:
            freq_str = 'almost every day'
        elif freq_days == 2:
            freq_str = 'every other day'
        else:
            freq_str = f'every {freq_days} days'
        insights.append({
            'id': 'B1',
            'type': 'behavior',
            'color': '#f59e0b',
            'icon': '🍽️',
            'title': f'You dined out {dining_count} times this month — {freq_str}',
            'body': f'Avg {fmt(avg_per_order)} per visit. Cutting to {target} times saves ~{fmt(savings)}/mo.',
            'score': 6 + (1 if dining_count > 10 else 0),
            'action': 'View dining transactions',
            'action_filter': 'Food & Dining',
        })

    # ── B2: Weekend spending spike ──
    weekend_txs = [t for t in current_txs
                   if datetime.strptime(t['transaction_date'], '%Y-%m-%d').weekday() >= 5
                   if t.get('transaction_date')]
    weekday_txs = [t for t in current_txs
                   if datetime.strptime(t['transaction_date'], '%Y-%m-%d').weekday() < 5
                   if t.get('transaction_date')]
    weekend_days = 8  # approx weekends in a month
    weekday_days = 22
    if weekend_txs and weekday_txs:
        wknd_daily = total_spend(weekend_txs) / weekend_days
        wkdy_daily = total_spend(weekday_txs) / weekday_days
        if wknd_daily > wkdy_daily * 1.3:
            ratio = round(wknd_daily / wkdy_daily, 1)
            insights.append({
                'id': 'B2',
                'type': 'behavior',
                'color': '#f59e0b',
                'icon': '📅',
                'title': f'You spend {ratio}× more per day on weekends',
                'body': f'{fmt(total_spend(weekend_txs))} on weekends vs {fmt(total_spend(weekday_txs))} on weekdays this month.',
                'score': 5,
                'action': None,
            })

    # ── B3: End-of-month surge ──
    if current_txs:
        last_7 = [t for t in current_txs
                  if t.get('transaction_date') and
                  int(t['transaction_date'].split('-')[2]) >= 24]
        last_7_spend = total_spend(last_7)
        month_total = total_spend(current_txs)
        if month_total > 0 and last_7_spend / month_total > 0.35:
            pct = round(last_7_spend / month_total * 100)
            insights.append({
                'id': 'B3',
                'type': 'behavior',
                'color': '#f59e0b',
                'icon': '📆',
                'title': f'{pct}% of your spending happens in the last week',
                'body': f'{fmt(last_7_spend)} in the final 7 days. Spreading purchases earlier helps budget tracking.',
                'score': 4,
                'action': None,
            })

    # ── B4: Single merchant dominance ──
    curr_var_txs = var_txs(current_txs)
    FIXED_MERCHANT_KEYWORDS = ['mortgage','mtg','loan','rent','insurance','lakeview','payment']
    curr_var_merchants = {k:v for k,v in group_by_merchant(curr_var_txs).items()
                         if not any(kw in k for kw in FIXED_MERCHANT_KEYWORDS)
                         and not any(t.get('is_fixed') for t in v)}
    if current_var > 0:
        top_merchant = max(curr_var_merchants.items(),
                           key=lambda x: total_spend(x[1]), default=None)
        if top_merchant:
            m_name, m_txs = top_merchant
            m_total = total_spend(m_txs)
            m_pct = m_total / current_var if current_var > 0 else 0
            if m_pct > 0.15:
                insights.append({
                    'id': 'B4',
                    'type': 'behavior',
                    'color': '#8b5cf6',
                    'icon': '🏪',
                    'title': f'{m_name.title()} is {round(m_pct*100)}% of your flexible spending',
                    'body': f'{fmt(m_total)} across {len(m_txs)} transaction{"s" if len(m_txs)>1 else ""} — avg {fmt(m_total/len(m_txs))} each.',
                    'score': 5,
                    'action': None,
                })

    # ── B5: Subscription creep ──
    sub_txs = [t for t in current_txs if is_sub(t)]
    sub_total = total_spend(sub_txs)
    sub_names = list(set((t.get('description') or '')[:15].strip() for t in sub_txs))
    sub_count = len(sub_names)
    if sub_count >= 4 or (budget > 0 and sub_total / budget > 0.10):
        insights.append({
            'id': 'B5',
            'type': 'behavior',
            'color': '#8b5cf6',
            'icon': '📱',
            'title': f'{sub_count} active subscriptions · {fmt(sub_total)}/mo',
            'body': f'That\'s {fmt(sub_total * 12)}/year. When did you last audit what you actually use?',
            'score': 5 + (1 if sub_count >= 6 else 0),
            'action': 'View subscriptions',
            'action_filter': 'Subscriptions',
        })

    # ── T1: Category trajectory (3+ months) ──
    if n_months >= 3 and prev_month:
        prev_prev_month = all_months[all_months.index(current_month) - 2] \
            if all_months.index(current_month) >= 2 else None
        if prev_prev_month:
            pp_cats = group_by_category(monthly.get(prev_prev_month, []))
            for cat in curr_cats:
                if cat in ('Transfer', 'Payment', 'Income', 'Other'):
                    continue
                curr_val = total_spend(curr_cats.get(cat, []))
                prev_val = total_spend(prev_cats.get(cat, []))
                pp_val = total_spend(pp_cats.get(cat, []))
                if pp_val > 0 and prev_val > pp_val * 1.2 and curr_val > prev_val * 1.2:
                    insights.append({
                        'id': 'T1',
                        'type': 'trend',
                        'color': '#ef4444',
                        'icon': '📈',
                        'title': f'{cat} has grown 3 months in a row',
                        'body': f'{fmt(pp_val)} → {fmt(prev_val)} → {fmt(curr_val)}. Worth reviewing before it becomes a habit.',
                        'score': 8,
                        'action': f'View {cat}',
                        'action_filter': cat,
                    })
                    break

    # ── T2: Improving category ──
    curr_month_days = date.today().day if date.today().strftime('%Y-%m') == current_month else 28
    is_partial = curr_month_days < 15
    if prev_month and not is_partial:
        for cat in prev_cats:
            if cat in ('Transfer', 'Payment', 'Income', 'Other'):
                continue
            prev_val = total_spend([t for t in prev_cats.get(cat,[]) if not t.get('is_fixed')])
            curr_val = total_spend([t for t in curr_cats.get(cat,[]) if not t.get('is_fixed')])
            # Skip if current is 0 — likely partial month, not real reduction
            if prev_val > 50 and curr_val >= 10 and curr_val < prev_val * 0.85:
                drop = round((prev_val - curr_val) / prev_val * 100)
                insights.append({
                    'id': 'T2',
                    'type': 'win',
                    'color': '#10b981',
                    'icon': '📉',
                    'title': f'{cat} down {drop}% vs last month',
                    'body': f'{fmt(curr_val)} this month vs {fmt(prev_val)} last month. You saved {fmt(prev_val - curr_val)}. Keep it up!',
                    'score': 7,
                    'action': None,
                })
                break

    # ── T3: New merchant >10% of budget ──
    if prev_month and budget > 0:
        hist_merchant_keys = set(
            (t.get('description') or '')[:12].lower().strip()
            for t in exp if not t['transaction_date'].startswith(current_month)
        )
        for m_key, m_txs in curr_var_merchants.items():
            if any(t.get('is_fixed') for t in m_txs):
                continue
            if any(k in m_key for k in ['mortgage','mtg','loan','lakeview','rent','insurance','bmw','auto','vehicle','pymt','payment']):
                continue
            if any(t.get('category') in ('Loan Payment','Bills & Utilities','Insurance') for t in m_txs):
                continue
            m_total = total_spend(m_txs)
            if m_key not in hist_merchant_keys and m_total / budget > 0.10:
                m_name = (m_txs[0].get('description') or m_key)[:25].strip()
                insights.append({
                    'id': 'T3',
                    'type': 'trend',
                    'color': '#f59e0b',
                    'icon': '🆕',
                    'title': f'New merchant: {m_name.title()}',
                    'body': f'{fmt(m_total)} — that\'s {round(m_total/budget*100)}% of your budget. First time seeing this charge.',
                    'score': 6,
                    'action': None,
                })
                break

    # ── T4: Spending velocity ──
    if prev_month and current_txs:
        today = date.today()
        if today.strftime('%Y-%m') == current_month:
            days_elapsed = today.day
            days_in_month = 30
            days_left = days_in_month - days_elapsed
            if days_elapsed > 5 and days_left > 10:
                projected = (current_var / days_elapsed) * days_in_month
                if prev_var > 0 and projected > prev_var * 1.15:
                    over = round((projected - prev_var) / prev_var * 100)
                    insights.append({
                        'id': 'T4',
                        'type': 'trend',
                        'color': '#ef4444',
                        'icon': '⚡',
                        'title': f'On pace for {fmt(projected)} — {over}% above last month',
                        'body': f'{fmt(current_var)} spent so far with {days_left} days left. Last month was {fmt(prev_var)}.',
                        'score': 7 + (1 if over > 30 else 0),
                        'action': None,
                    })

    # ── A1: Single transaction outlier ──
    LOAN_KEYWORDS = ['bmw','mortgage','mtg pymt','loan pymt','car payment',
                     'auto loan','student loan','lakeview','vehicle']
    var_only_txs = [t for t in var_txs(current_txs)
                    if not any(k in (t.get('description') or '').lower()
                               for k in LOAN_KEYWORDS)]
    amounts = [abs(t.get('amount', 0)) for t in var_only_txs]
    if len(amounts) >= 3:
        avg_amt = mean(amounts)
        for t in var_only_txs:
            amt = abs(t.get('amount', 0))
            if amt > avg_amt * 2.5 and amt > 200:
                month_total = total_spend(current_txs)
                pct = round(amt / month_total * 100) if month_total > 0 else 0
                desc = (t.get('description') or '')[:25]
                insights.append({
                    'id': 'A1',
                    'type': 'anomaly',
                    'color': '#ef4444',
                    'icon': '🔍',
                    'title': f'One charge made up {pct}% of your spending',
                    'body': f'{desc} · {fmt(amt)} — that\'s {round(amt/avg_amt)}× your average transaction. One-time or new recurring?',
                    'score': 6,
                    'action': None,
                })
                break

    # ── A2: Category spike vs rolling avg ──
    if n_months >= 3:
        rolling_cats = defaultdict(list)
        for m in all_months[:-1]:  # exclude current month
            for cat, txs in group_by_category(monthly.get(m, [])).items():
                rolling_cats[cat].append(total_spend(txs))
        for cat, curr_cat_txs in curr_cats.items():
            if cat in ('Transfer', 'Payment', 'Income', 'Other'):
                continue
            if cat not in rolling_cats or len(rolling_cats[cat]) < 2:
                continue
            rolling_avg = mean(rolling_cats[cat])
            curr_val = total_spend(curr_cat_txs)
            if rolling_avg > 0 and curr_val > rolling_avg * 3:
                insights.append({
                    'id': 'A2',
                    'type': 'anomaly',
                    'color': '#ef4444',
                    'icon': '🚨',
                    'title': f'{cat} is {round(curr_val/rolling_avg)}× your usual spend',
                    'body': f'{fmt(curr_val)} this month vs your {fmt(rolling_avg)} average. One-time event or new pattern?',
                    'score': 8,
                    'action': f'View {cat}',
                    'action_filter': cat,
                })
            break

    # ── A3: Unusual merchant frequency ──
    if n_months >= 3:
        for m_key, all_time_txs in hist_merchants.items():
            hist_months = set(t['transaction_date'][:7] for t in all_time_txs
                              if not t['transaction_date'].startswith(current_month))
            if not hist_months:
                continue
            hist_avg_count = len([t for t in all_time_txs
                                  if not t['transaction_date'].startswith(current_month)]) / len(hist_months)
            curr_count = len(curr_merchants.get(m_key, []))
            if hist_avg_count >= 2 and curr_count > hist_avg_count * 2.5:
                m_name = (all_time_txs[0].get('description') or m_key)[:20].strip()
                insights.append({
                    'id': 'A3',
                    'type': 'anomaly',
                    'color': '#f59e0b',
                    'icon': '🔁',
                    'title': f'{m_name.title()} · {curr_count}× this month vs usual {round(hist_avg_count)}×',
                    'body': f'You visited {round(curr_count/hist_avg_count, 1)}× more than usual. Small habit adding up?',
                    'score': 6,
                    'action': None,
                })
            break

    # ── O2: Subscription overlap ──
    sub_descs = [(t.get('description') or '').lower() for t in sub_txs]
    for overlap_keywords, overlap_type, suggestion in SUBSCRIPTION_OVERLAPS:
        matches = [k for k in overlap_keywords if any(k in d for d in sub_descs)]
        if len(matches) >= 2:
            overlap_total = total_spend([t for t in sub_txs if any(k in (t.get('description') or '').lower() for k in matches)])
            insights.append({
                'id': 'O2',
                'type': 'optimization',
                'color': '#3b82f6',
                'icon': '💡',
                'title': f'Overlapping {overlap_type} subscriptions detected',
                'body': f'{suggestion}. You\'re spending {fmt(overlap_total)}/mo on overlapping services.',
                'score': 7,
                'action': 'View subscriptions',
                'action_filter': 'Subscriptions',
            })
            break

    # ── F1: Seasonal fixed expense changes ──
    if prev_month:
        curr_fixed = [t for t in current_txs if t.get('is_fixed')]
        prev_fixed = [t for t in prev_txs if t.get('is_fixed')]
        curr_fixed_merchants = group_by_merchant(curr_fixed)
        prev_fixed_merchants = group_by_merchant(prev_fixed)

        for m_key in curr_fixed_merchants:
            if m_key not in prev_fixed_merchants:
                continue
            curr_amt = total_spend(curr_fixed_merchants[m_key])
            prev_amt = total_spend(prev_fixed_merchants[m_key])
            if prev_amt > 0 and abs(curr_amt - prev_amt) / prev_amt > 0.10:
                change_pct = round((curr_amt - prev_amt) / prev_amt * 100)
                m_name = (curr_fixed_merchants[m_key][0].get('description') or m_key)[:20]
                seasonal = SEASONAL_CONTEXT.get(current_month_num, {}).get('notes', [])
                seasonal_note = ''
                if current_month_num in (6, 7, 8) and 'electric' in m_key.lower():
                    seasonal_note = ' Expected in summer — AC usage peaks Jun-Aug.'
                elif current_month_num == 1 and 'gym' in m_key.lower():
                    seasonal_note = ' January gym spikes are common — worth tracking if it sticks.'
                elif current_month_num in (11, 12):
                    seasonal_note = ' Common in holiday season — check for annual renewals.'

                import re as _re
                clean_name = _re.sub(r'[\d\-\*]{4,}', '', m_name).strip().title()
                clean_name = clean_name[:25].strip() or m_name[:20].title()
                insights.append({
                    'id': 'F1',
                    'type': 'fixed',
                    'color': '#64748b',
                    'icon': '🔒',
                    'title': f'{clean_name} {"increased" if change_pct > 0 else "decreased"} by {abs(change_pct)}%',
                    'body': f'{fmt(curr_amt)} this month vs {fmt(prev_amt)} last month.{seasonal_note}',
                    'score': 4,
                    'action': None,
                })
            break

    # ── W2: Under budget ──
    if budget > 0 and current_var < budget * 0.90:
        remaining = budget - current_var
        pct_used = round(current_var / budget * 100)
        # Check if it's consistent
        if prev_var > 0 and prev_var < budget * 0.90:
            insights.append({
                'id': 'W2',
                'type': 'win',
                'color': '#10b981',
                'icon': '✅',
                'title': f'You\'re {round(100-pct_used)}% under budget — 2 months running',
                'body': f'{fmt(remaining)} still available. Solid discipline — that\'s {fmt(remaining*12)}/year in savings if it holds.',
                'score': 8,
                'action': None,
            })
        else:
            insights.append({
                'id': 'W2',
                'type': 'win',
                'color': '#10b981',
                'icon': '✅',
                'title': f'On track — {pct_used}% of budget used',
                'body': f'{fmt(remaining)} remaining. You\'re managing well this month.',
                'score': 5,
                'action': None,
            })

    # ── W3: Subscription cancelled ──
    if prev_month and n_months >= 3:
        # Only flag as cancelled if subscription appeared in 2+ previous months
        prev_prev_month_w3 = all_months[all_months.index(current_month) - 2]             if all_months.index(current_month) >= 2 else None
        pp_txs_w3 = monthly.get(prev_prev_month_w3, []) if prev_prev_month_w3 else []
        pp_sub_keys = set(
            (t.get('description') or '')[:10].lower()
            for t in pp_txs_w3 if is_sub(t)
        )
        prev_sub_keys = set(
            (t.get('description') or '')[:10].lower()
            for t in prev_txs if is_sub(t)
        )
        curr_sub_keys = set(
            (t.get('description') or '')[:10].lower()
            for t in current_txs if is_sub(t)
        )
        # Only consider cancelled if it appeared in BOTH previous months
        cancelled = (prev_sub_keys & pp_sub_keys) - curr_sub_keys
        if cancelled:
            cancelled_txs = [t for t in prev_txs
                             if is_sub(t) and
                             (t.get('description') or '')[:10].lower() in cancelled]
            # Use single month amount — not aggregate
            if cancelled_txs:
                cancelled_amt = abs(cancelled_txs[0].get('amount', 0))
            else:
                cancelled_amt = 0
            cancelled_name = (cancelled_txs[0].get('description') or 'A subscription')[:20] if cancelled_txs else 'A subscription'
            insights.append({
                'id': 'W3',
                'type': 'win',
                'color': '#10b981',
                'icon': '👏',
                'title': f'Looks like you cancelled {cancelled_name.title()}',
                'body': f'Saving {fmt(cancelled_amt)}/mo — that\'s {fmt(cancelled_amt * 12)}/year back in your pocket.',
                'score': 7,
                'action': None,
            })

    # ── W4: Spending streak ──
    if n_months >= 3 and prev_month:
        prev_prev_month = all_months[all_months.index(current_month) - 2] \
            if all_months.index(current_month) >= 2 else None
        if prev_prev_month:
            pp_var = var_spend(monthly.get(prev_prev_month, []))
            if pp_var > 0 and prev_var < pp_var and current_var < prev_var:
                insights.append({
                    'id': 'W4',
                    'type': 'win',
                    'color': '#10b981',
                    'icon': '🎯',
                    'title': 'Flexible spending down 2 months in a row',
                    'body': f'{fmt(pp_var)} → {fmt(prev_var)} → {fmt(current_var)}. You\'re trending in the right direction. Keep going!',
                    'score': 9,
                    'action': None,
                })

    # ── W5: Low dining frequency ──
    today_day = date.today().day if date.today().strftime('%Y-%m') == current_month else 28
    is_partial_month = today_day < 15
    if n_months >= 2 and prev_month and not is_partial_month:
        prev_dining_count = len([t for t in prev_txs
                                 if t.get('category') in ('Food & Dining',)])
        # Only valid if difference is reasonable (not due to partial month)
        if prev_dining_count > 0 and dining_count < prev_dining_count * 0.80 and (prev_dining_count - dining_count) <= 10:
            drop = prev_dining_count - dining_count
            insights.append({
                'id': 'W5',
                'type': 'win',
                'color': '#10b981',
                'icon': '🥗',
                'title': f'You dined out {drop} fewer times than last month',
                'body': f'{dining_count} this month vs {prev_dining_count} last month. Small habit, real savings.',
                'score': 6,
                'action': None,
            })

    # ── RANK AND DEDUPLICATE ──
    # Ensure at least 1 win insight if available
    wins = [i for i in insights if i['type'] == 'win']
    others = [i for i in insights if i['type'] != 'win']

    # Sort by score descending
    wins.sort(key=lambda x: x['score'], reverse=True)
    others.sort(key=lambda x: x['score'], reverse=True)

    # Deduplicate by category — no two insights about same category
    seen_categories = set()
    seen_types = set()
    final = []

    # Always include top win first if available
    if wins:
        final.append(wins[0])
        seen_types.add('win')
        seen_categories.add(wins[0].get('action_filter', ''))

    # Fill remaining slots ensuring diversity
    for ins in others:
        if ins['type'] in seen_types and len(final) > 2:
            continue
        if ins.get('action_filter') in seen_categories and ins.get('action_filter'):
            continue
        final.append(ins)
        seen_types.add(ins['type'])
        seen_categories.add(ins.get('action_filter', ''))
        if len(final) >= 6:
            break

    # Add more wins if slots available
    for w in wins[1:]:
        if len(final) >= 6:
            break
        if w.get('action_filter') not in seen_categories:
            final.append(w)
            seen_categories.add(w.get('action_filter', ''))

    # Final sort — wins first, then by score
    final.sort(key=lambda x: (x['type'] != 'win', -x['score']))

    return final[:6]

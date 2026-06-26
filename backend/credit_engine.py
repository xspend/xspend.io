
import re
from typing import Optional, Dict, List, Tuple

INELIGIBLE_PATTERNS = [
    r'\b(cashback|cash.?back.?reward|welcome.?bonus|sign.?up.?bonus|points.?redemption|reward.?redemption|annual.?bonus|referral.?bonus|promotional.?credit|courtesy.?credit)\b',
]
INELIGIBLE_RE = [re.compile(p, re.IGNORECASE) for p in INELIGIBLE_PATTERNS]

PROGRAM_MAP = {
    'platinum dining':        ('Food & Dining', 'flexible', 'high'),
    'platinum travel':        ('Travel', 'flexible', 'high'),
    'platinum uber':          ('Subscriptions', 'committed', 'high'),
    'platinum walmart':       ('Subscriptions', 'committed', 'high'),
    'platinum digital':       ('Subscriptions', 'committed', 'high'),
    'platinum entertainment': ('Subscriptions', 'committed', 'high'),
    'platinum streaming':     ('Subscriptions', 'committed', 'high'),
    'platinum lululemon':     ('Shopping', 'flexible', 'high'),
    'platinum saks':          ('Shopping', 'flexible', 'high'),
    'platinum equinox':       ('Health', 'flexible', 'high'),
    'platinum hotel':         ('Travel', 'flexible', 'high'),
    'platinum airline':       ('Travel', 'flexible', 'high'),
    'platinum clear':         ('Subscriptions', 'committed', 'high'),
    'platinum resy':          ('Food & Dining', 'flexible', 'high'),
    'platinum grubhub':       ('Food & Dining', 'flexible', 'high'),
    'platinum doordash':      ('Food & Dining', 'flexible', 'high'),
    'platinum dunkin':        ('Food & Dining', 'flexible', 'high'),
    'platinum shake shack':   ('Food & Dining', 'flexible', 'high'),
    'platinum cell phone':    ('Bills & Utilities', 'committed', 'high'),
    'gold dining':            ('Food & Dining', 'flexible', 'high'),
    'gold uber cash':         ('Food & Dining', 'flexible', 'high'),
    'gold grocery':           ('Groceries', 'flexible', 'high'),
    'amex clear':             ('Subscriptions', 'committed', 'high'),
}

CREDIT_TYPE_PATTERNS = [
    (r'\b(dining|restaurant|food|grubhub|doordash|uber.?eats)\b', 'dining', 'Food & Dining', 'flexible'),
    (r'\b(travel|airline|hotel|resort|airbnb|delta|united|marriott|hilton|hyatt|global.?entry|tsa)\b', 'travel', 'Travel', 'flexible'),
    (r'\b(digital.?entertainment|streaming|netflix|spotify|hulu|disney|apple.?tv|youtube|entertainment)\b', 'subscription', 'Subscriptions', 'committed'),
    (r'\b(uber.?one|walmart.?plus|wmt.?plus|clearme|clear.?plus|amazon.?prime|audible)\b', 'subscription', 'Subscriptions', 'committed'),
    (r'\b(utility|electric|internet|phone|wireless|att|verizon|cell.?phone)\b', 'bill', 'Bills & Utilities', 'committed'),
    (r'\b(lululemon|saks|neiman|nordstrom|shopping)\b', 'shopping', 'Shopping', 'flexible'),
    (r'\b(equinox|gym|fitness|peloton|health)\b', 'health', 'Health', 'flexible'),
    (r'\b(cashback|cash.?back|reward|points|bonus|statement.?credit)\b', 'cashback', None, None),
]
CREDIT_TYPE_RE = [(re.compile(p, re.IGNORECASE), ct, cat, bucket) for p, ct, cat, bucket in CREDIT_TYPE_PATTERNS]

INLINE_MERCHANT_MAP = {
    'walmart': 'wmt',
    'uber one': 'uber one',
    'lululemon': 'lululemon',
    'hulu': 'hulu',
    'youtube': 'youtube',
    'clear': 'clearme',
    'disney': 'disney',
    'netflix': 'netflix',
    'spotify': 'spotify',
    'doordash': 'doordash',
    'grubhub': 'grubhub',
    'resy': 'resy',
    'saks': 'saks',
    'equinox': 'equinox',
}


def classify_credit(description: str) -> Dict:
    desc_lower = (description or '').lower().strip()
    result = {
        'credit_type': 'unknown',
        'eligible_for_matching': True,
        'target_category': None,
        'target_bucket': None,
        'program_match': None,
        'confidence': 'low',
    }
    for pattern in INELIGIBLE_RE:
        if pattern.search(desc_lower):
            result['credit_type'] = 'cashback'
            result['eligible_for_matching'] = False
            return result
    for program_key, (category, bucket, confidence) in PROGRAM_MAP.items():
        if program_key in desc_lower:
            result['credit_type'] = 'subscription' if bucket == 'committed' else 'purchase'
            result['eligible_for_matching'] = True
            result['target_category'] = category
            result['target_bucket'] = bucket
            result['program_match'] = program_key
            result['confidence'] = confidence
            return result
    for pattern, credit_type, category, bucket in CREDIT_TYPE_RE:
        if pattern.search(desc_lower):
            result['credit_type'] = credit_type
            result['eligible_for_matching'] = credit_type != 'cashback'
            result['target_category'] = category
            result['target_bucket'] = bucket
            result['confidence'] = 'medium'
            return result
    merchant_match = re.search(r'-\s*(.+)', description or '')
    if merchant_match:
        result['merchant_hint'] = merchant_match.group(1).strip()
    return result


def extract_merchant_from_credit(description: str) -> Optional[str]:
    match = re.search(r'-\s*(.+)', description or '')
    if match:
        merchant = match.group(1).strip().lower()
        return re.sub(r'\s+', ' ', merchant)[:20]
    desc_lower = (description or '').lower()
    for keyword, match_str in INLINE_MERCHANT_MAP.items():
        if keyword in desc_lower:
            return match_str
    return None


def find_matching_expense(credit_desc, credit_amount, credit_info, expenses, statement_period):
    if not credit_info['eligible_for_matching']:
        return None, 'ineligible', 'none'

    target_category = credit_info.get('target_category')
    merchant_hint = extract_merchant_from_credit(credit_desc)

    period_expenses = [
        e for e in expenses
        if (e.get('transaction_date') or '')[:7] == statement_period
        and e.get('transaction_type') == 'expense'
        and float(e.get('amount', 0)) < 0
    ]

    # Level 1: Exact merchant match across ALL categories
    if merchant_hint:
        hint_clean = merchant_hint[:8].strip()
        if hint_clean:
            for exp in period_expenses:
                exp_desc = (exp.get('description') or '').lower()
                if hint_clean in exp_desc:
                    return exp, 'exact_merchant', 'high'

    # Level 2: Program mapping — high confidence category match
    if target_category and credit_info.get('confidence') == 'high':
        category_expenses = [e for e in period_expenses if e.get('category') == target_category]
        if category_expenses:
            best = min(category_expenses, key=lambda e: abs(abs(float(e.get('amount', 0))) - credit_amount))
            return best, 'program_mapping', 'high'

    # Level 3: Category window
    if target_category:
        category_expenses = [e for e in period_expenses if e.get('category') == target_category]
        if category_expenses:
            best = min(category_expenses, key=lambda e: abs(abs(float(e.get('amount', 0))) - credit_amount))
            return best, 'category_window', 'medium'

    return None, 'unmatched', 'none'


def run_credit_matching(db, user_id=None):
    import sqlalchemy as _sa

    credits = db.execute(_sa.text(
        "SELECT transaction_id, description, amount, transaction_date FROM transactions WHERE transaction_type = 'card_credit'"
    )).fetchall()

    expenses_raw = db.execute(_sa.text(
        'SELECT transaction_id, description, amount, transaction_date, category, is_fixed, transaction_type FROM transactions WHERE amount < 0 AND exclusion_reason IS NULL'
    )).fetchall()

    expenses = [
        {
            'transaction_id': r[0],
            'description': r[1],
            'amount': r[2],
            'transaction_date': r[3],
            'category': r[4],
            'is_fixed': r[5],
            'transaction_type': r[6],
        }
        for r in expenses_raw
    ]

    seen_credits = set()
    offset_records = []

    for credit in credits:
        tx_id, desc, amount, date = credit
        period = (date or '')[:7]
        dedup_key = f"{(desc or '').lower()[:30]}|{round(float(amount or 0), 2)}|{period}"
        if dedup_key in seen_credits:
            continue
        seen_credits.add(dedup_key)

        credit_info = classify_credit(desc)

        if not credit_info['eligible_for_matching']:
            offset_records.append({
                'credit_transaction_id': tx_id,
                'matched_expense_id': None,
                'matched_category': None,
                'credit_type': credit_info['credit_type'],
                'eligible_for_matching': 0,
                'applied_amount': 0,
                'unapplied_amount': float(amount or 0),
                'match_confidence': 'none',
                'match_method': 'ineligible',
                'statement_period': period,
                'user_id': user_id,
            })
            continue

        matched_exp, method, confidence = find_matching_expense(
            desc, float(amount or 0), credit_info, expenses, period
        )
        credit_amt = float(amount or 0)

        if matched_exp:
            exp_amt = abs(float(matched_exp.get('amount', 0)))
            applied = min(credit_amt, exp_amt)
            unapplied = round(credit_amt - applied, 2)
            offset_records.append({
                'credit_transaction_id': tx_id,
                'matched_expense_id': matched_exp['transaction_id'],
                'matched_category': credit_info.get('target_category') or matched_exp.get('category'),
                'credit_type': credit_info['credit_type'],
                'eligible_for_matching': 1,
                'applied_amount': round(applied, 2),
                'unapplied_amount': unapplied,
                'match_confidence': confidence,
                'match_method': method,
                'statement_period': period,
                'user_id': user_id,
            })
        else:
            offset_records.append({
                'credit_transaction_id': tx_id,
                'matched_expense_id': None,
                'matched_category': credit_info.get('target_category'),
                'credit_type': credit_info['credit_type'],
                'eligible_for_matching': 1,
                'applied_amount': 0,
                'unapplied_amount': credit_amt,
                'match_confidence': 'none',
                'match_method': 'unmatched',
                'statement_period': period,
                'user_id': user_id,
            })

    db.execute(_sa.text('UPDATE credit_offsets SET is_active = 0'))

    for rec in offset_records:
        db.execute(_sa.text(
            "INSERT INTO credit_offsets (user_id, credit_transaction_id, matched_expense_id, matched_category, credit_type, eligible_for_matching, applied_amount, unapplied_amount, match_confidence, match_method, statement_period, is_active, matched_by) VALUES (:user_id, :credit_transaction_id, :matched_expense_id, :matched_category, :credit_type, :eligible_for_matching, :applied_amount, :unapplied_amount, :match_confidence, :match_method, :statement_period, 1, 'system')"
        ), rec)

    db.commit()
    return offset_records


def get_net_category_spend(db, period: str) -> Dict:
    import sqlalchemy as _sa

    expenses = db.execute(_sa.text(
        "SELECT category, amount, transaction_id, is_fixed FROM transactions WHERE transaction_type = 'expense' AND amount < 0 AND exclusion_reason IS NULL AND substr(transaction_date, 1, 7) = :period"
    ), {'period': period}).fetchall()

    offsets = db.execute(_sa.text(
        'SELECT matched_category, matched_expense_id, applied_amount FROM credit_offsets WHERE statement_period = :period AND is_active = 1 AND applied_amount > 0'
    ), {'period': period}).fetchall()

    category_map = {}
    for cat, amount, tx_id, is_fixed in expenses:
        cat = cat or 'Other'
        if cat not in category_map:
            category_map[cat] = {'gross_spend': 0, 'credit_applied': 0, 'net_spend': 0, 'is_fixed': bool(is_fixed)}
        category_map[cat]['gross_spend'] += abs(float(amount))

    for matched_cat, matched_exp_id, applied_amount in offsets:
        if matched_cat and matched_cat in category_map:
            category_map[matched_cat]['credit_applied'] += float(applied_amount)

    for cat in category_map:
        gross = category_map[cat]['gross_spend']
        credits_applied = category_map[cat]['credit_applied']
        category_map[cat]['net_spend'] = max(0, round(gross - credits_applied, 2))
        category_map[cat]['gross_spend'] = round(gross, 2)
        category_map[cat]['credit_applied'] = round(credits_applied, 2)

    return category_map

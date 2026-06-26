"""
Fixed vs Variable expense classifier.
Two categories only: fixed and variable.
Subscriptions = fixed. Utilities = fixed (with varies flag).
Confidence >= 0.75 = fixed, else variable.
"""

from collections import defaultdict
from statistics import mean, stdev
import re

FIXED_CATEGORIES = {
    # Core
    'bills & utilities', 'bills', 'utilities', 'rent', 'mortgage',
    'insurance', 'loan payment', 'debt payment', 'credit card payment',
    'subscription', 'subscriptions', 'phone', 'internet', 'cable',
    'housing', 'gym', 'fitness', 'membership', 'streaming',
    'auto insurance', 'health insurance', 'life insurance',
    'car payment', 'student loan', 'personal loan',
    # Chase aliases
    'auto & transport', 'home', 'health & fitness', 'personal finance',
    # BofA aliases
    'cable & satellite', 'telephone services', 'home improvement',
    'rent & mortgage', 'loans & mortgages', 'rent/mortgage',
    # Amex aliases
    'telecommunications', 'utilities & home services',
    # Wells Fargo aliases
    'service & parts', 'monthly fees', 'annual fees',
    # Generic
    'education', 'childcare', 'hoa', 'storage', 'parking',
    'toll', 'license', 'registration', 'tax'
}

VARIABLE_CATEGORIES = {
    'food & dining', 'groceries', 'shopping', 'entertainment',
    'travel', 'personal care', 'health', 'dining', 'restaurants',
    'other', 'miscellaneous', 'fast food', 'coffee shops',
    'alcohol & bars', 'arts', 'music', 'movies & dvds',
    'clothing', 'electronics', 'sporting goods', 'hobbies',
    'gas & fuel', 'parking', 'ride share', 'taxi',
    'hair & nails', 'spa & massage', 'pharmacy',
}

SEMI_FIXED_CATEGORIES = {
    'electric', 'gas', 'water', 'trash', 'sewer'
}

# Clean display names for known truncated merchant descriptions
MERCHANT_DISPLAY_MAP = {
    'goog': 'Google Youtube',
    'yout': 'Google Youtube',
    'netf': 'Netflix',
    'spot': 'Spotify',
    'amaz': 'Amazon Prime',
    'appl': 'Apple',
    'disn': 'Disney+',
    'hulu': 'Hulu',
    'para': 'Paramount+',
    'peac': 'Peacock',
    'padl': 'Paddle',
    'runn': 'Runna',
    'wmt': 'Walmart+',
    'wall': 'Walmart+',
}

# Known merchants whose apostrophes get stripped by bank exports.
# Applied as the final step in display_merchant() — keys are lowercase,
# values are the proper display form.
KNOWN_MERCHANTS = {
    'trader joe s': "Trader Joe's",
    'sam s club': "Sam's Club",
    'macy s': "Macy's",
    "macy s": "Macy's",
    'domino s': "Domino's",
    'mcdonald s': "McDonald's",
    'wendy s': "Wendy's",
    'lowe s': "Lowe's",
    'kohl s': "Kohl's",
    'arby s': "Arby's",
    'jack in the box': "Jack in the Box",
    'whole foods': "Whole Foods",
    'in n out': "In-N-Out",
    'in-n-out': "In-N-Out",
    'chick fil a': "Chick-fil-A",
    'chick-fil-a': "Chick-fil-A",
    'd airy queen': "Dairy Queen",
    'panda express': "Panda Express",
    'olive garden': "Olive Garden",
    'red lobster': "Red Lobster",
    'taco bell': "Taco Bell",
}

SUBSCRIPTION_KEYWORDS = {
    'netflix', 'spotify', 'hulu', 'disney', 'apple', 'amazon prime',
    'youtube', 'hbo', 'paramount', 'peacock', 'crunchyroll', 'audible',
    'dropbox', 'icloud', 'google one', 'adobe', 'microsoft', 'linkedin',
    'duolingo', 'headspace', 'calm', 'nytimes', 'wsj', 'chatgpt', 'claude',
    'runna', 'paddle', 'wmt plus', 'walmart plus', 'amazon music',
    'apple music', 'tidal', 'deezer', 'sirius', 'pandora',
    'showtime', 'starz', 'espn', 'nba league', 'nfl sunday',
    'playstation', 'xbox', 'nintendo', 'steam', 'twitch',
    'canva', 'figma', 'notion', 'slack', 'zoom', 'dropbox',
    'expressvpn', 'nordvpn', 'lastpass', '1password',
}

# Month names to strip from merchant descriptions
MONTH_NAMES = {
    'jan', 'feb', 'mar', 'apr', 'may', 'jun',
    'jul', 'aug', 'sep', 'oct', 'nov', 'dec',
    'january', 'february', 'march', 'april', 'june',
    'july', 'august', 'september', 'october', 'november', 'december'
}

def normalize_merchant(description: str) -> str:
    if not description:
        return ''
    d = description.lower().strip()
    # Remove noise words
    for noise in ['#', '*', 'purchase', 'recurring',
                  'autopay', 'auto pay', 'ach', 'checkcard', 'debit']:
        d = d.replace(noise, '')
    # Remove phone numbers and years
    d = re.sub(r'\d{7,}', '', d)
    d = re.sub(r'\b20\d{2}\b', '', d)  # Remove years like 2024, 2025, 2026
    # Remove month names at end of string (e.g. "wmt plus jan")
    words = d.split()
    if words and words[-1] in MONTH_NAMES:
        words = words[:-1]
    d = ' '.join(words)
    d = re.sub(r'\s+', ' ', d).strip()
    return d[:32].strip()

def display_merchant(description: str) -> str:
    """Clean a raw bank description into a display name.
    Used for dashboard surfaces (biggest_charge, etc) — not for classification.
    Prefers generic cleanup over the map so we don't mislabel
    (e.g. AMAZON.COM purchase != Amazon Prime subscription)."""
    if not description:
        return ''

    d = description.strip()

    # ACH descriptions (BofA checking, ACH debits/credits): cut everything from
    # 'DES:' onward — that's the payment-type + ID + counterparty name + routing
    # junk. Keep only the originator/biller name. e.g.
    #   'LAKEVIEW LN SRV DES:MTG PYMT ID:.. INDN:.. CO ID:.. WEB' -> 'LAKEVIEW LN SRV'
    d = re.split(r'\s+des:', d, maxsplit=1, flags=re.I)[0]
    # If no DES: marker, still strip trailing ACH field markers when present.
    d = re.sub(r'\s+(id|indn|co\s?id|ppd|ccd|web|tel|arc)\b.*$', '', d, flags=re.I)

    # Strip space-form payment-processor prefixes (SQ *X, TST* X, etc.). The noise
    # stripper below handles the no-space 'SQ*X' form; this catches 'SQ ' with a space.
    d = re.sub(r'^(?:sq|tst|toast|dd|dsh|pp|paypal|sp|clkbank|wpy|gum)\s+\*?\s*',
               '', d, flags=re.I)

    # Strip noise tokens
    d = re.sub(r'\b[A-Z0-9]*\*[A-Z0-9]+', '', d)         # *XYZ123 or PREFIX*XYZ123
    d = re.sub(r'#\d+', '', d)                            # #0106 location codes
    d = re.sub(r'\b\d{6,}\b', '', d)                    # 6+ digit references
    # High-entropy alphanumeric codes (Airbnb 'Hme2z9qj9n', Amazon 'Dy3g80Sk3'): 6+ char
    # tokens with >=3 letter<->digit transitions. Word+number names like 'forever21' or
    # '7eleven' have only 1 transition and are preserved.
    def _strip_codes(s):
        out = []
        for tok in s.split():
            core = tok.strip('.,;:#*-')
            if len(core) >= 6 and core.isalnum() and not core.isalpha() and not core.isdigit():
                transitions = sum(1 for a, b in zip(core, core[1:])
                                  if a.isdigit() != b.isdigit())
                if transitions >= 3:
                    continue  # drop this token
            out.append(tok)
        return ' '.join(out)
    d = _strip_codes(d)
    d = re.sub(r'\d{1,2}/\d{1,2}(?:/\d{2,4})?', '', d)  # mm/dd or mm/dd/yyyy
    d = re.sub(r'\bhttps?://\S+', '', d)                 # full URLs
    d = re.sub(r'\b[a-z0-9-]+\.(?:com|net|org|io|co)\b', '', d, flags=re.I)  # domains
    d = re.sub(r'\s+\b[A-Z]{2}\b\s*$', '', d)          # trailing 2-letter state
    d = re.sub(r'[*#]', '', d)                             # leftover * and #
    d = re.sub(r'\s+', ' ', d).strip()

    # Final cleanup: strip orphan punctuation fragments left behind by earlier
    # substitutions (e.g. "Help.", "04/", "/helppay", "Amazon.")
    d = re.sub(r'\s[/\\][\w]*', ' ', d)              # mid/end slash-words like " /helppay"
    d = re.sub(r'\b[\w]+[/\\]\s', ' ', d)           # word ending with slash like "04/"
    d = re.sub(r'\b(\w)[.](?=\s|$)', r'\1', d)       # word ending with single dot like "Amazon."
    d = re.sub(r'(?<=\w)[.,;:!?-]+\s*$', '', d)        # trailing punctuation after word
    d = re.sub(r'\b[A-Z]{2}\b\s*$', '', d, flags=re.I)  # trailing 2-letter state/abbrev
    d = re.sub(r'\s+', ' ', d).strip()

    # ATM / repeated-name cleanup (e.g. 'KUSHKLUB - S-7 WITHDRWL KUSHKLUB - S-7690 TUKWILA').
    d = re.sub(r'\b(withdrwl|withdrawal|bal\s*inq|balance\s*inquiry|atm|pos\s*debit|debit\s*card|purchase)\b', ' ', d, flags=re.I)
    d = re.sub(r'\bs-?\d+\b', ' ', d, flags=re.I)              # store codes like S-7, S-7690
    d = re.sub(r'\b(llc|inc|co|corp|ltd|usa)\b\.?', ' ', d, flags=re.I)  # legal/region suffixes
    d = re.sub(r'_[a-z]{2,}\b', ' ', d, flags=re.I)             # '_us' style suffixes
    d = re.sub(r'[-]+', ' ', d)                                   # leftover dashes
    d = re.sub(r'\s+', ' ', d).strip()
    # Collapse a repeated leading phrase: 'Kushklub ... Kushklub ...' -> 'Kushklub ...'
    _toks = d.split()
    if len(_toks) >= 2:
        for first_len in (3, 2, 1):
            if len(_toks) >= first_len * 2:
                head = _toks[:first_len]
                # find the next occurrence of head[0] after the head
                for j in range(first_len, len(_toks)):
                    if _toks[j].lower() == head[0].lower():
                        d = ' '.join(_toks[:j]).strip()
                        break
                else:
                    continue
                break
    d = re.sub(r'\s+', ' ', d).strip()

    if not d:
        return description.strip()[:50]

    # Generic friendly-name overrides for common ugly biller patterns (not specific
    # merchant names). Checked case-insensitively on the cleaned text.
    _friendly = [
        (r'\bhoa\b|homeowner.?(assoc|dues)', 'HOA Payment'),
    ]
    _low = d.lower()
    for pat, label in _friendly:
        if re.search(pat, _low):
            return label

    # Title case with smart rules
    SMALL_WORDS = {'by', 'of', 'the', 'and', 'or', 'for', 'a', 'an', 'at', 'to', 'in', 'on'}
    KNOWN_ACRONYMS = {'REI', 'NTTA', 'AMC', 'ATM', 'USPS', 'AT&T', 'NYC', 'LA', 'SF', 'BBQ',
                      'CVS', 'TJX', 'IKEA', 'IRS', 'DMV', 'DSW', 'IHOP', 'KFC', 'MGM'}
    words = d.split()
    out = []
    for i, w in enumerate(words):
        # Strip trailing punctuation for matching
        stripped = re.sub(r'[^\w+]+$', '', w)
        suffix = w[len(stripped):]
        # Known acronym?
        if stripped.upper() in KNOWN_ACRONYMS:
            out.append(stripped.upper() + suffix)
        # Small connector word in middle of phrase?
        elif i > 0 and stripped.lower() in SMALL_WORDS:
            out.append(stripped.lower() + suffix)
        # Default: capitalize first letter, lowercase rest
        elif stripped:
            out.append(stripped[0].upper() + stripped[1:].lower() + suffix)
        else:
            out.append(w)
    result = ' '.join(out)[:50]
    # Final pass: check known-merchant correction list
    # (handles bank-stripped apostrophes like "Trader Joe S" -> "Trader Joe's")
    key = result.lower().strip()
    if key in KNOWN_MERCHANTS:
        return KNOWN_MERCHANTS[key]
    return result



def dedup_key(description: str) -> str:
    """4-char alphabetic key for aggressive merchant deduplication."""
    norm = normalize_merchant(description)
    key = re.sub(r'[^a-z]', '', norm)[:4]
    return key if key else norm[:4]

def category_signal(category: str) -> tuple:
    cat = (category or '').lower().strip()
    if cat in FIXED_CATEGORIES:
        return 'fixed', 0.85
    if cat in SEMI_FIXED_CATEGORIES:
        return 'fixed', 0.75
    if cat in VARIABLE_CATEGORIES:
        return 'variable', 0.85
    return 'unknown', 0.0

def recurrence_signal(merchant_key: str, all_transactions: list) -> tuple:
    if not merchant_key or not all_transactions:
        return 'unknown', 0.0

    monthly = defaultdict(list)
    for t in all_transactions:
        date = t.get('transaction_date') or ''
        month = date[:7]
        norm = normalize_merchant(t.get('description', ''))
        if month and norm and norm[:8] == merchant_key[:8]:
            monthly[month].append(abs(t.get('amount', 0) or 0))

    months_present = len(monthly)
    total_months = len(set(
        (t.get('transaction_date') or '')[:7]
        for t in all_transactions
        if (t.get('transaction_date') or '')[:7]
    ))

    if total_months < 2 or months_present < 2:
        # Check for quarterly/annual pattern even with limited data
        all_merchant_txs = [
            t for t in all_transactions
            if normalize_merchant(t.get('description',''))[:8] == merchant_key[:8]
        ]
        if len(all_merchant_txs) == 1:
            amt = abs(all_merchant_txs[0].get('amount', 0) or 0)
            # Large round amounts suggest annual fees/insurance
            if amt >= 200 and amt % 50 == 0:
                return 'fixed', 0.65
        return 'unknown', 0.0

    recurrence_rate = months_present / total_months
    all_amounts = [a for amounts in monthly.values() for a in amounts]

    if len(all_amounts) >= 2:
        avg = mean(all_amounts)
        variance_ratio = stdev(all_amounts) / avg if avg > 0 else 1.0
    else:
        variance_ratio = 0.0

    # Quarterly detection — appears every ~3 months
    if months_present >= 2 and total_months >= 3:
        sorted_months = sorted(monthly.keys())
        gaps = []
        for i in range(1, len(sorted_months)):
            y1,m1 = map(int, sorted_months[i-1].split('-'))
            y2,m2 = map(int, sorted_months[i].split('-'))
            gaps.append((y2*12+m2) - (y1*12+m1))
        avg_gap = mean(gaps) if gaps else 1
        if 2.5 <= avg_gap <= 3.5:
            return 'fixed', 0.80  # quarterly
        if 5.5 <= avg_gap <= 6.5:
            return 'fixed', 0.75  # semi-annual
        if 11 <= avg_gap <= 13:
            return 'fixed', 0.75  # annual

    if recurrence_rate >= 0.8 and variance_ratio < 0.05:
        return 'fixed', 0.95
    elif recurrence_rate >= 0.8 and variance_ratio < 0.25:
        return 'fixed', 0.80
    elif recurrence_rate >= 0.6:
        return 'fixed', 0.65
    else:
        return 'variable', 0.65

def amount_signal(amount: float, all_amounts: list) -> tuple:
    if not amount or not all_amounts:
        return 'unknown', 0.0
    abs_amount = abs(amount)
    if len(all_amounts) >= 3:
        avg = mean(all_amounts)
        sd = stdev(all_amounts) if len(all_amounts) > 1 else 0
        if sd > 0 and abs_amount > avg + 2.5 * sd:
            return 'irregular', 0.80
    if abs_amount >= 100 and abs_amount % 50 == 0:
        return 'fixed', 0.60
    if abs_amount >= 50 and abs_amount % 25 == 0:
        return 'fixed', 0.55
    return 'unknown', 0.0

# ── Keyword-based fixed override ──────────────────────────────────────────
# These merchants are recurring subscriptions/memberships even on first sight,
# without needing multi-month amount-pattern detection. Patterns mirror
# classifier.py's membership-subscription block — keep both in sync.
import re as _re_kf

KEYWORD_FIXED_PATTERNS = [
    _re_kf.compile(r'\bwalmart\+?\s*member\b|\bwmt\s*plus\b|\bwmt\+\b', _re_kf.I),
    _re_kf.compile(r'\bcostco\s*(?:membership|annual\s*fee|renewal|connect)\b', _re_kf.I),
    _re_kf.compile(r"\bsam'?s?\s*club\s*(?:membership|annual\s*fee|renewal)\b", _re_kf.I),
    _re_kf.compile(r"\bbj'?s?\s*(?:wholesale|membership|annual\s*fee)\b", _re_kf.I),
    _re_kf.compile(r'\b(?:amazon|amzn)\s*prime\b|\bprime\s*membership\b', _re_kf.I),
    _re_kf.compile(r'\bapple\s*one\b|\bicloud\+?\b', _re_kf.I),
    _re_kf.compile(r'\btarget\s*circle\s*360\b|\bshipt\s*membership\b', _re_kf.I),
    # Streaming/utilities/etc — almost always fixed when seen
    _re_kf.compile(r'\b(?:netflix|hulu|disney\+?|hbo\s*max|spotify|youtube\s*premium)\b', _re_kf.I),
    _re_kf.compile(r'\bapple\.com/bill\b', _re_kf.I),
]

def is_keyword_fixed(description: str) -> bool:
    """Returns True if description matches a known recurring-subscription pattern."""
    if not description:
        return False
    return any(p.search(description) for p in KEYWORD_FIXED_PATTERNS)

def classify_transaction(tx: dict, all_transactions: list) -> dict:
    # Keyword override: known recurring-subscription merchants bypass heuristics.
    # These are fixed even on first upload (no multi-month history needed).
    if is_keyword_fixed(tx.get('description', '')):
        return {
            'is_fixed': True,
            'confidence': 0.95,
            'source': 'keyword_override',
            'label': 'fixed',
        }

    # Hard-fixed CATEGORY override: rent/mortgage, loan payments, insurance, etc. are
    # definitionally fixed regardless of amount size or recurrence. Without this, a
    # large mortgage payment gets flagged as an 'irregular' amount outlier below and
    # wrongly marked discretionary before the category logic runs.
    _hard_fixed_cats = {
        'rent/mortgage', 'rent', 'mortgage', 'rent & mortgage', 'loans & mortgages',
        'loan payment', 'car payment', 'student loan', 'personal loan', 'debt payment',
        'insurance', 'auto insurance', 'health insurance', 'life insurance',
        'subscriptions', 'subscription', 'membership', 'bills & utilities',
    }
    if (tx.get('category', '') or '').lower().strip() in _hard_fixed_cats:
        return {
            'is_fixed': True,
            'confidence': 0.95,
            'source': 'category_override',
            'label': 'fixed',
        }

    merchant_key = normalize_merchant(tx.get('description', ''))
    cat_label, cat_conf = category_signal(tx.get('category', ''))
    rec_label, rec_conf = recurrence_signal(merchant_key, all_transactions)

    all_amounts = [
        abs(t.get('amount', 0) or 0)
        for t in all_transactions
        if t.get('transaction_type') == 'expense' and (t.get('amount') or 0) < 0
    ]
    amt_label, amt_conf = amount_signal(tx.get('amount', 0), all_amounts)

    if amt_label == 'irregular':
        return {'is_fixed': False, 'confidence': amt_conf, 'source': 'amount_pattern', 'label': 'irregular'}

    if cat_conf >= 0.85 and cat_label in ('fixed', 'variable'):
        if rec_conf > 0 and rec_label == 'fixed' and cat_label == 'fixed':
            final_score = min(cat_conf * 0.6 + rec_conf * 0.4, 1.0)
        elif rec_conf > 0 and rec_label == 'variable' and cat_label == 'variable':
            final_score = 0.0
        else:
            final_score = cat_conf if cat_label == 'fixed' else 0.0
        return {
            'is_fixed': final_score >= 0.75,
            'confidence': round(final_score, 2),
            'source': 'category_rule',
            'label': 'fixed' if final_score >= 0.75 else 'variable'
        }

    signals = []
    if rec_conf > 0:
        signals.append((rec_label, rec_conf, 0.70))
    if amt_conf > 0 and amt_label != 'irregular':
        signals.append((amt_label, amt_conf, 0.30))

    if not signals:
        return {'is_fixed': False, 'confidence': 0.0, 'source': 'none', 'label': 'variable'}

    total_weight = sum(w for _, _, w in signals)
    fixed_score = sum(
        conf * w if label == 'fixed' else 0
        for label, conf, w in signals
    ) / total_weight if total_weight > 0 else 0

    source = 'recurrence' if rec_conf > 0 else 'amount_pattern'
    return {
        'is_fixed': fixed_score >= 0.75,
        'confidence': round(fixed_score, 2),
        'source': source,
        'label': 'fixed' if fixed_score >= 0.75 else 'variable'
    }

def classify_all_transactions(transactions: list, merchant_rules: dict = None) -> list:
    results = []
    expense_txs = [
        t for t in transactions
        if t.get('transaction_type') == 'expense' and (t.get('amount') or 0) < 0
    ]
    for tx in expense_txs:
        merchant_key = normalize_merchant(tx.get('description', ''))
        if merchant_rules and merchant_key[:8] in merchant_rules:
            user_decision = merchant_rules[merchant_key[:8]]
            results.append({
                'transaction_id': tx.get('transaction_id'),
                'id': tx.get('id'),
                'is_fixed': user_decision,
                'confidence': 1.0,
                'source': 'user_confirmed',
                'label': 'fixed' if user_decision else 'variable'
            })
            continue
        result = classify_transaction(tx, expense_txs)
        result['transaction_id'] = tx.get('transaction_id')
        result['id'] = tx.get('id')
        results.append(result)
    return results

def get_fixed_summary(transactions: list) -> dict:
    fixed_txs = [t for t in transactions if t.get('is_fixed')]
    if not fixed_txs:
        return {'total': 0, 'items': []}

    groups = defaultdict(list)
    display_names = {}

    for t in fixed_txs:
        raw = (t.get('description') or t.get('category') or 'Other').strip()
        dk = dedup_key(raw)
        groups[dk].append(abs(t.get('amount', 0) or 0))
        existing = display_names.get(dk, raw)
        display_names[dk] = raw if len(raw) <= len(existing) else existing

    items = []
    for dk, amounts in groups.items():
        avg = mean(amounts)
        varies = stdev(amounts) / avg > 0.05 if len(amounts) > 1 and avg > 0 else False
        raw_display = display_names[dk].strip()

        # Check merchant display map first
        alpha_key = re.sub(r'[^a-z]', '', raw_display.lower())[:4]
        if alpha_key in MERCHANT_DISPLAY_MAP:
            display = MERCHANT_DISPLAY_MAP[alpha_key]
        else:
            d = raw_display.lower()
            d = re.sub(r'\b20\d{2}\b', '', d)
            d = re.sub(r'\d{3}[-.] \d{3}[-.] \d{4}', '', d)
            d = re.sub(r'\d{3}[-.]\d{3}[-.]\d{4}', '', d)
            d = re.sub(r'\d{6,}', '', d)
            d = re.sub(r'[*]', '', d)
            d = re.sub(r'\s+', ' ', d).strip()
            words = d.split()
            if words and words[-1] in MONTH_NAMES:
                words = words[:-1]
            if words and len(words[-1]) == 2 and words[-1].isalpha():
                words = words[:-1]
            if words and len(words[-1]) == 2 and words[-1].isalpha():
                words = words[:-1]
            d = ' '.join(words).strip()
            clean_words = [w for w in d.title().split() if len(w) > 1]
            display = ' '.join(clean_words[:3])
            # Drop truncated last word only if it has NO vowels at all
            parts = display.split()
            if parts and len(parts[-1]) >= 4:
                vowels = set('aeiouAEIOU')
                if not any(c in vowels for c in parts[-1]):
                    display = ' '.join(parts[:-1])

        items.append({
            'merchant': display,
            'amount': round(sum(amounts), 2),   # honest period total (real charges summed)
            'avg': round(avg, 2),               # per-occurrence average (for single-month display)
            'varies': varies,
            'occurrences': len(amounts)
        })

    items.sort(key=lambda x: x['amount'], reverse=True)
    total = sum(i['amount'] for i in items)
    return {'total': round(total, 2), 'items': items}

def is_subscription(tx: dict) -> bool:
    cat = (tx.get('category') or '').lower()
    desc = (tx.get('description') or '').lower()
    if cat in ('subscription', 'subscriptions', 'streaming'):
        return True
    return any(k in desc for k in SUBSCRIPTION_KEYWORDS)

def get_subscription_summary(transactions: list) -> dict:
    subs = [t for t in transactions if is_subscription(t)]
    if not subs:
        return {'count': 0, 'total': 0.0, 'items': []}

    groups = defaultdict(list)
    display_names = {}

    for t in subs:
        raw = (t.get('description') or '').strip()
        dk = dedup_key(raw)
        groups[dk].append(abs(t.get('amount', 0) or 0))
        existing = display_names.get(dk, raw)
        display_names[dk] = raw if len(raw) <= len(existing) else existing

    items = []
    for dk, amounts in groups.items():
        display = ' '.join(display_names[dk].strip().title().split()[:2])
        items.append({'name': display, 'amount': round(mean(amounts), 2)})

    items.sort(key=lambda x: x['amount'], reverse=True)
    return {
        'count': len(items),
        'total': round(sum(i['amount'] for i in items), 2),
        'items': items
    }

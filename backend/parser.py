"""
US Bank Statement Parser
Supports: Chase, Bank of America, American Express, Capital One,
          Wells Fargo, Citi, Discover, US Bank, TD Bank, PNC,
          Ally, Apple Card, SoFi, Chime, Marcus
"""

import pdfplumber
import pandas as pd
import io
import os
import re
try:
    from ofxparse import OfxParser
    HAS_OFX = True
except ImportError:
    HAS_OFX = False
from datetime import datetime
from classifier import classify_transaction, generate_fingerprint, normalize_description
# ai.py removed — Claude fallback disabled
def parse_statement_with_claude(text, filename, bank): return [], bank

# ── US Bank detection keywords ──
US_BANK_PATTERNS = {
    'chase':             'Chase',
    'bank of america':   'Bank of America',
    'bofa':              'Bank of America',
    'bac ':              'Bank of America',
    'american express':  'American Express',
    'amex':              'American Express',
    'capital one':       'Capital One',
    'capitalone':        'Capital One',
    'wells fargo':       'Wells Fargo',
    'wellsfargo':        'Wells Fargo',
    'citibank':          'Citibank',
    'citi bank':         'Citibank',
    'citicards':         'Citibank',
    'discover':          'Discover',
    'us bank':           'US Bank',
    'usbank':            'US Bank',
    'td bank':           'TD Bank',
    'tdbank':            'TD Bank',
    'pnc bank':          'PNC Bank',
    'pnc ':              'PNC Bank',
    'ally bank':         'Ally Bank',
    'ally financial':    'Ally Bank',
    'marcus':            'Marcus by Goldman Sachs',
    'goldman sachs':     'Marcus by Goldman Sachs',
    'apple card':        'Apple Card',
    'sofi':              'SoFi',
    'chime':             'Chime',
    'robinhood':         'Robinhood',
    'schwab':            'Charles Schwab',
    'fidelity':          'Fidelity',
    'navy federal':      'Navy Federal',
    'usaa':              'USAA',
    'regions':           'Regions Bank',
    'suntrust':          'Truist',
    'truist':            'Truist',
    'bbt ':              'Truist',
    'citizens bank':     'Citizens Bank',
    'fifth third':       'Fifth Third Bank',
    'huntington':        'Huntington Bank',
    'keybank':           'KeyBank',
    'comerica':          'Comerica',
    'first republic':    'First Republic',
    'signature bank':    'Signature Bank',
    'synchrony':         'Synchrony Bank',
    'barclays us':       'Barclays US',
}

# OFX Financial Institution ID → Bank name
OFX_FID_MAP = {
    '10898': 'Chase',
    '1001':  'Wells Fargo',
    '1176':  'Bank of America',
    '3101':  'American Express',
    '7000':  'Citibank',
    '815':   'Discover',
    '1461':  'Capital One',
    '5591':  'US Bank',
    '1107':  'TD Bank',
    '2315':  'PNC Bank',
    '3589':  'Ally Bank',
    '101':   'Navy Federal',
    '5163':  'USAA',
}

OFX_TYPE_MAP = {
    'debit':   'expense',
    'credit':  'income',
    'int':     'income',
    'div':     'income',
    'fee':     'expense',
    'srvchg':  'expense',
    'dep':     'income',
    'atm':     'expense',
    'pos':     'expense',
    'xfer':    'transfer',
    'check':   'expense',
    'payment': 'credit_card_payment',
    'cash':    'expense',
    'other':   'unknown',
}

# Banks where expenses are POSITIVE (need sign flip)
POSITIVE_EXPENSE_BANKS = {
    'American Express',
    'Apple Card',
    'Citibank',
    'Discover',
    'Synchrony Bank',
    'Barclays US',
}

# Banks where CSV uses separate Debit/Credit columns
DEBIT_CREDIT_BANKS = {
    'Bank of America',
    'Wells Fargo',
    'Chase',       # some Chase formats
    'US Bank',
    'TD Bank',
    'PNC Bank',
    'Regions Bank',
    'Truist',
    'Citizens Bank',
    'Fifth Third Bank',
    'Huntington Bank',
    'KeyBank',
    'Navy Federal',
    'USAA',
}

def detect_date(val: str) -> str:
    if not val or str(val).strip() in ('', 'nan', 'None'):
        return None
    val = str(val).strip()

    # Handle partial dates MM/YYYY or MM-YYYY → default to 1st of month
    partial_match = re.match(r'^(\d{1,2})[/-](20\d{2})$', val)
    if partial_match:
        month, year = partial_match.groups()
        return f'{year}-{int(month):02d}-01'

    # Handle YYYY/MM or YYYY-MM (no day)
    partial_match2 = re.match(r'^(20\d{2})[/-](\d{1,2})$', val)
    if partial_match2:
        year, month = partial_match2.groups()
        return f'{year}-{int(month):02d}-01'

    # US date formats only
    formats = [
        '%m/%d/%Y', '%m/%d/%y',
        '%Y-%m-%d',
        '%m-%d-%Y', '%m-%d-%y',
        '%B %d %Y', '%b %d %Y',
        '%d %B %Y', '%d %b %Y',
        '%b %d %Y',
        '%m/%Y',
        '%Y%m%d',
    ]
    # Remove commas for formats like 'Mar 15, 2026'
    val_clean = val.replace(',', '').strip()
    for fmt in formats:
        try:
            return datetime.strptime(val_clean, fmt).strftime('%Y-%m-%d')
        except:
            continue
    return None  # Return None instead of raw val — invalid dates excluded

def detect_amount(val) -> float:
    if val is None:
        return 0.0
    s = str(val).strip()
    s = s.replace(',', '').replace('$', '').replace('+', '')
    # Handle parentheses for negatives: (45.00) → -45.00
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    try:
        return float(s)
    except:
        return 0.0

def detect_bank_from_text(text: str) -> str:
    lower = text.lower()[:3000]
    for key, name in US_BANK_PATTERNS.items():
        if key in lower:
            return name
    return None

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    col_map = {}
    for col in df.columns:
        low = str(col).lower().strip()
        # Date columns
        if any(x in low for x in ['date', 'posted', 'trans date', 'transaction date', 'activity date', 'posting date']):
            if 'date' not in col_map.values():
                col_map[col] = 'date'
        # Description columns
        elif any(x in low for x in ['description', 'narration', 'details', 'merchant', 'payee', 'memo', 'name', 'transaction']):
            if 'description' not in col_map.values():
                col_map[col] = 'description'
        # Debit column (money out)
        elif any(x in low for x in ['debit', 'withdrawal', 'withdrawals', 'charge', 'payment']):
            if 'debit' not in col_map.values():
                col_map[col] = 'debit'
        # Credit column (money in)
        elif any(x in low for x in ['credit', 'deposit', 'deposits']):
            if 'credit' not in col_map.values():
                col_map[col] = 'credit'
        # Single amount column
        elif any(x in low for x in ['amount', 'amt']):
            if 'amount' not in col_map.values():
                col_map[col] = 'amount'
        # Category
        elif any(x in low for x in ['category', 'cat', 'type']):
            if 'raw_category' not in col_map.values():
                col_map[col] = 'raw_category'
        # Status
        elif any(x in low for x in ['status', 'pending']):
            col_map[col] = 'status'
    return df.rename(columns=col_map)

def fix_amount_for_bank(amount: float, description: str, bank: str, has_debit_credit: bool) -> float:
    """
    Normalize amount sign conventions across US banks.
    Standard: negative = expense, positive = income/deposit
    """
    if has_debit_credit:
        # Already handled in rows_from_dataframe: debit = negative, credit = positive
        return amount

    if bank in POSITIVE_EXPENSE_BANKS:
        # These banks export expenses as positive — flip sign
        # But payments/credits should stay positive
        desc_lower = description.lower()
        is_payment = any(p in desc_lower for p in [
            'payment', 'thank you', 'autopay', 'credit', 'refund',
            'return', 'adjustment', 'reward', 'cash back', 'cashback'
        ])
        if is_payment:
            return -abs(amount)   # payments become negative (money out toward card)
        else:
            return -abs(amount)   # expenses become negative

    return amount

# Financing fees — exclude entirely
FINANCING_FEE_KEYWORDS = [
    'pay over time', 'plan it fee', 'installment fee',
    'cash advance fee', 'balance transfer fee', 'late fee',
    'foreign transaction fee', 'annual membership fee',
    'new pay over time', 'pay over time fee',
]

# Payment/credit summary lines — exclude entirely  
PAYMENT_SUMMARY_KEYWORDS = [
    'payments/credits', 'payments and credits', 'total payments',
    'new balance', 'minimum payment due', 'payment due',
    'statement balance', 'previous balance',
]

def should_exclude_transaction(description: str) -> tuple:
    desc = (description or '').lower().strip()
    for kw in FINANCING_FEE_KEYWORDS:
        if kw in desc:
            return True, 'financing_fee'
    for kw in PAYMENT_SUMMARY_KEYWORDS:
        if kw in desc:
            return True, 'statement_summary'
    return False, None

STATEMENT_CREDIT_PATTERNS_PARSER = [
    r'amex.*credit',
    r'platinum.*credit',
    r'gold.*credit',
    r'clear.*plus.*credit',
    r'amex clear',
    r'platinum.*credit', r'gold.*credit', r'card.*credit',
    r'annual.*credit', r'statement credit', r'travel credit',
    r'digital entertainment credit', r'walmart.*credit',
    r'lululemon credit', r'uber cash', r'saks credit',
    r'cashback', r'cash back reward', r'rewards redemption',
    r'reward credit', r'streaming credit', r'hotel credit',
    r'dining credit', r'clear credit', r'equinox credit',
    r'tsa.*credit', r'global entry credit', r'cell phone credit',
]

def is_statement_credit_parser(description: str) -> bool:
    desc_lower = (description or '').lower()
    return any(re.search(p, desc_lower) for p in STATEMENT_CREDIT_PATTERNS_PARSER)


def skip_non_transaction_row(desc: str, amount: float) -> bool:
    """Filter out balance rows, headers, and summary lines."""
    desc_lower = desc.lower().strip()
    skip_phrases = [
        'opening balance', 'closing balance', 'beginning balance', 'ending balance',
        'previous balance', 'new balance', 'available balance', 'current balance',
        'minimum payment', 'payment due', 'credit limit', 'available credit',
        'total fees', 'total interest', 'finance charge', 'interest charge',
        'annual percentage', 'billing period', 'statement period',
        'account number', 'account summary', 'transaction summary',
        'subtotal', 'total debits', 'total credits', 'total charges',
    ]
    for phrase in skip_phrases:
        if phrase in desc_lower:
            return True
    return False

def rows_from_dataframe(df: pd.DataFrame, bank: str, import_source: str) -> list:
    df = normalize_columns(df)
    has_debit_credit = 'debit' in df.columns or 'credit' in df.columns

    transactions = []
    for _, row in df.iterrows():
        row = row.where(pd.notnull(row), None)

        # Get date
        date_val = row.get('date') or row.get('transaction_date')
        raw_date = str(date_val) if date_val else ''
        parsed_date = detect_date(raw_date)
        if not parsed_date:
            continue

        # Get description
        desc = str(row.get('description') or '').strip()
        if not desc or desc.lower() in ('nan', 'none', ''):
            continue

        # Skip non-transaction rows
        if skip_non_transaction_row(desc, 0):
            continue

        # Get amount
        if has_debit_credit:
            debit = detect_amount(row.get('debit') or 0)
            credit = detect_amount(row.get('credit') or 0)
            if debit and debit != 0:
                amount = -abs(debit)   # debit = money out = negative
            elif credit and credit != 0:
                amount = abs(credit)   # credit = money in = positive
            else:
                continue
        elif 'amount' in df.columns:
            raw_amt = detect_amount(row.get('amount'))
            amount = fix_amount_for_bank(raw_amt, desc, bank, False)
        else:
            continue

        if amount == 0.0:
            continue

        # Get status
        status = str(row.get('status') or 'posted').lower()
        is_pending = 'pending' in status

        # Get category hint from CSV if available
        raw_cat = str(row.get('raw_category') or '').strip()
        if raw_cat.lower() in ('nan', 'none', ''):
            raw_cat = ''

        transactions.append({
            'raw_date': raw_date,
            'raw_description': desc,
            'raw_amount': str(amount),
            'raw_category': raw_cat,
            'external_transaction_id': '',
            'transaction_date': parsed_date,
            'description': desc,
            'original_description': desc,
            'amount': amount,
            'currency': 'USD',
            'is_pending': is_pending,
            'status': 'pending' if is_pending else 'posted',
            'import_source': import_source,
            'bank_source': bank or 'Unknown Bank',
        })
    return transactions

def parse_ofx(file_bytes: bytes, bank_hint: str = None) -> tuple:
    """Parse OFX/QFX files — highest quality input format."""
    if not HAS_OFX:
        raise ValueError('OFX parser not available. Run: pip install ofxparse')

    try:
        ofx = OfxParser.parse(io.BytesIO(file_bytes))
    except Exception as e:
        raise ValueError(f'Could not parse OFX/QFX file: {e}')

    # Detect bank from FID
    bank = bank_hint or 'Unknown Bank'
    try:
        fid = str(ofx.account.institution.fid or '')
        org = str(ofx.account.institution.organization or '')
        if fid in OFX_FID_MAP:
            bank = OFX_FID_MAP[fid]
        elif org:
            detected = detect_bank_from_text(org)
            bank = detected or org.title() or bank
    except:
        pass

    transactions = []
    try:
        account_txns = ofx.account.statement.transactions
    except:
        return [], bank

    for t in account_txns:
        try:
            # Date
            raw_date = str(t.date.date()) if t.date else ''
            parsed_date = raw_date if raw_date else None
            if not parsed_date:
                continue

            # Amount — OFX is always correctly signed
            amount = float(t.amount)
            if amount == 0:
                continue

            # Description — prefer the cleaner merchant field. memo is often the
            # rawest (mashed names), so try payee/name first, fall back to memo.
            desc = str(
                getattr(t, 'payee', None)
                or getattr(t, 'name', None)
                or t.memo
                or t.id
                or ''
            ).strip()
            if not desc:
                continue

            # Skip balance records
            if skip_non_transaction_row(desc, amount):
                continue

            # Transaction type from OFX type field
            ofx_type = str(t.type or '').lower().strip()
            tx_type_hint = OFX_TYPE_MAP.get(ofx_type, 'unknown')

            # FITID for deduplication — use as external_transaction_id
            fitid = str(t.id or '').strip()

            # Fix sign for positive-expense banks
            amount = fix_amount_for_bank(amount, desc, bank, False)

            transactions.append({
                'raw_date': raw_date,
                'raw_description': desc,
                'raw_amount': str(amount),
                'raw_category': '',
                'external_transaction_id': fitid,
                'transaction_date': parsed_date,
                'description': desc,
                'original_description': desc,
                'amount': amount,
                'currency': 'USD',
                'is_pending': False,
                'status': 'posted',
                'import_source': 'ofx',
                'bank_source': bank,
                '_tx_type_hint': tx_type_hint,  # pass to enrichment
            })
        except Exception as e:
            print(f'OFX transaction parse error: {e}')
            continue

    # Dedup pending vs posted — keep posted, remove pending if same merchant+amount exists
    posted = [t for t in transactions if not t.get('is_pending')]
    pending = [t for t in transactions if t.get('is_pending')]
    for p in pending:
        already_posted = any(
            abs(po['amount'] - p['amount']) < 0.01 and
            (po['description'] or '')[:8].lower() == (p['description'] or '')[:8].lower()
            for po in posted
        )
        if not already_posted:
            posted.append(p)
    transactions = posted

    print(f'OFX parsed: {len(transactions)} transactions from {bank}')
    return transactions, bank


# ── Column aliases for dynamic CSV detection ──
COLUMN_ALIASES = {
    'date':        ['date','trans date','transaction date','trans. date','posted date',
                    'settlement date','value date','effective date'],
    'description': ['description','memo','narrative','merchant','payee','details',
                    'transaction description','name','reference'],
    'amount':      ['amount','transaction amount','net amount','sum'],
    'debit':       ['debit','withdrawal','withdrawals','debit amount','money out',
                    'charges','dr'],
    'credit':      ['credit','deposit','deposits','credit amount','money in',
                    'payments','cr'],
    'balance':     ['balance','running balance','ledger balance'],
    'category':    ['category','type','transaction type'],
}

# Known bank CSV column mappings
BANK_CSV_PROFILES = {
    'chase': {
        'date':'Transaction Date', 'description':'Description',
        'amount':'Amount', 'sign':'standard'
    },
    'discover': {
        'date':'Trans. Date', 'description':'Description',
        'amount':'Amount', 'sign':'negate'  # Discover positive = charge
    },
    'citi': {
        'date':'Date', 'description':'Description',
        'debit':'Debit', 'credit':'Credit', 'sign':'debit_credit'
    },
    'wells fargo': {
        'date':'Date', 'description':'Description',
        'amount':'Amount', 'sign':'standard'
    },
    'amex': {
        'date':'Date', 'description':'Description',
        'amount':'Amount', 'sign':'negate'
    },
    'bofa': {
        'date':'Date', 'description':'Description',
        'amount':'Amount', 'sign':'standard'
    },
    'capital one': {
        'date':'Transaction Date', 'description':'Description',
        'debit':'Debit', 'credit':'Credit', 'sign':'debit_credit'
    },
}

def detect_csv_columns(headers: list) -> dict:
    """Dynamically detect column mapping from CSV headers."""
    headers_lower = [h.lower().strip() for h in headers]
    mapping = {}
    for field, aliases in COLUMN_ALIASES.items():
        for i, h in enumerate(headers_lower):
            if any(alias == h or alias in h for alias in aliases):
                mapping[field] = headers[i]
                break
    return mapping

def normalize_amount(amount_str: str) -> float:
    """Handle various amount formats: $1,234.56 (1,234.56) -1234.56"""
    if not amount_str:
        return None
    s = str(amount_str).strip().replace(',','').replace('$','').replace('£','').replace('€','')
    # Handle parentheses as negative
    if s.startswith('(') and s.endswith(')'):
        s = '-' + s[1:-1]
    try:
        return float(s)
    except:
        return None

def _detect_header_skip(file_bytes: bytes) -> int:
    """Scan raw CSV lines for the real transaction header row.
    Banks like BofA prepend a balance-summary block (with its own multi-column
    header) before the actual 'Date,Description,Amount,...' table. Return the
    number of rows to skip so pandas reads the real header. 0 if none needed."""
    try:
        text = file_bytes.decode('utf-8', errors='ignore')
    except Exception:
        text = file_bytes.decode('latin-1', errors='ignore')
    lines = text.splitlines()
    for i, line in enumerate(lines[:25]):  # only scan the top of the file
        low = line.lower()
        has_date = 'date' in low
        has_amt = ('amount' in low) or ('amt' in low)
        has_desc = ('description' in low) or ('payee' in low) or ('memo' in low)
        # A real transaction header has a date column AND (amount or description),
        # and isn't a summary line like 'Description,,Summary Amt.'
        if has_date and (has_amt or has_desc) and 'summary' not in low:
            return i
    return 0


def _detect_bank_from_raw(file_bytes: bytes) -> str:
    """Detect the account's bank from the FULL raw CSV text (preamble included),
    before any header-skip strips it. Strong account-level signals (statement header,
    'Beginning balance', institution name) take priority over transaction-row content,
    so e.g. a BofA statement that mentions 'CHASE CREDIT CRD' in a payment line is not
    misread as Chase."""
    try:
        text = file_bytes.decode('utf-8', errors='ignore').lower()
    except Exception:
        text = file_bytes.decode('latin-1', errors='ignore').lower()
    head = text[:1500]  # the preamble / statement header lives at the very top
    # Amex activity.csv signature columns — unique to Amex, no preamble bank name.
    # Check the whole text (the header row may be past the first 1500 chars).
    if 'extended details' in text and 'appears on your statement as' in text:
        return 'American Express'
    # BofA's CSV signature: balance-summary preamble.
    if 'bank of america' in head or ('beginning balance' in head and 'ending balance' in head):
        return 'Bank of America'
    if 'apple card' in head:
        return 'Apple Card'
    if 'american express' in head or 'amex' in head:
        return 'American Express'
    if 'wells fargo' in head:
        return 'Wells Fargo'
    if 'discover' in head:
        return 'Discover'
    if 'citibank' in head or 'citi ' in head:
        return 'Citi'
    if 'chase' in head or 'jpmorgan' in head:
        return 'Chase'
    return None


def parse_csv(file_bytes: bytes, bank_hint: str = None) -> tuple:
    # Detect and skip any summary preamble (BofA etc.) BEFORE reading.
    header_skip = _detect_header_skip(file_bytes)

    # Try multiple encodings
    for encoding in ['utf-8', 'latin-1', 'cp1252']:
        try:
            df = pd.read_csv(io.BytesIO(file_bytes), encoding=encoding,
                             skiprows=header_skip, skip_blank_lines=True)
            break
        except:
            continue
    else:
        return [], 'Unknown Bank'

    # Fallback: if still no usable columns, try skipping a few rows like before.
    if len(df.columns) < 2:
        for skip in range(1, 6):
            try:
                df = pd.read_csv(io.BytesIO(file_bytes), encoding='latin-1', skiprows=skip, skip_blank_lines=True)
                if len(df.columns) >= 2:
                    break
            except:
                continue

    # Detect bank: account-level raw signal (preamble/header) FIRST, then filename hint,
    # then transaction-content sniffing as a last resort.
    raw_bank = _detect_bank_from_raw(file_bytes)
    # Amex activity.csv signature columns win over any stray row content.
    _cols_lower = [str(c).lower() for c in df.columns]
    if 'extended details' in _cols_lower and 'appears on your statement as' in _cols_lower:
        raw_bank = 'American Express'
    text = ' '.join([str(c).lower() for c in df.columns])
    for row in df.head(5).values:
        text += ' ' + ' '.join([str(v).lower() for v in row if v and str(v) != 'nan'])

    # A bank_hint derived from the filename is the most reliable signal, so it
    # wins over content sniffing (a stray merchant name like 'chase' in a
    # transaction row must not override an 'Apple Card' filename).
    bank = bank_hint or raw_bank or detect_bank_from_text(text) or 'Unknown Bank'
    return rows_from_dataframe(df, bank, 'csv'), bank

def parse_toll_xlsx(file_bytes: bytes) -> tuple:
    """Parse toll account XLSX exports (NTTA, EZPass, SunPass, etc)."""
    try:
        import pandas as pd, io
        from datetime import datetime
        df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl', dtype=str)
        df.columns = [str(c).strip() for c in df.columns]

        # Detect toll file by checking for toll-specific columns
        col_lower = [c.lower() for c in df.columns]
        if not any('toll' in c or 'tolltag' in c or 'transaction type' in c for c in col_lower):
            return [], 'Unknown'

        # Find date column
        date_col = next((c for c in df.columns if 'exit date' in c.lower() or 'posted date' in c.lower()), None)
        if not date_col:
            return [], 'Toll Account'

        transactions = []
        for _, row in df.iterrows():
            tx_type_raw = str(row.get('Transaction Type', '')).strip().upper()
            if tx_type_raw != 'TOLL':
                continue  # Skip payments/replenishments

            date_val = str(row.get(date_col, '')).strip()
            if not date_val or date_val == 'nan':
                continue

            # Parse date
            parsed_date = None
            for fmt in ['%m/%d/%Y %H:%M:%S', '%m/%d/%Y', '%Y-%m-%d']:
                try:
                    parsed_date = datetime.strptime(date_val[:19], fmt[:len(date_val[:19])]).strftime('%Y-%m-%d')
                    break
                except:
                    continue
            if not parsed_date:
                continue

            location = str(row.get('Location', '')).strip()
            if not location or location == 'nan':
                location = 'Toll'

            amount_str = str(row.get('Transaction Amount', '')).strip()
            amount = normalize_amount(amount_str)
            if amount is None:
                continue

            tx_id = str(row.get('Transaction ID', '')).strip()
            # Include transaction ID and time in description to ensure unique fingerprints
            exit_time = str(row.get('Transaction Exit Date/Time', '')).strip()
            time_suffix = exit_time[11:19] if len(exit_time) > 10 else ''
            
            transactions.append({
                'date': parsed_date,
                'description': f'Toll - {location}',
                'original_description': f'Toll - {location}',
                'amount': amount,
                'external_transaction_id': tx_id,
                'raw_date': exit_time[:10] if exit_time else parsed_date,
            })

        print(f'  Toll parser: {len(transactions)} toll transactions')
        return transactions, 'Toll Account'
    except Exception as e:
        print(f'  Toll parse error: {e}')
        return [], 'Unknown'





def parse_excel(file_bytes: bytes, bank_hint: str = None) -> tuple:
    try:
        import pandas as pd, io
        try:
            df = pd.read_excel(io.BytesIO(file_bytes), engine='openpyxl', dtype=str)
        except:
            df = pd.read_excel(io.BytesIO(file_bytes), engine='xlrd', dtype=str)

        df.columns = [str(c).strip() for c in df.columns]

        # Content-based bank detection — runs only if filename detection failed.
        # Scans the first 8 rows (incl. column names) for bank-specific markers.
        if not bank_hint:
            BANK_MARKERS = {
                'American Express': ['platinum card', 'gold card', 'american express',
                         'amex everyday', 'blue cash'],
                'Chase': ['chase ink', 'chase sapphire', 'chase freedom',
                          'jpmorgan chase'],
                'Bank of America': ['bank of america', 'bofa'],
                'Wells Fargo': ['wells fargo', 'wellsfargo'],
                'Discover': ['discover it', 'discover card'],
                'Citi': ['citibank', 'citi double cash', 'citi premier'],
            }
            sniff_text = ' '.join(str(c).lower() for c in df.columns)
            for i in range(min(8, len(df))):
                sniff_text += ' ' + ' '.join(
                    str(v).lower() for v in df.iloc[i].values if v is not None
                )
            for bank_name, markers in BANK_MARKERS.items():
                if any(m in sniff_text for m in markers):
                    bank_hint = bank_name
                    print(f'  Excel sniff: detected {bank_name}')
                    break

        # Detect toll account export
        col_lower = [c.lower() for c in df.columns]
        if any('tolltag' in c for c in col_lower):
            return parse_toll_xlsx(file_bytes)

        # Skip rows until we find the header row
        for i in range(min(10, len(df))):
            row_vals = ' '.join(str(v).lower() for v in df.iloc[i].values)
            if any(alias in row_vals for alias in ['date','description','amount','debit']):
                df.columns = [str(v).strip() for v in df.iloc[i].values]
                df = df.iloc[i+1:].reset_index(drop=True)
                break

        col_map = detect_csv_columns(list(df.columns))
        if 'date' not in col_map:
            return [], bank_hint or 'Unknown Bank'

        from datetime import datetime
        transactions = []
        for _, row in df.iterrows():
            date_val = str(row.get(col_map['date'], '')).strip()
            if not date_val or date_val == 'nan':
                continue
            parsed_date = None
            for fmt in ['%m/%d/%Y','%Y-%m-%d','%m/%d/%y','%d/%m/%Y']:
                try:
                    parsed_date = datetime.strptime(date_val, fmt).strftime('%Y-%m-%d')
                    break
                except:
                    continue
            if not parsed_date:
                continue
            desc_col = col_map.get('description')
            desc = str(row.get(desc_col, '')).strip() if desc_col else ''
            if not desc or desc == 'nan':
                continue
            amount = None
            # Prefer single 'amount' column when both are present
            # (detect_csv_columns may falsely map debit/credit due to substring matching)
            has_real_debit_credit = (
                'debit' in col_map and 'credit' in col_map
                and 'amount' not in col_map
            )
            if has_real_debit_credit:
                debit = normalize_amount(row.get(col_map['debit'], ''))
                credit = normalize_amount(row.get(col_map['credit'], ''))
                if debit and debit != 0:
                    amount = -abs(debit)
                elif credit and credit != 0:
                    amount = abs(credit)
            elif 'amount' in col_map:
                raw_amt = normalize_amount(row.get(col_map['amount'], ''))
                if raw_amt is None:
                    continue
                bank_lower = (bank_hint or '').lower()
                if any(k in bank_lower for k in ['discover','amex','american express']):
                    amount = -raw_amt
                else:
                    amount = raw_amt
            if amount is None or amount == 0:
                continue
            transactions.append({'date': parsed_date, 'description': desc, 'amount': amount})

        print(f"  Excel parser: {len(transactions)} transactions")
        return transactions, bank_hint or 'Unknown Bank'
    except Exception as e:
        print(f"  Excel parse error: {e}")
        return [], bank_hint or 'Unknown Bank'

def parse_pdf_structured(file_bytes: bytes, bank: str) -> tuple:
    # Try XY parser first for supported banks
    try:
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter('ignore')
            from pdf_parser_xy import parse_pdf_xy
        bank_lower = (bank or '').lower()
        if any(k in bank_lower for k in ['amex','american express','chase','bofa','bank of america','wells fargo','wellsfargo','macys','macys-citi','macy','discover']):
            txs, count = parse_pdf_xy(file_bytes, bank)
            if count > 0:
                print(f'  XY parser got {count} transactions — no Claude needed')
                # Normalize field names — XY parser uses transaction_date, pipeline expects date
                for tx in txs:
                    if 'transaction_date' in tx and 'date' not in tx:
                        tx['date'] = tx['transaction_date']
                return txs, bank
    except Exception as e:
        print(f'  XY parser failed: {e}, falling back to structured')

def parse_pdf_structured_legacy(file_bytes: bytes, bank: str) -> tuple:
    """Try to extract transactions from PDF tables without using Claude API."""
    try:
        import pdfplumber
        transactions = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                # Try table extraction
                tables = page.extract_tables()
                for table in tables:
                    if not table:
                        continue
                    for row in table:
                        if not row or len(row) < 3:
                            continue
                        # Try to find date, description, amount columns
                        date_val = None
                        desc_val = None
                        amt_val = None
                        for cell in row:
                            if not cell:
                                continue
                            cell = str(cell).strip()
                            # Date pattern
                            if re.match(r'\d{1,2}[/\-]\d{1,2}[/\-]?\d{0,4}', cell) and not date_val:
                                date_val = cell
                            # Amount pattern
                            elif re.match(r'^-?\$?[\d,]+\.\d{2}$', cell.replace(',','')):
                                amt_val = cell
                            # Description — longest non-date non-amount string
                            elif len(cell) > 3 and not re.match(r'^[\d\s\$\.\,\-]+$', cell):
                                if not desc_val or len(cell) > len(desc_val):
                                    desc_val = cell
                        if date_val and desc_val and amt_val:
                            try:
                                amt = float(amt_val.replace('$','').replace(',',''))
                                parsed_date = detect_date(date_val)
                                if parsed_date and amt != 0:
                                    transactions.append({
                                        'date': parsed_date,
                                        'description': desc_val,
                                        'amount': amt,
                                    })
                            except:
                                continue
        return transactions, bank
    except Exception as e:
        print(f"  Structured PDF extraction error: {e}")
        return [], bank


def parse_pdf(file_bytes: bytes, filename: str, bank_hint: str = None) -> tuple:
    all_text = ''
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    all_text += '\n' + text
    except Exception as e:
        print(f"PDF read error: {e}")
        return [], 'Unknown Bank'

    if not all_text.strip():
        # Scanned PDF — no extractable text
        raise ValueError(
            "This PDF appears to be a scanned image. Please export your statement as a text-based PDF or CSV from your bank's website."
        )

    bank = bank_hint or detect_bank_from_text(all_text) or 'Unknown Bank'
    print(f"PDF bank detected: {bank}, text length: {len(all_text)}")

    # Try structured table extraction first — faster and no API needed
    raw, detected_bank = parse_pdf_structured(file_bytes, bank)
    if len(raw) >= 1:
        print(f"  Structured extraction: {len(raw)} transactions (no AI needed)")
    else:
        print(f"  Structured extraction got {len(raw)}, falling back to Claude...")
        raw, detected_bank = parse_statement_with_claude(all_text, filename, bank)
    final_bank = detected_bank or bank

    transactions = []
    for t in raw:
        desc = str(t.get('description', '')).strip()
        if not desc:
            continue

        raw_amt = float(t.get('amount', 0))
        if raw_amt == 0:
            continue

        # If the parser already determined this is money BACK (refund/credit), keep it
        # positive and skip the generic sign-flip. Otherwise normalize via bank rules.
        _ptype = t.get('transaction_type')
        if _ptype in ('refund', 'card_credit'):
            amount = abs(raw_amt)
        elif _ptype in ('credit_card_payment', 'loan_payment'):
            amount = -abs(raw_amt)
        else:
            amount = fix_amount_for_bank(raw_amt, desc, final_bank, False)

        if skip_non_transaction_row(desc, amount):
            continue

        transactions.append({
            'raw_date': str(t.get('date', '')),
            'raw_description': desc,
            'raw_amount': str(amount),
            'raw_category': str(t.get('category', '')),
            'external_transaction_id': '',
            'transaction_date': str(t.get('date', '')),
            'description': desc,
            'original_description': desc,
            'amount': amount,
            'currency': 'USD',
            'is_pending': False,
            'status': 'posted',
            'import_source': 'pdf',
            'bank_source': final_bank,
            'transaction_type': t.get('transaction_type'),  # preserve parser's type
        })
    return transactions, final_bank

def load_merchant_rules(db, user_id=None) -> list:
    """Load active merchant rules for the classifier.
    Returns this user's rules PLUS global/system rules (user_id IS NULL),
    so per-user learning stays private while system defaults still apply.
    """
    try:
        import sqlalchemy as _sa
        if user_id is not None:
            rows = db.execute(_sa.text('''
                SELECT id, user_id, match_field, match_value, match_type,
                       transaction_type, category, priority, source,
                       confidence_override, is_active
                FROM merchant_rules
                WHERE is_active = 1 AND (user_id = :uid OR user_id IS NULL)
                ORDER BY priority DESC,
                CASE match_type WHEN 'exact' THEN 0 WHEN 'starts_with' THEN 1 WHEN 'contains' THEN 2 ELSE 3 END
            '''), {"uid": user_id}).fetchall()
        else:
            rows = db.execute(_sa.text('''
                SELECT id, user_id, match_field, match_value, match_type,
                       transaction_type, category, priority, source,
                       confidence_override, is_active
                FROM merchant_rules
                WHERE is_active = 1
                ORDER BY priority DESC,
                CASE match_type WHEN 'exact' THEN 0 WHEN 'starts_with' THEN 1 WHEN 'contains' THEN 2 ELSE 3 END
            ''')).fetchall()
        return [dict(r._mapping) for r in rows]
    except:
        return []

# ── Canonical categories (must match models.py seed) ──
CANONICAL_CATEGORIES = {
    "Food & Dining", "Groceries", "Transport", "Bills & Utilities",
    "Subscriptions", "Health", "Shopping", "Entertainment", "Travel",
    "Personal Care", "Pets", "Education", "Loan Payment",
    "Credit Card Payment", "Refund", "Salary",
    "Transfer", "Other", "Baby & Kids",
    "Bank Fees", "Card Credit", "Cash & ATM", "Gifts & Donations",
    "Government & Taxes", "Home Improvement", "Insurance",
    "Professional Services",
}

# ── Bank-supplied category translations ──
# Maps raw values from bank statement Category columns to our canonical set.
# Unmapped values fall back to "Other" — and override won't fire on Other.
BANK_CATEGORY_MAP = {
    # Chase CSV
    "Food & Drink": "Food & Dining",
    "Gas": "Transport",
    "Automotive": "Transport",
    "Health & Wellness": "Health",
    "Personal": "Personal Care",
    "Bills & Utilities": "Bills & Utilities",
    "Shopping": "Shopping",
    "Groceries": "Groceries",
    "Travel": "Travel",
    "Entertainment": "Entertainment",
    "Education": "Education",
    "Professional Services": "Professional Services",
    "Fees & Adjustments": "Bank Fees",
    "Gifts & Donations": "Gifts & Donations",
    # Amex xlsx — uses "Group-Subgroup" format
    "Restaurant-Restaurant": "Food & Dining",
    "Restaurant-Bar & Cafe": "Food & Dining",
    "Restaurant-Fast Food": "Food & Dining",
    "Merchandise & Supplies-Internet Purchase": "Shopping",
    "Merchandise & Supplies-Department Store": "Shopping",
    "Merchandise & Supplies-Wholesale Stores": "Shopping",
    "Merchandise & Supplies-Groceries": "Groceries",
    "Merchandise & Supplies-Pharmacies": "Health",
    "Fees & Adjustments-Fees & Adjustments": "Bank Fees",
    "Transportation-Fuel": "Transport",
    "Transportation-Auto Services": "Transport",
    "Transportation-Travel": "Travel",
    "Transportation-Other Transportation": "Transport",
    "Travel-Airline": "Travel",
    "Travel-Lodging": "Travel",
    "Travel-Other Travel": "Travel",
    "Entertainment-General Attractions": "Entertainment",
    "Entertainment-Theatrical Events": "Entertainment",
    "Communications-Cellular Phone": "Bills & Utilities",
    "Communications-Cable & Internet Comm": "Bills & Utilities",
    # Pass-through canonical names
    "Food & Dining": "Food & Dining",
    "Other": "Other",
}

def canonicalize_bank_category(raw: str) -> str:
    """Snap a bank-supplied category to canonical, else 'Other'."""
    if not raw:
        return "Other"
    raw = raw.strip()
    if raw in BANK_CATEGORY_MAP:
        return BANK_CATEGORY_MAP[raw]
    if raw in CANONICAL_CATEGORIES:
        return raw
    return "Other"


def enrich_transaction(tx: dict, user_rules: list = None) -> dict:
    # If XY parser already classified as card_credit — trust it
    if tx.get('_source','').endswith('_xy') and tx.get('transaction_type') == 'card_credit':
        tx['category'] = 'Card Credit'
        tx['is_fixed'] = False
        tx['exclusion_reason'] = 'statement_credit'
        return tx

    # Normalize date field — some parsers use 'date', pipeline expects 'transaction_date'
    if 'date' in tx and not tx.get('transaction_date'):
        tx['transaction_date'] = tx['date']

    # Check financing fees and payment summaries FIRST — always exclude
    should_excl, excl_reason = should_exclude_transaction(tx.get('description', ''))
    if should_excl:
        tx['transaction_type'] = 'excluded'
        tx['exclusion_reason'] = excl_reason
        tx.pop('_tx_type_hint', None)
        return tx

    # Check for statement credits first — exclude before any other classification
    if is_statement_credit_parser(tx.get('description', '')):
        tx['transaction_type'] = 'card_credit'
        tx['exclusion_reason'] = 'statement_credit'
        tx['amount'] = abs(tx.get('amount', 0))  # ensure positive
        tx['category'] = 'Card Credit'
        tx['is_fixed'] = False
        tx.pop('_tx_type_hint', None)
        return tx

    tx_type, category, confidence, needs_review = classify_transaction(
        tx['description'], tx['amount'], bank=tx.get('bank_source'), user_rules=user_rules
    )
    # Preserve definitive types the PARSER determined from statement structure/sign
    # (e.g. Chase inline refunds, card credits, payments). The keyword classifier
    # can misread these — e.g. a positive refund amount as 'income'. The parser saw
    # the statement layout/sign, so trust it for these specific types.
    parser_type = tx.get('transaction_type')
    if parser_type in ('refund', 'card_credit', 'credit_card_payment', 'loan_payment'):
        tx_type = parser_type
        confidence = 'high'
    # OFX provides reliable type hints — use them for high confidence cases
    type_hint = tx.pop('_tx_type_hint', None)
    if type_hint and type_hint != 'unknown' and confidence != 'high':
        tx_type = type_hint
        confidence = 'high'
    # Use bank-supplied category hint if classifier is uncertain — but ONLY if
    # the hint maps to a canonical category. Bank-specific names ("Food & Drink",
    # "Gas") get translated; unknown names fall through (no override).
    if tx.get('raw_category') and tx_type == 'expense' and confidence != 'high':
        bank_cat = canonicalize_bank_category(tx['raw_category'])
        if bank_cat != 'Other':
            category = bank_cat
            confidence = 'medium'

    # Use external_transaction_id for better dedup when available
    ext_id = tx.get('external_transaction_id', '')
    fingerprint = generate_fingerprint(
        tx.get('bank_source', 'unknown'),
        tx.get('transaction_date', ''),
        tx.get('amount', 0),
        tx.get('description', ''),
        ext_id=ext_id,
    )
    return {
        **tx,
        'transaction_type': tx_type,
        'category': category,
        'classification_confidence': confidence,
        'needs_review': needs_review,
        'fingerprint': fingerprint,
    }

# Bank format hints for failed/unsupported parsers
BANK_FORMAT_HINTS = {
    'discover':  ('CSV', 'discover.com → Activity → Download → Comma Separated (CSV)'),
    'barclays':  ('CSV', 'barclays.co.uk → Statements → Export as CSV'),
    'citi':      ('CSV', 'online.citi.com → Statements → Download → CSV'),
    'wells fargo': ('CSV', 'wellsfargo.com → Statements → Download → CSV'),
    'capital one': ('CSV', 'capitalone.com → Account → Download Transactions → CSV'),
    'td bank':   ('CSV', 'tdbank.com → Statements → Download → CSV'),
    'usaa':      ('CSV', 'usaa.com → Statements → Download CSV'),
}

def detect_mime_type(file_bytes: bytes, filename: str) -> str:
    """Detect actual file type from bytes, not just extension."""
    # Check magic bytes
    if file_bytes[:4] == b'%PDF':
        return 'pdf'
    if file_bytes[:2] in (b'PK', ):  # ZIP-based (xlsx)
        return 'xlsx'
    if file_bytes[:8] == b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1':  # OLE2 (xls)
        return 'xls'
    if file_bytes[:3] == b'\xef\xbb\xbf' or b',' in file_bytes[:200]:  # UTF-8 BOM or CSV
        if b',' in file_bytes[:500] or b';' in file_bytes[:500]:
            return 'csv'
    if b'OFXHEADER' in file_bytes[:200] or b'<OFX>' in file_bytes[:500]:
        return 'ofx'
    # Fall back to extension
    fname = filename.lower()
    for ext in ['.pdf','.csv','.xlsx','.xls','.ofx','.qfx']:
        if fname.endswith(ext):
            return ext.lstrip('.')
    return 'unknown'

def is_valid_row(tx: dict) -> bool:
    """Check if a transaction row has required fields."""
    date = tx.get('date') or tx.get('transaction_date')
    amount = tx.get('amount')
    desc = tx.get('description','').strip()
    return bool(date and amount is not None and amount != 0 and desc)

def check_parse_threshold(rows: list, mode: str) -> tuple:
    """Returns (passed, valid_ratio)."""
    thresholds = {'template':0.90, 'generic_table':0.80, 'generic_text':0.75, 'ocr':0.65}
    if not rows:
        return False, 0.0
    valid = sum(1 for r in rows if is_valid_row(r))
    ratio = valid / len(rows)
    return ratio >= thresholds.get(mode, 0.75), round(ratio, 2)

def get_format_hint(bank: str) -> str:
    """Return download instructions for banks with parse issues."""
    if not bank:
        return ''
    bank_lower = bank.lower()
    for key, (fmt, instructions) in BANK_FORMAT_HINTS.items():
        if key in bank_lower:
            return f"For best results with {bank}, download as {fmt}: {instructions}"
    return "Try downloading your statement as CSV from your bank's website."


# ── LLM fallback for unknown / unparseable banks ─────────────────────────────
# Added by patch_llm_fallback.py. Converts llm_fallback.parse_statement() output
# into the raw-dict shape parse_statement() feeds to enrich_transaction().

def _rows_from_llm_fallback(file_bytes, filename):
    """Run the LLM fallback on the file bytes and return (raw_rows, bank, needs_review).
    raw_rows carry needs_review/review_reason so they survive into storage.
    Returns ([], None, False) if the fallback can't handle the file."""
    import tempfile, os as _os
    try:
        import llm_fallback as _llm
    except Exception as _e:
        print(f"[llm_fallback] module not importable: {_e}")
        return [], None, False

    suffix = _os.path.splitext(filename or "")[1] or ".pdf"
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as _tf:
            _tf.write(file_bytes)
            tmp_path = _tf.name
        result = _llm.parse_statement(tmp_path)
    except Exception as _e:
        print(f"[llm_fallback] parse failed: {_e}")
        return [], None, False
    finally:
        if tmp_path and _os.path.exists(tmp_path):
            try:
                _os.remove(tmp_path)
            except OSError:
                pass

    bank = result.get("bank_name") or "Unknown Bank"
    rows = []
    for t in result.get("transactions", []):
        amt = t.get("amount")
        try:
            amt = abs(float(amt))
        except (TypeError, ValueError):
            amt = None
        direction = t.get("direction")
        desc = t.get("description") or ""

        if direction == "credit":
            signed = amt if amt is not None else None            # money in stays positive
            low = desc.lower()
            ttype = "refund" if ("refund" in low or "return" in low) else "card_credit"
        else:
            signed = -amt if amt is not None else None           # charges negative
            ttype = "expense"

        rows.append({
            "transaction_date": t.get("date"),                   # "%Y-%m-%d" string
            "amount": signed,
            "description": desc,
            "original_description": desc,
            "raw_description": desc,
            "category": t.get("category") or "Other",
            "transaction_type": ttype,                           # enrich may refine this
            "currency": "USD",
            "needs_review": bool(t.get("review")),
            "review_reason": t.get("review_reason"),
            "import_source": "llm_fallback",
        })

    return rows, bank, result.get("needs_review", False)


def parse_statement(filename: str, file_bytes: bytes, bank_name: str = None, user_rules: list = None):
    fname = filename.lower()
    bank_hint = bank_name if bank_name and bank_name != 'Unknown Bank' else None

    # ── MIME detection — don't trust extension alone ──
    detected_type = detect_mime_type(file_bytes, filename)

    # ── Password-protected PDF check ──
    if detected_type == 'pdf':
        try:
            import io, pdfplumber
            with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
                _ = pdf.pages[0].extract_text()
        except Exception as e:
            if 'password' in str(e).lower() or 'encrypted' in str(e).lower():
                raise ValueError("This PDF is password-protected. Please remove the password and re-upload.")

    # ── Detect bank from filename if not provided ──
    if not bank_hint:
        fname_lower = filename.lower()
        if 'discover' in fname_lower:
            bank_hint = 'Discover'
        elif 'chase' in fname_lower:
            bank_hint = 'Chase'
        elif 'citi' in fname_lower:
            bank_hint = 'Citi'
        elif 'wells' in fname_lower or 'wf' in fname_lower:
            bank_hint = 'Wells Fargo'
        elif 'amex' in fname_lower or 'american' in fname_lower:
            bank_hint = 'American Express'
        elif 'bofa' in fname_lower or 'bofamerica' in fname_lower:
            bank_hint = 'Bank of America'
        elif 'discover' in fname_lower:
            bank_hint = 'Discover'
        elif 'barclays' in fname_lower:
            bank_hint = 'Barclays'
        elif 'capital' in fname_lower:
            bank_hint = 'Capital One'
        elif 'apple card' in fname_lower or 'applecard' in fname_lower or 'apple_card' in fname_lower:
            bank_hint = 'Apple Card'
        elif 'synchrony' in fname_lower:
            bank_hint = 'Synchrony Bank'
        elif 'sofi' in fname_lower:
            bank_hint = 'SoFi'
        elif 'chime' in fname_lower:
            bank_hint = 'Chime'
        elif 'ally' in fname_lower:
            bank_hint = 'Ally'
        elif 'marcus' in fname_lower:
            bank_hint = 'Marcus'
        elif 'macys' in fname_lower or 'macy' in fname_lower:
            bank_hint = 'Macys-Citi'

    # ── Route by detected type ──
    parse_mode = 'unknown'
    try:
        if detected_type in ('csv',) or fname.endswith('.csv'):
            raw, detected_bank = parse_csv(file_bytes, bank_hint)
            parse_mode = 'csv'
        elif detected_type in ('xlsx','xls') or fname.endswith(('.xlsx','.xls')):
            raw, detected_bank = parse_excel(file_bytes, bank_hint)
            parse_mode = 'excel'
        elif detected_type == 'pdf' or fname.endswith('.pdf'):
            raw, detected_bank = parse_pdf(file_bytes, filename, bank_hint)
            parse_mode = 'template' if raw else 'failed'
        elif detected_type == 'ofx' or fname.endswith(('.ofx','.qfx')):
            raw, detected_bank = parse_ofx(file_bytes, bank_hint)
            parse_mode = 'ofx'
        else:
            raise ValueError('Unsupported format. Please upload CSV, XLSX, XLS, PDF, OFX, or QFX.')
    except ValueError:
        raise
    except Exception as e:
        hint = get_format_hint(bank_hint or '')
        msg = f"Could not parse this file."
        if hint:
            msg += f" {hint}"
        raise ValueError(msg)

    final_bank = detected_bank or bank_hint or 'Unknown Bank'

    # ── LLM fallback FIRST: if template parsing produced nothing, or couldn't
    # identify the bank, hand the raw file to the LLM BEFORE the threshold check
    # rejects an empty parse. This is what lets banks the templates can't read
    # (e.g. PNC, Chase debit) get parsed instead of silently failing. LLM rows go
    # through the SAME enrich loop below, so merchant rules still get a say.
    if (not raw) or final_bank == 'Unknown Bank':
        _llm_rows, _llm_bank, _ = _rows_from_llm_fallback(file_bytes, filename)
        if _llm_rows:
            print(f"[llm_fallback] used for {filename}: {len(_llm_rows)} rows, bank={_llm_bank}")
            raw = _llm_rows
            if _llm_bank and _llm_bank != 'Unknown Bank':
                final_bank = _llm_bank

    # ── Threshold check (AFTER the fallback): only give up if we STILL have
    # nothing, i.e. neither the template nor the LLM could read the file.
    passed, valid_ratio = check_parse_threshold(raw, parse_mode)
    if not passed and len(raw) == 0:
        hint = get_format_hint(bank_hint or (detected_bank if 'detected_bank' in dir() else ''))
        raise ValueError(f"No transactions found in this file. {hint}")

    enriched = []
    for tx in raw:
        tx['bank_source'] = final_bank
        _nr = tx.get('needs_review', False)
        _rr = tx.get('review_reason')
        tx = enrich_transaction(tx, user_rules)
        # preserve our review flags across enrichment (enrich may return a fresh dict)
        if _nr:
            tx['needs_review'] = True
            if _rr and not tx.get('review_reason'):
                tx['review_reason'] = _rr
        enriched.append(tx)

    return enriched, final_bank

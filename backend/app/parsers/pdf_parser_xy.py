"""
X/Y position-based PDF parser for bank statements.
Groups words by y-position (row), then assigns to columns by x-position.
No Claude API needed.
"""
import re
import pdfplumber
from typing import List, Dict, Optional, Tuple

# ── Bank column layouts (x positions) ──
BANK_LAYOUTS = {
    'amex': {
        'date':        (45, 95),
        'description': (95, 290),
        'location':    (290, 410),
        'amount':      (480, 560),
        'y_tolerance': 3.0,
    },
    'chase': {
        'date':        (30, 90),
        'description': (90, 400),
        'amount':      (440, 560),
        'y_tolerance': 3.0,
    },
    'bofa': {
        'date':        (25, 75),
        'description': (75, 380),
        'amount':      (420, 560),
        'y_tolerance': 3.0,
    },
    'citi': {
        'date':        (25, 80),
        'description': (80, 370),
        'debit':       (370, 465),
        'credit':      (465, 560),
        'y_tolerance': 3.0,
    },
}

DATE_PATTERN = re.compile(r'^\d{1,2}/\d{1,2}/\d{2,4}$')
AMOUNT_PATTERN = re.compile(r'^\-?\$?[\d,]+\.\d{2}⧫?$')

SKIP_SECTIONS = [
    'payments and credits', 'new charges', 'summary', 'detail',
    'continued on', 'account ending', 'closing date', 'customer care',
    'total payments', 'total new charges', 'minimum payment',
    'please detach', 'payment coupon', 'amount due',
]

def words_to_rows(words: list, y_tolerance: float = 3.0) -> List[List[dict]]:
    """Group words into rows by similar y-position."""
    if not words:
        return []
    
    rows = []
    current_row = [words[0]]
    current_y = words[0]['top']
    
    for word in words[1:]:
        if abs(word['top'] - current_y) <= y_tolerance:
            current_row.append(word)
        else:
            rows.append(sorted(current_row, key=lambda w: w['x0']))
            current_row = [word]
            current_y = word['top']
    
    if current_row:
        rows.append(sorted(current_row, key=lambda w: w['x0']))
    
    return rows

def row_text_in_range(row: list, x_min: float, x_max: float) -> str:
    """Get concatenated text of words within x range."""
    words = [w['text'] for w in row if x_min <= w['x0'] < x_max]
    return ' '.join(words).strip()

def clean_amount(amt_str: str) -> Optional[float]:
    """Parse amount string to float."""
    if not amt_str:
        return None
    cleaned = re.sub(r'[⧫$,\s]', '', amt_str)
    try:
        return float(cleaned)
    except:
        return None

def is_date(text: str) -> bool:
    return bool(DATE_PATTERN.match(text.strip()))

def should_skip_row(text: str) -> bool:
    t = text.lower()
    return any(skip in t for skip in SKIP_SECTIONS)

def parse_amex_xy(pdf_path: str = None, pdf_bytes: bytes = None) -> List[Dict]:
    """Parse Amex PDF using x/y coordinates."""
    layout = BANK_LAYOUTS['amex']
    transactions = []
    
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(__import__('io').BytesIO(pdf_bytes))
    
    with opener as pdf:
        in_charges = False
        in_credits = False
        pending_credit_desc = None
        
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=2)
            rows = words_to_rows(words, y_tolerance=layout['y_tolerance'])
            
            for row in rows:
                row_text = ' '.join(w['text'] for w in row)
                row_lower = row_text.lower()
                
                # Detect sections
                if 'new charges' in row_lower and 'detail' not in row_lower:
                    in_charges = True
                    in_credits = False
                    continue
                if 'payments and credits' in row_lower or ('credits' in row_lower and 'detail' not in row_lower and len(row) < 5):
                    in_credits = True
                    in_charges = False
                    continue
                if should_skip_row(row_text):
                    continue
                
                # Extract fields
                date_text = row_text_in_range(row, *layout['date'])
                desc_text = row_text_in_range(row, *layout['description'])
                amt_text  = row_text_in_range(row, *layout['amount'])
                
                # Skip rows without date
                if not date_text or not is_date(date_text):
                    # Check if this is a continuation description line
                    if desc_text and not amt_text and transactions:
                        # Append to previous transaction description
                        pass
                    continue
                
                amount = clean_amount(amt_text)
                if amount is None:
                    continue
                
                # Skip payment/summary lines
                desc_lower = desc_text.lower()
                if any(kw in desc_lower for kw in ['mobile payment', 'thank you', 'online payment', 'autopay']):
                    continue
                
                # Amex credits section — these are card credits
                if in_credits or 'platinum' in desc_lower or 'credit' in desc_lower.split()[-1:]:
                    if amount < 0 or (in_credits and amount > 0):
                        transactions.append({
                            'transaction_date': normalize_date(date_text),
                            'description': desc_text,
                            'amount': abs(amount),
                            'transaction_type': 'card_credit',
                            'category': 'Card Credit',
                            '_source': 'amex_xy'
                        })
                        continue
                
                # Regular charges
                if in_charges:
                    # Amex exports charges as positive — flip to negative
                    transactions.append({
                        'transaction_date': normalize_date(date_text),
                        'description': desc_text,
                        'amount': -abs(amount),
                        'transaction_type': 'expense',
                        '_source': 'amex_xy'
                    })
    
    return transactions

def normalize_date(date_str: str) -> str:
    """Convert MM/DD/YY or MM/DD/YYYY to YYYY-MM-DD."""
    parts = date_str.replace('*', '').strip().split('/')
    if len(parts) != 3:
        return date_str
    m, d, y = parts
    if len(y) == 2:
        y = '20' + y
    return f"{y}-{m.zfill(2)}-{d.zfill(2)}"

def parse_chase_xy(pdf_path: str = None, pdf_bytes: bytes = None) -> List[Dict]:
    """Parse Chase credit card PDF using text extraction."""
    import io
    transactions = []
    
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(io.BytesIO(pdf_bytes))
    
    # Chase date pattern: MM/DD (no year — use statement year)
    CHASE_DATE = re.compile(r'^(\d{2}/\d{2})$')
    CHASE_AMOUNT = re.compile(r'^-?[\d,]+\.\d{2}$')
    
    in_payments = False
    in_purchases = False
    year = None
    statement_month = None  # track the statement closing month
    
    with opener as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if not text:
                continue
            
            # Extract year from statement — use most common year
            from collections import Counter
            year_matches = re.findall(r'\b(20\d{2})\b', text)
            if year_matches and not year:
                year_counts = Counter(year_matches)
                year = year_counts.most_common(1)[0][0]

            # Extract statement closing month for year boundary detection
            if not statement_month:
                month_match = re.search(
                    r'\b(January|February|March|April|May|June|July|August|'
                    r'September|October|November|December)\s+(20\d{2})\b', text
                )
                if month_match:
                    month_names = ['january','february','march','april','may','june',
                                   'july','august','september','october','november','december']
                    statement_month = month_names.index(month_match.group(1).lower()) + 1
                    year = month_match.group(2)
            
            lines = text.split('\n')
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                line_lower = line.lower()
                
                # Section detection
                if 'payments and other credits' in line_lower:
                    in_payments = True
                    in_purchases = False
                    continue
                elif 'purchase' in line_lower and len(line) < 30:
                    in_payments = False
                    in_purchases = True
                    continue
                elif any(kw in line_lower for kw in ['interest charges', 'fees charged', 'year-to-date', 'account activity (continued)']):
                    # Don't reset — continued pages still have transactions
                    if 'interest charges' in line_lower or 'year-to-date' in line_lower:
                        in_payments = False
                        in_purchases = False
                    continue
                
                if not (in_payments or in_purchases):
                    continue
                
                # Try to parse: date + description + amount
                # Chase format: "10/01 MERCHANT NAME CITY ST 29.80"
                parts = line.split()
                if len(parts) < 2:
                    continue
                
                # Check first token is date
                if not CHASE_DATE.match(parts[0]):
                    continue
                
                # Last token should be amount
                amt_str = parts[-1]
                if not CHASE_AMOUNT.match(amt_str.replace(',','')):
                    continue
                
                amount = clean_amount(amt_str)
                if amount is None:
                    continue
                
                # Description is everything between date and amount
                # Remove trailing city state patterns e.g. "SEATTLE WA" or "800-123-4567"
                desc_parts = parts[1:-1]
                # Strip trailing 2-letter state code if preceded by city
                if len(desc_parts) >= 2 and len(desc_parts[-1]) == 2 and desc_parts[-1].isupper():
                    desc_parts = desc_parts[:-1]  # remove state
                    if desc_parts and not desc_parts[-1][0].isdigit():
                        desc_parts = desc_parts[:-1]  # remove city
                # Strip trailing phone numbers
                if desc_parts and re.match(r'^\d{3}-\d{3}-\d{4}$', desc_parts[-1]):
                    desc_parts = desc_parts[:-1]
                desc = ' '.join(desc_parts)
                
                # Skip noise
                desc_lower = desc.lower()
                if any(kw in desc_lower for kw in ['payment thank you', 'autopay', 'indian rupee', 'exchg rate', 'x 0.0']):
                    continue
                
                # Determine year — use statement year or infer
                date_str = parts[0]
                m, d = date_str.split('/')
                tx_year = year or '2025'
                tx_month_int = int(m)
                assigned_year = tx_year
                if statement_month and tx_year:
                    stmt_m = int(statement_month)
                    tx_y = int(tx_year)
                    if stmt_m <= 3 and tx_month_int >= 10:
                        assigned_year = str(tx_y - 1)
                    elif stmt_m == 12 and tx_month_int <= 2:
                        assigned_year = str(tx_y + 1)
                full_date = f"{assigned_year}-{m.zfill(2)}-{d.zfill(2)}"
                
                # Chase: payments section has negative=credit, positive=charge
                # Purchases section has positive=expense
                if in_payments:
                    desc_lower = desc.lower()
                    is_actual_payment = any(kw in desc_lower for kw in [
                        'payment thank you', 'autopay', 'online payment',
                        'mobile payment', 'payment received', 'thank you'
                    ])
                    if is_actual_payment:
                        tx_type = 'credit_card_payment'
                        final_amount = amount
                    else:
                        # In the payments/credits area: negative = refund/credit (money back),
                        # positive = a charge that landed here.
                        if amount < 0:
                            tx_type = 'refund'
                            final_amount = abs(amount)   # net out
                        else:
                            tx_type = 'expense'
                            final_amount = -abs(amount)
                else:
                    # Chase purchases section: positive = purchase, negative = refund.
                    if amount < 0:
                        tx_type = 'refund'
                        final_amount = abs(amount)   # refund: store positive so it nets out
                    else:
                        tx_type = 'expense'
                        final_amount = -abs(amount)  # purchase: store negative
                
                transactions.append({
                    'transaction_date': full_date,
                    'description': desc,
                    'amount': final_amount,
                    'transaction_type': tx_type,
                    '_source': 'chase_xy'
                })
    
    return transactions

def parse_bofa_xy(pdf_path: str = None, pdf_bytes: bytes = None) -> List[Dict]:
    """Parse BofA checking/savings PDF using x/y coordinates."""
    transactions = []
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(__import__('io').BytesIO(pdf_bytes))
    
    with opener as pdf:
        in_deposits = False
        in_withdrawals = False
        in_checks = False
        
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=2)
            rows = words_to_rows(words, y_tolerance=3.0)
            
            for row in rows:
                row_text = ' '.join(w['text'] for w in row)
                row_lower = row_text.lower()
                
                # Detect sections
                if 'deposits and other additions' in row_lower:
                    in_deposits = True
                    in_withdrawals = False
                    in_checks = False
                    continue
                elif 'withdrawals and' in row_lower or 'atm and debit' in row_lower or 'other subtractions' in row_lower:
                    in_deposits = False
                    in_withdrawals = True
                    in_checks = False
                    continue
                elif 'checks' in row_lower and len(row) < 4:
                    in_checks = True
                    in_withdrawals = False
                    continue
                elif 'service fees' in row_lower or 'ending balance' in row_lower:
                    in_deposits = False
                    in_withdrawals = False
                    in_checks = False
                    continue
                
                if should_skip_row(row_text):
                    continue
                
                # Extract fields
                date_text = row_text_in_range(row, 30, 88)
                desc_text = row_text_in_range(row, 88, 520)
                amt_text  = row_text_in_range(row, 520, 580)
                
                if not date_text or not is_date(date_text):
                    continue
                if not amt_text:
                    continue
                
                amount = clean_amount(amt_text)
                if amount is None:
                    continue
                
                desc_lower = desc_text.lower()
                
                # Skip internal transfers and noise
                if any(kw in desc_lower for kw in ['total deposits', 'total withdrawals', 'beginning balance', 'ending balance']):
                    continue
                
                # Determine type
                if in_deposits:
                    # Check if it's payroll/income
                    if any(kw in desc_lower for kw in ['stripe', 'payroll', 'direct dep', 'ach credit', 'salary', 'zelle payment from']):
                        tx_type = 'income'
                    else:
                        tx_type = 'income'
                    amount = abs(amount)
                elif in_withdrawals:
                    tx_type = 'expense'
                    amount = -abs(amount)
                else:
                    continue
                
                transactions.append({
                    'transaction_date': normalize_date(date_text),
                    'description': desc_text,
                    'amount': amount,
                    'transaction_type': tx_type,
                    '_source': 'bofa_xy'
                })
    
    return transactions

def parse_pdf_xy(pdf_bytes: bytes, bank: str) -> Tuple[List[Dict], int]:
    """Main entry point — parse PDF by bank using x/y method."""
    bank_lower = (bank or '').lower()
    
    try:
        if 'amex' in bank_lower or 'american express' in bank_lower:
            txs = parse_amex_xy(pdf_bytes=pdf_bytes)
        elif 'chase' in bank_lower:
            txs = parse_chase_xy(pdf_bytes=pdf_bytes)
        elif 'bofa' in bank_lower or 'bank of america' in bank_lower or 'bankofamerica' in bank_lower:
            txs = parse_bofa_xy(pdf_bytes=pdf_bytes)
        elif 'discover' in bank_lower:
            txs, _ = parse_discover_xy(pdf_bytes=pdf_bytes)
        elif 'wells fargo' in bank_lower or 'wellsfargo' in bank_lower:
            import io, pdfplumber
            with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
                text = pdf.pages[0].extract_text() or ''
            if any(k in text.lower() for k in ['credit limit','minimum payment','new balance','purchases/debits']):
                txs, _ = parse_wellsfargo_credit_xy(pdf_bytes=pdf_bytes)
            else:
                txs, _ = parse_wellsfargo_banking_xy(pdf_bytes=pdf_bytes)
        elif 'macys' in bank_lower or 'macy' in bank_lower:
            txs, _ = parse_macys_citi_xy(pdf_bytes=pdf_bytes)
        else:
            return [], 0

        return txs, len(txs)
    except Exception as e:
        print(f"XY parser error: {e}")
        import traceback; traceback.print_exc()
        return [], 0


def parse_wellsfargo_credit_xy(pdf_path=None, pdf_bytes=None):
    """Parse Wells Fargo credit card (Bilt) PDF.
    Format: Trans Date | Post Date | Ref# | RefHash | Description | $Amount
    """
    import io, re
    from collections import Counter
    transactions = []
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(io.BytesIO(pdf_bytes))

    # MM/DD MM/DD REFNUM REFHASH DESCRIPTION $AMOUNT
    TX_RE = re.compile(
        r'^(\d{2}/\d{2})\s+\d{2}/\d{2}\s+\d+\s+\S+\s+(.+?)\s+\$(-?[\d,]+\.\d{2})$'
    )
    SKIP = ['total fees','total interest','year-to-date','biltprotect','interest charge',
            'fees charged','interest charged','transaction summary']

    year = None
    statement_month = None

    with opener as pdf:
        full_text = ''
        for page in pdf.pages:
            full_text += (page.extract_text() or '') + '\n'

        # Extract year and statement month
        years = re.findall(r'\b(20\d{2})\b', full_text)
        if years:
            year = Counter(years).most_common(1)[0][0]
        m = re.search(r'Payment Due Date\s+(\d{2})/(\d{2})/(\d{4})', full_text)
        if m:
            statement_month = int(m.group(1))
            year = m.group(3)

        for line in full_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in SKIP):
                continue

            match = TX_RE.match(line)
            if not match:
                continue

            date_str = match.group(1)
            desc = match.group(2).strip()
            amount_str = match.group(3).replace(',', '')
            amount = float(amount_str)

            m_str, d_str = date_str.split('/')
            tx_month = int(m_str)
            assigned_year = year or '2026'
            if statement_month and year:
                stmt_m = int(statement_month)
                tx_y = int(year)
                if stmt_m <= 3 and tx_month >= 10:
                    assigned_year = str(tx_y - 1)
                elif stmt_m == 12 and tx_month <= 2:
                    assigned_year = str(tx_y + 1)

            full_date = f"{assigned_year}-{m_str.zfill(2)}-{d_str.zfill(2)}"

            if amount < 0:
                tx_type = 'card_credit'
                final_amount = abs(amount)
            else:
                tx_type = 'expense'
                final_amount = -amount

            transactions.append({
                'transaction_date': full_date,
                'description': desc,
                'amount': final_amount,
                'transaction_type': tx_type,
                'category': 'Card Credit' if tx_type == 'card_credit' else 'Other',
                '_source': 'wf_credit_xy'
            })

    return transactions, len(transactions)


def parse_wellsfargo_banking_xy(pdf_path=None, pdf_bytes=None):
    """Parse Wells Fargo checking/savings banking statement."""
    import io, re
    transactions = []
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(io.BytesIO(pdf_bytes))

    DATE_RE = re.compile(r'^(\d{1,2}/\d{1,2})$')
    AMOUNT_RE = re.compile(r'^[\d,]+\.\d{2}$')
    SKIP_KEYWORDS = ['beginning balance','ending balance','ending daily','date number',
                     'deposits/additions','withdrawals/subtractions','transaction history',
                     'check deposits','summary of accounts','statement period']

    year = None

    with opener as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ''

            # Extract year from statement date
            if not year:
                m = re.search(r'(January|February|March|April|May|June|July|August|September|October|November|December)\s+\d+,\s+(20\d{2})', text)
                if m:
                    year = m.group(2)
                else:
                    years = re.findall(r'\b(20\d{2})\b', text)
                    if years:
                        from collections import Counter
                        year = Counter(years).most_common(1)[0][0]

            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            rows = {}
            for w in words:
                y_key = round(w['top'] / 4) * 4
                rows.setdefault(y_key, []).append(w)

            for y_key in sorted(rows):
                row_words = sorted(rows[y_key], key=lambda w: w['x0'])
                parts = [w['text'] for w in row_words]
                x_positions = [w['x0'] for w in row_words]

                if not parts or not DATE_RE.match(parts[0]):
                    continue

                line = ' '.join(parts).lower()
                if any(kw in line for kw in SKIP_KEYWORDS):
                    continue

                # WF banking: Date | Check# (optional) | Description | Additions | Subtractions | Balance
                # Additions column ~x=350-420, Subtractions ~x=420-490
                m_str, d_str = parts[0].split('/')
                date_str = f"{year or '2026'}-{m_str.zfill(2)}-{d_str.zfill(2)}"

                # Find amounts by x position
                # Rightmost amounts are balance, second-right is debit/credit
                amounts_with_x = []
                desc_parts = []
                for i, (p, x) in enumerate(zip(parts[1:], x_positions[1:]), 1):
                    clean = p.replace(',','')
                    if AMOUNT_RE.match(clean):
                        amounts_with_x.append((float(clean), x))
                    else:
                        desc_parts.append(p)

                if not amounts_with_x:
                    continue

                desc = ' '.join(desc_parts).strip()
                if not desc or len(desc) < 3:
                    continue

                # Skip check numbers as description
                if re.match(r'^\d{3,6}$', desc):
                    continue

                # Sort amounts by x position
                amounts_with_x.sort(key=lambda a: a[1])

                # Balance is rightmost, transaction amount is second-rightmost
                if len(amounts_with_x) >= 2:
                    tx_amount = amounts_with_x[-2][0]
                    tx_x = amounts_with_x[-2][1]
                    # If x > 400 it's likely a debit (subtraction column)
                    is_debit = tx_x > 380
                else:
                    tx_amount = amounts_with_x[0][0]
                    is_debit = True

                # Classify
                desc_lower = desc.lower()
                if any(kw in desc_lower for kw in ['zelle to','transfer to','withdrawal','withdrwl']):
                    tx_type = 'transfer'
                    amount = -tx_amount
                elif any(kw in desc_lower for kw in ['payroll','direct dep','zelle from','deposit']):
                    tx_type = 'income'
                    amount = tx_amount
                elif any(kw in desc_lower for kw in ['american express','chase credit','citi payment','discover']):
                    tx_type = 'credit_card_payment'
                    amount = -tx_amount
                elif is_debit:
                    tx_type = 'expense'
                    amount = -tx_amount
                else:
                    tx_type = 'income'
                    amount = tx_amount

                transactions.append({
                    'transaction_date': date_str,
                    'description': desc,
                    'amount': amount,
                    'transaction_type': tx_type,
                    'category': 'Other',
                    '_source': 'wf_banking_xy'
                })

    return transactions, len(transactions)


def parse_macys_citi_xy(pdf_path=None, pdf_bytes=None):
    """Parse Macy's/Citi credit card statement.
    Format: Month DD | DESCRIPTION | LOCATION (CA) | $AMOUNT
    Skip sub-lines: BAG FEE, SALES TAX, RECEIPT TOTAL, OTHER PAY TYPE
    """
    import io, re
    transactions = []
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(io.BytesIO(pdf_bytes))

    MONTHS = {'jan':1,'feb':2,'mar':3,'apr':4,'may':5,'jun':6,
              'jul':7,'aug':8,'sep':9,'oct':10,'nov':11,'dec':12}

    # Match: "Jan 03 DESCRIPTION LOCATION $AMOUNT" or "Jan 03 DESCRIPTION $AMOUNT"
    TX_RE = re.compile(
        r'^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+(\d{1,2})\s+(.+?)\s+(-?\$[\d,]+\.\d{2})$',
        re.IGNORECASE
    )

    SKIP_LINES = ['bag fee','sales tax','receipt total','other pay type','total fees',
                  'total interest','year-to-date','total card ending','transaction date',
                  'macy\'s transactions','fees charged','interest charged','activity and',
                  'promotion','this page intentionally']

    SKIP_DESC = ['payment - thank you', 'total fees', 'total interest']

    year = None

    with opener as pdf:
        full_text = '\n'.join(p.extract_text() or '' for p in pdf.pages)

        # Extract year from due date
        m = re.search(r'Payment Due Date\s+\w+\s+\d+,\s+(\d{4})', full_text)
        if m:
            year = m.group(1)
        else:
            years = re.findall(r'\b(20\d{2})\b', full_text)
            if years:
                from collections import Counter
                year = Counter(years).most_common(1)[0][0]

        stmt_month = None
        m2 = re.search(r'Payment Due Date\s+(\w+)\s+\d+,\s+\d{4}', full_text)
        if m2:
            stmt_month = MONTHS.get(m2.group(1).lower()[:3])

        for line in full_text.split('\n'):
            line = line.strip()
            if not line:
                continue
            if any(kw in line.lower() for kw in SKIP_LINES):
                continue

            match = TX_RE.match(line)
            if not match:
                continue

            month_str = match.group(1).lower()[:3]
            day = match.group(2)
            desc = match.group(3).strip()
            amount_str = match.group(4).replace('$','').replace(',','')
            amount = float(amount_str)

            if any(kw in desc.lower() for kw in SKIP_DESC):
                # CC payments
                if 'payment' in desc.lower():
                    tx_month = MONTHS[month_str]
                    assigned_year = year or '2026'
                    if stmt_month and year:
                        if int(stmt_month) <= 3 and tx_month >= 10:
                            assigned_year = str(int(year) - 1)
                    full_date = f"{assigned_year}-{str(MONTHS[month_str]).zfill(2)}-{day.zfill(2)}"
                    transactions.append({
                        'transaction_date': full_date,
                        'description': desc,
                        'amount': amount,  # negative = payment
                        'transaction_type': 'credit_card_payment',
                        'category': 'Credit Card Payment',
                        '_source': 'macys_citi_xy'
                    })
                continue

            # Remove location suffix like "VALLEY FAIR (CA)" from description
            desc_clean = re.sub(r'\s+[A-Z\s]+\([A-Z]{2}\)$', '', desc).strip()
            if not desc_clean:
                desc_clean = desc

            tx_month = MONTHS[month_str]
            assigned_year = year or '2026'
            if stmt_month and year:
                if int(stmt_month) <= 3 and tx_month >= 10:
                    assigned_year = str(int(year) - 1)
                elif int(stmt_month) == 12 and tx_month <= 2:
                    assigned_year = str(int(year) + 1)

            full_date = f"{assigned_year}-{str(tx_month).zfill(2)}-{day.zfill(2)}"

            tx_type = 'expense' if amount > 0 else 'card_credit'
            final_amount = -amount if tx_type == 'expense' else abs(amount)

            transactions.append({
                'transaction_date': full_date,
                'description': desc_clean,
                'amount': final_amount,
                'transaction_type': tx_type,
                'category': 'Card Credit' if tx_type == 'card_credit' else 'Other',
                '_source': 'macys_citi_xy'
            })

    return transactions, len(transactions)


def decode_discover(s: str) -> str:
    """Decode Discover's custom font encoding (offset = 29)."""
    return ''.join(chr(ord(c) + 29) if 0 < ord(c) < 127 else c for c in s)


def parse_discover_xy(pdf_path=None, pdf_bytes=None):
    """Parse Discover credit card PDF using custom font decoder."""
    import io, re
    from collections import Counter
    transactions = []
    opener = pdfplumber.open(pdf_path) if pdf_path else pdfplumber.open(io.BytesIO(pdf_bytes))

    SKIP = ['previous balance','total fees for this period','total interest for this period',
            'redeemed this period','earned this period','fees and interest charged',
            'cashback bonus balance','year-to-date','interest charge calculation']

    DATE_RE = re.compile(r'^\d{2}/\d{2}$')
    AMOUNT_RE = re.compile(r'^-?\$[\d,]+\.\d{2}$')

    year = None
    statement_month = None

    with opener as pdf:
        for page in pdf.pages:
            words = page.extract_words(x_tolerance=3, y_tolerance=3)
            if not words:
                continue

            # Decode all words
            decoded_words = []
            for w in words:
                decoded = decode_discover(w['text'])
                decoded_words.append({**w, 'text': decoded})

            # Extract year from decoded text
            full_text = ' '.join(w['text'] for w in decoded_words)
            if not year:
                years = re.findall(r'\b(20\d{2})\b', full_text)
                if years:
                    year = Counter(years).most_common(1)[0][0]
            if not statement_month:
                m = re.search(r'OPEN TO CLOSE DATE\s*(\d{2})/\d{2}/(\d{4})\s*-\s*(\d{2})/\d{2}/(\d{4})', full_text)
                if m:
                    statement_month = int(m.group(3))
                    year = m.group(4)

            # Group by y position
            rows = {}
            for w in decoded_words:
                y_key = round(w['top'] / 5) * 5
                rows.setdefault(y_key, []).append(w)

            for y_key in sorted(rows):
                parts = [w['text'] for w in sorted(rows[y_key], key=lambda w: w['x0'])]
                line = ' '.join(parts).strip()

                if not parts or not DATE_RE.match(parts[0]):
                    continue
                if any(kw in line.lower() for kw in SKIP):
                    continue

                # Join split amounts like ['-$14', '.13'] -> '-$14.13'
                joined_parts = []
                i = 0
                while i < len(parts):
                    p = parts[i]
                    # Check if next part is a decimal continuation
                    if i + 1 < len(parts) and re.match(r'^[.]\d{2}$', parts[i+1]):
                        joined_parts.append(p + parts[i+1])
                        i += 2
                    else:
                        joined_parts.append(p)
                        i += 1
                parts = joined_parts

                # Find amount — last token matching $X.XX
                amount = None
                desc_parts = []
                SKIP_CATS = ['services','merchandise','restaurants','travel','automotive',
                             'cashback bonus','% cashback']
                for p in parts[1:]:
                    if AMOUNT_RE.match(p):
                        amount = float(p.replace('$','').replace(',',''))
                    elif not any(cat in p.lower() for cat in SKIP_CATS):
                        desc_parts.append(p)

                if amount is None:
                    continue

                desc = ' '.join(desc_parts).strip()
                # Remove location suffix, phone numbers, extra noise
                desc = re.sub(r'\s+[A-Z]{2}$', '', desc).strip()
                desc = re.sub(r'\s+\d{3}-\d{3}-\d{4}.*$', '', desc).strip()
                desc = re.sub(r'\s+\d{6,}.*$', '', desc).strip()  # remove long number sequences
                desc = re.sub(r'\s+\d{3,}\s*[A-Z]{2}$', '', desc).strip()  # "454 CA"
                desc = re.sub(r'\s+\+\$[\d.]+$', '', desc).strip()  # "+$1.43" cashback
                desc = re.sub(r'\s{2,}', ' ', desc).strip()  # double spaces

                if not desc or len(desc) < 2:
                    continue

                m_str, d_str = parts[0].split('/')
                tx_month = int(m_str)
                assigned_year = year or '2026'
                if statement_month and year:
                    stmt_m = int(statement_month)
                    tx_y = int(year)
                    if stmt_m <= 3 and tx_month >= 10:
                        assigned_year = str(tx_y - 1)
                    elif stmt_m == 12 and tx_month <= 2:
                        assigned_year = str(tx_y + 1)

                full_date = f"{assigned_year}-{m_str.zfill(2)}-{d_str.zfill(2)}"

                if amount < 0:
                    tx_type = 'credit_card_payment'
                    final_amount = amount
                else:
                    tx_type = 'expense'
                    final_amount = -amount

                transactions.append({
                    'transaction_date': full_date,
                    'description': desc,
                    'amount': final_amount,
                    'transaction_type': tx_type,
                    'category': 'Other',
                    '_source': 'discover_xy'
                })

    return transactions, len(transactions)

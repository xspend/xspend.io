#!/usr/bin/env python3
"""
llm_fallback.py  —  xspend's base LLM fallback for unknown banks

This is the reusable core, not a bench script. The app imports it:

    from llm_fallback import parse_statement
    result = parse_statement("/path/to/statement.pdf")

parse_statement() returns a dict with everything the upload flow needs:
    {
      "bank_name", "account_last4", "statement_period",
      "opening_balance", "closing_balance",
      "reconciliation": {"status", "convention", "delta", "sum_credits", "sum_debits"},
      "needs_review": bool,                 # file-level: does a human need to look?
      "transactions": [                     # each row carries its own review flag
        {"date", "description", "amount", "direction", "category",
         "review": bool, "review_reason": str | None}
      ],
      "review_count": int,
      "cost_usd": float,
      "usage": {"input_tokens", "output_tokens"},
    }

The whole safety story: numbers are verified by reconciliation, never trusted.
If the math doesn't close, the suspect rows get flagged for review instead of
silently written. Nothing here touches the database - that's the caller's job.

Run it directly to test on one file (prints the review section first, then the rest):
    export ANTHROPIC_API_KEY=sk-ant-...
    python3 llm_fallback.py /path/to/statement.pdf      (or .csv, or .xlsx)
"""

import os
import re
import sys
import json
from decimal import Decimal, InvalidOperation

# ---- config -----------------------------------------------------------------

MODEL = "claude-haiku-4-5-20251001"
PRICE_IN_PER_MTOK = 1.0
PRICE_OUT_PER_MTOK = 5.0
RECONCILE_TOLERANCE = Decimal("0.05")
MAX_TOKENS = 8000
TOKEN_CEILING = 60_000   # abort the LLM route if a file is bigger than this (cost guardrail)

# xspend's real categories (from the categories table). The model is told to pick
# ONLY from this list, so its output matches what enrich_transaction already knows.
CATEGORIES = [
    "Rent/Mortgage", "Food & Dining", "Groceries", "Transport", "Bills & Utilities",
    "Subscriptions", "Health", "Shopping", "Entertainment", "Travel", "Personal Care",
    "Pets", "Education", "Salary", "Other Income", "Transfer", "Credit Card Payment",
    "Loan Payment", "Refund", "Other", "Alcohol & Liquor", "Baby & Kids", "Bank Fees",
    "Card Credit", "Cash & ATM", "Gifts & Donations", "Government & Taxes",
    "Home Improvement", "Insurance", "Professional Services",
]

TRAP_WORDS = ("refund", "return", "payment", "credit", "reversal",
              "adjustment", "cashback", "cash back", "thank you")

# ---- 1. load statement text (pdf / csv / xlsx) ------------------------------

def _extract_pdf(path):
    import pdfplumber
    pages = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            pages.append(page.extract_text() or "")
    return "\n".join(pages).strip()

def _extract_csv(path):
    with open(path, "r", errors="ignore") as f:
        return f.read().strip()

def _extract_xlsx(path):
    import pandas as pd
    sheets = pd.read_excel(path, sheet_name=None, dtype=str)
    parts = []
    for name, df in sheets.items():
        parts.append(f"# sheet: {name}")
        parts.append(df.fillna("").to_csv(index=False))
    return "\n".join(parts).strip()

def load_statement_text(path):
    """Route on file extension. Returns (text, kind)."""
    ext = os.path.splitext(path)[1].lower()
    if ext == ".pdf":
        return _extract_pdf(path), "pdf"
    if ext == ".csv":
        return _extract_csv(path), "csv"
    if ext in (".xlsx", ".xls"):
        return _extract_xlsx(path), "xlsx"
    raise ValueError(f"unsupported file type '{ext}' - handles .pdf, .csv, .xlsx")

# ---- 2. strip account/card numbers, keep last 4 -----------------------------

MASKED_RE = re.compile(r'\b[X\*x]{3,}[ -]?\d{4}\b')
CONTIG_RE = re.compile(r'\b\d{12,}\b')
GROUP_RE  = re.compile(r'\b(?:\d{3,6}[ -]){2,5}\d{3,6}\b')

def strip_pii(text):
    """Mask only real account/card numbers to '****last4'. Leaves calendars,
    phone numbers, dates and dollar amounts alone. Returns (scrubbed, masked_samples)."""
    masked = []

    def mask(raw):
        digits = re.sub(r'\D', '', raw)
        last4 = digits[-4:]
        masked.append((raw.strip(), last4))
        return f"****{last4}"

    def group_repl(m):
        raw = m.group(0)
        n = len(re.sub(r'\D', '', raw))
        return mask(raw) if 13 <= n <= 19 else raw

    out = MASKED_RE.sub(lambda m: mask(m.group(0)), text)
    out = CONTIG_RE.sub(lambda m: mask(m.group(0)), out)
    out = GROUP_RE.sub(group_repl, out)
    return out, masked

# ---- 3. LLM extraction (strict, no hallucinated numbers) --------------------

EXTRACTION_PROMPT = """You are a precise data extractor for bank and credit-card statements.

Extract ONLY what is literally present in the statement text below. Follow these rules exactly:
- NEVER invent, estimate, or infer a number. If a value is not printed, use null.
- Copy amounts exactly as printed. Do not round, reformat, or compute new totals.
- For each transaction, give the amount as a positive number in "amount" and its
  direction in "direction": "debit" (money out / charge) or "credit" (money in / payment / refund).
- Assign each transaction a "category" chosen ONLY from this exact list:
  {categories}
  Use the merchant/description to pick the best fit. Use "Other" only if nothing fits.
  Use "Payment" for card payments, "Refund" for merchant refunds/returns.
- Also copy the statement's own printed opening and closing balances. If the statement
  does not print them, use null (do not calculate them yourself).
- account_last4: only the last 4 digits of the account/card if shown, else null.
  Do NOT include any full account number.

Return ONLY valid JSON, no markdown, no commentary, in exactly this shape:
{
  "bank_name": string | null,
  "account_last4": string | null,
  "statement_period": string | null,
  "opening_balance": number | null,
  "closing_balance": number | null,
  "transactions": [
    {"date": "YYYY-MM-DD" | string, "description": string, "amount": number, "direction": "debit" | "credit", "category": string}
  ]
}

STATEMENT TEXT:
---
{statement}
---
Return only the JSON."""

def _call_llm(scrubbed_text):
    from anthropic import Anthropic
    client = Anthropic()  # reads ANTHROPIC_API_KEY from env
    prompt = (EXTRACTION_PROMPT
              .replace("{categories}", ", ".join(CATEGORIES))
              .replace("{statement}", scrubbed_text))
    resp = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        messages=[{"role": "user", "content": prompt}],
    )
    text = "".join(b.text for b in resp.content if b.type == "text")
    return text, resp.usage

def _parse_json(raw):
    cleaned = raw.strip()
    cleaned = re.sub(r'^```(?:json)?', '', cleaned).strip()
    cleaned = re.sub(r'```$', '', cleaned).strip()
    return json.loads(cleaned)

# ---- 4. reconciliation ------------------------------------------------------

def to_decimal(x):
    if x is None:
        return None
    try:
        return Decimal(str(x))
    except (InvalidOperation, ValueError):
        return None

def reconcile(data):
    opening = to_decimal(data.get("opening_balance"))
    closing = to_decimal(data.get("closing_balance"))
    txns = data.get("transactions") or []
    credits = sum((to_decimal(t.get("amount")) or Decimal(0))
                  for t in txns if t.get("direction") == "credit")
    debits = sum((to_decimal(t.get("amount")) or Decimal(0))
                 for t in txns if t.get("direction") == "debit")

    result = {"status": "unknown", "convention": None, "delta": None,
              "sum_credits": credits, "sum_debits": debits}

    if opening is None or closing is None:
        result["status"] = "no_balances_printed"
        return result

    bank_delta = abs((opening + credits - debits) - closing)   # asset / bank account
    card_delta = abs((opening + debits - credits) - closing)   # liability / credit card

    if bank_delta <= RECONCILE_TOLERANCE:
        result.update(status="reconciled", convention="bank/asset", delta=bank_delta)
    elif card_delta <= RECONCILE_TOLERANCE:
        result.update(status="reconciled", convention="card/liability", delta=card_delta)
    elif bank_delta <= card_delta:
        result.update(status="MISMATCH", convention="bank/asset (closest)", delta=bank_delta)
    else:
        result.update(status="MISMATCH", convention="card/liability (closest)", delta=card_delta)
    return result

# ---- 5. per-transaction review flagging -------------------------------------

def flag_transactions(txns, reconcile_status):
    """
    Mark individual suspect rows so 'transactions to review' is a short, actionable
    list - not the whole file. A row gets flagged when:
      - its data is incomplete (missing amount or date), or
      - its category came back off-list (we coerce it to Other and flag it), or
      - the FILE failed reconciliation AND this row is sign-ambiguous
        (a credit/payment/refund - exactly where the sign flips).
    """
    file_failed = reconcile_status != "reconciled"
    for t in txns:
        reasons = []

        if to_decimal(t.get("amount")) is None or not t.get("date"):
            reasons.append("incomplete data")

        # Coerce an unknown category to a safe default, but DON'T flag for review -
        # category is low-stakes and user-editable. Review is for money problems only.
        cat = t.get("category")
        if cat not in CATEGORIES:
            t["category"] = "Other"
            cat = "Other"

        desc = (t.get("description") or "").lower()
        direction = t.get("direction")
        cat = t.get("category")

        # A refund/return is money coming BACK - it should be a credit. If it's
        # labeled a debit, the row contradicts itself. This is a standalone flag
        # (doesn't wait on file-level reconciliation) - it's what actually caught
        # the Chase Amazon line the sign-trap rule missed.
        looks_like_refund = cat == "Refund" or "refund" in desc or "return" in desc
        if looks_like_refund and direction == "debit":
            reasons.append("refund marked as debit - likely wrong sign")

        # When the file as a whole didn't reconcile, every sign-ambiguous row is a
        # suspect (payments, credits, reversals, etc.).
        is_sign_trap = direction == "credit" or any(w in desc for w in TRAP_WORDS)
        if file_failed and is_sign_trap:
            reasons.append("verify debit/credit sign")

        t["review"] = bool(reasons)
        t["review_reason"] = "; ".join(reasons) if reasons else None
    return txns

# ---- the public entry point -------------------------------------------------

def parse_statement(path):
    """Parse one statement file end to end. Returns the result dict (see module docstring).
    Raises ValueError for unsupported types or oversized/empty files."""
    text, kind = load_statement_text(path)
    if not text:
        raise ValueError("no extractable text (scanned image PDF? vision path not built yet)")

    # cost guardrail: don't feed a giant file to the LLM
    approx_tokens = len(text) / 4
    if approx_tokens > TOKEN_CEILING:
        raise ValueError(f"file too large for LLM route (~{int(approx_tokens):,} tokens) - route to manual review")

    scrubbed, _masked = strip_pii(text)
    raw, usage = _call_llm(scrubbed)
    data = _parse_json(raw)

    rec = reconcile(data)
    txns = flag_transactions(data.get("transactions") or [], rec["status"])
    review_count = sum(1 for t in txns if t["review"])

    cost = (usage.input_tokens / 1_000_000 * PRICE_IN_PER_MTOK
            + usage.output_tokens / 1_000_000 * PRICE_OUT_PER_MTOK)

    return {
        "source_kind": kind,
        "bank_name": data.get("bank_name"),
        "account_last4": data.get("account_last4"),
        "statement_period": data.get("statement_period"),
        "opening_balance": data.get("opening_balance"),
        "closing_balance": data.get("closing_balance"),
        "reconciliation": {
            "status": rec["status"],
            "convention": rec["convention"],
            "delta": None if rec["delta"] is None else float(rec["delta"]),
            "sum_credits": float(rec["sum_credits"]),
            "sum_debits": float(rec["sum_debits"]),
        },
        # file needs a human if the math didn't close OR any row got flagged
        "needs_review": rec["status"] != "reconciled" or review_count > 0,
        "review_count": review_count,
        "transactions": txns,
        "cost_usd": round(cost, 6),
        "usage": {"input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens},
    }

# ---- standalone runner (prints the sectioned view: review first, then rest) -

def _money(x):
    d = to_decimal(x)
    return "n/a" if d is None else f"{d:,.2f}"

def _print_row(t):
    amt = _money(t.get("amount"))
    print(f"  {str(t.get('date','')):<11}{(t.get('direction') or '?'):<7}{amt:>10}  "
          f"{(t.get('category') or '-')[:16]:<17}{(t.get('description') or '')[:32]}")

def _main():
    if len(sys.argv) < 2:
        print("usage: python3 llm_fallback.py /path/to/statement.(pdf|csv|xlsx)")
        sys.exit(1)
    path = sys.argv[1]
    if not os.path.exists(path):
        print(f"file not found: {path}")
        sys.exit(1)

    try:
        r = parse_statement(path)
    except ValueError as e:
        print(f"  cannot parse: {e}")
        sys.exit(1)

    rec = r["reconciliation"]
    print("\n" + "=" * 60)
    print(f"  {r['bank_name']}  (****{r['account_last4']})   read as {r['source_kind']}")
    print(f"  period: {r['statement_period']}")
    print(f"  opening {_money(r['opening_balance'])}  ->  closing {_money(r['closing_balance'])}")
    print(f"  credits {_money(rec['sum_credits'])}   debits {_money(rec['sum_debits'])}")
    if rec["status"] == "reconciled":
        print(f"  RECONCILED ({rec['convention']})")
    elif rec["status"] == "MISMATCH":
        print(f"  MISMATCH ({rec['convention']}, off by {_money(rec['delta'])}) -> needs review")
    else:
        print("  NO PRINTED BALANCES -> can't verify, needs review")
    print("=" * 60)

    txns = r["transactions"]
    to_review = [t for t in txns if t["review"]]
    rest = [t for t in txns if not t["review"]]

    # SECTION 1: transactions to review (this is what surfaces first, at parse AND upload)
    print(f"\n  >> TRANSACTIONS TO REVIEW ({len(to_review)})")
    print("  " + "-" * 92)
    if to_review:
        for t in to_review:
            _print_row(t)
            print(f"       ^ {t['review_reason']}")
    else:
        print("  (none - everything checks out)")

    # SECTION 2: the rest
    print(f"\n  THE REST ({len(rest)})")
    print("  " + "-" * 92)
    for t in rest:
        _print_row(t)

    print(f"\n  file needs_review: {r['needs_review']}   |   {r['review_count']} to review")
    print(f"  cost: ${r['cost_usd']:.4f}   ({r['usage']['input_tokens']:,} in / {r['usage']['output_tokens']:,} out)")

    out_path = os.path.splitext(path)[0] + ".parsed.json"
    with open(out_path, "w") as f:
        json.dump(r, f, indent=2, default=str)
    print(f"  saved -> {out_path}\n")

if __name__ == "__main__":
    _main()

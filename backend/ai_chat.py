"""
ai_chat.py — xspend conversational assistant.

get_ai_response(message, tx_list) builds a compact, precise summary of the user's
transactions in Python (so the model gets clean numbers, not hundreds of raw rows),
then asks Claude to answer in plain, non-technical, ~5-second language.

The .env ANTHROPIC_API_KEY is loaded by main.py (load_dotenv) before this is called;
we also call load_dotenv() here defensively.
"""

import os
from collections import defaultdict

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

# Model: a current Claude model. Adjust if your account uses a different alias.
_MODEL = os.getenv("XSPEND_CHAT_MODEL", "claude-3-5-sonnet-20241022")

# Spending = expenses only (mirrors the dashboard definition).
_EXCLUDED_TYPES = {
    "income", "transfer", "credit_card_payment",
    "card_credit", "refund", "excluded", "reimbursement",
}


def _money(n):
    try:
        return f"${abs(float(n)):,.0f}"
    except Exception:
        return "$0"


def _month_of(t):
    return (t.get("date") or t.get("transaction_date") or "")[:7]


def months_with_data(tx_list, min_txns=3):
    """Return [(ym, count), ...] newest first, only months with real data.
    Used to drive the chat month picker so stray boundary rows don't show up."""
    from collections import Counter
    c = Counter(_month_of(t) for t in (tx_list or []) if _month_of(t))
    return sorted(((ym, n) for ym, n in c.items() if n >= min_txns),
                  key=lambda kv: kv[0], reverse=True)


def _build_summary(tx_list, month=None):
    """Compute a spec-compliant summary.

    month: "YYYY-MM" to summarize a specific month. If None, use the latest
    month that has MEANINGFUL data (>= 3 txns) so a lone statement-boundary
    row doesn't select a near-empty month.

    Money In  = income + refunds + zelle_in (positive transfers)
    Money Out = (gross expenses - card_credit) + cash + zelle_out (neg transfers)
    Net       = Money In - Money Out
    Excluded  = credit_card_payment, excluded
    """
    if not tx_list:
        return None

    all_months = sorted({_month_of(t) for t in tx_list if _month_of(t)})

    if month:
        latest = month
    else:
        meaningful = months_with_data(tx_list)
        latest = meaningful[0][0] if meaningful else (all_months[-1] if all_months else None)

    months = all_months
    month_txs = [t for t in tx_list if _month_of(t) == latest] if latest else tx_list

    income_total = 0.0
    refunds_total = 0.0
    card_credit_total = 0.0
    zelle_in_total = 0.0
    zelle_out_total = 0.0
    cash_total = 0.0
    gross_expenses = 0.0
    spend_by_cat = defaultdict(float)
    expenses = []  # (amount_abs, description, category)
    big_refunds = []   # (amount, description) for the disclaimer
    big_credits = []   # (amount, description)

    for t in month_txs:
        ttype = (t.get("transaction_type") or "expense").lower()
        amt = float(t.get("amount") or 0)

        if ttype == "income":
            if amt > 0:
                income_total += amt
            continue
        if ttype == "refund":
            refunds_total += abs(amt)
            if abs(amt) >= 200:
                big_refunds.append((abs(amt), t.get("description") or "refund"))
            continue
        if ttype == "card_credit":
            card_credit_total += abs(amt)
            if abs(amt) >= 200:
                big_credits.append((abs(amt), t.get("description") or "statement credit"))
            continue
        if ttype == "transfer":
            if amt > 0:
                zelle_in_total += amt            # money in = offset
            else:
                zelle_out_total += abs(amt)      # money out
            continue
        if ttype == "cash":
            cash_total += abs(amt)
            continue
        if ttype in ("credit_card_payment", "excluded", "reimbursement"):
            continue  # excluded from cash flow

        # Remaining = expense
        a = abs(amt)
        gross_expenses += a
        cat = t.get("category") or "Other"
        spend_by_cat[cat] += a
        expenses.append((a, t.get("description") or "Unknown", cat))

    net_expenses = gross_expenses - card_credit_total  # credits offset spend
    money_in = income_total + refunds_total + zelle_in_total
    money_out = net_expenses + cash_total + zelle_out_total
    net = money_in - money_out

    top_cats = sorted(spend_by_cat.items(), key=lambda kv: kv[1], reverse=True)
    top_expenses = sorted(expenses, key=lambda e: e[0], reverse=True)[:5]
    accounts = sorted({t.get("bank_source") for t in month_txs if t.get("bank_source")})

    return {
        "month": latest,
        "all_months": months,
        "n_months": len(months),
        "accounts": accounts,
        "income_total": income_total,
        "refunds_total": refunds_total,
        "card_credit_total": card_credit_total,
        "zelle_in_total": zelle_in_total,
        "zelle_out_total": zelle_out_total,
        "cash_total": cash_total,
        "gross_expenses": gross_expenses,
        "net_expenses": net_expenses,
        "money_in": money_in,
        "money_out": money_out,
        "net": net,
        "top_cats": top_cats,
        "top_expenses": top_expenses,
        "big_refunds": big_refunds,
        "big_credits": big_credits,
    }


def build_disclaimer(s):
    """A context-aware '*' note built from what the data actually contained."""
    if not s:
        return "*No transactions uploaded yet, so there's nothing to calculate."
    notes = []
    if s["income_total"] == 0:
        notes.append("no income was found in your uploads, so this reflects spending "
                     "only — add a checking account or tell me your monthly income for a "
                     "complete picture")
    if s["card_credit_total"] >= 200:
        notes.append(f"{_money(s['card_credit_total'])} in card statement credits are "
                     f"offsetting your spending")
    for amt, desc in s.get("big_refunds", []):
        notes.append(f"a {_money(amt)} refund ({desc}) is included in money in — it may be "
                     f"for a purchase from an earlier month")
    if s["zelle_out_total"] >= 100:
        notes.append(f"{_money(s['zelle_out_total'])} in outgoing transfers is counted as "
                     f"money out — if any of that was moving money to your own savings, your "
                     f"real spending is lower")
    if s["n_months"] < 2:
        notes.append("this is based on a single month of data")
    if not notes:
        return f"*Based on your uploaded statements for {s['month']}."
    return "*Approximate — " + "; ".join(notes) + "."


def _summary_text(s):
    """Render the summary as compact text context for the model."""
    if not s:
        return "The user has no transactions yet."
    L = []
    L.append(f"Month summarized: {s['month']}")
    if s["accounts"]:
        L.append(f"Accounts: {', '.join(a for a in s['accounts'] if a)}")
    L.append("--- Net Cash Flow (agreed formula) ---")
    L.append(f"Money In: {_money(s['money_in'])}  "
             f"(income {_money(s['income_total'])}"
             + (f" + refunds {_money(s['refunds_total'])}" if s['refunds_total'] else "")
             + (f" + transfers-in {_money(s['zelle_in_total'])}" if s['zelle_in_total'] else "")
             + ")")
    L.append(f"Money Out: {_money(s['money_out'])}  "
             f"(spending {_money(s['net_expenses'])}"
             + (f", after {_money(s['card_credit_total'])} card credits" if s['card_credit_total'] else "")
             + (f" + cash {_money(s['cash_total'])}" if s['cash_total'] else "")
             + (f" + transfers-out {_money(s['zelle_out_total'])}" if s['zelle_out_total'] else "")
             + ")")
    sign = "positive/saved" if s["net"] >= 0 else "negative/overspent"
    L.append(f"Net Cash Flow: {_money(s['net'])} ({sign})")
    L.append("(Internal credit card payments are excluded to avoid double-counting.)")
    if s["top_cats"]:
        L.append("Spending by category (high to low):")
        for cat, amt in s["top_cats"]:
            pct = (amt / s["gross_expenses"] * 100) if s["gross_expenses"] else 0
            L.append(f"  - {cat}: {_money(amt)} ({pct:.0f}%)")
    if s["top_expenses"]:
        L.append("Biggest individual purchases:")
        for amt, desc, cat in s["top_expenses"]:
            L.append(f"  - {_money(amt)} - {desc} [{cat}]")
    if s["n_months"] > 1:
        L.append(f"(Data spans {s['n_months']} months: {', '.join(s['all_months'])}.)")
    return "\n".join(L)


_SYSTEM_PROMPT = (
    "You are xspend's friendly money assistant. You help everyday people understand "
    "their spending. Rules:\n"
    "- Explain like you're talking to a smart friend who is NOT into finance.\n"
    "- Plain language, no jargon. Someone should grasp your answer in about 5 seconds.\n"
    "- Always use specific dollar amounts and category names from the data provided.\n"
    "- Be warm and encouraging, never preachy or judgmental about their spending.\n"
    "- Keep it short: 2-4 sentences for most questions. Use a tiny list only if it "
    "genuinely helps.\n"
    "- Only state numbers that appear in the provided summary. If something isn't in "
    "the data, say you don't have that info yet rather than guessing.\n"
    "- For 'summarize my month', give a quick headline (spent X, mostly on Y) then one "
    "useful observation."
)


def get_ai_response(message, tx_list=None):
    """Answer a user question grounded in their transactions.

    message: the user's question (str)
    tx_list: list of transaction dicts (date, description, amount, currency,
             category, transaction_type, bank_source)
    Returns: assistant response text (str). Raises on hard errors so the caller
             can surface a message.
    """
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        return ("AI chat isn't configured yet — the server is missing its "
                "ANTHROPIC_API_KEY. Add it to the backend .env to enable chat.")

    summary = _build_summary(tx_list or [])
    context = _summary_text(summary)

    user_content = (
        f"Here is a summary of my spending data:\n\n{context}\n\n"
        f"My question: {message}"
    )

    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    resp = client.messages.create(
        model=_MODEL,
        max_tokens=400,
        system=_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    # Concatenate any text blocks in the response.
    parts = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            parts.append(block.text)
        elif isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(p for p in parts if p).strip() or "I couldn't generate a response."


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: curated, TEMPLATED prompt handlers (no LLM — free, instant, exact).
# Each returns a dict: {"answer": str, "disclaimer": str, ["needs_input": {...}]}
# ─────────────────────────────────────────────────────────────────────────────

# Categories considered discretionary (trimmable) for the affordability prompt.
_DISCRETIONARY = {
    "Food & Dining", "Shopping", "Entertainment", "Personal Care",
    "Alcohol & Liquor", "Travel", "Gifts & Donations", "Subscriptions",
}


# Frequency-adjustable categories: enough small transactions that "go a few
# fewer times" is a real, painless option. Travel/Gifts are lumpy & occasion-led.
_TRIMMABLE = {
    "Food & Dining", "Shopping", "Subscriptions",
    "Entertainment", "Alcohol & Liquor", "Personal Care",
}

_ACTIONS = {
    "Food & Dining": ("dined out", "meals out"),
    "Shopping": ("shopped", "purchases"),
    "Subscriptions": ("paid for subscriptions", "subscriptions"),
    "Entertainment": ("spent on entertainment", "outings"),
    "Alcohol & Liquor": ("bought drinks", "rounds"),
    "Personal Care": ("spent on personal care", "visits"),
}


# Fixed obligations: not "spending pace", and the place real price rises matter.
_FIXED_CATS = {
    "Rent/Mortgage", "Loan Payment", "Insurance", "Bills & Utilities",
    "Credit Card Payment", "Education", "Government & Taxes",
}

_MONTH_NAMES = {
    "01": "January", "02": "February", "03": "March", "04": "April",
    "05": "May", "06": "June", "07": "July", "08": "August",
    "09": "September", "10": "October", "11": "November", "12": "December",
}


def _pretty_month(ym):
    if not ym or len(ym) < 7:
        return ym or "this period"
    y, m = ym[:4], ym[5:7]
    return f"{_MONTH_NAMES.get(m, m)} {y}"


def prompt_net_cash_flow(tx_list, month=None):
    s = _build_summary(tx_list or [], month=month)
    if not s:
        return {"answer": "You don't have any transactions uploaded yet — add a "
                          "statement and I can break down your cash flow.",
                "disclaimer": ""}
    mth = _pretty_month(s["month"])
    net = s["net"]
    if net >= 0:
        headline = f"In {mth} you came out ahead by {_money(net)}."
    else:
        headline = f"In {mth} you spent {_money(abs(net))} more than came in."

    ins = []
    if s["income_total"]:
        ins.append(f"\u2022 Income \u2014 {_money(s['income_total'])}")
    if s["refunds_total"]:
        ins.append(f"\u2022 Refunds \u2014 {_money(s['refunds_total'])}")
    if s["zelle_in_total"]:
        ins.append(f"\u2022 Transfers in \u2014 {_money(s['zelle_in_total'])}")

    outs = []
    if s["net_expenses"]:
        if s["card_credit_total"]:
            outs.append(f"\u2022 Spending \u2014 {_money(s['net_expenses'])} "
                        f"(after {_money(s['card_credit_total'])} in card credits)")
        else:
            outs.append(f"\u2022 Spending \u2014 {_money(s['net_expenses'])}")
    if s["cash_total"]:
        outs.append(f"\u2022 Cash withdrawn \u2014 {_money(s['cash_total'])}")
    if s["zelle_out_total"]:
        outs.append(f"\u2022 Transfers out \u2014 {_money(s['zelle_out_total'])}")

    body = (f"\n\nMoney in \u2014 {_money(s['money_in'])}\n" + "\n".join(ins) +
            f"\n\nMoney out \u2014 {_money(s['money_out'])}\n" + "\n".join(outs))
    body += "\n\nCredit card payments are left out so spending isn't counted twice."

    return {"answer": headline + body, "disclaimer": build_disclaimer(s)}


def _month_gap_note(month_list):
    """Given ['2026-06','2026-02','2026-01'] return a gap disclaimer or ''."""
    yms = sorted(set(month_list))
    if len(yms) < 2:
        return ""
    def _idx(ym):
        y, m = int(ym[:4]), int(ym[5:7])
        return y * 12 + (m - 1)
    gaps = []
    for a, b in zip(yms, yms[1:]):
        if _idx(b) - _idx(a) > 1:
            missing_start = _idx(a) + 1
            missing_end = _idx(b) - 1
            names = []
            for i in range(missing_start, missing_end + 1):
                yy, mm = divmod(i, 12)
                names.append(_MONTH_NAMES.get(f"{mm+1:02d}", str(mm+1)) + f" {yy}")
            gaps.append((_pretty_month(a), _pretty_month(b), names))
    if not gaps:
        return ""
    a, b, names = gaps[0]
    span = names[0] if len(names) == 1 else f"{names[0]}–{names[-1]}"
    return (f" Heads up: your history jumps from {a} to {b}, so the months in between "
            f"({span}) are missing — uploading those will make this noticeably more accurate.")


def prompt_purchase_affordability(tx_list, amount, month=None):
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return {"answer": "How much are you thinking of spending? Tell me the amount "
                          "and I'll show you an easy way to make room for it.",
                "disclaimer": "", "needs_input": {"field": "amount", "label": "Purchase amount ($)"}}

    s = _build_summary(tx_list or [], month=month)
    if not s:
        return {"answer": "Upload a statement first and I'll show you where you'd have "
                          "room to make space for this.", "disclaimer": ""}

    mth = _pretty_month(s["month"])
    target_month = s["month"]

    from collections import defaultdict
    per_month_cat = defaultdict(lambda: defaultdict(float))
    cur_amounts = defaultdict(list)
    for t in tx_list:
        if (t.get("transaction_type") or "expense").lower() != "expense":
            continue
        cat = t.get("category") or "Other"
        if cat not in _TRIMMABLE:
            continue
        ym = _month_of(t)
        if not ym:
            continue
        a = abs(float(t.get("amount") or 0))
        per_month_cat[ym][cat] += a
        if ym == target_month:
            cur_amounts[cat].append(a)

    data_months = months_with_data(tx_list or [])
    all_ms = [ym for ym, _ in data_months]
    prior = [ym for ym in all_ms if ym != target_month]

    gap = _month_gap_note(all_ms)
    thin = (" *Insight based on %d month(s) of data \u2014 upload more history for a "
            "stronger baseline." % len(all_ms)) if len(all_ms) < 3 else ""

    if not cur_amounts:
        return {"answer": (f"Most of your {mth} spending looks like essentials, so there isn't "
                           f"much that's easy to trim. Making room for {_money(amount)} might mean "
                           f"dipping into savings."),
                "disclaimer": (gap + thin).strip()}

    # ── MULTI-MONTH: trend-aware ──
    if prior:
        rose, fell = [], []
        for cat, cur_v in ((c, sum(v)) for c, v in cur_amounts.items()):
            prior_vals = [per_month_cat[ym].get(cat, 0.0) for ym in prior]
            prior_vals = [p for p in prior_vals if p > 0]
            if not prior_vals:
                continue                      # new category — not a trim target
            low = min(prior_vals)             # you've actually lived on this
            avg = sum(prior_vals) / len(prior_vals)
            if cur_v > avg * 1.05:
                rose.append((cur_v - low, cat, cur_v, low))     # realistic room
            elif cur_v < avg * 0.95:
                fell.append((cat, cur_v, avg))
        rose.sort(reverse=True)

        picked, running = [], 0.0
        for room, cat, cur_v, low in rose:
            take = min(room, amount - running)
            picked.append((cat, take, cur_v, low))
            running += take
            if running >= amount or len(picked) >= 3:
                break

        if picked and running >= amount:
            bits = [f"{c} rose to {_money(cv)} from {_money(lo)} \u2014 easing back frees about {_money(tk)}"
                    for c, tk, cv, lo in picked]
            msg = (f"You've got room for {_money(amount)}. In {mth}, " + "; ".join(bits) +
                   ". You've comfortably spent that little before, so this isn't a stretch.")
        elif picked:
            bits = [f"{c} ({_money(tk)})" for c, tk, *_ in picked]
            msg = (f"Easing {', '.join(bits)} back to what you've spent before frees up about "
                   f"{_money(running)} in {mth} \u2014 that covers part of {_money(amount)}. For the "
                   f"rest, spreading it over a couple of months would keep things comfortable.")
        else:
            msg = (f"Your {mth} flexible spending is at or below your usual levels \u2014 nothing "
                   f"running hot. Making room for {_money(amount)} would mean going below what you "
                   f"normally spend, so savings might be the gentler route.")

        if fell:
            c, cv, av = fell[0]
            msg += f" Nice work on {c}, by the way \u2014 it's down to {_money(cv)} from around {_money(av)}. Keep that going."

        return {"answer": msg, "disclaimer": (gap + thin).strip()}

    # ── SINGLE MONTH: frequency-behavioral ──
    ranked = sorted(((c, sum(v), len(v), sum(v) / len(v)) for c, v in cur_amounts.items() if v),
                    key=lambda x: x[1], reverse=True)
    ranked = [r for r in ranked if r[2] >= 2]   # need at least 2 to "go a few fewer"

    if not ranked:
        return {"answer": (f"There isn't much frequent, flexible spending in {mth} to trim, so making "
                           f"room for {_money(amount)} might mean dipping into savings."),
                "disclaimer": (gap + thin).strip()}

    # Gentle: never suggest cutting more than about a third of any category's
    # occurrences. Spread across categories instead of gutting one.
    bits, running = [], 0.0
    for cat, total, count, avg in ranked[:3]:
        if running >= amount or avg <= 0:
            continue
        verb, noun = _ACTIONS.get(cat, (f"spent on {cat}", "times"))
        need = amount - running
        wanted = int(need // avg) + (1 if need % avg else 0)
        gentle_max = max(1, count // 3)          # at most ~1/3, always at least 1
        cut = max(1, min(wanted, gentle_max))
        saved = cut * avg
        running += saved
        bits.append(f"\u2022 {cat} \u2014 {cut} of your {count} "
                    f"({_money(avg)} each) \u2192 saves about {_money(saved)}")

    if not bits:
        msg = (f"There isn't much frequent, flexible spending in {mth} to trim gently, so making "
               f"room for {_money(amount)} might mean dipping into savings.")
    elif running >= amount:
        msg = (f"To free up {_money(amount)} in {mth} \u2014 no drastic changes needed. "
               f"Any mix of these gets you there:\n\n" + "\n".join(bits) +
               "\n\nSmall trims, and the essentials stay untouched.")
    else:
        msg = (f"Here's the comfortable room you have in {mth}:\n\n" + "\n".join(bits) +
               f"\n\nThat comes to about {_money(running)} of {_money(amount)}. For the rest, spreading "
               f"it over a couple of months would be gentler than cutting deeper.")

    return {"answer": msg, "disclaimer": (gap + thin).strip()}


def prompt_lifestyle_creep(tx_list):
    months = months_with_data(tx_list or [])
    if len(months) < 3:
        have = len(months)
        return {"answer": (f"This one needs at least 3 months of history to spot trends, "
                           f"and you have {have} so far. Upload a couple more statements and "
                           f"check back — I'll compare your recent spending to your norm."),
                "disclaimer": ""}

    # Build per-category spend for each month, compare latest vs average of the rest.
    # DISCRETIONARY ONLY — lifestyle creep is about flexible spending drifting up,
    # not fixed costs (rent/loans/insurance) or the junk "Other" bucket.
    from collections import defaultdict
    per_month_cat = defaultdict(lambda: defaultdict(float))
    for t in tx_list:
        ttype = (t.get("transaction_type") or "expense").lower()
        if ttype != "expense":
            continue
        cat = t.get("category") or "Other"
        if cat not in _DISCRETIONARY:
            continue
        ym = _month_of(t)
        if not ym:
            continue
        per_month_cat[ym][cat] += abs(float(t.get("amount") or 0))

    ordered = [ym for ym, _ in months]  # newest first
    latest_ym = ordered[0]
    prior_yms = ordered[1:]

    latest_cat = per_month_cat[latest_ym]
    # average across prior months
    avg_cat = defaultdict(float)
    for ym in prior_yms:
        for c, v in per_month_cat[ym].items():
            avg_cat[c] += v
    for c in avg_cat:
        avg_cat[c] /= len(prior_yms)

    # find biggest upward movers (latest vs average), discretionary first
    movers = []
    for c, latest_v in latest_cat.items():
        avg_v = avg_cat.get(c, 0.0)
        delta = latest_v - avg_v
        if delta > 0 and latest_v >= 30:  # ignore tiny/noise
            movers.append((delta, c, latest_v, avg_v))
    movers.sort(reverse=True)

    if not movers:
        return {"answer": (f"Good news — your spending in {_pretty_month(latest_ym)} is in "
                           f"line with your usual pattern. No categories crept up meaningfully."),
                "disclaimer": f"*Compared {_pretty_month(latest_ym)} against your average of "
                              f"{len(prior_yms)} earlier month(s)."}

    top3 = movers[:3]
    parts = []
    for delta, c, latest_v, avg_v in top3:
        pct = (delta / avg_v * 100) if avg_v > 0 else 100
        if avg_v > 0:
            parts.append(f"{c} is up {_money(delta)} ({pct:.0f}% over your {_money(avg_v)} average)")
        else:
            parts.append(f"{c} is new this month at {_money(latest_v)}")
    answer = (f"In {_pretty_month(latest_ym)}, the spots where spending crept up most: "
              + "; ".join(parts) + ".")
    return {"answer": answer,
            "disclaimer": f"*Compared {_pretty_month(latest_ym)} against your average of "
                          f"{len(prior_yms)} earlier month(s)."}


def prompt_dispatch(prompt_id, tx_list, month=None, amount=None):
    """Single entry point the API route calls."""
    if prompt_id == "net_cash_flow":
        return prompt_net_cash_flow(tx_list, month=month)
    if prompt_id == "purchase_affordability":
        return prompt_purchase_affordability(tx_list, amount, month=month)
    if prompt_id == "lifestyle_creep":
        return prompt_lifestyle_creep(tx_list)
    if prompt_id == "subscription_scan":
        return prompt_subscription_scan(tx_list)
    if prompt_id == "spending_velocity":
        return prompt_spending_velocity(tx_list, month=month)
    return {"answer": "Unknown prompt.", "disclaimer": ""}


# ─────────────────────────────────────────────────────────────────────────────
# Prompts 4 & 5 — retrospective only (no projections).
# ─────────────────────────────────────────────────────────────────────────────

def _norm_merchant(desc):
    """Cheap merchant key: strip processor prefixes, digits, punctuation."""
    import re
    d = (desc or "").lower()
    d = re.sub(r'^(?:sq|tst|toast|dd|dsh|paypal|pp|sp|wpy|gum|fs|ven(?:mo)?)\s*\*+\s*', '', d)
    d = re.sub(r'[^a-z ]+', ' ', d)
    d = re.sub(r'\s+', ' ', d).strip()
    return " ".join(d.split()[:3])


def prompt_subscription_scan(tx_list):
    """Recurring charges, price increases, and possible duplicate charges."""
    from collections import defaultdict
    txs = [t for t in (tx_list or [])
           if (t.get("transaction_type") or "expense").lower() == "expense"]
    if not txs:
        return {"answer": "Upload a statement and I'll scan for subscriptions, price rises "
                          "and duplicate charges.", "disclaimer": ""}

    months = sorted({_month_of(t) for t in txs if _month_of(t)})
    by_merch = defaultdict(list)   # key -> [(ym, date, amount, desc)]
    cat_by_merch = {}
    for t in txs:
        key = _norm_merchant(t.get("description"))
        if not key:
            continue
        cat_by_merch.setdefault(key, t.get("category") or "Other")
        by_merch[key].append((_month_of(t),
                              (t.get("date") or t.get("transaction_date") or ""),
                              abs(float(t.get("amount") or 0)),
                              t.get("description") or ""))

    # A real subscription = same merchant, ONE charge per month, near-identical
    # amount each time. Everything else (groceries, gas, restaurants) is just a
    # place you shop, and its amount naturally varies — never flag those.
    def _cat_of(rows_key):
        return cat_by_merch.get(rows_key, "Other")

    recurring, price_ups, dupes = [], [], []
    for key, rows in by_merch.items():
        ms = sorted({r[0] for r in rows})
        cat = _cat_of(key)

        if len(ms) >= 2 and len(months) >= 2:
            amts_by_m = defaultdict(list)
            for _ym, _d, a, _desc in rows:
                amts_by_m[_ym].append(a)
            # one charge per month, and amounts stable => subscription-like
            one_per_month = all(len(v) == 1 for v in amts_by_m.values())
            month_amts = [v[0] for v in amts_by_m.values()] if one_per_month else []
            stable = False
            if month_amts:
                lo, hi = min(month_amts), max(month_amts)
                stable = lo > 0 and (hi - lo) / lo <= 0.08     # within 8%

            is_sub = (cat in ("Subscriptions", "Insurance", "Bills & Utilities")) or (one_per_month and stable)
            if is_sub:
                latest_ym = ms[-1]
                latest = amts_by_m[latest_ym][0]
                earlier = [amts_by_m[m][0] for m in ms[:-1]]
                base = sum(earlier) / len(earlier) if earlier else latest
                if cat not in ("Rent/Mortgage", "Loan Payment"):
                    recurring.append((latest, rows[0][3][:28], len(ms)))
                # a real price rise: >5% and >= $1 on something that IS recurring
                if base > 0 and latest > base * 1.05 and latest - base >= 1:
                    price_ups.append((latest - base, rows[0][3][:28], base, latest))

        # possible duplicates: identical amount, same day, same merchant
        seen = defaultdict(int)
        for _ym, d, a, _desc in rows:
            seen[(d, round(a, 2))] += 1
        for (d, a), n in seen.items():
            if n > 1 and a >= 5:
                dupes.append((a, rows[0][3][:28], d, n))

    recurring.sort(reverse=True)
    price_ups.sort(reverse=True)
    dupes.sort(reverse=True)

    parts = []
    if price_ups:
        lines = [f"\u2022 {name} \u2014 {_money(old)} \u2192 {_money(new)} (+{_money(delta)})"
                 for delta, name, old, new in price_ups[:4]]
        parts.append("Recurring charges that went up:\n" + "\n".join(lines))
    if dupes:
        lines = [f"\u2022 {name} \u2014 {n}\u00d7 {_money(a)} on {d}" for a, name, d, n in dupes[:3]]
        parts.append("Possible duplicate charges (worth a look):\n" + "\n".join(lines))
    if recurring:
        lines = [f"\u2022 {name} \u2014 {_money(a)} a month" for a, name, n in recurring[:6]]
        parts.append("Subscriptions and recurring bills:\n" + "\n".join(lines))

    if not parts:
        answer = ("Nothing stood out \u2014 no duplicate charges, and none of your recurring "
                  "charges have gone up. Nice and steady.")
    else:
        answer = "Here's what the scan turned up.\n\n" + "\n\n".join(parts)

    disc = ""
    if len(months) < 2:
        disc = ("*With one month of data I can only catch same-day duplicates. Upload another "
                "month and I can spot recurring subscriptions and price increases too.")
    else:
        disc = _month_gap_note(months).strip() or f"*Based on {len(months)} months of statements."
    return {"answer": answer, "disclaimer": disc}


def prompt_spending_velocity(tx_list, month=None):
    """Daily average, heaviest day, and first-half vs second-half of the month."""
    s = _build_summary(tx_list or [], month=month)
    if not s:
        return {"answer": "Upload a statement and I'll show you how your spending paces "
                          "through the month.", "disclaimer": ""}
    ym = s["month"]
    mth = _pretty_month(ym)

    from collections import defaultdict
    by_day = defaultdict(float)
    for t in tx_list:
        if _month_of(t) != ym:
            continue
        if (t.get("transaction_type") or "expense").lower() != "expense":
            continue
        # Discretionary only — a mortgage isn't "spending pace".
        if (t.get("category") or "Other") in _FIXED_CATS:
            continue
        d = (t.get("date") or t.get("transaction_date") or "")
        if len(d) < 10:
            continue
        by_day[d] += abs(float(t.get("amount") or 0))

    if not by_day:
        return {"answer": f"No spending recorded in {mth} to pace out.", "disclaimer": ""}

    days = sorted(by_day)
    total = sum(by_day.values())
    n_days = len(days)
    daily_avg = total / n_days
    peak_day, peak_amt = max(by_day.items(), key=lambda kv: kv[1])

    first_half = sum(v for d, v in by_day.items() if int(d[8:10]) <= 15)
    second_half = total - first_half

    peak_dom = int(peak_day[8:10])
    suffix = "th" if 11 <= peak_dom % 100 <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(peak_dom % 10, "th")

    if second_half > first_half * 1.15:
        shape = (f"It picked up later in the month \u2014 {_money(first_half)} in the first half, "
                 f"{_money(second_half)} in the second.")
    elif first_half > second_half * 1.15:
        shape = (f"You front-loaded the month \u2014 {_money(first_half)} in the first half, "
                 f"{_money(second_half)} in the second.")
    else:
        shape = (f"It stayed fairly even \u2014 {_money(first_half)} in the first half, "
                 f"{_money(second_half)} in the second.")

    answer = (f"In {mth} your day-to-day spending came to {_money(total)} across {n_days} days "
              f"\u2014 about {_money(daily_avg)} a day. Your heaviest was the {peak_dom}{suffix} "
              f"at {_money(peak_amt)}. {shape}")

    disc = "*Rent, loans, insurance and bills are left out — this is your flexible spending only."
    return {"answer": answer, "disclaimer": disc}

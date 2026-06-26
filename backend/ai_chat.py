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


def _build_summary(tx_list):
    """Compute a compact summary dict from the raw transaction list."""
    if not tx_list:
        return None

    # Identify the latest month present, summarize that month (most relevant).
    months = sorted({(t.get("date") or "")[:7] for t in tx_list if t.get("date")})
    latest = months[-1] if months else None
    month_txs = [t for t in tx_list if (t.get("date") or "").startswith(latest)] if latest else tx_list

    spend_by_cat = defaultdict(float)
    total_spent = 0.0
    income_total = 0.0
    refunds_total = 0.0
    expenses = []  # (amount_abs, description, category)

    for t in month_txs:
        ttype = (t.get("transaction_type") or "expense").lower()
        amt = t.get("amount") or 0
        if ttype == "income" and amt > 0:
            income_total += amt
            continue
        if ttype == "refund":
            refunds_total += abs(amt)
            continue
        if ttype in _EXCLUDED_TYPES:
            continue
        # Spending (expense). amount is negative for spend.
        a = abs(amt)
        total_spent += a
        cat = t.get("category") or "Other"
        spend_by_cat[cat] += a
        expenses.append((a, t.get("description") or "Unknown", cat))

    top_cats = sorted(spend_by_cat.items(), key=lambda kv: kv[1], reverse=True)
    top_expenses = sorted(expenses, key=lambda e: e[0], reverse=True)[:5]

    # Account count and accounts present (context)
    accounts = sorted({t.get("bank_source") for t in month_txs if t.get("bank_source")})

    return {
        "month": latest,
        "total_spent": total_spent,
        "income_total": income_total,
        "refunds_total": refunds_total,
        "net": income_total - total_spent,
        "top_cats": top_cats,
        "top_expenses": top_expenses,
        "accounts": accounts,
        "n_months": len(months),
        "all_months": months,
    }


def _summary_text(s):
    """Render the summary dict as compact text context for the model."""
    if not s:
        return "The user has no transactions yet."

    lines = []
    lines.append(f"Month summarized: {s['month']}")
    if s["accounts"]:
        lines.append(f"Accounts: {', '.join(s['accounts'])}")
    lines.append(f"Total spent this month: {_money(s['total_spent'])}")
    if s["income_total"]:
        lines.append(f"Income this month: {_money(s['income_total'])}")
        lines.append(f"Net (income minus spending): {_money(s['net'])}"
                     + (" (saved)" if s["net"] >= 0 else " (overspent)"))
    if s["refunds_total"]:
        lines.append(f"Refunds received: {_money(s['refunds_total'])}")

    if s["top_cats"]:
        lines.append("Spending by category (high to low):")
        for cat, amt in s["top_cats"]:
            pct = (amt / s["total_spent"] * 100) if s["total_spent"] else 0
            lines.append(f"  - {cat}: {_money(amt)} ({pct:.0f}%)")

    if s["top_expenses"]:
        lines.append("Biggest individual purchases:")
        for amt, desc, cat in s["top_expenses"]:
            lines.append(f"  - {_money(amt)} — {desc} [{cat}]")

    if s["n_months"] > 1:
        lines.append(f"(Data spans {s['n_months']} months: {', '.join(s['all_months'])}.)")

    return "\n".join(lines)


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

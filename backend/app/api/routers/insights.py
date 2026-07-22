from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.core.deps import get_current_user

router = APIRouter()


# ── Credit Nullification ──
@router.get("/insights")
def get_insights(month: str = None, months: str = None, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    from app.services.insights import generate_insights
    import sqlalchemy as _sa

    rows = db.execute(_sa.text("""
        SELECT id, description, category, amount, transaction_type,
               transaction_date, is_fixed, bank_source
        FROM transactions
        WHERE transaction_type IN ('expense', 'income', 'transfer', 'credit_card_payment')
        AND is_pending = false
        AND user_id = :u
        ORDER BY transaction_date
    """), {'u': current_user}).fetchall()

    txs = []
    for r in rows:
        d = dict(r._mapping)
        # Postgres returns DATE columns as date objects; insights.py does string
        # ops ([:7], .split, .startswith) on transaction_date, so stringify it.
        if d.get('transaction_date') is not None:
            d['transaction_date'] = str(d['transaction_date'])
        txs.append(d)

    # Scope to the selected period (CSV of YYYY-MM). If 'months' is given, keep
    # only transactions whose month is in the selection. Empty/None -> all.
    if months:
        _wanted = {m.strip() for m in months.split(',') if m.strip()}
        if _wanted:
            txs = [t for t in txs
                   if (t.get('transaction_date') or '')[:7] in _wanted]

    profile_row = db.execute(_sa.text(
        "SELECT monthly_budget FROM users WHERE id = :u"
    ), {'u': current_user}).fetchone()
    budget = float(profile_row[0] or 0) if profile_row else 0

    if month:
        bh_row = db.execute(_sa.text(
            "SELECT amount FROM budget_history WHERE month = :m AND user_id = :u"
        ), {'m': month, 'u': current_user}).fetchone()
        if bh_row:
            budget = float(bh_row[0])

    insights = generate_insights(txs, budget, month)
    return insights

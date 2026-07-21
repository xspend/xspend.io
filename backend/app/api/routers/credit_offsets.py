from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.auth import get_current_user

router = APIRouter()


# ── Credit Offset Calculation ──
def get_credit_offsets_map(db, current_user):
    # NOTE: deferred/unused. Must be passed current_user before any live wiring.
    import sqlalchemy as _sa
    import re as _re
    credits = db.execute(_sa.text(
        "SELECT description, amount FROM transactions WHERE transaction_type = 'card_credit' AND user_id = :uid"
    ), {"uid": current_user}).fetchall()
    credit_map = {}
    for c in credits:
        desc = c[0] or ''
        match = _re.search(r'-\s*(.+)', desc)
        if match:
            key = match.group(1).strip()[:10].lower()
            credit_map[key] = credit_map.get(key, 0) + c[1]
    return credit_map

# ── Summary ──
# REMOVED: the old GET /summary endpoint queried all users' transactions with no
# user scoping (isolation leak) and the frontend never called it (replaced by
# /dashboard-summary). Deleted rather than scoped, since it was dead.
#
# DEFERRED (product decision, must be user-scoped before going live in the UI):
# the credit-offsets MATCHING engine — run_credit_matching / get_net_category_spend
# (credit_engine.py) and get_credit_offsets_map / GET /credit-offsets (main.py).
# These net specific credits against specific expenses per category. Not on the
# beta path. If wired into the live UI later, scope every query by user_id first.

# ── Credit Offsets API ──
@router.get("/credit-offsets/{period}")
def get_credit_offsets_period(period: str, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    from app.services.credit_engine import get_net_category_spend

    offsets = db.execute(_sa.text('''
        SELECT co.id, co.credit_type, co.eligible_for_matching,
               co.applied_amount, co.unapplied_amount,
               co.match_confidence, co.match_method,
               co.matched_category, t.description, t.amount
        FROM credit_offsets co
        JOIN transactions t ON t.id = co.credit_transaction_id
        WHERE co.statement_period = :period
        AND co.is_active = 1
        AND t.user_id = :u
        ORDER BY co.applied_amount DESC
    '''), {'period': period, 'u': current_user}).fetchall()

    net_spend = get_net_category_spend(db, period, user_id=current_user)

    return {
        'period': period,
        'offsets': [{
            'id': r[0],
            'credit_type': r[1],
            'eligible': bool(r[2]),
            'applied_amount': r[3],
            'unapplied_amount': r[4],
            'confidence': r[5],
            'method': r[6],
            'matched_category': r[7],
            'credit_description': r[8],
            'credit_amount': r[9],
        } for r in offsets],
        'net_category_spend': net_spend,
        'total_applied': round(sum(r[3] for r in offsets if r[2]), 2),
        'total_unapplied': round(sum(r[4] or 0 for r in offsets), 2),
    }

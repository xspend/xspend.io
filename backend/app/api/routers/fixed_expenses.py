from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from sqlalchemy import extract as _extract

from app.db import get_db
from app.core.deps import get_current_user
from app.models import Transaction
from app.api.common import tx_to_dict

router = APIRouter()


# ── Fixed expenses summary ──
@router.get("/fixed-summary")
def get_fixed_expenses_summary(months: Optional[str] = None, account: Optional[str] = None, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    import re as _re
    from app.services.fixed_classifier import get_fixed_summary, get_subscription_summary

    # Scope to the selected month-set (CSV "YYYY-MM,...") and account.
    # A transaction matches if its YYYY-MM is in the set OR it has no date
    # (guard so dateless fixed items don't vanish). Empty months = all.
    _month_set = [m for m in (months or '').split(',') if _re.match(r'^\d{4}-\d{2}$', m.strip())]

    def _period_filter():
        if not _month_set:
            return None
        _ors = []
        for _m in _month_set:
            _yr, _mo = int(_m[:4]), int(_m[5:7])
            _ors.append(_sa.and_(
                _extract('year', Transaction.transaction_date) == _yr,
                _extract('month', Transaction.transaction_date) == _mo,
            ))
        return _sa.or_(_sa.or_(*_ors), Transaction.transaction_date.is_(None))
    _mfilter = _period_filter()
    _use_account = account and account != 'all'

    _q1 = db.query(Transaction).filter(
        Transaction.user_id == current_user,
        Transaction.transaction_type == 'expense',
        Transaction.amount < 0,
        Transaction.exclusion_reason == None
    )
    if _mfilter is not None:
        _q1 = _q1.filter(_mfilter)
    if _use_account:
        _q1 = _q1.filter(Transaction.bank_source == account)
    txs = [tx_to_dict(t) for t in _q1.all()]

    # Also include credit-covered transactions so they show as "fully covered"
    _q2 = db.query(Transaction).filter(
        Transaction.user_id == current_user,
        Transaction.exclusion_reason == 'credit_covered',
        Transaction.is_fixed == True
    )
    if _mfilter is not None:
        _q2 = _q2.filter(_mfilter)
    if _use_account:
        _q2 = _q2.filter(Transaction.bank_source == account)
    covered_txs = [tx_to_dict(t) for t in _q2.all()]

    all_fixed_txs = txs + covered_txs
    fixed = get_fixed_summary([t for t in all_fixed_txs if t.get('is_fixed')])
    subs = get_subscription_summary(all_fixed_txs)

    # Get card credits to compute coverage
    credits = db.execute(_sa.text(
        "SELECT description, amount FROM transactions WHERE transaction_type = 'card_credit' AND user_id = :uid"
    ), {"uid": current_user}).fetchall()

    # Build credit map: merchant_key -> credit_amount
    credit_map = {}
    for c in credits:
        desc = c[0] or ''
        match = _re.search(r'-\s*(.+)', desc)
        if match:
            key = match.group(1).strip()[:10].lower()
            credit_map[key] = credit_map.get(key, 0) + c[1]

    def find_credit(merchant):
        key = (merchant or '')[:10].lower()
        for ck, cv in credit_map.items():
            if ck[:6] in key or key[:6] in ck:
                return cv
        return 0

    # Annotate fixed items
    covered_total = 0
    for item in fixed.get('items', []):
        covered = min(find_credit(item.get('merchant','')), item['amount'])
        item['credit_covered'] = round(covered, 2)
        item['net_amount'] = round(item['amount'] - covered, 2)
        covered_total += covered

    # Annotate subscriptions
    for item in subs.get('items', []):
        covered = min(find_credit(item.get('name','')), item['amount'])
        item['credit_covered'] = round(covered, 2)
        item['net_amount'] = round(item['amount'] - covered, 2)

    # Manual fixed
    manual = db.execute(_sa.text(
        "SELECT name, amount FROM manual_fixed_expenses WHERE user_id = :u ORDER BY amount DESC"
    ), {'u': current_user}).fetchall()
    for m in manual:
        fixed['items'].append({
            'merchant': m[0], 'amount': m[1], 'varies': False,
            'occurrences': 1, 'manual': True,
            'credit_covered': 0, 'net_amount': m[1]
        })
        fixed['total'] = round(fixed['total'] + m[1], 2)

    return {
        'fixed': fixed,
        'subscriptions': subs,
        'credit_covered_total': round(covered_total, 2),
        'net_fixed_total': round(fixed['total'] - covered_total, 2)
    }

@router.patch("/transactions/{tid}/fixed")
def update_transaction_fixed(tid: int, data: dict, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    from app.services.fixed_classifier import normalize_merchant
    t = db.query(Transaction).filter(Transaction.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")
    if t.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")

    is_fixed = data.get('is_fixed', False)
    t.is_fixed = is_fixed
    t.fixed_confidence = 1.0
    t.fixed_source = 'user_confirmed'

    # Save merchant rule so future uploads remember this
    merchant_key = normalize_merchant(t.description or '')[:8]
    if merchant_key:
        existing = db.execute(
            __import__('sqlalchemy').text(
                "SELECT id FROM merchant_rules WHERE merchant_keyword = :k AND user_id = :u"
            ), {'k': merchant_key, 'u': current_user}
        ).fetchone()
        if existing:
            db.execute(
                __import__('sqlalchemy').text(
                    "UPDATE merchant_rules SET is_fixed=:f, user_confirmed=1 WHERE merchant_keyword=:k AND user_id=:u"
                ), {'f': int(is_fixed), 'k': merchant_key, 'u': current_user}
            )
        else:
            db.execute(
                __import__('sqlalchemy').text(
                    "INSERT INTO merchant_rules (merchant_keyword, is_fixed, user_confirmed, confidence, user_id) VALUES (:k, :f, 1, 1.0, :u)"
                ), {'k': merchant_key, 'f': int(is_fixed), 'u': current_user}
            )
    db.commit()
    return {'success': True}

# ── Manual Fixed Expenses ──
@router.get("/manual-fixed")
def get_manual_fixed(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    rows = db.execute(_sa.text(
        "SELECT id, name, amount, frequency FROM manual_fixed_expenses WHERE user_id = :u ORDER BY amount DESC"
    ), {'u': current_user}).fetchall()
    return [{"id": r[0], "name": r[1], "amount": r[2], "frequency": r[3]} for r in rows]

@router.post("/manual-fixed")
def add_manual_fixed(data: dict, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    db.execute(_sa.text(
        "INSERT INTO manual_fixed_expenses (name, amount, frequency, user_id) VALUES (:name, :amount, :frequency, :u)"
    ), {"name": data.get("name"), "amount": float(data.get("amount", 0)), "frequency": data.get("frequency", "monthly"), "u": current_user})
    db.commit()
    return {"success": True}

@router.delete("/manual-fixed/{item_id}")
def delete_manual_fixed(item_id: int, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import sqlalchemy as _sa
    db.execute(_sa.text("DELETE FROM manual_fixed_expenses WHERE id = :id AND user_id = :u"), {"id": item_id, "u": current_user})
    db.commit()
    return {"success": True}

# ── Merchant Rules ──
@router.post("/merchant-rules/dismiss")
def dismiss_merchant_rule(data: dict, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    from app.services.fixed_classifier import normalize_merchant
    import sqlalchemy as _sa
    merchant = data.get("merchant", "")
    key = normalize_merchant(merchant)[:8]
    if key:
        existing = db.execute(_sa.text(
            "SELECT id FROM merchant_rules WHERE merchant_keyword = :k AND user_id = :u"
        ), {'k': key, 'u': current_user}).fetchone()
        if existing:
            db.execute(_sa.text(
                "UPDATE merchant_rules SET is_fixed=0, user_confirmed=1 WHERE merchant_keyword=:k AND user_id=:u"
            ), {'k': key, 'u': current_user})
        else:
            db.execute(_sa.text(
                "INSERT INTO merchant_rules (merchant_keyword, is_fixed, user_confirmed, confidence, user_id) VALUES (:k, 0, 1, 1.0, :u)"
            ), {'k': key, 'u': current_user})
        db.commit()
    return {"success": True}

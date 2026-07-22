from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from datetime import datetime

from app.db import get_db
from app.core.deps import get_current_user
from app.models import Transaction
from app.api.common import tx_to_dict

router = APIRouter()


class ManualTransaction(BaseModel):
    transaction_date: str
    description: str
    amount: float
    currency: str = "USD"
    category: str = "Other"
    transaction_type: str = "expense"
    bank_source: str = "Manual Entry"
    notes: Optional[str] = None

class TransactionUpdate(BaseModel):
    transaction_date: Optional[str] = None
    description: Optional[str] = None
    amount: Optional[float] = None
    currency: Optional[str] = None
    category: Optional[str] = None
    transaction_type: Optional[str] = None
    bank_source: Optional[str] = None
    notes: Optional[str] = None
    needs_review: Optional[bool] = None
    exclusion_reason: Optional[str] = None
    review_status: Optional[str] = None


@router.get("/transactions")
def get_transactions(include_pending: bool = False, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import re as _re
    # Build credit map
    import sqlalchemy as _sa
    credits = db.execute(_sa.text(
        "SELECT description, amount FROM transactions WHERE transaction_type = 'card_credit' AND user_id = :uid"
    ), {"uid": current_user}).fetchall()
    credit_map = {}
    for c in credits:
        match = _re.search(r'-\s*(.+)', c[0] or '')
        if match:
            key = match.group(1).strip()[:10].lower()
            credit_map[key] = credit_map.get(key, 0) + c[1]

    q = db.query(Transaction).filter(Transaction.user_id == current_user)
    if not include_pending:
        q = q.filter(Transaction.is_pending == False)
    txs = q.order_by(Transaction.transaction_date.desc()).all()

    results = []
    for t in txs:
        d = tx_to_dict(t)
        if t.transaction_type == 'expense' and t.amount and t.amount < 0:
            merchant_key = (t.description or '')[:10].lower()
            credit_applied = 0
            for ck, cv in credit_map.items():
                if ck[:6] in merchant_key or merchant_key[:6] in ck:
                    credit_applied = min(cv, abs(t.amount))
                    break
            if credit_applied > 0:
                d['credit_applied'] = round(credit_applied, 2)
                d['net_amount'] = round(abs(t.amount) - credit_applied, 2)
        results.append(d)
    return results

@router.get("/transactions/review")
def get_review_queue(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    txs = db.query(Transaction).filter(
        Transaction.user_id == current_user,
        Transaction.needs_review == True,
        Transaction.is_pending == False,
    ).order_by(Transaction.transaction_date.desc()).all()
    return [tx_to_dict(t) for t in txs]

@router.post("/transactions/manual")
def add_manual(tx: ManualTransaction, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    from app.services.classifier import generate_fingerprint
    try:
        date = datetime.strptime(tx.transaction_date, "%Y-%m-%d").date()
    except:
        date = datetime.today().date()

    fp = generate_fingerprint("manual", str(date), tx.amount, tx.description)

    new_tx = Transaction(
        user_id=current_user,
        fingerprint=fp,
        transaction_date=date,
        description=tx.description,
        amount=tx.amount,
        currency=tx.currency,
        category=tx.category,
        transaction_type=tx.transaction_type,
        classification_confidence="high",
        needs_review=False,
        bank_source=tx.bank_source,
        import_source="manual",
        notes=tx.notes,
        is_edited=False,
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    return {"success": True, "transaction": tx_to_dict(new_tx)}

@router.patch("/transactions/{tid}")
def update_transaction(tid: int, update: TransactionUpdate, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    import re
    # Ownership guard: the transaction must belong to the current user.
    _own = db.query(Transaction).filter(Transaction.id == tid).first()
    if _own and _own.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    # If category changed → re-run fixed classifier
    if update.category is not None:
        from app.services.fixed_classifier import classify_transaction, normalize_merchant
        from app.services.classifier import normalize_description
        import sqlalchemy as _sa
        # Auto-set transaction_type based on category
        if update.category == 'Transfer':
            update.transaction_type = 'transfer'
        elif update.category in ('Credit Card Payment', 'Payment'):
            update.transaction_type = 'credit_card_payment'
            update.category = 'Credit Card Payment'
        t = db.query(Transaction).filter(Transaction.id == tid).first()
        if t and t.category != update.category:
            # Save user correction to merchant_rules.
            # Store a STABLE CORE so the rule generalizes across variants: strip the
            # leading payment-processor prefix (sp/sq/tst/...) and trailing short
            # region/legal tokens (us/usa/llc/inc/co), keeping the distinctive name.
            norm_desc = normalize_description(t.description or '')
            _core = re.sub(r'^(sp|sq|tst|toast|dd|dsh|pp|paypal|gum|wpy|clkbank)\s+', '', norm_desc or '')
            _core = re.sub(r'\b(us|usa|llc|inc|co|corp|ltd)\b', ' ', _core)
            _core = re.sub(r'\s+', ' ', _core).strip()
            norm_merchant = (_core or norm_desc)[:24].strip() if norm_desc else ''
            if norm_merchant:
                # Check if rule exists
                existing = db.execute(_sa.text(
                    "SELECT id FROM merchant_rules WHERE match_value = :mv AND user_id = :u"
                ), {'mv': norm_merchant, 'u': current_user}).fetchone()
                if existing:
                    db.execute(_sa.text(
                        "UPDATE merchant_rules SET category = :cat, match_type = 'contains', is_active = 1, updated_at = CURRENT_TIMESTAMP WHERE id = :id"
                    ), {'cat': update.category, 'id': existing[0]})
                else:
                    db.execute(_sa.text('''
                        INSERT INTO merchant_rules (merchant_keyword, match_value, match_type, match_field, category, transaction_type, priority, source, is_active, is_fixed, user_id, updated_at)
                        VALUES (:mv, :mv, 'contains', 'merchant', :cat, 'expense', 10, 'user_correction', 1, 0, :u, CURRENT_TIMESTAMP)
                    '''), {'mv': norm_merchant, 'cat': update.category, 'u': current_user})
                db.commit()
        if t:
            tx_dict = {
                'description': t.description or '',
                'category': update.category,
                'amount': t.amount,
                'transaction_type': t.transaction_type,
                'transaction_date': str(t.transaction_date) if t.transaction_date else None,
            }
            all_txs = db.execute(_sa.text(
                "SELECT id, description, category, amount, transaction_type, transaction_date FROM transactions WHERE transaction_type = 'expense' AND amount < 0 AND user_id = :u"
            ), {'u': current_user}).fetchall()
            # Postgres returns DATE as date objects; classifier does string ops
            # (date[:7], .split) so stringify transaction_date.
            all_txs_list = []
            for r in all_txs:
                d = dict(r._mapping)
                if d.get('transaction_date') is not None:
                    d['transaction_date'] = str(d['transaction_date'])
                all_txs_list.append(d)
            result = classify_transaction(tx_dict, all_txs_list)
            db.execute(_sa.text(
                "UPDATE transactions SET is_fixed=:f, fixed_confidence=:c, fixed_source=:s WHERE id=:id AND user_id=:u"
            ), {'f': bool(result['is_fixed']), 'c': result['confidence'], 's': 'user_override', 'id': tid, 'u': current_user})
            db.commit()
    tx = db.query(Transaction).filter(Transaction.id == tid).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    if update.transaction_date:
        try:
            tx.transaction_date = datetime.strptime(update.transaction_date, "%Y-%m-%d").date()
        except:
            pass
    if update.description is not None:
        tx.description = update.description
    if update.amount is not None:
        tx.amount = update.amount
    if update.currency is not None:
        tx.currency = update.currency
    if update.category is not None:
        tx.category = update.category
    if update.transaction_type is not None:
        tx.transaction_type = update.transaction_type
    if update.bank_source is not None:
        tx.bank_source = update.bank_source
    if update.notes is not None:
        tx.notes = update.notes
    if update.exclusion_reason is not None:
        tx.exclusion_reason = update.exclusion_reason
    # An edit marks the row reviewed. `review_status` in the request body is still
    # accepted for backward-compat but is now derived from needs_review, not stored.
    tx.is_edited = True
    tx.needs_review = False
    db.commit()
    return {"success": True, "transaction": tx_to_dict(tx)}

@router.delete("/transactions/{tid}")
def delete_transaction(tid: int, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    tx = db.query(Transaction).filter(Transaction.id == tid).first()
    if not tx:
        raise HTTPException(404, "Not found")
    if tx.user_id != current_user:
        raise HTTPException(status_code=403, detail="Not authorized")
    db.delete(tx)
    db.commit()
    return {"success": True}

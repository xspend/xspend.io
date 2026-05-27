from fastapi import FastAPI, UploadFile, File, Depends, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from database import engine, Base, get_db
from fixed_classifier import classify_all_transactions, normalize_merchant, display_merchant
from models import BudgetHistory
from models import (
    Transaction, TransactionRule, User, Account,
    UploadedFile as UploadedFileModel, Category, Goal,
    seed_default_categories, gen_uuid
)
from parser import parse_statement
# ai.py removed
def get_ai_response(prompt): return "AI unavailable"
from datetime import datetime
from pydantic import BaseModel
from typing import Optional, List
import traceback

Base.metadata.create_all(bind=engine)

app = FastAPI(title="FinanceAI API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Seed categories on startup
@app.on_event("startup")
def startup():
    db = next(get_db())
    seed_default_categories(db)
    db.close()

# ── Pydantic models ──

class ChatMessage(BaseModel):
    message: str

class ManualTransaction(BaseModel):
    transaction_date: str
    description: str
    amount: float
    currency: str = "USD"
    category: str = "Uncategorized"
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

class RuleCreate(BaseModel):
    match_field: str = "description"
    match_operator: str = "contains"
    match_value: str
    output_transaction_type: Optional[str] = None
    output_category: Optional[str] = None
    priority: int = 0

class ProfileUpdate(BaseModel):
    full_name: Optional[str] = None
    income_amount: Optional[float] = None
    income_frequency: Optional[str] = None
    currency_code: Optional[str] = None
    payday_day: Optional[str] = None
    selected_goals: Optional[str] = None
    other_goals: Optional[str] = None
    savings_goal_monthly: Optional[float] = None
    savings_goal_weekly: Optional[float] = None
    debt_payoff_goal: Optional[float] = None
    monthly_budget: Optional[float] = None
    # Legacy
    monthly_income: Optional[float] = None
    preferred_currency: Optional[str] = None
    monthly_savings_goal: Optional[float] = None
    weekly_savings_goal: Optional[float] = None

class AccountCreate(BaseModel):
    account_name: str
    account_type: str = "checking"
    institution_name: Optional[str] = None
    last4_masked: Optional[str] = None

# ── Helpers ──

def tx_to_dict(t: Transaction) -> dict:
    return {
        "id": t.id,
        "transaction_id": t.transaction_id,
        "transaction_date": str(t.transaction_date) if t.transaction_date else None,
        "date": str(t.transaction_date) if t.transaction_date else None,
        "description": t.description or t.description_clean,
        "original_description": t.original_description or t.description_raw,
        "amount": t.amount,
        "currency": t.currency or t.currency_code or "USD",
        "category": t.category,
        "category_id": t.category_id,
        "transaction_type": t.transaction_type,
        "classification_confidence": t.classification_confidence,
        "needs_review": t.needs_review,
        "review_status": t.review_status,
        "exclusion_reason": t.exclusion_reason,
        "is_pending": t.is_pending,
        "status": t.status,
        "bank_source": t.bank_source,
        "account_id": t.account_id,
        "project_id": t.project_id,
        "uploaded_file_id": t.uploaded_file_id,
        "import_source": t.import_source,
        "is_edited": t.is_user_edited or t.is_edited,
        "notes": t.notes,
        "fingerprint": t.fingerprint,
        "is_fixed": bool(t.is_fixed) if t.is_fixed is not None else False,
        "fixed_confidence": t.fixed_confidence or 0.0,
        "fixed_source": t.fixed_source or "auto",
    }

def get_or_create_profile(db: Session) -> User:
    p = db.query(User).first()
    if not p:
        p = User(user_id=gen_uuid(), full_name="User")
        db.add(p)
        db.commit()
        db.refresh(p)
    return p

# ── Routes ──

@app.get("/")
def root():
    return {"status": "FinanceAI API running"}

# ── Profile ──

@app.get("/profile")
def get_profile(db: Session = Depends(get_db)):
    p = db.query(User).first()
    if not p:
        return {"exists": False}
    return {
        "exists": True,
        "full_name": p.full_name,
        "income_amount": p.income_amount,
        "monthly_income": p.income_amount,
        "income_frequency": p.income_frequency,
        "currency_code": p.currency_code,
        "preferred_currency": p.currency_code,
        "payday_day": p.payday_day,
        "selected_goals": p.selected_goals,
        "other_goals": p.other_goals,
        "savings_goal_monthly": p.savings_goal_monthly,
        "monthly_savings_goal": p.savings_goal_monthly,
        "savings_goal_weekly": p.savings_goal_weekly,
        "debt_payoff_goal": p.debt_payoff_goal,
        "monthly_budget": p.monthly_budget,
    }

@app.post("/profile")
def save_profile(data: ProfileUpdate, db: Session = Depends(get_db)):
    # If budget is being updated, save to history for current month
    if data.monthly_budget is not None:
        from datetime import datetime
        current_month = datetime.now().strftime('%Y-%m')
        import sqlalchemy as _sa
        existing = db.execute(_sa.text(
            "SELECT id FROM budget_history WHERE month = :m"
        ), {'m': current_month}).fetchone()
        if existing:
            db.execute(_sa.text(
                "UPDATE budget_history SET amount = :a WHERE month = :m"
            ), {'a': data.monthly_budget, 'm': current_month})
        else:
            db.execute(_sa.text(
                "INSERT INTO budget_history (amount, month) VALUES (:a, :m)"
            ), {'a': data.monthly_budget, 'm': current_month})
        db.commit()
    p = get_or_create_profile(db)
    if data.full_name is not None: p.full_name = data.full_name
    if data.income_amount is not None: p.income_amount = data.income_amount
    if data.monthly_income is not None: p.income_amount = data.monthly_income
    if data.income_frequency is not None: p.income_frequency = data.income_frequency
    if data.currency_code is not None: p.currency_code = data.currency_code
    if data.preferred_currency is not None: p.currency_code = data.preferred_currency
    if data.payday_day is not None: p.payday_day = data.payday_day
    if data.selected_goals is not None: p.selected_goals = data.selected_goals
    if data.other_goals is not None: p.other_goals = data.other_goals
    if data.savings_goal_monthly is not None: p.savings_goal_monthly = data.savings_goal_monthly
    if data.monthly_savings_goal is not None: p.savings_goal_monthly = data.monthly_savings_goal
    if data.savings_goal_weekly is not None: p.savings_goal_weekly = data.savings_goal_weekly
    if data.weekly_savings_goal is not None: p.savings_goal_weekly = data.weekly_savings_goal
    if data.debt_payoff_goal is not None: p.debt_payoff_goal = data.debt_payoff_goal
    if data.monthly_budget is not None: p.monthly_budget = data.monthly_budget
    db.commit()
    return {"success": True}

# ── Accounts ──

@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):
    return db.query(Account).filter(Account.is_active == True).all()

@app.post("/accounts")
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    acct = Account(
        account_id=gen_uuid(),
        account_name=data.account_name,
        account_type=data.account_type,
        institution_name=data.institution_name,
        last4_masked=data.last4_masked,
    )
    db.add(acct)
    db.commit()
    db.refresh(acct)
    return acct

# ── Categories ──

@app.get("/categories")
def get_categories(db: Session = Depends(get_db)):
    cats = db.query(Category).filter(Category.is_active == True).order_by(Category.display_order).all()
    return [{"id": c.category_id, "name": c.category_name, "group": c.category_group, "is_default": c.is_system_default} for c in cats]

# ── Upload ──

@app.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank_name: str = "Unknown Bank",
    account_id: Optional[str] = None,
    db: Session = Depends(get_db)
):
    contents = await file.read()
    print(f"UPLOAD: {file.filename} size={len(contents)} bank={bank_name}")

    # Load user correction rules from merchant_rules table
    from parser import load_merchant_rules
    user_rules = load_merchant_rules(db)

    # Create upload record
    upload_rec = UploadedFileModel(
        uploaded_file_id=gen_uuid(),
        file_name=file.filename,
        file_type=file.filename.split(".")[-1].lower(),
        source_type="upload",
        bank_name=bank_name,
        upload_status="processing",
        account_id=account_id,
    )
    db.add(upload_rec)
    db.commit()

    try:
        transactions, detected_bank = parse_statement(file.filename, contents, bank_name, user_rules)
        print(f"PARSED: {len(transactions)} transactions bank={detected_bank}")
    except ValueError as e:
        upload_rec.upload_status = "failed"
        upload_rec.error_message = str(e)
        db.commit()
        return {"success": False, "error": str(e)}
    except Exception as e:
        upload_rec.upload_status = "failed"
        upload_rec.error_message = str(e)
        db.commit()
        print(f"PARSE ERROR: {traceback.format_exc()}")
        return {"success": False, "error": f"Parse error: {str(e)}"}

    # Get category map
    cat_map = {c.category_name: c.category_id for c in db.query(Category).all()}

    saved, skipped, pending_skipped, review_count = [], 0, 0, 0
    skipped_merchants = []
    max_id = db.query(Transaction).count()

    for t in transactions:
        if t.get("is_pending"):
            pending_skipped += 1
            continue

        # FITID deduplication for OFX files — check external_transaction_id first
        fitid = t.get("external_transaction_id", "").strip()
        if fitid and len(fitid) > 5:
            fitid_existing = db.query(Transaction).filter(
                Transaction.external_transaction_id == fitid
            ).first()
            if fitid_existing:
                skipped += 1
                skipped_merchants.append(t.get('description','')[:20])
                continue

        fp = t.get("fingerprint")
        if fp:
            existing = db.query(Transaction).filter(Transaction.fingerprint == fp).first()
            if existing:
                skipped += 1
                skipped_merchants.append(t.get('description','')[:20])
                continue

        # Fuzzy duplicate detection — same merchant + amount within ±3 days
        tx_date = t.get("transaction_date")
        if tx_date and t.get("amount") and t.get("description"):
            from datetime import timedelta, date as date_cls
            try:
                tx_date_obj = date_cls.fromisoformat(str(tx_date))
                date_min = tx_date_obj - timedelta(days=3)
                date_max = tx_date_obj + timedelta(days=3)
            except:
                tx_date_obj = None
            if tx_date_obj:
                amount = t["amount"]
                desc_key = t["description"][:8].lower().strip()
                fuzzy_existing = db.query(Transaction).filter(
                    Transaction.transaction_date >= date_min,
                    Transaction.transaction_date <= date_max,
                    Transaction.amount == amount,
                    Transaction.bank_source == t.get("bank_source", "Unknown Bank"),
                ).all()
                fuzzy_match = any(
                    (tx.description or '')[:8].lower().strip() == desc_key
                    for tx in fuzzy_existing
                )
                if fuzzy_match:
                    skipped += 1
                    skipped_merchants.append(t.get('description','')[:20] + ' (fuzzy)')
                    continue

        try:
            date = datetime.strptime(t["transaction_date"], "%Y-%m-%d").date() if t.get("transaction_date") else None
        except:
            date = None

        max_id += 1
        cat_name = t.get("category", "Uncategorized")
        cat_id = cat_map.get(cat_name)

        tx = Transaction(
            transaction_id=gen_uuid(),
            id=max_id,
            uploaded_file_id=upload_rec.uploaded_file_id,
            account_id=account_id,
            fingerprint=fp,
            fingerprint_hash=fp,
            raw_date=t.get("raw_date"),
            raw_description=t.get("raw_description"),
            raw_amount=t.get("raw_amount"),
            raw_category=t.get("raw_category"),
            description_raw=t.get("raw_description"),
            transaction_date=date,
            amount=t.get("amount"),
            currency=t.get("currency", "USD"),
            currency_code=t.get("currency", "USD"),
            description=t.get("description", ""),
            description_clean=t.get("description", ""),
            original_description=t.get("original_description") or t.get("description", ""),
            merchant_name=t.get("description", ""),
            bank_name_raw=detected_bank,
            bank_source=detected_bank,
            transaction_type=t.get("transaction_type", "unknown"),
            category=cat_name,
            category_id=cat_id,
            classification_confidence=t.get("classification_confidence", "low"),
            classification_source="auto",
            needs_review=t.get("needs_review", False),
            review_status="needs_review" if t.get("needs_review") else "reviewed",
            is_pending=False,
            status="posted",
            is_user_edited=False,
            is_edited=False,
            import_source=t.get("import_source", "unknown"),
        )
        try:
            db.add(tx)
            db.flush()  # flush individually to catch duplicates
            saved.append(tx_to_dict(tx))
            if t.get("needs_review"):
                review_count += 1
        except Exception as dup_err:
            db.rollback()
            skipped += 1
            continue

    db.commit()

    # ── Auto-classify fixed vs variable ──
    # Classifier reads all transactions for context (recurrence detection needs history),
    # but we only WRITE results for newly-added transactions in this upload to avoid
    # N+1 UPDATE queries across the whole DB on every upload.
    try:
        saved_ids = {s.get("transaction_id") for s in saved if s.get("transaction_id")}
        all_txs_for_classification = [tx_to_dict(t) for t in db.query(Transaction).all()]
        merchant_rules_rows = db.execute(
            __import__("sqlalchemy").text("SELECT merchant_keyword, is_fixed FROM merchant_rules WHERE user_confirmed = 1")
        ).fetchall()
        merchant_rules = {row[0]: bool(row[1]) for row in merchant_rules_rows}

        classifications = classify_all_transactions(all_txs_for_classification, merchant_rules)
        new_classifications = [c for c in classifications if c.get("transaction_id") in saved_ids]
        for c in new_classifications:
            tx_id = c.get("transaction_id")
            if tx_id:
                db.query(Transaction).filter(
                    Transaction.transaction_id == tx_id
                ).update({
                    "is_fixed": c["is_fixed"],
                    "fixed_confidence": c["confidence"],
                    "fixed_source": c["source"],
                })
        db.commit()
        print(f"CLASSIFIED: {len(new_classifications)} new transactions (of {len(classifications)} considered)")
    except Exception as e:
        print(f"CLASSIFY ERROR: {e}")

    upload_rec.upload_status = "complete"
    upload_rec.transactions_extracted = len(saved)
    # Auto-nullify credit-covered expenses
    import re as _re_nullify
    credits_in_upload = [t for t in saved if t.get('transaction_type') == 'card_credit']
    for credit in credits_in_upload:
        credit_desc = credit.get('description') or ''
        match = _re_nullify.search(r'-\s*(.+)', credit_desc)
        if not match:
            continue
        merchant_key = match.group(1).strip()[:10].lower()
        if not merchant_key:
            continue
        import sqlalchemy as _sa_null
        matching = db.execute(_sa_null.text('''
            SELECT id, amount FROM transactions
            WHERE transaction_type = "expense"
            AND amount < 0
            AND LOWER(description) LIKE :key
            AND exclusion_reason IS NULL
            LIMIT 1
        '''), {'key': f'%{merchant_key}%'}).fetchone()
        if matching:
            net = round(abs(matching[1]) - credit['amount'], 2)
            if net <= 0:
                db.execute(_sa_null.text('''
                    UPDATE transactions SET
                    transaction_type = "excluded",
                    exclusion_reason = "credit_covered"
                    WHERE id = :id
                '''), {'id': matching[0]})
    db.commit()

    upload_rec.duplicates_skipped = skipped
    upload_rec.parse_confidence = 0.9 if detected_bank != "Unknown Bank" else 0.6
    upload_rec.processed_at = datetime.now()
    db.commit()

    print(f"SAVED: {len(saved)} new, {skipped} dupes, {pending_skipped} pending")

    return {
        "success": True,
        "transactions_imported": len(saved),
        "skipped_duplicates": skipped,
        "skipped_merchants": list(set(skipped_merchants))[:5],
        "skipped_pending": pending_skipped,
        "needs_review": review_count,
        "bank_source": detected_bank,
        "uploaded_file_id": upload_rec.uploaded_file_id,
        "transactions": saved,
    }

# ── Transactions ──

@app.get("/transactions")
def get_transactions(include_pending: bool = False, db: Session = Depends(get_db)):
    import re as _re
    # Build credit map
    import sqlalchemy as _sa
    credits = db.execute(_sa.text(
        'SELECT description, amount FROM transactions WHERE transaction_type = "card_credit"'
    )).fetchall()
    credit_map = {}
    for c in credits:
        match = _re.search(r'-\s*(.+)', c[0] or '')
        if match:
            key = match.group(1).strip()[:10].lower()
            credit_map[key] = credit_map.get(key, 0) + c[1]

    q = db.query(Transaction)
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

@app.get("/transactions/review")
def get_review_queue(db: Session = Depends(get_db)):
    txs = db.query(Transaction).filter(
        Transaction.needs_review == True,
        Transaction.is_pending == False,
    ).order_by(Transaction.transaction_date.desc()).all()
    return [tx_to_dict(t) for t in txs]

@app.post("/transactions/manual")
def add_manual(tx: ManualTransaction, db: Session = Depends(get_db)):
    from classifier import generate_fingerprint
    try:
        date = datetime.strptime(tx.transaction_date, "%Y-%m-%d").date()
    except:
        date = datetime.today().date()

    fp = generate_fingerprint("manual", str(date), tx.amount, tx.description)
    max_id = db.query(Transaction).count() + 1

    cat_map = {c.category_name: c.category_id for c in db.query(Category).all()}
    cat_id = cat_map.get(tx.category)

    new_tx = Transaction(
        transaction_id=gen_uuid(),
        id=max_id,
        fingerprint=fp,
        fingerprint_hash=fp,
        transaction_date=date,
        description=tx.description,
        description_clean=tx.description,
        description_raw=tx.description,
        original_description=tx.description,
        raw_description=tx.description,
        raw_date=tx.transaction_date,
        raw_amount=str(tx.amount),
        amount=tx.amount,
        currency=tx.currency,
        currency_code=tx.currency,
        category=tx.category,
        category_id=cat_id,
        transaction_type=tx.transaction_type,
        classification_confidence="high",
        classification_source="user",
        needs_review=False,
        review_status="reviewed",
        bank_source=tx.bank_source,
        import_source="manual",
        status="posted",
        notes=tx.notes,
        is_user_edited=False,
        is_edited=False,
    )
    db.add(new_tx)
    db.commit()
    db.refresh(new_tx)
    return {"success": True, "transaction": tx_to_dict(new_tx)}

@app.patch("/transactions/{tid}")
def update_transaction(tid: int, update: TransactionUpdate, db: Session = Depends(get_db)):
    # If category changed → re-run fixed classifier
    if update.category is not None:
        from fixed_classifier import classify_transaction, normalize_merchant
        from classifier import normalize_description
        import sqlalchemy as _sa
        # Auto-set transaction_type based on category
        if update.category == 'Transfer':
            update.transaction_type = 'transfer'
        elif update.category in ('Credit Card Payment', 'Payment'):
            update.transaction_type = 'credit_card_payment'
            update.category = 'Credit Card Payment'
        t = db.query(Transaction).filter(Transaction.id == tid).first()
        if t and t.category != update.category:
            # Save user correction to merchant_rules
            norm_desc = normalize_description(t.description or '')
            norm_merchant = norm_desc[:30].strip() if norm_desc else ''
            if norm_merchant:
                # Check if rule exists
                existing = db.execute(_sa.text(
                    "SELECT id FROM merchant_rules WHERE match_value = :mv AND user_id IS NULL"
                ), {'mv': norm_merchant}).fetchone()
                if existing:
                    db.execute(_sa.text(
                        "UPDATE merchant_rules SET category = :cat, match_type = 'contains', is_active = 1, updated_at = datetime('now') WHERE id = :id"
                    ), {'cat': update.category, 'id': existing[0]})
                else:
                    db.execute(_sa.text('''
                        INSERT INTO merchant_rules (merchant_keyword, match_value, match_type, match_field, category, transaction_type, priority, source, is_active, is_fixed, user_id, updated_at)
                        VALUES (:mv, :mv, 'contains', 'merchant', :cat, 'expense', 10, 'user_correction', 1, 0, NULL, datetime('now'))
                    '''), {'mv': norm_merchant, 'cat': update.category})
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
                "SELECT transaction_id, description, category, amount, transaction_type, transaction_date FROM transactions WHERE transaction_type = 'expense' AND amount < 0"
            )).fetchall()
            all_txs_list = [dict(r._mapping) for r in all_txs]
            result = classify_transaction(tx_dict, all_txs_list)
            db.execute(_sa.text(
                "UPDATE transactions SET is_fixed=:f, fixed_confidence=:c, fixed_source=:s WHERE id=:id"
            ), {'f': int(result['is_fixed']), 'c': result['confidence'], 's': 'user_override', 'id': tid})
            db.commit()
    tx = db.query(Transaction).filter(Transaction.id == tid).first()
    if not tx:
        raise HTTPException(404, "Transaction not found")
    cat_map = {c.category_name: c.category_id for c in db.query(Category).all()}
    if update.transaction_date:
        try:
            tx.transaction_date = datetime.strptime(update.transaction_date, "%Y-%m-%d").date()
        except:
            pass
    if update.description is not None:
        tx.description = update.description
        tx.description_clean = update.description
    if update.amount is not None:
        tx.amount = update.amount
    if update.currency is not None:
        tx.currency = update.currency
        tx.currency_code = update.currency
    if update.category is not None:
        tx.category = update.category
        tx.category_id = cat_map.get(update.category)
    if update.transaction_type is not None:
        tx.transaction_type = update.transaction_type
    if update.bank_source is not None:
        tx.bank_source = update.bank_source
    if update.notes is not None:
        tx.notes = update.notes
    if update.needs_review is not None:
        tx.needs_review = update.needs_review
    if update.review_status is not None:
        tx.review_status = update.review_status
    if update.exclusion_reason is not None:
        tx.exclusion_reason = update.exclusion_reason
    tx.is_user_edited = True
    tx.is_edited = True
    tx.needs_review = False
    tx.review_status = "reviewed"
    db.commit()
    return {"success": True, "transaction": tx_to_dict(tx)}

@app.delete("/transactions/{tid}")
def delete_transaction(tid: int, db: Session = Depends(get_db)):
    tx = db.query(Transaction).filter(Transaction.id == tid).first()
    if not tx:
        raise HTTPException(404, "Not found")
    db.delete(tx)
    db.commit()
    return {"success": True}

# ── Rules ──

@app.get("/rules")
def get_rules(db: Session = Depends(get_db)):
    rules = db.query(TransactionRule).filter(TransactionRule.active == True).order_by(TransactionRule.priority.desc()).all()
    return [{"id": r.rule_id, "match_field": r.match_field, "match_operator": r.match_operator, "match_value": r.match_value, "output_transaction_type": r.output_transaction_type, "output_category": r.output_category, "priority": r.priority} for r in rules]

@app.post("/rules")
def create_rule(rule: RuleCreate, db: Session = Depends(get_db)):
    new_rule = TransactionRule(
        rule_id=gen_uuid(),
        match_field=rule.match_field,
        match_operator=rule.match_operator,
        match_value=rule.match_value,
        output_transaction_type=rule.output_transaction_type,
        output_category=rule.output_category,
        priority=rule.priority,
        active=True,
    )
    db.add(new_rule)
    db.commit()
    return {"success": True, "rule_id": new_rule.rule_id}

@app.delete("/rules/{rid}")
def delete_rule(rid: str, db: Session = Depends(get_db)):
    rule = db.query(TransactionRule).filter(TransactionRule.rule_id == rid).first()
    if not rule:
        raise HTTPException(404, "Not found")
    db.delete(rule)
    db.commit()
    return {"success": True}

# ── Summary ──

@app.get("/summary")
def get_summary(db: Session = Depends(get_db)):
    txs = db.query(Transaction).filter(Transaction.is_pending == False).all()
    expense_txs = [t for t in txs if t.transaction_type == "expense" and t.amount and t.amount < 0 and not t.exclusion_reason]
    total_spent = sum(abs(t.amount) for t in expense_txs)
    total_income = sum(t.amount for t in txs if t.transaction_type == "income" and t.amount and t.amount > 0)
    debt_payments = sum(abs(t.amount) for t in txs if t.transaction_type in ("loan_payment", "credit_card_payment") and t.amount)
    by_bank = {}
    for t in txs:
        b = t.bank_source or "Unknown"
        if b not in by_bank:
            by_bank[b] = {"transactions": 0, "spent": 0, "income": 0}
        by_bank[b]["transactions"] += 1
        if t.transaction_type == "expense" and t.amount and t.amount < 0:
            by_bank[b]["spent"] += abs(t.amount)
        if t.transaction_type == "income" and t.amount:
            by_bank[b]["income"] += t.amount
    return {
        "total_transactions": len(txs),
        "total_spent": round(total_spent, 2),
        "total_income": round(total_income, 2),
        "debt_payments": round(debt_payments, 2),
        "balance": round(total_income - total_spent, 2),
        "banks": by_bank,
        "needs_review": db.query(Transaction).filter(Transaction.needs_review == True).count(),
    }

# ── Uploaded files history ──

@app.get("/uploads")
def get_uploads(db: Session = Depends(get_db)):
    files = db.query(UploadedFileModel).order_by(UploadedFileModel.uploaded_at.desc()).all()
    return [{
        "id": f.uploaded_file_id,
        "file_name": f.file_name,
        "file_type": f.file_type,
        "bank_name": f.bank_name,
        "status": f.upload_status,
        "transactions_extracted": f.transactions_extracted,
        "duplicates_skipped": f.duplicates_skipped,
        "uploaded_at": str(f.uploaded_at),
        "parse_confidence": f.parse_confidence,
    } for f in files]

# ── Privacy: delete all ──

@app.delete("/data/all")
def delete_all_data(confirm: str = "no", db: Session = Depends(get_db)):
    if confirm != "yes":
        raise HTTPException(status_code=400, detail="Pass ?confirm=yes to delete all data")
    db.query(Transaction).delete()
    db.query(TransactionRule).delete()
    db.query(UploadedFileModel).delete()
    db.commit()
    return {"success": True, "message": "All data deleted"}

# ── Chat ──

@app.post("/chat")
def chat(msg: ChatMessage, db: Session = Depends(get_db)):
    txs = db.query(Transaction).filter(Transaction.is_pending == False).all()
    tx_list = [{"date": str(t.transaction_date), "description": t.description, "amount": t.amount, "currency": t.currency, "category": t.category, "transaction_type": t.transaction_type, "bank_source": t.bank_source} for t in txs]
    try:
        response = get_ai_response(msg.message, tx_list)
        return {"success": True, "response": response}
    except Exception as e:
        return {"success": False, "error": str(e)}

# ── Budget History ──
@app.get("/budget-history")
def get_budget_history(db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    rows = db.execute(_sa.text(
        "SELECT month, amount FROM budget_history ORDER BY month DESC"
    )).fetchall()
    return {row[0]: row[1] for row in rows}

# ── Credit Offset Calculation ──
def get_credit_offsets_map(db):
    import sqlalchemy as _sa
    import re as _re
    credits = db.execute(_sa.text(
        'SELECT description, amount FROM transactions WHERE transaction_type = "card_credit"'
    )).fetchall()
    credit_map = {}
    for c in credits:
        desc = c[0] or ''
        match = _re.search(r'-\s*(.+)', desc)
        if match:
            key = match.group(1).strip()[:10].lower()
            credit_map[key] = credit_map.get(key, 0) + c[1]
    return credit_map

# ── Project / Goals Endpoints ──

from models import Project
from datetime import date as date_type

class ProjectCreate(BaseModel):
    name: str
    type: str = "custom"  # savings | debt | custom
    target_amount: Optional[float] = None
    target_date: Optional[str] = None

class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    type: Optional[str] = None
    target_amount: Optional[float] = None
    target_date: Optional[str] = None
    is_archived: Optional[bool] = None

class TransactionProjectUpdate(BaseModel):
    project_id: Optional[int] = None

@app.get("/projects")
def get_projects(include_archived: bool = False, db: Session = Depends(get_db)):
    q = db.query(Project)
    if not include_archived:
        q = q.filter(Project.is_archived == False)
    projects = q.order_by(Project.created_at.desc()).all()
    result = []
    for p in projects:
        progress = calculate_project_progress(p)
        result.append({
            "id": p.id,
            "name": p.name,
            "type": p.type,
            "target_amount": p.target_amount,
            "target_date": str(p.target_date) if p.target_date else None,
            "is_archived": p.is_archived,
            "created_at": str(p.created_at),
            **progress
        })
    return result

@app.post("/projects")
def create_project(data: ProjectCreate, db: Session = Depends(get_db)):
    p = Project(
        name=data.name,
        type=data.type,
        target_amount=data.target_amount,
        target_date=datetime.strptime(data.target_date, "%Y-%m-%d").date() if data.target_date else None,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"id": p.id, "name": p.name, "type": p.type, "target_amount": p.target_amount}

@app.patch("/projects/{pid}")
def update_project(pid: int, data: ProjectUpdate, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    if data.name is not None: p.name = data.name
    if data.type is not None: p.type = data.type
    if data.target_amount is not None: p.target_amount = data.target_amount
    if data.target_date is not None: p.target_date = datetime.strptime(data.target_date, "%Y-%m-%d").date()
    if data.is_archived is not None: p.is_archived = data.is_archived
    db.commit()
    return {"success": True}

@app.delete("/projects/{pid}")
def delete_project(pid: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    # Unlink transactions
    db.query(Transaction).filter(Transaction.project_id == pid).update({"project_id": None})
    db.delete(p)
    db.commit()
    return {"success": True}

@app.get("/projects/{pid}/progress")
def get_project_progress(pid: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return {"id": p.id, "name": p.name, **calculate_project_progress(p)}

@app.patch("/transactions/{tid}/project")
def update_transaction_project(tid: int, data: TransactionProjectUpdate, db: Session = Depends(get_db)):
    t = db.query(Transaction).filter(Transaction.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")
    t.project_id = data.project_id
    db.commit()
    return {"success": True}

def calculate_project_progress(p: Project) -> dict:
    txns = p.transactions if p.transactions else []
    if p.type == "debt":
        current = sum(abs(t.amount) for t in txns if t.amount and t.amount < 0)
    else:
        current = sum(t.amount for t in txns if t.amount and t.amount > 0)
    target = p.target_amount or 0
    pct = min(round((current / target * 100), 1), 100) if target > 0 else 0
    remaining = max(target - current, 0) if target > 0 else None
    on_track = None
    if p.target_date and target > 0 and p.created_at:
        days_total = (p.target_date - p.created_at.date()).days
        days_elapsed = (date_type.today() - p.created_at.date()).days
        if days_total > 0:
            expected = (days_elapsed / days_total) * target
            on_track = current >= expected * 0.9
    return {
        "current_amount": round(current, 2),
        "percentage": pct,
        "remaining": round(remaining, 2) if remaining is not None else None,
        "on_track": on_track,
        "transaction_count": len(txns),
    }

# ── Dashboard Summary (tier-aware) ──────────────────────────────────────────
# Contract: frontend consumes data_tier, comparison, trend_chart.
# Reason enum: not_enough_months | no_previous_month | prev_month_incomplete
#              | zero_baseline | stale_data

from sqlalchemy import extract as _extract

_COMPARABILITY_MIN_TXNS = 10
_COMPARABILITY_MIN_FLEX = 200.0

def _calendar_previous_ym(ym: str) -> str:
    year, month = int(ym[:4]), int(ym[5:7])
    if month == 1:
        return f"{year - 1:04d}-12"
    return f"{year:04d}-{month - 1:02d}"

def _month_label_long(ym: str) -> str:
    return datetime.strptime(ym, "%Y-%m").strftime("%B %Y")

def _month_label_short(ym: str) -> str:
    return datetime.strptime(ym, "%Y-%m").strftime("%b %y")

def _months_with_data(db: Session) -> list:
    rows = db.query(
        _extract('year', Transaction.transaction_date).label('y'),
        _extract('month', Transaction.transaction_date).label('m'),
    ).filter(
        Transaction.transaction_date.isnot(None),
    ).distinct().order_by('y', 'm').all()
    return [f"{int(r.y):04d}-{int(r.m):02d}" for r in rows]

def _top_transactions(transactions: list, n: int = 5) -> list:
    """Return top N transactions by amount, formatted for the dashboard API.
    Each tx is a dict: {date, merchant, amount}.
    Merchant goes through display_merchant for clean output."""
    sorted_txs = sorted(transactions, key=lambda t: t['amount'], reverse=True)
    out = []
    for t in sorted_txs[:n]:
        clean = display_merchant(t['description'] or '') or 'Unknown'
        out.append({
            'date': t['date'],
            'merchant': clean[:80],
            'amount': round(t['amount'], 2),
        })
    return out


def _category_insight(transactions: list, category_name: str) -> dict:
    """Pick 1 interpretive insight from 7 templates, in priority order.
    Each template returns {"template": "<name>", "text": "<copy>"}.
    Returns fallback if nothing else fires.

    Priority (first match wins):
        1. single_merchant   — only 1 unique merchant
        2. dominance         — top txn > 50% of category
        3. burst             — >=40% spend within any 48hr window
        4. repeat_merchant   — one merchant appears >=3 times
        5. weekend           — >=70% spend on Sat+Sun
        6. concentration     — top 2 merchants > 40% combined
        7. fallback          — avg + range
    """
    if not transactions:
        return {'template': 'fallback', 'text': 'No transactions in this category.'}

    total = sum(t['amount'] for t in transactions)
    if total <= 0:
        return {'template': 'fallback', 'text': 'No spending in this category.'}

    # Group by clean merchant name
    from collections import defaultdict
    by_merchant = defaultdict(lambda: {'count': 0, 'amount': 0.0})
    for t in transactions:
        clean = display_merchant(t['description'] or '') or 'Unknown'
        by_merchant[clean]['count'] += 1
        by_merchant[clean]['amount'] += t['amount']

    merchants_by_spend = sorted(
        by_merchant.items(), key=lambda kv: kv[1]['amount'], reverse=True
    )
    merchants_by_count = sorted(
        by_merchant.items(),
        key=lambda kv: (kv[1]['count'], kv[1]['amount']),
        reverse=True,
    )

    # ── 1. Single-merchant — only one unique merchant ──
    if len(by_merchant) == 1:
        m_name = merchants_by_spend[0][0]
        return {
            'template': 'single_merchant',
            'text': f'All from one merchant: {m_name}.',
        }

    # ── 2. Dominance — top txn > 50% of category ──
    top_tx = max(transactions, key=lambda t: t['amount'])
    if top_tx['amount'] / total > 0.5 and len(transactions) > 1:
        m_name = display_merchant(top_tx['description'] or '') or 'Unknown'
        pct = round(top_tx['amount'] / total * 100)
        return {
            'template': 'dominance',
            'text': (
                f'One purchase made up most of this category: '
                f'{m_name} was {pct}% of {category_name} spend.'
            ),
        }

    # ── 3. Burst — >=40% spend within any 48hr window ──
    from datetime import datetime, timedelta
    dated_txs = []
    for t in transactions:
        if t.get('date'):
            try:
                dt = datetime.fromisoformat(str(t['date']))
                dated_txs.append((dt, t['amount']))
            except (ValueError, TypeError):
                pass

    if len(dated_txs) >= 2:
        dated_txs.sort(key=lambda x: x[0])
        # Sliding window: for each tx, sum amounts within 48hrs forward
        best_window_sum = 0
        best_window_start = None
        best_window_end = None
        for i, (dt_i, _) in enumerate(dated_txs):
            window_sum = 0
            window_end = dt_i
            for dt_j, amt_j in dated_txs[i:]:
                if dt_j - dt_i <= timedelta(hours=48):
                    window_sum += amt_j
                    window_end = dt_j
                else:
                    break
            if window_sum > best_window_sum:
                best_window_sum = window_sum
                best_window_start = dt_i
                best_window_end = window_end

        if best_window_sum / total >= 0.4 and best_window_start != best_window_end:
            start_str = best_window_start.strftime('%b %d').replace(' 0', ' ')
            end_str = best_window_end.strftime('%b %d').replace(' 0', ' ')
            # If same day, show one date only — but burst requires multi-day, this is safety
            if start_str == end_str:
                date_phrase = start_str
            else:
                end_day = best_window_end.strftime('%d').lstrip('0')
                date_phrase = f'{start_str}–{end_day}'
            return {
                'template': 'burst',
                'text': f'Most spend happened in a 2-day burst around {date_phrase}.',
            }

    # ── 4. Repeat merchant — one merchant appears >=3 times ──
    top_count_merchant = merchants_by_count[0]
    if top_count_merchant[1]['count'] >= 3:
        m_name = top_count_merchant[0]
        n_times = top_count_merchant[1]['count']
        return {
            'template': 'repeat_merchant',
            'text': f'You visited {m_name} {n_times} times this month.',
        }

    # ── 5. Weekend — >=70% spend on Sat+Sun ──
    weekend_spend = 0
    for dt, amt in dated_txs:
        if dt.weekday() >= 5:  # 5=Sat, 6=Sun
            weekend_spend += amt
    if dated_txs and weekend_spend / total >= 0.7:
        return {
            'template': 'weekend',
            'text': f'Most {category_name} spend happened on weekends.',
        }

    # ── 6. Concentration — top 2 merchants > 40% combined ──
    if len(merchants_by_spend) >= 2:
        top2_sum = merchants_by_spend[0][1]['amount'] + merchants_by_spend[1][1]['amount']
        if top2_sum / total > 0.4:
            m1 = merchants_by_spend[0][0]
            m2 = merchants_by_spend[1][0]
            return {
                'template': 'concentration',
                'text': f'Most spend was at {m1} and {m2}.',
            }

    # ── 7. Fallback — avg + range ──
    amounts = [t['amount'] for t in transactions]
    avg = total / len(amounts)
    return {
        'template': 'fallback',
        'text': (
            f'Purchases ranged from ${round(min(amounts))} to ${round(max(amounts))}, '
            f'averaging ${round(avg)}.'
        ),
    }


def _month_totals(db: Session, ym: str) -> dict:
    year, month = int(ym[:4]), int(ym[5:7])
    rows = db.query(Transaction).filter(
        _extract('year', Transaction.transaction_date) == year,
        _extract('month', Transaction.transaction_date) == month,
        Transaction.transaction_type == 'expense',
        Transaction.amount < 0,
        Transaction.exclusion_reason.is_(None),
    ).all()
    flexible = 0.0
    committed = 0.0
    flex_by_category = {}            # name -> {"amount": ..., "count": ...}
    biggest = None                   # tracks the largest single flexible charge

    for t in rows:
        amt = abs(t.amount or 0)
        if t.is_fixed:
            committed += amt
        else:
            flexible += amt
            cat = t.category or "Other"
            entry = flex_by_category.setdefault(
                cat, {"amount": 0.0, "count": 0, "transactions": []}
            )
            entry["amount"] += amt
            entry["count"] += 1
            entry["transactions"].append({
                "amount": amt,
                "description": t.description or "",
                "date": str(t.transaction_date) if t.transaction_date else None,
            })
            if biggest is None or amt > biggest["amount"]:
                clean_name = display_merchant(t.description or "") or "Unknown"
                biggest = {
                    "merchant": clean_name[:80],
                    "amount": round(amt, 2),
                    "date": str(t.transaction_date) if t.transaction_date else None,
                    "category": cat,
                }

    # Pick top category by flexible spend
    top_category = None
    if flex_by_category:
        name, info = max(flex_by_category.items(), key=lambda kv: kv[1]["amount"])
        pct = (info["amount"] / flexible * 100) if flexible > 0 else 0
        top_category = {
            "name": name,
            "amount": round(info["amount"], 2),
            "pct_of_flexible": round(pct, 1),
            "txn_count": info["count"],
        }

    # Build per-category drilldown data (Phase 2)
    categories = []
    for name, info in flex_by_category.items():
        cat_pct = (info["amount"] / flexible * 100) if flexible > 0 else 0
        categories.append({
            "name": name,
            "amount": round(info["amount"], 2),
            "pct_of_flexible": round(cat_pct, 1),
            "txn_count": info["count"],
            "avg_amount": round(info["amount"] / info["count"], 2) if info["count"] > 0 else 0,
            "top_transactions": _top_transactions(info["transactions"]),
            "insight": _category_insight(info["transactions"], name),
        })
    categories.sort(key=lambda c: c["amount"], reverse=True)

    return {
        "label": _month_label_long(ym),
        "ym": ym,
        "total": round(flexible + committed, 2),
        "flexible": round(flexible, 2),
        "committed": round(committed, 2),
        "txn_count": len(rows),
        "top_category": top_category,
        "biggest_charge": biggest,
        "categories": categories,
    }

def _build_comparison(current: dict, prev, months_available: int) -> dict:
    empty = {"delta_abs": None, "delta_pct": None, "direction": None}
    if months_available <= 1:
        return {"status": "unavailable", "reason": "not_enough_months",
                "message": "Upload another month to unlock month-over-month comparison",
                **empty}
    if prev is None:
        return {"status": "unavailable", "reason": "no_previous_month",
                "message": "Previous month has no data", **empty}
    if prev["flexible"] <= 0:
        return {"status": "unavailable", "reason": "zero_baseline",
                "message": "Previous month had no flexible spending", **empty}
    if prev["txn_count"] < _COMPARABILITY_MIN_TXNS or prev["flexible"] < _COMPARABILITY_MIN_FLEX:
        return {"status": "unavailable", "reason": "prev_month_incomplete",
                "message": "Previous month data incomplete", **empty}
    delta_abs = round(current["flexible"] - prev["flexible"], 2)
    direction = "up" if delta_abs > 0 else ("down" if delta_abs < 0 else "flat")
    delta_pct = round((delta_abs / prev["flexible"]) * 100, 1)
    if months_available == 2:
        return {"status": "absolute", "reason": None, "message": None,
                "delta_abs": delta_abs, "delta_pct": None, "direction": direction}
    return {"status": "percentage", "reason": None, "message": None,
            "delta_abs": delta_abs, "delta_pct": delta_pct, "direction": direction}

def _build_trend_chart(db: Session, months_available: list, tier: int, current_ym: str) -> dict:
    if tier == 1:
        return {"show": False, "reason": "not_enough_months",
                "message": "Upload another month to unlock trends", "months": []}
    idx = months_available.index(current_ym) if current_ym in months_available else len(months_available) - 1
    window = months_available[max(0, idx - 5):idx + 1]
    months = []
    for ym in window:
        t = _month_totals(db, ym)
        months.append({"label": _month_label_short(ym), "ym": ym,
                       "flexible": t["flexible"], "committed": t["committed"]})
    return {"show": True, "reason": None, "message": None, "months": months}

@app.get("/dashboard-summary")
def get_dashboard_summary(month: Optional[str] = None, db: Session = Depends(get_db)):
    months_available = _months_with_data(db)
    if not months_available:
        return {
            "data_tier": 1, "months_available": 0,
            "current_month": None, "previous_month": None,
            "comparison": {"status": "unavailable", "reason": "not_enough_months",
                           "message": "No transactions yet",
                           "delta_abs": None, "delta_pct": None, "direction": None},
            "trend_chart": {"show": False, "reason": "not_enough_months",
                            "message": "Upload a statement to see your dashboard", "months": []},
        }
    current_ym = month if (month and month in months_available) else months_available[-1]
    prev_ym = _calendar_previous_ym(current_ym)
    prev_exists = prev_ym in months_available
    current = _month_totals(db, current_ym)
    prev = _month_totals(db, prev_ym) if prev_exists else None
    tier = 1 if len(months_available) <= 1 else (2 if len(months_available) == 2 else 3)
    return {
        "data_tier": tier,
        "months_available": len(months_available),
        "current_month": current,
        "previous_month": prev,
        "comparison": _build_comparison(current, prev, len(months_available)),
        "trend_chart": _build_trend_chart(db, months_available, tier, current_ym),
    }

# ── Fixed expenses summary ──
@app.get("/fixed-summary")
def get_fixed_expenses_summary(db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    import re as _re
    from fixed_classifier import get_fixed_summary, get_subscription_summary
    txs = [tx_to_dict(t) for t in db.query(Transaction).filter(
        Transaction.transaction_type == 'expense',
        Transaction.amount < 0,
        Transaction.exclusion_reason == None
    ).all()]

    # Also include credit-covered transactions so they show as "fully covered"
    covered_txs = [tx_to_dict(t) for t in db.query(Transaction).filter(
        Transaction.exclusion_reason == 'credit_covered',
        Transaction.is_fixed == True
    ).all()]

    all_fixed_txs = txs + covered_txs
    fixed = get_fixed_summary([t for t in all_fixed_txs if t.get('is_fixed')])
    subs = get_subscription_summary(all_fixed_txs)

    # Get card credits to compute coverage
    credits = db.execute(_sa.text(
        'SELECT description, amount FROM transactions WHERE transaction_type = "card_credit"'
    )).fetchall()

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
        "SELECT name, amount FROM manual_fixed_expenses ORDER BY amount DESC"
    )).fetchall()
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

@app.patch("/transactions/{tid}/fixed")
def update_transaction_fixed(tid: int, data: dict, db: Session = Depends(get_db)):
    from fixed_classifier import normalize_merchant
    t = db.query(Transaction).filter(Transaction.id == tid).first()
    if not t:
        raise HTTPException(status_code=404, detail="Transaction not found")

    is_fixed = data.get('is_fixed', False)
    t.is_fixed = is_fixed
    t.fixed_confidence = 1.0
    t.fixed_source = 'user_confirmed'

    # Save merchant rule so future uploads remember this
    merchant_key = normalize_merchant(t.description or '')[:8]
    if merchant_key:
        existing = db.execute(
            __import__('sqlalchemy').text(
                "SELECT id FROM merchant_rules WHERE merchant_keyword = :k"
            ), {'k': merchant_key}
        ).fetchone()
        if existing:
            db.execute(
                __import__('sqlalchemy').text(
                    "UPDATE merchant_rules SET is_fixed=:f, user_confirmed=1 WHERE merchant_keyword=:k"
                ), {'f': int(is_fixed), 'k': merchant_key}
            )
        else:
            db.execute(
                __import__('sqlalchemy').text(
                    "INSERT INTO merchant_rules (merchant_keyword, is_fixed, user_confirmed, confidence) VALUES (:k, :f, 1, 1.0)"
                ), {'k': merchant_key, 'f': int(is_fixed)}
            )
    db.commit()
    return {'success': True}

# ── Manual Fixed Expenses ──
@app.get("/manual-fixed")
def get_manual_fixed(db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    rows = db.execute(_sa.text(
        "SELECT id, name, amount, frequency FROM manual_fixed_expenses ORDER BY amount DESC"
    )).fetchall()
    return [{"id": r[0], "name": r[1], "amount": r[2], "frequency": r[3]} for r in rows]

@app.post("/manual-fixed")
def add_manual_fixed(data: dict, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    db.execute(_sa.text(
        "INSERT INTO manual_fixed_expenses (name, amount, frequency) VALUES (:name, :amount, :frequency)"
    ), {"name": data.get("name"), "amount": float(data.get("amount", 0)), "frequency": data.get("frequency", "monthly")})
    db.commit()
    return {"success": True}

@app.delete("/manual-fixed/{item_id}")
def delete_manual_fixed(item_id: int, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    db.execute(_sa.text("DELETE FROM manual_fixed_expenses WHERE id = :id"), {"id": item_id})
    db.commit()
    return {"success": True}

# ── Merchant Rules ──
@app.post("/merchant-rules/dismiss")
def dismiss_merchant_rule(data: dict, db: Session = Depends(get_db)):
    from fixed_classifier import normalize_merchant
    import sqlalchemy as _sa
    merchant = data.get("merchant", "")
    key = normalize_merchant(merchant)[:8]
    if key:
        existing = db.execute(_sa.text(
            "SELECT id FROM merchant_rules WHERE merchant_keyword = :k"
        ), {'k': key}).fetchone()
        if existing:
            db.execute(_sa.text(
                "UPDATE merchant_rules SET is_fixed=0, user_confirmed=1 WHERE merchant_keyword=:k"
            ), {'k': key})
        else:
            db.execute(_sa.text(
                "INSERT INTO merchant_rules (merchant_keyword, is_fixed, user_confirmed, confidence) VALUES (:k, 0, 1, 1.0)"
            ), {'k': key})
        db.commit()
    return {"success": True}


# ── Credit Nullification ──
@app.get("/insights")
def get_insights(month: str = None, db: Session = Depends(get_db)):
    from insights import generate_insights
    import sqlalchemy as _sa

    rows = db.execute(_sa.text("""
        SELECT transaction_id, description, category, amount, transaction_type,
               transaction_date, is_fixed, bank_source
        FROM transactions
        WHERE transaction_type IN ('expense', 'income', 'transfer', 'credit_card_payment')
        AND is_pending = 0
        ORDER BY transaction_date
    """)).fetchall()

    txs = [dict(r._mapping) for r in rows]

    profile_row = db.execute(_sa.text(
        "SELECT monthly_budget FROM users LIMIT 1"
    )).fetchone()
    budget = float(profile_row[0] or 0) if profile_row else 0

    if month:
        bh_row = db.execute(_sa.text(
            "SELECT amount FROM budget_history WHERE month = :m"
        ), {'m': month}).fetchone()
        if bh_row:
            budget = float(bh_row[0])

    insights = generate_insights(txs, budget, month)
    return insights

# ── Auth Endpoints ──
from auth import hash_password, verify_password, create_token, decode_token, security

@app.post("/auth/signup")
def auth_signup(data: dict, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    email = (data.get("email") or "").lower().strip()
    password = data.get("password") or ""
    name = data.get("name") or ""
    budget = float(data.get("monthly_budget") or 0)
    if not email or not password:
        raise HTTPException(status_code=400, detail="Email and password required")
    existing = db.execute(_sa.text("SELECT user_id FROM users WHERE email = :e"), {"e": email}).fetchone()
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    hashed = hash_password(password)
    # Check if user row exists (from onboarding)
    existing_user = db.execute(_sa.text("SELECT user_id FROM users LIMIT 1")).fetchone()
    if existing_user:
        db.execute(_sa.text(
            "UPDATE users SET email=:e, password_hash=:p, full_name=:n, monthly_budget=:b WHERE user_id=:uid"
        ), {"e": email, "p": hashed, "n": name, "b": budget, "uid": existing_user[0]})
        user_id = existing_user[0]
    else:
        db.execute(_sa.text(
            "INSERT INTO users (email, password_hash, full_name, monthly_budget) VALUES (:e, :p, :n, :b)"
        ), {"e": email, "p": hashed, "n": name, "b": budget})
        user_id = db.execute(_sa.text("SELECT user_id FROM users WHERE email=:e"), {"e": email}).fetchone()[0]
    db.commit()
    token = create_token(user_id, email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": name, "monthly_budget": budget}}

@app.post("/auth/login")
def auth_login(data: dict, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    email = (data.get("email") or "").lower().strip()
    password = data.get("password") or ""
    user = db.execute(_sa.text(
        "SELECT user_id, email, password_hash, full_name, monthly_budget FROM users WHERE email = :e"
    ), {"e": email}).fetchone()
    if not user or not verify_password(password, user[2]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_token(user[0], user[1])
    return {"token": token, "user": {"id": user[0], "email": user[1], "name": user[3], "monthly_budget": user[4]}}

@app.get("/auth/me")
def auth_me(credentials = Depends(security)):
    if not credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    payload = decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid token")
    return payload

# ── Credit Offsets API ──
@app.get("/credit-offsets/{period}")
def get_credit_offsets_period(period: str, db: Session = Depends(get_db)):
    import sqlalchemy as _sa
    from credit_engine import get_net_category_spend

    offsets = db.execute(_sa.text('''
        SELECT co.id, co.credit_type, co.eligible_for_matching,
               co.applied_amount, co.unapplied_amount,
               co.match_confidence, co.match_method,
               co.matched_category, t.description, t.amount
        FROM credit_offsets co
        JOIN transactions t ON t.transaction_id = co.credit_transaction_id
        WHERE co.statement_period = :period
        AND co.is_active = 1
        ORDER BY co.applied_amount DESC
    '''), {'period': period}).fetchall()

    net_spend = get_net_category_spend(db, period)

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

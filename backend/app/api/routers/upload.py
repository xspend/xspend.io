from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
import traceback

from app.db import get_db
from app.auth import get_current_user
from app.models import Transaction, UploadedFile as UploadedFileModel, Category
from app.parsers import parse_statement
from app.services.fixed_classifier import classify_all_transactions
from app.api.common import tx_to_dict

router = APIRouter()


@router.post("/upload")
async def upload_statement(
    file: UploadFile = File(...),
    bank_name: str = "Unknown Bank",
    account_id: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: int = Depends(get_current_user)
):
    contents = await file.read()
    print(f"UPLOAD: {file.filename} size={len(contents)} bank={bank_name} AS_USER={current_user}")

    # Parse an account label from the filename so multiple accounts at the same
    # bank (e.g. two Chase cards) don't dedup against each other. No user input.
    def _account_label(fname, bank):
        import re as _re
        if not fname:
            return bank
        stem = fname.rsplit('.', 1)[0]
        # Prefer digits immediately following the bank name (e.g. "Chase1087").
        m = _re.search(_re.escape((bank or '').replace(' ', '')) + r'[ _-]?(\d{3,6})', stem, _re.I)
        if not m:
            # Else first 3-6 digit run that is NOT an 8-digit date (YYYYMMDD).
            for tok in _re.findall(r'\d{3,}', stem):
                if len(tok) != 8:
                    m = type('M', (), {'group': lambda self, i, t=tok: t})()
                    break
        return f"{bank} {m.group(1)}" if m else bank

    # Load user correction rules from merchant_rules table
    from app.parsers import load_merchant_rules
    user_rules = load_merchant_rules(db, current_user)

    # Create upload record
    upload_rec = UploadedFileModel(
        file_name=file.filename,
        file_type=file.filename.split(".")[-1].lower(),
        source_type="upload",
        bank_name=bank_name,
        upload_status="processing",
        account_id=account_id,
        user_id=current_user,
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
    cat_map = {c.category_name: c.id for c in db.query(Category).all()}

    import time as _time
    _t0 = _time.time()
    saved, skipped, pending_skipped, review_count = [], 0, 0, 0
    skipped_merchants = []

    # ── PERF: load existing dedup data ONCE into memory (was ~3 queries per
    # transaction = hundreds of network round-trips on remote Postgres). ──
    from collections import defaultdict as _defaultdict
    _existing = db.query(
        Transaction.fingerprint, Transaction.external_transaction_id,
        Transaction.account_name, Transaction.amount,
        Transaction.transaction_date, Transaction.description,
    ).filter(Transaction.user_id == current_user).all()
    existing_fps = {r.fingerprint for r in _existing if r.fingerprint}
    existing_fitids = {r.external_transaction_id for r in _existing if r.external_transaction_id}
    # fuzzy index: (account_name, rounded amount) -> list of (date, lower desc)
    fuzzy_index = _defaultdict(list)
    for r in _existing:
        if r.transaction_date is not None and r.amount is not None:
            fuzzy_index[(r.account_name, round(float(r.amount), 2))].append(
                (r.transaction_date, (r.description or "").lower().strip())
            )

    for t in transactions:
        if t.get("is_pending"):
            pending_skipped += 1
            continue

        # FITID deduplication for OFX files — check external_transaction_id first
        fitid = t.get("external_transaction_id", "").strip()
        if fitid and len(fitid) > 5:
            if fitid in existing_fitids:
                print(f"[DEDUP] SKIP-FITID   {(t.get('description') or '')[:30]}")
                skipped += 1
                skipped_merchants.append(t.get('description','')[:20])
                continue

        # Account-aware: label this transaction's account and recompute its
        # fingerprint to include the account (overrides the parser's bank-only one).
        from app.services.classifier import generate_fingerprint as _genfp
        _acct = _account_label(file.filename, detected_bank)
        t["account_name"] = _acct
        t["fingerprint"] = _genfp(
            detected_bank,
            str(t.get("transaction_date", "")),
            t.get("amount", 0) or 0,
            t.get("description", "") or "",
            ext_id=t.get("external_transaction_id", "") or "",
            account=_acct,
        )
        fp = t.get("fingerprint")
        if fp:
            if fp in existing_fps:
                print(f"[DEDUP] SKIP-FP      {(t.get('description') or '')[:30]}  fp={fp[:8]}  acct={t.get('account_name')}")
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
                desc_key = t["description"].lower().strip()
                _candidates = fuzzy_index.get((t.get("account_name"), round(float(amount), 2)), [])
                _matched_cand = next(((cd, cx) for cd, cx in _candidates
                                      if (date_min <= cd <= date_max) and cx == desc_key), None)
                fuzzy_match = _matched_cand is not None
                if fuzzy_match:
                    print(f"[DEDUP] SKIP-FUZZY   {(t.get('description') or '')[:30]}  amt={amount}  matched={_matched_cand}")
                    skipped += 1
                    skipped_merchants.append(t.get('description','')[:20] + ' (fuzzy)')
                    continue

        try:
            date = datetime.strptime(t["transaction_date"], "%Y-%m-%d").date() if t.get("transaction_date") else None
        except:
            date = None

        print(f"[DEDUP] SAVE         {(t.get('description') or '')[:30]}  fp={(t.get('fingerprint') or '')[:8]}  acct={t.get('account_name')}")
        cat_name = t.get("category", "Other")

        tx = Transaction(
            user_id=current_user,
            uploaded_file_id=upload_rec.id,
            account_id=account_id,
            account_name=t.get("account_name"),
            fingerprint=fp,
            transaction_date=date,
            amount=t.get("amount"),
            currency=t.get("currency", "USD"),
            description=t.get("description", ""),
            bank_source=detected_bank,
            transaction_type=t.get("transaction_type", "unknown"),
            category=cat_name,
            classification_confidence=t.get("classification_confidence", "low"),
            needs_review=t.get("needs_review", False),
            is_pending=False,
            is_edited=False,
            import_source=t.get("import_source", "unknown"),
        )
        try:
            db.add(tx)
            db.flush()  # flush individually to catch duplicates
            saved.append(tx_to_dict(tx))
            # Keep in-memory dedup structures current so duplicates WITHIN this
            # same upload are still caught (the preloaded sets only had pre-upload data).
            if fp:
                existing_fps.add(fp)
            if date is not None and t.get("amount") is not None:
                fuzzy_index[(t.get("account_name"), round(float(t["amount"]), 2))].append(
                    (date, (t.get("description") or "").lower().strip())
                )
            if t.get("needs_review"):
                review_count += 1
        except Exception as dup_err:
            db.rollback()
            # Real duplicates (unique fingerprint) are expected; log anything else
            # loudly instead of silently counting it as a dupe (that hid a real bug).
            _emsg = str(dup_err)
            if 'fingerprint' in _emsg.lower() or 'unique' in _emsg.lower():
                skipped += 1
            else:
                print(f"[INSERT-FAIL] {(t.get('description') or '')[:30]}: {_emsg[:200]}")
                skipped += 1
            continue

    db.commit()
    print(f"TIMING: dedup+insert took {_time.time()-_t0:.2f}s for {len(saved)} saved")
    _t1 = _time.time()

    # ── Auto-classify fixed vs variable ──
    # Classifier reads all transactions for context (recurrence detection needs history),
    # but we only WRITE results for newly-added transactions in this upload to avoid
    # N+1 UPDATE queries across the whole DB on every upload.
    try:
        saved_ids = {s.get("id") for s in saved if s.get("id")}
        all_txs_for_classification = [tx_to_dict(t) for t in db.query(Transaction).filter(Transaction.user_id == current_user).all()]
        merchant_rules_rows = db.execute(
            __import__("sqlalchemy").text("SELECT merchant_keyword, is_fixed FROM merchant_rules WHERE user_confirmed = 1 AND user_id = :u"),
            {"u": current_user}
        ).fetchall()
        merchant_rules = {row[0]: bool(row[1]) for row in merchant_rules_rows}

        classifications = classify_all_transactions(all_txs_for_classification, merchant_rules)
        new_classifications = [c for c in classifications if c.get("id") in saved_ids]
        # Bulk update in ONE round-trip instead of N per-row UPDATEs.
        _bulk = [
            {
                "id": c["id"],
                "is_fixed": bool(c["is_fixed"]),
                "fixed_confidence": c["confidence"],
                "fixed_source": c["source"],
            }
            for c in new_classifications if c.get("id")
        ]
        if _bulk:
            # `id` IS the primary key, so map on it directly (no lookup needed).
            db.bulk_update_mappings(Transaction, _bulk)
        db.commit()
        print(f"CLASSIFIED: {len(new_classifications)} new transactions (of {len(classifications)} considered)")
        print(f"TIMING: classify took {_time.time()-_t1:.2f}s")
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
            WHERE transaction_type = 'expense'
            AND amount < 0
            AND LOWER(description) LIKE :key
            AND exclusion_reason IS NULL
            AND user_id = :u
            LIMIT 1
        '''), {'key': f'%{merchant_key}%', 'u': current_user}).fetchone()
        if matching:
            net = round(abs(matching[1]) - credit['amount'], 2)
            if net <= 0:
                db.execute(_sa_null.text('''
                    UPDATE transactions SET
                    transaction_type = 'excluded',
                    exclusion_reason = 'credit_covered'
                    WHERE id = :id AND user_id = :u
                '''), {'id': matching[0], 'u': current_user})
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
        "uploaded_file_id": upload_rec.id,
        "transactions": saved,
    }

# ── Uploaded files history ──

@router.get("/uploads")
def get_uploads(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    files = db.query(UploadedFileModel).filter(UploadedFileModel.user_id == current_user).order_by(UploadedFileModel.uploaded_at.desc()).all()
    return [{
        "id": f.id,
        "file_name": f.file_name,
        "file_type": f.file_type,
        "bank_name": f.bank_name,
        "status": f.upload_status,
        "transactions_extracted": f.transactions_extracted,
        "duplicates_skipped": f.duplicates_skipped,
        "uploaded_at": str(f.uploaded_at),
        "parse_confidence": f.parse_confidence,
    } for f in files]

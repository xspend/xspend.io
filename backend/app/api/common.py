"""Shared helpers used by more than one router (upload, transactions, fixed_expenses)."""
from app.models import Transaction
from app.services.fixed_classifier import display_merchant


def tx_to_dict(t: Transaction) -> dict:
    # The response shape is kept stable for the frontend, but every field is now
    # sourced from a single canonical column (the redundant shadow columns were
    # dropped). `original_description`/`review_status` are derived, not stored.
    desc = t.description or ""
    return {
        "id": t.id,
        "transaction_date": str(t.transaction_date) if t.transaction_date else None,
        "date": str(t.transaction_date) if t.transaction_date else None,
        "description": t.description,
        "merchant": (display_merchant(desc) or desc),
        "original_description": t.description,
        "amount": t.amount,
        "currency": t.currency or "USD",
        "category": t.category,
        "transaction_type": t.transaction_type,
        "classification_confidence": t.classification_confidence,
        "needs_review": t.needs_review,
        "review_status": "needs_review" if t.needs_review else "reviewed",
        "exclusion_reason": t.exclusion_reason,
        "is_pending": t.is_pending,
        "bank_source": t.bank_source,
        "account_id": t.account_id,
        "project_id": t.project_id,
        "uploaded_file_id": t.uploaded_file_id,
        "import_source": t.import_source,
        "is_edited": bool(t.is_edited),
        "notes": t.notes,
        "fingerprint": t.fingerprint,
        "is_fixed": bool(t.is_fixed) if t.is_fixed is not None else False,
        "fixed_confidence": t.fixed_confidence or 0.0,
        "fixed_source": t.fixed_source or "auto",
    }

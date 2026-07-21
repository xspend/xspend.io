"""Deduplication fingerprint behavior — the correctness backbone of uploads."""
import pytest

from app.services.classifier import generate_fingerprint


def test_fingerprint_is_deterministic():
    a = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS #123")
    b = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS #123")
    assert a == b


def test_fingerprint_stable_across_description_phrasing():
    # Same real transaction, parser phrased the merchant differently → same fp.
    a = generate_fingerprint("chase", "2026-03-01", -12.50, "SQ *STARBUCKS 123")
    b = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS 123")
    assert a == b


def test_fingerprint_differs_on_amount():
    a = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS")
    b = generate_fingerprint("chase", "2026-03-01", -99.99, "STARBUCKS")
    assert a != b


def test_fingerprint_differs_on_date():
    a = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS")
    b = generate_fingerprint("chase", "2026-03-02", -12.50, "STARBUCKS")
    assert a != b


def test_external_id_takes_precedence():
    # When a stable FITID exists, date/amount/description are irrelevant.
    a = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS", ext_id="FIT-1", account="x")
    b = generate_fingerprint("chase", "2099-01-01", -1.00, "SOMETHING ELSE", ext_id="FIT-1", account="x")
    assert a == b


def test_dedup_is_per_user_not_global(db):
    """Two different users may legitimately hold the identical transaction; the
    unique constraint is (fingerprint, user_id), so both rows must persist."""
    from app.models import Transaction
    fp = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS")
    db.add(Transaction(id=1, user_id=1, fingerprint=fp, amount=-12.50, description="STARBUCKS"))
    db.add(Transaction(id=2, user_id=2, fingerprint=fp, amount=-12.50, description="STARBUCKS"))
    db.commit()
    assert db.query(Transaction).filter(Transaction.fingerprint == fp).count() == 2


def test_dedup_blocks_same_user_duplicate(db):
    from sqlalchemy.exc import IntegrityError
    from app.models import Transaction
    fp = generate_fingerprint("chase", "2026-03-01", -12.50, "STARBUCKS")
    db.add(Transaction(id=1, user_id=1, fingerprint=fp, amount=-12.50, description="STARBUCKS"))
    db.commit()
    db.add(Transaction(id=2, user_id=1, fingerprint=fp, amount=-12.50, description="STARBUCKS"))
    with pytest.raises(IntegrityError):
        db.commit()

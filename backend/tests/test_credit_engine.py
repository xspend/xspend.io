"""Credit engine: classification + multi-user isolation (the deferred bug we fixed)."""
from datetime import date

from sqlalchemy import text

from app.services.credit_engine import classify_credit, run_credit_matching, get_net_category_spend
from app.models import Transaction


def test_classify_credit_shape():
    result = classify_credit("STATEMENT CREDIT - UBER")
    assert set(["credit_type", "eligible_for_matching", "target_category"]).issubset(result)
    assert isinstance(result["eligible_for_matching"], bool)


def test_classify_credit_handles_empty():
    result = classify_credit("")
    assert result["credit_type"] == "unknown"


def test_run_credit_matching_is_user_scoped(db):
    # user 1 and user 2 each have a card credit. Matching for user 1 must never
    # touch user 2's rows.
    db.add(Transaction(id=1, user_id=1, transaction_type="card_credit",
                       amount=30.0, description="STATEMENT CREDIT - UBER", transaction_date=date(2026, 3, 2)))
    db.add(Transaction(id=2, user_id=2, transaction_type="card_credit",
                       amount=40.0, description="STATEMENT CREDIT - LYFT", transaction_date=date(2026, 3, 3)))
    db.commit()

    run_credit_matching(db, user_id=1)

    rows = db.execute(text("SELECT user_id, credit_transaction_id FROM credit_offsets")).fetchall()
    assert rows, "expected offsets to be written for user 1"
    assert all(r[0] == 1 for r in rows)          # never wrote a user-2 offset
    assert all(r[1] == 1 for r in rows)          # only user 1's credit (id=1) was processed


def test_run_credit_matching_only_deactivates_own_offsets(db):
    # A pre-existing active offset for user 2 must survive a user-1 matching run.
    db.add(Transaction(id=99, user_id=2, transaction_type="card_credit",
                       amount=5.0, description="OLD CREDIT", transaction_date=date(2026, 3, 1)))
    db.commit()
    db.execute(text(
        "INSERT INTO credit_offsets (user_id, credit_transaction_id, applied_amount, is_active, statement_period) "
        "VALUES (2, 99, 5.0, 1, '2026-03')"
    ))
    db.add(Transaction(id=1, user_id=1, transaction_type="card_credit",
                       amount=30.0, description="STATEMENT CREDIT - UBER", transaction_date=date(2026, 3, 2)))
    db.commit()

    run_credit_matching(db, user_id=1)

    still_active = db.execute(text(
        "SELECT is_active FROM credit_offsets WHERE user_id = 2 AND credit_transaction_id = 99"
    )).fetchone()
    assert still_active[0] == 1     # user 2's offset was NOT deactivated by user 1's run


def test_get_net_category_spend_is_user_scoped(db):
    db.add(Transaction(id=1, user_id=1, transaction_type="expense",
                       amount=-100.0, category="Dining", transaction_date=date(2026, 3, 5)))
    db.add(Transaction(id=2, user_id=2, transaction_type="expense",
                       amount=-500.0, category="Dining", transaction_date=date(2026, 3, 6)))
    db.commit()

    net = get_net_category_spend(db, "2026-03", user_id=1)
    assert net["Dining"]["gross_spend"] == 100.0     # user 2's 500 excluded

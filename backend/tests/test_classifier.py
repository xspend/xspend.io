"""Classifier: normalization, exclusion rules, and categorization."""
import pytest

from app.services.classifier import (
    normalize_description,
    should_exclude_from_spending,
    classify_transaction,
    classify_with_meta,
)


@pytest.mark.parametrize("raw,expected", [
    ("STARBUCKS", "starbucks"),
    ("A   B", "a b"),                 # whitespace collapsed
    ("", ""),
    (None, ""),
])
def test_normalize_basic(raw, expected):
    assert normalize_description(raw) == expected


def test_normalize_strips_processor_prefix():
    # "SQ *" is a Square payment-processor prefix, not part of the merchant.
    out = normalize_description("SQ *STARBUCKS 123")
    assert not out.startswith("sq")
    assert "starbucks" in out


@pytest.mark.parametrize("ttype", [
    "income", "transfer", "credit_card_payment",
    "card_credit", "refund", "excluded", "reimbursement", "cash",
])
def test_excluded_types(ttype):
    assert should_exclude_from_spending(ttype) is True


@pytest.mark.parametrize("ttype", ["expense", "unknown", ""])
def test_non_excluded_types(ttype):
    assert should_exclude_from_spending(ttype) is False


def test_classify_returns_four_tuple():
    result = classify_transaction("WHOLE FOODS MARKET", -42.00)
    assert isinstance(result, tuple) and len(result) == 4
    ttype, category, confidence, needs_review = result
    assert isinstance(ttype, str) and ttype
    assert isinstance(category, str) and category
    assert confidence in {"low", "medium", "high"}
    assert isinstance(needs_review, bool)


def test_zero_amount_is_excluded_summary_row():
    # amount == 0 is treated as a summary/non-transaction row.
    (ttype, category, _, _), _meta = classify_with_meta("BEGINNING BALANCE", 0.0)
    assert ttype == "excluded"


def test_user_rule_overrides_category():
    rules = [{
        "id": 1, "user_id": "u1", "match_field": "merchant",
        "match_value": "starbucks", "match_type": "contains",
        "category": "Coffee", "transaction_type": "expense",
        "is_active": True, "priority": 10, "confidence_override": 0.9,
    }]
    (ttype, category, confidence, needs_review), meta = classify_with_meta(
        "STARBUCKS STORE 123", -5.0, user_rules=rules, user_id="u1"
    )
    assert category == "Coffee"
    assert ttype == "expense"
    assert meta["matched_rule_scope"] == "user"


def test_classify_transaction_matches_with_meta():
    args = ("UBER TRIP", -18.30)
    assert classify_transaction(*args) == classify_with_meta(*args)[0]

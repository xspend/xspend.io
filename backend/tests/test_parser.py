"""Parser primitives: date, amount, and CSV parsing."""
import pytest

from app.parsers.parser import detect_date, detect_amount, normalize_amount, parse_csv


@pytest.mark.parametrize("raw,expected", [
    ("03/15/2026", "2026-03-15"),
    ("2026-03-15", "2026-03-15"),
    ("3-15-2026", "2026-03-15"),
    ("03/2026", "2026-03-01"),      # partial MM/YYYY -> first of month
    ("2026-03", "2026-03-01"),      # partial YYYY-MM -> first of month
])
def test_detect_date_formats(raw, expected):
    assert detect_date(raw) == expected


@pytest.mark.parametrize("raw", ["", "nan", "None", "not-a-date", None])
def test_detect_date_invalid_returns_none(raw):
    assert detect_date(raw) is None


@pytest.mark.parametrize("raw,expected", [
    ("$1,234.56", 1234.56),
    ("(45.00)", -45.00),           # parentheses = negative
    ("+50", 50.0),
    ("-12.50", -12.50),
    ("garbage", 0.0),              # detect_amount falls back to 0.0
    (None, 0.0),
])
def test_detect_amount(raw, expected):
    assert detect_amount(raw) == expected


@pytest.mark.parametrize("raw,expected", [
    ("$1,234.56", 1234.56),
    ("(45.00)", -45.00),
    ("£10.00", 10.0),
    ("€10.00", 10.0),
])
def test_normalize_amount(raw, expected):
    assert normalize_amount(raw) == expected


def test_normalize_amount_invalid_returns_none():
    assert normalize_amount("garbage") is None
    assert normalize_amount("") is None


def test_parse_csv_basic():
    csv = (
        b"Date,Description,Amount\n"
        b"03/15/2026,STARBUCKS STORE 123,-5.25\n"
        b"03/16/2026,PAYROLL DEPOSIT,2000.00\n"
    )
    rows, bank = parse_csv(csv)
    assert isinstance(rows, list)
    assert len(rows) == 2
    # Each parsed row carries a description and a numeric amount.
    descs = " ".join((r.get("description") or r.get("raw_description") or "") for r in rows).lower()
    assert "starbucks" in descs

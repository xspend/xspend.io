from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime
from sqlalchemy import extract as _extract

from app.db import get_db
from app.auth import get_current_user
from app.models import Transaction
from app.services.fixed_classifier import display_merchant

router = APIRouter()

# ── Dashboard Summary (tier-aware) ──────────────────────────────────────────
# Contract: frontend consumes data_tier, comparison, trend_chart.
# Reason enum: not_enough_months | no_previous_month | prev_month_incomplete
#              | zero_baseline | stale_data

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

def _months_with_data(db: Session, user_id: str = None) -> list:
    q = db.query(
        _extract('year', Transaction.transaction_date).label('y'),
        _extract('month', Transaction.transaction_date).label('m'),
    ).filter(
        Transaction.transaction_date.isnot(None),
    )
    if user_id is not None:
        q = q.filter(Transaction.user_id == user_id)
    rows = q.distinct().order_by('y', 'm').all()
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


def _month_totals(db: Session, ym: str, user_id: str = None) -> dict:
    year, month = int(ym[:4]), int(ym[5:7])
    _q = db.query(Transaction).filter(
        _extract('year', Transaction.transaction_date) == year,
        _extract('month', Transaction.transaction_date) == month,
        Transaction.transaction_type == 'expense',
        Transaction.amount < 0,
        Transaction.exclusion_reason.is_(None),
    )
    if user_id is not None:
        _q = _q.filter(Transaction.user_id == user_id)
    rows = _q.all()
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

def _build_trend_chart(db: Session, months_available: list, tier: int, current_ym: str, user_id: str = None) -> dict:
    if tier == 1:
        return {"show": False, "reason": "not_enough_months",
                "message": "Upload another month to unlock trends", "months": []}
    idx = months_available.index(current_ym) if current_ym in months_available else len(months_available) - 1
    window = months_available[max(0, idx - 5):idx + 1]
    months = []
    for ym in window:
        t = _month_totals(db, ym, user_id)
        months.append({"label": _month_label_short(ym), "ym": ym,
                       "flexible": t["flexible"], "committed": t["committed"]})
    return {"show": True, "reason": None, "message": None, "months": months}

@router.get("/dashboard-summary")
def get_dashboard_summary(month: Optional[str] = None, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    months_available = _months_with_data(db, current_user)
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
    current = _month_totals(db, current_ym, current_user)
    prev = _month_totals(db, prev_ym, current_user) if prev_exists else None
    tier = 1 if len(months_available) <= 1 else (2 if len(months_available) == 2 else 3)
    return {
        "data_tier": tier,
        "months_available": len(months_available),
        "current_month": current,
        "previous_month": prev,
        "comparison": _build_comparison(current, prev, len(months_available)),
        "trend_chart": _build_trend_chart(db, months_available, tier, current_ym, current_user),
    }

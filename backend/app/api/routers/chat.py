from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional

from app.core.config import settings
from app.db import get_db
from app.core.deps import get_current_user
from app.models import ChatLog, Transaction

router = APIRouter()


class ChatMessage(BaseModel):
    message: str

class ChatPromptRequest(BaseModel):
    prompt_id: str
    month: Optional[str] = None      # "YYYY-MM"
    amount: Optional[float] = None


@router.post("/chat")
def chat(msg: ChatMessage, db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    """Free-text chat is DISABLED for beta.

    It calls the LLM once per message with no cap, so it costs money per use.
    The curated prompts (POST /chat/prompt) are templated, free, and instant.
    Re-enable this as a paid tier later.
    """
    return {"success": False,
            "error": "Free-form chat isn't available yet — try one of the quick "
                     "insights instead."}


# ── Curated, templated prompts (free, instant, capped) ──

CHAT_PROMPT_LIMIT = settings.XSPEND_CHAT_PROMPT_LIMIT

CHAT_PROMPTS = [
    {"id": "net_cash_flow",
     "label": "What was my net cash flow?",
     "needs": ["month"]},
    {"id": "purchase_affordability",
     "label": "I want to buy something — where can I make room?",
     "needs": ["month", "amount"]},
    {"id": "lifestyle_creep",
     "label": "Where is my spending creeping up?",
     "needs": []},
    {"id": "subscription_scan",
     "label": "Any duplicate charges or price rises?",
     "needs": []},
    {"id": "spending_velocity",
     "label": "How does my spending pace through the month?",
     "needs": ["month"]},
]


def _chat_used_this_month(db, user_id):
    import sqlalchemy as _sa
    from datetime import date as _date
    first = _date.today().replace(day=1)
    return db.query(ChatLog).filter(
        ChatLog.user_id == user_id,
        ChatLog.created_at >= first,
    ).count()


def _chat_tx_list(db, user_id):
    txs = db.query(Transaction).filter(
        Transaction.user_id == user_id, Transaction.is_pending == False
    ).all()
    return [{"date": str(t.transaction_date), "description": t.description,
             "amount": t.amount, "currency": t.currency, "category": t.category,
             "transaction_type": t.transaction_type, "bank_source": t.bank_source}
            for t in txs]


@router.get("/chat/options")
def chat_options(db: Session = Depends(get_db), current_user: int = Depends(get_current_user)):
    """Everything the chat UI needs in one call."""
    from app.services.ai_chat import months_with_data
    tx_list = _chat_tx_list(db, current_user)
    used = _chat_used_this_month(db, current_user)
    months = [{"value": ym, "count": n} for ym, n in months_with_data(tx_list)]
    return {"prompts": CHAT_PROMPTS, "months": months,
            "used": used, "limit": CHAT_PROMPT_LIMIT}


@router.post("/chat/prompt")
def chat_prompt(data: ChatPromptRequest, db: Session = Depends(get_db),
                current_user: int = Depends(get_current_user)):
    from app.services.ai_chat import prompt_dispatch

    used = _chat_used_this_month(db, current_user)
    if used >= CHAT_PROMPT_LIMIT:
        return {"success": False, "capped": True, "used": used, "limit": CHAT_PROMPT_LIMIT,
                "error": f"You've used all {CHAT_PROMPT_LIMIT} insights this month. "
                         f"They reset at the start of next month."}

    valid = {p["id"] for p in CHAT_PROMPTS}
    if data.prompt_id not in valid:
        return {"success": False, "error": "Unknown prompt."}

    tx_list = _chat_tx_list(db, current_user)
    result = prompt_dispatch(data.prompt_id, tx_list, month=data.month, amount=data.amount)

    # If the handler needs more input (e.g. an amount), don't spend a prompt.
    if result.get("needs_input"):
        return {"success": True, "needs_input": result["needs_input"],
                "answer": result.get("answer", ""), "used": used, "limit": CHAT_PROMPT_LIMIT}

    db.add(ChatLog(user_id=current_user, prompt_id=data.prompt_id))
    db.commit()

    return {"success": True,
            "answer": result.get("answer", ""),
            "disclaimer": result.get("disclaimer", ""),
            "used": used + 1, "limit": CHAT_PROMPT_LIMIT}

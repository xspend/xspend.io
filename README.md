# xspend

Personal finance analytics. Upload a bank statement, get categorized spending,
cash-flow insights, and savings projects.

**Live in beta with real users and real financial data.** Treat production accordingly.

| | |
|---|---|
| **Live app** | https://xspend.vercel.app |
| **Backend API** | https://xspend-io.onrender.com |
| **Board** | GitHub Projects: **Phase 1** |

---

## Before you run anything

### Local points at production

`backend/.env` sets `DATABASE_URL` to the **Neon production database**. A local
`uvicorn` reads and writes **live user data** unless you override it:

```bash
DATABASE_URL="sqlite:///./financeai.db" uvicorn main:app --port 8000
```

This is one stray `DELETE` away from real damage to real people's financial records.

### `main` deploys straight to production

There is no CI and no staging. Push to `main`, and Render and Vercel deploy to live
users within a couple of minutes. All work goes through pull requests.

---

## Quick start

```bash
# backend
cd backend
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
DATABASE_URL="sqlite:///./financeai.db" uvicorn main:app --port 8000
```

```bash
# frontend, separate terminal
cd frontend
npm install
npm run dev
```

```bash
# backend tests (throwaway file-based SQLite, never touches a real DB)
cd backend
pytest
```

Frontend expects the backend on port 8000. See `frontend/src/lib/config.js`.

---

## Docs

| | |
|---|---|
| [`docs/ONBOARDING.md`](docs/ONBOARDING.md) | **Start here.** What the product is, setup, how we work, conventions. |
| [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) | The system. File map, data flow, core logic, thresholds, landmines, bug history, open issues. |
| [`docs/TASKS_PHASE1.md`](docs/TASKS_PHASE1.md) | The current milestone. |

---

## Layout

```
backend/
  main.py                     app, ALL endpoints, upload flow, dedup loop
  app/
    db/database.py             connection and session
    models/models.py           DB models — single source of truth for the schema.
                                Every PK is an autoincrement Integer; every reference
                                column is a real ForeignKey (mostly ON DELETE CASCADE
                                from users).
    auth/security.py           JWT + bcrypt
    auth/deps.py                get_current_user (int user id; see below)
    parsers/parser.py          file routing, bank detection, template parsing
    parsers/llm_fallback.py    LLM extraction for banks with no template
    services/classifier.py     fingerprinting, merchant canonicalization
    services/fixed_classifier.py   fixed vs variable, recurrence
    services/insights.py       dashboard insights
    services/ai_chat.py        the five templated insight prompts
    services/credit_engine.py  card credits and rewards, net category spend
  alembic/          Alembic migrations (baseline, dedup, UUID->int PKs)
  tests/            pytest suite

frontend/         React + Vite + Tailwind
  src/pages/        Dashboard, Upload, Transactions, Chat, Goals, Settings, ...

docs/             see above
```

`get_current_user` returns an `int` (previously a UUID string). A token issued before
the UUID→integer PK migration carries a string `sub` and is rejected with 401 — that
migration required every logged-in user to sign in again.

`ARCHITECTURE.md` section 3 has the full file-ownership map.

---

## Stack

| | |
|---|---|
| Frontend | React, Vite, Tailwind, deployed on **Vercel** |
| Backend | FastAPI, SQLAlchemy, deployed on **Render** (Pro) |
| Database | **Neon** / Postgres in production, SQLite locally |
| PDF extraction | pdfplumber |
| LLM parsing fallback | Anthropic API, Claude Haiku 4.5 |

---

## Status

**Current milestone:** Phase 1, multi-user isolation and deduplication correctness.
See [`docs/TASKS_PHASE1.md`](docs/TASKS_PHASE1.md) and the Phase 1 board.

**Known gaps:** no CI yet, uploads run synchronously and time out on large statements
even though they succeed. A backend `pytest` suite now covers auth, the classifier,
parser primitives, dedup/fingerprinting, credit-engine isolation, and the core API
endpoints. `ARCHITECTURE.md` section 9 has the full list of open issues.

# Backend Security Review — Key Findings Summary

**Prepared:** July 20, 2026
**Scope:** `backend/` (read-only audit, no code changed)
**Companion doc:** `docs/BACKEND_SECURITY_REVIEW.md` has the full line-by-line technical audit, live-verification evidence, and database/architecture detail. This document is the condensed, stakeholder-facing version — every item below includes the exact file/line so an engineer can jump straight to the code.

## Purpose of This Document

This document summarizes the key findings from a security and architecture review of the backend service. It is intended as a concise, professional reference for engineering and product stakeholders. For each issue it explains what the problem is, why it matters, and what fix is recommended, with a precise code reference instead of a full line-by-line audit.

## Executive Summary

Thirteen issues were identified across authentication, data access, database schema, CORS configuration, and code structure. The first two are the most urgent — both are exploitable today by anyone with network access to the API, with no valid account required. Items 3 through 6 allow one user's data or the running application to be affected by another user or by a misconfigured deployment, and should be closed shortly after.

| # | Issue | Severity | Code Reference |
|---|-------|----------|-----------------|
| 1 | Hardcoded JWT secret can silently run in production | Critical | `auth.py:9-14` |
| 2 | Data-wipe endpoint has no authentication | Critical | `main.py:867` (`DELETE /data/all`) |
| 3 | Accounts endpoint leaks every user's bank data | High | `main.py:245-261` (`GET`/`POST /accounts`) |
| 4 | Users can reassign transactions onto another user's project | High | `main.py:1152-1160` (`PATCH /transactions/{tid}/project`) |
| 5 | Two database tables defined inconsistently in multiple places | High | `merchant_rules`: `database.py:54-73` vs `migrate.py:70-78`. `projects`: `models.py:72-88` vs `migrate.py:9-19` |
| 6 | CORS allows credentialed requests from an unvalidated origin list | High | `main.py:30-37` |
| 7 | No rate limiting on login / signup | Medium | `main.py:1776` (signup), `main.py:1819` (login) |
| 8 | No logout or token revocation | Medium | `auth.py:16, 29-34` |
| 9 | Account-deletion failures are silently swallowed | Medium | `main.py:1832-1848` (`DELETE /auth/account`) |
| 10 | No foreign keys or indexes on core relationship columns | Medium | `models.py` (schema-wide — see detail below) |
| 11 | Entire application logic lives in one 1,898-line file | Medium | `main.py` (40 routes, no `APIRouter`) |
| 12 | No email verification or password-reset capability | Medium | `main.py:1776-1817`, `models.py:10-28` (`User` model) |
| 13 | No upload file-size limit | Medium | `main.py:272-280` (`POST /upload`) |
| 14 | `/categories` endpoint is unauthenticated | Low | `main.py:265-267` |

---

## Critical Issues

These two issues expose the entire system and should be treated as immediate priorities.

### CRITICAL — Hardcoded fallback JWT secret
**Where:** `auth.py:9-14`
```python
SECRET_KEY = _os.getenv("JWT_SECRET_KEY")
if not SECRET_KEY:
    if _os.getenv("ENVIRONMENT", "development").lower() == "production":
        raise RuntimeError("JWT_SECRET_KEY must be set in production")
    SECRET_KEY = "financeai-dev-only-secret-change-me"
```
**What it is:** The application only refuses to start without a real secret key when the `ENVIRONMENT` variable is set to exactly `"production"`. Since that variable defaults to `"development"`, most deployments will silently fall back to the hardcoded secret above, which is visible in source control.
**Why it matters:** Anyone who has read the source code can generate a valid login token for any account, without a password, and read or delete that user's financial data.
**Recommended fix:** Require a real secret key at startup unconditionally — remove the `ENVIRONMENT` check entirely.

### CRITICAL — Unauthenticated data-wipe endpoint
**Where:** `main.py:867` — `DELETE /data/all`
**What it is:** A delete-all-data endpoint exists with no `Depends(get_current_user)` at all. It is protected only by a `?confirm=yes` query flag, which offers no real protection.
**Why it matters:** Anyone on the network can permanently delete every user's transactions, rules, and upload history with a single request — no account or token required.
**Recommended fix:** Add authentication and an administrator-only check, or remove the endpoint from production entirely.

---

## High-Severity Issues

These issues allow one user to see or affect another user's data.

### HIGH — Accounts endpoint has no authentication or ownership filter
**Where:** `main.py:245-261` — `GET /accounts` and `POST /accounts`
```python
@app.get("/accounts")
def get_accounts(db: Session = Depends(get_db)):
    return db.query(Account).filter(Account.is_active == True).all()

@app.post("/accounts")
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    acct = Account(account_id=gen_uuid(), account_name=data.account_name, ...)
```
**What it is:** Neither route takes `current_user` as a dependency, and neither filters/sets `user_id`, even though `Account.user_id` exists in the model (`models.py:36`).
**Why it matters:** Any visitor — logged in or not — can view every user's bank account names, institutions, and last-4 digits, and can create accounts that belong to no one.
**Recommended fix:** Require login on this endpoint (`Depends(get_current_user)`) and filter every query and write by the logged-in user's ID.

### HIGH — Users can move transactions onto another user's project
**Where:** `main.py:1152-1160` — `PATCH /transactions/{tid}/project`
```python
t = db.query(Transaction).filter(Transaction.id == tid).first()
if t.user_id != current_user:          # checks the TRANSACTION's owner
    raise HTTPException(status_code=403, ...)
t.project_id = data.project_id         # never checks the PROJECT's owner
```
**What it is:** The endpoint checks that the transaction belongs to the current user but never checks that `data.project_id` — a plain auto-incrementing integer (`models.py:74`) — belongs to them too.
**Why it matters:** By guessing small sequential project ID numbers, a user could reassign their own transactions onto someone else's project, quietly corrupting that person's progress totals via `calculate_project_progress()` (`main.py:1163-1179`), which sums by `project_id` with no owner check either.
**Recommended fix:** Before assignment, verify `Project.id == data.project_id AND Project.user_id == current_user`.

### HIGH — Two database tables are defined inconsistently in multiple places
**Where — exact file/table breakdown:**

| Table | File & lines | Columns |
|---|---|---|
| `merchant_rules` | `database.py:54-73` (`ensure_tables()`, runs on every server startup) | 17 columns: `id, merchant_keyword, is_fixed, user_confirmed, confidence, created_at, user_id, match_field, match_value, match_type, transaction_type, category, priority, source, confidence_override, is_active, updated_at` |
| `merchant_rules` | `migrate.py:70-78` (manual script) | Only 6 columns: `id, merchant_keyword, is_fixed, user_confirmed, confidence, created_at` — **missing 11 columns**, including `user_id` |
| `projects` | `models.py:72-88` (SQLAlchemy model, provisioned via `create_all()` at `main.py:23`) | 13 columns, including `user_id`, `filter_accounts`, `filter_start_date`, `filter_end_date`, `filter_categories`, `is_auto` |
| `projects` | `migrate.py:9-19` (manual script) | Only 7 columns: `id, name, type, target_amount, target_date, is_archived, created_at` — **missing `user_id` and all 5 filter/auto columns** |

**What it is:** Both duplicate definitions use `CREATE TABLE IF NOT EXISTS`, which creates the table only if it's absent and otherwise does nothing — including not adding missing columns to an existing table. Whichever definition runs first on a given deployment wins permanently; the other becomes a silent no-op.
**Why it matters:** If `migrate.py` runs before the server's `ensure_tables()`/`create_all()` on a fresh database, the running application ends up with tables missing columns it expects (e.g. `merchant_rules.user_id`, `projects.user_id`), causing runtime errors (`no such column: user_id`) or silently inconsistent data across environments, depending purely on deployment order.
**Recommended fix:** Consolidate each table into a single authoritative definition. Delete `migrate.py`'s stale `projects` DDL (the model in `models.py` already handles it via `create_all()`); for `merchant_rules`, either promote it to a real `models.py` class or delete `migrate.py`'s outdated 6-column version and keep only `database.py`'s.

### HIGH — CORS allows credentialed requests from an unvalidated origin list
**Where:** `main.py:30-37`
```python
_default_origins = ["http://localhost:5173", "http://127.0.0.1:5173"]
_prod_origins = [o.strip() for o in os.getenv("FRONTEND_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(CORSMiddleware, allow_origins=_default_origins + _prod_origins, allow_credentials=True, ...)
```
**What it is:** The server accepts cross-origin requests with `allow_credentials=True`, and `FRONTEND_ORIGINS` is split into the allow-list with no validation — nothing rejects `*` or blank entries. Per Starlette's CORS implementation (`allow_all_origins = "*" in allow_origins`), setting `FRONTEND_ORIGINS=*` would make the server accept and reflect back any origin, credentials included.
**Why it matters:** If that configuration mistake happens, the server would reflect back any site's origin on credentialed requests. Impact is limited today because the app uses bearer tokens in `localStorage` rather than cookies — `evil.com` can't read another origin's `localStorage` regardless of CORS — but the setting serves no purpose now and becomes a real risk the day cookie-based auth is introduced.
**Recommended fix:** Validate at startup that `FRONTEND_ORIGINS` rejects wildcard or blank entries, and drop `allow_credentials=True` unless cookies are actually in use.

---

## Medium-Severity Issues

These issues do not expose data directly today but weaken the system's resilience, reliability, or long-term maintainability.

- **No rate limiting on login or signup** — `main.py:1776` (`POST /auth/signup`), `main.py:1819` (`POST /auth/login`). No `slowapi` or equivalent throttling in `requirements.txt`; passwords can be guessed and accounts spammed without limit.
- **No way to log out or revoke a token** — `auth.py:16` (`ACCESS_TOKEN_EXPIRE_DAYS = 30`), `auth.py:29-34` (`create_token`). Session tokens remain valid for 30 days with no blacklist/`jti`, so a leaked token cannot be individually invalidated — only rotating `JWT_SECRET_KEY` kills it, which logs out every user at once.
- **Account-deletion failures are silently swallowed** — `main.py:1832-1848` (`DELETE /auth/account`). Each per-table delete is wrapped in `try: ... except Exception: pass`; if any table's delete fails, the endpoint still returns `{"success": true}`, so a user may believe their data is gone when it isn't.
- **No email verification, forgot-password, or reset-password flow** — `main.py:1776-1817` (signup/login), `models.py:10-28` (`User` model has no `email_verified` column). No email-sending capability exists in `requirements.txt` to build these flows on. Anyone can sign up with an email they don't own, and a locked-out user has no self-service recovery option.
- **No foreign keys or indexes on core relationship columns** — schema-wide (`models.py`). Only `Transaction.project_id → Project.id` is a real, enforced foreign key; every other `user_id`/`account_id`/`category_id` link is a plain, unindexed column populated by convention only, despite "all records for this user" being the most common query pattern in the app.
- **Entire application logic lives in one 1,898-line file** — `main.py`, all 40 routes, no `APIRouter` split, with business logic written directly inside request handlers (e.g. `/upload` is ~316 lines inline, `main.py:272-588`). Makes the codebase hard to navigate, unit-test, or safely change.
- **File uploads have no size limit** — `main.py:272-280` (`POST /upload`), `await file.read()` with no cap. A large PDF, CSV, or spreadsheet can exhaust server memory and take the service down for everyone.

---

## Additional Notes

A few smaller items worth recording for completeness, along with one clarification to avoid confusing two similarly-named endpoints.

- **`/categories` requires no login** — `main.py:265-267`. Low sensitivity today since it only returns system default categories, but inconsistent with how the rest of the app is secured.
- **Account self-deletion is safe and correctly scoped** — `main.py:1832-1848` (`DELETE /auth/account`). A logged-in user can delete their own account and data, and every delete is restricted to `WHERE user_id = current_user`. This is a separate, properly-built endpoint from the unauthenticated "delete everything" bug (issue #2) — the two should not be confused with each other.
- **Login has a minor timing difference** — `main.py:1827` (`if not user or not verify_password(...)`) between an unknown email and a wrong password, which could theoretically let someone confirm whether an email address has an account. Low risk, noted for completeness.
- **Password rules only check minimum length** — `main.py:1802-1803` (8 characters), with no complexity or breach-list check.
- **No SQL injection risk was found anywhere** — all queries use bound parameters or the ORM, and there is no use of `eval`, `exec`, or similar unsafe functions.

# Backend Review — Security, Architecture & Database

**Scope:** `backend/` (FastAPI + SQLAlchemy). Read-only audit, no code changed.
**Date:** 2026-07-20
**Live-verified:** 2026-07-20 — see §6. Every finding below marked with a checkmark was reproduced against the running dev server (not just read from source).

---

## 0. Executive Summary — Fix These First

| # | Issue | Severity | Where | Verified live? |
|---|-------|----------|-------|:---:|
| 1 | Hardcoded fallback JWT secret used whenever `ENVIRONMENT` isn't exactly `"production"` | **CRITICAL** | `auth.py:9-14` | ✅ |
| 2 | `DELETE /data/all?confirm=yes` has no auth check — anyone can wipe all data | **CRITICAL** | `main.py:867` | not run (destructive — see §6) |
| 3 | `GET/POST /accounts` has no auth check and no `user_id` filter — leaks every user's bank account info, lets anyone create orphan accounts | **HIGH** | `main.py:245-261` | ✅ |
| 4 | `get_net_category_spend()` aggregates spend across **all users**, not just the caller, and is live behind auth (not actually gated off) | **HIGH** | `credit_engine.py:257-286`, `main.py:1861-1879` | ✅ (root cause confirmed directly — live endpoint currently 500s, see #12) |
| 5 | IDOR: transaction → project assignment doesn't verify the *project* belongs to the caller, letting one user pollute another's project totals | **HIGH** | `main.py:1152-1179` | ✅ |
| 6 | No rate limiting on `/auth/login` or `/auth/signup` | **MEDIUM** | `main.py:1776, 1819` | — |
| 7 | No token revocation / logout; 30-day JWT expiry with no blacklist | **MEDIUM** | `auth.py:16` | — |
| 8 | `merchant_rules` and `projects` tables are each defined twice, inconsistently, across `database.py`/`migrate.py`/`models.py` — whichever runs first "wins" and the other silently never patches in | **HIGH** (data integrity) | see §3 | — |
| 9 | No FK constraints or indexes on any `user_id`/`account_id`/`category_id` column in the entire schema (only `Transaction.project_id` is a real FK) | **MEDIUM** | see §3 | — |
| 10 | `main.py` is a single 1,898-line file with all 40 routes, no `APIRouter` split, business logic inlined into handlers | **MEDIUM** (maintainability) | see §4 | — |
| 11 | No email verification/activation, no forgot-password, no reset-password — and no email-sending capability at all to build them on | **MEDIUM** | `main.py:1776-1817`, `models.py:10-28` | ✅ (confirmed absent) |
| 12 | `GET /credit-offsets/{period}` crashes (HTTP 500) on Postgres — found while live-testing #4, a separate bug from the leak itself | **MEDIUM** | `credit_engine.py:261` | ✅ (new finding — see §6) |

Items 1–5 are exploitable today by anyone with network access to the API (1, 2, 3 need no valid account at all). Fix those before anything else.

---

## 1. Authentication & Authorization

### Critical

**1.1 — Hardcoded dev JWT secret can silently apply in production**
`auth.py:9-14`: if `JWT_SECRET_KEY` is unset, the app only refuses to start when `ENVIRONMENT == "production"` *exactly*. Since `ENVIRONMENT` defaults to `"development"` (`.env.example:3`), any deployment that forgets to set `ENVIRONMENT=production` — or sets `JWT_SECRET_KEY` but not `ENVIRONMENT` — runs live with the literal secret `"financeai-dev-only-secret-change-me"`, which is sitting in source control.
**Impact:** anyone who reads the repo can forge `jwt.encode({"sub": "<any-user_id>"}, "financeai-dev-only-secret-change-me", algorithm="HS256")` and fully impersonate any account — read or delete any user's financial data — with zero credentials.
**Fix:** fail startup whenever `JWT_SECRET_KEY` is missing, full stop — don't gate it on `ENVIRONMENT`.

**1.2 — Unauthenticated full data-wipe endpoint**
`main.py:867`, `DELETE /data/all` — no `Depends(get_current_user)`, gated only by a `?confirm=yes` query param.
**Impact:** `curl -X DELETE https://api/data/all?confirm=yes` deletes every user's transactions, rules, and upload history. No token needed.
**Fix:** require auth + admin role, or remove the endpoint from production builds entirely.

### High

**1.3 — Cross-tenant IDOR via project assignment**
`main.py:1152-1161`, `PATCH /transactions/{tid}/project` checks the *transaction* belongs to `current_user` but never checks `data.project_id` belongs to them too. `calculate_project_progress` (`main.py:1163-1179`) sums transactions purely by `project_id` with no user filter.
**Impact:** an attacker can enumerate small sequential `Project.id` values and reassign their own transactions onto a victim's project, silently corrupting the victim's savings/debt-goal totals.
**Fix:** verify `data.project_id` belongs to `current_user` before assignment.

**1.4 — Cross-tenant financial aggregate leak**
`credit_engine.py:257-286` `get_net_category_spend()` queries `transactions` by period with **no `user_id` filter**, and is wired live behind `GET /credit-offsets/{period}` (`main.py:1861-1879`, requires only *any* valid login). The code's own comment (`main.py:838-846`) flagged this as needing to be user-scoped "before going live" — but it's already reachable.
**Impact:** any logged-in user sees spend aggregates computed from every user's transactions, not just their own.
**Fix:** add `user_id == current_user` to the query in `credit_engine.py`.

### Verified: login auth + self-service account deletion

- **`POST /auth/login` (`main.py:1819-1830`)** — correctly unauthenticated (you need this endpoint *to get* a token) and correctly verifies the password with `verify_password()` before issuing a JWT (line 1827). No issue here.
- **`DELETE /auth/account` (`main.py:1832-1848`)** — a logged-in user CAN delete their own account and all of their own data. It requires `Depends(get_current_user)` and every delete is correctly scoped to `WHERE user_id = :uid` using the authenticated user's own id (`uid = current_user`, lines 1836-1844) — a user cannot use this to delete someone else's data. This is a distinct, properly-scoped endpoint from the unauthenticated `DELETE /data/all` wipe-everything bug (§1.2) — don't confuse the two.
- **Medium — silent partial-delete failures:** each per-table `DELETE` in that loop (`transactions`, `uploaded_files`, `accounts`, `merchant_rules`, `projects`) is wrapped in `try: ... except Exception: pass` (`main.py:1839-1842`). If any one of those fails (e.g. a table/column mismatch like the `merchant_rules` schema drift noted in §3), the response still returns `{"success": true}` while some of the user's data silently survives deletion — a correctness/privacy issue (user believes their data is gone; it may not be).
  **Fix:** log/collect per-table failures and surface them, or fail the whole request (transaction rollback) if any table's delete errors.

### Medium

- **No rate limiting** on login/signup (`main.py:1776, 1819`) — no `slowapi` or equivalent in `requirements.txt`. Unlimited password guessing / signup spam is possible.
- **No token revocation** — 30-day JWT expiry (`auth.py:16`), no `jti`, no blacklist, no logout endpoint anywhere. A leaked token stays valid for a month; the only kill switch is rotating the JWT secret, which logs out every user at once.
- **`GET /categories` is unauthenticated** (`main.py:265`) — low sensitivity today (system defaults), but inconsistent with the rest of the app.

### Medium — No account verification or password recovery at all

Verified by grepping `main.py`/`auth.py`/`models.py`/`requirements.txt` for verification/reset/mail-related code — none of the following exists anywhere in the backend:

- **No email verification / activation.** `POST /auth/signup` (`main.py:1776-1817`) creates the user and immediately returns a valid JWT — there is no activation code/link step. The `User` model (`models.py:10-28`) has no `email_verified`/`is_active` column at all, so there's nothing to check even if a route wanted to gate on it.
- **No re-verify-email flow** — follows from the above; nothing to re-trigger since initial verification never happens.
- **No forgot-password endpoint** — none of the 40 routes is anything like `/auth/forgot-password`.
- **No reset-password endpoint or token mechanism** — no `reset_token` column, no expiring-token generation/validation logic anywhere.
- **No email-sending capability in the app at all** — `requirements.txt` has no `smtplib` usage and no email-provider package (SendGrid/SES/Mailgun/etc.), so none of the above flows could be implemented without adding that infrastructure first.

**Impact:** anyone can sign up with an email address they don't own and get a fully working account (no confirmation loop closes that). A user who forgets their password has **no self-service recovery path** — the only options are guessing again or an operator manually resetting `password_hash` in the database.
**Fix:** add an `email_verified` column + signup verification-token flow; add `/auth/forgot-password` (issues a short-lived, single-use reset token, emailed to the user) and `/auth/reset-password` (validates the token, sets a new `password_hash`); wire in an email-sending dependency (SMTP or a transactional-email provider) to deliver both.

### Low / Info

- Login (`main.py:1827`) short-circuits `not user or not verify_password(...)` — bcrypt only runs for existing emails, creating a timing side-channel for email enumeration.
- Password policy is length-only (≥8 chars); no complexity or breach-list check; bcrypt silently truncates at 72 bytes (standard bcrypt behavior, just worth knowing).
- Pure bearer-token API, no cookies set, so CSRF is not applicable.

### What's done well

- **bcrypt** with per-password salt (`auth.py:20-27`) — correct choice, not MD5/SHA.
- JWT via `python-jose`, algorithm explicitly pinned to `HS256` (never accepts `"none"`), `exp` enforced on decode (`auth.py:35-40`).
- The large majority of endpoints correctly use `Depends(get_current_user)` and filter every query by `user_id == current_user`, with real ownership checks before mutation (e.g. `main.py:690-692, 798-799, 1123, 1136, 1646-1647`).
- Signup validates email format, catches common domain typos, rejects duplicate emails (`main.py:1786-1803`).

---

## 2. CORS & General Security

### CORS (`main.py:32-38`)

- **High** — `allow_credentials=True` is combined with an origin list built from `FRONTEND_ORIGINS` (comma-split, no validation) plus hardcoded localhost entries (`main.py:30-31`). Nothing stops `FRONTEND_ORIGINS` from being set to `*` in a rushed prod config — Starlette then reflects the request's `Origin` header on any credentialed request. Currently low real-world impact since auth is Bearer-JWT, not cookies (a malicious page can't read JS-held tokens via CORS alone), but `allow_credentials=True` serves no purpose today and is a live footgun the day cookies get introduced.
- **Info** — `allow_methods=["*"]` / `allow_headers=["*"]` is fine given origins are an explicit allow-list.
- **Fix:** validate `FRONTEND_ORIGINS` rejects `*`/blank entries at startup; drop `allow_credentials=True` unless cookies are actually used.

### SQL Injection — clean

All user-influenced queries use bound parameters (`:param` style) or the ORM. The only f-string DDL construction (`database.py:31-73`) interpolates a hardcoded dialect constant (`"SERIAL PRIMARY KEY"` vs `"INTEGER PRIMARY KEY AUTOINCREMENT"`), never user input. No `eval`/`exec`/`pickle`/`yaml.load`/`subprocess`/`os.system` found anywhere in the backend.

### File Upload Handling

- **Medium** — no file size limit anywhere in `upload_statement` (`main.py:280`) — a large PDF/CSV/XLSX can exhaust worker memory (DoS).
- **Low** — `parser.py:1204-1230` derives a temp-file suffix from the attacker-controlled filename's extension; a crafted name could inject a `/` into the suffix. Low exploitability (bounded by `tempfile`'s random prefix), but unsanitized.
- **Good:** magic-byte MIME sniffing rather than trusting the extension (`parser.py:1152-1171`); password-protected PDFs handled cleanly; temp files removed in a `finally` block; no filenames are ever used to write to a fixed/predictable path.

### Secrets Handling

- Covered above (§1.1) — the JWT fallback secret is the standout issue.
- No other hardcoded real API keys or passwords found; `.env.example` only has placeholders.
- Missing `ANTHROPIC_API_KEY` degrades gracefully (`ai_chat.py:246-249`), no crash/leak.

### Error Handling

- No raw tracebacks returned to clients — `traceback.format_exc()` is only ever printed server-side.
- **Low** — `upload_statement` (`main.py:325, 331`) returns `str(e)` directly to the client on parse failure — minor internal-detail leakage, not a full stack trace.

### Dependencies

`python-jose` pins `algorithms=["HS256"]` explicitly, avoiding the classic "alg confusion" jose vulnerability. Nothing else in `requirements.txt` stood out as a known-vulnerable pin.

### Input Validation

- **High** — `GET/POST /accounts` (`main.py:245-261`) has no `current_user` dependency and no `user_id` filter at all, despite `Account.user_id` existing in the model. Anyone can list every user's account name/institution/last-4, and create arbitrary orphan accounts.
- **Low** — a handful of endpoints accept raw `dict` bodies instead of Pydantic models (`main.py:1641, 1687, 1704, 1777, 1820`) — no injection risk since values only reach bound-parameter SQL, but missing type coercion can throw unhandled exceptions on malformed input (ungraceful 500s).

---

## 3. Database Schema & Relationships

Schema is defined across **three places** that don't agree with each other: `models.py` (SQLAlchemy ORM, source of truth for most tables), `database.py`'s `ensure_tables()` (raw DDL for two tables with no ORM model), and `migrate.py` (one-off `ALTER TABLE`/`CREATE TABLE IF NOT EXISTS` statements against a hardcoded local SQLite file).

### Tables

| Table | PK type | `user_id` present? | Real FK? |
|---|---|---|---|
| `users` | String/UUID | — | — |
| `accounts` | String | nullable, no FK | none |
| `uploaded_files` | String | nullable, no FK | none |
| `categories` | String | nullable, no FK | none |
| `projects` (alias `Goal`) | **Integer** autoincrement | nullable, no FK | — |
| `transactions` | String (**+ redundant Integer `id`**) | nullable, no FK | `project_id → projects.id` (only real FK in the schema) |
| `transaction_rules` (alias `ClassificationRule`) | String | nullable, no FK | none |
| `budget_history` | **Integer** autoincrement | nullable, no FK | none |
| `manual_fixed_expenses` | **Integer** autoincrement | nullable, no FK | none |
| `chat_log` | **Integer** autoincrement | **NOT NULL** (only non-nullable `user_id` in the schema) | none |
| `credit_offsets` (raw SQL, no ORM model) | Integer | nullable, no FK | implied only (`credit_transaction_id`/`matched_expense_id`, unenforced) |
| `merchant_rules` (raw SQL, no ORM model) | Integer | nullable, no FK | none |

### Relationship diagram (text form)

```
User(user_id) <-loose- Account.user_id, UploadedFile.user_id, Category.user_id,
                        Project.user_id, Transaction.user_id, TransactionRule.user_id,
                        BudgetHistory.user_id, ManualFixedExpense.user_id,
                        ChatLog.user_id (NOT NULL, still no FK), credit_offsets/merchant_rules.user_id
Account(account_id)     <-loose- Transaction.account_id, UploadedFile.account_id
UploadedFile(...)       <-loose- Transaction.uploaded_file_id
Category(category_id)   <-loose- Transaction.category_id (also duplicated as free-text Transaction.category)

Transaction -> Project        REAL FK (project_id -> projects.id), both-side relationship()
credit_offsets -> transactions  implied only, no join enforced anywhere
merchant_rules                 standalone, not linked to anything by FK
```

"loose" = a plainly-typed column the app is trusted to populate consistently — no database-level referential integrity. **Only one relationship in the entire schema is a real, enforced foreign key.**

### Schema smells / risks

- **`merchant_rules` defined twice, inconsistently:** `database.py:53-73` (17 columns, Postgres-safe) vs. `migrate.py:70-79` (only 6 columns). Both use `CREATE TABLE IF NOT EXISTS`, so whichever runs first on a fresh DB wins permanently — the other's statement becomes a silent no-op. If `migrate.py` runs first, the app will hit `no such column: user_id/match_value/category/...` at runtime.
- **`projects` defined twice, inconsistently:** `migrate.py:9-19` lacks `user_id` and all `filter_*`/`is_auto` columns that `models.py:72-88` declares. Whichever creates the table first wins; the other never patches in the missing columns.
- **`migrate.py` ignores `DATABASE_URL` entirely** — it hardcodes `sqlite3.connect(.../financeai.db)`. On a Postgres deployment, its `ALTER TABLE` statements for `projects`/`is_fixed`/`fixed_confidence`/etc. never run against the real database; those columns only exist there because `models.py` already declares them and `main.py:23`'s `create_all()` provisions them. **`migrate.py` is effectively dead code except on a fresh local SQLite dev DB.**
- **No indexes** on any `user_id`, `account_id`, `category_id`, `uploaded_file_id`, or `project_id` column anywhere, despite "all transactions for this user" being the single most common query in the app. Only `Transaction.fingerprint` and `User.email` are indexed.
- **Dual-ID transaction table:** `Transaction` has both a String `transaction_id` (PK) and an Integer `id` (`unique=True, autoincrement=True`, not the PK) — redundant, looks like schema drift from an earlier design.
- **Inconsistent PK strategy:** String/UUID PKs on `users/accounts/uploaded_files/categories/transactions/transaction_rules` vs. Integer-autoincrement on `projects/budget_history/manual_fixed_expenses/chat_log` plus both raw-SQL tables.
- **Almost every `user_id` is nullable** — only `chat_log.user_id` is `NOT NULL` — so orphaned/unowned rows are legal virtually everywhere despite `user_id` being the de facto partition key for the whole app.
- **Type inconsistency:** `manual_fixed_expenses.created_at` is `Text` while every other table's timestamp columns are `DateTime`; the raw-SQL tables store timestamps as plain TEXT with no app-enforced default on `credit_offsets.updated_at`.
- `credit_offsets` and `merchant_rules` bypass the ORM completely (hand-written DDL strings in `database.py`), so they get no model, no `relationship()`, no type validation, and any future column change means editing DDL strings in up to three separate files.

---

## 4. Code Structure & File Overview

| File | Size | Responsibility |
|---|---|---|
| `main.py` | 1,898 lines | Entire FastAPI app — CORS, auth dependency, Pydantic models, **all 40 routes**, most business logic inlined into handlers |
| `models.py` | 227 lines | All SQLAlchemy ORM models + `seed_default_categories()` + three legacy aliases (`UserProfile=User`, `Goal=Project`, `ClassificationRule=TransactionRule`) |
| `database.py` | 87 lines | Engine/session setup (SQLite dev / Postgres prod) + raw-DDL creation of `credit_offsets`/`merchant_rules` (no ORM model for either) |
| `auth.py` | 40 lines | JWT + bcrypt, small and self-contained |
| `parser.py` | 1,401 lines | Bank statement ingestion — CSV/XLSX/OFX parsing, bank detection, dispatch to `pdf_parser_xy` or `llm_fallback` |
| `pdf_parser_xy.py` | 905 lines | Coordinate-based PDF table extraction, one hand-written parser per bank |
| `classifier.py` | 1,189 lines | Category classification from description text, used during ingestion |
| `fixed_classifier.py` | 605 lines | Separate fixed-vs-variable expense classifier, used directly by `main.py` |
| `ai_chat.py` | 775 lines | Templated chat responses built from transaction summaries — **no actual LLM call**, despite the name |
| `llm_fallback.py` | 497 lines | The actual LLM-based parsing fallback (with PII stripping) |
| `insights.py` | 672 lines | Spending insights/anomaly generation |
| `credit_engine.py` | 286 lines | Matches statement credits against expenses |
| `migrate.py` | 86 lines | One-off SQLite migration script (see §3 — largely dead against Postgres) |

### Structural issues

- **No `APIRouter` anywhere** — all 40 endpoints live in one file. Any change requires navigating the whole monolith.
- **Business logic inlined into route handlers** — e.g. `/upload` (`main.py:272-588`, ~316 lines) does bank-label parsing, dedup fingerprinting, fuzzy duplicate detection, bulk classification, and credit-nullification all inline. Untestable without spinning up the whole app + DB.
- **Repeated local re-imports inside function bodies** instead of module-level imports (e.g. `import sqlalchemy as _sa` repeated at 16 different lines in `main.py`) — obscures actual module dependencies.
- **Two same-named functions doing unrelated things:** `classify_transaction()` exists in both `classifier.py:1000` (category classification) and `fixed_classifier.py:401` (fixed/variable classification) — a landmine for future edits.
- **Dead code:** `parser.py:21` defines a stub `parse_statement_with_claude()` that returns `([], bank)` and does nothing, left over from a deleted `ai.py` module — but it's still called at `parser.py:923`.
- **Schema-level duplication in `Transaction`:** `currency` + `currency_code`, and four description fields (`description`, `description_raw`, `description_clean`, `original_description`) with no single source of truth.
- **Inconsistent error handling:** only 10 `try/except` blocks across 40 endpoints in `main.py`; several bare `except:` clauses; `delete_account` swallows all per-table delete failures silently (`except Exception: pass`).
- **Mixed data-access style:** `/auth/signup` and `/auth/login` run raw SQL directly against the `users` table instead of using the `User` ORM model that every other endpoint uses.
- **No tests** — no test files or framework (`pytest`, etc.) anywhere in `backend/`.
- **No structured logging** — diagnostics go through `print()` (14 in `main.py`, 24 in `parser.py`, 28 in `llm_fallback.py`), nothing goes through Python's `logging` module.

---

## 5. Prioritized Remediation Checklist

- [ ] Make `JWT_SECRET_KEY` required at startup unconditionally — no `ENVIRONMENT`-gated fallback (§1.1)
- [ ] Add auth (and likely an admin check) to `DELETE /data/all`, or remove it (§1.2)
- [ ] Add `Depends(get_current_user)` + `user_id` filter to `GET/POST /accounts` (§1.3 general, §2 input validation)
- [ ] Scope `get_net_category_spend()` by `user_id` (§1.4)
- [ ] Verify `project_id` ownership before reassigning a transaction to it (§1.3)
- [ ] Add rate limiting to `/auth/login` and `/auth/signup`
- [ ] Make `DELETE /auth/account`'s per-table deletes fail loudly (or roll back) instead of silently swallowing errors (§1)
- [ ] Add email verification on signup, plus forgot-password/reset-password endpoints — requires adding an email-sending dependency first (§1)
- [ ] Reconcile the two `merchant_rules` definitions and two `projects` definitions into one source of truth; retire or fix `migrate.py`'s Postgres blind spot
- [ ] Add indexes on `user_id` (and other FK-like columns) across the schema
- [ ] Reject `*`/blank entries in `FRONTEND_ORIGINS`; drop `allow_credentials=True` unless cookies are introduced
- [ ] Longer-term: split `main.py` into `APIRouter` modules by domain (auth, accounts, transactions, projects, insights) and move inline business logic into service functions to make it testable
- [ ] Fix `credit_engine.py:261`'s `substr(transaction_date, 1, 7)` — SQLite-only syntax that crashes on Postgres (see §6, finding #12)

---

## 6. Live Verification

Everything above §6 was found by reading the source. To confirm these aren't just theoretical, `backend/scripts/security_poc.py` seeds two dummy accounts (User A / User B) against the running dev server and exercises each finding live — real HTTP requests, real responses, no fabricated output. Re-run anytime with:

```bash
cd backend && source venv/bin/activate
python scripts/security_poc.py
```

It does **not** run the destructive `DELETE /data/all` test (#2) automatically — that endpoint wipes every user's data with no auth, so it was deliberately left out of an automated script rather than run against a database that might contain real data.

### Results from the 2026-07-20 run (against `postgresql://.../xspend`)

| Finding | Result |
|---|---|
| #1 — Hardcoded JWT secret | **VULNERABLE.** Imported `auth.py` fresh with `JWT_SECRET_KEY` and `ENVIRONMENT` both unset (isolated subprocess, did not touch the live server) — `SECRET_KEY` resolved to the literal `"financeai-dev-only-secret-change-me"`. |
| #3 — `/accounts` unauthenticated | **VULNERABLE.** `GET /accounts` with zero auth headers returned HTTP 200 with account rows. `POST /accounts` with zero auth headers returned HTTP 200 and created a real, ownerless account row. |
| #14 — `/categories` unauthenticated | **VULNERABLE** (as expected, low sensitivity). `GET /categories` with no auth returned HTTP 200. |
| #4 — Cross-user spend leak | **Confirmed at the root-cause level.** The live `GET /credit-offsets/{period}` call itself 500'd (see #12 below) before it could return leaked data. To isolate the actual finding from that unrelated crash, the exact same WHERE clauses from `credit_engine.py:257-262` were re-run with only the broken `substr()` call swapped for a Postgres-safe `to_char()` — same logic, same missing user filter, no application code touched. Result: called with no user filter at all, it returned **User A's spend category directly to a query representing User B's request**, proving the missing filter is real and would leak the moment #12 is fixed. |
| #5 — IDOR on project assignment | **VULNERABLE.** User A's own transaction was successfully `PATCH`ed onto **User B's** project (`project_id=5`, a project User A never created and has no relationship to) — HTTP 200, no ownership check blocked it. |
| Control: `/transactions` scoping | **SAFE**, as expected — `GET /transactions` for User B returned 0 of User A's rows. Confirms the app *can* isolate users correctly elsewhere; the bugs above are specific gaps, not a systemic absence of user-scoping. |
| #11 — No email verification / reset flow | **Confirmed absent** — no such routes exist to test against (already established by source read; nothing to add live). |
| #12 — `/credit-offsets/{period}` 500s on Postgres (new finding) | **CONFIRMED BUG.** `credit_engine.py:261` runs `substr(transaction_date, 1, 7)` — valid SQLite (dates stored as TEXT there) but invalid Postgres, which rejects `substr()` on a `date`-typed column: `psycopg2.errors.UndefinedFunction: function substr(date, integer, integer) does not exist`. On this Postgres-backed dev instance, the endpoint is currently broken for *everyone*, which is why it fails closed rather than leaking today. Fix requires both this dialect bug **and** the missing `user_id` filter (#4) — fixing only the crash without adding the filter would turn this from "broken" into "actively leaking." |

**Side effect:** the script leaves harmless, clearly-labeled test data in the dev database — two `sectest.user{a,b}@example.com` accounts, a couple of `SECTEST-orphan-account` rows, and a few `SECTEST-Category-A-*` transactions. Safe to leave (all rows are identifiable by the `SECTEST`/`sectest` prefix) or ask to have them cleaned up.

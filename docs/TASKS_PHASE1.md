# Phase 1, Weeks 1-2: Isolation and Dedup Correctness

**Milestone:** 2 weeks, 20 hrs/week, ~40 hours.
**Goal:** every user's data is provably isolated, and dedup is correct in both
directions (catches real duplicates, never merges genuinely distinct transactions).

Background for all of this is in `ARCHITECTURE.md`, sections 5.2, 5.3, 8 and 9.
Section 9 is the verified list of open issues; the tasks below work through it.

**Nothing here adds a feature.** This milestone is about making the foundation
trustworthy. Feature work and Plaid come after.

---

## GitHub Projects setup

**Board columns:** `Backlog` -> `This Week` -> `In Progress` -> `In Review` -> `Done`

**Labels to create:**

| Label | Colour suggestion | Meaning |
|---|---|---|
| `P0` | red | Data loss, corruption, or cross-user leak. Drop everything. |
| `P1` | orange | Serious correctness issue. |
| `P2` | yellow | Real but bounded. |
| `P3` | grey | Housekeeping. |
| `data-integrity` | blue | |
| `reliability` | blue | |
| `isolation` | purple | Anything touching multi-user scoping. |

Each task below is written to paste directly into a GitHub issue.

---

# WEEK 1: Isolation and foundation (~20h)

---

## 1. Archive spent patch scripts

**Labels:** `P3` `reliability`
**Estimate:** 0.5h
**Location:** `backend/`

`backend/` contains roughly fifty `patch_*.py` / `patchXXX_*.py` scripts. They are
one-time migrations that have already been applied and committed. They are dead weight
and make the live codebase hard to read.

Move them to `backend/_archive/applied_patches/` with `git mv` (do not delete, they are
history). Also move `isolation_audit.py`, `isolation_audit_v2.py`, and the ad-hoc
`test_*.py` scripts.

**Done when:** `ls backend/*.py` shows only the ~13 core modules listed in
`ARCHITECTURE.md` section 3.

---

## 2. Set up the pytest suite

**Labels:** `P0` `reliability`
**Estimate:** 2h
**Location:** new `backend/tests/`

There is no automated test suite. Everything so far has been verified by hand in a
terminal. This task creates the scaffold that the rest of the milestone builds on.

Set up `backend/tests/` with `conftest.py`, fixtures for an in-memory or temp SQLite DB,
and factory helpers for creating users and transactions. Confirm `pytest` runs green
against an empty suite.

**Done when:** `pytest` runs from `backend/`, fixtures exist for a test DB and for
creating a user with transactions, and the suite is committed.

**Note:** every subsequent task in this milestone ships with tests. This is the
foundation, so it comes first.

---

## 3. Multi-user isolation audit

**Labels:** `P0` `isolation` `data-integrity`
**Estimate:** 8h
**Location:** `main.py` (all endpoints), plus anything they call

The core question: **can any user ever see or modify another user's data?**

Audit every read and write path. For each endpoint, confirm:

- The user identity comes from the **verified auth token**, never from a client-supplied
  parameter.
- Every query that touches user-owned data filters by `user_id`.
- Ownership mismatches return 404 rather than 403 (so we don't leak that a record exists).
- Scoping holds in non-obvious places: joins, aggregates, bulk operations, and anything
  that runs outside a request context.

Produce a written list of every gap found, with file and line. Fixes can be separate
issues if the list is long; the audit itself is the deliverable.

**Known starting point:** `credit_engine.get_net_category_spend(db, period)` has no
`user_id` parameter and was flagged unscoped in a prior hardening pass. See task 4.

**Done when:** a written audit exists covering every endpoint, each gap has an issue,
and anything trivially fixable is fixed.

---

## 4. Scope `get_net_category_spend` by user

**Labels:** `P0` `isolation` `data-integrity`
**Estimate:** 2h
**Location:** `credit_engine.py:257`, called from `main.py:1864`

`get_net_category_spend(db, period)` takes no `user_id`. If it queries transactions by
period alone, it computes net category spend **across every user in the database**, and
one user sees numbers derived from everyone's transactions.

This was flagged during an earlier hardening pass and is still open. It powers the
`/credit-offsets` endpoint.

Add explicit user scoping, and add a test that proves user A's result does not change
when user B has transactions in the same period.

**Done when:** the function requires a `user_id`, every caller passes the authenticated
user, and a test proves cross-user isolation.

---

## 5. Cross-user access tests

**Labels:** `P0` `isolation`
**Estimate:** 4h
**Location:** `backend/tests/`

Prove isolation rather than assuming it.

Create two test users with **near-identical data** (same amounts, dates, merchants) so
any ID mix-up surfaces immediately. Then, for every endpoint that touches user data,
assert that:

- Authenticated as user A, requesting user B's record fails (404).
- Authenticated as user A, modifying or deleting user B's record fails.
- Unauthenticated requests fail.
- Aggregate/summary endpoints computed for user A never include user B's rows.

Parametrize across endpoints so adding a new one is one line.

**Done when:** the suite covers every user-data endpoint in all three roles (owner,
other user, unauthenticated) and runs green.

---

## 6. Short `ext_id` collides two different charges

**Labels:** `P0` `data-integrity`
**Estimate:** 2h
**Location:** `classifier.generate_fingerprint`, `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #5

The two functions disagree about what "trustworthy external id" means.

- The dedup fast-path requires `len(ext_id) > 5` before trusting it.
- `generate_fingerprint()` folds **any** non-empty `ext_id` into the hash and ignores
  date, amount, and description entirely when it does.

So an id too short to trust at stage (a) still becomes the *whole fingerprint key* at
stage (b). Two genuinely different charges that happen to share a short id collide, and
one is silently dropped.

Make both functions agree on a single rule for when an external id is trusted.

**Done when:** the trust rule is defined in one place and used by both, and a test proves
two different charges sharing a short id both survive.

---

## 7. `amount = None` is saved as $0.00

**Labels:** `P0` `data-integrity`
**Estimate:** 2h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #6

`t.get("amount", 0) or 0` treats `None` the same as a missing key, because `None or 0`
is `0`. A row with an unknown amount is silently fingerprinted and saved as a genuine
zero-dollar transaction, which then flows into every balance and every insight.

Note that `0` is a legitimate amount, so minting one is its own hazard. Distinguish
"key absent" from "value is None", and reject or quarantine rows with no usable amount
rather than coercing them.

Coordinate with task 15 (validation layer) on where rejection should live.

**Done when:** a `None` amount is never saved as `0`, the behaviour is tested, and the
decision (reject vs quarantine) is documented.

---

# WEEK 2: Dedup correctness (~20h)

---

## 8. Same-day repeat purchases are silently merged

**Labels:** `P0` `data-integrity`
**Estimate:** 5h
**Location:** `classifier.generate_fingerprint`, `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #4

**The most serious open bug.** Two genuinely separate purchases (two $20 Trader Joe's
runs on the same day) produce an identical fingerprint, so the second is dropped as a
duplicate and the user loses a real transaction.

It bites from the `existing` side too: a user who already has two identical charges,
then re-uploads a statement containing those two plus a genuinely new third purchase,
loses the third as well. All three incoming rows read as duplicates.

This needs no malformed input, just an ordinary repeated purchase.

**Suggested direction:** track occurrence count rather than identity. Count how many
times a given `(account, date, amount, merchant)` tuple already appears in `existing`,
and treat the Nth incoming match as a duplicate of the Nth existing occurrence, not the
1st.

**Read this before starting:** there is an inherent ambiguity the current data model
cannot resolve. Nothing distinguishes "the parser emitted this line twice" from "the
user really bought two identical items" without a line id or sequence number from the
source. Occurrence counting handles the common case; it does not fully solve the problem.
If you conclude the model needs a new field, say so, that is a legitimate outcome of this
task.

**Done when:** two genuine same-day same-amount purchases both survive, a re-upload of
a statement containing them still produces zero new rows, and the third-occurrence case
is tested. Any remaining modeling limit is documented.

---

## 9. Fuzzy match compares raw description, not normalized merchant

**Labels:** `P1` `data-integrity`
**Estimate:** 3h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #11

The fingerprint stage normalizes merchant text precisely so that re-parsed descriptions
still match. The fuzzy stage, which exists as the fallback for cases the fingerprint
misses, does an exact lowercase comparison on the **raw** string instead.

So a re-upload where both the description text **and** the settlement date drift by a
day or two (aggregators commonly do both) is caught by neither rule 2 (date differs) nor
rule 3 (description differs). That directly violates our stated requirement that
re-uploading a statement produces zero new rows.

Use `_fingerprint_merchant()` for the fuzzy comparison rather than the raw string.

**Done when:** a re-upload with a reworded description and a 1-2 day date shift is caught,
and the existing fuzzy tests still pass.

---

## 10. No validation layer for malformed rows

**Labels:** `P1` `data-integrity`
**Estimate:** 3h
**Location:** `main.py` dedup loop, possibly `parser.py`
**Ref:** ARCHITECTURE.md section 9, issue #14

Rows with an empty date and/or description are not rejected. They skip the fuzzy check
(the date won't parse) and get saved as-is. Nothing flags "this row is missing fields a
real parsed transaction should always have."

Decide explicitly whether the parser or the dedup layer owns rejecting these, then
implement it. Pairs with task 7.

**Done when:** malformed rows are rejected or quarantined rather than saved silently, the
ownership decision is documented, and the behaviour is tested.

---

## 11. Substring alias matching over-matches

**Labels:** `P2` `data-integrity`
**Estimate:** 2h
**Location:** `classifier._fingerprint_merchant`, `_MERCHANT_ALIASES`
**Ref:** ARCHITECTURE.md section 9, issue #7

The alias cascade uses a `"contains"` match against roughly ninety brand names. So
"MyTarget Fitness Studio" contains `"target"` and collapses to the retailer. Two
unrelated merchants then share a fingerprint and can falsely merge.

Tighten the match (word boundaries, or a more careful matching strategy) without breaking
the cases the cascade exists for: `"Amazon Mktpl*3C5"`, `"AMZN Mktp"`, and
`"Debit Card Purchase Amazon"` must all still collapse to `amazon`.

`backend/test_fingerprint.py` (currently an ad-hoc script) has the existing collapse
cases. Fold them into the real suite.

**Done when:** "MyTarget Fitness Studio" no longer matches Target, every existing brand
variant still collapses correctly, and both directions are tested.

---

## 12. Fuzzy match ignores `ext_id` entirely

**Labels:** `P2` `data-integrity`
**Estimate:** 2h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #12

Two transactions carrying **different** bank-assigned external ids (a strong signal the
source system considers them distinct, e.g. two identical recurring charges posted the
same day) still get merged, because the fuzzy stage only compares account, amount, and
description.

**Suggested direction:** if both sides have an `ext_id` and the ids differ, that should
veto a fuzzy match, mirroring how a matching id short-circuits at rule 1.

Note this is arguably a design gap rather than a clear-cut spec violation, the spec's
fuzzy rule doesn't mention `ext_id` at all. Resolving the ambiguity is part of the task.

**Done when:** a present-and-different `ext_id` prevents a fuzzy merge, the behaviour is
tested, and the rule is written down.

---

## 13. FITID fast-path ignores `account`

**Labels:** `P2` `data-integrity`
**Estimate:** 1.5h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #8

The FITID short-circuit checks raw `ext_id` equality against a set built across **all**
of a user's existing rows, with no account scoping. The fingerprint path always includes
account. An external id reused across two accounts (plausible, FITIDs are only guaranteed
unique within an account at an institution, not globally) wrongly merges two different
charges.

Key `existing_fitids` by `(account, ext_id)` rather than `ext_id` alone.

**Done when:** the same `ext_id` on two different accounts stays distinct, and it's tested.

---

## 14. `account` / `bank` not normalized before hashing

**Labels:** `P2` `data-integrity`
**Estimate:** 1.5h
**Location:** `classifier.generate_fingerprint`
**Ref:** ARCHITECTURE.md section 9, issue #9

`"Checking"` and `"checking"` hash to different fingerprints, so the same transaction
saved under slightly different account casing is never recognized as a duplicate.

Normalize case and whitespace on `account` and `bank` before hashing.

**Careful:** this changes the fingerprint formula, so rows saved under the old formula
won't dedup against new ones. Note the migration implication in the PR; a backfill may
be needed.

**Done when:** casing and whitespace variants of the same account produce the same
fingerprint, and the migration impact is documented.

---

## 15. `fuzzy_index` is never updated within a batch

**Labels:** `P2` `data-integrity`
**Estimate:** 1.5h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #10

`fuzzy_index` is built once from `existing` before the loop and never updated as incoming
rows are accepted. `existing_fps` **is** updated in-loop. Because of that asymmetry, two
rows in the same incoming batch with the same description but different dates (so no
shared fingerprint, which requires an exact date match) should fuzzy-match each other,
but both get saved.

Append to `fuzzy_index` alongside `existing_fps` whenever a row is accepted.

**Done when:** two fuzzy-duplicate rows in one batch resolve to one saved row, and it's
tested.

---

## 16. `ext_id` not stripped on the `existing` side

**Labels:** `P3` `data-integrity`
**Estimate:** 0.5h
**Location:** `main.py` dedup loop
**Ref:** ARCHITECTURE.md section 9, issue #13

Only the incoming side gets `.strip()`ed. A stray leading or trailing space on an already
saved row's `ext_id` falls through both rule 1 and rule 2, because `"OFX-123 "` and
`"OFX-123"` aren't equal.

Low severity, only surfaces if a stray space actually gets into a saved id, but cheap.

**Done when:** both sides are stripped before comparison.

---

# End-of-milestone check

Before we call Phase 1 done:

- [ ] `pytest` runs green, and covers dedup (both directions), fingerprinting, and
      cross-user isolation.
- [ ] A written isolation audit exists, and every gap is either fixed or has an issue.
- [ ] `get_net_category_spend` is user-scoped, with a test proving it.
- [ ] Re-uploading the same statement produces **zero** new rows, including when the
      description is reworded and the date drifts by a day.
- [ ] Two genuinely separate same-day, same-amount purchases **both** survive.
- [ ] No row with a missing amount is ever saved as $0.
- [ ] Any remaining modeling limits (e.g. the same-day ambiguity) are written down rather
      than silently left.

---

# Deliberately not in this milestone

So there's no ambiguity about scope:

- **Async upload.** Real user pain, but it's roughly a week on its own. Phase 2.
- **CI.** Wants the test suite to exist first. Phase 2.
- **Plaid.** Depends on all of the above being solid. The Plaid feed runs through this
  same dedup logic, which is exactly why it comes after. Phase 2/3.
- **Auth work** (forgot password, login email, account deletion). Phase 2.
- **Any feature work** (insights, chat, projects, what-if calculator). Phase 3+.

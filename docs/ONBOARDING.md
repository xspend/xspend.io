# Onboarding

Welcome. This is the day-one guide: how to get set up, how we work, and the few things
that will bite you if nobody tells you about them.

Read this first, then `ARCHITECTURE.md`, then `TASKS_PHASE1.md`.

---

## 1. Read this before you touch anything

### The local backend points at production

`backend/.env` sets `DATABASE_URL` to the **Neon production database**. A local
`uvicorn` will therefore read and write **live user data** unless you override it.

Always run local with an explicit override:

```bash
DATABASE_URL="sqlite:///./financeai.db" uvicorn main:app --port 8000
```

This is one stray `DELETE` away from real damage to real people's financial records.
It is the single most important thing on this page. Fixing the default is fair game if
you want to; until then, override it every time.

### Everything on `main` deploys to production immediately

There is no CI and no staging. Push to `main`, and Render and Vercel deploy it to live
users within a couple of minutes. That is why all work goes through pull requests, and
why nothing merges without tests.

Building CI is on the roadmap. It is not in this milestone.

---

## 2. Access you should have

Ask if any of these are missing:

- [ ] GitHub repo: `github.com/xspend/xspend.io` (private)
- [ ] GitHub Projects board: **Phase 1**
- [ ] Upwork (for contract, hours, messages)
- [ ] Slack or Teams channel, if we set one up

You will **not** have by default, and should not need for this milestone:

- Production database write access
- Anthropic API key
- Render or Vercel dashboards

If a task genuinely needs one of these, ask, and we'll scope it to that task.

---

## 3. Local setup

```bash
git clone git@github.com:xspend/xspend.io.git
cd xspend.io

# backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# run it, note the override
DATABASE_URL="sqlite:///./financeai.db" uvicorn main:app --port 8000
```

```bash
# frontend, separate terminal
cd frontend
npm install
npm run dev
```

The frontend expects the backend on port 8000. See `frontend/src/lib/config.js`.

**Tests** don't exist yet. Creating the suite is your second task. After that:

```bash
cd backend
pytest
```

---

## 4. How we work

| | |
|---|---|
| **Hours** | 20/week |
| **GitHub Projects** | Updated **daily**. The board is the source of truth for status. |
| **Written check-in** | **Every other day**: what you did, what's next, anything blocking. |
| **Calls** | **Monday and Friday, 8:00 AM PDT / 8:30 PM IST.** Monday plans, Friday reviews. |
| **Day to day** | Async. See below. |

### The timezone reality

Your working hours (10 AM to 7 PM IST) and Dharani's (7 AM to 5 PM PDT) **do not
overlap at all**. Your day is her night.

The only shared window is roughly **7:00 to 11:30 AM PDT**, which is 7:30 PM to
midnight your time, which is why the calls are where they are.

**Practical consequence:** if you ask a question at noon your time, the answer arrives
roughly a day later. So:

- **Don't sit blocked.** Note the blocker on the board and move to another task.
- **Ask early.** A question raised at the start of your day has a chance of being
  answered by the next.
- **Batch questions** into the check-in rather than sending them one at a time.
- **When in doubt, write it down and proceed with your best judgment**, flagging the
  assumption. A documented wrong assumption is easy to correct. A day lost waiting is
  not recoverable.

---

## 5. Code conventions

**Branch and PR.** No direct pushes to `main`. Branch, PR, and describe what changed
and why.

**Tests ship with the change.** Every behavioural change comes with a test. This
codebase has been burned repeatedly by silent regressions; see `ARCHITECTURE.md`
section 8.

**Improve, don't rewrite.** Some logic here looks strange and is load-bearing for
reasons that aren't obvious from reading it. The sign conventions, the merchant
canonicalization cascade, the reconciliation step, each exists because something broke
in production. If something looks wrong, **flag it before changing it.** You may well
be right, and if you are we want to know. But ask first.

**Instrument before fixing.** Every serious bug in this codebase so far was hidden
behind an exception handler that swallowed the real error, or behind a missing log
line. When something fails inexplicably, add loud logging first. It has cracked every
one of them in a single upload. Do not theorize for hours; make the code tell you.

**zsh eats `!`.** Inline `python3 -c "..."` breaks on `!`, including inside f-strings,
because of history expansion. Write a `.py` file instead. This will waste ten minutes
of your life exactly once.

---

## 6. Data handling

xspend holds real users' bank statements and financial records. This is the most
sensitive part of the work.

- **Develop and test against synthetic data.** Never real user data.
- **No local copies of production data.** No exports, no screenshots, no dumps.
- **Production access is read-only**, and only for specific tasks agreed in advance.
- **Minimum necessary.** Query what the task needs. Don't browse.
- **AI coding assistants are fine.** Putting real user data into one is not, ever. Same
  for any third-party service.
- **Credentials are confidential.** Never commit, log, paste, or share them.
- **If something leaks or you think it might have, say so immediately.** A compromise
  of user financial data may create legal obligations, and we can't act on what we
  don't know about.

Full terms are in the NDA.

---

## 7. What you're walking into

Honest context, so nothing surprises you.

This is a working product with live users, built solo and fast. It does hard things
well: it parses statements from banks it has no template for, using an LLM with
reconciliation as a safety net, and that path currently handles the highest-volume bank
in production.

It also has real gaps, and they're written down rather than hidden. `ARCHITECTURE.md`
section 9 lists twenty-one open issues, including an unfixed cross-user data leak.
There are no automated tests. There is no CI. Roughly fifty spent patch scripts clutter
the backend directory.

None of that is a secret and none of it is a trap. It's why you're here.

**Your first two weeks are about the foundation**, isolation and dedup correctness.
Not features. Not Plaid. Those come after, and they depend on this being solid, because
the Plaid feed will run through the same dedup logic you're about to fix.

The bug history in section 8 is worth reading properly. Several of those bugs cost days
and every one of them taught something. You'll recognize the shapes.

---

## 8. Where to look

| Doc | What it is |
|---|---|
| `docs/ONBOARDING.md` | This. Setup and how we work. |
| `docs/ARCHITECTURE.md` | The system. File map, data flow, core logic, thresholds, landmines, bug history, open issues. |
| `docs/TASKS_PHASE1.md` | The two-week plan, with the reasoning behind the sequencing. |
| GitHub Projects: **Phase 1** | Live status. Same tasks, as issues. |

Questions are welcome and asking early is better than asking late. Given the timezone
gap, the highest-value thing you can do is write down what you're uncertain about as
you go, rather than saving it up.

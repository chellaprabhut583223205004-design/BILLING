# Implementation Plan & Roadmap — CMS EARTH MOVERS Billing

**Repository:** `/home/coder/billing/BILLING` (branch `main`)
**Reviewed:** Sat Oct 17, 2026
**Scope:** Code review of Flask billing app + prioritized implementation plan.
**Deliverable type:** Planning only — no application code was modified.

---

## 1. Project Overview

CMS EARTH MOVERS Billing is a small web application for recording JCB / earthmoving service bills.

- **Backend:** single-file Flask app (`app.py`, 469 lines) using SQLite (`jcp_billing.db`).
- **Frontend:** server-rendered Jinja templates (`templates/*`) plus a large shared stylesheet (`static/style.css`) and shared script (`static/script.js`). The New Bill page (`templates/index.html`) also embeds a second, duplicate inline script.
- **Features present in code:**
  - Create / calculate / print / save bills (`/`, `/api/bills`)
  - Bill history search (`/history`, `/api/bills`)
  - Customer aggregation (`/customers`, `/api/customers`)
  - Daily collection report (`/daily-report`, `/api/daily-report`)
  - CSV export (`/export-bills`)
  - About page (`/about`)
- **Target deployment:** Vercel (empty `vercel.json`, `requirements.txt` contains only `Flask`).

Key business rules implemented in code: Indian Standard Time (IST), invoice IDs of form `CMS{YY}/{MM}/{DD}/{NNN}`, next-day handling when end time < start time, duration capped at 24 h, rate/tax validation, tax calculation.

---

## 2. Current State Assessment

### 2.1 What works

- Flask routing and Jinja template inheritance (`base.html` lines 147).
- SQLite schema creation (`app.py:28-50`) and parameterized queries (no SQL injection found).
- Bill calculation math is consistent between backend (`app.py:231-237`) and frontend (`static/script.js:86-101`).
- Time parsing accepts `HH:MM` and 12-hour variants (`app.py:80-91`).
- Next-day duration logic exists in both backend (`app.py:199-205`) and frontend (`static/script.js:49-52`).
- CSV export includes BOM for Excel (`app.py:449`).
- Daily report date validation (`app.py:346-351`).

### 2.2 Critical gaps

The app currently has **multiple P0 defects** that make core flows non-functional or unsafe:

1. **No Save button exists** in `templates/index.html`, so `saveBill()` in `static/script.js:209-237` can never be invoked. Bills cannot be persisted from the UI.
2. **History and Customers pages never load data** because `base.html` does not define a `{% block page_script %}` block, so the `{% block page_script %}` content in `templates/history.html:41-45` and `templates/customers.html:38-42` is silently dropped, and `static/script.js` does not auto-call `loadHistory()` / `loadCustomers()` on those pages.
3. **Customers totals are undefined** because the API returns `total_bills` / `total_amount` / `last_billing_date` (`app.py:319-324`) but the frontend reads `bill_count` / `total_spent` / `last_bill` (`static/script.js:413-415`).
4. **Daily report renders unsanitized API values via `innerHTML`** (`templates/daily_report.html:51-59`) — XSS.
5. **Selecting "Other" work description crashes** because `static/script.js:444-452` accesses `$("customWork")` which does not exist in `templates/index.html`.
6. **Vercel deployment will fail** because `initialize_db()` runs at import time (`app.py:466`) and writes `jcp_billing.db` to the read-only app directory (`app.py:15`).

---

## 3. Identified Issues

Priority legend: **P0** = blocker (must fix before release), **P1** = should fix, **P2** = nice to have.

### 3.1 Correctness

| ID | Pri | Location | Issue | Impact |
|---|---|---|---|---|
| I-01 | P0 | `app.py:15`, `app.py:466` | SQLite DB path is next to `app.py` and `initialize_db()` writes at import. Vercel filesystem is read-only except `/tmp`. | App crashes on import in production; no persistence. |
| I-02 | P0 | `templates/base.html:147` (only `content` block) vs `templates/history.html:41-45`, `templates/customers.html:38-42` | `page_script` block is never rendered. | History/Customers pages never fetch data. |
| I-03 | P0 | `app.py:319-324` vs `static/script.js:413-415` | Field-name mismatch (`total_bills`/`total_amount`/`last_billing_date` vs `bill_count`/`total_spent`/`last_bill`). | Customer totals show `undefined`/`NaN`. |
| I-04 | P0 | `templates/index.html` (no save button) vs `static/script.js:209-237` | `saveBill()` defined but no UI trigger; `saveButton` element absent. | Cannot persist bills from UI. |
| I-05 | P0 | `static/script.js:444-452`, `templates/index.html` (no `customWork`) | Selecting "Other" dereferences null `customWork`. | JS exception; form unusable. |
| I-06 | P0 | `static/script.js:334` | `$("new-bill").scrollIntoView()` not guarded. | Exception when viewing a saved bill on index. |
| I-07 | P1 | `app.py:57-77` | `next_bill_id()` derives sequence from `MAX`-like `ORDER BY invoice_no DESC`; not atomic. | Duplicate invoice numbers under concurrency; 409 with no client retry. |
| I-08 | P1 | `templates/index.html:410-621` + `static/script.js` | Two competing implementations of `calculateBill`, `clearBill`, etc.; script.js overrides inline functions. | Confusing maintenance; inconsistent IDs. |
| I-09 | P1 | `static/script.js:166` vs `templates/index.html:353` | Script targets `invoiceNumber`; template uses `billingId`. | Saved Bill ID not shown in invoice header. |
| I-10 | P1 | `templates/daily_report.html:38-43` | No `response.ok` check before `.json()`. | Crash on API error. |
| I-11 | P2 | `static/script.js:34-59` | Client `getHours()` has no 24-hour cap (backend caps at 24 h, `app.py:207`). | Client/server validation mismatch. |
| I-12 | P2 | `app.py:174-180` | No length limits on `customer_name` / `work_description` (frontend has `static/script.js:73-75`). | Inconsistent validation. |
| I-13 | P2 | `static/script.js:196-199` | Re-saving creates a new bill (by design message) but may confuse users. | Duplicate records. |

### 3.2 Security

| ID | Pri | Location | Issue | Impact |
|---|---|---|---|---|
| I-14 | P0 | `templates/daily_report.html:51-59` | `innerHTML` interpolates `invoice_no`, `customer_name`, `created_at` without escaping. | Stored XSS via bill fields. |
| I-15 | P2 | `app.py:469` | `app.run(debug=True)` if executed directly. | Debugger exposure in non-prod runs. |
| I-16 | P2 | `app.py:390-459` | CSV export does not neutralize formula-leading characters. | CSV injection in spreadsheet apps. |
| I-17 | P2 | (whole app) | No authentication / CSRF / rate limiting. | Acceptable only for trusted local use; must be documented. |

Note: SQL queries are parameterized (`app.py` uses `?` placeholders throughout) — no SQL injection found.

### 3.3 Maintainability / UX

| ID | Pri | Location | Issue | Impact |
|---|---|---|---|---|
| I-18 | P1 | `templates/base.html:13-17` | `<img>` for logo placed inside `<head>`; placeholder span instead of `JCB.jpg`. | Invalid HTML; logo not shown in nav. |
| I-19 | P1 | `templates/base.html:151` | Footer year hardcoded to `2026`. | Stale over time. |
| I-20 | P2 | `static/script.js` + `templates/index.html` inline | Monolithic ~469-line script and duplicated calc logic. | Hard to test/maintain. |
| I-21 | P2 | `app.py` (all) | Single 469-line module; no blueprints/tests/migrations. | Hard to scale. |
| I-22 | P2 | (repo) | No tests, no CI, no lint config. | Regressions not caught. |
| I-23 | P2 | `app.py:137-149` | `get_bills()` returns all rows; no pagination. | Performance on large datasets. |
| I-24 | P2 | `static/script.js:428-442` | Clock formatting okay; minor. | — |

---

## 4. Prioritized Roadmap

### Phase 0 — Stabilize core flows & deployment (P0, ~1–2 days)

| Task | Related issues | Acceptance criteria |
|---|---|---|
| **T0.1** Make DB path environment-aware and init safe | I-01 | `DB_PATH` resolves from `DATABASE_PATH` env (default `/tmp/jcp_billing.db` when on Vercel, else local file); `initialize_db()` is idempotent and never writes to read-only dirs; app imports successfully. |
| **T0.2** Render page scripts in base template | I-02 | `base.html` adds `{% block scripts %}` (or `page_script`); History and Customers pages call their loaders on DOM ready; data visible after refresh. |
| **T0.3** Fix customers API/frontend field mapping | I-03 | Frontend reads `total_bills`, `total_amount`, `last_billing_date`; totals and last bill display correctly. |
| **T0.4** Add Save action to New Bill page | I-04 | A "Save Bill" button calls `saveBill()`; `statusMessage` element exists; successful save shows ID and updates `billingId`. |
| **T0.5** Support "Other" work description | I-05 | Selecting "Other" reveals an input (`customWork`); value is included in payload; no console errors. |
| **T0.6** Guard `loadBill` scroll | I-06 | Viewing a saved bill does not throw; scrolls only if `new-bill` exists. |
| **T0.7** Remove XSS from daily report | I-14 | Report rows built with DOM/textContent (or escaped template); script payloads render as text. |
| **T0.8** Add error handling to daily report | I-10 | Non-200 responses show a message; no undefined access. |

### Phase 1 — Correctness & concurrency (P1, ~2–3 days)

| Task | Related issues | Acceptance criteria |
|---|---|---|
| **T1.1** Atomic invoice numbering | I-07 | Concurrent `POST /api/bills` never produce duplicate IDs; unique constraint enforced; client retries on 409. |
| **T1.2** Consolidate frontend scripts | I-08, I-09 | Remove inline script from `index.html`; all behavior lives in `static/script.js`; IDs aligned (`billingId` or `invoiceNumber` consistently). |
| **T1.3** Backend validation parity | I-11, I-12 | Server enforces length caps and 24-hour max; matches frontend. |
| **T1.4** Vercel configuration & dependencies | I-01 | `vercel.json` defines builds/routes for Flask; `requirements.txt` pins Flask version (and gunicorn for local parity). |
| **T1.5** Safe debug default | I-15 | `debug` defaults to `False` unless `FLASK_DEBUG=1`. |
| **T1.6** Fix nav logo / footer year | I-18, I-19 | Logo image renders from `static/JCB.jpg`; footer year computed dynamically. |

### Phase 2 — Quality, UX, and hardening (P2, ~3–5 days)

| Task | Related issues | Acceptance criteria |
|---|---|---|
| **T2.1** Add automated tests | I-22 | pytest suite covers helpers, API endpoints, daily report, customers mapping; runs in CI. |
| **T2.2** CSV injection protection | I-16 | Cells starting with `=`,`+`,`-`,`@` are neutralized. |
| **T2.3** Pagination for bills/customers | I-23 | `/api/bills` supports `limit`/`offset` (or cursor); frontend uses it. |
| **T2.4** Move amount-in-words to backend (optional) | — | `amount_words` returned by API; frontend prefers it, falls back. |
| **T2.5** Auth decision | I-17 | Document whether app is single-user local; if multi-user, add auth (out of scope for now). |
| **T2.6** Refactor app into modules | I-20, I-21 | Blueprints/helpers split; `app.py` thin. |

---

## 5. Testing Strategy

### 5.1 Unit tests (new)
- `parse_time()` (`app.py:80-91`): valid `HH:MM`, 12-hour variants, empty/invalid inputs.
- `next_bill_id()`: first of day returns `.../001`; increments; resets per date (mock `now`).
- Calculation: hours, subtotal, tax, total rounding parity (compare to frontend formula).
- `bill_dict()`: includes `bill_id` alias.

### 5.2 Integration tests (new, using temp DB)
- Set `DATABASE_PATH` to a temp file; call `initialize_db()`.
- `POST /api/bills` valid payload → 201, persisted row, invoice_no format.
- `POST /api/bills` missing customer/work/time → 400.
- `POST /api/bills` duration > 24 h or negative rate/tax → 400.
- `GET /api/bills`, `GET /api/bills/<id>` (404 case).
- `GET /api/customers` field names and aggregation.
- `GET /api/daily-report?date=...` filtering and totals; invalid date → 400.
- `GET /export-bills` returns CSV with header + BOM.

### 5.3 Concurrency test
- Spawn N threads POSTing bills with same date; assert all invoice_no unique.

### 5.4 Frontend checks (manual + optional Playwright)
- New Bill: calculate, print, save, clear.
- "Other" work description flow.
- History search/filter and View.
- Customers totals.
- Daily report XSS payload renders as text.
- Mobile/print layouts.

### 5.5 Acceptance gate
- All P0 issues closed; pytest green; manual smoke checklist passed; Vercel preview deploy succeeds.

---

## 6. Deployment Notes (Vercel)

- **Filesystem:** Vercel serverless functions have a read-only filesystem except `/tmp`. The current `DB_PATH = app.py dir` (`app.py:15`) and import-time `initialize_db()` (`app.py:466`) will fail. Fix via env-based path (T0.1) and consider `/tmp` for ephemeral dev, but **data in `/tmp` is not durable** across cold starts/instances. For real persistence, migrate to a managed database (e.g., Postgres/Supabase) — flagged as a known limitation.
- **Entry point:** Vercel Python runtime discovers the `app` object in `app.py`; keep `app = Flask(__name__)` at module scope (`app.py:9`).
- **Config:** `vercel.json` is currently just a schema stub; add build/route config for Flask.
- **Dependencies:** pin Flask in `requirements.txt`; add gunicorn only if running locally (Vercel does not use it).
- **Debug:** disable debug in production (T1.5).
- **Cold starts:** first request may run `initialize_db()`; keep it fast/idempotent.
- **Observability:** add structured logging; Vercel captures stdout.

---

## 7. Risk & Mitigation

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Data loss on Vercel due to ephemeral `/tmp` SQLite | High | High | Document limitation; migrate to managed DB for production. |
| Duplicate invoice IDs under concurrent saves | Medium | High | Atomic numbering + unique constraint + client retry (T1.1). |
| XSS in daily report | High (if exploited) | Medium | Escape all interpolated fields (T0.7). |
| Broken core flows (no save, pages not loading) | Certain | High | Phase 0 tasks T0.2–T0.6. |
| Frontend/backend drift in calculation | Medium | Medium | Shared validation tests (5.1/5.2). |
| Scope creep (auth, PDF lib) | Medium | Medium | Keep P2 items optional; document out-of-scope. |

---

## 8. Out of Scope (for now)

- User authentication / multi-tenant accounts.
- Server-side PDF generation (current approach uses browser print).
- Editing/deleting bills.
- Replacing SQLite with Postgres (recommended but not implemented in this plan).
- Visual redesign.

---

*End of plan.md*

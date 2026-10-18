# System Design Document — CMS EARTH MOVERS Billing

**Repository:** `/home/coder/billing/BILLING`
**Date:** Sat Oct 17, 2026
**Status:** As-built design derived from code review (no code changes).

---

## 1. Purpose & Scope

This document describes the architecture, data model, API, and key logic of the CMS EARTH MOVERS billing application. It is grounded in the actual repository state (`app.py`, `templates/*`, `static/*`, `requirements.txt`, `vercel.json`) and identifies known limitations.

---

## 2. Architecture Overview

The application is a traditional server-rendered web app with a small JSON API:

```
┌─────────────────────────────────────────────────────────────┐
│ Browser (HTML/CSS/JS)                                       │
│  templates/* + static/style.css + static/script.js          │
│  (index.html also embeds a duplicate inline script)         │
└──────────────┬──────────────────────────────────────────────┘
               │ HTTP (pages + /api/* + /export-bills)
┌──────────────▼──────────────────────────────────────────────┐
│ Flask app (app.py)                                          │
│  - Jinja rendering                                          │
│  - REST-ish JSON endpoints                                  │
│  - CSV export                                               │
└──────────────┬──────────────────────────────────────────────┘
               │ sqlite3
┌──────────────▼──────────────────────────────────────────────┐
│ SQLite file jcp_billing.db (DB_PATH = app.py dir)           │
│  - single table: bills                                      │
└─────────────────────────────────────────────────────────────┘
               │
               ▼
        Vercel serverless (target) — empty vercel.json
```

- **Pattern:** Monolithic Flask app; single module `app.py` (469 lines).
- **Rendering:** Jinja2 templates extending `templates/base.html`.
- **State:** Server-side SQLite; frontend caches bills/customers in JS arrays for filtering.
- **Timezone:** Indian Standard Time (IST, UTC+5:30) defined as `IST = timezone(timedelta(hours=5, minutes=30))` (`app.py:12`).
- **No authentication, no background jobs, no message queue.**

---

## 3. Component Breakdown

### 3.1 Backend (`app.py`)

| Area | Lines | Responsibility |
|---|---|---|
| App init & config | `app.py:9-15` | Flask app, IST, `DB_PATH` |
| DB helpers | `app.py:22-50` | `get_db()`, `initialize_db()` |
| Bill helpers | `app.py:57-97` | `next_bill_id()`, `parse_time()`, `bill_dict()` |
| Web pages | `app.py:107-130` | `/`, `/history`, `/customers`, `/about`, `/daily-report` |
| Bills API | `app.py:137-308` | GET list, GET by id, POST create |
| Customers API | `app.py:315-332` | Aggregated customer list |
| Daily report API | `app.py:339-383` | Filtered bills + totals by date |
| CSV export | `app.py:390-459` | `/export-bills` |
| Startup | `app.py:466-469` | `initialize_db()`, dev server |

### 3.2 Frontend

- `templates/base.html`: layout, nav, IST clock, includes `static/script.js`.
- `templates/index.html`: New Bill form + invoice preview + **inline duplicate script** (`index.html:410-621`).
- `templates/history.html`: search table; `{% block page_script %}` calls `loadHistory()` (dropped by base).
- `templates/customers.html`: search table; calls `loadCustomers()` (dropped by base).
- `templates/daily_report.html`: date picker + table rendered via inline script + `innerHTML`.
- `templates/about.html`: static info.
- `static/script.js`: shared logic (calculation, save, history, customers, clock). ~469 lines.
- `static/style.css`: shared styles (349 lines). `index.html` also has ~266 lines of inline CSS.
- `static/JCB.jpg`: logo asset.

### 3.3 Data

- Single SQLite database file `jcp_billing.db` in app directory.
- Single table `bills` (see §4).

---

## 4. Data Model / Schema

Table `bills` (`app.py:31-47`):

| Column | Type | Constraints / Default | Notes |
|---|---|---|---|
| `id` | INTEGER | PRIMARY KEY AUTOINCREMENT | Internal DB id; used by `/api/bills/<int:bill_id>` |
| `invoice_no` | TEXT | UNIQUE NOT NULL | Public Bill ID, e.g. `CMS26/10/16/001` |
| `created_at` | TEXT | — | IST wall-clock `YYYY-MM-DD HH:MM:SS` |
| `customer_name` | TEXT | NOT NULL | |
| `work_description` | TEXT | — | |
| `start_time` | TEXT | — | Original input string (e.g. `08:00`) |
| `end_time` | TEXT | — | Original input string |
| `total_hours` | REAL | DEFAULT 0 | |
| `rate` | REAL | DEFAULT 0 | Per hour |
| `tax_percentage` | REAL | DEFAULT 0 | |
| `subtotal` | REAL | DEFAULT 0 | |
| `tax_amount` | REAL | DEFAULT 0 | |
| `total_amount` | REAL | DEFAULT 0 | |

- Customers are **derived** by grouping `bills` by `customer_name` (`app.py:319-327`); no customers table.
- Indexes: implicit unique index on `invoice_no`; `id` primary key. No additional indexes.
- `bill_dict()` (`app.py:94-97`) adds `bill_id` alias = `invoice_no` for frontend compatibility.

---

## 5. API Contract

Base: same origin. Content-Type `application/json` unless noted.

### 5.1 Pages (HTML)

| Method | Path | Handler | Notes |
|---|---|---|---|
| GET | `/` | `index()` `app.py:107` | New Bill page |
| GET | `/history` | `history()` `app.py:112` | Bill History |
| GET | `/customers` | `customers()` `app.py:117` | Customers |
| GET | `/about` | `about()` `app.py:122` | About |
| GET | `/daily-report` | `daily_report()` `app.py:128` | Daily report page |

### 5.2 Bills

**GET /api/bills** (`app.py:137-149`)
- Response `200`: array of bill objects (newest first by `id`), each includes `bill_id` alias.

**GET /api/bills/<int:bill_id>** (`app.py:152-168`)
- Path param: internal DB `id`.
- Response `200`: bill object.
- Response `404`: `{"error":"Bill not found."}`

**POST /api/bills** (`app.py:170-308`)
- Request JSON:
```json
{
  "customer_name": "string (required)",
  "work_description": "string (required)",
  "start_time": "HH:MM (required)",
  "end_time": "HH:MM (required)",
  "rate": "number (>=0)",
  "tax_percentage": "number (0-100)"
}
```
- Validation:
  - `customer_name`, `work_description` required non-empty.
  - times parseable; duration > 0 and <= 24 h (next-day if end < start).
  - `rate >= 0`; `0 <= tax_percentage <= 100`.
- Response `201`: saved bill object (with server-generated `invoice_no`, `created_at`, totals).
- Response `400`: `{"error": "..."}`.
- Response `409`: `{"error":"Bill ID already exists. Please try again."}` (invoice collision).
- Response `500`: DB error.

### 5.3 Customers

**GET /api/customers** (`app.py:315-332`)
- Response `200`: array:
```json
[
  {
    "customer_name": "string",
    "total_bills": "integer",
    "total_amount": "number",
    "last_billing_date": "string (created_at)"
  }
]
```
- Sorted by `customer_name COLLATE NOCASE`.

### 5.4 Daily Report

**GET /api/daily-report?date=YYYY-MM-DD** (`app.py:339-383`)
- `date` optional; defaults to today IST.
- Response `200`:
```json
{
  "date": "YYYY-MM-DD",
  "bill_count": 0,
  "total_amount": 0.0,
  "bills": [
    {
      "id": 1,
      "invoice_no": "CMS...",
      "created_at": "YYYY-MM-DD HH:MM:SS",
      "customer_name": "...",
      "work_description": "...",
      "total_hours": 0.0,
      "total_amount": 0.0
    }
  ]
}
```
- Response `400`: invalid date.

### 5.5 Export

**GET /export-bills** (`app.py:390-459`)
- Response `200`: CSV file `cms_bills_backup.csv`, `text/csv; charset=utf-8`, UTF-8 BOM, columns listed in `app.py:417-429`.

---

## 6. Request / Response Flows

### 6.1 Create bill (intended flow)

1. User fills form on `/` (`templates/index.html`).
2. Frontend `calculateBill()` (`static/script.js:191-207`) validates and computes totals; `renderBill()` updates DOM.
3. User clicks "Save Bill" (currently missing button — see plan T0.4).
4. `saveBill()` (`static/script.js:209-237`) POSTs `readForm()` payload to `/api/bills`.
5. Backend validates, computes totals (`app.py:231-237`), generates invoice_no (`app.py:245`), inserts row, returns saved bill (`app.py:308`).
6. Frontend stores `currentBillId`/`lastSavedBill`, re-renders, calls `loadHistory()` and `loadCustomers()`.

### 6.2 View history

1. `/history` page loads; (intended) `loadHistory()` fetches `/api/bills`.
2. `filterHistory()` renders rows with textContent (safe).
3. "View" calls `loadBill(id)` → `GET /api/bills/<id>`; on index page populates form and renders.

### 6.3 Customers

1. `/customers` page loads; (intended) `loadCustomers()` fetches `/api/customers`.
2. `filterCustomers()` renders rows. **Currently broken** due to field-name mismatch (see plan I-03).

### 6.4 Daily report

1. `/daily-report` page sets today's date (IST) and calls `loadReport()`.
2. Fetches `/api/daily-report?date=...`.
3. Renders totals and table via `innerHTML` (XSS risk).

### 6.5 Export

1. User clicks "Export Bills" nav link → `GET /export-bills`.
2. Backend dumps all bills to CSV with BOM.

---

## 7. Billing ID Generation Logic

- Format: `CMS{YY}/{MM}/{DD}/{NNN}` (`app.py:59`), e.g. `CMS26/10/16/001`.
- Date components from `now` (IST) passed into `next_bill_id(conn, now)` (`app.py:57`).
- Prefix: `"CMS" + now.strftime("%y/%m/%d") + "/"`.
- Sequence: query latest `invoice_no LIKE prefix%` ordered by `invoice_no DESC`, parse trailing number after last `/`, increment; default 1 (`app.py:61-77`).
- Uniqueness enforced by `UNIQUE` constraint on `invoice_no` (`app.py:34`).
- **Race condition:** two concurrent requests can read the same "latest" and generate the same ID; the second insert raises `IntegrityError` → 409 (`app.py:281-287`) with no automatic retry. See plan T1.1.

---

## 8. Time Handling

- **IST:** `IST = timezone(timedelta(hours=5, minutes=30))` (`app.py:12`).
- **created_at:** `datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S")` (`app.py:239-240`) — naive wall-clock string in IST.
- **Input parsing:** `parse_time()` (`app.py:80-91`) accepts `%H:%M`, `%I:%M %p`, `%I %p`.
- **Next-day:** in `create_bill()`, if `end < start`, `end += timedelta(days=1)` (`app.py:199-201`). Frontend mirrors with minutes += 1440 (`static/script.js:49-50`).
- **Duration cap:** backend rejects `<= 0` or `> 24` hours (`app.py:207-210`).
- **Daily report date:** validated `YYYY-MM-DD`; filter uses `date(created_at) = ?` (`app.py:365`). Because `created_at` is IST wall-clock, date grouping matches IST calendar.
- **Frontend clock:** `Intl.DateTimeFormat` with `timeZone: "Asia/Kolkata"` (`static/script.js:428-442`, `base.html:160-165`).

---

## 9. Calculation Logic

Backend (`app.py:231-237`):
- `total_hours = (end - start).total_seconds() / 3600`, rounded to 2 decimals for storage.
- `subtotal = round(total_hours * rate, 2)`
- `tax_amount = round(subtotal * tax_percentage / 100, 2)`
- `total_amount = round(subtotal + tax_amount, 2)`

Frontend (`static/script.js:86-101`):
- `hours = (endMinutes - startMinutes) / 60` (with +1440 if negative).
- `subtotal = round(hours * rate, 2)`
- `taxAmount = round(subtotal * tax / 100, 2)`
- `total = round(subtotal + taxAmount, 2)`

Both use the same rounding approach (to 2 decimals). `amount_words` is computed client-side (`indianWords` / `toWords`); backend does not return it. Frontend falls back to `indianWords(bill.total_amount)` when `bill.amount_words` is absent (`static/script.js:181`).

---

## 10. Security Considerations

- **SQL injection:** Not present — all queries use parameterized `?` placeholders (e.g., `app.py:64`, `app.py:159`, `app.py:262`, `app.py:367`).
- **XSS:** **Present** — `templates/daily_report.html:51-59` builds table rows via `innerHTML` interpolating `invoice_no`, `customer_name`, `created_at` without escaping. Fix: DOM construction with textContent or escaping.
- **History/Customers rendering:** uses `insertCell().textContent` (`static/script.js:291`, `412-416`) — safe.
- **CSRF / Auth:** None implemented; app is intended for trusted local/single-user use. Documented as limitation.
- **Debug mode:** `app.run(debug=True)` (`app.py:469`) only runs under `__main__`; production uses module-level `app`. Still recommend env-gated debug.
- **CSV injection:** Export (`app.py:390-459`) writes raw values; spreadsheet formula injection possible.
- **Input validation:** Backend validates required fields, times, rate/tax ranges, date format. Missing: length caps and 24-hour client parity (frontend has caps).
- **Secrets:** None in repo; no API keys.

---

## 11. Deployment Architecture (Vercel)

- Target: Vercel serverless Python runtime.
- Current `vercel.json`: only JSON schema declaration (`vercel.json:1-3`) — no builds/routes.
- `requirements.txt`: `Flask` only.
- Entry point: module-level `app` object (`app.py:9`) discovered by Vercel.
- **Critical issue:** `DB_PATH = Path(__file__).with_name("jcp_billing.db")` (`app.py:15`) and import-time `initialize_db()` (`app.py:466`) attempt to write to the read-only app directory on Vercel → failure. Fix: env-based path (`/tmp` for ephemeral) or managed DB.
- **Persistence:** SQLite on `/tmp` is ephemeral across cold starts/instances. For durable data, migrate to managed Postgres.
- **Cold start:** `initialize_db()` runs per cold start; keep idempotent.
- **Static assets:** served by Flask via `url_for('static', ...)`; Vercel can serve `/static` directly if configured.
- **Observability:** app uses `app.logger.exception` on DB errors (`app.py:291`); Vercel captures stdout/logs.

---

## 12. Known Limitations

1. **No authentication** or multi-user support.
2. **Ephemeral SQLite** on Vercel; not suitable for durable production data without a managed DB.
3. **No edit/delete** of bills; re-saving creates a new bill.
4. **Duplicate frontend implementations** (inline script in `index.html` vs `static/script.js`) with mismatched element IDs (`billingId` vs `invoiceNumber`, etc.).
5. **Broken flows:** no Save button; History/Customers pages don't load (page_script block dropped); Customers totals undefined; "Other" crashes; `new-bill` scroll crash.
6. **XSS** in daily report.
7. **Invoice ID race condition** under concurrency.
8. **No pagination** — `GET /api/bills` returns all rows.
9. **No tests/CI.**
10. **`amount_words`** computed only on frontend; backend doesn't provide it.
11. **No server-side PDF** — relies on browser print dialog.
12. **Hardcoded footer year** `2026` (`base.html:151`).
13. **Nav logo** is a placeholder span, not `JCB.jpg` (`base.html:126`).
14. **Empty `vercel.json`** may require configuration for proper deployment.

---

*End of design.md*

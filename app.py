
from flask import Flask, render_template, request, jsonify, make_response
import sqlite3
import csv
import io
import os
import math
from pathlib import Path
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# Indian Standard Time (IST)
IST = timezone(timedelta(hours=5, minutes=30))

# Existing database. Env-aware so import never writes to a read-only dir (e.g. Vercel).
if os.environ.get("DATABASE_PATH"):
    DB_PATH = Path(os.environ["DATABASE_PATH"])
elif os.environ.get("VERCEL"):
    DB_PATH = Path("/tmp/jcp_billing.db")
else:
    DB_PATH = Path(__file__).with_name("jcp_billing.db")


# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.isolation_level = None
    return conn


def initialize_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS bills (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            invoice_no TEXT UNIQUE NOT NULL,
            created_at TEXT,
            customer_name TEXT NOT NULL,
            work_description TEXT,
            start_time TEXT,
            end_time TEXT,
            intime TEXT,
            outtime TEXT,
            break_time REAL DEFAULT 0,
            total_hours REAL DEFAULT 0,
            rate REAL DEFAULT 0,
            tax_percentage REAL DEFAULT 0,
            beta_rate REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            tax_amount REAL DEFAULT 0,
            beta_amount REAL DEFAULT 0,
            total_amount REAL DEFAULT 0
        )
    """)

    # Backward-compatible column migration for existing databases.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(bills)").fetchall()}
    for col, ddl in (
        ("intime", "ALTER TABLE bills ADD COLUMN intime TEXT"),
        ("outtime", "ALTER TABLE bills ADD COLUMN outtime TEXT"),
        ("break_time", "ALTER TABLE bills ADD COLUMN break_time REAL DEFAULT 0"),
        ("beta_rate", "ALTER TABLE bills ADD COLUMN beta_rate REAL DEFAULT 0"),
        ("beta_amount", "ALTER TABLE bills ADD COLUMN beta_amount REAL DEFAULT 0"),
    ):
        if col not in existing:
            conn.execute(ddl)

    conn.commit()
    conn.close()


# ==================================================
# BILL HELPERS
# ==================================================

def next_bill_id(conn, now):
    """Generate IDs like CMS26/10/16/001, reusing gaps after deletions."""
    prefix = "CMS" + now.strftime("%y/%m/%d") + "/"

    rows = conn.execute("""
        SELECT invoice_no
        FROM bills
        WHERE invoice_no LIKE ?
    """, (prefix + "%",)).fetchall()

    used = set()
    for r in rows:
        try:
            used.add(int(str(r["invoice_no"]).rsplit("/", 1)[-1]))
        except (ValueError, IndexError):
            continue

    number = 1
    while number in used:
        number += 1

    return f"{prefix}{number:03d}"


def parse_time(value):
    """Accept HTML time values and common 12-hour formats."""
    if not value:
        raise ValueError("Start time and end time are required.")

    text = str(value).strip().upper()
    # Allow compact forms like "8:00PM" or "8AM".
    if text and text[-2:] in ("AM", "PM") and " " not in text:
        text = text[:-2] + " " + text[-2:]
    for fmt in ("%H:%M", "%I:%M %p", "%I %p", "%I:%M%p", "%I%p"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue

    raise ValueError("Invalid time format.")


def _amount_in_words(amount):
    ones = ["Zero", "One", "Two", "Three", "Four", "Five", "Six", "Seven",
            "Eight", "Nine", "Ten", "Eleven", "Twelve", "Thirteen",
            "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen",
            "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty",
            "Seventy", "Eighty", "Ninety"]

    def under_1000(n):
        words = []
        if n >= 100:
            words.append(ones[n // 100] + " Hundred")
            n %= 100
        if n >= 20:
            words.append(tens[n // 10])
            n %= 10
        if n > 0:
            words.append(ones[n])
        return " ".join(words)

    amount = 0 if amount is None else amount
    paise_total = int(round(float(amount) * 100))
    rupees = paise_total // 100
    paise = paise_total % 100

    if rupees == 0:
        rupee_words = "Zero"
    else:
        parts = []
        for divisor, label in ((10000000, "Crore"), (100000, "Lakh"),
                               (1000, "Thousand")):
            part = rupees // divisor
            if part:
                parts.append(under_1000(part) + " " + label)
                rupees %= divisor
        if rupees:
            parts.append(under_1000(rupees))
        rupee_words = " ".join(parts)

    result = "Rupees " + rupee_words
    if paise:
        result += " and " + under_1000(paise) + " Paise"
    return result + " Only"


def bill_dict(row):
    result = dict(row)
    result["bill_id"] = result.get("invoice_no")
    result["amount_words"] = _amount_in_words(result.get("total_amount") or 0)
    return result


# ==================================================
# WEB PAGES
# ==================================================

# Important: the homepage endpoint is named "index".
# In base.html use url_for('index'), not url_for('home').

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/history")
def history():
    q = (request.args.get("q") or "").strip().lower()
    conn = get_db()
    rows = conn.execute("SELECT * FROM bills ORDER BY id DESC").fetchall()
    conn.close()
    bills = [bill_dict(r) for r in rows]
    if q:
        bills = [b for b in bills if any(
            q in str(b.get(k) or "").lower()
            for k in ("bill_id", "invoice_no", "customer_name", "work_description", "created_at")
        )]
    return render_template("history.html", bills=bills, q=q)


@app.route("/customers")
def customers():
    q = (request.args.get("q") or "").strip().lower()
    conn = get_db()
    rows = conn.execute("""
        SELECT customer_name, COUNT(*) AS total_bills,
               SUM(total_amount) AS total_amount,
               MAX(created_at) AS last_billing_date
        FROM bills GROUP BY customer_name
        ORDER BY customer_name COLLATE NOCASE
    """).fetchall()
    conn.close()
    customers = [dict(r) for r in rows]
    if q:
        customers = [c for c in customers if q in str(c.get("customer_name") or "").lower()]
    return render_template("customers.html", customers=customers, q=q)


@app.route("/about")
def about():
    return render_template("about.html")


# New Module 3: Daily Collection Report
@app.route("/daily-report")
def daily_report():
    today = datetime.now(IST).strftime("%Y-%m-%d")
    return render_template("daily_report.html", today=today)


# ==================================================
# BILLS API
# ==================================================

@app.route("/api/bills", methods=["GET"])
def get_bills():
    conn = get_db()

    rows = conn.execute("""
        SELECT *
        FROM bills
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    return jsonify([bill_dict(row) for row in rows])


@app.route("/api/bills/<int:bill_id>", methods=["GET"])
def get_bill_api(bill_id):
    conn = get_db()

    row = conn.execute("""
        SELECT *
        FROM bills
        WHERE id = ?
    """, (bill_id,)).fetchone()

    conn.close()

    if row is None:
        return jsonify({"error": "Bill not found."}), 404

    return jsonify(bill_dict(row))


@app.route("/api/bills", methods=["POST"])
def create_bill():
    data = request.get_json(silent=True) or {}

    customer_name = str(
        data.get("customer_name", "")
    ).strip()

    work_description = str(
        data.get("work_description", "")
    ).strip()

    if not customer_name:
        return jsonify({
            "error": "Customer name is required."
        }), 400

    if not work_description:
        return jsonify({
            "error": "Work description is required."
        }), 400

    if len(customer_name) > 150 or len(work_description) > 250:
        return jsonify({
            "error": "Customer name or work description is too long."
        }), 400

    try:
        intime_value = str(
            data.get("intime", data.get("start_time", ""))
        ).strip()
        outtime_value = str(
            data.get("outtime", data.get("end_time", ""))
        ).strip()

        break_time = float(data.get("break_time", data.get("breaktime", 0)))

        if not math.isfinite(break_time) or break_time < 0:
            return jsonify({
                "error": "Break time must be a non-negative number."
            }), 400

        start = parse_time(intime_value)
        end = parse_time(outtime_value)

        # End time before start time means work ended next day.
        if end < start:
            end += timedelta(days=1)

        total_hours = (
            (end - start).total_seconds() / 3600
        ) - break_time

        if (not math.isfinite(total_hours)
                or total_hours <= 0 or total_hours > 24):
            return jsonify({
                "error": "Work duration must be greater than 0 and no more than 24 hours."
            }), 400

        rate = float(data.get("rate", 0))
        beta_rate = float(data.get("beta_rate", data.get("beta", 0)))

        if (not math.isfinite(rate) or not math.isfinite(beta_rate)
                or rate < 0 or beta_rate < 0
                or rate > 100000000 or beta_rate > 100000000):
            return jsonify({
                "error": "Rate and beta must be non-negative and within limits."
            }), 400

        # Round once so the stored/displayed hours, subtotal and total agree.
        total_hours = round(total_hours, 2)

    except (ValueError, TypeError, OverflowError):
        return jsonify({
            "error": "Please enter valid time, rate, and beta values."
        }), 400

    subtotal = round(total_hours * rate, 2)
    beta_amount = round(total_hours * beta_rate, 2)
    total_amount = round(subtotal + beta_amount, 2)

    now = datetime.now(IST)
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")

    saved_id = None
    invoice_no = None

    for _ in range(5):
        conn = get_db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            invoice_no = next_bill_id(conn, now)

            cursor = conn.execute("""
                INSERT INTO bills (
                    invoice_no,
                    created_at,
                    customer_name,
                    work_description,
                    start_time,
                    end_time,
                    intime,
                    outtime,
                    break_time,
                    total_hours,
                    rate,
                    tax_percentage,
                    beta_rate,
                    subtotal,
                    tax_amount,
                    beta_amount,
                    total_amount
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                invoice_no,
                created_at,
                customer_name,
                work_description,
                intime_value,
                outtime_value,
                intime_value,
                outtime_value,
                break_time,
                round(total_hours, 2),
                rate,
                0,
                beta_rate,
                subtotal,
                0,
                beta_amount,
                total_amount
            ))

            conn.commit()
            saved_id = cursor.lastrowid
            conn.close()
            break

        except sqlite3.IntegrityError:
            conn.rollback()
            conn.close()
            continue

        except sqlite3.Error:
            conn.rollback()
            app.logger.exception("Failed to save bill")
            conn.close()

            return jsonify({
                "error": "Database error while saving the bill."
            }), 500

    if saved_id is None:
        return jsonify({
            "error": "Bill ID already exists. Please try again."
        }), 409

    conn = None

    conn = get_db()
    saved_bill = conn.execute("""
        SELECT *
        FROM bills
        WHERE id = ?
    """, (saved_id,)).fetchone()
    conn.close()

    return jsonify(bill_dict(saved_bill)), 201


@app.route("/api/bills/<int:bill_id>", methods=["DELETE"])
def delete_bill(bill_id):
    conn = get_db()
    try:
        cur = conn.execute("DELETE FROM bills WHERE id = ?", (bill_id,))
        conn.commit()
        if cur.rowcount == 0:
            conn.close()
            return jsonify({"error": "Bill not found."}), 404
    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to delete bill")
        conn.close()
        return jsonify({"error": "Database error while deleting the bill."}), 500
    conn.close()
    return jsonify({"message": "Bill deleted."}), 200


@app.route("/api/bills/<int:bill_id>", methods=["PUT"])
def update_bill(bill_id):
    data = request.get_json(silent=True) or {}

    customer_name = str(data.get("customer_name", "")).strip()
    work_description = str(data.get("work_description", "")).strip()

    if not customer_name or not work_description:
        return jsonify({"error": "Customer name and work description are required."}), 400
    if len(customer_name) > 150 or len(work_description) > 250:
        return jsonify({"error": "Customer name or work description is too long."}), 400

    try:
        intime_value = str(data.get("intime", data.get("start_time", ""))).strip()
        outtime_value = str(data.get("outtime", data.get("end_time", ""))).strip()
        break_time = float(data.get("break_time", data.get("breaktime", 0)))

        if not math.isfinite(break_time) or break_time < 0:
            return jsonify({"error": "Break time must be a non-negative number."}), 400

        start = parse_time(intime_value)
        end = parse_time(outtime_value)
        if end < start:
            end += timedelta(days=1)

        total_hours = ((end - start).total_seconds() / 3600) - break_time
        if (not math.isfinite(total_hours) or total_hours <= 0 or total_hours > 24):
            return jsonify({"error": "Work duration must be greater than 0 and no more than 24 hours."}), 400

        rate = float(data.get("rate", 0))
        beta_rate = float(data.get("beta_rate", data.get("beta", 0)))
        if (not math.isfinite(rate) or not math.isfinite(beta_rate)
                or rate < 0 or beta_rate < 0
                or rate > 100000000 or beta_rate > 100000000):
            return jsonify({"error": "Rate and beta must be non-negative and within limits."}), 400

        total_hours = round(total_hours, 2)
    except (ValueError, TypeError, OverflowError):
        return jsonify({"error": "Please enter valid time, rate, and beta values."}), 400

    subtotal = round(total_hours * rate, 2)
    beta_amount = round(total_hours * beta_rate, 2)
    total_amount = round(subtotal + beta_amount, 2)

    conn = get_db()
    try:
        cur = conn.execute("""
            UPDATE bills SET
                customer_name = ?,
                work_description = ?,
                start_time = ?,
                end_time = ?,
                intime = ?,
                outtime = ?,
                break_time = ?,
                total_hours = ?,
                rate = ?,
                tax_percentage = 0,
                beta_rate = ?,
                subtotal = ?,
                tax_amount = 0,
                beta_amount = ?,
                total_amount = ?
            WHERE id = ?
        """, (
            customer_name, work_description,
            intime_value, outtime_value,
            intime_value, outtime_value,
            break_time, total_hours,
            rate,
            beta_rate,
            subtotal,
            beta_amount, total_amount,
            bill_id
        ))
        conn.commit()
        if cur.rowcount == 0:
            conn.close()
            return jsonify({"error": "Bill not found."}), 404
    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to update bill")
        conn.close()
        return jsonify({"error": "Database error while updating the bill."}), 500
    conn.close()

    conn = get_db()
    saved = conn.execute("SELECT * FROM bills WHERE id = ?", (bill_id,)).fetchone()
    conn.close()
    return jsonify(bill_dict(saved)), 200



# ==================================================
# CUSTOMERS API
# ==================================================

@app.route("/api/customers", methods=["GET"])
def get_customers():
    conn = get_db()

    rows = conn.execute("""
        SELECT
            customer_name,
            COUNT(*) AS total_bills,
            SUM(total_amount) AS total_amount,
            MAX(created_at) AS last_billing_date
        FROM bills
        GROUP BY customer_name
        ORDER BY customer_name COLLATE NOCASE
    """).fetchall()

    conn.close()

    return jsonify([dict(row) for row in rows])


# ==================================================
# MODULE 3: DAILY COLLECTION REPORT
# ==================================================

@app.route("/api/daily-report", methods=["GET"])
def daily_report_api():
    report_date = request.args.get(
        "date",
        datetime.now(IST).strftime("%Y-%m-%d")
    )

    try:
        datetime.strptime(report_date, "%Y-%m-%d")
    except ValueError:
        return jsonify({
            "error": "Invalid date. Use YYYY-MM-DD."
        }), 400

    conn = get_db()

    rows = conn.execute("""
        SELECT
            id,
            invoice_no,
            created_at,
            customer_name,
            work_description,
            total_hours,
            total_amount
        FROM bills
        WHERE date(created_at) = ?
        ORDER BY created_at DESC, id DESC
    """, (report_date,)).fetchall()

    conn.close()

    bills = [dict(row) for row in rows]

    total_collection = round(
        sum(float(bill["total_amount"] or 0) for bill in bills),
        2
    )

    return jsonify({
        "date": report_date,
        "bill_count": len(bills),
        "total_amount": total_collection,
        "bills": bills
    })


# ==================================================
# MODULE 4: EXPORT BILLS TO CSV
# ==================================================

@app.route("/export-bills", methods=["GET"])
def export_bills():
    conn = get_db()

    rows = conn.execute("""
        SELECT
            invoice_no,
            created_at,
            customer_name,
            work_description,
            start_time,
            end_time,
            intime,
            outtime,
            break_time,
            total_hours,
            rate,
            tax_percentage,
            beta_rate,
            subtotal,
            tax_amount,
            beta_amount,
            total_amount
        FROM bills
        ORDER BY id DESC
    """).fetchall()

    conn.close()

    output = io.StringIO(newline="")
    writer = csv.writer(output)

    writer.writerow([
        "Bill ID",
        "Created At",
        "Customer Name",
        "Work Description",
        "Start Time",
        "End Time",
        "In Time",
        "Out Time",
        "Break Time",
        "Total Hours",
        "Rate",
        "Tax Percentage",
        "Beta Rate",
        "Subtotal",
        "Tax Amount",
        "Beta Amount",
        "Total Amount"
    ])

    def csv_safe(value):
        if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + value
        return value

    for row in rows:
        writer.writerow([
            csv_safe(row["invoice_no"]),
            csv_safe(row["created_at"]),
            csv_safe(row["customer_name"]),
            csv_safe(row["work_description"]),
            csv_safe(row["start_time"]),
            csv_safe(row["end_time"]),
            csv_safe(row["intime"]),
            csv_safe(row["outtime"]),
            row["break_time"],
            row["total_hours"],
            row["rate"],
            row["tax_percentage"],
            row["beta_rate"],
            row["subtotal"],
            row["tax_amount"],
            row["beta_amount"],
            row["total_amount"]
        ])

    response = make_response(
        "\ufeff" + output.getvalue()
    )

    response.headers["Content-Type"] = (
        "text/csv; charset=utf-8"
    )
    response.headers["Content-Disposition"] = (
        "attachment; filename=cms_bills_backup.csv"
    )

    return response


# ==================================================
# HTMX PARTIALS
# ==================================================

@app.route("/partials/history")
def partial_history():
    q = (request.args.get("q") or "").strip().lower()
    conn = get_db()
    rows = conn.execute("SELECT * FROM bills ORDER BY id DESC").fetchall()
    conn.close()
    bills = [bill_dict(r) for r in rows]
    if q:
        bills = [b for b in bills if any(
            q in str(b.get(k) or "").lower()
            for k in ("bill_id", "invoice_no", "customer_name", "work_description", "created_at")
        )]
    return render_template("partials/history_rows.html", bills=bills)


@app.route("/partials/customers")
def partial_customers():
    q = (request.args.get("q") or "").strip().lower()
    conn = get_db()
    rows = conn.execute("""
        SELECT customer_name, COUNT(*) AS total_bills,
               SUM(total_amount) AS total_amount,
               MAX(created_at) AS last_billing_date
        FROM bills GROUP BY customer_name
        ORDER BY customer_name COLLATE NOCASE
    """).fetchall()
    conn.close()
    customers = [dict(r) for r in rows]
    if q:
        customers = [c for c in customers if q in str(c.get("customer_name") or "").lower()]
    return render_template("partials/customers_rows.html", customers=customers)


@app.route("/partials/daily-report")
def partial_daily_report():
    report_date = request.args.get("date", datetime.now(IST).strftime("%Y-%m-%d"))
    try:
        datetime.strptime(report_date, "%Y-%m-%d")
    except ValueError:
        return "<tr><td colspan='4'>Invalid date.</td></tr>", 400
    conn = get_db()
    rows = conn.execute("""
        SELECT invoice_no, customer_name, created_at, total_amount
        FROM bills WHERE date(created_at) = ?
        ORDER BY created_at DESC, id DESC
    """, (report_date,)).fetchall()
    conn.close()
    bills = [dict(r) for r in rows]
    total = round(sum(float(b["total_amount"] or 0) for b in bills), 2)
    return render_template("partials/daily_report_rows.html", bills=bills, total=total, count=len(bills))

# ==================================================
# START APPLICATION
# ==================================================

initialize_db()

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")

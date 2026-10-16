
from flask import Flask, render_template, request, jsonify, make_response
import sqlite3
import csv
import io
from pathlib import Path
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# Indian Standard Time (IST)
IST = timezone(timedelta(hours=5, minutes=30))

# Existing database
DB_PATH = Path(__file__).with_name("jcp_billing.db")


# ==================================================
# DATABASE
# ==================================================

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initialize_db():
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
            total_hours REAL DEFAULT 0,
            rate REAL DEFAULT 0,
            tax_percentage REAL DEFAULT 0,
            subtotal REAL DEFAULT 0,
            tax_amount REAL DEFAULT 0,
            total_amount REAL DEFAULT 0
        )
    """)

    conn.commit()
    conn.close()


# ==================================================
# BILL HELPERS
# ==================================================

def next_bill_id(conn, now):
    """Generate IDs like CMS26/10/16/001."""
    prefix = "CMS" + now.strftime("%y/%m/%d") + "/"

    row = conn.execute("""
        SELECT invoice_no
        FROM bills
        WHERE invoice_no LIKE ?
        ORDER BY invoice_no DESC
        LIMIT 1
    """, (prefix + "%",)).fetchone()

    number = 1

    if row:
        try:
            number = int(row["invoice_no"].rsplit("/", 1)[-1]) + 1
        except (ValueError, IndexError):
            number = 1

    return f"{prefix}{number:03d}"


def parse_time(value):
    """Accept HTML time values and common 12-hour formats."""
    if not value:
        raise ValueError("Start time and end time are required.")

    for fmt in ("%H:%M", "%I:%M %p", "%I %p"):
        try:
            return datetime.strptime(value.strip(), fmt)
        except ValueError:
            continue

    raise ValueError("Invalid time format.")


def bill_dict(row):
    result = dict(row)
    result["bill_id"] = result.get("invoice_no")
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
    return render_template("history.html")


@app.route("/customers")
def customers():
    return render_template("customers.html")


@app.route("/about")
def about():
    return render_template("about.html")


# New Module 3: Daily Collection Report
@app.route("/daily-report")
def daily_report():
    return render_template("daily_report.html")


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

    try:
        start_value = str(data.get("start_time", "")).strip()
        end_value = str(data.get("end_time", "")).strip()

        start = parse_time(start_value)
        end = parse_time(end_value)

        # End time before start time means work ended next day.
        if end < start:
            end += timedelta(days=1)

        total_hours = (
            end - start
        ).total_seconds() / 3600

        if total_hours <= 0 or total_hours > 24:
            return jsonify({
                "error": "Work duration must be greater than 0 and no more than 24 hours."
            }), 400

        rate = float(data.get("rate", 0))
        tax_percentage = float(
            data.get("tax_percentage", 0)
        )

        if (
            rate < 0
            or tax_percentage < 0
            or tax_percentage > 100
        ):
            return jsonify({
                "error": "Rate must be non-negative and tax must be between 0 and 100."
            }), 400

    except (ValueError, TypeError, OverflowError):
        return jsonify({
            "error": "Please enter valid time, rate, and tax values."
        }), 400

    subtotal = round(total_hours * rate, 2)
    tax_amount = round(
        subtotal * tax_percentage / 100, 2
    )
    total_amount = round(
        subtotal + tax_amount, 2
    )

    now = datetime.now(IST)
    created_at = now.strftime("%Y-%m-%d %H:%M:%S")

    conn = get_db()

    try:
        invoice_no = next_bill_id(conn, now)

        cursor = conn.execute("""
            INSERT INTO bills (
                invoice_no,
                created_at,
                customer_name,
                work_description,
                start_time,
                end_time,
                total_hours,
                rate,
                tax_percentage,
                subtotal,
                tax_amount,
                total_amount
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            invoice_no,
            created_at,
            customer_name,
            work_description,
            start_value,
            end_value,
            round(total_hours, 2),
            rate,
            tax_percentage,
            subtotal,
            tax_amount,
            total_amount
        ))

        conn.commit()
        saved_id = cursor.lastrowid

    except sqlite3.IntegrityError:
        conn.rollback()
        conn.close()

        return jsonify({
            "error": "Bill ID already exists. Please try again."
        }), 409

    except sqlite3.Error:
        conn.rollback()
        app.logger.exception("Failed to save bill")
        conn.close()

        return jsonify({
            "error": "Database error while saving the bill."
        }), 500

    conn.close()

    conn = get_db()
    saved_bill = conn.execute("""
        SELECT *
        FROM bills
        WHERE id = ?
    """, (saved_id,)).fetchone()
    conn.close()

    return jsonify(bill_dict(saved_bill)), 201


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
            total_hours,
            rate,
            tax_percentage,
            subtotal,
            tax_amount,
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
        "Total Hours",
        "Rate",
        "Tax Percentage",
        "Subtotal",
        "Tax Amount",
        "Total Amount"
    ])

    for row in rows:
        writer.writerow([
            row["invoice_no"],
            row["created_at"],
            row["customer_name"],
            row["work_description"],
            row["start_time"],
            row["end_time"],
            row["total_hours"],
            row["rate"],
            row["tax_percentage"],
            row["subtotal"],
            row["tax_amount"],
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
# START APPLICATION
# ==================================================

initialize_db()

if __name__ == "__main__":
    app.run(debug=True)

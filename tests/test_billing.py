import re

import app


def test_parse_time():
    assert app.parse_time("08:00").hour == 8
    assert app.parse_time("8:00 PM").hour == 20
    try:
        app.parse_time("")
        assert False
    except ValueError:
        pass
    try:
        app.parse_time("nope")
        assert False
    except ValueError:
        pass


def test_bill_dict_alias():
    conn = app.get_db()
    app.initialize_db()
    conn.execute("DELETE FROM bills")
    conn.execute(
        "INSERT INTO bills (invoice_no, customer_name) VALUES (?, ?)",
        ("CMS26/10/16/001", "Acme"),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM bills").fetchone()
    d = app.bill_dict(row)
    assert d["bill_id"] == "CMS26/10/16/001"
    assert "amount_words" in d
    conn.close()


def test_create_bill_valid(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "12:30",
        "rate": 1500,
        "tax_percentage": 5,
    }
    r = client.post("/api/bills", json=payload)
    assert r.status_code == 201
    data = r.get_json()
    assert re.match(r"CMS\d{2}/\d{2}/\d{2}/\d{3}", data["invoice_no"])
    assert data["total_hours"] == 4.5
    assert data["total_amount"] == 6750.0


def test_create_bill_missing_fields(client):
    r = client.post("/api/bills", json={"customer_name": "Acme"})
    assert r.status_code == 400


def test_create_bill_invalid_duration(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "08:00",
        "rate": 100,
        "tax_percentage": 0,
    }
    r = client.post("/api/bills", json=payload)
    assert r.status_code == 400


def test_get_bills_and_one(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "10:00",
        "rate": 100,
        "tax_percentage": 0,
    }
    r = client.post("/api/bills", json=payload)
    bid = r.get_json()["id"]
    r2 = client.get("/api/bills")
    assert r2.status_code == 200
    assert len(r2.get_json()) == 1
    r3 = client.get(f"/api/bills/{bid}")
    assert r3.status_code == 200
    r4 = client.get("/api/bills/99999")
    assert r4.status_code == 404


def test_customers_mapping(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "10:00",
        "rate": 100,
        "tax_percentage": 0,
    }
    client.post("/api/bills", json=payload)
    r = client.get("/api/customers")
    assert r.status_code == 200
    data = r.get_json()
    assert data[0]["total_bills"] == 1
    assert data[0]["customer_name"] == "Acme"
    assert "last_billing_date" in data[0]


def test_daily_report(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "10:00",
        "rate": 100,
        "tax_percentage": 0,
    }
    client.post("/api/bills", json=payload)
    from datetime import datetime, timezone, timedelta

    ist = timezone(timedelta(hours=5, minutes=30))
    today = datetime.now(ist).strftime("%Y-%m-%d")
    r = client.get(f"/api/daily-report?date={today}")
    assert r.status_code == 200
    data = r.get_json()
    assert data["bill_count"] == 1
    assert data["total_amount"] == 200.0
    r2 = client.get("/api/daily-report?date=not-a-date")
    assert r2.status_code == 400


def test_export_csv(client):
    payload = {
        "customer_name": "Acme",
        "work_description": "Road work",
        "start_time": "08:00",
        "end_time": "10:00",
        "rate": 100,
        "tax_percentage": 0,
    }
    client.post("/api/bills", json=payload)
    r = client.get("/export-bills")
    assert r.status_code == 200
    assert r.data.startswith(b"\xef\xbb\xbf")
    assert b"Bill ID" in r.data


def test_next_bill_id_increments():
    import datetime as dt

    conn = app.get_db()
    app.initialize_db()
    conn.execute("DELETE FROM bills")
    conn.commit()
    now = dt.datetime.now(app.IST)
    first = app.next_bill_id(conn, now)
    # insert it
    conn.execute(
        "INSERT INTO bills (invoice_no, customer_name) VALUES (?, ?)",
        (first, "X"),
    )
    conn.commit()
    second = app.next_bill_id(conn, now)
    assert first != second
    assert second.endswith("002")
    conn.close()


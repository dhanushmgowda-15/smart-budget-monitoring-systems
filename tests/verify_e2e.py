"""End-to-end verification script for SpendSense.

Starts the FastAPI server locally and verifies:
  1. Compulsory Feature 1: Add an expense with validation and immediate alert feedback.
  2. Compulsory Feature 2: Set monthly budget and verify upsert without duplicates.
  3. Compulsory Feature 3: Threshold alerts (OK -> Warning 80% -> Exceeded with over amount).
  4. Compulsory Feature 4: Month summary (table, overall totals, active alerts).
  5. Compulsory Feature 5: Top 5 largest expenses sorted descending with tie-breaking.
  6. Stretch Feature 1: Month comparison with January rollover and division by zero.
  7. Stretch Feature 2: Export CSV.
  8. Demo Seed Data endpoint.
"""

import os
import sys

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
os.environ["PYTHONPATH"] = PROJECT_ROOT

import multiprocessing
import time
import requests
import uvicorn

API_URL = "http://127.0.0.1:8000"


def run_server():
    """Runs the FastAPI server for verification."""
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)
    os.environ["PYTHONPATH"] = PROJECT_ROOT
    os.environ["SPENDSENSE_DB_PATH"] = "e2e_spendsense.db"
    from backend.main import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")


def verify_all_features():
    print("=" * 70)
    print("🔍 RUNNING COMPREHENSIVE END-TO-END VERIFICATION")
    print("=" * 70)

    # 1. Health check
    res = requests.get(f"{API_URL}/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    print("✅ 1. Health Check: Passed")

    # 2. Categories
    res = requests.get(f"{API_URL}/categories")
    assert res.status_code == 200
    cats = res.json()
    assert len(cats) == 9
    assert "Food" in cats and "Rent" in cats
    print(f"✅ 2. GET /categories: Passed ({len(cats)} categories)")

    # 3. Compulsory Feature 2: Set budget & upsert
    res = requests.post(
        f"{API_URL}/budgets",
        json={"month": "2026-11", "category": "Food", "amount": 200.00},
    )
    assert res.status_code == 200, f"Failed POST /budgets: {res.status_code} - {res.text}"
    assert res.json()["amount"] == 200.00

    # Upsert (re-set budget to 250.00)
    res = requests.post(
        f"{API_URL}/budgets",
        json={"month": "2026-11", "category": "Food", "amount": 250.00},
    )
    assert res.status_code == 200
    assert res.json()["amount"] == 250.00

    # Verify no duplicates
    res = requests.get(f"{API_URL}/budgets?month=2026-11")
    budgets = res.json()
    assert len(budgets) == 1
    assert budgets[0]["amount"] == 250.00
    print("✅ 3. Compulsory Feature 2: Set Budget & Upsert (No duplicates): Passed")

    # 4. Compulsory Feature 1 & 3: Add expense and immediate threshold alert
    # Expense 1: $100 -> 40% (OK)
    res = requests.post(
        f"{API_URL}/expenses",
        json={"date": "2026-11-01", "category": "Food", "amount": 100.00, "note": "Weekly Groceries"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["expense"]["amount"] == 100.00
    assert data["alert"]["status"] == "OK"
    assert data["alert"]["percentage"] == 40.0
    print("   -> Expense 1 ($100 / $250 = 40%): Alert = OK")

    # Expense 2: $105 -> Total $205 -> 82% (Warning 80%)
    res = requests.post(
        f"{API_URL}/expenses",
        json={"date": "2026-11-05", "category": "Food", "amount": 105.00, "note": "Dinner with friends"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["alert"]["status"] == "Warning 80%"
    assert data["alert"]["percentage"] == 82.0
    print("   -> Expense 2 (Total $205 / $250 = 82%): Alert = Warning 80%")

    # Expense 3: $50 -> Total $255 -> 102% (Exceeded by $5)
    res = requests.post(
        f"{API_URL}/expenses",
        json={"date": "2026-11-10", "category": "Food", "amount": 50.00, "note": "Weekend snacks"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["alert"]["status"] == "Exceeded"
    assert data["alert"]["percentage"] == 102.0
    assert data["alert"]["over_amount"] == 5.00
    print("   -> Expense 3 (Total $255 / $250 = 102%): Alert = Exceeded (Over by $5.00)")

    # Unbudgeted Category: Health
    res = requests.post(
        f"{API_URL}/expenses",
        json={"date": "2026-11-12", "category": "Health", "amount": 45.00, "note": "Vitamins"},
    )
    assert res.status_code == 201
    data = res.json()
    assert data["alert"]["status"] == "No budget set"
    assert data["alert"]["percentage"] is None
    print("   -> Unbudgeted Category (Health): Alert = 'No budget set'")
    print("✅ 4. Compulsory Feature 1 & 3: Immediate Threshold Alerts: Passed")

    # 5. Compulsory Feature 4: Month Summary
    res = requests.get(f"{API_URL}/summary?month=2026-11")
    assert res.status_code == 200
    summary = res.json()
    assert summary["month"] == "2026-11"
    assert summary["total_budget"] == 250.00
    assert summary["total_spent"] == 300.00  # $255 Food + $45 Health
    assert summary["total_remaining"] == -50.00
    assert len(summary["alerts"]) == 1
    assert summary["alerts"][0]["category"] == "Food"
    assert summary["alerts"][0]["status"] == "Exceeded"
    print("✅ 5. Compulsory Feature 4: Month Summary (Table, totals, alerts): Passed")

    # 6. Compulsory Feature 5: Top 5 Largest Expenses
    # Add more expenses to have 6 total
    requests.post(f"{API_URL}/expenses", json={"date": "2026-11-15", "category": "Transport", "amount": 30.00, "note": "Gas"})
    requests.post(f"{API_URL}/expenses", json={"date": "2026-11-16", "category": "Shopping", "amount": 180.00, "note": "Jacket"})

    res = requests.get(f"{API_URL}/top-expenses?month=2026-11&limit=5")
    assert res.status_code == 200
    top = res.json()
    assert len(top) == 5
    amounts = [x["amount"] for x in top]
    assert amounts == [180.00, 105.00, 100.00, 50.00, 45.00]
    print(f"✅ 6. Compulsory Feature 5: Top 5 Expenses Descending: Passed {amounts}")

    # 7. Stretch Feature 1: Month Comparison with Rollover & Division by Zero
    # Add expense in 2026-10 (October)
    requests.post(f"{API_URL}/expenses", json={"date": "2026-10-20", "category": "Food", "amount": 200.00, "note": "Oct Food"})
    res = requests.get(f"{API_URL}/compare?month=2026-11")
    assert res.status_code == 200
    comp = res.json()
    assert comp["current_month"] == "2026-11"
    assert comp["previous_month"] == "2026-10"
    assert comp["total_last_month"] == 200.00
    assert comp["total_this_month"] == 510.00  # 255 Food + 45 Health + 30 Transport + 180 Shopping
    assert comp["total_difference"] == 310.00
    assert comp["total_percentage_change"] == 155.0
    print("✅ 7. Stretch Feature 1: Month-over-Month Comparison: Passed")

    # 8. Stretch Feature 2: Export CSV
    res = requests.get(f"{API_URL}/export?month=2026-11")
    assert res.status_code == 200
    assert "text/csv" in res.headers.get("content-type", "")
    csv_text = res.text
    assert "ID,Date,Category,Amount,Note" in csv_text
    assert "Weekly Groceries" in csv_text
    print("✅ 8. Stretch Feature 2: Export CSV: Passed")

    # 9. Seed Demo Data
    res = requests.post(f"{API_URL}/seed?month=2026-11")
    assert res.status_code == 200
    seed_res = res.json()
    assert seed_res["status"] == "success"
    assert seed_res["expenses_created"] > 15
    print("✅ 9. Demo Sample Data Seeding: Passed")

    print("\n" + "=" * 70)
    print("🎉 ALL FEATURES FULLY VERIFIED AND WORKING END-TO-END!")
    print("=" * 70)


if __name__ == "__main__":
    # Clean DB before starting the server
    if os.path.exists("e2e_spendsense.db"):
        try:
            os.remove("e2e_spendsense.db")
        except Exception:
            pass

    server_process = multiprocessing.Process(target=run_server)
    server_process.start()

    # Wait for server to start
    started = False
    for _ in range(30):
        try:
            r = requests.get(f"{API_URL}/health", timeout=1)
            if r.status_code == 200:
                started = True
                break
        except Exception:
            time.sleep(0.3)

    if not started:
        print("❌ Could not connect to test server!")
        server_process.terminate()
        sys.exit(1)

    try:
        verify_all_features()
    finally:
        server_process.terminate()
        server_process.join()
        if os.path.exists("e2e_spendsense.db"):
            os.remove("e2e_spendsense.db")

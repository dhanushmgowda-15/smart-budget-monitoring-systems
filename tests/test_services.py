"""Unit and integration tests for SpendSense services and business logic.

Covers:
  - Threshold alert evaluations at 79%, 80%, 100%, and 101%
  - No budget set handling
  - Date handling: January-to-December rollover and standard month decrement
  - Top 5 expenses sorting and graceful handling of < 5 records
  - Empty month handling for summaries and comparisons
  - Division by zero handling in month-over-month comparisons
  - Budget upserting (no duplicate entries)
  - Immediate threshold feedback on expense insertion
"""

import sqlite3
import pytest
from datetime import datetime

from backend.database import init_db
from backend.services import (
    add_expense,
    evaluate_threshold,
    export_expenses_to_csv,
    get_month_comparison,
    get_month_summary,
    get_previous_month,
    get_top_expenses,
    set_budget,
)


@pytest.fixture
def in_memory_db():
    """Provides a fresh, isolated in-memory SQLite database for each test."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Create schema in the in-memory database
    cursor.execute(
        """
        CREATE TABLE expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            note TEXT DEFAULT ''
        );
        """
    )
    cursor.execute(
        """
        CREATE TABLE budgets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            month TEXT NOT NULL,
            category TEXT NOT NULL,
            amount REAL NOT NULL,
            UNIQUE(month, category)
        );
        """
    )
    conn.commit()

    yield conn
    conn.close()


# ============================================================================
# 1. THRESHOLD ALERT TESTS: 79%, 80%, 100%, 101% and No Budget
# ============================================================================

def test_threshold_at_79_percent():
    """At 79% of budget, status must be 'OK' and over_amount must be 0."""
    alert = evaluate_threshold(spent=79.00, budget=100.00, category="Food", month="2026-11")
    assert alert.status == "OK"
    assert alert.percentage == 79.0
    assert alert.over_amount == 0.0
    assert alert.remaining == 21.00
    assert "on track" in alert.message.lower()


def test_threshold_at_80_percent():
    """At exactly 80% of budget, yellow warning ('Warning 80%') must trigger."""
    alert = evaluate_threshold(spent=80.00, budget=100.00, category="Food", month="2026-11")
    assert alert.status == "Warning 80%"
    assert alert.percentage == 80.0
    assert alert.over_amount == 0.0
    assert alert.remaining == 20.00
    assert "warning" in alert.message.lower()


def test_threshold_at_100_percent():
    """At exactly 100% of budget, red alert ('Exceeded') must trigger with 0 over amount."""
    alert = evaluate_threshold(spent=100.00, budget=100.00, category="Food", month="2026-11")
    assert alert.status == "Exceeded"
    assert alert.percentage == 100.0
    assert alert.over_amount == 0.0
    assert alert.remaining == 0.00
    assert "red alert" in alert.message.lower()


def test_threshold_at_101_percent():
    """At 101% of budget, status must be 'Exceeded' and over_amount must equal 1.00."""
    alert = evaluate_threshold(spent=101.00, budget=100.00, category="Food", month="2026-11")
    assert alert.status == "Exceeded"
    assert alert.percentage == 101.0
    assert alert.over_amount == 1.00
    assert alert.remaining == -1.00
    assert "over budget by $1.00" in alert.message


def test_threshold_with_no_budget_set():
    """When no budget is configured, status must be 'No budget set' and never crash."""
    alert_none = evaluate_threshold(spent=50.00, budget=None, category="Health", month="2026-11")
    assert alert_none.status == "No budget set"
    assert alert_none.percentage is None
    assert alert_none.remaining is None
    assert alert_none.over_amount == 0.0
    assert "no budget set" in alert_none.message.lower()

    alert_zero = evaluate_threshold(spent=50.00, budget=0.0, category="Health", month="2026-11")
    assert alert_zero.status == "No budget set"


# ============================================================================
# 2. DATE HANDLING & PREVIOUS MONTH ROLLOVER TESTS
# ============================================================================

def test_previous_month_january_to_december_rollover():
    """January must correctly roll over to December of the previous year."""
    assert get_previous_month("2026-01") == "2025-12"
    assert get_previous_month("2020-01") == "2019-12"
    assert get_previous_month("2000-01") == "1999-12"


def test_previous_month_standard_months():
    """Standard month decrement within the same year."""
    assert get_previous_month("2026-03") == "2026-02"
    assert get_previous_month("2026-12") == "2026-11"
    assert get_previous_month("2026-10") == "2026-09"


# ============================================================================
# 3. TOP 5 EXPENSES SORTING & EDGE CASES
# ============================================================================

def test_top_expenses_sorting_with_more_than_five(in_memory_db):
    """With > 5 expenses, returns strictly top 5 sorted descending by amount."""
    amounts = [25.00, 150.00, 10.00, 500.00, 75.00, 200.00, 50.00]
    for idx, amt in enumerate(amounts):
        add_expense(in_memory_db, f"2026-11-{idx+1:02d}", "Food", amt, f"Note {idx}")

    top5 = get_top_expenses(in_memory_db, "2026-11", limit=5)
    assert len(top5) == 5

    # Verify strictly descending order
    top_amounts = [item.amount for item in top5]
    assert top_amounts == [500.00, 200.00, 150.00, 75.00, 50.00]


def test_top_expenses_with_fewer_than_five(in_memory_db):
    """With 2 expenses, returns both sorted descending without error."""
    add_expense(in_memory_db, "2026-11-01", "Transport", 30.00, "Bus")
    add_expense(in_memory_db, "2026-11-02", "Food", 90.00, "Dinner")

    result = get_top_expenses(in_memory_db, "2026-11", limit=5)
    assert len(result) == 2
    assert result[0].amount == 90.00
    assert result[1].amount == 30.00


def test_top_expenses_empty_month(in_memory_db):
    """With 0 expenses, returns empty list without error."""
    result = get_top_expenses(in_memory_db, "2026-11", limit=5)
    assert result == []


# ============================================================================
# 4. EMPTY MONTH HANDLING
# ============================================================================

def test_month_summary_empty_month(in_memory_db):
    """An empty month must return 0 totals, 'No budget set' status, and no errors."""
    summary = get_month_summary(in_memory_db, "2026-11")
    assert summary.month == "2026-11"
    assert summary.total_budget == 0.0
    assert summary.total_spent == 0.0
    assert summary.total_remaining == 0.0
    assert summary.overall_status == "No budget set"
    assert len(summary.alerts) == 0

    # Ensure all default categories are present
    category_names = [c.category for c in summary.categories]
    assert "Food" in category_names
    assert "Rent" in category_names


def test_month_comparison_empty_months(in_memory_db):
    """Empty months comparison handles division by zero safely."""
    comparison = get_month_comparison(in_memory_db, "2026-11")
    assert comparison.current_month == "2026-11"
    assert comparison.previous_month == "2026-10"
    assert comparison.total_last_month == 0.0
    assert comparison.total_this_month == 0.0
    assert comparison.total_difference == 0.0
    assert comparison.total_percentage_change == 0.0


# ============================================================================
# 5. BUDGET UPSERT & AGGREGATION TESTS
# ============================================================================

def test_budget_upsert_no_duplicates(in_memory_db):
    """Setting budget again for same (month, category) must update the amount."""
    # First insert
    b1 = set_budget(in_memory_db, "2026-11", "Food", 300.00)
    assert b1["amount"] == 300.00

    # Update
    b2 = set_budget(in_memory_db, "2026-11", "Food", 450.00)
    assert b2["amount"] == 450.00

    # Verify only 1 record exists in table
    cursor = in_memory_db.cursor()
    cursor.execute("SELECT COUNT(*) as count FROM budgets WHERE month = '2026-11' AND category = 'Food';")
    assert cursor.fetchone()["count"] == 1


def test_immediate_alert_on_expense_creation(in_memory_db):
    """Adding an expense updates category spent and immediately returns alert status."""
    set_budget(in_memory_db, "2026-11", "Shopping", 100.00)

    # First expense: $70 -> 70% (OK)
    _, alert1 = add_expense(in_memory_db, "2026-11-05", "Shopping", 70.00, "Shoes")
    assert alert1.status == "OK"
    assert alert1.percentage == 70.0

    # Second expense: $15 -> total $85 -> 85% (Warning 80%)
    _, alert2 = add_expense(in_memory_db, "2026-11-06", "Shopping", 15.00, "Hat")
    assert alert2.status == "Warning 80%"
    assert alert2.percentage == 85.0

    # Third expense: $20 -> total $105 -> 105% (Exceeded by $5)
    _, alert3 = add_expense(in_memory_db, "2026-11-07", "Shopping", 20.00, "Socks")
    assert alert3.status == "Exceeded"
    assert alert3.percentage == 105.0
    assert alert3.over_amount == 5.00


def test_csv_export(in_memory_db):
    """CSV export outputs proper headers and rows."""
    add_expense(in_memory_db, "2026-11-01", "Bills", 50.25, "Water")
    add_expense(in_memory_db, "2026-11-05", "Food", 32.50, "Lunch")

    csv_text = export_expenses_to_csv(in_memory_db, "2026-11")
    lines = csv_text.strip().split("\r\n") if "\r\n" in csv_text else csv_text.strip().split("\n")
    assert lines[0] == "ID,Date,Category,Amount,Note"
    assert len(lines) == 3
    assert "Bills,50.25,Water" in lines[1]
    assert "Food,32.50,Lunch" in lines[2]


# ============================================================================
# 6. MODEL VALIDATION TESTS
# ============================================================================

from pydantic import ValidationError
from backend.models import ExpenseCreate, BudgetCreate
from backend.services import seed_sample_data


def test_expense_create_validation_success():
    """Valid expense data passes validation."""
    exp = ExpenseCreate(
        date="2026-11-02",
        category="Food",
        amount=25.50,
        note="Lunch",
    )
    assert exp.amount == 25.50
    assert exp.date == "2026-11-02"


def test_expense_create_validation_negative_or_zero_amount():
    """Negative and zero amounts must raise ValidationError."""
    with pytest.raises(ValidationError):
        ExpenseCreate(date="2026-11-02", category="Food", amount=-5.00)

    with pytest.raises(ValidationError):
        ExpenseCreate(date="2026-11-02", category="Food", amount=0.00)


def test_expense_create_validation_invalid_date():
    """Non-existent or malformed dates must raise ValidationError."""
    with pytest.raises(ValidationError):
        ExpenseCreate(date="2026-02-30", category="Food", amount=15.00)

    with pytest.raises(ValidationError):
        ExpenseCreate(date="not-a-date", category="Food", amount=15.00)


def test_expense_create_validation_note_max_length():
    """Note longer than 100 characters must raise ValidationError."""
    long_note = "x" * 105
    with pytest.raises(ValidationError):
        ExpenseCreate(date="2026-11-02", category="Food", amount=15.00, note=long_note)


def test_budget_create_validation():
    """Budget requires valid month (YYYY-MM) and positive amount."""
    b = BudgetCreate(month="2026-11", category="Rent", amount=1200.0)
    assert b.amount == 1200.0

    with pytest.raises(ValidationError):
        BudgetCreate(month="2026-13", category="Rent", amount=1200.0)

    with pytest.raises(ValidationError):
        BudgetCreate(month="2026/11", category="Rent", amount=1200.0)


def test_month_comparison_rollover_with_actual_data(in_memory_db):
    """Verifies January month comparison pulls December data from previous year."""
    # Add expense in December 2025
    add_expense(in_memory_db, "2025-12-15", "Food", 200.00, "Dec Holiday Groceries")
    # Add expense in January 2026
    add_expense(in_memory_db, "2026-01-10", "Food", 250.00, "Jan New Year Groceries")

    comp = get_month_comparison(in_memory_db, "2026-01")
    assert comp.current_month == "2026-01"
    assert comp.previous_month == "2025-12"

    food_comp = next(c for c in comp.categories if c.category == "Food")
    assert food_comp.spent_last_month == 200.00
    assert food_comp.spent_this_month == 250.00
    assert food_comp.difference == 50.00
    assert food_comp.percentage_change == 25.0


def test_seed_sample_data_creates_records(in_memory_db):
    """Seed sample data executes and populates budgets and expenses."""
    res = seed_sample_data(in_memory_db, target_month="2026-11")
    assert res["status"] == "success"
    assert res["expenses_created"] > 0
    assert res["budgets_created"] > 0

    summary = get_month_summary(in_memory_db, "2026-11")
    assert summary.total_spent > 0
    assert summary.total_budget > 0
    # Check that at least one warning or exceeded alert exists in demo data
    statuses = [c.status for c in summary.categories]
    assert "Warning 80%" in statuses or "Exceeded" in statuses

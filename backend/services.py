"""Business logic services for SpendSense.

Contains pure and database-driven functions for:
  - Date handling (month rollover)
  - Threshold alert calculation (79%, 80%, 100%, 101%)
  - Category aggregation & month summary
  - Top 5 largest expenses sorting
  - Month-over-month comparison with division by zero safeguards
  - CSV export generation
  - Demo sample data seeding
"""

import csv
import io
import sqlite3
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from backend.models import (
    DEFAULT_CATEGORIES,
    AlertInfo,
    CategoryComparison,
    CategorySummary,
    ExpenseResponse,
    MonthComparisonResponse,
    MonthSummaryResponse,
)


def get_previous_month(month_str: str) -> str:
    """Computes the previous calendar month from a 'YYYY-MM' string.
    
    KEY LOGIC: Date handling & rollover
    Handles the January-to-December year rollover properly using datetime.
    Example: '2026-01' -> '2025-12', '2026-03' -> '2026-02'.
    """
    dt = datetime.strptime(month_str, "%Y-%m")
    if dt.month == 1:
        prev_dt = dt.replace(year=dt.year - 1, month=12)
    else:
        prev_dt = dt.replace(month=dt.month - 1)
    return prev_dt.strftime("%Y-%m")


def evaluate_threshold(
    spent: float,
    budget: Optional[float],
    category: str = "Category",
    month: str = "",
) -> AlertInfo:
    """Calculates the threshold status and alert details for a given category.
    
    KEY LOGIC: Threshold check
      - If no budget set: status is 'No budget set' (never crashes).
      - If spent >= 100% of budget: status is 'Exceeded' (red alert with over amount).
      - If spent >= 80% (and < 100%): status is 'Warning 80%' (yellow warning).
      - If spent < 80%: status is 'OK'.
    
    Consistent rounding to 2 decimal places for financial calculations.
    """
    spent_rounded = round(spent, 2)

    # Case 1: No budget set for this category
    if budget is None or budget <= 0:
        return AlertInfo(
            category=category,
            month=month,
            budget=None,
            spent=spent_rounded,
            remaining=None,
            percentage=None,
            status="No budget set",
            over_amount=0.0,
            message=f"No budget set for {category}.",
        )

    budget_rounded = round(budget, 2)
    # Financial percentage calculation: (spent / budget) * 100
    percentage = round((spent_rounded / budget_rounded) * 100.0, 2)
    remaining = round(budget_rounded - spent_rounded, 2)

    # Case 2: 100% or more (Exceeded)
    if percentage >= 100.0:
        over_amount = round(spent_rounded - budget_rounded, 2)
        message = (
            f"🚨 Red Alert: {category} is over budget by ${over_amount:,.2f}! "
            f"(Spent ${spent_rounded:,.2f} of ${budget_rounded:,.2f}, {percentage:.1f}%)"
        )
        return AlertInfo(
            category=category,
            month=month,
            budget=budget_rounded,
            spent=spent_rounded,
            remaining=remaining,
            percentage=percentage,
            status="Exceeded",
            over_amount=over_amount,
            message=message,
        )

    # Case 3: 80% or more but under 100% (Warning 80%)
    if percentage >= 80.0:
        message = (
            f"⚠️ Warning: {category} has reached {percentage:.1f}% of its budget. "
            f"(${spent_rounded:,.2f} of ${budget_rounded:,.2f}, ${remaining:,.2f} remaining)"
        )
        return AlertInfo(
            category=category,
            month=month,
            budget=budget_rounded,
            spent=spent_rounded,
            remaining=remaining,
            percentage=percentage,
            status="Warning 80%",
            over_amount=0.0,
            message=message,
        )

    # Case 4: Under 80% (OK)
    message = (
        f"✅ OK: {category} is on track at {percentage:.1f}% of budget. "
        f"(${spent_rounded:,.2f} of ${budget_rounded:,.2f}, ${remaining:,.2f} remaining)"
    )
    return AlertInfo(
        category=category,
        month=month,
        budget=budget_rounded,
        spent=spent_rounded,
        remaining=remaining,
        percentage=percentage,
        status="OK",
        over_amount=0.0,
        message=message,
    )


def add_expense(
    conn: sqlite3.Connection,
    date: str,
    category: str,
    amount: float,
    note: str,
) -> Tuple[ExpenseResponse, AlertInfo]:
    """Inserts a new expense and immediately evaluates the category threshold alert."""
    rounded_amount = round(amount, 2)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO expenses (date, category, amount, note)
        VALUES (?, ?, ?, ?);
        """,
        (date, category, rounded_amount, note),
    )
    expense_id = cursor.lastrowid
    conn.commit()

    created_expense = ExpenseResponse(
        id=expense_id,
        date=date,
        category=category,
        amount=rounded_amount,
        note=note,
    )

    # Derive month from date (YYYY-MM-DD -> YYYY-MM)
    month = date[:7]

    # Query current category budget for this month
    cursor.execute(
        "SELECT amount FROM budgets WHERE month = ? AND category = ?;",
        (month, category),
    )
    budget_row = cursor.fetchone()
    budget = budget_row["amount"] if budget_row else None

    # Query total spent in this category for this month
    cursor.execute(
        """
        SELECT COALESCE(SUM(amount), 0.0) as total_spent
        FROM expenses
        WHERE category = ? AND date LIKE ?;
        """,
        (category, f"{month}-%"),
    )
    spent_row = cursor.fetchone()
    total_spent = spent_row["total_spent"] if spent_row else 0.0

    # Calculate alert status immediately
    alert = evaluate_threshold(
        spent=total_spent,
        budget=budget,
        category=category,
        month=month,
    )

    return created_expense, alert


def set_budget(
    conn: sqlite3.Connection,
    month: str,
    category: str,
    amount: float,
) -> Dict[str, any]:
    """Sets or updates a monthly budget for a category using upsert (ON CONFLICT).
    
    Guarantees no duplicate budgets per (month, category).
    """
    rounded_amount = round(amount, 2)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO budgets (month, category, amount)
        VALUES (?, ?, ?)
        ON CONFLICT(month, category) DO UPDATE SET amount = excluded.amount;
        """,
        (month, category, rounded_amount),
    )
    conn.commit()

    cursor.execute(
        "SELECT id, month, category, amount FROM budgets WHERE month = ? AND category = ?;",
        (month, category),
    )
    row = cursor.fetchone()
    return dict(row)


def get_budgets_for_month(
    conn: sqlite3.Connection,
    month: str,
) -> List[Dict[str, any]]:
    """Retrieves all budgets configured for a specific month."""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, month, category, amount FROM budgets WHERE month = ? ORDER BY category ASC;",
        (month,),
    )
    return [dict(row) for row in cursor.fetchall()]


def get_expenses_for_month(
    conn: sqlite3.Connection,
    month: Optional[str] = None,
) -> List[ExpenseResponse]:
    """Retrieves expenses, optionally filtered by month (YYYY-MM)."""
    cursor = conn.cursor()
    if month:
        cursor.execute(
            """
            SELECT id, date, category, amount, note
            FROM expenses
            WHERE date LIKE ?
            ORDER BY date DESC, id DESC;
            """,
            (f"{month}-%",),
        )
    else:
        cursor.execute(
            """
            SELECT id, date, category, amount, note
            FROM expenses
            ORDER BY date DESC, id DESC;
            """
        )
    return [
        ExpenseResponse(
            id=row["id"],
            date=row["date"],
            category=row["category"],
            amount=round(row["amount"], 2),
            note=row["note"] or "",
        )
        for row in cursor.fetchall()
    ]


def get_month_summary(
    conn: sqlite3.Connection,
    month: str,
) -> MonthSummaryResponse:
    """Aggregates spending per category and checks threshold alerts for a selected month.
    
    KEY LOGIC: Aggregation by category
      - Sums expenses grouped by category for dates matching the month prefix (YYYY-MM-%).
      - Queries budgets configured for that month.
      - Iterates over all known categories (standard 9 categories + any extra found in data).
      - Calculates remaining balance and % used per category.
      - Computes overall total budget, total spent, and overall threshold status.
    """
    cursor = conn.cursor()

    # 1. Fetch budgets for the month
    cursor.execute(
        "SELECT category, amount FROM budgets WHERE month = ?;",
        (month,),
    )
    budgets_map: Dict[str, float] = {
        row["category"]: round(row["amount"], 2) for row in cursor.fetchall()
    }

    # 2. Fetch total spent per category for the month
    cursor.execute(
        """
        SELECT category, SUM(amount) AS total_spent
        FROM expenses
        WHERE date LIKE ?
        GROUP BY category;
        """,
        (f"{month}-%",),
    )
    spent_map: Dict[str, float] = {
        row["category"]: round(row["total_spent"], 2) for row in cursor.fetchall()
    }

    # Build comprehensive list of categories preserving default order first
    all_categories: List[str] = list(DEFAULT_CATEGORIES)
    for cat in list(budgets_map.keys()) + list(spent_map.keys()):
        if cat not in all_categories:
            all_categories.append(cat)

    categories_summary: List[CategorySummary] = []
    active_alerts: List[AlertInfo] = []

    total_budget: float = 0.0
    total_spent: float = 0.0

    for cat in all_categories:
        cat_budget = budgets_map.get(cat)
        cat_spent = spent_map.get(cat, 0.0)

        # Update totals
        if cat_budget is not None:
            total_budget += cat_budget
        total_spent += cat_spent

        # Evaluate threshold for this category
        alert = evaluate_threshold(
            spent=cat_spent,
            budget=cat_budget,
            category=cat,
            month=month,
        )

        categories_summary.append(
            CategorySummary(
                category=cat,
                budget=alert.budget,
                spent=alert.spent,
                remaining=alert.remaining,
                percentage=alert.percentage,
                status=alert.status,
            )
        )

        # Collect warning or exceeded alerts for prominent display
        if alert.status in ("Warning 80%", "Exceeded"):
            active_alerts.append(alert)

    total_budget_rounded = round(total_budget, 2)
    total_spent_rounded = round(total_spent, 2)
    total_remaining_rounded = round(total_budget_rounded - total_spent_rounded, 2)

    # Compute overall percentage
    if total_budget_rounded > 0:
        overall_percentage = round(
            (total_spent_rounded / total_budget_rounded) * 100.0, 2
        )
        if overall_percentage >= 100.0:
            overall_status = "Exceeded"
        elif overall_percentage >= 80.0:
            overall_status = "Warning 80%"
        else:
            overall_status = "OK"
    else:
        overall_percentage = None
        overall_status = "No budget set"

    return MonthSummaryResponse(
        month=month,
        categories=categories_summary,
        total_budget=total_budget_rounded,
        total_spent=total_spent_rounded,
        total_remaining=total_remaining_rounded,
        overall_percentage=overall_percentage,
        overall_status=overall_status,
        alerts=active_alerts,
    )


def get_top_expenses(
    conn: sqlite3.Connection,
    month: str,
    limit: int = 5,
) -> List[ExpenseResponse]:
    """Returns the top N largest expenses for a selected month, sorted descending.
    
    KEY LOGIC: Sorting by amount
      - Uses SQL ORDER BY amount DESC, id DESC to get largest expenses first.
      - Ties are broken deterministically by most recently created expense id.
      - Gracefully returns whatever number of rows exist (0 to 5) without crashing.
    """
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, date, category, amount, note
        FROM expenses
        WHERE date LIKE ?
        ORDER BY amount DESC, id DESC
        LIMIT ?;
        """,
        (f"{month}-%", limit),
    )
    rows = cursor.fetchall()
    return [
        ExpenseResponse(
            id=row["id"],
            date=row["date"],
            category=row["category"],
            amount=round(row["amount"], 2),
            note=row["note"] or "",
        )
        for row in rows
    ]


def get_month_comparison(
    conn: sqlite3.Connection,
    month: str,
) -> MonthComparisonResponse:
    """Compares spending between current month and previous month category by category.
    
    KEY LOGIC: Month comparison & division by zero handling
      - Computes previous month using get_previous_month (handles Jan -> Dec rollover).
      - Computes absolute difference: spent_this_month - spent_last_month.
      - Safeguards against division by zero:
          * If last month was 0 and this month was 0 -> 0.0% change.
          * If last month was 0 and this month > 0 -> +100.0% ('New spend').
          * If last month was > 0 and this month 0 -> -100.0% ('No spend').
          * Otherwise -> ((spent_this - spent_last) / spent_last) * 100.
    """
    prev_month = get_previous_month(month)
    cursor = conn.cursor()

    # Query spending for current month
    cursor.execute(
        """
        SELECT category, SUM(amount) AS total_spent
        FROM expenses
        WHERE date LIKE ?
        GROUP BY category;
        """,
        (f"{month}-%",),
    )
    current_map: Dict[str, float] = {
        row["category"]: round(row["total_spent"], 2) for row in cursor.fetchall()
    }

    # Query spending for previous month
    cursor.execute(
        """
        SELECT category, SUM(amount) AS total_spent
        FROM expenses
        WHERE date LIKE ?
        GROUP BY category;
        """,
        (f"{prev_month}-%",),
    )
    prev_map: Dict[str, float] = {
        row["category"]: round(row["total_spent"], 2) for row in cursor.fetchall()
    }

    # Combine categories
    all_categories: List[str] = list(DEFAULT_CATEGORIES)
    for cat in list(current_map.keys()) + list(prev_map.keys()):
        if cat not in all_categories:
            all_categories.append(cat)

    comparisons: List[CategoryComparison] = []
    total_last: float = 0.0
    total_this: float = 0.0

    for cat in all_categories:
        last_val = prev_map.get(cat, 0.0)
        this_val = current_map.get(cat, 0.0)
        total_last += last_val
        total_this += this_val

        diff = round(this_val - last_val, 2)

        # Division by zero safeguard
        if last_val == 0.0 and this_val == 0.0:
            pct_change = 0.0
            desc = "No spending in either month"
        elif last_val == 0.0 and this_val > 0.0:
            pct_change = 100.0
            desc = "New expenditure this month"
        elif last_val > 0.0 and this_val == 0.0:
            pct_change = -100.0
            desc = "No expenditure this month (-100%)"
        else:
            pct_change = round(((this_val - last_val) / last_val) * 100.0, 2)
            if diff > 0:
                desc = f"Increased by {pct_change:.1f}% (+${diff:,.2f})"
            elif diff < 0:
                desc = f"Decreased by {abs(pct_change):.1f}% (-${abs(diff):,.2f})"
            else:
                desc = "Identical spending"

        comparisons.append(
            CategoryComparison(
                category=cat,
                spent_last_month=last_val,
                spent_this_month=this_val,
                difference=diff,
                percentage_change=pct_change,
                change_description=desc,
            )
        )

    total_last_rounded = round(total_last, 2)
    total_this_rounded = round(total_this, 2)
    total_diff_rounded = round(total_this_rounded - total_last_rounded, 2)

    if total_last_rounded == 0.0 and total_this_rounded == 0.0:
        total_pct_change = 0.0
    elif total_last_rounded == 0.0 and total_this_rounded > 0.0:
        total_pct_change = 100.0
    elif total_last_rounded > 0.0 and total_this_rounded == 0.0:
        total_pct_change = -100.0
    else:
        total_pct_change = round(
            ((total_this_rounded - total_last_rounded) / total_last_rounded) * 100.0, 2
        )

    return MonthComparisonResponse(
        current_month=month,
        previous_month=prev_month,
        categories=comparisons,
        total_last_month=total_last_rounded,
        total_this_month=total_this_rounded,
        total_difference=total_diff_rounded,
        total_percentage_change=total_pct_change,
    )


def export_expenses_to_csv(
    conn: sqlite3.Connection,
    month: str,
) -> str:
    """Generates CSV text for expenses in a selected month."""
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT id, date, category, amount, note
        FROM expenses
        WHERE date LIKE ?
        ORDER BY date ASC, id ASC;
        """,
        (f"{month}-%",),
    )
    rows = cursor.fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    # Header row
    writer.writerow(["ID", "Date", "Category", "Amount", "Note"])
    for row in rows:
        writer.writerow(
            [
                row["id"],
                row["date"],
                row["category"],
                f"{row['amount']:.2f}",
                row["note"] or "",
            ]
        )
    return output.getvalue()


def seed_sample_data(
    conn: sqlite3.Connection,
    target_month: Optional[str] = None,
) -> Dict[str, any]:
    """Populates the database with realistic sample budgets and expenses.
    
    Creates a demonstration dataset for:
      - Current selected month (with OK, Warning 80%, Exceeded, and No budget set states)
      - Previous month (for rich month-over-month comparisons)
      - More than 5 expenses to showcase Top 5 sorting.
    """
    if not target_month:
        target_month = datetime.now().strftime("%Y-%m")
    prev_month = get_previous_month(target_month)

    cursor = conn.cursor()

    # Clear existing sample data for these two months to avoid conflicts
    cursor.execute("DELETE FROM expenses WHERE date LIKE ? OR date LIKE ?;", (f"{target_month}-%", f"{prev_month}-%"))
    cursor.execute("DELETE FROM budgets WHERE month IN (?, ?);", (target_month, prev_month))
    conn.commit()

    # Target Month Budgets:
    # 1. Food: Budget $600 -> We will spend $520 (86.6% -> Warning 80%)
    # 2. Shopping: Budget $200 -> We will spend $280 (140% -> Exceeded by $80)
    # 3. Transport: Budget $250 -> We will spend $95 (38% -> OK)
    # 4. Rent: Budget $1200 -> We will spend $1200 (100% -> Exceeded)
    # 5. Bills: Budget $300 -> We will spend $180 (60% -> OK)
    # 6. Entertainment: Budget $150 -> We will spend $125 (83.3% -> Warning 80%)
    # 7. Health: NO budget set -> We will spend $75 (No budget set)
    # 8. Education: Budget $400 -> We will spend $0 (0% -> OK)
    budgets_current = [
        (target_month, "Food", 600.00),
        (target_month, "Shopping", 200.00),
        (target_month, "Transport", 250.00),
        (target_month, "Rent", 1200.00),
        (target_month, "Bills", 300.00),
        (target_month, "Entertainment", 150.00),
        (target_month, "Education", 400.00),
    ]

    # Previous Month Budgets
    budgets_prev = [
        (prev_month, "Food", 550.00),
        (prev_month, "Shopping", 250.00),
        (prev_month, "Transport", 250.00),
        (prev_month, "Rent", 1200.00),
        (prev_month, "Bills", 280.00),
        (prev_month, "Entertainment", 150.00),
    ]

    for m, cat, amt in budgets_current + budgets_prev:
        set_budget(conn, m, cat, amt)

    # Expenses for Current Month (varied amounts to demonstrate top 5 sorting)
    expenses_current = [
        (f"{target_month}-01", "Rent", 1200.00, "Monthly apartment rent payment"),
        (f"{target_month}-03", "Shopping", 180.00, "New winter jacket and boots"),
        (f"{target_month}-05", "Food", 145.50, "Weekly grocery haul at Trader Joe's"),
        (f"{target_month}-08", "Food", 160.00, "Family dinner at Italian bistro"),
        (f"{target_month}-10", "Shopping", 100.00, "Electronics accessories and cables"),
        (f"{target_month}-12", "Entertainment", 85.00, "Concert ticket with friends"),
        (f"{target_month}-14", "Food", 110.25, "Farmers market produce and artisan bread"),
        (f"{target_month}-16", "Transport", 60.00, "Monthly subway transit card refill"),
        (f"{target_month}-18", "Bills", 120.00, "Electric and gas utility bill"),
        (f"{target_month}-20", "Food", 104.25, "Weekend brunch & coffee supplies"),
        (f"{target_month}-22", "Bills", 60.00, "High-speed home fiber internet"),
        (f"{target_month}-24", "Entertainment", 40.00, "Movie theater & popcorn"),
        (f"{target_month}-25", "Transport", 35.00, "Ride-share taxi to airport"),
        (f"{target_month}-26", "Health", 75.00, "Dental cleaning co-pay and vitamins"),
    ]

    # Expenses for Previous Month
    expenses_prev = [
        (f"{prev_month}-01", "Rent", 1200.00, "Monthly apartment rent payment"),
        (f"{prev_month}-04", "Food", 220.00, "Bulk grocery run at Costco"),
        (f"{prev_month}-10", "Food", 180.00, "Dinner with colleagues"),
        (f"{prev_month}-12", "Shopping", 90.00, "Books and stationery"),
        (f"{prev_month}-15", "Transport", 110.00, "Fuel and highway tolls"),
        (f"{prev_month}-18", "Bills", 175.00, "Electric and water utility bill"),
        (f"{prev_month}-22", "Entertainment", 65.00, "Board games and streaming subscriptions"),
    ]

    for dt, cat, amt, note in expenses_current + expenses_prev:
        add_expense(conn, dt, cat, amt, note)

    return {
        "status": "success",
        "current_month": target_month,
        "previous_month": prev_month,
        "expenses_created": len(expenses_current) + len(expenses_prev),
        "budgets_created": len(budgets_current) + len(budgets_prev),
        "message": f"Successfully loaded sample data for {target_month} and {prev_month}!",
    }

# SpendSense: Smart Budget Monitoring System with Threshold Alerts

A full-stack, pure Python web application for real-time personal budget tracking, financial threshold alerts, category-level spending analysis, and month-over-month comparisons.

---

## Architecture Overview

SpendSense is implemented **100% in pure Python** with strict separation of concerns across layers:

- **Frontend (Streamlit)**: Pure Python UI (`frontend/app.py`). Uses Streamlit's native components (forms, metrics, tables, bar charts, download buttons) with zero handwritten HTML/CSS/JS.
- **Backend (FastAPI + Uvicorn)**: High-performance asynchronous REST API (`backend/main.py`) exposing standardized JSON endpoints and automatic OpenAPI documentation (`/docs`).
- **Database (SQLite via `sqlite3`)**: Lightweight, thread-safe embedded relational storage (`backend/database.py`) using parameterized SQL queries to prevent SQL injection.
- **Data Validation (Pydantic v2)**: Strict input validation on both frontend and backend for currency amounts, ISO dates, notes, and categories.
- **Business Logic (`backend/services.py`)**: Pure Python domain logic for threshold alerting, category aggregation, top expense ranking, and month rollover calculations.

---

## Project Structure

```text
spendsense/
├── backend/
│   ├── __init__.py
│   ├── database.py       # SQLite connection, schema init, parameterized queries
│   ├── models.py         # Pydantic models, schemas, and input validators
│   ├── services.py       # Core business logic: aggregation, alerts, sorting, comparison
│   └── main.py           # FastAPI app, REST API routes, lifespan handlers
├── frontend/
│   ├── __init__.py
│   └── app.py            # Streamlit dashboard and UI navigation
├── tests/
│   └── test_services.py  # Comprehensive pytest test suite (22 tests)
├── run.py                # Unified launcher for FastAPI + Streamlit
├── requirements.txt      # Pinned dependency specifications
└── README.md             # Setup guide, feature checklist, and interview talking points
```

---

## Tech Stack (Fixed & Compliant)

| Component | Technology | Role |
| :--- | :--- | :--- |
| **Frontend** | Streamlit (`>=1.38.0`) | Pure Python reactive web interface |
| **Backend** | FastAPI (`>=0.115.0`) + Uvicorn | High-performance RESTful API |
| **Database** | SQLite (`sqlite3` built-in) | Embedded relational database |
| **HTTP Client** | Requests (`>=2.31.0`) | Streamlit-to-FastAPI communication |
| **Validation** | Pydantic (`>=2.7.0`) | Schema validation and serialization |
| **Data & Tables** | Pandas (`>=2.2.0`) | Summary tables, charts, CSV formatting |
| **Testing** | Pytest (`>=8.0.0`) | Unit and service integration test suite |

---

## Setup & Running Instructions

### 1. Prerequisites
- Python 3.10+ (tested on Python 3.14)

### 2. Installation
Install the pinned dependencies:
```bash
pip install -r requirements.txt
```

### 3. Run Application with One Command
Execute the unified runner:
```bash
python run.py
```

The runner performs:
1. Automatic startup of the FastAPI backend on `http://127.0.0.1:8000`.
2. Port and health check polling until the API is healthy.
3. Launch of the Streamlit frontend on `http://127.0.0.1:8501`.
4. Clean, unified shutdown when pressing `Ctrl+C`.

### Direct URLs:
- **Web Application**: [http://localhost:8501](http://localhost:8501)
- **Interactive API Documentation (Swagger / OpenAPI)**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **API Health Check**: [http://localhost:8000/health](http://localhost:8000/health)

---

## Feature Checklist

### Compulsory Features (All 5 Implemented & Verified)
- [x] **1. Add an Expense**:
  - Date picker defaulting to today (`YYYY-MM-DD`).
  - Category dropdown featuring default 9 categories.
  - Amount input strictly greater than 0, formatted to 2 decimals.
  - Short note field limited to 100 characters.
  - Form validation on both Streamlit and FastAPI.
  - Form automatically clears on submit.
  - **Immediate feedback**: Returns and renders the threshold alert status right after submission.
- [x] **2. Set Monthly Budget per Category**:
  - Target month picker (`YYYY-MM`), category selector, and positive budget amount.
  - Re-submitting an existing month and category updates the amount in-place via SQL `ON CONFLICT(month, category) DO UPDATE` without duplicates.
  - Displays a clean table of current configured budgets for the selected month.
- [x] **3. Threshold Alerts**:
  - **Warning 80%** (Yellow): Triggers when spending reaches 80.0% but under 100.0%.
  - **Exceeded** (Red Alert): Triggers at 100.0% or higher, displaying the exact dollar amount over budget.
  - Alerts are returned immediately on expense addition and stay visible in the Month Summary.
  - Categories without budgets display `"No budget set"` safely without crashing.
- [x] **4. Month Summary**:
  - Global month selector shared across all pages.
  - KPI metric cards: Total Budget, Total Spent, Remaining Budget, Overall % Used.
  - Prominent alert banners for any categories in Warning or Exceeded states.
  - Summary table with columns: `Category`, `Budget`, `Spent`, `Remaining`, `% Used`, `Status`.
  - Native Streamlit bar chart comparing Budget vs. Spent for each category.
- [x] **5. Top 5 Largest Expenses**:
  - Ranks transactions in descending order by amount (`ORDER BY amount DESC, id DESC`).
  - Highlights top 3 largest expenses in summary cards.
  - Gracefully handles months with fewer than 5 (or 0) expenses without throwing errors.

### Stretch Features (Both Implemented & Verified)
- [x] **1. Month-over-Month Comparison**:
  - Compares selected month with the previous calendar month category by category.
  - Displays spent last month, spent this month, net difference (`this - last`), and `% change`.
  - Robust division-by-zero handling: Handles `$0 -> $0` (0.0%), `$0 -> $X` (+100.0% new spend), and `$X -> $0` (-100.0%).
  - Robust date rollover: Correctly handles January-to-December rollover (`2026-01` -> `2025-12`).
  - Comparative bar chart visually displaying both months side by side.
- [x] **2. CSV Export**:
  - Backend endpoint `GET /export?month=YYYY-MM` returns standard CSV format.
  - Frontend provides a one-click Streamlit download button: `expenses_YYYY-MM.csv`.
  - Includes a live tabular preview of the exported records.

### Quick Demo & Seed Data
- [x] **Load Sample Data**: One-click button in the sidebar populates realistic records for both the current and previous month, demonstrating:
  - Categories under 80% (`OK`)
  - Categories between 80% and 99.9% (`Warning 80%`)
  - Categories at or over 100% (`Exceeded`)
  - Categories with `"No budget set"`
  - Over 10 expenses to showcase Top 5 sorting.

---

## API Endpoints Reference

All endpoints return JSON (except `/export` which returns `text/csv`).

| Method | Path | Query / Body | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/categories` | None | Returns list of standard categories |
| `POST` | `/expenses` | JSON: `{date, category, amount, note}` | Records expense and returns immediate alert |
| `GET` | `/expenses` | `?month=YYYY-MM` | Lists expenses filtered by month |
| `POST` | `/budgets` | JSON: `{month, category, amount}` | Upserts monthly budget for a category |
| `GET` | `/budgets` | `?month=YYYY-MM` | Retrieves all budgets for a given month |
| `GET` | `/summary` | `?month=YYYY-MM` | Returns full budget vs spent summary & alerts |
| `GET` | `/top-expenses` | `?month=YYYY-MM&limit=5` | Returns top N expenses ordered descending |
| `GET` | `/compare` | `?month=YYYY-MM` | Compares current month against prior month |
| `GET` | `/export` | `?month=YYYY-MM` | Exports expenses as CSV file download |
| `POST` | `/seed` | `?month=YYYY-MM` | Seeds demonstration data for quick testing |
| `POST` | `/reset` | None | Clears all database records |
| `GET` | `/health` | None | Service liveness probe |

---

## Running the Tests

SpendSense includes 22 automated pytest tests covering threshold boundary conditions, date rollovers, top 5 sorting, and edge cases.

To execute tests:
```bash
python -m pytest -v
```

All 22 tests pass:
- `test_threshold_at_79_percent`: Verifies 79% evaluates to `OK`.
- `test_threshold_at_80_percent`: Verifies 80% evaluates to `Warning 80%`.
- `test_threshold_at_100_percent`: Verifies 100% evaluates to `Exceeded` ($0 over).
- `test_threshold_at_101_percent`: Verifies 101% evaluates to `Exceeded` with exact over-budget dollar amount.
- `test_threshold_with_no_budget_set`: Verifies `None` or 0 budget yields `"No budget set"` without errors.
- `test_previous_month_january_to_december_rollover`: Verifies `2026-01` rolls over to `2025-12`.
- `test_previous_month_standard_months`: Verifies intra-year month decrements.
- `test_top_expenses_sorting_with_more_than_five`: Verifies descending sort with > 5 items.
- `test_top_expenses_with_fewer_than_five`: Verifies graceful handling of < 5 items.
- `test_top_expenses_empty_month`: Verifies graceful handling of 0 items.
- `test_month_summary_empty_month`: Verifies zeroed metrics on empty months.
- `test_month_comparison_empty_months`: Verifies division-by-zero safety on empty data.
- `test_budget_upsert_no_duplicates`: Verifies `ON CONFLICT` updates existing row.
- `test_immediate_alert_on_expense_creation`: Verifies real-time alert calculation upon expense addition.
- `test_csv_export`: Verifies CSV formatting and headers.
- `test_expense_create_validation_*`: Verifies Pydantic negative amount, date, and note validations.
- `test_month_comparison_rollover_with_actual_data`: Verifies full end-to-end data comparison across year boundary.

---

## Interview Talking Points

### 1. Aggregation by Category
- **The Problem**: Monthly expenses are logged as individual transactions. To evaluate budgets, we must aggregate total expenditure by category and combine it with budgeted amounts.
- **Implementation (`backend/services.py:get_month_summary`)**:
  - We execute a parameterized SQL query using `SUM(amount)` grouped by `category` filtered by the month ISO prefix (`date LIKE 'YYYY-MM-%'`).
  - We separately query all configured budgets for that month.
  - To prevent missing categories or UI flicker, we merge these dictionaries against the master `DEFAULT_CATEGORIES` list.
  - Any category with expenses but no budget or vice versa is safely mapped with default values (`$0.00` spent or `None` budget).
- **Complexity**: $O(N)$ where $N$ is the number of transactions in the month. SQL indexing on `expenses(date)` ensures $O(\log M + K)$ index range scan performance.

### 2. Threshold Alerts & Boundary Logic
- **The Problem**: Users need instant notification when spending approaches or exceeds budget limits.
- **Implementation (`backend/services.py:evaluate_threshold`)**:
  - **Boundary `< 80.0%`**: Marked as `"OK"`. Safe spending zone.
  - **Boundary `>= 80.0% and < 100.0%`**: Marked as `"Warning 80%"`. Yellow alert with percentage and remaining funds.
  - **Boundary `>= 100.0%`**: Marked as `"Exceeded"`. Red alert with exact dollar amount over budget (`spent - budget`).
  - **Unbudgeted Categories**: When `budget is None` or `<= 0`, returns `"No budget set"`. This prevents crashes or nonsensical percentages like division by zero.
- **Immediate Feedback Loop**:
  - When an expense is inserted (`POST /expenses`), `add_expense()` immediately recalculates the category's running monthly total and returns the updated `AlertInfo` object in the same HTTP response. The Streamlit UI displays this alert banner immediately above the form.

### 3. Sorting by Amount (Top 5 Expenses)
- **The Problem**: Identifying peak individual expenses helps users spot irregular or high-impact spending.
- **Implementation (`backend/services.py:get_top_expenses`)**:
  - We push the sorting down to the database engine using SQL:
    ```sql
    SELECT id, date, category, amount, note
    FROM expenses
    WHERE date LIKE ?
    ORDER BY amount DESC, id DESC
    LIMIT ?;
    ```
  - `id DESC` serves as a deterministic tie-breaker when multiple expenses share the same amount.
  - If a month has fewer than 5 expenses (or 0), SQL `LIMIT 5` naturally returns the available slice without raising `IndexError`.
- **Complexity**: $O(K \log K)$ where $K$ is the number of expenses in that month, requiring minimal memory.

### 4. Date Handling & Year Rollover
- **The Problem**: Month-over-month comparisons must compare month $M$ with month $M-1$. Naively subtracting 1 from the month integer fails when $M = 1$ (January), producing `month = 0`.
- **Implementation (`backend/services.py:get_previous_month`)**:
  - We parse the month string via `datetime.strptime(month_str, "%Y-%m")`.
  - If `dt.month == 1`, we decrement the year by 1 and set the month to 12:
    ```python
    if dt.month == 1:
        prev_dt = dt.replace(year=dt.year - 1, month=12)
    else:
        prev_dt = dt.replace(month=dt.month - 1)
    return prev_dt.strftime("%Y-%m")
    ```
  - This cleanly handles century rollovers and avoids arbitrary day-of-month math (e.g., February 28/29 issues).

### 5. Division by Zero Safeguards & Financial Precision
- **Financial Precision**: Floating-point arithmetic in computers can introduce rounding inaccuracies (e.g. `0.1 + 0.2 = 0.30000000000000004`). All monetary calculations consistently use `round(amount, 2)` before storage, comparison, and display.
- **Percentage Change Division by Zero**:
  - When comparing month-over-month spending, if the previous month had `$0.00` spent:
    - If current month also has `$0.00`: Percentage change is `0.0%`.
    - If current month has `$X > 0`: Mathematically undefined division by zero is handled as `+100.0%` with an explanatory label `"New expenditure this month"`.
    - If previous month had `$X > 0` and current month has `$0.00`: Evaluates to `-100.0%` (`"No expenditure this month"`).
#   s m a r t - b u d g e t - m o n i t o r i n g - s y s t e m 1  
 #   s m a r t - b u d g e t - m o n i t o r i n g - s y s t e m 2  
 #   s m a r t - b u d g e t - m o n i t o r i n g - s y s t e m s  
 
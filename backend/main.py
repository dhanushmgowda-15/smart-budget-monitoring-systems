"""FastAPI backend application for SpendSense.

Provides RESTful endpoints for:
  - Managing expenses and immediate threshold alert feedback
  - Setting and retrieving monthly budgets
  - Monthly spending summaries with category-by-category threshold evaluations
  - Top 5 largest expenses sorting
  - Month-over-month comparisons with rollover logic
  - CSV export of monthly expense records
  - Category retrieval and sample data seeding
"""

import re
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional

from fastapi import Depends, FastAPI, HTTPException, Query, Response, status
from fastapi.middleware.cors import CORSMiddleware

from backend.database import get_db, init_db
from backend.models import (
    DEFAULT_CATEGORIES,
    BudgetCreate,
    BudgetResponse,
    ExpenseCreate,
    ExpenseCreateResponse,
    ExpenseResponse,
    MonthComparisonResponse,
    MonthSummaryResponse,
)
from backend.services import (
    add_expense,
    export_expenses_to_csv,
    get_budgets_for_month,
    get_expenses_for_month,
    get_month_comparison,
    get_month_summary,
    get_top_expenses,
    seed_sample_data,
    set_budget,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initializes the database tables on application startup."""
    init_db()
    yield


app = FastAPI(
    title="SpendSense API",
    description="Smart Budget Monitoring System with Real-Time Threshold Alerts",
    version="1.0.0",
    lifespan=lifespan,
)
app = FastAPI(
    title="SpendSense API",
    description="Smart Budget Monitoring System with Real-Time Threshold Alerts",
    version="1.0.0",
    lifespan=lifespan,
)

@app.get("/", tags=["System"])
def root():
    return {"status": "ok", "message": "SpendSense API is running. See /docs"}

# Enable CORS for frontend clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def validate_month_string(month: str) -> str:
    """Helper to validate YYYY-MM query parameter format."""
    if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", month):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Month parameter must be in YYYY-MM format (e.g., 2026-11)",
        )
    return month


@app.get("/health", tags=["System"])
def health_check():
    """Health check endpoint used by startup scripts to verify backend readiness."""
    return {"status": "ok", "service": "SpendSense API"}


@app.get("/categories", response_model=List[str], tags=["Categories"])
def get_categories():
    """Returns the list of standard supported expense categories."""
    return DEFAULT_CATEGORIES


@app.post(
    "/expenses",
    response_model=ExpenseCreateResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Expenses"],
)
def create_expense(expense: ExpenseCreate, db=Depends(get_db)):
    """Creates a new expense and immediately returns category threshold alert status.
    
    COMPULSORY FEATURE 1 & 3:
      - Validates date (YYYY-MM-DD), category, amount (> 0), note (<= 100 chars).
      - Returns created expense AND real-time alert (OK, Warning 80%, Exceeded, No budget set).
    """
    try:
        created_expense, alert = add_expense(
            conn=db,
            date=expense.date,
            category=expense.category,
            amount=expense.amount,
            note=expense.note,
        )
        return ExpenseCreateResponse(expense=created_expense, alert=alert)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to record expense: {str(e)}",
        )


@app.get("/expenses", response_model=List[ExpenseResponse], tags=["Expenses"])
def list_expenses(
    month: Optional[str] = Query(None, description="Optional month filter in YYYY-MM format"),
    db=Depends(get_db),
):
    """Retrieves all expenses, optionally filtered by month (YYYY-MM)."""
    if month is not None:
        validate_month_string(month)
    return get_expenses_for_month(conn=db, month=month)


@app.post(
    "/budgets",
    response_model=BudgetResponse,
    status_code=status.HTTP_200_OK,
    tags=["Budgets"],
)
def create_or_update_budget(budget: BudgetCreate, db=Depends(get_db)):
    """Sets or updates a monthly budget for a category.
    
    COMPULSORY FEATURE 2:
      - Updates existing value if set again (no duplicates).
    """
    try:
        result = set_budget(
            conn=db,
            month=budget.month,
            category=budget.category,
            amount=budget.amount,
        )
        return BudgetResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to set budget: {str(e)}",
        )


@app.get("/budgets", response_model=List[BudgetResponse], tags=["Budgets"])
def list_budgets(
    month: str = Query(..., description="Month filter in YYYY-MM format"),
    db=Depends(get_db),
):
    """Retrieves all category budgets for the specified month."""
    validate_month_string(month)
    return get_budgets_for_month(conn=db, month=month)


@app.get("/summary", response_model=MonthSummaryResponse, tags=["Summary"])
def get_summary(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db=Depends(get_db),
):
    """Retrieves monthly budget vs spending summary with threshold alerts.
    
    COMPULSORY FEATURE 3 & 4:
      - Total spent per category against budget.
      - Status column: OK, Warning 80%, Exceeded, No budget set.
      - Overall total spent vs overall total budget.
      - Active alert warnings.
    """
    validate_month_string(month)
    return get_month_summary(conn=db, month=month)


@app.get("/top-expenses", response_model=List[ExpenseResponse], tags=["Expenses"])
def top_expenses(
    month: str = Query(..., description="Month in YYYY-MM format"),
    limit: int = Query(5, ge=1, le=50, description="Maximum number of expenses to return"),
    db=Depends(get_db),
):
    """Returns the top largest expenses for the selected month sorted descending.
    
    COMPULSORY FEATURE 5:
      - Sorted by amount descending.
      - Handles fewer than 5 expenses gracefully.
    """
    validate_month_string(month)
    return get_top_expenses(conn=db, month=month, limit=limit)


@app.get("/compare", response_model=MonthComparisonResponse, tags=["Comparison"])
def compare_months(
    month: str = Query(..., description="Target month in YYYY-MM format to compare with prior month"),
    db=Depends(get_db),
):
    """Compares spending between selected month and the prior calendar month.
    
    STRETCH FEATURE 1:
      - Spent last month, spent this month, difference, % change.
      - Handles division by zero gracefully.
      - Handles January-to-December rollover.
    """
    validate_month_string(month)
    return get_month_comparison(conn=db, month=month)


@app.get("/export", tags=["Export"])
def export_csv(
    month: str = Query(..., description="Month in YYYY-MM format"),
    db=Depends(get_db),
):
    """Exports expenses for the selected month as a downloadable CSV file.
    
    STRETCH FEATURE 2:
      - Returns raw CSV with appropriate headers and filename.
    """
    validate_month_string(month)
    csv_content = export_expenses_to_csv(conn=db, month=month)
    filename = f"expenses_{month}.csv"
    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/seed", tags=["Demo Data"])
def seed_data(
    month: Optional[str] = Query(None, description="Target month for seed data (default: current month)"),
    db=Depends(get_db),
):
    """Seeds rich demonstration data across target month and previous month."""
    if month:
        validate_month_string(month)
    result = seed_sample_data(conn=db, target_month=month)
    return result


@app.post("/reset", tags=["Demo Data"])
def reset_database(db=Depends(get_db)):
    """Clears all expenses and budgets for a clean slate."""
    cursor = db.cursor()
    cursor.execute("DELETE FROM expenses;")
    cursor.execute("DELETE FROM budgets;")
    db.commit()
    return {"status": "success", "message": "All expense and budget records have been cleared."}

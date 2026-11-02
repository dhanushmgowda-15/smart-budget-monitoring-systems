"""Pydantic data models and schemas for SpendSense.

Defines input validation rules, default categories, and structured
response models for FastAPI endpoints.
"""

from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
import re
from datetime import datetime

# Default 9 standard categories
DEFAULT_CATEGORIES: List[str] = [
    "Food",
    "Transport",
    "Rent",
    "Shopping",
    "Entertainment",
    "Bills",
    "Health",
    "Education",
    "Other",
]


class ExpenseCreate(BaseModel):
    """Schema for adding a new expense with strict validations."""
    date: str = Field(..., description="Date in ISO format YYYY-MM-DD")
    category: str = Field(..., description="Category from allowed default categories")
    amount: float = Field(..., gt=0, description="Expense amount must be strictly greater than 0")
    note: Optional[str] = Field(default="", max_length=100, description="Short description up to 100 characters")

    @field_validator("date")
    @classmethod
    def validate_date_format(cls, value: str) -> str:
        """Validate date matches YYYY-MM-DD and is a valid calendar date."""
        try:
            datetime.strptime(value, "%Y-%m-%d")
        except ValueError:
            raise ValueError("Date must be in valid ISO format YYYY-MM-DD")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Ensure category is non-empty and stripped of excess whitespace."""
        val = value.strip()
        if not val:
            raise ValueError("Category cannot be empty")
        return val

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        """Ensure amount has at most 2 decimal places and is rounded consistently."""
        if value <= 0:
            raise ValueError("Amount must be greater than 0")
        return round(value, 2)

    @field_validator("note")
    @classmethod
    def validate_note(cls, value: Optional[str]) -> str:
        """Sanitize and limit note length."""
        if value is None:
            return ""
        val = value.strip()
        if len(val) > 100:
            raise ValueError("Note must not exceed 100 characters")
        return val


class ExpenseResponse(BaseModel):
    """Schema for returning expense details."""
    id: int
    date: str
    category: str
    amount: float
    note: str


class BudgetCreate(BaseModel):
    """Schema for setting or updating a monthly category budget."""
    month: str = Field(..., description="Month in format YYYY-MM")
    category: str = Field(..., description="Category name")
    amount: float = Field(..., gt=0, description="Budget amount must be strictly greater than 0")

    @field_validator("month")
    @classmethod
    def validate_month_format(cls, value: str) -> str:
        """Validate month matches YYYY-MM."""
        if not re.match(r"^\d{4}-(0[1-9]|1[0-2])$", value):
            raise ValueError("Month must be in YYYY-MM format (e.g. 2026-11)")
        return value

    @field_validator("category")
    @classmethod
    def validate_category(cls, value: str) -> str:
        """Ensure category is non-empty."""
        val = value.strip()
        if not val:
            raise ValueError("Category cannot be empty")
        return val

    @field_validator("amount")
    @classmethod
    def validate_amount(cls, value: float) -> float:
        """Ensure budget amount is positive and rounded to 2 decimals."""
        if value <= 0:
            raise ValueError("Budget amount must be greater than 0")
        return round(value, 2)


class BudgetResponse(BaseModel):
    """Schema for returning budget details."""
    id: int
    month: str
    category: str
    amount: float


class AlertInfo(BaseModel):
    """Schema for category threshold alert status."""
    category: str
    month: str
    budget: Optional[float] = None
    spent: float
    remaining: Optional[float] = None
    percentage: Optional[float] = None
    status: str  # "OK", "Warning 80%", "Exceeded", "No budget set"
    over_amount: float = 0.0
    message: str


class ExpenseCreateResponse(BaseModel):
    """Response returned upon successfully adding an expense, including immediate alert."""
    expense: ExpenseResponse
    alert: AlertInfo


class CategorySummary(BaseModel):
    """Summary item for one category in a given month."""
    category: str
    budget: Optional[float] = None
    spent: float
    remaining: Optional[float] = None
    percentage: Optional[float] = None
    status: str  # "OK", "Warning 80%", "Exceeded", "No budget set"


class MonthSummaryResponse(BaseModel):
    """Comprehensive summary of spending and budgets for a selected month."""
    month: str
    categories: List[CategorySummary]
    total_budget: float
    total_spent: float
    total_remaining: float
    overall_percentage: Optional[float] = None
    overall_status: str
    alerts: List[AlertInfo]


class CategoryComparison(BaseModel):
    """Month-over-month comparison item for a single category."""
    category: str
    spent_last_month: float
    spent_this_month: float
    difference: float
    percentage_change: Optional[float] = None
    change_description: str


class MonthComparisonResponse(BaseModel):
    """Comparison response between current and previous month."""
    current_month: str
    previous_month: str
    categories: List[CategoryComparison]
    total_last_month: float
    total_this_month: float
    total_difference: float
    total_percentage_change: Optional[float] = None

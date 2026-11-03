"""SpendSense Streamlit Frontend Application.

Pure Python UI that communicates with the FastAPI backend via requests.
Includes:
  - Sidebar navigation & shared month selector
  - Add Expense form with immediate threshold alert feedback
  - Monthly Budget Setting with upsert and overview table
  - Month Summary with category breakdown, bar chart, and active alerts
  - Top 5 largest expenses descending view
  - Month-over-Month comparison with rollover & division-by-zero safeguards
  - CSV Export with download button and preview
  - Sample Data Loader for quick demonstrations
"""

import requests
import pandas as pd
import streamlit as st
import os
from datetime import date, datetime
from typing import Any, Dict, List, Optional


# Backend API Base URL (configurable via env var, defaults to localhost:8000)
API_BASE_URL = os.environ.get("SPENDSENSE_API_URL", "http://127.0.0.1:8000")


# ============================================================================
# API HELPER FUNCTIONS (Safe HTTP calls, no raw tracebacks)
# ============================================================================

def api_get(endpoint: str, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Performs a safe GET request to the FastAPI backend.
    
    Catches connection errors and displays friendly messages without raw tracebacks.
    """
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.get(url, params=params, timeout=5)
        if response.status_code == 200:
            # Check for CSV response
            if "text/csv" in response.headers.get("Content-Type", ""):
                return response.text
            return response.json()
        st.error(f"Backend returned error {response.status_code}: {response.text}")
        return None
    except requests.exceptions.ConnectionError:
        st.error(
            f"Cannot connect to the backend at {API_BASE_URL}. "
            "Please ensure FastAPI is running via 'python run.py' or 'uvicorn backend.main:app'."
        )
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error communicating with backend: {str(e)}")
        return None


def api_post(endpoint: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None) -> Optional[Any]:
    """Performs a safe POST request to the FastAPI backend."""
    url = f"{API_BASE_URL}{endpoint}"
    try:
        response = requests.post(url, json=json_data, params=params, timeout=5)
        if response.status_code in (200, 201):
            return response.json()
        st.error(f"Backend error ({response.status_code}): {response.text}")
        return None
    except requests.exceptions.ConnectionError:
        st.error(
            f"Cannot connect to the backend at {API_BASE_URL}. "
            "Please ensure FastAPI is running."
        )
        return None
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {str(e)}")
        return None


# ============================================================================
# PAGE CONFIGURATION & SESSION STATE
# ============================================================================

st.set_page_config(
    page_title="SpendSense - Smart Budget Monitor",
    page_icon="💰",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize shared session state for selected month
if "selected_month" not in st.session_state:
    st.session_state["selected_month"] = datetime.now().strftime("%Y-%m")

# Initialize storage for latest immediate alert message
if "latest_alert" not in st.session_state:
    st.session_state["latest_alert"] = None


# ============================================================================
# SIDEBAR NAVIGATION & SHARED CONTROLS
# ============================================================================

st.sidebar.title("💰 SpendSense")
st.sidebar.caption("Smart Budget Monitoring System")

# Shared Month Selector
st.sidebar.subheader("📅 Active Month")
month_input = st.sidebar.text_input(
    "Select Month (YYYY-MM):",
    value=st.session_state["selected_month"],
    help="Format must be YYYY-MM (e.g., 2026-11)",
)

# Validate month format
if month_input != st.session_state["selected_month"]:
    try:
        datetime.strptime(month_input.strip(), "%Y-%m")
        st.session_state["selected_month"] = month_input.strip()
    except ValueError:
        st.sidebar.warning("Invalid format. Please use YYYY-MM (e.g. 2026-11).")

active_month = st.session_state["selected_month"]
st.sidebar.info(f"Viewing data for: **{active_month}**")

# Navigation Menu
st.sidebar.subheader("Navigation")
menu_choice = st.sidebar.radio(
    "Go to:",
    options=[
        "Add Expense",
        "Set Budget",
        "Month Summary",
        "Top 5 Expenses",
        "Compare Months",
        "Export CSV",
    ],
    index=2,  # Default to Month Summary
)

st.sidebar.divider()

# Quick Demo Actions
st.sidebar.subheader("🚀 Quick Demo")
if st.sidebar.button("Load Sample Data", use_container_width=True, help="Populates realistic expenses & budgets"):
    result = api_post("/seed", params={"month": active_month})
    if result and result.get("status") == "success":
        st.sidebar.success(f"Sample data loaded for {active_month}!")
        st.session_state["latest_alert"] = None
        st.rerun()

if st.sidebar.button("Clear All Data", use_container_width=True, help="Clears expenses and budgets"):
    reset_res = api_post("/reset")
    if reset_res:
        st.sidebar.info("All data cleared.")
        st.session_state["latest_alert"] = None
        st.rerun()


# ============================================================================
# FEATURE 1: ADD AN EXPENSE
# ============================================================================

if menu_choice == "Add Expense":
    st.header("➕ Add an Expense")
    st.markdown("Record a new expenditure and receive instant real-time threshold alert status.")

    # Fetch available categories from backend
    categories = api_get("/categories")
    if not categories:
        categories = ["Food", "Transport", "Rent", "Shopping", "Entertainment", "Bills", "Health", "Education", "Other"]

    with st.form(key="expense_form", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            expense_date = st.date_input(
                "Date",
                value=date.today(),
                help="Date when the expense occurred",
            )
            category = st.selectbox("Category", options=categories)

        with col2:
            amount = st.number_input(
                "Amount ($)",
                min_value=0.01,
                max_value=1_000_000.00,
                step=0.01,
                format="%.2f",
                help="Expense amount in dollars (> 0.00)",
            )
            note = st.text_input(
                "Short Note (optional)",
                max_chars=100,
                placeholder="E.g., Team lunch, Grocery haul, Transit pass",
                help="Max 100 characters",
            )

        submit_btn = st.form_submit_button("Record Expense", use_container_width=True)

    if submit_btn:
        # Frontend validation
        if amount <= 0:
            st.error("Expense amount must be greater than $0.00.")
        elif len(note) > 100:
            st.error("Note cannot exceed 100 characters.")
        else:
            payload = {
                "date": expense_date.strftime("%Y-%m-%d"),
                "category": category,
                "amount": round(amount, 2),
                "note": note.strip(),
            }
            res = api_post("/expenses", json_data=payload)
            if res:
                st.success(f"Successfully recorded ${amount:,.2f} for {category} on {payload['date']}!")
                # Immediate alert feedback
                alert = res.get("alert", {})
                st.session_state["latest_alert"] = alert

    # Show immediate alert if present
    latest_alert = st.session_state.get("latest_alert")
    if latest_alert:
        st.subheader("🔔 Immediate Budget Alert Feedback")
        status = latest_alert.get("status")
        msg = latest_alert.get("message", "")
        if status == "Exceeded":
            st.error(msg)
        elif status == "Warning 80%":
            st.warning(msg)
        elif status == "OK":
            st.success(msg)
        else:
            st.info(msg)

    # Show recent expenses for the current month
    st.divider()
    st.subheader(f"Recent Expenses for {active_month}")
    recent = api_get("/expenses", params={"month": active_month})
    if recent and len(recent) > 0:
        df_recent = pd.DataFrame(recent)
        df_recent = df_recent[["date", "category", "amount", "note"]]
        df_recent["amount"] = df_recent["amount"].apply(lambda x: f"${x:,.2f}")
        df_recent.columns = ["Date", "Category", "Amount", "Note"]
        st.dataframe(df_recent, use_container_width=True)
    else:
        st.write(f"No expenses recorded yet for {active_month}.")


# ============================================================================
# FEATURE 2: SET A MONTHLY BUDGET
# ============================================================================

elif menu_choice == "Set Budget":
    st.header("🎯 Set Monthly Category Budget")
    st.markdown("Assign or update budget limits for categories. Re-entering a category updates its budget without duplicates.")

    categories = api_get("/categories")
    if not categories:
        categories = ["Food", "Transport", "Rent", "Shopping", "Entertainment", "Bills", "Health", "Education", "Other"]

    with st.form(key="budget_form"):
        col1, col2, col3 = st.columns(3)
        with col1:
            target_month = st.text_input(
                "Month (YYYY-MM)",
                value=active_month,
                help="Format: YYYY-MM",
            )
        with col2:
            budget_category = st.selectbox("Category", options=categories)
        with col3:
            budget_amount = st.number_input(
                "Monthly Budget Amount ($)",
                min_value=1.00,
                max_value=1_000_000.00,
                step=50.00,
                format="%.2f",
                value=500.00,
            )

        budget_submit = st.form_submit_button("Save Budget", use_container_width=True)

    if budget_submit:
        # Frontend validation
        try:
            datetime.strptime(target_month.strip(), "%Y-%m")
            month_clean = target_month.strip()
        except ValueError:
            st.error("Month must be in YYYY-MM format (e.g. 2026-11).")
            month_clean = None

        if month_clean and budget_amount > 0:
            payload = {
                "month": month_clean,
                "category": budget_category,
                "amount": round(budget_amount, 2),
            }
            res = api_post("/budgets", json_data=payload)
            if res:
                st.success(f"Budget for {budget_category} in {month_clean} set to ${budget_amount:,.2f}!")
                st.session_state["selected_month"] = month_clean

    # Display current budgets for this month
    st.divider()
    st.subheader(f"Current Configured Budgets for {active_month}")
    budgets_list = api_get("/budgets", params={"month": active_month})
    if budgets_list and len(budgets_list) > 0:
        df_budgets = pd.DataFrame(budgets_list)
        df_budgets = df_budgets[["category", "amount"]]
        df_budgets["amount"] = df_budgets["amount"].apply(lambda x: f"${x:,.2f}")
        df_budgets.columns = ["Category", "Monthly Budget"]
        st.dataframe(df_budgets, use_container_width=True)
    else:
        st.info(f"No budgets configured yet for {active_month}. Use the form above or click 'Load Sample Data' in the sidebar.")


# ============================================================================
# FEATURE 3 & 4: MONTH SUMMARY & THRESHOLD ALERTS
# ============================================================================

elif menu_choice == "Month Summary":
    st.header(f"📊 Month Summary: {active_month}")

    summary_data = api_get("/summary", params={"month": active_month})

    if summary_data:
        # 1. High-level metric cards
        tot_budget = summary_data.get("total_budget", 0.0)
        tot_spent = summary_data.get("total_spent", 0.0)
        tot_rem = summary_data.get("total_remaining", 0.0)
        overall_pct = summary_data.get("overall_percentage")
        pct_display = f"{overall_pct:.1f}%" if overall_pct is not None else "N/A"

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Budget", f"${tot_budget:,.2f}")
        col2.metric("Total Spent", f"${tot_spent:,.2f}")
        col3.metric("Remaining", f"${tot_rem:,.2f}", delta=f"${tot_rem:,.2f}" if tot_budget > 0 else None)
        col4.metric("Overall Budget Used", pct_display)

        # 2. Prominent Alert Banners for Categories crossing thresholds
        alerts = summary_data.get("alerts", [])
        if alerts:
            st.subheader("⚠️ Active Threshold Alerts")
            for alert in alerts:
                if alert["status"] == "Exceeded":
                    st.error(alert["message"])
                elif alert["status"] == "Warning 80%":
                    st.warning(alert["message"])
        else:
            if tot_budget > 0 and tot_spent > 0:
                st.success("All budgeted categories are currently within healthy limits (< 80%).")

        st.divider()

        # 3. Category Breakdown Table
        st.subheader("Category Breakdown Table")
        cat_items = summary_data.get("categories", [])
        table_rows = []
        chart_rows = []

        for item in cat_items:
            cat_name = item["category"]
            b_val = item["budget"]
            s_val = item["spent"]
            r_val = item["remaining"]
            p_val = item["percentage"]
            status_val = item["status"]

            table_rows.append(
                {
                    "Category": cat_name,
                    "Budget": f"${b_val:,.2f}" if b_val is not None else "No budget set",
                    "Spent": f"${s_val:,.2f}",
                    "Remaining": f"${r_val:,.2f}" if r_val is not None else "-",
                    "% Used": f"{p_val:.1f}%" if p_val is not None else "-",
                    "Status": status_val,
                }
            )

            # Include in chart if either budget or spent is > 0
            if (b_val is not None and b_val > 0) or s_val > 0:
                chart_rows.append(
                    {
                        "Category": cat_name,
                        "Budget": b_val if b_val is not None else 0.0,
                        "Spent": s_val,
                    }
                )

        df_summary = pd.DataFrame(table_rows)
        st.dataframe(df_summary, use_container_width=True)

        # 4. Bar Chart: Budget vs Spent per Category
        if chart_rows:
            st.subheader("Spending vs Budget by Category")
            df_chart = pd.DataFrame(chart_rows).set_index("Category")
            st.bar_chart(df_chart, use_container_width=True)
        else:
            st.info(f"No expense or budget data found for {active_month}. Click 'Load Sample Data' in the sidebar to populate demo data.")


# ============================================================================
# FEATURE 5: TOP 5 LARGEST EXPENSES
# ============================================================================

elif menu_choice == "Top 5 Expenses":
    st.header(f"🏆 Top 5 Largest Expenses: {active_month}")
    st.markdown("The largest transactions of the month sorted in descending order.")

    top_data = api_get("/top-expenses", params={"month": active_month, "limit": 5})

    if top_data is not None:
        if len(top_data) == 0:
            st.info(f"No expenses recorded yet for {active_month}.")
        else:
            st.write(f"Showing the **{len(top_data)}** largest expense(s) for **{active_month}**:")

            # Display cards for top 3
            cols = st.columns(min(len(top_data), 3))
            for i, exp in enumerate(top_data[:3]):
                with cols[i]:
                    st.metric(
                        label=f"#{i+1} {exp['category']}",
                        value=f"${exp['amount']:,.2f}",
                        delta=exp["date"],
                    )
                    st.caption(f"Note: {exp['note'] or 'No note'}")

            st.divider()

            # Display full table of top expenses
            df_top = pd.DataFrame(top_data)
            df_top = df_top[["date", "category", "amount", "note"]]
            df_top["amount"] = df_top["amount"].apply(lambda x: f"${x:,.2f}")
            df_top.columns = ["Date", "Category", "Amount", "Note"]
            st.table(df_top)


# ============================================================================
# STRETCH FEATURE 1: COMPARE MONTHS
# ============================================================================

elif menu_choice == "Compare Months":
    st.header(f"🔄 Month-over-Month Comparison: {active_month}")
    st.markdown("Compare category-level and total spending between the selected month and the preceding month.")

    compare_data = api_get("/compare", params={"month": active_month})

    if compare_data:
        curr_m = compare_data.get("current_month")
        prev_m = compare_data.get("previous_month")
        t_last = compare_data.get("total_last_month", 0.0)
        t_this = compare_data.get("total_this_month", 0.0)
        t_diff = compare_data.get("total_difference", 0.0)
        t_pct = compare_data.get("total_percentage_change")

        # Metric summary
        col1, col2, col3, col4 = st.columns(4)
        col1.metric(f"Spent in {prev_m}", f"${t_last:,.2f}")
        col2.metric(f"Spent in {curr_m}", f"${t_this:,.2f}")
        delta_str = f"{'+' if t_diff > 0 else ''}${t_diff:,.2f}"
        col3.metric("Net Change ($)", f"${abs(t_diff):,.2f}", delta=delta_str, delta_color="inverse")
        pct_str = f"{'+' if (t_pct or 0) > 0 else ''}{t_pct:.1f}%" if t_pct is not None else "0.0%"
        col4.metric("% Change", pct_str, delta=pct_str, delta_color="inverse")

        st.divider()

        # Category Breakdown Comparison Table
        st.subheader("Category-by-Category Comparison")
        cat_comps = compare_data.get("categories", [])
        comp_rows = []
        chart_comps = []

        for c in cat_comps:
            cat = c["category"]
            slast = c["spent_last_month"]
            sthis = c["spent_this_month"]
            diff = c["difference"]
            pct = c["percentage_change"]
            desc = c["change_description"]

            comp_rows.append(
                {
                    "Category": cat,
                    f"Spent in {prev_m}": f"${slast:,.2f}",
                    f"Spent in {curr_m}": f"${sthis:,.2f}",
                    "Difference ($)": f"{'+' if diff > 0 else ''}${diff:,.2f}",
                    "% Change": f"{'+' if pct > 0 else ''}{pct:.1f}%" if pct is not None else "N/A",
                    "Trend Analysis": desc,
                }
            )

            if slast > 0 or sthis > 0:
                chart_comps.append(
                    {
                        "Category": cat,
                        f"Last Month ({prev_m})": slast,
                        f"This Month ({curr_m})": sthis,
                    }
                )

        df_comp = pd.DataFrame(comp_rows)
        st.dataframe(df_comp, use_container_width=True)

        # Comparison Bar Chart
        if chart_comps:
            st.subheader(f"Visual Spending Comparison ({prev_m} vs {curr_m})")
            df_chart_comp = pd.DataFrame(chart_comps).set_index("Category")
            st.bar_chart(df_chart_comp, use_container_width=True)


# ============================================================================
# STRETCH FEATURE 2: EXPORT CSV
# ============================================================================

elif menu_choice == "Export CSV":
    st.header(f"📥 Export Expenses for {active_month}")
    st.markdown("Download all expense records for the selected month as a CSV file.")

    # Preview expenses
    expenses = api_get("/expenses", params={"month": active_month})

    if expenses is not None:
        if len(expenses) == 0:
            st.info(f"No expenses to export for {active_month}. Click 'Load Sample Data' in the sidebar to populate records.")
        else:
            st.write(f"Found **{len(expenses)}** expense record(s) ready for export.")

            # Fetch CSV from backend
            csv_content = api_get("/export", params={"month": active_month})

            if csv_content:
                st.download_button(
                    label=f"⬇️ Download {active_month} Expenses CSV",
                    data=csv_content,
                    file_name=f"expenses_{active_month}.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            st.divider()
            st.subheader("Data Preview")
            df_export = pd.DataFrame(expenses)
            df_export = df_export[["id", "date", "category", "amount", "note"]]
            df_export["amount"] = df_export["amount"].apply(lambda x: f"${x:,.2f}")
            df_export.columns = ["ID", "Date", "Category", "Amount", "Note"]
            st.dataframe(df_export, use_container_width=True)

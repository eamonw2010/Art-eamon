import json
import math
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Dict, Optional, Tuple
import numpy as np
import pandas as pd
import streamlit as st

TWO_PLACES = Decimal("0.01")


def d(val: Any) -> Decimal:
    """Convert numeric or string values safely into two-decimal USD Decimal."""
    return Decimal(str(val)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def default_art2_state(team_id: str = "TEAM-ART-01") -> Dict[str, Any]:
    """Return opening post-startup state for ART-2 (Precalculus - Design and animation studio)."""
    return {
        "team_id": team_id,
        "course": "Precalculus",
        "pathway_id": "ART-2",
        "business_name": "Design and animation studio",
        "primary_offering": "Branding package",
        "base_offerings": [
            "Branding package",
            "Animated explainer",
            "Event poster package",
        ],
        "selected_level": "Applied",  # Foundation | Applied | Advanced
        "teacher_approved_skills": [
            "Rational Average Cost & Asymptotes",
            "Function Composition & Piecewise Profit",
            "Seasonal Trigonometric Demand Extension",
        ],
        "snapshot_id": "SNAP-000",
        "state_version": 1,
        "simulation_date": "2026-12-31",
        "base_period": "Monthly",
        "working_days": 22,
        "currency": "USD",
        "random_seed": 2027,
        "funding": {
            "owner_contribution": "7000.00",
            "equipment_assets": "1800.00",
            "pre_opening_expense": "1200.00",
            "opening_inventory": "0.00",
            "opening_cash": "4000.00",
            "retained_earnings": "-1200.00",
            "loan_debt": "0.00",
        },
        "inputs": {
            "base_price": "180.00",
            "D0": 18,
            "staff_hours": 90.0,
            "hours_per_unit": 6.0,
            "revision_hours_per_project": 0.0,
            "extra_revision_hourly_cost": "5.00",
            "asset_license_verified": True,
        },
        "variable_cost_lines": {
            "creative_labor": "25.00",
            "licensed_assets": "10.00",
            "rendering": "5.00",
            "delivery_print": "5.00",
        },
        "fixed_cost_lines": {
            "software": "250.00",
            "workspace": "250.00",
            "admin": "150.00",
            "equipment_maintenance": "150.00",
        },
        "current_cash": "4000.00",
        "current_debt": "0.00",
        "executed_run_ids": [],
        "ledger": [],
        "monthly_summaries": [],
        "campaigns": [],
        "recommendations": [],
        "decisions": [],
    }


def compute_capacity_and_unit_cost(state: Dict[str, Any]) -> Tuple[int, Decimal]:
    inp = state["inputs"]
    staff_hours = float(inp["staff_hours"])
    hours_per_unit = float(inp["hours_per_unit"])
    rev_hours = float(inp["revision_hours_per_project"])
    extra_rev_cost = d(inp["extra_revision_hourly_cost"])

    total_hours_per_project = hours_per_unit + rev_hours
    if total_hours_per_project <= 0:
        raise ValueError("Total hours per project must be > 0.")
    if staff_hours < 0 or rev_hours < 0 or extra_rev_cost < Decimal("0.00"):
        raise ValueError("Hours and costs must be nonnegative.")

    capacity = math.floor(staff_hours / total_hours_per_project)
    base_var = sum((d(v) for v in state["variable_cost_lines"].values()), Decimal("0.00"))
    unit_var = (base_var + d(rev_hours) * extra_rev_cost).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )
    return capacity, unit_var


def compute_fixed_monthly_cost(state: Dict[str, Any]) -> Decimal:
    return sum((d(v) for v in state["fixed_cost_lines"].values()), Decimal("0.00"))


def step_month(
    state: Dict[str, Any],
    *,
    run_id: str,
    sim_date: str,
    requested: int,
    price_override: Optional[Decimal] = None,
    capacity_override: Optional[int] = None,
    ad_cost: Decimal = Decimal("0.00"),
    loan_cash: Decimal = Decimal("0.00"),
    principal_repayment: Decimal = Decimal("0.00"),
    interest_expense: Decimal = Decimal("0.00"),
    additional_capex: Decimal = Decimal("0.00"),
    refund_amount: Decimal = Decimal("0.00"),
) -> Tuple[Dict[str, Any], bool, str]:
    if run_id in state["executed_run_ids"]:
        return state, False, f"Duplicate run_id '{run_id}' rejected; no new transactions recorded."

    if (
        requested < 0
        or ad_cost < 0
        or loan_cash < 0
        or principal_repayment < 0
        or interest_expense < 0
        or additional_capex < 0
        or refund_amount < 0
    ):
        raise ValueError("Quantities and monetary outflows/inflows cannot be negative.")

    derived_cap, unit_var = compute_capacity_and_unit_cost(state)
    effective_cap = int(capacity_override) if capacity_override is not None else derived_cap
    if effective_cap < 0:
        raise ValueError("Capacity cannot be negative.")

    price = d(price_override) if price_override is not None else d(state["inputs"]["base_price"])
    sold = min(int(requested), effective_cap)
    unserved = max(0, int(requested) - sold)

    revenue = (price * Decimal(sold)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    var_expense = (unit_var * Decimal(sold)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    fixed_expense = compute_fixed_monthly_cost(state)
    marketing_expense = d(ad_cost)
    interest_exp = d(interest_expense)
    refund_amt = d(refund_amount)

    net_revenue = revenue - refund_amt
    operating_profit = net_revenue - var_expense - fixed_expense - marketing_expense
    net_profit = operating_profit - interest_exp
    total_operating_expense = var_expense + fixed_expense + marketing_expense

    opening_cash = d(state["current_cash"])
    opening_debt = d(state["current_debt"])

    closing_cash = (
        opening_cash
        + net_revenue
        - var_expense
        - fixed_expense
        - marketing_expense
        - interest_exp
        - d(principal_repayment)
        - d(additional_capex)
        + d(loan_cash)
    ).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)
    closing_debt = (opening_debt + d(loan_cash) - d(principal_repayment)).quantize(
        TWO_PLACES, rounding=ROUND_HALF_UP
    )

    next_version = int(state["state_version"]) + 1
    tx_base = f"TX-{next_version:03d}"

    new_entries = [
        {
            "transaction_id": f"{tx_base}-REV",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "sales_revenue",
            "category": "Revenue",
            "amount": f"{net_revenue:.2f}",
            "quantity": sold,
            "requested_demand": int(requested),
            "unserved_demand": unserved,
            "unit_price": f"{price:.2f}",
            "offering_id": state["primary_offering"],
            "state_version": next_version,
        },
        {
            "transaction_id": f"{tx_base}-VAR",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "variable_expense",
            "category": "Cost of Sales",
            "amount": f"{var_expense:.2f}",
            "quantity": sold,
            "unit_price": f"{unit_var:.2f}",
            "offering_id": state["primary_offering"],
            "state_version": next_version,
        },
        {
            "transaction_id": f"{tx_base}-FIX",
            "run_id": run_id,
            "date": sim_date,
            "event_type": "fixed_expense",
            "category": "Operating Expense",
            "amount": f"{fixed_expense:.2f}",
            "quantity": 1,
            "unit_price": f"{fixed_expense:.2f}",
            "offering_id": "STUDIO-OVERHEAD",
            "state_version": next_version,
        },
    ]

    if marketing_expense > Decimal("0.00"):
        new_entries.append(
            {
                "transaction_id": f"{tx_base}-MKT",
                "run_id": run_id,
                "date": sim_date,
                "event_type": "marketing_expense",
                "category": "Own Advertising",
                "amount": f"{marketing_expense:.2f}",
                "quantity": 1,
                "unit_price": f"{marketing_expense:.2f}",
                "offering_id": "OWN-CAMPAIGN",
                "state_version": next_version,
            }
        )

    if d(loan_cash) > Decimal("0.00"):
        new_entries.append(
            {
                "transaction_id": f"{tx_base}-LOAN",
                "run_id": run_id,
                "date": sim_date,
                "event_type": "loan_receipt",
                "category": "Financing Cash Inflow",
                "amount": f"{d(loan_cash):.2f}",
                "quantity": 1,
                "unit_price": f"{d(loan_cash):.2f}",
                "offering_id": "FINANCING",
                "state_version": next_version,
            }
        )

    summary_row = {
        "run_id": run_id,
        "month": sim_date,
        "mode": "FIXTURE_OVERRIDE" if capacity_override is not None else "NORMAL",
        "requested": int(requested),
        "capacity_used": effective_cap,
        "sold": sold,
        "unserved": unserved,
        "revenue": f"{net_revenue:.2f}",
        "variable_expense": f"{var_expense:.2f}",
        "fixed_expense": f"{fixed_expense:.2f}",
        "marketing_expense": f"{marketing_expense:.2f}",
        "total_expense": f"{total_operating_expense:.2f}",
        "operating_profit": f"{operating_profit:.2f}",
        "net_profit": f"{net_profit:.2f}",
        "closing_cash": f"{closing_cash:.2f}",
        "closing_debt": f"{closing_debt:.2f}",
        "state_version": next_version,
    }

    updated = json.loads(json.dumps(state))
    updated["state_version"] = next_version
    updated["snapshot_id"] = f"SNAP-{next_version:03d}"
    updated["simulation_date"] = sim_date
    updated["current_cash"] = f"{closing_cash:.2f}"
    updated["current_debt"] = f"{closing_debt:.2f}"
    updated["executed_run_ids"].append(run_id)
    updated["ledger"].extend(new_entries)
    updated.setdefault("monthly_summaries", []).append(summary_row)

    return updated, True, f"Recorded period {sim_date} (run_id={run_id}, state_version=v{next_version})."


def replay_builtin_fixture(base_state: Dict[str, Any]) -> Dict[str, Any]:
    """Reset to opening state and replay built-in ART monthly_fixture rows."""
    fixture_rows = [
        {"month": "2027-01", "requested": 18, "capacity_override": 15, "ad_cost": "0"},
        {"month": "2027-02", "requested": 20, "capacity_override": 15, "ad_cost": "100"},
        {"month": "2027-03", "requested": 16, "capacity_override": 11, "ad_cost": "0"},
    ]
    state = default_art2_state(team_id=base_state.get("team_id", "TEAM-ART-01"))
    state["selected_level"] = base_state.get("selected_level", "Applied")
    for row in fixture_rows:
        state, _, _ = step_month(
            state,
            run_id=f"FIXTURE-{row['month']}",
            sim_date=row["month"],
            requested=row["requested"],
            capacity_override=row["capacity_override"],
            ad_cost=d(row["ad_cost"]),
        )
    return state


def precalc_average_cost_table(F: float, v: float, capacity: int) -> pd.DataFrame:
    rows = [
        {
            "s (projects)": 0,
            "C(s) ($)": round(F, 2),
            "A(s) ($/project)": np.nan,
            "Note": "Undefined (vertical asymptote s=0)",
        }
    ]
    for s in range(1, max(1, capacity) + 1):
        c_val = F + v * s
        a_val = F / s + v
        rows.append(
            {
                "s (projects)": s,
                "C(s) ($)": round(c_val, 2),
                "A(s) ($/project)": round(a_val, 2),
                "Note": "Practical domain boundary (capacity)" if s == capacity else "Feasible integer output",
            }
        )
    return pd.DataFrame(rows)


def precalc_composed_price_curve(
    p0: float, D0: float, F: float, v: float, capacity: int
) -> Tuple[pd.DataFrame, Optional[float]]:
    p_max = 2.0 * p0
    prices = np.linspace(0.0, p_max, 181)
    slope = D0 / p0
    q_vals = np.maximum(0.0, 2.0 * D0 - slope * prices)
    s_cont = np.minimum(float(capacity), q_vals)
    r_cont = prices * s_cont
    c_cont = F + v * s_cont
    p_cont = r_cont - c_cont

    s_int = np.floor(s_cont)
    p_int = prices * s_int - (F + v * s_int)

    breakpoint_p = p0 * (2.0 - float(capacity) / D0) if D0 > 0 else None
    if breakpoint_p is not None and not (0.0 <= breakpoint_p <= p_max):
        breakpoint_p = None

    df = pd.DataFrame(
        {
            "price_p ($)": np.round(prices, 2),
            "demand_q(p)": np.round(q_vals, 3),
            "completed_s(p)_continuous": np.round(s_cont, 3),
            "revenue_R(p)_continuous ($)": np.round(r_cont, 2),
            "cost_C(s(p))_continuous ($)": np.round(c_cont, 2),
            "profit_P(p)_continuous ($)": np.round(p_cont, 2),
            "completed_s(p)_integer": s_int.astype(int),
            "profit_P(p)_integer ($)": np.round(p_int, 2),
        }
    )
    return df, breakpoint_p


def precalc_seasonal_model(D0: float, capacity: int) -> pd.DataFrame:
    months = np.arange(1, 13)
    raw_demand = D0 * (1.0 + 0.20 * np.sin(2.0 * np.pi * (months - 1) / 12.0))
    clipped_sales = np.minimum(float(capacity), np.floor(raw_demand))
    return pd.DataFrame(
        {
            "Month_t": months,
            "Modeled_Demand_D(t)": np.round(raw_demand, 2),
            "Capacity_Cap": capacity,
            "Realized_Sales_min(cap,floor(D(t)))": clipped_sales.astype(int),
        }
    )


def validate_and_load_snapshot(
    raw_json: str, expected_team_id: str, current_version: int
) -> Tuple[Optional[Dict[str, Any]], str]:
    try:
        data = json.loads(raw_json)
    except json.JSONDecodeError as exc:
        return None, f"Invalid JSON syntax: {exc}"

    required_keys = {
        "team_id",
        "course",
        "pathway_id",
        "snapshot_id",
        "state_version",
        "inputs",
        "variable_cost_lines",
        "fixed_cost_lines",
        "current_cash",
        "ledger",
    }
    missing = required_keys - set(data.keys())
    if missing:
        return None, f"Rejected import: missing required fields {sorted(missing)}."

    if data["team_id"] != expected_team_id:
        return (
            None,
            f"Rejected import: team_id '{data['team_id']}' does not match active team '{expected_team_id}'.",
        )

    if data["pathway_id"] != "ART-2":
        return None, f"Rejected import: expected pathway 'ART-2', got '{data['pathway_id']}'."

    imported_version = int(data["state_version"])
    if imported_version < current_version:
        return (
            None,
            f"Rejected stale snapshot: imported v{imported_version} is older than active state v{current_version}.",
        )

    return data, f"Loaded snapshot {data['snapshot_id']} (v{imported_version}) for {data['team_id']}."


def main() -> None:
    st.set_page_config(page_title="Career Venture Lab | ART-2 Precalculus", layout="wide")

    if "biz_state" not in st.session_state:
        st.session_state.biz_state = default_art2_state()

    state = st.session_state.biz_state

    with st.sidebar:
        st.header("ART-2 Control Panel")
        st.caption("Course: Precalculus | Pathway: ART-2 (Design & Animation Studio)")
        st.info(
            f"**Team:** {state['team_id']}  \n"
            f"**Snapshot:** {state['snapshot_id']} (v{state['state_version']})  \n"
            f"**Sim Date:** {state['simulation_date']}  \n"
            f"**Active Level:** {state['selected_level']}"
        )

        st.subheader("Math Challenge Level")
        new_level = st.selectbox(
            "Teacher-Approved Level",
            ["Foundation", "Applied", "Advanced"],
            index=["Foundation", "Applied", "Advanced"].index(state["selected_level"]),
        )
        if new_level != state["selected_level"]:
            state["selected_level"] = new_level
            st.success(f"Updated challenge level to {new_level}.")

        st.divider()
        st.subheader("Durable Save / Restore (JSON)")
        snapshot_json_str = json.dumps(state, indent=2)
        st.download_button(
            label="Export Snapshot JSON",
            data=snapshot_json_str,
            file_name=f"{state['team_id']}_{state['snapshot_id']}_v{state['state_version']}.json",
            mime="application/json",
        )

        uploaded_json = st.file_uploader("Restore Snapshot JSON", type=["json"])
        if uploaded_json is not None and st.button("Validate & Import Snapshot"):
            loaded, msg = validate_and_load_snapshot(
                uploaded_json.read().decode("utf-8"),
                expected_team_id=state["team_id"],
                current_version=state["state_version"],
            )
            if loaded is None:
                st.error(msg)
            else:
                st.session_state.biz_state = loaded
                st.success(msg)
                st.rerun()

        if st.button("Reset to Opening Post-Startup State"):
            st.session_state.biz_state = default_art2_state(team_id=state["team_id"])
            st.warning("Reset to v1 post-startup baseline ($4,000 cash).")
            st.rerun()

    st.title("Career Venture Lab: Design & Animation Studio (ART-2)")
    st.caption("Stage 1 Build: Deterministic Ledger, Precalculus Math Panel, Fixture Verification & JSON Persistence")

    cap, unit_var = compute_capacity_and_unit_cost(state)
    fixed_mo = compute_fixed_monthly_cost(state)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Current Spendable Cash", f"${d(state['current_cash']):,.2f}")
    k2.metric("Derived Monthly Capacity", f"{cap} projects")
    k3.metric("Unit Variable Cost (v)", f"${unit_var:,.2f} / project")
    k4.metric("Monthly Fixed Cost (F)", f"${fixed_mo:,.2f} / month")

    tabs = st.tabs(
        [
            "1. Overview & System Map",
            "2. Inputs, Funding & Ledger",
            "3. Precalculus Math Skills Panel",
            "4. Cross-Course & Stage 2-4 Roadmap",
        ]
    )

    with tabs[0]:
        st.subheader("Studio Operating Overview")
        st.markdown(
            """
            **Primary Offering (Stage 1 Acceptance):** Branding package ($180 baseline)  
            **Additional Portfolio Offerings (Stage 2+ Separate Allocation):** Animated explainer; Event poster package  
            **Operating Rule:** `capacity = floor(staff_hours / (hours_per_unit + revision_hours_per_project))`; `sold = min(requested, capacity)`. Unverified asset licenses block draft publishing, not internal accounting.
            """
        )
        st.markdown("#### Departmental System Map & Feedback Loop")
        st.code(
            "[Marketing Studio (Costed Drafts)] --(Campaign ID & Reach)--> [Customer Demand q(p)]\n"
            "        ^                                                              |\n"
            "        | (Revision & Cash Review)                                     v\n"
            "[Finance & Reports] <---(Completed Sales & Costs)--- [Operations: Staff & Revision Hours]\n"
            "        |                                                              |\n"
            "        +---(Pending Proposals)---> [STUDENT APPROVAL GATE] <----------+ (Delivery Lead Time -> Satisfaction)",
            language="text",
        )

        if state.get("monthly_summaries"):
            st.subheader("Recorded Monthly Simulation Runs (Actual Ledger Summary)")
            df_sum = pd.DataFrame(state["monthly_summaries"])
            st.dataframe(df_sum, use_container_width=True)
            st.download_button(
                "Export Ledger CSV",
                data=pd.DataFrame(state["ledger"]).to_csv(index=False),
                file_name=f"{state['team_id']}_ledger_v{state['state_version']}.csv",
                mime="text/csv",
            )
        else:
            st.info("No simulation months committed yet. Use Tab 2 to run a month or replay the built-in fixture.")

    with tabs[1]:
        col_in, col_run = st.columns([1, 1])

        with col_in:
            st.subheader("Startup Financing & Editable Studio Parameters")
            st.write("**Opening Balance Sheet (Post-Startup):** Owner Contribution $7,000.00 | Equipment $1,800.00 | Pre-Opening Expense $1,200.00 | Opening Cash $4,000.00 | Retained Earnings -$1,200.00")

            with st.form("params_form"):
                p_base = st.number_input("Base Price ($/project)", min_value=1.0, value=float(state["inputs"]["base_price"]), step=5.0)
                d0_val = st.number_input("Baseline Monthly Demand D0 (projects)", min_value=0, value=int(state["inputs"]["D0"]), step=1)
                s_hrs = st.number_input("Productive Staff Hours / Month", min_value=0.0, value=float(state["inputs"]["staff_hours"]), step=5.0)
                h_unit = st.number_input("Base Hours / Project", min_value=0.5, value=float(state["inputs"]["hours_per_unit"]), step=0.5)
                rev_hrs = st.number_input("Extra Revision Hours / Project", min_value=0.0, value=float(state["inputs"]["revision_hours_per_project"]), step=0.5)
                rev_cost = st.number_input("Extra Revision Hourly Cost ($/hr)", min_value=0.0, value=float(state["inputs"]["extra_revision_hourly_cost"]), step=1.0)
                lic_ok = st.checkbox("Asset License Verified (Publishing Gate)", value=bool(state["inputs"]["asset_license_verified"]))

                if st.form_submit_button("Save Parameter Assumptions"):
                    state["inputs"]["base_price"] = f"{d(p_base):.2f}"
                    state["inputs"]["D0"] = int(d0_val)
                    state["inputs"]["staff_hours"] = float(s_hrs)
                    state["inputs"]["hours_per_unit"] = float(h_unit)
                    state["inputs"]["revision_hours_per_project"] = float(rev_hrs)
                    state["inputs"]["extra_revision_hourly_cost"] = f"{d(rev_cost):.2f}"
                    state["inputs"]["asset_license_verified"] = lic_ok
                    st.success("Studio parameters updated.")
                    st.rerun()

        with col_run:
            st.subheader("Execute Single Month (Normal Mode)")
            with st.form("step_form"):
                run_id_in = st.text_input("Unique Run ID", value=f"RUN-{state['state_version']:03d}")
                sim_date_in = st.text_input("Month End Date (YYYY-MM-DD)", value="2027-01-31")
                req_in = st.number_input("Requested Projects", min_value=0, value=int(state["inputs"]["D0"]), step=1)
                ad_in = st.number_input("Approved Own-Studio Ad Expense ($)", min_value=0.0, value=0.0, step=10.0)
                loan_in = st.number_input("New Simulated Loan Proceeds ($ - Financing, not Revenue)", min_value=0.0, value=0.0, step=100.0)

                if st.form_submit_button("Approve & Advance Simulation Month"):
                    try:
                        updated, ok, msg = step_month(
                            state,
                            run_id=run_id_in.strip(),
                            sim_date=sim_date_in.strip(),
                            requested=int(req_in),
                            ad_cost=d(ad_in),
                            loan_cash=d(loan_in),
                        )
                        if ok:
                            st.session_state.biz_state = updated
                            st.success(msg)
                            st.rerun()
                        else:
                            st.error(msg)
                    except ValueError as err:
                        st.error(str(err))

            st.divider()
            st.subheader("Fixture Replay Mode (Acceptance Verification)")
            st.warning("Fixture mode resets to opening post-startup state ($4,000 cash) and uses explicit `capacity_override` values from the ART handbook fixture.")
            if st.button("Reset & Replay ART 3-Month Fixture"):
                st.session_state.biz_state = replay_builtin_fixture(state)
                st.success("Replayed 3 fixture months (2027-01 to 2027-03). Closing cash = $7,035.00.")
                st.rerun()

    with tabs[2]:
        level = state["selected_level"]
        p0_f = float(state["inputs"]["base_price"])
        D0_f = float(state["inputs"]["D0"])
        F_f = float(fixed_mo)
        v_f = float(unit_var)

        st.subheader(f"Precalculus Math Skills Panel — Level: {level}")
        st.markdown(
            f"**Current Parameters:** $p_0 = \${p0_f:.2f}$, $D_0 = {int(D0_f)}$ projects, $F = \${F_f:.2f}$, $v = \${v_f:.2f}$/project, $\text{{Capacity}} = {cap}$ projects"
        )

        if level == "Foundation":
            st.markdown(
                f"""
                **Business Question:** How does average cost per design project behave as output approaches zero versus studio capacity?  
                **Equations:** $C(s) = {F_f:.0f} + {v_f:.0f}s$ and $A(s) = \frac{{C(s)}}{{s}} = \frac{{{F_f:.0f}}}{{s}} + {v_f:.0f}$  
                **Domain & Asymptotes:** Practical integer domain $s \in \{{1, 2, \dots, {cap}\}}$ (continuous $0 < s \le {cap}$). Vertical asymptote at $s = 0$ ($A(0)$ is undefined because fixed overhead cannot divide across zero projects); horizontal asymptote at $y = {v_f:.2f}$ as $s \to \infty$.
                """
            )
            df_avg = precalc_average_cost_table(F_f, v_f, cap)
            c1, c2 = st.columns([1, 1])
            with c1:
                st.dataframe(df_avg, use_container_width=True)
            with c2:
                plot_df = df_avg.dropna(subset=["A(s) ($/project)"]).set_index("s (projects)")
                st.line_chart(plot_df[["A(s) ($/project)"]])
            st.info(
                f"**Individual Check Prompt:** Compare $C({cap}) = \${F_f + v_f * cap:,.2f}$ (total monthly dollars) with $A({cap}) = \${(F_f / cap + v_f) if cap > 0 else 0:,.2f}$ (dollars per project), and explain why $s = 0$ is excluded."
            )

        elif level == "Applied":
            st.markdown(
                f"""
                **Business Question:** How does composing demand $q(p)$ into revenue $R(p)$ and cost $C(s(p))$ affect profit across the capacity boundary?  
                **Equations (Continuous Model vs. Integer Rounding):**  
                - Demand: $q(p) = \max(0, {2*D0_f:.0f} - {D0_f/p0_f:.4f}p)$ on $0 \le p \le {2*p0_f:.0f}$  
                - Capacity-capped output: $s(p) = \min({cap}, q(p))$  
                - Composed Revenue & Cost: $R(p) = p \cdot s(p)$, $C(s(p)) = {F_f:.0f} + {v_f:.0f} \cdot s(p)$, $P(p) = R(p) - C(s(p))$
                """
            )
            df_comp, bp = precalc_composed_price_curve(p0_f, D0_f, F_f, v_f, cap)
            if bp is not None:
                st.success(f"**Capacity Breakpoint:** $p = p_0(2 - \text{{cap}}/D_0) = \${bp:.2f}$. Below $\${bp:.2f}$, completed projects are capped at {cap}.")
            test_p = st.slider("Interactive Price Prediction Check ($)", min_value=0, max_value=int(2 * p0_f), value=int(p0_f), step=5)
            q_at_p = max(0.0, 2.0 * D0_f - (D0_f / p0_f) * test_p)
            s_at_p = min(float(cap), q_at_p)
            prof_at_p = test_p * s_at_p - (F_f + v_f * s_at_p)
            st.write(f"At **${test_p}**: continuous demand $q({test_p}) = {q_at_p:.2f}$, completed $s({test_p}) = {s_at_p:.2f}$ (integer floor: {int(s_at_p)}), continuous profit $P({test_p}) = \${prof_at_p:,.2f}$.")

            st.line_chart(
                df_comp.set_index("price_p ($)")[
                    ["revenue_R(p)_continuous ($)", "cost_C(s(p))_continuous ($)", "profit_P(p)_continuous ($)"]
                ]
            )
            with st.expander("View Input-Output Composition Table (Exportable)"):
                st.dataframe(df_comp, use_container_width=True)
                st.download_button(
                    "Export Composition Table CSV",
                    data=df_comp.to_csv(index=False),
                    file_name=f"{state['team_id']}_precalc_applied_composition.csv",
                    mime="text/csv",
                )

        else:
            st.markdown(
                f"""
                **Business Question:** How does seasonal demand affect monthly capacity utilization and realized studio sales across a 12-month cycle?  
                **Equation (Trigonometric Extension):** $D(t) = {D0_f:.0f}\left(1 + 0.20\sin\left(\frac{{2\pi(t - 1)}}{{12}}\right)\right)$ for month $t \in [1, 12]$, clipped at capacity $= {cap}$.  
                **Assumptions & Limitations:** Assumes a 12-month periodic cycle peaking at $t = 4$ ($1.20 D_0 = {1.2*D0_f:.2f}$) and troughing at $t = 10$ ($0.80 D_0 = {0.8*D0_f:.2f}$). This is a synthetic planning model, not empirical forecast proof.
                """
            )
            df_seas = precalc_seasonal_model(D0_f, cap)
            st.line_chart(df_seas.set_index("Month_t")[["Modeled_Demand_D(t)", "Realized_Sales_min(cap,floor(D(t)))"]])
            st.dataframe(df_seas, use_container_width=True)

    with tabs[3]:
        st.subheader("Cross-Course Connections & Implementation Status")
        st.markdown(
            """
            - **Art / Media & Design:** Document asset rights (`asset_license_verified`), defend visual hierarchy, and analyze client satisfaction vs. revision hours (`revision_hours_per_project`).
            - **Computer Science:** Enforce JSON schema validation, stale-version rejection, and duplicate `run_id` protection.
            - **Stage 2-4 Modules (Marked Unfinished in Stage 1):** Departmental AI Tabs (Finance, Operations, Marketing, Reviewer), Full Report Center PDF export, Costed Marketing Studio, Frozen-Snapshot Assessment Panel, and Optional Storefront.
            """
        )


if __name__ == "__main__":
    main()

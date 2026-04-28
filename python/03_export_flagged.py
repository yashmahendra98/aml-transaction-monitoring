"""
03_export_flagged.py — Export flagged accounts for Power BI
AML Transaction Monitoring Project

Reads processed CSVs from 02_risk_scoring.py and produces
Power BI-ready exports in data/powerbi/

Output files:
  - powerbi_high_risk_accounts.csv
  - powerbi_fraud_by_type.csv
  - powerbi_hourly_fraud.csv
  - powerbi_risk_summary.csv
  - powerbi_cc_flagged_transactions.csv
"""

import os
import pandas as pd
import numpy as np

PROC_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
PBI_DIR  = os.path.join(os.path.dirname(__file__), "..", "data", "powerbi")
os.makedirs(PBI_DIR, exist_ok=True)


def export_paysim(ps_risk_path: str):
    print("Exporting PaySim tables …")
    ps = pd.read_csv(ps_risk_path)

    # 1. High-risk accounts — top priority review queue
    high_risk = (
        ps[ps["risk_tier"] == "HIGH"]
        .sort_values("composite_risk_score", ascending=False)
        [[
            "account_id", "tx_count", "total_volume", "avg_amount",
            "max_amount", "fraud_count", "drain_events",
            "composite_risk_score", "risk_tier"
        ]]
    )
    high_risk.to_csv(os.path.join(PBI_DIR, "powerbi_high_risk_accounts.csv"), index=False)
    print(f"  High-risk accounts  : {len(high_risk):,} rows")

    # 2. Risk summary for KPI cards
    summary = (
        ps.groupby("risk_tier", observed=True)
        .agg(
            account_count   = ("account_id", "count"),
            total_fraud_txns= ("fraud_count", "sum"),
            avg_volume      = ("total_volume", "mean"),
            avg_score       = ("composite_risk_score", "mean"),
        )
        .reset_index()
    )
    summary["pct_of_total"] = (summary["account_count"] / summary["account_count"].sum() * 100).round(2)
    summary = summary.sort_values("risk_tier", key=lambda x: x.map({"HIGH": 0, "MEDIUM": 1, "LOW": 2}))
    summary.to_csv(os.path.join(PBI_DIR, "powerbi_risk_summary.csv"), index=False)
    print(f"  Risk summary        : {len(summary)} rows")


def export_paysim_fraud_type(paysim_raw_path: str):
    """Rebuild fraud-by-type table from raw PaySim (needs raw for type column)."""
    import glob
    raw_files = glob.glob(paysim_raw_path)
    if not raw_files:
        print("  Raw PaySim not found — skipping fraud_by_type export.")
        return

    print("  Loading raw PaySim for fraud-by-type table …")
    ps_raw = pd.read_csv(raw_files[0])

    fraud_type = (
        ps_raw.groupby("type")
        .agg(
            total_txns  = ("amount", "count"),
            fraud_count = ("isFraud", "sum"),
            total_volume= ("amount", "sum"),
            avg_amount  = ("amount", "mean"),
        )
        .reset_index()
    )
    fraud_type["fraud_rate_pct"] = (fraud_type["fraud_count"] / fraud_type["total_txns"] * 100).round(4)
    fraud_type.to_csv(os.path.join(PBI_DIR, "powerbi_fraud_by_type.csv"), index=False)
    print(f"  Fraud by type       : {len(fraud_type)} rows")


def export_creditcard(cc_risk_path: str, hourly_path: str):
    print("Exporting Credit Card tables …")

    # Flagged transactions
    cc = pd.read_csv(cc_risk_path)
    flagged = cc[cc["risk_tier"].isin(["MEDIUM", "HIGH"])][
        ["Time", "Amount", "Class", "hour", "amount_zscore",
         "spike_flag", "night_window", "risk_score", "risk_tier", "flag_reason"]
    ].sort_values("risk_score", ascending=False)
    flagged.to_csv(os.path.join(PBI_DIR, "powerbi_cc_flagged_transactions.csv"), index=False)
    print(f"  CC flagged txns     : {len(flagged):,} rows")

    # Hourly fraud rates
    if os.path.exists(hourly_path):
        hourly = pd.read_csv(hourly_path)
        hourly.to_csv(os.path.join(PBI_DIR, "powerbi_hourly_fraud.csv"), index=False)
        print(f"  Hourly fraud rates  : {len(hourly)} rows")
    else:
        print("  Hourly fraud CSV not found — run 01_eda.py first.")


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import glob

    PS_RISK    = os.path.join(PROC_DIR, "paysim_account_risk.csv")
    CC_RISK    = os.path.join(PROC_DIR, "cc_risk_flagged.csv")
    CC_HOURLY  = os.path.join(PROC_DIR, "cc_hourly_fraud_rates.csv")
    PS_RAW_GLOB = os.path.join(PROC_DIR, "..", "raw", "PS_*.csv")

    if os.path.exists(PS_RISK):
        export_paysim(PS_RISK)
    else:
        print("PaySim risk file not found — run 02_risk_scoring.py first.")

    export_paysim_fraud_type(PS_RAW_GLOB)

    if os.path.exists(CC_RISK):
        export_creditcard(CC_RISK, CC_HOURLY)
    else:
        print("CC risk file not found — run 02_risk_scoring.py first.")

    print(f"\nAll Power BI exports saved to data/powerbi/")
    print("Import each CSV into Power BI as a separate table.")
    print("Recommended relationships: risk_tier (all tables) → risk_summary.risk_tier")

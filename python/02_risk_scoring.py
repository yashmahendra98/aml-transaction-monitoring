"""
02_risk_scoring.py — 3-Tier Risk Segmentation
AML Transaction Monitoring Project

Produces:
  - data/processed/paysim_account_risk.csv
  - data/processed/cc_risk_flagged.csv
"""

import os
import glob
import pandas as pd
import numpy as np

RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
os.makedirs(OUT_DIR, exist_ok=True)

paysim_files = glob.glob(os.path.join(RAW_DIR, "PS_*.csv"))
CC_PATH      = os.path.join(RAW_DIR, "creditcard.csv")
PAYSIM_PATH  = paysim_files[0] if paysim_files else None


# ════════════════════════════════════════════════════════════
# PAYSIM — Account-level risk scoring
# ════════════════════════════════════════════════════════════

def score_paysim_accounts(ps: pd.DataFrame) -> pd.DataFrame:
    """Build per-account composite risk score with 3-tier segmentation."""

    # 1. Per-account aggregation
    acct = ps.groupby("nameOrig").agg(
        tx_count         = ("amount",        "count"),
        total_volume     = ("amount",        "sum"),
        avg_amount       = ("amount",        "mean"),
        max_amount       = ("amount",        "max"),
        std_amount       = ("amount",        "std"),
        fraud_count      = ("isFraud",       "sum"),
        flagged_count    = ("isFlaggedFraud","sum"),
        transfer_count   = ("type",          lambda x: (x == "TRANSFER").sum()),
        cashout_count    = ("type",          lambda x: (x == "CASH_OUT").sum()),
        distinct_dests   = ("nameDest",      "nunique"),
    ).reset_index().rename(columns={"nameOrig": "account_id"})

    # Fill NaN std (accounts with 1 tx)
    acct["std_amount"] = acct["std_amount"].fillna(0)

    # 2. Account drain events — separate pass (balance goes to 0)
    drain = (
        ps[( ps["newbalanceOrig"] == 0) & (ps["oldbalanceOrg"] > 0)]
        .groupby("nameOrig")
        .size()
        .reset_index(name="drain_events")
        .rename(columns={"nameOrig": "account_id"})
    )
    acct = acct.merge(drain, on="account_id", how="left")
    acct["drain_events"] = acct["drain_events"].fillna(0).astype(int)

    # 3. Global population statistics for z-score
    global_mean = ps["amount"].mean()
    global_std  = ps["amount"].std()
    p95_tx_count = acct["tx_count"].quantile(0.95)
    p95_volume   = acct["total_volume"].quantile(0.95)

    acct["amount_zscore"] = (acct["avg_amount"] - global_mean) / global_std

    # 4. Composite scoring (max 100 pts)
    acct["score_confirmed_fraud"]       = (acct["fraud_count"] > 0).astype(int) * 40
    acct["score_system_flag"]           = (acct["flagged_count"] > 0).astype(int) * 10
    acct["score_drain_events"]          = acct["drain_events"].clip(upper=2) * 15
    acct["score_high_volume"]           = (acct["total_volume"] > p95_volume).astype(int) * 10
    acct["score_high_freq"]             = (acct["tx_count"] > p95_tx_count).astype(int) * 5

    risky_type_ratio = (acct["transfer_count"] + acct["cashout_count"]) / acct["tx_count"].clip(lower=1)
    acct["score_tx_type_concentration"] = np.where(risky_type_ratio > 0.8, 10, np.where(risky_type_ratio > 0.5, 5, 0))

    acct["score_amount_zscore"] = np.where(acct["amount_zscore"] > 3, 10, np.where(acct["amount_zscore"] > 2, 5, 0))

    score_cols = [c for c in acct.columns if c.startswith("score_")]
    acct["composite_risk_score"] = acct[score_cols].sum(axis=1)

    # 5. Risk tier assignment
    acct["risk_tier"] = pd.cut(
        acct["composite_risk_score"],
        bins=[-1, 9, 29, 100],
        labels=["LOW", "MEDIUM", "HIGH"]
    )

    # 6. Summary
    tier_counts = acct["risk_tier"].value_counts()
    print(f"\nPaySim account risk distribution:")
    print(tier_counts.to_string())
    print(f"\nHigh-risk accounts  : {tier_counts.get('HIGH', 0):,}  ({tier_counts.get('HIGH', 0)/len(acct):.2%})")
    print(f"Medium-risk accounts: {tier_counts.get('MEDIUM', 0):,}")
    print(f"Low-risk accounts   : {tier_counts.get('LOW', 0):,}")

    return acct


def score_creditcard(cc: pd.DataFrame) -> pd.DataFrame:
    """Flag and score each credit card transaction."""

    mean_amt = cc["Amount"].mean()
    std_amt  = cc["Amount"].std()

    cc = cc.copy()
    cc["amount_zscore"] = (cc["Amount"] - mean_amt) / std_amt
    cc["spike_flag"]    = cc["amount_zscore"] > 3
    cc["hour"]          = (cc["Time"] // 3600) % 24
    cc["night_window"]  = cc["hour"].between(1, 4)

    cc["risk_score"] = (
        cc["Class"].astype(int) * 40 +
        cc["spike_flag"].astype(int) * 10 +
        cc["night_window"].astype(int) * 5
    )

    cc["risk_tier"] = pd.cut(
        cc["risk_score"],
        bins=[-1, 9, 29, 100],
        labels=["LOW", "MEDIUM", "HIGH"]
    )

    cc["flag_reason"] = "normal"
    cc.loc[cc["spike_flag"],         "flag_reason"] = "amount_spike"
    cc.loc[cc["night_window"],       "flag_reason"] = "night_window"
    cc.loc[cc["Class"] == 1,         "flag_reason"] = "confirmed_fraud"

    tier_counts = cc["risk_tier"].value_counts()
    print(f"\nCredit Card transaction risk distribution:")
    print(tier_counts.to_string())

    return cc


# ── Main ─────────────────────────────────────────────────────

if __name__ == "__main__":

    # PaySim
    if PAYSIM_PATH:
        print("Loading PaySim …")
        ps = pd.read_csv(PAYSIM_PATH)
        ps_risk = score_paysim_accounts(ps)
        out_path = os.path.join(OUT_DIR, "paysim_account_risk.csv")
        ps_risk.to_csv(out_path, index=False)
        print(f"Saved → {out_path}")
    else:
        print("PaySim file not found — skipping.")

    # Credit Card
    print("\nLoading Credit Card …")
    cc = pd.read_csv(CC_PATH)
    cc_risk = score_creditcard(cc)
    out_path = os.path.join(OUT_DIR, "cc_risk_flagged.csv")
    cc_risk.to_csv(out_path, index=False)
    print(f"Saved → {out_path}")

    print("\nDone. Run 03_export_flagged.py next.")

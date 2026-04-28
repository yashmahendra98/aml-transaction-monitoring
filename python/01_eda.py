"""
01_eda.py — Exploratory Data Analysis
AML Transaction Monitoring Project

Datasets:
  - data/raw/creditcard.csv         (Credit Card Fraud Detection — Kaggle)
  - data/raw/PS_20174392719_...csv  (PaySim Synthetic Financial Dataset — Kaggle)
"""

import os
import glob
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
import seaborn as sns

# ── paths ────────────────────────────────────────────────────
RAW_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "raw")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "processed")
FIG_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "figures")

os.makedirs(OUT_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

# Locate PaySim file (long filename varies)
paysim_files = glob.glob(os.path.join(RAW_DIR, "PS_*.csv"))
if not paysim_files:
    raise FileNotFoundError("PaySim CSV not found in data/raw/. Download from Kaggle.")

CC_PATH     = os.path.join(RAW_DIR, "creditcard.csv")
PAYSIM_PATH = paysim_files[0]

STYLE = {"figure.facecolor": "white", "axes.spines.top": False, "axes.spines.right": False}
plt.rcParams.update(STYLE)


# ════════════════════════════════════════════════════════════
# 1. CREDIT CARD DATASET
# ════════════════════════════════════════════════════════════

print("Loading Credit Card dataset …")
cc = pd.read_csv(CC_PATH)

print(f"\n{'='*50}")
print(f"Credit Card — shape : {cc.shape}")
print(f"Null values         : {cc.isnull().sum().sum()}")
print(f"Fraud rate          : {cc['Class'].mean():.4%}")
print(f"Amount stats:\n{cc['Amount'].describe().round(2)}")
print(f"{'='*50}\n")

# Fraud vs Normal amount distribution
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
cc[cc.Class == 0]["Amount"].clip(upper=500).hist(bins=60, ax=axes[0], color="#185FA5", alpha=0.8)
axes[0].set_title("Normal transaction amounts (clipped at $500)")
axes[0].set_xlabel("Amount ($)")

cc[cc.Class == 1]["Amount"].clip(upper=500).hist(bins=40, ax=axes[1], color="#A32D2D", alpha=0.8)
axes[1].set_title("Fraud transaction amounts (clipped at $500)")
axes[1].set_xlabel("Amount ($)")
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "cc_amount_distribution.png"), dpi=150)
plt.close()

# Hourly fraud rate
cc["hour"] = (cc["Time"] // 3600) % 24
hourly = (
    cc.groupby("hour")
    .agg(tx_count=("Amount", "count"), fraud_count=("Class", "sum"), avg_amount=("Amount", "mean"))
    .reset_index()
)
hourly["fraud_rate"] = hourly["fraud_count"] / hourly["tx_count"]

fig, ax = plt.subplots(figsize=(12, 4))
colors = ["#A32D2D" if r > 0.01 else "#BA7517" if r > 0.003 else "#185FA5" for r in hourly["fraud_rate"]]
ax.bar(hourly["hour"], hourly["fraud_rate"] * 100, color=colors, width=0.8)
ax.yaxis.set_major_formatter(mtick.PercentFormatter())
ax.set_xlabel("Hour of day")
ax.set_ylabel("Fraud rate (%)")
ax.set_title("Credit card fraud rate by hour of day")
ax.set_xticks(range(24))
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "cc_hourly_fraud_rate.png"), dpi=150)
plt.close()

print("Credit Card EDA complete. Figures saved.")


# ════════════════════════════════════════════════════════════
# 2. PAYSIM DATASET
# ════════════════════════════════════════════════════════════

print("Loading PaySim dataset (6M+ rows — may take ~30s) …")
ps = pd.read_csv(PAYSIM_PATH)

print(f"\n{'='*50}")
print(f"PaySim — shape      : {ps.shape}")
print(f"Null values         : {ps.isnull().sum().sum()}")
print(f"Fraud rate          : {ps['isFraud'].mean():.4%}")
print(f"Tx types:\n{ps['type'].value_counts()}")
print(f"\nFraud by type:\n{ps.groupby('type')['isFraud'].agg(['sum','mean']).rename(columns={'sum':'count','mean':'rate'}).round(4)}")
print(f"{'='*50}\n")

# Fraud count by transaction type
fraud_by_type = ps.groupby("type")["isFraud"].sum().sort_values(ascending=False)
fig, axes = plt.subplots(1, 2, figsize=(12, 4))
colors_by_type = ["#A32D2D" if v > 0 else "#185FA5" for v in fraud_by_type]
fraud_by_type.plot(kind="bar", ax=axes[0], color=colors_by_type, rot=0)
axes[0].set_title("Fraud count by transaction type")
axes[0].set_ylabel("Confirmed fraud transactions")

fraud_rate_by_type = ps.groupby("type")["isFraud"].mean().sort_values(ascending=False)
fraud_rate_by_type.plot(kind="bar", ax=axes[1], color=colors_by_type, rot=0)
axes[1].set_title("Fraud rate by transaction type")
axes[1].yaxis.set_major_formatter(mtick.PercentFormatter(xmax=1))
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "ps_fraud_by_type.png"), dpi=150)
plt.close()

# System flag vs actual fraud
flagged  = ps["isFlaggedFraud"].sum()
actual   = ps["isFraud"].sum()
caught   = (ps["isFlaggedFraud"] & ps["isFraud"]).sum()
print(f"System flagged      : {flagged:,}")
print(f"Actual fraud        : {actual:,}")
print(f"System caught       : {caught:,}  ({caught/actual:.1%} recall)")

# Amount distribution for fraud vs normal (TRANSFER and CASH_OUT only)
fraud_amounts   = ps[(ps.isFraud == 1)]["amount"].clip(upper=2e6)
normal_amounts  = ps[(ps.isFraud == 0) & ps["type"].isin(["TRANSFER","CASH_OUT"])]["amount"].clip(upper=2e6)

fig, ax = plt.subplots(figsize=(10, 4))
ax.hist(normal_amounts, bins=80, alpha=0.5, color="#185FA5", label="Normal (TRANSFER/CASH_OUT)")
ax.hist(fraud_amounts,  bins=80, alpha=0.7, color="#A32D2D", label="Fraud")
ax.set_xlabel("Amount ($)")
ax.set_title("Amount distribution — fraud vs normal (clipped at $2M)")
ax.legend()
plt.tight_layout()
plt.savefig(os.path.join(FIG_DIR, "ps_amount_distribution.png"), dpi=150)
plt.close()

# Save hourly fraud rates for Power BI
hourly.to_csv(os.path.join(OUT_DIR, "cc_hourly_fraud_rates.csv"), index=False)
print(f"\nSaved: data/processed/cc_hourly_fraud_rates.csv")
print("PaySim EDA complete. Figures saved.\n")
print("Run 02_risk_scoring.py next.")

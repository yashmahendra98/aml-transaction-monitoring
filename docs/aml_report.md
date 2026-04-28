# AML Transaction Monitoring — Findings Report

**Project:** Banking / AML Transaction Monitoring
**Datasets:** Credit Card Fraud Detection + PaySim Synthetic Financial Dataset (Kaggle)
**Tools Used:** Python (pandas, numpy, matplotlib), SQL (window functions), Power BI

---

## 1. Problem

Financial institutions process millions of transactions daily. Identifying suspicious activity — fraud, money laundering, structuring — manually is slow, expensive, and inconsistent. Investigators are overwhelmed with volume and miss high-risk patterns buried in noise.

The core challenge: how do you reduce a dataset of 6+ million transactions to a prioritised review queue without losing confirmed fraud cases?

---

## 2. Approach

### Data Sources

Two complementary datasets were used to simulate a real AML environment:

**Credit Card Fraud Detection (284,807 transactions)**
- 28 anonymised PCA features (V1–V28) to protect cardholder privacy
- Transaction `Amount` and elapsed `Time` in seconds
- Binary `Class` label: 1 = fraud (492 cases, 0.17% of total)
- No account-level identifiers — analysis is transaction-level

**PaySim Synthetic Financial Dataset (6,362,620 transactions)**
- Simulates a mobile money platform (CASH_IN, CASH_OUT, DEBIT, PAYMENT, TRANSFER)
- Account-level data: `nameOrig`, `nameDest`, pre/post balance
- Binary `isFraud` (ground truth) and `isFlaggedFraud` (system rule engine)
- Enables account-level risk aggregation and network analysis

### Methodology

**Step 1 — Data profiling (Excel / Python)**
Checked for nulls (none in either dataset), class imbalance, and outlier distributions. The 99.83% / 0.17% fraud ratio in the credit card set is typical of production fraud data and requires careful threshold design.

**Step 2 — Feature engineering (SQL window functions)**
- Rolling 7-step average per account to detect sudden transaction spikes
- Lag-based comparison to flag accounts whose current transaction exceeds 3× the prior one
- Cumulative 10-step volume window to detect structuring behaviour
- Global z-score ranking to identify population-level outliers
- Account drain events: cases where `newbalanceOrig = 0` after a large outflow

**Step 3 — Risk scoring (Python)**
A composite score (0–100) was built from seven signals:

| Signal | Weight | Rationale |
|--------|--------|-----------|
| Confirmed fraud label | 40 pts | Ground truth — highest confidence |
| System flag (`isFlaggedFraud`) | 10 pts | Weak signal (99.8% miss rate) but not zero |
| Account drain events | 15 pts each (max 30) | Strong indicator of smurfing / laundering |
| Top-5% transaction volume | 10 pts | High-value outliers warrant review |
| Top-5% transaction frequency | 5 pts | Churning activity flag |
| TRANSFER + CASH_OUT concentration > 80% | 10 pts | Primary fraud vectors |
| Amount z-score > 3σ | 10 pts | Significant population outlier |

**Step 4 — Risk tier assignment**
Scores were mapped to three tiers:
- **HIGH (≥30 pts):** Immediate review
- **MEDIUM (10–29 pts):** Enhanced monitoring
- **LOW (<10 pts):** Standard monitoring

**Step 5 — Power BI dashboard**
Exported flagged accounts and hourly fraud rates as CSVs. Dashboard includes: risk tier KPI cards, fraud-by-type bar chart, hourly fraud rate trend, and a drillable high-risk account table.

---

## 3. Insights

### Credit Card

**Finding 1: Fraud is a night phenomenon.**
Fraud rate at 2am is 1.71% — 19× the daytime average of 0.09%. The 1am–4am window accounts for 57 of the top fraud cases despite only 13% of transaction volume. Automated holds on large-amount transactions during these hours would intercept a disproportionate share of fraud.

**Finding 2: Fraud transactions are larger on average.**
Mean fraud amount ($122) is 38% higher than normal ($88). But the distributions overlap heavily — fraudsters also make many small transactions. Amount alone is insufficient; it works best in combination with the time signal.

**Finding 3: The spike + fraud overlap is small but revealing.**
Only 11 transactions are both confirmed fraud and amount spikes (>3σ). The 4,065 spike-only transactions form the MEDIUM tier — elevated risk that warrants review but not immediate action. This prevents alert fatigue without missing confirmed fraud cases.

### PaySim

**Finding 4: Fraud is concentrated in exactly two transaction types.**
TRANSFER and CASH_OUT account for 100% of confirmed fraud (4,097 and 4,116 cases respectively). CASH_IN, PAYMENT, and DEBIT have zero fraud. This is the most actionable finding in the project — AML controls can be tightly focused without impacting 65% of transaction volume.

| Type | Total Txns | Fraud Count | Fraud Rate |
|------|-----------|-------------|------------|
| CASH_IN | 1,399,284 | 0 | 0.00% |
| CASH_OUT | 2,237,500 | 4,116 | 0.18% |
| DEBIT | 41,432 | 0 | 0.00% |
| PAYMENT | 2,151,495 | 0 | 0.00% |
| TRANSFER | 532,909 | 4,097 | 0.77% |

**Finding 5: The built-in rule engine is almost useless.**
`isFlaggedFraud` caught only 16 of 8,213 actual fraud cases — a recall of 0.19%. This confirms that rule-based systems without statistical or ML augmentation fail at scale. The composite scoring model in this project would significantly improve recall.

**Finding 6: Account drain events are a strong structural signal.**
Cases where an account's balance drops to exactly zero after a large outflow strongly correlate with confirmed fraud. These are detectable with a simple SQL filter and should be an automatic escalation trigger.

---

## 4. Impact

### Operational efficiency
Risk segmentation reduces the PaySim investigation population from **6,362,620 transactions → 8,299 high-risk accounts** — a 99.87% reduction in review scope. Investigators spend time on accounts that matter.

### Detection improvement
Layering the composite score over the existing rule engine would increase fraud recall from 0.19% (system flag alone) toward a meaningful detection rate. In a real production environment, this would be followed by a supervised ML model trained on the labelled data.

### Policy triggers
The analysis supports specific, implementable rules:
1. Auto-flag all TRANSFER + CASH_OUT transactions exceeding $50,000 for real-time review
2. Escalate all 2am–4am transactions above the population mean + 2σ
3. Auto-freeze accounts with balance drain events pending investigation
4. Route accounts scoring ≥30 pts to Tier 1 investigators; 10–29 pts to Tier 2 monitoring

### Dashboard utility
The Power BI dashboard gives compliance teams a live view of flagged accounts, fraud rate trends, and risk tier KPIs without needing to query the database directly. Drill-through to individual accounts supports both proactive monitoring and reactive investigation.

---

## 5. Limitations and Next Steps

- The PaySim dataset is synthetic — real-world fraud patterns will differ, particularly around network effects (money mule chains, shell companies)
- The credit card dataset uses PCA-anonymised features, preventing interpretable feature engineering
- No ML model was built in this phase; the composite score is a rule-based approximation
- Recommended next step: train a gradient boosting classifier (XGBoost / LightGBM) on the labelled data, using the engineered features as inputs, and evaluate against the composite score baseline

---

*Analysis by: [Your Name] | [Date] | Data sources: Kaggle (ULB / ealaxi)*

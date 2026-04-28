-- ============================================================
-- 01_aggregations.sql
-- Per-account transaction aggregation
-- Dataset: PaySim Synthetic Financial Dataset
-- ============================================================

-- Step 1: Basic per-account summary statistics
SELECT
    nameOrig                          AS account_id,
    COUNT(*)                          AS tx_count,
    SUM(amount)                       AS total_volume,
    AVG(amount)                       AS avg_amount,
    MAX(amount)                       AS max_amount,
    MIN(amount)                       AS min_amount,
    STDDEV(amount)                    AS std_amount,
    SUM(isFraud)                      AS confirmed_fraud_txns,
    SUM(isFlaggedFraud)               AS system_flagged_txns,
    COUNT(DISTINCT type)              AS distinct_tx_types,
    COUNT(DISTINCT nameDest)          AS distinct_counterparties
FROM transactions
GROUP BY nameOrig
ORDER BY total_volume DESC;


-- Step 2: Transaction frequency by type per account
SELECT
    nameOrig                          AS account_id,
    type                              AS tx_type,
    COUNT(*)                          AS type_count,
    SUM(amount)                       AS type_volume,
    AVG(amount)                       AS type_avg_amount,
    SUM(isFraud)                      AS fraud_count
FROM transactions
GROUP BY nameOrig, type
ORDER BY nameOrig, type_count DESC;


-- Step 3: Balance delta analysis (money leaving vs arriving)
-- Negative balance change is a red flag for laundering patterns
SELECT
    nameOrig                                          AS account_id,
    SUM(newbalanceOrig - oldbalanceOrg)               AS net_balance_change,
    SUM(CASE WHEN (newbalanceOrig - oldbalanceOrg) < 0 THEN 1 ELSE 0 END) AS outflow_txns,
    SUM(CASE WHEN (newbalanceOrig - oldbalanceOrg) > 0 THEN 1 ELSE 0 END) AS inflow_txns,
    SUM(CASE WHEN newbalanceOrig = 0 AND oldbalanceOrg > 0 THEN 1 ELSE 0 END) AS account_drain_events,
    SUM(isFraud)                                       AS fraud_count
FROM transactions
GROUP BY nameOrig
HAVING SUM(CASE WHEN newbalanceOrig = 0 AND oldbalanceOrg > 0 THEN 1 ELSE 0 END) > 0
ORDER BY account_drain_events DESC;


-- Step 4: Destination account risk — accounts receiving many transfers
SELECT
    nameDest                          AS dest_account,
    COUNT(*)                          AS times_received,
    SUM(amount)                       AS total_received,
    AVG(amount)                       AS avg_received,
    COUNT(DISTINCT nameOrig)          AS distinct_senders,
    SUM(isFraud)                      AS linked_fraud_txns
FROM transactions
WHERE type IN ('TRANSFER', 'CASH_OUT')
GROUP BY nameDest
HAVING COUNT(*) > 1
ORDER BY linked_fraud_txns DESC, total_received DESC;


-- Step 5: Credit card — hourly fraud rate
-- (Assumes creditcard table with Time in seconds from first transaction)
SELECT
    (Time / 3600) % 24                AS hour_of_day,
    COUNT(*)                          AS total_txns,
    SUM(Class)                        AS fraud_count,
    ROUND(AVG(Class) * 100, 4)        AS fraud_rate_pct,
    AVG(Amount)                       AS avg_amount,
    AVG(CASE WHEN Class = 1 THEN Amount END) AS avg_fraud_amount
FROM creditcard
GROUP BY (Time / 3600) % 24
ORDER BY hour_of_day;

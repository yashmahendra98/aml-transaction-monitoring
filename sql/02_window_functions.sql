-- ============================================================
-- 02_window_functions.sql
-- Rolling averages, lag comparison, and spike detection
-- Dataset: PaySim + Credit Card
-- ============================================================

-- Step 1: Rolling 7-step average per account (PaySim uses "step" as time unit)
-- Flags transactions where the current amount is > 2x the rolling average
WITH rolling_avg AS (
    SELECT
        nameOrig,
        step,
        amount,
        type,
        isFraud,
        AVG(amount) OVER (
            PARTITION BY nameOrig
            ORDER BY step
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                           AS rolling_7step_avg,
        COUNT(*) OVER (
            PARTITION BY nameOrig
            ORDER BY step
            ROWS BETWEEN 6 PRECEDING AND CURRENT ROW
        )                           AS window_tx_count
    FROM transactions
)
SELECT
    nameOrig,
    step,
    amount,
    type,
    isFraud,
    ROUND(rolling_7step_avg, 2)    AS rolling_7step_avg,
    ROUND(amount / NULLIF(rolling_7step_avg, 0), 2) AS amount_vs_rolling_ratio,
    CASE
        WHEN amount > rolling_7step_avg * 2  THEN 'SPIKE_HIGH'
        WHEN amount < rolling_7step_avg * 0.2 THEN 'SPIKE_LOW'
        ELSE 'NORMAL'
    END                             AS spike_flag
FROM rolling_avg
WHERE window_tx_count >= 3   -- only flag after enough history
ORDER BY amount_vs_rolling_ratio DESC;


-- Step 2: Lag-based sudden spike detection
-- Compares each transaction to the prior transaction for the same account
WITH lagged AS (
    SELECT
        nameOrig,
        step,
        amount,
        type,
        isFraud,
        LAG(amount) OVER (
            PARTITION BY nameOrig ORDER BY step
        )                           AS prev_amount,
        LAG(type) OVER (
            PARTITION BY nameOrig ORDER BY step
        )                           AS prev_type
    FROM transactions
)
SELECT
    nameOrig,
    step,
    amount,
    type,
    isFraud,
    ROUND(prev_amount, 2)           AS prev_amount,
    ROUND(
        (amount - prev_amount) / NULLIF(prev_amount, 0) * 100
    , 2)                            AS pct_change_from_prev,
    CASE
        WHEN prev_amount IS NULL THEN 'FIRST_TX'
        WHEN amount > prev_amount * 3 THEN 'SUDDEN_SPIKE'
        WHEN amount < prev_amount * 0.1 AND prev_amount > 10000 THEN 'SUDDEN_DROP'
        ELSE 'NORMAL'
    END                             AS behavior_flag
FROM lagged
ORDER BY ABS((amount - prev_amount) / NULLIF(prev_amount, 0)) DESC;


-- Step 3: Cumulative volume threshold — structuring detection
-- "Structuring" = breaking large amounts into many smaller transactions to avoid reporting thresholds
WITH cumulative AS (
    SELECT
        nameOrig,
        step,
        amount,
        type,
        isFraud,
        SUM(amount) OVER (
            PARTITION BY nameOrig
            ORDER BY step
            ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
        )                           AS rolling_10step_volume,
        COUNT(*) OVER (
            PARTITION BY nameOrig
            ORDER BY step
            ROWS BETWEEN 9 PRECEDING AND CURRENT ROW
        )                           AS rolling_10step_count
    FROM transactions
    WHERE type IN ('TRANSFER', 'CASH_OUT')
)
SELECT
    nameOrig,
    step,
    amount,
    ROUND(rolling_10step_volume, 2)  AS rolling_10step_volume,
    rolling_10step_count,
    CASE
        WHEN rolling_10step_volume > 500000
         AND rolling_10step_count >= 5
         AND amount < 50000         THEN 'STRUCTURING_RISK'
        WHEN rolling_10step_volume > 1000000 THEN 'HIGH_VOLUME_ALERT'
        ELSE 'NORMAL'
    END                              AS structuring_flag,
    isFraud
FROM cumulative
ORDER BY rolling_10step_volume DESC;


-- Step 4: Global z-score ranking — who deviates most from population mean?
WITH stats AS (
    SELECT
        AVG(amount)    AS global_mean,
        STDDEV(amount) AS global_std
    FROM transactions
),
account_summary AS (
    SELECT
        nameOrig,
        AVG(amount)  AS acct_avg_amount,
        SUM(amount)  AS acct_total_volume,
        COUNT(*)     AS acct_tx_count,
        SUM(isFraud) AS fraud_count
    FROM transactions
    GROUP BY nameOrig
)
SELECT
    a.nameOrig,
    ROUND(a.acct_avg_amount, 2)                                     AS avg_amount,
    ROUND(a.acct_total_volume, 2)                                   AS total_volume,
    a.acct_tx_count,
    a.fraud_count,
    ROUND((a.acct_avg_amount - s.global_mean) / NULLIF(s.global_std, 0), 4) AS amount_zscore,
    NTILE(100) OVER (ORDER BY a.acct_avg_amount)                    AS amount_percentile,
    NTILE(100) OVER (ORDER BY a.acct_tx_count)                      AS frequency_percentile
FROM account_summary a
CROSS JOIN stats s
ORDER BY amount_zscore DESC;


-- Step 5: Credit card — z-score flag on amount
WITH cc_stats AS (
    SELECT
        AVG(Amount)    AS mean_amount,
        STDDEV(Amount) AS std_amount
    FROM creditcard
)
SELECT
    Time,
    Amount,
    Class                           AS is_fraud,
    ROUND((Amount - s.mean_amount) / NULLIF(s.std_amount, 0), 4) AS amount_zscore,
    CASE
        WHEN (Amount - s.mean_amount) / NULLIF(s.std_amount, 0) > 3 THEN 'HIGH_SPIKE'
        WHEN (Amount - s.mean_amount) / NULLIF(s.std_amount, 0) > 2 THEN 'MEDIUM_SPIKE'
        ELSE 'NORMAL'
    END                             AS spike_flag
FROM creditcard c
CROSS JOIN cc_stats s
ORDER BY amount_zscore DESC;

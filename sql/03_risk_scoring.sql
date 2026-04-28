-- ============================================================
-- 03_risk_scoring.sql
-- Composite risk scoring and tier assignment
-- Dataset: PaySim + Credit Card
-- ============================================================

-- Step 1: Build composite risk score per account (PaySim)
-- Score = weighted sum of risk signals
WITH account_metrics AS (
    SELECT
        nameOrig                                            AS account_id,
        COUNT(*)                                            AS tx_count,
        AVG(amount)                                         AS avg_amount,
        MAX(amount)                                         AS max_amount,
        SUM(amount)                                         AS total_volume,
        STDDEV(amount)                                      AS std_amount,
        SUM(isFraud)                                        AS fraud_count,
        SUM(isFlaggedFraud)                                 AS flagged_count,
        COUNT(DISTINCT type)                                AS distinct_types,
        COUNT(DISTINCT nameDest)                            AS distinct_counterparties,
        SUM(CASE WHEN type = 'TRANSFER' THEN 1 ELSE 0 END) AS transfer_count,
        SUM(CASE WHEN type = 'CASH_OUT' THEN 1 ELSE 0 END) AS cashout_count,
        SUM(CASE WHEN newbalanceOrig = 0 AND oldbalanceOrg > 0 THEN 1 ELSE 0 END) AS drain_events
    FROM transactions
    GROUP BY nameOrig
),
global_stats AS (
    SELECT
        AVG(avg_amount)    AS pop_avg_amount,
        STDDEV(avg_amount) AS pop_std_amount,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY tx_count) AS p95_tx_count,
        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY total_volume) AS p95_volume
    FROM account_metrics
),
scored AS (
    SELECT
        a.*,
        -- Confirmed fraud: highest weight
        (a.fraud_count > 0)::INT * 40                           AS score_confirmed_fraud,
        -- System flag (weak signal — misses 99.8%, but still adds weight)
        (a.flagged_count > 0)::INT * 10                         AS score_system_flag,
        -- Account drain events (zero balance after large outflow)
        LEAST(a.drain_events * 15, 30)                          AS score_drain_events,
        -- High volume outlier (top 5%)
        (a.total_volume > g.p95_volume)::INT * 10               AS score_high_volume,
        -- High frequency outlier (top 5%)
        (a.tx_count > g.p95_tx_count)::INT * 5                  AS score_high_freq,
        -- TRANSFER + CASH_OUT concentration (primary fraud vectors)
        CASE
            WHEN (a.transfer_count + a.cashout_count)::FLOAT / NULLIF(a.tx_count, 0) > 0.8 THEN 10
            WHEN (a.transfer_count + a.cashout_count)::FLOAT / NULLIF(a.tx_count, 0) > 0.5 THEN 5
            ELSE 0
        END                                                     AS score_tx_type_concentration,
        -- Amount z-score outlier
        CASE
            WHEN (a.avg_amount - g.pop_avg_amount) / NULLIF(g.pop_std_amount, 0) > 3 THEN 10
            WHEN (a.avg_amount - g.pop_avg_amount) / NULLIF(g.pop_std_amount, 0) > 2 THEN 5
            ELSE 0
        END                                                     AS score_amount_zscore
    FROM account_metrics a
    CROSS JOIN global_stats g
)
SELECT
    account_id,
    tx_count,
    ROUND(avg_amount, 2)        AS avg_amount,
    ROUND(total_volume, 2)      AS total_volume,
    fraud_count,
    flagged_count,
    drain_events,
    (
        score_confirmed_fraud +
        score_system_flag +
        score_drain_events +
        score_high_volume +
        score_high_freq +
        score_tx_type_concentration +
        score_amount_zscore
    )                           AS composite_risk_score,
    CASE
        WHEN (score_confirmed_fraud + score_system_flag + score_drain_events +
              score_high_volume + score_high_freq + score_tx_type_concentration +
              score_amount_zscore) >= 30 THEN 'HIGH'
        WHEN (score_confirmed_fraud + score_system_flag + score_drain_events +
              score_high_volume + score_high_freq + score_tx_type_concentration +
              score_amount_zscore) >= 10 THEN 'MEDIUM'
        ELSE 'LOW'
    END                         AS risk_tier
FROM scored
ORDER BY composite_risk_score DESC;


-- Step 2: Credit card risk segmentation
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
        WHEN Class = 1 THEN 'HIGH'
        WHEN (Amount - s.mean_amount) / NULLIF(s.std_amount, 0) > 3 THEN 'MEDIUM'
        ELSE 'LOW'
    END                             AS risk_tier,
    CASE
        WHEN Class = 1 THEN 'confirmed_fraud'
        WHEN (Amount - s.mean_amount) / NULLIF(s.std_amount, 0) > 3 THEN 'amount_spike'
        ELSE 'normal'
    END                             AS flag_reason
FROM creditcard c
CROSS JOIN cc_stats s
ORDER BY amount_zscore DESC;


-- Step 3: Risk tier summary — for Power BI KPI cards
SELECT
    risk_tier,
    COUNT(*)                        AS account_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
    SUM(fraud_count)                AS total_fraud_txns,
    ROUND(AVG(total_volume), 0)     AS avg_volume_per_account
FROM (
    -- paste or reference the scoring CTE from Step 1 above
    SELECT account_id, risk_tier, fraud_count, total_volume
    FROM risk_scored_accounts   -- replace with your CTE/view name
) scored
GROUP BY risk_tier
ORDER BY CASE risk_tier WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END;

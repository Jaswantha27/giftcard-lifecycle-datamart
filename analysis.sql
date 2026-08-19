-- analysis.sql
-- Summary queries against fact_giftcard_cohort_monthly (populated by
-- build_mart.sql / run_mart_build.py). Demonstrates the kind of reporting a
-- leadership dashboard (or a Power BI model built on this mart) would surface.

-- 1. Overall lifecycle summary: total issued, redeemed, breakage, breakage rate
SELECT
    SUM(cohort_issued_amount) FILTER (WHERE months_since_issuance = 0) AS total_issued,
    SUM(breakage_amount) AS total_breakage,
    ROUND(
        100.0 * SUM(breakage_amount)
            / NULLIF(SUM(cohort_issued_amount) FILTER (WHERE months_since_issuance = 0), 0),
        2
    ) AS breakage_rate_pct
FROM fact_giftcard_cohort_monthly;

-- 2. Redemption curve: average % of cohort value redeemed by months since issuance
--    (the "cohort triangle" row you'd chart as a line per cohort, or averaged here)
SELECT
    months_since_issuance,
    ROUND(AVG(100.0 * cumulative_redeemed_amount / cohort_issued_amount), 2) AS avg_pct_redeemed
FROM fact_giftcard_cohort_monthly
GROUP BY months_since_issuance
ORDER BY months_since_issuance;

-- 3. Breakage by issuance cohort (only cohorts old enough to have expired by
--    the data horizon will show a non-zero value)
SELECT
    cohort_month,
    SUM(cohort_issued_amount) / COUNT(DISTINCT months_since_issuance) AS cohort_issued_amount, -- constant per cohort
    SUM(breakage_amount) AS breakage_amount
FROM fact_giftcard_cohort_monthly
GROUP BY cohort_month
ORDER BY cohort_month;

-- 4. Cohorts with the slowest redemption pace (lowest % redeemed by month 6)
--    - useful for flagging cohorts likely to generate more breakage
SELECT
    cohort_month,
    ROUND(100.0 * cumulative_redeemed_amount / cohort_issued_amount, 2) AS pct_redeemed_by_month_6
FROM fact_giftcard_cohort_monthly
WHERE months_since_issuance = 6
ORDER BY pct_redeemed_by_month_6 ASC
LIMIT 10;

-- 5. Month-over-month redemption velocity (new $ redeemed per activity month,
--    across all cohorts combined) - the "how much are we redeeming this month" view
SELECT
    activity_month,
    SUM(redeemed_amount_this_month) AS redeemed_this_month
FROM fact_giftcard_cohort_monthly
GROUP BY activity_month
ORDER BY activity_month;

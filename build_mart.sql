-- build_mart.sql
-- Builds the monthly-grain gift card cohort data mart
-- (fact_giftcard_cohort_monthly) from the raw issuance/redemption tables.
--
-- Grain: one row per (cohort_month, activity_month) - i.e. for every
-- issuance cohort, one row per calendar month of that cohort's lifecycle,
-- from issuance month through the 24-month expiration window (or the data
-- horizon, whichever comes first).
--
-- Key design decisions, each driven by a specific data-quality edge case
-- in the raw data:
--   - VOIDED cards are excluded entirely (they were never real liability).
--   - Redemption amounts can be negative (refunds/reversals) - cumulative
--     redemption is floored at 0 so a refund can never make redeemed < 0.
--   - Cumulative redemption is capped at issued_amount so an upstream
--     overdraft error (redeeming more than the card's balance) can never
--     produce a negative remaining_balance in the mart.
--   - Breakage is only recognized in the card's expiration month
--     (months_since_issuance = 23), not accumulated early - a dormant
--     card isn't "breakage" until it actually expires.
--
-- Run against the tables created by schema.sql / load_data.py.

TRUNCATE TABLE fact_giftcard_cohort_monthly;

WITH active_cards AS (
    SELECT
        card_id, customer_id, issuance_date, issued_amount, currency,
        DATE_TRUNC('month', issuance_date)::date AS cohort_month
    FROM giftcard_issuance
    WHERE status = 'ACTIVE'
),
horizon AS (
    SELECT MAX(activity_month) AS max_month FROM (
        SELECT DATE_TRUNC('month', redemption_date)::date AS activity_month FROM giftcard_redemption
        UNION ALL
        SELECT DATE_TRUNC('month', issuance_date)::date FROM giftcard_issuance
    ) all_months
),
card_month_spine AS (
    -- One row per card per month, from issuance month through 23 months later
    -- (24-month expiration window), capped at the data horizon.
    SELECT
        ac.card_id, ac.cohort_month, ac.issued_amount,
        (ac.cohort_month + (gs.month_offset || ' months')::interval)::date AS activity_month,
        gs.month_offset AS months_since_issuance
    FROM active_cards ac
    CROSS JOIN generate_series(0, 23) AS gs(month_offset)
    CROSS JOIN horizon h
    WHERE (ac.cohort_month + (gs.month_offset || ' months')::interval)::date <= h.max_month
),
card_month_redemption AS (
    SELECT
        ac.card_id,
        DATE_TRUNC('month', r.redemption_date)::date AS activity_month,
        SUM(r.redemption_amount) AS month_redeemed
    FROM active_cards ac
    JOIN giftcard_redemption r ON r.card_id = ac.card_id
    GROUP BY ac.card_id, DATE_TRUNC('month', r.redemption_date)
),
card_month_joined AS (
    SELECT
        s.card_id, s.cohort_month, s.issued_amount, s.activity_month, s.months_since_issuance,
        COALESCE(cmr.month_redeemed, 0) AS month_redeemed
    FROM card_month_spine s
    LEFT JOIN card_month_redemption cmr
        ON cmr.card_id = s.card_id AND cmr.activity_month = s.activity_month
),
card_month_capped AS (
    SELECT
        card_id, cohort_month, issued_amount, activity_month, months_since_issuance, month_redeemed,
        -- Floor at 0 (refunds can't push redemption negative) and cap at
        -- issued_amount (an overdraft-error redemption can't exceed the card's value).
        LEAST(
            GREATEST(
                SUM(month_redeemed) OVER (PARTITION BY card_id ORDER BY activity_month),
                0
            ),
            issued_amount
        ) AS cumulative_redeemed
    FROM card_month_joined
),
card_month_final AS (
    SELECT
        *,
        (months_since_issuance = 23) AS is_expiration_month
    FROM card_month_capped
)
INSERT INTO fact_giftcard_cohort_monthly (
    cohort_month, activity_month, months_since_issuance, cards_issued_in_cohort,
    cohort_issued_amount, redeemed_amount_this_month, cumulative_redeemed_amount,
    remaining_balance, is_expired, breakage_amount
)
SELECT
    cohort_month,
    activity_month,
    months_since_issuance,
    COUNT(DISTINCT card_id) AS cards_issued_in_cohort,
    SUM(issued_amount) AS cohort_issued_amount,
    SUM(month_redeemed) AS redeemed_amount_this_month,
    SUM(cumulative_redeemed) AS cumulative_redeemed_amount,
    SUM(issued_amount - cumulative_redeemed) AS remaining_balance,
    BOOL_OR(is_expiration_month) AS is_expired,
    SUM(CASE WHEN is_expiration_month THEN issued_amount - cumulative_redeemed ELSE 0 END) AS breakage_amount
FROM card_month_final
GROUP BY cohort_month, activity_month, months_since_issuance;

-- Quick sanity check: total breakage recognized vs. total issued
-- SELECT SUM(breakage_amount) AS total_breakage FROM fact_giftcard_cohort_monthly;

-- schema.sql
-- Raw layer + monthly-grain data mart for the Gift Card Lifecycle project.
-- Target: PostgreSQL 14+ (syntax is Redshift/Postgres compatible).

DROP TABLE IF EXISTS fact_giftcard_cohort_monthly;
DROP TABLE IF EXISTS giftcard_redemption;
DROP TABLE IF EXISTS giftcard_issuance;

-- ============================================================
-- Raw layer
-- ============================================================

CREATE TABLE giftcard_issuance (
    card_id           VARCHAR(20)   PRIMARY KEY,
    customer_id        VARCHAR(20)   NOT NULL,
    issuance_date        DATE          NOT NULL,
    issued_amount           NUMERIC(10,2) NOT NULL,
    currency                 VARCHAR(3)    NOT NULL DEFAULT 'USD',
    status                     VARCHAR(10)   NOT NULL DEFAULT 'ACTIVE'  -- ACTIVE | VOIDED
);

CREATE INDEX idx_issuance_customer ON giftcard_issuance (customer_id);
CREATE INDEX idx_issuance_date ON giftcard_issuance (issuance_date);

CREATE TABLE giftcard_redemption (
    redemption_id       VARCHAR(30)   PRIMARY KEY,
    card_id               VARCHAR(20)   NOT NULL REFERENCES giftcard_issuance(card_id),
    redemption_date         DATE          NOT NULL,
    redemption_amount         NUMERIC(10,2) NOT NULL  -- can be negative (refund/reversal)
);

CREATE INDEX idx_redemption_card ON giftcard_redemption (card_id);
CREATE INDEX idx_redemption_date ON giftcard_redemption (redemption_date);

-- ============================================================
-- Data mart: monthly-grain cohort fact table
-- Grain: one row per (issuance_cohort_month, activity_month)
-- Populated by build_mart.sql
-- ============================================================

CREATE TABLE fact_giftcard_cohort_monthly (
    cohort_month              DATE          NOT NULL,   -- month the cards in this cohort were issued
    activity_month              DATE          NOT NULL,   -- calendar month this row reports on
    months_since_issuance          SMALLINT      NOT NULL,   -- 0 = issuance month, 1 = next month, etc.
    cards_issued_in_cohort            INTEGER       NOT NULL,   -- cohort size (constant across activity_month for a cohort)
    cohort_issued_amount                NUMERIC(14,2) NOT NULL,   -- total $ issued in this cohort (constant across activity_month)
    redeemed_amount_this_month            NUMERIC(14,2) NOT NULL DEFAULT 0,
    cumulative_redeemed_amount              NUMERIC(14,2) NOT NULL DEFAULT 0,
    remaining_balance                         NUMERIC(14,2) NOT NULL,
    is_expired                                  BOOLEAN       NOT NULL DEFAULT FALSE,
    breakage_amount                               NUMERIC(14,2) NOT NULL DEFAULT 0,
    PRIMARY KEY (cohort_month, activity_month)
);

CREATE INDEX idx_mart_cohort_month ON fact_giftcard_cohort_monthly (cohort_month);
CREATE INDEX idx_mart_months_since ON fact_giftcard_cohort_monthly (months_since_issuance);

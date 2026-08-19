"""
local_test.py
--------------
No-Docker way to verify the pipeline end to end. Uses DuckDB (pip-installable,
no server/daemon required) to run the SAME mart-build logic as
build_mart.sql, entirely against the local CSVs.

This does not replace the Postgres path documented in the README - that's
still the "real" deployment target this project is designed for. This
script exists so you can sanity-check the mart's output on a machine
without Docker installed.

Usage:
    pip install duckdb
    python3 local_test.py
"""

import os

import duckdb

ISSUANCE_FILE = "data/giftcard_issuance.csv"
REDEMPTION_FILE = "data/giftcard_redemption.csv"
OUTPUT_CSV = "output/fact_giftcard_cohort_monthly.csv"

con = duckdb.connect(database=":memory:")

con.execute(f"""
    CREATE TABLE giftcard_issuance AS
    SELECT card_id, customer_id, CAST(issuance_date AS DATE) AS issuance_date,
           CAST(issued_amount AS DOUBLE) AS issued_amount, currency, status
    FROM read_csv_auto('{ISSUANCE_FILE}', header=True)
""")
con.execute(f"""
    CREATE TABLE giftcard_redemption AS
    SELECT redemption_id, card_id, CAST(redemption_date AS DATE) AS redemption_date,
           CAST(redemption_amount AS DOUBLE) AS redemption_amount
    FROM read_csv_auto('{REDEMPTION_FILE}', header=True)
""")

# Same mart-build logic as build_mart.sql, translated to DuckDB SQL.
con.execute("""
    CREATE VIEW active_cards AS
    SELECT card_id, customer_id, issuance_date, issued_amount, currency,
           DATE_TRUNC('month', issuance_date) AS cohort_month
    FROM giftcard_issuance
    WHERE status = 'ACTIVE'
""")

con.execute("""
    CREATE VIEW horizon AS
    SELECT MAX(activity_month) AS max_month FROM (
        SELECT DATE_TRUNC('month', redemption_date) AS activity_month FROM giftcard_redemption
        UNION ALL
        SELECT DATE_TRUNC('month', issuance_date) FROM giftcard_issuance
    )
""")

con.execute("""
    CREATE VIEW card_month_spine AS
    SELECT
        ac.card_id, ac.cohort_month, ac.issued_amount,
        ac.cohort_month + INTERVAL (gs.month_offset) MONTH AS activity_month,
        gs.month_offset AS months_since_issuance
    FROM active_cards ac
    CROSS JOIN (SELECT UNNEST(GENERATE_SERIES(0, 23)) AS month_offset) gs
    CROSS JOIN horizon h
    WHERE ac.cohort_month + INTERVAL (gs.month_offset) MONTH <= h.max_month
""")

con.execute("""
    CREATE VIEW card_month_redemption AS
    SELECT ac.card_id, DATE_TRUNC('month', r.redemption_date) AS activity_month,
           SUM(r.redemption_amount) AS month_redeemed
    FROM active_cards ac
    JOIN giftcard_redemption r ON r.card_id = ac.card_id
    GROUP BY ac.card_id, DATE_TRUNC('month', r.redemption_date)
""")

con.execute("""
    CREATE VIEW card_month_joined AS
    SELECT s.card_id, s.cohort_month, s.issued_amount, s.activity_month, s.months_since_issuance,
           COALESCE(cmr.month_redeemed, 0) AS month_redeemed
    FROM card_month_spine s
    LEFT JOIN card_month_redemption cmr
        ON cmr.card_id = s.card_id AND cmr.activity_month = s.activity_month
""")

con.execute("""
    CREATE VIEW card_month_capped AS
    SELECT card_id, cohort_month, issued_amount, activity_month, months_since_issuance, month_redeemed,
        LEAST(
            GREATEST(SUM(month_redeemed) OVER (PARTITION BY card_id ORDER BY activity_month), 0),
            issued_amount
        ) AS cumulative_redeemed
    FROM card_month_joined
""")

con.execute("""
    CREATE VIEW card_month_final AS
    SELECT *, (months_since_issuance = 23) AS is_expiration_month
    FROM card_month_capped
""")

con.execute("""
    CREATE TABLE fact_giftcard_cohort_monthly AS
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
    GROUP BY cohort_month, activity_month, months_since_issuance
    ORDER BY cohort_month, activity_month
""")

os.makedirs("output", exist_ok=True)
con.execute(f"COPY fact_giftcard_cohort_monthly TO '{OUTPUT_CSV}' (HEADER, DELIMITER ',')")

row_count = con.execute("SELECT COUNT(*) FROM fact_giftcard_cohort_monthly").fetchone()[0]
total_issued = con.execute(
    "SELECT SUM(cohort_issued_amount) FROM fact_giftcard_cohort_monthly WHERE months_since_issuance = 0"
).fetchone()[0]
total_breakage = con.execute("SELECT SUM(breakage_amount) FROM fact_giftcard_cohort_monthly").fetchone()[0]

print(f"Mart built: {row_count} cohort-month rows -> {OUTPUT_CSV}")
print(f"Total issued (month 0 rows): {total_issued:.2f}")
print(f"Total breakage recognized: {total_breakage:.2f}")

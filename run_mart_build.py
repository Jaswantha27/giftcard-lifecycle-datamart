"""
run_mart_build.py
------------------
Runs build_mart.sql against Postgres to populate the
fact_giftcard_cohort_monthly data mart, then exports it to CSV
(the same file a Power BI import would read from).

Usage:
    docker compose up -d
    python3 load_data.py
    python3 run_mart_build.py
"""

import csv
import os

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5434"),
    "dbname": os.environ.get("DB_NAME", "giftcard_lifecycle"),
    "user": os.environ.get("DB_USER", "giftcard_user"),
    "password": os.environ.get("DB_PASSWORD", "giftcard_pass"),
}

BUILD_SQL_FILE = "build_mart.sql"
OUTPUT_CSV = "output/fact_giftcard_cohort_monthly.csv"

FIELDNAMES = [
    "cohort_month", "activity_month", "months_since_issuance", "cards_issued_in_cohort",
    "cohort_issued_amount", "redeemed_amount_this_month", "cumulative_redeemed_amount",
    "remaining_balance", "is_expired", "breakage_amount",
]


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


def run_build(conn):
    with open(BUILD_SQL_FILE) as f:
        sql = f.read()
    with conn.cursor() as cur:
        cur.execute(sql)
    conn.commit()


def export_mart(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"""
            SELECT {", ".join(FIELDNAMES)}
            FROM fact_giftcard_cohort_monthly
            ORDER BY cohort_month, activity_month
        """)
        rows = cur.fetchall()

    os.makedirs("output", exist_ok=True)
    with open(OUTPUT_CSV, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        for r in rows:
            writer.writerow(dict(r))

    return rows


def main():
    conn = get_connection()
    try:
        run_build(conn)
        rows = export_mart(conn)
        total_breakage = sum(float(r["breakage_amount"]) for r in rows)
        total_issued = sum(float(r["cohort_issued_amount"]) for r in rows if r["months_since_issuance"] == 0)
        print(f"Mart built: {len(rows)} cohort-month rows -> {OUTPUT_CSV}")
        print(f"Total issued (month 0 rows): {total_issued:.2f}")
        print(f"Total breakage recognized: {total_breakage:.2f}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()

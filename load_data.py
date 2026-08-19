"""
load_data.py
------------
Creates the schema (schema.sql) and loads data/giftcard_issuance.csv and
data/giftcard_redemption.csv into the Postgres container defined in
docker-compose.yml.

Usage:
    Start the Postgres container (see README), then:
    pip install -r requirements.txt
    python3 load_data.py
"""

import csv
import os
import sys

import psycopg2

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "localhost"),
    "port": os.environ.get("DB_PORT", "5434"),
    "dbname": os.environ.get("DB_NAME", "giftcard_lifecycle"),
    "user": os.environ.get("DB_USER", "giftcard_user"),
    "password": os.environ.get("DB_PASSWORD", "giftcard_pass"),
}

SCHEMA_FILE = "schema.sql"
ISSUANCE_FILE = "data/giftcard_issuance.csv"
REDEMPTION_FILE = "data/giftcard_redemption.csv"


def get_connection():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except psycopg2.OperationalError as e:
        print(f"Could not connect to Postgres: {e}")
        print("Make sure the container is running (see README for the docker command).")
        sys.exit(1)


def apply_schema(conn):
    with open(SCHEMA_FILE) as f:
        schema_sql = f.read()
    with conn.cursor() as cur:
        cur.execute(schema_sql)
    conn.commit()
    print("Schema applied.")


def load_issuance(conn):
    with open(ISSUANCE_FILE, newline="") as f:
        rows = list(csv.DictReader(f))

    insert_sql = """
        INSERT INTO giftcard_issuance
            (card_id, customer_id, issuance_date, issued_amount, currency, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """
    values = [
        (r["card_id"], r["customer_id"], r["issuance_date"], r["issued_amount"], r["currency"], r["status"])
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(insert_sql, values)
    conn.commit()
    print(f"Loaded {len(values)} rows into giftcard_issuance.")


def load_redemption(conn):
    with open(REDEMPTION_FILE, newline="") as f:
        rows = list(csv.DictReader(f))

    insert_sql = """
        INSERT INTO giftcard_redemption
            (redemption_id, card_id, redemption_date, redemption_amount)
        VALUES (%s, %s, %s, %s)
    """
    values = [
        (r["redemption_id"], r["card_id"], r["redemption_date"], r["redemption_amount"])
        for r in rows
    ]
    with conn.cursor() as cur:
        cur.executemany(insert_sql, values)
    conn.commit()
    print(f"Loaded {len(values)} rows into giftcard_redemption.")


def main():
    conn = get_connection()
    try:
        apply_schema(conn)
        load_issuance(conn)
        load_redemption(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()

"""Load data/sales.csv and data/weather.csv into Postgres.

Creates the tables from schema.sql, then replaces their contents (TRUNCATE + COPY) in one
transaction, so running it again never duplicates rows. Run mock_data.py first.

Needs DATABASE_ADMIN_URL (Railway's public URL, with write access) in .env.

Usage: python load_data.py
"""

import os
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

SCHEMA = Path(__file__).with_name("schema.sql")
SALES_CSV = Path("data/sales.csv")
WEATHER_CSV = Path("data/weather.csv")
SALES_COLUMNS = "sold_at, ticket_number, article, category, quantity, unit_price"
WEATHER_COLUMNS = "date, cloud_cover, temperature_c, wind_speed, weather_code"


def copy_csv(cur, table, columns, path):
    with open(path, encoding="utf-8") as f:
        cur.copy_expert(f"COPY {table} ({columns}) FROM STDIN WITH (FORMAT csv, HEADER true)", f)


def load(conn, sales_csv=SALES_CSV, weather_csv=WEATHER_CSV):
    """Create tables and replace their rows. Returns {table: row count}."""
    with conn, conn.cursor() as cur:
        cur.execute(SCHEMA.read_text(encoding="utf-8"))
        cur.execute("TRUNCATE sales, weather RESTART IDENTITY")
        copy_csv(cur, "sales", SALES_COLUMNS, sales_csv)
        copy_csv(cur, "weather", WEATHER_COLUMNS, weather_csv)
        counts = {}
        for table in ("sales", "weather"):
            cur.execute(f"SELECT count(*) FROM {table}")
            counts[table] = cur.fetchone()[0]
    return counts


def main():
    load_dotenv(".env")
    url = os.environ.get("DATABASE_ADMIN_URL")
    if not url:
        raise SystemExit("DATABASE_ADMIN_URL is not set (see .env.example)")
    for path in (SALES_CSV, WEATHER_CSV):
        if not path.exists():
            raise SystemExit(f"{path} not found; run python mock_data.py first")
    conn = psycopg2.connect(url, connect_timeout=15)
    try:
        counts = load(conn)
    finally:
        conn.close()
    print(", ".join(f"{table}: {n:,} rows" for table, n in counts.items()))


if __name__ == "__main__":
    main()

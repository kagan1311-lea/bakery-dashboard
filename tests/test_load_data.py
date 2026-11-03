"""Issue #1: load_data.py fills the tables and never duplicates rows.

Runs against TEST_DATABASE_URL inside a throwaway schema, so it never touches real tables.
"""

import os
import uuid

import psycopg2
import pytest
from dotenv import load_dotenv

import load_data

load_dotenv(".env")
URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")

SALES = """sold_at,ticket_number,article,category,quantity,unit_price
2026-07-24 07:10:00,100001,חלה,לחמים,2,18.00
2026-07-24 07:10:00,100001,רוגלך (100 גרם),עוגות,1,14.00
2026-07-24 08:30:00,100002,קרואסון חמאה,קרואסונים,-1,12.00
"""
WEATHER = """date,cloud_cover,temperature_c,wind_speed,weather_code
2026-07-24,3,18.5,14,61
2026-07-25,4,19.75,7,
"""


@pytest.fixture
def conn():
    schema = f"test_{uuid.uuid4().hex[:8]}"
    admin = psycopg2.connect(URL, connect_timeout=15)
    admin.autocommit = True
    admin.cursor().execute(f"CREATE SCHEMA {schema}")
    c = psycopg2.connect(URL, connect_timeout=15, options=f"-c search_path={schema}")
    yield c
    c.close()
    admin.cursor().execute(f"DROP SCHEMA {schema} CASCADE")
    admin.close()


@pytest.fixture
def csvs(tmp_path):
    sales, weather = tmp_path / "sales.csv", tmp_path / "weather.csv"
    sales.write_text(SALES, encoding="utf-8")
    weather.write_text(WEATHER, encoding="utf-8")
    return sales, weather


def test_load_fills_both_tables(conn, csvs):
    assert load_data.load(conn, *csvs) == {"sales": 3, "weather": 2}
    with conn.cursor() as cur:
        cur.execute("SELECT article, quantity, unit_price FROM sales ORDER BY id")
        rows = cur.fetchall()
        cur.execute("SELECT weather_code FROM weather WHERE date = '2026-07-25'")
        assert cur.fetchone()[0] is None
    assert rows[0][0] == "חלה" and rows[2][1] == -1 and float(rows[0][2]) == 18.0


def test_loading_twice_gives_no_duplicates(conn, csvs):
    load_data.load(conn, *csvs)
    assert load_data.load(conn, *csvs) == {"sales": 3, "weather": 2}

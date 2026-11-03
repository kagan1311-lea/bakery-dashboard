"""Issue #2: dashboard numbers on a small hand-made dataset, and the page itself."""

from datetime import date

import pytest
import streamlit as st
from streamlit.testing.v1 import AppTest

import db
from conftest import create_tables

# ticket, day, article, quantity, unit price
ROWS = [
    (1, "2026-07-01", "חלה", 2, 18),
    (1, "2026-07-01", "לחמנייה", 6, 4),
    (2, "2026-07-01", "לחמנייה", 4, 4),
    (3, "2026-07-02", "בבקה שוקולד", 1, 42),
    (4, "2026-07-02", "חלה", 1, 18),
    (5, "2026-07-02", "חלה", -1, 18),  # a return
]
START, END = date(2026, 7, 1), date(2026, 7, 2)


@pytest.fixture
def sales(conn):
    create_tables(conn)
    with conn, conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO sales (sold_at, ticket_number, article, category, quantity, unit_price) "
            "VALUES (%s::date + time '08:00', %s, %s, 'x', %s, %s)",
            [(day, ticket, article, qty, price) for ticket, day, article, qty, price in ROWS],
        )
    return conn


def test_totals(sales):
    t = db.totals(sales, START, END)
    assert t["revenue"] == 36 + 24 + 16 + 42 + 18 - 18
    assert t["transactions"] == 4  # ticket 5 is only a return
    assert t["best_seller"] == "לחמנייה"  # 10 units, more than חלה's 2 net


def test_revenue_by_day(sales):
    assert db.revenue_by_day(sales, START, END) == [(START, 76.0), (END, 42.0)]


def test_top_products_best_first(sales):
    assert db.top_products(sales, START, END) == [("לחמנייה", 10), ("חלה", 2), ("בבקה שוקולד", 1)]
    assert db.top_products(sales, START, END, limit=1) == [("לחמנייה", 10)]


def test_date_range(sales):
    assert db.date_range(sales) == (START, END)


def test_range_includes_only_its_days(sales):
    t = db.totals(sales, END, END)
    assert t["revenue"] == 42 and t["transactions"] == 2 and t["best_seller"] == "בבקה שוקולד"
    assert db.revenue_by_day(sales, END, END) == [(END, 42.0)]
    assert db.top_products(sales, START, START) == [("לחמנייה", 10), ("חלה", 2)]


def run_app(monkeypatch, url):
    monkeypatch.setenv("DATABASE_URL", url)
    st.cache_data.clear()
    return AppTest.from_file("app.py", default_timeout=30).run()


def test_page_shows_three_cards(sales, schema_url, monkeypatch):
    at = run_app(monkeypatch, schema_url)
    assert not at.exception
    assert [m.label for m in at.metric] == ["סך ההכנסות", "מספר עסקאות", "המוצר הנמכר ביותר"]
    assert at.metric[2].value == "לחמנייה"


def test_date_filter_defaults_to_full_range(sales, schema_url, monkeypatch):
    at = run_app(monkeypatch, schema_url)
    assert at.date_input[0].value == (START, END)
    assert at.metric[0].value == "₪118"


def test_date_filter_narrows_the_cards(sales, schema_url, monkeypatch):
    at = run_app(monkeypatch, schema_url)
    at.date_input[0].set_value((END, END)).run()
    assert not at.exception
    assert [m.value for m in at.metric] == ["₪42", "2", "בבקה שוקולד"]


def test_page_shows_error_when_db_unreachable(monkeypatch):
    at = run_app(monkeypatch, "postgresql://nobody:nothing@127.0.0.1:1/none")
    assert not at.exception
    assert len(at.error) == 1
    assert not at.metric

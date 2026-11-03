"""Dashboard queries. Every function takes an open connection and a date range (inclusive).

See architecture.md → Flows → Dashboard load.
"""

import os

import psycopg2


def connect(url=None):
    return psycopg2.connect(url or os.environ["DATABASE_URL"], connect_timeout=10)


def _rows(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def date_range(conn):
    """(first day, last day) in the sales data."""
    return _rows(conn, "SELECT min(sold_at)::date, max(sold_at)::date FROM sales")[0]


def totals(conn, start, end):
    """Revenue (returns included), transactions (tickets with a sale) and best seller by quantity."""
    revenue, transactions = _rows(conn, """
        SELECT coalesce(sum(quantity * unit_price), 0),
               count(DISTINCT ticket_number) FILTER (WHERE quantity > 0)
        FROM sales WHERE sold_at::date BETWEEN %s AND %s
    """, (start, end))[0]
    best = top_products(conn, start, end, limit=1)
    return {
        "revenue": float(revenue),
        "transactions": transactions,
        "best_seller": best[0][0] if best else None,
    }


def revenue_by_day(conn, start, end):
    """[(day, revenue)] in date order."""
    return [(day, float(revenue)) for day, revenue in _rows(conn, """
        SELECT sold_at::date AS day, sum(quantity * unit_price)
        FROM sales WHERE sold_at::date BETWEEN %s AND %s
        GROUP BY day ORDER BY day
    """, (start, end))]


def product_sales(conn, start, end, product):
    """[(article, units, revenue)] for articles whose name contains `product`."""
    return [(article, units, float(revenue)) for article, units, revenue in _rows(conn, """
        SELECT article, sum(quantity), sum(quantity * unit_price)
        FROM sales WHERE sold_at::date BETWEEN %s AND %s AND article ILIKE %s
        GROUP BY article ORDER BY 2 DESC
    """, (start, end, f"%{product}%"))]


def top_products(conn, start, end, limit=10):
    """[(article, quantity sold)], best first; ties broken by name."""
    return _rows(conn, """
        SELECT article, sum(quantity) AS sold
        FROM sales WHERE sold_at::date BETWEEN %s AND %s
        GROUP BY article ORDER BY sold DESC, article LIMIT %s
    """, (start, end, limit))

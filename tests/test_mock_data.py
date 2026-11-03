"""Issue #1: mock data is deterministic and keeps the Kaggle revenue."""

import random
from collections import defaultdict

import mock_data


def build():
    return mock_data.build_sales(random.Random(mock_data.SEED), mock_data.read_revenue())


def test_same_seed_gives_same_rows():
    assert build() == build()


def test_daily_revenue_per_category_matches_kaggle():
    revenue = mock_data.read_revenue()
    expected = defaultdict(float)
    for day, groups in revenue.items():
        for group, eur in groups.items():
            category = mock_data.PRODUCTS[group][0]
            expected[(day + mock_data.SHIFT, category)] += eur * mock_data.EUR_TO_ILS

    actual = defaultdict(float)
    for sold_at, _, _, category, qty, price in build():
        if qty > 0:  # returns are added on top of the Kaggle revenue
            actual[(sold_at.date(), category)] += qty * price

    # 5%, or ₪15 on small days where one item is a big share of the total
    off = [key for key, value in expected.items() if abs(actual[key] - value) > max(0.05 * value, 15)]
    assert not off, f"{len(off)} of {len(expected)} day/category totals off by > 5%: {off[:3]}"

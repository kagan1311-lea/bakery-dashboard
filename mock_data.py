"""Build mock transaction data from the Kaggle bakery files.

Input  (data/raw/, never edited):
  train.csv   daily revenue (EUR) per product group, Kiel bakery 2013-2018
  wetter.csv  daily weather for the same city

Output (data/, regenerated, not committed):
  sales.csv    one row per line item: sold_at, ticket_number, article, category, quantity, unit_price
  weather.csv  one row per day: date, cloud_cover, temperature_c, wind_speed, weather_code

How: take the last two years of train.csv, convert each group's daily revenue to ILS, split it
into line items of invented Israeli bakery products, then pack the items into tickets with
times in opening hours. Dates are shifted by whole weeks so weekdays and seasons stay put.
Seeded, so every run gives the same files.

Usage: python mock_data.py
"""

import csv
import random
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data")
SEED = 42
YEARS_KEPT = 2
SHIFT = timedelta(weeks=417)  # 2018-07-31 -> 2026-07-28, same weekday
EUR_TO_ILS = 4.0
FIRST_TICKET = 100001
RETURN_RATE = 0.002  # share of tickets that are a single-item return

# Kaggle group number -> (category, [(article, unit_price ILS, weight, max qty, months or None)])
PRODUCTS = {
    "1": ("לחמים", [
        ("חלה", 18.0, 3, 2, None),
        ("לחם מחמצת", 24.0, 3, 1, None),
        ("לחם כוסמין", 26.0, 2, 1, None),
        ("באגט", 12.0, 3, 2, None),
        ("לחם שיפון", 22.0, 1, 1, None),
    ]),
    "2": ("לחמניות", [
        ("לחמנייה", 4.0, 4, 6, None),
        ("בייגלה ירושלמי", 8.0, 3, 4, None),
        ("לחמניית מלא", 5.0, 2, 6, None),
        ("פוקאצ'ה אישית", 10.0, 2, 2, None),
    ]),
    "3": ("קרואסונים", [
        ("קרואסון חמאה", 12.0, 4, 3, None),
        ("קרואסון שקדים", 15.0, 2, 2, None),
        ("פן או שוקולד", 13.0, 3, 3, None),
        ("בורקס גבינה", 11.0, 3, 3, None),
    ]),
    "4": ("קונדיטוריה", [
        ("אקלר", 16.0, 3, 2, None),
        ("טארט פירות", 22.0, 2, 1, None),
        ("מוס שוקולד", 20.0, 2, 2, None),
        ("אלפחורס", 8.0, 2, 4, None),
    ]),
    "5": ("עוגות", [
        ("עוגת שמרים", 45.0, 3, 1, None),
        ("בבקה שוקולד", 42.0, 3, 1, None),
        ("עוגת גבינה (פרוסה)", 18.0, 2, 2, None),
        ("רוגלך (100 גרם)", 14.0, 3, 2, None),
        ("עוגיות חמאה", 10.0, 2, 3, None),
    ]),
    "6": ("עונתי", [
        ("עוגת דבש", 38.0, 3, 1, {9, 10}),
        ("חלה עגולה", 22.0, 2, 2, {9, 10}),
        ("סופגנייה", 7.0, 4, 6, {11, 12, 1}),
        ("לביבה מתוקה", 9.0, 1, 4, {11, 12, 1}),
    ]),
}
FRIDAY_BOOST = {"חלה": 5}  # challah sells mostly on Fridays

# opening hours: hour -> relative weight; Friday closes early, Saturday the Kaggle data has sales too
HOURS = {6: 3, 7: 9, 8: 10, 9: 8, 10: 6, 11: 5, 12: 5, 13: 4, 14: 4, 15: 4, 16: 6, 17: 7, 18: 5, 19: 2}
FRIDAY_HOURS = {6: 5, 7: 10, 8: 12, 9: 12, 10: 10, 11: 8, 12: 6, 13: 4, 14: 2}
TICKET_SIZES = [1, 2, 3, 4]
TICKET_SIZE_WEIGHTS = [40, 30, 20, 10]


def parse_day(text):
    return datetime.strptime(text, "%d/%m/%Y").date()


def read_revenue():
    """{date: {group: revenue EUR}} for the last YEARS_KEPT years of train.csv."""
    revenue = defaultdict(dict)
    with open(RAW / "train.csv", newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            revenue[parse_day(row["Datum"])][row["Warengruppe"]] = float(row["Umsatz"])
    last = max(revenue)
    first = last - timedelta(days=365 * YEARS_KEPT - 1)
    return {d: groups for d, groups in revenue.items() if d >= first}


def products_for(group, day):
    category, items = PRODUCTS[group]
    friday = day.weekday() == 4
    choices = [
        (name, price, weight * (FRIDAY_BOOST.get(name, 1) if friday else 1), max_qty)
        for name, price, weight, max_qty, months in items
        if months is None or day.month in months
    ]
    return category, choices


def split_revenue(rng, group, day, target):
    """Line items (article, category, qty, price) adding up to about `target` ILS."""
    category, choices = products_for(group, day)
    if not choices:
        return []
    weights = [c[2] for c in choices]
    cheapest = min(c[1] for c in choices)
    items, remaining = [], target
    while remaining >= cheapest / 2:
        name, price, _, max_qty = rng.choices(choices, weights)[0]
        qty = min(rng.choices(range(1, max_qty + 1), [2 ** -q for q in range(max_qty)])[0],
                  max(1, round(remaining / price)))
        items.append((name, category, qty, price))
        remaining -= qty * price
    return items


def pack_tickets(rng, day, items):
    """Group a day's line items into tickets with a time of sale."""
    rng.shuffle(items)
    hours = FRIDAY_HOURS if day.weekday() == 4 else HOURS
    tickets = []
    while items:
        size = rng.choices(TICKET_SIZES, TICKET_SIZE_WEIGHTS)[0]
        lines, items = items[:size], items[size:]
        hour = rng.choices(list(hours), list(hours.values()))[0]
        sold_at = datetime(day.year, day.month, day.day, hour, rng.randrange(60), rng.randrange(60))
        merged = defaultdict(int)
        for name, category, qty, price in lines:
            merged[(name, category, price)] += qty
        tickets.append((sold_at, [(n, c, q, p) for (n, c, p), q in merged.items()]))
    return sorted(tickets)


def build_sales(rng, revenue):
    rows, ticket = [], FIRST_TICKET
    for day in sorted(revenue):
        shifted = day + SHIFT
        items = []
        for group, eur in sorted(revenue[day].items()):
            items += split_revenue(rng, group, shifted, eur * EUR_TO_ILS)
        for sold_at, lines in pack_tickets(rng, shifted, items):
            for name, category, qty, price in lines:
                rows.append((sold_at, ticket, name, category, qty, price))
            if rng.random() < RETURN_RATE:
                name, category, _, price = rng.choice(lines)
                ticket += 1
                rows.append((sold_at + timedelta(minutes=rng.randrange(5, 60)), ticket, name, category, -1, price))
            ticket += 1
    return rows


def write_sales(rows):
    with open(OUT / "sales.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["sold_at", "ticket_number", "article", "category", "quantity", "unit_price"])
        for sold_at, ticket, name, category, qty, price in rows:
            w.writerow([sold_at.isoformat(sep=" "), ticket, name, category, qty, f"{price:.2f}"])


def write_weather(first, last):
    with open(RAW / "wetter.csv", newline="", encoding="utf-8") as src, \
         open(OUT / "weather.csv", "w", newline="", encoding="utf-8") as dst:
        w = csv.writer(dst)
        w.writerow(["date", "cloud_cover", "temperature_c", "wind_speed", "weather_code"])
        count = 0
        for row in csv.DictReader(src):
            day = parse_day(row["Datum"])
            if first <= day <= last:
                w.writerow([(day + SHIFT).isoformat(), row["Bewoelkung"], row["Temperatur"],
                            row["Windgeschwindigkeit"], row["Wettercode"]])
                count += 1
    return count


def main():
    rng = random.Random(SEED)
    revenue = read_revenue()
    rows = build_sales(rng, revenue)
    write_sales(rows)
    weather_days = write_weather(min(revenue), max(revenue))

    total = sum(r[4] * r[5] for r in rows)
    tickets = len({r[1] for r in rows})
    days = len(revenue)
    print(f"sales.csv   {len(rows):,} lines, {tickets:,} tickets, {days} days "
          f"({min(revenue) + SHIFT} .. {max(revenue) + SHIFT})")
    print(f"            revenue {total:,.0f} ILS, {total / days:,.0f} ILS/day, {total / tickets:.1f} ILS/ticket")
    print(f"weather.csv {weather_days} days")


if __name__ == "__main__":
    main()

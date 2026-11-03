# Bakery Sales Dashboard + Ask Box — spec

A one-page sales dashboard for a small bakery, with a small question box where Claude answers questions about the sales data.

## 1. Users

- **Who:** the bakery owner and up to three staff. **Ten users at most.**
- **From where:** the office laptop (desktop-first) and phones (must stay readable on a narrow screen).
- **How often:** a few times a day — a morning look at yesterday's numbers, the occasional question.
- **Not users:** customers, suppliers, anyone outside the bakery. No public sign-up.

## 2. Jobs

1. **See how sales are doing** — the owner opens the page and sees total revenue, number of transactions and the best-selling product, a daily sales line chart and the top 10 products bar chart.
2. **Narrow to a period** — the owner picks a date range and every number and chart updates to that range.
3. **Ask a question in plain words** — the owner types "What sold best last week?" and gets a short answer built only from numbers the `sales_query` tool returned from Postgres. Never an invented number.

## 3. Not in v1

- Logging invoices, photos or file uploads
- Writing, editing or deleting sales data from the UI or the agent (the agent is **read-only**)
- Chat history kept across sessions, conversation list
- User accounts, roles, multi-tenant (one bakery only)
- Payments, inventory, forecasting
- A mobile app (the web page is responsive)
- Morning digest / scheduled jobs
- Questions outside the bakery's sales (weather, recipes, general chat) — the agent says they are out of scope

## 4. Speed — per job

| Job | Mechanism | Target |
|---|---|---|
| Dashboard load (cards + charts) | Request/response, queries cached (`st.cache_data`, 10 min) | Under **3 s** on first load, under 1 s when cached |
| Date-range change | Same, re-query | Under **2 s** |
| Ask a question | Request/response with a spinner (no streaming in v1) | Answer under **10 s** |
| Loading the CSV into Postgres | One-off script, run by hand | Minutes is fine |

## 5. Data

- **Source:** two Kaggle files from a bakery in Kiel, kept untouched in `data/raw/`:
  - `train.csv`: daily revenue (EUR) per product group (1 bread, 2 rolls, 3 croissants, 4 confectionery, 5 cakes, 6 seasonal), 2013-07 to 2018-07
  - `wetter.csv`: daily weather (cloud cover, temperature, wind, weather code)
- **Mock transactions:** the Kaggle data has no tickets or products, so `mock_data.py` builds them. It takes the last 2 years, converts each group's daily revenue to ₪ (×4), and splits it into line items of invented Israeli bakery products (Hebrew names, e.g. חלה, בייגלה ירושלמי, רוגלך, סופגנייה). It then packs them into tickets with a time in opening hours. Daily revenue per group matches the source within a few percent. Challah peaks on Fridays, and the seasonal items appear only in season (sufganiyot in Nov–Jan). About 0.2% of tickets are returns (quantity −1). The script is seeded, so every run gives the same files.
- **Dates:** shifted by whole weeks (+417 weeks), so weekdays and seasons are kept. The data covers **2024-07-29 → 2026-07-28**: 713 trading days, ~165k lines, ~89k tickets, ~₪4,000/day.
- **"Today" is the last date in the data**, not the calendar date. "Last week" means the 7 days ending on `MAX(sold_at)`. The data ends in July 2026, so the real "last week" would be empty.
- **Stored:** `sales` (from `data/sales.csv`), `weather` (from `data/weather.csv`), and `agent_runs` (each question: text, tool calls, answer, tokens, cost). `agent_runs` is kept **90 days**.
- **Sensitive:** nothing personal in the sales data. Secrets (`ANTHROPIC_API_KEY`, `DATABASE_URL`) are never in the repo.

## 6. Limits

- **Questions:** 20 per browser session per hour (Streamlit has no login, so the session is the "user").
- **Spend:** **$1/month** hard cap on model cost, counted from `agent_runs` since the 1st of the month. Over the cap the box says "the assistant is resting until next month"; the dashboard keeps working. A second, hard cap is set on the Anthropic workspace that owns the key (Console → Limits).
- **Question length:** 500 characters max.
- **Model:** see [architecture.md](architecture.md) → Model.

## 7. Done — checks a stranger could run

**Feature: Load the CSV into Postgres (v1)**
1. `python mock_data.py` then `python load_data.py` fills `sales` with one row per line of `data/sales.csv`, and `weather` with one row per day.
2. Running `load_data.py` a second time leaves the same row count — no duplicates.
3. For every day, the mock revenue per category (returns excluded) is within 5% (or ₪15 on small days) of the Kaggle revenue × 4.

**Feature: Dashboard (v2)**
4. The page shows three cards: total revenue, number of transactions (distinct `ticket_number`), best-selling product (by quantity).
5. A line chart shows revenue per day; a bar chart shows the top 10 products by quantity.
6. The best-seller function returns the right product on a small hand-made dataset.
7. If the database cannot be reached, the page shows a clear error instead of crashing.

**Feature: Date-range filter (v2)**
8. Picking a date range changes the cards and both charts to that range only.
9. The default range is the full data range.

**Feature: Ask box (v3)**
10. "What sold best last week?" → the `sales_query` tool is called and the answer names a product that appears in the tool's result.
11. "Delete all the data" → no tool call; the agent refuses.
12. "What's the weather?" → no tool call; the agent says it only answers questions about the bakery's sales.
13. Question 21 in the same hour is refused with a message; nothing is sent to the model.
14. When the month's spend passes $1, the box is disabled with a message; nothing is sent to the model.

# Tickets — drafts for GitHub Issues

Taken from [spec.md](spec.md) §7. Copy each one into a GitHub Issue, using the format from [practice.md](practice.md). After the Issues exist, GitHub is the source of truth, not this file.

---

## #1 Mock data from Kaggle, loaded into Postgres
**Milestone** v1 data · **Label** feature · **Branch** `1-load-data`

**Why** spec.md §2 and §5: every job needs the sales data in Postgres.

**Done when**
- `python mock_data.py` writes `data/sales.csv` + `data/weather.csv`, and two runs give identical files
- for every day, the mock revenue per category (returns excluded) is within 5% (or ₪15 on small days) of Kaggle revenue × 4
- `python load_data.py` creates the tables from `schema.sql` and fills `sales` and `weather`
- running `load_data.py` twice leaves the same row count

**Test** `tests/test_mock_data.py`: deterministic output and revenue match. `tests/test_load_data.py`: a double load gives no duplicates (Postgres in CI)

**Out of scope** dashboard (#2), read-only queries for the agent (#4)

---

## #2 Dashboard: cards and charts
**Milestone** v2 dashboard · **Label** feature · **Branch** `2-dashboard`

**Why** spec.md §2, job 1.

**Done when**
- three cards: total revenue, number of transactions, best-selling product
- a line chart of revenue per day and a bar chart of the top 10 products
- if the database is unreachable, the page shows an error message instead of crashing

**Test** `tests/test_metrics.py`: best seller and totals on a small hand-made dataset

**Out of scope** date filter (#3), ask box (#4)

---

## #3 Date-range filter
**Milestone** v2 dashboard · **Label** feature · **Branch** `3-date-filter`

**Why** spec.md §2, job 2.

**Done when**
- picking a range changes the cards and both charts to that range
- the default range is the full data range

**Test** `tests/test_metrics.py`: the metrics for a range include only rows in that range

**Out of scope** comparing two periods

---

## #4 Ask box with Claude and `sales_query`
**Milestone** v3 agent · **Label** feature · **Branch** `4-ask-agent`

**Why** spec.md §2, job 3.

**Done when**
- "What sold best last week?" calls `sales_query` and the answer names a product from the tool result
- "Delete all the data" makes no tool call, and the agent refuses
- an out-of-scope question makes no tool call, and the agent says it only answers questions about sales
- `sales_query` runs in a READ ONLY transaction and accepts only the fixed parameters
- every question is saved to `agent_runs` with its tokens and cost

**Test** `tests/test_agent.py` (model mocked): a fake tool_use runs the query and an answer comes back. Evals: `evals/cases.yaml` (10 cases), score saved to `evals/history.csv`

**Out of scope** rate limit and monthly cap (#5), chat history

---

## #5 Limits: questions per hour and monthly spend cap
**Milestone** v3 agent · **Label** feature · **Branch** `5-limits`

**Why** spec.md §6.

**Done when**
- question 21 in the same session hour is refused, and the model is not called
- once this month's `agent_runs.cost_usd` sum is ≥ $1, the box is disabled with a message
- a question longer than 500 characters is refused

**Test** `tests/test_limits.py`

**Out of scope** user accounts

---

## #6 CI gate
**Milestone** v1 data · **Label** feature · **Branch** `6-ci`

**Why** practice.md step 8: merge only when CI is green.

**Done when** `.github/workflows/ci.yml` runs `pytest` on every PR, with a Postgres service container and no Anthropic key

**Test** the PR's own check turns green

---

## #7 (expected bug) "Last week" returns nothing
**Label** bug · **Branch** `7-fix-relative-dates`

Open this only if the eval actually shows it. Steps: ask "What sold best last week?". Expected: a product. Actual: empty, because the agent uses the calendar date and not `MAX(sold_at)`. Fixes spec.md §5.

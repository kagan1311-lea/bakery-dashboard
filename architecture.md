# Architecture

Read with [spec.md](spec.md). When the system changes, this file changes in the same commit.

## Components

```
 ┌──────────────────────────┐        ┌──────────────────────────────┐
 │ LAYER 1 · UI             │        │ EXTERNAL · MODEL             │
 │ Streamlit page (app.py)  │        │ Claude API                   │
 │ cards · charts · filter  │        │ stateless, billed per token  │
 │ ask box                  │        └──────────────▲───────────────┘
 └────────────┬─────────────┘                       │ one call per turn
              │ same process                        │ (+1 after a tool call)
 ┌────────────▼─────────────────────────────────────┴───────────────┐
 │ LAYER 2 · BACKEND (Python, same Streamlit process)               │
 │ db.py: dashboard queries  ·  agent.py: agent loop, rate limit,   │
 │ daily cap, logging to agent_runs                                 │
 └────────────┬─────────────────────────────┬───────────────────────┘
              │ read                        │ read-only role
 ┌────────────▼─────────────┐     ┌─────────▼──────────────────────┐
 │ LAYER 3 · DATABASE       │◄────┤ LAYER 4 · TOOLS                │
 │ Postgres                 │     │ sales_query (read)             │
 │ sales · agent_runs       │     │ fixed metrics + date range     │
 └──────────────────────────┘     └────────────────────────────────┘
              ▲
              │ one-off: load_data.py (CSV from Kaggle)
```

The UI and the backend are one Streamlit process. There is no separate API, because one business with up to ten users does not need one.

## Flows

**Dashboard load / date change**
1. `app.py` reads the date range (default: min → max of `sales.sold_at`).
2. `db.py` runs 3 aggregate queries (cards, revenue per day, top 10), cached 10 min.
3. Streamlit draws the cards and charts.

**Ask a question**
1. The user types a question. `agent.py` checks the length (≤ 500), the session's count this hour (≤ 20) and today's spend from `agent_runs` (≤ $1). If any check fails, it returns a message and does not call the model.
2. Call Claude with the system prompt and the `sales_query` tool. The system prompt says that "today" is `MAX(sold_at)`.
3. If Claude asks for `sales_query`: validate the arguments, run a parameterised query, and send the rows back. One more call to Claude produces the answer. Max **3 tool calls** per question.
4. Save to `agent_runs` the question, the tool calls, the answer, the tokens and the cost. Show the answer.

**Load data (one-off)**
1. `python mock_data.py` reads `data/raw/train.csv` + `wetter.csv` and writes `data/sales.csv` + `data/weather.csv` (seeded, about 2 s).
2. `python load_data.py` runs `TRUNCATE sales, weather` and inserts both CSVs, in one transaction.

## Storage

| Table | Key | Columns |
|---|---|---|
| `sales` | `id` (serial) | `sold_at` timestamp, `ticket_number` int, `article` text (Hebrew), `category` text (Hebrew), `quantity` int (negative = return), `unit_price` numeric(8,2) ILS |
| `weather` | `date` | `cloud_cover` int (0–8), `temperature_c` numeric, `wind_speed` int, `weather_code` int (nullable) |
| `agent_runs` | `id` (serial) | `asked_at` timestamptz, `session_id` text, `question` text, `tool_calls` jsonb, `answer` text, `input_tokens` int, `output_tokens` int, `cost_usd` numeric(8,5) |

- Index on `sales(sold_at)`, because every query filters by date.
- The schema lives in `schema.sql` and `load_data.py` runs it (`CREATE TABLE IF NOT EXISTS`). Nobody creates tables by hand.
- `agent_runs` rows older than 90 days are deleted when the app starts.

## Tool: `sales_query`

The model **never writes SQL**. The tool takes fixed parameters, and the code builds a parameterised query:

| Parameter | Values |
|---|---|
| `metric` | `top_products` · `revenue_by_day` · `totals` (revenue, transactions) · `product_sales` |
| `start_date`, `end_date` | ISO dates, inside the data range |
| `product` | only for `product_sales` |
| `limit` | 1–20, default 10 |

It runs with a Postgres role that has `SELECT` only. Even a bug cannot delete data.

## Model

- **Model:** `claude-haiku-5-5`. One simple tool and short answers, so the cheapest current model is enough. Revisit if eval pass rate < 80%.
- **Effort:** default, no extended thinking. The task is lookup-and-summarise, not reasoning.
- **max_tokens:** 512 per call. Answers are 2–4 sentences.
- **System prompt:** cached (prompt caching), since it is identical on every call.
- **History:** none. Each question stands alone (spec §3).

## Limits

| Layer | Owner | Number |
|---|---|---|
| Users → us | `agent.py` | 20 questions / session / hour · 500 chars / question |
| Us → Anthropic | Anthropic SDK | Built-in retry with backoff on 429/5xx (max 2 retries). Then "try again in a minute". |
| Our wallet | `agent.py` + `agent_runs` | **$1 / day**, then the box is disabled until midnight (Asia/Jerusalem) |
| Agent loop | `agent.py` | Max 3 tool calls per question |

## Hosting (Part 2 — planned)

| Piece | Home | Size |
|---|---|---|
| Streamlit service (UI + backend) | Railway service from this GitHub repo; deploys on every push to `main` | 0.5 vCPU · 512 MB |
| Postgres | Railway Postgres plugin, same project | < 100 MB (~165k sales rows) |
| Model | Anthropic API | ~50 questions/day × ~2 calls |
| Secrets | `.env` locally · Railway Variables in production | — |

**Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

**Rough cost:** hosting is a few dollars a month (Railway plan). The model costs about 100 calls/day × ~1.5k tokens, which is cents per day and well under the $1 cap.

## Secrets

| Name | Used by | Local | Railway |
|---|---|---|---|
| `DATABASE_URL` | app (dashboard + agent, read-only role) | `.env` | Variables (Postgres plugin reference; use the *internal* URL) |
| `DATABASE_ADMIN_URL` | `load_data.py` only (needs write) | `.env` (Railway's *public* URL) | not set — the service never writes `sales` |
| `ANTHROPIC_API_KEY` | `agent.py` | `.env` | Variables |

`.env` is in `.gitignore`. `.env.example` lists these names with no values.

**Check:** `git log -p | grep -E "sk-ant|rlwy\.net"` must come back empty. The only connection string in the repo is CI's throwaway `postgres:postgres@localhost` container.

**CI** (`.github/workflows/ci.yml`) needs no secrets: Postgres is a service container and the model is mocked.

## Decisions

| Date | Choice | Reason | What would change it |
|---|---|---|---|
| 2026-11-03 | Streamlit over HTML/JS + API | One Python file gives cards, charts and an input box, with no frontend build. Up to 10 users fits one process | Real login, or more than ~50 users at once |
| 2026-11-03 | Postgres over CSV in the repo / SQLite | Railway gives it in one click, it survives redeploys, and the agent's read-only role is native | Data stays tiny and the agent is dropped |
| 2026-11-03 | Fixed-parameter tool over free SQL | The "delete all data" case can't happen by design, answers are testable, and evals are deterministic on tool args | Questions the 4 metrics can't answer show up in evals |
| 2026-11-03 | `claude-haiku-5-5` | Cheapest, fast enough for < 10 s, and the job is simple | Eval pass rate < 80% → try Sonnet and compare cost |
| 2026-11-03 | "Today" = `MAX(sold_at)` | The dataset is historical, so calendar "last week" is always empty | Live data starts flowing in |
| 2026-11-03 | Mock transactions built from Kaggle "bakery sales Kiel" daily group revenue | The real file has revenue per group per day only, but the dashboard and agent need tickets and products. Building them from real daily totals keeps real trends (weekday, season, years) | A transaction-level dataset becomes available |
| 2026-11-03 | Hebrew product names, prices in ₪ | The users are an Israeli bakery's staff | — |
| 2026-11-03 | Shift dates +417 weeks; keep the last 2 years | Data ends close to "now" with weekdays and seasons kept; ~165k rows fits a small DB | — |
| 2026-11-03 | Generated CSVs not committed (`.gitignore`); `data/raw/` committed | The output is reproducible from the seed, so 12 MB would be noise in Git | Generation stops being deterministic |
| 2026-11-03 | `TRUNCATE` + insert on load | Re-running never duplicates rows, and there is no natural unique key (one ticket has many rows) | Incremental daily loads |

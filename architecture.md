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
 │ monthly cap, logging to agent_runs                               │
 └────────────┬─────────────────────────────┬───────────────────────┘
              │ read                        │ READ ONLY transaction
 ┌────────────▼─────────────┐     ┌─────────▼──────────────────────┐
 │ LAYER 3 · DATABASE       │◄────┤ LAYER 4 · TOOLS                │
 │ Postgres                 │     │ sales_query (read)             │
 │ sales · agent_runs       │     │ fixed metrics + date range     │
 └──────────────────────────┘     └────────────────────────────────┘
              ▲
              │ one-off: load_data.py (CSV from Kaggle)
```

The UI and the backend are one Streamlit process. There is no separate API, because one business with up to ten users does not need one.

**The agent's five parts** (lesson 6: LLM + tools + memory + goal + loop), and where each lives:

| Part | Here | File |
|---|---|---|
| LLM (brain) | `claude-haiku-5-5`, effort `low` | `agent.py` → `MODEL`, `EFFORT` |
| Tools (hands) | `sales_query`: 4 fixed metrics, READ ONLY transaction | `agent.py` → `TOOL`, `run_tool` |
| Memory: context | the question + tool results of this one question | `agent.py` → `ask` |
| Memory: notebook | products, synonyms, how to search | `notes/products.md` |
| Memory: the world | sales and weather (the system of record) | Postgres `sales`, `weather` |
| Goal (job) | who it is, rules, refusals, "today" | `agent.py` → `SYSTEM` |
| Loop (engine) | ask → run tool → feed back; max 3 tool calls | `agent.py` → `ask` |
| Log | every question with tokens and cost | Postgres `agent_runs` |

## Flows

**Dashboard load / date change**
1. `app.py` reads the date range (default: min → max of `sales.sold_at`).
2. `db.py` runs 3 aggregate queries (cards, revenue per day, top 10), cached 10 min.
3. Streamlit draws the cards and charts.

**Ask a question**
1. The user types a question. `agent.py` checks the length (≤ 500), the session's count this hour (≤ 20) and this month's spend from `agent_runs` (≤ $1). If any check fails, it returns a message and does not call the model.
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
| `product` | only for `product_sales`; several matches also return a `total`, so the model never adds numbers itself |
| `limit` | 1–20, default 10 |

Every query runs inside a `SET TRANSACTION READ ONLY` transaction, so Postgres itself rejects any write. Even a bug cannot delete data (tested in `tests/test_agent.py`).

## Model

- **Model:** `claude-haiku-5-5`. One simple tool and short answers, so the cheapest current model is enough. Revisit if eval pass rate < 80%.
- **Effort:** `low` (adaptive thinking stays on, as on every Haiku 5.5 call). The task is lookup-and-summarise, not reasoning; the evals pass at 100% at this level.
- **max_tokens:** 512 per call. Answers are 2–4 sentences.
- **System prompt:** cached (prompt caching), since it is identical on every call.
- **History:** none. Each question stands alone (spec §3).
- **Notebook:** `notes/products.md` (products, synonyms, plurals, how to search) is appended to the cached system prompt. Edit it when the product list changes.

## Limits

| Layer | Owner | Number |
|---|---|---|
| Users → us | `agent.py` | 20 questions / session / hour · 500 chars / question |
| Us → Anthropic | Anthropic SDK | Built-in retry with backoff on 429/5xx (max 2 retries). Then "try again in a minute". |
| Our wallet | `agent.py` + `agent_runs` | **$1 / month**, then the box is disabled until the 1st (Asia/Jerusalem) |
| Our wallet, hard stop | Anthropic Console | Workspace `bakery-dashboard` spend limit; the API key lives in that workspace |
| Agent loop | `agent.py` | Max 3 tool calls per question · 20 s timeout per model call, 2 retries · a cut answer (`max_tokens`) is replaced by a clear message · a DB error inside the tool goes back to the model as `is_error` |
| Page | `app.py` | Timeout, API, DB and unexpected errors each show a short Hebrew message and are logged (`bakery.ask` logger → Railway logs); the dashboard above keeps working |

## Hosting (Part 2 — planned)

| Piece | Home | Size |
|---|---|---|
| Streamlit service (UI + backend) | Railway service from this GitHub repo; deploys on every push to `main` | 0.5 vCPU · 512 MB |
| Postgres | Railway Postgres plugin, same project | < 100 MB (~165k sales rows) |
| Model | Anthropic API | ~50 questions/day × ~2 calls |
| Secrets | `.env` locally · Railway Variables in production | — |

**Start command:** `streamlit run app.py --server.port $PORT --server.address 0.0.0.0`

**Rough cost:** hosting is a few dollars a month (Railway plan). The model costs about 100 calls/day × ~1.5k tokens, about $0.0002–0.0005 per question: thousands of questions fit under the $1/month cap.

## Secrets

| Name | Used by | Local | Railway |
|---|---|---|---|
| `DATABASE_URL` | app (dashboard + agent; tool queries in READ ONLY transactions) | `.env` | Variables (Postgres plugin reference; use the *internal* URL) |
| `DATABASE_ADMIN_URL` | `load_data.py` only (needs write) | `.env` (Railway's *public* URL) | not set — the service never writes `sales` |
| `ANTHROPIC_API_KEY` | `agent.py` | `.env` | Variables |

`.env` is in `.gitignore`. `.env.example` lists these names with no values.

**Check:** `git log -p | grep -E "sk-ant|rlwy\.net"` must come back empty. The only connection string in the repo is CI's throwaway `postgres:postgres@localhost` container.

**CI** (`.github/workflows/ci.yml`) needs no secrets: Postgres is a service container and the model is mocked.

## Decisions

| Date | Choice | Reason | What would change it |
|---|---|---|---|
| 2026-11-03 | Streamlit over HTML/JS + API | One Python file gives cards, charts and an input box, with no frontend build. Up to 10 users fits one process | Real login, or more than ~50 users at once |
| 2026-11-03 | Postgres over CSV in the repo / SQLite | Railway gives it in one click, it survives redeploys, and READ ONLY transactions are native | Data stays tiny and the agent is dropped |
| 2026-11-03 | Fixed-parameter tool over free SQL | The "delete all data" case can't happen by design, answers are testable, and evals are deterministic on tool args | Questions the 4 metrics can't answer show up in evals |
| 2026-11-03 | `claude-haiku-5-5` | Cheapest, fast enough for < 10 s, and the job is simple | Eval pass rate < 80% → try Sonnet and compare cost |
| 2026-11-03 | "Today" = `MAX(sold_at)` | The dataset is historical, so calendar "last week" is always empty | Live data starts flowing in |
| 2026-11-03 | Mock transactions built from Kaggle "bakery sales Kiel" daily group revenue | The real file has revenue per group per day only, but the dashboard and agent need tickets and products. Building them from real daily totals keeps real trends (weekday, season, years) | A transaction-level dataset becomes available |
| 2026-11-03 | Hebrew product names, prices in ₪ | The users are an Israeli bakery's staff | — |
| 2026-11-03 | Shift dates +417 weeks; keep the last 2 years | Data ends close to "now" with weekdays and seasons kept; ~165k rows fits a small DB | — |
| 2026-11-03 | Generated CSVs not committed (`.gitignore`); `data/raw/` committed | The output is reproducible from the seed, so 12 MB would be noise in Git | Generation stops being deterministic |
| 2026-11-03 | READ ONLY transaction for tool queries, not a separate Postgres role | Postgres enforces it per query, it needs no second secret on Railway, and a test proves a `DELETE` fails | The app gets other write paths, or more people get DB access |
| 2026-11-03 | Spend cap $1/month, not $1/day; also set as the Anthropic workspace spend limit | The owner's budget; ~$0.0003 per question leaves room for thousands | Real usage shows the box closing early in the month |
| 2026-11-03 | Effort `low` on Haiku 5.5 | Evals 30/30 at `low` (≈$0.0002 per question) | Eval pass rate drops below 80% |
| 2026-11-03 | Manual tool-use loop in our code, not Managed Agents or the SDK Tool Runner (lesson 6, "four ways to build one") | One question, one read-only tool, no sandbox, no files or bash, no schedule, one client. The loop is ~40 lines, tested with a mocked model, and runs inside the Streamlit service we already host | Scheduled jobs, file/bash/web tools, or many clients each with their own keys and memory → Managed Agents |
| 2026-11-03 | `TRUNCATE` + insert on load | Re-running never duplicates rows, and there is no natural unique key (one ticket has many rows) | Incremental daily loads |

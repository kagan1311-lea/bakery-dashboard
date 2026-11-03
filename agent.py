"""The ask box: Claude answers questions about sales using one read-only tool, sales_query.

The model never writes SQL. sales_query takes fixed parameters, and the code runs a
parameterised query inside a READ ONLY transaction. See architecture.md → Tool, Model, Limits.
"""

import json
from dataclasses import dataclass, field
from datetime import date

import anthropic
from psycopg2.extras import Json

import db

MODEL = "claude-haiku-5-5"
MAX_TOKENS = 1024
EFFORT = "low"
MAX_TOOL_CALLS = 3
RETENTION_DAYS = 90
# USD per token (claude-haiku-5-5, prompts under 100K tokens)
PRICE_INPUT = 0.10 / 1e6
PRICE_OUTPUT = 0.50 / 1e6
PRICE_CACHE_WRITE = PRICE_INPUT * 1.25
PRICE_CACHE_READ = PRICE_INPUT * 0.1

METRICS = ("totals", "top_products", "revenue_by_day", "product_sales")

SYSTEM = """You are the assistant of a small Israeli bakery. Staff ask you about the bakery's sales.

Rules:
- Answer in Hebrew, in 2-4 short sentences. Money is in shekels (₪).
- Every number in your answer must come from a sales_query result. Never estimate or invent a number. If the tool did not return it, say you don't have that figure.
- "Today" is the last day in the data, given at the start of each question - not the calendar date. "Last week" means the 7 days ending on that day; "last month" the 30 days ending on it.
- Product names are in Hebrew. For a question about one product, use metric product_sales with a short Hebrew name (e.g. "חלה", "סופגנייה").
- You can only read sales data. If asked to delete, change or add data, refuse politely and do not call the tool.
- If the question is not about the bakery's sales (weather, recipes, general chat), say briefly that you only answer questions about the bakery's sales, and do not call the tool."""

TOOL = {
    "name": "sales_query",
    "description": (
        "Read the bakery's sales for a date range (inclusive). "
        "totals: revenue, number of transactions and best-selling product. "
        "top_products: products ranked by units sold. "
        "revenue_by_day: revenue per day. "
        "product_sales: units and revenue of products whose name contains `product`."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metric": {"type": "string", "enum": list(METRICS)},
            "start_date": {"type": "string", "description": "YYYY-MM-DD"},
            "end_date": {"type": "string", "description": "YYYY-MM-DD"},
            "product": {"type": "string", "description": "Hebrew product name, only for product_sales"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "description": "top_products only, default 10"},
        },
        "required": ["metric", "start_date", "end_date"],
    },
}


@dataclass
class Answer:
    text: str
    tool_calls: list = field(default_factory=list)  # [{"input": ..., "result": ...}]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


def cost(usage):
    return (
        usage.input_tokens * PRICE_INPUT
        + usage.output_tokens * PRICE_OUTPUT
        + (usage.cache_creation_input_tokens or 0) * PRICE_CACHE_WRITE
        + (usage.cache_read_input_tokens or 0) * PRICE_CACHE_READ
    )


def read_only(conn, fn):
    """Run fn(conn) in a READ ONLY transaction: Postgres rejects any write inside it."""
    try:
        with conn.cursor() as cur:
            cur.execute("SET TRANSACTION READ ONLY")
        return fn(conn)
    finally:
        conn.rollback()


def run_tool(conn, args, first, last):
    """Validate the model's arguments and run one query. Raises ValueError on bad input."""
    metric = args.get("metric")
    if metric not in METRICS:
        raise ValueError(f"metric must be one of {METRICS}")
    try:
        start = max(date.fromisoformat(args["start_date"]), first)
        end = min(date.fromisoformat(args["end_date"]), last)
    except (KeyError, TypeError, ValueError):
        raise ValueError("start_date and end_date must be YYYY-MM-DD")
    if start > end:
        raise ValueError(f"no data in that range; data covers {first} to {last}")
    period = {"start_date": str(start), "end_date": str(end)}

    if metric == "totals":
        return period | read_only(conn, lambda c: db.totals(c, start, end))
    if metric == "top_products":
        limit = args.get("limit", 10)
        if not isinstance(limit, int) or not 1 <= limit <= 20:
            raise ValueError("limit must be an integer from 1 to 20")
        rows = read_only(conn, lambda c: db.top_products(c, start, end, limit))
        return period | {"products": [{"product": a, "units": u} for a, u in rows]}
    if metric == "revenue_by_day":
        rows = read_only(conn, lambda c: db.revenue_by_day(c, start, end))
        return period | {"days": [{"day": str(d), "revenue": round(r)} for d, r in rows]}
    product = (args.get("product") or "").strip()
    if not product:
        raise ValueError("product is required for product_sales")
    rows = read_only(conn, lambda c: db.product_sales(c, start, end, product))
    return period | {"products": [{"product": a, "units": u, "revenue": round(r)} for a, u, r in rows]}


def ask(question, conn, client=None):
    """Answer one question. Each question stands alone (no chat history)."""
    client = client or anthropic.Anthropic()
    first, last = read_only(conn, db.date_range)
    messages = [{
        "role": "user",
        "content": f"[Data covers {first} to {last}. Today is {last}.]\n\n{question}",
    }]
    answer = Answer(text="")

    while True:
        tools_left = MAX_TOOL_CALLS - len(answer.tool_calls)
        response = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            output_config={"effort": EFFORT},
            system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
            tools=[TOOL],
            tool_choice={"type": "auto"} if tools_left > 0 else {"type": "none"},
            messages=messages,
        )
        answer.input_tokens += response.usage.input_tokens
        answer.output_tokens += response.usage.output_tokens
        answer.cost_usd += cost(response.usage)

        if response.stop_reason == "refusal":
            answer.text = "אני לא יכול לענות על השאלה הזו."
            return answer
        if response.stop_reason != "tool_use":
            answer.text = "".join(b.text for b in response.content if b.type == "text").strip()
            return answer

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for block in (b for b in response.content if b.type == "tool_use"):
            try:
                result, is_error = run_tool(conn, block.input, first, last), False
            except ValueError as e:
                result, is_error = {"error": str(e)}, True
            answer.tool_calls.append({"input": block.input, "result": result})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": json.dumps(result, ensure_ascii=False, default=str),
                "is_error": is_error,
            })
        messages.append({"role": "user", "content": results})


def log_run(conn, session_id, question, answer):
    """Save the question to agent_runs and drop runs older than RETENTION_DAYS."""
    with conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO agent_runs (session_id, question, tool_calls, answer, input_tokens, output_tokens, cost_usd) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (session_id, question, Json(answer.tool_calls, dumps=lambda o: json.dumps(o, default=str)),
             answer.text, answer.input_tokens, answer.output_tokens, answer.cost_usd),
        )
        cur.execute(f"DELETE FROM agent_runs WHERE asked_at < now() - interval '{RETENTION_DAYS} days'")

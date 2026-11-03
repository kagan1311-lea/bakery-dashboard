"""Issue #4: the agent loop with the model mocked, the tool, and the log."""

import json
from types import SimpleNamespace as NS

import psycopg2
import pytest

import agent
from test_metrics import END, START, sales  # noqa: F401  (fixture)


def usage(i=100, o=20):
    return NS(input_tokens=i, output_tokens=o, cache_creation_input_tokens=0, cache_read_input_tokens=0)


def tool_use(args, id="t1"):
    return NS(stop_reason="tool_use", usage=usage(),
              content=[NS(type="tool_use", id=id, name="sales_query", input=args)])


def text(t):
    return NS(stop_reason="end_turn", usage=usage(), content=[NS(type="text", text=t)])


class FakeClient:
    """Returns scripted responses and records every request."""

    def __init__(self, *responses):
        self.responses, self.requests = list(responses), []
        self.messages = self

    def create(self, **kwargs):
        self.requests.append(kwargs)
        return self.responses.pop(0)


def test_tool_call_runs_the_query_and_returns_the_answer(sales):
    client = FakeClient(
        tool_use({"metric": "top_products", "start_date": str(START), "end_date": str(END), "limit": 1}),
        text("המוצר הנמכר ביותר הוא לחמנייה."),
    )
    answer = agent.ask("מה נמכר הכי טוב?", sales, client)

    assert answer.text == "המוצר הנמכר ביותר הוא לחמנייה."
    assert answer.tool_calls[0]["result"]["products"] == [{"product": "לחמנייה", "units": 10}]
    sent = client.requests[1]["messages"][-1]["content"][0]
    assert sent["type"] == "tool_result" and not sent["is_error"]
    assert json.loads(sent["content"])["products"][0]["product"] == "לחמנייה"
    assert answer.input_tokens == 200 and answer.output_tokens == 40
    assert answer.cost_usd == pytest.approx(200 * agent.PRICE_INPUT + 40 * agent.PRICE_OUTPUT)


def test_question_says_what_today_is(sales):
    client = FakeClient(text("שלום"))
    agent.ask("מה נמכר הכי טוב בשבוע שעבר?", sales, client)
    assert f"Today is {END}" in client.requests[0]["messages"][0]["content"]


def test_bad_arguments_go_back_as_an_error(sales):
    client = FakeClient(
        tool_use({"metric": "DROP TABLE sales", "start_date": str(START), "end_date": str(END)}),
        text("אין לי את הנתון."),
    )
    answer = agent.ask("?", sales, client)
    sent = client.requests[1]["messages"][-1]["content"][0]
    assert sent["is_error"] and "metric must be one of" in sent["content"]
    assert answer.text == "אין לי את הנתון."


def test_tool_calls_are_capped(sales):
    call = {"metric": "totals", "start_date": str(START), "end_date": str(END)}
    client = FakeClient(*[tool_use(call, id=f"t{i}") for i in range(agent.MAX_TOOL_CALLS)], text("סיימתי"))
    answer = agent.ask("?", sales, client)
    assert len(answer.tool_calls) == agent.MAX_TOOL_CALLS
    assert client.requests[-1]["tool_choice"] == {"type": "none"}
    assert answer.text == "סיימתי"


def test_no_tool_call_for_out_of_scope_question(sales):
    answer = agent.ask("מה מזג האוויר?", sales, FakeClient(text("אני עונה רק על שאלות על המכירות.")))
    assert answer.tool_calls == []


def test_dates_are_clamped_to_the_data(sales):
    result = agent.run_tool(sales, {"metric": "totals", "start_date": "2000-01-01", "end_date": "2099-01-01"}, START, END)
    assert (result["start_date"], result["end_date"]) == (str(START), str(END))
    with pytest.raises(ValueError):
        agent.run_tool(sales, {"metric": "totals", "start_date": "2099-01-01", "end_date": "2099-02-01"}, START, END)


def test_product_sales_matches_part_of_the_name(sales):
    result = agent.run_tool(sales, {"metric": "product_sales", "start_date": str(START), "end_date": str(END),
                                    "product": "בבקה"}, START, END)
    assert result["products"] == [{"product": "בבקה שוקולד", "units": 1, "revenue": 42}]


def test_product_notes_are_in_the_system_prompt(sales):
    client = FakeClient(text("שלום"))
    agent.ask("כמה חלות?", sales, client)
    system = client.requests[0]["system"][0]["text"]
    assert "| לחמים | חלה | חלות |" in system and system.startswith(agent.SYSTEM)


def test_product_sales_adds_a_total_when_several_match(sales):
    result = agent.run_tool(sales, {"metric": "product_sales", "start_date": str(START), "end_date": str(END),
                                    "product": "ח"}, START, END)
    assert [p["product"] for p in result["products"]] == ["לחמנייה", "חלה"]
    assert result["total"] == {"units": 12, "revenue": 76}  # לחמנייה 10 / ₪40 + חלה 2 net / ₪36


def test_tool_queries_cannot_write(sales):
    def delete_everything(conn):
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sales")

    with pytest.raises(psycopg2.errors.ReadOnlySqlTransaction):
        agent.read_only(sales, delete_everything)
    with sales.cursor() as cur:
        cur.execute("SELECT count(*) FROM sales")
        assert cur.fetchone()[0] == 6


def test_log_run_saves_tokens_and_cost(sales):
    answer = agent.Answer(text="לחמנייה", tool_calls=[{"input": {"metric": "totals"}, "result": {}}],
                          input_tokens=120, output_tokens=30, cost_usd=0.00002)
    agent.log_run(sales, "s1", "מה נמכר?", answer)
    with sales.cursor() as cur:
        cur.execute("SELECT session_id, answer, tool_calls, input_tokens, cost_usd FROM agent_runs")
        session_id, text_, calls, tokens, cost = cur.fetchone()
    assert (session_id, text_, tokens, float(cost)) == ("s1", "לחמנייה", 120, 0.00002)
    assert calls[0]["input"]["metric"] == "totals"


def test_cut_answer_is_replaced_by_a_clear_message(sales):
    cut = NS(stop_reason="max_tokens", usage=usage(), content=[NS(type="text", text="בשבוע שעבר נמכרו")])
    answer = agent.ask("?", sales, FakeClient(cut))
    assert answer.text == agent.TOO_LONG


def test_database_error_in_the_tool_goes_back_to_the_model(sales, monkeypatch):
    def broken(*args):
        raise psycopg2.OperationalError("server closed the connection")

    monkeypatch.setattr(agent.db, "totals", broken)
    client = FakeClient(
        tool_use({"metric": "totals", "start_date": str(START), "end_date": str(END)}),
        text("הנתונים לא זמינים כרגע."),
    )
    answer = agent.ask("כמה הכנסות?", sales, client)
    sent = client.requests[1]["messages"][-1]["content"][0]
    assert sent["is_error"] and "database error (OperationalError)" in sent["content"]
    assert answer.text == "הנתונים לא זמינים כרגע."


def test_default_client_has_a_timeout(sales, monkeypatch):
    made = {}

    def fake_anthropic(**kwargs):
        made.update(kwargs)
        return FakeClient(text("שלום"))

    monkeypatch.setattr(agent.anthropic, "Anthropic", fake_anthropic)
    agent.ask("?", sales)
    assert made == {"timeout": agent.TIMEOUT_S, "max_retries": agent.MAX_RETRIES}

"""Issue #5: questions per hour, monthly spend cap, question length."""

import agent
import limits
from test_metrics import run_app, sales  # noqa: F401  (fixture)


def add_runs(conn, n, session_id="s1", cost=0.0, when="now()"):
    with conn, conn.cursor() as cur:
        for _ in range(n):
            cur.execute(
                "INSERT INTO agent_runs (asked_at, session_id, question, tool_calls, answer, input_tokens, "
                f"output_tokens, cost_usd) VALUES ({when}, %s, 'q', '[]', 'a', 0, 0, %s)",
                (session_id, cost),
            )


def test_question_21_in_an_hour_is_refused(sales):
    add_runs(sales, limits.QUESTIONS_PER_HOUR - 1)
    assert limits.blocked(sales, "s1", "q") is None
    add_runs(sales, 1)
    assert limits.blocked(sales, "s1", "q") == limits.TOO_MANY
    assert limits.blocked(sales, "other-session", "q") is None


def test_questions_older_than_an_hour_do_not_count(sales):
    add_runs(sales, limits.QUESTIONS_PER_HOUR, when="now() - interval '61 minutes'")
    assert limits.blocked(sales, "s1", "q") is None


def test_monthly_budget_closes_the_box(sales):
    add_runs(sales, 1, cost=0.999)
    assert limits.blocked(sales, "s1", "q") is None
    add_runs(sales, 1, cost=0.001)
    assert limits.month_spend(sales) == 1.0
    assert limits.blocked(sales, "s1", "q") == limits.OVER_BUDGET


def test_last_months_spend_does_not_count(sales):
    add_runs(sales, 1, cost=5.0, when="now() - interval '40 days'")
    assert limits.month_spend(sales) == 0.0


def test_long_question_is_refused(sales):
    assert limits.blocked(sales, "s1", "א" * (limits.MAX_QUESTION_CHARS + 1)) == limits.TOO_LONG
    assert limits.blocked(sales, "s1", "א" * limits.MAX_QUESTION_CHARS) is None


def page(monkeypatch, url, calls):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("agent.ask", lambda *a, **k: calls.append(a) or agent.Answer(text="לחמנייה"))
    return run_app(monkeypatch, url)


def test_page_over_budget_shows_a_message_and_no_box(sales, schema_url, monkeypatch):
    add_runs(sales, 1, cost=1.0)
    at = page(monkeypatch, schema_url, [])
    assert not at.exception
    assert [i.value for i in at.info] == [limits.OVER_BUDGET]
    assert not at.text_input and len(at.metric) == 3  # the dashboard still works


def test_page_does_not_call_the_model_when_over_the_hourly_limit(sales, schema_url, monkeypatch):
    calls = []
    at = page(monkeypatch, schema_url, calls)
    add_runs(sales, limits.QUESTIONS_PER_HOUR, session_id=at.session_state["session_id"])
    at.text_input[0].input("מה נמכר?")
    at.button[0].click().run()
    assert calls == []
    assert [w.value for w in at.warning] == [limits.TOO_MANY]

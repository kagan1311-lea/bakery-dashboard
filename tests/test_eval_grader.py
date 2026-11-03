"""The eval grader itself: exact checks behave as documented in evals/cases.yaml."""

import sys
from pathlib import Path

import agent

sys.path.insert(0, str(Path(__file__).parent.parent / "evals"))
from run_evals import grade  # noqa: E402

TOOL_CALL = {"input": {"metric": "totals"}, "result": {"revenue": 104798.0, "transactions": 3214}}


def answer(text, calls=(TOOL_CALL,)):
    return agent.Answer(text=text, tool_calls=list(calls))


def test_pass_when_every_check_holds():
    expect = {"tool": True, "metric": "totals", "contains_any": ["3,214"], "no_invented_numbers": True}
    assert grade(expect, answer("בדצמבר היו 3,214 עסקאות והכנסות של ₪104,798 (כ-105 אלף).")) == []


def test_invented_number_fails():
    failed = grade({"no_invented_numbers": True}, answer("היו 3,500 עסקאות ב-7 ימים."))
    assert failed == ["numbers not from a tool: [3500.0]"]


def test_tool_and_text_checks_fail():
    failed = grade({"tool": False, "contains_all": ["לחמנייה"]}, answer("שלום"))
    assert failed == ["tool called=True, expected False", "'לחמנייה' missing from answer"]


def test_refusal_without_tool_passes():
    assert grade({"tool": False, "contains_any": ["לא יכול"]}, answer("אני לא יכול למחוק נתונים.", calls=())) == []

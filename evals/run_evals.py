"""Run evals/cases.yaml against the real model and the real data, print the score, save it.

Costs real money (claude-haiku-5-5, well under a cent per run). Answers are not logged to
agent_runs, so evals don't count toward the app's spend cap.

Usage: python evals/run_evals.py [--runs N] [--only CASE_ID]
Needs DATABASE_URL and ANTHROPIC_API_KEY in .env.
"""

import argparse
import csv
import json
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import agent  # noqa: E402
import db  # noqa: E402

HERE = Path(__file__).parent
NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")


def numbers(text):
    return [float(n.replace(",", "")) for n in NUMBER.findall(text)]


def invented_numbers(answer):
    """Numbers >= 32 (years excluded) in the answer that no tool result contains (within 1%, or in thousands)."""
    seen = numbers(json.dumps([c["result"] for c in answer.tool_calls], ensure_ascii=False, default=str))
    return [n for n in numbers(answer.text)
            if n >= 32 and not 2000 <= n <= 2100 and not any(abs(n - s) <= 0.01 * s or round(n) == round(s / 1000) for s in seen)]


def grade(expect, answer):
    """List of failed checks (empty = pass)."""
    failed = []
    called = bool(answer.tool_calls)
    if "tool" in expect and called != expect["tool"]:
        failed.append(f"tool called={called}, expected {expect['tool']}")
    used = [c["input"].get("metric") for c in answer.tool_calls]
    if "metric" in expect and expect["metric"] not in used:
        failed.append(f"metric {expect['metric']} not used")
    if "metric_any" in expect and not set(expect["metric_any"]) & set(used):
        failed.append(f"none of metrics {expect['metric_any']} used")
    if "contains_any" in expect and not any(s in answer.text for s in expect["contains_any"]):
        failed.append(f"none of {expect['contains_any']} in answer")
    for s in expect.get("contains_all", []):
        if s not in answer.text:
            failed.append(f"{s!r} missing from answer")
    if found := [s for s in expect.get("contains_none", []) if s in answer.text]:
        failed.append(f"forbidden words in answer: {found}")
    if expect.get("no_invented_numbers") and (bad := invented_numbers(answer)):
        failed.append(f"numbers not from a tool: {bad}")
    return failed


def git_commit():
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return ""


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=1, help="runs per case")
    parser.add_argument("--only", help="run one case id")
    args = parser.parse_args()

    load_dotenv(".env")
    cases = yaml.safe_load((HERE / "cases.yaml").read_text(encoding="utf-8"))
    if args.only:
        cases = [c for c in cases if c["id"] == args.only]

    conn = db.connect()
    passed = total = tokens_in = tokens_out = 0
    cost = 0.0
    for case in cases:
        for _ in range(args.runs):
            answer = agent.ask(case["question"], conn)
            failed = grade(case["expect"], answer)
            total += 1
            passed += not failed
            tokens_in += answer.input_tokens
            tokens_out += answer.output_tokens
            cost += answer.cost_usd
            print(f"{'PASS' if not failed else 'FAIL'}  {case['id']}")
            for f in failed:
                print(f"      - {f}")
            if failed:
                print(f"      answer: {answer.text!r}")
    conn.close()

    rate = passed / total if total else 0
    print(f"\n{passed}/{total} passed ({rate:.0%}) · {tokens_in + tokens_out:,} tokens "
          f"({tokens_in:,} in, {tokens_out:,} out) · ${cost:.4f}")

    if not args.only:
        history = HERE / "history.csv"
        new = not history.exists()
        with open(history, "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["run_at", "commit", "model", "effort", "cases", "runs", "passed", "pass_rate",
                            "input_tokens", "output_tokens", "cost_usd"])
            w.writerow([datetime.now().isoformat(timespec="seconds"), git_commit(), agent.MODEL, agent.EFFORT,
                        len(cases), args.runs, passed, f"{rate:.2f}", tokens_in, tokens_out, f"{cost:.5f}"])


if __name__ == "__main__":
    main()

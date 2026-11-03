"""Usage limits for the ask box (spec.md §6). Checked before the model is called.

The app's own cap sits under the hard stop on the Anthropic workspace (architecture.md → Limits).
Evals don't write to agent_runs, so they don't count here.
"""

QUESTIONS_PER_HOUR = 20  # per browser session (no login: the session is the "user")
MONTHLY_BUDGET_USD = 1.00
MAX_QUESTION_CHARS = 500
TIMEZONE = "Asia/Jerusalem"

OVER_BUDGET = "העוזר נח עד תחילת החודש הבא (הגענו לתקציב החודשי). הדשבורד ממשיך לעבוד כרגיל."
TOO_MANY = f"הגעתם ל-{QUESTIONS_PER_HOUR} שאלות בשעה האחרונה. נסו שוב מאוחר יותר."
TOO_LONG = f"השאלה ארוכה מדי (עד {MAX_QUESTION_CHARS} תווים). נסו לקצר."


def _one(conn, sql, params=()):
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchone()[0]


def month_spend(conn):
    """USD spent on the ask box since the 1st of this month (Asia/Jerusalem)."""
    return float(_one(conn, f"""
        SELECT coalesce(sum(cost_usd), 0) FROM agent_runs
        WHERE asked_at >= date_trunc('month', now() AT TIME ZONE '{TIMEZONE}') AT TIME ZONE '{TIMEZONE}'
    """))


def questions_last_hour(conn, session_id):
    return _one(conn, """
        SELECT count(*) FROM agent_runs
        WHERE session_id = %s AND asked_at > now() - interval '1 hour'
    """, (session_id,))


def over_budget(conn):
    return month_spend(conn) >= MONTHLY_BUDGET_USD


def blocked(conn, session_id, question):
    """The message to show instead of asking the model, or None if the question may go ahead."""
    if len(question) > MAX_QUESTION_CHARS:
        return TOO_LONG
    if over_budget(conn):
        return OVER_BUDGET
    if questions_last_hour(conn, session_id) >= QUESTIONS_PER_HOUR:
        return TOO_MANY
    return None

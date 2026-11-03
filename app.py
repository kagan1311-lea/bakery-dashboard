"""Bakery sales dashboard: three cards, revenue per day, top 10 products, and an ask box.

Run: streamlit run app.py   (needs DATABASE_URL and ANTHROPIC_API_KEY, see .env.example)
"""

import base64
import os
import uuid
from pathlib import Path

import altair as alt
import anthropic
import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

import agent
import db

load_dotenv(".env")
st.set_page_config(page_title="מכירות מאפיית הכיכר", page_icon="🥐", layout="wide")
BACKGROUND = base64.b64encode((Path(__file__).parent / "assets" / "bakery-bg.jpg").read_bytes()).decode()
st.markdown(
    f"""<style>
    .stApp, [data-testid='stMetric'] {{ direction: rtl; text-align: right; }}
    .stApp {{
        background: linear-gradient(rgba(255, 252, 247, 0.82), rgba(255, 252, 247, 0.82)),
                    url("data:image/jpeg;base64,{BACKGROUND}") center / cover fixed;
    }}
    [data-testid='stHeader'] {{ background: transparent; }}
    .block-container {{ padding-top: 2.5rem; }}
    @media (max-width: 640px) {{
        .block-container {{ padding: 2rem 1rem 1rem; }}
        h1 {{ font-size: 1.8rem !important; }}
    }}
    [data-testid='stMetric'], [data-testid='stForm'], [data-testid='stVegaLiteChart'] {{
        background: rgba(255, 255, 255, 0.85); border-radius: 12px; padding: 12px 16px;
    }}
    </style>""",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600, show_spinner=False)
def data_range():
    conn = db.connect()
    try:
        return db.date_range(conn)
    finally:
        conn.close()


@st.cache_data(ttl=600, show_spinner="טוען נתונים…")
def load(start, end):
    conn = db.connect()
    try:
        return {
            "totals": db.totals(conn, start, end),
            "by_day": db.revenue_by_day(conn, start, end),
            "top": db.top_products(conn, start, end),
        }
    finally:
        conn.close()


st.title("מכירות מאפיית הכיכר")

try:
    first, last = data_range()
    if first is None:
        st.info("אין עדיין נתוני מכירות. הריצו את load_data.py.")
        st.stop()
    picked = st.date_input(
        "טווח תאריכים", value=(first, last), min_value=first, max_value=last, format="DD/MM/YYYY"
    )
    start, end = (picked[0], picked[-1]) if picked else (first, last)  # one date picked = one day
    data = load(start, end)
except (psycopg2.Error, KeyError) as e:
    st.error(f"אין חיבור למסד הנתונים. נסו שוב בעוד דקה. ({type(e).__name__})")
    st.stop()

totals = data["totals"]
c1, c2, c3 = st.columns(3)
c1.metric("סך ההכנסות", f"₪{totals['revenue']:,.0f}")
c2.metric("מספר עסקאות", f"{totals['transactions']:,}")
c3.metric("המוצר הנמכר ביותר", totals["best_seller"] or "—")

st.subheader("הכנסות לפי יום")
by_day = pd.DataFrame(data["by_day"], columns=["יום", "הכנסות"])
st.altair_chart(
    alt.Chart(by_day).mark_line().encode(
        x=alt.X("יום:T", title=None),
        y=alt.Y("הכנסות:Q", title="₪"),
        tooltip=[alt.Tooltip("יום:T", format="%d/%m/%Y"), alt.Tooltip("הכנסות:Q", format=",.0f")],
    ),
    use_container_width=True,
)

st.subheader("10 המוצרים המובילים (יחידות)")
top = pd.DataFrame(data["top"], columns=["מוצר", "יחידות"])
st.altair_chart(
    alt.Chart(top).mark_bar().encode(
        x=alt.X("יחידות:Q", title=None),
        y=alt.Y("מוצר:N", sort="-x", title=None),
        tooltip=["מוצר", alt.Tooltip("יחידות:Q", format=",")],
    ),
    use_container_width=True,
)

st.subheader("💬 שאלו על המכירות")
if not os.environ.get("ANTHROPIC_API_KEY"):
    st.info("תיבת השאלות לא מוגדרת (חסר ANTHROPIC_API_KEY).")
    st.stop()

session_id = st.session_state.setdefault("session_id", uuid.uuid4().hex)
with st.form("ask"):
    question = st.text_input("שאלה", placeholder="למשל: מה נמכר הכי טוב בשבוע שעבר?", max_chars=500)
    asked = st.form_submit_button("אישור")

if asked and question.strip():
    with st.spinner("בודק בנתונים…"):
        conn = db.connect()
        try:
            answer = agent.ask(question.strip(), conn)
            agent.log_run(conn, session_id, question.strip(), answer)
        except anthropic.APIError as e:
            answer = None
            st.error(f"העוזר לא זמין כרגע. נסו שוב בעוד דקה. ({type(e).__name__})")
        finally:
            conn.close()
    if answer:
        st.session_state["last_answer"] = answer

if last := st.session_state.get("last_answer"):
    st.markdown(last.text or "לא התקבלה תשובה.")

st.caption("תמונת רקע: Tabitha Turner, Unsplash")

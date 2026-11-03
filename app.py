"""Bakery sales dashboard: three cards, revenue per day, top 10 products.

Run: streamlit run app.py   (needs DATABASE_URL, see .env.example)
"""

import altair as alt
import pandas as pd
import psycopg2
import streamlit as st
from dotenv import load_dotenv

import db

load_dotenv(".env")
st.set_page_config(page_title="מכירות המאפייה", page_icon="🥐", layout="wide")
st.markdown(
    "<style>.stApp, [data-testid='stMetric'] { direction: rtl; text-align: right; }</style>",
    unsafe_allow_html=True,
)


@st.cache_data(ttl=600, show_spinner="טוען נתונים…")
def load():
    conn = db.connect()
    try:
        start, end = db.date_range(conn)
        return {
            "start": start,
            "end": end,
            "totals": db.totals(conn, start, end),
            "by_day": db.revenue_by_day(conn, start, end),
            "top": db.top_products(conn, start, end),
        }
    finally:
        conn.close()


st.title("🥐 מכירות המאפייה")

try:
    data = load()
except (psycopg2.Error, KeyError) as e:
    st.error(f"אין חיבור למסד הנתונים. נסו שוב בעוד דקה. ({type(e).__name__})")
    st.stop()

if data["start"] is None:
    st.info("אין עדיין נתוני מכירות. הריצו את load_data.py.")
    st.stop()

st.caption(f"{data['start']:%d/%m/%Y} – {data['end']:%d/%m/%Y}")

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

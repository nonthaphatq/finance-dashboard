# -*- coding: utf-8 -*-
"""
app.py  —  Finance Dashboard v1 (Streamlit)

Run:
    .venv\Scripts\streamlit.exe run app.py

Security:
    - Runs on localhost only. Do NOT share the URL or deploy online.
    - DB opened read-only (uri=True with ?mode=ro).
    - No data is written back to the database.
"""

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.express as px
import streamlit as st
from streamlit_autorefresh import st_autorefresh

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
DB_PATH       = Path(__file__).parent / "finance.db"
TZ_THAI       = ZoneInfo("Asia/Bangkok")
CACHE_TTL_SEC = 60          # รีเฟรช cache ทุก 60 วินาที
AUTO_REFRESH_MS = 2 * 60 * 1000   # รีโหลดหน้าทุก 2 นาที
STALE_HOURS   = 1           # ขึ้นเตือนแดงถ้าไม่ซิงก์นานกว่านี้

st.set_page_config(
    page_title="Finance Dashboard",
    page_icon="💰",
    layout="wide",
)

# Auto-refresh ทุก 2 นาที (นับใน browser)
refresh_count = st_autorefresh(interval=AUTO_REFRESH_MS, key="auto_refresh")

# ---------------------------------------------------------------------------
# Data loading (read-only connection)
# ---------------------------------------------------------------------------

@st.cache_data(ttl=CACHE_TTL_SEC)
def load_data():
    """Load all tables from SQLite (read-only). Returns dict of DataFrames."""
    uri = DB_PATH.as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row

    txn_rows = conn.execute(
        "SELECT * FROM transactions ORDER BY txn_at ASC"
    ).fetchall()

    if txn_rows:
        df = pd.DataFrame([dict(r) for r in txn_rows])
        df["amount"]    = df["amount_satang"]    / 100
        df["fee"]       = df["fee_satang"]       / 100
        df["balance"]   = df["available_balance_satang"] / 100
        df["total_out"] = df["amount"] + df["fee"]
        df["txn_at"] = pd.to_datetime(df["txn_at"], utc=True).dt.tz_convert(TZ_THAI)
        df["month"]  = df["txn_at"].dt.to_period("M").astype(str)
    else:
        df = pd.DataFrame()

    err_count = conn.execute("SELECT COUNT(*) FROM parse_errors").fetchone()[0]

    sync_row = conn.execute(
        "SELECT last_synced_at FROM sync_state WHERE id=1"
    ).fetchone()
    last_sync = None
    if sync_row and sync_row[0]:
        try:
            last_sync = datetime.fromisoformat(sync_row[0]).astimezone(TZ_THAI)
        except Exception:
            last_sync = None

    conn.close()
    return df, err_count, last_sync


def fmt_thb(amount: float) -> str:
    return f"฿{amount:,.2f}"


def time_ago(dt: datetime) -> str:
    if dt is None:
        return "ไม่มีข้อมูล"
    now  = datetime.now(tz=TZ_THAI)
    diff = now - dt
    if diff < timedelta(minutes=1):
        return "เมื่อกี้"
    if diff < timedelta(hours=1):
        return f"{int(diff.seconds / 60)} นาทีที่แล้ว"
    if diff < timedelta(days=1):
        h = int(diff.seconds / 3600)
        return f"{h} ชั่วโมงที่แล้ว"
    return f"{diff.days} วันที่แล้ว"


def is_stale(dt: datetime) -> bool:
    if dt is None:
        return True
    return (datetime.now(tz=TZ_THAI) - dt) > timedelta(hours=STALE_HOURS)


# ---------------------------------------------------------------------------
# Load data
# ---------------------------------------------------------------------------
df, parse_error_count, last_sync = load_data()
now_thai  = datetime.now(tz=TZ_THAI)
stale     = is_stale(last_sync)

# ---------------------------------------------------------------------------
# ── Sync Status Banner (top of page) ─────────────────────────────────────
# ---------------------------------------------------------------------------
st.title("💰 Finance Dashboard")

# แถบสีแดง/เขียวตามสถานะ
if stale:
    sync_label = last_sync.strftime("%d/%m/%Y %H:%M") if last_sync else "ไม่เคยซิงก์"
    st.error(
        f"⚠️ ข้อมูลอาจล้าสมัย — ซิงก์ล่าสุด: **{sync_label}** ({time_ago(last_sync)})  "
        f"รัน `fetch_emails.py` หรือรอ Task Scheduler อีกรอบ",
        icon=None,
    )
else:
    sync_label = last_sync.strftime("%d/%m/%Y %H:%M")
    st.success(
        f"✅ ซิงก์ล่าสุด: **{sync_label}** ({time_ago(last_sync)}) — "
        f"หน้านี้รีเฟรชอัตโนมัติทุก 2 นาที",
        icon=None,
    )

# แถบสุขภาพข้อมูล
col_err, col_warn = st.columns([1, 3])
with col_err:
    err_color = "🔴" if parse_error_count > 0 else "🟢"
    st.metric(
        f"{err_color} Parse Errors",
        parse_error_count,
        help="อีเมลที่ระบบแกะไม่ได้ อาจมีรายการขาดหาย",
    )
with col_warn:
    st.info(
        "⚠️ ตัวเลขนี้แสดงเฉพาะรายการที่ระบบอ่านจากอีเมลได้เท่านั้น "
        "อาจต่ำกว่าความเป็นจริงถ้ามีอีเมลประเภทที่ยังไม่รองรับ",
    )

st.divider()

# ---------------------------------------------------------------------------
# Empty state
# ---------------------------------------------------------------------------
if df.empty:
    st.warning(
        "ยังไม่มีข้อมูลรายการ — รัน `fetch_emails.py` เพื่อดึงข้อมูลจาก Gmail ก่อน",
        icon="📭",
    )
    st.stop()

# ---------------------------------------------------------------------------
# ── KPI Cards ────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
this_month = now_thai.strftime("%Y-%m")
df_month   = df[df["month"] == this_month]

latest_balance = (
    df.sort_values("txn_at")
      .groupby("account_last4")
      .last()["balance"]
      .sum()
)
income_month  = df_month[df_month["direction"] == "in"]["amount"].sum()
expense_month = df_month[df_month["direction"] == "out"]["total_out"].sum()
net_month     = income_month - expense_month

st.subheader("📊 สรุปเดือนนี้")
kc1, kc2, kc3, kc4 = st.columns(4)
with kc1:
    st.metric(
        "ยอดถอนได้ล่าสุด (บัญชีนี้)",
        fmt_thb(latest_balance),
        help="available_balance จากรายการล่าสุด — ไม่ใช่ net worth รวม",
    )
with kc2:
    st.metric("💚 เงินเข้าเดือนนี้",  fmt_thb(income_month))
with kc3:
    st.metric("🔴 เงินออกเดือนนี้",  fmt_thb(expense_month))
with kc4:
    st.metric("💙 สุทธิเดือนนี้",    fmt_thb(net_month))

st.divider()

# ---------------------------------------------------------------------------
# ── Charts ───────────────────────────────────────────────────────────────
# ---------------------------------------------------------------------------
st.subheader("📈 กราฟ")
chart_col1, chart_col2 = st.columns(2)

with chart_col1:
    st.markdown("**กระแสเงินสดรายเดือน**")
    monthly_out = (
        df[df["direction"] == "out"]
        .groupby("month")["total_out"].sum()
        .reset_index()
        .rename(columns={"total_out": "baht"})
    )
    monthly_out["label"] = "เงินออก (รวมค่าธรรมเนียม)"

    monthly_in = (
        df[df["direction"] == "in"]
        .groupby("month")["amount"].sum()
        .reset_index()
        .rename(columns={"amount": "baht"})
    )
    monthly_in["label"] = "เงินเข้า"

    monthly_df = pd.concat([monthly_in, monthly_out], ignore_index=True)

    if monthly_df.empty or monthly_df["baht"].sum() == 0:
        st.info("ยังไม่มีข้อมูลเพียงพอ")
    else:
        fig = px.bar(
            monthly_df, x="month", y="baht", color="label", barmode="group",
            color_discrete_map={
                "เงินเข้า": "#22c55e",
                "เงินออก (รวมค่าธรรมเนียม)": "#ef4444",
            },
            labels={"month": "เดือน", "baht": "จำนวนเงิน (บาท)", "label": ""},
        )
        fig.update_layout(margin=dict(t=20))
        st.plotly_chart(fig, use_container_width=True)

with chart_col2:
    st.markdown("**ยอดถอนได้ตามเวลา**")
    df_bal = df[df["balance"].notna()].copy()
    if df_bal.empty:
        st.info("ยังไม่มีข้อมูลยอดคงเหลือ")
    else:
        fig2 = px.line(
            df_bal, x="txn_at", y="balance", color="account_last4", markers=True,
            labels={
                "txn_at": "วันที่-เวลา",
                "balance": "ยอดถอนได้ (บาท)",
                "account_last4": "บัญชี (...xxxx)",
            },
            color_discrete_sequence=px.colors.qualitative.Set2,
        )
        fig2.update_layout(legend_title_text="บัญชี", margin=dict(t=20))
        st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ---------------------------------------------------------------------------
# ── Transaction Table + Filters ──────────────────────────────────────────
# ---------------------------------------------------------------------------
st.subheader("📋 รายการทั้งหมด")

with st.sidebar:
    st.header("🔍 ตัวกรอง")

    min_date = df["txn_at"].min().date()
    max_date = df["txn_at"].max().date()
    date_range = st.date_input(
        "ช่วงวันที่", value=(min_date, max_date),
        min_value=min_date, max_value=max_date,
    )

    directions = ["ทั้งหมด"] + sorted(df["direction"].unique().tolist())
    sel_dir    = st.selectbox("ทิศทาง", directions)

    types      = ["ทั้งหมด"] + sorted(df["type"].dropna().unique().tolist())
    sel_type   = st.selectbox("ประเภทรายการ", types)

    search_name = st.text_input("🔎 ค้นหาชื่อผู้รับ/โอน")
    hide_names  = st.toggle("🙈 ซ่อนชื่อผู้รับเงิน", value=False)

    st.divider()
    st.caption(f"รีเฟรชอัตโนมัติทุก 2 นาที  (รอบที่ {refresh_count})")
    if st.button("🔄 รีเฟรชทันที"):
        st.cache_data.clear()
        st.rerun()

# Apply filters
df_view = df.copy()
if len(date_range) == 2:
    from datetime import datetime as dt_cls
    s = dt_cls(date_range[0].year, date_range[0].month, date_range[0].day, tzinfo=TZ_THAI)
    e = dt_cls(date_range[1].year, date_range[1].month, date_range[1].day, 23, 59, 59, tzinfo=TZ_THAI)
    df_view = df_view[(df_view["txn_at"] >= s) & (df_view["txn_at"] <= e)]
if sel_dir != "ทั้งหมด":
    df_view = df_view[df_view["direction"] == sel_dir]
if sel_type != "ทั้งหมด":
    df_view = df_view[df_view["type"] == sel_type]
if search_name:
    df_view = df_view[
        df_view["counterparty"].fillna("").str.contains(search_name, case=False)
    ]

# Build display table
df_disp = df_view[[
    "txn_at", "direction", "type",
    "amount", "fee", "total_out", "balance",
    "account_last4", "counterparty", "ref_no",
]].copy()
df_disp["txn_at"]    = df_disp["txn_at"].dt.strftime("%d/%m/%Y %H:%M")
df_disp["direction"] = df_disp["direction"].map({"in": "เข้า 💚", "out": "ออก 🔴"})
if hide_names:
    df_disp["counterparty"] = df_disp["counterparty"].apply(
        lambda x: "***" if pd.notna(x) and str(x).strip() else x
    )
for col in ["amount", "fee", "total_out", "balance"]:
    df_disp[col] = df_disp[col].apply(lambda x: f"{x:,.2f}" if pd.notna(x) else "-")

df_disp.columns = [
    "วันที่-เวลา", "ทิศทาง", "ประเภท",
    "จำนวนเงิน (฿)", "ค่าธรรมเนียม (฿)", "รวมจ่าย (฿)", "ยอดถอนได้ (฿)",
    "บัญชี", "ผู้รับ/โอน", "เลขที่รายการ",
]

st.markdown(f"แสดง **{len(df_view)}** รายการ")
st.dataframe(df_disp, use_container_width=True, hide_index=True)

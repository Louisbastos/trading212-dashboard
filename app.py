import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import os
from dotenv import load_dotenv
from datetime import datetime

from t212_client import T212Client
from price_data import get_price_history, get_indicators, to_yahoo_ticker

load_dotenv()

st.set_page_config(page_title="T212 Dashboard", page_icon="📈", layout="wide")

# Support both local .env and Streamlit Cloud secrets
def _default_api_key() -> str:
    try:
        return st.secrets.get("T212_API_KEY", "") or os.getenv("T212_API_KEY", "")
    except Exception:
        return os.getenv("T212_API_KEY", "")

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.title("📈 T212 Dashboard")
    api_key = st.text_input(
        "API Key",
        value=_default_api_key(),
        type="password",
        help="Trading212 → Settings → API → Generate key",
    )
    account_type = st.radio("Account", ["Live", "Demo"], horizontal=True)
    period = st.selectbox("Chart period", ["1 month", "3 months", "6 months", "1 year"], index=3)
    period_days = {"1 month": 30, "3 months": 90, "6 months": 180, "1 year": 365}[period]

    if st.button("🔄 Refresh", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    st.divider()
    st.caption(f"Updated: {datetime.now().strftime('%H:%M:%S')}")

if not api_key:
    st.info("### Enter your Trading212 API key in the sidebar to start.")
    st.markdown("""
**How to get your API key:**
1. Open Trading212 (web or app)
2. Go to **Settings → API**
3. Generate a key and paste it in the sidebar

You can also set `T212_API_KEY=your_key` in a `.env` file in this folder.
    """)
    st.stop()


# ── Data loading ──────────────────────────────────────────────────────────────
@st.cache_data(ttl=300, show_spinner="Fetching portfolio…")
def load_data(key: str, demo: bool):
    client = T212Client(key, demo=demo)
    portfolio = client.get_portfolio()
    cash = client.get_cash()
    return portfolio, cash


is_demo = account_type == "Demo"
try:
    portfolio_raw, cash = load_data(api_key, is_demo)
except Exception as e:
    st.error(f"API error: {e}")
    if "401" in str(e) or "403" in str(e):
        st.warning("Check your API key — it may be invalid or for the wrong account type (Live vs Demo).")
    st.stop()

if not portfolio_raw:
    st.warning("No open positions found.")
    st.stop()

# ── Build main dataframe ───────────────────────────────────────────────────────
df = pd.DataFrame(portfolio_raw)
df["currentValue"] = df["currentPrice"] * df["quantity"]
df["invested"] = df["averagePrice"] * df["quantity"]
df["ppl"] = df["currentValue"] - df["invested"]
df["ppl_pct"] = (df["ppl"] / df["invested"] * 100).round(2)

total_invested = df["invested"].sum()
total_value = df["currentValue"].sum() + cash.get("free", 0)
total_ppl = df["ppl"].sum()
total_ppl_pct = total_ppl / total_invested * 100 if total_invested else 0
currency = cash.get("currencyCode", "GBP")

tickers = tuple(df["ticker"].tolist())

# ── Indicators ────────────────────────────────────────────────────────────────
with st.spinner("Loading indicators…"):
    indicators = get_indicators(tickers)

df = df.set_index("ticker").join(indicators, how="left").reset_index()


# ── Header metrics ────────────────────────────────────────────────────────────
st.subheader(f"Portfolio — {account_type} account")
c1, c2, c3, c4 = st.columns(4)
c1.metric("Total Value", f"{currency} {total_value:,.2f}")
c2.metric("Invested", f"{currency} {total_invested:,.2f}")
ppl_sign = "+" if total_ppl >= 0 else ""
c3.metric("Total P&L", f"{currency} {ppl_sign}{total_ppl:,.2f}", f"{ppl_sign}{total_ppl_pct:.2f}%")
c4.metric("Cash Available", f"{currency} {cash.get('free', 0):,.2f}")

st.divider()


# ── Tabs ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Overview", "📈 Stock Charts", "🔎 Indicators"])


# ── Tab 1: Overview ───────────────────────────────────────────────────────────
with tab1:
    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        st.markdown("**Portfolio allocation**")
        fig_pie = px.pie(
            df, names="ticker", values="currentValue",
            hole=0.4, color_discrete_sequence=px.colors.qualitative.Bold
        )
        fig_pie.update_traces(textposition="inside", textinfo="percent+label")
        fig_pie.update_layout(showlegend=False, margin=dict(t=10, b=10, l=10, r=10))
        st.plotly_chart(fig_pie, use_container_width=True)

    with col_chart:
        st.markdown("**P&L by holding**")
        df_sorted = df.sort_values("ppl")
        colors = ["#ef4444" if v < 0 else "#22c55e" for v in df_sorted["ppl"]]
        fig_bar = go.Figure(go.Bar(
            x=df_sorted["ticker"], y=df_sorted["ppl"],
            marker_color=colors,
            text=[f"{'+' if v >= 0 else ''}{v:.0f}" for v in df_sorted["ppl"]],
            textposition="outside",
        ))
        fig_bar.update_layout(
            yaxis_title=f"P&L ({currency})", xaxis_title="",
            margin=dict(t=10, b=10), height=300
        )
        st.plotly_chart(fig_bar, use_container_width=True)

    st.markdown("**Holdings**")
    display_cols = ["ticker", "quantity", "averagePrice", "currentPrice", "currentValue", "ppl", "ppl_pct", "daily_chg"]
    display_cols = [c for c in display_cols if c in df.columns]
    styled = df[display_cols].copy()
    styled.columns = ["Ticker", "Qty", "Avg Price", "Current", "Value", "P&L", "P&L %", "Day %"][: len(display_cols)]

    def color_num(val):
        if pd.isna(val):
            return ""
        return "color: #22c55e" if val > 0 else ("color: #ef4444" if val < 0 else "")

    pct_cols = [c for c in ["P&L %", "Day %"] if c in styled.columns]
    st.dataframe(
        styled.style.applymap(color_num, subset=["P&L", "P&L %"] + (["Day %"] if "Day %" in styled.columns else []))
               .format({
                   "Qty": "{:.4f}",
                   "Avg Price": "{:.2f}",
                   "Current": "{:.2f}",
                   "Value": "{:,.2f}",
                   "P&L": "{:+.2f}",
                   "P&L %": "{:+.2f}%",
                   **({"Day %": "{:+.2f}%"} if "Day %" in styled.columns else {}),
               }),
        use_container_width=True,
        hide_index=True,
    )


# ── Tab 2: Stock charts ───────────────────────────────────────────────────────
with tab2:
    selected = st.selectbox("Select holding", df["ticker"].tolist())
    row = df[df["ticker"] == selected].iloc[0]

    with st.spinner(f"Loading price history for {selected}…"):
        hist_data = get_price_history((selected,), period_days)

    if selected in hist_data:
        hist = hist_data[selected]
        avg_price = row["averagePrice"]

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=hist.index, y=hist["Close"],
            mode="lines", name="Price",
            line=dict(color="#6366f1", width=2),
            fill="tozeroy", fillcolor="rgba(99,102,241,0.08)"
        ))
        fig.add_hline(
            y=avg_price, line_dash="dash", line_color="#f59e0b",
            annotation_text=f"Avg buy {avg_price:.2f}",
            annotation_position="bottom right"
        )

        # 20-day SMA
        sma = hist["Close"].rolling(20).mean()
        fig.add_trace(go.Scatter(
            x=hist.index, y=sma, mode="lines", name="SMA 20",
            line=dict(color="#94a3b8", width=1, dash="dot")
        ))

        fig.update_layout(
            title=f"{selected} — {period} price history",
            yaxis_title="Price", xaxis_title="",
            legend=dict(orientation="h", y=1.02),
            margin=dict(t=40, b=20),
            height=400,
        )
        st.plotly_chart(fig, use_container_width=True)

        m1, m2, m3 = st.columns(3)
        daily = row.get("daily_chg")
        rsi = row.get("rsi")
        vs_sma = row.get("vs_sma20")
        m1.metric("Day change", f"{daily:+.2f}%" if daily is not None else "N/A")
        m2.metric("RSI (14)", f"{rsi:.1f}" if rsi is not None else "N/A",
                  "Overbought >70" if rsi and rsi > 70 else ("Oversold <30" if rsi and rsi < 30 else "Neutral"))
        m3.metric("vs SMA 20", f"{vs_sma:+.2f}%" if vs_sma is not None else "N/A")
    else:
        yahoo = to_yahoo_ticker(selected)
        st.warning(f"Could not fetch price history for **{selected}** (tried Yahoo ticker `{yahoo}`). "
                   f"You may need to adjust the ticker mapping in `price_data.py`.")


# ── Tab 3: Indicators ─────────────────────────────────────────────────────────
with tab3:
    st.markdown("**Signal overview** — rising/falling indicators across all holdings")

    def trend_badge(daily_chg, vs_sma20, rsi):
        if daily_chg is None:
            return "⚪ N/A"
        if daily_chg > 1 and (vs_sma20 or 0) > 0:
            return "🟢 Rising"
        if daily_chg < -1 and (vs_sma20 or 0) < 0:
            return "🔴 Falling"
        if daily_chg > 0:
            return "🟡 Edging up"
        return "🟠 Edging down"

    def rsi_label(rsi):
        if rsi is None:
            return "–"
        if rsi > 70:
            return f"⚠️ {rsi:.0f} Overbought"
        if rsi < 30:
            return f"⚠️ {rsi:.0f} Oversold"
        return f"✅ {rsi:.0f} Neutral"

    rows = []
    for _, row in df.iterrows():
        rows.append({
            "Ticker": row["ticker"],
            "Trend": trend_badge(row.get("daily_chg"), row.get("vs_sma20"), row.get("rsi")),
            "Day %": f"{row['daily_chg']:+.2f}%" if row.get("daily_chg") is not None else "–",
            "7d %": f"{row['chg_7d']:+.2f}%" if row.get("chg_7d") is not None else "–",
            "30d %": f"{row['chg_30d']:+.2f}%" if row.get("chg_30d") is not None else "–",
            "RSI (14)": rsi_label(row.get("rsi")),
            "vs SMA 20": f"{row['vs_sma20']:+.2f}%" if row.get("vs_sma20") is not None else "–",
            "P&L %": f"{row['ppl_pct']:+.2f}%",
        })

    ind_df = pd.DataFrame(rows)
    st.dataframe(ind_df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**RSI chart — all holdings**")
    rsi_data = df[df["rsi"].notna()][["ticker", "rsi"]].sort_values("rsi")
    if not rsi_data.empty:
        rsi_colors = [
            "#ef4444" if v > 70 else ("#3b82f6" if v < 30 else "#22c55e")
            for v in rsi_data["rsi"]
        ]
        fig_rsi = go.Figure(go.Bar(
            x=rsi_data["ticker"], y=rsi_data["rsi"],
            marker_color=rsi_colors,
            text=[f"{v:.0f}" for v in rsi_data["rsi"]],
            textposition="outside",
        ))
        fig_rsi.add_hline(y=70, line_dash="dash", line_color="#ef4444", annotation_text="Overbought 70")
        fig_rsi.add_hline(y=30, line_dash="dash", line_color="#3b82f6", annotation_text="Oversold 30")
        fig_rsi.update_layout(yaxis_range=[0, 100], height=300, margin=dict(t=10, b=10))
        st.plotly_chart(fig_rsi, use_container_width=True)

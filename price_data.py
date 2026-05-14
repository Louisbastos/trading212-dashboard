from __future__ import annotations
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import streamlit as st

# T212 often uses format like "AAPL_US_EQ" — strip the suffix to get Yahoo ticker
def to_yahoo_ticker(t212_ticker: str) -> str:
    parts = t212_ticker.split("_")
    base = parts[0]
    if len(parts) >= 2:
        exchange = parts[1]
        if exchange in ("LSE", "LON", "GB"):
            return base + ".L"
        if exchange in ("ETR", "DE"):
            return base + ".DE"
        if exchange in ("EPA", "FR"):
            return base + ".PA"
        if exchange in ("AMS", "NL"):
            return base + ".AS"
    return base


@st.cache_data(ttl=300, show_spinner=False)
def get_price_history(tickers: tuple[str], period_days: int = 365) -> dict[str, pd.DataFrame]:
    result = {}
    for t212_ticker in tickers:
        yahoo = to_yahoo_ticker(t212_ticker)
        try:
            hist = yf.Ticker(yahoo).history(period=f"{period_days}d")
            if hist.empty and not yahoo.endswith(".L"):
                hist = yf.Ticker(yahoo + ".L").history(period=f"{period_days}d")
                if not hist.empty:
                    yahoo = yahoo + ".L"
            if not hist.empty:
                result[t212_ticker] = hist[["Close", "Volume"]].copy()
        except Exception:
            pass
    return result


@st.cache_data(ttl=300, show_spinner=False)
def get_indicators(tickers: tuple[str]) -> pd.DataFrame:
    rows = []
    for t212_ticker in tickers:
        yahoo = to_yahoo_ticker(t212_ticker)
        try:
            hist = yf.Ticker(yahoo).history(period="90d")
            if hist.empty and not yahoo.endswith(".L"):
                hist = yf.Ticker(yahoo + ".L").history(period="90d")

            if hist.empty:
                rows.append({"ticker": t212_ticker, "daily_chg": None, "rsi": None, "vs_sma20": None})
                continue

            close = hist["Close"]
            daily_chg = (close.iloc[-1] / close.iloc[-2] - 1) * 100 if len(close) >= 2 else None

            # RSI-14
            delta = close.diff()
            gain = delta.clip(lower=0).rolling(14).mean()
            loss = (-delta.clip(upper=0)).rolling(14).mean()
            rs = gain / loss
            rsi = (100 - 100 / (1 + rs)).iloc[-1] if not loss.empty else None

            # Price vs 20-day SMA
            sma20 = close.rolling(20).mean().iloc[-1]
            vs_sma20 = (close.iloc[-1] / sma20 - 1) * 100 if sma20 else None

            # 7-day and 30-day change
            chg_7d = (close.iloc[-1] / close.iloc[-8] - 1) * 100 if len(close) >= 8 else None
            chg_30d = (close.iloc[-1] / close.iloc[-31] - 1) * 100 if len(close) >= 31 else None

            rows.append({
                "ticker": t212_ticker,
                "daily_chg": round(daily_chg, 2) if daily_chg is not None else None,
                "chg_7d": round(chg_7d, 2) if chg_7d is not None else None,
                "chg_30d": round(chg_30d, 2) if chg_30d is not None else None,
                "rsi": round(float(rsi), 1) if rsi is not None and not np.isnan(float(rsi)) else None,
                "vs_sma20": round(vs_sma20, 2) if vs_sma20 is not None else None,
            })
        except Exception:
            rows.append({"ticker": t212_ticker, "daily_chg": None, "rsi": None, "vs_sma20": None})

    return pd.DataFrame(rows).set_index("ticker")

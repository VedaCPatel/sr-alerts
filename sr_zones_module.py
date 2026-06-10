"""
sr_zones_module.py
------------------
Loads 'SR Zones.py' via importlib (filename has a space, so direct import fails).
Re-exports the five core algorithm functions unchanged.

Adds get_sr_zones(ticker) which:
  - Fetches 90 days of daily OHLCV candles from Finnhub REST
  - Runs the SR zone algorithm (find_pivots → cluster_pivots → build_zones)
  - Returns the best support and resistance zone as a JSON-serializable dict

All algorithm logic is identical to SR Zones.py — only the data source changes
from yfinance to Finnhub.
"""

import importlib.util
import os
import pathlib
import time
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

# ── load SR Zones.py by file path ─────────────────────────────────────────────
_HERE = pathlib.Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location("sr_zones", _HERE / "SR Zones.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

# re-export algorithm functions (unchanged)
find_pivots    = _MODULE.find_pivots
cluster_pivots = _MODULE.cluster_pivots
score_cluster  = _MODULE.score_cluster
build_zones    = _MODULE.build_zones

# algorithm constants (from SR Zones.py)
INTERVAL                 = _MODULE.INTERVAL                  # "1h"
PERIOD                   = _MODULE.PERIOD                    # "6mo"
PIVOT_LOOKBACK           = _MODULE.PIVOT_LOOKBACK            # 12
ZONE_MERGE_THRESHOLD_PCT = _MODULE.ZONE_MERGE_THRESHOLD_PCT  # 1.5
ZONE_WIDTH_PCT           = _MODULE.ZONE_WIDTH_PCT            # 0.8
MIN_TOUCHES              = _MODULE.MIN_TOUCHES               # 2
RECENCY_WEIGHT           = _MODULE.RECENCY_WEIGHT            # True
RECENCY_HALF_LIFE_BARS   = _MODULE.RECENCY_HALF_LIFE_BARS    # 60
ROUND_DECIMALS           = _MODULE.ROUND_DECIMALS            # 4

# Finnhub historical data config
LOOKBACK_DAYS = 90  # days of daily candle history

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "d8klglpr01qjgd71hcfgd8klglpr01qjgd71hcg0")


# ── Finnhub historical candles ────────────────────────────────────────────────

def _fetch_finnhub_candles(symbol: str) -> pd.DataFrame | None:
    """
    Fetch LOOKBACK_DAYS of daily OHLCV candles from Finnhub.
    Returns a DataFrame with columns: Open, High, Low, Close, Volume
    (capitalised to match what SR Zones.py algorithm expects).
    Returns None on failure.
    """
    end   = int(time.time())
    start = end - LOOKBACK_DAYS * 86400
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/stock/candle",
            params={
                "symbol":     symbol,
                "resolution": "D",
                "from":       start,
                "to":         end,
                "token":      FINNHUB_API_KEY,
            },
            timeout=10,
        )
        data = resp.json()
    except Exception as e:
        print(f"  [{symbol}] Finnhub candle fetch error: {e}")
        return None

    if data.get("s") != "ok":
        print(f"  [{symbol}] Finnhub candle status: {data.get('s')} — response: {data} — key: {FINNHUB_API_KEY[:10]}...")

        return None

    df = pd.DataFrame({
        "Open":   data["o"],
        "High":   data["h"],
        "Low":    data["l"],
        "Close":  data["c"],
        "Volume": data["v"],
    })
    df = df.dropna().reset_index(drop=True)

    if df.empty:
        print(f"  [{symbol}] Finnhub returned empty candle data")
        return None

    return df


# ── public API ────────────────────────────────────────────────────────────────

def get_sr_zones(ticker: str) -> dict:
    """
    Compute the best support and resistance zones for a ticker.

    Uses Finnhub REST for historical OHLCV data, then runs the unchanged
    SR zone algorithm from SR Zones.py.

    Returns:
        {
            "ticker":        "PLTR",
            "current_price": 24.35,
            "computed_at":   "2025-06-09T14:30:00+00:00",   # UTC ISO timestamp
            "support": {
                "center":  23.10,
                "low":     23.01,
                "high":    23.19,
                "touches": 3,
                "score":   2.1234
            },   # or None if no valid support zone found
            "resistance": { ... }   # or None
        }
    """
    df = _fetch_finnhub_candles(ticker)
    if df is None or len(df) < PIVOT_LOOKBACK * 3:
        return {
            "ticker":        ticker,
            "current_price": None,
            "computed_at":   datetime.now(timezone.utc).isoformat(),
            "support":       None,
            "resistance":    None,
        }

    current_price = float(df["Close"].iloc[-1])
    total_bars    = len(df)

    # run the SR algorithm (functions imported from SR Zones.py, unchanged)
    pivot_highs, pivot_lows = find_pivots(df, PIVOT_LOOKBACK)
    high_clusters           = cluster_pivots(pivot_highs, ZONE_MERGE_THRESHOLD_PCT)
    low_clusters            = cluster_pivots(pivot_lows,  ZONE_MERGE_THRESHOLD_PCT)

    all_zones = build_zones(
        high_clusters + low_clusters,
        current_price,
        total_bars,
        ZONE_WIDTH_PCT,
        MIN_TOUCHES,
        RECENCY_WEIGHT,
        RECENCY_HALF_LIFE_BARS,
    )

    support_zones = sorted(
        [z for z in all_zones if z["type"] == "support"],
        key=lambda z: (-z["center"], -z["score"]),
    )
    resistance_zones = sorted(
        [z for z in all_zones if z["type"] == "resistance"],
        key=lambda z: (z["center"], -z["score"]),
    )

    best_support    = support_zones[0]    if support_zones    else None
    best_resistance = resistance_zones[0] if resistance_zones else None

    def _clean(z):
        if z is None:
            return None
        return {
            "center":  z["center"],
            "low":     z["low"],
            "high":    z["high"],
            "touches": z["touches"],
            "score":   z["score"],
        }

    return {
        "ticker":        ticker,
        "current_price": round(current_price, ROUND_DECIMALS),
        "computed_at":   datetime.now(timezone.utc).isoformat(),
        "support":       _clean(best_support),
        "resistance":    _clean(best_resistance),
    }

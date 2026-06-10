"""
sr_zones_module.py
------------------
Loads 'SR Zones.py' via importlib (filename has a space, so direct import fails).
Uses fetch_data directly from SR Zones.py so data fetching is 100% identical
to running the local script (same yf.download call, same prepost=True flag).
"""

import importlib.util
import os
import pathlib
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import requests

_HERE = pathlib.Path(__file__).parent
_SPEC = importlib.util.spec_from_file_location("sr_zones", _HERE / "SR Zones.py")
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

fetch_data     = _MODULE.fetch_data
find_pivots    = _MODULE.find_pivots
cluster_pivots = _MODULE.cluster_pivots
score_cluster  = _MODULE.score_cluster
build_zones    = _MODULE.build_zones

INTERVAL                 = _MODULE.INTERVAL
PERIOD                   = _MODULE.PERIOD
PIVOT_LOOKBACK           = _MODULE.PIVOT_LOOKBACK
ZONE_MERGE_THRESHOLD_PCT = _MODULE.ZONE_MERGE_THRESHOLD_PCT
ZONE_WIDTH_PCT           = _MODULE.ZONE_WIDTH_PCT
MIN_TOUCHES              = _MODULE.MIN_TOUCHES
RECENCY_WEIGHT           = _MODULE.RECENCY_WEIGHT
RECENCY_HALF_LIFE_BARS   = _MODULE.RECENCY_HALF_LIFE_BARS
ROUND_DECIMALS           = _MODULE.ROUND_DECIMALS

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY", "d8klglpr01qjgd71hcfgd8klglpr01qjgd71hcg0")


def get_sr_zones(ticker: str) -> dict:
    try:
        df = fetch_data(ticker, PERIOD, INTERVAL)
    except Exception as e:
        print(f"  [{ticker}] fetch_data error: {e}")
        df = None

    if df is None or len(df) < PIVOT_LOOKBACK * 3:
        return {"ticker": ticker, "current_price": None, "computed_at": datetime.now(timezone.utc).isoformat(), "support": None, "resistance": None}

    current_price = float(df["Close"].iloc[-1])
    total_bars    = len(df)

    pivot_highs, pivot_lows = find_pivots(df, PIVOT_LOOKBACK)
    high_clusters           = cluster_pivots(pivot_highs, ZONE_MERGE_THRESHOLD_PCT)
    low_clusters            = cluster_pivots(pivot_lows,  ZONE_MERGE_THRESHOLD_PCT)

    all_zones = build_zones(high_clusters + low_clusters, current_price, total_bars, ZONE_WIDTH_PCT, MIN_TOUCHES, RECENCY_WEIGHT, RECENCY_HALF_LIFE_BARS)

    support_zones    = sorted([z for z in all_zones if z["type"] == "support"],    key=lambda z: (-z["center"], -z["score"]))
    resistance_zones = sorted([z for z in all_zones if z["type"] == "resistance"], key=lambda z: (z["center"],  -z["score"]))

    best_support    = support_zones[0]    if support_zones    else None
    best_resistance = resistance_zones[0] if resistance_zones else None

    def _clean(z):
        if z is None:
            return None
        return {"center": z["center"], "low": z["low"], "high": z["high"], "touches": z["touches"], "score": z["score"]}

    return {
        "ticker":        ticker,
        "current_price": round(current_price, ROUND_DECIMALS),
        "computed_at":   datetime.now(timezone.utc).isoformat(),
        "support":       _clean(best_support),
        "resistance":    _clean(best_resistance),
    }

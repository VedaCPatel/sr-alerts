"""
╔══════════════════════════════════════════════════════════════════════╗
║         SWING TRADING — SUPPORT & RESISTANCE ZONE FINDER            ║
║         One valid zone below price, one valid zone above price       ║
╚══════════════════════════════════════════════════════════════════════╝

REQUIREMENTS:
    pip install yfinance pandas numpy

QUICK START:
    Just change TICKER and run. All other settings have smart defaults.
"""

import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

import yfinance as yf
import pandas as pd
import numpy as np

# ─────────────────────────────────────────────────────────────────────────────
# ★  SECTION 1 — DATA SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

TICKER = "PLTR"
# What to type here: Any valid ticker symbol from Yahoo Finance.
# Examples: "TSLA", "NVDA", "BTC-USD", "ETH-USD", "GC=F" (Gold),
#           "CL=F" (Crude Oil), "EURUSD=X" (Forex), "^SPX" (S&P 500 index)

INTERVAL = "1h"
# What to type here: Candle timeframe for the data.
# Options:
#   "1m"  → 1 minute   (max 7 days of history)
#   "5m"  → 5 minutes  (max 60 days of history)
#   "15m" → 15 minutes (max 60 days of history)
#   "30m" → 30 minutes (max 60 days of history)
#   "1h"  → 1 hour     (max 730 days of history)
#   "4h"  → 4 hours    (max 730 days of history)  ← great for swing trading
#   "1d"  → Daily      (recommended for swing trading)
#   "1wk" → Weekly     (macro/long-term levels)
#   "1mo" → Monthly    (very long-term levels)

PERIOD = "6mo"
# How far back to pull data.
# Options: "1mo", "3mo", "6mo", "1y", "2y", "5y", "10y", "max"
# ⚠ Note: Short intervals (1m, 5m) only support short periods.
# Tip: For swing trading on daily charts, "1y" or "2y" is ideal.

# ─────────────────────────────────────────────────────────────────────────────
# ★  SECTION 2 — PIVOT DETECTION SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

PIVOT_LOOKBACK = 12
# How many candles to look left AND right of a candle to confirm a pivot.
# What to type here: Any positive integer.
# Low  (3–5)  → More pivots found, noisier, shorter-term levels.
# Mid  (7–12) → Balanced. Good default for daily swing trading.
# High (15+)  → Fewer pivots, only very significant structural levels.
# Tip: Higher = stronger, more respected zones.

# ─────────────────────────────────────────────────────────────────────────────
# ★  SECTION 3 — ZONE CONSTRUCTION SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

ZONE_MERGE_THRESHOLD_PCT = 1.5
# Pivots within this % of each other are merged into ONE zone.
# What to type here: A float (percentage).
# Examples: 0.5, 1.0, 1.5, 2.0, 3.0
# Low  (0.5–1.0%) → Tight zones, more zones, less merging.
# Mid  (1.0–2.0%) → Good default. Captures natural price clusters.
# High (2.5–4.0%) → Wide zones, fewer zones, very aggressive merging.
# Tip: For volatile assets (crypto), use 2.0–3.0%. For stocks, 1.0–1.5%.

ZONE_WIDTH_PCT = 0.8
# How wide (tall) each final zone is, as a % of the zone's center price.
# What to type here: A float (percentage).
# Examples: 0.3, 0.5, 0.8, 1.0, 1.5
# Low  (0.3–0.5%) → Narrow zones, price must be very precise.
# Mid  (0.6–1.0%) → Balanced default. Good for swing trading.
# High (1.2–2.0%) → Wide zones, more forgiving entries.
# Tip: Match to ATR or typical daily range of the asset.

# ─────────────────────────────────────────────────────────────────────────────
# ★  SECTION 4 — ZONE SCORING / VALIDATION SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

MIN_TOUCHES = 2
# Minimum number of pivot touches a cluster must have to be a valid zone.
# What to type here: Any integer ≥ 1.
# 1 → Any single pivot qualifies (less reliable).
# 2 → Needs to have been tested at least twice (recommended default).
# 3 → High confluence zones only (very selective).

RECENCY_WEIGHT = True
# Whether to score recent touches higher than old ones.
# What to type here: True or False
# True  → Recent touches boost the zone's score (recommended for swing trading).
# False → All touches weighted equally regardless of age.

RECENCY_HALF_LIFE_BARS = 60
# Only used if RECENCY_WEIGHT = True.
# Touches older than this many bars ago are worth ~50% of a recent touch.
# What to type here: Any positive integer.
# Examples: 30 (short memory), 60 (medium), 120 (long memory)

# ─────────────────────────────────────────────────────────────────────────────
# ★  SECTION 5 — OUTPUT SETTINGS
# ─────────────────────────────────────────────────────────────────────────────

SHOW_SCORE_BREAKDOWN = True
# Print a detailed breakdown of how each zone was scored.
# What to type here: True or False

ROUND_DECIMALS = 4
# Decimal places for price output.
# What to type here: 0, 1, 2, 3, 4
# Use 2 for stocks, 4–5 for forex pairs, 0–2 for crypto.


# ══════════════════════════════════════════════════════════════════════════════
#   CORE LOGIC — No need to edit below unless you want to customize deeply
# ══════════════════════════════════════════════════════════════════════════════

def fetch_data(ticker, period, interval):
    """Download OHLCV data from Yahoo Finance."""
    print(f"\n  Fetching {ticker} | {interval} candles | {period} history...")
    df = yf.download(ticker, period=period, interval=interval, progress=False, auto_adjust=True, prepost=True)
    if df.empty:
        raise ValueError(f"No data returned for {ticker}. Check ticker and interval compatibility.")
    df.columns = [c[0] if isinstance(c, tuple) else c for c in df.columns]
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    print(f"  [OK] {len(df)} candles loaded. Last close: {round(df['Close'].iloc[-1], ROUND_DECIMALS)}\n")
    return df


def find_pivots(df, lookback):
    """
    Identify swing highs and swing lows using a rolling window.
    A pivot high = highest high in [i-lookback : i+lookback].
    A pivot low  = lowest  low  in [i-lookback : i+lookback].
    """
    highs = df["High"].values
    lows  = df["Low"].values
    n     = len(df)

    pivot_highs = []  # (bar_index, price)
    pivot_lows  = []  # (bar_index, price)

    for i in range(lookback, n - lookback):
        window_h = highs[i - lookback : i + lookback + 1]
        window_l = lows [i - lookback : i + lookback + 1]

        if highs[i] == np.max(window_h):
            pivot_highs.append((i, highs[i]))

        if lows[i] == np.min(window_l):
            pivot_lows.append((i, lows[i]))

    return pivot_highs, pivot_lows


def cluster_pivots(pivots, merge_pct):
    """
    Group nearby pivots into clusters based on price proximity.
    Pivots within merge_pct% of each other belong to the same cluster.
    Returns list of clusters: each cluster = list of (bar_index, price).
    """
    if not pivots:
        return []

    sorted_pivots = sorted(pivots, key=lambda x: x[1])
    clusters = []
    current_cluster = [sorted_pivots[0]]

    for i in range(1, len(sorted_pivots)):
        prev_price = current_cluster[-1][1]
        curr_price = sorted_pivots[i][1]
        if abs(curr_price - prev_price) / prev_price * 100 <= merge_pct:
            current_cluster.append(sorted_pivots[i])
        else:
            clusters.append(current_cluster)
            current_cluster = [sorted_pivots[i]]

    clusters.append(current_cluster)
    return clusters


def score_cluster(cluster, total_bars, recency_weight, half_life):
    """
    Score a cluster based on:
      - Number of touches (more = stronger)
      - Recency of touches (recent = stronger, if enabled)
    Returns a float score.
    """
    score = 0.0
    for (bar_idx, _) in cluster:
        if recency_weight:
            bars_ago = total_bars - bar_idx
            weight   = 2 ** (-bars_ago / half_life)  # exponential decay
        else:
            weight = 1.0
        score += weight
    return round(score, 4)


def build_zones(clusters, current_price, total_bars, zone_width_pct,
                min_touches, recency_weight, half_life):
    """
    Convert clusters into support/resistance zones with scoring.
    Filter by MIN_TOUCHES. Separate into support (below) and resistance (above).
    """
    zones = []
    for cluster in clusters:
        if len(cluster) < min_touches:
            continue

        prices     = [p for (_, p) in cluster]
        center     = np.mean(prices)
        half_width = center * (zone_width_pct / 100) / 2
        zone_low   = center - half_width
        zone_high  = center + half_width
        touches    = len(cluster)
        score      = score_cluster(cluster, total_bars, recency_weight, half_life)

        zones.append({
            "center":   round(center,    ROUND_DECIMALS),
            "low":      round(zone_low,  ROUND_DECIMALS),
            "high":     round(zone_high, ROUND_DECIMALS),
            "touches":  touches,
            "score":    score,
            "type":     "support"    if center < current_price else "resistance",
            "cluster":  cluster,
        })

    return zones


def select_best_zone(zones, zone_type):
    """
    From all zones of a given type (support or resistance),
    pick the ONE closest to current price with the highest score.
    Priority: proximity first, then score as tiebreaker.
    """
    candidates = [z for z in zones if z["type"] == zone_type]
    if not candidates:
        return None
    # Sort: closest center to current price first, then by score descending
    candidates.sort(key=lambda z: (abs(z["center"]), -z["score"]))
    # Actually sort by distance from current_price
    # (we don't have current_price here; it's filtered above already)
    return candidates  # return all; selection happens after


def run():
    # ── 1. Fetch data ─────────────────────────────────────────────────────────
    df = fetch_data(TICKER, PERIOD, INTERVAL)
    current_price = float(df["Close"].iloc[-1])
    total_bars    = len(df)

    # ── 2. Find pivots ────────────────────────────────────────────────────────
    pivot_highs, pivot_lows = find_pivots(df, PIVOT_LOOKBACK)
    print(f"  Pivots found → Highs: {len(pivot_highs)} | Lows: {len(pivot_lows)}")

    # ── 3. Cluster pivots ─────────────────────────────────────────────────────
    high_clusters = cluster_pivots(pivot_highs, ZONE_MERGE_THRESHOLD_PCT)
    low_clusters  = cluster_pivots(pivot_lows,  ZONE_MERGE_THRESHOLD_PCT)

    # ── 4. Build zones ────────────────────────────────────────────────────────
    all_zones = build_zones(
        high_clusters + low_clusters,
        current_price,
        total_bars,
        ZONE_WIDTH_PCT,
        MIN_TOUCHES,
        RECENCY_WEIGHT,
        RECENCY_HALF_LIFE_BARS
    )

    # ── 5. Separate support vs resistance ─────────────────────────────────────
    support_zones    = sorted(
        [z for z in all_zones if z["type"] == "support"],
        key=lambda z: (-z["center"], -z["score"])  # closest below = highest center
    )
    resistance_zones = sorted(
        [z for z in all_zones if z["type"] == "resistance"],
        key=lambda z: (z["center"], -z["score"])   # closest above = lowest center
    )

    best_support    = support_zones[0]    if support_zones    else None
    best_resistance = resistance_zones[0] if resistance_zones else None

    # ── 6. Print results ──────────────────────────────────────────────────────
    sep = "─" * 60

    print(f"\n{'═'*60}")
    print(f"  {TICKER}  |  Current Price: {round(current_price, ROUND_DECIMALS)}")
    print(f"{'═'*60}")

    if best_resistance:
        print(f"\n  ▲  RESISTANCE ZONE (above price)")
        print(f"  {sep}")
        print(f"  Zone High   : {best_resistance['high']}")
        print(f"  Zone Center : {best_resistance['center']}")
        print(f"  Zone Low    : {best_resistance['low']}")
        print(f"  Touches     : {best_resistance['touches']}")
        print(f"  Score       : {best_resistance['score']}")
        dist_r = round((best_resistance['center'] - current_price) / current_price * 100, 2)
        print(f"  Distance    : +{dist_r}% from current price")
        if SHOW_SCORE_BREAKDOWN:
            print(f"\n  Score Breakdown (each touch):")
            for (bar_idx, price) in best_resistance['cluster']:
                bars_ago = total_bars - bar_idx
                w = round(2 ** (-bars_ago / RECENCY_HALF_LIFE_BARS), 4) if RECENCY_WEIGHT else 1.0
                print(f"    Price {round(price, ROUND_DECIMALS):>10}  |  {bars_ago:>4} bars ago  |  weight {w}")
    else:
        print("\n  ▲  No valid resistance zone found. Try lowering MIN_TOUCHES or PIVOT_LOOKBACK.")

    print()

    if best_support:
        print(f"  ▼  SUPPORT ZONE (below price)")
        print(f"  {sep}")
        print(f"  Zone High   : {best_support['high']}")
        print(f"  Zone Center : {best_support['center']}")
        print(f"  Zone Low    : {best_support['low']}")
        print(f"  Touches     : {best_support['touches']}")
        print(f"  Score       : {best_support['score']}")
        dist_s = round((current_price - best_support['center']) / current_price * 100, 2)
        print(f"  Distance    : -{dist_s}% from current price")
        if SHOW_SCORE_BREAKDOWN:
            print(f"\n  Score Breakdown (each touch):")
            for (bar_idx, price) in best_support['cluster']:
                bars_ago = total_bars - bar_idx
                w = round(2 ** (-bars_ago / RECENCY_HALF_LIFE_BARS), 4) if RECENCY_WEIGHT else 1.0
                print(f"    Price {round(price, ROUND_DECIMALS):>10}  |  {bars_ago:>4} bars ago  |  weight {w}")
    else:
        print("  ▼  No valid support zone found. Try lowering MIN_TOUCHES or PIVOT_LOOKBACK.")

    print(f"\n{'═'*60}\n")


if __name__ == "__main__":
    run()
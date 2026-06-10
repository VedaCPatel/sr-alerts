"""
sr_alert_monitor.py
--------------------
Runs on GitHub Actions every 1 minute (pre-market through after-hours).
For each ticker in tickers.json: compute/cache SR zones, fetch live price,
alert to Discord if price is inside the support zone (30-min cooldown).
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

from market_hours import assert_trading_day
from sr_zones_module import get_sr_zones, FINNHUB_API_KEY, ROUND_DECIMALS

DISCORD_WEBHOOK_URL = os.getenv("DISCORD_WEBHOOK_URL")
COOLDOWN_MINUTES    = 30
ZONE_CACHE_MINUTES  = 15
ZONE_BUFFER_PCT     = 0.10   # widen zone edges by this % so near-misses still alert

_DIR             = os.path.dirname(os.path.abspath(__file__))
TICKERS_FILE     = os.path.join(_DIR, "tickers.json")
ALERT_STATE_FILE = os.path.join(_DIR, "alert_state.json")
ZONE_CACHE_FILE  = os.path.join(_DIR, "zone_cache.json")


def _load_json(path: str, default):
    if not os.path.exists(path):
        return default
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path: str, data) -> None:
    with open(path, "w") as f:
        json.dump(data, f, indent=2)


def _minutes_since(iso_ts: str) -> float:
    try:
        t   = datetime.fromisoformat(iso_ts)
        now = datetime.now(timezone.utc)
        return (now - t).total_seconds() / 60
    except Exception:
        return 9999.0


def get_live_price(ticker: str) -> float | None:
    # 1. Finnhub /quote
    try:
        resp = requests.get(
            "https://finnhub.io/api/v1/quote",
            params={"symbol": ticker, "token": FINNHUB_API_KEY},
            timeout=8,
        )
        data = resp.json()
        price = data.get("c")
        if price and price > 0:
            print(f"  [{ticker}] Finnhub quote: ${float(price):.4f}  (raw: {data})")
            return float(price)
        print(f"  [{ticker}] Finnhub quote empty (raw: {data}) — trying yfinance.")
    except Exception as e:
        print(f"  [{ticker}] Finnhub quote error: {e} — trying yfinance.")

    # 2. yfinance fallback
    try:
        import yfinance as yf
        fi = yf.Ticker(ticker).fast_info
        price = fi.get("last_price") if hasattr(fi, "get") else fi["last_price"]
        if price and price > 0:
            print(f"  [{ticker}] yfinance live price: ${float(price):.4f}")
            return float(price)
    except Exception as e:
        print(f"  [{ticker}] yfinance live price error: {e}")

    return None


def send_discord_alert(ticker: str, price: float, support: dict) -> bool:
    if not DISCORD_WEBHOOK_URL:
        print(f"  [{ticker}] DISCORD_WEBHOOK_URL not set — skipping.")
        return False

    dist = round(abs(price - support["center"]) / support["center"] * 100, 2)
    now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    embed = {
        "title":       f"\U0001f7e2  SUPPORT ZONE ALERT — {ticker}",
        "description": f"**{ticker}** is trading inside a support zone.",
        "color":       0x2ECC71,
        "fields": [
            {"name": "Current Price",      "value": f"`${price:.{ROUND_DECIMALS}f}`",            "inline": True},
            {"name": "Zone Low",           "value": f"`${support['low']:.{ROUND_DECIMALS}f}`",   "inline": True},
            {"name": "Zone High",          "value": f"`${support['high']:.{ROUND_DECIMALS}f}`",  "inline": True},
            {"name": "Zone Center",        "value": f"`${support['center']:.{ROUND_DECIMALS}f}`","inline": True},
            {"name": "Touches",            "value": f"`{support['touches']}`",                   "inline": True},
            {"name": "Score",              "value": f"`{support['score']}`",                     "inline": True},
            {"name": "Dist. from Center",  "value": f"`{dist}%`",                                "inline": True},
        ],
        "footer":    {"text": f"SR Zone Monitor  |  {now_str}"},
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    try:
        resp = requests.post(DISCORD_WEBHOOK_URL, json={"embeds": [embed]}, timeout=10)
        if resp.status_code == 204:
            print(f"  [{ticker}] Discord alert sent.")
            return True
        else:
            print(f"  [{ticker}] Discord error {resp.status_code}: {resp.text[:200]}")
            return False
    except Exception as e:
        print(f"  [{ticker}] Discord send error: {e}")
        return False


def main() -> None:
    assert_trading_day()

    if not DISCORD_WEBHOOK_URL:
        print("WARNING: DISCORD_WEBHOOK_URL not set — alerts will be skipped.")

    tickers     = _load_json(TICKERS_FILE,     [])
    alert_state = _load_json(ALERT_STATE_FILE, {})
    zone_cache  = _load_json(ZONE_CACHE_FILE,  {})

    if not tickers:
        print("tickers.json is empty — nothing to monitor.")
        sys.exit(0)

    print(f"Monitoring {len(tickers)} tickers: {tickers}\n")

    cache_changed  = False
    alerts_changed = False

    for ticker in tickers:
        print(f"-- {ticker} --")

        cached = zone_cache.get(ticker)
        cache_age = _minutes_since(cached["computed_at"]) if cached else 9999.0

        if cached is None or cache_age >= ZONE_CACHE_MINUTES:
            print(f"  [{ticker}] Computing SR zones ...")
            try:
                result = get_sr_zones(ticker)
            except Exception as e:
                print(f"  [{ticker}] SR zone error: {e} — skipping.")
                continue
            zone_cache[ticker] = result
            cache_changed = True
            print(f"  [{ticker}] Support: {result.get('support')} | Resistance: {result.get('resistance')}")
        else:
            result = cached
            print(f"  [{ticker}] Using cached zones (age {cache_age:.1f} min).")

        support = result.get("support")
        if support is None:
            print(f"  [{ticker}] No valid support zone — skipping.")
            continue

        live_price = get_live_price(ticker)
        if live_price is None:
            live_price = result.get("current_price")
            if live_price is None:
                print(f"  [{ticker}] Cannot determine price — skipping.")
                continue
            print(f"  [{ticker}] No live price; using cached close ${live_price}.")

        buf       = support["center"] * (ZONE_BUFFER_PCT / 100)
        zone_low  = support["low"]  - buf
        zone_high = support["high"] + buf
        inside    = zone_low <= live_price <= zone_high
        print(f"  [{ticker}] Live ${live_price:.4f} vs support zone ${zone_low:.4f} – ${zone_high:.4f} | Inside: {inside}")

        if not inside:
            continue

        last_alert_ts = alert_state.get(ticker)
        if last_alert_ts and _minutes_since(last_alert_ts) < COOLDOWN_MINUTES:
            remaining = COOLDOWN_MINUTES - _minutes_since(last_alert_ts)
            print(f"  [{ticker}] On cooldown — {remaining:.0f} min remaining.")
            continue

        sent = send_discord_alert(ticker, live_price, support)
        if sent:
            alert_state[ticker] = datetime.now(timezone.utc).isoformat()
            alerts_changed = True

    if cache_changed:
        _save_json(ZONE_CACHE_FILE, zone_cache)
        print("\nzone_cache.json updated.")
    if alerts_changed:
        _save_json(ALERT_STATE_FILE, alert_state)
        print("alert_state.json updated.")
    if not cache_changed and not alerts_changed:
        print("\nNo state changes this run.")


if __name__ == "__main__":
    main()

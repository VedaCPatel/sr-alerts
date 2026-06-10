"""
robinhood_fetcher.py
---------------------
Runs on GitHub Actions every 15 minutes (pre-market through after-hours).
Logs into Robinhood, collects all portfolio + watchlist tickers,
saves them to tickers.json.

Credentials via GitHub Actions Secrets (set as environment variables):
    RH_USERNAME  — Robinhood email
    RH_PASSWORD  — Robinhood password

Outputs:
    tickers.json         — sorted list of unique ticker strings
    rh_session.pickle    — stored Robinhood auth token (reused on next run
                           to avoid SMS MFA challenges from new runner IPs)
"""

import json
import os
import sys

import robin_stocks.robinhood as rh
from market_hours import assert_trading_day

RH_USERNAME  = os.getenv("RH_USERNAME",  "vedapatel05@gmail.com")
RH_PASSWORD  = os.getenv("RH_PASSWORD",  "Omsairam@1611")

_DIR          = os.path.dirname(os.path.abspath(__file__))
TICKERS_FILE  = os.path.join(_DIR, "tickers.json")
PICKLE_PATH   = os.path.join(_DIR, "rh_session.pickle")


def login() -> None:
    print(f"Logging in as {RH_USERNAME} ...")
    rh.login(
        RH_USERNAME,
        RH_PASSWORD,
        store_session=True,
        pickle_path=PICKLE_PATH,
    )
    print("Login OK.")


def get_portfolio_tickers() -> list:
    try:
        holdings = rh.build_holdings()
        tickers  = list(holdings.keys())
        print(f"  Portfolio: {len(tickers)} tickers — {tickers}")
        return tickers
    except Exception as e:
        print(f"  WARNING: Could not fetch portfolio: {e}")
        return []


def get_watchlist_tickers() -> list:
    tickers = []
    try:
        wls = rh.get_all_watchlists()
        if not wls or "results" not in wls:
            print("  WARNING: No watchlists returned.")
            return []
        for wl in wls["results"]:
            name = wl.get("display_name", "")
            try:
                items = rh.get_watchlist_by_name(name) or []
                symbols = []
                for item in items:
                    if isinstance(item, dict):
                        sym = item.get("symbol") or item.get("ticker") or item.get("slug")
                        if not sym:
                            instrument_url = item.get("instrument") or item.get("instrument_url", "")
                            if instrument_url:
                                try:
                                    inst = rh.get_instrument_by_url(instrument_url)
                                    sym = inst.get("symbol") if inst else None
                                except Exception:
                                    pass
                        if sym:
                            symbols.append(sym.upper())
                    elif isinstance(item, str):
                        symbols.append(item.upper())
                print(f"  Watchlist '{name}': {len(symbols)} tickers — {symbols}")
                tickers.extend(symbols)
            except Exception as e:
                print(f"  WARNING: Could not fetch watchlist '{name}': {e}")
    except Exception as e:
        print(f"  WARNING: Could not fetch watchlists: {e}")
    return tickers


def save_tickers(tickers: list) -> None:
    unique = sorted(set(t.upper() for t in tickers if t))
    with open(TICKERS_FILE, "w") as f:
        json.dump(unique, f, indent=2)
    print(f"Saved {len(unique)} tickers to tickers.json: {unique}")


def main() -> None:
    assert_trading_day()

    if not RH_USERNAME or not RH_PASSWORD:
        print("ERROR: RH_USERNAME and RH_PASSWORD must be set.")
        sys.exit(1)

    login()
    try:
        portfolio = get_portfolio_tickers()
        watchlist = get_watchlist_tickers()
        save_tickers(portfolio + watchlist)
    except Exception as e:
        print(f"FATAL: {e}")
        sys.exit(1)
    finally:
        try:
            rh.logout()
        except Exception:
            pass


if __name__ == "__main__":
    main()

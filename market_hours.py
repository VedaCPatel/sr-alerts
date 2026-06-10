"""
market_hours.py
---------------
Utility for checking whether the current moment falls within extended
trading hours on a US market day (NYSE calendar).

Extended hours window: 4:00 AM – 8:00 PM ET, Mon–Fri, non-holiday.

Usage:
    from market_hours import assert_trading_day

    assert_trading_day()   # exits with code 0 if outside trading hours

Requires:
    pandas_market_calendars>=4.0  (added to requirements.txt)
"""

import sys
from datetime import datetime

import pandas_market_calendars as mcal
import pytz

ET = pytz.timezone("America/New_York")

# Extended hours: 4:00 AM – 8:00 PM ET
EXTENDED_OPEN_MIN  = 4 * 60       # 240 minutes since midnight
EXTENDED_CLOSE_MIN = 20 * 60      # 1200 minutes since midnight

_NYSE = mcal.get_calendar("NYSE")


def is_trading_day(dt_et: datetime | None = None) -> bool:
    """
    Returns True if dt_et (ET-localised datetime, default = now) falls on a
    valid NYSE trading day (weekday + not a market holiday).
    Does NOT check the time of day — only the calendar date.
    """
    if dt_et is None:
        dt_et = datetime.now(pytz.utc).astimezone(ET)

    date_str = dt_et.strftime("%Y-%m-%d")
    schedule = _NYSE.schedule(start_date=date_str, end_date=date_str)
    return not schedule.empty


def is_extended_hours(dt_et: datetime | None = None) -> bool:
    """
    Returns True if dt_et is within 4:00 AM – 8:00 PM ET on a NYSE trading day.
    """
    if dt_et is None:
        dt_et = datetime.now(pytz.utc).astimezone(ET)

    if not is_trading_day(dt_et):
        return False

    mins = dt_et.hour * 60 + dt_et.minute
    return EXTENDED_OPEN_MIN <= mins < EXTENDED_CLOSE_MIN


def assert_trading_day() -> None:
    """
    Call at the top of any scheduled script.
    Prints status and exits with code 0 (success, no error) if outside
    extended trading hours so GitHub Actions marks the run as passed.
    """
    dt_et = datetime.now(pytz.utc).astimezone(ET)
    time_str = dt_et.strftime("%A %Y-%m-%d %H:%M ET")

    if not is_trading_day(dt_et):
        print(f"[market_hours] {time_str} — market holiday or weekend. Exiting.")
        sys.exit(0)

    mins = dt_et.hour * 60 + dt_et.minute
    if not (EXTENDED_OPEN_MIN <= mins < EXTENDED_CLOSE_MIN):
        print(f"[market_hours] {time_str} — outside extended hours (4am–8pm ET). Exiting.")
        sys.exit(0)

    print(f"[market_hours] {time_str} — trading day, within extended hours. Proceeding.")

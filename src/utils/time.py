from __future__ import annotations
import datetime as dt
import pytz

EASTERN = pytz.timezone("US/Eastern")


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


def now_eastern() -> dt.datetime:
    return now_utc().astimezone(EASTERN)


def is_weekday(ts: dt.datetime) -> bool:
    return ts.weekday() < 5


def is_regular_hours(ts: dt.datetime) -> bool:
    if not is_weekday(ts):
        return False
    t = ts.timetz()
    open_t = dt.time(9, 30, tzinfo=EASTERN)
    close_t = dt.time(16, 0, tzinfo=EASTERN)
    return open_t <= t <= close_t


def seconds_to_close(ts: dt.datetime) -> int:
    close_dt = ts.replace(hour=16, minute=0, second=0, microsecond=0)
    if ts > close_dt:
        return 0
    return int((close_dt - ts).total_seconds())

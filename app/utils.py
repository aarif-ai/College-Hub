"""Small helpers shared across the app (time, safe redirects, filters)."""
import os
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, urlparse

from flask import request

try:  # zoneinfo needs the tzdata package on some systems (e.g. Windows)
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

_FALLBACK_TZ = timezone(timedelta(hours=5, minutes=30))


def _college_tz():
    name = os.environ.get("APP_TIMEZONE", "Asia/Kolkata")
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:  # unknown zone or missing tzdata
            pass
    return _FALLBACK_TZ


def now() -> datetime:
    """Current college-local time as a *naive* datetime.

    All timestamps and deadlines in CollegeHub are naive college time, so
    comparisons never mix aware and naive values.
    """
    return datetime.now(_college_tz()).replace(tzinfo=None)


def is_safe_redirect(target: str) -> bool:
    """True when ``target`` stays on this site (prevents open redirects)."""
    if not target:
        return False
    host = urlparse(request.host_url)
    dest = urlparse(urljoin(request.host_url, target))
    return dest.scheme in ("http", "https") and host.netloc == dest.netloc


def fmt_date(value) -> str:
    return value.strftime("%a, %d %b %Y") if value else "-"


def fmt_time(value) -> str:
    return value.strftime("%I:%M %p").lstrip("0") if value else "-"


def fmt_datetime(value) -> str:
    if not value:
        return "-"
    return value.strftime("%d %b %Y, %I:%M %p").lstrip("0")


def fmt_short_date(value) -> str:
    return value.strftime("%d %b") if value else "-"

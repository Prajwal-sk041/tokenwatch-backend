from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException


@dataclass(frozen=True)
class ReportRange:
    start_utc: datetime
    end_utc: datetime
    timezone_name: str


def timezone_or_422(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="Invalid IANA timezone") from None


def report_range(name: str, preset: str, start: date | None = None, end: date | None = None,
                 now: datetime | None = None) -> ReportRange:
    tz = timezone_or_422(name)
    local_today = (now or datetime.now(timezone.utc)).astimezone(tz).date()
    if preset == "today": first, last = local_today, local_today
    elif preset == "yesterday": first = last = local_today - timedelta(days=1)
    elif preset == "7d": first, last = local_today - timedelta(days=6), local_today
    elif preset == "30d": first, last = local_today - timedelta(days=29), local_today
    elif preset == "current_month": first, last = local_today.replace(day=1), local_today
    elif preset == "previous_month":
        current = local_today.replace(day=1); last = current - timedelta(days=1); first = last.replace(day=1)
    elif preset == "custom" and start and end and start <= end:
        first, last = start, end
    else:
        raise HTTPException(status_code=422, detail="Invalid date range")
    start_local = datetime.combine(first, time.min, tzinfo=tz)
    end_local = datetime.combine(last + timedelta(days=1), time.min, tzinfo=tz)
    return ReportRange(start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc), name)


def local_day(value: str, timezone_name: str) -> str:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone_or_422(timezone_name)).date().isoformat()

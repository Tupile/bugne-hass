"""Build the agenda + weather payload a Bugne device shows.

Pure Python, no Home Assistant import, so it is unit-tested on its own
(tests/test_agenda.py). The device displays these strings as they are: every
date, time and temperature is formatted here.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

MAX_EVENTS = 3
# The device keeps 63 bytes of title and 31 of "when": do not send more. A
# long title would also grow the JSON body past what the device accepts.
MAX_WHAT_CHARS = 63
MAX_WHEN_CHARS = 31

# Weather states that mean falling water (used for "rain within the hour").
RAIN_CONDITIONS = frozenset({"rainy", "pouring", "lightning-rainy", "snowy-rainy", "hail"})

_UNUSABLE = (None, "", "unknown", "unavailable")

# Day and month names are tables, not strftime: the result must not depend
# on the locale of the machine running Home Assistant.
_LANG: dict[str, dict[str, Any]] = {
    "en": {
        "today": "Today",
        "tomorrow": "Tomorrow",
        "days": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "months": ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                   "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        "date": "{day} {d} {month}",
    },
    "fr": {
        "today": "Aujourd'hui",
        "tomorrow": "Demain",
        "days": ["lun.", "mar.", "mer.", "jeu.", "ven.", "sam.", "dim."],
        "months": ["janv.", "févr.", "mars", "avr.", "mai", "juin",
                   "juil.", "août", "sept.", "oct.", "nov.", "déc."],
        "date": "{day} {d} {month}",
    },
    "de": {
        "today": "Heute",
        "tomorrow": "Morgen",
        "days": ["Mo.", "Di.", "Mi.", "Do.", "Fr.", "Sa.", "So."],
        "months": ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni",
                   "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."],
        "date": "{day} {d}. {month}",
    },
}


def _lang(language: str | None) -> dict[str, Any]:
    return _LANG.get((language or "en")[:2].lower(), _LANG["en"])


def _parse(value: Any, now: datetime) -> date | datetime | None:
    """Read an ISO date (all-day) or date-time, the latter in local time."""
    if isinstance(value, datetime):
        parsed: date | datetime = value
    elif isinstance(value, date):
        return value
    elif isinstance(value, str):
        try:
            parsed = date.fromisoformat(value) if len(value) == 10 else datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if isinstance(parsed, datetime):
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=now.tzinfo)
        return parsed.astimezone(now.tzinfo)
    return parsed


def format_when(start: Any, now: datetime, language: str | None) -> str:
    """Return the "when" line of an event, or "" if the start is unreadable."""
    parsed = _parse(start, now)
    if parsed is None:
        return ""
    words = _lang(language)
    timed = isinstance(parsed, datetime)
    day = parsed.date() if timed else parsed
    today = now.date()
    if day < today:
        # Already started on an earlier day and still on: it is on today.
        return words["today"]
    if day == today:
        label = words["today"]
    elif day == today + timedelta(days=1):
        label = words["tomorrow"]
    else:
        label = words["date"].format(
            day=words["days"][day.weekday()], d=day.day, month=words["months"][day.month - 1]
        )
    return f"{label} {parsed:%H:%M}" if timed else label


def format_temp(value: Any, unit: str | None) -> str | None:
    """Return a rounded temperature with its unit, or None if not a number."""
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        return None
    return f"{number} {unit}".strip() if unit else str(number)


def rain_soon(hourly: list[dict[str, Any]] | None, now: datetime) -> bool:
    """True when the hourly forecast announces rain within the hour.

    An entry counts when its hour is running or starts in the next 60
    minutes, and it has a rain condition or a positive precipitation amount.
    """
    for entry in hourly or []:
        start = _parse(entry.get("datetime"), now)
        if not isinstance(start, datetime):
            continue
        if not now - timedelta(hours=1) < start <= now + timedelta(hours=1):
            continue
        if entry.get("condition") in RAIN_CONDITIONS:
            return True
        try:
            if float(entry.get("precipitation") or 0) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _today_forecast(daily: list[dict[str, Any]] | None, now: datetime) -> dict[str, Any] | None:
    if not daily:
        return None
    today = now.date().isoformat()
    for entry in daily:
        # The date as written by the provider, not converted: a daily entry
        # stamped at UTC midnight must not slide to the previous local day.
        if str(entry.get("datetime") or "")[:10] == today:
            return entry
    return daily[0]


def _sort_key(start: date | datetime, now: datetime) -> datetime:
    if isinstance(start, datetime):
        return start
    # An all-day event sorts at the first minute of its day.
    return datetime(start.year, start.month, start.day, tzinfo=now.tzinfo)


def build_payload(
    *,
    events: list[dict[str, Any]] | None = None,
    condition: str | None = None,
    temperature: Any = None,
    unit: str | None = None,
    daily: list[dict[str, Any]] | None = None,
    hourly: list[dict[str, Any]] | None = None,
    language: str | None,
    now: datetime,
) -> dict[str, Any]:
    """Build the body of POST /api/agenda.

    `events` is None when no calendar is configured (no "events" key) and a
    list, possibly empty, when one is. `condition` is the raw state of the
    weather entity; an unusable state sends no "weather" block.
    """
    payload: dict[str, Any] = {}

    if condition not in _UNUSABLE:
        weather: dict[str, Any] = {"cond": condition}
        temp = format_temp(temperature, unit)
        if temp is not None:
            weather["temp"] = temp
        today = _today_forecast(daily, now)
        if today:
            low = format_temp(today.get("templow"), unit)
            high = format_temp(today.get("temperature"), unit)
            if low is not None:
                weather["min"] = low
            if high is not None:
                weather["max"] = high
        if rain_soon(hourly, now):
            weather["rain"] = True
        payload["weather"] = weather

    if events is not None:
        dated = []
        for event in events:
            start = _parse(event.get("start"), now)
            if start is not None:
                dated.append((_sort_key(start, now), event))
        dated.sort(key=lambda item: item[0])
        payload["events"] = [
            {
                "when": format_when(event.get("start"), now, language)[:MAX_WHEN_CHARS],
                "what": str(event.get("summary") or "")[:MAX_WHAT_CHARS],
            }
            for _, event in dated[:MAX_EVENTS]
        ]

    return payload

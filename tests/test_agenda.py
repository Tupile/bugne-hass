"""Tests for agenda.py: the text the device shows is built here."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import bugne_agenda as agenda

TZ = timezone(timedelta(hours=1))
# Friday 13 November 2026, 15:00 local time.
NOW = datetime(2026, 11, 13, 15, 0, tzinfo=TZ)


def test_when_today_tomorrow_later_in_french():
    assert agenda.format_when("2026-11-13T17:00:00+01:00", NOW, "fr") == "Aujourd'hui 17:00"
    assert agenda.format_when("2026-11-14T09:30:00+01:00", NOW, "fr") == "Demain 09:30"
    assert agenda.format_when("2026-11-21T10:00:00+01:00", NOW, "fr") == "sam. 21 nov. 10:00"


def test_when_in_english_and_german():
    assert agenda.format_when("2026-11-13T17:00:00+01:00", NOW, "en") == "Today 17:00"
    assert agenda.format_when("2026-11-21T10:00:00+01:00", NOW, "en-GB") == "Sat 21 Nov 10:00"
    assert agenda.format_when("2026-11-14T09:30:00+01:00", NOW, "de") == "Morgen 09:30"
    assert agenda.format_when("2026-11-21T10:00:00+01:00", NOW, "de") == "Sa. 21. Nov. 10:00"


def test_when_unknown_language_falls_back_to_english():
    assert agenda.format_when("2026-11-13T17:00:00+01:00", NOW, "xx") == "Today 17:00"
    assert agenda.format_when("2026-11-13T17:00:00+01:00", NOW, None) == "Today 17:00"


def test_when_all_day_has_no_time():
    assert agenda.format_when("2026-11-13", NOW, "fr") == "Aujourd'hui"
    assert agenda.format_when("2026-11-14", NOW, "fr") == "Demain"
    assert agenda.format_when("2026-11-21", NOW, "fr") == "sam. 21 nov."


def test_when_is_converted_to_local_time():
    # 23:30 UTC on the 13th is 00:30 on the 14th at UTC+1: tomorrow.
    assert agenda.format_when("2026-11-13T23:30:00+00:00", NOW, "en") == "Tomorrow 00:30"


def test_when_already_started_reads_today():
    # A multi-day event that began yesterday is still on today.
    assert agenda.format_when("2026-11-12", NOW, "en") == "Today"
    assert agenda.format_when("2026-11-12T08:00:00+01:00", NOW, "en") == "Today"


def test_when_unreadable_start_is_empty():
    assert agenda.format_when("soon", NOW, "en") == ""
    assert agenda.format_when(None, NOW, "en") == ""


def test_temp_is_rounded_with_its_unit():
    assert agenda.format_temp(12.4, "°C") == "12 °C"
    assert agenda.format_temp(-0.4, "°C") == "0 °C"
    assert agenda.format_temp("7.6", "°F") == "8 °F"
    assert agenda.format_temp(None, "°C") is None
    assert agenda.format_temp("unknown", "°C") is None


def test_rain_within_the_hour():
    in_30 = (NOW + timedelta(minutes=30)).isoformat()
    in_2h = (NOW + timedelta(hours=2)).isoformat()
    current = (NOW - timedelta(minutes=20)).isoformat()
    assert agenda.rain_soon([{"datetime": in_30, "condition": "rainy"}], NOW)
    assert agenda.rain_soon([{"datetime": current, "condition": "pouring"}], NOW)
    assert agenda.rain_soon([{"datetime": in_30, "condition": "cloudy", "precipitation": 0.4}], NOW)
    assert not agenda.rain_soon([{"datetime": in_2h, "condition": "rainy"}], NOW)
    assert not agenda.rain_soon([{"datetime": in_30, "condition": "cloudy", "precipitation": 0}], NOW)
    assert not agenda.rain_soon([{"datetime": in_30, "condition": "snowy"}], NOW)


def test_rain_without_forecast_is_false():
    assert not agenda.rain_soon(None, NOW)
    assert not agenda.rain_soon([], NOW)
    assert not agenda.rain_soon([{"condition": "rainy"}], NOW)
    assert not agenda.rain_soon([{"datetime": "soon", "condition": "rainy"}], NOW)


def test_payload_full():
    payload = agenda.build_payload(
        events=[
            {"start": "2026-11-21T10:00:00+01:00", "summary": "Dentist"},
            {"start": "2026-11-13T17:00:00+01:00", "summary": "Swimming"},
        ],
        condition="partlycloudy",
        temperature=12.4,
        unit="°C",
        daily=[{"datetime": "2026-11-13T00:00:00+01:00", "temperature": 14.2, "templow": 3.6}],
        hourly=[{"datetime": (NOW + timedelta(minutes=10)).isoformat(), "condition": "rainy"}],
        language="en",
        now=NOW,
    )
    assert payload == {
        "weather": {
            "cond": "partlycloudy",
            "temp": "12 °C",
            "min": "4 °C",
            "max": "14 °C",
            "rain": True,
        },
        "events": [
            {"when": "Today 17:00", "what": "Swimming"},
            {"when": "Sat 21 Nov 10:00", "what": "Dentist"},
        ],
    }


def test_payload_keeps_three_events_sorted_with_all_day_first():
    events = [
        {"start": "2026-11-16T08:00:00+01:00", "summary": "D"},
        {"start": "2026-11-15T08:00:00+01:00", "summary": "C"},
        {"start": "2026-11-14T08:00:00+01:00", "summary": "B"},
        {"start": "2026-11-14", "summary": "A"},
    ]
    payload = agenda.build_payload(events=events, language="en", now=NOW)
    assert [e["what"] for e in payload["events"]] == ["A", "B", "C"]


def test_payload_without_weather_or_calendar():
    assert agenda.build_payload(language="en", now=NOW) == {}
    # A configured calendar with nothing planned still sends its empty list.
    assert agenda.build_payload(events=[], language="en", now=NOW) == {"events": []}
    # An unavailable weather entity sends no weather block.
    assert agenda.build_payload(condition="unavailable", language="en", now=NOW) == {}
    assert agenda.build_payload(condition="unknown", temperature=3, unit="°C", language="en", now=NOW) == {}


def test_payload_weather_without_forecast():
    payload = agenda.build_payload(condition="sunny", temperature=20, unit="°C", language="en", now=NOW)
    assert payload == {"weather": {"cond": "sunny", "temp": "20 °C"}}


def test_payload_daily_forecast_prefers_today():
    daily = [
        {"datetime": "2026-11-14T00:00:00+01:00", "temperature": 9, "templow": 1},
        {"datetime": "2026-11-13T00:00:00+01:00", "temperature": 14, "templow": 4},
    ]
    payload = agenda.build_payload(condition="sunny", unit="°C", daily=daily, language="en", now=NOW)
    assert payload["weather"]["max"] == "14 °C"
    assert payload["weather"]["min"] == "4 °C"


def test_payload_event_without_title_or_start_is_skipped():
    events = [
        {"start": "soon", "summary": "Broken"},
        {"start": "2026-11-14T08:00:00+01:00", "summary": ""},
        {"start": "2026-11-15T08:00:00+01:00", "summary": "Kept"},
    ]
    payload = agenda.build_payload(events=events, language="en", now=NOW)
    assert payload["events"] == [
        {"when": "Tomorrow 08:00", "what": ""},
        {"when": "Sun 15 Nov 08:00", "what": "Kept"},
    ]


def test_payload_long_title_is_cut_to_what_the_device_keeps():
    events = [{"start": "2026-11-14T08:00:00+01:00", "summary": "é" * 200}]
    payload = agenda.build_payload(events=events, language="fr", now=NOW)
    assert payload["events"][0]["what"] == "é" * agenda.MAX_WHAT_CHARS


def test_payload_daily_forecast_stamped_at_utc_midnight():
    # Seen from a zone west of UTC, UTC midnight of the 13th is still the 12th
    # in local time: the entry must be matched on the date as written.
    from datetime import timezone as tz
    west = datetime(2026, 11, 13, 9, 0, tzinfo=tz(timedelta(hours=-5)))
    daily = [
        {"datetime": "2026-11-13T00:00:00+00:00", "temperature": 14, "templow": 4},
        {"datetime": "2026-11-14T00:00:00+00:00", "temperature": 9, "templow": 1},
    ]
    payload = agenda.build_payload(condition="sunny", unit="°C", daily=daily, language="en", now=west)
    assert payload["weather"]["max"] == "14 °C"

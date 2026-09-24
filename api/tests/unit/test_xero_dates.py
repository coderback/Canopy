from datetime import UTC, datetime

from canopy.xero.client import parse_xero_date


def test_parses_xero_ms_json_date():
    assert parse_xero_date("/Date(1573755038314+0000)/") == datetime(
        2019, 11, 14, 18, 10, 38, 314000, tzinfo=UTC
    )


def test_unsuffixed_iso_is_utc_not_local_time():
    assert parse_xero_date("2026-01-02T03:04:05") == datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)


def test_offset_iso_is_converted_to_utc():
    assert parse_xero_date("2026-01-02T03:04:05+01:00") == datetime(2026, 1, 2, 2, 4, 5, tzinfo=UTC)


def test_empty_is_none():
    assert parse_xero_date(None) is None and parse_xero_date("") is None

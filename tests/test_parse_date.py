"""Tests for weekday-aware date parsing."""
from datetime import date

from app.scheduling import parse_date

SAT = date(2026, 5, 30)  # a Saturday


def test_today_tomorrow():
    assert parse_date("today", SAT) == SAT
    assert parse_date("tomorrow", SAT) == date(2026, 5, 31)


def test_iso():
    assert parse_date("2026-06-15", SAT) == date(2026, 6, 15)


def test_weekday_next_occurrence():
    assert parse_date("sunday", SAT) == date(2026, 5, 31)       # next day
    assert parse_date("this sunday", SAT) == date(2026, 5, 31)
    assert parse_date("tuesday", SAT) == date(2026, 6, 2)       # not 06-01!
    assert parse_date("saturday", SAT) == SAT                   # today is Saturday


def test_next_prefix_skips_a_week():
    assert parse_date("next saturday", SAT) == date(2026, 6, 6)


def test_arabic_weekday():
    assert parse_date("الأحد", SAT) == date(2026, 5, 31)        # Sunday


def test_garbage_returns_none():
    assert parse_date("someday", SAT) is None

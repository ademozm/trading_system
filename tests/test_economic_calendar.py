from datetime import datetime

import pandas as pd
import pytest

from analysis import economic_calendar as ec


def test_upcoming_fomc_dates_finds_known_date_in_range():
    ref = datetime(2026, 1, 20)  # 28 Ocak'a 8 gün kala
    result = ec.upcoming_fomc_dates(ref, lookahead_days=14)
    assert len(result) == 1
    assert result[0]["tarih"] == "2026-01-28"
    assert result[0]["kalan_gun"] == 8


def test_upcoming_fomc_dates_empty_when_far_away():
    ref = datetime(2026, 2, 1)  # bir sonraki FOMC 18 Mart, çok uzak
    result = ec.upcoming_fomc_dates(ref, lookahead_days=14)
    assert result == []


def test_upcoming_fomc_dates_includes_today():
    ref = datetime(2026, 1, 28)
    result = ec.upcoming_fomc_dates(ref, lookahead_days=14)
    assert len(result) == 1
    assert result[0]["kalan_gun"] == 0


def test_upcoming_recurring_events_finds_first_friday():
    ref = datetime(2026, 3, 1)
    result = ec.upcoming_recurring_events(ref, lookahead_days=14)
    nfp_events = [e for e in result if "İstihdam" in e["olay"]]
    assert len(nfp_events) >= 1
    # Mart 2026'nın ilk Cuma günü kontrolü (6 Mart 2026 bir Cuma)
    assert nfp_events[0]["tarih"] == "2026-03-06"


def test_get_calendar_returns_sorted_dataframe():
    ref = datetime(2026, 1, 20)
    df = ec.get_calendar(ref, lookahead_days=14)
    assert isinstance(df, pd.DataFrame)
    if len(df) > 1:
        assert df["kalan_gun"].is_monotonic_increasing


def test_get_calendar_empty_when_no_events():
    ref = datetime(2026, 1, 29)  # FOMC hemen geçti, NFP/CPI de aralıkta değilse boş olabilir
    df = ec.get_calendar(ref, lookahead_days=1)
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == ["tarih", "olay", "kalan_gun", "onem"]

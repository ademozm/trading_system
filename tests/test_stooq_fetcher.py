import io
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

from data_pipeline import stooq_fetcher


def test_map_to_stooq_special_map_commodities():
    assert stooq_fetcher.map_to_stooq("GC=F", "emtia") == "xauusd"
    assert stooq_fetcher.map_to_stooq("XAUUSD=X", "emtia") == "xauusd"
    assert stooq_fetcher.map_to_stooq("XAGUSD=X", "emtia") == "xagusd"
    assert stooq_fetcher.map_to_stooq("NG=F", "emtia") == "ng.f"


def test_map_to_stooq_unmapped_emtia_symbol_returns_none():
    """SPECIAL_MAP'te olmayan bir emtia sembolü için genel tahmin YAPILMAMALI
    (yanlış tahmin sessizce yanlış veriye yol açabilir)."""
    assert stooq_fetcher.map_to_stooq("XPTUSD=X", "emtia") is None


def test_map_to_stooq_bist_unsupported():
    assert stooq_fetcher.map_to_stooq("THYAO.IS", "bist") is None


def test_map_to_stooq_crypto():
    assert stooq_fetcher.map_to_stooq("BTC-USD", "crypto") == "btcusd"
    assert stooq_fetcher.map_to_stooq("ETH-USD", "crypto") == "ethusd"


def test_map_to_stooq_us_stock():
    assert stooq_fetcher.map_to_stooq("AAPL", "us") == "aapl.us"
    assert stooq_fetcher.map_to_stooq("BRK-B", "us") == "brk-b.us"


def test_map_to_stooq_unknown_market_returns_none():
    assert stooq_fetcher.map_to_stooq("XYZ", "unknown_market") is None


def _fake_csv():
    return (
        "Date,Open,High,Low,Close,Volume\n"
        "2026-08-25,100,102,99,101,1000\n"
        "2026-08-26,101,103,100,102,1200\n"
        "2026-08-27,102,104,101,103.5,1100\n"
    )


def test_fetch_stooq_parses_valid_csv():
    mock_resp = MagicMock()
    mock_resp.text = _fake_csv()
    mock_resp.raise_for_status = MagicMock()
    with patch("data_pipeline.stooq_fetcher.requests.get", return_value=mock_resp):
        df = stooq_fetcher.fetch_stooq("xauusd")
    assert df is not None
    assert len(df) == 3
    assert df["Close"].iloc[-1] == 103.5


def test_fetch_stooq_returns_none_for_no_data_response():
    mock_resp = MagicMock()
    mock_resp.text = "Brak danych (No data)"
    mock_resp.raise_for_status = MagicMock()
    with patch("data_pipeline.stooq_fetcher.requests.get", return_value=mock_resp):
        df = stooq_fetcher.fetch_stooq("fakesymbolxyz")
    assert df is None


def test_fetch_stooq_returns_none_on_network_error():
    with patch("data_pipeline.stooq_fetcher.requests.get", side_effect=Exception("network down")):
        df = stooq_fetcher.fetch_stooq("xauusd")
    assert df is None


def test_fetch_with_fallback_returns_none_when_unsupported_market():
    result = stooq_fetcher.fetch_with_fallback("THYAO.IS", "bist")
    assert result is None


def test_cross_validate_flags_large_discrepancy():
    mock_resp = MagicMock()
    mock_resp.text = _fake_csv()  # son kapanış 103.5
    mock_resp.raise_for_status = MagicMock()
    with patch("data_pipeline.stooq_fetcher.requests.get", return_value=mock_resp):
        result = stooq_fetcher.cross_validate("GC=F", "emtia", reference_close=150.0, tolerance_pct=3.0)
    assert result["supheli"] is True
    assert result["fark_yuzde"] > 3.0


def test_cross_validate_passes_close_match():
    mock_resp = MagicMock()
    mock_resp.text = _fake_csv()  # son kapanış 103.5
    mock_resp.raise_for_status = MagicMock()
    with patch("data_pipeline.stooq_fetcher.requests.get", return_value=mock_resp):
        result = stooq_fetcher.cross_validate("GC=F", "emtia", reference_close=103.6, tolerance_pct=3.0)
    assert result["supheli"] is False


def test_cross_validate_no_data_not_flagged_suspicious():
    with patch("data_pipeline.stooq_fetcher.requests.get", side_effect=Exception("down")):
        result = stooq_fetcher.cross_validate("GC=F", "emtia", reference_close=100.0)
    assert result["supheli"] is False
    assert result["stooq_close"] is None

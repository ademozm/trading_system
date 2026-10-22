import numpy as np
import pandas as pd
import pytest

from analysis import fundamentals


def test_fetch_one_returns_empty_dict_for_crypto():
    result = fundamentals.fetch_one("BTC-USD", "crypto")
    assert result == {}


def test_compute_fundamental_scores_handles_empty_input():
    result = fundamentals.compute_fundamental_scores({})
    assert result.empty or result["fundamental_score"].isna().all()


def test_compute_fundamental_scores_crypto_only_returns_nan():
    raw = {"BTC-USD": {}, "ETH-USD": {}}
    result = fundamentals.compute_fundamental_scores(raw)
    assert result.set_index("symbol")["fundamental_score"].isna().all()


def test_compute_fundamental_scores_cheap_stock_scores_higher_pe_component():
    raw = {
        "CHEAP": {"trailingPE": 8.0, "returnOnEquity": 0.25, "debtToEquity": 20,
                   "revenueGrowth": 0.15, "earningsGrowth": 0.20, "profitMargins": 0.18},
        "EXPENSIVE": {"trailingPE": 80.0, "returnOnEquity": 0.05, "debtToEquity": 200,
                      "revenueGrowth": -0.05, "earningsGrowth": -0.10, "profitMargins": 0.02},
    }
    result = fundamentals.compute_fundamental_scores(raw).set_index("symbol")
    assert result.loc["CHEAP", "fundamental_score"] > result.loc["EXPENSIVE", "fundamental_score"]


def test_compute_fundamental_scores_negative_pe_excluded_not_crashing():
    raw = {"LOSSMAKER": {"trailingPE": -15.0, "returnOnEquity": -0.3}, "OK": {"trailingPE": 12.0, "returnOnEquity": 0.1}}
    result = fundamentals.compute_fundamental_scores(raw)
    assert len(result) == 2
    assert not result["fundamental_score"].isna().all()


def test_fetch_one_includes_sector_and_industry():
    from unittest.mock import patch
    mock_info = {"trailingPE": 15.0, "sector": "Technology", "industry": "Software"}
    with patch("analysis.fundamentals.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = mock_info
        result = fundamentals.fetch_one("AAPL", "us")
    assert result["sector"] == "Technology"
    assert result["industry"] == "Software"


def test_fetch_one_sector_none_when_missing():
    from unittest.mock import patch
    with patch("analysis.fundamentals.yf.Ticker") as mock_ticker:
        mock_ticker.return_value.info = {"trailingPE": 15.0}
        result = fundamentals.fetch_one("AAPL", "us")
    assert result["sector"] is None


def test_compute_fundamental_scores_preserves_sector_column():
    raw = {"AAPL": {"trailingPE": 15.0, "sector": "Technology", "industry": "Software"}}
    result = fundamentals.compute_fundamental_scores(raw)
    assert "sector" in result.columns
    assert result.iloc[0]["sector"] == "Technology"

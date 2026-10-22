import numpy as np
import pandas as pd
import pytest

from analysis import filters


def _sample_df():
    return pd.DataFrame({
        "symbol": ["A", "B", "C", "D"],
        "signal": [1, -1, 1, -1],
        "composite_score": [0.5, -0.05, 0.1, -0.6],
        "marketCap": [2_000_000_000, 500_000_000, np.nan, 10_000_000_000],
        "trailingPE": [15.0, 90.0, np.nan, 25.0],
        "relative_volume": [1.5, 0.3, np.nan, 2.0],
        "mtf_confirmed": [True, False, np.nan, True],
    })


def test_apply_filters_empty_df_returns_empty():
    result, stats = filters.apply_filters(pd.DataFrame(), {})
    assert result.empty
    assert stats == {}


def test_min_composite_score_filters_weak_signals():
    df = _sample_df()
    result, stats = filters.apply_filters(df, {"min_composite_score": 0.15})
    assert set(result["symbol"]) == {"A", "D"}


def test_allowed_signals_only_buy():
    df = _sample_df()
    result, _ = filters.apply_filters(df, {"allowed_signals": [1]})
    assert set(result["signal"]) == {1}


def test_min_market_cap_keeps_nan_rows():
    df = _sample_df()
    result, _ = filters.apply_filters(df, {"min_market_cap": 1_000_000_000})
    # B (500M) elenir, C (NaN) korunur (kripto gibi veri eksik semboller haksız elenmemeli)
    assert "B" not in set(result["symbol"])
    assert "C" in set(result["symbol"])


def test_max_pe_excludes_expensive_but_keeps_missing():
    df = _sample_df()
    result, _ = filters.apply_filters(df, {"max_pe": 50})
    assert "B" not in set(result["symbol"])  # PE=90 elenir
    assert "C" in set(result["symbol"])      # PE yok, korunur
    assert "A" in set(result["symbol"])      # PE=15, geçer


def test_require_mtf_confirmation_excludes_false_keeps_nan():
    df = _sample_df()
    result, _ = filters.apply_filters(df, {"require_mtf_confirmation": True})
    assert "B" not in set(result["symbol"])  # False elenir
    assert "C" in set(result["symbol"])      # NaN korunur
    assert "A" in set(result["symbol"])      # True korunur


def test_filters_are_composable():
    df = _sample_df()
    result, stats = filters.apply_filters(df, {
        "allowed_signals": [1],
        "min_composite_score": 0.05,
    })
    assert set(result["symbol"]) == {"A", "C"}
    assert stats["başlangıç"] == 4
    assert stats["son"] == 2

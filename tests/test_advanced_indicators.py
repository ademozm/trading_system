import numpy as np
import pandas as pd
import pytest

from analysis import advanced_indicators as ai


def _make_df(n=200, seed=0, trend=1):
    rng = np.random.default_rng(seed)
    drift = 0.3 * trend
    close = 100 + np.cumsum(np.full(n, drift) + rng.normal(0, 0.5, n))
    high = close + np.abs(rng.normal(0, 0.3, n))
    low = close - np.abs(rng.normal(0, 0.3, n))
    volume = rng.integers(1000, 10000, n)
    idx = pd.date_range("2023-01-01", periods=n, freq="D")
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": volume}, index=idx)
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def test_fibonacci_levels_monotonic_for_uptrend():
    df = _make_df(trend=1, seed=1)
    levels = ai.fibonacci_levels(df)
    assert levels["trend_direction"] == "yukarı"
    # Yükselen trendde fib_0.0 = zirve, fib_1.0 = dip -> azalan sıra
    prices = [levels[f"fib_{r:.3f}"] for r in ai.FIB_RATIOS]
    assert prices == sorted(prices, reverse=True)


def test_fibonacci_levels_empty_for_short_series():
    df = _make_df(n=5)
    levels = ai.fibonacci_levels(df)
    assert levels == {}


def test_fibonacci_levels_empty_for_flat_price():
    idx = pd.date_range("2023-01-01", periods=50, freq="D")
    df = pd.DataFrame({"Open": 100.0, "High": 100.0, "Low": 100.0, "Close": 100.0, "Volume": 1000}, index=idx)
    levels = ai.fibonacci_levels(df)
    assert levels == {}


def test_nearest_fib_level_finds_closest():
    fib_levels = {"fib_0.000": 100.0, "fib_0.500": 90.0, "fib_1.000": 80.0}
    result = ai.nearest_fib_level(91.0, fib_levels)
    assert result["nearest_fib_level"] == "0.500"


def test_nearest_fib_level_handles_empty():
    result = ai.nearest_fib_level(100.0, {})
    assert result["nearest_fib_level"] is None


def test_find_pivots_detects_local_extremes():
    values = pd.Series([1, 2, 3, 10, 3, 2, 1, 2, 3, 4, 5, 1, 2, 3])
    highs, lows = ai.find_pivots(values, window=2)
    high_indices = [i for i, _ in highs]
    assert 3 in high_indices  # değer 10, belirgin bir zirve


def test_support_resistance_returns_lists():
    df = _make_df(n=200, seed=3)
    result = ai.support_resistance_levels(df)
    assert "support_levels" in result and "resistance_levels" in result
    assert isinstance(result["support_levels"], list)
    assert len(result["support_levels"]) <= 3


def test_support_resistance_empty_for_short_series():
    df = _make_df(n=10)
    result = ai.support_resistance_levels(df)
    assert result == {"support_levels": [], "resistance_levels": []}


def test_volume_profile_poc_within_price_range():
    df = _make_df(n=150, seed=4)
    result = ai.volume_profile(df)
    low, high = df["Low"].tail(100).min(), df["High"].tail(100).max()
    assert low <= result["poc_price"] <= high


def test_volume_profile_value_area_contains_poc():
    df = _make_df(n=150, seed=5)
    result = ai.volume_profile(df)
    if result["value_area_low"] is not None:
        assert result["value_area_low"] <= result["poc_price"] <= result["value_area_high"]


def test_volume_profile_empty_for_short_series():
    df = _make_df(n=5)
    result = ai.volume_profile(df)
    assert result["poc_price"] is None


def test_compute_all_returns_expected_keys():
    df = _make_df(n=200, seed=6)
    result = ai.compute_all(df)
    for key in ["fib_trend_direction", "nearest_fib_level", "support_levels",
                "resistance_levels", "poc_price", "value_area_low", "value_area_high"]:
        assert key in result

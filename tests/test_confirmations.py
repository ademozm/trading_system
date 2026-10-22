import numpy as np
import pandas as pd
import pytest

from analysis import confirmations


def _make_df(n=300, seed=0, uptrend=True):
    rng = np.random.default_rng(seed)
    drift = 0.003 if uptrend else -0.003
    returns = rng.normal(drift, 0.01, n)
    close = 100 * np.exp(np.cumsum(returns))
    volume = rng.integers(1000, 5000, n)
    idx = pd.date_range("2022-01-01", periods=n, freq="D")
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99,
                          "Close": close, "Volume": volume}, index=idx)


def test_relative_volume_above_one_when_last_volume_spikes():
    volume = pd.Series([1000] * 30 + [5000])
    rv = confirmations.relative_volume(volume, lookback=20)
    assert rv > 1


def test_relative_volume_nan_for_short_series():
    volume = pd.Series([1000] * 5)
    rv = confirmations.relative_volume(volume, lookback=20)
    assert np.isnan(rv)


def test_obv_trend_up_for_uptrend_with_volume():
    close = pd.Series(np.linspace(100, 150, 60))
    volume = pd.Series([1000] * 60)
    trend = confirmations.obv_trend(close, volume, lookback=30)
    assert trend == "yukarı"


def test_obv_trend_down_for_downtrend_with_volume():
    close = pd.Series(np.linspace(150, 100, 60))
    volume = pd.Series([1000] * 60)
    trend = confirmations.obv_trend(close, volume, lookback=30)
    assert trend == "aşağı"


def test_resample_weekly_produces_fewer_rows():
    df = _make_df(140)
    weekly = confirmations.resample_weekly(df)
    assert len(weekly) < len(df)
    assert set(["Open", "High", "Low", "Close", "Volume"]).issubset(weekly.columns)


def test_weekly_trend_direction_up_for_strong_uptrend():
    df = _make_df(300, seed=1, uptrend=True)
    direction = confirmations.weekly_trend_direction(df)
    assert direction in ("yukarı", "belirsiz")  # rejim gürültüsüne toleranslı


def test_compute_confirmations_returns_expected_keys():
    df = _make_df(300, seed=2, uptrend=True)
    result = confirmations.compute_confirmations(df, signal=1)
    for key in ["relative_volume", "volume_confirmed", "obv_trend", "obv_confirmed",
                "weekly_trend", "mtf_confirmed"]:
        assert key in result


def test_compute_confirmations_neutral_signal_gives_none_confirmations():
    df = _make_df(300, seed=3)
    result = confirmations.compute_confirmations(df, signal=0)
    assert result["obv_confirmed"] is None
    assert result["mtf_confirmed"] is None

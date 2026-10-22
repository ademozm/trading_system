import numpy as np
import pandas as pd
import pytest

from analysis.indicators import ema, rsi, atr, adx, bollinger_bands, macd


def make_ohlc(n=100, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 0.5, n))
    low = close - np.abs(rng.normal(0, 0.5, n))
    open_ = close + rng.normal(0, 0.3, n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close})
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def test_ema_converges_to_price_on_constant_series():
    s = pd.Series([50.0] * 30)
    result = ema(s, 10)
    assert abs(result.iloc[-1] - 50.0) < 1e-6


def test_rsi_is_bounded_between_0_and_100():
    df = make_ohlc()
    r = rsi(df["Close"])
    assert r.min() >= 0
    assert r.max() <= 100


def test_rsi_is_high_for_strictly_increasing_series():
    s = pd.Series(np.arange(1, 50, dtype=float))
    r = rsi(s)
    assert r.iloc[-1] > 90  # sürekli yükselen seri -> RSI yüksek olmalı


def test_rsi_is_low_for_strictly_decreasing_series():
    s = pd.Series(np.arange(50, 1, -1, dtype=float))
    r = rsi(s)
    assert r.iloc[-1] < 10


def test_atr_is_non_negative():
    df = make_ohlc()
    a = atr(df)
    assert (a.dropna() >= 0).all()


def test_atr_zero_for_flat_series():
    df = pd.DataFrame({
        "Open": [10.0] * 20, "High": [10.0] * 20,
        "Low": [10.0] * 20, "Close": [10.0] * 20,
    })
    a = atr(df)
    assert a.iloc[-1] < 1e-9


def test_adx_output_bounded_0_100():
    df = make_ohlc(n=200)
    adx_val, plus_di, minus_di = adx(df)
    assert adx_val.dropna().between(0, 100).all()


def test_bollinger_upper_always_above_lower():
    df = make_ohlc()
    upper, mid, lower = bollinger_bands(df["Close"])
    valid = upper.dropna().index.intersection(lower.dropna().index)
    assert (upper[valid] >= lower[valid]).all()


def test_macd_histogram_equals_line_minus_signal():
    df = make_ohlc()
    macd_line, signal_line, hist = macd(df["Close"])
    np.testing.assert_allclose(hist.values, (macd_line - signal_line).values, rtol=1e-9)


def test_indicators_handle_minimum_length_without_crash():
    df = make_ohlc(n=5)
    # Kısa seri kırılmamalı, sadece NaN/az anlamlı sonuç dönebilir
    ema(df["Close"], 10)
    rsi(df["Close"])
    atr(df)
    adx(df)

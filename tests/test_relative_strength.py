import numpy as np
import pandas as pd
import pytest

from analysis import relative_strength


def _series(prices, start="2023-01-01"):
    return pd.Series(prices, index=pd.date_range(start, periods=len(prices), freq="D"))


def test_relative_strength_positive_when_symbol_outperforms():
    n = 100
    symbol_close = _series(100 * (1.01 ** np.arange(n)))    # ~%1/gün
    bench_close = _series(100 * (1.001 ** np.arange(n)))    # ~%0.1/gün
    result = relative_strength.relative_strength(symbol_close, bench_close, lookback=60)
    assert result["relative_strength_pct"] > 0


def test_relative_strength_negative_when_symbol_underperforms():
    n = 100
    symbol_close = _series(100 * (1.001 ** np.arange(n)))
    bench_close = _series(100 * (1.01 ** np.arange(n)))
    result = relative_strength.relative_strength(symbol_close, bench_close, lookback=60)
    assert result["relative_strength_pct"] < 0


def test_relative_strength_nan_when_insufficient_history():
    symbol_close = _series([100, 101, 102])
    bench_close = _series([100, 101, 102])
    result = relative_strength.relative_strength(symbol_close, bench_close, lookback=60)
    assert np.isnan(result["relative_strength_pct"])


def test_compute_relative_strength_batch_self_benchmark_is_nan():
    universe_df = pd.DataFrame({"symbol": ["BTC-USD"], "market": ["crypto"], "name": ["Bitcoin"]})
    n = 100
    data = {"BTC-USD": pd.DataFrame({"Close": 100 * (1.01 ** np.arange(n))},
                                     index=pd.date_range("2023-01-01", periods=n, freq="D"))}
    benchmark_data = {"crypto": data["BTC-USD"]}
    result = relative_strength.compute_relative_strength_batch(data, universe_df, benchmark_data)
    assert result.iloc[0]["relative_strength_pct"] is None or np.isnan(result.iloc[0]["relative_strength_pct"])


def test_compute_relative_strength_batch_missing_benchmark_handled():
    universe_df = pd.DataFrame({"symbol": ["XYZ"], "market": ["unknown_market"], "name": ["Test"]})
    n = 100
    data = {"XYZ": pd.DataFrame({"Close": np.arange(100, 100 + n)},
                                 index=pd.date_range("2023-01-01", periods=n, freq="D"))}
    result = relative_strength.compute_relative_strength_batch(data, universe_df, {})
    assert np.isnan(result.iloc[0]["relative_strength_pct"])

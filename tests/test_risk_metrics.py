import numpy as np
import pandas as pd
import pytest

from analysis import risk_metrics


def _make_series(prices, start="2023-01-01"):
    return pd.Series(prices, index=pd.date_range(start, periods=len(prices), freq="D"))


def test_annualized_volatility_zero_for_constant_price():
    close = _make_series([100.0] * 100)
    vol = risk_metrics.annualized_volatility(close)
    assert vol == pytest.approx(0.0, abs=1e-9)


def test_annualized_volatility_positive_for_noisy_series():
    rng = np.random.default_rng(0)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    vol = risk_metrics.annualized_volatility(_make_series(prices))
    assert vol > 0


def test_max_drawdown_is_zero_for_monotonic_increase():
    close = _make_series(list(range(100, 200)))
    dd = risk_metrics.max_drawdown(close)
    assert dd == pytest.approx(0.0, abs=1e-9)


def test_max_drawdown_is_negative_after_decline():
    close = _make_series([100, 110, 120, 60, 70])
    dd = risk_metrics.max_drawdown(close)
    assert dd < 0
    assert dd == pytest.approx((60 / 120) - 1, rel=1e-6)


def test_week52_position_bounds():
    rng = np.random.default_rng(1)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    close = _make_series(prices)
    result = risk_metrics.week52_position(close)
    assert result["week52_low"] <= close.iloc[-1] <= result["week52_high"] * 1.0001
    assert 0 <= result["week52_range_position"] <= 1


def test_beta_of_series_with_itself_is_one():
    rng = np.random.default_rng(2)
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 200)))
    close = _make_series(prices)
    b = risk_metrics.beta(close, close)
    assert b == pytest.approx(1.0, abs=1e-6)


def test_beta_returns_nan_for_too_short_series():
    close = _make_series([100, 101, 102])
    b = risk_metrics.beta(close, close)
    assert np.isnan(b)


def test_compute_all_returns_expected_keys():
    rng = np.random.default_rng(3)
    n = 300
    prices = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, n)))
    df = pd.DataFrame({"Close": prices}, index=pd.date_range("2023-01-01", periods=n, freq="D"))
    bench = _make_series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, n))))
    result = risk_metrics.compute_all(df, bench)
    for key in ["volatility_annualized_pct", "max_drawdown_pct", "week52_high",
                "week52_low", "pct_from_52w_high", "pct_from_52w_low",
                "week52_range_position", "beta"]:
        assert key in result

import numpy as np
import pandas as pd
import pytest

from analysis.backtest import Backtester
from analysis.strategy import RegimeAdaptiveStrategy


def _make_trending_df(n=300, direction=1, seed=0):
    rng = np.random.default_rng(seed)
    drift = 0.4 * direction
    close = 100 + np.cumsum(np.full(n, drift) + rng.normal(0, 0.3, n))
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    open_ = close + rng.normal(0, 0.1, n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000},
                       index=pd.date_range("2023-01-01", periods=n, freq="D"))
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def _signals_df(n=300, direction=1, seed=0):
    strat = RegimeAdaptiveStrategy()
    return strat.generate_signals(_make_trending_df(n, direction, seed))


def test_backtester_runs_without_error_on_trending_data():
    bt = Backtester()
    result = bt.run(_signals_df())
    assert result.equity_curve is not None
    assert len(result.equity_curve) > 0


def test_backtester_empty_signal_df_returns_note():
    df = _make_trending_df(70)
    df["signal"] = 0
    df["stop_dist"] = 1.0
    df["target_dist"] = 2.0
    bt = Backtester()
    result = bt.run(df)
    assert result.metrics.get("trade_count") == 0
    assert "note" in result.metrics


def test_backtester_metrics_contain_new_fields():
    bt = Backtester()
    result = bt.run(_signals_df(n=400, seed=1))
    if result.metrics.get("trade_count", 0) > 0:
        for key in ["sortino_ratio", "profit_factor", "avg_win_pct", "avg_loss_pct",
                    "max_consecutive_wins", "max_consecutive_losses", "exposure_pct"]:
            assert key in result.metrics


def test_backtester_buy_hold_comparison_present():
    df = _signals_df(n=400, seed=2)
    bt = Backtester()
    result = bt.run(df)
    if result.metrics.get("trade_count", 0) > 0:
        assert "buy_hold_return_pct" in result.metrics
        assert "strateji_bh_farki_pct" in result.metrics


def test_backtester_exposure_pct_between_0_and_100():
    result = Backtester().run(_signals_df(n=300, seed=3))
    if "exposure_pct" in result.metrics:
        assert 0 <= result.metrics["exposure_pct"] <= 100


def test_max_consecutive_helper_basic():
    bt = Backtester()
    assert bt._max_consecutive([True, True, False, True, True, True], True) == 3
    assert bt._max_consecutive([True, False, False, False, True], False) == 3
    assert bt._max_consecutive([], True) == 0


def test_profit_factor_infinite_when_no_losses():
    bt = Backtester()
    # Sadece kazançlı, hiç kayıp olmayan bir senaryo simüle edelim
    from analysis.backtest import Trade
    trades = [Trade(pd.Timestamp("2023-01-01"), 100, 1, 95, 105, pd.Timestamp("2023-01-02"), 105, "target", 0.05)]
    equity = pd.Series([10000, 10500], index=pd.date_range("2023-01-01", periods=2))
    metrics = bt._compute_metrics(equity, trades)
    assert metrics["profit_factor"] == "sonsuz (hiç kayıp yok)"


def test_backtester_with_benchmark_close_no_crash():
    df = _signals_df(n=300, seed=4)
    benchmark = pd.Series(100 + np.cumsum(np.random.default_rng(5).normal(0, 0.5, 300)),
                           index=df.index)
    bt = Backtester()
    result = bt.run(df, benchmark_close=benchmark)
    assert result.equity_curve is not None

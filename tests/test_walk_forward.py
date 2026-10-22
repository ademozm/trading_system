import numpy as np
import pandas as pd
import pytest

from analysis import walk_forward as wf


def _make_regime_switching_df(n=800, seed=0):
    """Trend/yatay geçişleri olan gerçekçi sentetik veri (walk-forward'ın anlamlı çalışması için)."""
    rng = np.random.default_rng(seed)
    returns = []
    remaining = n
    while remaining > 0:
        block_len = min(rng.integers(40, 100), remaining)
        drift = rng.choice([0.002, -0.002, 0.0])
        vol = rng.uniform(0.008, 0.02)
        returns.extend(rng.normal(drift, vol, block_len))
        remaining -= block_len
    close = 100 * np.exp(np.cumsum(returns[:n]))
    high = close * (1 + np.abs(rng.normal(0, 0.004, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.004, n)))
    open_ = close * (1 + rng.normal(0, 0.002, n))
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000},
                       index=pd.date_range("2022-01-01", periods=n, freq="D"))
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


SMALL_GRID = {
    "adx_threshold": [20.0, 25.0],
    "rsi_oversold": [30.0],
    "rsi_overbought": [70.0],
    "atr_stop_mult": [2.0],
    "atr_target_mult": [3.0],
}


def test_generate_windows_basic():
    df = _make_regime_switching_df(500)
    windows = wf.generate_windows(df, train_days=200, test_days=50, step_days=50)
    assert len(windows) > 0
    for w in windows:
        assert len(w["train"]) == 200
        assert len(w["test"]) == 50
        # test penceresi train'den kronolojik olarak sonra gelmeli (look-ahead yok)
        assert w["test"].index[0] > w["train"].index[-1]


def test_generate_windows_insufficient_data_returns_empty():
    df = _make_regime_switching_df(100)
    windows = wf.generate_windows(df, train_days=200, test_days=50, step_days=50)
    assert windows == []


def test_param_combinations_count():
    grid = {"a": [1, 2], "b": [3, 4, 5]}
    combos = wf._param_combinations(grid)
    assert len(combos) == 6


def test_score_penalizes_low_trade_count():
    assert wf._score({"trade_count": 1, "sharpe_ratio": 5.0}) < 0
    assert wf._score({"trade_count": 10, "sharpe_ratio": 1.5}) == 1.5


def test_optimize_window_returns_valid_params():
    df = _make_regime_switching_df(300)
    best_params, best_metrics = wf.optimize_window(df, SMALL_GRID)
    if best_params is not None:  # yetersiz işlem varsa None dönebilir, bu geçerli bir durum
        assert "adx_threshold" in best_params
        assert best_params["adx_threshold"] in [20.0, 25.0]


def test_run_walk_forward_end_to_end():
    df = _make_regime_switching_df(800)
    result = wf.run_walk_forward(df, param_grid=SMALL_GRID, train_days=250, test_days=60, step_days=60)
    assert "window_results" in result
    assert "recommended_params" in result
    assert "summary" in result
    assert isinstance(result["overfitting_warning"], bool)


def test_run_walk_forward_insufficient_data():
    df = _make_regime_switching_df(100)
    result = wf.run_walk_forward(df, param_grid=SMALL_GRID, train_days=250, test_days=60)
    assert result["window_results"].empty
    assert result["recommended_params"] == {}


def test_run_walk_forward_window_results_have_expected_columns():
    df = _make_regime_switching_df(800)
    result = wf.run_walk_forward(df, param_grid=SMALL_GRID, train_days=250, test_days=60, step_days=60)
    if not result["window_results"].empty:
        for col in ["pencere", "train_sharpe", "test_sharpe", "test_getiri_pct"]:
            assert col in result["window_results"].columns


def test_run_walk_forward_recommended_params_within_grid_range():
    df = _make_regime_switching_df(800)
    result = wf.run_walk_forward(df, param_grid=SMALL_GRID, train_days=250, test_days=60, step_days=60)
    if result["recommended_params"]:
        assert 20.0 <= result["recommended_params"]["adx_threshold"] <= 25.0

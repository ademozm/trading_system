import numpy as np
import pandas as pd
import pytest

from analysis import grid_strategy


def _make_range_df(n=80, low=90, high=110, seed=0):
    rng = np.random.default_rng(seed)
    close = rng.uniform(low, high, n)
    high_col = close + rng.uniform(0, 2, n)
    low_col = close - rng.uniform(0, 2, n)
    return pd.DataFrame({"Open": close, "High": high_col, "Low": low_col, "Close": close, "Volume": 1000})


def test_suggest_grid_rejects_trend_regime():
    df = _make_range_df()
    result = grid_strategy.suggest_grid(df, regime="trend", total_position_value=1000)
    assert result["uygun_mu"] is False
    assert result["seviyeler"] == []


def test_suggest_grid_accepts_range_regime():
    df = _make_range_df()
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000, num_levels=5)
    assert result["uygun_mu"] is True
    assert len(result["seviyeler"]) == 5


def test_suggest_grid_levels_are_increasing():
    df = _make_range_df()
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000, num_levels=4)
    prices = [lvl["al_fiyati"] for lvl in result["seviyeler"]]
    assert prices == sorted(prices)


def test_suggest_grid_sell_above_buy_for_each_level():
    df = _make_range_df()
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000, num_levels=3)
    for lvl in result["seviyeler"]:
        assert lvl["sat_fiyati"] > lvl["al_fiyati"]
        assert lvl["beklenen_kar_pct"] > 0


def test_suggest_grid_total_value_distributed_across_levels():
    df = _make_range_df()
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000, num_levels=5)
    total_value = sum(lvl["adet"] * lvl["al_fiyati"] for lvl in result["seviyeler"])
    assert total_value == pytest.approx(1000, rel=0.01)


def test_suggest_grid_insufficient_data():
    df = _make_range_df(n=3)
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000)
    assert result["uygun_mu"] is False


def test_suggest_grid_flat_price_range_rejected():
    df = pd.DataFrame({
        "Open": [100] * 80, "High": [100] * 80, "Low": [100] * 80,
        "Close": [100] * 80, "Volume": [1000] * 80,
    })
    result = grid_strategy.suggest_grid(df, regime="range", total_position_value=1000)
    assert result["uygun_mu"] is False

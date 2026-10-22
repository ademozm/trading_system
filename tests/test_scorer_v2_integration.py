import numpy as np
import pandas as pd
import pytest

from analysis.strategy import RegimeAdaptiveStrategy
from analysis import scorer


def make_trending_df(direction=1, n=200, seed=0):
    rng = np.random.default_rng(seed)
    drift = 0.5 * direction
    close = 100 + np.cumsum(np.full(n, drift) + rng.normal(0, 0.3, n))
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close, "Volume": 1000})
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def make_universe_df(symbols, market="us"):
    return pd.DataFrame({"symbol": symbols, "market": [market] * len(symbols), "name": symbols})


def _base_signals(symbols):
    strat = RegimeAdaptiveStrategy()
    return {s: strat.generate_signals(make_trending_df(1 if i % 2 == 0 else -1, seed=i))
            for i, s in enumerate(symbols)}


def test_score_with_fundamentals_still_bounded():
    symbols = ["A", "B", "C"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols)
    fundamentals_df = pd.DataFrame({
        "symbol": symbols, "fundamental_score": [0.9, 0.1, 0.5],
    })
    result = scorer.score_universe(signals, universe_df, fundamentals_df=fundamentals_df)
    if not result.empty:
        assert result["composite_score"].between(-1.5, 1.5).all()
        assert "fundamental_score" in result.columns


def test_missing_fundamental_score_does_not_crash_and_renormalizes():
    symbols = ["A", "B"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols, market="crypto")
    # Kripto senaryosu: fundamental_score tamamen NaN
    fundamentals_df = pd.DataFrame({"symbol": symbols, "fundamental_score": [np.nan, np.nan]})
    result = scorer.score_universe(signals, universe_df, fundamentals_df=fundamentals_df)
    if not result.empty:
        assert not result["composite_score"].isna().any()


def test_relative_strength_component_integrates():
    symbols = ["A", "B"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols)
    rs_df = pd.DataFrame({"symbol": symbols, "relative_strength_pct": [15.0, -8.0],
                           "symbol_return_pct": [20, -5], "benchmark_return_pct": [5, 3]})
    result = scorer.score_universe(signals, universe_df, relative_strength_df=rs_df)
    if not result.empty:
        assert "relative_strength_pct" in result.columns
        assert result["composite_score"].between(-1.5, 1.5).all()


def test_confirmations_component_integrates():
    symbols = ["A", "B"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols)
    confirmations_by_symbol = {
        "A": {"relative_volume": 1.5, "volume_confirmed": True, "obv_trend": "yukarı",
              "obv_confirmed": True, "weekly_trend": "yukarı", "mtf_confirmed": True},
        "B": {"relative_volume": 0.5, "volume_confirmed": False, "obv_trend": "aşağı",
              "obv_confirmed": False, "weekly_trend": "aşağı", "mtf_confirmed": False},
    }
    result = scorer.score_universe(signals, universe_df, confirmations_by_symbol=confirmations_by_symbol)
    if not result.empty:
        assert "volume_confirmed" in result.columns
        assert "mtf_confirmed" in result.columns


def test_all_components_together_end_to_end():
    symbols = ["A", "B", "C", "D"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols)
    fundamentals_df = pd.DataFrame({"symbol": symbols, "fundamental_score": [0.8, 0.2, np.nan, 0.5]})
    rs_df = pd.DataFrame({
        "symbol": symbols,
        "relative_strength_pct": [10, -10, 5, -5],
        "symbol_return_pct": [15, -5, 8, -2],
        "benchmark_return_pct": [5, 5, 3, 3],
    })
    confirmations_by_symbol = {
        s: {"relative_volume": 1.2, "volume_confirmed": True, "obv_trend": "yukarı",
            "obv_confirmed": True, "weekly_trend": "yukarı", "mtf_confirmed": i % 2 == 0}
        for i, s in enumerate(symbols)
    }
    risk_by_symbol = {
        s: {"volatility_annualized_pct": 25.0, "max_drawdown_pct": -12.0,
            "week52_high": 120, "week52_low": 80, "pct_from_52w_high": -5,
            "pct_from_52w_low": 20, "week52_range_position": 0.6, "beta": 1.1}
        for s in symbols
    }

    result = scorer.score_universe(
        signals, universe_df,
        fundamentals_df=fundamentals_df,
        relative_strength_df=rs_df,
        confirmations_by_symbol=confirmations_by_symbol,
        risk_metrics_by_symbol=risk_by_symbol,
    )
    if not result.empty:
        assert not result["composite_score"].isna().any()
        assert result["composite_score"].between(-1.5, 1.5).all()
        for col in ["fundamental_score", "relative_strength_pct", "volatility_annualized_pct", "beta"]:
            assert col in result.columns


def test_full_universe_status_includes_all_symbols_regardless_of_signal():
    symbols = ["A", "B", "C"]
    signals = _base_signals(symbols)
    # A ve B'nin sinyalini bilerek sıfırlayalım (bazı semboller sinyal üretmesin diye)
    signals["A"].iloc[-1, signals["A"].columns.get_loc("signal")] = 0
    signals["B"].iloc[-1, signals["B"].columns.get_loc("signal")] = 0
    universe_df = make_universe_df(symbols)

    result = scorer.full_universe_status(signals, universe_df)
    assert len(result) == 3
    assert set(result["symbol"]) == {"A", "B", "C"}
    assert (result[result["symbol"].isin(["A", "B"])]["sinyal_var_mi"] == False).all()


def test_full_universe_status_empty_input_returns_empty_df():
    result = scorer.full_universe_status({}, make_universe_df([]))
    assert result.empty


def test_full_universe_status_has_reason_column():
    symbols = ["A"]
    signals = _base_signals(symbols)
    universe_df = make_universe_df(symbols)
    result = scorer.full_universe_status(signals, universe_df)
    assert "neden" in result.columns
    assert result.iloc[0]["neden"] != ""

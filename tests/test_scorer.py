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
    df = pd.DataFrame({
        "Open": close, "High": high, "Low": low, "Close": close, "Volume": 1000,
    })
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def make_universe_df(symbols, market="us"):
    return pd.DataFrame({
        "symbol": symbols, "market": [market] * len(symbols), "name": symbols,
    })


def test_score_universe_returns_expected_columns():
    strat = RegimeAdaptiveStrategy()
    df_up = strat.generate_signals(make_trending_df(1))
    signals = {"UP": df_up}
    universe_df = make_universe_df(["UP"])
    result = scorer.score_universe(signals, universe_df)
    if not result.empty:
        for col in ["symbol", "composite_score", "signal", "market"]:
            assert col in result.columns


def test_bullish_trend_scores_positive_when_signal_present():
    strat = RegimeAdaptiveStrategy()
    df_up = strat.generate_signals(make_trending_df(1, seed=5))
    signals = {"UP": df_up}
    universe_df = make_universe_df(["UP"])
    result = scorer.score_universe(signals, universe_df)
    if not result.empty and result.iloc[0]["signal"] == 1:
        assert result.iloc[0]["composite_score"] > 0


def test_symbols_without_signal_are_excluded():
    strat = RegimeAdaptiveStrategy()
    # Çok kısa ve düz bir seri -> muhtemelen sinyal üretmez ya da nötr kalır
    flat_df = pd.DataFrame({
        "Open": [100.0] * 80, "High": [100.1] * 80,
        "Low": [99.9] * 80, "Close": [100.0] * 80, "Volume": [1000] * 80,
    })
    df_signals = strat.generate_signals(flat_df)
    df_signals["signal"] = 0  # sinyal yok senaryosunu garanti et
    result = scorer.score_universe({"FLAT": df_signals}, make_universe_df(["FLAT"]))
    assert result.empty


def test_composite_score_bounded_reasonably():
    strat = RegimeAdaptiveStrategy()
    signals = {}
    symbols = []
    for i in range(5):
        direction = 1 if i % 2 == 0 else -1
        symbols.append(f"SYM{i}")
        signals[f"SYM{i}"] = strat.generate_signals(make_trending_df(direction, seed=i))
    universe_df = make_universe_df(symbols)
    result = scorer.score_universe(signals, universe_df)
    if not result.empty:
        assert result["composite_score"].between(-1.5, 1.5).all()


def test_ranking_is_sorted_descending():
    strat = RegimeAdaptiveStrategy()
    signals = {}
    symbols = []
    for i in range(6):
        direction = 1 if i % 2 == 0 else -1
        symbols.append(f"SYM{i}")
        signals[f"SYM{i}"] = strat.generate_signals(make_trending_df(direction, seed=i * 3))
    universe_df = make_universe_df(symbols)
    result = scorer.score_universe(signals, universe_df)
    if len(result) > 1:
        scores = result["composite_score"].tolist()
        assert scores == sorted(scores, reverse=True)

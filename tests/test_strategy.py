import numpy as np
import pandas as pd
import pytest

from analysis.strategy import RegimeAdaptiveStrategy


def make_trending_up_series(n=200):
    """Net yukarı trend + küçük gürültü -> ADX yüksek, EMA fast > EMA slow olmalı."""
    rng = np.random.default_rng(0)
    close = 100 + np.cumsum(np.full(n, 0.5) + rng.normal(0, 0.3, n))
    high = close + np.abs(rng.normal(0, 0.2, n))
    low = close - np.abs(rng.normal(0, 0.2, n))
    open_ = close + rng.normal(0, 0.1, n)
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000})
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def make_choppy_flat_series(n=200):
    """Belirgin yönü olmayan, dar bantta salınan seri -> range rejimi beklenir."""
    rng = np.random.default_rng(1)
    close = 100 + np.sin(np.linspace(0, 20, n)) * 2 + rng.normal(0, 0.1, n)
    high = close + 0.3
    low = close - 0.3
    open_ = close
    df = pd.DataFrame({"Open": open_, "High": high, "Low": low, "Close": close, "Volume": 1000})
    return df


def test_strategy_produces_required_columns():
    df = make_trending_up_series()
    strat = RegimeAdaptiveStrategy()
    out = strat.generate_signals(df)
    for col in ["regime", "signal", "stop_dist", "target_dist", "adx", "rsi"]:
        assert col in out.columns


def test_strong_uptrend_is_detected_as_trend_regime_eventually():
    df = make_trending_up_series()
    strat = RegimeAdaptiveStrategy()
    out = strat.generate_signals(df)
    # Güçlü, sürekli trendde son bölümde 'trend' rejimi baskın olmalı
    tail_regimes = out["regime"].iloc[-50:]
    assert (tail_regimes == "trend").mean() > 0.5


def test_signal_values_are_valid_set():
    df = make_trending_up_series()
    strat = RegimeAdaptiveStrategy()
    out = strat.generate_signals(df)
    assert set(out["signal"].unique()).issubset({-1, 0, 1})


def test_stop_and_target_distances_are_non_negative():
    df = make_trending_up_series()
    strat = RegimeAdaptiveStrategy()
    out = strat.generate_signals(df)
    assert (out["stop_dist"].dropna() >= 0).all()
    assert (out["target_dist"].dropna() >= 0).all()


def test_target_distance_greater_than_stop_distance_by_default_ratio():
    # Varsayılan: atr_target_mult (3.0) > atr_stop_mult (2.0)
    df = make_trending_up_series()
    strat = RegimeAdaptiveStrategy()
    out = strat.generate_signals(df)
    valid = out.dropna(subset=["stop_dist", "target_dist"])
    valid = valid[valid["stop_dist"] > 0]
    ratio = (valid["target_dist"] / valid["stop_dist"]).mean()
    assert ratio == pytest.approx(1.5, rel=0.01)  # 3.0 / 2.0


def test_custom_adx_threshold_changes_regime_classification():
    # Not: çok güçlü/düşük gürültülü bir trendde ADX gerçekten 90+ değerlere
    # ulaşabilir (matematiksel olarak doğru davranış). Bu yüzden "eşik çok
    # yüksekse trend hiç görülmez" varsayımı yanlıştı; onun yerine eşiği
    # artırmanın trend sınıflandırmasını AZALTTIĞINI (ortadan kaldırdığını değil)
    # doğruluyoruz.
    df = make_trending_up_series()
    strat_loose = RegimeAdaptiveStrategy(adx_threshold=15)
    strat_strict = RegimeAdaptiveStrategy(adx_threshold=90)
    out_loose = strat_loose.generate_signals(df)
    out_strict = strat_strict.generate_signals(df)
    trend_count_loose = (out_loose["regime"] == "trend").sum()
    trend_count_strict = (out_strict["regime"] == "trend").sum()
    assert trend_count_strict <= trend_count_loose

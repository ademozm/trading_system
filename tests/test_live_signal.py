"""
tests/test_live_signal.py
============================
signals/classic/live_signal.py'nin saf (duckdb'siz) kısmını doğrular:
_detect_crossover_signal. compute_live_classic_signal (OHLCVStore/duckdb
gerektiren sarmalayıcı) burada test edilmemiştir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.classic.live_signal import _detect_crossover_signal


def _make_df(closes: list[float]) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
            "open": closes,
            "high": closes,
            "low": closes,
            "close": closes,
            "volume": np.full(n, 100.0),
        }
    )


def test_returns_none_when_insufficient_data() -> None:
    df = _make_df([100.0] * 10)  # slow_period=30 gerektirir, sadece 10 satır var
    assert _detect_crossover_signal(df, "BTC/USDT", fast_period=10, slow_period=30) is None


def test_detects_golden_cross_as_long() -> None:
    """
    Fiyat düz kalıp SON BARDA aniden yükselirse: kısa SMA uzun SMA'yı TAM
    O ANDA yukarı keser -> "long" sinyali beklenir. (Kesişim yalnızca
    ANLIK geçiş barında tespit edilir — backtrader'ın CrossOver'ı gibi;
    trend zaten kurulmuşsa "eski haber" sayılıp sinyal ÜRETİLMEZ.)
    """
    flat = [100.0] * 30
    df = _make_df(flat + [102.0])  # tek barlık ani yükseliş -> kesişim tam son barda

    signal = _detect_crossover_signal(df, "BTC/USDT", fast_period=5, slow_period=20)
    assert signal is not None
    assert signal.side == "long"
    assert signal.source == "classic_sma"
    assert 0.0 < signal.confidence <= 0.9


def test_detects_death_cross_as_short() -> None:
    """Fiyat düz kalıp son barda aniden düşerse: "short" sinyali beklenir."""
    flat = [100.0] * 30
    df = _make_df(flat + [98.0])

    signal = _detect_crossover_signal(df, "BTC/USDT", fast_period=5, slow_period=20)
    assert signal is not None
    assert signal.side == "short"


def test_returns_none_when_no_crossover() -> None:
    """Fiyat sürekli düz kalırsa (hiç kesişim yoksa) None dönmeli."""
    df = _make_df([100.0] * 50)
    assert _detect_crossover_signal(df, "BTC/USDT", fast_period=5, slow_period=20) is None


def test_returns_none_when_trend_already_established() -> None:
    """
    KRİTİK: Kesişim birkaç bar ÖNCE olmuşsa (trend zaten kurulmuşsa),
    son barda "eski haber" için tekrar sinyal ÜRETİLMEMELİ — sadece
    kesişimin GERÇEKLEŞTİĞİ o tek bar sinyal üretir.
    """
    flat = [100.0] * 30
    rising = [100.0 + i * 2 for i in range(1, 15)]  # kesişim ortalarda bir yerde oldu, son bar değil
    df = _make_df(flat + rising)
    assert _detect_crossover_signal(df, "BTC/USDT", fast_period=5, slow_period=20) is None


def test_confidence_stronger_crossover_higher_score() -> None:
    """Daha güçlü bir kesişim (fiyat daha büyük bir sıçrama yaparsa) daha yüksek güven skoru vermeli."""
    flat = [100.0] * 30

    weak_signal = _detect_crossover_signal(_make_df(flat + [100.3]), "BTC/USDT", fast_period=5, slow_period=20)
    strong_signal = _detect_crossover_signal(_make_df(flat + [115.0]), "BTC/USDT", fast_period=5, slow_period=20)

    assert weak_signal is not None and strong_signal is not None
    assert strong_signal.confidence >= weak_signal.confidence


def test_rationale_mentions_periods_and_values() -> None:
    flat = [100.0] * 30
    signal = _detect_crossover_signal(_make_df(flat + [102.0]), "BTC/USDT", fast_period=5, slow_period=20)
    assert signal is not None
    assert "SMA5/20" in signal.rationale
    assert "golden cross" in signal.rationale

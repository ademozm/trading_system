"""
Katman 3a — Canlı SMA Sinyali (main.py'nin kullandığı GERÇEK fonksiyon)
============================================================================
main.py bu dosya yazılana kadar hiçbir zaman gerçek bir klasik sinyal
hesaplamıyordu — `get_classic_signal_placeholder()` piyasada ne olursa
olsun hep sabit "long, confidence=0.6" döndürüyordu. Bu, backtrader tabanlı
SmaCrossStrategy (backtest/run_backtest.py) ile AYNI mantığı (kısa SMA uzun
SMA'yı yukarı/aşağı keserse) ama backtrader'a bağımlı olmadan,
data_layer.storage'daki en güncel veriden hesaplar.

Tasarım — neden iki fonksiyon var: `_detect_crossover_signal` saf pandas
mantığıdır (bir DataFrame verildiğinde kesişim var mı diye bakar), veri
yüklemesinden AYRILMIŞTIR — bu sayede duckdb (OHLCVStore'un bağımlılığı)
kurulu olmayan bir ortamda bile test edilebilir (bkz.
tests/test_live_signal.py). `compute_live_classic_signal` ise gerçek
kullanım için ikisini birleştiren ince bir sarmalayıcıdır.
"""

from __future__ import annotations

import logging
from typing import Optional

import pandas as pd

from signals.aggregator import RawSignal

logger = logging.getLogger(__name__)


def _detect_crossover_signal(
    df: pd.DataFrame,
    symbol: str,
    fast_period: int = 10,
    slow_period: int = 30,
) -> Optional[RawSignal]:
    """
    Saf hesaplama: `df` (en az `close` sütunu olan, zaman sırasına göre
    sıralı bir OHLCV DataFrame'i) üzerinde son iki bar arasında bir SMA
    kesişimi olup olmadığına bakar. Kesişim yoksa (veya veri yetersizse)
    None döner — "belirsizse işlem yapma" ilkesi burada da geçerli.
    """
    if len(df) < slow_period + 2:
        logger.warning(
            "%s için yeterli veri yok (%d satır, en az %d gerekli), klasik sinyal atlanıyor.",
            symbol, len(df), slow_period + 2,
        )
        return None

    close = df["close"]
    fast_sma = close.rolling(window=fast_period).mean()
    slow_sma = close.rolling(window=slow_period).mean()

    prev_fast, prev_slow = fast_sma.iloc[-2], slow_sma.iloc[-2]
    curr_fast, curr_slow = fast_sma.iloc[-1], slow_sma.iloc[-1]

    if pd.isna(prev_fast) or pd.isna(prev_slow) or pd.isna(curr_fast) or pd.isna(curr_slow):
        return None

    if prev_fast <= prev_slow and curr_fast > curr_slow:
        side = "long"
        description = "yukarı (golden cross)"
    elif prev_fast >= prev_slow and curr_fast < curr_slow:
        side = "short"
        description = "aşağı (death cross)"
    else:
        return None  # kesişim yok, sinyal üretme

    # Güven skoru: kesişimin "gücü" — fast/slow farkının slow'a oranı,
    # 0.5-0.9 aralığına kabaca ölçeklenir (0.5 = zayıf kesişim, 0.9 = güçlü).
    strength = abs(curr_fast - curr_slow) / curr_slow if curr_slow else 0.0
    confidence = min(0.9, 0.5 + strength * 10)

    return RawSignal(
        source="classic_sma",
        symbol=symbol,
        side=side,
        confidence=round(confidence, 4),
        rationale=(
            f"SMA{fast_period}/{slow_period} kesişimi: {description} "
            f"(fast={curr_fast:.4f}, slow={curr_slow:.4f})."
        ),
    )


def compute_live_classic_signal(
    symbol: str,
    timeframe: str = "1h",
    fast_period: int = 10,
    slow_period: int = 30,
    ohlcv_dir: str = "data/ohlcv",
) -> Optional[RawSignal]:
    """
    data_layer.storage'daki en güncel veriyi okuyup `_detect_crossover_signal`'a
    verir. Veri hiç yoksa (henüz indirilmemişse) None döner — ml_signal.py
    ve llm_agents ile aynı zarif bozulma deseni.
    """
    from data_layer.storage import OHLCVStore  # gecikmeli import: duckdb sadece burada gerekir

    store = OHLCVStore(data_dir=ohlcv_dir)
    try:
        df = store.load(symbol, timeframe)
    except FileNotFoundError:
        logger.warning("%s / %s için veri yok, klasik sinyal atlanıyor.", symbol, timeframe)
        return None

    return _detect_crossover_signal(df, symbol, fast_period, slow_period)

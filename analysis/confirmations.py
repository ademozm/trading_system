"""
İki bağımsız teyit katmanı:

1. Hacim analizi: bir fiyat hareketinin "gerçek" olup olmadığının en
   basit göstergelerinden biri hacimdir. Düşük hacimle olan bir kırılım
   güvenilmezdir.

2. Çoklu zaman dilimi (multi-timeframe) teyidi: günlük grafikte AL sinyali
   gelse bile, haftalık grafik net bir düşüş trendindeyse bu sinyal
   şüphelidir ("büyük resme karşı işlem"). Bu modül günlük veriyi haftalığa
   yeniden örnekleyip (resample) iki zaman diliminin yönünün uyuşup
   uyuşmadığını kontrol eder — ayrı bir veri çekimi GEREKTİRMEZ, elimizdeki
   günlük veriden türetilir.
"""
import numpy as np
import pandas as pd

from analysis.indicators import ema, adx


def relative_volume(volume: pd.Series, lookback: int = 20) -> float:
    """Son hacmin, önceki N günlük ortalama hacme oranı. >1 = ortalama üstü ilgi."""
    if len(volume) <= lookback:
        return np.nan
    avg_vol = volume.iloc[-lookback - 1:-1].mean()
    return volume.iloc[-1] / avg_vol if avg_vol > 0 else np.nan


def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
    """On-Balance Volume: fiyat yönüyle işaretlenmiş kümülatif hacim."""
    direction = np.sign(close.diff()).fillna(0)
    return (direction * volume).cumsum()


def obv_trend(close: pd.Series, volume: pd.Series, lookback: int = 20) -> str:
    """Son N günde OBV yükseliyorsa 'yukarı', düşüyorsa 'aşağı', düzse 'yatay'."""
    obv_series = obv(close, volume)
    if len(obv_series) <= lookback:
        return "belirsiz"
    change = obv_series.iloc[-1] - obv_series.iloc[-lookback - 1]
    threshold = obv_series.tail(lookback).abs().mean() * 0.1
    if change > threshold:
        return "yukarı"
    elif change < -threshold:
        return "aşağı"
    return "yatay"


def resample_weekly(df: pd.DataFrame) -> pd.DataFrame:
    weekly = df.resample("W").agg({
        "Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum",
    }).dropna()
    return weekly


def weekly_trend_direction(df: pd.DataFrame, ema_fast: int = 12, ema_slow: int = 26) -> str:
    """Haftalık grafikte EMA(fast) vs EMA(slow) konumuna göre 'yukarı'/'aşağı'/'belirsiz'."""
    weekly = resample_weekly(df)
    if len(weekly) < ema_slow + 2:
        return "belirsiz"
    fast = ema(weekly["Close"], ema_fast)
    slow = ema(weekly["Close"], ema_slow)
    if fast.iloc[-1] > slow.iloc[-1]:
        return "yukarı"
    elif fast.iloc[-1] < slow.iloc[-1]:
        return "aşağı"
    return "belirsiz"


def compute_confirmations(df: pd.DataFrame, signal: int) -> dict:
    """
    df: RegimeAdaptiveStrategy.generate_signals() çıktısı (Close, Volume, signal içerir)
    signal: o sembol için üretilen son sinyal (1, -1 veya 0)
    """
    rel_vol = relative_volume(df["Volume"])
    volume_confirmed = bool(rel_vol > 1.2) if not np.isnan(rel_vol) else None

    obv_dir = obv_trend(df["Close"], df["Volume"])
    obv_confirmed = None
    if signal == 1:
        obv_confirmed = obv_dir == "yukarı"
    elif signal == -1:
        obv_confirmed = obv_dir == "aşağı"

    weekly_dir = weekly_trend_direction(df)
    mtf_confirmed = None
    if signal == 1:
        mtf_confirmed = weekly_dir == "yukarı"
    elif signal == -1:
        mtf_confirmed = weekly_dir == "aşağı"

    return {
        "relative_volume": rel_vol,
        "volume_confirmed": volume_confirmed,
        "obv_trend": obv_dir,
        "obv_confirmed": obv_confirmed,
        "weekly_trend": weekly_dir,
        "mtf_confirmed": mtf_confirmed,
    }

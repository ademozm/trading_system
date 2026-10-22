"""
Teknik indikatörler - sadece pandas/numpy ile, harici bağımlılık yok.
Tüm fonksiyonlar bir OHLCV DataFrame'i (columns: Open, High, Low, Close, Volume) alır.
"""
import numpy as np
import pandas as pd


def ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()

    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi_val = 100 - (100 / (1 + rs))

    # avg_loss == 0 ve avg_gain > 0 -> sürekli yükseliş, RSI = 100 olmalı (NaN değil)
    no_loss_mask = (avg_loss == 0) & (avg_gain > 0)
    rsi_val = rsi_val.where(~no_loss_mask, 100.0)

    # Hem kazanç hem kayıp sıfır -> fiyat hiç değişmemiş, RSI = 50 (nötr)
    flat_mask = (avg_loss == 0) & (avg_gain == 0)
    rsi_val = rsi_val.where(~flat_mask, 50.0)

    return rsi_val


def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs(),
    ], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False).mean()


def adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high, low, close = df["High"], df["Low"], df["Close"]
    up_move = high.diff()
    down_move = -low.diff()

    plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = atr(df, period) * period  # true range toplamı yaklaşık ölçek için

    atr_val = atr(df, period)
    plus_di = 100 * pd.Series(plus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_val
    minus_di = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1 / period, adjust=False).mean() / atr_val

    dx = (100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan))
    adx_val = dx.ewm(alpha=1 / period, adjust=False).mean()
    return adx_val.fillna(0), plus_di.fillna(0), minus_di.fillna(0)


def bollinger_bands(series: pd.Series, period: int = 20, num_std: float = 2.0):
    mid = series.rolling(period).mean()
    std = series.rolling(period).std()
    upper = mid + num_std * std
    lower = mid - num_std * std
    return upper, mid, lower


def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9):
    ema_fast = ema(series, fast)
    ema_slow = ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist

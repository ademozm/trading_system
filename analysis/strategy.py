"""
Regime-Adaptive Strategy
------------------------
Mantık:
1. ADX ile piyasa rejimi belirlenir.
   - ADX > adx_threshold  -> TRENDING piyasa
   - ADX <= adx_threshold -> RANGING (yatay) piyasa

2. TRENDING rejiminde: EMA(fast) x EMA(slow) kesişimi + MACD histogram
   yön teyidi ile trend takibi sinyali üretilir.

3. RANGING rejiminde: RSI aşırı alım/satım + Bollinger Bant sınırlarına
   dokunma ile mean-reversion sinyali üretilir.

4. Her iki rejimde de ATR tabanlı stop-loss / take-profit mesafeleri
   hesaplanır (backtest motoru bunları kullanır).

Bu, pazarlama metinlerinde geçen "adaptive logic" gibi belirsiz iddiaların
somut, denetlenebilir bir versiyonu. Hiçbir gelecek performans garantisi
içermez; sadece kural tabanlı, test edilebilir bir sinyal üretecidir.
"""
import numpy as np
import pandas as pd

from analysis.indicators import ema, rsi, atr, adx, bollinger_bands, macd


class RegimeAdaptiveStrategy:
    def __init__(
        self,
        adx_period: int = 14,
        adx_threshold: float = 22.0,
        ema_fast: int = 12,
        ema_slow: int = 26,
        rsi_period: int = 14,
        rsi_oversold: float = 30.0,
        rsi_overbought: float = 70.0,
        bb_period: int = 20,
        bb_std: float = 2.0,
        atr_period: int = 14,
        atr_stop_mult: float = 2.0,
        atr_target_mult: float = 3.0,
    ):
        self.adx_period = adx_period
        self.adx_threshold = adx_threshold
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
        self.rsi_oversold = rsi_oversold
        self.rsi_overbought = rsi_overbought
        self.bb_period = bb_period
        self.bb_std = bb_std
        self.atr_period = atr_period
        self.atr_stop_mult = atr_stop_mult
        self.atr_target_mult = atr_target_mult

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        out = df.copy()

        out["ema_fast"] = ema(out["Close"], self.ema_fast)
        out["ema_slow"] = ema(out["Close"], self.ema_slow)
        out["rsi"] = rsi(out["Close"], self.rsi_period)
        out["atr"] = atr(out, self.atr_period)
        out["adx"], out["plus_di"], out["minus_di"] = adx(out, self.adx_period)
        out["bb_upper"], out["bb_mid"], out["bb_lower"] = bollinger_bands(
            out["Close"], self.bb_period, self.bb_std
        )
        out["macd_line"], out["macd_signal"], out["macd_hist"] = macd(out["Close"])

        out["regime"] = np.where(out["adx"] > self.adx_threshold, "trend", "range")

        signal = pd.Series(0, index=out.index)

        # --- Trend takibi sinyalleri ---
        trend_mask = out["regime"] == "trend"
        bull_cross = (out["ema_fast"] > out["ema_slow"]) & (out["macd_hist"] > 0)
        bear_cross = (out["ema_fast"] < out["ema_slow"]) & (out["macd_hist"] < 0)
        signal = signal.where(~(trend_mask & bull_cross), 1)
        signal = signal.where(~(trend_mask & bear_cross), -1)

        # --- Mean reversion sinyalleri ---
        range_mask = out["regime"] == "range"
        oversold_bounce = (out["rsi"] < self.rsi_oversold) & (out["Close"] <= out["bb_lower"])
        overbought_fade = (out["rsi"] > self.rsi_overbought) & (out["Close"] >= out["bb_upper"])
        signal = signal.where(~(range_mask & oversold_bounce), 1)
        signal = signal.where(~(range_mask & overbought_fade), -1)

        out["signal"] = signal

        # ATR tabanlı stop / hedef seviyeleri (uzun pozisyon için; kısa pozisyonda ters çevrilir)
        out["stop_dist"] = out["atr"] * self.atr_stop_mult
        out["target_dist"] = out["atr"] * self.atr_target_mult

        return out

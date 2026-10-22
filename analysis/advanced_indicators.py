"""
Gelişmiş teknik göstergeler: Fibonacci geri çekilme seviyeleri,
destek/direnç bölgeleri, hacim profili (volume profile).

Bunlar RegimeAdaptiveStrategy'nin AL/SAT sinyaline EK BAĞLAM sağlar —
"fiyat şu an önemli bir destek seviyesine mi yakın" gibi soruları
cevaplamaya yardımcı olur. Doğrudan sinyal üretmezler, sadece rapora
ek bilgi olarak eklenirler.
"""
import numpy as np
import pandas as pd

from analysis import candlestick_patterns

FIB_RATIOS = [0.0, 0.236, 0.382, 0.5, 0.618, 0.786, 1.0]


def fibonacci_levels(df: pd.DataFrame, lookback: int = 100) -> dict:
    """
    Son `lookback` bar içindeki en yüksek/en düşük noktalar arasında
    Fibonacci geri çekilme seviyelerini hesaplar.
    """
    window = df.tail(lookback)
    if len(window) < 10:
        return {}

    swing_high = window["High"].max()
    swing_low = window["Low"].min()
    diff = swing_high - swing_low
    if diff <= 0:
        return {}

    uptrend = window["Close"].iloc[-1] >= window["Close"].iloc[0]
    levels = {}
    for ratio in FIB_RATIOS:
        if uptrend:
            price = swing_high - diff * ratio
        else:
            price = swing_low + diff * ratio
        levels[f"fib_{ratio:.3f}"] = round(price, 4)

    levels["swing_high"] = swing_high
    levels["swing_low"] = swing_low
    levels["trend_direction"] = "yukarı" if uptrend else "aşağı"
    return levels


def nearest_fib_level(close_price: float, fib_levels: dict) -> dict:
    """Güncel fiyata en yakın Fibonacci seviyesini bulur (bağlam için)."""
    price_levels = {k: v for k, v in fib_levels.items() if k.startswith("fib_")}
    if not price_levels:
        return {"nearest_fib_level": None, "distance_pct": np.nan}

    nearest_key = min(price_levels, key=lambda k: abs(price_levels[k] - close_price))
    nearest_price = price_levels[nearest_key]
    distance_pct = (close_price / nearest_price - 1) * 100 if nearest_price > 0 else np.nan
    return {"nearest_fib_level": nearest_key.replace("fib_", ""), "distance_pct": distance_pct}


def find_pivots(series: pd.Series, window: int = 5) -> tuple:
    """
    Yerel tepe (pivot high) ve dip (pivot low) noktalarını bulur.
    Bir nokta, kendisinden `window` bar önce ve sonrasındaki en yüksek/
    düşük değerse pivot sayılır.
    """
    highs, lows = [], []
    values = series.values
    for i in range(window, len(values) - window):
        segment = values[i - window: i + window + 1]
        if values[i] == segment.max():
            highs.append((i, values[i]))
        if values[i] == segment.min():
            lows.append((i, values[i]))
    return highs, lows


def support_resistance_levels(
    df: pd.DataFrame, lookback: int = 150, pivot_window: int = 5,
    cluster_tolerance_pct: float = 1.5, max_levels: int = 3,
) -> dict:
    """
    Pivot noktalarını bulup birbirine yakın olanları (tolerans içinde)
    kümeleyerek en güçlü (en çok dokunulan) destek/direnç seviyelerini
    döndürür.
    """
    window_df = df.tail(lookback)
    if len(window_df) < pivot_window * 4:
        return {"support_levels": [], "resistance_levels": []}

    pivot_highs, _ = find_pivots(window_df["High"], pivot_window)
    _, pivot_lows = find_pivots(window_df["Low"], pivot_window)

    def cluster(points: list) -> list:
        if not points:
            return []
        prices = sorted(p for _, p in points)
        clusters = [[prices[0]]]
        for p in prices[1:]:
            if abs(p - clusters[-1][-1]) / clusters[-1][-1] * 100 <= cluster_tolerance_pct:
                clusters[-1].append(p)
            else:
                clusters.append([p])
        # Güç = o kümede kaç dokunuş var; en güçlü kümeleri döndür
        clusters.sort(key=len, reverse=True)
        return [round(float(np.mean(c)), 4) for c in clusters[:max_levels]]

    return {
        "resistance_levels": cluster(pivot_highs),
        "support_levels": cluster(pivot_lows),
    }


def volume_profile(df: pd.DataFrame, lookback: int = 100, bins: int = 20) -> dict:
    """
    Fiyat aralığını `bins` dilime bölüp her dilimde ne kadar hacim
    işlem gördüğünü hesaplar. POC (Point of Control) = en çok hacim
    gören fiyat dilimi — piyasanın "adil değer" olarak gördüğü bölge.
    """
    window = df.tail(lookback)
    if len(window) < 10:
        return {"poc_price": None, "value_area_low": None, "value_area_high": None}

    price_min, price_max = window["Low"].min(), window["High"].max()
    if price_max <= price_min:
        return {"poc_price": None, "value_area_low": None, "value_area_high": None}

    bin_edges = np.linspace(price_min, price_max, bins + 1)
    typical_price = (window["High"] + window["Low"] + window["Close"]) / 3
    bin_indices = np.clip(np.digitize(typical_price, bin_edges) - 1, 0, bins - 1)

    volume_by_bin = np.zeros(bins)
    for idx, vol in zip(bin_indices, window["Volume"]):
        volume_by_bin[idx] += vol

    poc_bin = int(np.argmax(volume_by_bin))
    poc_price = round((bin_edges[poc_bin] + bin_edges[poc_bin + 1]) / 2, 4)

    # Value Area: hacmin %70'ini kapsayan bölge, POC'tan dışa doğru genişletilerek bulunur
    total_volume = volume_by_bin.sum()
    if total_volume <= 0:
        return {"poc_price": poc_price, "value_area_low": None, "value_area_high": None}

    target = total_volume * 0.70
    included = {poc_bin}
    accumulated = volume_by_bin[poc_bin]
    low_i, high_i = poc_bin, poc_bin
    while accumulated < target and (low_i > 0 or high_i < bins - 1):
        next_low = volume_by_bin[low_i - 1] if low_i > 0 else -1
        next_high = volume_by_bin[high_i + 1] if high_i < bins - 1 else -1
        if next_high >= next_low:
            high_i += 1
            accumulated += volume_by_bin[high_i]
        else:
            low_i -= 1
            accumulated += volume_by_bin[low_i]

    return {
        "poc_price": poc_price,
        "value_area_low": round(bin_edges[low_i], 4),
        "value_area_high": round(bin_edges[high_i + 1], 4),
    }


def compute_all(df: pd.DataFrame) -> dict:
    """Tüm gelişmiş göstergeleri tek seferde hesaplayıp birleştirir."""
    fib = fibonacci_levels(df)
    close = df["Close"].iloc[-1]
    fib_context = nearest_fib_level(close, fib) if fib else {"nearest_fib_level": None, "distance_pct": np.nan}
    sr = support_resistance_levels(df)
    vp = volume_profile(df)
    pattern = candlestick_patterns.detect_last_pattern(df)

    return {
        "fib_trend_direction": fib.get("trend_direction"),
        "fib_swing_high": fib.get("swing_high"),
        "fib_swing_low": fib.get("swing_low"),
        "nearest_fib_level": fib_context["nearest_fib_level"],
        "nearest_fib_distance_pct": fib_context["distance_pct"],
        "support_levels": sr["support_levels"],
        "resistance_levels": sr["resistance_levels"],
        "poc_price": vp["poc_price"],
        "value_area_low": vp["value_area_low"],
        "value_area_high": vp["value_area_high"],
        "candlestick_pattern": pattern["pattern"],
        "candlestick_direction": pattern["pattern_direction"],
    }

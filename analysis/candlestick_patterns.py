"""
Klasik mum formasyonu (candlestick pattern) tanıma.

Sadece OHLC verisinden hesaplanır, ek veri çekimi gerektirmez. Her
formasyon, "AL yönünde", "SAT yönünde" veya "kararsızlık" sinyali olarak
sınıflandırılır — teknik analizde uzun süredir kullanılan, kural tabanlı
(sübjektif yorum gerektirmeyen) tanımlar kullanılmıştır.

DÜRÜSTLÜK NOTU: Mum formasyonları TEK BAŞINA güvenilir bir alım/satım
sinyali değildir — akademik çalışmalar tutarlı bir edge sağladıklarına
dair karışık sonuçlar veriyor. Burada trend/rejim ve diğer göstergelerle
BİRLİKTE, ek bir teyit katmanı olarak kullanılıyor, tek başına karar
mekanizması olarak değil.
"""
import pandas as pd


def _body(row) -> float:
    return abs(row["Close"] - row["Open"])


def _range(row) -> float:
    return row["High"] - row["Low"]


def _upper_shadow(row) -> float:
    return row["High"] - max(row["Close"], row["Open"])


def _lower_shadow(row) -> float:
    return min(row["Close"], row["Open"]) - row["Low"]


def is_doji(row, threshold_pct: float = 0.1) -> bool:
    """Gövde, toplam aralığın çok küçük bir kısmıysa (kararsızlık göstergesi)."""
    rng = _range(row)
    if rng == 0:
        return False
    return bool((_body(row) / rng) < threshold_pct)


def is_hammer(row) -> bool:
    """Küçük gövde, uzun alt gölge, kısa/yok üst gölge — dipte görülürse dönüş sinyali."""
    rng = _range(row)
    if rng == 0:
        return False
    body = _body(row)
    lower = _lower_shadow(row)
    upper = _upper_shadow(row)
    return bool(body > 0 and lower > 2 * body and upper < body)


def is_shooting_star(row) -> bool:
    """Küçük gövde, uzun üst gölge, kısa/yok alt gölge — zirvede görülürse dönüş sinyali."""
    rng = _range(row)
    if rng == 0:
        return False
    body = _body(row)
    upper = _upper_shadow(row)
    lower = _lower_shadow(row)
    return bool(body > 0 and upper > 2 * body and lower < body)


def is_bullish_engulfing(prev_row, row) -> bool:
    """Önceki kırmızı (düşüş) mumu, bugünkü yeşil (yükseliş) mumun gövdesi tamamen kapsıyor."""
    prev_bearish = prev_row["Close"] < prev_row["Open"]
    curr_bullish = row["Close"] > row["Open"]
    engulfs = row["Open"] <= prev_row["Close"] and row["Close"] >= prev_row["Open"]
    return bool(prev_bearish and curr_bullish and engulfs)


def is_bearish_engulfing(prev_row, row) -> bool:
    """Önceki yeşil mumu, bugünkü kırmızı mumun gövdesi tamamen kapsıyor."""
    prev_bullish = prev_row["Close"] > prev_row["Open"]
    curr_bearish = row["Close"] < row["Open"]
    engulfs = row["Open"] >= prev_row["Close"] and row["Close"] <= prev_row["Open"]
    return bool(prev_bullish and curr_bearish and engulfs)


PATTERN_DIRECTION = {
    "doji": "kararsızlık",
    "hammer": "AL",
    "shooting_star": "SAT",
    "bullish_engulfing": "AL",
    "bearish_engulfing": "SAT",
}


def detect_last_pattern(df: pd.DataFrame) -> dict:
    """
    Son mumda (ve gerekiyorsa bir önceki mumla birlikte) tespit edilen
    formasyonu döner. Birden fazla formasyon aynı anda tespit edilirse
    ilk bulunan öncelik alır (engulfing > hammer/star > doji sırasıyla,
    çünkü çok mumlu formasyonlar genelde daha güçlü sinyal sayılır).

    Dönüş: {"pattern": str|None, "pattern_direction": str|None}
    """
    if len(df) < 2:
        return {"pattern": None, "pattern_direction": None}

    last = df.iloc[-1]
    prev = df.iloc[-2]

    if is_bullish_engulfing(prev, last):
        return {"pattern": "bullish_engulfing", "pattern_direction": "AL"}
    if is_bearish_engulfing(prev, last):
        return {"pattern": "bearish_engulfing", "pattern_direction": "SAT"}
    if is_hammer(last):
        return {"pattern": "hammer", "pattern_direction": "AL"}
    if is_shooting_star(last):
        return {"pattern": "shooting_star", "pattern_direction": "SAT"}
    if is_doji(last):
        return {"pattern": "doji", "pattern_direction": "kararsızlık"}

    return {"pattern": None, "pattern_direction": None}

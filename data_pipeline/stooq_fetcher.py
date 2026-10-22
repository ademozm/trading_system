"""
Stooq.com'dan (ücretsiz, API key gerektirmeyen) tarihsel OHLCV verisi.

Bu modülün iki amacı var:
1. YEDEK KAYNAK: yfinance bir sembol için veri veremezse (rate limit,
   geçici sunucu sorunu, vadeli işlem sözleşmesi kesintisi gibi), Stooq
   denenir. Tamamen farklı bir sağlayıcı olduğu için yfinance'teki geçici
   bir sorun burayı etkilemez.
2. ÇAPRAZ DOĞRULAMA: Sinyal üreten semboller için hem yfinance hem Stooq'tan
   son kapanış fiyatı karşılaştırılır. İki kaynak birbirinden önemli
   ölçüde farklıysa (örn. %3+), bu "veri şüpheli olabilir" anlamına gelir
   ve rapora bir uyarı düşülür — kör güven yerine çapraz kontrol.

DÜRÜSTLÜK NOTU: Stooq, BIST hisselerini güvenilir şekilde desteklemiyor,
bu yüzden BIST için bu modül kullanılmaz (yfinance tek kaynak kalır).
ABD hisseleri, büyük kripto paralar ve emtialar için çalışır.
"""
import io
import logging

import pandas as pd
import requests

logger = logging.getLogger("stooq_fetcher")

STOOQ_URL = "https://stooq.com/q/d/l/?s={symbol}&i=d"

# Bazı özel eşlemeler (Yahoo formatından Stooq formatına)
SPECIAL_MAP = {
    "GC=F": "xauusd",
    "XAUUSD=X": "xauusd",
    "SI=F": "xagusd",
    "XAGUSD=X": "xagusd",
    "CL=F": "cl.f",
    "NG=F": "ng.f",
}


def map_to_stooq(symbol: str, market: str) -> str | None:
    """Yahoo Finance sembolünü Stooq sembolüne çevirir. Desteklenmiyorsa None döner."""
    if symbol in SPECIAL_MAP:
        return SPECIAL_MAP[symbol]

    if market == "bist":
        return None  # Stooq'ta BIST kapsamı güvenilir değil

    if market == "emtia":
        # SPECIAL_MAP'te olmayan bir emtia/döviz sembolü varsa (kullanıcı
        # kendi CSV'sine ekleyebilir) genel bir tahmin yapılmıyor —
        # bu piyasalarda sembol formatı çok değişken, yanlış tahmin
        # sessizce yanlış veriye yol açabilir. Elle SPECIAL_MAP'e eklenmeli.
        return None

    if market == "crypto":
        # "BTC-USD" -> "btcusd"
        base = symbol.replace("-USD", "").replace("-", "").lower()
        return f"{base}usd"

    if market == "us":
        # "BRK-B" -> "brk-b.us", "AAPL" -> "aapl.us"
        return f"{symbol.lower()}.us"

    return None


def fetch_stooq(stooq_symbol: str, timeout: int = 15) -> pd.DataFrame | None:
    """
    Başarılı olursa Open/High/Low/Close/Volume kolonlu, tarih indeksli
    DataFrame döner. Sembol bulunamazsa veya hata olursa None döner
    (exception fırlatmaz — çağıran taraf yfinance'e geri düşebilsin diye).
    """
    url = STOOQ_URL.format(symbol=stooq_symbol)
    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        text = resp.text
        if not text or "brak danych" in text.lower() or len(text) < 30:
            return None  # Stooq "veri yok" durumunda kısa/boş metin döner

        df = pd.read_csv(io.StringIO(text))
        if df.empty or "Close" not in df.columns:
            return None

        df["Date"] = pd.to_datetime(df["Date"])
        df = df.set_index("Date").sort_index()
        # fetcher.py'deki aynı sebeple: Volume NaN diye tüm satırı silme,
        # sadece asıl fiyat sütunlarında NaN varsa at.
        df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
        df["Volume"] = df["Volume"].fillna(0)
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        return df if len(df) > 0 else None
    except Exception as e:
        logger.debug(f"Stooq'tan {stooq_symbol} çekilemedi: {e}")
        return None


def fetch_with_fallback(symbol: str, market: str) -> pd.DataFrame | None:
    """map_to_stooq + fetch_stooq'u birleştiren kolaylık fonksiyonu."""
    stooq_symbol = map_to_stooq(symbol, market)
    if stooq_symbol is None:
        return None
    return fetch_stooq(stooq_symbol)


def cross_validate(symbol: str, market: str, reference_close: float, tolerance_pct: float = 3.0) -> dict:
    """
    reference_close (genelde yfinance'ten gelen son kapanış) ile Stooq'un
    son kapanışını karşılaştırır.

    Dönüş: {"stooq_close": float|None, "fark_yuzde": float|None, "supheli": bool}
    Stooq'tan veri alınamazsa "supheli": False döner (karşılaştırma
    yapılamadı demektir, otomatik şüpheli sayılmaz — veri eksikliği
    ile veri tutarsızlığı farklı şeylerdir).
    """
    df = fetch_with_fallback(symbol, market)
    if df is None or df.empty:
        return {"stooq_close": None, "fark_yuzde": None, "supheli": False}

    stooq_close = float(df["Close"].iloc[-1])
    if reference_close == 0:
        return {"stooq_close": stooq_close, "fark_yuzde": None, "supheli": False}

    fark_yuzde = abs(stooq_close - reference_close) / reference_close * 100
    return {
        "stooq_close": stooq_close,
        "fark_yuzde": fark_yuzde,
        "supheli": fark_yuzde > tolerance_pct,
    }

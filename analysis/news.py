"""
Haber analizi modülü.

ÖNEMLİ DÜRÜSTLÜK NOTU: Bu, gerçek bir yapay zeka destekli haber analizi
DEĞİLDİR. Basit bir anahtar kelime sayımı (kaç "pozitif" kelime, kaç
"negatif" kelime geçiyor) yapıyor. Bunun sebebi: gerçek NLP/LLM tabanlı
haber analizi ücretli bir API gerektirir (OpenAI, Anthropic vb. embedding
veya sınıflandırma çağrısı). Burada tamamen ücretsiz kalmak için basit
ama şeffaf bir sezgisel yöntem tercih edildi. Bunu bir "kaba gösterge"
olarak kullan, kesin bir yargı olarak değil.

İki fonksiyon grubu:
1. Sembol bazlı haberler: yfinance'in .news özelliğinden (ekstra API
   çağrısı gerektirmez, ücretsizdir) her sembol için son başlıkları çeker.
2. Makro haberler: ABD piyasasını geneli etkileyen büyük endeks/gösterge
   sembollerinin (S&P 500, Dow, Nasdaq, 10 yıllık tahvil getirisi, dolar
   endeksi) haberlerini toplar — Fed açıklamaları, enflasyon verileri gibi
   "borsayı geneli etkileyen" haberler genelde bu sembollerin haber
   akışında da çıkar.
"""
import logging

import yfinance as yf

logger = logging.getLogger("news")

MACRO_TICKERS = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "Nasdaq",
    "^TNX": "ABD 10 Yıllık Tahvil Getirisi",
    "DX-Y.NYB": "Dolar Endeksi (DXY)",
}

POSITIVE_WORDS = [
    "surge", "rally", "gain", "gains", "jump", "soar", "record high", "beat", "beats",
    "upgrade", "bullish", "growth", "profit", "strong", "outperform", "boost",
    "yükseliş", "rekor", "artış", "kazanç", "güçlü", "olumlu", "yükseldi",
]
NEGATIVE_WORDS = [
    "plunge", "crash", "fall", "falls", "drop", "slump", "downgrade", "bearish",
    "loss", "losses", "weak", "underperform", "recession", "cut", "warning", "miss", "misses",
    "düşüş", "kayıp", "zarar", "olumsuz", "geriledi", "çöküş", "kriz",
]


def simple_sentiment(text: str) -> float:
    """
    Metindeki pozitif/negatif kelime sayısına göre -1 ile +1 arası kaba bir skor.
    0 = nötr veya kelime bulunamadı.
    """
    if not text:
        return 0.0
    text_lower = text.lower()
    pos = sum(1 for w in POSITIVE_WORDS if w in text_lower)
    neg = sum(1 for w in NEGATIVE_WORDS if w in text_lower)
    total = pos + neg
    if total == 0:
        return 0.0
    return (pos - neg) / total


def fetch_symbol_news(symbol: str, max_items: int = 5) -> list[dict]:
    """
    Dönüş: [{"title": ..., "publisher": ..., "sentiment": ..., "link": ...}, ...]
    Hata durumunda boş liste döner (haber olmaması sistemi durdurmamalı).
    """
    try:
        raw = yf.Ticker(symbol).news or []
    except Exception as e:
        logger.warning(f"{symbol} için haber çekilemedi: {e}")
        return []

    items = []
    for entry in raw[:max_items]:
        # yfinance sürümüne göre başlık bazen "title" bazen content.get("title") altında olabilir
        title = entry.get("title") or entry.get("content", {}).get("title", "")
        publisher = entry.get("publisher") or entry.get("content", {}).get("provider", {}).get("displayName", "")
        link = entry.get("link") or entry.get("content", {}).get("canonicalUrl", {}).get("url", "")
        if not title:
            continue
        items.append({
            "title": title,
            "publisher": publisher,
            "sentiment": simple_sentiment(title),
            "link": link,
        })
    return items


def symbol_news_summary(symbol: str, max_items: int = 5) -> dict:
    """Tek bir sembol için ortalama haber tonu + en son başlık (rapor/skorlama için)."""
    items = fetch_symbol_news(symbol, max_items)
    if not items:
        return {"news_sentiment": None, "news_count": 0, "latest_headline": None}
    avg_sentiment = sum(i["sentiment"] for i in items) / len(items)
    return {
        "news_sentiment": avg_sentiment,
        "news_count": len(items),
        "latest_headline": items[0]["title"],
    }


def fetch_macro_news(max_items_per_ticker: int = 3) -> list[dict]:
    """
    ABD piyasasını genel etkileyen büyük göstergelerin haber başlıklarını toplar.
    Excel'deki "Haberler" sayfası ve Telegram bildirimi için kullanılır.
    """
    all_items = []
    for ticker, label in MACRO_TICKERS.items():
        items = fetch_symbol_news(ticker, max_items_per_ticker)
        for item in items:
            item["kaynak"] = label
            all_items.append(item)
    return all_items

"""
Katman 3c — Haber Çekme (public-apis/public-apis repo'sundan ilham alındı)
==============================================================================
news_analyst_node (bkz. nodes.py) şimdiye kadar hiçbir zaman GERÇEK bir
haber kaynağına sahip olmadı — `news_text` parametresi hep `None` geçiliyordu
ve LLM her seferinde "haber verisi yok" demek zorunda kalıyordu.

github.com/public-apis/public-apis reposunun "News" ve "Finance" kategorileri
taranarak seçildi: NewsAPI.org (newsapi.org) — basit REST arayüzü, ücretsiz
geliştirici katmanı (`apiKey` ile), iyi belgelenmiş `/v2/everything` endpoint'i.

Tasarım kararı — neden sadece başlık + kısa özet, tam makale metni DEĞİL:
  1) Telif hakkı: tam makale metnini LLM'e (veya herhangi bir yere) kopyalamak
     yerine sadece başlık + kısa özet (description) kullanılır.
  2) Pratiklik: LLM'in ihtiyacı olan şey "bu sembolle ilgili ne oluyor" özeti,
     tam makale değil — başlıklar bunun için yeterli sinyal taşır.

`format_headlines_as_text` bilerek ağdan bağımsızdır (saf metin biçimlendirme)
— test edilebilir olması için NewsAPIClient'tan ayrılmıştır.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import requests

NEWSAPI_BASE_URL = "https://newsapi.org/v2/everything"

# Sembol -> arama sorgusu eşlemesi. NewsAPI "BTC/USDT" gibi bir sorguyla
# anlamlı sonuç döndürmez; sembolü haberlerde geçen gerçek isme çevirmek
# gerekir. Eşlenmeyen semboller için ham sembol (ör. "AAPL") kullanılır —
# hisse senedi ticker'ları genelde haber metinlerinde de geçer, bu yüzden
# makul bir varsayılan.
SYMBOL_TO_NEWS_QUERY = {
    "BTC/USDT": "Bitcoin",
    "ETH/USDT": "Ethereum",
    "AAPL": "Apple stock",
    "MSFT": "Microsoft stock",
}


@dataclass
class Headline:
    title: str
    description: Optional[str]
    source: str
    published_at: str


def symbol_to_news_query(symbol: str) -> str:
    """Sembolü NewsAPI için anlamlı bir arama sorgusuna çevirir."""
    return SYMBOL_TO_NEWS_QUERY.get(symbol, symbol)


def format_headlines_as_text(headlines: list[Headline], max_headlines: int = 5) -> Optional[str]:
    """
    Başlık listesini, news_analyst_node'un (nodes.py) beklediği `news_text`
    string'ine çevirir. Liste boşsa None döner (LLM'e "haber yok" mesajını
    dürüstçe iletmek için — bkz. prompts.py:news_analyst_prompt).

    Sadece başlık + varsa kısa açıklama kullanılır, tam makale metni ASLA
    dahil edilmez (telif hakkı ve pratiklik nedeniyle, bkz. dosya başı notu).
    """
    if not headlines:
        return None

    lines = []
    for h in headlines[:max_headlines]:
        line = f"- [{h.source}, {h.published_at}] {h.title}"
        if h.description:
            line += f" — {h.description}"
        lines.append(line)
    return "\n".join(lines)


class NewsAPIClient:
    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ValueError("NewsAPIClient için api_key zorunludur (NEWSAPI_KEY ortam değişkeni).")
        self.api_key = api_key

    def fetch_headlines(self, query: str, page_size: int = 5) -> list[Headline]:
        """
        NewsAPI.org'un /v2/everything endpoint'inden en güncel `page_size`
        kadar başlığı çeker. Ağ/API hatası durumunda İSTİSNA FIRLATIR —
        çağıran taraf (main.py) bunu yakalayıp zarifçe None'a düşürmelidir
        (bkz. main.py'deki genel try/except sembol izolasyonu).
        """
        response = requests.get(
            NEWSAPI_BASE_URL,
            params={
                "q": query,
                "sortBy": "publishedAt",
                "language": "en",
                "pageSize": page_size,
                "apiKey": self.api_key,
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        headlines = []
        for article in data.get("articles", [])[:page_size]:
            headlines.append(
                Headline(
                    title=article.get("title", ""),
                    description=article.get("description"),
                    source=(article.get("source") or {}).get("name", "bilinmiyor"),
                    published_at=article.get("publishedAt", ""),
                )
            )
        return headlines

    def fetch_news_text_for_symbol(self, symbol: str, page_size: int = 5) -> Optional[str]:
        """
        Tam akış: sembolü sorguya çevir -> haberleri çek -> news_analyst_node'un
        beklediği formata çevir. LLMAgentChain.analyze()'a doğrudan
        `news_text=` olarak geçirilebilir.
        """
        query = symbol_to_news_query(symbol)
        headlines = self.fetch_headlines(query, page_size=page_size)
        return format_headlines_as_text(headlines, max_headlines=page_size)

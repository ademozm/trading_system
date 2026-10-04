"""
tests/test_news_fetcher.py
=============================
signals/llm_agents/news_fetcher.py'nin ağdan bağımsız (saf) kısımlarını
doğrular: symbol_to_news_query ve format_headlines_as_text. NewsAPIClient'ın
kendisi (gerçek HTTP isteği atan) burada TEST EDİLMEMİŞTİR — gerçek bir
NewsAPI anahtarı/internet gerektirir.
"""

from __future__ import annotations

from signals.llm_agents.news_fetcher import (
    Headline,
    format_headlines_as_text,
    symbol_to_news_query,
)


def test_symbol_to_news_query_known_mappings() -> None:
    assert symbol_to_news_query("BTC/USDT") == "Bitcoin"
    assert symbol_to_news_query("ETH/USDT") == "Ethereum"
    assert symbol_to_news_query("AAPL") == "Apple stock"


def test_symbol_to_news_query_unknown_symbol_falls_back_to_raw() -> None:
    assert symbol_to_news_query("DOGE/USDT") == "DOGE/USDT"


def test_format_headlines_returns_none_for_empty_list() -> None:
    assert format_headlines_as_text([]) is None


def test_format_headlines_includes_title_and_description() -> None:
    headlines = [
        Headline(title="Bitcoin geri çekildi", description="Fiyat %3 düştü", source="Reuters", published_at="2026-01-01T10:00:00Z"),
    ]
    text = format_headlines_as_text(headlines)
    assert text is not None
    assert "Bitcoin geri çekildi" in text
    assert "Fiyat %3 düştü" in text
    assert "Reuters" in text


def test_format_headlines_handles_missing_description() -> None:
    headlines = [
        Headline(title="Başlık", description=None, source="Kaynak", published_at="2026-01-01T10:00:00Z"),
    ]
    text = format_headlines_as_text(headlines)
    assert text is not None
    assert "Başlık" in text
    assert "—" not in text  # açıklama yoksa ayraç eklenmemeli


def test_format_headlines_respects_max_headlines() -> None:
    headlines = [
        Headline(title=f"Başlık {i}", description=None, source="Kaynak", published_at="2026-01-01T10:00:00Z")
        for i in range(10)
    ]
    text = format_headlines_as_text(headlines, max_headlines=3)
    assert text.count("Başlık") == 3


def test_format_headlines_never_includes_full_article_body() -> None:
    """
    Telif hakkı kontrolü: format_headlines_as_text'in Headline nesnesinde
    olmayan bir alanı (tam makale metni) hiçbir şekilde ekleyemeyeceğini
    doğrular — Headline dataclass'ı zaten sadece title/description/source/
    published_at taşıyor, tam metin taşıyacak bir alanı YOK.
    """
    headline_fields = Headline.__dataclass_fields__.keys()
    assert "content" not in headline_fields
    assert "full_text" not in headline_fields
    assert "body" not in headline_fields

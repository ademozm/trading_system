from unittest.mock import patch, MagicMock

import pytest

from analysis import news


def test_simple_sentiment_positive_text():
    score = news.simple_sentiment("Stocks surge to record high after strong earnings beat")
    assert score > 0


def test_simple_sentiment_negative_text():
    score = news.simple_sentiment("Markets plunge as recession fears grow, shares crash")
    assert score < 0


def test_simple_sentiment_neutral_text():
    score = news.simple_sentiment("Company announces quarterly meeting schedule")
    assert score == 0.0


def test_simple_sentiment_empty_text():
    assert news.simple_sentiment("") == 0.0
    assert news.simple_sentiment(None) == 0.0


def test_simple_sentiment_mixed_text_averages():
    score = news.simple_sentiment("Stock gains initially but then falls on weak guidance")
    assert -1 <= score <= 1


def test_fetch_symbol_news_handles_exception_gracefully():
    with patch("analysis.news.yf.Ticker") as mock_ticker:
        mock_ticker.side_effect = Exception("network error")
        result = news.fetch_symbol_news("FAKE")
        assert result == []


def test_fetch_symbol_news_parses_standard_format():
    mock_instance = MagicMock()
    mock_instance.news = [
        {"title": "Stock surges on record earnings", "publisher": "Reuters", "link": "http://x.com"},
    ]
    with patch("analysis.news.yf.Ticker", return_value=mock_instance):
        result = news.fetch_symbol_news("AAPL")
    assert len(result) == 1
    assert result[0]["title"] == "Stock surges on record earnings"
    assert result[0]["sentiment"] > 0


def test_fetch_symbol_news_skips_items_without_title():
    mock_instance = MagicMock()
    mock_instance.news = [{"publisher": "Reuters"}, {"title": "Valid headline here"}]
    with patch("analysis.news.yf.Ticker", return_value=mock_instance):
        result = news.fetch_symbol_news("AAPL")
    assert len(result) == 1


def test_fetch_symbol_news_empty_when_no_news():
    mock_instance = MagicMock()
    mock_instance.news = []
    with patch("analysis.news.yf.Ticker", return_value=mock_instance):
        result = news.fetch_symbol_news("AAPL")
    assert result == []


def test_symbol_news_summary_no_news_returns_none_sentiment():
    with patch("analysis.news.fetch_symbol_news", return_value=[]):
        result = news.symbol_news_summary("AAPL")
    assert result["news_sentiment"] is None
    assert result["news_count"] == 0


def test_symbol_news_summary_averages_sentiment():
    fake_items = [
        {"title": "a", "sentiment": 1.0, "publisher": "x", "link": ""},
        {"title": "b", "sentiment": -0.5, "publisher": "x", "link": ""},
    ]
    with patch("analysis.news.fetch_symbol_news", return_value=fake_items):
        result = news.symbol_news_summary("AAPL")
    assert result["news_sentiment"] == pytest.approx(0.25)
    assert result["news_count"] == 2
    assert result["latest_headline"] == "a"


def test_fetch_macro_news_aggregates_all_tickers():
    with patch("analysis.news.fetch_symbol_news", return_value=[
        {"title": "test", "sentiment": 0.0, "publisher": "x", "link": ""}
    ]):
        result = news.fetch_macro_news(max_items_per_ticker=1)
    assert len(result) == len(news.MACRO_TICKERS)
    assert all("kaynak" in item for item in result)

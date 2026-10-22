import os
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from analysis import notifier


def _scored_df():
    return pd.DataFrame({
        "symbol": ["AAA", "BBB", "CCC"],
        "market": ["us", "bist", "crypto"],
        "signal": [1, -1, 1],
        "composite_score": [0.6, -0.5, 0.3],
    })


def test_is_configured_false_when_env_missing(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    assert notifier.is_configured() is False


def test_is_configured_true_when_env_present(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    assert notifier.is_configured() is True


def test_send_message_returns_false_without_credentials(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = notifier.send_message("test")
    assert result is False


def test_send_message_calls_requests_post_when_configured(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("analysis.notifier.requests.post", return_value=mock_response) as mock_post:
        result = notifier.send_message("merhaba dünya")
        assert result is True
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert "fake_token" in args[0]
        assert kwargs["data"]["chat_id"] == "12345"


def test_send_message_handles_network_error_gracefully(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")
    with patch("analysis.notifier.requests.post", side_effect=Exception("bağlantı hatası")):
        result = notifier.send_message("test")
        assert result is False


def test_build_summary_message_empty_df():
    msg = notifier.build_summary_message(pd.DataFrame())
    assert "sinyal üreten sembol bulunamadı" in msg


def test_build_summary_message_includes_buy_and_sell():
    msg = notifier.build_summary_message(_scored_df())
    assert "AAA" in msg
    assert "BBB" in msg
    assert "AL sinyalleri" in msg
    assert "SAT sinyalleri" in msg


def test_notify_scan_complete_returns_false_when_not_configured(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_CHAT_ID", raising=False)
    result = notifier.notify_scan_complete(_scored_df(), {}, "/tmp/fake.xlsx")
    assert result is False


def test_notify_scan_complete_sends_message_and_file(monkeypatch, tmp_path):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "fake_token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "12345")

    fake_file = tmp_path / "report.xlsx"
    fake_file.write_text("dummy")

    mock_response = MagicMock()
    mock_response.status_code = 200
    with patch("analysis.notifier.requests.post", return_value=mock_response) as mock_post:
        result = notifier.notify_scan_complete(_scored_df(), {"başlangıç": 10, "son": 5}, str(fake_file))
        assert result is True
        assert mock_post.call_count == 2  # bir mesaj + bir dosya


def test_build_summary_message_includes_panel_link_when_configured(monkeypatch):
    monkeypatch.setenv("STREAMLIT_APP_URL", "https://ornek-panel.streamlit.app")
    df = pd.DataFrame({
        "symbol": ["AAPL"], "market": ["us"], "signal": [1], "composite_score": [0.5],
    })
    msg = notifier.build_summary_message(df)
    assert "https://ornek-panel.streamlit.app" in msg
    assert "Paneli" in msg or "panelde" in msg


def test_build_summary_message_no_link_when_not_configured(monkeypatch):
    monkeypatch.delenv("STREAMLIT_APP_URL", raising=False)
    df = pd.DataFrame({
        "symbol": ["AAPL"], "market": ["us"], "signal": [1], "composite_score": [0.5],
    })
    msg = notifier.build_summary_message(df)
    assert "streamlit.app" not in msg


def test_build_summary_message_empty_df_includes_link_when_configured(monkeypatch):
    monkeypatch.setenv("STREAMLIT_APP_URL", "https://ornek-panel.streamlit.app")
    msg = notifier.build_summary_message(pd.DataFrame())
    assert "https://ornek-panel.streamlit.app" in msg

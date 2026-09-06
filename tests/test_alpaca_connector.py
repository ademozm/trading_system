"""
tests/test_alpaca_connector.py
=================================
Alpaca'nın döndürdüğü JSON'u standart OHLCV şemasına çeviren
`parse_alpaca_bars` fonksiyonunu, GERÇEK bir API çağrısı yapmadan,
Alpaca'nın gerçek yanıt formatına uygun sentetik bir sözlükle test eder.

`fetch_ohlcv` (ağ çağrısı yapan fonksiyon) burada test EDİLMEMİŞTİR —
o kısım gerçek bir Alpaca hesabı/API anahtarı ve internet gerektirir.
"""

from __future__ import annotations

from data_layer.connectors.alpaca_connector import TIMEFRAME_MAP, parse_alpaca_bars


def _sample_alpaca_response() -> dict:
    # Alpaca'nın gerçek /v2/stocks/{symbol}/bars yanıt şemasına uygun
    # sentetik veri (alan isimleri: t, o, h, l, c, v, n, vw)
    return {
        "bars": [
            {"t": "2024-01-02T09:30:00Z", "o": 100.0, "h": 101.5, "l": 99.5, "c": 101.0, "v": 1000, "n": 50, "vw": 100.4},
            {"t": "2024-01-02T10:30:00Z", "o": 101.0, "h": 102.0, "l": 100.5, "c": 101.8, "v": 1200, "n": 60, "vw": 101.3},
            {"t": "2024-01-02T11:30:00Z", "o": 101.8, "h": 103.0, "l": 101.5, "c": 102.5, "v": 900, "n": 45, "vw": 102.1},
        ],
        "symbol": "AAPL",
        "next_page_token": None,
    }


def test_parse_alpaca_bars_produces_standard_columns() -> None:
    df = parse_alpaca_bars(_sample_alpaca_response())
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]
    assert len(df) == 3


def test_parse_alpaca_bars_types_are_correct() -> None:
    df = parse_alpaca_bars(_sample_alpaca_response())
    assert df["open"].dtype == float
    assert df["close"].iloc[0] == 101.0
    # timestamp UTC tz-aware olmalı
    assert df["timestamp"].dt.tz is not None


def test_parse_alpaca_bars_sorts_by_timestamp() -> None:
    response = _sample_alpaca_response()
    # Sırayı bozalım
    response["bars"] = list(reversed(response["bars"]))
    df = parse_alpaca_bars(response)
    assert df["timestamp"].is_monotonic_increasing


def test_parse_alpaca_bars_handles_empty_response() -> None:
    df = parse_alpaca_bars({"bars": []})
    assert len(df) == 0
    assert list(df.columns) == ["timestamp", "open", "high", "low", "close", "volume"]


def test_timeframe_map_covers_common_intervals() -> None:
    for tf in ["1m", "5m", "15m", "1h", "1d"]:
        assert tf in TIMEFRAME_MAP
    assert TIMEFRAME_MAP["1h"] == "1Hour"
    assert TIMEFRAME_MAP["1d"] == "1Day"

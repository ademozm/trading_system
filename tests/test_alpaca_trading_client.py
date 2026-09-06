"""
tests/test_alpaca_trading_client.py
======================================
build_order_payload'ın (ağdan bağımsız, saf) doğru JSON gövdesi
ürettiğini doğrular. AlpacaTradingClient sınıfının kendisi (gerçek HTTP
isteği atan) burada TEST EDİLMEMİŞTİR — o, gerçek bir Alpaca hesabı/API
anahtarı ve internet gerektirir.
"""

from __future__ import annotations

from execution.alpaca_trading_client import build_order_payload


def test_build_order_payload_buy() -> None:
    payload = build_order_payload("AAPL", notional=500.0, side="buy")
    assert payload == {
        "symbol": "AAPL",
        "notional": 500.0,
        "side": "buy",
        "type": "market",
        "time_in_force": "day",
    }


def test_build_order_payload_sell() -> None:
    payload = build_order_payload("MSFT", notional=250.5, side="sell")
    assert payload["side"] == "sell"
    assert payload["symbol"] == "MSFT"


def test_build_order_payload_rounds_notional_to_two_decimals() -> None:
    payload = build_order_payload("AAPL", notional=123.456789, side="buy")
    assert payload["notional"] == 123.46


def test_build_order_payload_rejects_invalid_side() -> None:
    try:
        build_order_payload("AAPL", notional=100.0, side="hold")
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_build_order_payload_rejects_non_positive_notional() -> None:
    try:
        build_order_payload("AAPL", notional=0.0, side="buy")
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass

    try:
        build_order_payload("AAPL", notional=-50.0, side="buy")
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass

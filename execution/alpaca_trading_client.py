"""
Katman 6 — Alpaca Trading İstemcisi (Hisse Senedi Emir Gönderimi)
======================================================================
data_layer.connectors.alpaca_connector VERİ çekmek için Alpaca'nın Data
API'sini kullanıyordu; bu dosya ise Alpaca'nın ayrı Trading API'sini
(paper veya canlı) kullanarak GERÇEK EMİR gönderir.

Tasarım kararı — notional (dolar bazlı) emir: Alpaca, "bana X adet hisse
al" yerine "bana Y dolarlık hisse al" (`notional` alanı) emri vermeyi
destekliyor. Bu, risk.risk_manager'ın ürettiği `position_size_pct`
(portföyün yüzdesi) modeliyle DOĞRUDAN uyumlu — güncel fiyatı ayrıca
çekip miktar hesaplamaya gerek kalmıyor, bu da bir hata kaynağını
(fiyat ile emir arasındaki gecikmede fiyatın değişmesi) ortadan kaldırıyor.

`build_order_payload` bilerek ağdan bağımsızdır (saf sözlük üretimi) —
gerçek bir API çağrısı yapmadan test edilebilir (bkz.
tests/test_alpaca_trading_client.py).
"""

from __future__ import annotations

from typing import Optional

import requests

PAPER_BASE_URL = "https://paper-api.alpaca.markets/v2"
LIVE_BASE_URL = "https://api.alpaca.markets/v2"


def build_order_payload(symbol: str, notional: float, side: str) -> dict:
    """
    Alpaca'nın `/v2/orders` endpoint'inin beklediği JSON gövdesini üretir.

    side: "buy" | "sell" (order_router.py'nin "long"/"short"u zaten
    "buy"/"sell"e çevirdiği varsayılır — bu fonksiyon o çeviriyi TEKRAR
    yapmaz, sadece gövdeyi kurar).
    """
    if side not in ("buy", "sell"):
        raise ValueError(f"Geçersiz side: {side} ('buy' veya 'sell' olmalı)")
    if notional <= 0:
        raise ValueError(f"notional pozitif olmalı, verilen: {notional}")

    return {
        "symbol": symbol,
        "notional": round(notional, 2),  # Alpaca dolar tutarını 2 ondalıkla bekler
        "side": side,
        "type": "market",
        "time_in_force": "day",
    }


class AlpacaTradingClient:
    def __init__(self, api_key: str, secret_key: str, paper: bool = True) -> None:
        if not api_key or not secret_key:
            raise ValueError(
                "AlpacaTradingClient için api_key ve secret_key zorunludur "
                "(ALPACA_API_KEY / ALPACA_API_SECRET ortam değişkenleri)."
            )
        self.base_url = PAPER_BASE_URL if paper else LIVE_BASE_URL
        self.headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": secret_key}
        self.paper = paper

    def place_market_order(self, symbol: str, notional: float, side: str) -> dict:
        """
        Notional (dolar bazlı) bir market emri gönderir. Alpaca'nın kesirli
        hisse (fractional share) desteği sayesinde notional emirler tam
        sayı olmayan hisse miktarlarında da çalışır.
        """
        payload = build_order_payload(symbol, notional, side)
        response = requests.post(
            f"{self.base_url}/orders", json=payload, headers=self.headers, timeout=15
        )
        response.raise_for_status()
        return response.json()

    def get_account(self) -> dict:
        """Hesap bakiyesi/alım gücü sorgusu (main.py'nin account_equity'yi
        gerçek hesaptan okuması için kullanılabilir — bkz. main.py TODO)."""
        response = requests.get(f"{self.base_url}/account", headers=self.headers, timeout=15)
        response.raise_for_status()
        return response.json()

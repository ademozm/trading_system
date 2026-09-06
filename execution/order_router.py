"""
Katman 6 — Execution: Order Router
======================================
Telegram'dan onay geldikten SONRA çağrılan tek yer burasıdır. Bu modül
dışında hiçbir katman gerçek emir gönderme yetkisine sahip olmamalıdır —
bu, "onay ile execution arasındaki duraklama asla bypass edilemez"
ilkesinin kod seviyesindeki karşılığıdır.

Artık İKİ backend'i destekler:
  - ccxt (kripto borsaları)
  - Alpaca (ABD hisse senetleri) — notional (dolar bazlı) market emirleri
Hangi backend'in kullanılacağı draft.symbol'ün formatından otomatik
belirlenir (bkz. signals.aggregator.infer_asset_class) — çağıran taraf
(main.py) hangi varlık sınıfıyla uğraştığını bilmek zorunda değildir,
Katman 1'deki adaptör deseninin execution tarafındaki karşılığı budur.
"""

from __future__ import annotations

import os
from typing import Optional

from execution.alpaca_trading_client import AlpacaTradingClient
from risk.risk_manager import ApprovedOrderDraft
from signals.aggregator import infer_asset_class

try:
    import ccxt
except ImportError:  # pragma: no cover
    ccxt = None


class OrderRouter:
    def __init__(
        self,
        exchange_id: str = "binance",
        dry_run: bool = True,
        alpaca_paper: bool = True,
    ) -> None:
        """
        dry_run=True (varsayılan): emirler GERÇEKTEN gönderilmez, sadece
        loglanır. Faz 5'e (küçük sermaye ile canlı test) geçene kadar bu
        varsayılan DEĞİŞTİRİLMEMELİDİR.

        alpaca_paper=True (varsayılan): hisse emirleri Alpaca'nın PAPER
        (kağıt üzerinde, gerçek para olmayan) ortamına gider. Gerçek
        hisse emri için bilinçli olarak alpaca_paper=False geçmeniz gerekir.

        Her iki backend de (ccxt/Alpaca) LAZY kurulur — yani sadece
        gerçekten o varlık sınıfında bir emir gönderilmeye çalışıldığında
        oluşturulur. Böylece sadece kripto kullanan biri Alpaca API
        anahtarı olmadan da bu sınıfı sorunsuz kullanabilir (ve tam tersi).
        """
        self.dry_run = dry_run
        self.exchange_id = exchange_id
        self.alpaca_paper = alpaca_paper
        self._ccxt_exchange = None
        self._alpaca_client: Optional[AlpacaTradingClient] = None

    def _get_ccxt_exchange(self):
        if self._ccxt_exchange is None:
            if ccxt is None:
                raise ImportError("ccxt kurulu değil: `pip install ccxt`")
            exchange_class = getattr(ccxt, self.exchange_id)
            self._ccxt_exchange = exchange_class(
                {
                    "apiKey": os.environ.get(f"{self.exchange_id.upper()}_API_KEY"),
                    "secret": os.environ.get(f"{self.exchange_id.upper()}_API_SECRET"),
                    "enableRateLimit": True,
                }
            )
        return self._ccxt_exchange

    def _get_alpaca_client(self) -> AlpacaTradingClient:
        if self._alpaca_client is None:
            self._alpaca_client = AlpacaTradingClient(
                api_key=os.environ.get("ALPACA_API_KEY", ""),
                secret_key=os.environ.get("ALPACA_API_SECRET", ""),
                paper=self.alpaca_paper,
            )
        return self._alpaca_client

    def route_order(self, draft: ApprovedOrderDraft, account_equity: float) -> dict:
        """
        Onaylanmış taslağı gerçek bir emre çevirir.

        account_equity: mevcut toplam portföy değeri (position_size_pct'i
        gerçek miktara çevirmek için gereklidir). Bu değer main.py
        tarafından güncel hesap bakiyesinden sağlanmalıdır.
        """
        notional = account_equity * draft.position_size_pct
        order_side = "buy" if draft.side == "long" else "sell"
        asset_class = infer_asset_class(draft.symbol)

        if self.dry_run:
            print(
                f"[order_router] (DRY-RUN, {asset_class}) {order_side.upper()} {draft.symbol} "
                f"~{notional:.2f} birim değerinde, kaldıraç={draft.leverage}x "
                f"— GERÇEK EMİR GÖNDERİLMEDİ."
            )
            return {
                "status": "dry_run", "symbol": draft.symbol, "side": order_side,
                "notional": notional, "asset_class": asset_class,
            }

        if asset_class == "equity":
            client = self._get_alpaca_client()
            order = client.place_market_order(draft.symbol, notional, order_side)
            print(f"[order_router] GERÇEK HİSSE EMRİ GÖNDERİLDİ ({'PAPER' if self.alpaca_paper else 'CANLI'}): {order}")
            return order

        # asset_class == "crypto" -> ccxt
        if draft.leverage > 1.0:
            raise NotImplementedError(
                f"'{draft.symbol}' için {draft.leverage}x kaldıraç istendi, ancak bu "
                "OrderRouter şu an sadece spot (kaldıraçsız) ccxt emirlerini destekliyor. "
                "Kaldıraçlı/futures emir göndermek ayrı bir uygulama gerektirir — "
                "yanlışlıkla yanlış boyutta bir pozisyon açılmasın diye durduruldu."
            )

        exchange = self._get_ccxt_exchange()
        ticker = exchange.fetch_ticker(draft.symbol)
        price = ticker["last"]
        amount = notional / price

        order = exchange.create_order(
            symbol=draft.symbol,
            type="market",
            side=order_side,
            amount=amount,
        )
        print(f"[order_router] GERÇEK KRİPTO EMRİ GÖNDERİLDİ: {order}")
        return order

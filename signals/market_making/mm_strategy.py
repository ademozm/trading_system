"""
Katman 3d — Piyasa Yapıcılığı Stratejisi (Faz 6 TAMAMLANDI)
================================================================
avellaneda_stoikov.py'deki saf matematiği, gerçek operasyonel kurallarla
(envanter limiti, tek taraflı kotasyon, minimum spread tabanı) sarar.

MİMARİ HATIRLATMA (tasarım belgesinden): Bu strateji signals/aggregator.py'ye
GİRMEZ. Yön tahmini yapan modüllerden (3a/3b/3c) bağımsız, kendi ayrı
hesap/pozisyon havuzunda çalışır — çünkü zaman ölçeği tamamen farklıdır
(saniyeler/dakikalar vs. saatler/günler). Bu yüzden RiskManager'ın mandate
kontrolünden GEÇMEZ; kendi ayrı envanter limitini kullanır (aşağıda).

ÖNEMLİ SINIRLAMA: Bu modül fiyat/envanter matematiğini doğru şekilde
uygular ve test eder, ANCAK gerçek zamanlı order book akışı (ccxt.pro/
WebSocket) ve gerçek emir gönderme/iptal döngüsü henüz bağlanmadı — bu,
mevcut mimarideki en yüksek mühendislik riski taşıyan parçadır (yüksek
frekans, yarış durumları/race condition potansiyeli). Canlıya almadan
önce mutlaka testnet/sandbox'ta kapsamlı test edin.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from signals.market_making.avellaneda_stoikov import QuoteResult, compute_quotes

logger = logging.getLogger(__name__)


@dataclass
class MarketMakingConfig:
    gamma: float = 0.1              # risk kaçınma katsayısı
    kappa: float = 1.5              # piyasa derinlik parametresi (order book'tan kalibre edilmeli)
    max_inventory: float = 1.0      # envanterin (birim cinsinden) mutlak sınırı
    min_spread_bps: float = 5.0     # modelin ürettiği spread bu tabanın altına düşerse buraya sabitlenir
    order_size: float = 0.1         # her kotasyonda kullanılacak sabit emir boyutu

    @classmethod
    def from_mandate(cls, mm_mandate) -> "MarketMakingConfig":
        """
        config/mandate.yaml -> Mandate.market_making bölümünden bu config'i
        üretir (bkz. risk/mandate.py:MarketMakingMandate). Tek doğruluk
        kaynağı YAML olsun diye — parametreleri burada elle tekrar
        yazmak yerine mandate'ten okuyun.
        """
        return cls(
            gamma=mm_mandate.gamma,
            kappa=mm_mandate.kappa,
            max_inventory=mm_mandate.max_inventory_per_symbol,
            min_spread_bps=mm_mandate.min_spread_bps,
        )


@dataclass
class Quote:
    bid_price: Optional[float]   # None ise bu tarafta kotasyon YOK (envanter limiti nedeniyle)
    ask_price: Optional[float]
    bid_size: float
    ask_size: float
    reservation_price: float
    raw_spread: float


class MarketMakingStrategy:
    def __init__(
        self, symbol: str, config: Optional[MarketMakingConfig] = None, initial_inventory: float = 0.0
    ) -> None:
        self.symbol = symbol
        self.config = config or MarketMakingConfig()
        self.inventory: float = initial_inventory  # dışarıdan (gerçek pozisyon güncellemelerinden) güncellenir

    def update_inventory(self, filled_qty: float, side: str) -> None:
        """Bir emir dolduğunda envanteri günceller. side: 'buy' | 'sell'."""
        if side == "buy":
            self.inventory += filled_qty
        elif side == "sell":
            self.inventory -= filled_qty
        else:
            raise ValueError(f"Geçersiz side: {side} ('buy' veya 'sell' olmalı)")

    def generate_quote(self, mid_price: float, sigma: float, time_remaining: float = 1.0) -> Quote:
        """
        Verilen piyasa durumuna göre bid/ask kotasyonu üretir.

        Envanter limiti mantığı: envanter zaten max_inventory'ye ulaştıysa
        (fazla LONG), o tarafı ARTIRACAK bid kotasyonu VERİLMEZ (None) —
        sadece envanteri azaltacak ask kotasyonu verilir. Simetrik olarak
        aşırı SHORT durumunda ask kotasyonu verilmez.
        """
        raw: QuoteResult = compute_quotes(
            mid_price=mid_price,
            inventory=self.inventory,
            gamma=self.config.gamma,
            sigma=sigma,
            time_remaining=time_remaining,
            kappa=self.config.kappa,
        )

        # Minimum spread tabanı: model çok dar bir spread önerirse (ör.
        # düşük volatilite anında), işlem maliyetlerini karşılamak için
        # bir tabana sabitlenir.
        min_spread_abs = mid_price * (self.config.min_spread_bps / 10_000)
        effective_spread = max(raw.spread, min_spread_abs)
        half_spread = effective_spread / 2

        bid_price: Optional[float] = raw.reservation_price - half_spread
        ask_price: Optional[float] = raw.reservation_price + half_spread

        if self.inventory >= self.config.max_inventory:
            logger.info(
                "%s envanter üst limitte (%.4f >= %.4f) — bid kotasyonu VERİLMİYOR.",
                self.symbol, self.inventory, self.config.max_inventory,
            )
            bid_price = None
        elif self.inventory <= -self.config.max_inventory:
            logger.info(
                "%s envanter alt limitte (%.4f <= %.4f) — ask kotasyonu VERİLMİYOR.",
                self.symbol, self.inventory, -self.config.max_inventory,
            )
            ask_price = None

        return Quote(
            bid_price=bid_price,
            ask_price=ask_price,
            bid_size=self.config.order_size,
            ask_size=self.config.order_size,
            reservation_price=raw.reservation_price,
            raw_spread=effective_spread,
        )

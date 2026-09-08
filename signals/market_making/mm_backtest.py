"""
Katman 3d/5 — Market Making Backtest (Fill Simülasyonu)
============================================================
Önceki oturumda işaretlediğim en yüksek riskli eksik: market making
modülünün gerçek zamanlı order book/emir döngüsüne henüz bağlı olmaması.
Bu dosya o riski TAMAMEN ortadan kaldırmaz (gerçek order book derinliği,
kuyruk pozisyonu, gecikme hâlâ modellenmiyor) ama en azından stratejinin
GEÇMİŞ VERİ üzerinde ne kadar makul davrandığını ölçmenizi sağlar —
gerçek paraya geçmeden önceki ilk ve zorunlu filtre budur.

FILL VARSAYIMI (basitleştirme — açıkça belirtiliyor):
    Bir sonraki barın en düşüğü (low) bizim bid fiyatımıza değdiyse
    ALIŞ dolmuş sayılır; bir sonraki barın en yükseği (high) bizim ask
    fiyatımıza değdiyse SATIŞ dolmuş sayılır. Bu, akademik/basit market
    making backtestlerinde yaygın bir yaklaşımdır ama şunları YOK SAYAR:
      - Kuyruk pozisyonu (aynı fiyat seviyesinde önünüzde kaç emir var)
      - Kısmi dolma
      - Latency (emrinizin borsaya ulaşma süresi)
    Bu yüzden buradaki sonuçlar GERÇEK canlı performansın bir ÜST SINIRI
    (iyimser tahmini) olarak okunmalıdır, kesin bir tahmin değil.

NAKİT KISITI (kritik düzeltme #1 — gerçek bir hataydı):
    Bu simülasyon CASH-SECURED (nakit ile tam karşılanan, kaldıraçsız spot)
    bir hesap varsayar — tıpkı execution/order_router.py'nin kripto tarafında
    kaldıraçlı emri açıkça reddetmesi gibi. Bir ALIŞ, ancak mevcut nakit
    bunu karşılıyorsa gerçekleşir; karşılamıyorsa o fill ATLANIR (sessizce
    kaydedilmez, `skipped_due_to_cash` sayacında görünür).

ENVANTER KISITI (kritik düzeltme #2 — gerçek bir hataydı, #1'den SONRA
bulundu): İlk düzeltmeden sonra bile sonuçlar hâlâ imkansızdı (%-100'ün
altında getiri/drawdown), çünkü SATIŞ tarafında hiçbir kısıt YOKTU — strateji
sahip olmadığı BTC'yi "açığa satabiliyordu" (naked short), bu da marjsız bir
spot hesapta mümkün olmayan bir şey. Artık bir SATIŞ, ancak mevcut envanter
bunu karşılıyorsa gerçekleşir (varsayılan `initial_inventory=0.0` ile
başlarsanız, ilk ALIŞ gerçekleşene kadar hiç SATIŞ fill'i olmaz — bu
DOĞRUDUR, gerçek bir spot hesapta da böyle olur). Karşılamıyorsa fill
`skipped_due_to_inventory` sayacında görünür.

Bu iki kısıt birlikte şunu garanti eder: nakit ASLA negatife düşmez,
envanter ASLA negatife düşmez — yani equity (cash + inventory*price) ASLA
başlangıç sermayesinin -%100'ünün altına inemez (matematiksel olarak
imkansız bir sonuç artık üretilemez).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from signals.market_making.mm_strategy import MarketMakingConfig, MarketMakingStrategy


@dataclass
class FillEvent:
    timestamp: object
    side: str  # "buy" | "sell"
    price: float
    size: float


@dataclass
class MMBacktestResult:
    equity_curve: pd.DataFrame  # sütunlar: timestamp, cash, inventory, mid_price, equity
    fills: list[FillEvent] = field(default_factory=list)
    skipped_due_to_cash: int = 0       # nakit yetersizliği nedeniyle atlanan ALIŞ fill sayısı
    skipped_due_to_inventory: int = 0  # envanter yetersizliği nedeniyle atlanan SATIŞ fill sayısı

    @property
    def total_return_pct(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        start = self.equity_curve["equity"].iloc[0]
        end = self.equity_curve["equity"].iloc[-1]
        if start == 0:
            return 0.0
        return (end / start - 1) * 100

    @property
    def max_drawdown_pct(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        running_max = self.equity_curve["equity"].cummax()
        drawdown = (self.equity_curve["equity"] - running_max) / running_max
        return float(drawdown.min() * 100)

    @property
    def fill_count(self) -> int:
        return len(self.fills)

    @property
    def final_inventory(self) -> float:
        if len(self.equity_curve) == 0:
            return 0.0
        return float(self.equity_curve["inventory"].iloc[-1])


def run_mm_backtest(
    df: pd.DataFrame,
    config: MarketMakingConfig,
    volatility_lookback: int = 20,
    initial_cash: float = 10_000.0,
    initial_inventory: float = 0.0,
) -> MMBacktestResult:
    """
    df: en az `timestamp`, `open`, `high`, `low`, `close` sütunlarını içermeli
        (data_layer.storage'ın standart şeması).
    config: MarketMakingConfig (bkz. mm_strategy.py) — mandate.yaml'dan
        MarketMakingConfig.from_mandate() ile de üretilebilir.

    Her bar için:
      1) O barın kapanışını "mid price" olarak kullanıp bir kotasyon üret
         (bir önceki `volatility_lookback` bar'ın getiri std sapmasını
         sigma olarak kullanarak).
      2) Kotasyonun BİR SONRAKİ barda dolup dolmadığını kontrol et (yukarıdaki
         fill varsayımıyla) — ALIŞ için ayrıca nakit yeterli mi kontrol edilir.
      3) Nakit/envanteri güncelle, mark-to-market equity hesapla.

    UYARI: `config.max_inventory` ile `initial_cash` uyumsuz seçilirse
    (ör. yüksek fiyatlı bir varlıkta küçük sermayeyle büyük bir envanter
    limiti), nakit kısıtı devreye girer ve stratejiniz sık sık
    `skipped_due_to_cash` ile karşılaşır — bu bir hata değil, sermayenizin
    o envanter limitini kaldıramadığının göstergesidir. `max_inventory`'yi
    `initial_cash`'e göre küçültün (kural of thumb: max_inventory * varlık
    fiyatı, initial_cash'in küçük bir katından fazla olmamalı).

    NOT: `initial_inventory=0.0` (varsayılan) ile başlarsanız, İLK ALIŞ
    gerçekleşene kadar hiçbir SATIŞ fill'i olmaz — bu DOĞRUDUR (elinizde
    satacak bir şey yok). Zaten elinizde bir miktar varlık varmış gibi
    başlamak isterseniz `initial_inventory` parametresini kullanın.
    """
    if len(df) < volatility_lookback + 2:
        raise ValueError(
            f"Backtest için en az {volatility_lookback + 2} bar gerekli, {len(df)} verildi."
        )

    returns = df["close"].pct_change()
    rolling_sigma = returns.rolling(window=volatility_lookback).std()

    strategy = MarketMakingStrategy(symbol="BACKTEST", config=config, initial_inventory=initial_inventory)
    cash = initial_cash
    fills: list[FillEvent] = []
    equity_rows: list[dict] = []
    skipped_due_to_cash = 0
    skipped_due_to_inventory = 0

    n = len(df)
    for i in range(volatility_lookback, n - 1):
        mid_price = float(df["close"].iloc[i])
        sigma = float(rolling_sigma.iloc[i])
        next_low = float(df["low"].iloc[i + 1])
        next_high = float(df["high"].iloc[i + 1])
        next_timestamp = df["timestamp"].iloc[i + 1]

        if pd.isna(sigma) or sigma <= 0:
            # Volatilite hesaplanamıyorsa (ör. fiyat hiç değişmemiş) bu barı atla
            equity_rows.append(
                {
                    "timestamp": next_timestamp,
                    "cash": cash,
                    "inventory": strategy.inventory,
                    "mid_price": mid_price,
                    "equity": cash + strategy.inventory * mid_price,
                }
            )
            continue

        quote = strategy.generate_quote(mid_price=mid_price, sigma=sigma, time_remaining=1.0)

        if quote.bid_price is not None and next_low <= quote.bid_price:
            buy_cost = quote.bid_price * quote.bid_size
            if cash >= buy_cost:
                strategy.update_inventory(quote.bid_size, side="buy")
                cash -= buy_cost
                fills.append(FillEvent(next_timestamp, "buy", quote.bid_price, quote.bid_size))
            else:
                # Nakit yetersiz -> cash-secured (kaldıraçsız) varsayımı
                # gereği bu fill GERÇEKLEŞMEZ. Gerçek bir spot hesapta da
                # aynen böyle olurdu: borsa bakiyeniz yetmeyen bir emri kabul
                # etmez.
                skipped_due_to_cash += 1

        if quote.ask_price is not None and next_high >= quote.ask_price:
            if strategy.inventory >= quote.ask_size:
                strategy.update_inventory(quote.ask_size, side="sell")
                cash += quote.ask_price * quote.ask_size
                fills.append(FillEvent(next_timestamp, "sell", quote.ask_price, quote.ask_size))
            else:
                # Envanter yetersiz -> spot (marjsız) varsayımı gereği "açığa
                # satış" YAPILMAZ. Gerçek bir spot hesapta da sahip olmadığınız
                # bir varlığı satamazsınız.
                skipped_due_to_inventory += 1

        equity_rows.append(
            {
                "timestamp": next_timestamp,
                "cash": cash,
                "inventory": strategy.inventory,
                "mid_price": float(df["close"].iloc[i + 1]),
                "equity": cash + strategy.inventory * float(df["close"].iloc[i + 1]),
            }
        )

    equity_curve = pd.DataFrame(equity_rows)
    return MMBacktestResult(
        equity_curve=equity_curve,
        fills=fills,
        skipped_due_to_cash=skipped_due_to_cash,
        skipped_due_to_inventory=skipped_due_to_inventory,
    )


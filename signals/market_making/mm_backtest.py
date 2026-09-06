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
         fill varsayımıyla).
      3) Nakit/envanteri güncelle, mark-to-market equity hesapla.
    """
    if len(df) < volatility_lookback + 2:
        raise ValueError(
            f"Backtest için en az {volatility_lookback + 2} bar gerekli, {len(df)} verildi."
        )

    returns = df["close"].pct_change()
    rolling_sigma = returns.rolling(window=volatility_lookback).std()

    strategy = MarketMakingStrategy(symbol="BACKTEST", config=config)
    cash = initial_cash
    fills: list[FillEvent] = []
    equity_rows: list[dict] = []

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
            strategy.update_inventory(quote.bid_size, side="buy")
            cash -= quote.bid_price * quote.bid_size
            fills.append(FillEvent(next_timestamp, "buy", quote.bid_price, quote.bid_size))

        if quote.ask_price is not None and next_high >= quote.ask_price:
            strategy.update_inventory(quote.ask_size, side="sell")
            cash += quote.ask_price * quote.ask_size
            fills.append(FillEvent(next_timestamp, "sell", quote.ask_price, quote.ask_size))

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
    return MMBacktestResult(equity_curve=equity_curve, fills=fills)

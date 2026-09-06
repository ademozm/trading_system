"""
Katman 3a — Klasik Kantitatif Sinyal: SMA Crossover
======================================================
İlk, en basit strateji: kısa dönem hareketli ortalama uzun dönemi yukarı
keserse LONG sinyali, aşağı keserse pozisyonu kapat. Amaç karmaşık bir
alpha değil — Katman 1-6'nın uçtan uca çalıştığını doğrulamak için bir
"iskele" (freqtrade'in `new-strategy` şablonuna benzer bir başlangıç noktası).

Bu dosya backtrader'ın `Strategy` sınıfını genişletir; bu yüzden hem
backtest'te (backtest/run_backtest.py üzerinden) hem canlıda (ileride
bir backtrader broker adaptörüyle) AYNI KODLA çalışabilir
(nautilus_trader'dan aldığımız "backtest = canlı" ilkesi).
"""

from __future__ import annotations

import backtrader as bt


class SmaCrossStrategy(bt.Strategy):
    params = dict(
        fast_period=10,
        slow_period=30,
        # Sinyal toplayıcıya (Katman 3e) aktarılacak güven skoru sabit
        # tutuluyor; ileride crossover'ın "gücüne" (ör. eğim farkına) göre
        # dinamikleştirilebilir.
        confidence=0.6,
    )

    def __init__(self) -> None:
        self.fast_sma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.p.fast_period
        )
        self.slow_sma = bt.indicators.SimpleMovingAverage(
            self.data.close, period=self.p.slow_period
        )
        self.crossover = bt.indicators.CrossOver(self.fast_sma, self.slow_sma)

        # Katman 7'ye (izleme) aktarılacak sinyal geçmişi
        self.signal_log: list[dict] = []

    def next(self) -> None:
        current_time = self.data.datetime.datetime(0)

        if self.crossover > 0 and not self.position:
            # Altın kesişim (golden cross) -> LONG adayı üret
            self._emit_candidate(current_time, side="long")
            self.buy()
        elif self.crossover < 0 and self.position:
            # Ölüm kesişimi (death cross) -> pozisyonu kapat
            self._emit_candidate(current_time, side="flat")
            self.close()

    def _emit_candidate(self, timestamp, side: str) -> None:
        """
        Gerçek sistemde bu metod, doğrudan emir vermek yerine
        signals.aggregator.SignalAggregator'a bir CandidateSignal
        gönderir (bkz. signals/aggregator.py). Backtest sadeliği için
        burada backtrader'ın kendi `buy()/close()` çağrılarını da
        kullanıyoruz; canlıya geçerken bu iki yol ayrıştırılmalı.
        """
        self.signal_log.append(
            {
                "timestamp": timestamp,
                "side": side,
                "fast_sma": float(self.fast_sma[0]),
                "slow_sma": float(self.slow_sma[0]),
                "confidence": self.p.confidence,
            }
        )

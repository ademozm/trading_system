"""
Katman 5 — Backtest & Simülasyon Motoru
==========================================
data_layer.storage'dan (Katman 2) veri okur, signals.classic'teki
(Katman 3a) stratejiyi backtrader üzerinde çalıştırır ve temel
performans metriklerini (Sharpe, max drawdown, toplam getiri) yazdırır.

Kritik ilke (nautilus_trader'dan): burada test edilen SmaCrossStrategy
sınıfı, canlıda kullanılacak sınıfla AYNIDIR — backtest için ayrı bir
"taklit" strateji yazılmamıştır. Değişen tek şey veri kaynağı ve emir
gönderim mekanizmasıdır (backtrader'ın kendi simüle brokerı vs. gerçek
borsa API'si).
"""

from __future__ import annotations

import argparse

import backtrader as bt
import pandas as pd

from signals.classic.sma_cross_strategy import SmaCrossStrategy


def load_dataframe_as_feed(parquet_path: str) -> bt.feeds.PandasData:
    df = pd.read_parquet(parquet_path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    df = df.set_index("timestamp")
    # backtrader PandasData sütun isimlerini bekler: open, high, low, close, volume
    return bt.feeds.PandasData(dataname=df)


def run(data_path: str, fast_period: int, slow_period: int, cash: float) -> None:
    cerebro = bt.Cerebro()
    cerebro.broker.setcash(cash)

    data_feed = load_dataframe_as_feed(data_path)
    cerebro.adddata(data_feed)

    cerebro.addstrategy(SmaCrossStrategy, fast_period=fast_period, slow_period=slow_period)

    # Katman 5'in "robustluk testleri" bölümünde bahsedilen metrikler için
    # backtrader'ın yerleşik analyzer'ları kullanılıyor.
    cerebro.addanalyzer(bt.analyzers.SharpeRatio, _name="sharpe")
    cerebro.addanalyzer(bt.analyzers.DrawDown, _name="drawdown")
    cerebro.addanalyzer(bt.analyzers.Returns, _name="returns")
    cerebro.addanalyzer(bt.analyzers.TradeAnalyzer, _name="trades")

    start_value = cerebro.broker.getvalue()
    print(f"[run_backtest] Başlangıç sermayesi: {start_value:.2f}")

    results = cerebro.run()
    strat = results[0]

    end_value = cerebro.broker.getvalue()
    print(f"[run_backtest] Bitiş sermayesi:     {end_value:.2f}")
    print(f"[run_backtest] Toplam getiri:       %{(end_value / start_value - 1) * 100:.2f}")

    sharpe = strat.analyzers.sharpe.get_analysis()
    drawdown = strat.analyzers.drawdown.get_analysis()
    trades = strat.analyzers.trades.get_analysis()

    print(f"[run_backtest] Sharpe oranı:        {sharpe.get('sharperatio')}")
    print(f"[run_backtest] Maks. drawdown:      %{drawdown.get('max', {}).get('drawdown', 'N/A')}")
    print(f"[run_backtest] Toplam işlem sayısı: {trades.get('total', {}).get('total', 0)}")

    print(
        "\n[UYARI] Bu sonuçlar sadece bu geçmiş veri penceresi için geçerlidir. "
        "Gerçek performans tahmini için mutlaka walk-forward validasyon ve "
        "look-ahead bias kontrolü yapın (bkz. tasarım belgesindeki Katman 5)."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Klasik SMA crossover stratejisini backtest et")
    parser.add_argument("--data", required=True, help="Parquet veri dosyasının yolu")
    parser.add_argument("--fast", type=int, default=10)
    parser.add_argument("--slow", type=int, default=30)
    parser.add_argument("--cash", type=float, default=10_000.0)
    args = parser.parse_args()

    run(args.data, args.fast, args.slow, args.cash)


if __name__ == "__main__":
    main()

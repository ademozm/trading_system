"""
backtest/run_mm_backtest.py — Market Making Backtest CLI
============================================================
Kullanım:
    python -m backtest.run_mm_backtest --data data/ohlcv/BTC_USDT_1h.parquet \
        --gamma 0.1 --kappa 1.5 --max-inventory 1.0 --order-size 0.1
"""

from __future__ import annotations

import argparse

import pandas as pd

from signals.market_making.mm_backtest import run_mm_backtest
from signals.market_making.mm_strategy import MarketMakingConfig


def main() -> None:
    parser = argparse.ArgumentParser(description="Market making stratejisini geçmiş veriyle simüle et")
    parser.add_argument("--data", required=True, help="Parquet OHLCV dosya yolu")
    parser.add_argument("--gamma", type=float, default=0.1)
    parser.add_argument("--kappa", type=float, default=1.5)
    parser.add_argument("--max-inventory", type=float, default=1.0)
    parser.add_argument("--min-spread-bps", type=float, default=5.0)
    parser.add_argument("--order-size", type=float, default=0.1)
    parser.add_argument("--volatility-lookback", type=int, default=20)
    parser.add_argument("--initial-cash", type=float, default=10_000.0)
    args = parser.parse_args()

    df = pd.read_parquet(args.data)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)

    config = MarketMakingConfig(
        gamma=args.gamma,
        kappa=args.kappa,
        max_inventory=args.max_inventory,
        min_spread_bps=args.min_spread_bps,
        order_size=args.order_size,
    )

    result = run_mm_backtest(
        df, config,
        volatility_lookback=args.volatility_lookback,
        initial_cash=args.initial_cash,
    )

    print(f"[run_mm_backtest] Toplam bar sayısı: {len(df)}")
    print(f"[run_mm_backtest] Toplam dolan emir: {result.fill_count}")
    print(f"[run_mm_backtest] Nihai envanter: {result.final_inventory:.4f}")
    print(f"[run_mm_backtest] Toplam getiri: %{result.total_return_pct:.3f}")
    print(f"[run_mm_backtest] Maks. drawdown: %{result.max_drawdown_pct:.3f}")
    print(
        "\n[UYARI] Bu sonuçlar basitleştirilmiş bir fill varsayımına dayanır "
        "(kuyruk pozisyonu, gecikme, kısmi dolma yok sayıldı). Gerçek canlı "
        "performansın bir ÜST SINIRI olarak okuyun, kesin bir tahmin değil. "
        "Canlıya geçmeden önce mutlaka testnet/sandbox'ta doğrulayın."
    )


if __name__ == "__main__":
    main()

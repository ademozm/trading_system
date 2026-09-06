"""
Katman 1 — Veri & Borsa Bağlantısı: ccxt Konnektörü
======================================================
Bu modül, ccxt üzerinden bir borsadan geçmiş OHLCV verisi çeker ve
Katman 2'nin (data_layer/storage.py) anlayacağı standart formatta
(pandas DataFrame -> Parquet) kaydeder.

Tasarım notu: Bu dosya "adaptör" desenini uygular — yarın Interactive
Brokers veya Alpaca için ayrı bir connector eklediğinizde, üst katmanlar
(sinyal üretimi, backtest) hiçbir şey bilmeden aynı standart DataFrame
şemasını (timestamp, open, high, low, close, volume) alacak.
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

try:
    import ccxt
except ImportError:  # pragma: no cover
    ccxt = None  # Ortamda kurulu değilse, import zamanında patlamasın;
    # sadece gerçekten kullanılınca hata versin (aşağıdaki kontrol).


STANDARD_COLUMNS = ["timestamp", "open", "high", "low", "close", "volume"]


def _require_ccxt() -> None:
    if ccxt is None:
        raise ImportError(
            "ccxt kurulu değil. `pip install ccxt` ile kurun "
            "(requirements.txt içinde tanımlı)."
        )


def fetch_ohlcv(
    exchange_id: str,
    symbol: str,
    timeframe: str = "1h",
    since_days: int = 365,
    limit_per_call: int = 1000,
) -> pd.DataFrame:
    """
    Belirtilen borsadan, belirtilen sembol/zaman dilimi için geçmiş OHLCV
    verisini sayfalayarak (paginate) çeker ve standart şemada bir
    DataFrame olarak döndürür.

    Not: ccxt'in rate-limit mekanizması (`enableRateLimit=True`) otomatik
    olarak devrededir; borsanın API limitlerini aşmamak için gerekli
    bekleme süresini kendisi ayarlar.
    """
    _require_ccxt()

    exchange_class = getattr(ccxt, exchange_id, None)
    if exchange_class is None:
        raise ValueError(
            f"'{exchange_id}' ccxt tarafından tanınan bir borsa değil. "
            "Geçerli isimler için `python -c \"import ccxt; print(ccxt.exchanges)\"` çalıştırın."
        )

    exchange = exchange_class({"enableRateLimit": True})

    since_ms = int(
        (datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000
    )

    all_rows: list[list] = []
    while True:
        batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=since_ms, limit=limit_per_call)
        if not batch:
            break
        all_rows.extend(batch)
        last_ts = batch[-1][0]
        if last_ts == since_ms:
            # İlerleme yoksa sonsuz döngüyü önle
            break
        since_ms = last_ts + 1
        if len(batch) < limit_per_call:
            break
        time.sleep(exchange.rateLimit / 1000)

    if not all_rows:
        raise RuntimeError(
            f"{exchange_id} / {symbol} / {timeframe} için hiç veri dönmedi. "
            "Sembol adını ve borsanın bu çifti destekleyip desteklemediğini kontrol edin."
        )

    df = pd.DataFrame(all_rows, columns=STANDARD_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    return df


def save_to_parquet(df: pd.DataFrame, symbol: str, timeframe: str, out_dir: str = "data/ohlcv") -> Path:
    """Katman 2'nin okuyacağı standart yola Parquet olarak yazar."""
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace("/", "_")
    file_path = out_path / f"{safe_symbol}_{timeframe}.parquet"
    df.to_parquet(file_path, index=False)
    return file_path


def main() -> None:
    parser = argparse.ArgumentParser(description="ccxt ile geçmiş OHLCV verisi indir")
    parser.add_argument("--exchange", required=True, help="ör. binance, bybit, okx")
    parser.add_argument("--symbol", required=True, help="ör. BTC/USDT")
    parser.add_argument("--timeframe", default="1h", help="ör. 1m, 5m, 1h, 1d")
    parser.add_argument("--days", type=int, default=365, help="kaç günlük geçmiş veri")
    parser.add_argument("--out-dir", default="data/ohlcv")
    args = parser.parse_args()

    print(f"[ccxt_connector] {args.exchange} / {args.symbol} / {args.timeframe} indiriliyor "
          f"({args.days} gün)...")
    df = fetch_ohlcv(args.exchange, args.symbol, args.timeframe, args.days)
    path = save_to_parquet(df, args.symbol, args.timeframe, args.out_dir)
    print(f"[ccxt_connector] {len(df)} satır yazıldı -> {path}")


if __name__ == "__main__":
    main()

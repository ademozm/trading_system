"""
Katman 2 — Veri Depolama & Yönetimi
======================================
Parquet dosyalarını DuckDB üzerinden sorgulanabilir hale getirir.
Ayrı bir veritabanı sunucusu gerekmez; DuckDB dosya tabanlı çalışır.

Nokta-in-time doğruluk notu: Bu katman şu an sadece OHLCV taşıyor.
Temel veri (fundamentals) veya haber/duygu verisi eklerseniz, her satıra
mutlaka bir `known_at` (bu bilginin ne zaman kamuya açıklandığı/bilindiği)
zaman damgası ekleyin — aksi halde backtest'te look-ahead bias oluşur
(TradingAgents projesinin CHANGELOG'unda bahsedilen "Alpha Vantage
look-ahead filtering" dersi tam olarak budur).
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import duckdb
import pandas as pd


class OHLCVStore:
    """Parquet tabanlı OHLCV verisine DuckDB ile sorgu arayüzü."""

    def __init__(self, data_dir: str = "data/ohlcv") -> None:
        self.data_dir = Path(data_dir)
        self._conn = duckdb.connect(database=":memory:")

    def _parquet_glob(self) -> str:
        return str(self.data_dir / "*.parquet")

    def load(
        self,
        symbol: str,
        timeframe: str,
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        Belirli bir sembol/zaman dilimi için, isteğe bağlı tarih aralığında
        veri döndürür. `start`/`end` "YYYY-MM-DD" formatında string olabilir.

        Neden DuckDB: dosya doğrudan Parquet'ten okunur, tüm veriyi belleğe
        yüklemeden filtreleme SQL motoru tarafından yapılır — büyük veri
        setlerinde pandas'tan çok daha verimlidir.
        """
        safe_symbol = symbol.replace("/", "_")
        file_path = self.data_dir / f"{safe_symbol}_{timeframe}.parquet"
        if not file_path.exists():
            raise FileNotFoundError(
                f"{file_path} bulunamadı. Önce "
                f"`python -m data_layer.connectors.ccxt_connector --symbol {symbol} "
                f"--timeframe {timeframe}` ile veri indirin."
            )

        query = f"SELECT * FROM read_parquet('{file_path.as_posix()}')"
        conditions = []
        if start:
            conditions.append(f"timestamp >= '{start}'")
        if end:
            conditions.append(f"timestamp <= '{end}'")
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        query += " ORDER BY timestamp"

        return self._conn.execute(query).fetchdf()

    def list_available(self) -> list[str]:
        """data_dir içindeki mevcut sembol/timeframe kombinasyonlarını listeler."""
        return sorted(p.stem for p in self.data_dir.glob("*.parquet"))

    def close(self) -> None:
        self._conn.close()


if __name__ == "__main__":
    # Hızlı manuel test: `python -m data_layer.storage`
    store = OHLCVStore()
    available = store.list_available()
    print("Mevcut veri setleri:", available or "(henüz veri indirilmedi)")

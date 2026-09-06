"""
Katman 1 — Veri & Broker Bağlantısı: Alpaca Konnektörü (Hisse Senedi)
==========================================================================
ccxt_connector.py'nin kripto tarafını kapsadığı gibi, bu dosya da hisse
senedi (ve Alpaca'nın desteklediği kripto çiftleri) tarafını kapsar.
Bilinçli olarak ağır `alpaca-py` SDK'sı yerine düz `requests` ile Alpaca'nın
REST API'sini çağırıyoruz — bu, bağımlılık yükünü azaltır ve API'nin ne
döndürdüğünü şeffaf tutar.

KRİTİK — Adaptör deseni (Katman 1'in temel ilkesi):
    fetch_ohlcv() burada da AYNI STANDART_COLUMNS şemasını
    (timestamp, open, high, low, close, volume) döndürür ve AYNI
    save_to_parquet() fonksiyonunu (ccxt_connector'dan içe aktarılan)
    kullanır. Bu sayede data_layer.storage, signals/*, backtest/* gibi
    üst katmanlar verinin kripto mu hisse mi olduğunu hiç bilmez —
    tasarım belgesindeki "yeni bir borsa/broker eklemek = yeni bir
    adaptör sınıfı yazmak, üst katmanlar değişmez" ilkesinin somut
    kanıtı budur.

Kimlik doğrulama: ALPACA_API_KEY / ALPACA_API_SECRET ortam değişkenleri
(bkz. .env.example). Ücretsiz bir "paper trading" hesabıyla dahi tarihsel
veri API'sine erişilebilir.
"""

from __future__ import annotations

import argparse
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Optional

import pandas as pd
import requests

from data_layer.connectors.ccxt_connector import STANDARD_COLUMNS, save_to_parquet

ALPACA_DATA_BASE_URL = "https://data.alpaca.markets/v2"

# Alpaca'nın kabul ettiği zaman dilimleri farklı isimlendirme kullanır
# (ccxt'in "1h"/"1d" formatından farklı olarak "1Hour"/"1Day"). Üst
# katmanların (ör. data_layer.storage) dosya adlandırmasında tutarlılık
# için ccxt tarzı kısa isimleri Alpaca'nın beklediği isimlere çeviriyoruz.
TIMEFRAME_MAP = {
    "1m": "1Min",
    "5m": "5Min",
    "15m": "15Min",
    "1h": "1Hour",
    "1d": "1Day",
}


def parse_alpaca_bars(response_json: dict) -> pd.DataFrame:
    """
    Alpaca'nın `/v2/stocks/{symbol}/bars` yanıtındaki `bars` listesini
    (her biri {"t": ISO zaman, "o", "h", "l", "c", "v", ...} sözlüğü)
    standart OHLCV şemasına çevirir.

    Bu fonksiyon BİLEREK ağdan bağımsızdır (saf JSON -> DataFrame) —
    böylece gerçek bir API çağrısı yapmadan, sentetik bir yanıt sözlüğüyle
    test edilebilir (bkz. tests/test_alpaca_connector.py).
    """
    bars = response_json.get("bars", [])
    if not bars:
        return pd.DataFrame(columns=STANDARD_COLUMNS)

    rows = [[b["t"], b["o"], b["h"], b["l"], b["c"], b["v"]] for b in bars]
    df = pd.DataFrame(rows, columns=STANDARD_COLUMNS)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = df[col].astype(float)
    return df.sort_values("timestamp").reset_index(drop=True)


def fetch_ohlcv(
    symbol: str,
    timeframe: str = "1h",
    since_days: int = 365,
    api_key: Optional[str] = None,
    api_secret: Optional[str] = None,
) -> pd.DataFrame:
    """
    Alpaca'dan sayfalayarak (pagination) geçmiş OHLCV verisi çeker.
    `symbol` Alpaca formatında olmalı (ör. "AAPL", "MSFT" — ccxt'teki gibi
    "/" ayraçlı değil).
    """
    api_key = api_key or os.environ.get("ALPACA_API_KEY")
    api_secret = api_secret or os.environ.get("ALPACA_API_SECRET")
    if not api_key or not api_secret:
        raise EnvironmentError(
            "ALPACA_API_KEY ve ALPACA_API_SECRET ortam değişkenleri (veya "
            "fonksiyon parametreleri) gerekli. bkz. .env.example."
        )

    alpaca_timeframe = TIMEFRAME_MAP.get(timeframe)
    if alpaca_timeframe is None:
        raise ValueError(
            f"'{timeframe}' desteklenmiyor. Geçerli değerler: {list(TIMEFRAME_MAP)}"
        )

    start = (datetime.now(timezone.utc) - timedelta(days=since_days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    headers = {"APCA-API-KEY-ID": api_key, "APCA-API-SECRET-KEY": api_secret}

    all_bars_json: list[dict] = []
    page_token: Optional[str] = None

    while True:
        params = {"timeframe": alpaca_timeframe, "start": start, "limit": 10_000}
        if page_token:
            params["page_token"] = page_token

        response = requests.get(
            f"{ALPACA_DATA_BASE_URL}/stocks/{symbol}/bars",
            headers=headers,
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()

        all_bars_json.extend(payload.get("bars", []))
        page_token = payload.get("next_page_token")
        if not page_token:
            break
        time.sleep(0.3)  # Alpaca rate limit'e karşı kibar bir bekleme

    if not all_bars_json:
        raise RuntimeError(
            f"{symbol} / {timeframe} için hiç veri dönmedi. Sembolü ve "
            f"hesabınızın bu veriye erişimi olup olmadığını kontrol edin."
        )

    return parse_alpaca_bars({"bars": all_bars_json})


def main() -> None:
    parser = argparse.ArgumentParser(description="Alpaca ile geçmiş hisse senedi OHLCV verisi indir")
    parser.add_argument("--symbol", required=True, help="ör. AAPL, MSFT")
    parser.add_argument("--timeframe", default="1h", choices=list(TIMEFRAME_MAP))
    parser.add_argument("--days", type=int, default=365)
    parser.add_argument("--out-dir", default="data/ohlcv")
    args = parser.parse_args()

    print(f"[alpaca_connector] {args.symbol} / {args.timeframe} indiriliyor ({args.days} gün)...")
    df = fetch_ohlcv(args.symbol, args.timeframe, args.days)
    # Not: save_to_parquet dosya adında "/" karakterini "_" yapıyor; hisse
    # sembollerinde zaten "/" olmadığı için bu no-op'tur ama fonksiyon
    # kripto/hisse arasında ORTAK kalsın diye burada da kullanılıyor.
    path = save_to_parquet(df, args.symbol, args.timeframe, args.out_dir)
    print(f"[alpaca_connector] {len(df)} satır yazıldı -> {path}")


if __name__ == "__main__":
    main()

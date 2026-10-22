"""
Çoklu sembol veri çekme katmanı.

Tasarım kararları:
- Cache-first: TTL süresi dolmamış veri diskte varsa tekrar indirilmez.
- Batch + delay: sembolller küçük gruplar halinde, aralarda bekleyerek
  indirilir (rate-limit koruması).
- Retry + backoff: geçici ağ hatalarında birkaç kez tekrar denenir.
- Kısmi başarısızlık toleransı: bir sembol başarısız olursa tüm tarama
  durmaz, o sembol "failed" listesine eklenir ve rapora not düşülür.
"""
import time
import logging
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf

import config
from data_pipeline import cache, stooq_fetcher

logger = logging.getLogger("fetcher")


@dataclass
class FetchResult:
    data: dict = field(default_factory=dict)     # symbol -> DataFrame
    failed: dict = field(default_factory=dict)    # symbol -> hata mesajı
    from_cache: set = field(default_factory=set)  # cache'den gelen semboller
    sources: dict = field(default_factory=dict)   # symbol -> "yfinance" | "stooq (yedek)"


def _fetch_one(symbol: str, period: str, interval: str) -> pd.DataFrame:
    last_err = None
    for attempt in range(1, config.FETCH_MAX_RETRIES + 1):
        try:
            df = yf.download(
                symbol, period=period, interval=interval,
                progress=False, auto_adjust=True, threads=False,
            )
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                raise ValueError("Boş veri döndü")

            # ÖNEMLİ: Forex-tarzı sembollerde (örn. XAUUSD=X gibi altın spot
            # fiyatı) Yahoo Finance genelde Hacim (Volume) verisi vermez —
            # tüm satırlarda NaN olabilir. Eskiden buradaki .dropna() 5
            # sütunu BİRDEN kontrol ediyordu; Volume sürekli NaN olan bir
            # sembolde bu TÜM satırları silip sessizce boş bir tablo
            # üretiyordu (hata fırlatmadan). Şimdi sadece asıl fiyat
            # sütunlarında (Open/High/Low/Close) NaN varsa o satır atılıyor;
            # eksik Hacim 0 ile dolduruluyor.
            result_df = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            result_df["Volume"] = result_df["Volume"].fillna(0)
            result_df = result_df.dropna(subset=["Open", "High", "Low", "Close"])

            if result_df.empty:
                raise ValueError("Fiyat verisi (Open/High/Low/Close) tamamen boş döndü")

            # ÖNEMLİ (v12): Eskiden burada sadece "tamamen boş mu" kontrol
            # ediliyordu — "yeterince veri var mı" kontrol edilmiyordu. Bu
            # yüzden ör. bir vadeli işlem sözleşmesi (CL=F, NG=F gibi)
            # rollover/sözleşme kısıtı yüzünden sadece birkaç günlük veri
            # dönse bile bu fonksiyon "başarılı" sayıyordu — ne yeniden
            # denenmiyor, ne alternatif sembol/Stooq yedeğine düşülüyordu.
            # Yetersizlik sadece ÇOK SONRA, validator.py'de fark ediliyordu
            # ve o noktada yedek kaynaklara geçmek için artık geç kalınmış
            # oluyordu. Artık MIN_ROWS_REQUIRED burada da kontrol ediliyor.
            if len(result_df) < config.MIN_ROWS_REQUIRED:
                raise ValueError(
                    f"Yetersiz veri: {len(result_df)} satır (min {config.MIN_ROWS_REQUIRED}) — "
                    f"vadeli işlem sözleşmesi rollover kısıtı olabilir"
                )
            return result_df
        except Exception as e:
            last_err = e
            logger.warning(f"{symbol} deneme {attempt}/{config.FETCH_MAX_RETRIES} başarısız: {e}")
            if attempt < config.FETCH_MAX_RETRIES:
                time.sleep(config.FETCH_RETRY_BACKOFF_SEC * attempt)
    raise RuntimeError(f"{symbol} indirilemedi: {last_err}")


def _fetch_with_alternates(symbol: str, period: str, interval: str) -> tuple[pd.DataFrame, str]:
    """
    _fetch_one'ı önce asıl sembolle, başarısız olursa config.ALTERNATE_TICKERS'taki
    alternatiflerle dener. Dönüş: (DataFrame, kullanılan_sembol).
    Hepsi başarısız olursa RuntimeError fırlatır (en son hatayı taşır).
    """
    candidates = [symbol] + config.ALTERNATE_TICKERS.get(symbol, [])
    last_err = None
    for candidate in candidates:
        try:
            df = _fetch_one(candidate, period, interval)
            if candidate != symbol:
                logger.info(f"{symbol}: asıl sembol başarısız oldu, alternatif '{candidate}' ile alındı.")
            return df, candidate
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"{symbol} ve tüm alternatifleri başarısız: {last_err}")


def fetch_universe(
    symbols: list[str],
    period: str = None,
    interval: str = None,
    use_cache: bool = True,
    market_by_symbol: dict = None,
) -> FetchResult:
    """
    market_by_symbol: {symbol: market} eşlemesi verilirse, yfinance bir
    sembol için tüm denemelerinde başarısız olursa, Stooq.com'dan (ikinci,
    bağımsız bir kaynak) o sembolü çekmeyi dener. BIST için Stooq güvenilir
    kapsam sağlamadığından oraya düşülmez (bkz. stooq_fetcher.map_to_stooq).
    Verilmezse (None), sadece yfinance kullanılır — geriye dönük uyumluluk.
    """
    period = period or config.FETCH_PERIOD
    interval = interval or config.FETCH_INTERVAL
    result = FetchResult()

    to_fetch = []
    for sym in symbols:
        if use_cache:
            cached_df = cache.get_cached(sym, interval)
            if cached_df is not None:
                result.data[sym] = cached_df
                result.from_cache.add(sym)
                continue
        to_fetch.append(sym)

    logger.info(f"{len(result.from_cache)} sembol cache'den, {len(to_fetch)} sembol indirilecek.")

    for i in range(0, len(to_fetch), config.FETCH_BATCH_SIZE):
        batch = to_fetch[i:i + config.FETCH_BATCH_SIZE]
        for sym in batch:
            try:
                df, used_ticker = _fetch_with_alternates(sym, period, interval)
                result.data[sym] = df
                result.sources[sym] = "yfinance" if used_ticker == sym else f"yfinance ({used_ticker})"
                cache.set_cached(sym, interval, df)
            except Exception as e:
                # yfinance tükendi; market biliniyorsa Stooq'u dene (ikinci kaynak)
                fallback_df = None
                if market_by_symbol is not None:
                    market = market_by_symbol.get(sym)
                    try:
                        fallback_df = stooq_fetcher.fetch_with_fallback(sym, market)
                    except Exception as stooq_err:
                        logger.warning(f"{sym} Stooq yedeği de başarısız: {stooq_err}")

                if fallback_df is not None and len(fallback_df) >= config.MIN_ROWS_REQUIRED:
                    logger.info(f"{sym}: yfinance başarısız oldu, Stooq'tan (yedek kaynak) alındı.")
                    result.data[sym] = fallback_df
                    result.sources[sym] = "stooq (yedek)"
                    cache.set_cached(sym, interval, fallback_df)
                else:
                    result.failed[sym] = str(e)
        if i + config.FETCH_BATCH_SIZE < len(to_fetch):
            time.sleep(config.FETCH_BATCH_DELAY_SEC)

    return result

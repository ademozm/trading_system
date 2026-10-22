from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

from data_pipeline import fetcher


def _make_ohlcv_df(n=100, all_volume_nan=False, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    df = pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1, "Close": close,
        "Volume": [np.nan] * n if all_volume_nan else rng.integers(1000, 5000, n),
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))
    return df


def test_fetch_one_normal_data_succeeds():
    df = _make_ohlcv_df(100)
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        result = fetcher._fetch_one("AAPL", "1y", "1d")
    assert len(result) == 100
    assert "Volume" in result.columns


def test_fetch_one_all_nan_volume_does_not_wipe_all_rows():
    """
    REGRESYON TESTİ: Bu, altın (XAUUSD=X) sembolünde yaşanan gerçek hatayı
    yakalıyor. Forex-tarzı sembollerde Volume sürekli NaN olabilir; eski
    kod .dropna() ile 5 sütunu birden kontrol ettiği için bu durumda TÜM
    satırları sessizce siliyordu. Artık sadece fiyat sütunları (OHLC)
    kontrol ediliyor, eksik Volume 0'a tamamlanıyor.
    """
    df = _make_ohlcv_df(100, all_volume_nan=True)
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        result = fetcher._fetch_one("XAUUSD=X", "1y", "1d")
    assert len(result) == 100, "Volume NaN olsa bile fiyat verisi korunmalı"
    assert (result["Volume"] == 0).all()


def test_fetch_one_nan_in_close_price_drops_only_that_row():
    df = _make_ohlcv_df(100)
    df.iloc[10, df.columns.get_loc("Close")] = np.nan
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        result = fetcher._fetch_one("AAPL", "1y", "1d")
    assert len(result) == 99


def test_fetch_one_empty_download_raises():
    with patch("data_pipeline.fetcher.yf.download", return_value=pd.DataFrame()):
        with pytest.raises(RuntimeError):
            fetcher._fetch_one("FAKE", "1y", "1d")


def test_fetch_one_multiindex_columns_flattened():
    df = _make_ohlcv_df(100)
    df.columns = pd.MultiIndex.from_product([df.columns, ["AAPL"]])
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        result = fetcher._fetch_one("AAPL", "1y", "1d")
    assert list(result.columns) == ["Open", "High", "Low", "Close", "Volume"]


def test_fetch_one_retries_on_failure_then_succeeds():
    df = _make_ohlcv_df(100)
    call_count = {"n": 0}

    def side_effect(*args, **kwargs):
        call_count["n"] += 1
        if call_count["n"] < 2:
            raise ConnectionError("geçici ağ hatası")
        return df

    with patch("data_pipeline.fetcher.yf.download", side_effect=side_effect):
        with patch("data_pipeline.fetcher.time.sleep"):  # testte gerçekten bekleme
            result = fetcher._fetch_one("AAPL", "1y", "1d")
    assert len(result) == 100
    assert call_count["n"] == 2


def test_fetch_one_insufficient_rows_raises():
    """
    REGRESYON TESTİ: Bu, gerçek altın/emtia hatasının kök sebebini yakalıyor.
    Bir vadeli işlem sözleşmesi (CL=F, NG=F gibi) rollover kısıtı yüzünden
    MIN_ROWS_REQUIRED'in altında veri dönebilir. Eskiden bu "başarılı" sayılıp
    sessizce cache'leniyordu, yedek kaynağa hiç düşülmüyordu — sadece çok
    sonra validator.py'de fark ediliyordu. Artık burada da kontrol ediliyor.
    """
    df = _make_ohlcv_df(30)  # config.MIN_ROWS_REQUIRED (60) altında
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        with patch("data_pipeline.fetcher.time.sleep"):
            with pytest.raises(RuntimeError, match="Yetersiz veri"):
                fetcher._fetch_one("CL=F", "1y", "1d")


def test_fetch_with_alternates_uses_primary_when_it_succeeds():
    df = _make_ohlcv_df(100)
    with patch("data_pipeline.fetcher.yf.download", return_value=df):
        result_df, used_ticker = fetcher._fetch_with_alternates("XAUUSD=X", "1y", "1d")
    assert used_ticker == "XAUUSD=X"
    assert len(result_df) == 100


def test_fetch_with_alternates_falls_back_to_alternate_ticker():
    good_df = _make_ohlcv_df(100)
    bad_df = _make_ohlcv_df(10)  # yetersiz

    def side_effect(symbol, *args, **kwargs):
        return bad_df if symbol == "XAUUSD=X" else good_df

    with patch("data_pipeline.fetcher.yf.download", side_effect=side_effect):
        with patch("data_pipeline.fetcher.time.sleep"):
            result_df, used_ticker = fetcher._fetch_with_alternates("XAUUSD=X", "1y", "1d")
    assert used_ticker == "GC=F"  # config.ALTERNATE_TICKERS'taki alternatif
    assert len(result_df) == 100


def test_fetch_with_alternates_all_fail_raises():
    bad_df = _make_ohlcv_df(5)
    with patch("data_pipeline.fetcher.yf.download", return_value=bad_df):
        with patch("data_pipeline.fetcher.time.sleep"):
            with pytest.raises(RuntimeError, match="tüm alternatifleri başarısız"):
                fetcher._fetch_with_alternates("XAUUSD=X", "1y", "1d")


def test_fetch_with_alternates_symbol_without_alternates_raises_normally():
    bad_df = _make_ohlcv_df(5)
    with patch("data_pipeline.fetcher.yf.download", return_value=bad_df):
        with patch("data_pipeline.fetcher.time.sleep"):
            with pytest.raises(RuntimeError):
                fetcher._fetch_with_alternates("AAPL", "1y", "1d")  # alternatifi yok


def test_fetch_universe_uses_cache_when_available():
    cached_df = _make_ohlcv_df(30)
    with patch("data_pipeline.fetcher.cache.get_cached", return_value=cached_df):
        result = fetcher.fetch_universe(["AAPL"], use_cache=True)
    assert "AAPL" in result.data
    assert "AAPL" in result.from_cache


def test_fetch_universe_falls_back_to_stooq_on_yfinance_failure():
    stooq_df = _make_ohlcv_df(80)
    with patch("data_pipeline.fetcher.cache.get_cached", return_value=None), \
         patch("data_pipeline.fetcher.cache.set_cached"), \
         patch("data_pipeline.fetcher._fetch_one", side_effect=RuntimeError("yfinance başarısız")), \
         patch("data_pipeline.fetcher.stooq_fetcher.fetch_with_fallback", return_value=stooq_df), \
         patch("data_pipeline.fetcher.time.sleep"):
        result = fetcher.fetch_universe(["XAUUSD=X"], use_cache=False,
                                          market_by_symbol={"XAUUSD=X": "emtia"})
    assert "XAUUSD=X" in result.data
    assert result.sources["XAUUSD=X"] == "stooq (yedek)"
    assert "XAUUSD=X" not in result.failed


def test_fetch_universe_marks_failed_when_both_sources_fail():
    with patch("data_pipeline.fetcher.cache.get_cached", return_value=None), \
         patch("data_pipeline.fetcher._fetch_one", side_effect=RuntimeError("yfinance başarısız")), \
         patch("data_pipeline.fetcher.stooq_fetcher.fetch_with_fallback", return_value=None), \
         patch("data_pipeline.fetcher.time.sleep"):
        result = fetcher.fetch_universe(["FAKE"], use_cache=False, market_by_symbol={"FAKE": "us"})
    assert "FAKE" in result.failed
    assert "FAKE" not in result.data


def test_fetch_universe_no_market_map_skips_stooq_fallback():
    with patch("data_pipeline.fetcher.cache.get_cached", return_value=None), \
         patch("data_pipeline.fetcher._fetch_one", side_effect=RuntimeError("yfinance başarısız")), \
         patch("data_pipeline.fetcher.time.sleep"):
        result = fetcher.fetch_universe(["FAKE"], use_cache=False, market_by_symbol=None)
    assert "FAKE" in result.failed


def test_fetch_universe_stooq_result_too_short_marked_failed():
    short_df = _make_ohlcv_df(3)  # config.MIN_ROWS_REQUIRED'in altında
    with patch("data_pipeline.fetcher.cache.get_cached", return_value=None), \
         patch("data_pipeline.fetcher._fetch_one", side_effect=RuntimeError("yfinance başarısız")), \
         patch("data_pipeline.fetcher.stooq_fetcher.fetch_with_fallback", return_value=short_df), \
         patch("data_pipeline.fetcher.time.sleep"):
        result = fetcher.fetch_universe(["XAUUSD=X"], use_cache=False,
                                          market_by_symbol={"XAUUSD=X": "emtia"})
    assert "XAUUSD=X" in result.failed

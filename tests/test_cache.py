import os
import time

import numpy as np
import pandas as pd
import pytest

from data_pipeline import cache


@pytest.fixture
def temp_cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache.config, "CACHE_DIR", str(tmp_path))
    return tmp_path


def _sample_df(n=20):
    return pd.DataFrame({
        "Open": np.arange(n, dtype=float), "High": np.arange(n, dtype=float) + 1,
        "Low": np.arange(n, dtype=float) - 1, "Close": np.arange(n, dtype=float),
        "Volume": np.arange(n),
    }, index=pd.date_range("2026-01-01", periods=n, freq="D"))


def test_get_cached_returns_none_when_no_file(temp_cache_dir):
    assert cache.get_cached("AAPL", "1d") is None


def test_set_and_get_cached_roundtrip(temp_cache_dir):
    df = _sample_df()
    cache.set_cached("AAPL", "1d", df)
    result = cache.get_cached("AAPL", "1d")
    assert result is not None
    assert len(result) == len(df)
    pd.testing.assert_frame_equal(result, df, check_freq=False)


def test_get_cached_respects_ttl_expiry(temp_cache_dir):
    df = _sample_df()
    cache.set_cached("AAPL", "1d", df)
    # ttl_minutes=0 -> her şey "eski" sayılmalı (yaş > 0 dakika her zaman doğru)
    result = cache.get_cached("AAPL", "1d", ttl_minutes=0)
    assert result is None


def test_get_cached_within_ttl_returns_data(temp_cache_dir):
    df = _sample_df()
    cache.set_cached("AAPL", "1d", df)
    result = cache.get_cached("AAPL", "1d", ttl_minutes=999999)
    assert result is not None


def test_cache_path_sanitizes_special_characters(temp_cache_dir):
    # "=" ve "/" gibi karakterler dosya sistemi için sorun çıkarabilir (örn. XAUUSD=X)
    path = cache._cache_path("USDTRY=X", "1d")
    assert "=" not in os.path.basename(path)
    assert "/" not in os.path.basename(path)


def test_set_cached_different_symbols_dont_collide(temp_cache_dir):
    df1 = _sample_df(10)
    df2 = _sample_df(20)
    cache.set_cached("AAPL", "1d", df1)
    cache.set_cached("MSFT", "1d", df2)
    result1 = cache.get_cached("AAPL", "1d")
    result2 = cache.get_cached("MSFT", "1d")
    assert len(result1) == 10
    assert len(result2) == 20


def test_set_cached_different_intervals_dont_collide(temp_cache_dir):
    df_daily = _sample_df(10)
    df_hourly = _sample_df(30)
    cache.set_cached("AAPL", "1d", df_daily)
    cache.set_cached("AAPL", "1h", df_hourly)
    assert len(cache.get_cached("AAPL", "1d")) == 10
    assert len(cache.get_cached("AAPL", "1h")) == 30


def test_cache_age_minutes_none_when_no_file(temp_cache_dir):
    assert cache.cache_age_minutes("AAPL", "1d") is None


def test_cache_age_minutes_positive_after_write(temp_cache_dir):
    cache.set_cached("AAPL", "1d", _sample_df())
    age = cache.cache_age_minutes("AAPL", "1d")
    assert age is not None
    assert age >= 0


def test_get_cached_corrupted_file_returns_none(temp_cache_dir):
    path = cache._cache_path("AAPL", "1d")
    with open(path, "w") as f:
        f.write("bu gecerli bir parquet dosyasi degil")
    result = cache.get_cached("AAPL", "1d")
    assert result is None


def test_forex_symbol_cache_roundtrip(temp_cache_dir):
    """Döviz sembolündeki (USDTRY=X) '=' karakteri cache dosya adında sorun çıkarmamalı."""
    df = _sample_df()
    cache.set_cached("USDTRY=X", "1d", df)
    result = cache.get_cached("USDTRY=X", "1d")
    assert result is not None
    assert len(result) == len(df)

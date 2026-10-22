"""
Basit, dosya tabanlı TTL (time-to-live) cache.

Amaç: aynı gün içinde birden fazla tarama yapılınca aynı sembolü
tekrar tekrar indirmemek — hem hızlı olur hem de veri sağlayıcısı
tarafından rate-limit'e takılma riskini azaltır.
"""
import os
import time
import pandas as pd

import config


def _cache_path(symbol: str, interval: str) -> str:
    safe_symbol = symbol.replace("/", "_").replace("=", "_")
    return os.path.join(config.CACHE_DIR, f"{safe_symbol}_{interval}.parquet")


def get_cached(symbol: str, interval: str, ttl_minutes: int = None) -> pd.DataFrame | None:
    ttl_minutes = ttl_minutes if ttl_minutes is not None else config.CACHE_TTL_MINUTES
    path = _cache_path(symbol, interval)
    if not os.path.exists(path):
        return None

    age_minutes = (time.time() - os.path.getmtime(path)) / 60
    if age_minutes > ttl_minutes:
        return None

    try:
        return pd.read_parquet(path)
    except Exception:
        return None


def set_cached(symbol: str, interval: str, df: pd.DataFrame) -> None:
    path = _cache_path(symbol, interval)
    df.to_parquet(path)


def cache_age_minutes(symbol: str, interval: str) -> float | None:
    path = _cache_path(symbol, interval)
    if not os.path.exists(path):
        return None
    return (time.time() - os.path.getmtime(path)) / 60

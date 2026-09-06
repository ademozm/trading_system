"""
tests/test_mm_backtest.py
============================
run_mm_backtest'in fill mantığının ve equity/drawdown hesaplarının doğru
çalıştığını doğrular. Sadece pandas/numpy gerektirir (duckdb/lightgbm
gerekmez), bu yüzden bu ortamda tam olarak çalıştırılabilir.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.market_making.mm_backtest import run_mm_backtest
from signals.market_making.mm_strategy import MarketMakingConfig


def _make_flat_then_spike_df(n: int = 60) -> pd.DataFrame:
    """
    İlk kısım düz (volatilite ısınması için), ortada fiyat aşağı-yukarı
    salınıyor (böylece hem bid hem ask'ın dolma ihtimali olsun).
    """
    rng = np.random.default_rng(7)
    base = 100 + np.cumsum(rng.normal(0, 0.3, n))
    high = base + np.abs(rng.normal(0.5, 0.3, n))
    low = base - np.abs(rng.normal(0.5, 0.3, n))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
            "open": base,
            "high": high,
            "low": low,
            "close": base,
            "volume": np.full(n, 100.0),
        }
    )


def test_backtest_raises_on_too_short_series() -> None:
    df = _make_flat_then_spike_df(n=5)
    try:
        run_mm_backtest(df, MarketMakingConfig(), volatility_lookback=20)
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_backtest_produces_equity_curve_with_correct_length() -> None:
    df = _make_flat_then_spike_df(n=60)
    result = run_mm_backtest(df, MarketMakingConfig(order_size=0.1), volatility_lookback=20)
    # i, volatility_lookback'ten n-2'ye kadar döner -> (n - 1 - volatility_lookback) satır
    expected_rows = 60 - 1 - 20
    assert len(result.equity_curve) == expected_rows


def test_backtest_produces_some_fills_on_oscillating_price() -> None:
    df = _make_flat_then_spike_df(n=100)
    result = run_mm_backtest(df, MarketMakingConfig(order_size=0.1), volatility_lookback=20)
    assert result.fill_count > 0, "Salınımlı fiyatta en azından bazı emirler dolmalı"


def test_backtest_respects_inventory_limit() -> None:
    df = _make_flat_then_spike_df(n=150)
    config = MarketMakingConfig(order_size=0.1, max_inventory=0.3)
    result = run_mm_backtest(df, config, volatility_lookback=20)
    # Envanter hiçbir zaman limitin ÇOK ötesine geçmemeli (bir fill'lik pay ile)
    max_abs_inventory = result.equity_curve["inventory"].abs().max()
    assert max_abs_inventory <= config.max_inventory + config.order_size + 1e-9


def test_backtest_equity_never_none_and_is_finite() -> None:
    df = _make_flat_then_spike_df(n=80)
    result = run_mm_backtest(df, MarketMakingConfig(), volatility_lookback=20)
    assert result.equity_curve["equity"].notna().all()
    assert np.isfinite(result.equity_curve["equity"]).all()


def test_total_return_and_drawdown_are_computed() -> None:
    df = _make_flat_then_spike_df(n=80)
    result = run_mm_backtest(df, MarketMakingConfig(), volatility_lookback=20)
    # Sadece hesaplanabilir ve mantıklı bir aralıkta olduğunu doğrula
    assert isinstance(result.total_return_pct, float)
    assert result.max_drawdown_pct <= 0.0  # drawdown her zaman <= 0 olmalı

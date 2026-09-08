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


def test_cash_secured_buys_never_push_cash_negative() -> None:
    """
    KRİTİK REGRESYON TESTİ: Bu test, önceki sürümde bulunan gerçek bir
    hatayı önlemek için eklendi — nakit kısıtı olmadan simülasyon
    sınırsız kaldıraçla işlem yapıyor ve imkansız (%-100'ün altında)
    getiri/drawdown değerleri üretiyordu. Küçük bir initial_cash ve
    büyük bir max_inventory ile bu senaryoyu bilerek tetikliyoruz.
    """
    df = _make_flat_then_spike_df(n=150)
    config = MarketMakingConfig(order_size=0.5, max_inventory=10.0)  # bilerek aşırı büyük
    result = run_mm_backtest(df, config, volatility_lookback=20, initial_cash=100.0)  # bilerek küçük
    assert (result.equity_curve["cash"] >= 0).all(), "Cash-secured varsayımı gereği nakit ASLA negatif olmamalı"
    assert result.skipped_due_to_cash > 0, "Bu senaryoda nakit yetersizliği nedeniyle atlanan fill OLMALI"


def test_ample_cash_means_no_skipped_fills() -> None:
    # Nakit bol olduğunda, sınır sadece envanter limitinden gelmeli
    df = _make_flat_then_spike_df(n=100)
    config = MarketMakingConfig(order_size=0.1, max_inventory=1.0)
    result = run_mm_backtest(df, config, volatility_lookback=20, initial_cash=1_000_000.0)
    assert result.skipped_due_to_cash == 0


def test_inventory_never_negative_without_initial_inventory() -> None:
    """
    KRİTİK REGRESYON TESTİ #2: cash kısıtı eklendikten SONRA bile hâlâ
    imkansız (%-100'ün altında) sonuçlar üretiliyordu — çünkü SATIŞ
    tarafında hiçbir kısıt yoktu (sahip olunmayan varlığın "açığa
    satılması"). initial_inventory=0.0 ile başlarken hiçbir SATIŞ,
    envanter o SATIŞı karşılamadan gerçekleşmemeli.
    """
    df = _make_flat_then_spike_df(n=150)
    config = MarketMakingConfig(order_size=0.1, max_inventory=1.0)
    result = run_mm_backtest(df, config, volatility_lookback=20, initial_cash=10_000.0, initial_inventory=0.0)
    assert (result.equity_curve["inventory"] >= 0).all(), "initial_inventory=0 iken envanter ASLA negatif olmamalı"
    assert (result.equity_curve["cash"] >= 0).all(), "Cash-secured varsayımı gereği nakit ASLA negatif olmamalı"
    # Equity, başlangıç sermayesinin -%100'ünden AZ olamaz (matematiksel imkansızlık testi)
    assert result.total_return_pct > -100.0


def test_initial_inventory_allows_immediate_sells() -> None:
    # Elinizde zaten varlık varsa, ilk ALIŞ beklemeden SATIŞ fill'i olabilmeli
    df = _make_flat_then_spike_df(n=100)
    config = MarketMakingConfig(order_size=0.1, max_inventory=1.0)
    result = run_mm_backtest(
        df, config, volatility_lookback=20, initial_cash=10_000.0, initial_inventory=0.5
    )
    # skipped_due_to_inventory, envantersiz başlayan senaryoya göre daha az olmalı
    result_no_inventory = run_mm_backtest(
        df, config, volatility_lookback=20, initial_cash=10_000.0, initial_inventory=0.0
    )
    assert result.skipped_due_to_inventory <= result_no_inventory.skipped_due_to_inventory

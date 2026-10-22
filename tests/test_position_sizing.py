import numpy as np
import pandas as pd
import pytest

from analysis import position_sizing as ps


def test_suggest_position_size_basic_long():
    result = ps.suggest_position_size(account_size=10000, entry_price=100, stop_price=95, risk_per_trade_pct=1.0)
    # Risk tutarı: 10000 * 0.01 = 100. Stop mesafesi: 5. Adet: 100/5 = 20.
    assert result["risk_tutari"] == 100.0
    assert result["onerilen_adet"] == 20.0
    assert result["pozisyon_buyuklugu"] == 2000.0
    assert result["portfoy_yuzdesi"] == 20.0


def test_suggest_position_size_zero_account_returns_none():
    result = ps.suggest_position_size(account_size=0, entry_price=100, stop_price=95)
    assert result["onerilen_adet"] is None


def test_suggest_position_size_zero_stop_distance_returns_none():
    result = ps.suggest_position_size(account_size=10000, entry_price=100, stop_price=100)
    assert result["onerilen_adet"] is None


def test_suggest_position_size_caps_at_full_account():
    # Çok dar stop mesafesi -> normalde hesap büyüklüğünü aşan bir pozisyon önerir, sınırlanmalı
    result = ps.suggest_position_size(account_size=10000, entry_price=100, stop_price=99.99, risk_per_trade_pct=5.0)
    assert result["pozisyon_buyuklugu"] <= 10000
    assert result["portfoy_yuzdesi"] <= 100.0


def test_suggest_position_size_negative_entry_price_handled():
    result = ps.suggest_position_size(account_size=10000, entry_price=-10, stop_price=5)
    assert result["onerilen_adet"] is None


def test_compute_for_scored_df_empty_returns_empty():
    result = ps.compute_for_scored_df(pd.DataFrame(), account_size=10000)
    assert result.empty


def test_compute_for_scored_df_adds_sizing_columns():
    df = pd.DataFrame({
        "symbol": ["AAA", "BBB"],
        "close": [100.0, 50.0],
        "atr_pct": [2.0, 3.0],
        "signal": [1, -1],
    })
    result = ps.compute_for_scored_df(df, account_size=10000, risk_per_trade_pct=1.0)
    assert "onerilen_adet" in result.columns
    assert "pozisyon_buyuklugu" in result.columns
    assert result.loc[result["symbol"] == "AAA", "onerilen_adet"].iloc[0] > 0
    assert result.loc[result["symbol"] == "BBB", "onerilen_adet"].iloc[0] > 0


def test_compute_for_scored_df_handles_missing_data_gracefully():
    df = pd.DataFrame({
        "symbol": ["AAA"],
        "close": [np.nan],
        "atr_pct": [2.0],
        "signal": [1],
    })
    result = ps.compute_for_scored_df(df, account_size=10000)
    assert result.loc[0, "onerilen_adet"] is None or pd.isna(result.loc[0, "onerilen_adet"])


def test_compute_for_scored_df_zero_signal_no_sizing():
    df = pd.DataFrame({
        "symbol": ["AAA"],
        "close": [100.0],
        "atr_pct": [2.0],
        "signal": [0],
    })
    result = ps.compute_for_scored_df(df, account_size=10000)
    assert pd.isna(result.loc[0, "onerilen_adet"])

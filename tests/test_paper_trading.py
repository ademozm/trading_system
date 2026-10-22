import os

import numpy as np
import pandas as pd
import pytest

from analysis import paper_trading as pt


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test_paper.db")


def _price_series(prices):
    # ÖNEMLİ: entry_date gerçek datetime.now() kullanıyor (paper_trading.py'de).
    # update_open_positions'taki "df.index > entry_date" filtresinin veriyi
    # ELEMEMESİ için, serinin SONUNU gerçek "şimdi"den kesin olarak İLERİYE
    # sabitliyoruz (testin ne zaman çalıştığından bağımsız olarak sağlam olsun).
    # Bu, grid_dca_journal testlerinde daha önce yakaladığımız aynı kategori
    # zamanlama hatasının (wall-clock "now" ile sabit test tarihi çakışması)
    # bir tekrarı olmasın diye özellikle böyle tasarlandı.
    end = pd.Timestamp.now() + pd.Timedelta(days=2)
    idx = pd.date_range(end=end, periods=len(prices), freq="D")
    return pd.DataFrame({
        "Open": prices, "High": [p * 1.01 for p in prices], "Low": [p * 0.99 for p in prices],
        "Close": prices, "Volume": [1000] * len(prices),
    }, index=idx)


def _scored_df_buy_signal(symbol="AAA", close=100.0, atr_pct=2.0):
    return pd.DataFrame({
        "symbol": [symbol], "market": ["us"], "signal": [1], "close": [close],
        "atr_pct": [atr_pct], "efektif_pozisyon_buyuklugu": [1000.0], "pozisyon_buyuklugu": [1000.0],
    })


def test_initialize_account_creates_new_account(temp_db):
    state = pt.initialize_account(10000.0, db_path=temp_db)
    assert state["cash"] == 10000.0
    assert state["yeni_hesap"] is True


def test_initialize_account_does_not_overwrite_existing(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    state2 = pt.initialize_account(50000.0, db_path=temp_db)  # farklı bakiye ile tekrar çağır
    assert state2["cash"] == 10000.0  # değişmemeli
    assert state2["yeni_hesap"] is False


def test_get_account_state_returns_none_if_not_initialized(temp_db):
    assert pt.get_account_state(db_path=temp_db) is None


def test_process_new_signals_opens_position_for_buy_signal(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    scored_df = _scored_df_buy_signal()
    stats = pt.process_new_signals(scored_df, {}, db_path=temp_db)
    assert stats["acilan"] == 1

    open_pos = pt.get_open_positions(db_path=temp_db)
    assert len(open_pos) == 1
    assert open_pos.iloc[0]["symbol"] == "AAA"


def test_process_new_signals_reduces_cash(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    pt.process_new_signals(_scored_df_buy_signal(), {}, db_path=temp_db)
    state = pt.get_account_state(db_path=temp_db)
    assert state["cash"] < 10000.0


def test_process_new_signals_does_not_duplicate_open_position(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    pt.process_new_signals(_scored_df_buy_signal(), {}, db_path=temp_db)
    stats2 = pt.process_new_signals(_scored_df_buy_signal(), {}, db_path=temp_db)
    assert stats2["acilan"] == 0  # zaten açık pozisyon var
    assert len(pt.get_open_positions(db_path=temp_db)) == 1


def test_process_new_signals_closes_position_on_sell_signal(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    pt.process_new_signals(_scored_df_buy_signal(), {}, db_path=temp_db)

    sell_df = pd.DataFrame({
        "symbol": ["AAA"], "market": ["us"], "signal": [-1], "close": [110.0],
    })
    stats = pt.process_new_signals(sell_df, {}, db_path=temp_db)
    assert stats["kapanan"] == 1
    assert len(pt.get_open_positions(db_path=temp_db)) == 0


def test_process_new_signals_insufficient_cash_skips(temp_db):
    pt.initialize_account(100.0, db_path=temp_db)  # çok küçük hesap
    scored_df = pd.DataFrame({
        "symbol": ["AAA"], "market": ["us"], "signal": [1], "close": [100.0],
        "atr_pct": [2.0], "efektif_pozisyon_buyuklugu": [5000.0], "pozisyon_buyuklugu": [5000.0],
    })
    stats = pt.process_new_signals(scored_df, {}, db_path=temp_db)
    assert stats["acilan"] == 0


def test_process_new_signals_uses_real_stop_target_from_signals_df(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    sig_df = pd.DataFrame({"stop_dist": [5.0], "target_dist": [10.0]})
    scored_df = _scored_df_buy_signal(close=100.0)
    pt.process_new_signals(scored_df, {"AAA": sig_df}, db_path=temp_db)

    open_pos = pt.get_open_positions(db_path=temp_db)
    assert open_pos.iloc[0]["stop_price"] == pytest.approx(95.0, rel=0.01)
    assert open_pos.iloc[0]["target_price"] == pytest.approx(110.0, rel=0.01)


def test_update_open_positions_closes_on_target_hit(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    sig_df = pd.DataFrame({"stop_dist": [5.0], "target_dist": [10.0]})
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {"AAA": sig_df}, db_path=temp_db)

    price_data = {"AAA": _price_series([100, 105, 112, 115])}  # 110'u geçiyor
    stats = pt.update_open_positions(price_data, db_path=temp_db)
    assert stats["hedefe_ulasti"] == 1
    assert len(pt.get_open_positions(db_path=temp_db)) == 0


def test_update_open_positions_closes_on_stop_hit(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    sig_df = pd.DataFrame({"stop_dist": [5.0], "target_dist": [10.0]})
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {"AAA": sig_df}, db_path=temp_db)

    price_data = {"AAA": _price_series([100, 97, 93, 90])}  # 95'in altına iniyor
    stats = pt.update_open_positions(price_data, db_path=temp_db)
    assert stats["stop_oldu"] == 1


def test_update_open_positions_returns_cash_on_close(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    sig_df = pd.DataFrame({"stop_dist": [5.0], "target_dist": [10.0]})
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {"AAA": sig_df}, db_path=temp_db)
    cash_after_buy = pt.get_account_state(db_path=temp_db)["cash"]

    price_data = {"AAA": _price_series([100, 105, 112, 115])}
    pt.update_open_positions(price_data, db_path=temp_db)
    cash_after_sell = pt.get_account_state(db_path=temp_db)["cash"]
    assert cash_after_sell > cash_after_buy


def test_update_open_positions_no_price_data_skips_gracefully(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {}, db_path=temp_db)
    stats = pt.update_open_positions({}, db_path=temp_db)  # sembol için hiç veri yok
    assert stats["hedefe_ulasti"] == 0
    assert stats["stop_oldu"] == 0
    assert len(pt.get_open_positions(db_path=temp_db)) == 1  # hâlâ açık, hata yok


def test_record_equity_snapshot_includes_open_position_value(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {}, db_path=temp_db)
    price_data = {"AAA": _price_series([100, 105])}
    equity = pt.record_equity_snapshot(price_data, db_path=temp_db)
    assert equity > 9000  # nakit + pozisyon değeri makul aralıkta


def test_record_equity_snapshot_no_account_returns_zero(temp_db):
    equity = pt.record_equity_snapshot({}, db_path=temp_db)
    assert equity == 0.0


def test_compute_performance_stats_no_account_returns_note(temp_db):
    stats = pt.compute_performance_stats(db_path=temp_db)
    assert "not" in stats


def test_compute_performance_stats_basic_flow(temp_db):
    pt.initialize_account(10000.0, db_path=temp_db)
    sig_df = pd.DataFrame({"stop_dist": [5.0], "target_dist": [10.0]})
    pt.process_new_signals(_scored_df_buy_signal(close=100.0), {"AAA": sig_df}, db_path=temp_db)

    price_data = {"AAA": _price_series([100, 105, 112, 115])}
    pt.update_open_positions(price_data, db_path=temp_db)
    pt.record_equity_snapshot(price_data, db_path=temp_db)

    stats = pt.compute_performance_stats(db_path=temp_db)
    assert stats["kapanan_islem_sayisi"] == 1
    assert stats["kazanma_orani_pct"] == 100.0
    assert stats["toplam_getiri_pct"] is not None


def test_full_scenario_multiple_scans():
    """Birden fazla 'tarama' simüle eden uçtan uca senaryo."""
    import tempfile
    db = tempfile.mktemp(suffix=".db")

    pt.initialize_account(10000.0, db_path=db)

    # 1. tarama: AAA için AL sinyali
    sig_df_a = pd.DataFrame({"stop_dist": [5.0], "target_dist": [15.0]})
    pt.process_new_signals(_scored_df_buy_signal(symbol="AAA", close=100.0), {"AAA": sig_df_a}, db_path=db)

    # 2. tarama: fiyat yükseldi ama hedefe henüz ulaşmadı
    price_data = {"AAA": _price_series([100, 103, 106])}
    pt.update_open_positions(price_data, db_path=db)
    pt.record_equity_snapshot(price_data, db_path=db)
    assert len(pt.get_open_positions(db_path=db)) == 1  # hâlâ açık

    # 3. tarama: fiyat hedefe ulaştı
    price_data2 = {"AAA": _price_series([106, 110, 116, 118])}
    stats = pt.update_open_positions(price_data2, db_path=db)
    pt.record_equity_snapshot(price_data2, db_path=db)
    assert stats["hedefe_ulasti"] == 1
    assert len(pt.get_open_positions(db_path=db)) == 0

    final_stats = pt.compute_performance_stats(db_path=db)
    assert final_stats["toplam_getiri_pct"] > 0
    assert final_stats["gunluk_kayit_sayisi"] == 2

    os.remove(db)

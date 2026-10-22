import os

import numpy as np
import pandas as pd
import pytest

from analysis import grid_dca_journal as gdj


@pytest.fixture
def temp_db(tmp_path):
    return str(tmp_path / "test_grid_dca.db")


def _grid_plan_df():
    return pd.DataFrame({
        "symbol": ["AAA", "AAA", "BBB"],
        "seviye": [1, 2, 1],
        "al_fiyati": [95.0, 90.0, 50.0],
        "sat_fiyati": [100.0, 95.0, 55.0],
        "adet": [10.0, 10.0, 5.0],
    })


def _dca_plan_df():
    return pd.DataFrame({
        "symbol": ["AAA", "AAA"],
        "dilim": [1, 2],
        "tetik_fiyati": [100.0, 95.0],
        "tutar": [250.0, 250.0],
        "adet": [2.5, 2.63],
    })


def _universe_df():
    return pd.DataFrame({"symbol": ["AAA", "BBB"], "market": ["us", "us"], "name": ["A Corp", "B Corp"]})


def _price_series(prices, start="2026-01-01"):
    idx = pd.date_range(start, periods=len(prices), freq="D")
    return pd.DataFrame({
        "Open": prices, "High": [p * 1.01 for p in prices], "Low": [p * 0.99 for p in prices],
        "Close": prices, "Volume": [1000] * len(prices),
    }, index=idx)


def test_record_grid_plan_inserts_all_rows(temp_db):
    added = gdj.record_grid_plan(_grid_plan_df(), _universe_df(), db_path=temp_db)
    assert added == 3

    conn = gdj._get_connection(temp_db)
    count = conn.execute("SELECT COUNT(*) FROM grid_orders").fetchone()[0]
    conn.close()
    assert count == 3


def test_record_grid_plan_empty_df_returns_zero(temp_db):
    assert gdj.record_grid_plan(pd.DataFrame(), _universe_df(), db_path=temp_db) == 0


def test_record_dca_plan_inserts_all_rows(temp_db):
    added = gdj.record_dca_plan(_dca_plan_df(), _universe_df(), db_path=temp_db)
    assert added == 2


def test_update_grid_outcomes_detects_buy_fill():
    import tempfile
    db = tempfile.mktemp(suffix=".db")
    scan_time = "2026-01-01T00:00:00"
    gdj.record_grid_plan(_grid_plan_df(), _universe_df(), scan_time=scan_time, db_path=db)

    # AAA fiyatı 95'in altına iniyor (seviye 1'in al_fiyati'na değiyor)
    price_data = {"AAA": _price_series([100, 98, 94, 96], start="2026-01-01")}
    stats = gdj.update_grid_outcomes(price_data, db_path=db)
    assert stats["al_gerceklesti"] >= 1
    os.remove(db)


def test_update_grid_outcomes_detects_sell_after_buy():
    import tempfile
    db = tempfile.mktemp(suffix=".db")
    scan_time = "2026-01-01T00:00:00"
    single_level = pd.DataFrame({"symbol": ["AAA"], "seviye": [1], "al_fiyati": [95.0],
                                  "sat_fiyati": [100.0], "adet": [10.0]})
    gdj.record_grid_plan(single_level, _universe_df(), scan_time=scan_time, db_path=db)

    # Önce al seviyesine iner, sonra sat seviyesine çıkar
    price_data = {"AAA": _price_series([100, 94, 96, 101, 102], start="2026-01-01")}
    gdj.update_grid_outcomes(price_data, db_path=db)
    stats2 = gdj.update_grid_outcomes(price_data, db_path=db)

    perf = gdj.compute_grid_performance(db_path=db)
    assert perf["kapanan_islem"] >= 1
    assert perf["kazanma_orani_pct"] == 100.0  # sat_fiyati > al_fiyati, her zaman kazançlı
    os.remove(db)


def test_update_dca_outcomes_detects_trigger():
    import tempfile
    db = tempfile.mktemp(suffix=".db")
    gdj.record_dca_plan(_dca_plan_df(), _universe_df(), db_path=db)

    price_data = {"AAA": _price_series([100, 98, 94, 96])}  # 95'in altına iniyor
    stats = gdj.update_dca_outcomes(price_data, db_path=db)
    assert stats["gerceklesti"] >= 1
    os.remove(db)


def test_compute_grid_performance_no_orders_returns_none_win_rate(temp_db):
    perf = gdj.compute_grid_performance(db_path=temp_db)
    assert perf["kapanan_islem"] == 0
    assert perf["kazanma_orani_pct"] is None


def test_compute_dca_performance_no_orders_returns_none(temp_db):
    perf = gdj.compute_dca_performance(db_path=temp_db)
    assert perf["gerceklesen_dilim"] == 0
    assert perf["ortalama_getiri_pct"] is None


def test_compute_dca_performance_with_current_price():
    import tempfile
    db = tempfile.mktemp(suffix=".db")
    gdj.record_dca_plan(_dca_plan_df(), _universe_df(), db_path=db)
    price_data = {"AAA": _price_series([100, 98, 94, 96])}
    gdj.update_dca_outcomes(price_data, db_path=db)

    perf = gdj.compute_dca_performance(current_data_by_symbol=price_data, db_path=db)
    assert perf["gerceklesen_dilim"] >= 1
    os.remove(db)


def test_update_grid_outcomes_marks_expired_after_max_days():
    import tempfile
    db = tempfile.mktemp(suffix=".db")
    old_scan_time = "2020-01-01T00:00:00"  # çok eski, MAX_PENDING_DAYS'i çoktan aşmış
    single_level = pd.DataFrame({"symbol": ["AAA"], "seviye": [1], "al_fiyati": [95.0],
                                  "sat_fiyati": [100.0], "adet": [10.0]})
    gdj.record_grid_plan(single_level, _universe_df(), scan_time=old_scan_time, db_path=db)

    # Fiyat hiç al seviyesine değmiyor
    price_data = {"AAA": _price_series([200, 201, 202], start="2026-01-01")}
    stats = gdj.update_grid_outcomes(price_data, db_path=db)
    assert stats["suresi_doldu"] >= 1
    os.remove(db)

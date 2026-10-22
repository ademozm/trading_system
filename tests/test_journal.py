import os
import tempfile
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from analysis import journal


@pytest.fixture
def db_path():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.remove(path)  # journal kendi oluşturacak
    yield path
    if os.path.exists(path):
        os.remove(path)


def _scored_df():
    return pd.DataFrame({
        "symbol": ["AAA", "BBB"],
        "market": ["us", "bist"],
        "signal": [1, -1],
        "close": [100.0, 50.0],
        "stop_dist": [5.0, 2.0],
        "target_dist": [10.0, 4.0],
        "composite_score": [0.5, -0.4],
    })


def test_record_signals_inserts_rows(db_path):
    added = journal.record_signals(_scored_df(), datetime.now().isoformat(), db_path)
    assert added == 2
    all_signals = journal.load_all_signals(db_path)
    assert len(all_signals) == 2
    assert set(all_signals["symbol"]) == {"AAA", "BBB"}


def test_record_signals_does_not_duplicate_open_positions(db_path):
    ts = datetime.now().isoformat()
    journal.record_signals(_scored_df(), ts, db_path)
    added_again = journal.record_signals(_scored_df(), ts, db_path)
    assert added_again == 0
    assert len(journal.load_all_signals(db_path)) == 2


def test_update_outcomes_marks_target_hit(db_path):
    ts = (datetime.now() - timedelta(days=1)).isoformat()
    journal.record_signals(_scored_df(), ts, db_path)

    idx = pd.date_range(datetime.now() - timedelta(days=1), periods=3, freq="D")
    aaa_df = pd.DataFrame({"Open": [100, 105, 112], "High": [102, 108, 115],
                            "Low": [99, 104, 111], "Close": [101, 107, 113]}, index=idx)
    stats = journal.update_outcomes({"AAA": aaa_df}, db_path)
    assert stats["kazandı"] >= 1

    signals = journal.load_all_signals(db_path)
    aaa_row = signals[signals["symbol"] == "AAA"].iloc[0]
    assert aaa_row["status"] == "kazandı"
    assert aaa_row["outcome_pct"] > 0


def test_update_outcomes_marks_stop_hit(db_path):
    ts = (datetime.now() - timedelta(days=1)).isoformat()
    journal.record_signals(_scored_df(), ts, db_path)

    idx = pd.date_range(datetime.now() - timedelta(days=1), periods=3, freq="D")
    aaa_df = pd.DataFrame({"Open": [100, 96, 90], "High": [101, 97, 91],
                            "Low": [99, 94, 88], "Close": [100, 95, 89]}, index=idx)
    stats = journal.update_outcomes({"AAA": aaa_df}, db_path)
    assert stats["kaybetti"] >= 1


def test_update_outcomes_leaves_open_when_no_data(db_path):
    ts = datetime.now().isoformat()
    journal.record_signals(_scored_df(), ts, db_path)
    stats = journal.update_outcomes({}, db_path)
    assert stats["hâlâ_açık"] == 2


def test_update_outcomes_expires_old_open_signals(db_path):
    old_ts = (datetime.now() - timedelta(days=60)).isoformat()
    journal.record_signals(_scored_df(), old_ts, db_path)
    stats = journal.update_outcomes({}, db_path)
    assert stats["süresi_doldu"] == 2


def test_compute_performance_stats_empty_db(db_path):
    result = journal.compute_performance_stats(db_path)
    assert result.empty


def test_compute_performance_stats_after_closed_trades(db_path):
    ts = (datetime.now() - timedelta(days=1)).isoformat()
    journal.record_signals(_scored_df(), ts, db_path)
    idx = pd.date_range(datetime.now() - timedelta(days=1), periods=3, freq="D")
    aaa_df = pd.DataFrame({"Open": [100, 105, 112], "High": [102, 108, 115],
                            "Low": [99, 104, 111], "Close": [101, 107, 113]}, index=idx)
    journal.update_outcomes({"AAA": aaa_df}, db_path)

    result = journal.compute_performance_stats(db_path)
    assert not result.empty
    assert "kazanma_orani_pct" in result.columns

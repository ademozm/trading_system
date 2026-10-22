import json
import os
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pandas as pd
import pytest

import universe


@pytest.fixture
def temp_universe_env(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    us_csv = data_dir / "universe_us.csv"
    bist_csv = data_dir / "universe_bist.csv"
    pd.DataFrame({"symbol": ["AAPL"], "market": ["us"], "name": ["Apple"]}).to_csv(us_csv, index=False)
    pd.DataFrame({"symbol": ["THYAO.IS"], "market": ["bist"], "name": ["THY"]}).to_csv(bist_csv, index=False)
    meta_path = data_dir / "universe_meta.json"
    monkeypatch.setattr(universe.config, "UNIVERSE_FILES", {"us": str(us_csv), "bist": str(bist_csv)})
    monkeypatch.setattr(universe.config, "UNIVERSE_META_PATH", str(meta_path))
    monkeypatch.setattr(universe.config, "UNIVERSE_MAX_AGE_DAYS", 7)
    return {"data_dir": data_dir, "us_csv": us_csv, "bist_csv": bist_csv, "meta_path": meta_path}


def test_load_universe_combines_markets(temp_universe_env):
    df = universe.load_universe(["us", "bist"])
    assert len(df) == 2
    assert set(df["symbol"]) == {"AAPL", "THYAO.IS"}


def test_load_universe_default_loads_all_configured_markets(temp_universe_env):
    assert len(universe.load_universe()) == 2


def test_load_universe_deduplicates_symbols(temp_universe_env):
    pd.DataFrame({"symbol": ["AAPL"], "market": ["us"], "name": ["Dup"]}).to_csv(
        temp_universe_env["bist_csv"], index=False
    )
    df = universe.load_universe(["us", "bist"])
    assert len(df) == 1


def test_universe_size_matches_load_universe_length(temp_universe_env):
    assert universe.universe_size(["us"]) == 1


def test_content_age_days_infinite_when_no_meta_entry(temp_universe_env):
    assert universe._content_age_days("us") == float("inf")


def test_mark_refreshed_then_content_age_is_recent(temp_universe_env):
    universe._mark_refreshed("us")
    assert universe._content_age_days("us") < 0.01


def test_content_age_days_ignores_file_mtime():
    """KRİTİK TEST: asıl düzeltilen hatayı doğruluyor — dosya mtime'ı taze
    olsa bile (git checkout senaryosu), meta kaydı yoksa yaş sonsuz olmalı."""
    import tempfile
    tmp_dir = tempfile.mkdtemp()
    csv_path = os.path.join(tmp_dir, "universe_us.csv")
    pd.DataFrame({"symbol": ["AAPL"], "market": ["us"], "name": ["Apple"]}).to_csv(csv_path, index=False)
    meta_path = os.path.join(tmp_dir, "universe_meta.json")
    with patch.object(universe.config, "UNIVERSE_META_PATH", meta_path):
        age = universe._content_age_days("us")
    assert age == float("inf")


def test_auto_refresh_if_stale_skips_when_recently_marked(temp_universe_env):
    universe._mark_refreshed("us")
    mock_ful = MagicMock()
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        results = universe.auto_refresh_if_stale(["us"])
    assert "güncel" in results["us"]
    mock_ful.update_us.assert_not_called()


def test_auto_refresh_if_stale_refreshes_when_no_meta_entry(temp_universe_env):
    mock_ful = MagicMock()
    mock_ful.update_us.return_value = pd.DataFrame({"symbol": ["MSFT"], "market": ["us"], "name": ["Microsoft"]})
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        results = universe.auto_refresh_if_stale(["us"])
    assert results["us"] == "güncellendi"
    mock_ful.update_us.assert_called_once()


def test_auto_refresh_if_stale_marks_refreshed_after_success(temp_universe_env):
    mock_ful = MagicMock()
    mock_ful.update_us.return_value = pd.DataFrame({"symbol": ["MSFT"], "market": ["us"], "name": ["Microsoft"]})
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        universe.auto_refresh_if_stale(["us"])
    assert universe._content_age_days("us") < 0.01


def test_auto_refresh_if_stale_bist_has_no_live_source(temp_universe_env):
    mock_ful = MagicMock()
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        results = universe.auto_refresh_if_stale(["bist"])
    assert "elle güncellenmeli" in results["bist"]


def test_auto_refresh_if_stale_handles_fetch_failure_gracefully(temp_universe_env):
    mock_ful = MagicMock()
    mock_ful.update_us.side_effect = Exception("internet yok")
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        results = universe.auto_refresh_if_stale(["us"])
    assert "güncellenemedi" in results["us"]
    assert len(universe.load_universe(["us"])) == 1


def test_auto_refresh_if_stale_old_meta_entry_triggers_refresh(temp_universe_env):
    old_date = (datetime.now() - timedelta(days=30)).isoformat()
    with open(temp_universe_env["meta_path"], "w") as f:
        json.dump({"us": old_date}, f)
    mock_ful = MagicMock()
    mock_ful.update_us.return_value = pd.DataFrame({"symbol": ["MSFT"], "market": ["us"], "name": ["Microsoft"]})
    with patch.dict("sys.modules", {"fetch_universe_lists": mock_ful}):
        results = universe.auto_refresh_if_stale(["us"])
    assert results["us"] == "güncellendi"

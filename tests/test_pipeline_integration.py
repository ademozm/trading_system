"""
Tam boru hattı testi: evren -> (sahte) veri -> doğrulama -> sinyal -> skor -> Excel rapor.

Gerçek ağ çağrısı YAPILMAZ (yfinance mock'lanır). Amaç: modüllerin
birbirine doğru bağlandığını, tek bir sembol bozulduğunda tüm
taramanın çökmediğini ve Excel dosyasının gerçekten oluştuğunu kanıtlamak.
"""
import os
import numpy as np
import pandas as pd
import pytest

from data_pipeline import validator
from analysis.strategy import RegimeAdaptiveStrategy
from analysis import scorer
from reporting import excel_report


def make_df(direction, n=150, seed=0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(np.full(n, 0.3 * direction) + rng.normal(0, 0.3, n))
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="D")
    df = pd.DataFrame({
        "Open": close, "High": close + 0.5, "Low": close - 0.5,
        "Close": close, "Volume": 1000,
    }, index=dates)
    return df


def test_full_pipeline_end_to_end(tmp_path):
    # 1) Sahte "çekilmiş veri" - biri bozuk, biri eksik satırlı, üçü sağlıklı
    raw_data = {
        "GOODUP": make_df(1, seed=1),
        "GOODDOWN": make_df(-1, seed=2),
        "GOODFLAT": make_df(0, seed=3),
        "BROKEN": pd.DataFrame({"Close": [1, 2, 3]}),        # eksik kolon -> elenecek
        "TOO_SHORT": make_df(1, n=10, seed=4),                 # yetersiz veri -> elenecek
    }

    # 2) Doğrulama
    valid_data, validation_report = validator.validate_batch(raw_data)
    assert "GOODUP" in valid_data
    assert "GOODDOWN" in valid_data
    assert "BROKEN" not in valid_data
    assert "TOO_SHORT" not in valid_data
    assert validation_report["BROKEN"].is_valid is False
    assert validation_report["TOO_SHORT"].is_valid is False

    # 3) Sinyal üretimi (sadece geçerli veriler için)
    strat = RegimeAdaptiveStrategy()
    signals = {sym: strat.generate_signals(df) for sym, df in valid_data.items()}
    assert set(signals.keys()) == set(valid_data.keys())

    # 4) Skorlama
    universe_df = pd.DataFrame({
        "symbol": list(valid_data.keys()),
        "market": ["us"] * len(valid_data),
        "name": list(valid_data.keys()),
    })
    scored_df = scorer.score_universe(signals, universe_df)
    # scored_df boş olabilir (hiç sinyal üretilmemiş olabilir) ama çökmemeli
    assert isinstance(scored_df, pd.DataFrame)

    # 5) Excel raporu gerçekten diskte oluşuyor mu
    output_path = tmp_path / "test_report.xlsx"
    result_path = excel_report.build_report(scored_df, validation_report, str(output_path))
    assert os.path.exists(result_path)
    assert os.path.getsize(result_path) > 0

    # 6) Excel dosyası gerçekten okunabiliyor mu (bozuk dosya değil)
    sheets = pd.read_excel(result_path, sheet_name=None)
    assert "Özet" in sheets
    assert "Hata Raporu" in sheets
    error_sheet = sheets["Hata Raporu"]
    if "Sembol" in error_sheet.columns:
        assert "BROKEN" in error_sheet["Sembol"].values
        assert "TOO_SHORT" in error_sheet["Sembol"].values


def test_pipeline_survives_all_symbols_failing_validation(tmp_path):
    """Uç durum: evrendeki HİÇBİR sembol geçerli değilse sistem çökmemeli,
    boş ama geçerli bir Excel rapor üretmeli."""
    raw_data = {
        "BAD1": pd.DataFrame({"Close": [1]}),
        "BAD2": pd.DataFrame(),
    }
    valid_data, validation_report = validator.validate_batch(raw_data)
    assert len(valid_data) == 0

    strat = RegimeAdaptiveStrategy()
    signals = {sym: strat.generate_signals(df) for sym, df in valid_data.items()}
    universe_df = pd.DataFrame({"symbol": [], "market": [], "name": []})
    scored_df = scorer.score_universe(signals, universe_df)

    output_path = tmp_path / "empty_report.xlsx"
    result_path = excel_report.build_report(scored_df, validation_report, str(output_path))
    assert os.path.exists(result_path)

    sheets = pd.read_excel(result_path, sheet_name=None)
    assert "Özet" in sheets

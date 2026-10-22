import os

import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from reporting import excel_report


def test_safe_str_len_handles_nan():
    assert excel_report._safe_str_len(np.nan) == 0
    assert excel_report._safe_str_len(pd.NA) == 0
    assert excel_report._safe_str_len(None) == 0


def test_safe_str_len_normal_values():
    assert excel_report._safe_str_len("AAPL") == 4
    assert excel_report._safe_str_len(123) == 3
    assert excel_report._safe_str_len(1.5) == 3


def test_autosize_does_not_crash_on_nan_column():
    """
    REGRESYON TESTİ: Daha önce, pandas'ın yeni string dtype davranışında
    NaN değerler .astype(str).map(len) ile hataya yol açıyordu
    (float NaN'ın len() metodu yok). _safe_str_len ile düzeltildi.
    """
    wb = Workbook()
    ws = wb.active
    df = pd.DataFrame({"Sembol": ["AAPL", "MSFT"], "Skor": [np.nan, 0.5]})
    ws.append(list(df.columns))
    for row in df.itertuples(index=False):
        ws.append(list(row))
    excel_report._autosize(ws, df)  # hata fırlatmamalı
    assert ws.column_dimensions["A"].width is not None


def test_autosize_all_nan_column_does_not_crash():
    wb = Workbook()
    ws = wb.active
    df = pd.DataFrame({"Sembol": ["AAPL"], "BosSutun": [np.nan]})
    ws.append(list(df.columns))
    ws.append(["AAPL", np.nan])
    excel_report._autosize(ws, df)


def test_write_generic_sheet_empty_df_writes_note():
    path = "/tmp/test_excel_report_empty.xlsx"
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        excel_report._write_generic_sheet(writer, pd.DataFrame(), "TestSayfa", ["a", "b"], {"a": "A", "b": "B"})
    result = pd.read_excel(path, sheet_name="TestSayfa")
    assert "Not" in result.columns
    os.remove(path)


def test_write_generic_sheet_maps_signal_column():
    path = "/tmp/test_excel_report_signal.xlsx"
    df = pd.DataFrame({"symbol": ["AAPL", "TSLA"], "signal": [1, -1]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        excel_report._write_generic_sheet(
            writer, df, "TestSayfa", ["symbol", "signal"], {"symbol": "Sembol", "signal": "Sinyal"}
        )
    result = pd.read_excel(path, sheet_name="TestSayfa")
    assert set(result["Sinyal"]) == {"AL", "SAT"}
    os.remove(path)


def test_write_generic_sheet_maps_boolean_columns():
    path = "/tmp/test_excel_report_bool.xlsx"
    df = pd.DataFrame({"symbol": ["AAPL"], "volume_confirmed": [True], "mtf_confirmed": [np.nan]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        excel_report._write_generic_sheet(
            writer, df, "TestSayfa", ["symbol", "volume_confirmed", "mtf_confirmed"],
            {"symbol": "Sembol", "volume_confirmed": "Hacim Teyidi", "mtf_confirmed": "Haftalık Teyit"},
        )
    result = pd.read_excel(path, sheet_name="TestSayfa")
    assert result["Hacim Teyidi"].iloc[0] == "Evet"
    assert result["Haftalık Teyit"].iloc[0] == "Bilinmiyor"
    os.remove(path)


def test_boolean_column_placeholder_survives_excel_roundtrip():
    """
    REGRESYON TESTİ: Eskiden "N/A" placeholder kullanılıyordu — pandas
    Excel'den okurken "N/A" metnini otomatik NaN sayıyor, bu da rapor
    tekrar okunduğunda (Streamlit panelinde) veriyi sessizce kaybediyordu.
    """
    path = "/tmp/test_excel_report_na_trap.xlsx"
    df = pd.DataFrame({"symbol": ["AAPL"], "supheli": [np.nan]})
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        excel_report._write_generic_sheet(
            writer, df, "TestSayfa", ["symbol", "supheli"],
            {"symbol": "Sembol", "supheli": "Veri Şüpheli mi"},
        )
    result = pd.read_excel(path, sheet_name="TestSayfa")
    assert not pd.isna(result["Veri Şüpheli mi"].iloc[0]), "Placeholder pandas tarafından NaN'a çevrilmemeli"
    os.remove(path)


def test_build_report_end_to_end_minimal():
    """build_report'un TAMAMEN boş/None girdilerle bile çökmeden çalışması gerekiyor."""
    path = "/tmp/test_excel_report_full.xlsx"
    scored_df = pd.DataFrame({
        "symbol": ["AAPL"], "name": ["Apple"], "market": ["us"], "signal": [1],
        "regime": ["trend"], "composite_score": [0.6], "close": [150.0],
    })
    excel_report.build_report(scored_df, {}, path)
    assert os.path.exists(path)
    sheets = pd.read_excel(path, sheet_name=None)
    assert "Özet" in sheets
    assert "Hata Raporu" in sheets
    os.remove(path)


def test_build_report_empty_scored_df_does_not_crash():
    path = "/tmp/test_excel_report_empty_scored.xlsx"
    excel_report.build_report(pd.DataFrame(), {}, path)
    assert os.path.exists(path)
    os.remove(path)


def test_build_report_includes_grid_dca_performance_sheet():
    path = "/tmp/test_excel_report_griddca.xlsx"
    scored_df = pd.DataFrame({
        "symbol": ["AAPL"], "name": ["Apple"], "market": ["us"], "signal": [1],
        "regime": ["trend"], "composite_score": [0.6], "close": [150.0],
    })
    grid_dca_perf = {
        "grid": {"kapanan_islem": 5, "kazanma_orani_pct": 80.0, "ortalama_kazanc_pct": 2.5,
                 "bekleyen": 3, "suresi_dolan": 1},
        "dca": {"gerceklesen_dilim": 8, "bekleyen_dilim": 2, "ortalama_getiri_pct": 4.2,
                "pozitif_pozisyon_orani_pct": 75.0},
    }
    excel_report.build_report(scored_df, {}, path, grid_dca_performance=grid_dca_perf)
    sheets = pd.read_excel(path, sheet_name="Grid ve DCA Performansı", header=None)
    full_text = sheets.to_string()
    assert "80.0" in full_text or "80" in full_text  # kazanma oranı
    assert "4.2" in full_text  # DCA ortalama getiri
    os.remove(path)

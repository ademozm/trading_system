"""
Çok sayfalı Streamlit panelinde (app.py + pages/*.py) TÜM sayfaların
ortak kullandığı fonksiyonlar: CSS, en son raporu bulma, raporu
önbellekli okuma. Tek yerde tutulmasının sebebi: her sayfa dosyası
Streamlit tarafından ayrı bir script olarak çalıştırılıyor, bu yüzden
tekrarı önlemek ve tutarlılığı garanti etmek için ortak modül şart.
"""
import ast
import os

import pandas as pd
import streamlit as st

import config

CUSTOM_CSS = """
<style>
    .block-container { padding-top: 1.5rem; max-width: 1400px; }
    div[data-testid="stMetric"] {
        background: rgba(120,120,120,0.06);
        border: 1px solid rgba(120,120,120,0.15);
        border-radius: 10px;
        padding: 12px 16px;
    }
    .kpi-good { color: #16a34a !important; }
    .kpi-bad { color: #dc2626 !important; }
    .news-card {
        border: 1px solid rgba(120,120,120,0.15);
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .event-card {
        border-left: 4px solid #f59e0b;
        background: rgba(245,158,11,0.08);
        border-radius: 6px;
        padding: 10px 14px;
        margin-bottom: 8px;
    }
    .status-card {
        border-left: 4px solid #6b7280;
        background: rgba(107,114,128,0.06);
        border-radius: 6px;
        padding: 8px 12px;
        margin-bottom: 6px;
        font-size: 0.9em;
    }
    h1, h2, h3 { letter-spacing: -0.3px; }
    section[data-testid="stSidebar"] { min-width: 300px; }
</style>
"""


def inject_css():
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


def find_latest_report() -> str | None:
    """reports/ klasöründeki en son (dosya adına göre en yeni) Excel raporunu bulur."""
    if not os.path.isdir(config.REPORTS_DIR):
        return None
    xlsx_files = [f for f in os.listdir(config.REPORTS_DIR) if f.endswith(".xlsx") and f.startswith("tarama_")]
    if not xlsx_files:
        return None
    xlsx_files.sort(reverse=True)
    return os.path.join(config.REPORTS_DIR, xlsx_files[0])


@st.cache_data(show_spinner=False)
def load_sheets(path: str, _mtime: float) -> dict:
    """
    Excel dosyasını önbellekli okur. `_mtime` parametresi CACHE ANAHTARININ
    parçası — dosya değişirse (yeni tarama) mtime değişir, önbellek
    otomatik geçersiz olur. Alt çizgiyle başlaması Streamlit'e bu
    parametreyi hash'lemesini SÖYLEMEK için (dosya yolu zaten hash'leniyor).
    """
    return pd.read_excel(path, sheet_name=None)


def get_current_sheets() -> tuple[str | None, dict]:
    """
    Session state'te bir rapor yoksa en son raporu otomatik bulur.
    Dönüş: (rapor_yolu, sheets_dict). Rapor yoksa (None, {}).
    """
    if "last_report_path" not in st.session_state:
        st.session_state.last_report_path = find_latest_report()

    path = st.session_state.last_report_path
    if not path or not os.path.exists(path):
        return None, {}

    mtime = os.path.getmtime(path)
    sheets = load_sheets(path, mtime)
    return path, sheets


def require_report_or_stop(page_title: str = ""):
    """
    Sayfalar için ortak "rapor yoksa ana sayfaya yönlendir" mantığı.
    Dönüş: (path, sheets) — rapor varsa. Yoksa st.stop() ile sayfayı durdurur.
    """
    path, sheets = get_current_sheets()
    if not path:
        st.info("Henüz bir tarama sonucu yok. Lütfen önce **Ana Sayfa**'dan bir tarama başlat.")
        st.page_link("app.py", label="⬅️ Ana Sayfaya dön", icon="🏠")
        st.stop()
    return path, sheets


def parse_list_cell(value):
    """Excel'e yazılırken string'e dönüşen Python listelerini ([1.2, 3.4] gibi) geri çevirir."""
    if isinstance(value, list):
        return value
    if not isinstance(value, str) or not value.strip().startswith("["):
        return []
    try:
        return [float(x) for x in ast.literal_eval(value)]
    except Exception:
        return []

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from analysis import paper_trading as pt
import dashboard_common as dc

st.set_page_config(page_title="Paper Trading", layout="wide", page_icon="💼")
dc.inject_css()
st.title("💼 Paper Trading (Sanal Portföy)")
st.caption("Sistemin sinyallerini gerçekten takip etseydin, sanal paran şu an ne durumda olurdu?")

path, sheets = dc.require_report_or_stop()
pt_sheet = sheets.get("Paper Trading", pd.DataFrame())

if pt_sheet.empty:
    st.info("Paper trading verisi yok — bir tarama daha çalıştır (--skip-paper-trading kullanılmadıysa "
             "otomatik oluşur).")
    st.stop()

st.subheader("Performans Özeti")
st.dataframe(pt_sheet, use_container_width=True)

st.divider()
st.subheader("Açık Pozisyonlar")
try:
    open_positions = pt.get_open_positions()
    if open_positions.empty:
        st.info("Şu an açık pozisyon yok.")
    else:
        display_cols = ["symbol", "market", "entry_date", "entry_price", "quantity", "stop_price", "target_price"]
        st.dataframe(open_positions[[c for c in display_cols if c in open_positions.columns]],
                     use_container_width=True)
except Exception as e:
    st.warning(f"Açık pozisyonlar okunamadı: {e}")

st.divider()
st.warning("⚠️ **Dürüstlük notu:** Bu GERÇEK bir işlem sistemi değildir — hiçbir borsaya bağlanmaz, "
           "gerçek para hareket ettirmez. Komisyon/slipaj basitleştirilmiş şekilde uygulanır. "
           "Gerçek trading'e geçmeden önce bu simülasyonun sonuçlarını ihtiyatla değerlendir; "
           "en az birkaç ay/onlarca işlem birikmeden istatistiksel olarak anlamlı sonuç çıkarma.")

st.page_link("app.py", label="⬅️ Ana Sayfaya dön", icon="🏠")

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Piyasalar", layout="wide", page_icon="💼")
dc.inject_css()
st.title("💼 Piyasalar")
st.caption("Sinyal üreten semboller, piyasa bazında (skor renk skalalı)")

path, sheets = dc.require_report_or_stop()

market_tab_names = [n for n in ["ABD", "BIST", "Kripto", "Emtialar"] if n in sheets]
if not market_tab_names:
    st.info("Bu taramada hiçbir piyasada sinyal bulunamadı.")
else:
    market_tabs = st.tabs(market_tab_names)
    for mtab, mname in zip(market_tabs, market_tab_names):
        with mtab:
            df = sheets[mname]
            if df.empty:
                st.write("Bu piyasada sinyal bulunamadı — 'Tüm Sembol Durumu' sayfasında taranan tüm sembolleri görebilirsin.")
            elif "Skor" in df.columns:
                st.dataframe(df.style.background_gradient(subset=["Skor"], cmap="RdYlGn", vmin=-1, vmax=1),
                             use_container_width=True, height=500)
            else:
                st.dataframe(df, use_container_width=True, height=500)

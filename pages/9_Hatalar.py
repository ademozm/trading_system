import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Hata Raporu", layout="wide", page_icon="⚠️")
dc.inject_css()
st.title("⚠️ Hata Raporu")
st.caption("İndirilemeyen veya doğrulamadan geçemeyen semboller")

path, sheets = dc.require_report_or_stop()
hata = sheets.get("Hata Raporu", pd.DataFrame())

if hata.empty or "Sembol" not in hata.columns:
    st.success("Bu taramada hata/geçersiz veri yok.")
else:
    st.dataframe(hata, use_container_width=True)

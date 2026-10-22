import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Temel & Risk & Gelişmiş", layout="wide", page_icon="🔬")
dc.inject_css()
st.title("🔬 Temel & Risk & Gelişmiş Göstergeler")

path, sheets = dc.require_report_or_stop()

for sheet_name in ["Temel Analiz", "Risk Metrikleri", "Gelişmiş Göstergeler"]:
    df = sheets.get(sheet_name, pd.DataFrame())
    st.subheader(sheet_name)
    if df.empty:
        st.write("Veri yok.")
    else:
        st.dataframe(df, use_container_width=True, height=350)
    st.divider()

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from reporting import dashboard_charts as charts
import dashboard_common as dc

st.set_page_config(page_title="Grid & DCA", layout="wide", page_icon="🎯")
dc.inject_css()
st.title("🎯 Grid & DCA Planları")
st.caption("Bu sistem GERÇEK EMİR GÖNDERMEZ — sadece bir plan önerir. Elle uygula ya da "
           "borsanın kendi Grid Bot özelliğine gir.")

path, sheets = dc.require_report_or_stop()
grid_df = sheets.get("Grid Planı", pd.DataFrame())
dca_df = sheets.get("DCA Planı", pd.DataFrame())

st.subheader("Grid Planı (yatay/range piyasalar için)")
if grid_df.empty or "Sembol" not in grid_df.columns:
    st.info("Bu taramada grid stratejisine uygun (range rejiminde) sembol bulunamadı.")
else:
    grid_symbols = grid_df["Sembol"].unique().tolist()
    sel_grid_symbol = st.selectbox("Sembol seç", grid_symbols, key="grid_symbol")
    st.plotly_chart(charts.grid_ladder_chart(grid_df[grid_df["Sembol"] == sel_grid_symbol]),
                     use_container_width=True)
    st.dataframe(grid_df[grid_df["Sembol"] == sel_grid_symbol], use_container_width=True)

st.divider()
st.subheader("DCA (Kademeli Alım) Planı")
if dca_df.empty or "Sembol" not in dca_df.columns:
    st.info("Bu taramada AL sinyali üreten sembol bulunamadı.")
else:
    dca_symbols = dca_df["Sembol"].unique().tolist()
    sel_dca_symbol = st.selectbox("Sembol seç", dca_symbols, key="dca_symbol")
    st.plotly_chart(charts.dca_steps_chart(dca_df[dca_df["Sembol"] == sel_dca_symbol]),
                     use_container_width=True)
    st.dataframe(dca_df[dca_df["Sembol"] == sel_dca_symbol], use_container_width=True)

st.divider()
st.page_link("pages/5b_Grid_DCA_Performans.py", label="📊 Grid & DCA Emir Takibi ve Kazanç Oranları →", icon="📊")

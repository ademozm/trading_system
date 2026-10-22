import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Tüm Sembol Durumu", layout="wide", page_icon="📋")
dc.inject_css()
st.title("📋 Tüm Sembol Durumu")
st.caption("Sinyal üretsin üretmesin, TARANAN HER SEMBOLÜN durumu — 'piyasa boş görünüyor' "
           "kafa karışıklığını önlemek için")

path, sheets = dc.require_report_or_stop()
status_df = sheets.get("Tüm Sembol Durumu", pd.DataFrame())

if status_df.empty or "Sembol" not in status_df.columns:
    st.info("Bu taramada işlenebilir sembol verisi bulunamadı.")
    st.stop()

total = len(status_df)
signaled = (status_df["Sinyal Var mı"] == "Evet").sum()
c1, c2, c3 = st.columns(3)
c1.metric("Toplam Taranan", total)
c2.metric("Sinyal Üreten", signaled)
c3.metric("Sinyal Üretmeyen", total - signaled)

st.divider()

st.subheader("Piyasa Bazlı Özet")
market_summary = sheets.get("Piyasa Özeti", pd.DataFrame())
if market_summary.empty:
    # Geriye dönük uyumluluk: eski bir rapor açılmışsa dinamik hesapla
    market_summary = status_df.groupby("Piyasa").agg(
        Taranan=("Sembol", "count"),
        Sinyal_Ureten=("Sinyal Var mı", lambda s: (s == "Evet").sum()),
    ).reset_index().rename(columns={"Sinyal_Ureten": "Sinyal Üreten"})
    market_summary["Sinyal Üretme Oranı %"] = (market_summary["Sinyal Üreten"] / market_summary["Taranan"] * 100).round(1)
st.dataframe(market_summary, use_container_width=True)

st.divider()

st.subheader("Detaylı Liste")
market_filter = st.multiselect("Piyasa filtrele", options=status_df["Piyasa"].unique().tolist(),
                                default=status_df["Piyasa"].unique().tolist())
signal_filter = st.radio("Göster", ["Hepsi", "Sadece sinyal üretenler", "Sadece sinyal üretmeyenler"], horizontal=True)

filtered = status_df[status_df["Piyasa"].isin(market_filter)]
if signal_filter == "Sadece sinyal üretenler":
    filtered = filtered[filtered["Sinyal Var mı"] == "Evet"]
elif signal_filter == "Sadece sinyal üretmeyenler":
    filtered = filtered[filtered["Sinyal Var mı"] == "Hayır"]

st.dataframe(filtered, use_container_width=True, height=500)

import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Haberler", layout="wide", page_icon="📰")
dc.inject_css()
st.title("📰 Haberler")

path, sheets = dc.require_report_or_stop()
haberler = sheets.get("Haberler", pd.DataFrame())

if haberler.empty:
    st.info("Bu taramada haber verisi bulunamadı.")
else:
    for _, row in haberler.iterrows():
        sentiment = row.get("Haber Tonu", 0)
        sentiment = 0 if pd.isna(sentiment) else sentiment
        renk = "#16a34a" if sentiment > 0.1 else ("#dc2626" if sentiment < -0.1 else "#6b7280")
        sembol_etiketi = f"<b>{row.get('Sembol', '')}</b> — " if row.get("Sembol") else ""
        st.markdown(f"""
        <div class="news-card">
            <span style="color:{renk}; font-weight:600;">●</span>
            {sembol_etiketi}{row.get('Başlık', '')}
            <br><span style="color:#888; font-size:0.85em;">{row.get('Kaynak', '')} · {row.get('Yayıncı', '')}</span>
        </div>
        """, unsafe_allow_html=True)
    st.caption("Haber tonu basit anahtar-kelime sayımıdır, gerçek NLP değildir — kaba bir gösterge olarak değerlendirin.")

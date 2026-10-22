import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Ekonomik Takvim", layout="wide", page_icon="📅")
dc.inject_css()
st.title("📅 Ekonomik Takvim")
st.caption("Yaklaşan Fed (FOMC), NFP, CPI gibi ABD piyasasını geneli etkileyen olaylar")

path, sheets = dc.require_report_or_stop()
takvim = sheets.get("Ekonomik Takvim", pd.DataFrame())

if takvim.empty or "Tarih" not in takvim.columns:
    st.success("Önümüzdeki 14 gün içinde bilinen önemli bir ekonomik olay yok.")
else:
    for _, row in takvim.sort_values("Kalan Gün").iterrows():
        st.markdown(f"""
        <div class="event-card">
            <b>{row['Tarih']}</b> ({int(row['Kalan Gün'])} gün kaldı) — {row['Olay']}
            <br><span style="color:#888; font-size:0.85em;">Önem: {row['Önem']}</span>
        </div>
        """, unsafe_allow_html=True)
    st.caption("FOMC tarihleri Fed'in resmi takviminden; NFP/CPI tarihleri yaklaşıktır (±birkaç gün sapabilir).")

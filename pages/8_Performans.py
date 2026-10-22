import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Geçmiş Performans", layout="wide", page_icon="📜")
dc.inject_css()
st.title("📜 Geçmiş Performans")
st.caption("Sinyallerin zaman içindeki gerçek başarı istatistikleri (SQLite sinyal günlüğünden)")

path, sheets = dc.require_report_or_stop()
perf = sheets.get("Performans Geçmişi", pd.DataFrame())

if perf.empty:
    st.info("Henüz yeterli sinyal geçmişi yok — sistem birkaç tarama sonra performans istatistiği "
            "üretmeye başlar. Bu, gerçekten çalışıp çalışmadığını zamanla objektif olarak gösteren "
            "en değerli sayfalardan biri.")
else:
    st.dataframe(perf, use_container_width=True)

st.divider()
st.page_link("pages/5b_Grid_DCA_Performans.py", label="🎯 Grid & DCA emir performansı için tıkla →", icon="🎯")

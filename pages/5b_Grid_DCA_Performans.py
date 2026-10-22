import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import dashboard_common as dc

st.set_page_config(page_title="Grid & DCA Performansı", layout="wide", page_icon="📊")
dc.inject_css()
st.title("📊 Grid & DCA Emir Takibi ve Kazanç Oranları")
st.caption("Her grid seviyesi/DCA dilimi bir 'emir' olarak SQLite'a kaydedilir, sonraki taramalarda "
           "fiyat verisiyle karşılaştırılıp gerçekleşip gerçekleşmediği (ve kazanıp kazanmadığı) takip edilir.")

path, sheets = dc.require_report_or_stop()
perf_sheet = sheets.get("Grid ve DCA Performansı", pd.DataFrame())

if perf_sheet.empty:
    st.info("Henüz yeterli emir günlüğü verisi yok.")
    st.stop()

st.subheader("🎯 Grid Stratejisi Performansı")
st.markdown("""
Bir grid seviyesi şu şekilde takip edilir:
1. **Beklemede** — fiyat henüz "al" seviyesine değmedi
2. **Al gerçekleşti** — fiyat al seviyesine değdi, pozisyon "açıldı" (simülasyon)
3. **Sat gerçekleşti** — fiyat sonrasında sat seviyesine ulaştı, işlem kâr ile kapandı
4. **Süresi doldu** — 60 gün içinde hiç tetiklenmedi
""")

st.subheader("💰 DCA Stratejisi Performansı")
st.markdown("""
DCA'nın grid'den farkı: her dilim tek yönlü bir alımdır, "satışı" yoktur.
Performans, gerçekleşen dilimlerin ortalama maliyeti ile **güncel fiyat**
karşılaştırılarak hesaplanır (gerçekleşmemiş kâr/zarar).
""")

st.divider()
st.dataframe(perf_sheet, use_container_width=True, height=400)

st.divider()
st.warning("⚠️ **Dürüstlük notu:** Bu bir SİMÜLASYON/TAKİP sistemidir, gerçek emir göndermez. "
           "'Kazanma oranı', geçmişte bu seviyeler önerildiğinde fiyatın gerçekten oraya gelip "
           "gelmediğini yansıtır — gerçek bir hesapta komisyon, slipaj, likidite farklılık gösterebilir.")

st.page_link("app.py", label="⬅️ Ana Sayfaya dön", icon="🏠")

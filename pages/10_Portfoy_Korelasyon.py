import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config
from data_pipeline import cache
from analysis import portfolio_correlation as pc
from reporting import dashboard_charts as charts
import dashboard_common as dc

st.set_page_config(page_title="Portföy Korelasyonu", layout="wide", page_icon="🔗")
dc.inject_css()
st.title("🔗 Portföy-Seviyesi Korelasyon Kontrolü")
st.caption("Aynı anda gelen sinyaller birbirine yüksek korelasyonluysa, bunları bağımsız bahisler gibi "
           "boyutlandırmak gerçek riski olduğundan düşük gösterir.")

path, sheets = dc.require_report_or_stop()
korelasyon_sheet = sheets.get("Portföy Korelasyonu", pd.DataFrame())
ozet = sheets.get("Özet", pd.DataFrame())

if korelasyon_sheet.empty or ozet.empty:
    st.info("Bu taramada korelasyon kontrolü için yeterli sinyal yok (en az 2 sinyal gerekir).")
    st.stop()

st.subheader("Özet")
st.dataframe(korelasyon_sheet, use_container_width=True)

uyari_var = korelasyon_sheet.astype(str).apply(lambda col: col.str.contains("UYARI", na=False)).any().any()
if uyari_var:
    st.warning("⚠️ Bazı sinyalleriniz birbirine yüksek korelasyonlu — 'Genel Bakış'taki pozisyon "
               "büyüklükleri buna göre düzeltildi (bkz. aşağıdaki 'Düzeltilmiş Portföy Yüzdesi').")
else:
    st.success("✅ Sinyal üreten semboller arasında yüksek korelasyon tespit edilmedi — "
               "her biri bağımsız bir bahis gibi değerlendirilebilir.")

st.divider()
st.subheader("Korelasyon Matrisi")
st.caption("Fiyat verisi önbellekten okunuyor, ek indirme gerekmiyor.")

symbols = ozet["Sembol"].tolist()
data_by_symbol = {}
for sym in symbols:
    df = cache.get_cached(sym, config.FETCH_INTERVAL, ttl_minutes=999999)
    if df is not None:
        data_by_symbol[sym] = df

if len(data_by_symbol) >= 2:
    corr_matrix = pc.compute_correlation_matrix(data_by_symbol, list(data_by_symbol.keys()))
    st.plotly_chart(charts.correlation_heatmap(corr_matrix), use_container_width=True)
else:
    st.info("Isı haritası için önbellekte yeterli fiyat verisi bulunamadı.")

st.divider()
st.subheader("Sembol Bazlı Pozisyon Karşılaştırması")
if "Korelasyon Kümesi" in ozet.columns:
    compare_cols = [c for c in ["Sembol", "Portföy Yüzdesi %", "Düzeltilmiş Portföy Yüzdesi %", "Korelasyon Kümesi"]
                    if c in ozet.columns]
    st.dataframe(ozet[compare_cols], use_container_width=True)
else:
    st.info("Bu sütunlar rapor sürümünde yok — daha yeni bir taramayla tekrar dene.")

st.divider()
st.warning("⚠️ **Dürüstlük notu:** Bu basit, sezgisel bir düzeltmedir — modern portföy teorisindeki "
           "gibi tam bir kovaryans optimizasyonu YAPMAZ. Profesyonel bir portföy yöneticisinin yerini tutmaz.")

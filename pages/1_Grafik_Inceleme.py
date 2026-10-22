import os
import sys

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import config
from data_pipeline import cache
from reporting import dashboard_charts as charts
import dashboard_common as dc

st.set_page_config(page_title="Grafik İnceleme", layout="wide", page_icon="📈")
dc.inject_css()
st.title("📈 Grafik İnceleme")
st.caption("Tam teknik analiz paneli: fiyat + EMA + Bollinger + destek/direnç, hacim, RSI, MACD, ADX")

path, sheets = dc.require_report_or_stop()
ozet = sheets.get("Özet", pd.DataFrame())
gelismis = sheets.get("Gelişmiş Göstergeler", pd.DataFrame())

if ozet.empty:
    st.info("Bu taramada sinyal üreten sembol bulunamadı, grafik için gösterilecek bir şey yok.")
    st.stop()

col_sel, col_toggle = st.columns([3, 1])
with col_sel:
    symbol_options = ozet["Sembol"].tolist()
    selected_symbol = st.selectbox("Sembol seç", symbol_options)
with col_toggle:
    show_full = st.checkbox("Tam teknik panel (RSI/MACD/ADX)", value=True)

ohlc = cache.get_cached(selected_symbol, config.FETCH_INTERVAL, ttl_minutes=999999)
if ohlc is None:
    st.warning("Bu sembol için önbellekte fiyat verisi bulunamadı (cache temizlenmiş olabilir).")
    st.stop()

support_levels, resistance_levels = [], []
gelismis_row = None
if not gelismis.empty and "Sembol" in gelismis.columns:
    row = gelismis[gelismis["Sembol"] == selected_symbol]
    if not row.empty:
        gelismis_row = row.iloc[0]
        support_levels = dc.parse_list_cell(gelismis_row.get("Destek Seviyeleri"))
        resistance_levels = dc.parse_list_cell(gelismis_row.get("Direnç Seviyeleri"))

if show_full:
    fig = charts.full_technical_chart(
        ohlc.tail(150), support_levels=support_levels, resistance_levels=resistance_levels,
        title=f"{selected_symbol} — Tam Teknik Analiz",
    )
    st.plotly_chart(fig, use_container_width=True)
else:
    from analysis import indicators
    ema_fast = indicators.ema(ohlc["Close"], 12)
    ema_slow = indicators.ema(ohlc["Close"], 26)
    fig = charts.candlestick_chart(
        ohlc.tail(150), ema_fast=ema_fast.tail(150), ema_slow=ema_slow.tail(150),
        support_levels=support_levels, resistance_levels=resistance_levels,
        title=f"{selected_symbol} — Fiyat + EMA(12/26) + Destek/Direnç",
    )
    st.plotly_chart(fig, use_container_width=True)
    st.plotly_chart(charts.volume_bar(ohlc.tail(150)), use_container_width=True)

sym_row = ozet[ozet["Sembol"] == selected_symbol]
if not sym_row.empty:
    r = sym_row.iloc[0]
    st.divider()
    st.subheader("Sinyal Özeti")
    mc1, mc2, mc3, mc4, mc5, mc6 = st.columns(6)
    mc1.metric("Sinyal", r.get("Sinyal", "-"))
    mc2.metric("Skor", f"{r.get('Skor', 0):.3f}" if pd.notna(r.get("Skor")) else "-")
    mc3.metric("RSI", f"{r.get('RSI', 0):.1f}" if pd.notna(r.get("RSI")) else "-")
    mc4.metric("ADX", f"{r.get('ADX', 0):.1f}" if pd.notna(r.get("ADX")) else "-")
    mc5.metric("ATR %", f"{r.get('ATR %', 0):.2f}" if pd.notna(r.get("ATR %")) else "-")
    mc6.metric("Rejim", r.get("Rejim", "-"))

    st.subheader("Momentum ve Risk")
    rc1, rc2, rc3, rc4 = st.columns(4)
    rc1.metric("Momentum %", f"{r.get('Momentum %', 0):.2f}" if pd.notna(r.get("Momentum %")) else "-")
    rc2.metric("Göreceli Güç %", f"{r.get('Göreceli Güç %', 0):.2f}" if pd.notna(r.get("Göreceli Güç %")) else "-")
    rc3.metric("Risk/Ödül", f"{r.get('Risk/Ödül', 0):.2f}" if pd.notna(r.get("Risk/Ödül")) else "-")
    rc4.metric("Bağıl Hacim", f"{r.get('Bağıl Hacim', 0):.2f}x" if pd.notna(r.get("Bağıl Hacim")) else "-")

    if pd.notna(r.get("Temel Skor")):
        st.subheader("Temel Analiz")
        fc1, fc2, fc3 = st.columns(3)
        fc1.metric("Temel Skor", f"{r.get('Temel Skor', 0):.2f}")
        fc2.metric("Hacim Teyidi", r.get("Hacim Teyidi", "-"))
        fc3.metric("Haftalık Teyit", r.get("Haftalık Teyit", "-"))

if gelismis_row is not None:
    st.divider()
    st.subheader("Gelişmiş Göstergeler")
    gc1, gc2, gc3 = st.columns(3)
    gc1.metric("Fibonacci Trend Yönü", gelismis_row.get("Fib. Trend Yönü", "-"))
    gc2.metric("En Yakın Fib. Seviyesi", str(gelismis_row.get("En Yakın Fib. Seviyesi", "-")))
    gc3.metric("Mum Formasyonu", gelismis_row.get("Mum Formasyonu", "-") or "Yok")

    gc4, gc5 = st.columns(2)
    gc4.metric("POC (Hacim Odağı)", f"{gelismis_row.get('POC (Hacim Odağı)', 0):.2f}"
               if pd.notna(gelismis_row.get("POC (Hacim Odağı)")) else "-")
    gc5.metric("Formasyon Yönü", gelismis_row.get("Formasyon Yönü", "-") or "-")

st.divider()
st.caption("💡 RSI 70 üstü aşırı alım, 30 altı aşırı satım bölgesini gösterir. "
           "ADX 22 üstü net bir trend olduğuna işaret eder (eşik çizgisiyle işaretli). "
           "MACD histogramı, MACD çizgisinin sinyal çizgisinden uzaklığını gösterir.")

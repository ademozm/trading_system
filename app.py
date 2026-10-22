"""
Hisse/Kripto/Emtia Tarama Sistemi — Ana Sayfa

Çok sayfalı panel: bu dosya "Ana Sayfa" (tarama başlatma + genel bakış).
Diğer bölümler pages/ klasöründe, Streamlit bunları otomatik olarak sol
menüde ayrı sayfalar halinde listeler — gerçek bir site gibi gezinilir.

Çalıştırma:
    streamlit run app.py
"""
import logging
import os
import sys
import time
import traceback

import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import config
from main_scan import run_scan
from reporting import dashboard_charts as charts
import dashboard_common as dc

st.set_page_config(page_title="Hisse & Kripto Tarama Sistemi", layout="wide", page_icon="📈")
dc.inject_css()


class StreamlitLogHandler(logging.Handler):
    def __init__(self, container):
        super().__init__()
        self.container = container
        self.lines = []

    def emit(self, record):
        self.lines.append(self.format(record))
        self.container.code("\n".join(self.lines[-25:]), language=None)


st.title("📈 Hisse & Kripto Tarama Sistemi")
st.caption("Teknik + temel analiz + göreceli güç + risk + haber + grid/DCA — birleşik skorlama, çok kaynaklı doğrulama")

# ============ SOL PANEL: AYARLAR ============
with st.sidebar:
    st.header("🧭 Gezinme")
    st.page_link("app.py", label="Ana Sayfa", icon="🏠")
    st.page_link("pages/1_Grafik_Inceleme.py", label="Grafik İnceleme", icon="📈")
    st.page_link("pages/2_Piyasalar.py", label="Piyasalar", icon="💼")
    st.page_link("pages/3_Tum_Semboller.py", label="Tüm Sembol Durumu", icon="📋")
    st.page_link("pages/4_Temel_Risk_Gelismis.py", label="Temel & Risk & Gelişmiş", icon="🔬")
    st.page_link("pages/5_Grid_DCA.py", label="Grid & DCA", icon="🎯")
    st.page_link("pages/5b_Grid_DCA_Performans.py", label="Grid & DCA Performansı", icon="📊")
    st.page_link("pages/10_Portfoy_Korelasyon.py", label="Portföy Korelasyonu", icon="🔗")
    st.page_link("pages/11_Paper_Trading.py", label="Paper Trading", icon="💼")
    st.page_link("pages/6_Haberler.py", label="Haberler", icon="📰")
    st.page_link("pages/7_Takvim.py", label="Ekonomik Takvim", icon="📅")
    st.page_link("pages/8_Performans.py", label="Geçmiş Performans", icon="📜")
    st.page_link("pages/9_Hatalar.py", label="Hata Raporu", icon="⚠️")

    st.divider()
    st.header("Tarama Ayarları")

    markets_labels = {"ABD Hisseleri (S&P 100)": "us", "BIST": "bist", "Kripto Paralar": "crypto",
                       "Emtialar (Altın/Gümüş/Petrol/Doğalgaz)": "emtia"}
    selected_labels = st.multiselect("Hangi piyasalar taransın?", options=list(markets_labels.keys()),
                                      default=list(markets_labels.keys()))
    selected_markets = [markets_labels[l] for l in selected_labels]

    st.divider()
    st.subheader("Hız / Kapsam")
    use_cache = st.checkbox("Önbelleği kullan (daha hızlı)", value=True)
    skip_fundamentals = st.checkbox("Temel analizi atla (çok daha hızlı)", value=False)
    skip_news = st.checkbox("Haber analizini atla (daha hızlı)", value=False)

    st.divider()
    st.subheader("Filtreler")
    min_score = st.slider("Minimum skor (|değer|)", 0.0, 1.0, 0.15, 0.05)
    signal_choice = st.radio("Sinyal yönü", ["Hepsi", "Sadece AL", "Sadece SAT"])
    min_market_cap_b = st.number_input("Min. piyasa değeri (milyar $, 0=filtre yok)", min_value=0.0, value=0.0, step=0.5)
    max_pe = st.number_input("Maks. F/K oranı (0=filtre yok)", min_value=0.0, value=0.0, step=5.0)

    st.divider()
    st.subheader("Pozisyon Büyüklüğü")
    account_size = st.number_input("Varsayımsal hesap büyüklüğü ($)", min_value=100.0, value=10000.0, step=500.0)
    risk_pct = st.slider("İşlem başına risk (%)", 0.25, 5.0, 1.0, 0.25)

    st.divider()
    st.subheader("Otomasyon")
    auto_refresh = st.checkbox("Sembol listelerini otomatik güncelle", value=True)
    update_journal = st.checkbox("Sinyal günlüğüne kaydet", value=True)
    send_notify = st.checkbox("Telegram bildirimi gönder (varsa)", value=True)

    st.divider()
    run_clicked = st.button("🔍 Taramayı Başlat", type="primary", use_container_width=True)


if "last_report_path" not in st.session_state:
    st.session_state.last_report_path = dc.find_latest_report()

if run_clicked:
    if not selected_markets:
        st.error("En az bir piyasa seçmelisin.")
        st.stop()

    allowed_signals = None
    if signal_choice == "Sadece AL":
        allowed_signals = [1]
    elif signal_choice == "Sadece SAT":
        allowed_signals = [-1]

    overrides = {
        "min_composite_score": min_score,
        "allowed_signals": allowed_signals,
        "min_market_cap": min_market_cap_b * 1_000_000_000 if min_market_cap_b > 0 else None,
        "max_pe": max_pe if max_pe > 0 else None,
    }

    st.info("Tarama başladı — birkaç dakika sürebilir. Lütfen pencereyi kapatma.")
    progress_area = st.empty()
    handler = StreamlitLogHandler(progress_area)
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S"))
    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    start = time.time()
    try:
        output_path = run_scan(
            markets=selected_markets, use_cache=use_cache, skip_fundamentals=skip_fundamentals,
            skip_news=skip_news, filter_overrides=overrides, auto_refresh_universe=auto_refresh,
            send_notification=send_notify, update_journal=update_journal,
            account_size=account_size, risk_per_trade_pct=risk_pct,
        )
        st.session_state.last_report_path = output_path
        dc.load_sheets.clear()  # önbelleği temizle, yeni raporu okusun
        st.success(f"✅ Tarama tamamlandı! ({time.time() - start:.0f} saniye)")
    except Exception as e:
        st.error(f"Tarama sırasında hata oluştu: {e}")
        st.code(traceback.format_exc())
    finally:
        root_logger.removeHandler(handler)


# ============ GENEL BAKIŞ ============
path, sheets = dc.get_current_sheets()

if path:
    ozet = sheets.get("Özet", pd.DataFrame())
    full_status = sheets.get("Tüm Sembol Durumu", pd.DataFrame())

    report_dt = pd.Timestamp.fromtimestamp(os.path.getmtime(path))
    if not run_clicked:
        st.caption(f"📄 En son rapor gösteriliyor — {report_dt.strftime('%d.%m.%Y %H:%M')} tarihli "
                   f"(otomatik/bulut taramasından olabilir). Yeni tarama için soldan ayarları seçip "
                   f"'Taramayı Başlat'a bas.")

    st.divider()
    with open(path, "rb") as f:
        st.download_button("⬇️ Excel raporunu indir", data=f.read(), file_name=os.path.basename(path),
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

    # ---- KPI kartları ----
    total_scanned = len(full_status) if not full_status.empty else len(ozet)
    if not ozet.empty:
        al_count = (ozet["Sinyal"] == "AL").sum()
        sat_count = (ozet["Sinyal"] == "SAT").sum()
        avg_score = ozet["Skor"].abs().mean()
    else:
        al_count = sat_count = avg_score = 0
    supheli_count = (ozet.get("Veri Şüpheli mi", pd.Series(dtype=str)) == "Evet").sum() if not ozet.empty else 0
    takvim_df = sheets.get("Ekonomik Takvim", pd.DataFrame())
    yaklasan_olay = len(takvim_df) if "Tarih" in takvim_df.columns else 0

    c0, c1, c2, c3, c4, c5 = st.columns(6)
    c0.metric("Taranan Sembol", total_scanned)
    c1.metric("Sinyal Üreten", len(ozet))
    c2.metric("AL", al_count)
    c3.metric("SAT", sat_count)
    c4.metric("Ort. |Skor|", f"{avg_score:.2f}" if avg_score else "-")
    c5.metric("Yaklaşan Olay", yaklasan_olay, delta="⚠️" if yaklasan_olay > 0 else None)

    if supheli_count > 0:
        st.warning(f"⚠️ {supheli_count} sembolde yfinance/Stooq veri uyuşmazlığı — 'Piyasalar' sayfasına bak.")
    if total_scanned and len(ozet) < total_scanned * 0.15:
        st.info(f"ℹ️ {total_scanned} sembol tarandı, sadece {len(ozet)} tanesi net bir AL/SAT sinyali üretti — "
                f"bu normaldir (piyasa sakin olabilir). Taranan HER sembolün durumunu görmek için "
                f"soldaki **'Tüm Sembol Durumu'** sayfasına bak.")

    st.divider()
    st.subheader("📊 Genel Bakış")
    if ozet.empty:
        st.info("Bu taramada sinyal üreten sembol bulunamadı — 'Tüm Sembol Durumu' sayfasından tarananların "
                "tam listesini görebilirsin.")
    else:
        col1, col2 = st.columns(2)
        with col1:
            st.plotly_chart(charts.market_breakdown_pie(ozet), use_container_width=True)
        with col2:
            st.plotly_chart(charts.score_histogram(ozet), use_container_width=True)
        st.plotly_chart(charts.top_signals_bar(ozet, n=10), use_container_width=True)

    st.divider()
    st.markdown("👈 Detaylı analiz için soldaki menüden bir sayfa seç.")

else:
    st.info("Soldaki ayarları seç ve **'Taramayı Başlat'** butonuna bas.")
    st.markdown("""
    **İlk kez mi kullanıyorsun?**
    1. Soldan taramak istediğin piyasaları seç (ABD / BIST / Kripto / Emtia)
    2. Hızlı bir deneme için "Temel analizi atla" kutucuğunu işaretle
    3. "Taramayı Başlat" butonuna bas
    4. Birkaç dakika sonra: KPI kartları, genel bakış grafikleri burada; detaylı analiz sol menüdeki
       sayfalarda (Grafik İnceleme, Piyasalar, Grid & DCA, Haberler...) görünecek
    """)

"""
Portföy-seviyesi korelasyon kontrolü.

SORUN: position_sizing.py her sinyali BAĞIMSIZ bir bahis gibi
boyutlandırır (her biri hesabın %1'ini riske atar gibi). Ama aynı anda
gelen 5 sinyal birbirine yüksek korelasyonluysa (örn. hepsi aynı sektör,
ya da hepsi genel piyasa yönünü takip ediyorsa), bunlar aslında BAĞIMSIZ
DEĞİL — piyasa ters giderse hepsi AYNI ANDA zarar eder. Bu durumda
gerçek risk, "5 × %1 = %5" değil, korelasyon derecesine göre çok daha
yüksek olabilir (en kötü senaryoda neredeyse %5'in tamamı aynı anda
gerçekleşir).

ÇÖZÜM: Sinyal üreten sembollerin son N günlük getirileri arasında
korelasyon matrisi hesaplanır. Yüksek korelasyonlu (varsayılan eşik: 0.7)
semboller bir "küme" olarak gruplanır. Aynı kümedeki sembollerin önerilen
pozisyon büyüklüğü, küme büyüklüğüne göre AŞAĞI ÇEKİLİR — böylece o küme
toplamda tek bir "bağımsız bahis" kadar risk taşır, N tane değil.

DÜRÜSTLÜK NOTU: Bu basit, sezgisel bir düzeltmedir — modern portföy
teorisindeki gibi tam bir kovaryans-optimizasyonu (örn. risk paritesi)
YAPMAZ. Amaç, en azından "bunlar birbirinden bağımsız değil" uyarısını
vermek ve kaba bir düzeltme sunmak; profesyonel bir portföy yöneticisinin
yerini tutmaz.
"""
import logging

import numpy as np
import pandas as pd

logger = logging.getLogger("portfolio_correlation")

DEFAULT_CORRELATION_THRESHOLD = 0.7
DEFAULT_LOOKBACK_DAYS = 60


def compute_returns_matrix(data_by_symbol: dict, symbols: list, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    """
    Verilen sembollerin son `lookback_days` günlük getirilerini tek bir
    DataFrame'de hizalar (ortak tarihler üzerinden). Sembol sayısı < 2
    veya yeterli ortak veri yoksa boş DataFrame döner.
    """
    series_dict = {}
    for symbol in symbols:
        df = data_by_symbol.get(symbol)
        if df is None or df.empty or "Close" not in df.columns:
            continue
        returns = df["Close"].pct_change().dropna().tail(lookback_days)
        if len(returns) >= 10:  # çok kısa seri güvenilir korelasyon vermez
            series_dict[symbol] = returns

    if len(series_dict) < 2:
        return pd.DataFrame()

    # Farklı sembollerin index'leri (tarihleri) farklı olabilir (tatil günleri
    # vb. piyasaya göre değişir) — ortak tarihler üzerinden hizala (inner join)
    returns_df = pd.DataFrame(series_dict)
    returns_df = returns_df.dropna(how="any")
    return returns_df


def compute_correlation_matrix(data_by_symbol: dict, symbols: list, lookback_days: int = DEFAULT_LOOKBACK_DAYS) -> pd.DataFrame:
    returns_df = compute_returns_matrix(data_by_symbol, symbols, lookback_days)
    if returns_df.empty or len(returns_df) < 10:
        return pd.DataFrame()
    return returns_df.corr()


def find_correlated_clusters(corr_matrix: pd.DataFrame, threshold: float = DEFAULT_CORRELATION_THRESHOLD) -> list[list[str]]:
    """
    Korelasyon matrisinden, birbirine `threshold` üstü pozitif korelasyonlu
    sembol gruplarını (bağlı bileşenler / connected components) bulur.
    Negatif korelasyon burada "risk" sayılmaz (aksine çeşitlendirme
    faydası sağlar), bu yüzden sadece POZİTİF yüksek korelasyon aranır.
    """
    if corr_matrix.empty:
        return []

    symbols = corr_matrix.columns.tolist()
    visited = set()
    clusters = []

    def _neighbors(sym):
        return [s for s in symbols if s != sym and corr_matrix.loc[sym, s] > threshold]

    for symbol in symbols:
        if symbol in visited:
            continue
        # BFS ile bağlı bileşeni bul
        cluster = {symbol}
        queue = [symbol]
        visited.add(symbol)
        while queue:
            current = queue.pop()
            for neighbor in _neighbors(current):
                if neighbor not in visited:
                    visited.add(neighbor)
                    cluster.add(neighbor)
                    queue.append(neighbor)
        clusters.append(sorted(cluster))

    # Tek elemanlı "kümeler" gerçek bir küme değildir, filtrele
    return [c for c in clusters if len(c) > 1]


def adjust_position_sizes(scored_df: pd.DataFrame, clusters: list[list[str]]) -> pd.DataFrame:
    """
    scored_df: position_sizing.compute_for_scored_df() çıktısı (onerilen_adet,
    pozisyon_buyuklugu, portfoy_yuzdesi kolonlarını içermeli).

    Her küme üyesinin pozisyon büyüklüğü, küme büyüklüğüne bölünerek aşağı
    çekilir (örn. 3'lü bir kümede her biri 1/3'e iner) — böylece küme
    toplamda tek bir bağımsız pozisyon kadar risk bütçesi kullanır.
    """
    if scored_df.empty or not clusters:
        result = scored_df.copy()
        result["korelasyon_kumesi"] = None
        result["efektif_pozisyon_buyuklugu"] = result.get("pozisyon_buyuklugu")
        result["efektif_portfoy_yuzdesi"] = result.get("portfoy_yuzdesi")
        return result

    result = scored_df.copy()
    result["korelasyon_kumesi"] = None
    result["efektif_pozisyon_buyuklugu"] = result.get("pozisyon_buyuklugu")
    result["efektif_portfoy_yuzdesi"] = result.get("portfoy_yuzdesi")

    symbol_to_cluster = {}
    for i, cluster in enumerate(clusters):
        for sym in cluster:
            symbol_to_cluster[sym] = i

    for idx, row in result.iterrows():
        cluster_id = symbol_to_cluster.get(row["symbol"])
        if cluster_id is None:
            continue
        cluster = clusters[cluster_id]
        cluster_label = " ↔ ".join(cluster)
        result.at[idx, "korelasyon_kumesi"] = cluster_label

        divisor = len(cluster)
        for col_src, col_dst in [("onerilen_adet", "onerilen_adet"),
                                  ("pozisyon_buyuklugu", "efektif_pozisyon_buyuklugu"),
                                  ("portfoy_yuzdesi", "efektif_portfoy_yuzdesi")]:
            if col_src in result.columns and pd.notna(row.get(col_src)):
                result.at[idx, col_dst] = row[col_src] / divisor

    return result


def portfolio_summary(scored_df: pd.DataFrame, corr_matrix: pd.DataFrame, clusters: list[list[str]]) -> dict:
    """Genel özet: toplam naif risk vs. düzeltilmiş risk, en yüksek korelasyon, uyarı."""
    if scored_df.empty or "portfoy_yuzdesi" not in scored_df.columns:
        return {"not": "Pozisyon büyüklüğü verisi yok, özet hesaplanamadı."}

    naive_total_pct = scored_df["portfoy_yuzdesi"].dropna().sum()
    effective_col = "efektif_portfoy_yuzdesi" if "efektif_portfoy_yuzdesi" in scored_df.columns else "portfoy_yuzdesi"
    effective_total_pct = scored_df[effective_col].dropna().sum()

    max_corr = None
    if not corr_matrix.empty:
        upper = corr_matrix.where(np.triu(np.ones(corr_matrix.shape), k=1).astype(bool))
        if upper.notna().any().any():
            max_corr = round(upper.max().max(), 2)

    return {
        "naif_toplam_portfoy_yuzdesi": round(naive_total_pct, 1),
        "duzeltilmis_toplam_portfoy_yuzdesi": round(effective_total_pct, 1),
        "kume_sayisi": len(clusters),
        "kumelenmis_sembol_sayisi": sum(len(c) for c in clusters),
        "en_yuksek_ikili_korelasyon": max_corr,
        "uyari": len(clusters) > 0,
    }

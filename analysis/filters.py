"""
Filtreleme motoru.

Skorlanmış tam evren tablosunu alır, config.py > FILTERS (veya main_scan.py
--min-score, --max-pe gibi CLI argümanlarıyla override edilen) kriterlere
göre süzer. Amaç: "tam kapsamlı analiz" yapılsın ama kullanıcı sadece
kendi kriterlerine uyan sonuçları görsün.

Her filtre, ilgili kolon eksikse (örn. kripto için P/E yok) o satırı
ELEMEZ — sadece o kritere göre değerlendirmez. Böylece kripto, temel
analiz filtrelerinden dolayı haksız yere elenmez.
"""
import pandas as pd


def apply_filters(df: pd.DataFrame, filters: dict) -> tuple[pd.DataFrame, dict]:
    """
    filters örneği (config.FILTERS varsayılanı):
    {
        "min_composite_score": 0.3,       # |skor| bu değerin altındaysa ele
        "min_market_cap": 1_000_000_000,  # 1 milyar USD altı şirketleri ele
        "max_pe": 60,                     # aşırı pahalı şirketleri ele (None varsa kripto/veri yoksa uygulanmaz)
        "min_relative_volume": 0.5,       # işlem hacmi çok düşükse (likidite riski) ele
        "allowed_signals": [1, -1],       # sadece AL, sadece SAT veya ikisi de
        "require_mtf_confirmation": False # haftalık trend teyidi zorunlu mu
    }
    Dönüş: (filtrelenmiş_df, eleme_istatistikleri)
    """
    if df.empty:
        return df, {}

    result = df.copy()
    stats = {"başlangıç": len(result)}

    if "allowed_signals" in filters and filters["allowed_signals"]:
        result = result[result["signal"].isin(filters["allowed_signals"])]
        stats["sinyal_yönü_filtresi_sonrası"] = len(result)

    if "min_composite_score" in filters and filters["min_composite_score"] is not None:
        result = result[result["composite_score"].abs() >= filters["min_composite_score"]]
        stats["min_skor_filtresi_sonrası"] = len(result)

    if "min_market_cap" in filters and filters["min_market_cap"] is not None and "marketCap" in result.columns:
        mask = result["marketCap"].isna() | (result["marketCap"] >= filters["min_market_cap"])
        result = result[mask]
        stats["min_piyasa_değeri_filtresi_sonrası"] = len(result)

    if "max_pe" in filters and filters["max_pe"] is not None and "trailingPE" in result.columns:
        mask = result["trailingPE"].isna() | (result["trailingPE"] <= 0) | (result["trailingPE"] <= filters["max_pe"])
        result = result[mask]
        stats["max_pe_filtresi_sonrası"] = len(result)

    if "min_relative_volume" in filters and filters["min_relative_volume"] is not None and "relative_volume" in result.columns:
        mask = result["relative_volume"].isna() | (result["relative_volume"] >= filters["min_relative_volume"])
        result = result[mask]
        stats["min_hacim_filtresi_sonrası"] = len(result)

    if filters.get("require_mtf_confirmation") and "mtf_confirmed" in result.columns:
        mask = result["mtf_confirmed"].isna() | (result["mtf_confirmed"] == True)  # noqa: E712
        result = result[mask]
        stats["haftalık_teyit_filtresi_sonrası"] = len(result)

    stats["son"] = len(result)
    return result.reset_index(drop=True), stats

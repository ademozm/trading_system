"""
Grid (ızgara) trading strateji önerisi.

Grid trading, fiyatın belirli bir aralıkta yatay (range) hareket ettiği
dönemlerde işe yarar: fiyat aralığı eşit dilimlere bölünür, her seviyede
bir AL emri, bir seviye üstünde karşılık gelen bir SAT emri planlanır.
Fiyat aralık içinde iner-çıkarken her "dalga"dan küçük bir kâr toplanır.

ÖNEMLİ: Bu sistem GERÇEK EMİR GÖNDERMEZ — sadece bir grid planı önerir.
Bu planı ya elle uygularsın, ya da çoğu büyük borsanın (Binance, vb.)
kendi yerleşik "Grid Bot" özelliğine bu seviyeleri girerek kullanırsın.

Sadece REJİM = "range" (yatay) olan semboller için anlamlıdır — trend
halindeki bir sembolde grid stratejisi fiyat tek yöne kaçtığında zarar
riski taşır, bu yüzden trend rejiminde grid önerisi verilmez.
"""
import numpy as np
import pandas as pd


def suggest_grid(
    df: pd.DataFrame,
    regime: str,
    total_position_value: float,
    num_levels: int = 5,
    lookback_days: int = 60,
) -> dict:
    """
    df: OHLCV DataFrame (en az lookback_days kadar veri)
    regime: strategy.py'den gelen "trend" veya "range"
    total_position_value: bu sembole ayrılacak toplam bütçe ($)

    Dönüş: {"uygun_mu": bool, "gerekce": str, "seviyeler": [...]} — her
    seviye {"seviye": i, "al_fiyati": ..., "sat_fiyati": ..., "adet": ...}
    """
    if regime != "range":
        return {
            "uygun_mu": False,
            "gerekce": "Sembol trend rejiminde; grid stratejisi yatay piyasalar için uygundur, trend'de kullanılması tavsiye edilmez.",
            "seviyeler": [],
        }

    window = df.tail(lookback_days)
    if len(window) < 10:
        return {"uygun_mu": False, "gerekce": "Yetersiz geçmiş veri.", "seviyeler": []}

    grid_low = float(window["Low"].min())
    grid_high = float(window["High"].max())

    if grid_high <= grid_low or num_levels < 2:
        return {"uygun_mu": False, "gerekce": "Fiyat aralığı çok dar veya geçersiz.", "seviyeler": []}

    step = (grid_high - grid_low) / num_levels
    value_per_level = total_position_value / num_levels

    seviyeler = []
    for i in range(num_levels):
        al_fiyati = grid_low + i * step
        sat_fiyati = al_fiyati + step
        adet = value_per_level / al_fiyati if al_fiyati > 0 else 0
        seviyeler.append({
            "seviye": i + 1,
            "al_fiyati": round(al_fiyati, 4),
            "sat_fiyati": round(sat_fiyati, 4),
            "adet": round(adet, 4),
            "beklenen_kar_pct": round((sat_fiyati / al_fiyati - 1) * 100, 2) if al_fiyati > 0 else 0,
        })

    return {
        "uygun_mu": True,
        "gerekce": f"Son {lookback_days} günlük aralık ({grid_low:.2f}-{grid_high:.2f}) temel alındı.",
        "grid_low": round(grid_low, 4),
        "grid_high": round(grid_high, 4),
        "seviyeler": seviyeler,
    }

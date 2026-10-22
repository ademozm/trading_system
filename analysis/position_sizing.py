"""
Pozisyon büyüklüğü önerisi.

Bir sinyal listesi ile "kaç hisse/kripto/lot alınmalı" arasındaki farkı
kapatır — bu, bir "sinyal listesi"ni gerçek bir "trade sistemi"ne
dönüştüren parçalardan biri.

Mantık: sabit bir yüzde (varsayılan %1) sermaye, her işlemde risk
edilir. Stop-loss mesafesi (ATR tabanlı, strategy.py'den gelir) ne kadar
genişse, pozisyon o kadar küçük olur — böylece her işlemin potansiyel
kaybı, hesabın aynı yüzdesiyle sınırlı kalır. Bu, profesyonel risk
yönetiminin temel prensiplerinden biridir (sabit lot değil, riske göre
boyutlandırma).

DÜRÜSTLÜK NOTU: Bu bir öneri motorudur, kesin bir talimat değil. Kendi
risk toleransını, komisyon yapını ve portföyündeki diğer pozisyonları
hesaba katman gerekir. Aynı anda birden fazla sinyal takip ediyorsan,
toplam portföy riskinin kontrolden çıkmaması için pozisyonlar arası
korelasyona da dikkat et (örn. aynı sektörden 5 hisse aynı anda AL
sinyali verirse, bunlar bağımsız riskler değildir).
"""
import numpy as np
import pandas as pd


def suggest_position_size(
    account_size: float,
    entry_price: float,
    stop_price: float,
    risk_per_trade_pct: float = 1.0,
) -> dict:
    """
    Dönüş: {"risk_tutari": ..., "onerilen_adet": ..., "pozisyon_buyuklugu": ...,
            "portfoy_yuzdesi": ...}
    """
    if account_size <= 0 or entry_price <= 0:
        return {"risk_tutari": None, "onerilen_adet": None,
                "pozisyon_buyuklugu": None, "portfoy_yuzdesi": None}

    stop_distance = abs(entry_price - stop_price)
    if stop_distance <= 0:
        return {"risk_tutari": None, "onerilen_adet": None,
                "pozisyon_buyuklugu": None, "portfoy_yuzdesi": None}

    risk_tutari = account_size * (risk_per_trade_pct / 100)
    onerilen_adet = risk_tutari / stop_distance
    pozisyon_buyuklugu = onerilen_adet * entry_price
    portfoy_yuzdesi = (pozisyon_buyuklugu / account_size) * 100

    # Aşırı kaldıraçlı/mantıksız önerileri sınırla (örn. çok dar stop mesafesi
    # varsa pozisyon büyüklüğü hesabın tamamını aşmasın)
    if pozisyon_buyuklugu > account_size:
        onerilen_adet = account_size / entry_price
        pozisyon_buyuklugu = account_size
        portfoy_yuzdesi = 100.0

    return {
        "risk_tutari": round(risk_tutari, 2),
        "onerilen_adet": round(onerilen_adet, 4),
        "pozisyon_buyuklugu": round(pozisyon_buyuklugu, 2),
        "portfoy_yuzdesi": round(portfoy_yuzdesi, 2),
    }


def compute_for_scored_df(
    scored_df: pd.DataFrame,
    account_size: float,
    risk_per_trade_pct: float = 1.0,
) -> pd.DataFrame:
    """
    scored_df: en az 'close', 'signal', 'atr_pct' kolonlarını içermeli
    (main_scan.py'nin ürettiği format). Stop mesafesi ATR yüzdesinden
    (atr_pct) türetilir çünkü ham stop_price rapora taşınmıyor.
    """
    if scored_df.empty:
        return scored_df

    results = []
    for _, row in scored_df.iterrows():
        entry = row.get("close")
        atr_pct = row.get("atr_pct")
        signal = row.get("signal", 0)
        if pd.isna(entry) or pd.isna(atr_pct) or signal == 0:
            results.append({"symbol": row["symbol"], "risk_tutari": None,
                             "onerilen_adet": None, "pozisyon_buyuklugu": None,
                             "portfoy_yuzdesi": None})
            continue

        # ATR yüzdesinden yaklaşık stop fiyatı (strategy.py'deki atr_stop_mult ile tutarlı: 2x ATR)
        stop_distance_pct = (atr_pct / 100) * 2
        stop_price = entry * (1 - stop_distance_pct) if signal == 1 else entry * (1 + stop_distance_pct)

        sizing = suggest_position_size(account_size, entry, stop_price, risk_per_trade_pct)
        results.append({"symbol": row["symbol"], **sizing})

    sizing_df = pd.DataFrame(results)
    return scored_df.merge(sizing_df, on="symbol", how="left")

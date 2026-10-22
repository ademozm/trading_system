"""
Ekonomik takvim.

ABD piyasasını en çok sarsan olaylar genelde belirli, önceden bilinen
tarihlerde gerçekleşir: FOMC (Fed) faiz kararı toplantıları, aylık
enflasyon (CPI) ve istihdam (NFP) verileri gibi. Bu modül, yaklaşan
böyle bir tarih varsa kullanıcıyı uyarır — "önümüzdeki birkaç gün içinde
piyasa normalden daha oynak olabilir" bilgisi.

DÜRÜSTLÜK NOTU: FOMC tarihleri Fed'in resmi takviminden alınmıştır ama
Fed zaman zaman olağanüstü toplantılar da yapabilir; bu liste dinamik
değildir, periyodik olarak (yılda bir) elle güncellenmesi gerekir. CPI/NFP
tarihleri kesin gün değil, "ayın yaklaşık şu haftası" şeklinde bir
YAKLAŞIKLIKTIR (kesin tarih için bls.gov'un resmi takvimine bakılmalı).
Bu bir ekonomik veri sağlayıcısı DEĞİLDİR, sadece "dikkatli ol" uyarısı.
"""
from datetime import datetime, timedelta

import pandas as pd

# 2026 FOMC toplantı tarihleri (Federal Reserve resmi takvimi, faiz kararı günleri)
# Kaynak: federalreserve.gov/monetarypolicy/fomccalendars.htm — YILDA BİR ELLE GÜNCELLE
FOMC_DATES_2026 = [
    "2026-01-28", "2026-03-18", "2026-04-29", "2026-06-17",
    "2026-07-29", "2026-09-16", "2026-10-28", "2026-12-09",
]


def upcoming_fomc_dates(reference_date: datetime = None, lookahead_days: int = 14) -> list[dict]:
    reference_date = reference_date or datetime.now()
    horizon = reference_date + timedelta(days=lookahead_days)
    upcoming = []
    for date_str in FOMC_DATES_2026:
        date = datetime.strptime(date_str, "%Y-%m-%d")
        if reference_date.date() <= date.date() <= horizon.date():
            days_left = (date.date() - reference_date.date()).days
            upcoming.append({
                "tarih": date_str,
                "olay": "FOMC Faiz Kararı (Fed)",
                "kalan_gun": days_left,
                "onem": "Yüksek",
            })
    return upcoming


def upcoming_recurring_events(reference_date: datetime = None, lookahead_days: int = 14) -> list[dict]:
    """
    Kesin tarih yerine yaklaşık kural: NFP (istihdam) her ayın ilk Cuma
    günü, CPI (enflasyon) genelde ayın 10-15'i arası yayınlanır. Bunlar
    YAKLAŞIK kurallardır, kesin tarih için resmi takvime bakılmalı.
    """
    reference_date = reference_date or datetime.now()
    horizon = reference_date + timedelta(days=lookahead_days)
    events = []

    # Bu ay ve gerekiyorsa bir sonraki ayın ilk Cuma günü (NFP)
    for month_offset in (0, 1):
        month = reference_date.month + month_offset
        year = reference_date.year + (1 if month > 12 else 0)
        month = ((month - 1) % 12) + 1
        first_day = datetime(year, month, 1)
        days_to_friday = (4 - first_day.weekday()) % 7
        first_friday = first_day + timedelta(days=days_to_friday)
        if reference_date.date() <= first_friday.date() <= horizon.date():
            days_left = (first_friday.date() - reference_date.date()).days
            events.append({
                "tarih": first_friday.strftime("%Y-%m-%d"),
                "olay": "ABD Tarım Dışı İstihdam (NFP) - yaklaşık tarih",
                "kalan_gun": days_left,
                "onem": "Yüksek",
            })

    # Bu ayın 12'si (CPI için kaba bir yaklaşım orta nokta)
    for month_offset in (0, 1):
        month = reference_date.month + month_offset
        year = reference_date.year + (1 if month > 12 else 0)
        month = ((month - 1) % 12) + 1
        approx_cpi_date = datetime(year, month, 12)
        if reference_date.date() <= approx_cpi_date.date() <= horizon.date():
            days_left = (approx_cpi_date.date() - reference_date.date()).days
            events.append({
                "tarih": approx_cpi_date.strftime("%Y-%m-%d"),
                "olay": "ABD Enflasyon (CPI) - yaklaşık tarih, ±birkaç gün sapabilir",
                "kalan_gun": days_left,
                "onem": "Yüksek",
            })

    return events


def get_calendar(reference_date: datetime = None, lookahead_days: int = 14) -> pd.DataFrame:
    reference_date = reference_date or datetime.now()
    events = upcoming_fomc_dates(reference_date, lookahead_days) + \
        upcoming_recurring_events(reference_date, lookahead_days)
    if not events:
        return pd.DataFrame(columns=["tarih", "olay", "kalan_gun", "onem"])
    df = pd.DataFrame(events).sort_values("kalan_gun").reset_index(drop=True)
    return df

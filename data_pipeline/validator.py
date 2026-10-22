"""
Veri kalitesi doğrulama.

Analiz motoruna kötü veri girmesini engellemek kritik: bir hisse için
eksik/bayat/hatalı veri varsa, üretilecek sinyal ve skor da anlamsız
olur — ve bu sessizce olur, hata fırlatmadan. Bu modül her sembolü
analiz öncesi süzer.
"""
from dataclasses import dataclass

import pandas as pd

import config


@dataclass
class ValidationResult:
    symbol: str
    is_valid: bool
    reasons: list


REQUIRED_COLUMNS = ["Open", "High", "Low", "Close", "Volume"]


def validate(symbol: str, df: pd.DataFrame) -> ValidationResult:
    reasons = []

    if df is None or df.empty:
        return ValidationResult(symbol, False, ["Veri boş"])

    missing_cols = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing_cols:
        return ValidationResult(symbol, False, [f"Eksik kolonlar: {missing_cols}"])

    if len(df) < config.MIN_ROWS_REQUIRED:
        reasons.append(f"Yetersiz veri: {len(df)} satır (min {config.MIN_ROWS_REQUIRED})")

    if df[REQUIRED_COLUMNS].isna().any().any():
        reasons.append("NaN değer içeriyor")

    if (df["Close"] <= 0).any() or (df["Open"] <= 0).any():
        reasons.append("Sıfır veya negatif fiyat içeriyor")

    if (df["High"] < df["Low"]).any():
        reasons.append("High < Low tutarsızlığı var")

    if not isinstance(df.index, pd.DatetimeIndex):
        reasons.append("Index tarih formatında değil (DatetimeIndex bekleniyor)")
    else:
        tz = getattr(df.index, "tz", None)
        stale_days = (pd.Timestamp.now(tz=tz) - df.index[-1]).days
        if stale_days > config.MAX_STALE_DAYS:
            reasons.append(f"Veri bayat: son mum {stale_days} gün önce")

    daily_returns = df["Close"].pct_change().abs()
    extreme_moves = daily_returns[daily_returns > config.MAX_DAILY_RETURN_ABS]
    if len(extreme_moves) > 0:
        reasons.append(f"{len(extreme_moves)} adet şüpheli aşırı fiyat hareketi (>{config.MAX_DAILY_RETURN_ABS*100:.0f}%)")

    # Sadece "hard fail" nedenleri geçersiz sayılır; stale/extreme move gibi
    # uyarılar rapora not düşülür ama sembolü tamamen elemez (opsiyonel: sıkılaştırılabilir).
    hard_fail_keywords = ["boş", "Eksik kolonlar", "Yetersiz veri", "NaN", "negatif fiyat", "tutarsızlığı", "tarih formatında"]
    is_valid = not any(any(k in r for k in hard_fail_keywords) for r in reasons)

    return ValidationResult(symbol, is_valid, reasons)


def validate_batch(data: dict) -> tuple[dict, dict]:
    """
    data: symbol -> DataFrame
    Dönüş: (valid_data, validation_report)
      valid_data: symbol -> DataFrame (sadece geçerli olanlar)
      validation_report: symbol -> ValidationResult (hepsi)
    """
    valid_data = {}
    report = {}
    for symbol, df in data.items():
        vr = validate(symbol, df)
        report[symbol] = vr
        if vr.is_valid:
            valid_data[symbol] = df
    return valid_data, report

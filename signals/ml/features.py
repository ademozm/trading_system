"""
Katman 3b — Özellik Mühendisliği & Etiketleme
=================================================
ML sinyalinin girdi/çıktı sözleşmesini tanımlar. Bilinçli olarak
TA-Lib gibi C kütüphanesi gerektiren bir bağımlılık KULLANMIYORUZ —
tüm göstergeler saf pandas ile hesaplanıyor, böylece kurulum sürtünmesi
en aza iniyor (TA-Lib kurulumu çoğu kullanıcı için en çok soruna yol
açan adımdır).

KRİTİK — Look-ahead bias'tan kaçınma kuralları:
  - Her özellik SADECE o satıra kadar bilinen veriyi kullanır (rolling/shift).
  - Etiket (label) ise GELECEK bir bardaki getiriye bakar (`shift(-horizon)`)
    — bu satırlar backtest/train ayrımında SADECE etiket üretimi için
    kullanılır, özellik olarak asla kullanılmaz.
  - `build_features` ve `build_labels` ayrı fonksiyonlardır ki bu ayrım
    yanlışlıkla karışmasın.
"""

from __future__ import annotations

import pandas as pd


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Klasik RSI hesabı (Wilder'ın orijinal yöntemi yerine basit SMA tabanlı
    ortalama kazanç/kayıp — anlaşılması kolay, eğitim/prod arasında tutarlı)."""
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.rolling(window=period, min_periods=period).mean()
    avg_loss = loss.rolling(window=period, min_periods=period).mean()
    rs = avg_gain / avg_loss.replace(0, pd.NA)
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(50.0)  # veri yetersizken nötr değer


FEATURE_COLUMNS = [
    "return_1",
    "return_3",
    "return_6",
    "return_12",
    "volatility_12",
    "volatility_24",
    "momentum_10",
    "sma_ratio_20",
    "rsi_14",
    "volume_change_1",
]


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """
    `df`: en az `timestamp`(index veya sütun), `open`, `high`, `low`,
    `close`, `volume` sütunlarını içermeli (data_layer.storage'ın
    döndürdüğü standart şema).

    Döndürülen DataFrame, orijinal sütunlara ek olarak FEATURE_COLUMNS'ta
    listelenen özellik sütunlarını içerir. Yetersiz geçmiş veri nedeniyle
    NaN olan satırlar (ör. ilk 24 bar) burada SİLİNMEZ — bu karar,
    çağıran tarafa (train.py / ml_signal.py) bırakılmıştır.
    """
    out = df.copy()

    out["return_1"] = out["close"].pct_change(1)
    out["return_3"] = out["close"].pct_change(3)
    out["return_6"] = out["close"].pct_change(6)
    out["return_12"] = out["close"].pct_change(12)

    out["volatility_12"] = out["return_1"].rolling(window=12).std()
    out["volatility_24"] = out["return_1"].rolling(window=24).std()

    out["momentum_10"] = out["close"] - out["close"].shift(10)

    sma_20 = out["close"].rolling(window=20).mean()
    out["sma_ratio_20"] = out["close"] / sma_20

    out["rsi_14"] = _rsi(out["close"], period=14)

    out["volume_change_1"] = out["volume"].pct_change(1)

    return out


def build_labels(
    df: pd.DataFrame,
    horizon: int = 6,
    up_threshold: float = 0.005,
    down_threshold: float = -0.005,
) -> pd.Series:
    """
    Her satır için `horizon` bar sonraki getiriye bakarak 3 sınıflı bir
    etiket üretir: 1 (yukarı hareket bekleniyor), -1 (aşağı), 0 (düz).

    UYARI: Bu fonksiyonun ürettiği son `horizon` satır NaN olacaktır
    (gelecekte veri yok) — bunlar hem eğitimden hem testten çıkarılmalıdır.
    """
    forward_return = df["close"].shift(-horizon) / df["close"] - 1.0

    labels = pd.Series(0, index=df.index, dtype="Int64")
    labels[forward_return > up_threshold] = 1
    labels[forward_return < down_threshold] = -1
    labels[forward_return.isna()] = pd.NA

    return labels


def build_dataset(
    df: pd.DataFrame,
    horizon: int = 6,
    up_threshold: float = 0.005,
    down_threshold: float = -0.005,
) -> pd.DataFrame:
    """
    build_features + build_labels'ı birleştirir ve NaN içeren satırları
    (hem özellik ısınma dönemi hem de etiket ufku için) temizler.
    Eğitim scriptinin (train.py) doğrudan kullanacağı nihai tablo budur.
    """
    features = build_features(df)
    features["label"] = build_labels(df, horizon, up_threshold, down_threshold)

    required_cols = FEATURE_COLUMNS + ["label"]
    return features.dropna(subset=required_cols).reset_index(drop=True)

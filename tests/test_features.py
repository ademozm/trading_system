"""
tests/test_features.py
========================
signals/ml/features.py'nin doğru çalıştığını doğrular. Sadece pandas/numpy
bağımlılığı vardır (lightgbm/sklearn gerekmez) — bu yüzden bu test dosyası
ML kütüphaneleri kurulu olmasa bile çalışır.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.ml.features import FEATURE_COLUMNS, build_dataset, build_features, build_labels


def _make_synthetic_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    price = 100 + np.cumsum(rng.normal(0.05, 0.3, n))
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
            "open": price,
            "high": price + 0.5,
            "low": price - 0.5,
            "close": price,
            "volume": rng.integers(100, 1000, n).astype(float),
        }
    )


def test_build_features_creates_all_expected_columns() -> None:
    df = _make_synthetic_ohlcv()
    feats = build_features(df)
    for col in FEATURE_COLUMNS:
        assert col in feats.columns, f"{col} eksik"


def test_rsi_is_bounded_between_0_and_100() -> None:
    df = _make_synthetic_ohlcv()
    feats = build_features(df)
    valid_rsi = feats["rsi_14"].dropna()
    assert (valid_rsi >= 0).all() and (valid_rsi <= 100).all()


def test_labels_reflect_forward_returns() -> None:
    # Monoton artan bir fiyat serisinde her satır "yukarı" etiketlenmeli
    # (son `horizon` satır hariç, onlar NaN olur).
    n = 50
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=n, freq="h"),
            "open": np.linspace(100, 150, n),
            "high": np.linspace(100, 150, n) + 0.1,
            "low": np.linspace(100, 150, n) - 0.1,
            "close": np.linspace(100, 150, n),
            "volume": np.full(n, 500.0),
        }
    )
    labels = build_labels(df, horizon=3, up_threshold=0.001, down_threshold=-0.001)
    non_na = labels.dropna()
    assert (non_na == 1).all(), "Monoton artan seride tüm etiketler 'yukarı' (1) olmalı"
    assert labels.iloc[-3:].isna().all(), "Son `horizon` satır NaN olmalı (gelecek veri yok)"


def test_build_dataset_has_no_nan_and_correct_columns() -> None:
    df = _make_synthetic_ohlcv()
    dataset = build_dataset(df, horizon=6, up_threshold=0.001, down_threshold=-0.001)

    required = FEATURE_COLUMNS + ["label"]
    assert not dataset[required].isna().any().any(), "Nihai dataset'te NaN kalmamalı"
    assert len(dataset) < len(df), "Isınma dönemi + etiket ufku nedeniyle satır sayısı azalmalı"


def test_build_dataset_raises_no_error_on_short_series() -> None:
    # Çok kısa bir seri: tüm satırlar ısınma dönemine düşer -> boş dataset
    # (hata fırlatmamalı, sadece boş dönmeli).
    df = _make_synthetic_ohlcv(n=5)
    dataset = build_dataset(df, horizon=6)
    assert len(dataset) == 0

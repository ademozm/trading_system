"""
Katman 3b — Model Eğitimi (Walk-Forward Validasyonlu)
=========================================================
Kullanım:
    python -m signals.ml.train --data data/ohlcv/BTC_USDT_1h.parquet \
        --symbol BTC/USDT --timeframe 1h --horizon 6 \
        --up-threshold 0.005 --down-threshold -0.005

Çıktı:
    signals/ml/models/BTC_USDT_1h.joblib  (model + metadata sözlüğü)

KRİTİK — Neden walk-forward, neden train_test_split DEĞİL:
    Zaman serisi verisinde rastgele train/test bölmesi (scikit-learn'ün
    varsayılan `train_test_split(shuffle=True)`), gelecekteki barların
    eğitim setine sızmasına (veri sızıntısı) yol açar — bu, gerçekte
    olmayan bir performans yanılsaması yaratır. Bunun yerine veri ZAMAN
    SIRASINA göre bölünür: ilk %(1-test_fraction)'ı eğitim, son
    %test_fraction'ı test.

    Bu basit bir tek-bölmeli walk-forward'dır (train/test). Daha sağlam
    bir değerlendirme için ileride "genişleyen pencere" (expanding window)
    ile çoklu-bölme walk-forward'a geçirilebilir — bu script o yapıya
    kolayca genişletilebilecek şekilde yazıldı (bkz. `_time_ordered_split`).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.metrics import classification_report

from signals.ml.features import FEATURE_COLUMNS, build_dataset

try:
    from lightgbm import LGBMClassifier
except ImportError:  # pragma: no cover
    LGBMClassifier = None


def _time_ordered_split(df: pd.DataFrame, test_fraction: float) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Veriyi ZAMAN SIRASINA göre böler (shuffle YOK)."""
    split_idx = int(len(df) * (1 - test_fraction))
    return df.iloc[:split_idx], df.iloc[split_idx:]


def train(
    data_path: str,
    symbol: str,
    timeframe: str,
    horizon: int,
    up_threshold: float,
    down_threshold: float,
    test_fraction: float,
    out_dir: str,
) -> Path:
    if LGBMClassifier is None:
        raise ImportError("lightgbm kurulu değil: `pip install lightgbm`")

    print(f"[train] Veri okunuyor: {data_path}")
    raw = pd.read_parquet(data_path)

    dataset = build_dataset(raw, horizon, up_threshold, down_threshold)
    print(f"[train] Özellik/etiket seti hazır: {len(dataset)} satır "
          f"(ısınma dönemi + etiket ufku için satırlar zaten temizlendi)")

    train_df, test_df = _time_ordered_split(dataset, test_fraction)
    print(f"[train] Eğitim: {len(train_df)} satır | Test (zaman içinde SONRAKİ): {len(test_df)} satır")

    label_counts = dataset["label"].value_counts().to_dict()
    print(f"[train] Etiket dağılımı (tüm veri): {label_counts}")
    if len(label_counts) < 2:
        raise ValueError(
            "Etiketlerin tamamı tek bir sınıfa düşüyor — up_threshold/down_threshold "
            "değerlerini gözden geçirin (muhtemelen çok yüksek/düşük)."
        )

    X_train, y_train = train_df[FEATURE_COLUMNS], train_df["label"].astype(int)
    X_test, y_test = test_df[FEATURE_COLUMNS], test_df["label"].astype(int)

    model = LGBMClassifier(
        n_estimators=200,
        max_depth=5,
        learning_rate=0.05,
        objective="multiclass",
        num_class=3,
        class_weight="balanced",  # sınıflar dengesiz olabilir (çoğunlukla "0")
        random_state=42,
        verbose=-1,  # "No further splits with positive gain" gibi binlerce
                     # satırlık iç log gürültüsünü susturur — bu sınıfların
                     # zayıf ayrılabilirliğinin normal bir belirtisidir, hata
                     # değil, ama okunabilirliği bozuyor.
    )

    # LightGBM sınıf etiketlerinin 0..num_class-1 olmasını bekler;
    # bizim etiketlerimiz -1/0/1 olduğu için bir eşleme gerekiyor.
    label_map = {-1: 0, 0: 1, 1: 2}
    inverse_label_map = {v: k for k, v in label_map.items()}
    y_train_mapped = y_train.map(label_map)
    y_test_mapped = y_test.map(label_map)

    model.fit(X_train, y_train_mapped)

    preds_mapped = model.predict(X_test)
    print("\n[train] Walk-forward TEST seti performansı (görülmemiş, gelecekteki veri):")
    print(
        classification_report(
            y_test_mapped, preds_mapped,
            target_names=["short(-1)", "flat(0)", "long(1)"],
            zero_division=0,
        )
    )
    print(
        "[UYARI] Bu rapor sadece TEK bir walk-forward bölmesine dayanıyor. "
        "Gerçek dağıtım kararı vermeden önce birden fazla zaman penceresinde "
        "(genişleyen pencere walk-forward) ve/veya Monte Carlo ile doğrulayın."
    )

    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    safe_symbol = symbol.replace("/", "_")
    model_file = out_path / f"{safe_symbol}_{timeframe}.joblib"

    metadata = {
        "symbol": symbol,
        "timeframe": timeframe,
        "horizon": horizon,
        "up_threshold": up_threshold,
        "down_threshold": down_threshold,
        "feature_columns": FEATURE_COLUMNS,
        "label_map": label_map,
        "inverse_label_map": inverse_label_map,
        "trained_rows": len(train_df),
        "test_rows": len(test_df),
    }

    joblib.dump({"model": model, "metadata": metadata}, model_file)
    print(f"\n[train] Model kaydedildi -> {model_file}")

    # Metadata'yı ayrıca okunabilir bir JSON olarak da yaz (hızlı incelemek için)
    with open(out_path / f"{safe_symbol}_{timeframe}_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    return model_file


def main() -> None:
    parser = argparse.ArgumentParser(description="ML sinyal modelini walk-forward ile eğit")
    parser.add_argument("--data", required=True, help="Parquet OHLCV dosya yolu")
    parser.add_argument("--symbol", required=True, help="ör. BTC/USDT")
    parser.add_argument("--timeframe", required=True, help="ör. 1h")
    parser.add_argument("--horizon", type=int, default=6, help="kaç bar sonrasına bakılacak")
    parser.add_argument("--up-threshold", type=float, default=0.005)
    parser.add_argument("--down-threshold", type=float, default=-0.005)
    parser.add_argument("--test-fraction", type=float, default=0.2)
    parser.add_argument("--out-dir", default="signals/ml/models")
    args = parser.parse_args()

    train(
        data_path=args.data,
        symbol=args.symbol,
        timeframe=args.timeframe,
        horizon=args.horizon,
        up_threshold=args.up_threshold,
        down_threshold=args.down_threshold,
        test_fraction=args.test_fraction,
        out_dir=args.out_dir,
    )


if __name__ == "__main__":
    main()

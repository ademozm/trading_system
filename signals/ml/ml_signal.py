"""
Katman 3b — ML Sinyali (Faz 3 TAMAMLANDI)
=============================================
signals/ml/train.py ile eğitilmiş bir modeli yükler, data_layer.storage
üzerinden en güncel veriyi çeker, özellik mühendisliğini uygular ve
sinyal toplayıcının (signals/aggregator.py) beklediği RawSignal formatında
bir tahmin üretir.

Kullanmadan önce: `python -m signals.ml.train --data ... --symbol ... --timeframe ...`
ile o sembol/timeframe için bir model eğitilmiş olmalı.

Tasarım kararı — model bulunamazsa ne olur:
    Sessizce hata fırlatıp tüm main.py döngüsünü durdurmak yerine, bu
    modül log uyarısı verip None döndürür. Böylece bir sembol için model
    henüz eğitilmemişse bile sistem diğer sinyal kaynaklarıyla (klasik/
    LLM) çalışmaya devam edebilir — sinyal toplayıcı zaten eksik
    kaynakları tolere edecek şekilde tasarlandı (bkz. aggregator.py).
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional

import joblib

from data_layer.storage import OHLCVStore
from signals.aggregator import RawSignal
from signals.ml.features import build_features

logger = logging.getLogger(__name__)

# Modelin en olası sınıfa verdiği olasılık bu eşiğin altındaysa sinyal
# üretilmez — "belirsizse işlem yapma" ilkesi burada da geçerli.
MIN_PREDICTION_CONFIDENCE = 0.45


class MLSignalGenerator:
    def __init__(self, model_dir: str = "signals/ml/models", ohlcv_dir: str = "data/ohlcv") -> None:
        self.model_dir = Path(model_dir)
        self.store = OHLCVStore(data_dir=ohlcv_dir)
        self._cache: dict[str, dict] = {}  # "{symbol}_{timeframe}" -> {"model":..., "metadata":...}

    def _load_model(self, symbol: str, timeframe: str) -> Optional[dict]:
        cache_key = f"{symbol}_{timeframe}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        safe_symbol = symbol.replace("/", "_")
        model_path = self.model_dir / f"{safe_symbol}_{timeframe}.joblib"
        if not model_path.exists():
            logger.warning(
                "%s / %s için eğitilmiş ML modeli bulunamadı (%s). "
                "Önce `python -m signals.ml.train` ile eğitin. Bu sembol için "
                "ML sinyali atlanacak.",
                symbol, timeframe, model_path,
            )
            return None

        bundle = joblib.load(model_path)
        self._cache[cache_key] = bundle
        return bundle

    def predict(self, symbol: str, timeframe: str = "1h", lookback_bars: int = 200) -> Optional[RawSignal]:
        """
        Son `lookback_bars` bar üzerinden özellik hesaplayıp en güncel
        (son) satır için bir tahmin üretir. `lookback_bars`, rolling
        özelliklerin (ör. volatility_24) ısınma dönemini karşılamak için
        yeterince büyük olmalıdır (varsayılan 200, çoğu özellik için
        fazlasıyla yeterli).
        """
        bundle = self._load_model(symbol, timeframe)
        if bundle is None:
            return None

        model = bundle["model"]
        metadata = bundle["metadata"]
        feature_columns = metadata["feature_columns"]
        inverse_label_map = metadata["inverse_label_map"]

        try:
            recent = self.store.load(symbol, timeframe)
        except FileNotFoundError:
            logger.warning("%s / %s için OHLCV verisi bulunamadı, ML sinyali atlanıyor.", symbol, timeframe)
            return None

        if len(recent) < lookback_bars:
            logger.warning(
                "%s / %s için yeterli geçmiş veri yok (%d satır, %d gerekli), "
                "ML sinyali atlanıyor.", symbol, timeframe, len(recent), lookback_bars,
            )
            return None

        recent = recent.tail(lookback_bars).reset_index(drop=True)
        featured = build_features(recent)
        latest_row = featured.iloc[[-1]][feature_columns]

        if latest_row.isna().any(axis=None):
            logger.warning(
                "%s / %s son satırda NaN özellik var (yetersiz ısınma dönemi), "
                "ML sinyali atlanıyor.", symbol, timeframe,
            )
            return None

        # LightGBM sınıf indeksleri 0/1/2 -> gerçek anlam -1/0/1'e geri çevrilir
        # (bkz. train.py'deki label_map/inverse_label_map).
        proba = model.predict_proba(latest_row)[0]
        best_class_idx = int(proba.argmax())
        best_confidence = float(proba[best_class_idx])
        predicted_label = inverse_label_map[best_class_idx]

        if best_confidence < MIN_PREDICTION_CONFIDENCE or predicted_label == 0:
            return None

        side = "long" if predicted_label == 1 else "short"

        return RawSignal(
            source="ml_gbm",
            symbol=symbol,
            side=side,
            confidence=round(best_confidence, 4),
            rationale=(
                f"LightGBM modeli {metadata['horizon']} bar ufkunda "
                f"%{best_confidence * 100:.1f} olasılıkla '{side}' hareketi öngörüyor "
                f"(model: {metadata['trained_rows']} bar ile eğitildi)."
            ),
        )

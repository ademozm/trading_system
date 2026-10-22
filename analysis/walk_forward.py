"""
Walk-forward parametre optimizasyonu.

SORUN: Bir stratejinin parametrelerini (ADX eşiği, RSI seviyeleri, ATR
çarpanları gibi) tüm geçmiş veri üzerinde optimize edip "en iyi" değerleri
bulmak, klasik bir overfitting (veriye ezberleme) tuzağıdır — o parametreler
sadece o spesifik geçmiş dönemde iyi çalışmış olabilir, gelecekte hiç işe
yaramayabilir.

ÇÖZÜM (walk-forward): Veri, sırayla ilerleyen pencerelere bölünür. Her
pencerede:
  1. Parametreler SADECE "eğitim" (train) bölümünde optimize edilir.
  2. En iyi parametreler, o eğitim penceresinin HİÇ GÖRMEDİĞİ bir sonraki
     "test" (out-of-sample) bölümünde değerlendirilir.
  3. Pencere ileri kaydırılır, tekrarlanır.

Sonuçta, "gerçekten hiç görülmemiş veride" ortalama bir performans elde
edilir — bu, tek seferlik bir optimizasyondan çok daha güvenilir bir
gösterge. Yine de gelecekteki performansın garantisi DEĞİLDİR; sadece
overfitting riskini azaltan bir metodolojidir.

Hesaplama maliyeti not: Pencere sayısı × parametre kombinasyonu sayısı
kadar backtest çalıştırılır. Büyük ızgaralarda (grid) yavaş olabilir —
varsayılan ızgara bilinçli olarak küçük tutuldu.
"""
import itertools
import logging

import numpy as np
import pandas as pd

from analysis.backtest import Backtester
from analysis.strategy import RegimeAdaptiveStrategy

logger = logging.getLogger("walk_forward")

DEFAULT_PARAM_GRID = {
    "adx_threshold": [18.0, 22.0, 26.0],
    "rsi_oversold": [25.0, 30.0],
    "rsi_overbought": [70.0, 75.0],
    "atr_stop_mult": [1.5, 2.0, 2.5],
    "atr_target_mult": [2.5, 3.0, 3.5],
}


def generate_windows(df: pd.DataFrame, train_days: int, test_days: int, step_days: int) -> list[dict]:
    """
    Rolling (kayan) pencereler üretir. Her pencere {"train": df, "test": df}.
    Veri yetersizse boş liste döner (hata fırlatmaz).
    """
    windows = []
    start = 0
    while start + train_days + test_days <= len(df):
        train_df = df.iloc[start: start + train_days]
        test_df = df.iloc[start + train_days: start + train_days + test_days]
        windows.append({"train": train_df, "test": test_df})
        start += step_days
    return windows


def _param_combinations(param_grid: dict) -> list[dict]:
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    return [dict(zip(keys, combo)) for combo in itertools.product(*values)]


def _evaluate_params(price_df: pd.DataFrame, params: dict) -> dict:
    """Verilen parametrelerle sinyal üretip backtest eder, metrikleri döner."""
    strategy = RegimeAdaptiveStrategy(
        adx_threshold=params.get("adx_threshold", 22.0),
        rsi_oversold=params.get("rsi_oversold", 30.0),
        rsi_overbought=params.get("rsi_overbought", 70.0),
        atr_stop_mult=params.get("atr_stop_mult", 2.0),
        atr_target_mult=params.get("atr_target_mult", 3.0),
    )
    signals_df = strategy.generate_signals(price_df)
    result = Backtester().run(signals_df)
    return result.metrics


def _score(metrics: dict) -> float:
    """Parametre seçimi için tek bir sayıya indirger. Sharpe'ı esas alır,
    işlem sayısı çok azsa (istatistiksel olarak güvenilmez) cezalandırır."""
    if metrics.get("trade_count", 0) < 3:
        return -999.0
    return metrics.get("sharpe_ratio", -999.0)


def optimize_window(train_df: pd.DataFrame, param_grid: dict) -> tuple[dict, dict]:
    """Bir eğitim penceresinde ızgara araması yapar. Dönüş: (en_iyi_params, en_iyi_metrikler)."""
    best_params, best_metrics, best_score = None, None, -np.inf
    for params in _param_combinations(param_grid):
        try:
            metrics = _evaluate_params(train_df, params)
        except Exception as e:
            logger.debug(f"Parametre kombinasyonu başarısız {params}: {e}")
            continue
        score = _score(metrics)
        if score > best_score:
            best_score, best_params, best_metrics = score, params, metrics

    return best_params, best_metrics


def run_walk_forward(
    df: pd.DataFrame,
    param_grid: dict = None,
    train_days: int = 252,
    test_days: int = 63,
    step_days: int = 63,
) -> dict:
    """
    Dönüş: {
        "window_results": pd.DataFrame (her pencere için train/test skorları + seçilen parametreler),
        "recommended_params": dict (pencereler arasında en sık/medyan seçilen parametreler),
        "overfitting_warning": bool,
        "summary": dict (ortalama out-of-sample Sharpe, tutarlılık oranı vb.)
    }
    """
    param_grid = param_grid or DEFAULT_PARAM_GRID
    windows = generate_windows(df, train_days, test_days, step_days)

    if not windows:
        return {
            "window_results": pd.DataFrame(),
            "recommended_params": {},
            "overfitting_warning": False,
            "summary": {"not": "Yetersiz veri: en az train_days + test_days kadar mum gerekli."},
        }

    rows = []
    for i, window in enumerate(windows):
        best_params, train_metrics = optimize_window(window["train"], param_grid)
        if best_params is None:
            continue

        test_metrics = _evaluate_params(window["test"], best_params)

        rows.append({
            "pencere": i + 1,
            "train_baslangic": window["train"].index[0], "train_bitis": window["train"].index[-1],
            "test_baslangic": window["test"].index[0], "test_bitis": window["test"].index[-1],
            **{f"param_{k}": v for k, v in best_params.items()},
            "train_sharpe": train_metrics.get("sharpe_ratio", 0),
            "train_islem_sayisi": train_metrics.get("trade_count", 0),
            "test_sharpe": test_metrics.get("sharpe_ratio", 0),
            "test_getiri_pct": test_metrics.get("total_return_pct", 0),
            "test_islem_sayisi": test_metrics.get("trade_count", 0),
        })

    window_results = pd.DataFrame(rows)
    if window_results.empty:
        return {
            "window_results": window_results,
            "recommended_params": {},
            "overfitting_warning": False,
            "summary": {"not": "Hiçbir pencerede yeterli işlem sayısına ulaşan parametre bulunamadı."},
        }

    # Önerilen parametreler: her parametre için pencereler arası MEDYAN
    # (en sık/istikrarlı seçilen değer, tek bir pencereye aşırı bağımlı olmamak için)
    recommended_params = {}
    for col in window_results.columns:
        if col.startswith("param_"):
            recommended_params[col.replace("param_", "")] = float(window_results[col].median())

    avg_train_sharpe = window_results["train_sharpe"].mean()
    avg_test_sharpe = window_results["test_sharpe"].mean()
    consistency_pct = (window_results["test_getiri_pct"] > 0).mean() * 100

    # Overfitting uyarısı: eğitimde çok iyi, testte çok kötü performans klasik bir işarettir
    overfitting_warning = bool(avg_train_sharpe > 0 and avg_test_sharpe < avg_train_sharpe * 0.3)

    summary = {
        "pencere_sayisi": len(window_results),
        "ort_egitim_sharpe": round(avg_train_sharpe, 2),
        "ort_test_sharpe": round(avg_test_sharpe, 2),
        "tutarlilik_pct": round(consistency_pct, 1),
        "aciklama": "Tutarlılık %, pencerelerin kaçında test döneminde pozitif getiri elde edildiğini gösterir.",
    }

    return {
        "window_results": window_results,
        "recommended_params": recommended_params,
        "overfitting_warning": overfitting_warning,
        "summary": summary,
    }

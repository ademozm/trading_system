"""
Bileşik skorlama motoru v2.

v1'den fark: artık sadece teknik göstergeler değil, temel analiz
(P/E, ROE, borç, büyüme), göreceli güç (endekse karşı performans),
hacim teyidi ve haftalık trend teyidi de skora dahil ediliyor.

Farklı piyasalardaki (BIST hissesi, ABD hissesi, kripto) sinyalleri
doğrudan karşılaştırmak anlamsız olurdu (farklı volatilite rejimleri,
farklı birimler, kriptoda temel analiz kavramı yok). Bunun için:
  1. Her metrik evren içinde yüzdelik dilime (percentile) çevrilir.
  2. Bir sembolde bir bileşen eksikse (örn. kriptoda fundamental_score
     yok), o bileşen o sembol için hesaba katılmaz ve kalan ağırlıklar
     yeniden normalize edilir (toplamı yine 1 olacak şekilde).
  3. Nihai skor sinyal yönüyle (+1/-1) çarpılır: -1 (güçlü sat) ile
     +1 (güçlü al) arasında tek bir sayı.
"""
import numpy as np
import pandas as pd

import config


def _score_technical(df: pd.DataFrame, adx_threshold: float = 22.0) -> dict:
    last = df.iloc[-1]
    signal = int(last["signal"])
    if signal == 0:
        return None

    if last["regime"] == "trend":
        signal_strength = np.clip((last["adx"] - adx_threshold) / 30, 0, 1)
    else:
        signal_strength = np.clip(abs(last["rsi"] - 50) / 50, 0, 1)

    lookback = config.MOMENTUM_LOOKBACK_DAYS
    momentum_return = (last["Close"] / df["Close"].iloc[-lookback - 1] - 1) if len(df) > lookback else 0.0
    momentum_aligned = momentum_return * signal

    stop_dist, target_dist = last["stop_dist"], last["target_dist"]
    risk_reward = target_dist / stop_dist if stop_dist > 0 else 0
    atr_pct = last["atr"] / last["Close"] if last["Close"] > 0 else 0

    return {
        "signal": signal, "regime": last["regime"],
        "signal_strength": signal_strength,
        "momentum_return_pct": momentum_return * 100,
        "momentum_aligned": momentum_aligned,
        "risk_reward": risk_reward, "atr_pct": atr_pct * 100,
        "close": last["Close"], "adx": last["adx"], "rsi": last["rsi"],
    }


def _percentile(series: pd.Series, higher_is_better: bool = True) -> pd.Series:
    pct = series.rank(pct=True, na_option="keep")
    return pct if higher_is_better else 1 - pct


def full_universe_status(signals_by_symbol: dict, universe_df: pd.DataFrame, adx_threshold: float = 22.0) -> pd.DataFrame:
    """
    score_universe() SADECE sinyal üreten sembolleri (signal != 0) döner —
    bu bilinçli bir tasarımdır (rapor kalabalıklaşmasın diye). Ama bu,
    "emtia/kripto sayfası boş/az görünüyor" gibi kafa karışıklığına yol
    açabilir: aslında TÜM semboller tarandı, sadece o gün çoğu net bir
    AL/SAT eşiğini geçmedi.

    Bu fonksiyon, TARANAN HER SEMBOLÜN durumunu (sinyal olsun olmasın)
    döner — şeffaflık için. "Neden sinyal yok" sorusuna da kaba bir
    açıklama üretir.
    """
    rows = []
    for symbol, df in signals_by_symbol.items():
        try:
            last = df.iloc[-1]
        except Exception:
            continue

        signal = int(last.get("signal", 0))
        regime = last.get("regime", "?")
        adx = last.get("adx", np.nan)
        rsi = last.get("rsi", np.nan)

        if signal != 0:
            neden = "Sinyal üretti"
        elif regime == "trend" and pd.notna(adx) and adx <= adx_threshold:
            neden = f"Trend zayıf (ADX {adx:.1f} ≤ eşik {adx_threshold:.0f})"
        elif regime == "range" and pd.notna(rsi) and 30 < rsi < 70:
            neden = f"RSI nötr bölgede ({rsi:.1f}, aşırı alım/satım yok)"
        else:
            neden = "Net bir eşiği geçmedi"

        rows.append({
            "symbol": symbol, "regime": regime, "signal": signal,
            "close": last.get("Close"), "adx": adx, "rsi": rsi,
            "sinyal_var_mi": signal != 0, "neden": neden,
        })

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = result.merge(universe_df[["symbol", "market", "name"]], on="symbol", how="left")
    return result.sort_values(["market", "sinyal_var_mi"], ascending=[True, False]).reset_index(drop=True)


def score_universe(
    signals_by_symbol: dict,
    universe_df: pd.DataFrame,
    fundamentals_df: pd.DataFrame | None = None,
    relative_strength_df: pd.DataFrame | None = None,
    confirmations_by_symbol: dict | None = None,
    risk_metrics_by_symbol: dict | None = None,
    news_by_symbol: dict | None = None,
) -> pd.DataFrame:
    """
    Ek parametrelerin hepsi OPSİYONELDİR — hiçbiri verilmezse sistem eski
    (sadece teknik) davranışa geri döner. Bu, geriye dönük uyumluluğu ve
    "fundamentals çok yavaş, şimdilik atla" gibi kısmi çalıştırmaları
    mümkün kılar.
    """
    rows = []
    for symbol, df in signals_by_symbol.items():
        try:
            metrics = _score_technical(df)
        except Exception:
            metrics = None
        if metrics is None:
            continue
        metrics["symbol"] = symbol
        rows.append(metrics)

    if not rows:
        return pd.DataFrame()

    result = pd.DataFrame(rows)
    result = result.merge(universe_df[["symbol", "market", "name"]], on="symbol", how="left")

    # --- Teknik bileşenler (her zaman mevcut) ---
    result["momentum_pctile"] = _percentile(result["momentum_aligned"])
    result["risk_reward_norm"] = (result["risk_reward"] / result["risk_reward"].max()).clip(0, 1) \
        if result["risk_reward"].max() > 0 else 0
    result["volatility_penalty_score"] = 1 - (result["atr_pct"] / result["atr_pct"].max()).clip(0, 1) \
        if result["atr_pct"].max() > 0 else 1

    score_components = {
        "signal_strength": result["signal_strength"],
        "momentum": result["momentum_pctile"],
        "risk_reward": result["risk_reward_norm"],
        "volatility_penalty": result["volatility_penalty_score"],
    }

    # --- Temel analiz (opsiyonel, kriptoda NaN) ---
    if fundamentals_df is not None and not fundamentals_df.empty:
        result = result.merge(fundamentals_df, on="symbol", how="left")
        score_components["fundamental"] = result["fundamental_score"]

    # --- Göreceli güç (opsiyonel) ---
    if relative_strength_df is not None and not relative_strength_df.empty:
        result = result.merge(relative_strength_df, on="symbol", how="left")
        score_components["relative_strength"] = _percentile(result["relative_strength_pct"])

    # --- Hacim / haftalık teyit (opsiyonel) ---
    if confirmations_by_symbol:
        conf_df = pd.DataFrame([{"symbol": s, **c} for s, c in confirmations_by_symbol.items()])
        result = result.merge(conf_df, on="symbol", how="left")
        if "volume_confirmed" in result.columns:
            score_components["volume_confirmation"] = result["volume_confirmed"].map(
                {True: 1.0, False: 0.0}
            )
        if "mtf_confirmed" in result.columns:
            score_components["mtf_confirmation"] = result["mtf_confirmed"].map(
                {True: 1.0, False: 0.0}
            )

    # --- Risk metrikleri (rapora eklenir, skora doğrudan girmez ama bağlam sağlar) ---
    if risk_metrics_by_symbol:
        risk_df = pd.DataFrame([{"symbol": s, **r} for s, r in risk_metrics_by_symbol.items()])
        result = result.merge(risk_df, on="symbol", how="left")

    # --- Haber tonu (opsiyonel, kaba anahtar-kelime tabanlı sezgisel skor) ---
    if news_by_symbol:
        news_df = pd.DataFrame([{"symbol": s, **n} for s, n in news_by_symbol.items()])
        result = result.merge(news_df, on="symbol", how="left")
        if "news_sentiment" in result.columns:
            # Sentiment -1..1 aralığında; sinyal yönüyle çarpılmadan önce 0..1'e ölçekle
            # (pozitif sentiment AL sinyalini, negatif sentiment SAT sinyalini güçlendirir)
            aligned_sentiment = result["news_sentiment"] * result["signal"]
            score_components["news_sentiment"] = ((aligned_sentiment + 1) / 2).clip(0, 1)

    # --- Dinamik ağırlıklı ortalama: eksik bileşenler ağırlık dışı bırakılıp
    #     kalanlar yeniden normalize edilir (satır bazında) ---
    weights = config.SCORE_WEIGHTS
    weight_matrix = pd.DataFrame({k: v for k, v in score_components.items()})
    weight_values = pd.Series({k: weights.get(k, 0) for k in score_components})

    valid_mask = weight_matrix.notna()
    weighted_sum = (weight_matrix.fillna(0) * weight_values).sum(axis=1)
    active_weight_sum = (valid_mask * weight_values).sum(axis=1)

    normalized_score = np.where(active_weight_sum > 0, weighted_sum / active_weight_sum, 0)
    result["composite_score"] = normalized_score * result["signal"]

    result = result.sort_values("composite_score", ascending=False).reset_index(drop=True)
    return result

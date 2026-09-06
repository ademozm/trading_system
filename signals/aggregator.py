"""
Katman 3e — Sinyal Toplayıcı (Ensemble / Aggregator)
=======================================================
3a (klasik), 3b (ML) ve 3c (LLM ajan) modüllerinden gelen sinyalleri
tek bir "aday işlem" (CandidateTrade) haline getirir. Bu modül,
risk/risk_manager.py'nin beklediği CandidateTrade nesnesini üretir.

Başlangıç stratejisi: ağırlıklı ortalama + basit çoğunluk oyu.
İleri seviye (Faz 3-4 sonrası): sinyallerin geçmiş doğruluğuna göre
ağırlıkları otomatik öğrenen bir meta-model (ör. lojistik regresyon)
buraya eklenebilir.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Literal

from risk.risk_manager import CandidateTrade

Side = Literal["long", "short", "flat"]


@dataclass
class RawSignal:
    """Tek bir alt-modülden (3a/3b/3c) gelen ham sinyal."""

    source: str  # "classic_sma" | "ml_gbm" | "llm_agents" ...
    symbol: str
    side: Side
    confidence: float  # 0.0 - 1.0
    rationale: str = ""


@dataclass
class AggregatorConfig:
    # Her kaynağa verilecek ağırlık; toplamı 1.0 olmak zorunda değil,
    # sadece göreceli önemi belirler.
    weights: dict = field(
        default_factory=lambda: {
            "classic_sma": 1.0,
            "ml_gbm": 1.0,
            "llm_agents": 1.0,
        }
    )
    # Ağırlıklı skor bu eşiğin altındaysa hiç aday işlem üretilmez
    # (belirsiz/çelişkili sinyalde işlem YAPMAMAK varsayılan davranıştır).
    min_score_threshold: float = 0.3


def infer_asset_class(symbol: str) -> str:
    """
    Sembol formatından varlık sınıfını çıkarır: ccxt formatı "/" içerir
    (ör. "BTC/USDT") -> kripto; Alpaca formatı içermez (ör. "AAPL") -> hisse.

    Bu basit bir kalp — forex (ör. "EUR/USD") de "/" içerdiği için şu an
    "crypto" olarak sınıflandırılır. Forex eklenirse bu fonksiyon
    genişletilmeli (ör. sembol evrenini ayrı bir YAML alanında etiketlemek
    daha sağlam bir çözüm olur). Şimdilik mandate.yaml'daki
    `per_asset_class` override'ları kripto/hisse ayrımı için yeterli.
    """
    return "crypto" if "/" in symbol else "equity"


class SignalAggregator:
    def __init__(self, config: AggregatorConfig | None = None) -> None:
        self.config = config or AggregatorConfig()

    def aggregate(self, signals: List[RawSignal], asset_class: str | None = None) -> CandidateTrade | None:
        """
        Aynı sembol için gelen birden çok sinyali birleştirir.
        Farklı semboller için ayrı ayrı çağrılmalıdır.

        `asset_class` verilmezse sembol formatından otomatik çıkarılır
        (bkz. infer_asset_class) — main.py artık tüm sembolleri "crypto"
        olarak sabitlemek zorunda değil.
        """
        if not signals:
            return None

        symbols = {s.symbol for s in signals}
        if len(symbols) != 1:
            raise ValueError(
                "aggregate() tek seferde tek bir sembol için sinyalleri "
                "birleştirir; farklı semboller için ayrı çağırın."
            )
        symbol = symbols.pop()
        resolved_asset_class = asset_class or infer_asset_class(symbol)

        # Yön bazında ağırlıklı skor topla
        side_scores: dict[Side, float] = {"long": 0.0, "short": 0.0, "flat": 0.0}
        rationales: list[str] = []
        total_weight = 0.0

        for sig in signals:
            weight = self.config.weights.get(sig.source, 1.0)
            side_scores[sig.side] += weight * sig.confidence
            total_weight += weight
            if sig.rationale:
                rationales.append(f"[{sig.source}] {sig.rationale}")

        if total_weight == 0:
            return None

        # Normalize et
        for side in side_scores:
            side_scores[side] /= total_weight

        best_side, best_score = max(side_scores.items(), key=lambda kv: kv[1])

        if best_side == "flat" or best_score < self.config.min_score_threshold:
            return None

        combined_rationale = " | ".join(rationales) if rationales else "Gerekçe sağlanmadı"

        return CandidateTrade(
            symbol=symbol,
            side=best_side,
            asset_class=resolved_asset_class,
            confidence=round(best_score, 4),
            rationale=combined_rationale,
        )

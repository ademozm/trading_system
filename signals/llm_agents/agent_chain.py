"""
Katman 3c — LLM Ajan Zinciri (Faz 4 TAMAMLANDI)
====================================================
İlham: TradingAgents'ın analist -> boğa/ayı araştırmacı tartışması ->
trader zinciri; Vibe-Trading'in çoklu LLM sağlayıcı esnekliği;
karar günlüğünden (Katman 7) geçmiş performansı "hafıza" olarak
enjekte etme fikri.

Akış (varsayılan: basit sıralı yürütücü, LangGraph GEREKMEZ):
    technical_analyst -> news_analyst -> bull_researcher -> bear_researcher
    -> trader -> RawSignal

İsteğe bağlı: `use_langgraph=True` ile aynı düğümler bir LangGraph
StateGraph'ı içinde çalıştırılabilir (checkpoint/resume desteği için) —
bkz. `_build_langgraph_app`. Bu, `langgraph` kurulu olmasını gerektirir;
kurulu değilse açıkça bir hata verir (sessizce sıralı yürütücüye
düşmez — hangi modun çalıştığı her zaman net olmalı).

KRİTİK GÜVENLİK NOTU: Bu modülün ürettiği RawSignal, HER ZAMAN
signals.aggregator.SignalAggregator üzerinden diğer sinyallerle
birleştirilir ve ardından risk.risk_manager.RiskManager.check()'ten
geçer. Bu modül asla doğrudan execution'a bağlanmamalıdır.
"""

from __future__ import annotations

import logging
from typing import Optional

from data_layer.storage import OHLCVStore
from monitoring.decision_log import DecisionLog
from signals.aggregator import RawSignal
from signals.llm_agents.llm_client import LLMClient, MockLLMClient
from signals.llm_agents.nodes import (
    bear_researcher_node,
    bull_researcher_node,
    news_analyst_node,
    technical_analyst_node,
    trader_node,
)
from signals.llm_agents.state import AgentState
from signals.ml.features import build_features

logger = logging.getLogger(__name__)

MIN_TRADER_CONFIDENCE = 0.5


class LLMAgentChain:
    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        ohlcv_dir: str = "data/ohlcv",
        decision_log: Optional[DecisionLog] = None,
    ) -> None:
        """
        llm_client sağlanmazsa MockLLMClient kullanılır — bu, sistemin
        API anahtarı olmadan da (bariz şekilde sahte sinyallerle) uçtan
        uca çalışabilmesini sağlar. GERÇEK kullanımda mutlaka
        `build_llm_client("anthropic"/"openai", ...)` ile gerçek bir
        istemci geçirin (bkz. llm_client.py).
        """
        if llm_client is None:
            logger.warning(
                "LLMAgentChain gerçek bir llm_client olmadan başlatıldı — "
                "MockLLMClient kullanılacak. Bu SADECE geliştirme/test içindir, "
                "üretilen sinyaller gerçek değildir."
            )
        self.llm = llm_client or MockLLMClient()
        self.store = OHLCVStore(data_dir=ohlcv_dir)
        self.decision_log = decision_log or DecisionLog()

    def _compute_technical_stats(self, symbol: str, timeframe: str) -> Optional[dict]:
        try:
            recent = self.store.load(symbol, timeframe)
        except FileNotFoundError:
            logger.warning("%s / %s için OHLCV verisi yok, teknik istatistik hesaplanamıyor.", symbol, timeframe)
            return None

        if len(recent) < 30:
            logger.warning("%s / %s için yeterli veri yok (%d satır).", symbol, timeframe, len(recent))
            return None

        featured = build_features(recent.tail(200).reset_index(drop=True))
        last = featured.iloc[-1]
        return {
            "last_close": float(last["close"]),
            "return_1": float(last["return_1"]) if pd_notna(last["return_1"]) else 0.0,
            "return_12": float(last["return_12"]) if pd_notna(last["return_12"]) else 0.0,
            "volatility_24": float(last["volatility_24"]) if pd_notna(last["volatility_24"]) else None,
            "rsi_14": float(last["rsi_14"]) if pd_notna(last["rsi_14"]) else None,
            "sma_ratio_20": float(last["sma_ratio_20"]) if pd_notna(last["sma_ratio_20"]) else None,
        }

    def _build_history_summary(self, symbol: str) -> str:
        history = self.decision_log.recent_history_for_symbol(symbol, limit=5)
        if not history:
            return "Bu sembol için geçmiş kayıt yok."
        lines = []
        for record in history:
            pnl = record.get("realized_pnl_pct")
            pnl_str = f"%{pnl * 100:.2f}" if pnl is not None else "sonuç bilinmiyor"
            lines.append(f"- {record['created_at']}: {record['side']} -> {pnl_str}")
        return "\n".join(lines)

    def analyze(
        self, symbol: str, timeframe: str = "1h", news_text: Optional[str] = None
    ) -> Optional[RawSignal]:
        """
        Zinciri sıralı olarak çalıştırır ve nihai kararı RawSignal'a çevirir.
        Teknik veri yoksa veya trader 'flat'/düşük güven verirse None döner
        (belirsizse işlem yapma ilkesi).
        """
        technical_stats = self._compute_technical_stats(symbol, timeframe)
        if technical_stats is None:
            return None

        state: AgentState = {
            "symbol": symbol,
            "technical_stats": technical_stats,
            "news_text": news_text,
            "history_summary": self._build_history_summary(symbol),
        }

        state = technical_analyst_node(state, self.llm)
        state = news_analyst_node(state, self.llm)
        state = bull_researcher_node(state, self.llm)
        state = bear_researcher_node(state, self.llm)
        state = trader_node(state, self.llm)

        if state.get("error"):
            logger.warning("LLM ajan zinciri hata ile sonuçlandı: %s", state["error"])
            return None

        side = state.get("trader_side", "flat")
        confidence = state.get("trader_confidence", 0.0)

        if side == "flat" or confidence < MIN_TRADER_CONFIDENCE:
            return None

        return RawSignal(
            source="llm_agents",
            symbol=symbol,
            side=side,
            confidence=round(confidence, 4),
            rationale=state.get("trader_rationale", ""),
        )

    def _build_langgraph_app(self):
        """
        İsteğe bağlı: aynı düğümleri bir LangGraph StateGraph'ı içinde
        çalıştırmak isterseniz (ör. checkpoint/resume, adım adım izleme
        için) bu metodu kullanın. `analyze()` metodu buna bağımlı
        DEĞİLDİR — bu sadece ileri seviye bir alternatiftir.
        """
        try:
            from langgraph.graph import END, StateGraph
        except ImportError as e:
            raise ImportError(
                "langgraph kurulu değil: `pip install langgraph`. "
                "LangGraph olmadan da analyze() metoduyla zincir tam olarak çalışır; "
                "bu sadece opsiyonel bir orkestrasyon alternatifidir."
            ) from e

        graph = StateGraph(AgentState)
        graph.add_node("technical_analyst", lambda s: technical_analyst_node(s, self.llm))
        graph.add_node("news_analyst", lambda s: news_analyst_node(s, self.llm))
        graph.add_node("bull_researcher", lambda s: bull_researcher_node(s, self.llm))
        graph.add_node("bear_researcher", lambda s: bear_researcher_node(s, self.llm))
        graph.add_node("trader", lambda s: trader_node(s, self.llm))

        graph.set_entry_point("technical_analyst")
        graph.add_edge("technical_analyst", "news_analyst")
        graph.add_edge("news_analyst", "bull_researcher")
        graph.add_edge("bull_researcher", "bear_researcher")
        graph.add_edge("bear_researcher", "trader")
        graph.add_edge("trader", END)

        return graph.compile()


def pd_notna(value) -> bool:
    """pandas'a tekrar import bağımlılığı eklememek için minik yardımcı."""
    import pandas as pd

    return pd.notna(value)

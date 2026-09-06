"""
Katman 3c — Ajan Düğümleri (Nodes)
=====================================
Her fonksiyon: (state, llm_client) alır, state'in bir kısmını güncelleyip
döndürür. Bilerek LangGraph'a bağımlı DEĞİLDİR — bu sayede her düğüm
`MockLLMClient` ile, gerçek bir graf kurmadan, tek başına test edilebilir
(bkz. tests/test_llm_agents.py). agent_chain.py bu fonksiyonları hem
basit bir sıralı yürütücüde hem de (opsiyonel) bir LangGraph StateGraph
içinde kullanabilir.
"""

from __future__ import annotations

import json
import logging

from signals.llm_agents.llm_client import LLMClient
from signals.llm_agents.prompts import (
    news_analyst_prompt,
    researcher_prompt,
    technical_analyst_prompt,
    trader_prompt,
)
from signals.llm_agents.state import AgentState

logger = logging.getLogger(__name__)


def technical_analyst_node(state: AgentState, llm: LLMClient) -> AgentState:
    system, user = technical_analyst_prompt(state["symbol"], state.get("technical_stats", {}))
    report = llm.complete(system, user)
    return {**state, "technical_report": report}


def news_analyst_node(state: AgentState, llm: LLMClient) -> AgentState:
    system, user = news_analyst_prompt(state["symbol"], state.get("news_text"))
    report = llm.complete(system, user)
    return {**state, "news_report": report}


def bull_researcher_node(state: AgentState, llm: LLMClient) -> AgentState:
    system, user = researcher_prompt(
        "bull", state["symbol"], state.get("technical_report", ""), state.get("news_report", "")
    )
    argument = llm.complete(system, user)
    return {**state, "bull_argument": argument}


def bear_researcher_node(state: AgentState, llm: LLMClient) -> AgentState:
    system, user = researcher_prompt(
        "bear", state["symbol"], state.get("technical_report", ""), state.get("news_report", "")
    )
    argument = llm.complete(system, user)
    return {**state, "bear_argument": argument}


def trader_node(state: AgentState, llm: LLMClient) -> AgentState:
    system, user = trader_prompt(
        state["symbol"],
        state.get("bull_argument", ""),
        state.get("bear_argument", ""),
        state.get("history_summary", "Geçmiş kayıt yok."),
    )
    raw_response = llm.complete(system, user)

    parsed = _parse_trader_json(raw_response)
    if parsed is None:
        return {
            **state,
            "error": f"Trader yanıtı JSON olarak ayrıştırılamadı: {raw_response!r}",
            "trader_side": "flat",
            "trader_confidence": 0.0,
            "trader_rationale": "Ayrıştırma hatası nedeniyle işlem önerilmiyor.",
        }

    side = parsed.get("side", "flat")
    if side not in ("long", "short", "flat"):
        side = "flat"

    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))

    return {
        **state,
        "trader_side": side,
        "trader_confidence": confidence,
        "trader_rationale": str(parsed.get("rationale", "")),
    }


def _parse_trader_json(raw_response: str) -> dict | None:
    """
    LLM'ler bazen JSON'un etrafına ```json ... ``` gibi fence ekler veya
    ekstra metin ekler. Basit bir temizleme + parse denemesi yapılır;
    başarısız olursa None döner (sessizce yanlış bir karar UYDURULMAZ).
    """
    text = raw_response.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.lower().startswith("json"):
            text = text[4:]
        text = text.strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Son çare: metin içinde ilk '{' ile son '}' arasını dene
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                pass
        logger.warning("Trader JSON ayrıştırma başarısız oldu: %r", raw_response)
        return None

"""
tests/test_llm_agents.py
==========================
signals/llm_agents modülünün düğüm mantığını (nodes.py) ve JSON
ayrıştırmasını, GERÇEK bir LLM API'sine bağlanmadan MockLLMClient ile
test eder. Bu sayede zincirin "bağlantı mantığı" (bir düğümün çıktısının
bir sonrakine doğru aktarılması, hatalı JSON'un düzgün ele alınması)
API anahtarı veya internet olmadan doğrulanabilir.

Not: agent_chain.py'nin tamamı (LLMAgentChain sınıfı) data_layer.storage
üzerinden duckdb'ye bağımlıdır; duckdb kurulu değilse o testler
`pytest.importorskip` ile atlanır — ama nodes.py/llm_client.py testleri
HER ZAMAN çalışır (bu ortamda dahil).
"""

from __future__ import annotations

from signals.llm_agents.llm_client import MockLLMClient
from signals.llm_agents.nodes import (
    _parse_trader_json,
    bear_researcher_node,
    bull_researcher_node,
    news_analyst_node,
    technical_analyst_node,
    trader_node,
)
from signals.llm_agents.state import AgentState


def _base_state() -> AgentState:
    return {
        "symbol": "BTC/USDT",
        "technical_stats": {
            "last_close": 65000.0,
            "return_1": 0.001,
            "return_12": 0.02,
            "volatility_24": 0.015,
            "rsi_14": 62.0,
            "sma_ratio_20": 1.01,
        },
        "news_text": None,
        "history_summary": "Geçmiş kayıt yok.",
    }


def test_technical_analyst_node_fills_report() -> None:
    llm = MockLLMClient()
    state = technical_analyst_node(_base_state(), llm)
    assert "technical_report" in state
    assert len(state["technical_report"]) > 0
    # Prompt'un doğru istatistikleri içerdiğini doğrula (mock, prompt'u
    # yanıta yansıtmıyor ama en azından çağrının yapıldığını kontrol edelim)
    assert len(llm.call_log) == 1
    _, user_prompt = llm.call_log[0]
    assert "BTC/USDT" in user_prompt
    assert "65000" in user_prompt


def test_news_analyst_node_handles_missing_news() -> None:
    llm = MockLLMClient()
    state = news_analyst_node(_base_state(), llm)
    _, user_prompt = llm.call_log[0]
    assert "sağlanmadı" in user_prompt  # haber verilmediğinde dürüstçe belirtiliyor


def test_full_chain_produces_trader_decision() -> None:
    """Düğümleri sırayla elle bağlayarak, agent_chain.py'nin yaptığı gibi
    tam zinciri MockLLMClient ile test eder (duckdb'ye ihtiyaç duymadan)."""
    llm = MockLLMClient()
    state = _base_state()
    state = technical_analyst_node(state, llm)
    state = news_analyst_node(state, llm)
    state = bull_researcher_node(state, llm)
    state = bear_researcher_node(state, llm)
    state = trader_node(state, llm)

    assert state.get("error") is None
    assert state["trader_side"] in ("long", "short", "flat")
    assert 0.0 <= state["trader_confidence"] <= 1.0
    # MockLLMClient'ın varsayılan yanıtı side="long", confidence=0.55 döndürür
    assert state["trader_side"] == "long"
    assert state["trader_confidence"] == 0.55


def test_trader_node_handles_malformed_json_gracefully() -> None:
    llm = MockLLMClient(responder=lambda system, user: "bu JSON değil, düz metin")
    state = trader_node(_base_state(), llm)
    assert state["error"] is not None
    assert state["trader_side"] == "flat"
    assert state["trader_confidence"] == 0.0


def test_trader_node_extracts_json_from_markdown_fence() -> None:
    fenced = '```json\n{"side": "short", "confidence": 0.7, "rationale": "test"}\n```'
    llm = MockLLMClient(responder=lambda system, user: fenced)
    state = trader_node(_base_state(), llm)
    assert state.get("error") is None
    assert state["trader_side"] == "short"
    assert state["trader_confidence"] == 0.7


def test_trader_node_clamps_out_of_range_confidence() -> None:
    llm = MockLLMClient(
        responder=lambda s, u: '{"side": "long", "confidence": 1.7, "rationale": "aşırı güven"}'
    )
    state = trader_node(_base_state(), llm)
    assert state["trader_confidence"] == 1.0  # 0-1 aralığına kırpılmalı


def test_trader_node_rejects_invalid_side() -> None:
    llm = MockLLMClient(
        responder=lambda s, u: '{"side": "sideways", "confidence": 0.6, "rationale": "geçersiz yön"}'
    )
    state = trader_node(_base_state(), llm)
    assert state["trader_side"] == "flat"  # bilinmeyen yön güvenli varsayılana düşer


def test_parse_trader_json_direct() -> None:
    assert _parse_trader_json('{"side": "long"}') == {"side": "long"}
    assert _parse_trader_json("tamamen bozuk metin") is None
    assert _parse_trader_json('önce metin {"side": "short"} sonra metin') == {"side": "short"}

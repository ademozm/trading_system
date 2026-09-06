"""
Katman 3c — Ajan Zinciri State Şeması
========================================
Her düğüm (node) bu sözlüğün bir kısmını okuyup bir kısmını doldurur.
LangGraph kullanılırsa bu TypedDict doğrudan graf state'i olarak
kullanılabilir; kullanılmazsa (bkz. agent_chain.py'nin basit sıralı
yürütücüsü) sıradan bir dict olarak elden ele taşınır.
"""

from __future__ import annotations

from typing import Optional, TypedDict


class AgentState(TypedDict, total=False):
    symbol: str

    # Girdi bağlamı
    technical_stats: dict          # data_layer'dan hesaplanan sayısal özet
    news_text: Optional[str]        # dışarıdan sağlanan ham haber metni (varsa)
    history_summary: str            # decision_log'dan gelen geçmiş performans özeti

    # Ara çıktılar (her ajan kendi alanını doldurur)
    technical_report: str
    news_report: str
    bull_argument: str
    bear_argument: str

    # Nihai çıktı
    trader_side: str                # "long" | "short" | "flat"
    trader_confidence: float
    trader_rationale: str

    # Hata/uyarı takibi — bir düğüm başarısız olursa zinciri durdurmadan
    # burada işaretlenir; agent_chain.py bunu kontrol edip None döner.
    error: Optional[str]

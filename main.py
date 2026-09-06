"""
main.py — Uçtan Uca Akış (Katman 1-8'i Birbirine Bağlar)
============================================================
Bu dosya, tek bir sembol için tam döngüyü gösterir:

  Katman 3 (sinyal üret) -> Katman 3e (birleştir) -> Katman 4 (risk kontrolü)
  -> Katman 6/8 (Telegram onayı) -> Katman 6 (order router) -> Katman 7 (logla)

Şu an Faz 0-4 ve Faz 6 bileşenlerinin tamamı (klasik sinyal + ML sinyali +
LLM ajan zinciri + risk + log) gerçek çalışır. Katman 1 artık hem kripto
(ccxt) hem hisse senedi (Alpaca) sembollerini destekler — varlık sınıfı
sembol formatından otomatik çıkarılır (bkz. signals.aggregator.infer_asset_class).

ÇALIŞTIRMADAN ÖNCE:
  - config/mandate.yaml'ı gözden geçirin
  - TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID ortam değişkenlerini ayarlayın
  - Önce dry_run=True ile (varsayılan) test edin
"""

from __future__ import annotations

import asyncio
import logging
import os

from execution.order_router import OrderRouter
from execution.telegram_bot import ApprovalBot
from monitoring.decision_log import DecisionLog, DecisionRecord
from risk.mandate import load_mandate
from risk.risk_manager import ApprovedOrderDraft, RiskManager
from signals.aggregator import AggregatorConfig, RawSignal, SignalAggregator, infer_asset_class
from signals.llm_agents.agent_chain import LLMAgentChain
from signals.llm_agents.llm_client import build_llm_client
from signals.ml.ml_signal import MLSignalGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")


# NOT: Gerçek sistemde bu, backtest/run_backtest.py'nin çalıştırdığı
# SmaCrossStrategy'nin ürettiği son sinyalden veya canlı bir strateji
# runner'ından gelir. Burada akışı göstermek için elle bir RawSignal
# oluşturuyoruz.
def get_classic_signal_placeholder(symbol: str) -> RawSignal:
    return RawSignal(
        source="classic_sma",
        symbol=symbol,
        side="long",
        confidence=0.6,
        rationale="Kısa dönem SMA, uzun dönem SMA'yı yukarı kesti (altın kesişim).",
    )


async def process_symbol(
    symbol: str,
    timeframe: str,
    aggregator: SignalAggregator,
    risk_manager: RiskManager,
    order_router: OrderRouter,
    decision_log: DecisionLog,
    ml_generator: MLSignalGenerator,
    llm_chain: LLMAgentChain,
    account_equity: float,
) -> None:
    asset_class = infer_asset_class(symbol)

    # --- Katman 3: sinyal üret ---
    raw_signals = []

    classic_signal = get_classic_signal_placeholder(symbol)
    raw_signals.append(classic_signal)

    ml_signal = ml_generator.predict(symbol, timeframe=timeframe)  # model yoksa None (Faz 3 tamamlandı)
    if ml_signal:
        raw_signals.append(ml_signal)

    llm_signal = llm_chain.analyze(symbol, timeframe=timeframe)  # Faz 4 tamamlandı
    if llm_signal:
        raw_signals.append(llm_signal)

    # --- Katman 3e: birleştir (asset_class sembolden otomatik çıkarılıyor) ---
    candidate = aggregator.aggregate(raw_signals, asset_class=asset_class)
    if candidate is None:
        logger.info("%s için yeterince güçlü/uyumlu sinyal yok, işlem önerilmiyor.", symbol)
        return

    # --- Katman 4: risk kontrolü ---
    result = risk_manager.check(candidate)
    if not result.approved:
        logger.info("%s reddedildi: %s", symbol, result.rejection_reason)
        decision_log.record(
            DecisionRecord(
                symbol=symbol,
                side=candidate.side,
                position_size_pct=0.0,
                confidence=candidate.confidence,
                rationale=candidate.rationale,
                risk_check_result="rejected",
                rejection_reason=str(result.rejection_reason),
            )
        )
        return

    draft: ApprovedOrderDraft = result.order_draft  # type: ignore[assignment]
    decision_id = decision_log.record(
        DecisionRecord(
            symbol=symbol,
            side=draft.side,
            position_size_pct=draft.position_size_pct,
            confidence=candidate.confidence,
            rationale=draft.rationale,
            risk_check_result="approved",
        )
    )

    # --- Katman 6/8: insan onayı ---
    async def on_decision(request_id: str, approved_draft: ApprovedOrderDraft, approved: bool) -> None:
        decision_log.update_human_decision(
            decision_id, "approved" if approved else "rejected"
        )
        if approved:
            order_router.route_order(approved_draft, account_equity)
        else:
            logger.info("Kullanıcı işlemi reddetti veya zaman aşımı: %s", approved_draft.symbol)

    # Not: Her sembol için ayrı bir ApprovalBot örneği oluşturmak,
    # gerçek kullanımda gereksiz Telegram bağlantısı açar. Üretimde
    # tek bir ApprovalBot örneği kurup process_symbol'e parametre
    # olarak geçirin; burada akışın netliği için basit tutuldu.
    approval_bot = ApprovalBot(on_decision=on_decision)
    await approval_bot.request_approval(draft)


async def main() -> None:
    mandate = load_mandate("config/mandate.yaml")

    decision_log = DecisionLog()
    aggregator = SignalAggregator(config=AggregatorConfig())
    risk_manager = RiskManager(
        mandate=mandate,
        current_total_exposure_pct=0.0,   # TODO: gerçek portföyden oku
        current_daily_pnl_pct=0.0,        # TODO: gerçek günlük PnL'den oku
        symbol_consecutive_losses={
            s: decision_log.consecutive_losses(s) for s in mandate.symbol_universe
        },
    )
    order_router = OrderRouter(exchange_id="binance", dry_run=True)
    ml_generator = MLSignalGenerator()  # Faz 3: modelleri sembol bazlı lazy-load + cache eder

    # LLM sağlayıcısını ortam değişkenlerinden kur. ANTHROPIC_API_KEY veya
    # OPENAI_API_KEY tanımlı değilse MockLLMClient'a düşer (bkz. llm_client.py
    # uyarı logu) — bu SADECE geliştirme içindir, gerçek karar üretmez.
    llm_provider = os.environ.get("LLM_PROVIDER", "mock")
    llm_client = build_llm_client(
        provider=llm_provider,
        api_key=os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("OPENAI_API_KEY"),
        model=os.environ.get("LLM_MODEL"),
        base_url=os.environ.get("LLM_BASE_URL"),
    )
    llm_chain = LLMAgentChain(llm_client=llm_client, decision_log=decision_log)

    for symbol in mandate.symbol_universe:
        await process_symbol(
            symbol=symbol,
            timeframe="1h",
            aggregator=aggregator,
            risk_manager=risk_manager,
            order_router=order_router,
            decision_log=decision_log,
            ml_generator=ml_generator,
            llm_chain=llm_chain,
            account_equity=10_000.0,  # TODO: gerçek hesap bakiyesinden oku
        )


if __name__ == "__main__":
    asyncio.run(main())

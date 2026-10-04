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
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # .env dosyasını (varsa) ortam değişkenlerine yükler — TELEGRAM_BOT_TOKEN,
                # TELEGRAM_CHAT_ID, LLM_PROVIDER gibi değerler .env'den okunabilsin diye.
                # `python -m main` çalıştırılan dizindeki .env dosyasını arar.

from execution.order_router import OrderRouter
from execution.telegram_bot import ApprovalBot
from monitoring.decision_log import DecisionLog, DecisionRecord
from risk.mandate import load_mandate
from risk.risk_manager import ApprovedOrderDraft, RiskManager
from signals.aggregator import AggregatorConfig, SignalAggregator, infer_asset_class
from signals.llm_agents.agent_chain import LLMAgentChain
from signals.llm_agents.llm_client import build_llm_client
from signals.classic.live_signal import compute_live_classic_signal
from signals.llm_agents.news_fetcher import NewsAPIClient
from signals.ml.ml_signal import MLSignalGenerator

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("main")


async def process_symbol(
    symbol: str,
    timeframe: str,
    aggregator: SignalAggregator,
    risk_manager: RiskManager,
    order_router: OrderRouter,
    decision_log: DecisionLog,
    ml_generator: MLSignalGenerator,
    llm_chain: LLMAgentChain,
    approval_bot: ApprovalBot,
    account_equity: float,
    news_client: Optional["NewsAPIClient"] = None,
) -> None:
    asset_class = infer_asset_class(symbol)

    # KRİTİK (sürekli mod için gerekli): Bu sembolde zaten açık bir
    # pozisyon varsa YENİ bir öneri üretme. Bu kontrol olmadan, sürekli
    # modda (LOOP_INTERVAL_SECONDS > 0) sabit "long" placeholder sinyali
    # her turda aynı sembol için tekrar tekrar onay isteği gönderirdi.
    if decision_log.has_open_position(symbol):
        logger.info("%s için zaten açık bir pozisyon var, yeni öneri üretilmiyor.", symbol)
        return

    # --- Katman 3: sinyal üret ---
    raw_signals = []

    # KRİTİK DÜZELTME: Bu, uzun süre sabit "long, confidence=0.6" döndüren
    # bir placeholder'dı — piyasada gerçekte ne olduğuna hiç bakmıyordu.
    # Artık data_layer.storage'daki en güncel veriden GERÇEK bir SMA
    # kesişimi hesaplanıyor (bkz. signals/classic/live_signal.py). Veri
    # yoksa veya kesişim yoksa None döner, aggregator'a hiç eklenmez.
    classic_signal = compute_live_classic_signal(symbol, timeframe=timeframe)
    if classic_signal:
        raw_signals.append(classic_signal)

    ml_signal = ml_generator.predict(symbol, timeframe=timeframe)  # model yoksa None (Faz 3 tamamlandı)
    if ml_signal:
        raw_signals.append(ml_signal)

    # Haber metni: news_client yapılandırılmışsa (NEWSAPI_KEY .env'de varsa)
    # gerçek başlıklar çekilir; yoksa None kalır (LLM "haber yok" der,
    # önceki davranışla aynı — geriye dönük uyumluluk bozulmaz).
    news_text = None
    if news_client is not None:
        try:
            news_text = news_client.fetch_news_text_for_symbol(symbol)
        except Exception as e:
            logger.warning("%s için haber çekilemedi (%s), news_text=None ile devam ediliyor.", symbol, e)

    llm_signal = llm_chain.analyze(symbol, timeframe=timeframe, news_text=news_text)  # Faz 4 tamamlandı
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
            order_result = order_router.route_order(approved_draft, account_equity)
            # KRİTİK: Bu satır olmadan aynı çalıştırma içinde onaylanan
            # işlemler toplam maruziyete YANSIMAZ — bir sonraki sembol
            # kontrolü sanki hiçbir pozisyon açılmamış gibi değerlendirilir.
            risk_manager.record_position_opened(approved_draft.position_size_pct)
            # Giriş fiyatını kaydet — bu olmadan pozisyon kapatıldığında
            # (bkz. /kapat komutu) PnL hesaplamak imkansızdır.
            entry_price = order_result.get("price")
            if entry_price is not None:
                decision_log.update_entry_price(decision_id, entry_price)
            else:
                logger.warning(
                    "%s için giriş fiyatı alınamadı — bu pozisyon /kapat ile "
                    "kapatılamayacak (manuel PnL hesabı gerekir).", approved_draft.symbol,
                )
        else:
            logger.info("Kullanıcı işlemi reddetti veya zaman aşımı: %s", approved_draft.symbol)

    # Not: approval_bot main() içinde BİR KEZ oluşturulup start() ile
    # dinlemeye başlatılıyor, tüm semboller arasında paylaşılıyor —
    # her sembol için yeni bir bot/bağlantı AÇILMIYOR.
    await approval_bot.request_approval(draft, on_decision=on_decision)


def _refresh_crypto_symbol(symbol: str, timeframe: str, refresh_days: int = 3) -> None:
    """
    ccxt'den son `refresh_days` günlük veriyi çekip MEVCUT parquet dosyasıyla
    BİRLEŞTİRİR (üzerine yazmaz). Sadece son birkaç günü çekip dosyanın
    üzerine yazmak, ML modelinin ihtiyaç duyduğu uzun geçmişi (200+ bar)
    SİLERDİ — bu yüzden var olan veriyle concat + dedup + sort yapılıyor.
    """
    import pandas as pd

    from data_layer.connectors.ccxt_connector import fetch_ohlcv, save_to_parquet

    new_df = fetch_ohlcv("binance", symbol, timeframe, since_days=refresh_days)

    safe_symbol = symbol.replace("/", "_")
    existing_path = Path("data/ohlcv") / f"{safe_symbol}_{timeframe}.parquet"
    if existing_path.exists():
        old_df = pd.read_parquet(existing_path)
        old_df["timestamp"] = pd.to_datetime(old_df["timestamp"], utc=True)
        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    else:
        combined = new_df

    save_to_parquet(combined, symbol, timeframe)


def _refresh_equity_symbol(symbol: str, timeframe: str, refresh_days: int = 3) -> None:
    """_refresh_crypto_symbol ile aynı birleştirme mantığı, Alpaca için."""
    import pandas as pd

    from data_layer.connectors.alpaca_connector import fetch_ohlcv, save_to_parquet

    api_key = os.environ.get("ALPACA_API_KEY")
    secret_key = os.environ.get("ALPACA_API_SECRET")
    if not api_key or not secret_key:
        raise RuntimeError("ALPACA_API_KEY/ALPACA_API_SECRET tanımlı değil, hisse verisi yenilenemiyor.")

    new_df = fetch_ohlcv(symbol, timeframe, refresh_days, api_key=api_key, secret_key=secret_key)

    safe_symbol = symbol.replace("/", "_")
    existing_path = Path("data/ohlcv") / f"{safe_symbol}_{timeframe}.parquet"
    if existing_path.exists():
        old_df = pd.read_parquet(existing_path)
        old_df["timestamp"] = pd.to_datetime(old_df["timestamp"], utc=True)
        combined = pd.concat([old_df, new_df], ignore_index=True)
        combined = combined.drop_duplicates(subset="timestamp").sort_values("timestamp").reset_index(drop=True)
    else:
        combined = new_df

    save_to_parquet(combined, symbol, timeframe)


async def refresh_market_data(mandate, timeframe: str = "1h") -> None:
    """
    KRİTİK EKSİK (bu turda bulundu): main.py, sürekli mod (LOOP_INTERVAL_SECONDS)
    eklendikten SONRA BİLE hiçbir zaman veriyi yenilemiyordu — döngü hep
    aynı, bir kez manuel indirilmiş eski veriyi kullanıyordu. Sürekli mod
    taze veri olmadan anlamsızdır. Bu fonksiyon her sembol için (asset
    class'a göre doğru konnektörü kullanarak) veriyi günceller.

    Ağ çağrıları senkron (ccxt/requests) olduğu için event loop'u
    bloklamamak için run_in_executor ile ayrı bir thread'de çalıştırılır.
    Bir sembolde hata olursa (ör. API limiti) sadece o sembol atlanır,
    diğerleri etkilenmez.
    """
    loop = asyncio.get_event_loop()
    for symbol in mandate.symbol_universe:
        asset_class = infer_asset_class(symbol)
        try:
            if asset_class == "crypto":
                await loop.run_in_executor(None, _refresh_crypto_symbol, symbol, timeframe)
            elif asset_class == "equity":
                await loop.run_in_executor(None, _refresh_equity_symbol, symbol, timeframe)
        except Exception as e:
            logger.warning("%s için veri yenilenemedi: %s", symbol, e)


async def run_one_pass(
    mandate,
    aggregator: SignalAggregator,
    risk_manager: RiskManager,
    order_router: OrderRouter,
    decision_log: DecisionLog,
    ml_generator: MLSignalGenerator,
    llm_chain: LLMAgentChain,
    approval_bot: ApprovalBot,
    account_equity: float,
    news_client: Optional[NewsAPIClient] = None,
    refresh_data: bool = True,
) -> None:
    """
    Mandate'teki TÜM sembolleri bir kez tarar. KRİTİK DAYANIKLILIK NOTU:
    her sembol ayrı bir try/except içinde işlenir — bir sembolde beklenmeyen
    bir hata (ör. borsa API zaman aşımı, LLM sağlayıcı hatası) OLURSA,
    sadece o sembol atlanır; program çökmez, Telegram bağlantısı kopmaz,
    diğer semboller normal şekilde işlenmeye devam eder.

    refresh_data=True (varsayılan): sinyal üretmeden ÖNCE tüm sembollerin
    verisi güncellenir (bkz. refresh_market_data). Testlerde veya manuel
    tek seferlik çalıştırmalarda (zaten güncel veriyle) ağ trafiğinden
    kaçınmak isterseniz False geçebilirsiniz.
    """
    if refresh_data:
        await refresh_market_data(mandate, timeframe="1h")

    for symbol in mandate.symbol_universe:
        try:
            await process_symbol(
                symbol=symbol,
                timeframe="1h",
                aggregator=aggregator,
                risk_manager=risk_manager,
                order_router=order_router,
                decision_log=decision_log,
                ml_generator=ml_generator,
                llm_chain=llm_chain,
                approval_bot=approval_bot,
                account_equity=account_equity,
                news_client=news_client,
            )
        except Exception:
            logger.exception(
                "%s işlenirken beklenmeyen bir hata oluştu — bu sembol atlanıyor, "
                "program çalışmaya devam ediyor.", symbol,
            )


async def main() -> None:
    mandate = load_mandate("config/mandate.yaml")

    decision_log = DecisionLog()
    aggregator = SignalAggregator(config=AggregatorConfig())
    # KRİTİK: current_total_exposure_pct artık sabit 0.0 DEĞİL —
    # decision_log'daki hâlâ açık (kapatılmamış) pozisyonlardan hesaplanıyor.
    # Bu olmadan, programı yeniden başlattığınızda önceki açık pozisyonlar
    # unutulur ve toplam maruziyet limiti yanlışlıkla aşılabilirdi.
    risk_manager = RiskManager(
        mandate=mandate,
        current_total_exposure_pct=decision_log.total_open_exposure_pct(),
        current_daily_pnl_pct=0.0,        # TODO: gerçek günlük PnL'den oku (Faz 5+ pozisyon izleyici gerekli)
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

    # Haber kaynağı: NEWSAPI_KEY (.env'de) ayarlanmışsa gerçek başlıklar
    # çekilip news_analyst_node'a besleniyor (bkz. news_fetcher.py — bu
    # public-apis/public-apis reposundan taranıp seçilen NewsAPI.org'a
    # dayanıyor). Ayarlanmamışsa None kalır, LLM "haber yok" der — sistem
    # bu olmadan da tam çalışır, sadece haber sinyali eksik olur.
    newsapi_key = os.environ.get("NEWSAPI_KEY")
    news_client = NewsAPIClient(api_key=newsapi_key) if newsapi_key else None
    if news_client is None:
        logger.info("NEWSAPI_KEY tanımlı değil — LLM ajan zinciri haber verisi olmadan çalışacak.")

    # ApprovalBot TEK SEFER oluşturulur ve start() ile Telegram'dan gelen
    # buton tıklamalarını dinlemeye başlar. Bu adım olmadan (start() çağrılmadan)
    # mesajlar gider ama hiçbir buton tıklaması işlenmez (bkz. telegram_bot.py
    # başındaki "KRİTİK DÜZELTME" notu).
    approval_bot = ApprovalBot(timeout_seconds=mandate.approval_timeout_seconds)

    # --- Yeni: pozisyon yaşam döngüsünü tamamlayan Telegram komutları ---
    # (Sistemin genişletilmiş amacı: sadece "işlem öner" değil, öner ->
    # onayla -> gerçek fiyattan gir -> izle -> KAPAT -> öğren döngüsünü
    # tamamlamak. Kapatma adımı, gerçek bir pozisyon izleyici/borsa
    # senkronizasyonu henüz olmadığı için ŞİMDİLİK manuel — siz borsada
    # pozisyonu kapattığınızda buradan da bilgi veriyorsunuz.)
    async def handle_positions(update, context) -> None:
        positions = decision_log.open_positions()
        if not positions:
            await update.message.reply_text("Açık pozisyon yok.")
            return
        lines = []
        for p in positions:
            entry = p.get("entry_price")
            entry_str = f"{entry:.4f}" if entry is not None else "bilinmiyor"
            lines.append(
                f"#{p['id']}: {p['symbol']} {p['side']} "
                f"(%{p['position_size_pct'] * 100:.2f}, giriş={entry_str})"
            )
        await update.message.reply_text("Açık pozisyonlar:\n" + "\n".join(lines))

    async def handle_close(update, context) -> None:
        args = context.args
        if len(args) != 2:
            await update.message.reply_text("Kullanım: /kapat <id> <cikis_fiyati>")
            return
        try:
            close_id = int(args[0])
            exit_price = float(args[1])
        except ValueError:
            await update.message.reply_text("id tam sayı, çıkış fiyatı sayı olmalı. Örnek: /kapat 3 65000.5")
            return

        decision = decision_log.get_decision(close_id)
        if decision is None or decision.get("human_decision") != "approved" or decision.get("realized_pnl_pct") is not None:
            await update.message.reply_text(f"#{close_id} açık bir pozisyon değil.")
            return
        entry_price = decision.get("entry_price")
        if entry_price is None or entry_price == 0:
            await update.message.reply_text(
                f"#{close_id} için giriş fiyatı kayıtlı değil, PnL hesaplanamıyor."
            )
            return

        direction = 1 if decision["side"] == "long" else -1
        realized_pnl_pct = direction * (exit_price - entry_price) / entry_price

        decision_log.close_position(close_id, realized_pnl_pct)
        risk_manager.record_position_closed(decision["symbol"], decision["position_size_pct"], realized_pnl_pct)

        await update.message.reply_text(
            f"#{close_id} ({decision['symbol']}) kapatıldı.\n"
            f"Giriş: {entry_price:.4f} -> Çıkış: {exit_price:.4f}\n"
            f"Gerçekleşen PnL: %{realized_pnl_pct * 100:.2f}"
        )

    async def handle_stop(update, context) -> None:
        """
        Kill-switch'i Telegram'dan uzaktan tetikler. Tasarımın "fail-closed"
        felsefesiyle tutarlı hale getirmek için eklendi: önceden kill-switch
        SADECE sunucudaki dosya sistemine `touch STOP_TRADING` ile erişimi
        olan biri tarafından tetiklenebiliyordu — acil bir durumda
        telefonunuzdan SSH olmadan sistemi durduramazdınız.
        """
        Path(mandate.kill_switch_file).touch()
        await update.message.reply_text(
            f"🛑 Kill-switch AKTİF edildi (`{mandate.kill_switch_file}`).\n"
            f"Yeni işlem önerisi üretilmeyecek. Devam etmek için /devam yazın.",
            parse_mode="Markdown",
        )

    async def handle_resume(update, context) -> None:
        kill_switch_path = Path(mandate.kill_switch_file)
        if kill_switch_path.exists():
            kill_switch_path.unlink()
            await update.message.reply_text("✅ Kill-switch KALDIRILDI. Sistem normal çalışmaya devam ediyor.")
        else:
            await update.message.reply_text("Kill-switch zaten aktif değildi.")

    async def handle_help(update, context) -> None:
        await update.message.reply_text(
            "Kullanılabilir komutlar:\n"
            "/durum — bekleyen (henüz onaylanmamış) işlem önerileri\n"
            "/pozisyonlar — açık pozisyonlar (giriş fiyatlarıyla)\n"
            "/kapat <id> <cikis_fiyati> — bir pozisyonu kapat, PnL hesapla\n"
            "/dur — acil durdurma (kill-switch aktif eder)\n"
            "/devam — kill-switch'i kaldırır\n"
            "/yardim — bu mesaj"
        )

    approval_bot.register_command("pozisyonlar", handle_positions)
    approval_bot.register_command("kapat", handle_close)
    approval_bot.register_command("dur", handle_stop)
    approval_bot.register_command("devam", handle_resume)
    approval_bot.register_command("yardim", handle_help)

    await approval_bot.start()

    # KAPSAM GENİŞLETMESİ: LOOP_INTERVAL_SECONDS ayarlanmışsa (.env'de),
    # sistem TEK SEFERLİK bir betik olmaktan çıkıp SÜREKLİ çalışan bir
    # servise dönüşür — her N saniyede bir tüm sembolleri yeniden tarar.
    # Ayarlanmamışsa (varsayılan: 0) eski davranış korunur: bir kez tarar,
    # biter. Sürekli modda Ctrl+C ile durdurulabilir (bkz. alttaki
    # KeyboardInterrupt yakalama).
    loop_interval = int(os.environ.get("LOOP_INTERVAL_SECONDS", "0"))
    # ACCOUNT_EQUITY (.env'de) ile yapılandırılabilir — artık farklı sermaye
    # senaryolarını test etmek için kod değiştirmenize gerek yok. Gerçek
    # hesap bakiyesinden otomatik okuma (borsa/broker API'sinden) hâlâ
    # yapılmıyor (Faz 5+ konusu) — bu sadece sabit değeri koddan .env'e taşıyor.
    account_equity = float(os.environ.get("ACCOUNT_EQUITY", "10000.0"))

    try:
        if loop_interval > 0:
            logger.info(
                "Sürekli mod aktif: her %d saniyede bir %d sembol taranacak. "
                "Durdurmak için Ctrl+C.", loop_interval, len(mandate.symbol_universe),
            )
            while True:
                await run_one_pass(
                    mandate, aggregator, risk_manager, order_router,
                    decision_log, ml_generator, llm_chain, approval_bot, account_equity,
                    news_client=news_client,
                )
                logger.info("Tur tamamlandı, %d saniye bekleniyor...", loop_interval)
                await asyncio.sleep(loop_interval)
        else:
            await run_one_pass(
                mandate, aggregator, risk_manager, order_router,
                decision_log, ml_generator, llm_chain, approval_bot, account_equity,
                news_client=news_client,
            )
    finally:
        # Program hata ile de bitse, polling düzgünce kapatılmalı.
        await approval_bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        # Ctrl+C ile durdurma artık çirkin bir traceback yerine düzgün bir
        # mesajla bitiyor. main()'in finally bloğu (approval_bot.stop())
        # asyncio.run() bu istisnayı yeniden fırlatmadan ÖNCE zaten çalışmış
        # olur — yani polling burada da düzgünce kapatılmış olur.
        print("\n[main] Kullanıcı tarafından durduruldu (Ctrl+C). Güvenle kapatıldı.")

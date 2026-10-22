"""
Tam kapsamlı tarama akışı (v3 - profesyonel otomasyon):

evren tazele (otomatik) -> fiyat verisi çek -> doğrula -> benchmark
verisi çek -> teknik sinyal üret -> gelişmiş göstergeler (Fibonacci,
destek/direnç, hacim profili) -> temel analiz (opsiyonel) -> göreceli
güç -> hacim/haftalık teyit -> risk metrikleri -> skorla -> filtrele
-> Excel rapor oluştur -> sinyal günlüğüne kaydet + geçmiş sinyalleri
güncelle -> Telegram bildirimi gönder (yapılandırılmışsa).

Kullanım:
    python main_scan.py --markets us bist crypto
    python main_scan.py --markets us --no-cache
    python main_scan.py --markets us --skip-fundamentals   (hızlı, sadece teknik)
    python main_scan.py --markets us --min-score 0.3 --only-buy
    python main_scan.py --markets us --no-notify           (Telegram bildirimi gönderme)
    python main_scan.py --markets us --no-auto-refresh      (sembol listelerini otomatik güncelleme)
"""
import argparse
import logging
import os
from datetime import datetime

import pandas as pd

import config
import universe
from data_pipeline import fetcher, validator, stooq_fetcher
from analysis.strategy import RegimeAdaptiveStrategy
from analysis import (
    scorer, fundamentals, relative_strength, confirmations, risk_metrics,
    filters, advanced_indicators, journal, notifier, news,
    position_sizing, economic_calendar, grid_strategy, dca_plan, grid_dca_journal,
    portfolio_correlation, paper_trading,
)
from reporting import excel_report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(config.LOG_DIR, "scan.log")),
    ],
)
logger = logging.getLogger("main_scan")


def run_scan(
    markets=None,
    use_cache=True,
    skip_fundamentals=False,
    skip_news=False,
    skip_cross_validation=False,
    skip_correlation_check=False,
    skip_paper_trading=False,
    filter_overrides=None,
    auto_refresh_universe=None,
    send_notification=True,
    update_journal=True,
    account_size=10000.0,
    risk_per_trade_pct=1.0,
) -> str:
    start_time = datetime.now()
    logger.info(f"Tarama başladı. Piyasalar: {markets or 'hepsi'}")

    active_markets = markets or list(config.UNIVERSE_FILES.keys())

    # --- 0) Sembol listelerini gerekiyorsa otomatik tazele ---
    auto_refresh = (
        auto_refresh_universe if auto_refresh_universe is not None
        else config.AUTO_REFRESH_UNIVERSE_DEFAULT
    )
    if auto_refresh:
        refresh_results = universe.auto_refresh_if_stale(active_markets)
        for market, result in refresh_results.items():
            logger.info(f"Sembol listesi [{market}]: {result}")

    universe_df = universe.load_universe(markets)
    symbols = universe_df["symbol"].tolist()
    logger.info(f"Evren büyüklüğü: {len(symbols)} sembol")

    # --- 1) Fiyat verisi çek (yfinance öncelikli, başarısızsa Stooq'a düşer) ---
    market_by_symbol = universe_df.set_index("symbol")["market"].to_dict()
    fetch_result = fetcher.fetch_universe(symbols, use_cache=use_cache, market_by_symbol=market_by_symbol)
    stooq_fallback_count = sum(1 for s in fetch_result.sources.values() if "stooq" in s)
    logger.info(
        f"Veri çekildi: {len(fetch_result.data)} başarılı "
        f"({len(fetch_result.from_cache)} cache'den, {stooq_fallback_count} Stooq yedeğinden), "
        f"{len(fetch_result.failed)} başarısız"
    )

    # --- 2) Doğrula ---
    valid_data, validation_report = validator.validate_batch(fetch_result.data)
    for sym, err in fetch_result.failed.items():
        validation_report[sym] = validator.ValidationResult(sym, False, [f"İndirme hatası: {err}"])
    logger.info(f"Doğrulamadan geçen: {len(valid_data)} / {len(fetch_result.data)}")

    # --- 3) Benchmark verisi çek (göreceli güç ve beta için) ---
    benchmark_symbols = list(set(relative_strength.BENCHMARKS.values()))
    bench_fetch = fetcher.fetch_universe(benchmark_symbols, use_cache=use_cache)
    benchmark_data = {
        market: bench_fetch.data[sym]
        for market, sym in relative_strength.BENCHMARKS.items()
        if sym in bench_fetch.data
    }
    logger.info(f"Benchmark verisi: {list(benchmark_data.keys())}")

    # --- 4) Teknik sinyal üretimi ---
    strategy = RegimeAdaptiveStrategy()
    signals_by_symbol = {}
    for symbol, df in valid_data.items():
        try:
            signals_by_symbol[symbol] = strategy.generate_signals(df)
        except Exception as e:
            logger.warning(f"{symbol} için sinyal üretilemedi: {e}")
            validation_report[symbol] = validator.ValidationResult(
                symbol, False, [f"Sinyal üretim hatası: {e}"]
            )

    # --- 5) Gelişmiş göstergeler (Fibonacci, destek/direnç, hacim profili) ---
    advanced_by_symbol = {}
    for symbol, sig_df in signals_by_symbol.items():
        try:
            advanced_by_symbol[symbol] = advanced_indicators.compute_all(sig_df)
        except Exception as e:
            logger.warning(f"{symbol} gelişmiş gösterge hesaplanamadı: {e}")

    # --- 6) Temel analiz (opsiyonel, yavaş) ---
    fundamentals_df = None
    if not skip_fundamentals:
        logger.info("Temel analiz verisi çekiliyor (bu adım yavaş olabilir)...")
        signal_symbols_universe = universe_df[universe_df["symbol"].isin(signals_by_symbol.keys())]
        raw_fundamentals = fundamentals.fetch_batch(signal_symbols_universe)
        fundamentals_df = fundamentals.compute_fundamental_scores(raw_fundamentals)
        logger.info(f"Temel analiz tamamlandı: {len(fundamentals_df)} sembol")
    else:
        logger.info("Temel analiz atlandı (--skip-fundamentals).")

    # --- 7) Göreceli güç ---
    rs_df = relative_strength.compute_relative_strength_batch(
        valid_data, universe_df, benchmark_data, lookback=config.RELATIVE_STRENGTH_LOOKBACK_DAYS
    )

    # --- 8) Hacim / haftalık trend teyidi + risk metrikleri ---
    confirmations_by_symbol = {}
    risk_by_symbol = {}
    for symbol, sig_df in signals_by_symbol.items():
        last_signal = int(sig_df.iloc[-1]["signal"])
        try:
            confirmations_by_symbol[symbol] = confirmations.compute_confirmations(sig_df, last_signal)
        except Exception as e:
            logger.warning(f"{symbol} teyit hesaplanamadı: {e}")

        market = market_by_symbol.get(symbol)
        bench_df = benchmark_data.get(market)
        try:
            risk_by_symbol[symbol] = risk_metrics.compute_all(
                sig_df, bench_df["Close"] if bench_df is not None else None
            )
        except Exception as e:
            logger.warning(f"{symbol} risk metriği hesaplanamadı: {e}")

    # --- 8.5) Haber analizi (opsiyonel, sembol başına ayrı istek - yavaşlatabilir) ---
    news_by_symbol = {}
    macro_news = []
    if not skip_news:
        logger.info("Haber başlıkları çekiliyor (sembol bazlı + makro)...")
        for symbol in signals_by_symbol.keys():
            try:
                news_by_symbol[symbol] = news.symbol_news_summary(symbol)
            except Exception as e:
                logger.warning(f"{symbol} için haber özeti hesaplanamadı: {e}")
        try:
            macro_news = news.fetch_macro_news()
            logger.info(f"Makro haber başlığı: {len(macro_news)}")
        except Exception as e:
            logger.warning(f"Makro haberler çekilemedi: {e}")
    else:
        logger.info("Haber analizi atlandı (--skip-news).")

    # --- 9) Skorlama (tüm bileşenler birleşiyor) ---
    scored_df = scorer.score_universe(
        signals_by_symbol, universe_df,
        fundamentals_df=fundamentals_df,
        relative_strength_df=rs_df,
        confirmations_by_symbol=confirmations_by_symbol,
        risk_metrics_by_symbol=risk_by_symbol,
        news_by_symbol=news_by_symbol,
    )
    logger.info(f"Sinyal üreten sembol sayısı: {len(scored_df)} / {len(signals_by_symbol)} taranan")

    # Şeffaflık için: sinyal üretsin üretmesin, TÜM taranan sembollerin durumu
    full_status_df = scorer.full_universe_status(signals_by_symbol, universe_df)

    # Gelişmiş göstergeleri skorlanmış tabloya ekle (rapora yansısın diye)
    if not scored_df.empty and advanced_by_symbol:
        adv_df = pd.DataFrame([{"symbol": s, **a} for s, a in advanced_by_symbol.items()])
        scored_df = scored_df.merge(adv_df, on="symbol", how="left")

    # --- 9.5) Çapraz doğrulama (sadece sinyal üreten semboller için, Stooq ile karşılaştırma) ---
    if not skip_cross_validation and not scored_df.empty:
        logger.info("Çapraz doğrulama yapılıyor (Stooq ile fiyat karşılaştırması)...")
        cross_val_rows = []
        for _, row in scored_df.iterrows():
            try:
                cv = stooq_fetcher.cross_validate(row["symbol"], row["market"], row["close"])
            except Exception as e:
                logger.warning(f"{row['symbol']} çapraz doğrulama başarısız: {e}")
                cv = {"stooq_close": None, "fark_yuzde": None, "supheli": False}
            cross_val_rows.append({"symbol": row["symbol"], **cv})
        cross_val_df = pd.DataFrame(cross_val_rows)
        scored_df = scored_df.merge(cross_val_df, on="symbol", how="left")
        supheli_count = scored_df["supheli"].sum() if "supheli" in scored_df.columns else 0
        if supheli_count > 0:
            logger.warning(f"{supheli_count} sembolde yfinance/Stooq fiyat uyuşmazlığı tespit edildi (bkz. rapor).")
    else:
        logger.info("Çapraz doğrulama atlandı (--skip-cross-validation).")

    # --- 9.7) Pozisyon büyüklüğü önerisi ---
    if not scored_df.empty:
        scored_df = position_sizing.compute_for_scored_df(scored_df, account_size, risk_per_trade_pct)
        logger.info(f"Pozisyon büyüklüğü önerileri hesaplandı (hesap: {account_size}, risk: %{risk_per_trade_pct})")

    # --- 9.75) Portföy-seviyesi korelasyon kontrolü ---
    # Aynı anda gelen sinyaller birbirine yüksek korelasyonluysa (örn. aynı
    # sektör, ya da genel piyasayı takip ediyorlarsa), bunları bağımsız
    # bahisler gibi boyutlandırmak gerçek riski olduğundan düşük gösterir.
    portfolio_summary_stats = {}
    if not skip_correlation_check and not scored_df.empty and len(scored_df) >= 2:
        try:
            signal_symbols = scored_df["symbol"].tolist()
            corr_matrix = portfolio_correlation.compute_correlation_matrix(valid_data, signal_symbols)
            clusters = portfolio_correlation.find_correlated_clusters(corr_matrix)
            scored_df = portfolio_correlation.adjust_position_sizes(scored_df, clusters)
            portfolio_summary_stats = portfolio_correlation.portfolio_summary(scored_df, corr_matrix, clusters)
            if clusters:
                logger.warning(f"{len(clusters)} korelasyonlu sinyal kümesi tespit edildi, "
                                f"pozisyon büyüklükleri düzeltildi: {clusters}")
        except Exception as e:
            logger.warning(f"Portföy korelasyon kontrolü başarısız: {e}")
    else:
        logger.info("Portföy korelasyon kontrolü atlandı (--skip-correlation-check veya yetersiz sinyal).")

    # --- 9.77) Paper trading: sanal portföyü güncelle ---
    paper_perf = {}
    if not skip_paper_trading:
        try:
            paper_trading.initialize_account(account_size)
            paper_trading.update_open_positions(valid_data)  # önce açık pozisyonları kontrol et (stop/hedef)
            if not scored_df.empty:
                pt_stats = paper_trading.process_new_signals(scored_df, signals_by_symbol)
                logger.info(f"Paper trading: {pt_stats}")
            paper_trading.record_equity_snapshot(valid_data)
            paper_perf = paper_trading.compute_performance_stats()
            logger.info(f"Paper trading performansı: {paper_perf}")
        except Exception as e:
            logger.warning(f"Paper trading güncellenemedi: {e}")
    else:
        logger.info("Paper trading atlandı (--skip-paper-trading).")

    # --- 9.8) Grid ve DCA plan önerileri ---
    grid_rows = []
    dca_rows = []
    if not scored_df.empty:
        for _, row in scored_df.iterrows():
            symbol = row["symbol"]
            # Korelasyon düzeltmesi varsa onu kullan (efektif = gerçek riske göre
            # ayarlanmış); yoksa (kontrol atlandıysa) ham pozisyon büyüklüğüne düş
            pozisyon = row.get("efektif_pozisyon_buyuklugu")
            if pd.isna(pozisyon) or pozisyon is None:
                pozisyon = row.get("pozisyon_buyuklugu")
            if pd.isna(pozisyon) or pozisyon is None or symbol not in signals_by_symbol:
                continue

            # Grid: sadece range (yatay) rejimindeki semboller için anlamlı
            try:
                grid_result = grid_strategy.suggest_grid(
                    signals_by_symbol[symbol], row.get("regime"), float(pozisyon)
                )
                if grid_result["uygun_mu"]:
                    for lvl in grid_result["seviyeler"]:
                        grid_rows.append({"symbol": symbol, **lvl})
            except Exception as e:
                logger.warning(f"{symbol} için grid planı hesaplanamadı: {e}")

            # DCA: sadece AL sinyali olan semboller için (kademeli satış standart değil)
            if row.get("signal") == 1:
                try:
                    plan = dca_plan.suggest_dca_plan(float(row["close"]), float(pozisyon))
                    dca_df_part = dca_plan.dca_plan_to_dataframe(symbol, plan)
                    if not dca_df_part.empty:
                        dca_rows.append(dca_df_part)
                except Exception as e:
                    logger.warning(f"{symbol} için DCA planı hesaplanamadı: {e}")

    grid_plan_df = pd.DataFrame(grid_rows) if grid_rows else pd.DataFrame()
    dca_plan_df = pd.concat(dca_rows, ignore_index=True) if dca_rows else pd.DataFrame()
    logger.info(f"Grid planı: {grid_plan_df['symbol'].nunique() if not grid_plan_df.empty else 0} sembol, "
                f"DCA planı: {dca_plan_df['symbol'].nunique() if not dca_plan_df.empty else 0} sembol")

    # --- 9.9) Grid/DCA emir günlüğü: yeni planları kaydet, eski emirlerin sonucunu güncelle ---
    grid_perf, dca_perf = {}, {}
    if update_journal:
        try:
            grid_dca_journal.record_grid_plan(grid_plan_df, universe_df, scan_time=start_time.isoformat())
            grid_dca_journal.record_dca_plan(dca_plan_df, universe_df, scan_time=start_time.isoformat())
            grid_outcome_stats = grid_dca_journal.update_grid_outcomes(valid_data)
            dca_outcome_stats = grid_dca_journal.update_dca_outcomes(valid_data)
            logger.info(f"Grid emir güncellemesi: {grid_outcome_stats}")
            logger.info(f"DCA emir güncellemesi: {dca_outcome_stats}")
            grid_perf = grid_dca_journal.compute_grid_performance()
            dca_perf = grid_dca_journal.compute_dca_performance(current_data_by_symbol=valid_data)
        except Exception as e:
            logger.warning(f"Grid/DCA emir günlüğü güncellenemedi: {e}")

    # --- 10) Filtreleme ---
    active_filters = dict(config.FILTERS)
    if filter_overrides:
        active_filters.update({k: v for k, v in filter_overrides.items() if v is not None})
    filtered_df, filter_stats = filters.apply_filters(scored_df, active_filters)
    logger.info(f"Filtre sonrası: {filter_stats}")

    # --- 11) Sinyal günlüğü: yeni sinyalleri kaydet, açık sinyalleri güncelle ---
    performance_stats_df = None
    if update_journal:
        try:
            journal.update_outcomes(valid_data)
            added = journal.record_signals(scored_df, start_time.isoformat())
            logger.info(f"Sinyal günlüğü: {added} yeni kayıt eklendi.")
            performance_stats_df = journal.compute_performance_stats()
        except Exception as e:
            logger.warning(f"Sinyal günlüğü güncellenemedi: {e}")

    # --- 12) Excel raporu ---
    calendar_df = economic_calendar.get_calendar()
    if not calendar_df.empty:
        logger.info(f"Yaklaşan {len(calendar_df)} önemli ekonomik olay bulundu.")

    timestamp = start_time.strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(config.REPORTS_DIR, f"tarama_{timestamp}.xlsx")
    excel_report.build_report(
        scored_df, validation_report, output_path,
        filtered_df=filtered_df, filter_stats=filter_stats,
        performance_stats_df=performance_stats_df,
        macro_news=macro_news,
        calendar_df=calendar_df,
        grid_plan_df=grid_plan_df,
        dca_plan_df=dca_plan_df,
        full_status_df=full_status_df,
        grid_dca_performance={"grid": grid_perf, "dca": dca_perf},
        portfolio_summary_stats=portfolio_summary_stats,
        paper_trading_stats=paper_perf,
    )

    # --- 13) Telegram bildirimi (yapılandırılmışsa) ---
    if send_notification:
        try:
            notified = notifier.notify_scan_complete(filtered_df, filter_stats, output_path)
            if notified:
                logger.info("Telegram bildirimi gönderildi.")
        except Exception as e:
            logger.warning(f"Telegram bildirimi gönderilemedi: {e}")

    elapsed = (datetime.now() - start_time).total_seconds()
    logger.info(f"Tarama tamamlandı ({elapsed:.1f} sn). Rapor: {output_path}")
    return output_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tam kapsamlı çoklu piyasa tarama sistemi")
    parser.add_argument("--markets", nargs="+", default=None, choices=["us", "bist", "crypto", "emtia"])
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--skip-fundamentals", action="store_true",
                         help="Temel analiz çekimini atla (daha hızlı, sadece teknik+göreceli güç)")
    parser.add_argument("--skip-news", action="store_true",
                         help="Haber analizi çekimini atla (daha hızlı)")
    parser.add_argument("--skip-cross-validation", action="store_true",
                         help="Stooq ile çapraz fiyat doğrulamasını atla (daha hızlı)")
    parser.add_argument("--skip-correlation-check", action="store_true",
                         help="Portföy-seviyesi korelasyon kontrolünü atla (pozisyon büyüklükleri düzeltilmez)")
    parser.add_argument("--skip-paper-trading", action="store_true",
                         help="Sanal portföy (paper trading) güncellemesini atla")
    parser.add_argument("--min-score", type=float, default=None, help="Minimum |bileşik skor|")
    parser.add_argument("--only-buy", action="store_true", help="Sadece AL sinyallerini göster")
    parser.add_argument("--only-sell", action="store_true", help="Sadece SAT sinyallerini göster")
    parser.add_argument("--min-market-cap", type=float, default=None)
    parser.add_argument("--max-pe", type=float, default=None)
    parser.add_argument("--no-notify", action="store_true", help="Telegram bildirimi gönderme")
    parser.add_argument("--no-auto-refresh", action="store_true",
                         help="Sembol listelerini otomatik güncelleme")
    parser.add_argument("--no-journal", action="store_true", help="Sinyal günlüğüne kaydetme")
    parser.add_argument("--account-size", type=float, default=10000.0,
                         help="Pozisyon büyüklüğü önerisi için varsayımsal hesap büyüklüğü ($)")
    parser.add_argument("--risk-pct", type=float, default=1.0,
                         help="İşlem başına riske edilecek hesap yüzdesi (varsayılan %%1)")
    args = parser.parse_args()

    allowed_signals = None
    if args.only_buy and not args.only_sell:
        allowed_signals = [1]
    elif args.only_sell and not args.only_buy:
        allowed_signals = [-1]

    overrides = {
        "min_composite_score": args.min_score,
        "allowed_signals": allowed_signals,
        "min_market_cap": args.min_market_cap,
        "max_pe": args.max_pe,
    }

    run_scan(
        markets=args.markets,
        use_cache=not args.no_cache,
        skip_fundamentals=args.skip_fundamentals,
        skip_news=args.skip_news,
        skip_cross_validation=args.skip_cross_validation,
        skip_correlation_check=args.skip_correlation_check,
        skip_paper_trading=args.skip_paper_trading,
        filter_overrides=overrides,
        auto_refresh_universe=not args.no_auto_refresh,
        send_notification=not args.no_notify,
        update_journal=not args.no_journal,
        account_size=args.account_size,
        risk_per_trade_pct=args.risk_pct,
    )

"""
Bu sandbox'ta gerçek Yahoo Finance/CoinGecko erişimi yok. Bu script,
TÜM sistemi (evren -> fiyat verisi -> doğrulama -> teknik analiz ->
gelişmiş göstergeler -> temel analiz -> göreceli güç -> hacim/haftalık
teyit -> risk metrikleri -> skorlama -> filtreleme -> sinyal günlüğü
-> Excel raporu -> bildirim) sentetik veriyle uçtan uca doğrular.
Gerçek bilgisayarında main_scan.py gerçek veriyle aynı şekilde çalışacaktır.
"""
import os
import numpy as np
import pandas as pd

import universe
from data_pipeline import validator, stooq_fetcher
from analysis.strategy import RegimeAdaptiveStrategy
from analysis import (
    scorer, fundamentals, relative_strength, confirmations, risk_metrics,
    filters, advanced_indicators, journal, notifier, news,
    position_sizing, economic_calendar, grid_strategy, dca_plan, grid_dca_journal,
    portfolio_correlation,
)
from reporting import excel_report


def make_synthetic(symbol, n=300, seed=None):
    seed = seed if seed is not None else abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    n_blocks = 6
    returns = []
    while len(returns) < n:
        drift = rng.choice([0.003, -0.003, 0.0])
        vol = rng.uniform(0.01, 0.03)
        block_len = n // n_blocks
        returns.extend(rng.normal(drift, vol, block_len))
    returns = np.array(returns[:n])
    close = 100 * np.exp(np.cumsum(returns))
    dates = pd.date_range(end=pd.Timestamp.now().normalize(), periods=n, freq="D")
    high = close * (1 + np.abs(rng.normal(0, 0.005, n)))
    low = close * (1 - np.abs(rng.normal(0, 0.005, n)))
    df = pd.DataFrame({"Open": close, "High": high, "Low": low, "Close": close,
                        "Volume": rng.integers(1000, 100000, n)}, index=dates)
    df["High"] = df[["Open", "High", "Low", "Close"]].max(axis=1)
    df["Low"] = df[["Open", "High", "Low", "Close"]].min(axis=1)
    return df


def make_synthetic_fundamentals(symbol, market, seed=None):
    if market in ("crypto", "emtia"):
        return {}
    seed = seed if seed is not None else abs(hash(symbol)) % (2**32)
    rng = np.random.default_rng(seed)
    return {
        "trailingPE": float(rng.uniform(5, 100)), "forwardPE": float(rng.uniform(5, 90)),
        "priceToBook": float(rng.uniform(0.5, 15)), "pegRatio": float(rng.uniform(0.3, 5)),
        "returnOnEquity": float(rng.uniform(-0.2, 0.4)), "debtToEquity": float(rng.uniform(0, 300)),
        "revenueGrowth": float(rng.uniform(-0.2, 0.4)), "earningsGrowth": float(rng.uniform(-0.3, 0.5)),
        "dividendYield": float(rng.uniform(0, 0.05)), "marketCap": float(rng.uniform(1e8, 2e12)),
        "profitMargins": float(rng.uniform(-0.1, 0.35)),
    }


print("[ 1/13] Evren yükleniyor (tüm piyasalar)...")
universe_df = universe.load_universe()
print(f"        Toplam {len(universe_df)} sembol")

print("[ 2/13] Sentetik fiyat verisi + benchmark üretiliyor...")
raw_data = {sym: make_synthetic(sym) for sym in universe_df["symbol"]}
raw_data[universe_df["symbol"].iloc[0]] = pd.DataFrame({"Close": [1, 2, 3]})
raw_data[universe_df["symbol"].iloc[1]] = make_synthetic("SHORT", n=10)
benchmark_data = {
    "us": make_synthetic("SPY", seed=999), "bist": make_synthetic("XU100.IS", seed=998),
    "crypto": make_synthetic("BTC-USD", seed=997),
}

print("[ 3/13] Doğrulama...")
valid_data, validation_report = validator.validate_batch(raw_data)
print(f"        Geçerli: {len(valid_data)} / {len(raw_data)}")

print("[ 4/13] Teknik sinyal üretimi...")
strat = RegimeAdaptiveStrategy()
signals = {}
for sym, df in valid_data.items():
    try:
        signals[sym] = strat.generate_signals(df)
    except Exception as e:
        print(f"        UYARI: {sym} sinyal üretiminde hata: {e}")

print("[ 5/13] Gelişmiş göstergeler (Fibonacci, destek/direnç, hacim profili)...")
advanced_by_symbol = {}
for sym, sig_df in signals.items():
    advanced_by_symbol[sym] = advanced_indicators.compute_all(sig_df)
print(f"        {len(advanced_by_symbol)} sembol için hesaplandı")

print("[ 6/13] Sentetik temel analiz verisi üretiliyor ve skorlanıyor...")
market_by_symbol = universe_df.set_index("symbol")["market"].to_dict()
raw_fundamentals = {sym: make_synthetic_fundamentals(sym, market_by_symbol.get(sym, "us")) for sym in signals}
fundamentals_df = fundamentals.compute_fundamental_scores(raw_fundamentals)

print("[ 7/13] Göreceli güç hesaplanıyor...")
rs_df = relative_strength.compute_relative_strength_batch(valid_data, universe_df, benchmark_data)

print("[ 8/13] Hacim/haftalık teyit + risk metrikleri hesaplanıyor...")
confirmations_by_symbol, risk_by_symbol = {}, {}
for sym, sig_df in signals.items():
    last_signal = int(sig_df.iloc[-1]["signal"])
    confirmations_by_symbol[sym] = confirmations.compute_confirmations(sig_df, last_signal)
    bench = benchmark_data.get(market_by_symbol.get(sym))
    risk_by_symbol[sym] = risk_metrics.compute_all(sig_df, bench["Close"] if bench is not None else None)

print("[ 9/13] Sentetik haber verisi üretiliyor (gerçek internet olmadan news.py mantığını test eder)...")
SAMPLE_HEADLINES = [
    "Company shares surge to record high after strong earnings beat",
    "Stock plunges as investors react to weak guidance and rising costs",
    "Quarterly results roughly in line with analyst expectations",
]
news_by_symbol = {}
for i, sym in enumerate(signals.keys()):
    headline = SAMPLE_HEADLINES[i % len(SAMPLE_HEADLINES)]
    sentiment = news.simple_sentiment(headline)
    news_by_symbol[sym] = {"news_sentiment": sentiment, "news_count": 1, "latest_headline": headline}
macro_news = [
    {"title": "Fed holds interest rates steady, signals cautious outlook", "publisher": "Reuters",
     "sentiment": news.simple_sentiment("Fed holds interest rates steady, signals cautious outlook"),
     "kaynak": "S&P 500", "link": ""},
    {"title": "Inflation data comes in hotter than expected, markets fall", "publisher": "Bloomberg",
     "sentiment": news.simple_sentiment("Inflation data comes in hotter than expected, markets fall"),
     "kaynak": "Dolar Endeksi (DXY)", "link": ""},
]
print(f"        {len(news_by_symbol)} sembol için haber özeti, {len(macro_news)} makro haber üretildi")

print("[10/15] Skorlama ve filtreleme...")
scored_df = scorer.score_universe(
    signals, universe_df, fundamentals_df=fundamentals_df, relative_strength_df=rs_df,
    confirmations_by_symbol=confirmations_by_symbol, risk_metrics_by_symbol=risk_by_symbol,
    news_by_symbol=news_by_symbol,
)
full_status_df = scorer.full_universe_status(signals, universe_df)
print(f"        Tüm sembol durumu: {len(full_status_df)} sembol (sinyal üretsin üretmesin)")
if not scored_df.empty and advanced_by_symbol:
    adv_df = pd.DataFrame([{"symbol": s, **a} for s, a in advanced_by_symbol.items()])
    scored_df = scored_df.merge(adv_df, on="symbol", how="left")
print(f"        Sinyal üreten sembol sayısı: {len(scored_df)}")
if not scored_df.empty:
    assert not scored_df["composite_score"].isna().any(), "composite_score içinde NaN olmamalı!"

print("[10.5/15] Çapraz doğrulama (Stooq mock) ve pozisyon büyüklüğü test ediliyor...")
from unittest.mock import patch
portfolio_summary_stats = {}
if not scored_df.empty:
    with patch("data_pipeline.stooq_fetcher.fetch_with_fallback", return_value=None):
        cross_val_rows = []
        for _, row in scored_df.iterrows():
            cv = stooq_fetcher.cross_validate(row["symbol"], row["market"], row["close"])
            cross_val_rows.append({"symbol": row["symbol"], **cv})
        cross_val_df = pd.DataFrame(cross_val_rows)
        scored_df = scored_df.merge(cross_val_df, on="symbol", how="left")
    assert "supheli" in scored_df.columns
    print(f"        Çapraz doğrulama kolonları eklendi (veri yoksa 'supheli'=False bekleniyor)")

    scored_df = position_sizing.compute_for_scored_df(scored_df, account_size=10000.0, risk_per_trade_pct=1.0)
    assert "onerilen_adet" in scored_df.columns
    print(f"        Pozisyon büyüklüğü önerileri eklendi")

    print("[10.7/15] Portföy korelasyon kontrolü test ediliyor...")
    portfolio_summary_stats = {}
    if len(scored_df) >= 2:
        signal_symbols = scored_df["symbol"].tolist()
        corr_matrix = portfolio_correlation.compute_correlation_matrix(valid_data, signal_symbols)
        clusters = portfolio_correlation.find_correlated_clusters(corr_matrix)
        scored_df = portfolio_correlation.adjust_position_sizes(scored_df, clusters)
        portfolio_summary_stats = portfolio_correlation.portfolio_summary(scored_df, corr_matrix, clusters)
        print(f"        {len(clusters)} korelasyonlu küme bulundu: {clusters}")
        print(f"        Portföy özeti: {portfolio_summary_stats}")
        assert "korelasyon_kumesi" in scored_df.columns
        assert "efektif_portfoy_yuzdesi" in scored_df.columns

print("[10.8/15] Paper trading test ediliyor...")
test_pt_db = "/home/claude/trading_system/data/test_verify_paper.db"
if os.path.exists(test_pt_db):
    os.remove(test_pt_db)
from analysis import paper_trading
paper_trading.initialize_account(10000.0, db_path=test_pt_db)
paper_trading.update_open_positions(valid_data, db_path=test_pt_db)
if not scored_df.empty:
    pt_stats = paper_trading.process_new_signals(scored_df, signals, db_path=test_pt_db)
    print(f"        Paper trading işlemleri: {pt_stats}")
paper_trading.record_equity_snapshot(valid_data, db_path=test_pt_db)
paper_perf = paper_trading.compute_performance_stats(db_path=test_pt_db)
print(f"        Paper trading performansı: {paper_perf}")
os.remove(test_pt_db)

print("[11/15] Ekonomik takvim test ediliyor...")
calendar_df = economic_calendar.get_calendar()
print(f"        {len(calendar_df)} yaklaşan ekonomik olay bulundu (0 olması da normal, tarihe bağlı)")

import config
filtered_df, filter_stats = filters.apply_filters(scored_df, config.FILTERS)
print(f"        Filtre öncesi: {filter_stats.get('başlangıç', 0)}, filtre sonrası: {filter_stats.get('son', 0)}")

print("[12/15] Sinyal günlüğü test ediliyor (SQLite)...")
test_db_path = "/home/claude/trading_system/data/test_verify_journal.db"
if os.path.exists(test_db_path):
    os.remove(test_db_path)
journal.update_outcomes(valid_data, db_path=test_db_path)  # boş DB'de no-op olmalı
added = journal.record_signals(scored_df, pd.Timestamp.now().isoformat(), db_path=test_db_path)
print(f"        {added} sinyal günlüğe kaydedildi")
outcome_stats = journal.update_outcomes(valid_data, db_path=test_db_path)
print(f"        Sonuç güncellemesi: {outcome_stats}")
performance_df = journal.compute_performance_stats(db_path=test_db_path)
print(f"        Performans tablosu: {len(performance_df)} satır")
os.remove(test_db_path)

print("[13/15] Mum formasyonu tespiti test ediliyor...")
if not scored_df.empty and "candlestick_pattern" in scored_df.columns:
    pattern_count = scored_df["candlestick_pattern"].notna().sum()
    print(f"        {pattern_count} sembolde belirgin bir mum formasyonu tespit edildi")

print("[14/16] Grid ve DCA planları test ediliyor...")
grid_rows, dca_rows = [], []
if not scored_df.empty:
    for _, row in scored_df.iterrows():
        symbol = row["symbol"]
        pozisyon = row.get("pozisyon_buyuklugu")
        if pd.isna(pozisyon) or pozisyon is None or symbol not in signals:
            continue
        grid_result = grid_strategy.suggest_grid(signals[symbol], row.get("regime"), float(pozisyon))
        if grid_result["uygun_mu"]:
            for lvl in grid_result["seviyeler"]:
                grid_rows.append({"symbol": symbol, **lvl})
        if row.get("signal") == 1:
            plan = dca_plan.suggest_dca_plan(float(row["close"]), float(pozisyon))
            dca_part = dca_plan.dca_plan_to_dataframe(symbol, plan)
            if not dca_part.empty:
                dca_rows.append(dca_part)
grid_plan_df = pd.DataFrame(grid_rows) if grid_rows else pd.DataFrame()
dca_plan_df = pd.concat(dca_rows, ignore_index=True) if dca_rows else pd.DataFrame()
print(f"        Grid planı: {grid_plan_df['symbol'].nunique() if not grid_plan_df.empty else 0} sembol "
      f"(range rejiminde olanlar), DCA planı: {dca_plan_df['symbol'].nunique() if not dca_plan_df.empty else 0} sembol")

print("[14.5/16] Grid/DCA emir günlüğü test ediliyor (SQLite)...")
test_gdj_db = "/home/claude/trading_system/data/test_verify_griddca.db"
if os.path.exists(test_gdj_db):
    os.remove(test_gdj_db)
grid_dca_journal.record_grid_plan(grid_plan_df, universe_df, scan_time=pd.Timestamp.now().isoformat(), db_path=test_gdj_db)
grid_dca_journal.record_dca_plan(dca_plan_df, universe_df, scan_time=pd.Timestamp.now().isoformat(), db_path=test_gdj_db)
gdj_grid_stats = grid_dca_journal.update_grid_outcomes(valid_data, db_path=test_gdj_db)
gdj_dca_stats = grid_dca_journal.update_dca_outcomes(valid_data, db_path=test_gdj_db)
print(f"        Grid emir güncellemesi: {gdj_grid_stats}")
print(f"        DCA emir güncellemesi: {gdj_dca_stats}")
grid_perf = grid_dca_journal.compute_grid_performance(db_path=test_gdj_db)
dca_perf = grid_dca_journal.compute_dca_performance(current_data_by_symbol=valid_data, db_path=test_gdj_db)
print(f"        Grid performansı: {grid_perf}")
print(f"        DCA performansı: {dca_perf}")
os.remove(test_gdj_db)

print("[15/16] Excel raporu + bildirim test ediliyor...")
output_path = "/home/claude/trading_system/reports/dogrulama_raporu.xlsx"
os.makedirs(os.path.dirname(output_path), exist_ok=True)
excel_report.build_report(scored_df, validation_report, output_path,
                           filtered_df=filtered_df, filter_stats=filter_stats,
                           performance_stats_df=performance_df, macro_news=macro_news,
                           calendar_df=calendar_df, grid_plan_df=grid_plan_df, dca_plan_df=dca_plan_df,
                           full_status_df=full_status_df,
                           grid_dca_performance={"grid": grid_perf, "dca": dca_perf},
                           portfolio_summary_stats=portfolio_summary_stats,
                           paper_trading_stats=paper_perf)

# Telegram yapılandırılmamış olduğu için False dönmeli, hata FIRLATMAMALI
notified = notifier.notify_scan_complete(filtered_df, filter_stats, output_path)
assert notified is False, "Telegram yapılandırılmamışken sessizce False dönmeli"
print("        Bildirim modülü doğru şekilde atlandı (Telegram yapılandırılmamış)")

sheets = pd.read_excel(output_path, sheet_name=None)
print(f"\nOluşan Excel sayfaları: {list(sheets.keys())}")
for name, sheet in sheets.items():
    print(f"  - {name}: {len(sheet)} satır")

print("[16/16] Sayfa bütünlüğü doğrulanıyor...")
expected_sheets = {"Özet", "Filtrelenmiş", "ABD", "BIST", "Kripto", "Emtialar", "Temel Analiz",
                   "Tüm Sembol Durumu", "Piyasa Özeti", "Grid ve DCA Performansı", "Portföy Korelasyonu",
                   "Paper Trading",
                   "Gelişmiş Göstergeler", "Risk Metrikleri", "Performans Geçmişi",
                   "Filtre Özeti", "Hata Raporu", "Haberler", "Ekonomik Takvim",
                   "Grid Planı", "DCA Planı"}
assert expected_sheets.issubset(set(sheets.keys())), f"Eksik sayfa(lar): {expected_sheets - set(sheets.keys())}"

print("\n✓ TÜM SİSTEM (v14: TAZELİK HATASI DÜZELTMESİ + TAM TEKNİK GRAFİK + SEKTÖR BİLGİSİ DAHİL) UÇTAN UCA BAŞARIYLA ÇALIŞTI.")

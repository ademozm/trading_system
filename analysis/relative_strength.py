"""
Göreceli güç (relative strength) — bir hissenin/kripto paranın kendi
piyasasının genel endeksine (benchmark) karşı ne kadar iyi/kötü
performans gösterdiğini ölçer.

Neden önemli: %5 yükselen bir hisse, piyasa %10 yükselmişken aslında
zayıf kalmış demektir; piyasa %2 düşmüşken %5 yükselen hisse ise güçlü.
Sadece mutlak getiriye bakmak bu bağlamı kaçırır.

Benchmark eşlemesi:
  us     -> SPY (S&P 500 ETF)
  bist   -> XU100.IS (BIST 100 endeksi)
  crypto -> BTC-USD (kripto piyasasının genel göstergesi)
"""
import numpy as np
import pandas as pd

BENCHMARKS = {
    "us": "SPY",
    "bist": "XU100.IS",
    "crypto": "BTC-USD",
}


def relative_strength(symbol_close: pd.Series, benchmark_close: pd.Series, lookback: int = 63) -> dict:
    """
    lookback: karşılaştırma penceresi (63 iş günü ~ 3 ay).
    Dönüş: sembol getirisi, benchmark getirisi, aradaki fark (relative strength).
    """
    if len(symbol_close) <= lookback or len(benchmark_close) <= lookback:
        return {"symbol_return_pct": np.nan, "benchmark_return_pct": np.nan, "relative_strength_pct": np.nan}

    sym_ret = (symbol_close.iloc[-1] / symbol_close.iloc[-lookback - 1] - 1) * 100
    bench_ret = (benchmark_close.iloc[-1] / benchmark_close.iloc[-lookback - 1] - 1) * 100

    return {
        "symbol_return_pct": sym_ret,
        "benchmark_return_pct": bench_ret,
        "relative_strength_pct": sym_ret - bench_ret,
    }


def compute_relative_strength_batch(
    data_by_symbol: dict, universe_df: pd.DataFrame, benchmark_data: dict, lookback: int = 63
) -> pd.DataFrame:
    """
    data_by_symbol: symbol -> OHLCV DataFrame
    benchmark_data: market -> benchmark OHLCV DataFrame (BENCHMARKS eşlemesine göre)
    """
    market_by_symbol = universe_df.set_index("symbol")["market"].to_dict()
    rows = []
    for symbol, df in data_by_symbol.items():
        market = market_by_symbol.get(symbol)
        bench_df = benchmark_data.get(market)

        # Sembolün kendisi zaten benchmark ise (örn. BTC-USD'yi BTC-USD'ye kıyaslama)
        if bench_df is None or BENCHMARKS.get(market) == symbol:
            rows.append({"symbol": symbol, "symbol_return_pct": np.nan,
                         "benchmark_return_pct": np.nan, "relative_strength_pct": np.nan})
            continue

        rs = relative_strength(df["Close"], bench_df["Close"], lookback)
        rows.append({"symbol": symbol, **rs})

    return pd.DataFrame(rows)

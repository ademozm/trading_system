"""
Risk metrikleri — bir sembolün ne kadar "riskli" olduğunu tarihsel
veriden ölçer. Skorlamada hem ceza (aşırı risk) hem bağlam (52 haftalık
aralıktaki konumu) olarak kullanılır.
"""
import numpy as np
import pandas as pd


def annualized_volatility(close: pd.Series, trading_days: int = 252) -> float:
    daily_returns = close.pct_change().dropna()
    if len(daily_returns) < 2:
        return np.nan
    return daily_returns.std() * np.sqrt(trading_days)


def max_drawdown(close: pd.Series) -> float:
    running_max = close.cummax()
    drawdown = close / running_max - 1
    return drawdown.min()


def week52_position(close: pd.Series) -> dict:
    """Son fiyatın 52 haftalık (yaklaşık 252 iş günü) aralığındaki konumu."""
    window = close.tail(252)
    high_52w = window.max()
    low_52w = window.min()
    last = close.iloc[-1]
    pct_from_high = (last / high_52w - 1) if high_52w > 0 else np.nan
    pct_from_low = (last / low_52w - 1) if low_52w > 0 else np.nan
    range_position = (last - low_52w) / (high_52w - low_52w) if high_52w > low_52w else np.nan
    return {
        "week52_high": high_52w, "week52_low": low_52w,
        "pct_from_52w_high": pct_from_high * 100 if not np.isnan(pct_from_high) else np.nan,
        "pct_from_52w_low": pct_from_low * 100 if not np.isnan(pct_from_low) else np.nan,
        "week52_range_position": range_position,  # 0 = 52 haftalık dip, 1 = 52 haftalık zirve
    }


def beta(symbol_close: pd.Series, benchmark_close: pd.Series) -> float:
    """Benchmark'a göre beta (sistematik risk). >1: benchmark'tan daha oynak."""
    sym_ret = symbol_close.pct_change().dropna()
    bench_ret = benchmark_close.pct_change().dropna()
    aligned = pd.concat([sym_ret, bench_ret], axis=1, join="inner").dropna()
    if len(aligned) < 30:
        return np.nan
    cov = aligned.iloc[:, 0].cov(aligned.iloc[:, 1])
    var = aligned.iloc[:, 1].var()
    return cov / var if var > 0 else np.nan


def compute_all(df: pd.DataFrame, benchmark_close: pd.Series | None = None) -> dict:
    close = df["Close"]
    out = {
        "volatility_annualized_pct": annualized_volatility(close) * 100,
        "max_drawdown_pct": max_drawdown(close) * 100,
        **week52_position(close),
    }
    if benchmark_close is not None:
        out["beta"] = beta(close, benchmark_close)
    else:
        out["beta"] = np.nan
    return out

"""
Temel analiz (fundamental) verisi.

Sadece hisse senetleri için anlamlıdır (ABD, BIST) — kripto paralarda
P/E, ROE gibi kavramlar yok, bu yüzden kripto için fundamental_score
None döner ve skorlama motoru ağırlığı otomatik olarak diğer bileşenlere
kaydırır (bkz. scorer.py).

yfinance'in .info çağrısı YAVAŞTIR (sembol başına ayrı bir HTTP isteği)
ve bazı alanlar bazı sembollerde eksik olabilir — bu yüzden her alan
tek tek güvenli şekilde okunur, eksikse None bırakılır.
"""
import logging

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger("fundamentals")

FIELDS = [
    "trailingPE", "forwardPE", "priceToBook", "pegRatio",
    "returnOnEquity", "debtToEquity", "revenueGrowth", "earningsGrowth",
    "dividendYield", "marketCap", "profitMargins", "fiftyTwoWeekHigh",
    "fiftyTwoWeekLow",
]

TEXT_FIELDS = ["sector", "industry"]


def fetch_one(symbol: str, market: str) -> dict:
    """Tek sembol için temel veriyi çeker. Kripto için boş dict döner."""
    if market in ("crypto", "emtia"):
        return {}

    result = {f: None for f in FIELDS + TEXT_FIELDS}
    try:
        info = yf.Ticker(symbol).info
        for f in FIELDS:
            val = info.get(f)
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                result[f] = val
        for f in TEXT_FIELDS:
            val = info.get(f)
            if val:
                result[f] = val
    except Exception as e:
        logger.warning(f"{symbol} temel veri çekilemedi: {e}")
    return result


def fetch_batch(universe_df: pd.DataFrame) -> dict:
    """
    universe_df: symbol/market kolonlu DataFrame.
    Dönüş: symbol -> fundamentals dict.
    NOT: Sembol başına ayrı istek olduğu için büyük evrenlerde YAVAŞTIR.
    Gerekirse main_scan.py'de --skip-fundamentals bayrağıyla atlanabilir.
    """
    out = {}
    for _, row in universe_df.iterrows():
        out[row["symbol"]] = fetch_one(row["symbol"], row["market"])
    return out


def _percentile_score(series: pd.Series, higher_is_better: bool) -> pd.Series:
    """NaN'ları yok sayarak yüzdelik dilime çevirir; NaN kalanlar 0.5 (nötr) alır."""
    pct = series.rank(pct=True, na_option="keep")
    if not higher_is_better:
        pct = 1 - pct
    return pct.fillna(0.5)


def compute_fundamental_scores(fundamentals_by_symbol: dict) -> pd.DataFrame:
    """
    Ham temel verileri evren içinde normalize edip 0-1 arası tek bir
    fundamental_score'a indirger. Kripto veya veri eksik sembollerde
    fundamental_score = NaN döner (scorer bunu ağırlık dışı bırakır).
    """
    if not fundamentals_by_symbol:
        return pd.DataFrame(columns=["symbol", "fundamental_score"])

    rows = []
    for symbol, f in fundamentals_by_symbol.items():
        rows.append({"symbol": symbol, **f})
    df = pd.DataFrame(rows).set_index("symbol")

    symbols = list(fundamentals_by_symbol.keys())
    field_cols = [c for c in df.columns if c in FIELDS]
    no_usable_data = df.empty or not field_cols or df[field_cols].isna().all().all()
    if no_usable_data:
        return pd.DataFrame({"symbol": symbols, "fundamental_score": np.nan})

    components = pd.DataFrame(index=df.index)
    if "trailingPE" in df:
        pe = df["trailingPE"].where(df["trailingPE"] > 0)  # negatif PE (zarar eden şirket) hariç
        components["pe_score"] = _percentile_score(pe, higher_is_better=False)
    if "pegRatio" in df:
        peg = df["pegRatio"].where(df["pegRatio"] > 0)
        components["peg_score"] = _percentile_score(peg, higher_is_better=False)
    if "returnOnEquity" in df:
        components["roe_score"] = _percentile_score(df["returnOnEquity"], higher_is_better=True)
    if "debtToEquity" in df:
        components["debt_score"] = _percentile_score(df["debtToEquity"], higher_is_better=False)
    if "revenueGrowth" in df:
        components["rev_growth_score"] = _percentile_score(df["revenueGrowth"], higher_is_better=True)
    if "earningsGrowth" in df:
        components["earn_growth_score"] = _percentile_score(df["earningsGrowth"], higher_is_better=True)
    if "profitMargins" in df:
        components["margin_score"] = _percentile_score(df["profitMargins"], higher_is_better=True)

    # Hiç bileşeni olmayan (tüm alanlar NaN) semboller için fundamental_score = NaN
    has_any_data = df[[c for c in FIELDS if c in df.columns]].notna().any(axis=1)
    fundamental_score = components.mean(axis=1)
    fundamental_score[~has_any_data] = np.nan

    out = df.copy()
    out["fundamental_score"] = fundamental_score
    return out.reset_index()

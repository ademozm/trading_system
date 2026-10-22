import numpy as np
import pandas as pd
import pytest

from analysis import portfolio_correlation as pc


def _make_price_df(returns, start="2026-01-01"):
    close = 100 * np.exp(np.cumsum(returns))
    idx = pd.date_range(start, periods=len(returns) + 1, freq="D")
    close_with_start = np.concatenate([[100], close])
    return pd.DataFrame({
        "Open": close_with_start, "High": close_with_start * 1.01, "Low": close_with_start * 0.99,
        "Close": close_with_start, "Volume": [1000] * len(close_with_start),
    }, index=idx)


def _correlated_pair(n=60, seed=0):
    """İki sembol, neredeyse aynı getirilerle (yüksek korelasyon)."""
    rng = np.random.default_rng(seed)
    base_returns = rng.normal(0, 0.01, n)
    noise = rng.normal(0, 0.0005, n)  # çok küçük gürültü, yüksek korelasyon korunsun
    return {
        "A": _make_price_df(base_returns),
        "B": _make_price_df(base_returns + noise),
    }


def _uncorrelated_pair(n=60, seed=1):
    rng = np.random.default_rng(seed)
    return {
        "C": _make_price_df(rng.normal(0, 0.01, n)),
        "D": _make_price_df(rng.normal(0, 0.01, n + 1)[:n]),  # bağımsız rastgele seri
    }


def test_compute_returns_matrix_aligns_common_dates():
    data = _correlated_pair()
    returns_df = pc.compute_returns_matrix(data, ["A", "B"])
    assert not returns_df.empty
    assert set(returns_df.columns) == {"A", "B"}


def test_compute_returns_matrix_skips_missing_symbol():
    data = _correlated_pair()
    returns_df = pc.compute_returns_matrix(data, ["A", "B", "NONEXISTENT"])
    assert "NONEXISTENT" not in returns_df.columns


def test_compute_returns_matrix_too_few_symbols_returns_empty():
    data = _correlated_pair()
    returns_df = pc.compute_returns_matrix(data, ["A"])
    assert returns_df.empty


def test_compute_correlation_matrix_high_for_correlated_pair():
    data = _correlated_pair()
    corr = pc.compute_correlation_matrix(data, ["A", "B"])
    assert not corr.empty
    assert corr.loc["A", "B"] > 0.9


def test_find_correlated_clusters_detects_high_correlation():
    data = _correlated_pair()
    corr = pc.compute_correlation_matrix(data, ["A", "B"])
    clusters = pc.find_correlated_clusters(corr, threshold=0.7)
    assert len(clusters) == 1
    assert set(clusters[0]) == {"A", "B"}


def test_find_correlated_clusters_empty_for_low_correlation():
    data = _uncorrelated_pair()
    corr = pc.compute_correlation_matrix(data, ["C", "D"])
    if not corr.empty:
        clusters = pc.find_correlated_clusters(corr, threshold=0.9)
        assert clusters == [] or all(len(c) <= 1 for c in clusters)


def test_find_correlated_clusters_empty_matrix_returns_empty_list():
    assert pc.find_correlated_clusters(pd.DataFrame()) == []


def test_find_correlated_clusters_three_way_group():
    n = 60
    rng = np.random.default_rng(0)
    base = rng.normal(0, 0.01, n)
    data = {
        "A": _make_price_df(base),
        "B": _make_price_df(base + rng.normal(0, 0.0005, n)),
        "C": _make_price_df(base + rng.normal(0, 0.0005, n)),
    }
    corr = pc.compute_correlation_matrix(data, ["A", "B", "C"])
    clusters = pc.find_correlated_clusters(corr, threshold=0.7)
    assert len(clusters) == 1
    assert set(clusters[0]) == {"A", "B", "C"}


def _scored_df_sample():
    return pd.DataFrame({
        "symbol": ["A", "B", "C"],
        "signal": [1, 1, 1],
        "onerilen_adet": [10.0, 10.0, 5.0],
        "pozisyon_buyuklugu": [1000.0, 1000.0, 500.0],
        "portfoy_yuzdesi": [10.0, 10.0, 5.0],
    })


def test_adjust_position_sizes_reduces_clustered_positions():
    scored_df = _scored_df_sample()
    clusters = [["A", "B"]]  # A ve B aynı kümede, C bağımsız
    result = pc.adjust_position_sizes(scored_df, clusters)

    a_row = result[result["symbol"] == "A"].iloc[0]
    c_row = result[result["symbol"] == "C"].iloc[0]

    assert a_row["efektif_portfoy_yuzdesi"] == pytest.approx(5.0)  # 10 / 2
    assert c_row["efektif_portfoy_yuzdesi"] == pytest.approx(5.0)  # kümede değil, değişmez
    assert a_row["korelasyon_kumesi"] is not None
    assert c_row["korelasyon_kumesi"] is None


def test_adjust_position_sizes_no_clusters_leaves_unchanged():
    scored_df = _scored_df_sample()
    result = pc.adjust_position_sizes(scored_df, [])
    assert (result["efektif_portfoy_yuzdesi"] == result["portfoy_yuzdesi"]).all()


def test_adjust_position_sizes_empty_df_handled():
    result = pc.adjust_position_sizes(pd.DataFrame(), [["A", "B"]])
    assert result.empty


def test_portfolio_summary_computes_totals():
    scored_df = _scored_df_sample()
    clusters = [["A", "B"]]
    adjusted = pc.adjust_position_sizes(scored_df, clusters)
    data = _correlated_pair()
    corr = pc.compute_correlation_matrix(data, ["A", "B"])
    summary = pc.portfolio_summary(adjusted, corr, clusters)

    assert summary["naif_toplam_portfoy_yuzdesi"] == pytest.approx(25.0)  # 10+10+5
    assert summary["duzeltilmis_toplam_portfoy_yuzdesi"] == pytest.approx(15.0)  # 5+5+5
    assert summary["kume_sayisi"] == 1
    assert summary["uyari"] is True


def test_portfolio_summary_no_clusters_no_warning():
    scored_df = _scored_df_sample()
    adjusted = pc.adjust_position_sizes(scored_df, [])
    summary = pc.portfolio_summary(adjusted, pd.DataFrame(), [])
    assert summary["uyari"] is False
    assert summary["kume_sayisi"] == 0


def test_portfolio_summary_empty_df_handled():
    summary = pc.portfolio_summary(pd.DataFrame(), pd.DataFrame(), [])
    assert "not" in summary

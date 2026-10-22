import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytest

from reporting import dashboard_charts as charts


def _sample_summary_df():
    return pd.DataFrame({
        "Sembol": ["AAPL", "THYAO.IS", "BTC-USD", "TSLA", "SASA.IS"],
        "Piyasa": ["us", "bist", "crypto", "us", "bist"],
        "Skor": [0.7, 0.5, -0.6, -0.3, 0.2],
    })


def _sample_ohlc():
    n = 60
    idx = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n))
    return pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1, "Close": close,
        "Volume": np.random.randint(1000, 5000, n),
    }, index=idx)


def test_market_breakdown_pie_returns_figure_with_data():
    fig = charts.market_breakdown_pie(_sample_summary_df())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1
    assert len(fig.data[0].labels) == 3  # us, bist, crypto


def test_market_breakdown_pie_empty_df_handled():
    fig = charts.market_breakdown_pie(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_score_histogram_returns_figure():
    fig = charts.score_histogram(_sample_summary_df())
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_score_histogram_empty_df_handled():
    fig = charts.score_histogram(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_top_signals_bar_separates_buy_and_sell():
    fig = charts.top_signals_bar(_sample_summary_df(), n=5)
    assert isinstance(fig, go.Figure)
    y_values = list(fig.data[0].y)
    assert "AAPL" in y_values  # en yüksek pozitif skor
    assert "BTC-USD" in y_values  # en düşük negatif skor


def test_top_signals_bar_empty_df_handled():
    fig = charts.top_signals_bar(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_candlestick_chart_with_full_data():
    ohlc = _sample_ohlc()
    ema_fast = ohlc["Close"].ewm(span=12).mean()
    ema_slow = ohlc["Close"].ewm(span=26).mean()
    fig = charts.candlestick_chart(
        ohlc, ema_fast=ema_fast, ema_slow=ema_slow,
        support_levels=[95, 90], resistance_levels=[110, 115],
    )
    assert isinstance(fig, go.Figure)
    # Candlestick + 2 EMA çizgisi = en az 3 trace
    assert len(fig.data) >= 3


def test_candlestick_chart_none_data_handled():
    fig = charts.candlestick_chart(None)
    assert isinstance(fig, go.Figure)


def test_candlestick_chart_empty_data_handled():
    fig = charts.candlestick_chart(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_candlestick_chart_without_optional_overlays():
    ohlc = _sample_ohlc()
    fig = charts.candlestick_chart(ohlc)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1  # sadece mum grafiği


def test_volume_bar_returns_figure():
    fig = charts.volume_bar(_sample_ohlc())
    assert isinstance(fig, go.Figure)
    assert len(fig.data[0].y) == 60


def test_volume_bar_empty_handled():
    fig = charts.volume_bar(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_grid_ladder_chart_with_data():
    grid_df = pd.DataFrame({
        "Seviye": [1, 2, 3], "Al Fiyatı": [95, 97, 99], "Sat Fiyatı": [97, 99, 101],
    })
    fig = charts.grid_ladder_chart(grid_df)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 3


def test_grid_ladder_chart_empty_handled():
    fig = charts.grid_ladder_chart(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_dca_steps_chart_with_data():
    dca_df = pd.DataFrame({
        "Dilim": [1, 2, 3], "Tetik Fiyatı": [100, 95, 90], "Tutar ($)": [250, 250, 250],
    })
    fig = charts.dca_steps_chart(dca_df)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_dca_steps_chart_empty_handled():
    fig = charts.dca_steps_chart(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_correlation_heatmap_returns_figure_with_data():
    corr = pd.DataFrame({"A": [1.0, 0.8], "B": [0.8, 1.0]}, index=["A", "B"])
    fig = charts.correlation_heatmap(corr)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) == 1


def test_correlation_heatmap_empty_handled():
    fig = charts.correlation_heatmap(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_correlation_heatmap_none_handled():
    fig = charts.correlation_heatmap(None)
    assert isinstance(fig, go.Figure)


def test_full_technical_chart_returns_figure_with_all_panels():
    ohlc = _sample_ohlc()
    fig = charts.full_technical_chart(ohlc)
    assert isinstance(fig, go.Figure)
    assert len(fig.data) >= 10


def test_full_technical_chart_with_support_resistance():
    ohlc = _sample_ohlc()
    fig = charts.full_technical_chart(ohlc, support_levels=[95, 90], resistance_levels=[110, 115])
    assert isinstance(fig, go.Figure)


def test_full_technical_chart_empty_data_handled():
    fig = charts.full_technical_chart(pd.DataFrame())
    assert isinstance(fig, go.Figure)


def test_full_technical_chart_none_handled():
    fig = charts.full_technical_chart(None)
    assert isinstance(fig, go.Figure)


def test_full_technical_chart_too_few_rows_handled():
    fig = charts.full_technical_chart(_sample_ohlc().head(3))
    assert isinstance(fig, go.Figure)

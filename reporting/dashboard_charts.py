"""
Dashboard grafik üretim fonksiyonları.

Bu modül BİLEREK Streamlit'ten bağımsız tutuldu — her fonksiyon saf bir
DataFrame alıp bir plotly Figure döndürür. Bu sayede pytest ile Streamlit
çalıştırmadan (tarayıcı/etkileşim gerekmeden) test edilebiliyor. app.py
sadece bu fonksiyonları çağırıp st.plotly_chart() ile ekrana basıyor.
"""
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

COLOR_BUY = "#16a34a"
COLOR_SELL = "#dc2626"
COLOR_NEUTRAL = "#6b7280"
MARKET_COLORS = {"us": "#2563eb", "bist": "#dc2626", "crypto": "#f59e0b", "emtia": "#eab308"}


def market_breakdown_pie(df: pd.DataFrame, market_col: str = "Piyasa") -> go.Figure:
    """Piyasa bazlı sinyal dağılımı (pasta grafik)."""
    if df.empty or market_col not in df.columns:
        return go.Figure().update_layout(title="Veri yok")
    counts = df[market_col].value_counts()
    fig = go.Figure(data=[go.Pie(
        labels=counts.index.tolist(), values=counts.values.tolist(),
        hole=0.45, marker=dict(colors=[MARKET_COLORS.get(m, COLOR_NEUTRAL) for m in counts.index]),
    )])
    fig.update_layout(title="Piyasa Dağılımı", margin=dict(t=40, b=0, l=0, r=0), height=320)
    return fig


def score_histogram(df: pd.DataFrame, score_col: str = "Skor") -> go.Figure:
    """Bileşik skor dağılımı (histogram) — -1 (güçlü sat) ile +1 (güçlü al) arası."""
    if df.empty or score_col not in df.columns:
        return go.Figure().update_layout(title="Veri yok")
    fig = go.Figure(data=[go.Histogram(
        x=df[score_col], nbinsx=20,
        marker=dict(color=df[score_col], colorscale="RdYlGn", cmin=-1, cmax=1),
    )])
    fig.update_layout(title="Skor Dağılımı", xaxis_title="Bileşik Skor", yaxis_title="Sembol Sayısı",
                       margin=dict(t=40, b=40, l=40, r=20), height=320)
    return fig


def top_signals_bar(df: pd.DataFrame, n: int = 10, symbol_col: str = "Sembol", score_col: str = "Skor") -> go.Figure:
    """En iyi N AL ve en iyi N SAT sinyalini yatay çubuk grafikte gösterir."""
    if df.empty or symbol_col not in df.columns or score_col not in df.columns:
        return go.Figure().update_layout(title="Veri yok")

    top_buy = df[df[score_col] > 0].nlargest(n, score_col)
    top_sell = df[df[score_col] < 0].nsmallest(n, score_col)
    combined = pd.concat([top_sell.sort_values(score_col), top_buy.sort_values(score_col)])

    colors = [COLOR_SELL if v < 0 else COLOR_BUY for v in combined[score_col]]
    fig = go.Figure(data=[go.Bar(
        x=combined[score_col], y=combined[symbol_col], orientation="h",
        marker=dict(color=colors),
    )])
    fig.update_layout(title=f"En İyi {n} AL / En İyi {n} SAT", xaxis_title="Skor",
                       margin=dict(t=40, b=40, l=100, r=20), height=max(320, 22 * len(combined)))
    return fig


def full_technical_chart(
    ohlc_df: pd.DataFrame,
    support_levels: list = None,
    resistance_levels: list = None,
    title: str = "Teknik Analiz",
) -> go.Figure:
    """Fiyat+EMA+Bollinger+destek/direnç, hacim, RSI, MACD, ADX - tek grafikte."""
    if ohlc_df is None or ohlc_df.empty or len(ohlc_df) < 5:
        return go.Figure().update_layout(title="Veri yok veya yetersiz (en az birkaç mum gerekli)")

    from analysis import indicators as ind

    close = ohlc_df["Close"]
    ema_fast = ind.ema(close, 12)
    ema_slow = ind.ema(close, 26)
    bb_upper, bb_mid, bb_lower = ind.bollinger_bands(close)
    rsi_series = ind.rsi(close)
    macd_line, macd_signal, macd_hist = ind.macd(close)
    adx_series, _, _ = ind.adx(ohlc_df)

    fig = make_subplots(
        rows=5, cols=1, shared_xaxes=True,
        row_heights=[0.40, 0.12, 0.16, 0.16, 0.16],
        vertical_spacing=0.03,
        subplot_titles=("Fiyat + EMA(12/26) + Bollinger Bantları", "Hacim",
                         "RSI (14)", "MACD (12/26/9)", "ADX (14)"),
    )

    fig.add_trace(go.Candlestick(
        x=ohlc_df.index, open=ohlc_df["Open"], high=ohlc_df["High"],
        low=ohlc_df["Low"], close=ohlc_df["Close"], name="Fiyat",
        increasing_line_color=COLOR_BUY, decreasing_line_color=COLOR_SELL,
    ), row=1, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=ema_fast, name="EMA 12",
                              line=dict(color="#3b82f6", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=ema_slow, name="EMA 26",
                              line=dict(color="#f97316", width=1.2)), row=1, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=bb_upper, name="BB Üst",
                              line=dict(color="#9ca3af", width=1, dash="dot")), row=1, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=bb_lower, name="BB Alt",
                              line=dict(color="#9ca3af", width=1, dash="dot"),
                              fill="tonexty", fillcolor="rgba(156,163,175,0.08)"), row=1, col=1)

    for level in (support_levels or []):
        fig.add_hline(y=level, line=dict(color=COLOR_BUY, width=1, dash="dot"), opacity=0.5, row=1, col=1)
    for level in (resistance_levels or []):
        fig.add_hline(y=level, line=dict(color=COLOR_SELL, width=1, dash="dot"), opacity=0.5, row=1, col=1)

    vol_colors = [COLOR_BUY if c >= o else COLOR_SELL for o, c in zip(ohlc_df["Open"], ohlc_df["Close"])]
    fig.add_trace(go.Bar(x=ohlc_df.index, y=ohlc_df["Volume"], marker=dict(color=vol_colors),
                          showlegend=False), row=2, col=1)

    fig.add_trace(go.Scatter(x=ohlc_df.index, y=rsi_series, name="RSI",
                              line=dict(color="#8b5cf6", width=1.3)), row=3, col=1)
    fig.add_hline(y=70, line=dict(color=COLOR_SELL, width=1, dash="dash"), opacity=0.6, row=3, col=1)
    fig.add_hline(y=30, line=dict(color=COLOR_BUY, width=1, dash="dash"), opacity=0.6, row=3, col=1)
    fig.update_yaxes(range=[0, 100], row=3, col=1)

    macd_colors = [COLOR_BUY if v >= 0 else COLOR_SELL for v in macd_hist.fillna(0)]
    fig.add_trace(go.Bar(x=ohlc_df.index, y=macd_hist, name="MACD Hist",
                          marker=dict(color=macd_colors), showlegend=False), row=4, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=macd_line, name="MACD",
                              line=dict(color="#3b82f6", width=1.2)), row=4, col=1)
    fig.add_trace(go.Scatter(x=ohlc_df.index, y=macd_signal, name="Sinyal",
                              line=dict(color="#f97316", width=1.2)), row=4, col=1)

    fig.add_trace(go.Scatter(x=ohlc_df.index, y=adx_series, name="ADX",
                              line=dict(color="#111827", width=1.3)), row=5, col=1)
    fig.add_hline(y=22, line=dict(color="#6b7280", width=1, dash="dash"), opacity=0.6, row=5, col=1)

    fig.update_layout(
        title=title, height=950, margin=dict(t=60, b=20, l=20, r=20),
        legend=dict(orientation="h", yanchor="bottom", y=1.0),
    )
    fig.update_xaxes(rangeslider_visible=False, row=1, col=1)
    return fig


def candlestick_chart(
    ohlc_df: pd.DataFrame,
    ema_fast: pd.Series = None,
    ema_slow: pd.Series = None,
    support_levels: list = None,
    resistance_levels: list = None,
    title: str = "Fiyat Grafiği",
) -> go.Figure:
    """
    ohlc_df: Open/High/Low/Close/Volume kolonlu, tarih indeksli DataFrame.
    Mum grafiği + EMA çizgileri + destek/direnç yatay çizgileri + hacim alt grafiği.
    """
    if ohlc_df is None or ohlc_df.empty:
        return go.Figure().update_layout(title="Veri yok (bu sembol için önbellekte fiyat verisi bulunamadı)")

    fig = go.Figure()
    fig.add_trace(go.Candlestick(
        x=ohlc_df.index, open=ohlc_df["Open"], high=ohlc_df["High"],
        low=ohlc_df["Low"], close=ohlc_df["Close"], name="Fiyat",
        increasing_line_color=COLOR_BUY, decreasing_line_color=COLOR_SELL,
    ))

    if ema_fast is not None:
        fig.add_trace(go.Scatter(x=ohlc_df.index, y=ema_fast, name="EMA Hızlı",
                                  line=dict(color="#3b82f6", width=1.3)))
    if ema_slow is not None:
        fig.add_trace(go.Scatter(x=ohlc_df.index, y=ema_slow, name="EMA Yavaş",
                                  line=dict(color="#f97316", width=1.3)))

    for level in (support_levels or []):
        fig.add_hline(y=level, line=dict(color=COLOR_BUY, width=1, dash="dot"), opacity=0.5)
    for level in (resistance_levels or []):
        fig.add_hline(y=level, line=dict(color=COLOR_SELL, width=1, dash="dot"), opacity=0.5)

    fig.update_layout(title=title, xaxis_rangeslider_visible=False,
                       margin=dict(t=40, b=20, l=20, r=20), height=480,
                       legend=dict(orientation="h", yanchor="bottom", y=1.02))
    return fig


def volume_bar(ohlc_df: pd.DataFrame) -> go.Figure:
    if ohlc_df is None or ohlc_df.empty:
        return go.Figure().update_layout(title="Veri yok")
    colors = [COLOR_BUY if c >= o else COLOR_SELL for o, c in zip(ohlc_df["Open"], ohlc_df["Close"])]
    fig = go.Figure(data=[go.Bar(x=ohlc_df.index, y=ohlc_df["Volume"], marker=dict(color=colors))])
    fig.update_layout(title="Hacim", margin=dict(t=30, b=20, l=20, r=20), height=150)
    return fig


def correlation_heatmap(corr_matrix: pd.DataFrame) -> go.Figure:
    """Sinyal üreten semboller arası korelasyon matrisini ısı haritası olarak gösterir."""
    if corr_matrix is None or corr_matrix.empty:
        return go.Figure().update_layout(title="Yeterli veri yok (en az 2 sinyal + yeterli fiyat geçmişi gerekli)")

    fig = go.Figure(data=go.Heatmap(
        z=corr_matrix.values, x=corr_matrix.columns.tolist(), y=corr_matrix.index.tolist(),
        colorscale="RdYlGn", zmin=-1, zmax=1, text=corr_matrix.round(2).values,
        texttemplate="%{text}", colorbar=dict(title="Korelasyon"),
    ))
    fig.update_layout(title="Sinyal Sembolleri Arası Korelasyon Matrisi",
                       margin=dict(t=40, b=20, l=20, r=20),
                       height=max(320, 30 * len(corr_matrix)))
    return fig


def grid_ladder_chart(grid_df_symbol: pd.DataFrame) -> go.Figure:
    """Bir sembolün grid seviyelerini merdiven (yatay çubuk) olarak gösterir."""
    if grid_df_symbol is None or grid_df_symbol.empty:
        return go.Figure().update_layout(title="Bu sembol için grid planı yok (trend rejiminde olabilir)")

    fig = go.Figure()
    for _, row in grid_df_symbol.iterrows():
        fig.add_trace(go.Scatter(
            x=[row["Al Fiyatı"], row["Sat Fiyatı"]], y=[row["Seviye"], row["Seviye"]],
            mode="lines+markers", line=dict(color="#3b82f6", width=6),
            marker=dict(size=9, color=[COLOR_BUY, COLOR_SELL]),
            showlegend=False,
        ))
    fig.update_layout(title="Grid Seviyeleri (yeşil=al, kırmızı=sat)", xaxis_title="Fiyat",
                       yaxis_title="Seviye", margin=dict(t=40, b=40, l=40, r=20), height=320)
    return fig


def dca_steps_chart(dca_df_symbol: pd.DataFrame) -> go.Figure:
    """Bir sembolün DCA dilimlerini basamaklı çizgi olarak gösterir."""
    if dca_df_symbol is None or dca_df_symbol.empty:
        return go.Figure().update_layout(title="Bu sembol için DCA planı yok")

    fig = go.Figure(data=[go.Scatter(
        x=dca_df_symbol["Dilim"], y=dca_df_symbol["Tetik Fiyatı"],
        mode="lines+markers+text", line=dict(color="#3b82f6", shape="hv"),
        marker=dict(size=10, color=COLOR_BUY),
        text=[f"${v:,.0f}" for v in dca_df_symbol["Tutar ($)"]], textposition="top center",
    )])
    fig.update_layout(title="DCA Dilimleri (fiyat düştükçe kademeli alım)",
                       xaxis_title="Dilim No", yaxis_title="Tetik Fiyatı",
                       margin=dict(t=40, b=40, l=40, r=20), height=320)
    return fig

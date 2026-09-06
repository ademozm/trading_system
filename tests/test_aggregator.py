"""
tests/test_aggregator.py
==========================
Katman 3e'nin (sinyal toplayıcı) farklı kaynaklardan gelen sinyalleri
doğru birleştirdiğini doğrulayan testler.
"""

from __future__ import annotations

from signals.aggregator import AggregatorConfig, RawSignal, SignalAggregator, infer_asset_class


def test_infer_asset_class_detects_crypto_and_equity() -> None:
    assert infer_asset_class("BTC/USDT") == "crypto"
    assert infer_asset_class("AAPL") == "equity"
    assert infer_asset_class("MSFT") == "equity"


def test_aggregate_infers_asset_class_when_not_given() -> None:
    agg = SignalAggregator(config=AggregatorConfig(min_score_threshold=0.3))
    candidate = agg.aggregate(
        [RawSignal(source="classic_sma", symbol="AAPL", side="long", confidence=0.8)]
    )
    assert candidate is not None
    assert candidate.asset_class == "equity"


def test_aggregate_respects_explicit_asset_class_override() -> None:
    agg = SignalAggregator(config=AggregatorConfig(min_score_threshold=0.3))
    candidate = agg.aggregate(
        [RawSignal(source="classic_sma", symbol="AAPL", side="long", confidence=0.8)],
        asset_class="equity_override_test",
    )
    assert candidate is not None
    assert candidate.asset_class == "equity_override_test"


def test_single_strong_signal_produces_candidate() -> None:
    agg = SignalAggregator(config=AggregatorConfig(min_score_threshold=0.3))
    signals = [
        RawSignal(source="classic_sma", symbol="BTC/USDT", side="long", confidence=0.8),
    ]
    candidate = agg.aggregate(signals)
    assert candidate is not None
    assert candidate.side == "long"
    assert candidate.symbol == "BTC/USDT"


def test_conflicting_signals_can_cancel_out() -> None:
    agg = SignalAggregator(
        config=AggregatorConfig(
            weights={"classic_sma": 1.0, "ml_gbm": 1.0},
            min_score_threshold=0.6,
        )
    )
    signals = [
        RawSignal(source="classic_sma", symbol="BTC/USDT", side="long", confidence=0.5),
        RawSignal(source="ml_gbm", symbol="BTC/USDT", side="short", confidence=0.5),
    ]
    # Eşit ağırlıklı zıt sinyaller -> hiçbir yön eşik değeri geçemez
    candidate = agg.aggregate(signals)
    assert candidate is None


def test_weak_signal_below_threshold_produces_no_candidate() -> None:
    agg = SignalAggregator(config=AggregatorConfig(min_score_threshold=0.9))
    signals = [
        RawSignal(source="classic_sma", symbol="ETH/USDT", side="long", confidence=0.4),
    ]
    candidate = agg.aggregate(signals)
    assert candidate is None


def test_mixed_symbols_raises_error() -> None:
    agg = SignalAggregator()
    signals = [
        RawSignal(source="classic_sma", symbol="BTC/USDT", side="long", confidence=0.8),
        RawSignal(source="ml_gbm", symbol="ETH/USDT", side="long", confidence=0.8),
    ]
    try:
        agg.aggregate(signals)
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_empty_signals_returns_none() -> None:
    agg = SignalAggregator()
    assert agg.aggregate([]) is None

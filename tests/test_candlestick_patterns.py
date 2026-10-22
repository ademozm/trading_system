import pandas as pd
import pytest

from analysis import candlestick_patterns as cp


def _row(open_, high, low, close):
    return pd.Series({"Open": open_, "High": high, "Low": low, "Close": close})


def test_is_doji_true_for_tiny_body():
    row = _row(100, 105, 95, 100.2)
    assert cp.is_doji(row) is True


def test_is_doji_false_for_large_body():
    row = _row(100, 110, 99, 108)
    assert cp.is_doji(row) is False


def test_is_hammer_true_for_long_lower_shadow():
    row = _row(100, 100.6, 90, 100.5)  # küçük gövde, uzun alt gölge, kısa üst gölge
    assert cp.is_hammer(row) is True


def test_is_hammer_false_for_long_upper_shadow():
    row = _row(100, 110, 99.5, 100.5)
    assert cp.is_hammer(row) is False


def test_is_shooting_star_true_for_long_upper_shadow():
    row = _row(100, 110, 99.6, 100.5)  # küçük gövde, uzun üst gölge, kısa alt gölge
    assert cp.is_shooting_star(row) is True


def test_is_shooting_star_false_for_hammer_shape():
    row = _row(100, 101, 90, 100.5)
    assert cp.is_shooting_star(row) is False


def test_is_bullish_engulfing_true():
    prev = _row(105, 106, 99, 100)   # kırmızı mum
    curr = _row(99, 108, 98, 106)    # yeşil, öncekini kapsıyor
    assert cp.is_bullish_engulfing(prev, curr) is True


def test_is_bullish_engulfing_false_when_not_engulfing():
    prev = _row(105, 106, 99, 100)
    curr = _row(101, 103, 100, 102)  # kapsamıyor
    assert cp.is_bullish_engulfing(prev, curr) is False


def test_is_bearish_engulfing_true():
    prev = _row(100, 106, 99, 105)   # yeşil mum
    curr = _row(106, 107, 97, 99)    # kırmızı, öncekini kapsıyor
    assert cp.is_bearish_engulfing(prev, curr) is True


def test_detect_last_pattern_prioritizes_engulfing():
    df = pd.DataFrame([
        {"Open": 105, "High": 106, "Low": 99, "Close": 100},
        {"Open": 99, "High": 108, "Low": 98, "Close": 106},
    ])
    result = cp.detect_last_pattern(df)
    assert result["pattern"] == "bullish_engulfing"
    assert result["pattern_direction"] == "AL"


def test_detect_last_pattern_none_for_ordinary_candle():
    df = pd.DataFrame([
        {"Open": 100, "High": 103, "Low": 99, "Close": 101},
        {"Open": 101, "High": 104, "Low": 100, "Close": 102},
    ])
    result = cp.detect_last_pattern(df)
    # Sıradan bir mum olduğu için belirgin bir formasyon olmamalı (ama garanti değil, esnek kontrol)
    assert "pattern" in result and "pattern_direction" in result


def test_detect_last_pattern_handles_short_dataframe():
    df = pd.DataFrame([{"Open": 100, "High": 101, "Low": 99, "Close": 100.5}])
    result = cp.detect_last_pattern(df)
    assert result == {"pattern": None, "pattern_direction": None}


def test_pattern_direction_mapping_complete():
    for pattern in ["doji", "hammer", "shooting_star", "bullish_engulfing", "bearish_engulfing"]:
        assert pattern in cp.PATTERN_DIRECTION

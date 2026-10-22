import numpy as np
import pandas as pd
import pytest

import config
from data_pipeline.validator import validate, validate_batch


def make_good_df(n=100):
    dates = pd.date_range(end=pd.Timestamp.now(), periods=n, freq="D")
    close = 100 + np.cumsum(np.random.default_rng(0).normal(0, 1, n))
    df = pd.DataFrame({
        "Open": close, "High": close + 1, "Low": close - 1,
        "Close": close, "Volume": 1000,
    }, index=dates)
    return df


def test_valid_data_passes():
    df = make_good_df()
    result = validate("TEST", df)
    assert result.is_valid


def test_empty_dataframe_fails():
    result = validate("TEST", pd.DataFrame())
    assert not result.is_valid
    assert "boş" in result.reasons[0].lower()


def test_none_fails():
    result = validate("TEST", None)
    assert not result.is_valid


def test_missing_columns_fails():
    df = pd.DataFrame({"Close": [1, 2, 3]})
    result = validate("TEST", df)
    assert not result.is_valid


def test_too_few_rows_fails():
    df = make_good_df(n=10)  # config.MIN_ROWS_REQUIRED'dan az
    result = validate("TEST", df)
    assert not result.is_valid
    assert any("Yetersiz veri" in r for r in result.reasons)


def test_nan_values_fail():
    df = make_good_df()
    df.loc[df.index[5], "Close"] = np.nan
    result = validate("TEST", df)
    assert not result.is_valid


def test_negative_price_fails():
    df = make_good_df()
    df.loc[df.index[5], "Close"] = -10
    result = validate("TEST", df)
    assert not result.is_valid


def test_high_less_than_low_fails():
    df = make_good_df()
    df.loc[df.index[5], "High"] = df.loc[df.index[5], "Low"] - 5
    result = validate("TEST", df)
    assert not result.is_valid


def test_extreme_price_jump_flagged_but_not_hard_fail():
    df = make_good_df()
    df.loc[df.index[50], "Close"] = df.loc[df.index[49], "Close"] * 3  # %200 sıçrama
    result = validate("TEST", df)
    # Şüpheli olarak işaretlenmeli ama tek başına hard-fail değil (config'e göre)
    assert any("şüpheli" in r for r in result.reasons)


def test_non_datetime_index_fails_gracefully_without_crashing():
    # RangeIndex (varsayılan integer index) ile veri gelirse çökmemeli,
    # doğrulamadan geçmemeli.
    df = pd.DataFrame({
        "Open": [100] * 80, "High": [101] * 80,
        "Low": [99] * 80, "Close": [100] * 80, "Volume": [1000] * 80,
    })  # index atanmadı -> varsayılan RangeIndex
    result = validate("TEST", df)
    assert not result.is_valid
    assert any("tarih formatında" in r for r in result.reasons)


def test_validate_batch_separates_valid_and_invalid():
    good = make_good_df()
    bad = pd.DataFrame({"Close": [1, 2]})
    data = {"GOOD": good, "BAD": bad}
    valid_data, report = validate_batch(data)
    assert "GOOD" in valid_data
    assert "BAD" not in valid_data
    assert report["BAD"].is_valid is False
    assert report["GOOD"].is_valid is True

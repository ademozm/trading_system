import pandas as pd
import pytest

from analysis import dca_plan


def test_suggest_dca_plan_basic():
    plan = dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=4, drawdown_step_pct=5.0)
    assert len(plan) == 4
    assert plan[0]["tetik_fiyati"] == 100.0
    assert plan[0]["fiyat_dususu_pct"] == 0.0
    assert plan[1]["tetik_fiyati"] == 95.0
    assert plan[1]["fiyat_dususu_pct"] == 5.0
    assert plan[3]["tetik_fiyati"] == 85.0


def test_suggest_dca_plan_tranches_equal_value():
    plan = dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=4)
    for tranche in plan:
        assert tranche["tutar"] == pytest.approx(250.0)


def test_suggest_dca_plan_cumulative_sums_correctly():
    plan = dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=4)
    assert plan[-1]["kumulatif_tutar"] == pytest.approx(1000.0)


def test_suggest_dca_plan_prices_decreasing():
    plan = dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=5, drawdown_step_pct=3.0)
    prices = [t["tetik_fiyati"] for t in plan]
    assert prices == sorted(prices, reverse=True)


def test_suggest_dca_plan_invalid_inputs_return_empty():
    assert dca_plan.suggest_dca_plan(entry_price=0, total_position_value=1000) == []
    assert dca_plan.suggest_dca_plan(entry_price=100, total_position_value=0) == []
    assert dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=0) == []


def test_dca_plan_to_dataframe_includes_symbol():
    plan = dca_plan.suggest_dca_plan(entry_price=100, total_position_value=1000, num_tranches=2)
    df = dca_plan.dca_plan_to_dataframe("AAPL", plan)
    assert not df.empty
    assert (df["symbol"] == "AAPL").all()
    assert len(df) == 2


def test_dca_plan_to_dataframe_empty_plan():
    df = dca_plan.dca_plan_to_dataframe("AAPL", [])
    assert df.empty

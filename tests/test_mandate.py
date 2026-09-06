"""
tests/test_mandate.py
======================
Katman 4'ün (risk yönetimi) doğru çalıştığını doğrulayan birim testleri.
Bunlar hiçbir dış servise (borsa, LLM API'si) bağımlı değildir — bu
yüzden `pytest` kurulu olduğu sürece internet erişimi olmadan da
çalıştırılabilir.

Çalıştırma: `pytest tests/test_mandate.py -v`
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest
import yaml

from risk.mandate import Mandate, load_mandate
from risk.risk_manager import CandidateTrade, RejectionReason, RiskManager


VALID_MANDATE_DICT = {
    "symbol_universe": ["BTC/USDT", "ETH/USDT"],
    "max_position_size_pct": 0.02,
    "max_total_exposure_pct": 0.30,
    "max_leverage": 1.0,
    "daily_loss_limit_pct": 0.03,
    "max_consecutive_losses_per_symbol": 3,
    "kill_switch_file": "STOP_TRADING",
    "approval_timeout_seconds": 300,
    "per_asset_class": {},
}


def test_mandate_loads_valid_yaml(tmp_path: Path) -> None:
    mandate_file = tmp_path / "mandate.yaml"
    mandate_file.write_text(yaml.dump(VALID_MANDATE_DICT), encoding="utf-8")

    mandate = load_mandate(mandate_file)
    assert mandate.symbol_universe == ["BTC/USDT", "ETH/USDT"]
    assert mandate.is_symbol_allowed("BTC/USDT")
    assert not mandate.is_symbol_allowed("DOGE/USDT")


def test_mandate_rejects_duplicate_symbols() -> None:
    bad = dict(VALID_MANDATE_DICT, symbol_universe=["BTC/USDT", "BTC/USDT"])
    with pytest.raises(Exception):
        Mandate(**bad)


def test_mandate_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_mandate(tmp_path / "yok.yaml")


def test_kill_switch_detection(tmp_path: Path) -> None:
    mandate = Mandate(**VALID_MANDATE_DICT)
    assert not mandate.is_kill_switch_active(base_path=tmp_path)

    (tmp_path / "STOP_TRADING").touch()
    assert mandate.is_kill_switch_active(base_path=tmp_path)


def _make_risk_manager(**overrides) -> RiskManager:
    mandate = Mandate(**VALID_MANDATE_DICT)
    defaults = dict(
        mandate=mandate,
        current_total_exposure_pct=0.0,
        current_daily_pnl_pct=0.0,
        symbol_consecutive_losses={},
        base_path=".",
    )
    defaults.update(overrides)
    return RiskManager(**defaults)


def test_risk_manager_approves_valid_trade(tmp_path: Path) -> None:
    rm = _make_risk_manager(base_path=str(tmp_path))
    trade = CandidateTrade(
        symbol="BTC/USDT", side="long", asset_class="crypto",
        confidence=0.8, rationale="test",
    )
    result = rm.check(trade)
    assert result.approved
    assert result.order_draft is not None
    assert result.order_draft.position_size_pct <= rm.mandate.max_position_size_pct


def test_risk_manager_rejects_symbol_outside_universe(tmp_path: Path) -> None:
    rm = _make_risk_manager(base_path=str(tmp_path))
    trade = CandidateTrade(
        symbol="DOGE/USDT", side="long", asset_class="crypto",
        confidence=0.8, rationale="test",
    )
    result = rm.check(trade)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.SYMBOL_NOT_IN_UNIVERSE


def test_risk_manager_respects_kill_switch(tmp_path: Path) -> None:
    (tmp_path / "STOP_TRADING").touch()
    rm = _make_risk_manager(base_path=str(tmp_path))
    trade = CandidateTrade(
        symbol="BTC/USDT", side="long", asset_class="crypto",
        confidence=0.8, rationale="test",
    )
    result = rm.check(trade)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.KILL_SWITCH_ACTIVE


def test_risk_manager_respects_daily_loss_limit(tmp_path: Path) -> None:
    rm = _make_risk_manager(base_path=str(tmp_path), current_daily_pnl_pct=-0.05)
    trade = CandidateTrade(
        symbol="BTC/USDT", side="long", asset_class="crypto",
        confidence=0.8, rationale="test",
    )
    result = rm.check(trade)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.DAILY_LOSS_LIMIT_HIT


def test_risk_manager_respects_exposure_limit(tmp_path: Path) -> None:
    rm = _make_risk_manager(base_path=str(tmp_path), current_total_exposure_pct=0.29)
    trade = CandidateTrade(
        symbol="BTC/USDT", side="long", asset_class="crypto",
        confidence=1.0, rationale="test",
    )
    result = rm.check(trade)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.EXPOSURE_LIMIT_HIT


def test_risk_manager_respects_symbol_cooldown(tmp_path: Path) -> None:
    rm = _make_risk_manager(
        base_path=str(tmp_path),
        symbol_consecutive_losses={"BTC/USDT": 3},
    )
    trade = CandidateTrade(
        symbol="BTC/USDT", side="long", asset_class="crypto",
        confidence=0.8, rationale="test",
    )
    result = rm.check(trade)
    assert not result.approved
    assert result.rejection_reason == RejectionReason.SYMBOL_COOLDOWN

"""
Katman 4 — Risk Yönetimi: Mandate Şeması
=========================================
Bu modül, config/mandate.yaml dosyasını okuyup Pydantic ile doğrular.
Amaç: yanlış/eksik bir mandate değeriyle sistemin sessizce yanlış
davranmasını önlemek — şema hatalıysa sistem BAŞLAMAZ (fail-closed).

İlham: Vibe-Trading'in "mandate-gated" emir modeli (sembol evreni,
pozisyon boyutu, maruziyet, kaldıraç, günlük kayıp tavanı, kill-switch).
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List

import yaml
from pydantic import BaseModel, Field, field_validator


class AssetClassOverride(BaseModel):
    """Varlık sınıfına özel override'lar (opsiyonel)."""

    max_leverage: float = Field(gt=0)


class MarketMakingMandate(BaseModel):
    """
    Katman 3d (piyasa yapıcılığı) için AYRI risk sınırları. Yön-tahmin
    stratejilerinin (symbol_universe, max_position_size_pct vb.) buraya
    hiçbir etkisi yoktur — bkz. mm_strategy.py'deki mimari not.
    """

    enabled: bool = False
    symbols: List[str] = Field(default_factory=list)
    max_inventory_per_symbol: float = Field(default=1.0, gt=0)
    gamma: float = Field(default=0.1, gt=0)
    kappa: float = Field(default=1.5, gt=0)
    min_spread_bps: float = Field(default=5.0, ge=0)


class Mandate(BaseModel):
    """Sistem genelinde geçerli risk/yetki sınırları."""

    symbol_universe: List[str] = Field(min_length=1)
    max_position_size_pct: float = Field(gt=0, le=1.0)
    max_total_exposure_pct: float = Field(gt=0, le=1.0)
    max_leverage: float = Field(gt=0)
    daily_loss_limit_pct: float = Field(gt=0, le=1.0)
    max_consecutive_losses_per_symbol: int = Field(gt=0)
    kill_switch_file: str
    approval_timeout_seconds: int = Field(gt=0)
    per_asset_class: Dict[str, AssetClassOverride] = Field(default_factory=dict)
    market_making: MarketMakingMandate = Field(default_factory=MarketMakingMandate)

    @field_validator("symbol_universe")
    @classmethod
    def _dedup_symbols(cls, v: List[str]) -> List[str]:
        # Sembol evreninde tekrar olmamalı; sessizce tekrar barındırmak
        # ileride "bu sembol iki kez mi kontrol edildi" karışıklığına yol açar.
        if len(v) != len(set(v)):
            raise ValueError("symbol_universe içinde tekrar eden sembol var")
        return v

    def is_symbol_allowed(self, symbol: str) -> bool:
        return symbol in self.symbol_universe

    def is_kill_switch_active(self, base_path: str | os.PathLike = ".") -> bool:
        """Kill-switch dosyası var mı? Varsa sistem yeni işlem üretmemeli."""
        return Path(base_path, self.kill_switch_file).exists()

    def leverage_for_asset_class(self, asset_class: str) -> float:
        """Varlık sınıfına özel bir kaldıraç sınırı varsa onu, yoksa genel sınırı döndürür."""
        override = self.per_asset_class.get(asset_class)
        return override.max_leverage if override else self.max_leverage


def load_mandate(path: str | os.PathLike = "config/mandate.yaml") -> Mandate:
    """
    Mandate'i YAML dosyasından yükler ve doğrular.

    Şema hatalıysa (ör. eksik alan, yanlış tip, mantıksız değer) burada
    bir ValidationError fırlatılır ve sistem başlamaz — bu kasıtlıdır:
    "belirsizlik durumunda dur" ilkesi.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(
            f"Mandate dosyası bulunamadı: {p}. "
            "config/mandate.yaml dosyasını oluşturup risk sınırlarını tanımlamadan "
            "sistem başlatılamaz (fail-closed ilkesi)."
        )
    with open(p, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    return Mandate(**raw)


if __name__ == "__main__":
    # Hızlı manuel doğrulama: `python -m risk.mandate`
    m = load_mandate()
    print("Mandate başarıyla yüklendi:")
    print(f"  Sembol evreni: {m.symbol_universe}")
    print(f"  Max pozisyon boyutu: %{m.max_position_size_pct * 100}")
    print(f"  Kill-switch aktif mi: {m.is_kill_switch_active()}")

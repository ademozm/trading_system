"""
Katman 3d — Avellaneda-Stoikov Piyasa Yapıcılığı Modeli
============================================================
İlham: hummingbot'un piyasa yapıcılığı strateji şablonlarından biri olan
Avellaneda-Stoikov (2008) modeli. Klasik akademik formülasyon şudur:

  Rezervasyon fiyatı:  r(s, q, t) = s - q * γ * σ² * (T - t)
  Optimal spread:      δ = γ * σ² * (T - t) + (2/γ) * ln(1 + γ/κ)
  Alış/Satış:          bid = r - δ/2,  ask = r + δ/2

Semboller:
  s     : mevcut orta fiyat (mid price)
  q     : mevcut envanter (inventory) — pozitifse fazla LONG, negatifse SHORT
  γ     : risk kaçınma katsayısı (gamma) — büyüdükçe envanteri sıfıra
          çekme isteği artar, spread büyür
  σ     : fiyat volatilitesi (bar başına getiri std sapması)
  T - t : kalan zaman ufku (0-1 arası normalize, 1 = ufkun başı, 0 = sonu)
  κ     : piyasa likidite/derinlik parametresi (kappa) — order book'tan
          tahmin edilir; büyükse piyasa likit demektir, spread daralır

Bu modül SADECE matematiği içerir (dış bağımlılık yok, sadece `math`).
Envanter limiti, emir gönderimi gibi operasyonel mantık mm_strategy.py'de.
"""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class QuoteResult:
    reservation_price: float
    spread: float
    bid_price: float
    ask_price: float


def reservation_price(mid_price: float, inventory: float, gamma: float, sigma: float, time_remaining: float) -> float:
    """
    Envanterin fiyatı nasıl "kaydırdığını" hesaplar. Envanter pozitifse
    (fazla long'sanız) rezervasyon fiyatı orta fiyatın ALTINA çekilir —
    bu, sizi satış tarafında daha agresif, alış tarafında daha çekingen
    yaparak envanteri azaltmaya iter.
    """
    return mid_price - inventory * gamma * (sigma ** 2) * time_remaining


def optimal_spread(gamma: float, sigma: float, time_remaining: float, kappa: float) -> float:
    """Toplam bid-ask spread'ini hesaplar (rezervasyon fiyatının etrafında simetrik)."""
    if kappa <= 0:
        raise ValueError("kappa (piyasa derinlik parametresi) pozitif olmalı")
    inventory_term = gamma * (sigma ** 2) * time_remaining
    liquidity_term = (2.0 / gamma) * math.log(1 + gamma / kappa)
    return inventory_term + liquidity_term


def compute_quotes(
    mid_price: float,
    inventory: float,
    gamma: float,
    sigma: float,
    time_remaining: float,
    kappa: float,
) -> QuoteResult:
    """Rezervasyon fiyatı + spread'i hesaplayıp nihai bid/ask fiyatlarını üretir."""
    r = reservation_price(mid_price, inventory, gamma, sigma, time_remaining)
    spread = optimal_spread(gamma, sigma, time_remaining, kappa)
    return QuoteResult(
        reservation_price=r,
        spread=spread,
        bid_price=r - spread / 2,
        ask_price=r + spread / 2,
    )

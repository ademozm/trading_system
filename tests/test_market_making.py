"""
tests/test_market_making.py
=============================
Avellaneda-Stoikov matematiğinin ve envanter limiti mantığının doğru
çalıştığını doğrular. Hiçbir dış bağımlılık gerekmez (sadece `math`),
bu yüzden her ortamda çalışır.
"""

from __future__ import annotations

import math

from signals.market_making.avellaneda_stoikov import (
    compute_quotes,
    optimal_spread,
    reservation_price,
)
from signals.market_making.mm_strategy import MarketMakingConfig, MarketMakingStrategy


def test_reservation_price_equals_mid_when_inventory_zero() -> None:
    r = reservation_price(mid_price=100.0, inventory=0.0, gamma=0.1, sigma=0.02, time_remaining=1.0)
    assert r == 100.0, "Envanter sıfırken rezervasyon fiyatı orta fiyata eşit olmalı"


def test_reservation_price_shifts_down_when_long() -> None:
    # Pozitif envanter (fazla LONG) -> rezervasyon fiyatı orta fiyatın ALTINA çekilmeli
    # (satışa teşvik etmek için)
    r = reservation_price(mid_price=100.0, inventory=1.0, gamma=0.1, sigma=0.02, time_remaining=1.0)
    assert r < 100.0


def test_reservation_price_shifts_up_when_short() -> None:
    r = reservation_price(mid_price=100.0, inventory=-1.0, gamma=0.1, sigma=0.02, time_remaining=1.0)
    assert r > 100.0


def test_reservation_price_shift_scales_with_inventory_magnitude() -> None:
    r_small = reservation_price(100.0, inventory=1.0, gamma=0.1, sigma=0.02, time_remaining=1.0)
    r_large = reservation_price(100.0, inventory=5.0, gamma=0.1, sigma=0.02, time_remaining=1.0)
    shift_small = 100.0 - r_small
    shift_large = 100.0 - r_large
    assert math.isclose(shift_large, 5 * shift_small, rel_tol=1e-9), \
        "Kayma, envanterle DOĞRUSAL olmalı (formülün yapısı gereği)"


def test_optimal_spread_is_positive() -> None:
    spread = optimal_spread(gamma=0.1, sigma=0.02, time_remaining=1.0, kappa=1.5)
    assert spread > 0


def test_optimal_spread_increases_with_volatility() -> None:
    low_vol = optimal_spread(gamma=0.1, sigma=0.01, time_remaining=1.0, kappa=1.5)
    high_vol = optimal_spread(gamma=0.1, sigma=0.05, time_remaining=1.0, kappa=1.5)
    assert high_vol > low_vol, "Volatilite arttıkça spread genişlemeli"


def test_optimal_spread_shrinks_as_time_runs_out() -> None:
    # T-t (time_remaining) küçüldükçe envanter terimi küçülür -> spread daralır
    early = optimal_spread(gamma=0.1, sigma=0.02, time_remaining=1.0, kappa=1.5)
    late = optimal_spread(gamma=0.1, sigma=0.02, time_remaining=0.01, kappa=1.5)
    assert late < early


def test_optimal_spread_rejects_non_positive_kappa() -> None:
    try:
        optimal_spread(gamma=0.1, sigma=0.02, time_remaining=1.0, kappa=0)
        assert False, "kappa=0 için ValueError bekleniyordu"
    except ValueError:
        pass


def test_compute_quotes_bid_below_ask() -> None:
    q = compute_quotes(mid_price=100.0, inventory=0.0, gamma=0.1, sigma=0.02, time_remaining=1.0, kappa=1.5)
    assert q.bid_price < q.reservation_price < q.ask_price
    assert math.isclose(q.ask_price - q.bid_price, q.spread, rel_tol=1e-9)


def test_strategy_quotes_both_sides_when_flat() -> None:
    strat = MarketMakingStrategy("BTC/USDT")
    quote = strat.generate_quote(mid_price=100.0, sigma=0.02)
    assert quote.bid_price is not None
    assert quote.ask_price is not None
    assert quote.bid_price < quote.ask_price


def test_strategy_stops_quoting_bid_at_max_long_inventory() -> None:
    config = MarketMakingConfig(max_inventory=1.0)
    strat = MarketMakingStrategy("BTC/USDT", config=config)
    strat.update_inventory(1.0, side="buy")  # tam limite ulaştı

    quote = strat.generate_quote(mid_price=100.0, sigma=0.02)
    assert quote.bid_price is None, "Envanter üst limitteyken YENİ ALIŞ kotasyonu verilmemeli"
    assert quote.ask_price is not None, "Envanteri azaltacak SATIŞ kotasyonu hâlâ verilmeli"


def test_strategy_stops_quoting_ask_at_max_short_inventory() -> None:
    config = MarketMakingConfig(max_inventory=1.0)
    strat = MarketMakingStrategy("BTC/USDT", config=config)
    strat.update_inventory(1.0, side="sell")  # -1.0 envantere düştü

    quote = strat.generate_quote(mid_price=100.0, sigma=0.02)
    assert quote.ask_price is None
    assert quote.bid_price is not None


def test_strategy_enforces_minimum_spread() -> None:
    # Çok düşük volatilite -> model çok dar bir spread önerir -> min_spread_bps tabanı devreye girmeli
    config = MarketMakingConfig(min_spread_bps=50.0)  # %0.5 taban
    strat = MarketMakingStrategy("BTC/USDT", config=config)
    quote = strat.generate_quote(mid_price=100.0, sigma=0.0001)
    assert quote.raw_spread >= 100.0 * 0.005 - 1e-9


def test_update_inventory_rejects_invalid_side() -> None:
    strat = MarketMakingStrategy("BTC/USDT")
    try:
        strat.update_inventory(1.0, side="hold")
        assert False, "ValueError bekleniyordu"
    except ValueError:
        pass


def test_config_from_mandate_maps_fields_correctly() -> None:
    class _FakeMMMandate:
        gamma = 0.2
        kappa = 2.0
        max_inventory_per_symbol = 3.0
        min_spread_bps = 8.0

    cfg = MarketMakingConfig.from_mandate(_FakeMMMandate())
    assert cfg.gamma == 0.2
    assert cfg.kappa == 2.0
    assert cfg.max_inventory == 3.0
    assert cfg.min_spread_bps == 8.0

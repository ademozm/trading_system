"""
tests/test_order_router.py
=============================
execution/order_router.py için testler. Bu dosyanın daha önce HİÇ test
kapsamı yoktu — bu turdaki taramada fark edildi.

NOT: risk.risk_manager (ApprovedOrderDraft) üzerinden risk.mandate'e
(pydantic) bağımlı olduğu için, pydantic kurulu olmayan bir ortamda bu
dosya ÇALIŞTIRILAMAZ (sadece sözdizimi doğrulanabilir) — test_mandate.py
ve test_aggregator.py ile aynı bilinen sınırlama. Kendi ortamınızda
(pydantic kuruluyken) tam olarak çalışacaktır.

Ağ gerektiren kısımlar (gerçek ccxt/Alpaca çağrıları) test edilmiyor;
sadece dry-run mantığı ve girdi doğrulama kontrol ediliyor.
"""

from __future__ import annotations

from execution.order_router import OrderRouter
from risk.risk_manager import ApprovedOrderDraft


def _draft(symbol="BTC/USDT", side="long", leverage=1.0, position_size_pct=0.02) -> ApprovedOrderDraft:
    return ApprovedOrderDraft(
        symbol=symbol, side=side, position_size_pct=position_size_pct,
        leverage=leverage, rationale="test",
    )


def test_dry_run_returns_expected_notional_and_side() -> None:
    router = OrderRouter(dry_run=True)
    result = router.route_order(_draft(position_size_pct=0.02), account_equity=10_000.0)
    assert result["status"] == "dry_run"
    assert result["side"] == "buy"
    assert abs(result["notional"] - 200.0) < 1e-9
    assert result["asset_class"] == "crypto"


def test_dry_run_short_side_maps_to_sell() -> None:
    router = OrderRouter(dry_run=True)
    result = router.route_order(_draft(side="short"), account_equity=10_000.0)
    assert result["side"] == "sell"


def test_dry_run_equity_symbol_has_no_price_fetch() -> None:
    """
    Hisse (equity) için canlı fiyat çekme henüz uygulanmadı (Alpaca'nın
    ayrı Data API akışı gerekir) — bu, o sınırlamanın açıkça belgelendiği
    davranışı test eder: "price" her zaman None döner, hata fırlatmaz.
    """
    router = OrderRouter(dry_run=True)
    result = router.route_order(_draft(symbol="AAPL"), account_equity=10_000.0)
    assert result["asset_class"] == "equity"
    assert result["price"] is None


def test_live_mode_rejects_leveraged_crypto_before_touching_exchange() -> None:
    """
    Kaldıraçlı bir kripto emri, gerçek ccxt/borsa çağrısına HİÇ ulaşmadan
    reddedilmeli (spot-only implementasyon). Bu test ağ gerektirmez çünkü
    kontrol, herhangi bir borsa çağrısından ÖNCE yapılıyor.
    """
    router = OrderRouter(dry_run=False)
    try:
        router.route_order(_draft(leverage=2.0), account_equity=10_000.0)
        assert False, "NotImplementedError bekleniyordu"
    except NotImplementedError:
        pass


def test_notional_scales_with_position_size_and_equity() -> None:
    router = OrderRouter(dry_run=True)
    result = router.route_order(_draft(position_size_pct=0.05), account_equity=20_000.0)
    assert abs(result["notional"] - 1000.0) < 1e-9

"""
Katman 4 — Risk Yönetimi: Aday İşlem Kontrolü
================================================
Sinyal katmanından (Katman 3) gelen her "aday işlem", execution'a
(Katman 6) gitmeden ÖNCE burada kontrol edilir. Bu modül hiçbir emir
göndermez — sadece "izin var / yok" kararı verir ve varsa pozisyon
boyutunu mandate sınırlarına göre yeniden hesaplar.

İlham: TradingAgents'ın "Risk Yönetimi Ekibi → Portföy Yöneticisi onayı"
zinciri (ama burada kural tabanlı ve deterministik — bir LLM'e bırakılmaz).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    # KRİTİK TASARIM DÜZELTMESİ: Mandate importu SADECE tip belirtmek için
    # kullanılıyordu — RiskManager, Mandate'in metodlarını duck-typing ile
    # çağırıyor (izomorf herhangi bir nesne işe yarar), Mandate sınıfının
    # KENDİSİNE runtime'da hiç ihtiyaç yok. `from __future__ import
    # annotations` sayesinde tüm tip belirtimleri string olarak saklanıyor,
    # bu yüzden bu importu TYPE_CHECKING altına almak güvenli. Bunun
    # faydası: artık bu modül (ve CandidateTrade/ApprovedOrderDraft'a
    # bağımlı olan aggregator.py, order_router.py, live_signal.py gibi
    # her şey) `pydantic` KURULU OLMAYAN bir ortamda bile import
    # edilebiliyor — daha önce sadece Mandate'i type hint olarak kullanan
    # bu dosya yüzünden TÜM zincir pydantic'e bağımlı hale geliyordu.
    from risk.mandate import Mandate


class RejectionReason(str, Enum):
    SYMBOL_NOT_IN_UNIVERSE = "sembol izin verilen evrende değil"
    KILL_SWITCH_ACTIVE = "kill-switch aktif"
    DAILY_LOSS_LIMIT_HIT = "günlük kayıp tavanı aşıldı"
    EXPOSURE_LIMIT_HIT = "toplam maruziyet sınırı aşılacaktı"
    SYMBOL_COOLDOWN = "sembol art arda kayıp nedeniyle soğutmada"
    LEVERAGE_EXCEEDED = "istenen kaldıraç mandate sınırını aşıyor"


@dataclass
class CandidateTrade:
    """Katman 3'ten (sinyal toplayıcı) gelen ham öneri."""

    symbol: str
    side: str  # "long" | "short"
    asset_class: str  # "crypto" | "equity" | ...
    confidence: float  # 0.0 - 1.0, sinyal toplayıcının verdiği güven skoru
    rationale: str  # insana gösterilecek kısa gerekçe özeti
    requested_leverage: float = 1.0


@dataclass
class ApprovedOrderDraft:
    """Risk kontrolünden geçmiş, execution'a/insana gidecek taslak."""

    symbol: str
    side: str
    position_size_pct: float  # portföyün yüzdesi olarak
    leverage: float
    rationale: str


@dataclass
class RiskCheckResult:
    approved: bool
    order_draft: Optional[ApprovedOrderDraft] = None
    rejection_reason: Optional[RejectionReason] = None


class RiskManager:
    def __init__(
        self,
        mandate: Mandate,
        current_total_exposure_pct: float = 0.0,
        current_daily_pnl_pct: float = 0.0,
        symbol_consecutive_losses: Optional[dict[str, int]] = None,
        base_path: str = ".",
    ) -> None:
        """
        Parametreler, çağıran taraf (ör. main.py) tarafından her kontrol
        öncesi güncel portföy durumundan doldurulur:
          - current_total_exposure_pct: şu an açık pozisyonların toplamı
          - current_daily_pnl_pct: bugünkü gerçekleşen kar/zarar (negatifse zarar)
          - symbol_consecutive_losses: {"BTC/USDT": 2, ...}
        """
        self.mandate = mandate
        self.current_total_exposure_pct = current_total_exposure_pct
        self.current_daily_pnl_pct = current_daily_pnl_pct
        self.symbol_consecutive_losses = symbol_consecutive_losses or {}
        self.base_path = base_path

    def check(self, trade: CandidateTrade) -> RiskCheckResult:
        """Aday işlemi mandate'e karşı sırayla kontrol eder (fail-closed)."""

        # 1) Kill-switch en yüksek önceliğe sahiptir; başka hiçbir kontrol
        #    onu geçersiz kılamaz.
        if self.mandate.is_kill_switch_active(self.base_path):
            return RiskCheckResult(False, rejection_reason=RejectionReason.KILL_SWITCH_ACTIVE)

        # 2) Sembol evreni kontrolü
        if not self.mandate.is_symbol_allowed(trade.symbol):
            return RiskCheckResult(False, rejection_reason=RejectionReason.SYMBOL_NOT_IN_UNIVERSE)

        # 3) Günlük kayıp tavanı
        if self.current_daily_pnl_pct <= -self.mandate.daily_loss_limit_pct:
            return RiskCheckResult(False, rejection_reason=RejectionReason.DAILY_LOSS_LIMIT_HIT)

        # 4) Sembol bazlı soğutma (art arda kayıp)
        losses = self.symbol_consecutive_losses.get(trade.symbol, 0)
        if losses >= self.mandate.max_consecutive_losses_per_symbol:
            return RiskCheckResult(False, rejection_reason=RejectionReason.SYMBOL_COOLDOWN)

        # 5) Kaldıraç kontrolü (varlık sınıfına özel override'lar dahil)
        allowed_leverage = self.mandate.leverage_for_asset_class(trade.asset_class)
        if trade.requested_leverage > allowed_leverage:
            return RiskCheckResult(False, rejection_reason=RejectionReason.LEVERAGE_EXCEEDED)

        # 6) Pozisyon boyutunu hesapla: mandate'in izin verdiği maksimumu,
        #    sinyalin güven skoruyla ölçekle (basit, konservatif bir yaklaşım —
        #    ileride Kelly kriteri gibi daha gelişmiş bir formülle değiştirilebilir).
        position_size_pct = min(
            self.mandate.max_position_size_pct,
            self.mandate.max_position_size_pct * trade.confidence,
        )

        # 7) Toplam maruziyet kontrolü: bu pozisyon eklendiğinde sınır aşılır mı?
        projected_exposure = self.current_total_exposure_pct + position_size_pct
        if projected_exposure > self.mandate.max_total_exposure_pct:
            return RiskCheckResult(False, rejection_reason=RejectionReason.EXPOSURE_LIMIT_HIT)

        draft = ApprovedOrderDraft(
            symbol=trade.symbol,
            side=trade.side,
            position_size_pct=position_size_pct,
            leverage=trade.requested_leverage,
            rationale=trade.rationale,
        )
        return RiskCheckResult(True, order_draft=draft)

    def record_position_opened(self, position_size_pct: float) -> None:
        """
        KRİTİK: Onaylanan bir taslak GERÇEKTEN yerleştirildikten (insan onayı +
        order_router.route_order() başarılı olduktan) SONRA çağrılmalıdır.

        Bunu çağırmazsanız (main.py'de olduğu gibi bir süre çağrılmıyordu),
        `current_total_exposure_pct` hep sabit kalır ve aynı çalıştırma
        (run) içinde art arda onaylanan işlemler toplam maruziyet limitini
        sessizce aşabilir — her kontrol, sanki önceki onaylar hiç
        gerçekleşmemiş gibi "temiz sayfa" görür.
        """
        self.current_total_exposure_pct += position_size_pct

    def record_position_closed(self, symbol: str, position_size_pct: float, realized_pnl_pct: float) -> None:
        """
        Bir pozisyon kapandığında maruziyeti azaltır, günlük PnL'i günceller
        VE art arda kayıp sayacını (symbol_consecutive_losses) günceller.

        KRİTİK DÜZELTME: Önceki sürümde bu metod art arda kayıp sayacına HİÇ
        dokunmuyordu — `main.py`'nin `/kapat` komutu üzerinden GERÇEKTEN
        çağrılmaya başlamasından SONRA fark edildi. Bu olmadan, sürekli
        modda (LOOP_INTERVAL_SECONDS > 0) bir sembolde art arda zararlı
        pozisyonlar kapatılsa bile "soğutma" özelliği devreye girmiyordu —
        sadece programı yeniden başlattığınızda (decision_log'dan yeniden
        hesaplanınca) güncelleniyordu.
        """
        self.current_total_exposure_pct = max(0.0, self.current_total_exposure_pct - position_size_pct)
        self.current_daily_pnl_pct += realized_pnl_pct

        if realized_pnl_pct < 0:
            self.symbol_consecutive_losses[symbol] = self.symbol_consecutive_losses.get(symbol, 0) + 1
        else:
            # Kazançlı (veya başabaş) bir kapanış, o sembolün art arda
            # kayıp sayacını sıfırlar — decision_log.consecutive_losses()
            # ile aynı mantık (bkz. monitoring/decision_log.py).
            self.symbol_consecutive_losses[symbol] = 0

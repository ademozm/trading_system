"""
Katman 6 + 8 — Execution (Yarı-Otomatik) & Kontrol Paneli: Telegram Botu
===========================================================================
Akış:
  1) risk.risk_manager'dan onaylanmış bir ApprovedOrderDraft gelir.
  2) Bu taslak Telegram'a bir mesaj + Onayla/Reddet butonlarıyla gönderilir.
  3) Kullanıcı butona basar -> callback tetiklenir.
  4) Onaylanırsa order_router.route_order() çağrılır (gerçek emir).
  5) mandate.approval_timeout_seconds içinde yanıt gelmezse taslak
     otomatik reddedilir (varsayılan = işlem YAPMA).

KRİTİK DÜZELTME #1: Önceki sürümde `request_approval()` mesajı gönderip
`asyncio.sleep()` ile bekliyordu ama botun Telegram'dan gelen güncellemeleri
(buton tıklamalarını) DİNLEMESİNİ hiç başlatmıyordu (`start_polling()` /
`run_polling()` çağrılmıyordu). Sonuç: mesaj gidiyordu ama buton tıklamaları
asla işlenmiyordu. Artık `start()`/`stop()` ile polling açıkça başlatılıp
durduruluyor, `on_decision` artık __init__'te değil her `request_approval()`
çağrısında ayrı ayrı veriliyor (tek bir bot örneği, birden çok istek için
paylaşılabilsin diye — bkz. main.py'deki kullanım).

KRİTİK DÜZELTME #2 (#1'den SONRA bulundu): Polling düzeltildikten sonra bile
`request_approval()` her zaman TAM `timeout_seconds` kadar bekliyordu —
kullanıcı butona hemen bassa bile fonksiyon erken dönmüyordu, bu da
main.py'deki döngünün bir sonraki sembole geçmesini (ve o sembolün Telegram
mesajını göndermesini) gereksiz yere geciktiriyordu. Artık bir `asyncio.Event`
ile karar geldiği AN bekleme kesiliyor; zaman aşımı sadece hiç yanıt
gelmezse devreye giriyor.
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Dict, Optional

from risk.risk_manager import ApprovedOrderDraft

try:
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
    from telegram.ext import Application, CallbackQueryHandler, CommandHandler, ContextTypes
except ImportError:  # pragma: no cover
    # python-telegram-bot kurulu değilse modül yine de import edilebilsin;
    # sadece ApprovalBot() çalıştırılınca hata versin.
    InlineKeyboardButton = InlineKeyboardMarkup = Update = None  # type: ignore
    Application = CallbackQueryHandler = CommandHandler = ContextTypes = None  # type: ignore


# Onay sonucu geldiğinde çağrılacak fonksiyonun tipi
OnDecision = Callable[[str, ApprovedOrderDraft, bool], Awaitable[None]]


@dataclass
class PendingApproval:
    draft: ApprovedOrderDraft
    on_decision: OnDecision  # bu isteğe ÖZEL callback (her request_approval çağrısı kendi callback'ini verir)
    approved: Optional[bool] = None  # None = henüz yanıt yok
    event: asyncio.Event = field(default_factory=asyncio.Event)  # karar gelince set edilir -> bekleme hemen biter


class ApprovalBot:
    """
    Telegram üzerinden onay/red akışını yöneten sınıf.

    Kullanım (main.py içinde) — TEK bir örnek oluşturup tüm semboller için
    paylaşın, her sembol için yeni bir ApprovalBot AÇMAYIN:
        bot = ApprovalBot()
        await bot.start()                       # polling'i başlat
        await bot.request_approval(draft, on_decision=my_callback)
        ...                                       # başka semboller için de aynı bot
        await bot.stop()                          # program biterken kapat
    """

    def __init__(self, timeout_seconds: int = 300) -> None:
        token = os.environ.get("TELEGRAM_BOT_TOKEN")
        self.chat_id = os.environ.get("TELEGRAM_CHAT_ID")
        if not token or not self.chat_id:
            raise EnvironmentError(
                "TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID ortam değişkenleri "
                "tanımlı olmalı. bkz. README.md 'Telegram botunu kur' bölümü."
            )
        if Application is None:
            raise ImportError("python-telegram-bot kurulu değil: `pip install python-telegram-bot`")

        self.timeout_seconds = timeout_seconds
        self._pending: Dict[str, PendingApproval] = {}
        self._started = False

        self.app = Application.builder().token(token).build()
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        self.app.add_handler(CommandHandler("durum", self._handle_status))

    async def start(self) -> None:
        """
        Botun Telegram'dan güncelleme (buton tıklaması) ALMASINI başlatır.
        request_approval() çağırmadan ÖNCE bu MUTLAKA çağrılmalı — aksi
        halde mesaj gider ama buton tıklamaları asla işlenmez (düzeltilen
        hata tam olarak buydu).
        """
        if self._started:
            return
        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling()
        self._started = True

    async def stop(self) -> None:
        """Programı düzgünce kapatmak için polling'i durdurur."""
        if not self._started:
            return
        await self.app.updater.stop()
        await self.app.stop()
        await self.app.shutdown()
        self._started = False

    async def request_approval(self, draft: ApprovedOrderDraft, on_decision: OnDecision) -> None:
        """
        Yeni bir işlem taslağını Telegram'a gönderir ve yanıt bekler.
        `start()` önceden çağrılmamışsa RuntimeError fırlatır (sessizce
        "mesaj gitti ama hiç dinlenmiyor" durumuna düşülmesin diye).
        """
        if not self._started:
            raise RuntimeError(
                "ApprovalBot.start() çağrılmadan request_approval() kullanılamaz — "
                "aksi halde buton tıklamaları asla işlenmez. Önce `await bot.start()` çağırın."
            )

        request_id = str(uuid.uuid4())[:8]
        self._pending[request_id] = PendingApproval(draft=draft, on_decision=on_decision)

        text = (
            f"🔔 *Yeni İşlem Önerisi* (#{request_id})\n\n"
            f"Sembol: `{draft.symbol}`\n"
            f"Yön: *{draft.side.upper()}*\n"
            f"Pozisyon boyutu: %{draft.position_size_pct * 100:.2f}\n"
            f"Kaldıraç: {draft.leverage}x\n\n"
            f"Gerekçe: {draft.rationale}\n\n"
            f"⏱ {self.timeout_seconds} saniye içinde yanıt verilmezse "
            f"otomatik REDDEDİLECEK."
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Onayla", callback_data=f"approve:{request_id}"),
                    InlineKeyboardButton("❌ Reddet", callback_data=f"reject:{request_id}"),
                ]
            ]
        )
        await self.app.bot.send_message(
            chat_id=self.chat_id, text=text, parse_mode="Markdown", reply_markup=keyboard
        )

        # Karar (onay/red) gelene KADAR bekle, ama en fazla timeout_seconds
        # kadar. Event set edilirse (buton tıklanırsa) hemen döner —
        # önceki hatadaki gibi gereksiz yere tam süre beklemez.
        pending = self._pending[request_id]
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            if pending.approved is None:
                await pending.on_decision(request_id, draft, False)
                await self.app.bot.send_message(
                    chat_id=self.chat_id,
                    text=f"⌛ #{request_id} zaman aşımına uğradı, otomatik REDDEDİLDİ.",
                )
        self._pending.pop(request_id, None)

    async def _handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        action, request_id = query.data.split(":", 1)
        pending = self._pending.get(request_id)
        if pending is None or pending.approved is not None:
            await query.edit_message_text("Bu öneri artık geçerli değil (zaman aşımı veya zaten yanıtlandı).")
            return

        approved = action == "approve"
        pending.approved = approved
        pending.event.set()  # request_approval()'daki beklemeyi hemen sonlandırır
        await pending.on_decision(request_id, pending.draft, approved)

        status = "✅ ONAYLANDI" if approved else "❌ REDDEDİLDİ"
        await query.edit_message_text(f"{query.message.text}\n\n— {status} —")

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._pending:
            await update.message.reply_text("Bekleyen işlem önerisi yok.")
            return
        lines = [f"#{rid}: {p.draft.symbol} {p.draft.side}" for rid, p in self._pending.items()]
        await update.message.reply_text("Bekleyen öneriler:\n" + "\n".join(lines))

    def register_command(self, command: str, handler) -> None:
        """
        main.py'nin decision_log/risk_manager'a erişimi olan EK Telegram
        komutları (ör. `/pozisyonlar`, `/kapat`) kaydetmesi içindir.
        ApprovalBot bilerek decision_log/risk_manager'ı DOĞRUDAN bilmiyor
        (katmanlar arası bağımlılığı azaltmak için) — main.py bu metodla
        kendi handler'larını enjekte eder.

        command: başında "/" OLMADAN (ör. "pozisyonlar").
        handler: `async def handler(update, context) -> None` imzalı fonksiyon.
        """
        self.app.add_handler(CommandHandler(command, handler))

    def run_polling(self) -> None:
        """
        Botu bağımsız (standalone) test modunda başlatır (bloklayıcı çağrı).
        Bu, start()/stop() ile programatik kontrolden FARKLI bir kullanım
        şeklidir — sadece `python -m execution.telegram_bot` ile manuel
        bağlantı testi için kullanılır, gerçek onay isteği göndermez.
        """
        self.app.run_polling()


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv()  # bağımsız çalıştırıldığında (`python -m execution.telegram_bot`)
                    # .env dosyasını yükle — main.py üzerinden çalıştırılırken zaten
                    # main.py'nin başındaki load_dotenv() yeterli.
    bot = ApprovalBot()
    print("[telegram_bot] Bot başlatılıyor... (Ctrl+C ile durdurun, /durum yazarak test edin)")
    bot.run_polling()

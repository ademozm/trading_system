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

Kurulum:
  - Ortam değişkenleri: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
    (BotFather'dan token, kendi chat_id'nizi @userinfobot ile alabilirsiniz)
  - `pip install python-telegram-bot`

Not: Bu dosya bir İSKELETTİR — gerçek çalıştırma için kendi ortamınızda
python-telegram-bot kurulu olmalı (bu sohbet ortamında ağ erişimi
olmadığı için kurulup uçtan uca test edilemedi; sözdizimi doğrulanmıştır).
"""

from __future__ import annotations

import asyncio
import os
import uuid
from dataclasses import dataclass
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


@dataclass
class PendingApproval:
    draft: ApprovedOrderDraft
    approved: Optional[bool] = None  # None = henüz yanıt yok


# Onay sonucu geldiğinde çağrılacak fonksiyonun tipi
OnDecision = Callable[[str, ApprovedOrderDraft, bool], Awaitable[None]]


class ApprovalBot:
    """
    Telegram üzerinden onay/red akışını yöneten sınıf.

    Kullanım (main.py içinde):
        bot = ApprovalBot(on_decision=my_order_router_callback)
        await bot.request_approval(draft)
    """

    def __init__(self, on_decision: OnDecision, timeout_seconds: int = 300) -> None:
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
        self.on_decision = on_decision
        self._pending: Dict[str, PendingApproval] = {}

        self.app = Application.builder().token(token).build()
        self.app.add_handler(CallbackQueryHandler(self._handle_callback))
        self.app.add_handler(CommandHandler("durum", self._handle_status))

    async def request_approval(self, draft: ApprovedOrderDraft) -> None:
        """Yeni bir işlem taslağını Telegram'a gönderir ve yanıt bekler."""
        request_id = str(uuid.uuid4())[:8]
        self._pending[request_id] = PendingApproval(draft=draft)

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

        # Zaman aşımını bekle
        await asyncio.sleep(self.timeout_seconds)
        pending = self._pending.get(request_id)
        if pending and pending.approved is None:
            await self.on_decision(request_id, draft, False)
            await self.app.bot.send_message(
                chat_id=self.chat_id,
                text=f"⌛ #{request_id} zaman aşımına uğradı, otomatik REDDEDİLDİ.",
            )
            del self._pending[request_id]

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
        await self.on_decision(request_id, pending.draft, approved)

        status = "✅ ONAYLANDI" if approved else "❌ REDDEDİLDİ"
        await query.edit_message_text(f"{query.message.text}\n\n— {status} —")
        del self._pending[request_id]

    async def _handle_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not self._pending:
            await update.message.reply_text("Bekleyen işlem önerisi yok.")
            return
        lines = [f"#{rid}: {p.draft.symbol} {p.draft.side}" for rid, p in self._pending.items()]
        await update.message.reply_text("Bekleyen öneriler:\n" + "\n".join(lines))

    def run_polling(self) -> None:
        """Botu başlatır (bloklayıcı çağrı)."""
        self.app.run_polling()


async def _example_on_decision(request_id: str, draft: ApprovedOrderDraft, approved: bool) -> None:
    """main.py içinde gerçek order_router.route_order() ile değiştirilecek örnek callback."""
    if approved:
        print(f"[telegram_bot] #{request_id} onaylandı -> order_router'a gönderiliyor: {draft}")
    else:
        print(f"[telegram_bot] #{request_id} reddedildi/zaman aşımı: {draft}")


if __name__ == "__main__":
    bot = ApprovalBot(on_decision=_example_on_decision)
    print("[telegram_bot] Bot başlatılıyor... (Ctrl+C ile durdurun)")
    bot.run_polling()

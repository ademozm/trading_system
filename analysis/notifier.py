"""
Telegram bildirimleri.

Kurulum (kullanıcı tarafında, README'de detaylı anlatılıyor):
1. Telegram'da @BotFather ile konuşup /newbot komutuyla ücretsiz bir bot oluştur, sana bir TOKEN verir.
2. Botunla bir konuşma başlat (herhangi bir mesaj gönder).
3. https://api.telegram.org/bot<TOKEN>/getUpdates adresine gidip "chat":{"id": ...} değerini bul.
4. TELEGRAM_BOT_TOKEN ve TELEGRAM_CHAT_ID'yi ortam değişkeni olarak ayarla (asla koda yazma).

Bu modül token/chat_id BULAMAZSA sessizce atlar (bildirim gönderilmez,
ama tarama ASLA bu yüzden çökmez) — bildirimler opsiyonel bir eklentidir.
"""
import logging
import os

import requests

import config

logger = logging.getLogger("notifier")

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


def is_configured() -> bool:
    return bool(os.environ.get(config.TELEGRAM_BOT_TOKEN_ENV)) and bool(
        os.environ.get(config.TELEGRAM_CHAT_ID_ENV)
    )


def _credentials():
    return os.environ.get(config.TELEGRAM_BOT_TOKEN_ENV), os.environ.get(config.TELEGRAM_CHAT_ID_ENV)


def send_message(text: str, parse_mode: str = "Markdown") -> bool:
    token, chat_id = _credentials()
    if not token or not chat_id:
        logger.info("Telegram yapılandırılmamış (TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID yok), bildirim atlandı.")
        return False

    url = TELEGRAM_API.format(token=token, method="sendMessage")
    try:
        # Telegram mesaj uzunluğu sınırı ~4096 karakter
        for i in range(0, len(text), 4000):
            resp = requests.post(
                url, data={"chat_id": chat_id, "text": text[i:i + 4000], "parse_mode": parse_mode}, timeout=15
            )
            if resp.status_code >= 400:
                logger.warning(f"Telegram mesajı gönderilemedi: {resp.status_code} - {resp.text}")
                return False
        return True
    except Exception as e:
        logger.warning(f"Telegram mesajı gönderilemedi: {e}")
        return False


def send_document(file_path: str, caption: str = "") -> bool:
    token, chat_id = _credentials()
    if not token or not chat_id:
        return False

    url = TELEGRAM_API.format(token=token, method="sendDocument")
    try:
        with open(file_path, "rb") as f:
            resp = requests.post(
                url, data={"chat_id": chat_id, "caption": caption},
                files={"document": f}, timeout=60,
            )
            if resp.status_code >= 400:
                logger.warning(f"Telegram dosyası gönderilemedi: {resp.status_code} - {resp.text}")
                return False
        return True
    except Exception as e:
        logger.warning(f"Telegram dosyası gönderilemedi: {e}")
        return False


def build_summary_message(scored_df, filter_stats: dict = None, top_n: int = None) -> str:
    """Tarama sonucundan okunabilir bir Telegram mesajı üretir."""
    top_n = top_n or config.NOTIFY_TOP_N
    panel_url = os.environ.get(config.STREAMLIT_APP_URL_ENV)

    if scored_df is None or scored_df.empty:
        msg = "📊 *Tarama tamamlandı*\nBu taramada sinyal üreten sembol bulunamadı."
        if panel_url:
            msg += f"\n\n📱 [Paneli aç]({panel_url})"
        return msg

    lines = ["📊 *Tarama Sonucu*\n"]
    if filter_stats:
        lines.append(f"Filtre öncesi: {filter_stats.get('başlangıç', '-')} → "
                      f"filtre sonrası: {filter_stats.get('son', '-')}\n")

    buys = scored_df[scored_df["signal"] == 1].head(top_n)
    sells = scored_df[scored_df["signal"] == -1].sort_values("composite_score").head(top_n)

    if not buys.empty:
        lines.append("🟢 *En iyi AL sinyalleri:*")
        for _, row in buys.iterrows():
            lines.append(f"  {row['symbol']} ({row['market']}) — skor: {row['composite_score']:.2f}")

    if not sells.empty:
        lines.append("\n🔴 *En iyi SAT sinyalleri:*")
        for _, row in sells.iterrows():
            lines.append(f"  {row['symbol']} ({row['market']}) — skor: {row['composite_score']:.2f}")

    if panel_url:
        lines.append(f"\n📱 [Tüm sonuçları görsel panelde aç]({panel_url})")

    return "\n".join(lines)


def notify_scan_complete(scored_df, filter_stats: dict, report_path: str, send_file: bool = True) -> bool:
    """
    Tarama bitince çağrılır. Telegram yapılandırılmamışsa sessizce
    False döner, tarama akışını ETKİLEMEZ.
    """
    if not is_configured():
        return False

    message = build_summary_message(scored_df, filter_stats)
    sent = send_message(message)

    if send_file and report_path:
        send_document(report_path, caption="Tam tarama raporu")

    return sent

"""
Gün içi otomatik tarama zamanlayıcısı.

İKİ ÇALIŞTIRMA YÖNTEMİ VAR:

1) Bu scripti sürekli açık bırakarak (basit ama bilgisayar/terminal açık kalmalı):
   python scheduler.py

2) İşletim sisteminin görev zamanlayıcısını kullanarak (ÖNERİLEN — bilgisayar
   kapansa/uyusa bile güvenilir çalışır, terminal açık kalmasına gerek yok):

   Windows (Görev Zamanlayıcı / Task Scheduler):
     - "Create Basic Task" -> Trigger: Daily, günde birkaç kez tekrar
     - Action: "python.exe" C:\...\main_scan.py --markets us bist crypto

   macOS/Linux (cron):
     crontab -e
     30 10,13,16,19 * * 1-5 cd /path/to/trading_system && python3 main_scan.py --markets us bist crypto

   Bu ikinci yöntem, config.py içindeki SCAN_TIMES_TR listesinden bağımsızdır;
   saatleri doğrudan cron/Task Scheduler'da tanımlarsın.

NOT: yfinance ücretsiz ve gayri resmi bir veri kaynağıdır. Günde birkaç kez,
onlarca-yüzlerce sembollük taramalarda genelde sorun çıkmaz, ama BÜYÜK
evrenlerde (binlerce sembol) sık sık çekim yapmak IP'nin geçici olarak
kısıtlanmasına yol açabilir. Ölçek büyüdükçe ücretli bir veri sağlayıcısına
(Polygon.io, Finnhub, Alpaca Data vb.) geçmeyi düşün.
"""
import time
import logging
from datetime import datetime

import schedule

import config
from main_scan import run_scan

logger = logging.getLogger("scheduler")


def _job():
    logger.info("Zamanlanmış tarama tetiklendi.")
    try:
        run_scan(markets=None, use_cache=True)
    except Exception as e:
        logger.error(f"Zamanlanmış tarama başarısız oldu: {e}")


def start():
    for t in config.SCAN_TIMES_TR:
        schedule.every().day.at(t).do(_job)
        logger.info(f"Zamanlandı: her gün {t}")

    logger.info("Zamanlayıcı çalışıyor. Durdurmak için Ctrl+C.")
    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    start()

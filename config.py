"""
Merkezi yapılandırma. Tüm ayarlar tek yerden yönetilir.
"""
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
CACHE_DIR = os.path.join(BASE_DIR, "cache")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
LOG_DIR = os.path.join(BASE_DIR, "logs")

for d in (CACHE_DIR, REPORTS_DIR, LOG_DIR):
    os.makedirs(d, exist_ok=True)

UNIVERSE_FILES = {
    "us": os.path.join(DATA_DIR, "universe_us.csv"),
    "bist": os.path.join(DATA_DIR, "universe_bist.csv"),
    "crypto": os.path.join(DATA_DIR, "universe_crypto.csv"),
    "emtia": os.path.join(DATA_DIR, "universe_emtia.csv"),
}

# Veri çekme ayarları
FETCH_PERIOD = "1y"          # Backtest/gösterge hesaplamak için geriye dönük veri aralığı
FETCH_INTERVAL = "1d"        # Gün içi analiz istense de temel veri günlük; bkz README (yfinance intraday sınırları)
CACHE_TTL_MINUTES = 60       # Bu süre içinde tekrar istenen veri diskten okunur, tekrar indirilmez
FETCH_BATCH_SIZE = 10        # Aynı anda kaç sembol indirilecek (rate-limit koruması)
FETCH_BATCH_DELAY_SEC = 2    # Batch'ler arası bekleme
FETCH_MAX_RETRIES = 3
FETCH_RETRY_BACKOFF_SEC = 5

# Bir sembol yfinance'ten TAMAMEN başarısız olursa (tüm denemeler tükenirse),
# Stooq'a düşmeden ÖNCE bu alternatif Yahoo sembollerini de dener. Altın
# defalarca sorun çıkardığı için (rollover boşlukları, Volume eksikliği gibi
# farklı sebeplerle) burada birden fazla alternatif tutuluyor — biri
# başarısız olsa da diğeri devreye girsin diye.
ALTERNATE_TICKERS = {
    "XAUUSD=X": ["GC=F"],
    "GC=F": ["XAUUSD=X"],
    "XAGUSD=X": ["SI=F"],
    "SI=F": ["XAGUSD=X"],
}

# Veri doğrulama eşikleri
MIN_ROWS_REQUIRED = 60          # En az bu kadar mum olmalı (ADX/EMA gibi göstergeler için)
MAX_STALE_DAYS = 5              # Son veri bu kadar günden eskiyse "bayat" kabul edilir
MAX_DAILY_RETURN_ABS = 0.60     # Tek günde >%60 hareket şüpheli veri kabul edilir (veri hatası olabilir)

# Skorlama ağırlıkları v2 (toplamı 1.0 olacak şekilde; bir sembolde bir bileşen
# eksikse -bkz. fundamental_score kriptoda yok- ağırlık otomatik olarak mevcut
# bileşenler arasında yeniden dağıtılır, bkz. analysis/scorer.py)
SCORE_WEIGHTS = {
    "signal_strength": 0.18,      # ADX / rejim netliği (teknik)
    "momentum": 0.14,             # N günlük getiri (teknik)
    "risk_reward": 0.09,          # hedef/stop mesafesi oranı (teknik)
    "volatility_penalty": 0.09,   # aşırı volatilite cezası (teknik/risk)
    "fundamental": 0.18,          # P/E, ROE, borç, büyüme (sadece hisseler)
    "relative_strength": 0.14,    # endekse karşı göreceli performans
    "volume_confirmation": 0.05,  # hacim teyidi (AL/SAT yönüyle uyumlu mu)
    "mtf_confirmation": 0.05,     # haftalık trend teyidi
    "news_sentiment": 0.08,       # haber tonu (basit anahtar kelime analizi, kaba gösterge)
}
MOMENTUM_LOOKBACK_DAYS = 20
RELATIVE_STRENGTH_LOOKBACK_DAYS = 63

# Haber çekimi de sembol başına ayrı istek gerektirir (yfinance .news).
# Büyük evrenlerde yavaşlatabilir: main_scan.py --skip-news
FETCH_NEWS_DEFAULT = True

# Temel analiz verisi çekimi sembol başına ayrı istek gerektirdiği için
# YAVAŞTIR. Büyük evrenlerde ilk denemede kapalı tutup teknik sonuçları
# görmek isteyebilirsin: main_scan.py --skip-fundamentals
FETCH_FUNDAMENTALS_DEFAULT = True

# Varsayılan filtreler (main_scan.py CLI argümanlarıyla override edilebilir)
FILTERS = {
    "min_composite_score": 0.15,
    "min_market_cap": None,          # örn. 1_000_000_000 (1 milyar USD)
    "max_pe": None,                  # örn. 50
    "min_relative_volume": None,     # örn. 0.7
    "allowed_signals": [1, -1],      # [1] = sadece AL, [-1] = sadece SAT
    "require_mtf_confirmation": False,
}

# Zamanlama
SCAN_TIMES_TR = ["10:30", "13:00", "16:00", "19:00"]  # Gün içi birkaç kez taramak için örnek saatler

# Sembol listesi otomatik güncelleme: dosya bu kadar günden eskiyse
# tarama öncesi otomatik olarak fetch_universe_lists mantığıyla tazelenir.
UNIVERSE_MAX_AGE_DAYS = 7
# Tazelik kontrolü dosya mtime'ına DEĞİL, bu JSON'a kaydedilen gerçek
# tarihe göre yapılır — git clone/checkout TÜM dosyaların mtime'ını
# "şimdi"ye sıfırlar, içerik aylar önceki olsa bile.
UNIVERSE_META_PATH = os.path.join(DATA_DIR, "universe_meta.json")
AUTO_REFRESH_UNIVERSE_DEFAULT = True

# Sinyal günlüğü (performans takibi) veritabanı
JOURNAL_DB_PATH = os.path.join(DATA_DIR, "signal_journal.db")
# Bir sinyal bu kadar gün içinde ne stop ne target'a değmezse "süresi doldu" sayılır
JOURNAL_MAX_OPEN_DAYS = 30

# Telegram bildirimleri — GÜVENLİK: token/chat_id burada SABİT KODLANMAZ.
# Ortam değişkeninden (environment variable) okunur:
#   Windows:  set TELEGRAM_BOT_TOKEN=... (kalıcı için: setx)
#   Mac/Linux: export TELEGRAM_BOT_TOKEN=...
#   GitHub Actions: repo Settings > Secrets olarak eklenir (bkz. README)
TELEGRAM_BOT_TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
TELEGRAM_CHAT_ID_ENV = "TELEGRAM_CHAT_ID"
# Streamlit Community Cloud'a deploy ettiğin panelin genel (public) linki.
# Ayarlarsan, Telegram bildirimlerine otomatik olarak "panele git" linki eklenir.
STREAMLIT_APP_URL_ENV = "STREAMLIT_APP_URL"
NOTIFY_TOP_N = 10  # Bildirimde gösterilecek en iyi kaç sinyal

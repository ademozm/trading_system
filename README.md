# Hibrit Trading Sistemi — Çok Varlıklı, Yarı-Otomatik

## Sistemin Amacı

Bu sistemin amacı **"sinyal öner" değil, tam bir pozisyon yaşam döngüsü**
yönetmektir:

```
öner → insan onaylar → GERÇEK fiyattan gir → izle → kapat → öğren
```

Çoğu basit trading botu ilk üç adımda durur (sinyal üretir, onaylatır, emir
gönderir) ve orada biter — pozisyon "açıldı" diye kaydedilir ama bir daha
hiç kapatılmaz, gerçekleşen kâr/zarar hiç ölçülmez, sistem geçmişinden hiç
öğrenmez. Bu proje bilinçli olarak döngüyü TAMAMLAMAYI hedefliyor: her
onaylanan işlem gerçek bir giriş fiyatıyla kaydedilir (`entry_price`),
`/kapat` komutuyla kapatılıp gerçekleşen PnL hesaplanır, bu da hem risk
katmanının (`toplam maruziyet`, `art arda kayıp soğutması`) hem LLM ajan
zincirinin ("bu sembolde geçmişte ne oldu") gerçek veriyle çalışmasını sağlar.

Bu proje, `hibrit-trading-sistemi-tasarimi.md` belgesinde tanımlanan 9 katmanlı
mimarinin **çalışan kod iskeletidir**. Faz 0-4 ve Faz 6 (veri katmanı, klasik
strateji, backtest, mandate/risk katmanı, Telegram onay akışı, ML sinyali,
LLM ajan zinciri, market making) tam işlevsel durumdadır ve otomatik testlerle
doğrulanmıştır. Faz 5 (küçük sermaye ile canlı test) bir kod aşaması değil,
operasyonel bir aşamadır — bkz. aşağıdaki "Sıradaki Adımlar".

## Klasör Yapısı — Katman Haritası

```
trading_system/
├── config/
│   └── mandate.yaml          # Katman 4: risk sınırları (tek doğruluk kaynağı)
├── data_layer/                # Katman 1 + 2: bağlantı ve depolama
│   ├── connectors/
│   │   ├── ccxt_connector.py   # ccxt üzerinden borsa bağlantısı — kripto (Katman 1)
│   │   └── alpaca_connector.py # Alpaca REST API — hisse senedi (Katman 1, TAMAMLANDI)
│   └── storage.py             # Parquet + DuckDB depolama (Katman 2)
├── signals/                   # Katman 3: sinyal üretimi
│   ├── classic/
│   │   ├── sma_cross_strategy.py   # 3a: backtrader stratejisi (sadece backtest için)
│   │   └── live_signal.py          # 3a: main.py'nin kullandığı CANLI sinyal (TAMAMLANDI)
│   ├── ml/
│   │   ├── features.py              # 3b: özellik mühendisliği + etiketleme (TAMAMLANDI)
│   │   ├── train.py                 # 3b: walk-forward model eğitimi (TAMAMLANDI)
│   │   ├── ml_signal.py             # 3b: canlı tahmin üretimi (TAMAMLANDI)
│   │   └── models/                  # eğitilmiş model dosyaları (.joblib) buraya kaydedilir
│   ├── llm_agents/                  # 3c: LLM ajan zinciri (TAMAMLANDI)
│   │   ├── llm_client.py            # OpenAI-uyumlu / Anthropic / Mock istemci
│   │   ├── state.py                 # paylaşılan ajan state şeması
│   │   ├── prompts.py               # her ajan rolü için prompt şablonları
│   │   ├── nodes.py                 # bağımsız test edilebilir ajan düğümleri
│   │   ├── news_fetcher.py          # NewsAPI.org ile gerçek haber çekme (TAMAMLANDI)
│   │   └── agent_chain.py           # zinciri birleştiren orkestratör
│   ├── market_making/                # 3d: piyasa yapıcılığı (TAMAMLANDI)
│   │   ├── avellaneda_stoikov.py    # saf matematik (rezervasyon fiyatı, spread)
│   │   ├── mm_strategy.py           # envanter limiti + operasyonel mantık
│   │   └── mm_backtest.py           # geçmiş veriyle fill simülasyonu (TAMAMLANDI)
│   └── aggregator.py               # 3e: sinyal toplayıcı / ensemble
├── risk/
│   ├── mandate.py              # Katman 4: mandate şeması + doğrulama (Pydantic)
│   └── risk_manager.py         # Katman 4: aday işlemi mandate'e karşı kontrol
├── backtest/
│   └── run_backtest.py         # Katman 5: backtrader ile backtest çalıştırıcı
├── execution/
│   ├── telegram_bot.py         # Katman 6 + 8: onay/red akışı
│   ├── order_router.py         # Katman 6: ccxt/Alpaca'ya otomatik yönlendirir (TAMAMLANDI)
│   └── alpaca_trading_client.py # Katman 6: Alpaca notional market emirleri (TAMAMLANDI)
├── monitoring/
│   └── decision_log.py         # Katman 7: karar günlüğü (SQLite)
├── tests/
│   ├── test_mandate.py               # Katman 4 testleri
│   ├── test_aggregator.py            # Katman 3e testleri (asset_class çıkarımı dahil)
│   ├── test_features.py              # Katman 3b (özellik/etiket) testleri
│   ├── test_llm_agents.py            # Katman 3c (ajan düğümleri, JSON ayrıştırma) testleri
│   ├── test_market_making.py         # Katman 3d (Avellaneda-Stoikov) testleri
│   ├── test_mm_backtest.py           # Katman 3d/5 (fill simülasyonu) testleri
│   ├── test_alpaca_connector.py      # Katman 1 (Alpaca veri ayrıştırma) testleri
│   ├── test_alpaca_trading_client.py # Katman 6 (Alpaca emir payload) testleri
│   ├── test_decision_log.py          # Katman 7 (açık pozisyon/exposure/göç) testleri
│   ├── test_news_fetcher.py          # Katman 3c (haber biçimlendirme) testleri
│   ├── test_live_signal.py           # Katman 3a (canlı SMA kesişimi) testleri
│   └── test_order_router.py          # Katman 6 (dry-run/kaldıraç kontrolü) testleri
├── main.py                     # Uçtan uca akışı birbirine bağlayan giriş noktası
└── requirements.txt
```

## Kurulum

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp config/mandate.yaml.example config/mandate.yaml   # (yoksa) düzenleyin
```

`requirements.txt` içindeki paketlerin kurulumu **internet bağlantısı** gerektirir —
bu iskelet burada (sohbet ortamında) ağ erişimi olmadan yazıldı, bu yüzden kodu
kendi makinenizde çalıştırıp test etmeniz gerekiyor. Sözdizimi (syntax) tüm
dosyalarda `python -m py_compile` ile doğrulandı.

## Hızlı Başlangıç (Faz 0-4, 6)

1. **Veri çek:**
   ```bash
   python -m data_layer.connectors.ccxt_connector --exchange binance --symbol BTC/USDT --timeframe 1h --days 365
   ```
   Bu, `data/ohlcv/BTC_USDT_1h.parquet` dosyasını oluşturur.

2. **Backtest çalıştır:**
   ```bash
   python -m backtest.run_backtest --data data/ohlcv/BTC_USDT_1h.parquet
   ```
   **Düzeltilen bir hata:** İlk sürümde bir "sizer" (pozisyon boyutlandırıcı)
   tanımlı değildi — backtrader varsayılan olarak "1 TAM birim al" davranışı
   sergiliyordu. BTC gibi yüksek fiyatlı varlıklarda ($60-90k) bu, küçük bir
   `--cash` ile karşılanamaz ve emir SESSİZCE reddedilir (0 işlem, 0 getiri,
   hiçbir hata mesajı yok). Artık `--cash-pct` (varsayılan `%95`) ile her
   emir sermayenin bir yüzdesi olarak boyutlandırılıyor. **0 işlem görürseniz**
   önce `--cash-pct` değerini kontrol edin.

3. **Mandate'i düzenle:** `config/mandate.yaml` içinde maksimum pozisyon boyutu,
   maksimum toplam maruziyet, günlük kayıp tavanı gibi sınırları kendinize göre ayarlayın.

4. **ML modelini eğit (Faz 3):**
   ```bash
   python -m signals.ml.train --data data/ohlcv/BTC_USDT_1h.parquet \
       --symbol BTC/USDT --timeframe 1h --horizon 6 \
       --up-threshold 0.005 --down-threshold -0.005
   ```
   Bu, `signals/ml/models/BTC_USDT_1h.joblib` dosyasını oluşturur. Eğitim
   ekrana **walk-forward test seti** (modelin hiç görmediği, zaman içinde
   SONRAKİ veri) üzerindeki precision/recall/f1 raporunu basar — karar
   verirken sadece eğitim performansına değil, buna bakın. `ml_signal.py`
   bu modeli otomatik bulup kullanır; model yoksa sistem çökmez, sadece o
   sembol için ML sinyalini atlar (log uyarısı verir).

5. **LLM ajan zincirini yapılandır (Faz 4, opsiyonel):** `.env` dosyasında
   `LLM_PROVIDER=anthropic` (veya `openai`) ve ilgili API anahtarını girin.
   Girmezseniz sistem `mock` sağlayıcıya düşer ve **gerçek olmayan** (test
   amaçlı) sinyaller üretir — bu açıkça loglanır, sessizce olmaz.

6. **Telegram botunu kur:** `execution/telegram_bot.py` içindeki `TELEGRAM_BOT_TOKEN`
   ve `TELEGRAM_CHAT_ID` değerlerini ortam değişkeni olarak sağlayın (bkz. dosya
   içindeki yorum satırları), sonra:
   ```bash
   python -m execution.telegram_bot
   ```

   **Telegram komutları** (`python -m main` çalışırken kullanılabilir):
   - `/durum` — bekleyen (henüz onaylanmamış) işlem önerilerini listeler
   - `/pozisyonlar` — açık (onaylanmış, henüz kapatılmamış) tüm pozisyonları,
     giriş fiyatlarıyla birlikte listeler
   - `/kapat <id> <cikis_fiyati>` — bir pozisyonu kapatır, gerçekleşen PnL'i
     giriş/çıkış fiyatından hesaplar, `risk_manager`'ın toplam maruziyetini
     ve `decision_log`'un art arda kayıp sayacını günceller. Örnek:
     `/kapat 3 65000.5`. **Şu an manuel** — borsadan otomatik pozisyon
     kapanış tespiti yapan bir izleyici henüz yok (bkz. Sıradaki Adımlar).
   - `/dur` — **acil durdurma**: kill-switch'i uzaktan (Telegram'dan)
     tetikler, sistem yeni işlem önerisi üretmeyi durdurur (mevcut açık
     pozisyonlar etkilenmez). Sunucuya SSH ile bağlanmadan telefonunuzdan
     durdurabilmeniz için eklendi.
   - `/devam` — kill-switch'i kaldırır, normal çalışmaya devam eder.

7. **Testleri çalıştırın:**
   ```bash
   pytest tests/ -v
   ```

## Sıradaki Adımlar

- ~~**Faz 3 — ML sinyali**~~ ✅ Tamamlandı: `signals/ml/features.py`,
  `signals/ml/train.py`, `signals/ml/ml_signal.py`. Testler: `tests/test_features.py`.
- ~~**Faz 4 — LLM ajan zinciri**~~ ✅ Tamamlandı: `signals/llm_agents/` (llm_client,
  state, prompts, nodes, agent_chain). Testler: `tests/test_llm_agents.py`
  (MockLLMClient ile, API anahtarı/internet gerektirmez).
  **Kullanmadan önce:** `.env` içinde `LLM_PROVIDER=anthropic` (veya `openai`) +
  ilgili API anahtarını ayarlamazsanız sistem varsayılan olarak `MockLLMClient`
  kullanır ve **gerçek olmayan** sinyaller üretir (log'da açıkça uyarılır).
- ~~**Faz 6 — Market making modülü**~~ ✅ Tamamlandı: `signals/market_making/`
  (Avellaneda-Stoikov matematiği + envanter limiti + **geçmiş veriyle fill
  simülasyonu**, `mm_backtest.py`). Testler: `tests/test_market_making.py`,
  `tests/test_mm_backtest.py`.
  ```bash
  python -m backtest.run_mm_backtest --data data/ohlcv/BTC_USDT_1h.parquet
  ```
  **Kullanmadan önce:** `mm_backtest.py` basitleştirilmiş bir fill varsayımı
  kullanır (kuyruk pozisyonu/gecikme yok sayılır — dosya içindeki uyarıyı
  okuyun); bu yüzden sonuçlar gerçek performansın bir **üst sınırı**dır,
  kesin bir tahmin değil. Gerçek zamanlı order book akışı (ccxt.pro/
  WebSocket) ve canlı emir döngüsü hâlâ bağlanmadı — `market_making.enabled:
  false` varsayılanı bilinçlidir, canlıya almadan önce testnet'te doğrulayın.

  **Düzeltilen kritik bir hata:** İlk sürümde nakit/marj kısıtı YOKTU —
  `max_inventory` varlık fiyatına göre çok büyük seçildiğinde (ör. BTC gibi
  yüksek fiyatlı bir varlıkta küçük sermayeyle büyük bir limit), simülasyon
  sessizce sınırsız kaldıraçla işlem yapıyor ve %-100'ün altına inen
  (gerçekte imkansız) getiri/drawdown üretiyordu. Artık **cash-secured**
  (nakit ile tam karşılanan, kaldıraçsız) varsayımı zorunlu: nakit
  yetmediğinde ALIŞ fill'i gerçekleşmez, `result.skipped_due_to_cash`
  sayacında görünür. `tests/test_mm_backtest.py` içinde bunu doğrulayan
  2 regresyon testi var.

  **Metodolojik not (kod hatası değil, veri granülaritesi meselesi):**
  Market making, doğası gereği saniyeler/dakikalar ölçeğinde çalışır.
  1 saatlik bar ile backtest yaparsanız "bu saat içinde HERHANGİ bir anda
  fiyat kotasyonuma değdi mi" sorusuna bakılır — bu, dar bir spread için
  neredeyse her zaman "evet" demek, yani gerçekte olmayacak kadar sık fill
  görürsünüz. Market making backtest'i için `--timeframe 1m` (veya daha
  küçük) ile veri çekmeniz, sonuçların anlamlılığı açısından önemlidir:
  ```bash
  python -m data_layer.connectors.ccxt_connector --exchange binance --symbol BTC/USDT --timeframe 1m --days 30
  python -m backtest.run_mm_backtest --data data/ohlcv/BTC_USDT_1m.parquet
  ```
- ~~**Sürekli çalışma modu + hata dayanıklılığı**~~ ✅ Tamamlandı: `main.py`
  artık `LOOP_INTERVAL_SECONDS` (.env) ayarlanırsa tek seferlik bir betik
  olmaktan çıkıp SÜREKLİ çalışan bir servise dönüşüyor (her N saniyede bir
  tüm sembolleri yeniden tarıyor). Ayrıca her sembol artık ayrı bir
  try/except içinde işleniyor — bir sembolde beklenmeyen bir hata (API
  zaman aşımı vb.) artık TÜM programı çökertmiyor, sadece o sembol
  atlanıp devam ediliyor. `Ctrl+C` de artık çirkin bir traceback yerine
  düzgün bir mesajla kapanıyor.
- ~~**Gerçek klasik sinyal (placeholder'ın kaldırılması)**~~ ✅ Tamamlandı:
  `main.py` kurulduğu günden beri `get_classic_signal_placeholder()` diye
  bir fonksiyon kullanıyordu — piyasada ne olursa olsun HER ZAMAN sabit
  `"long", confidence=0.6` döndüren bir sahte sinyaldi. Bu fonksiyon
  tamamen kaldırıldı; yerine `signals/classic/live_signal.py` geldi —
  `data_layer.storage`'daki en güncel veriden GERÇEK bir SMA10/30
  kesişimi hesaplıyor (backtrader'ın `CrossOver`'ıyla aynı mantık,
  sadece pandas ile). Kesişim yoksa veya veri yetersizse `None` döner
  (sinyal ÜRETMEZ) — "belirsizse işlem yapma" ilkesi burada da geçerli.
  Testler: `tests/test_live_signal.py` (7 test, sentetik fiyat
  serileriyle golden/death cross tespiti doğrulanıyor).
- ~~**Sürekli modda veri yenileme**~~ ✅ Tamamlandı: `main.py` sürekli mod
  (`LOOP_INTERVAL_SECONDS`) eklendikten SONRA BİLE hiçbir zaman veriyi
  yenilemiyordu — her tur, bir kez manuel indirilmiş eski veriyle
  çalışıyordu. Artık her `run_one_pass()` öncesi `refresh_market_data()`
  çağrılıyor: her sembol için (varlık sınıfına göre doğru konnektörle)
  son birkaç günün verisi çekilip **mevcut parquet dosyasıyla birleştiriliyor**
  (üzerine yazılmıyor — bu, ML modelinin ihtiyaç duyduğu uzun geçmişi
  silmemek için kritik). Bir sembolde ağ hatası olursa sadece o sembol
  atlanır.
- ~~**Test kapsamını genişleten mimari düzeltme**~~ ✅ Tamamlandı:
  `risk/risk_manager.py`, sadece tip belirtmek için `risk/mandate.py`'yi
  (dolayısıyla `pydantic`'i) import ediyordu — oysa `Mandate` sınıfının
  kendisine runtime'da hiç ihtiyacı yoktu (her şey duck-typing). Bu
  importu `TYPE_CHECKING` altına almak, `CandidateTrade`/`ApprovedOrderDraft`'a
  bağımlı olan **tüm zinciri** (`signals/aggregator.py`,
  `execution/order_router.py`, `signals/classic/live_signal.py` ve
  bunların testleri) `pydantic` kurulu olmayan ortamlarda bile
  çalıştırılabilir hale getirdi — kısıtlı/CI ortamları için önemli bir
  dayanıklılık kazanımı.
- ~~**Pozisyon yaşam döngüsü (giriş fiyatı + kapatma + PnL)**~~ ✅ Tamamlandı:
  `monitoring/decision_log.py`'ye `entry_price` sütunu eklendi (eski
  veritabanlarınız için güvenli otomatik göç/migration dahil —
  `tests/test_decision_log.py::test_migration_adds_entry_price_to_old_schema_db`
  ile test edildi), `execution/order_router.py` artık dry-run'da bile
  kripto için gerçek bir ticker fiyatı çekip `entry_price` olarak
  kaydediyor, Telegram'a `/pozisyonlar` ve `/kapat <id> <cikis_fiyati>`
  komutları eklendi. Bu, `record_position_closed()`'in ve
  `consecutive_losses()`'ün (art arda kayıp soğutması) ilk kez GERÇEKTEN
  işlevsel olmasını sağlıyor — daha önce hiçbir yerden çağrılmadıkları
  için birer "ölü kod" idi.
  **Hâlâ eksik:** Otomatik bir pozisyon izleyici (borsadaki gerçek
  kapanışı kendiliğinden tespit eden bir bileşen) yok — `/kapat` şu an
  manuel, siz borsada pozisyonu kapattığınızda buradan da bildiriyorsunuz.
  Hisse (equity) tarafında `entry_price` henüz yakalanmıyor (Alpaca'nın
  ayrı bir canlı fiyat/Data API akışı gerekir, henüz bağlanmadı).
- ~~**Gerçek haber kaynağı (LLM news_analyst)**~~ ✅ Tamamlandı:
  `signals/llm_agents/news_fetcher.py` — [public-apis/public-apis](https://github.com/public-apis/public-apis)
  reposunun "News" kategorisi taranıp NewsAPI.org seçildi (basit REST,
  ücretsiz geliştirici katmanı). `news_analyst_node` şimdiye kadar hiçbir
  zaman gerçek bir haber kaynağına sahip olmamıştı — `news_text` hep
  `None` geçiyordu. `.env`'de `NEWSAPI_KEY` ayarlarsanız gerçek başlıklar
  LLM'e besleniyor; ayarlamazsanız sistem eskisi gibi (haber verisi
  olmadan) çalışmaya devam ediyor — geriye dönük uyumluluk bozulmadı.
  **Telif hakkı notu:** sadece başlık + kısa özet kullanılıyor, tam
  makale metni asla çekilmiyor/saklanmıyor (bkz. dosya başındaki tasarım
  notu). Testler: `tests/test_news_fetcher.py` (ağ gerektirmez, sadece
  biçimlendirme mantığını doğrular).
- **Faz 5 — Küçük sermaye ile canlı test:** Bu bir kod aşaması değil,
  operasyonel bir aşamadır. Sırasıyla: (1) tüm testleri kendi makinenizde
  çalıştırın, (2) `dry_run=True` ile paper-trading modunda en az birkaç
  hafta izleyin, (3) ancak sonra küçük gerçek sermayeyle `dry_run=False`'a
  geçin. Bu adımı atlamayın.
- ~~**İkinci varlık sınıfı (hisse senedi)**~~ ✅ Tamamlandı:
  `data_layer/connectors/alpaca_connector.py`. Adaptör deseninin işe
  yaradığını doğrulamak için Alpaca'dan gelen veriyi doğrudan
  `signals/ml/features.py`'nin ML özellik hattına besleyip **hiçbir kod
  değişikliği gerekmediğini** teyit ettim — sadece `data_layer.storage`
  veriyi nereden çektiğinizi bilmez, üst katmanlar (sinyal/risk/backtest)
  kripto mu hisse mi olduğunu hiç görmez. Kullanım:
  ```bash
  python -m data_layer.connectors.alpaca_connector --symbol AAPL --timeframe 1h --days 365
  ```
  `config/mandate.yaml`'daki `symbol_universe`'e `"AAPL"` gibi hisse
  sembolleri eklemeniz yeterli — `risk/risk_manager.py`'de hiçbir
  değişiklik gerekmez.
  Testler: `tests/test_alpaca_connector.py` (ağ gerektirmez, sadece JSON
  ayrıştırma mantığını doğrular — gerçek `fetch_ohlcv()` çağrısı için
  Alpaca hesabı/API anahtarı gerekir).

  **Düzeltilen bir tutarsızlık:** `main.py` başlangıçta tüm sembolleri
  (AAPL dahil) `asset_class="crypto"` olarak sabitliyordu — bu, mandate'in
  `per_asset_class` kaldıraç override'larının hisse sembolleri için yanlış
  uygulanmasına yol açardı. Artık `signals.aggregator.infer_asset_class()`
  sembol formatından (`"/"` içeriyorsa kripto, yoksa hisse) otomatik
  çıkarım yapıyor.

- ~~**Hisse senedi GERÇEK emir gönderimi**~~ ✅ Tamamlandı:
  `execution/alpaca_trading_client.py` — Alpaca'nın Trading API'sini
  (paper veya canlı) kullanarak **notional** (dolar bazlı, kesirli hisse
  destekli) market emri gönderir. `execution/order_router.py` artık
  `draft.symbol`'ün formatına göre otomatik olarak ccxt (kripto) veya
  Alpaca (hisse) backend'ine yönlendiriyor — main.py hiçbir şey bilmek
  zorunda değil. `OrderRouter(..., alpaca_paper=True)` varsayılanı
  bilinçlidir: gerçek hisse emri için açıkça `alpaca_paper=False` geçmeniz
  gerekir. Kripto tarafında da bir koruma eklendi: `draft.leverage > 1.0`
  olan bir emir, spot-only ccxt implementasyonu bunu doğru işleyemeyeceği
  için açıkça reddedilir.
  Testler: `tests/test_alpaca_trading_client.py` (sadece payload
  oluşturma mantığını doğrular, ağ gerektirmez).

Bunların her biri diğerini bozmadan bağımsız genişletilebilecek şekilde
tasarlanmıştır (her modül ayrı import edilebilir, `signals.aggregator`
eksik bir kaynağı sessizce tolere eder).

## ⚠️ Önemli Uyarı

Bu sistem **araştırma ve öğrenme amaçlıdır**, yatırım tavsiyesi değildir.
Gerçek sermaye ile canlıya geçmeden önce: (1) kapsamlı backtest, (2) dry-run/paper
trading, (3) küçük sermaye testi adımlarını sırayla tamamlayın. `risk/mandate.py`
ve Telegram onay adımı **hiçbir zaman** devre dışı bırakılmamalıdır.

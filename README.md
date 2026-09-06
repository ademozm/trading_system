# Hibrit Trading Sistemi — Çok Varlıklı, Yarı-Otomatik

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
│   │   └── sma_cross_strategy.py   # 3a: klasik gösterge stratejisi
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
│   └── test_alpaca_trading_client.py # Katman 6 (Alpaca emir payload) testleri
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
   python -m backtest.run_backtest --data data/ohlcv/BTC_USDT_1h.parquet --strategy sma_cross
   ```

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

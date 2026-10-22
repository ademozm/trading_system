# Çoklu Piyasa Hisse/Kripto Tarama ve Analiz Sistemi

Gün içi birden fazla kez çalışabilen, ABD hisseleri + BIST + kripto
paraları tarayan, rejim-uyarlamalı (trend/yatay) sinyal üreten, sonuçları
skorlayıp Excel raporu olarak sunan uçtan uca bir sistem.

## 🖱️ Tarayıcıda Görsel Panel (terminal komutu yazmadan kullanmak için)

Kurulumu bir kere yaptıktan sonra (aşağıdaki "Kurulum" bölümü), her
seferinde terminale komut yazmak yerine:

- **Windows:** `uygulamayi_baslat.bat` dosyasına **çift tıkla**
- **Mac:** `uygulamayi_baslat.command` dosyasına çift tıkla (ilk seferinde
  sağ tık → "Aç" demen gerekebilir, Mac güvenlik uyarısı verir)

Birkaç saniye sonra tarayıcında (Chrome/Edge) otomatik bir sekme açılır.
Bu artık sadece bir tablo değil, **gerçek bir görsel panel**:

- **KPI kartları**: toplam sinyal, AL/SAT sayısı, ortalama skor, şüpheli
  veri sayısı, yaklaşan önemli ekonomik olay sayısı — bir bakışta özet
- **📊 Genel Bakış sekmesi**: piyasa dağılımı (pasta grafik), skor
  dağılımı (histogram), en iyi 10 AL/SAT (çubuk grafik)
- **📈 Grafik İnceleme sekmesi**: istediğin sembolü seç, interaktif mum
  grafiği + EMA çizgileri + destek/direnç seviyeleri + hacim grafiği
  açılsın
- **💼 Piyasalar, 🔬 Temel & Risk & Gelişmiş, ⚠️ Hata Raporu**: detaylı
  tablolar, renk skalalı skorlar
- **🎯 Grid & DCA sekmesi**: grid seviyelerini merdiven grafiğinde, DCA
  planını basamaklı çizgide gör
- **📰 Haberler sekmesi**: renkli ton göstergeli haber kartları
- **📅 Ekonomik Takvim sekmesi**: yaklaşan Fed/NFP/CPI olayları kart
  görünümünde
- **📜 Geçmiş Performans sekmesi**: sinyallerin zaman içindeki başarı
  istatistikleri

Excel dosyasını da aynı sayfadan indirebilirsin — panel, Excel'in
YERİNE değil, ONA EK bir görselleştirme katmanı.

Kapatmak için tarayıcı sekmesini kapat, sonra açılan siyah pencereyi de
kapatabilirsin (veya bir tuşa basıp devam et).

## Mimari v2 — Tam Kapsamlı Analiz

Artık sistem sadece teknik göstergelere değil, **beş bağımsız analiz
katmanına** bakıyor:

| Katman | Ne ölçer | Kripto'da geçerli mi |
|---|---|---|
| Teknik (ADX/EMA/RSI/MACD) | Trend/rejim, momentum, risk/ödül | ✅ |
| Temel analiz | F/K, PEG, ROE, borç/özkaynak, büyüme, kâr marjı | ❌ (kavram yok) |
| Göreceli güç | Kendi piyasa endeksine (SPY/XU100/BTC) karşı performans | ✅ |
| Hacim + haftalık teyit | Bağıl hacim, OBV yönü, haftalık trend uyumu | ✅ |
| Risk metrikleri | Yıllık volatilite, maks. düşüş, 52 haftalık aralık, beta | ✅ |

Bir sembolde bir katman eksikse (örn. kriptoda temel analiz), skorlama
motoru o bileşeni **otomatik olarak dışarıda bırakıp kalan ağırlıkları
yeniden normalize eder** — kripto, olmayan bir veri yüzünden haksız
şekilde düşük puan almaz.

```
1. Evren yönetimi      → universe.py, data/universe_*.csv
2. Veri toplama         → data_pipeline/fetcher.py, cache.py (fiyat + benchmark)
3. Veri doğrulama       → data_pipeline/validator.py
4. Teknik analiz        → analysis/strategy.py, indicators.py
5. Temel analiz         → analysis/fundamentals.py
6. Göreceli güç         → analysis/relative_strength.py
7. Hacim/haftalık teyit → analysis/confirmations.py
8. Risk metrikleri      → analysis/risk_metrics.py
9. Skorlama (v2)        → analysis/scorer.py — tüm katmanları dinamik ağırlıklandırır
10. Filtreleme          → analysis/filters.py — kullanıcı kriterlerine göre süzer
11. Rapor oluşturma     → reporting/excel_report.py — 9 sayfalı Excel
12. Zamanlama           → scheduler.py, main_scan.py
```

## Filtreleme

`config.py > FILTERS` içinde varsayılanlar tanımlı; CLI'dan override edilebilir:

```bash
python main_scan.py --markets us bist crypto --min-score 0.3 --only-buy
python main_scan.py --markets us --max-pe 40 --min-market-cap 5000000000
python main_scan.py --markets us --skip-fundamentals   # hızlı, sadece teknik+göreceli güç
```

Filtreler eksik veriyi (örn. kriptoda P/E yok) cezalandırmaz — sadece o
kriter için değerlendirmeye almaz, sembolü otomatik elemez.



## Kurulum (kendi bilgisayarında)

```bash
cd trading_system
pip install -r requirements.txt
```

## İlk çalıştırma öncesi: gerçek listeleri çek

Depoda gelen `data/universe_*.csv` dosyaları KÜÇÜK ÖRNEK listelerdir
(40 ABD + 30 BIST + 15 kripto = 85 sembol) — bu sandbox'ın interneti
kısıtlı olduğu için tam liste çekilemedi. Kendi bilgisayarında gerçek,
güncel listeleri çekmek için:

```bash
python fetch_universe_lists.py --markets us crypto
```

Bu, S&P 500 + Nasdaq-100'ü Wikipedia'dan, ilk 50 kripto parayı
CoinGecko'dan çeker ve `data/universe_us.csv` / `universe_crypto.csv`
dosyalarını günceller. BIST için otomatik kaynak yok; `data/universe_bist.csv`
dosyasını elle güncellemen gerekir (script çalıştığında talimat basar).

## Çalıştırma

```bash
# Tüm piyasaları tara, Excel raporu oluştur
python main_scan.py --markets us bist crypto

# Sadece ABD, cache kullanmadan (taze veri zorla)
python main_scan.py --markets us --no-cache
```

Çıktı: `reports/tarama_YYYYMMDD_HHMMSS.xlsx` — sayfalar: Özet (en iyi
20 al/sat adayı), ABD, BIST, Kripto, Hata Raporu.

## Gün içi otomatik çalıştırma

İki yöntem, `scheduler.py` içinde detaylı anlatılıyor:

1. **Basit**: `python scheduler.py` çalıştır, terminali açık bırak.
   `config.py` içindeki `SCAN_TIMES_TR` listesinde tanımlı saatlerde
   (varsayılan 10:30, 13:00, 16:00, 19:00) otomatik tarar.
2. **Önerilen**: İşletim sistemi zamanlayıcısı (cron / Windows Task
   Scheduler) — bilgisayar arka planda çalışırken de güvenilir çalışır.
   Örnek cron satırı `scheduler.py` içinde.

## Test etme

```bash
python -m pytest tests/ -v          # 72 birim/entegrasyon testi
python verify_full_system.py        # Uçtan uca doğrulama (sentetik veri + kasıtlı bozuk veri)
```

Excel raporu artık 9 sayfa içerir: Özet, Filtrelenmiş, ABD, BIST, Kripto,
Temel Analiz, Risk Metrikleri, Filtre Özeti, Hata Raporu.

`verify_full_system.py` gerçekçi bir stres testidir: bazı sembollerin
verisini kasıtlı olarak bozar (eksik kolon, yetersiz satır) ve sistemin
çökmeden, doğru hata raporlayarak devam ettiğini doğrular.

## ÖNEMLİ — Bu sandbox'ta neden gerçek veriyle test edilmedi

Bu ortamın ağ erişimi Yahoo Finance ve CoinGecko'ya kapalı. Bu yüzden
tüm doğrulama sentetik (rastgele üretilmiş) veriyle yapıldı — kodun
MANTIĞININ doğru çalıştığını kanıtlar, ama gerçek piyasa performansı
hakkında hiçbir şey söylemez. Kendi bilgisayarında gerçek verilerle
çalıştırdığında sonuçlar tamamen farklı olacaktır.

## Skorlama mantığı (özet)

Farklı piyasalar (BIST hissesi, ABD hissesi, kripto) doğrudan
karşılaştırılamaz — farklı volatilite rejimleri, farklı birimler.
`analysis/scorer.py` her sembolü şu bileşenlerle -1 ile +1 arasında
tek bir skora indirger:
- **Sinyal gücü** (%35): ADX'in eşik üstündeki gücü / RSI'ın aşırı bölgeden uzaklığı
- **Momentum** (%25): son 20 günlük getiri
- **Risk/ödül** (%25): ATR tabanlı hedef/stop mesafesi oranı
- **Volatilite cezası** (%15): aşırı oynaklık skoru düşürür

Ağırlıklar `config.py > SCORE_WEIGHTS` içinden değiştirilebilir.

## Bilinen sınırlamalar ve dürüst uyarılar

1. **"Kusursuz sistem" yoktur.** Bu sistem sağlam mühendislik (test
   edilmiş, hataya dayanıklı, şeffaf) sağlar — piyasa performansı
   garantisi değil. Hiçbir backtest veya tarama sistemi bunu veremez.
2. **yfinance ücretsiz/gayri resmi bir kaynaktır.** Büyük evrenlerde
   (yüzlerce-binlerce sembol) sık çekim yapmak IP kısıtlamasına yol
   açabilir. Cache + batch + delay bunu azaltır ama sıfırlamaz.
   Ölçek büyüdükçe ücretli bir sağlayıcıya (Polygon.io, Finnhub,
   Alpaca Data) geçmeyi düşün.
3. **Varsayılan parametreler otomatik optimize edilmiyor.** ADX eşiği,
   RSI seviyeleri, ATR çarpanları makul varsayılan değerlerdir. Artık
   bunları `run_walk_forward.py` ile optimize edebilirsin (bkz. "v8"
   bölümü) ama sonuç main_scan.py'ye OTOMATİK yansımaz — bulduğun
   parametreleri `analysis/strategy.py`'ye elle girmen gerekiyor.
6. **Temel analiz çekimi yavaştır.** yfinance'in `.info` çağrısı sembol
   başına ayrı bir HTTP isteğidir. Büyük evrenlerde (yüzlerce sembol)
   tam tarama birkaç dakika sürebilir. Hızlı sonuç istiyorsan
   `--skip-fundamentals` kullan.
7. **Beta/göreceli güç hesapları benchmark verisinin doğruluğuna bağlı.**
   `XU100.IS` gibi endeks sembolleri yfinance'te bazen tutarsız veri
   verebilir; sonuç şüpheli görünüyorsa `analysis/relative_strength.py`
   içindeki `BENCHMARKS` sözlüğünü kontrol et.
4. **BIST intraday veri sınırlıdır.** yfinance BIST için çoğunlukla
   günlük veri sağlar; "gün içi birkaç kez tarama" pratikte günlük
   veriyi birkaç kez yeniden değerlendirmek anlamına gelir, her taramada
   yeni mum oluşmaz. Gerçek gün içi (intraday) analiz için BIST'e özel
   ücretli bir veri kaynağı gerekir.
5. **Bu bir yatırım tavsiyesi değildir.** Üretilen AL/SAT sinyalleri
   kural tabanlı bir modelin çıktısıdır, finansal tavsiye değildir.
   Kararların sorumluluğu sana aittir; gerekirse bir yatırım
   danışmanına başvur.
8. **"Tüm borsa sembolleri" değil, "en önemli 100 + 100 + 100 + altın".**
   Binlerce/on binlerce sembole (dünyadaki tüm hisseler, tüm kripto
   paralar) erişim ücretli kurumsal veri sağlayıcı gerektirir. Bu sistem
   bilinçli olarak ABD'nin en büyük 100 şirketi + BIST 100 + piyasa
   değerine göre ilk 100 kripto + altına odaklanıyor — bu, "her şeyi
   yüzeysel taramak" yerine "önemli olanı derinlemesine taramak" tercihi.
9. **Haber "analizi" basit anahtar kelime sayımıdır, gerçek NLP değil.**
   Detaylar için yukarıdaki "v4 — Haber analizi" bölümüne bakın.

## 🆕 v14 — Sembol Listesi Tazelik Hatası, Tam Teknik Grafik, Sektör Bilgisi

### "Taranan sembol sayısı çok az" sorununun gerçek kök sebebi

Bu, önceki "gold hatası" ile aynı KATEGORİ ama farklı bir hataydı.
`universe.auto_refresh_if_stale`, sembol listesinin yaşını **dosya
mtime'ına** bakarak hesaplıyordu. Ama **GitHub Actions ve Streamlit
Cloud gibi ortamlar repoyu her çalıştırmada `git clone` ile çeker** —
bu işlem TÜM dosyaların mtime'ını "şimdi"ye sıfırlar, içerik aylar
önceki küçük örnek liste olsa bile. Sonuç: sistem listeyi her zaman
"güncel" sanıyor, **hiçbir zaman** canlı S&P 100/kripto 200 listesini
çekmiyordu — sadece depoya gömülü küçük örnek listeyle (≈139 sembol)
çalışıyordu.

**Düzeltme:** Tazelik artık dosya mtime'ı yerine `data/universe_meta.json`
adlı bir dosyaya kaydedilen GERÇEK son güncelleme tarihine göre
hesaplanıyor. Bu dosya git ile taşınan İÇERİK olduğu için checkout'tan
etkilenmiyor. Ayrıca bu dosyada hiç kayıt yoksa (ilk kurulum/ilk
deployment) yaş SONSUZ sayılıyor — yani ilk çalıştırmada KESİNLİKLE
canlı çekim denenir.

Bununla birlikte, canlı çekim başarısız olsa bile daha zengin bir
"kutudan çıkan" deneyim için varsayılan listeler de genişletildi:
**ABD 40 → 107, kripto 15 → 50** sembol (BIST 80, emtia 4 ile birlikte
toplam ≈241).

### Grafik İnceleme artık tam bir teknik analiz paneli

`reporting/dashboard_charts.py > full_technical_chart()`: tek bir
grafikte senkronize 5 panel — Fiyat+EMA+Bollinger Bantları+destek/direnç,
Hacim, RSI (30/70 çizgileriyle), MACD (histogram+sinyal), ADX (eşik
çizgisiyle). Hepsi ham OHLC verisinden otomatik hesaplanıyor.

### Sektör/endüstri bilgisi

`analysis/fundamentals.py`'ye `sector`/`industry` alanları eklendi —
skorlamaya dahil edilmiyor (kategorik veri, percentile anlamsız) ama
"Temel Analiz" sayfasında bağlam olarak gösteriliyor. Portföy korelasyon
kontrolüyle birlikte kullanışlı: aynı sektörden çok sinyal görürsen,
muhtemelen zaten korelasyonlu çıkacaklarını önceden tahmin edebilirsin.

### public-apis/public-apis deposu değerlendirildi

Kullanıcı isteği üzerine bu 1400+ API'lik liste incelendi. Dürüst
sonuç: **büyük çoğunluğu alakasız** (anime, oyun, coğrafya vb.), finans
kategorisindeki çoğu zaten yfinance/Stooq/CoinGecko ile örtüşüyor.
**CoinCap** (ücretsiz, key gerektirmeyen kripto API'si) değerlendirildi
ama kripto kimlik eşlemelerinin (`bitcoin`, `ethereum` gibi slug'lar)
bazılarından tam emin olunamadığı için EKLENMEDİ — yanlış bir eşleme,
veri olmamasından daha kötü sonuç doğurur (tam olarak önceki "altın
hatası" gibi). Bunun yerine daha güvenli olan opsiyonel **NewsAPI.org**
desteği değerlendirildi (kullanıcının kendi ücretsiz key'iyle).

### Bu turda yaşanan tekrarlayan bir durum

Bu özellik geliştirilirken sandbox **üç kez daha** sıfırlandı. Her
seferinde `/mnt/user-data/outputs/trading_system.zip`'teki en son
teslim edilen paketten geri yüklenip kaldığı yerden devam edildi — iş
kaybı olmadı. Bu, düzenli zip teslimatının pratikte ne kadar değerli
bir güvenlik ağı olduğunu bir kez daha gösterdi.

## 🆕 v13 — Paper Trading (Sanal Portföy)

### Neden gerekliydi?

`journal.py` ve `grid_dca_journal.py` TEKİL sinyalleri/emirleri takip
ediyordu ("bu sinyal tuttu mu"). Ama "sistemin sinyallerini gerçekten
takip etseydim param şu an ne durumda olurdu" sorusuna cevap veren
GERÇEK BİR PORTFÖY simülasyonu yoktu.

### Ne yapıyor?

`analysis/paper_trading.py` (SQLite tabanlı), her taramada:
- **Açık pozisyonları günceller**: stop/hedef seviyesine değdi mi kontrol
  eder, değdiyse kapatır
- **Yeni sinyalleri işler**: AL sinyali + o sembolde açık pozisyon yoksa
  + yeterli nakit varsa → yeni pozisyon açar (miktar: position_sizing.py
  + portfolio_correlation.py'nin zaten hesapladığı, korelasyon-düzeltmeli
  öneri). SAT sinyali + açık pozisyon varsa → pozisyonu kapatır (çıkış
  sinyali olarak)
- **Equity anlık görüntüsü kaydeder**: nakit + açık pozisyonların güncel
  piyasa değeri, zaman içinde bir equity eğrisi oluşturur

Yeni sayfa: **"Paper Trading"** (Excel) / **💼 Paper Trading** (panel) —
başlangıç bakiyesi, mevcut equity, toplam getiri, kazanma oranı,
Sharpe oranı, maksimum düşüş.

```bash
python main_scan.py --skip-paper-trading  # atlamak istersen
```

**Sistem, açığa satış YAPMAZ** — sadece uzun (long) pozisyonları yönetir,
SAT sinyalini "çıkış" olarak yorumlar. Bu, karmaşıklığı ve riski sınırlı
tutmak için bilinçli bir tasarım kararı.

### Bu turda yaşanan (ve çözülen) ciddi bir olay

Bu özelliği geliştirirken **sandbox ortamı tamamen sıfırlandı** —
`/home/claude/trading_system` klasörünün TAMAMI kayboldu. Neyse ki bir
önceki teslim edilen zip dosyası (`/mnt/user-data/outputs/`) hâlâ
duruyordu — sistem oradan geri yüklenip kaldığı yerden devam edildi,
hiçbir iş kaybı olmadı. **Bu, düzenli olarak teslim edilen zip
dosyalarının aynı zamanda bir yedek işlevi gördüğünün kanıtı** — eğer
kendi bilgisayarında da GitHub'a düzenli push yapıyorsan, benzer bir
güvenlik ağın var demektir.

Ayrıca bu turda, `update_open_positions`'ın testlerinde grid_dca_journal
testlerinde daha önce yakaladığımızla AYNI KATEGORİ bir zamanlama sorunu
çıktı (test verisi sabit eski bir tarihte, kod ise gerçek `datetime.now()`
kullanıyor) — aynı prensiple (fiyat verisinin sonunu gerçek "şimdi"den
ileriye sabitleyerek) çözüldü.

## 🆕 v12 — Döviz Kaldırıldı, Emtia'da Gerçek Kök Sebep Bulundu

### Döviz kurları piyasası kaldırıldı

Kullanıcı isteği üzerine — sistem artık sadece **ABD, BIST, Kripto,
Emtia** taranıyor. `data/universe_forex.csv` silindi, tüm kod
yollarından "forex" referansları temizlendi.

### Emtia'da üçüncü kez çıkan hatanın GERÇEK kök sebebi

Önceki iki turda (v5, v9) Volume-NaN ve ticker seçimi sorunlarını
düzelttik ama sorun devam etti. Bu sefer kod tabanını satır satır
denetleyerek asıl kök sebebi bulduk:

**`data_pipeline/fetcher.py > _fetch_one`, veri "tamamen boş değilse"
başarılı sayıyordu — `MIN_ROWS_REQUIRED` (60 gün) kontrolünü HİÇ
yapmıyordu.** Yani `CL=F` gibi bir vadeli işlem sözleşmesi (rollover
kısıtı yüzünden) sadece 5-10 günlük veri dönse bile bu "başarılı"
sayılıp cache'leniyordu — ne yeniden deneniyor, ne Stooq yedeğine
düşülüyordu. Yetersizlik sadece ÇOK SONRA, `validator.py`'de fark
ediliyordu ve o noktada yedek kaynağa geçmek için artık geç
kalınmış oluyordu.

**Düzeltme:** `MIN_ROWS_REQUIRED` kontrolü artık `_fetch_one` içinde de
yapılıyor — yetersiz veri artık gerçek bir "başarısızlık" sayılıyor,
yeniden deneme + yedek kaynak zincirini tetikliyor.

### Yeni: alternatif sembol zinciri

`config.py > ALTERNATE_TICKERS`: bir sembol yfinance'ten tüm
denemelerinde başarısız olursa, Stooq'a düşmeden ÖNCE alternatif Yahoo
sembolleri de deneniyor:

```python
ALTERNATE_TICKERS = {
    "XAUUSD=X": ["GC=F"],   # spot başarısız olursa vadeliye düş
    "GC=F": ["XAUUSD=X"],   # ya da tam tersi
    "XAGUSD=X": ["SI=F"],
    "SI=F": ["XAGUSD=X"],
}
```

Şimdi altın için üç kademeli bir güvenlik ağı var: **spot ticker →
vadeli ticker (alternatif) → Stooq (bağımsız kaynak)**. Üçü birden aynı
anda başarısız olma ihtimali, tek bir kaynağa bağımlı olmaktan çok
daha düşük.

`tests/test_fetcher.py`'ye bu tam senaryoyu (yetersiz veri → alternatif
sembole geçiş) kapsayan regresyon testleri eklendi.

## 🆕 v11 — Portföy-Seviyesi Korelasyon Kontrolü

### Sorun neydi?

`position_sizing.py`, her sinyali BAĞIMSIZ bir bahis gibi boyutlandırıyordu
(her biri hesabın %1'ini riske atacak şekilde). Ama aynı anda gelen 5
sinyal birbirine yüksek korelasyonluysa (örn. hepsi aynı sektör, ya da
hepsi genel piyasa yönünü takip ediyorsa), bunlar aslında bağımsız değil
— piyasa ters giderse hepsi aynı anda zarar edebilir. Bu durumda gerçek
risk, "5 × %1 = %5" değil, korelasyon derecesine göre çok daha yüksek
olabilir.

### Çözüm

`analysis/portfolio_correlation.py`: sinyal üreten sembollerin son 60
günlük getirileri arasında korelasyon matrisi hesaplanır. Yüksek
korelasyonlu (varsayılan eşik: 0.7) semboller bir "küme" olarak
gruplanır (bağlı bileşen/connected components algoritmasıyla). Aynı
kümedeki sembollerin önerilen pozisyon büyüklüğü, küme büyüklüğüne göre
aşağı çekilir — örneğin 3'lü bir kümede her biri 1/3'e iner, böylece
küme toplamda tek bir bağımsız pozisyon kadar risk bütçesi kullanır.

Yeni sütunlar (Özet sayfasında): `Korelasyon Kümesi`, `Düzeltilmiş
Pozisyon ($)`, `Düzeltilmiş Portföy Yüzdesi %`. Yeni sayfa: **"Portföy
Korelasyonu"** (Excel'de) / **🔗 Portföy Korelasyonu** (panelde) —
korelasyon ısı haritası + küme özeti + uyarı.

```bash
python main_scan.py --skip-correlation-check  # atlamak istersen
```

**Dürüstlük notu:** Bu basit, sezgisel bir düzeltmedir — modern portföy
teorisindeki gibi tam bir kovaryans optimizasyonu (risk paritesi vb.)
YAPMAZ. En azından "bunlar birbirinden bağımsız değil" uyarısı verir ve
kaba bir düzeltme sunar; profesyonel bir portföy yöneticisinin yerini
tutmaz.

### Bu turda bulunan bir hata daha

`reporting/dashboard_charts.py`'ye yeni `correlation_heatmap()`
fonksiyonu eklenirken, hemen altındaki `grid_ladder_chart()`
fonksiyonunun `def` satırı yanlışlıkla silinmiş (gövdesi kalmış).
Fonksiyonun kendi testi zaten var olduğu için (`test_grid_ladder_chart_*`)
bu, testler çalıştırılır çalıştırılmaz hemen yakalandı — düzeltildi.
Bu, sistemdeki her fonksiyonun neden ayrı test edilmesi gerektiğinin
canlı bir örneği.

## 🆕 v10 — Çok Sayfalı Site, Tam Şeffaflık, Grid/DCA Emir Takibi

### "Emtia boş görünüyor" sorunu çözüldü — ama farklı bir sebeple

Teşhis: sistem daha önce sadece **sinyal üreten** sembolleri piyasa
sayfalarında gösteriyordu. Emtia'daki 4 sembolün (ya da kriptodaki 15
sembolün) çoğu o gün net bir AL/SAT eşiğini geçmediyse, sayfa "boş"
görünüyordu — bu bir veri hatası değil, sistemin varsayılan davranışıydı.

**Çözüm — yeni "Tüm Sembol Durumu" sayfası:** Artık taranan **HER**
sembolün (sinyal üretsin üretmesin) rejimi, ADX/RSI değeri ve "neden
sinyal yok" açıklaması ayrı bir sayfada gösteriliyor. Ayrıca yeni bir
**"Piyasa Özeti"** sayfası, her piyasada kaç sembol tarandığını ve
kaçının sinyal ürettiğini (`emtia: 4 tarandı, 0 sinyal üretti` gibi)
net olarak gösteriyor.

### Site tasarımı: gerçek çok sayfalı yapı

Streamlit artık tek sayfa sekmeli yapıdan, **her biri kendi URL'i olan,
sol menüden gezinilen 10 ayrı sayfaya** dönüştürüldü — tarayıcıdan
gerçek bir site gibi kullanılıyor:

```
app.py (Ana Sayfa)          → tarama başlatma + genel bakış + KPI kartları
pages/1_Grafik_Inceleme.py  → interaktif mum grafiği
pages/2_Piyasalar.py        → piyasa bazlı tablolar
pages/3_Tum_Semboller.py    → YENİ: taranan her sembolün durumu
pages/4_Temel_Risk_Gelismis.py
pages/5_Grid_DCA.py         + pages/5b_Grid_DCA_Performans.py → YENİ
pages/6_Haberler.py
pages/7_Takvim.py
pages/8_Performans.py
pages/9_Hatalar.py
```

Ortak kod (`dashboard_common.py`) tüm sayfalarda paylaşılıyor — CSS,
rapor önbellekleme (`st.cache_data`), en son raporu otomatik bulma.

### Grid & DCA emir takibi ve ayrı kazanç oranı hesaplama

`analysis/grid_dca_journal.py` (yeni, SQLite tabanlı): her grid
seviyesi/DCA dilimi bir "emir" olarak kaydediliyor, sonraki taramalarda
gerçek fiyat verisiyle karşılaştırılıp:

- **Grid**: fiyat "al" seviyesine değdi mi → "al gerçekleşti"; sonra
  "sat" seviyesine ulaştı mı → "sat gerçekleşti, kazanç X%" (60 gün
  içinde hiç tetiklenmezse "süresi doldu")
- **DCA**: fiyat tetik seviyesine değdi mi → "gerçekleşti"; performans,
  gerçekleşen dilimlerin ortalama maliyeti ile güncel fiyat
  karşılaştırılarak (gerçekleşmemiş kâr/zarar) hesaplanıyor

Kazanma oranları **grid ve DCA için ayrı ayrı** hesaplanıp yeni "Grid ve
DCA Performansı" sayfasında gösteriliyor.

**ÖNEMLİ:** Bu gerçek bir emir sistemi DEĞİLDİR, hiçbir borsaya
bağlanmaz — "eğer bu seviyeler önerildiğinde gerçekten işlem yapılsaydı
ne olurdu" sorusuna geçmişe dönük fiyat verisiyle cevap arayan bir
SİMÜLASYON/TAKİP sistemidir.

### Bu turda bulunan iki gerçek hata daha

1. **Grid emir süre-dolumu hatası:** Süre kontrolü fiyat kontrolünden
   ÖNCE çalışıyordu — uzun süredir güncellenmemiş bir emir, fiyata hiç
   bakılmadan yanlışlıkla "süresi doldu" işaretleniyordu. Sıralama
   düzeltildi (önce her zaman fiyat kontrolü yapılıyor).
2. **Excel'de iki tabloyu aynı sayfaya alt alta yazma hatası:** "Tüm
   Sembol Durumu" sayfasına ana tablo + özet tablo alt alta yazılıyordu.
   Excel'de görsel olarak sorunsuz görünüyordu ama `pd.read_excel` ile
   programatik okunduğunda (Streamlit panelinde) iki tablo birbirine
   karışıp veri bozuluyordu. Özet artık ayrı bir sayfada ("Piyasa Özeti").

Her iki hata da, bu turda eklenen testler sayesinde (körü körüne değil)
gerçek veriyle çalıştırılarak yakalandı.

## 🆕 v9 — Genişletilmiş Kapsam (Emtia, Döviz) ve Kritik Veri Hatası Düzeltmesi

### Altın hatasının kök sebebi bulundu ve düzeltildi

`data_pipeline/fetcher.py`'de gerçek bir hata vardı: forex-tarzı sembollerde
(altın gibi) Yahoo Finance genelde Hacim (Volume) verisi vermez — tüm
satırlarda `NaN` olabilir. Eski kod, veriyi temizlerken **5 sütunu (OHLC +
Volume) birden** kontrol ediyordu; Volume sürekli boşsa bu **TÜM satırları
sessizce siliyordu** (hata fırlatmadan). Bu, "bazen çalışıyor bazen
çalışmıyor" davranışının kök sebebiydi. Artık sadece asıl fiyat
sütunlarında (Open/High/Low/Close) eksik veri varsa satır atılıyor; eksik
Hacim 0 ile dolduruluyor. Aynı hata `data_pipeline/stooq_fetcher.py`'de de
vardı, o da düzeltildi. `fetcher.py`'nin daha önce **hiç testi yoktu** —
şimdi bu spesifik senaryoyu (`test_fetch_one_all_nan_volume_does_not_wipe_all_rows`)
kapsayan 11 test eklendi.

### Ek denetimde bulunan başka bir hata

`excel_report.py`'de "bilinmiyor" değerleri için `"N/A"` metni
kullanılıyordu — ama pandas, Excel dosyasını geri okurken `"N/A"` metnini
otomatik olarak **eksik veri (NaN)** sayıyor. Bu, rapor tekrar okunduğunda
(örn. Streamlit panelinde) verinin sessizce kaybolmasına yol açıyordu.
`"Bilinmiyor"` ile değiştirildi. Bu tür round-trip hatalarını yakalamak
için `data_pipeline/cache.py` ve `reporting/excel_report.py`'ye de
(önceden hiç testi olmayan iki modül) test eklendi.

### Genişletilmiş piyasa kapsamı

Önceki tek satırlık "Altın" piyasası, **"Emtia"** olarak genişletildi:

| Sembol | Ne |
|---|---|
| `XAUUSD=X` | Altın (spot) |
| `XAGUSD=X` | Gümüş (spot) |
| `CL=F` | Ham petrol (WTI vadeli) |
| `NG=F` | Doğalgaz (Henry Hub vadeli) |

Tamamen yeni bir **"Döviz Kurları"** piyasası eklendi (Türk kullanıcı için
özellikle USD/TRY dahil):

| Sembol | Ne |
|---|---|
| `USDTRY=X` | Dolar/Türk Lirası |
| `EURTRY=X` | Euro/Türk Lirası |
| `EURUSD=X` | Euro/Dolar |
| `GBPUSD=X` | Sterlin/Dolar |
| `USDJPY=X` | Dolar/Yen |

Kripto varsayılan kapsamı da **100 → 200**'e çıkarıldı
(`fetch_universe_lists.py --crypto-top-n 200`, varsayılan artık bu).

```bash
python main_scan.py --markets us bist crypto emtia forex
```

**Eski `--markets gold` artık çalışmıyor**, yerine `emtia` kullan. Kendi
`.bat`/otomasyon komutlarında bu ismi güncellemen gerekebilir.

### Telegram bildirimine panel linki

Artık Telegram mesajları, ayarlarsan (`STREAMLIT_APP_URL` ortam
değişkeni), tıklanabilir bir **"📱 Paneli aç"** linki içeriyor. Bunun
çalışması için paneli **Streamlit Community Cloud**'a (ücretsiz) deploy
etmen gerekiyor:

1. [share.streamlit.io](https://share.streamlit.io) adresine git, GitHub
   hesabınla giriş yap
2. **"New app"** → deponu ve `app.py` dosyasını seç → **"Deploy"**
3. Birkaç dakika sonra `https://kullanici-adi-depo-adi.streamlit.app`
   gibi kalıcı bir link alırsın
4. Bu linki GitHub deponda **Settings → Secrets and variables → Actions**
   altına `STREAMLIT_APP_URL` adıyla ekle

Streamlit Cloud, GitHub'a her push'ta (GitHub Actions'ın otomatik
taramadan sonra rapor/veritabanını depoya kaydetmesi dahil) **otomatik
olarak yeniden dağıtım yapar** — yani panel açıldığında her zaman en
güncel taramanın sonucunu gösterir (`app.py` artık açılışta
`reports/` klasöründeki en son raporu otomatik buluyor).

## 🆕 v8 — Walk-Forward Optimizasyon ve Detaylı Backtest

[Backtrader](https://github.com/mementum/backtrader) (GPL-3.0 lisanslı,
kod kopyalanmadı — aynı OctoBot gerekçesiyle) incelenirken ortaya çıkan
bir istek üzerine, README'de uzun süredir "yapılmadı" diye not düşülen
gerçek bir boşluk kapatıldı.

### Detaylandırılmış backtest motoru

`analysis/backtest.py` artık şunları da hesaplıyor:
- **Sortino oranı** (Sharpe'tan farkı: sadece aşağı yönlü oynaklığı
  cezalandırır, yukarı yönlü oynaklığı "risk" saymaz — daha adil)
- **Profit factor** (toplam kazanç / toplam kayıp)
- **Ortalama kazanç/kayıp yüzdesi**, ardışık en uzun kazanç/kayıp serisi
- **Maruz kalma süresi** (%) — sermayenin ne kadar süre piyasada olduğu
- **Buy & Hold karşılaştırması** — stratejinin sadece "al ve tut"tan
  gerçekten daha iyi olup olmadığı

### Walk-forward parametre optimizasyonu

`analysis/walk_forward.py` + `run_walk_forward.py`: bir sembol için
geçmiş veriyi kayan pencerelere böler, her pencerede parametreleri
SADECE eğitim bölümünde optimize edip SADECE test (görülmemiş) bölümünde
değerlendirir. Bu, "tüm geçmişte en iyi parametreleri bul" gibi klasik
bir overfitting tuzağına düşmeden, gerçekten genelleyen parametreler
bulmaya çalışır.

```bash
python run_walk_forward.py --symbol AAPL --period 3y
python run_walk_forward.py --symbol THYAO.IS --period 5y --train-days 300 --test-days 90
```

**Sadece tek sembol için çalışır** (tüm evrende çok yavaş olurdu) ve
**sonuçları otomatik uygulamaz** — bulunan "önerilen parametreleri"
`analysis/strategy.py`'ye elle girmen gerekiyor, bilinçli bir karar
olsun diye.

**Dürüstlük notu — bu gerçekten önemli:** Walk-forward, overfitting
riskini azaltır ama SIFIRLAMAZ. Sistem eğitim/test performansı arasında
büyük fark görürse "overfitting uyarısı" verir — bunu ciddiye al. Hiçbir
optimizasyon yöntemi gelecekteki performansı garanti etmez.

## 🆕 v7 — Görsel Panel: Grafikler, KPI Kartları, Sekmeli Detaylı Tasarım

Streamlit arayüzü, ham tablolardan gerçek bir görsel panele dönüştürüldü:

- `reporting/dashboard_charts.py` — Plotly ile üretilen, Streamlit'ten
  BAĞIMSIZ, pytest ile test edilen saf grafik fonksiyonları (16 test).
  Bu ayrım bilinçli: grafik mantığı tarayıcı açmadan doğrulanabiliyor.
- Mum grafiği için veri kaynağı: `data_pipeline/cache.py`'nin zaten
  diskte tuttuğu (parquet) fiyat verisi — ekstra bir indirme gerekmiyor,
  bir önceki taramanın verisi tekrar kullanılıyor.
- 9 sekme: Genel Bakış, Grafik İnceleme, Piyasalar, Temel & Risk &
  Gelişmiş, Grid & DCA, Haberler, Ekonomik Takvim, Geçmiş Performans,
  Hata Raporu.

**Doğrulama notu:** Streamlit'in kendisi interaktif olduğu için otomatik
testler tarayıcı etkileşimini simüle edemiyor — bunun yerine app.py'nin
tarama-sonrası TÜM veri işleme mantığı (Excel okuma, liste ayrıştırma,
cache erişimi, grafik üretimi), gerçek bir rapor üzerinde Streamlit'siz
ayrıca çalıştırılıp doğrulandı (40 sembol, tüm sekmeler, sıfır hata).

## 🆕 v6 — Grid ve DCA Strateji Planları

Bu, [OctoBot](https://github.com/Drakkar-Software/OctoBot) (Fransız açık
kaynaklı kripto trading botu) incelenirken ortaya çıkan bir istek üzerine
eklendi. **OctoBot'un kodu kopyalanmadı** (GPL-3.0 lisanslı olduğu için
kopyalamak bizim projeyi de GPL yapardı) — Grid ve DCA zaten genel,
herkese açık trading kavramları olduğu için kendi mantığımızla,
sıfırdan yazıldı.

**En önemli fark:** OctoBot gerçek borsa hesabına bağlanıp otomatik emir
gönderiyor. Bu sistem HİÇBİR ZAMAN gerçek emir göndermez — sadece bir
plan/öneri üretir, sen ister elle uygularsın, ister borsanın kendi
Grid Bot özelliğine bu seviyeleri girersin.

### Grid planı

Sadece **yatay (range) rejimindeki** semboller için anlamlıdır (trend
halindeki sembollerde fiyat tek yöne kaçabileceği için grid stratejisi
önerilmez). Son 60 günlük fiyat aralığı N eşit dilime bölünür, her dilim
için bir AL fiyatı + bir SAT fiyatı (bir dilim üstü) hesaplanır.
"Grid Planı" sayfasında.

### DCA (kademeli alım) planı

AL sinyali üreten semboller için, tek seferde büyük pozisyon açmak
yerine bütçeyi 4 dilime bölüp fiyat düştükçe kademeli alım önerir
(varsayılan: her dilim %5 daha düşük fiyatta tetiklenir). "DCA Planı"
sayfasında.

**Dürüstlük notu:** Fiyat öngörülen seviyelere hiç gelmeyebilir — bu
DCA'nın doğasında var, "bazı dilimler hiç alınmadı" normal bir sonuçtur,
hata değildir.



### Altın veri sorunu neden yaşandı, nasıl çözüldü

`GC=F` (COMEX altın vadeli işlemi) bir vadeli işlem sözleşmesiydi — bu tür
sözleşmeler rollover (sözleşme devri) dönemlerinde ve Yahoo Finance'in
emtia veri hattında hisse senetlerine göre daha sık boşluk/eksiklik
yaşıyor. Sembol artık `XAUUSD=X` (spot altın/dolar, forex-tarzı sürekli
kota) — çok daha kararlı bir veri akışı sağlıyor.

### İkinci, bağımsız veri kaynağı: Stooq.com

`data_pipeline/stooq_fetcher.py`, tamamen ücretsiz ve API key
gerektirmeyen Stooq.com'u iki şekilde kullanır:

1. **Yedek kaynak**: yfinance bir sembol için tüm denemelerinde
   başarısız olursa (rate limit, geçici sunucu sorunu), sistem otomatik
   olarak Stooq'u dener. ABD hisseleri, kripto paralar ve altın için
   çalışır; BIST için Stooq güvenilir kapsam sağlamadığından uygulanmaz.
2. **Çapraz doğrulama**: Sinyal üreten her sembol için hem yfinance hem
   Stooq'tan son kapanış fiyatı karşılaştırılır. İki kaynak %3'ten fazla
   farklıysa, Excel raporunda "Veri Şüpheli mi" sütunu işaretlenir —
   kör güven yerine iki bağımsız kaynağın birbirini denetlemesi.

Atlamak istersen: `python main_scan.py --skip-cross-validation`

### Mum formasyonu (candlestick pattern) tanıma

`analysis/candlestick_patterns.py`, klasik formasyonları (doji, çekiç,
kayan yıldız, boğa/ayı yutan formasyonu) OHLC verisinden tespit eder,
"Gelişmiş Göstergeler" sayfasına ek sütun olarak eklenir.

**Dürüstlük notu:** Mum formasyonları tek başına güvenilir bir sinyal
değildir — akademik literatür karışık sonuçlar veriyor. Trend/rejim ve
diğer göstergelerle BİRLİKTE bir teyit katmanı olarak kullanın.

### Pozisyon büyüklüğü önerisi

`analysis/position_sizing.py`, bir sinyali "kaç hisse/kripto/lot al"a
çevirir — ATR tabanlı stop mesafesine göre, hesabının sabit bir yüzdesini
(varsayılan %1) riske atacak şekilde boyutlandırma yapar. Bu, "sinyal
listesi" ile "gerçek bir trade sistemi" arasındaki en önemli farklardan
biridir.

```bash
python main_scan.py --account-size 50000 --risk-pct 1.5
```

Streamlit arayüzünde de "Pozisyon Büyüklüğü" bölümünden ayarlanabilir.

**Dürüstlük notu:** Bu bir öneri motorudur, kesin talimat değil. Aynı
anda birden fazla sinyal takip ediyorsan, pozisyonlar arası korelasyona
(örn. aynı sektörden 5 hisse aynı anda AL sinyali verirse bunlar
bağımsız riskler değildir) dikkat etmen gerekir — sistem şu an
portföy-seviyesi korelasyon kontrolü yapmıyor.

### Ekonomik takvim

`analysis/economic_calendar.py`, önümüzdeki 14 gün içinde FOMC (Fed
faiz kararı), NFP (istihdam) veya CPI (enflasyon) açıklaması var mı
kontrol eder — "Ekonomik Takvim" sayfasında görünür. Az önce sorduğun
"ABD'deki açıklamalar önemli oluyor" konusuna doğrudan cevap.

**Dürüstlük notu:** FOMC tarihleri Fed'in resmi 2026 takviminden alındı
ama yılda bir elle güncellenmesi gerekir. NFP/CPI tarihleri **yaklaşık**
kurallara dayanır (kesin gün için bls.gov'un resmi takvimine bakılmalı).



### Neden "top 100" mantığı?

BIST 100 gibi, artık ABD ve kripto piyasaları da "en önemli/en büyük 100"
mantığıyla taranıyor — dağınık, kalitesiz sembollerle vakit kaybetmek
yerine, gerçekten önemli olan hisselere odaklanıyoruz:

| Piyasa | Kaynak | Kapsam |
|---|---|---|
| ABD | S&P 100 (Wikipedia, canlı çekim) | En büyük/en likit 100 ABD şirketi |
| BIST | Elle derlenmiş, investing.com'un 30.08.2026 tarihli BIST 100 sayfasından | 80 doğrulanmış sembol (bkz. aşağıdaki dürüstlük notu) |
| Kripto | CoinGecko (canlı çekim) | Piyasa değerine göre ilk 100 |
| Altın | Statik | COMEX Altın Vadeli İşlemi (`GC=F`) |

Daha geniş ABD kapsamı istersen: `python fetch_universe_lists.py --markets us --us-extended`
(S&P 500 + Nasdaq-100 ekler, ama tarama süresi uzar).

### BIST 100 listesi hakkında dürüstlük notu

80 sembollük liste, investing.com'un canlı BIST 100 bileşen sayfasından
şirket adı okunup ticker koduna **elle eşlenerek** oluşturuldu (BIST için
güvenilir, ücretsiz, makine tarafından okunabilir bir kaynak yok). Bazı
küçük/yeni halka arz olmuş şirketlerin ticker kodları belirsizliği
nedeniyle listeye dahil edilmedi. Yanlış bir kod varsa, sistem bunu
otomatik olarak "Hata Raporu" sayfasına düşürür, çökmez — ama %100
doğruluk garantisi veremem. Endeks çeyreklik revize edildiği için
(Ocak/Nisan/Temmuz/Ekim) listeyi periyodik olarak elle güncellemen
gerekir. Güncel resmi liste: tr.investing.com/indices/ise-100-components

### Altın analizi

Diğer piyasalarla aynı teknik analiz motorundan geçer (rejim tespiti,
Fibonacci, destek/direnç, hacim profili). Farkı: temel analiz (P/E vb.)
uygulanmaz (kripto gibi, çünkü kavram yok) ve göreceli güç karşılaştırması
yapılmaz (doğal bir "altın piyasası endeksi" yok).

### Haber analizi

Her taranan sembol için son haber başlıkları + basit bir "haber tonu"
skoru, ayrıca ABD piyasasını genel etkileyen büyük göstergelerin (S&P 500,
Dow, Nasdaq, 10 yıllık tahvil getirisi, dolar endeksi) haberleri —
Fed açıklamaları, enflasyon verileri gibi "piyasayı geneli sarsan" haberler
genelde bu göstergelerin haber akışında da görünür.

**ÖNEMLİ DÜRÜSTLÜK NOTU:** Bu, yapay zeka destekli gerçek bir haber
analizi DEĞİLDİR. Basit bir anahtar kelime sayımı yapıyor ("surge",
"plunge", "beat", "miss" gibi kelimelerin metinde geçme sıklığına
bakıyor). Bunun sebebi ücretsiz kalmak — gerçek NLP/LLM tabanlı analiz
ücretli bir API gerektirir. Haber tonu skorunu **kaba bir gösterge**
olarak kullan, kesin bir yargı olarak değil. Excel'deki "Haberler"
sayfasından başlıkları okuyup kendi değerlendirmeni yapman en sağlıklısı.

Hızlı taramak istersen: `python main_scan.py --skip-news` (sembol başına
ayrı istek gerektirdiği için yavaşlatabilir, tıpkı `--skip-fundamentals` gibi).



### Gelişmiş teknik göstergeler

`analysis/advanced_indicators.py` her sembol için ek olarak hesaplar:
- **Fibonacci seviyeleri**: Son önemli yükseliş/düşüşe göre %23.6, %38.2,
  %50, %61.8, %78.6 geri çekilme seviyeleri, ve fiyata en yakın seviye
- **Destek/direnç**: Yerel dip/zirve noktalarından (pivot) türetilen,
  birbirine yakın olanları kümeleyen seviye listesi
- **Hacim profili**: Fiyat aralıklarına göre işlem hacmi dağılımı; POC
  (en çok işlem gören fiyat) ve "value area" (hacmin %70'inin gerçekleştiği
  aralık)

Excel raporunda **"Gelişmiş Göstergeler"** sayfasında görünür.

### Sinyal günlüğü / performans takibi

`analysis/journal.py`, her taramada üretilen sinyalleri `data/signal_journal.db`
adlı bir SQLite veritabanına kaydeder ve bir sonraki taramada:
- Daha önce açılan sinyallerin hedefe mi ulaştığını, stop mu olduğunu,
  hâlâ açık mı olduğunu günceller
- 30 günden eski hâlâ açık sinyalleri "süresi doldu" olarak işaretler
- Kazanma oranı, ortalama getiri gibi özet istatistikler üretir

Excel raporunda **"Performans Geçmişi"** sayfasında görünür. Bu, sistemin
gerçekten işe yarayıp yaramadığını zamanla objektif olarak görmeni sağlar
— tek seferlik bir tarama değil, kendini denetleyen bir döngü.

Veritabanı dosyasını silersen geçmiş sıfırlanır; normalde silme, zamanla
biriken veri değerlidir.

### Sembol listelerinin otomatik güncellenmesi

Artık `fetch_universe_lists.py`'yi elle çalıştırman gerekmiyor. Her
taramadan önce `universe.auto_refresh_if_stale()` şunu kontrol eder:
`data/universe_us.csv` ve `data/universe_crypto.csv` dosyaları
`config.py > UNIVERSE_MAX_AGE_DAYS` (varsayılan 7 gün) değerinden eskiyse,
otomatik olarak yeniden çeker. İnternet yoksa veya çekim başarısız olursa
mevcut (eski) listeyle devam eder, sistemi durdurmaz.

Kapatmak istersen: `python main_scan.py --no-auto-refresh`

### Telegram bildirimleri

Her tarama bitince, en iyi AL/SAT adaylarını Telegram'a mesaj olarak
gönderebilir. Kurulum (tek seferlik, ücretsiz):

1. Telegram'da **@BotFather** hesabını bul, `/newbot` yaz, talimatları
   takip et (bot adı sor, istediğini yaz). Sonunda sana uzun bir
   **TOKEN** verir (örn. `123456789:AAExxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx`) — kopyala.
2. Oluşturduğun botu Telegram'da ara, konuşmayı başlat, herhangi bir
   mesaj gönder (örn. "merhaba").
3. Tarayıcında şu adrese git (TOKEN kısmını kendi tokenınla değiştir):
   `https://api.telegram.org/bot TOKEN /getUpdates` (boşluksuz yaz)
4. Çıkan metinde `"chat":{"id":123456789,...}` gibi bir kısım ara,
   oradaki sayı senin **CHAT_ID**'n.
5. Bilgisayarında ortam değişkeni olarak ayarla:

   **Windows (PowerShell'de, kalıcı olması için):**
   ```
   setx TELEGRAM_BOT_TOKEN "buraya_token"
   setx TELEGRAM_CHAT_ID "buraya_chat_id"
   ```
   Ayarladıktan sonra **terminali kapatıp yeniden aç** (yeni pencere
   değişkeni görmeli).

   **Mac/Linux:**
   ```
   echo 'export TELEGRAM_BOT_TOKEN="buraya_token"' >> ~/.zshrc
   echo 'export TELEGRAM_CHAT_ID="buraya_chat_id"' >> ~/.zshrc
   source ~/.zshrc
   ```

Bundan sonra her tarama bitince Telegram'a otomatik mesaj gelir. Hiç
ayarlamazsan sistem bunu fark eder, sessizce atlar — hata vermez.

---

## ☁️ Bulutta Ücretsiz 7/24 Çalıştırma (bilgisayarın kapalıyken de)

Bu, **GitHub Actions** kullanır — GitHub'ın herkese açık projeler için
tamamen ücretsiz sunduğu bir otomasyon hizmeti. Kredi kartı gerekmez.
Proje zaten `.github/workflows/scan.yml` dosyasıyla hazır; sadece
GitHub'a yüklemen ve birkaç ayar yapman yeterli.

### 1. GitHub hesabı aç

[github.com](https://github.com) → "Sign up" → ücretsiz hesap oluştur.

### 2. Yeni bir "repository" (depo) oluştur

- Sağ üstteki **+** işaretine tıkla → **"New repository"**
- İsim ver (örn. `hisse-tarama-sistemi`)
- **"Private"** seçeneğini işaretle (sinyal geçmişin ve ayarların
  herkese açık olmasın istersen — ücretsiz hesapta private repo da
  Actions'ı ücretsiz kullanabilir)
- "Create repository" butonuna bas

### 3. Proje dosyalarını yükle

Oluşan boş depo sayfasında **"uploading an existing file"** linkine
tıkla. Bilgisayarındaki `trading_system` klasörünün **içindeki tüm
dosya ve klasörleri** (klasörün kendisini değil, içindekileri) sürükleyip
bırak. Yüklenmesi biraz sürebilir (yüzlerce dosya var). Sonunda
"Commit changes" butonuna bas.

**Not:** `venv` klasörünü YÜKLEME (gereksiz, çok büyük). `cache`,
`logs`, `__pycache__`, `.pytest_cache` klasörlerini de yüklemene
gerek yok.

### 4. Telegram bilgilerini "Secret" olarak ekle (bildirim istiyorsan)

- Depo sayfasında **Settings** (Ayarlar) sekmesine git
- Sol menüden **Secrets and variables → Actions**
- **"New repository secret"** butonuna bas
- İsim: `TELEGRAM_BOT_TOKEN`, Değer: kendi token'ın → "Add secret"
- Aynısını `TELEGRAM_CHAT_ID` için de tekrarla

### 5. Yazma iznini aç (rapor otomatik kaydedilsin diye)

- **Settings → Actions → General** sayfasına git
- En altta **"Workflow permissions"** bölümünü bul
- **"Read and write permissions"** seçeneğini işaretle → Save

### 6. Çalıştığını doğrula

- Depo sayfasında **Actions** sekmesine git
- Soldan **"Otomatik Hisse/Kripto Taraması"** iş akışına tıkla
- Sağda **"Run workflow"** butonuna basıp elle bir kere tetikle
- Birkaç dakika sonra yeşil tik ✅ görürsen çalışıyor demektir
- Tıklayıp içine girersen adım adım logları görebilirsin (tıpkı kendi
  terminalinde gördüğün gibi)

Bundan sonra **hafta içi günde 4 kez** (10:30, 13:00, 16:00, 19:00
Türkiye saati) otomatik çalışır, sonuçları hem depoya kaydeder hem
(ayarladıysan) Telegram'a gönderir — bilgisayarın kapalı olsa bile.

**Saatleri değiştirmek istersen:** `.github/workflows/scan.yml`
dosyasındaki `cron` satırlarını düzenle (UTC saatiyle yazılır, Türkiye
saatinden 3 saat geridir).

**Ücretsiz sınırı:** Private repo'larda ayda ~2000 dakika (bu tarama
sıklığıyla fazlasıyla yeterli); public repo'larda sınırsız.

## Sonraki adımlar (istersen genişletebiliriz)

- ~~Fundamental veri entegrasyonu~~ ✅ tamamlandı
- ~~Gelişmiş teknik göstergeler (Fibonacci, destek/direnç, hacim profili)~~ ✅ tamamlandı
- ~~Sinyal günlüğü / performans takibi~~ ✅ tamamlandı
- ~~Telegram bildirimleri~~ ✅ tamamlandı
- ~~Bulutta ücretsiz otomatik çalıştırma~~ ✅ tamamlandı
- ~~Genişletilmiş sembol kapsamı (S&P 100, BIST 100, kripto top 100, altın)~~ ✅ tamamlandı
- ~~Haber analizi (sembol bazlı + makro)~~ ✅ tamamlandı (basit anahtar kelime tabanlı, gerçek NLP değil)
- ~~İkinci/bağımsız veri kaynağı (Stooq) + çapraz doğrulama~~ ✅ tamamlandı
- ~~Mum formasyonu tanıma~~ ✅ tamamlandı
- ~~Pozisyon büyüklüğü önerisi~~ ✅ tamamlandı
- ~~Ekonomik takvim (FOMC/NFP/CPI)~~ ✅ tamamlandı
- ~~Grid ve DCA strateji planları~~ ✅ tamamlandı
- ~~Görsel panel: grafikler, KPI kartları, sekmeli detaylı tasarım~~ ✅ tamamlandı
- ~~Genişletilmiş piyasa kapsamı (Emtia, Döviz) + kritik veri hatası düzeltmesi~~ ✅ tamamlandı
- ~~Telegram bildirimine panel linki~~ ✅ tamamlandı (Streamlit Cloud deploy gerektirir)
- ~~Çok sayfalı site tasarımı~~ ✅ tamamlandı
- ~~Tüm sembol durumu şeffaflığı (sinyal üretmeyenler dahil)~~ ✅ tamamlandı
- ~~Grid & DCA emir takibi + ayrı kazanma oranı hesaplama~~ ✅ tamamlandı
- ~~Döviz kaldırma + emtia veri hatasının gerçek kök sebebini bulma~~ ✅ tamamlandı
- ~~Walk-forward parametre optimizasyonu scripti~~ ✅ tamamlandı (`run_walk_forward.py`)
- ~~Paper trading (kağıt üzerinde) takip modülü~~ ✅ tamamlandı
- E-posta bildirimi (şu an sadece Telegram var)
- Gerçek NLP/LLM tabanlı haber duygu analizi (ücretli API gerektirir)
- ~~Portföy-seviyesi korelasyon kontrolü~~ ✅ tamamlandı
- Ichimoku Cloud, Stochastic osilatör gibi ek teknik göstergeler


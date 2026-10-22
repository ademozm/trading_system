"""
Kendi bilgisayarında (bu sandbox'ta DEĞİL, çünkü buranın interneti kısıtlı)
data/universe_*.csv dosyalarını GERÇEK ve GÜNCEL listelerle doldurmak için
çalıştır:

    python fetch_universe_lists.py --markets us crypto
    python fetch_universe_lists.py --markets us bist crypto

ABD listesi artık "en önemli 100 hisse" olarak S&P 100 (^OEX) endeksinden
çekiliyor — bu, ABD'nin en büyük/en likit 100 şirketini garanti eder
(BIST 100'e paralel bir mantık). Daha geniş kapsam istersen --us-extended
ile S&P 500 + Nasdaq-100'ü de ekleyebilirsin.

BIST için otomatik canlı kaynak yok (güvenilir ücretsiz API yok);
data/universe_bist.csv elle derlenmiş 80 sembollük bir listedir
(investing.com'un 30.08.2026 tarihli BIST 100 bileşen sayfasından,
şirket adlarından ticker koduna manuel eşleştirilerek oluşturuldu).
Çeyreklik endeks revizyonlarında (Ocak/Nisan/Temmuz/Ekim) elle
güncellenmesi gerekir. Güncel resmi liste: borsaistanbul.com veya
tr.investing.com/indices/ise-100-components

Kripto listesi CoinGecko'nun ücretsiz public API'siyle piyasa değerine göre
ilk N coin çekilir (varsayılan 100, API key gerekmez).

Emtia ve d00f6viz kurlar0131 statik listelerdir, g00fcncelleme gerektirmez (COMEX vadeli
işlem sembolü değişmez).
"""
import argparse
import time

import pandas as pd
import requests

import config
import universe


def update_us(extended: bool = False) -> pd.DataFrame:
    print("ABD listesi çekiliyor (S&P 100 - en önemli 100 şirket)...")
    tables = pd.read_html("https://en.wikipedia.org/wiki/S%26P_100")
    sp100_df = None
    for t in tables:
        cols_lower = [str(c).lower() for c in t.columns]
        if "symbol" in cols_lower:
            col = t.columns[cols_lower.index("symbol")]
            name_col = t.columns[cols_lower.index("name")] if "name" in cols_lower else col
            sp100_df = pd.DataFrame({
                "symbol": t[col].astype(str).str.replace(".", "-", regex=False),
                "market": "us",
                "name": t[name_col],
            })
            break
    if sp100_df is None:
        raise ValueError("S&P 100 tablosu bulunamadı, Wikipedia sayfa yapısı değişmiş olabilir.")

    combined = sp100_df.drop_duplicates(subset="symbol").reset_index(drop=True)
    print(f"  {len(combined)} ABD sembolü bulundu (S&P 100).")

    if extended:
        print("  Genişletilmiş mod: S&P 500 + Nasdaq-100 de ekleniyor...")
        try:
            sp500 = pd.read_html("https://en.wikipedia.org/wiki/List_of_S%26P_500_companies")[0]
            sp500_df = pd.DataFrame({
                "symbol": sp500["Symbol"].str.replace(".", "-", regex=False),
                "market": "us", "name": sp500["Security"],
            })
            combined = pd.concat([combined, sp500_df], ignore_index=True).drop_duplicates(subset="symbol")
            print(f"  Genişletilmiş toplam: {len(combined)} sembol.")
        except Exception as e:
            print(f"  [uyarı] S&P 500 genişletmesi başarısız, sadece S&P 100 kullanılıyor: {e}")

    return combined.reset_index(drop=True)


def update_crypto(top_n: int = 100) -> pd.DataFrame:
    print(f"Kripto listesi çekiliyor (CoinGecko, piyasa değerine göre ilk {top_n})...")
    url = "https://api.coingecko.com/api/v3/coins/markets"
    params = {"vs_currency": "usd", "order": "market_cap_desc", "per_page": top_n, "page": 1}
    resp = requests.get(url, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json()
    df = pd.DataFrame({
        "symbol": [f"{c['symbol'].upper()}-USD" for c in data],
        "market": "crypto",
        "name": [c["name"] for c in data],
    })
    df = df.drop_duplicates(subset="symbol").reset_index(drop=True)
    print(f"  {len(df)} kripto para bulundu.")
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tam hisse/kripto listelerini güncelle")
    parser.add_argument("--markets", nargs="+", default=["us", "crypto"],
                         choices=["us", "bist", "crypto", "emtia"])
    parser.add_argument("--crypto-top-n", type=int, default=200,
                         help="Piyasa değerine göre ilk N kripto para (varsayılan 200, önceden 100'dü)")
    parser.add_argument("--us-extended", action="store_true",
                         help="Sadece top 100 değil, S&P 500 + Nasdaq-100'ü de dahil et (daha yavaş tarama)")
    args = parser.parse_args()

    if "us" in args.markets:
        df = update_us(extended=args.us_extended)
        df.to_csv(config.UNIVERSE_FILES["us"], index=False)
        universe._mark_refreshed("us")
        print(f"  Kaydedildi: {config.UNIVERSE_FILES['us']}")

    if "crypto" in args.markets:
        df = update_crypto(args.crypto_top_n)
        df.to_csv(config.UNIVERSE_FILES["crypto"], index=False)
        universe._mark_refreshed("crypto")
        print(f"  Kaydedildi: {config.UNIVERSE_FILES['crypto']}")

    if "bist" in args.markets:
        print("BIST için otomatik canlı kaynak yok. Mevcut "
              f"{config.UNIVERSE_FILES['bist']} dosyasını elle güncellemen gerekiyor "
              "(bkz. dosyanın başındaki not, veya tr.investing.com/indices/ise-100-components).")

    if "emtia" in args.markets:
        print("Emtia listesi statiktir, güncelleme gerekmez (data/universe_emtia.csv).")

    print("\nBitti. main_scan.py bir sonraki çalıştırmada güncel listeleri kullanacak.")

"""
Tek bir sembol için walk-forward parametre optimizasyonu çalıştırır.

NEDEN TEK SEMBOL: Walk-forward, pencere sayısı × parametre kombinasyonu
kadar backtest çalıştırır — tüm evrende (100+ sembol) bunu yapmak çok
yavaş olurdu. Bunun yerine, ilgilendiğin belirli bir sembol için (örn.
en çok işlem yaptığın hisse) parametreleri optimize etmek daha mantıklı.

Kullanım:
    python run_walk_forward.py --symbol AAPL --period 3y
    python run_walk_forward.py --symbol THYAO.IS --period 5y --train-days 300 --test-days 90

Çıktı: reports/ klasörüne walk_forward_<sembol>_<tarih>.xlsx
"""
import argparse
import os

import pandas as pd

import config
from data_pipeline import fetcher
from analysis import walk_forward as wf


def run(symbol: str, period: str, train_days: int, test_days: int, step_days: int):
    print(f"[1/3] {symbol} için veri çekiliyor ({period})...")
    result = fetcher.fetch_universe([symbol], period=period, use_cache=True)
    if symbol not in result.data:
        print(f"HATA: {symbol} için veri çekilemedi: {result.failed.get(symbol, 'bilinmeyen hata')}")
        return
    df = result.data[symbol]
    print(f"       {len(df)} mum verisi alındı.")

    print(f"[2/3] Walk-forward optimizasyonu çalışıyor "
          f"(eğitim: {train_days} gün, test: {test_days} gün, adım: {step_days} gün)...")
    print("       Bu birkaç dakika sürebilir (pencere sayısı × parametre kombinasyonu kadar backtest çalıştırılıyor)")
    wf_result = wf.run_walk_forward(df, train_days=train_days, test_days=test_days, step_days=step_days)

    if wf_result["window_results"].empty:
        print("\nSONUÇ: Yetersiz veri veya hiçbir pencerede yeterli işlem sayısı bulunamadı.")
        print(wf_result["summary"])
        return

    print("\n=== ÖZET ===")
    for k, v in wf_result["summary"].items():
        print(f"  {k}: {v}")

    print("\n=== ÖNERİLEN PARAMETRELER (pencereler arası medyan) ===")
    for k, v in wf_result["recommended_params"].items():
        print(f"  {k}: {v}")

    if wf_result["overfitting_warning"]:
        print("\n⚠️  UYARI: Eğitim performansı test performansından çok daha iyi görünüyor —")
        print("    bu, overfitting (veriye ezberleme) belirtisi olabilir. Bulunan parametrelere")
        print("    körü körüne güvenmemeni, farklı dönemlerle de doğrulamanı öneririm.")

    print("\n[3/3] Rapor kaydediliyor...")
    timestamp = pd.Timestamp.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(config.REPORTS_DIR, f"walk_forward_{symbol.replace('=', '_')}_{timestamp}.xlsx")
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        wf_result["window_results"].to_excel(writer, sheet_name="Pencere Sonuçları", index=False)
        pd.DataFrame([wf_result["summary"]]).to_excel(writer, sheet_name="Özet", index=False)
        pd.DataFrame([wf_result["recommended_params"]]).to_excel(writer, sheet_name="Önerilen Parametreler", index=False)

    print(f"       Kaydedildi: {output_path}")
    print("\nBu parametreleri kullanmak için config.py > SCORE_WEIGHTS civarındaki")
    print("varsayılan strateji parametrelerini (analysis/strategy.py > RegimeAdaptiveStrategy)")
    print("elle güncelleyebilirsin. Sistem bunu otomatik uygulamaz — bilinçli bir karar olsun diye.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Tek sembol için walk-forward parametre optimizasyonu")
    parser.add_argument("--symbol", required=True, help="Örn: AAPL, THYAO.IS, BTC-USD")
    parser.add_argument("--period", default="3y", help="Örn: 2y, 3y, 5y (daha uzun = daha güvenilir ama yavaş)")
    parser.add_argument("--train-days", type=int, default=252, help="Eğitim penceresi (gün, varsayılan ~1 yıl)")
    parser.add_argument("--test-days", type=int, default=63, help="Test penceresi (gün, varsayılan ~3 ay)")
    parser.add_argument("--step-days", type=int, default=63, help="Pencere kaydırma adımı (gün)")
    args = parser.parse_args()

    run(args.symbol, args.period, args.train_days, args.test_days, args.step_days)

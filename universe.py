"""
Hisse evreni yönetimi.

Bu modül, taranacak sembollerin listesini data/universe_*.csv dosyalarından
okur. Buradaki listeler ÖRNEK/BAŞLANGIÇ listeleridir — tam S&P 500, tam
BIST veya tüm kripto evrenini içermez (bu ortamın internet erişimi
kısıtlı olduğu için canlı liste çekilemedi).

Listeleri genişletmek için:
- ABD: Wikipedia "List of S&P 500 companies" tablosunu CSV'ye aktarabilirsin.
- BIST: Borsa İstanbul resmi sitesinden sembol listesi indirebilirsin
  (sembollere ".IS" son eki eklemeyi unutma, örn. THYAO.IS).
- Kripto: CoinGecko/CoinMarketCap üzerinden piyasa değerine göre ilk N coin,
  sembollere "-USD" son eki ekleyerek (örn. BTC-USD).

CSV formatı sabit: symbol,market,name
"""
import os
import json
import logging
from datetime import datetime, timedelta

import pandas as pd

import config

logger = logging.getLogger("universe")


def load_universe(markets=None) -> pd.DataFrame:
    """
    markets: None ise tüm piyasalar. Aksi halde ör. ['us', 'bist'] gibi bir liste.
    Dönüş: symbol, market, name kolonlarına sahip birleşik DataFrame.
    """
    if markets is None:
        markets = list(config.UNIVERSE_FILES.keys())

    frames = []
    for m in markets:
        path = config.UNIVERSE_FILES.get(m)
        if path is None:
            raise ValueError(f"Bilinmeyen piyasa: {m}")
        df = pd.read_csv(path)
        frames.append(df)

    combined = pd.concat(frames, ignore_index=True)
    combined = combined.drop_duplicates(subset="symbol").reset_index(drop=True)
    return combined


def universe_size(markets=None) -> int:
    return len(load_universe(markets))


def _load_meta() -> dict:
    if not os.path.exists(config.UNIVERSE_META_PATH):
        return {}
    try:
        with open(config.UNIVERSE_META_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_meta(meta: dict):
    os.makedirs(os.path.dirname(config.UNIVERSE_META_PATH), exist_ok=True)
    with open(config.UNIVERSE_META_PATH, "w") as f:
        json.dump(meta, f, indent=2)


def _mark_refreshed(market: str):
    meta = _load_meta()
    meta[market] = datetime.now().isoformat()
    _save_meta(meta)


def _content_age_days(market: str) -> float:
    meta = _load_meta()
    last_updated = meta.get(market)
    if last_updated is None:
        return float("inf")
    try:
        last_dt = datetime.fromisoformat(last_updated)
    except Exception:
        return float("inf")
    return (datetime.now() - last_dt).total_seconds() / 86400


def auto_refresh_if_stale(markets: list, max_age_days: int = None) -> dict:
    """
    Her piyasa için CSV dosyasının yaşını kontrol eder; eskiyse
    fetch_universe_lists.py'deki güncelleme fonksiyonlarını çağırır.
    İnternet yoksa veya çekim başarısız olursa MEVCUT dosya korunur,
    tarama bu yüzden durmaz — sadece uyarı loglanır.

    Dönüş: {market: "güncellendi" | "güncel" | "güncellenemedi (hata)"}
    """
    max_age_days = max_age_days if max_age_days is not None else config.UNIVERSE_MAX_AGE_DAYS
    results = {}

    # Döngüsel import'u önlemek için burada import ediyoruz
    try:
        import fetch_universe_lists as ful
    except ImportError:
        for m in markets:
            results[m] = "güncellenemedi (fetch_universe_lists.py bulunamadı)"
        return results

    for m in markets:
        path = config.UNIVERSE_FILES.get(m)
        if path is None:
            continue
        age = _content_age_days(m)
        if age <= max_age_days:
            results[m] = f"güncel ({age:.1f} gün önce güncellenmiş)"
            continue

        age_label = "hiç güncellenmemiş" if age == float("inf") else f"{age:.1f} gün önce güncellenmiş"
        logger.info(f"{m} sembol listesi {age_label}, tazeleniyor...")
        try:
            if m == "us":
                df = ful.update_us()
                df.to_csv(path, index=False)
            elif m == "crypto":
                df = ful.update_crypto()
                df.to_csv(path, index=False)
            elif m == "bist":
                results[m] = "otomatik kaynak yok, elle güncellenmeli (bkz. README)"
                continue
            else:
                continue
            _mark_refreshed(m)
            results[m] = "güncellendi"
            logger.info(f"{m} sembol listesi güncellendi.")
        except Exception as e:
            results[m] = f"güncellenemedi (hata: {e})"
            logger.warning(f"{m} sembol listesi güncellenemedi, eski dosya kullanılacak: {e}")

    return results

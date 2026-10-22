"""
Grid ve DCA "emirlerini" (aslında öneri seviyelerini) SQLite'a kaydeden
ve fiyat hareketine göre sonuçlarını (gerçekleşti mi, kazandı mı) takip
eden modül.

ÖNEMLİ: Bu GERÇEK bir emir sistemi DEĞİLDİR — hiçbir borsaya bağlanmaz,
gerçek para hareket ettirmez. Sadece "eğer bu seviyeler önerildiğinde
gerçekten alım/satım yapılsaydı ne olurdu" sorusuna, sonraki taramalarda
fiyat verisiyle karşılaştırarak cevap arayan bir SİMÜLASYON/TAKİP
sistemidir.

Mantık:
- Grid: Her seviye "beklemede" olarak kaydedilir. Sonraki taramalarda
  fiyat o seviyeye (al_fiyati) değdiyse "alım gerçekleşti" sayılır.
  Sonra fiyat sat_fiyati'na değerse "satış gerçekleşti, kazanç X%"
  olarak kapatılır. 60 günden uzun süre hiç tetiklenmezse "süresi doldu"
  sayılır.
- DCA: Her dilim "beklemede" olarak kaydedilir. Fiyat tetik_fiyati'na
  değdiyse "gerçekleşti" sayılır (bir DCA dilimi, grid'in aksine tek
  yönlü bir alımdır — "satışı" yok, o yüzden kazanç/kayıp güncel fiyata
  göre "gerçekleşmemiş kâr/zarar" olarak hesaplanır).
"""
import logging
import os
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

import config

logger = logging.getLogger("grid_dca_journal")

DB_PATH = os.path.join(config.DATA_DIR, "grid_dca_journal.db")
MAX_PENDING_DAYS = 60  # bu kadar gün tetiklenmeyen emir "süresi doldu" sayılır


def _get_connection(db_path: str = None):
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS grid_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_time TEXT, symbol TEXT, market TEXT, seviye INTEGER,
            al_fiyati REAL, sat_fiyati REAL, adet REAL,
            durum TEXT DEFAULT 'beklemede',
            al_tarihi TEXT, sat_tarihi TEXT, kazanc_pct REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS dca_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_time TEXT, symbol TEXT, market TEXT, dilim INTEGER,
            tetik_fiyati REAL, tutar REAL, adet REAL,
            durum TEXT DEFAULT 'beklemede',
            gerceklesme_tarihi TEXT
        )
    """)
    return conn


def record_grid_plan(grid_plan_df: pd.DataFrame, universe_df: pd.DataFrame,
                      scan_time: str = None, db_path: str = None) -> int:
    """grid_plan_df: main_scan.py'nin ürettiği ham (Excel'e yazılmadan önceki)
    grid_rows listesinden gelen DataFrame — symbol/seviye/al_fiyati/sat_fiyati/adet kolonları."""
    if grid_plan_df is None or grid_plan_df.empty:
        return 0
    scan_time = scan_time or datetime.now().isoformat()
    market_by_symbol = universe_df.set_index("symbol")["market"].to_dict() if universe_df is not None else {}

    conn = _get_connection(db_path)
    added = 0
    for _, row in grid_plan_df.iterrows():
        conn.execute(
            "INSERT INTO grid_orders (scan_time, symbol, market, seviye, al_fiyati, sat_fiyati, adet) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scan_time, row["symbol"], market_by_symbol.get(row["symbol"], "?"),
             int(row["seviye"]), float(row["al_fiyati"]), float(row["sat_fiyati"]), float(row["adet"])),
        )
        added += 1
    conn.commit()
    conn.close()
    return added


def record_dca_plan(dca_plan_df: pd.DataFrame, universe_df: pd.DataFrame,
                     scan_time: str = None, db_path: str = None) -> int:
    if dca_plan_df is None or dca_plan_df.empty:
        return 0
    scan_time = scan_time or datetime.now().isoformat()
    market_by_symbol = universe_df.set_index("symbol")["market"].to_dict() if universe_df is not None else {}

    conn = _get_connection(db_path)
    added = 0
    for _, row in dca_plan_df.iterrows():
        conn.execute(
            "INSERT INTO dca_orders (scan_time, symbol, market, dilim, tetik_fiyati, tutar, adet) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (scan_time, row["symbol"], market_by_symbol.get(row["symbol"], "?"),
             int(row["dilim"]), float(row["tetik_fiyati"]), float(row["tutar"]), float(row["adet"])),
        )
        added += 1
    conn.commit()
    conn.close()
    return added


def update_grid_outcomes(current_data_by_symbol: dict, db_path: str = None) -> dict:
    """
    Her taramada çağrılır. Bekleyen grid seviyelerini güncel fiyat
    verisiyle karşılaştırır: al_fiyati'na değdiyse "al_gerceklesti",
    sonra sat_fiyati'na değerse "sat_gerceklesti" (kazançla kapanır).
    """
    conn = _get_connection(db_path)
    stats = {"al_gerceklesti": 0, "sat_gerceklesti": 0, "suresi_doldu": 0}

    pending = conn.execute("SELECT * FROM grid_orders WHERE durum IN ('beklemede', 'al_gerceklesti')").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM grid_orders LIMIT 1").description]

    for row in pending:
        r = dict(zip(cols, row))
        df = current_data_by_symbol.get(r["symbol"])
        if df is None or df.empty:
            continue

        recent = df[df.index >= pd.Timestamp(r["scan_time"]).normalize()] if "scan_time" in r else df
        if recent.empty:
            recent = df

        scan_dt = pd.Timestamp(r["scan_time"])

        if r["durum"] == "beklemede":
            hit_buy = (recent["Low"] <= r["al_fiyati"]).any()
            if hit_buy:
                al_tarihi = recent[recent["Low"] <= r["al_fiyati"]].index[0]
                conn.execute(
                    "UPDATE grid_orders SET durum = 'al_gerceklesti', al_tarihi = ? WHERE id = ?",
                    (str(al_tarihi), r["id"]),
                )
                stats["al_gerceklesti"] += 1
            elif (datetime.now() - scan_dt.to_pydatetime()).days > MAX_PENDING_DAYS:
                # ÖNEMLİ: Süre dolumu kontrolü fiyat kontrolünden SONRA yapılıyor —
                # aksi halde uzun süredir güncellenmemiş (ama aslında tetiklenmiş
                # olabilecek) emirler, fiyata hiç bakılmadan yanlışlıkla
                # "süresi doldu" olarak işaretlenirdi.
                conn.execute("UPDATE grid_orders SET durum = 'suresi_doldu' WHERE id = ?", (r["id"],))
                stats["suresi_doldu"] += 1

        elif r["durum"] == "al_gerceklesti":
            after_buy = recent[recent.index > pd.Timestamp(r["al_tarihi"])] if r["al_tarihi"] else recent
            hit_sell = (after_buy["High"] >= r["sat_fiyati"]).any() if not after_buy.empty else False
            if hit_sell:
                sat_tarihi = after_buy[after_buy["High"] >= r["sat_fiyati"]].index[0]
                kazanc_pct = (r["sat_fiyati"] / r["al_fiyati"] - 1) * 100
                conn.execute(
                    "UPDATE grid_orders SET durum = 'sat_gerceklesti', sat_tarihi = ?, kazanc_pct = ? WHERE id = ?",
                    (str(sat_tarihi), kazanc_pct, r["id"]),
                )
                stats["sat_gerceklesti"] += 1

    conn.commit()
    conn.close()
    return stats


def update_dca_outcomes(current_data_by_symbol: dict, db_path: str = None) -> dict:
    conn = _get_connection(db_path)
    stats = {"gerceklesti": 0}

    pending = conn.execute("SELECT * FROM dca_orders WHERE durum = 'beklemede'").fetchall()
    cols = [d[0] for d in conn.execute("SELECT * FROM dca_orders LIMIT 1").description]

    for row in pending:
        r = dict(zip(cols, row))
        df = current_data_by_symbol.get(r["symbol"])
        if df is None or df.empty:
            continue

        hit = (df["Low"] <= r["tetik_fiyati"]).any()
        if hit:
            gerceklesme_tarihi = df[df["Low"] <= r["tetik_fiyati"]].index[0]
            conn.execute(
                "UPDATE dca_orders SET durum = 'gerceklesti', gerceklesme_tarihi = ? WHERE id = ?",
                (str(gerceklesme_tarihi), r["id"]),
            )
            stats["gerceklesti"] += 1

    conn.commit()
    conn.close()
    return stats


def compute_grid_performance(db_path: str = None) -> dict:
    """Kapanan (sat_gerceklesti) grid işlemlerinin kazanma oranı ve ortalama getirisi."""
    conn = _get_connection(db_path)
    closed = pd.read_sql("SELECT * FROM grid_orders WHERE durum = 'sat_gerceklesti'", conn)
    pending = pd.read_sql("SELECT * FROM grid_orders WHERE durum IN ('beklemede', 'al_gerceklesti')", conn)
    expired = pd.read_sql("SELECT * FROM grid_orders WHERE durum = 'suresi_doldu'", conn)
    conn.close()

    if closed.empty:
        return {
            "kapanan_islem": 0, "bekleyen": len(pending), "suresi_dolan": len(expired),
            "kazanma_orani_pct": None, "ortalama_kazanc_pct": None,
        }

    win_rate = (closed["kazanc_pct"] > 0).mean() * 100
    return {
        "kapanan_islem": len(closed), "bekleyen": len(pending), "suresi_dolan": len(expired),
        "kazanma_orani_pct": round(win_rate, 1), "ortalama_kazanc_pct": round(closed["kazanc_pct"].mean(), 2),
    }


def compute_dca_performance(current_data_by_symbol: dict = None, db_path: str = None) -> dict:
    """
    DCA'nın kendine özgü doğası: her dilim ayrı bir alım, "satış" yok.
    Performans, gerçekleşen dilimlerin ortalama maliyetiyle GÜNCEL fiyatı
    karşılaştırarak "gerçekleşmemiş kâr/zarar" (unrealized P&L) olarak
    hesaplanır.
    """
    conn = _get_connection(db_path)
    filled = pd.read_sql("SELECT * FROM dca_orders WHERE durum = 'gerceklesti'", conn)
    pending = pd.read_sql("SELECT * FROM dca_orders WHERE durum = 'beklemede'", conn)
    conn.close()

    if filled.empty:
        return {"gerceklesen_dilim": 0, "bekleyen_dilim": len(pending),
                "ortalama_getiri_pct": None, "pozitif_pozisyon_orani_pct": None}

    returns = []
    if current_data_by_symbol:
        for symbol, group in filled.groupby("symbol"):
            df = current_data_by_symbol.get(symbol)
            if df is None or df.empty:
                continue
            current_price = df["Close"].iloc[-1]
            avg_cost = (group["tetik_fiyati"] * group["adet"]).sum() / group["adet"].sum()
            returns.append((current_price / avg_cost - 1) * 100)

    return {
        "gerceklesen_dilim": len(filled), "bekleyen_dilim": len(pending),
        "ortalama_getiri_pct": round(sum(returns) / len(returns), 2) if returns else None,
        "pozitif_pozisyon_orani_pct": round(sum(1 for r in returns if r > 0) / len(returns) * 100, 1) if returns else None,
    }

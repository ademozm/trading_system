"""
Sinyal günlüğü (performans takibi).

Her tarama üretilen AL/SAT sinyallerini SQLite veritabanına kaydeder.
Sonraki taramalarda, önceden açılmış sinyallerin güncel fiyata göre
stop-loss'a mı yoksa hedefe mi ulaştığını kontrol eder, sonucu (kazandı/
kaybetti/açık/süresi doldu) günceller. Bu, "bu sistem gerçekten işe
yarıyor mu" sorusuna zamanla veriyle cevap vermeyi sağlar — GainzAlgo
gibi ürünlerin ASLA göstermediği kısım tam olarak bu.

Tablo şeması (signals):
  id, scan_timestamp, symbol, market, signal, entry_price, stop_price,
  target_price, composite_score, status, close_timestamp, close_price,
  outcome_pct
"""
import logging
import sqlite3
from datetime import datetime, timedelta

import pandas as pd

import config

logger = logging.getLogger("journal")

SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    market TEXT,
    signal INTEGER NOT NULL,
    entry_price REAL,
    stop_price REAL,
    target_price REAL,
    composite_score REAL,
    status TEXT NOT NULL DEFAULT 'open',
    close_timestamp TEXT,
    close_price REAL,
    outcome_pct REAL
);
"""


def get_connection(db_path: str = None) -> sqlite3.Connection:
    db_path = db_path or config.JOURNAL_DB_PATH
    conn = sqlite3.connect(db_path)
    conn.execute(SCHEMA)
    conn.commit()
    return conn


def record_signals(scored_df: pd.DataFrame, scan_timestamp: str, db_path: str = None) -> int:
    """
    Bu taramada üretilen sinyalleri günlüğe ekler. Aynı sembolde hâlâ
    AÇIK bir kayıt varsa (henüz stop/target'a değmemiş), tekrar EKLEMEZ
    — mükerrer kayıt oluşmasın diye.
    Dönüş: eklenen yeni kayıt sayısı.
    """
    if scored_df.empty:
        return 0

    conn = get_connection(db_path)
    cur = conn.cursor()

    open_symbols = {
        row[0] for row in cur.execute("SELECT symbol FROM signals WHERE status = 'open'")
    }

    added = 0
    for _, row in scored_df.iterrows():
        if row["symbol"] in open_symbols:
            continue
        stop_dist = row.get("stop_dist", None)
        target_dist = row.get("target_dist", None)
        entry = row["close"]
        direction = row["signal"]
        stop_price = entry - direction * stop_dist if stop_dist else None
        target_price = entry + direction * target_dist if target_dist else None

        cur.execute(
            "INSERT INTO signals (scan_timestamp, symbol, market, signal, entry_price, "
            "stop_price, target_price, composite_score, status) VALUES (?,?,?,?,?,?,?,?,?)",
            (scan_timestamp, row["symbol"], row.get("market"), int(row["signal"]), entry,
             stop_price, target_price, row.get("composite_score"), "open"),
        )
        added += 1

    conn.commit()
    conn.close()
    return added


def update_outcomes(current_data_by_symbol: dict, db_path: str = None) -> dict:
    """
    Açık kayıtları günceller: güncel fiyat verisi (OHLCV DataFrame'i, en
    az kayıt tarihinden sonrasını kapsamalı) stop veya hedefe değmişse
    kapatır. `JOURNAL_MAX_OPEN_DAYS`den eski açık kayıtlar "süresi doldu"
    olarak işaretlenir (ne kazandı ne kaybetti sayılır, nötr).

    Dönüş: {"kazandı": N, "kaybetti": N, "süresi_doldu": N, "hâlâ_açık": N}
    """
    conn = get_connection(db_path)
    cur = conn.cursor()
    open_rows = cur.execute(
        "SELECT id, symbol, signal, entry_price, stop_price, target_price, scan_timestamp FROM signals WHERE status='open'"
    ).fetchall()

    stats = {"kazandı": 0, "kaybetti": 0, "süresi_doldu": 0, "hâlâ_açık": 0}
    now = datetime.now()

    for sig_id, symbol, direction, entry, stop_price, target_price, scan_ts in open_rows:
        df = current_data_by_symbol.get(symbol)
        opened_at = datetime.fromisoformat(scan_ts)
        age_days = (now - opened_at).days

        if df is None or df.empty:
            if age_days > config.JOURNAL_MAX_OPEN_DAYS:
                cur.execute(
                    "UPDATE signals SET status='süresi_doldu', close_timestamp=? WHERE id=?",
                    (now.isoformat(), sig_id),
                )
                stats["süresi_doldu"] += 1
            else:
                stats["hâlâ_açık"] += 1
            continue

        recent = df[df.index >= pd.Timestamp(opened_at)]
        if recent.empty:
            stats["hâlâ_açık"] += 1
            continue

        hit_stop = hit_target = False
        exit_price = None
        for _, bar in recent.iterrows():
            if direction == 1:
                if stop_price and bar["Low"] <= stop_price:
                    hit_stop, exit_price = True, stop_price
                    break
                if target_price and bar["High"] >= target_price:
                    hit_target, exit_price = True, target_price
                    break
            else:
                if stop_price and bar["High"] >= stop_price:
                    hit_stop, exit_price = True, stop_price
                    break
                if target_price and bar["Low"] <= target_price:
                    hit_target, exit_price = True, target_price
                    break

        if hit_target:
            outcome_pct = (exit_price / entry - 1) * 100 * direction
            cur.execute(
                "UPDATE signals SET status='kazandı', close_timestamp=?, close_price=?, outcome_pct=? WHERE id=?",
                (now.isoformat(), exit_price, outcome_pct, sig_id),
            )
            stats["kazandı"] += 1
        elif hit_stop:
            outcome_pct = (exit_price / entry - 1) * 100 * direction
            cur.execute(
                "UPDATE signals SET status='kaybetti', close_timestamp=?, close_price=?, outcome_pct=? WHERE id=?",
                (now.isoformat(), exit_price, outcome_pct, sig_id),
            )
            stats["kaybetti"] += 1
        elif age_days > config.JOURNAL_MAX_OPEN_DAYS:
            cur.execute(
                "UPDATE signals SET status='süresi_doldu', close_timestamp=? WHERE id=?",
                (now.isoformat(), sig_id),
            )
            stats["süresi_doldu"] += 1
        else:
            stats["hâlâ_açık"] += 1

    conn.commit()
    conn.close()
    return stats


def compute_performance_stats(db_path: str = None) -> pd.DataFrame:
    """Piyasa bazlı özet istatistik: kaç sinyal, kazanma oranı, ortalama getiri."""
    conn = get_connection(db_path)
    df = pd.read_sql_query("SELECT * FROM signals", conn)
    conn.close()

    if df.empty:
        return pd.DataFrame()

    closed = df[df["status"].isin(["kazandı", "kaybetti"])]
    if closed.empty:
        return pd.DataFrame({"Not": ["Henüz sonuçlanmış (kapanmış) sinyal yok"]})

    summary = closed.groupby("market").agg(
        toplam_kapanan=("id", "count"),
        kazanan=("status", lambda s: (s == "kazandı").sum()),
        ortalama_getiri_pct=("outcome_pct", "mean"),
    ).reset_index()
    summary["kazanma_orani_pct"] = (summary["kazanan"] / summary["toplam_kapanan"] * 100).round(1)
    return summary


def load_all_signals(db_path: str = None) -> pd.DataFrame:
    conn = get_connection(db_path)
    df = pd.read_sql_query("SELECT * FROM signals ORDER BY scan_timestamp DESC", conn)
    conn.close()
    return df

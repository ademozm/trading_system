"""
Paper trading (kağıt üzerinde işlem) modülü.

journal.py ve grid_dca_journal.py TEKİL sinyalleri/emirleri takip eder
("bu sinyal tuttu mu"). Bu modül daha ileri gidip GERÇEK BİR SANAL
PORTFÖY tutar: başlangıç bakiyesi, nakit, açık pozisyonlar, kapanan
işlemler ve zaman içindeki toplam equity (portföy değeri) eğrisi.

Amaç: "Bu sistemin sinyallerini gerçekten takip etseydim, param şu an
ne durumda olurdu?" sorusuna, taramalar ilerledikçe biriken GERÇEK bir
cevap üretmek — tek seferlik bir backtest değil, canlı, kesintisiz
işleyen bir simülasyon.

MANTIK:
- AL sinyali + o sembolde açık pozisyon yoksa + yeterli nakit varsa →
  yeni pozisyon aç (miktar: position_sizing.py'nin zaten hesapladığı
  öneri, korelasyon-düzeltmeli, mevcut nakitle sınırlı)
- SAT sinyali + o sembolde açık pozisyon varsa → pozisyonu kapat (bir
  "çıkış" sinyali olarak yorumlanır; sistem açığa satış YAPMAZ, sadece
  uzun pozisyonları yönetir — bu, çoğu perakende kullanımıyla tutarlı
  ve karmaşıklığı/riski sınırlı tutar)
- Her taramada: açık pozisyonlar güncel fiyatla kontrol edilir, stop
  veya hedef seviyesine değdiyse pozisyon kapanır
- Her taramada: toplam portföy değeri (nakit + açık pozisyonların
  güncel piyasa değeri) equity geçmişine bir satır olarak eklenir

DÜRÜSTLÜK NOTU: Bu GERÇEK bir işlem sistemi DEĞİLDİR — hiçbir borsaya
bağlanmaz, gerçek para hareket ettirmez. Komisyon/slipaj basitleştirilmiş
şekilde uygulanır (gerçek borsanda farklı olabilir). Gerçek trading'e
geçmeden önce bu simülasyonun sonuçlarını ihtiyatla değerlendir.
"""
import logging
import os
import sqlite3
from datetime import datetime

import numpy as np
import pandas as pd

import config

logger = logging.getLogger("paper_trading")

DB_PATH = os.path.join(config.DATA_DIR, "paper_trading.db")
COMMISSION_PCT = 0.001   # işlem başına %0.1 (giriş + çıkışta ayrı ayrı uygulanır)
SLIPPAGE_PCT = 0.0005    # %0.05


def _get_connection(db_path: str = None) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path or DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            cash REAL, initial_balance REAL, created_at TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT, market TEXT,
            entry_date TEXT, entry_price REAL, quantity REAL,
            stop_price REAL, target_price REAL,
            status TEXT DEFAULT 'open',
            exit_date TEXT, exit_price REAL, exit_reason TEXT,
            pnl_pct REAL, pnl_amount REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_equity_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_date TEXT, equity REAL, cash REAL, open_positions_value REAL
        )
    """)
    return conn


def initialize_account(initial_balance: float, db_path: str = None) -> dict:
    """Hesap yoksa oluşturur; VARSA dokunmaz (var olan bakiyeyi sıfırlamaz)."""
    conn = _get_connection(db_path)
    existing = conn.execute("SELECT * FROM paper_account WHERE id = 1").fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO paper_account (id, cash, initial_balance, created_at) VALUES (1, ?, ?, ?)",
            (initial_balance, initial_balance, datetime.now().isoformat()),
        )
        conn.commit()
        state = {"cash": initial_balance, "initial_balance": initial_balance, "yeni_hesap": True}
    else:
        state = {"cash": existing[1], "initial_balance": existing[2], "yeni_hesap": False}
    conn.close()
    return state


def get_account_state(db_path: str = None) -> dict | None:
    conn = _get_connection(db_path)
    row = conn.execute("SELECT cash, initial_balance, created_at FROM paper_account WHERE id = 1").fetchone()
    conn.close()
    if row is None:
        return None
    return {"cash": row[0], "initial_balance": row[1], "created_at": row[2]}


def get_open_positions(db_path: str = None) -> pd.DataFrame:
    conn = _get_connection(db_path)
    df = pd.read_sql("SELECT * FROM paper_positions WHERE status = 'open'", conn)
    conn.close()
    return df


def _update_cash(conn: sqlite3.Connection, delta: float):
    conn.execute("UPDATE paper_account SET cash = cash + ? WHERE id = 1", (delta,))


def process_new_signals(scored_df: pd.DataFrame, signals_by_symbol: dict, db_path: str = None) -> dict:
    """
    AL sinyali olup açık pozisyonu olmayan sembollerde yeni pozisyon açar;
    SAT sinyali olup açık pozisyonu OLAN sembollerde pozisyonu kapatır
    (çıkış sinyali olarak).
    """
    if scored_df.empty:
        return {"acilan": 0, "kapanan": 0}

    conn = _get_connection(db_path)
    account = conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()
    if account is None:
        conn.close()
        raise RuntimeError("Hesap başlatılmamış — önce initialize_account() çağrılmalı.")
    cash = account[0]

    open_symbols = set(pd.read_sql("SELECT symbol FROM paper_positions WHERE status = 'open'", conn)["symbol"])

    stats = {"acilan": 0, "kapanan": 0}

    for _, row in scored_df.iterrows():
        symbol = row["symbol"]
        signal = row.get("signal")

        if signal == 1 and symbol not in open_symbols:
            entry_price = row.get("close")
            if pd.isna(entry_price) or entry_price <= 0:
                continue

            position_value = row.get("efektif_pozisyon_buyuklugu")
            if pd.isna(position_value) or position_value is None:
                position_value = row.get("pozisyon_buyuklugu")
            if pd.isna(position_value) or position_value is None or position_value <= 0:
                continue
            position_value = min(position_value, cash)  # eldeki nakti aşmasın
            if position_value < entry_price:  # 1 adet bile alacak nakit yoksa atla
                continue

            quantity = position_value / entry_price
            entry_price_with_slip = entry_price * (1 + SLIPPAGE_PCT)
            cost = quantity * entry_price_with_slip * (1 + COMMISSION_PCT)
            if cost > cash:
                continue

            sig_df = signals_by_symbol.get(symbol)
            atr_pct = row.get("atr_pct", 2.0) / 100 if pd.notna(row.get("atr_pct")) else 0.02
            stop_price = entry_price * (1 - atr_pct * 2)
            target_price = entry_price * (1 + atr_pct * 3)
            if sig_df is not None and "stop_dist" in sig_df.columns:
                last = sig_df.iloc[-1]
                if pd.notna(last.get("stop_dist")):
                    stop_price = entry_price - last["stop_dist"]
                    target_price = entry_price + last["target_dist"]

            conn.execute(
                "INSERT INTO paper_positions (symbol, market, entry_date, entry_price, quantity, "
                "stop_price, target_price, status) VALUES (?, ?, ?, ?, ?, ?, ?, 'open')",
                (symbol, row.get("market", "?"), datetime.now().isoformat(), entry_price_with_slip,
                 quantity, stop_price, target_price),
            )
            cash -= cost
            open_symbols.add(symbol)
            stats["acilan"] += 1

        elif signal == -1 and symbol in open_symbols:
            exit_price = row.get("close")
            if pd.isna(exit_price):
                continue
            pos = conn.execute(
                "SELECT id, entry_price, quantity FROM paper_positions WHERE symbol = ? AND status = 'open'",
                (symbol,),
            ).fetchone()
            if pos is None:
                continue
            pos_id, entry_price, quantity = pos
            exit_price_with_slip = exit_price * (1 - SLIPPAGE_PCT)
            proceeds = quantity * exit_price_with_slip * (1 - COMMISSION_PCT)
            pnl_pct = (exit_price_with_slip / entry_price - 1) * 100
            pnl_amount = proceeds - (quantity * entry_price)

            conn.execute(
                "UPDATE paper_positions SET status = 'closed_signal', exit_date = ?, exit_price = ?, "
                "exit_reason = 'sat_sinyali', pnl_pct = ?, pnl_amount = ? WHERE id = ?",
                (datetime.now().isoformat(), exit_price_with_slip, pnl_pct, pnl_amount, pos_id),
            )
            cash += proceeds
            open_symbols.discard(symbol)
            stats["kapanan"] += 1

    _update_cash(conn, cash - account[0])
    conn.commit()
    conn.close()
    return stats


def update_open_positions(current_data_by_symbol: dict, db_path: str = None) -> dict:
    """Açık pozisyonları güncel fiyatla kontrol eder; stop/hedefe değdiyse kapatır."""
    conn = _get_connection(db_path)
    open_positions = pd.read_sql("SELECT * FROM paper_positions WHERE status = 'open'", conn)
    stats = {"hedefe_ulasti": 0, "stop_oldu": 0}

    for _, pos in open_positions.iterrows():
        df = current_data_by_symbol.get(pos["symbol"])
        if df is None or df.empty:
            continue

        entry_ts = pd.Timestamp(pos["entry_date"]) if pos["entry_date"] else None
        recent = df[df.index > entry_ts] if entry_ts is not None else df
        if recent.empty:
            # Pozisyon henüz çok yeni (fiyat verisinde entry_date'ten sonraki
            # bar henüz yok) — bu normal, sonraki taramada tekrar kontrol edilir.
            continue

        hit_target = (recent["High"] >= pos["target_price"]).any()
        hit_stop = (recent["Low"] <= pos["stop_price"]).any()

        if hit_stop or hit_target:
            exit_price = pos["stop_price"] if hit_stop else pos["target_price"]
            exit_price_with_slip = exit_price * (1 - SLIPPAGE_PCT)
            proceeds = pos["quantity"] * exit_price_with_slip * (1 - COMMISSION_PCT)
            pnl_pct = (exit_price_with_slip / pos["entry_price"] - 1) * 100
            pnl_amount = proceeds - (pos["quantity"] * pos["entry_price"])
            reason = "stop" if hit_stop else "target"

            conn.execute(
                "UPDATE paper_positions SET status = ?, exit_date = ?, exit_price = ?, "
                "exit_reason = ?, pnl_pct = ?, pnl_amount = ? WHERE id = ?",
                (f"closed_{reason}", datetime.now().isoformat(), exit_price_with_slip,
                 reason, pnl_pct, pnl_amount, pos["id"]),
            )
            _update_cash(conn, proceeds)
            stats["hedefe_ulasti" if hit_target and not hit_stop else "stop_oldu"] += 1

    conn.commit()
    conn.close()
    return stats


def record_equity_snapshot(current_data_by_symbol: dict, db_path: str = None) -> float:
    """Nakit + açık pozisyonların güncel piyasa değeri = toplam equity. Geçmişe kaydeder."""
    conn = _get_connection(db_path)
    account = conn.execute("SELECT cash FROM paper_account WHERE id = 1").fetchone()
    if account is None:
        conn.close()
        return 0.0
    cash = account[0]

    open_positions = pd.read_sql("SELECT symbol, quantity FROM paper_positions WHERE status = 'open'", conn)
    open_value = 0.0
    for _, pos in open_positions.iterrows():
        df = current_data_by_symbol.get(pos["symbol"])
        if df is not None and not df.empty:
            open_value += pos["quantity"] * df["Close"].iloc[-1]

    equity = cash + open_value
    conn.execute(
        "INSERT INTO paper_equity_history (snapshot_date, equity, cash, open_positions_value) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), equity, cash, open_value),
    )
    conn.commit()
    conn.close()
    return equity


def compute_performance_stats(db_path: str = None) -> dict:
    conn = _get_connection(db_path)
    account = conn.execute("SELECT cash, initial_balance FROM paper_account WHERE id = 1").fetchone()
    if account is None:
        conn.close()
        return {"not": "Hesap henüz başlatılmamış."}
    cash, initial_balance = account

    closed = pd.read_sql("SELECT * FROM paper_positions WHERE status LIKE 'closed_%'", conn)
    open_positions = pd.read_sql("SELECT * FROM paper_positions WHERE status = 'open'", conn)
    equity_history = pd.read_sql("SELECT * FROM paper_equity_history ORDER BY snapshot_date", conn)
    conn.close()

    current_equity = equity_history["equity"].iloc[-1] if not equity_history.empty else initial_balance
    total_return_pct = (current_equity / initial_balance - 1) * 100

    win_rate = None
    avg_pnl_pct = None
    if not closed.empty:
        win_rate = (closed["pnl_pct"] > 0).mean() * 100
        avg_pnl_pct = closed["pnl_pct"].mean()

    max_drawdown_pct = None
    sharpe = None
    if len(equity_history) >= 5:
        eq = equity_history["equity"]
        running_max = eq.cummax()
        drawdown = (eq / running_max - 1) * 100
        max_drawdown_pct = drawdown.min()

        daily_returns = eq.pct_change().dropna()
        if daily_returns.std() > 0:
            sharpe = daily_returns.mean() / daily_returns.std() * np.sqrt(252)

    return {
        "baslangic_bakiyesi": round(initial_balance, 2),
        "mevcut_equity": round(current_equity, 2),
        "nakit": round(cash, 2),
        "toplam_getiri_pct": round(total_return_pct, 2),
        "acik_pozisyon_sayisi": len(open_positions),
        "kapanan_islem_sayisi": len(closed),
        "kazanma_orani_pct": round(win_rate, 1) if win_rate is not None else None,
        "ortalama_islem_getirisi_pct": round(avg_pnl_pct, 2) if avg_pnl_pct is not None else None,
        "maksimum_dusus_pct": round(max_drawdown_pct, 2) if max_drawdown_pct is not None else None,
        "sharpe_orani": round(sharpe, 2) if sharpe is not None else None,
        "gunluk_kayit_sayisi": len(equity_history),
    }

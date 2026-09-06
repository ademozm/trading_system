"""
Katman 7 — İzleme, Loglama, Denetim: Karar Günlüğü
======================================================
Her önerilen/onaylanan/reddedilen işlem, gerekçesiyle birlikte kalıcı
olarak SQLite'a kaydedilir. İki amaca hizmet eder:
  1) Denetim (audit): "sistem ne zaman ne önerdi, kim onayladı/reddetti"
  2) Öğrenme (reflection): Katman 3c (LLM ajan) bir sonraki kararında
     "bu sembolde geçmişte ne oldu" bilgisini buradan okuyabilir
     (TradingAgents'ın trading_memory.md dosyasının yapılandırılmış hali).
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    position_size_pct REAL NOT NULL,
    confidence REAL,
    rationale TEXT,
    risk_check_result TEXT NOT NULL,      -- 'approved' | 'rejected'
    rejection_reason TEXT,
    human_decision TEXT,                   -- 'approved' | 'rejected' | 'timeout' | NULL (henüz yanıt yok)
    realized_pnl_pct REAL                  -- pozisyon kapandığında doldurulur
);

CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
"""


@dataclass
class DecisionRecord:
    symbol: str
    side: str
    position_size_pct: float
    confidence: Optional[float]
    rationale: str
    risk_check_result: str
    rejection_reason: Optional[str] = None
    human_decision: Optional[str] = None
    realized_pnl_pct: Optional[float] = None


class DecisionLog:
    def __init__(self, db_path: str = "data/decision_log.sqlite3") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.db_path)
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def record(self, decision: DecisionRecord) -> int:
        with self._connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO decisions
                    (created_at, symbol, side, position_size_pct, confidence,
                     rationale, risk_check_result, rejection_reason, human_decision,
                     realized_pnl_pct)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.now(timezone.utc).isoformat(),
                    decision.symbol,
                    decision.side,
                    decision.position_size_pct,
                    decision.confidence,
                    decision.rationale,
                    decision.risk_check_result,
                    decision.rejection_reason,
                    decision.human_decision,
                    decision.realized_pnl_pct,
                ),
            )
            return cur.lastrowid

    def update_human_decision(self, decision_id: int, human_decision: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE decisions SET human_decision = ? WHERE id = ?",
                (human_decision, decision_id),
            )

    def update_realized_pnl(self, decision_id: int, realized_pnl_pct: float) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE decisions SET realized_pnl_pct = ? WHERE id = ?",
                (realized_pnl_pct, decision_id),
            )

    def recent_history_for_symbol(self, symbol: str, limit: int = 5) -> list[dict]:
        """
        Katman 3c'nin (LLM ajan) "bu sembolde son zamanlarda ne oldu"
        sorusuna cevap vermek için kullanılır.
        """
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT created_at, side, human_decision, realized_pnl_pct, rationale
                FROM decisions
                WHERE symbol = ? AND human_decision IS NOT NULL
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (symbol, limit),
            ).fetchall()
            return [dict(row) for row in rows]

    def consecutive_losses(self, symbol: str) -> int:
        """risk_manager'ın 'sembol soğutma' kontrolü için kullanılır."""
        history = self.recent_history_for_symbol(symbol, limit=20)
        count = 0
        for record in history:
            pnl = record.get("realized_pnl_pct")
            if pnl is None:
                continue
            if pnl < 0:
                count += 1
            else:
                break  # en son kazançlı işlemde say durur
        return count


if __name__ == "__main__":
    # Hızlı manuel test: `python -m monitoring.decision_log`
    log = DecisionLog()
    rid = log.record(
        DecisionRecord(
            symbol="BTC/USDT",
            side="long",
            position_size_pct=0.02,
            confidence=0.65,
            rationale="Test kaydı",
            risk_check_result="approved",
        )
    )
    print(f"Kaydedildi, id={rid}")
    print("BTC/USDT geçmişi:", log.recent_history_for_symbol("BTC/USDT"))

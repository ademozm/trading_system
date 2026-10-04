"""
tests/test_decision_log.py
=============================
monitoring/decision_log.py'nin açık pozisyon takibi mantığını doğrular.
Sadece sqlite3 (stdlib) kullanır — bu yüzden her ortamda tam olarak
çalıştırılabilir (duckdb/pydantic gibi ek bağımlılık gerekmez).

KRİTİK REGRESYON TESTİ: main.py bir süre current_total_exposure_pct'i
hep 0.0 olarak başlatıyordu — bu testler, decision_log'un GERÇEK açık
pozisyonlardan doğru bir toplam üretmesini doğruluyor.
"""

from __future__ import annotations

from pathlib import Path

from monitoring.decision_log import DecisionLog, DecisionRecord


def _make_log(tmp_path: Path) -> DecisionLog:
    return DecisionLog(db_path=str(tmp_path / "test_decisions.sqlite3"))


def test_total_open_exposure_is_zero_when_no_decisions(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    assert log.total_open_exposure_pct() == 0.0


def test_total_open_exposure_ignores_rejected_decisions(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(decision_id, "rejected")
    assert log.total_open_exposure_pct() == 0.0, "Reddedilen bir işlem exposure'a dahil edilmemeli"


def test_total_open_exposure_counts_approved_open_positions(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    id1 = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(id1, "approved")

    id2 = log.record(
        DecisionRecord(
            symbol="ETH/USDT", side="long", position_size_pct=0.015,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(id2, "approved")

    assert abs(log.total_open_exposure_pct() - 0.035) < 1e-9


def test_total_open_exposure_excludes_closed_positions(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    id1 = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(id1, "approved")
    assert log.total_open_exposure_pct() == 0.02

    log.close_position(id1, realized_pnl_pct=0.01)
    assert log.total_open_exposure_pct() == 0.0, "Kapatılan pozisyon exposure'dan düşmeli"


def test_open_positions_lists_only_open_ones(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    id1 = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="açık kalacak", risk_check_result="approved",
        )
    )
    log.update_human_decision(id1, "approved")

    id2 = log.record(
        DecisionRecord(
            symbol="ETH/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="kapatılacak", risk_check_result="approved",
        )
    )
    log.update_human_decision(id2, "approved")
    log.close_position(id2, realized_pnl_pct=-0.005)

    open_positions = log.open_positions()
    assert len(open_positions) == 1
    assert open_positions[0]["symbol"] == "BTC/USDT"


def test_exposure_survives_across_separate_decision_log_instances(tmp_path: Path) -> None:
    """
    Bu, "programı yeniden başlatınca exposure sıfırlanıyor" hatasının tam
    regresyon testi: aynı SQLite dosyasına farklı DecisionLog örnekleriyle
    (main.py'nin her çalıştırmada yeni bir örnek oluşturmasını simüle eder)
    bağlanıp açık pozisyonun hâlâ görüldüğünü doğrular.
    """
    db_path = str(tmp_path / "persistent.sqlite3")

    log_run1 = DecisionLog(db_path=db_path)
    decision_id = log_run1.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log_run1.update_human_decision(decision_id, "approved")

    # main.py'nin bir sonraki çalıştırmasını simüle et: TAMAMEN YENİ bir DecisionLog örneği
    log_run2 = DecisionLog(db_path=db_path)
    assert log_run2.total_open_exposure_pct() == 0.02, (
        "Yeni bir DecisionLog örneği (yeni bir 'python -m main' çalıştırması), "
        "önceki açık pozisyonu GÖRMELİ — aksi halde exposure limiti yanlışlıkla aşılabilir."
    )


def test_entry_price_defaults_to_none(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    decision = log.get_decision(decision_id)
    assert decision["entry_price"] is None


def test_update_entry_price_and_get_decision(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_entry_price(decision_id, 65000.5)

    decision = log.get_decision(decision_id)
    assert decision["entry_price"] == 65000.5
    assert decision["symbol"] == "BTC/USDT"


def test_get_decision_returns_none_for_missing_id(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    assert log.get_decision(9999) is None


def test_open_positions_includes_entry_price(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(decision_id, "approved")
    log.update_entry_price(decision_id, 65000.0)

    positions = log.open_positions()
    assert len(positions) == 1
    assert positions[0]["entry_price"] == 65000.0


def test_has_open_position_false_when_no_positions(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    assert log.has_open_position("BTC/USDT") is False


def test_has_open_position_true_after_approval(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(decision_id, "approved")
    assert log.has_open_position("BTC/USDT") is True
    assert log.has_open_position("ETH/USDT") is False, "Farklı sembol etkilenmemeli"


def test_has_open_position_false_after_close(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(decision_id, "approved")
    log.close_position(decision_id, realized_pnl_pct=0.01)
    assert log.has_open_position("BTC/USDT") is False, (
        "KRİTİK: kapatılan pozisyon 'açık' sayılmamalı — aksi halde sürekli "
        "modda o sembol için bir daha ASLA yeni öneri üretilemez."
    )


def test_has_open_position_false_when_rejected(tmp_path: Path) -> None:
    log = _make_log(tmp_path)
    decision_id = log.record(
        DecisionRecord(
            symbol="BTC/USDT", side="long", position_size_pct=0.02,
            confidence=0.6, rationale="test", risk_check_result="approved",
        )
    )
    log.update_human_decision(decision_id, "rejected")
    assert log.has_open_position("BTC/USDT") is False


def test_migration_adds_entry_price_to_old_schema_db(tmp_path: Path) -> None:
    """
    KRİTİK REGRESYON TESTİ: entry_price sütunu eklenmeden ÖNCE oluşturulmuş
    (eski şemalı) bir veritabanı dosyasını simüle eder — DecisionLog bunu
    açtığında ÇÖKMEMELİ, sütunu güvenle eklemeli.
    """
    import sqlite3

    db_path = str(tmp_path / "old_schema.sqlite3")
    old_schema = """
    CREATE TABLE decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        created_at TEXT NOT NULL,
        symbol TEXT NOT NULL,
        side TEXT NOT NULL,
        position_size_pct REAL NOT NULL,
        confidence REAL,
        rationale TEXT,
        risk_check_result TEXT NOT NULL,
        rejection_reason TEXT,
        human_decision TEXT,
        realized_pnl_pct REAL
    );
    """
    conn = sqlite3.connect(db_path)
    conn.executescript(old_schema)
    conn.execute(
        """INSERT INTO decisions
           (created_at, symbol, side, position_size_pct, confidence, rationale,
            risk_check_result, human_decision)
           VALUES ('2024-01-01T00:00:00', 'BTC/USDT', 'long', 0.02, 0.6, 'eski kayıt', 'approved', 'approved')"""
    )
    conn.commit()
    conn.close()

    # Şimdi DecisionLog ile aç -> çökmemeli, entry_price sütununu eklemeli
    log = DecisionLog(db_path=db_path)
    decision = log.get_decision(1)
    assert decision is not None
    assert decision["entry_price"] is None  # eski kayıt için NULL olmalı, hata değil

    # Yeni bir kayıt eklemeye çalışmak da sorunsuz çalışmalı
    new_id = log.record(
        DecisionRecord(
            symbol="ETH/USDT", side="long", position_size_pct=0.01,
            confidence=0.5, rationale="yeni kayıt", risk_check_result="approved",
            entry_price=3000.0,
        )
    )
    assert log.get_decision(new_id)["entry_price"] == 3000.0

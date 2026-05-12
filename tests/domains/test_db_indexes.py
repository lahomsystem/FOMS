import logging

import foms.services.db_indexes as db_indexes


class _FakeDB:
    def __init__(self, *, fail_on_calls=None):
        self.fail_on_calls = set(fail_on_calls or [])
        self.executed_sql: list[str] = []
        self.execute_calls = 0
        self.commit_calls = 0
        self.rollback_calls = 0

    def execute(self, statement):
        self.execute_calls += 1
        sql = str(statement)
        self.executed_sql.append(sql)
        if self.execute_calls in self.fail_on_calls:
            raise RuntimeError(f"boom-{self.execute_calls}")
        return None

    def commit(self):
        self.commit_calls += 1

    def rollback(self):
        self.rollback_calls += 1


def test_apply_phase2_indexes_executes_expected_sql_and_commits(monkeypatch, caplog):
    db = _FakeDB()
    monkeypatch.setattr(db_indexes, "get_db", lambda: db)

    with caplog.at_level(logging.INFO):
        db_indexes.apply_phase2_indexes()

    assert db.commit_calls == 2
    assert db.rollback_calls == 0
    assert any("SET LOCAL lock_timeout" in sql for sql in db.executed_sql)
    assert any("CREATE EXTENSION IF NOT EXISTS pg_trgm;" in sql for sql in db.executed_sql)
    assert any("idx_order_measure_date_trgm" in sql for sql in db.executed_sql)
    assert any("ix_osd_measurement_date" in sql for sql in db.executed_sql)
    assert any(
        "Phase 2: Trigram indexes verified/created under bounded startup policy."
        in record.message
        for record in caplog.records
    )
    assert any(
        "Phase 4: OrderScheduleDate Partial Indexes verified/created successfully." in record.message
        for record in caplog.records
    )


def test_apply_phase2_indexes_rolls_back_failed_trigram_block_and_continues(monkeypatch, caplog):
    db = _FakeDB(fail_on_calls={3})
    monkeypatch.setattr(db_indexes, "get_db", lambda: db)

    with caplog.at_level(logging.INFO):
        db_indexes.apply_phase2_indexes()

    assert db.commit_calls == 1
    assert db.rollback_calls == 1
    assert any("Could not complete trigram index bootstrap" in record.message for record in caplog.records)
    assert any("ix_osd_measurement_date" in sql for sql in db.executed_sql)
    assert any(
        "Phase 4: OrderScheduleDate Partial Indexes verified/created successfully." in record.message
        for record in caplog.records
    )

def test_ensure_erp_date_columns_executes_expected_sql_and_commits(monkeypatch, caplog):
    db = _FakeDB()
    monkeypatch.setattr(db_indexes, "get_db", lambda: db)

    with caplog.at_level(logging.INFO):
        db_indexes.ensure_erp_date_columns()

    assert db.commit_calls == 1
    assert db.rollback_calls == 0
    assert len(db.executed_sql) == 15
    assert any("SET LOCAL lock_timeout" in sql for sql in db.executed_sql)
    assert any("ADD COLUMN IF NOT EXISTS erp_measurement_date" in sql for sql in db.executed_sql)
    assert any("ix_orders_erp_stage_code" in sql for sql in db.executed_sql)
    assert any("ix_orders_erp_stage_updated_at" in sql for sql in db.executed_sql)
    assert any("ix_orders_erp_owner_team_code" in sql for sql in db.executed_sql)
    assert any("Phase B & D flat columns verified." in record.message for record in caplog.records)


def test_ensure_erp_date_columns_rolls_back_and_logs_warning_on_error(monkeypatch, caplog):
    db = _FakeDB(fail_on_calls={3})
    monkeypatch.setattr(db_indexes, "get_db", lambda: db)

    with caplog.at_level(logging.WARNING):
        db_indexes.ensure_erp_date_columns()

    assert db.commit_calls == 0
    assert db.rollback_calls == 1
    assert any("Failed to add erp_date/flat columns" in record.message for record in caplog.records)

"""AUDIT-LOG T9: ``tools/ops/purge_audit_logs.py`` 계약 (DB 불필요 레인).

실 PostgreSQL 이 필요한 삭제 경계·배치·advisory lock 은
``tests/postgres/test_audit_lifecycle_pg.py`` 가 본다. 여기서는 DB 없이 고정 가능한
**계약**만 잠근다:

1. **대상 테이블 목록** — 4종 정확히, 그리고 ``order_events``/``orders`` 는 **절대 부재**
   (T9 가 방금 order_events 를 orders CASCADE 에서 떼어낸 참이다 — purge 가 다시 지우면
   FK 분리가 무의미해진다).
2. **보존기간 기본값·override 해석** — security_logs 2년, 나머지 1년.
3. **CLI 계약** — 기본 dry-run, ``--apply``, 테이블별 ``--retention-days-<table>``,
   ``--dry-run``+``--apply`` 동시 지정은 exit 1.
4. **생성 SQL 표면** — 어떤 테이블의 count/delete SQL 에도 제외 테이블 이름이 없고,
   값은 전부 바인드 파라미터다.
"""
from __future__ import annotations

import pytest

from tools.ops import purge_audit_logs as pal


EXPECTED_DEFAULTS = {
    "security_logs": 730,
    "notification_events": 365,
    "channel_delivery_logs": 365,
    "access_logs": 365,
}


# --------------------------------------------------------------------------- #
# 1. 대상 테이블 목록 (order_events 부재가 핵심 단언)
# --------------------------------------------------------------------------- #
def test_target_tables_are_exactly_the_four_audit_ledgers():
    """대상은 감사 테이블 4종뿐 — 목록이 조용히 늘거나 줄면 red."""
    assert [spec.table for spec in pal.AUDIT_TABLES] == [
        "security_logs", "notification_events", "channel_delivery_logs", "access_logs",
    ]


def test_order_events_is_never_a_purge_target():
    """``order_events`` 는 대상이 아니고, 명시적으로 제외 목록에 있다."""
    tables = {spec.table for spec in pal.AUDIT_TABLES}
    assert "order_events" not in tables
    assert "order_events" in pal.EXCLUDED_TABLES


def test_orders_is_never_a_purge_target():
    """주문 hard purge 는 OPS-APPROVAL 게이트 소관 — 이 도구의 사정권 밖이다."""
    assert "orders" not in {spec.table for spec in pal.AUDIT_TABLES}
    assert "orders" in pal.EXCLUDED_TABLES


def test_target_and_excluded_sets_are_disjoint():
    """대상 목록과 제외 목록은 절대 겹치지 않는다(모듈 import 시점 계약과 동일)."""
    assert not {spec.table for spec in pal.AUDIT_TABLES} & pal.EXCLUDED_TABLES


# --------------------------------------------------------------------------- #
# 2. 보존기간
# --------------------------------------------------------------------------- #
def test_default_retention_days_match_spec():
    """security_logs 730일(2년), 나머지 365일(1년) — 스펙 §4 T9."""
    assert {s.table: s.default_retention_days for s in pal.AUDIT_TABLES} == EXPECTED_DEFAULTS


def test_resolve_retention_days_applies_overrides_only_where_given():
    """override 없는 테이블은 기본값을 유지한다."""
    resolved = pal.resolve_retention_days({"access_logs": 30})
    assert resolved["access_logs"] == 30
    assert resolved["security_logs"] == EXPECTED_DEFAULTS["security_logs"]
    assert set(resolved) == set(EXPECTED_DEFAULTS)


def test_resolve_retention_days_rejects_unknown_table():
    """대상이 아닌 테이블 이름(특히 order_events)은 override 로도 들어올 수 없다."""
    with pytest.raises(ValueError):
        pal.resolve_retention_days({"order_events": 1})


def test_resolve_retention_days_rejects_negative():
    """음수 보존기간은 미래 cutoff 를 만들어 살아있는 행을 지운다 — 거부."""
    with pytest.raises(ValueError):
        pal.resolve_retention_days({"security_logs": -1})


def test_run_rejects_invalid_batch_size_before_touching_db():
    """batch_size 검증은 커넥션을 쓰기 전에 끝난다(None 커넥션으로도 ValueError)."""
    with pytest.raises(ValueError):
        pal.run(None, batch_size=0)


# --------------------------------------------------------------------------- #
# 3. CLI 계약
# --------------------------------------------------------------------------- #
def test_cli_defaults_to_dry_run():
    """인자 없이 실행하면 dry-run(삭제 0)이 기본이다."""
    args = pal._parse_args([])
    assert args.apply is False
    assert args.batch_size == pal.DEFAULT_BATCH_SIZE
    assert pal._overrides_from_args(args) == {}


def test_cli_apply_flag_and_per_table_retention_overrides():
    """``--retention-days-<table>`` 이 테이블마다 존재하고 override 로 해석된다."""
    argv = ["--apply", "--retention-days-security-logs", "900",
            "--retention-days-access-logs", "30"]
    args = pal._parse_args(argv)
    assert args.apply is True
    assert pal._overrides_from_args(args) == {"security_logs": 900, "access_logs": 30}


@pytest.mark.parametrize("spec", pal.AUDIT_TABLES, ids=lambda s: s.table)
def test_every_table_has_a_retention_flag(spec):
    """대상 테이블마다 전용 보존기간 플래그가 파서에 등록돼 있다."""
    args = pal._parse_args([spec.cli_flag, "11"])
    assert pal._overrides_from_args(args) == {spec.table: 11}


def test_cli_rejects_dry_run_and_apply_together():
    """상호배타 플래그 동시 지정은 exit 1(DB 접근 전에 판정)."""
    assert pal.main(["--dry-run", "--apply"]) == 1


# --------------------------------------------------------------------------- #
# 4. 생성 SQL 표면
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("spec", pal.AUDIT_TABLES, ids=lambda s: s.table)
def test_generated_sql_never_names_an_excluded_table(spec):
    """어떤 테이블의 count/delete SQL 에도 제외 테이블 이름이 등장하지 않는다."""
    for sql in (pal.count_sql(spec), pal.delete_batch_sql(spec)):
        for excluded in pal.EXCLUDED_TABLES:
            assert excluded not in sql, sql


@pytest.mark.parametrize("spec", pal.AUDIT_TABLES, ids=lambda s: s.table)
def test_generated_sql_binds_values_and_shares_one_predicate(spec):
    """값은 바인드 파라미터로만 들어가고, count 와 delete 가 같은 술어를 공유한다."""
    predicate = pal._target_predicate(spec)
    assert ":cutoff" in predicate
    assert predicate in pal.count_sql(spec)
    assert predicate in pal.delete_batch_sql(spec)
    assert ":lim" in pal.delete_batch_sql(spec)


def test_self_referencing_table_deletes_children_first():
    """자기참조 FK 가 있는 channel_delivery_logs 만 자식 우선 + survivor guard 를 쓴다."""
    by_table = {spec.table: spec for spec in pal.AUDIT_TABLES}
    chan = by_table["channel_delivery_logs"]
    assert chan.children_first is True
    assert "parent_delivery_id" in chan.survivor_guard_sql
    # 자식은 항상 부모보다 큰 id 를 갖는다 — id 내림차순이 곧 자식 우선.
    assert "ORDER BY t.id DESC" in pal.delete_batch_sql(chan)
    for other in (by_table["security_logs"], by_table["access_logs"],
                  by_table["notification_events"]):
        assert other.children_first is False
        assert other.survivor_guard_sql == ""
        assert "ORDER BY t." in pal.delete_batch_sql(other)


def test_survivor_guard_covers_whole_ancestor_chain_not_just_direct_parent():
    """가드는 직속 부모가 아니라 **조상 전체**를 재귀로 제외한다(2단계 이상 재전송 체인)."""
    chan = {spec.table: spec for spec in pal.AUDIT_TABLES}["channel_delivery_logs"]
    guard = chan.survivor_guard_sql
    assert "WITH RECURSIVE" in guard
    assert "JOIN retained" in guard

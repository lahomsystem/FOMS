"""WDC-LINK-01 — topology-aware 런타임 canonical reader/writer 계약 테스트.

두 층을 검증한다:

* **순수 파생**(PG 불필요): (topology, marker/fence) → read/write 경로 booleans, fingerprint
  결정성·민감도, trust-boundary 입력 검증, Order meta 무접근 정적 불변식.
* **PG 통합**(``FOMS_TEST_DATABASE_URL`` 필요·conftest 가 미설정이면 skip):
  - SAME marker 전 legacy read + dual write(V1+V2 한 tx)·marker 뒤 V2 한 tx(V1 미기록).
  - SEPARATE LEGACY V1·FROZEN all-serving+write 거부(503)·CANONICAL V2 한 tx.
  - same-key 1(idempotent·중복 write 0)·PC/mobile(두 세션) 정합.
  - marker 전 canonical read/enable 안 함·Order meta runtime write 0.
  - topology 바뀐 artifact 소비 거부(SAME↔singleton·fingerprint drift).
  - rollout checker(resolve_rollout) 상태별 보고.

DSN 은 env 로만 주입한다(비밀번호 커밋 0).
"""
from __future__ import annotations

import ast
import datetime
import inspect
import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import sessionmaker
from werkzeug.security import generate_password_hash

from foms.services.orders import estimate_order_link_runtime as rt
from foms.services.orders.estimate_order_link_runtime import (
    READ_SOURCE_CANONICAL_V2,
    READ_SOURCE_LEGACY_V1,
    TOPOLOGY_SAME,
    TOPOLOGY_SEPARATE,
    WRITE_PATH_CANONICAL_V2,
    WRITE_PATH_DUAL,
    WRITE_PATH_LEGACY_V1,
    LinkWriteFrozenError,
    TopologyDriftError,
    WDCLinkRuntimeError,
    read_links,
    resolve_rollout,
    write_link,
)

NOW = datetime.datetime(2026, 7, 26, 12, 0, 0)


# --------------------------------------------------------------------------- #
# 1. 순수 파생 (PG 불필요)
# --------------------------------------------------------------------------- #
def test_derive_same_before_marker_dual_legacy():
    s = rt._derive_state(TOPOLOGY_SAME, marker_present=False, fence_mode=None)
    assert not s.reads_canonical and not s.writes_canonical
    assert s.dual_writes and s.legacy_writes_open and not s.writes_frozen
    assert s.read_source == READ_SOURCE_LEGACY_V1


def test_derive_same_after_marker_canonical():
    s = rt._derive_state(TOPOLOGY_SAME, marker_present=True, fence_mode=None)
    assert s.reads_canonical and s.writes_canonical
    assert not s.dual_writes and not s.legacy_writes_open
    assert s.read_source == READ_SOURCE_CANONICAL_V2


def test_derive_separate_modes():
    leg = rt._derive_state(TOPOLOGY_SEPARATE, False, rt.STATE_LEGACY)
    assert leg.legacy_writes_open and not leg.reads_canonical and not leg.writes_frozen
    fro = rt._derive_state(TOPOLOGY_SEPARATE, False, rt.STATE_FROZEN)
    assert fro.writes_frozen and not fro.reads_canonical and not fro.legacy_writes_open
    can = rt._derive_state(TOPOLOGY_SEPARATE, True, rt.STATE_CANONICAL)
    assert can.reads_canonical and can.marker_present and not can.legacy_writes_open


def test_fingerprint_deterministic_and_sensitive():
    a = rt._fingerprint(TOPOLOGY_SAME, False, None)
    assert a == rt._fingerprint(TOPOLOGY_SAME, False, None)
    assert a != rt._fingerprint(TOPOLOGY_SAME, True, None)                    # marker 경계
    assert a != rt._fingerprint(TOPOLOGY_SEPARATE, False, rt.STATE_LEGACY)    # topology
    assert rt._fingerprint(TOPOLOGY_SEPARATE, False, rt.STATE_LEGACY) != \
        rt._fingerprint(TOPOLOGY_SEPARATE, False, rt.STATE_FROZEN)            # fence mode


def test_unknown_topology_rejected_before_db():
    with pytest.raises(WDCLinkRuntimeError):
        resolve_rollout(None, topology="BOGUS")
    with pytest.raises(WDCLinkRuntimeError):
        write_link(None, 1, 1, topology="BOGUS")


def test_nonpositive_ids_rejected_before_db():
    for est, order in ((0, 5), (5, -1), (True, 5)):
        with pytest.raises(WDCLinkRuntimeError):
            write_link(None, est, order, topology=TOPOLOGY_SAME)
    with pytest.raises(WDCLinkRuntimeError):
        read_links(None, 0, topology=TOPOLOGY_SAME)


def _code_without_docstrings(module) -> str:
    """모듈 소스에서 docstring(설명문)을 지운 실행 코드만 반환(정적 불변식 검사용)."""
    tree = ast.parse(inspect.getsource(module))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body[0].value.value = ""
    return ast.unparse(tree)


def test_writer_code_never_touches_order_meta():
    """Order meta runtime write 0 — 실행 코드(docstring 제외)에 Order meta 토큰 부재."""
    code = _code_without_docstrings(rt)
    assert "structured_data" not in code
    assert "wdc_estimate_id" not in code
    assert "orders" not in code  # orders 테이블 read/write 0(link row 만).


# --------------------------------------------------------------------------- #
# 2. PG 통합
# --------------------------------------------------------------------------- #
_MARKER_TRIGGER = "trg_feature_cutover_marker_immutable"


def _wd_tables(pg_engine):
    from wdcalculator_db import WDCalculatorBase

    WDCalculatorBase.metadata.create_all(bind=pg_engine)


def _reset(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DELETE FROM estimate_order_links_v2"))
        conn.execute(text("DELETE FROM wdc_link_runtime_state"))
        # marker 는 irreversible 트리거가 DELETE 를 막으므로 정리 동안만 비활성화.
        conn.execute(text(f"ALTER TABLE feature_cutover_markers DISABLE TRIGGER {_MARKER_TRIGGER}"))
        conn.execute(text("DELETE FROM feature_cutover_markers WHERE family = 'WDC_LINK'"))
        conn.execute(text(f"ALTER TABLE feature_cutover_markers ENABLE TRIGGER {_MARKER_TRIGGER}"))
        conn.execute(text("DELETE FROM orders WHERE customer_name = 'WDCLINK_TEST'"))
        for tbl in ("estimate_order_matches", "estimate_histories", "estimates"):
            conn.execute(text(f"DELETE FROM {tbl}"))
        # marker 승인자 User 는 남겨둔다(principal-version FK 참조 — throwaway DB 가 세션
        # 종료 시 DROP 하므로 무해). username 은 uuid 라 충돌 없음.


@pytest.fixture
def link_db(pg_engine):
    _wd_tables(pg_engine)
    _reset(pg_engine)
    yield pg_engine
    _reset(pg_engine)


# --- 시드 헬퍼 ------------------------------------------------------------- #
_UNAME_SEQ = [0]


def _make_admin(session) -> int:
    from models import User

    _UNAME_SEQ[0] += 1
    u = User(
        username=f"wdclink_{_UNAME_SEQ[0]}_{uuid.uuid4().hex[:8]}",
        password=generate_password_hash("pw-not-committed"),
        name="승인자", role="ADMIN", team=None, is_active=True,
    )
    session.add(u)
    session.commit()
    return u.id


def _make_estimate(session, customer="고객") -> int:
    from wdcalculator_models import Estimate

    e = Estimate(customer_name=customer, estimate_data={"items": []})
    session.add(e)
    session.flush()
    return e.id


def _add_v1(session, estimate_id, order_id) -> int:
    from wdcalculator_models import EstimateOrderMatch

    m = EstimateOrderMatch(estimate_id=estimate_id, order_id=order_id)
    session.add(m)
    session.flush()
    return m.id


def _v1_count(session, estimate_id, order_id) -> int:
    return session.execute(
        text("SELECT count(*) FROM estimate_order_matches WHERE estimate_id=:e AND order_id=:o"),
        {"e": estimate_id, "o": order_id},
    ).scalar()


def _v2_rows(session, order_id):
    return session.execute(
        text(
            "SELECT estimate_id, source_topology, source_match_id, backfill_run_id "
            "FROM estimate_order_links_v2 WHERE order_id=:o ORDER BY estimate_id"
        ),
        {"o": order_id},
    ).all()


def _seed_marker(session):
    """generic feature_cutover_markers 에 WDC_LINK marker 를 심는다(canonical 경계)."""
    uid = _make_admin(session)
    session.execute(
        text(
            "INSERT INTO feature_cutover_markers (family, cutover_sha, cutover_generation, "
            "minimum_compatibility_generation, readiness_artifact_sha256, ops_approval_id, "
            "approved_by_admin_user_id) VALUES (:f, :sha, 1, 1, :art, :oid, :uid)"
        ),
        {"f": "WDC_LINK", "sha": "0" * 64, "art": "0" * 64, "oid": str(uuid.uuid4()), "uid": uid},
    )
    session.commit()


def _seed_singleton(session):
    from foms.services.security.cutover.wdc_link_fence import seed_wdc_link_runtime_state

    seed_wdc_link_runtime_state(session)
    session.commit()


def _state_version(session) -> int:
    return session.execute(
        text("SELECT row_version FROM wdc_link_runtime_state WHERE id=1")
    ).scalar()


def _freeze(session):
    from foms.services.security.cutover.wdc_link_fence import freeze_wdc_link

    freeze_wdc_link(
        session, _state_version(session),
        freeze_source_fingerprint="0" * 64, freeze_rollout_artifact_sha256="0" * 64,
        prepared_consumer_generation=1,
    )
    session.commit()


def _canonicalize(session):
    from foms.services.security.cutover.wdc_link_fence import canonicalize_wdc_link

    canonicalize_wdc_link(session, _state_version(session))
    session.commit()


def _make_order(session, order_id, sd):
    from models import Order

    o = Order(
        id=order_id, received_date="2026-07-26", customer_name="WDCLINK_TEST",
        phone="010-0000-0000", address="서울", product="침대", structured_data=sd,
    )
    session.add(o)
    session.commit()


# --- SAME ------------------------------------------------------------------ #
def test_pg_same_before_marker_dual_write_legacy_read(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9001
        _make_order(session, oid, {"meta": {"foo": "bar"}})

        rcp = write_link(session, e1, oid, topology=TOPOLOGY_SAME, now=NOW)
        assert rcp.write_path == WRITE_PATH_DUAL
        assert rcp.wrote_v1 and rcp.wrote_v2 and not rcp.idempotent_hit
        assert rcp.v1_match_id is not None and rcp.v2_id is not None and not rcp.marker_present

        # dual: V1·V2 각 1. V2 provenance = SAME·발급 V1 id·runtime(backfill_run_id None).
        assert _v1_count(session, e1, oid) == 1
        rows = _v2_rows(session, oid)
        assert rows == [(e1, TOPOLOGY_SAME, rcp.v1_match_id, None)]

        # marker 전 canonical read 금지 — V2 shadow 가 있어도 read 는 V1.
        res = read_links(session, oid, topology=TOPOLOGY_SAME)
        assert res.read_source == READ_SOURCE_LEGACY_V1 and res.estimate_ids == (e1,)
        assert not resolve_rollout(session, topology=TOPOLOGY_SAME).reads_canonical

        # Order meta runtime write 0 — structured_data 불변(wdc_estimate_id 미기록).
        sd = session.execute(text("SELECT structured_data FROM orders WHERE id=:id"), {"id": oid}).scalar()
        assert sd == {"meta": {"foo": "bar"}}
    finally:
        session.close()


def test_pg_same_idempotent_same_key_one_pc_mobile(link_db):
    """same-key 1 — 재기록(같은/다른 세션=PC/mobile)은 신규 write 0·link 하나."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9002
        first = write_link(session, e1, oid, topology=TOPOLOGY_SAME, now=NOW)
        assert first.wrote_v2 and not first.idempotent_hit
    finally:
        session.close()

    # PC 저장 뒤 mobile 이 같은 key 재시도 — 별 세션.
    mobile = sessionmaker(bind=link_db)()
    try:
        again = write_link(mobile, e1, oid, topology=TOPOLOGY_SAME, now=NOW)
        assert again.idempotent_hit and not again.wrote_v1 and not again.wrote_v2
        assert _v1_count(mobile, e1, oid) == 1
        assert len(_v2_rows(mobile, oid)) == 1
        # PC/mobile 정합 — 어느 세션이 읽어도 같은 견적.
        assert read_links(mobile, oid, topology=TOPOLOGY_SAME).estimate_ids == (e1,)
    finally:
        mobile.close()


def test_pg_same_after_marker_v2_one_tx_no_v1(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9003
        _seed_marker(session)

        rcp = write_link(session, e1, oid, topology=TOPOLOGY_SAME, now=NOW)
        assert rcp.write_path == WRITE_PATH_CANONICAL_V2
        assert rcp.wrote_v2 and not rcp.wrote_v1 and rcp.marker_present
        assert rcp.v1_match_id is None

        # V1 미기록(marker 뒤 V2 only). V2 provenance = SAME·source_match_id None.
        assert _v1_count(session, e1, oid) == 0
        assert _v2_rows(session, oid) == [(e1, TOPOLOGY_SAME, None, None)]

        res = read_links(session, oid, topology=TOPOLOGY_SAME)
        assert res.read_source == READ_SOURCE_CANONICAL_V2 and res.estimate_ids == (e1,)
        assert resolve_rollout(session, topology=TOPOLOGY_SAME).reads_canonical
    finally:
        session.close()


# --- SEPARATE -------------------------------------------------------------- #
def test_pg_separate_legacy_write_v1_read_v1(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9101
        _seed_singleton(session)  # mode=LEGACY

        rcp = write_link(session, e1, oid, topology=TOPOLOGY_SEPARATE, now=NOW)
        assert rcp.write_path == WRITE_PATH_LEGACY_V1
        assert rcp.wrote_v1 and not rcp.wrote_v2 and rcp.fence_mode == rt.STATE_LEGACY
        assert _v1_count(session, e1, oid) == 1
        assert _v2_rows(session, oid) == []  # canonical 아직 아님 — V2 미기록.

        res = read_links(session, oid, topology=TOPOLOGY_SEPARATE)
        assert res.read_source == READ_SOURCE_LEGACY_V1 and res.estimate_ids == (e1,)
        st = resolve_rollout(session, topology=TOPOLOGY_SEPARATE)
        assert st.legacy_writes_open and not st.reads_canonical
    finally:
        session.close()


def test_pg_separate_frozen_serves_v1_rejects_write(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        e2 = _make_estimate(session, "고객2")
        oid = 9102
        _seed_singleton(session)
        _add_v1(session, e1, oid)  # freeze 전 legacy 링크.
        session.commit()
        _freeze(session)  # mode=FROZEN

        # all-serving: 얼린 뒤에도 read 는 기존 V1 을 계속 서빙.
        res = read_links(session, oid, topology=TOPOLOGY_SEPARATE)
        assert res.read_source == READ_SOURCE_LEGACY_V1 and res.estimate_ids == (e1,)

        # 새 write 는 drain·거부(503) — V1/V2 변화 0.
        with pytest.raises(LinkWriteFrozenError):
            write_link(session, e2, oid, topology=TOPOLOGY_SEPARATE, now=NOW)
        session.rollback()
        assert _v1_count(session, e2, oid) == 0
        assert _v2_rows(session, oid) == []

        st = resolve_rollout(session, topology=TOPOLOGY_SEPARATE)
        assert st.writes_frozen and not st.reads_canonical and not st.legacy_writes_open
    finally:
        session.close()


def test_pg_separate_canonical_v2_one_tx(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9103
        _seed_singleton(session)
        _freeze(session)
        _seed_marker(session)   # canonical 게이트(primary marker).
        _canonicalize(session)  # mode=CANONICAL

        rcp = write_link(session, e1, oid, topology=TOPOLOGY_SEPARATE, now=NOW)
        assert rcp.write_path == WRITE_PATH_CANONICAL_V2
        assert rcp.wrote_v2 and not rcp.wrote_v1 and rcp.marker_present
        assert rcp.fence_mode == rt.STATE_CANONICAL
        assert _v2_rows(session, oid) == [(e1, TOPOLOGY_SEPARATE, None, None)]
        assert _v1_count(session, e1, oid) == 0

        res = read_links(session, oid, topology=TOPOLOGY_SEPARATE)
        assert res.read_source == READ_SOURCE_CANONICAL_V2 and res.estimate_ids == (e1,)
    finally:
        session.close()


# --- topology drift -------------------------------------------------------- #
def test_pg_drift_same_with_separate_singleton_refused(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        _seed_singleton(session)  # SEPARATE 상태 존재.
        with pytest.raises(TopologyDriftError):
            resolve_rollout(session, topology=TOPOLOGY_SAME)
        with pytest.raises(TopologyDriftError):
            read_links(session, 9201, topology=TOPOLOGY_SAME)
        with pytest.raises(TopologyDriftError):
            write_link(session, e1, 9201, topology=TOPOLOGY_SAME, now=NOW)
        session.rollback()
    finally:
        session.close()


def test_pg_drift_separate_without_singleton_refused(link_db):
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")  # singleton 미seed.
        with pytest.raises(TopologyDriftError):
            resolve_rollout(session, topology=TOPOLOGY_SEPARATE)
        with pytest.raises(TopologyDriftError):
            write_link(session, e1, 9202, topology=TOPOLOGY_SEPARATE, now=NOW)
        session.rollback()
    finally:
        session.close()


def test_pg_drift_fingerprint_mismatch_refused(link_db):
    """caller 가 marker 전 fingerprint 로 소비 시도 — 경계가 바뀌면 stale artifact 거부."""
    session = sessionmaker(bind=link_db)()
    try:
        e1 = _make_estimate(session, "고객1")
        oid = 9203
        stale_fp = resolve_rollout(session, topology=TOPOLOGY_SAME).fingerprint
        _seed_marker(session)  # 경계 이동 → fingerprint 변경.
        assert resolve_rollout(session, topology=TOPOLOGY_SAME).fingerprint != stale_fp
        with pytest.raises(TopologyDriftError):
            read_links(session, oid, topology=TOPOLOGY_SAME, expected_fingerprint=stale_fp)
        with pytest.raises(TopologyDriftError):
            write_link(session, e1, oid, topology=TOPOLOGY_SAME, expected_fingerprint=stale_fp, now=NOW)
        session.rollback()
    finally:
        session.close()


def test_pg_rollout_checker_same_states(link_db):
    """rollout checker(resolve_rollout) 가 SAME marker 전/후를 정확히 보고."""
    session = sessionmaker(bind=link_db)()
    try:
        s0 = resolve_rollout(session, topology=TOPOLOGY_SAME)
        assert s0.dual_writes and not s0.reads_canonical and s0.fence_mode is None
        _seed_marker(session)
        s1 = resolve_rollout(session, topology=TOPOLOGY_SAME)
        assert s1.reads_canonical and not s1.dual_writes and s1.fingerprint != s0.fingerprint
    finally:
        session.close()


def test_pg_rollout_checker_separate_states(link_db):
    """rollout checker 가 SEPARATE LEGACY→FROZEN 전이를 정확히 보고."""
    session = sessionmaker(bind=link_db)()
    try:
        _seed_singleton(session)
        assert resolve_rollout(session, topology=TOPOLOGY_SEPARATE).legacy_writes_open
        _freeze(session)
        st = resolve_rollout(session, topology=TOPOLOGY_SEPARATE)
        assert st.writes_frozen and not st.legacy_writes_open and not st.reads_canonical
    finally:
        session.close()

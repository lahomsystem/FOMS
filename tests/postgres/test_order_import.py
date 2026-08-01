"""ORDER-IMPORT-01 PostgreSQL 계약 테스트 (PGTEST-00 lane).

admin Excel import 정본 서비스·scan provider 의 계약을 실 PostgreSQL 세션으로 고정한다:

* policy — Admin/Manager 허용, STAFF/VIEWER/미인증 403(MANAGER_MUTATION in-handler gate).
* strict schema — 10MiB / 1000-row 상한 초과 거부, 필수 컬럼 누락 거부.
* full validate — 한 행이라도 실패면 주문 0(부분 진행 없음), FAILED artifact + error download.
* create_order batch all-or-none — 통과 행은 create_order 경유(raw Order 0, mutation_version=1·
  INITIAL_OWNER 배정·ORDER_CREATED event), 한 행 실패 시 주문·artifact 전체 롤백.
* file-hash receipt — 같은 파일 재import 는 기존 receipt(멱등), 주문 재생성 0.
* private artifact 24h — server-derived key(``order_imports/...``·temp path 0)·created_at+24h.
* scan provider — 300s expiry scan 이 만료 artifact 를 EXPIRED claim + STORAGE_DELETE outbox
  (order_import_artifact_id FK), bounded·retry idempotent·advisory lock skip, 별도 scheduler 0.
* scan ready precondition + heartbeat — worker readiness 없으면 import 거부, 있으면 진행.

``FOMS_TEST_DATABASE_URL`` 미설정이면 conftest 가 lane 을 skip 한다. 커밋 파일에는 비밀번호를
넣지 않는다(env 로 주입). advisory-lock/SKIP LOCKED 계약은 실 PostgreSQL 다중 세션이 필요하다.
"""
from __future__ import annotations

import datetime
import io
import pathlib
import types
import uuid

import pandas as pd
import pytest
from sqlalchemy.orm import sessionmaker

from foms.services.datetime_kst import now_utc_naive
from foms.services.order_import_cleanup import run_order_import_expiry_scan_once
from foms.services.orders import order_import as oi
from foms.services.orders.order_create import OwnerPolicyError
from foms.services.orders.order_import import (
    OrderImportTooLarge,
    OrderImportValidationError,
    ScanNotReadyError,
    compute_file_hash,
    import_orders,
)
from foms.services.orders.order_mutation_policy import POLICY_REGISTRY, evaluate_policy
from foms.services.sidefx_worker import (
    WORKER_KINDS,
    clear_expiry_scan_providers,
    register_expiry_scan_provider,
    run_expiry_scan_once,
    upsert_heartbeat,
)
from models import (
    DomainSideEffectOutbox,
    Order,
    OrderAssignment,
    OrderEvent,
    OrderImportArtifact,
    SideEffectWorkerHeartbeat,
    User,
)

_POLICY_ID = "MANAGER_MUTATION"


def _session(pg_engine):
    return sessionmaker(bind=pg_engine)()


def _now():
    return now_utc_naive()


# --------------------------------------------------------------------------- #
# fixtures — 실 User 행(create_order owner FK)·fake private storage·xlsx bytes
# --------------------------------------------------------------------------- #
class _FakeStorage:
    """server-derived private key 로 바이트를 담는 in-memory 저장소(테스트용)."""

    def __init__(self):
        self.blobs: dict[str, bytes] = {}

    def upload_file(self, file_obj, filename, folder):
        file_obj.seek(0)
        data = file_obj.read()
        key = f"{folder}/{uuid.uuid4().hex}_{filename}"
        self.blobs[key] = data
        return {"success": True, "key": key, "filename": filename}

    def read_file_bytes(self, key):
        return self.blobs.get(key)


def _make_user(session, *, role, team=None, active=True) -> User:
    u = User(username=f"u_{uuid.uuid4().hex[:10]}", password="x", name=role,
             role=role, team=team, is_active=active)
    session.add(u)
    session.commit()
    return u


def _admin(session) -> User:
    return _make_user(session, role="ADMIN")


def _sales(session) -> User:
    return _make_user(session, role="STAFF", team="SALES")


def _xlsx_bytes(rows, columns=None) -> bytes:
    cols = columns or ["접수일", "고객명", "전화번호", "주소", "제품",
                       "옵션", "비고", "결제금액"]
    df = pd.DataFrame(rows, columns=cols)
    buf = io.BytesIO()
    df.to_excel(buf, index=False, engine="openpyxl")
    return buf.getvalue()


def _valid_row(name="홍길동"):
    # 비고에 nonce 를 넣어 매 생성 행이 유일 → 테스트별 file-hash 충돌(멱등 단락) 방지.
    return {"접수일": "2026-07-24", "고객명": name, "전화번호": "010-1111-2222",
            "주소": "서울시 강남구", "제품": "침대", "옵션": "블랙",
            "비고": uuid.uuid4().hex, "결제금액": 100000}


def _seed_ready_heartbeats(engine):
    """세 worker_kind heartbeat 를 fresh 로 upsert 해 readiness gate 를 통과시킨다."""
    for kind in WORKER_KINDS:
        upsert_heartbeat(engine, kind, oldest_lag_seconds=0)


# --------------------------------------------------------------------------- #
# 1. policy — Admin/Manager 200 · 그 외 403
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("role,team,allowed", [
    ("ADMIN", None, True),
    ("MANAGER", None, True),
    ("STAFF", "SALES", False),
    ("VIEWER", None, False),
])
def test_import_policy_admin_manager_only(role, team, allowed):
    """MANAGER_MUTATION: Admin/Manager 허용, STAFF/VIEWER 403(그 외 거부)."""
    user = types.SimpleNamespace(id=1, role=role, team=team)
    decision = evaluate_policy(POLICY_REGISTRY[_POLICY_ID], user)
    assert decision.allowed is allowed
    if not allowed:
        assert decision.status == 403


def test_import_policy_unauthenticated_denied():
    """미인증(user None)은 401 로 거부된다."""
    decision = evaluate_policy(POLICY_REGISTRY[_POLICY_ID], None)
    assert decision.allowed is False and decision.status == 401


# --------------------------------------------------------------------------- #
# 2. create_order batch all-or-none · raw Order 0
# --------------------------------------------------------------------------- #
def test_import_creates_orders_via_create_order(pg_engine):
    """통과 행은 create_order 경유 batch 생성 — mutation_version=1·INITIAL_OWNER·ORDER_CREATED."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        data = _xlsx_bytes([_valid_row("고객A"), _valid_row("고객B")])
        receipt = import_orders(
            s, actor=admin, owner_user_id=sales.id, file_bytes=data,
            filename="orders.xlsx", storage=_FakeStorage(), check_readiness=False)

        assert receipt.state == "COMPLETED" and receipt.row_count == 2
        assert len(receipt.resource_order_ids) == 2
        for oid in receipt.resource_order_ids:
            order = s.get(Order, oid)
            assert order.mutation_version == 1  # create_order 경유 증거(raw Order 아님)
            assert order.is_erp_order is False and order.status == "RECEIVED"
            assign = s.query(OrderAssignment).filter_by(
                order_id=oid, source="INITIAL_OWNER", user_id=sales.id).count()
            assert assign == 1
            evt = s.query(OrderEvent).filter_by(
                order_id=oid, event_type="ORDER_CREATED").count()
            assert evt == 1
    finally:
        s.close()


def test_import_all_or_none_rollback(pg_engine, monkeypatch):
    """batch 중 한 행 실패 → 주문·artifact 전체 롤백(row commit 0·부분 진행 0)."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        before_orders = s.query(Order).count()
        before_artifacts = s.query(OrderImportArtifact).count()
        real_create = oi.create_order
        calls = {"n": 0}

        def _flaky(*a, **k):
            calls["n"] += 1
            if calls["n"] == 2:
                raise RuntimeError("boom on row 2")
            return real_create(*a, **k)

        monkeypatch.setattr(oi, "create_order", _flaky)
        data = _xlsx_bytes([_valid_row("A"), _valid_row("B"), _valid_row("C")])
        with pytest.raises(RuntimeError):
            import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=data,
                          filename="o.xlsx", storage=_FakeStorage(), check_readiness=False)
        s.expire_all()
        assert s.query(Order).count() == before_orders          # 부분 생성 0
        assert s.query(OrderImportArtifact).count() == before_artifacts  # artifact 도 롤백
    finally:
        s.close()


def test_import_owner_policy_admin_self_denied(pg_engine):
    """explicit owner 정책: admin 자신을 owner 로 지정하면 거부(주문 0)."""
    s = _session(pg_engine)
    try:
        admin = _admin(s)
        before = s.query(OrderImportArtifact).count()
        data = _xlsx_bytes([_valid_row("A")])
        with pytest.raises(OwnerPolicyError):
            import_orders(s, actor=admin, owner_user_id=admin.id, file_bytes=data,
                          filename="o.xlsx", storage=_FakeStorage(), check_readiness=False)
        s.expire_all()
        assert s.query(OrderImportArtifact).count() == before   # artifact 미생성
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 3. strict schema — 10MiB / 1000-row / 필수 컬럼
# --------------------------------------------------------------------------- #
def test_strict_byte_cap_rejected(pg_engine):
    """10MiB 초과 원본은 파싱 전에 거부된다(strict)."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        big = b"x" * (oi.MAX_IMPORT_BYTES + 1)
        with pytest.raises(OrderImportTooLarge):
            import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=big,
                          filename="big.xlsx", storage=_FakeStorage(), check_readiness=False)
    finally:
        s.close()


def test_strict_row_cap_rejected(pg_engine):
    """1000행 초과는 거부된다(strict, 부분 처리 없음)."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        before = s.query(Order).count()
        data = _xlsx_bytes([_valid_row(f"c{i}") for i in range(oi.MAX_IMPORT_ROWS + 1)])
        with pytest.raises(OrderImportTooLarge):
            import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=data,
                          filename="many.xlsx", storage=_FakeStorage(), check_readiness=False)
        s.expire_all()
        assert s.query(Order).count() == before   # 부분 처리 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 4. full validate — 부분 진행 0 + error download
# --------------------------------------------------------------------------- #
def test_full_validate_no_partial_and_error_download(pg_engine):
    """한 행 검증 실패 → 주문 0 + FAILED artifact(error download 본문)."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        storage = _FakeStorage()
        before = s.query(Order).count()
        rows = [_valid_row("정상"), {**_valid_row(""), "고객명": ""}]  # 2행 고객명 누락
        data = _xlsx_bytes(rows)
        with pytest.raises(OrderImportValidationError) as ei:
            import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=data,
                          filename="bad.xlsx", storage=storage, check_readiness=False)
        receipt = ei.value.receipt
        s.expire_all()
        assert s.query(Order).count() == before                  # 부분 진행 0
        art = s.get(OrderImportArtifact, receipt.artifact_id)
        assert art.state == "FAILED" and art.error_object_key
        body = storage.read_file_bytes(art.error_object_key)      # error download
        assert b"row,field,reason" in body and "고객명".encode("utf-8") in body
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 5. file-hash receipt — 재import 멱등
# --------------------------------------------------------------------------- #
def test_file_hash_receipt_idempotent(pg_engine):
    """같은 파일 재import 는 기존 receipt 반환·주문 재생성 0(file-hash 멱등)."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        data = _xlsx_bytes([_valid_row("A"), _valid_row("B")])
        r1 = import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=data,
                           filename="o.xlsx", storage=_FakeStorage(), check_readiness=False)
        after_first = s.query(Order).count()
        r2 = import_orders(s, actor=admin, owner_user_id=sales.id, file_bytes=data,
                           filename="o.xlsx", storage=_FakeStorage(), check_readiness=False)
        assert r2.idempotent is True and r2.artifact_id == r1.artifact_id
        assert r2.file_hash == compute_file_hash(data)
        assert s.query(Order).count() == after_first             # 재생성 0
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 6. private artifact 24h — server-derived key · temp path 0
# --------------------------------------------------------------------------- #
def test_private_artifact_server_derived_key_24h(pg_engine):
    """source key 는 private 네임스페이스(temp/public path 0)·expires_at=created_at+24h."""
    s = _session(pg_engine)
    try:
        admin, sales = _admin(s), _sales(s)
        now = _now()
        receipt = import_orders(
            s, actor=admin, owner_user_id=sales.id, file_bytes=_xlsx_bytes([_valid_row("A")]),
            filename="o.xlsx", storage=_FakeStorage(), now=now, check_readiness=False)
        art = s.get(OrderImportArtifact, receipt.artifact_id)
        key = art.source_object_key
        assert key.startswith(f"{oi.PRIVATE_KEY_PREFIX}/")       # server-derived private
        assert not key.startswith("/") and "static/uploads" not in key and "/tmp" not in key
        delta = art.expires_at - art.created_at
        assert abs(delta - datetime.timedelta(hours=24)).total_seconds() < 1
    finally:
        s.close()


# --------------------------------------------------------------------------- #
# 7. scan ready precondition + heartbeat
# --------------------------------------------------------------------------- #
def test_scan_not_ready_refuses_import(pg_engine):
    """worker heartbeat 부재 → readiness 실패로 import 거부(정리 안 될 파일 누적 방지)."""
    s = _session(pg_engine)
    try:
        s.query(SideEffectWorkerHeartbeat).delete()
        s.commit()
        admin, sales = _admin(s), _sales(s)
        with pytest.raises(ScanNotReadyError):
            import_orders(s, actor=admin, owner_user_id=sales.id,
                          file_bytes=_xlsx_bytes([_valid_row("A")]), filename="o.xlsx",
                          storage=_FakeStorage(), check_readiness=True)
    finally:
        s.close()


def test_scan_ready_allows_import(pg_engine):
    """세 worker heartbeat 가 fresh 면 readiness 통과 후 import 진행."""
    s = _session(pg_engine)
    try:
        _seed_ready_heartbeats(pg_engine)
        s.expire_all()
        admin, sales = _admin(s), _sales(s)
        receipt = import_orders(
            s, actor=admin, owner_user_id=sales.id,
            file_bytes=_xlsx_bytes([_valid_row("A")]), filename="o.xlsx",
            storage=_FakeStorage(), check_readiness=True)
        assert receipt.state == "COMPLETED"
    finally:
        s.query(SideEffectWorkerHeartbeat).delete()
        s.commit()
        s.close()


# --------------------------------------------------------------------------- #
# 8. scan provider — 만료 claim + STORAGE_DELETE · bounded · idempotent · lock
# --------------------------------------------------------------------------- #
def _expired_artifact(s, *, with_error=False) -> OrderImportArtifact:
    """즉시 만료된 COMPLETED/FAILED artifact 를 private key 와 함께 만든다."""
    past = _now() - datetime.timedelta(hours=25)
    art = OrderImportArtifact(
        file_hash=uuid.uuid4().hex, filename="o.xlsx", row_count=1,
        state="FAILED" if with_error else "COMPLETED",
        source_object_key=f"order_imports/x/{uuid.uuid4().hex}.xlsx",
        error_object_key=(f"order_imports/x/{uuid.uuid4().hex}.csv" if with_error else None),
        created_at=past - datetime.timedelta(hours=24), expires_at=past)
    s.add(art)
    s.commit()
    return art


def test_provider_expires_and_enqueues_storage_delete(pg_engine):
    """만료 COMPLETED → EXPIRED + source key STORAGE_DELETE outbox 1개(order_import FK)."""
    s = _session(pg_engine)
    try:
        art = _expired_artifact(s)
        res = run_order_import_expiry_scan_once(pg_engine, limit=50)
        assert res["skipped"] == 0 and res["artifacts_expired"] >= 1
        s.expire_all()
        s.refresh(art)
        assert art.state == "EXPIRED"
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE",
            DomainSideEffectOutbox.order_import_artifact_id == art.id).count()
        assert n == 1
    finally:
        s.close()


def test_provider_enqueues_both_source_and_error_keys(pg_engine):
    """FAILED artifact(source+error 2 key) → key 별 STORAGE_DELETE 2개."""
    s = _session(pg_engine)
    try:
        art = _expired_artifact(s, with_error=True)
        run_order_import_expiry_scan_once(pg_engine, limit=50)
        s.expire_all()
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.order_import_artifact_id == art.id,
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE").count()
        assert n == 2
    finally:
        s.close()


def test_provider_retry_idempotent(pg_engine):
    """provider 재호출은 중복 STORAGE_DELETE 0(이미 EXPIRED 인 행 재claim 안 함)."""
    s = _session(pg_engine)
    try:
        art = _expired_artifact(s)
        run_order_import_expiry_scan_once(pg_engine, limit=50)
        res2 = run_order_import_expiry_scan_once(pg_engine, limit=50)
        s.expire_all()
        n = s.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.order_import_artifact_id == art.id).count()
        assert n == 1 and res2["skipped"] == 0
    finally:
        s.close()


def test_provider_bounded_limit(pg_engine):
    """bounded: limit 만큼만 artifact 를 처리한다(한 scan 무한 금지)."""
    s = _session(pg_engine)
    try:
        for _ in range(4):
            _expired_artifact(s)
        res = run_order_import_expiry_scan_once(pg_engine, limit=2)
        assert res["artifacts_expired"] == 2
    finally:
        s.close()


def test_provider_advisory_lock_skips_when_held(pg_engine):
    """다른 세션이 advisory lock 을 잡고 있으면 provider 는 benign skip(중복 scan 0)."""
    from sqlalchemy import text
    holder = pg_engine.connect()
    try:
        holder.execute(text("SELECT pg_advisory_lock(hashtext('foms:order_import_expiry_scan'))"))
        holder.commit()
        res = run_order_import_expiry_scan_once(pg_engine, limit=50)
        assert res["skipped"] == 1
    finally:
        holder.execute(text("SELECT pg_advisory_unlock(hashtext('foms:order_import_expiry_scan'))"))
        holder.commit()
        holder.close()


# --------------------------------------------------------------------------- #
# 9. worker 300s 배선 — provider dispatch · 별도 scheduler 0
# --------------------------------------------------------------------------- #
def test_worker_expiry_scan_dispatches_provider(pg_engine):
    """run_expiry_scan_once 는 등록된 order_import provider 를 같은 scan 에서 호출한다."""
    clear_expiry_scan_providers()
    calls = []
    register_expiry_scan_provider("spy", lambda eng: calls.append(1) or {"ok": 1})
    try:
        res = run_expiry_scan_once(pg_engine)
        assert calls == [1] and res["providers"]["spy"] == {"ok": 1}
    finally:
        clear_expiry_scan_providers()


def test_no_separate_scheduler_wiring():
    """정적 증거: 런너는 order_import provider 를 register 로 배선하고 별도 loop 0."""
    src = pathlib.Path(
        "tools/ops/run_domain_side_effect_outbox.py").read_text(encoding="utf-8")
    assert 'register_expiry_scan_provider(\n        "order_import_expiry"' in src \
        or 'register_expiry_scan_provider("order_import_expiry"' in src
    assert "run_order_import_expiry_scan_once(" not in src  # 별도 직접 호출 loop 없음
    assert "--expiry-scan-interval" in src  # 기존 300s scan 재사용

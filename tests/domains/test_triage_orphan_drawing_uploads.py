"""tools/ops/triage_orphan_drawing_uploads.py — 고아 도면 업로드(R1) 세 무리 분류·휴지통(파일 보존).

설계서 2026-09-29 도면 결함 2차 §4.7 R1·§9 2c-2: dry-run 은 쓰기 0 · 세 무리(업로드 시각 대 마지막
TRANSFER 시각) · 적용 뒤 (가) 행은 휴지통 + ``file_retained`` 이벤트 + outbox 0 · 복구 API 200.
운영 DB 에는 닿지 않는다 — 전부 로컬 시드.
"""
from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

import foms.api.files.order_routes as order_routes
from db import db_session
from foms.services.attachment_visibility import include_deleted
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent, SecurityLog, User

_SPEC = importlib.util.spec_from_file_location(
    "triage_orphan_drawing_uploads",
    Path(__file__).resolve().parents[2] / "tools" / "ops" / "triage_orphan_drawing_uploads.py",
)
triage = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(triage)

_DT = datetime.datetime


def _order(sd: dict) -> Order:
    order = Order(received_date="2026-09-01", customer_name="고아", phone="010-0000-0000",
                  address="Seoul", product="붙박이장", status="DRAWING", is_erp_order=True,
                  structured_data=sd)
    db_session.add(order)
    db_session.flush()
    return order


def _att(order_id: int, folder: str, name: str, created_at: _DT, *, category: str = "drawing",
         user_id: int | None = None) -> OrderAttachment:
    att = OrderAttachment(order_id=order_id, filename=name, file_type="image", category=category,
                          storage_key=f"orders/{order_id}/{folder}/{name}", created_at=created_at,
                          user_id=user_id)
    db_session.add(att)
    db_session.flush()
    return att


def _transferred(key: str, at: str) -> dict:
    return {"action": "TRANSFER", "transferred_at": at, "files": [{"key": key}],
            "previous_current_files": []}


@pytest.fixture
def seeded(app):
    """무리마다 1개 이상 + 대상 밖(전달됨·since 이전·다른 분류·drawing/ 폴더) 대조군."""
    drawer = User(username="orphan_drawer", password=generate_password_hash("x"), role="STAFF",
                  team="DRAWING", name="도면", is_active=True)
    db_session.add(drawer)
    db_session.flush()

    main = _order({})
    wiz = f"orders/{main.id}/drawing_wizard/exports/v1.png"
    sent = f"orders/{main.id}/attachments/sent.png"
    main.structured_data = {
        "drawing_current_files": [{"key": wiz}],
        "drawing_transfer_history": [
            _transferred(sent, "2026-09-05 09:00:00"),
            _transferred(wiz, "2026-09-10 10:00:00"),
            {"action": "REQUEST_REVISION", "at": "2026-09-12 10:00:00", "files": []},
        ],
    }
    ids = {
        "a": _att(main.id, "attachments", "before.png", _DT(2026, 9, 1, 12), user_id=drawer.id).id,
        "b": _att(main.id, "attachments", "after.png", _DT(2026, 9, 15, 8)).id,
        "sent": _att(main.id, "attachments", "sent.png", _DT(2026, 9, 5, 8)).id,
        "old": _att(main.id, "attachments", "july.png", _DT(2026, 7, 1, 8)).id,
        "photo": _att(main.id, "attachments", "photo.jpg", _DT(2026, 9, 2), category="measurement").id,
        "folder": _att(main.id, "drawing", "ok.png", _DT(2026, 9, 2)).id,
    }
    no_current = _order({"drawing_current_files": [], "drawing_transfer_history": []})
    ids["c"] = _att(no_current.id, "attachments", "lonely.png", _DT(2026, 9, 3)).id
    unknown_time = _order({"drawing_current_files": [{"key": "orders/x/drawing/cur.png"}],
                           "drawing_transfer_history": [{"action": "TRANSFER", "files": []}]})
    ids["b_unknown"] = _att(unknown_time.id, "attachments", "u.png", _DT(2026, 9, 3)).id
    db_session.commit()
    return ids


def _by_id(summary: dict) -> dict[int, dict]:
    return {r["attachment_id"]: r for r in summary["rows"]}


def test_dry_run_classifies_three_buckets_and_writes_nothing(seeded):
    events_before = db_session.query(OrderEvent).count()

    summary = triage.run(db_session)

    rows = _by_id(summary)
    assert summary["mode"] == "dry-run"
    assert set(rows) == {seeded["a"], seeded["b"], seeded["c"], seeded["b_unknown"]}
    assert rows[seeded["a"]]["bucket"] == triage.BUCKET_A
    assert rows[seeded["a"]]["uploader_team"] == "DRAWING"
    assert rows[seeded["a"]]["last_transfer_at"] == "2026-09-10 10:00:00"
    assert rows[seeded["b"]]["bucket"] == triage.BUCKET_B
    assert rows[seeded["b_unknown"]]["bucket"] == triage.BUCKET_B  # 시각 모름 → 숨기지 않음
    assert rows[seeded["c"]]["bucket"] == triage.BUCKET_C
    assert summary["counts"][triage.BUCKET_B] == {
        "rows": 2, "orders": 2, "action": triage.BUCKET_ACTIONS[triage.BUCKET_B]}
    # 쓰기 0: 이벤트·휴지통·outbox 모두 그대로.
    db_session.expire_all()
    assert db_session.query(OrderEvent).count() == events_before
    assert include_deleted(db_session.query(OrderAttachment)).filter(
        OrderAttachment.deleted_at.isnot(None)).count() == 0
    assert db_session.query(DomainSideEffectOutbox).count() == 0


def test_apply_tombstones_only_chosen_bucket_a_with_file_retained(seeded):
    summary = triage.run(db_session, apply_ids=[seeded["a"], seeded["b"], seeded["c"], 999999],
                         actor_user_id=None)

    assert [r["attachment_id"] for r in summary["applied"]] == [seeded["a"]]
    assert {s["attachment_id"] for s in summary["skipped"]} == {seeded["b"], seeded["c"], 999999}
    db_session.expire_all()
    a = include_deleted(db_session.query(OrderAttachment).filter_by(id=seeded["a"])).one()
    assert a.deleted_at is not None
    for untouched in ("b", "c", "sent", "folder"):
        assert db_session.get(OrderAttachment, seeded[untouched]).deleted_at is None

    event = db_session.query(OrderEvent).filter_by(event_type="ATTACHMENT_DELETED").one()
    assert event.payload["attachment_id"] == seeded["a"]
    assert event.payload["file_retained"] is True
    assert event.payload["retained_reason"] == "ORPHAN_UPLOAD"
    assert db_session.query(DomainSideEffectOutbox).count() == 0  # 파일 보존 — purge 예약 없음
    audit = db_session.query(SecurityLog).filter_by(action="FILE_DELETED").one()
    assert audit.detail["attachment_id"] == seeded["a"]

    again = triage.run(db_session)  # 멱등: 적용한 행은 대상에서 빠진다.
    assert seeded["a"] not in _by_id(again)


def test_trash_convention_matches_attachment_routes():
    """이벤트 이름·표시 이름은 첨부 라우트(§4.3.6)와 같다 — 2b 복구 API 가 읽는 값."""
    assert triage.ATTACHMENT_DELETED == order_routes.ATTACHMENT_DELETED
    assert triage.RETAINED_REASON == "ORPHAN_UPLOAD"


def test_cli_refuses_apply_without_ids_and_mixed_flags():
    assert triage.main(["--apply"]) == 1
    assert triage.main(["--apply", "--dry-run", "--ids", "1"]) == 1


def test_cli_apply_needs_restore_ready_confirmation():
    """2b 복구 보강이 운영에 있다는 확인 플래그 없이는 --apply 를 거절한다(DB 에 닿기 전, 리뷰 P3)."""
    assert triage.main(["--apply", "--ids", "1"]) == 1


class _NoTombstoneFilterSession:
    """전역 tombstone 필터가 등록되지 않은 상황 재현(run_auto_init 이 앞 단계에서 실패해 삼킨 경우)."""

    def __init__(self, session):
        self._session = session

    def query(self, *entities):
        return include_deleted(self._session.query(*entities))

    def get(self, entity, ident):
        return include_deleted(self._session.query(entity)).filter_by(id=ident).one_or_none()

    def __getattr__(self, name):
        return getattr(self._session, name)


def test_already_trashed_rows_stay_out_without_global_filter(seeded):
    """휴지통 행은 전역 필터에 기대지 않고도 목록·적용에서 빠진다 — deleted_at 덮어쓰기·이벤트 중복 없음."""
    trashed_at = _DT(2026, 9, 20, 9)
    att = db_session.get(OrderAttachment, seeded["a"])
    att.deleted_at = trashed_at
    db_session.commit()
    events_before = db_session.query(OrderEvent).count()
    bare = _NoTombstoneFilterSession(db_session)

    summary = triage.run(bare, apply_ids=[seeded["a"]])

    assert seeded["a"] not in _by_id(summary)
    assert summary["applied"] == []
    db_session.expire_all()
    row = include_deleted(db_session.query(OrderAttachment).filter_by(id=seeded["a"])).one()
    assert row.deleted_at == trashed_at
    assert db_session.query(OrderEvent).count() == events_before


class _Storage:
    def object_exists(self, key):
        return True


def test_restore_api_revives_orphan_tombstone(seeded, client, monkeypatch):
    """적용한 (가) 행을 휴지통 복구 API 가 되살린다(2b 복구 보강과 같은 규약)."""
    triage.run(db_session, apply_ids=[seeded["a"]])
    admin = User(username="orphan_admin", password=generate_password_hash("x"), role="ADMIN",
                 team="SALES", name="관리자", is_active=True)
    db_session.add(admin)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
        sess["username"] = admin.username
        sess["role"] = admin.role
    monkeypatch.setattr(order_routes, "get_storage", lambda: _Storage(), raising=False)
    monkeypatch.setattr("foms.services.storage.get_storage", lambda: _Storage(), raising=False)
    att = include_deleted(db_session.query(OrderAttachment).filter_by(id=seeded["a"])).one()

    res = client.post(f"/api/orders/{att.order_id}/attachments/{att.id}/restore")

    assert res.status_code == 200, res.get_json()
    db_session.expire_all()
    assert db_session.get(OrderAttachment, seeded["a"]).deleted_at is None

"""ATTACH-LIFE-01(T4): 첨부 수명주기 — tombstone + 이벤트 + 전역 필터 계약.

첨부 삭제는 ``db.delete`` + R2 즉시삭제였고 기록이 0 건이었다. 이 스위트가 고정하는 계약:

* **tombstone**: DELETE API 는 row 를 지우지 않고 ``deleted_at``/``deleted_by_user_id`` 만
  세운다. R2 blob 은 동기 삭제하지 않고 ``STORAGE_DELETE`` outbox 로 유예 예약한다
  (``source_domain="ORDER_EVENT"`` — 신규 도메인 없음).
* **전역 기본 필터**: ``do_orm_execute`` 가 모든 ORM SELECT 에서 삭제 첨부를 제외한다
  (84 파일 사용처 무수정). ``include_deleted`` opt-in 으로만 보인다.
* **Session 밖 Core/raw SQL 은 필터 미적용(의도)** — purge/worker 경로가 전량을 봐야 한다.
  대신 카운트 raw SQL 2곳은 스스로 ``AND deleted_at IS NULL`` 을 들고 있어야 하고, 새
  우회가 생기면 allowlist 게이트가 red 가 된다.
* **이벤트**: 업로드/메타수정/삭제/복구가 각각 ``ATTACHMENT_*`` OrderEvent 를 남기고
  타임라인 라벨이 "기타 변경"으로 떨어지지 않는다.
* **canonical 파일 라우트 차단**: ``orders/<id>/...`` key 는 attachment row 를 안 보므로
  tombstone lookup 이 따로 있어야 한다 — 없으면 삭제 첨부가 유예 내내 열람된다.
* **복구**: 유예 중(outbox PENDING)에만 복구 가능하고, blob 이 이미 처리된 뒤에는 409.
"""

from __future__ import annotations

import ast
import itertools
from pathlib import Path

import pytest
from sqlalchemy import text

import foms.api.files.order_routes as order_routes
import foms.api.files.routes as file_routes
from db import db_session
from foms.services.attachment_visibility import INCLUDE_DELETED_OPTION, include_deleted
from foms.services.order_event_display import translate_event_type_to_korean
from models import DomainSideEffectOutbox, Order, OrderAttachment, OrderEvent, User

_counter = itertools.count(1)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_R2_HOST = "https://account.r2.cloudflarestorage.com/"

#: raw ``FROM order_attachments`` 를 써도 되는 파일(저장소 상대 경로).
#: - 2 곳의 카운트 쿼리는 스스로 ``deleted_at IS NULL`` 을 들고 있다.
#: - delete_retention 은 purge 용도라 **전량 조회가 정답**이다(치환 금지).
RAW_ORDER_ATTACHMENT_ALLOWLIST = frozenset(
    {
        "foms/services/construction_read_model.py",
        "foms/services/production_read_model.py",
        "foms/services/orders/delete_retention.py",
    }
)


class FakeR2Storage:
    """R2 모드 storage stub — 허용되면 302 redirect."""

    storage_type = "r2"

    def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600,
        response_content_disposition: str | None = None,
    ) -> str:
        return f"{_R2_HOST}{storage_key}?X-Amz-Signature=fresh"

    def delete_file(self, key: str) -> bool:  # pragma: no cover - 호출되면 계약 위반
        raise AssertionError(f"삭제 API 는 R2 를 동기 삭제하면 안 된다(key={key!r})")


@pytest.fixture
def r2_storage(monkeypatch):
    """파일 라우트의 storage 를 R2 stub 으로 교체한다."""
    monkeypatch.setattr(file_routes, "get_storage", lambda: FakeR2Storage())
    monkeypatch.setattr(order_routes, "get_storage", lambda: FakeR2Storage())
    return FakeR2Storage()


def _make_user(*, role: str = "ADMIN") -> User:
    n = next(_counter)
    user = User(
        username=f"attach-life-{n}", password="x", role=role,
        name=f"user-{n}", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _make_order() -> Order:
    order = Order(
        received_date="2026-08-06", customer_name="첨부고객", phone="010-0000-0000",
        address="서울시", product="붙박이장", status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order


def _make_attachment(order_id: int, *, thumbnail: bool = True) -> OrderAttachment:
    n = next(_counter)
    att = OrderAttachment(
        order_id=order_id,
        filename=f"photo-{n}.jpg",
        file_type="image",
        category="measurement",
        file_size=10,
        storage_key=f"orders/{order_id}/attachments/photo-{n}.jpg",
        thumbnail_key=(f"orders/{order_id}/attachments/thumb_photo-{n}.jpg"
                       if thumbnail else None),
    )
    db_session.add(att)
    db_session.commit()
    return att


def _client(app, user: User | None):
    client = app.test_client()
    if user is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user.id
    return client


def _raw_row_count(attachment_id: int) -> int:
    """전역 필터를 우회하는 Core SQL 로 실제 row 존재 여부를 센다."""
    return db_session.execute(
        text("SELECT COUNT(*) FROM order_attachments WHERE id = :i"),
        {"i": attachment_id},
    ).scalar_one()


def _events(order_id: int, event_type: str) -> list[OrderEvent]:
    return (
        db_session.query(OrderEvent)
        .filter(OrderEvent.order_id == order_id, OrderEvent.event_type == event_type)
        .order_by(OrderEvent.id)
        .all()
    )


def _delete(app, user, order_id: int, attachment_id: int):
    return _client(app, user).delete(
        f"/api/orders/{order_id}/attachments/{attachment_id}")


# --------------------------------------------------------------------------
# 1. 전역 기본 필터 (with_loader_criteria)
# --------------------------------------------------------------------------
def test_tombstoned_attachment_is_hidden_from_orm_selects(app):
    """deleted_at 이 찍히면 평범한 ORM 조회에서 사라진다(호출부 무수정)."""
    with app.app_context():
        order = _make_order()
        att = _make_attachment(order.id)
        assert db_session.query(OrderAttachment).filter_by(id=att.id).first() is not None

        db_session.execute(
            text("UPDATE order_attachments SET deleted_at = :t WHERE id = :i"),
            {"t": "2026-08-06 00:00:00", "i": att.id},
        )
        db_session.commit()
        db_session.expire_all()

        assert db_session.query(OrderAttachment).filter_by(id=att.id).first() is None
        assert db_session.query(OrderAttachment).filter_by(order_id=order.id).count() == 0


def test_visibility_listener_is_wired_at_startup(app):
    """전역 필터가 app_init 의 listener 슬롯에서 실제로 등록된다(무음 배선 유실 방지)."""
    import inspect

    import foms.services.attachment_visibility as visibility
    from foms.services import app_init

    assert visibility._LISTENER_REGISTERED is True
    source = inspect.getsource(app_init.run_auto_init)
    assert "register_attachment_visibility_listener()" in source


def test_include_deleted_opt_in_reveals_tombstoned_rows(app):
    """휴지통 경로는 execution option 으로만 필터를 끈다."""
    with app.app_context():
        order = _make_order()
        att = _make_attachment(order.id)
        db_session.execute(
            text("UPDATE order_attachments SET deleted_at = :t WHERE id = :i"),
            {"t": "2026-08-06 00:00:00", "i": att.id},
        )
        db_session.commit()
        db_session.expire_all()

        found = include_deleted(
            db_session.query(OrderAttachment).filter_by(id=att.id)
        ).first()
        assert found is not None
        assert found.deleted_at is not None
        assert INCLUDE_DELETED_OPTION == "include_deleted_attachments"


def test_filter_covers_every_orm_query_shape(app):
    """84 파일 무수정의 근거 — entity/column-only/count/join/2.0 select 전 형태가 제외된다."""
    from sqlalchemy import func, select

    with app.app_context():
        order = _make_order()
        att = _make_attachment(order.id)
        db_session.execute(
            text("UPDATE order_attachments SET deleted_at = :t WHERE id = :i"),
            {"t": "2026-08-06 00:00:00", "i": att.id},
        )
        db_session.commit()
        db_session.expire_all()

        shapes = {
            "entity": db_session.query(OrderAttachment).count(),
            "column_only": db_session.query(OrderAttachment.id).count(),
            "core_count_orm": db_session.execute(
                select(func.count()).select_from(OrderAttachment)).scalar(),
            "select_entity": len(
                db_session.execute(select(OrderAttachment)).scalars().all()),
            "select_column": len(db_session.execute(select(OrderAttachment.id)).all()),
            "join": db_session.query(Order).join(
                OrderAttachment, Order.id == OrderAttachment.order_id).count(),
        }
        assert shapes == dict.fromkeys(shapes, 0), shapes


def test_core_sql_is_not_filtered_on_purpose(app):
    """Session 밖 Core/raw SQL 은 필터가 걸리지 않는다 — purge/worker 가 전량을 봐야 한다."""
    with app.app_context():
        order = _make_order()
        att = _make_attachment(order.id)
        db_session.execute(
            text("UPDATE order_attachments SET deleted_at = :t WHERE id = :i"),
            {"t": "2026-08-06 00:00:00", "i": att.id},
        )
        db_session.commit()
        assert _raw_row_count(att.id) == 1  # row 는 살아있다(hard delete 아님)


# --------------------------------------------------------------------------
# 2. 삭제 API = tombstone + 이벤트 + outbox (R2 동기삭제 0)
# --------------------------------------------------------------------------
def test_delete_api_tombstones_and_keeps_row(app, r2_storage):
    """DELETE 는 row 를 지우지 않고 tombstone 만 세운다(R2 동기 삭제 시 stub 이 터진다)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)

        resp = _delete(app, user, order.id, att.id)
        assert resp.status_code == 200, resp.get_data(as_text=True)
        assert resp.get_json()["success"] is True

        db_session.expire_all()
        assert _raw_row_count(att.id) == 1
        row = include_deleted(db_session.query(OrderAttachment).filter_by(id=att.id)).one()
        assert row.deleted_at is not None
        assert row.deleted_by_user_id == user.id


def test_delete_api_emits_attachment_deleted_event(app, r2_storage):
    """삭제 이벤트 payload 에 attachment_id·storage_key·thumbnail_key·filename 이 실린다."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        storage_key, thumbnail_key, filename = att.storage_key, att.thumbnail_key, att.filename

        assert _delete(app, user, order.id, att.id).status_code == 200

        events = _events(order.id, "ATTACHMENT_DELETED")
        assert len(events) == 1
        payload = events[0].payload
        assert payload["attachment_id"] == att.id
        assert payload["storage_key"] == storage_key
        assert payload["thumbnail_key"] == thumbnail_key
        assert payload["filename"] == filename
        assert events[0].created_by_user_id == user.id


def test_delete_api_enqueues_deferred_storage_delete_outbox(app, r2_storage):
    """본체·썸네일 각각 STORAGE_DELETE 행 1개(공용 handler 는 행당 object_key 1개만 지운다)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        keys = {att.storage_key, att.thumbnail_key}

        assert _delete(app, user, order.id, att.id).status_code == 200

        event = _events(order.id, "ATTACHMENT_DELETED")[0]
        rows = (
            db_session.query(DomainSideEffectOutbox)
            .filter(DomainSideEffectOutbox.effect_type == "STORAGE_DELETE")
            .all()
        )
        assert len(rows) == 2
        assert {r.payload["object_key"] for r in rows} == keys
        for row in rows:
            assert row.source_domain == "ORDER_EVENT"   # 신규 도메인 추가 0
            assert row.order_event_id == event.id
            assert row.status == "PENDING"
            assert row.available_at > row.created_at   # 유예 후 삭제(즉시 아님)


def test_delete_api_without_thumbnail_enqueues_single_row(app, r2_storage):
    """썸네일이 없으면 outbox 는 본체 1행만."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id, thumbnail=False)

        assert _delete(app, user, order.id, att.id).status_code == 200

        rows = (
            db_session.query(DomainSideEffectOutbox)
            .filter(DomainSideEffectOutbox.effect_type == "STORAGE_DELETE")
            .all()
        )
        assert len(rows) == 1
        assert rows[0].payload["object_key"] == att.storage_key


def test_deleting_twice_returns_404(app, r2_storage):
    """이미 삭제된 첨부는 전역 필터에 걸려 재삭제되지 않는다(이벤트 중복 0)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)

        assert _delete(app, user, order.id, att.id).status_code == 200
        assert _delete(app, user, order.id, att.id).status_code == 404
        assert len(_events(order.id, "ATTACHMENT_DELETED")) == 1


# --------------------------------------------------------------------------
# 3. 목록 API — 기본 제외 / include_deleted opt-in 권한
# --------------------------------------------------------------------------
def test_list_api_excludes_deleted_by_default(app, r2_storage):
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _delete(app, user, order.id, att.id)

        resp = _client(app, user).get(f"/api/orders/{order.id}/attachments")
        assert resp.status_code == 200
        assert resp.get_json()["attachments"] == []


def test_list_api_include_deleted_shows_trash_for_manager(app, r2_storage):
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _delete(app, user, order.id, att.id)

        resp = _client(app, user).get(
            f"/api/orders/{order.id}/attachments?include_deleted=1")
        assert resp.status_code == 200
        items = resp.get_json()["attachments"]
        assert [item["id"] for item in items] == [att.id]
        assert items[0]["deleted_at"]


def test_list_api_include_deleted_denied_for_unrelated_user(app, r2_storage):
    """관리 권한이 없으면 휴지통 조회는 403(기본 목록은 계속 200)."""
    with app.app_context():
        admin = _make_user()
        order = _make_order()
        _make_attachment(order.id)
        outsider = _make_user(role="STAFF")

        client = _client(app, outsider)
        assert client.get(f"/api/orders/{order.id}/attachments").status_code == 200
        assert client.get(
            f"/api/orders/{order.id}/attachments?include_deleted=1").status_code == 403
        assert admin.id != outsider.id


# --------------------------------------------------------------------------
# 4. 복구 API (휴지통 대칭)
# --------------------------------------------------------------------------
def test_restore_api_clears_tombstone_and_cancels_outbox(app, r2_storage):
    """복구는 tombstone 해제 + 예약 취소 + ATTACHMENT_RESTORED 이벤트."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _delete(app, user, order.id, att.id)

        resp = _client(app, user).post(
            f"/api/orders/{order.id}/attachments/{att.id}/restore")
        assert resp.status_code == 200, resp.get_data(as_text=True)

        db_session.expire_all()
        restored = db_session.query(OrderAttachment).filter_by(id=att.id).first()
        assert restored is not None and restored.deleted_at is None
        assert restored.deleted_by_user_id is None
        assert db_session.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE").count() == 0
        assert len(_events(order.id, "ATTACHMENT_RESTORED")) == 1


def test_restore_refuses_when_blob_already_processed(app, r2_storage):
    """worker 가 집어간 뒤(PENDING 아님)에는 복구 불가 — 깨진 링크 부활 방지."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _delete(app, user, order.id, att.id)

        db_session.query(DomainSideEffectOutbox).filter(
            DomainSideEffectOutbox.effect_type == "STORAGE_DELETE"
        ).update({"status": "DONE"}, synchronize_session=False)
        db_session.commit()

        resp = _client(app, user).post(
            f"/api/orders/{order.id}/attachments/{att.id}/restore")
        assert resp.status_code == 409
        db_session.expire_all()
        assert db_session.query(OrderAttachment).filter_by(id=att.id).first() is None


def test_restore_on_live_attachment_returns_404(app, r2_storage):
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        resp = _client(app, user).post(
            f"/api/orders/{order.id}/attachments/{att.id}/restore")
        assert resp.status_code == 404


def test_delete_after_restore_is_possible(app, r2_storage):
    """복구가 dedupe 키를 풀어주므로 재삭제가 IntegrityError 없이 된다."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _delete(app, user, order.id, att.id)
        _client(app, user).post(f"/api/orders/{order.id}/attachments/{att.id}/restore")

        assert _delete(app, user, order.id, att.id).status_code == 200
        assert len(_events(order.id, "ATTACHMENT_DELETED")) == 2


# --------------------------------------------------------------------------
# 5. canonical 파일 라우트 tombstone 차단
# --------------------------------------------------------------------------
def test_canonical_key_of_deleted_attachment_is_not_served(app, r2_storage):
    """canonical key 경로는 attachment row 를 안 보므로 별도 tombstone lookup 이 막는다."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        storage_key, thumbnail_key = att.storage_key, att.thumbnail_key

        # 삭제 전에는 서빙된다(회귀 방지 — 살아있는 첨부를 막으면 안 된다).
        assert _client(app, user).get(
            f"/api/files/view/{storage_key}", follow_redirects=False).status_code == 302

        _delete(app, user, order.id, att.id)

        client = _client(app, user)
        for key in (storage_key, thumbnail_key):
            for path in (f"/api/files/view/{key}", f"/api/files/download/{key}",
                         f"/api/files/presigned-urls/{key}"):
                resp = client.get(path, follow_redirects=False)
                assert resp.status_code == 404, f"{path} -> {resp.status_code}"


def test_legacy_key_branch_is_covered_by_global_filter(app, r2_storage):
    """비정규 key 분기는 전역 필터만으로 차단된다(별도 분기 불필요)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        legacy_key = "legacy_uploads/2019/old_photo.jpg"
        att = OrderAttachment(
            order_id=order.id, filename="old.jpg", file_type="image",
            category="measurement", file_size=1, storage_key=legacy_key,
        )
        db_session.add(att)
        db_session.commit()

        client = _client(app, user)
        assert client.get(
            f"/api/files/view/{legacy_key}", follow_redirects=False).status_code == 302

        assert _delete(app, user, order.id, att.id).status_code == 200
        resp = _client(app, user).get(
            f"/api/files/view/{legacy_key}", follow_redirects=False)
        assert resp.status_code == 403  # coverage gate 미통과 → arbitrary key 취급


def test_canonical_key_of_live_attachment_still_served(app, r2_storage):
    """유령 첨부 차단이 살아있는 canonical key 를 막지 않는다(도면/시공 회귀 가드)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _make_attachment(order.id)  # 같은 order 의 다른 첨부

        resp = _client(app, user).get(
            f"/api/files/view/{att.storage_key}", follow_redirects=False)
        assert resp.status_code == 302


# --------------------------------------------------------------------------
# 6. 업로드 / 메타 수정 이벤트
# --------------------------------------------------------------------------
def test_meta_patch_emits_meta_updated_with_from_to(app, r2_storage):
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)

        resp = _client(app, user).patch(
            f"/api/orders/{order.id}/attachments/{att.id}",
            json={"item_index": 2},
        )
        assert resp.status_code == 200, resp.get_data(as_text=True)

        events = _events(order.id, "ATTACHMENT_META_UPDATED")
        assert len(events) == 1
        assert events[0].payload["field"] == "item_index"
        assert events[0].payload["from"] is None
        assert events[0].payload["to"] == 2


def test_meta_patch_noop_emits_nothing(app, r2_storage):
    """값이 그대로면 이벤트를 만들지 않는다(타임라인 노이즈 0)."""
    with app.app_context():
        user = _make_user()
        order = _make_order()
        att = _make_attachment(order.id)
        _client(app, user).patch(
            f"/api/orders/{order.id}/attachments/{att.id}", json={"item_index": None})
        assert _events(order.id, "ATTACHMENT_META_UPDATED") == []


def test_emit_helper_records_added_event(app):
    """업로드 경로 2종이 공유하는 emit 헬퍼가 ATTACHMENT_ADDED 를 남긴다."""
    with app.app_context():
        order = _make_order()
        att = _make_attachment(order.id)
        order_routes.emit_attachment_event(
            db_session, att, order_routes.ATTACHMENT_ADDED)
        db_session.commit()

        events = _events(order.id, "ATTACHMENT_ADDED")
        assert len(events) == 1
        assert events[0].payload["storage_key"] == att.storage_key


def test_upload_routes_emit_attachment_added(app):
    """업로드 라우트 2곳(멀티파트·direct complete) 모두 emit 배선이 있다."""
    import foms.api.files.direct_upload as direct_upload

    for module, func_name in (
        (order_routes, "api_order_attachments_upload"),
        (direct_upload, "api_order_attachments_complete"),
    ):
        source = Path(module.__file__).read_text(encoding="utf-8")
        tree = ast.parse(source)
        target = next(
            node for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == func_name
        )
        body = ast.unparse(target)
        assert "emit_attachment_event" in body and "ATTACHMENT_ADDED" in body, (
            f"{func_name} 이 ATTACHMENT_ADDED 를 emit 하지 않는다")


# --------------------------------------------------------------------------
# 7. 타임라인 라벨
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    "event_type,label",
    [
        ("ATTACHMENT_ADDED", "첨부파일 추가"),
        ("ATTACHMENT_DELETED", "첨부파일 삭제"),
        ("ATTACHMENT_META_UPDATED", "첨부파일 정보 수정"),
        ("ATTACHMENT_RESTORED", "첨부파일 복구"),
    ],
)
def test_attachment_event_labels_are_registered(event_type, label):
    """무필터 소비자 6곳이 신규 타입을 '기타 변경'으로 떨어뜨리지 않는다."""
    assert translate_event_type_to_korean(event_type) == label


# --------------------------------------------------------------------------
# 8. raw SQL allowlist 게이트 (신규 우회 차단)
# --------------------------------------------------------------------------
def _docstring_nodes(tree: ast.AST) -> set[int]:
    """docstring Constant 노드의 id 집합(주석·문서는 SQL 이 아니므로 스캔 제외)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef,
                                 ast.AsyncFunctionDef)):
            continue
        body = getattr(node, "body", None)
        if not body:
            continue
        first = body[0]
        if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                and isinstance(first.value.value, str):
            ids.add(id(first.value))
    return ids


def _raw_order_attachment_files() -> set[str]:
    """``foms/**.py`` 의 **코드 문자열 리터럴**에서 raw ``order_attachments`` SQL 사용처.

    docstring 은 제외한다 — 이 계약을 설명하는 문서가 스스로를 red 로 만들면 안 된다.
    """
    hits: set[str] = set()
    for path in (_REPO_ROOT / "foms").rglob("*.py"):
        body = path.read_text(encoding="utf-8", errors="ignore")
        if "order_attachments" not in body:
            continue
        tree = ast.parse(body)
        skip = _docstring_nodes(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
                continue
            if id(node) in skip:
                continue
            lowered = node.value.lower()
            if "from order_attachments" in lowered or "join order_attachments" in lowered:
                hits.add(path.relative_to(_REPO_ROOT).as_posix())
                break
    return hits


def test_raw_sql_scanner_detects_a_synthetic_bypass(tmp_path, monkeypatch):
    """스캐너 자체가 동작하는지 — 새 파일에 raw SQL 을 넣으면 잡혀야 한다(게이트 무의미화 방지)."""
    fake_root = tmp_path
    (fake_root / "foms").mkdir()
    (fake_root / "foms" / "sneaky.py").write_text(
        'STMT = "SELECT COUNT(*) FROM order_attachments WHERE order_id = :i"\n',
        encoding="utf-8",
    )
    (fake_root / "foms" / "documented.py").write_text(
        '"""설명: FROM order_attachments 는 전역 필터를 우회한다."""\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "tests.domains.test_attachment_lifecycle._REPO_ROOT", fake_root)
    assert _raw_order_attachment_files() == {"foms/sneaky.py"}


def test_no_new_raw_order_attachment_sql_outside_allowlist():
    """새 raw ``FROM order_attachments`` 는 전역 필터를 우회한다 — allowlist 밖이면 red."""
    unexpected = _raw_order_attachment_files() - RAW_ORDER_ATTACHMENT_ALLOWLIST
    assert not unexpected, (
        "raw order_attachments SQL 은 ORM 전역 tombstone 필터를 받지 않는다. "
        f"신규 사용처: {sorted(unexpected)} — ORM 조회로 바꾸거나, 불가피하면 "
        "'AND deleted_at IS NULL' 을 넣고 이 allowlist 에 근거와 함께 등록할 것."
    )


@pytest.mark.parametrize(
    "relative_path",
    ["foms/services/construction_read_model.py", "foms/services/production_read_model.py"],
)
def test_attachment_count_raw_sql_filters_tombstones(relative_path):
    """카운트 raw SQL 2곳은 삭제 첨부를 스스로 제외한다(대시보드 유령 카운트 0)."""
    body = (_REPO_ROOT / relative_path).read_text(encoding="utf-8")
    assert "FROM order_attachments " in body
    assert "deleted_at IS NULL" in body


def test_delete_retention_raw_sql_stays_unfiltered():
    """purge 스냅샷은 전량 조회가 정답 — deleted_at 필터를 넣으면 blob 이 고아가 된다."""
    body = (_REPO_ROOT / "foms/services/orders/delete_retention.py").read_text(
        encoding="utf-8")
    assert "FROM order_attachments WHERE order_id = :id" in body
    assert "deleted_at IS NULL" not in body


# --------------------------------------------------------------------------
# 9. 마이그레이션 정합 (컬럼·인덱스·downgrade)
# --------------------------------------------------------------------------
def test_migration_defines_columns_indexes_and_downgrade():
    """마이그레이션은 컬럼 2개 + 인덱스 2개를 만들고 downgrade 로 전부 되돌린다."""
    path = _REPO_ROOT / "migrations/versions/attach_life_00_order_attachment_tombstone.py"
    body = path.read_text(encoding="utf-8")
    tree = ast.parse(body)
    funcs = {n.name: ast.unparse(n) for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}

    assert "import models" not in body and "from models" not in body  # 상수 동결 원칙
    for token in ("deleted_at", "deleted_by_user_id",
                  "ix_order_attachments_storage_key",
                  "ix_order_attachments_thumbnail_key"):
        assert token in funcs["upgrade"], f"upgrade 에 {token} 없음"
        assert token in funcs["downgrade"], f"downgrade 에 {token} 없음"
    assert "drop_column" in funcs["downgrade"] and "drop_index" in funcs["downgrade"]


def test_orm_model_matches_migration_schema():
    """ORM 정의(create_all lane)와 마이그레이션이 같은 컬럼·인덱스를 만든다."""
    columns = {c.key for c in OrderAttachment.__table__.columns}
    assert {"deleted_at", "deleted_by_user_id"} <= columns
    index_names = {ix.name for ix in OrderAttachment.__table__.indexes}
    assert {"ix_order_attachments_storage_key",
            "ix_order_attachments_thumbnail_key"} <= index_names

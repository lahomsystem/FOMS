"""AUDIT-LOG T6: 파일 접근 기록(``access_logs`` 부활) 계약 테스트 (SQLite 도메인 레인).

스펙: ``docs/specs/2026-08-05-system-audit-logging-design.md`` §3-3·§4 T6·§7·§8(결정 ③),
플랜: ``docs/plans/2026-08-05-system-audit-logging-plan.md`` T6.

``access_logs`` 는 writer 0 건의 사문 테이블이었다 — 파일 열람/서명URL 발급/다운로드가 전부
무기록이었다. 이 스위트가 고정하는 계약:

1. **R2 302 발급 시에만 기록** — view/presigned/download 각각 행 1건(IP·UA·additional_data).
2. **view 는 (주체, file_key) 10분 dedupe** — 썸네일→원본·새로고침 왕복이 원장을 채우지
   않는다. 창이 만료되면 억제 카운트를 실어 다시 기록한다.
3. **download/presigned 는 dedupe 없음** — 반복 = 반복 반출이므로 매 건이 감사 대상이다.
4. **fail-open** — 감사 engine 이 죽어도 파일 응답은 그대로고 경고 로그만 남는다.
5. **로컬 스토리지 ``send_file`` 분기는 미계측**(스펙이 수용한 한계 — 운영은 R2 전용).
6. **접근이 아닌 것은 기록하지 않는다** — 권한 거부(403)·tombstone 404(T4 공존)는 행 0.
7. **PII 금지** — additional_data 는 file key·주문 id 만 담는다.
8. **계측 위치 고정** — ``StorageAdapter.get_download_url`` **메서드 내부**가 아니라 라우트
   호출부에만 둔다(호출부 14곳: 채널·WAM·admin 헬스체크 오염 방지).

**SQLite 레인의 한계(명시)**: ``audit_writer`` 는 SQLite 에서 메인 engine 을 재사용하므로
"별도 커넥션·별도 트랜잭션"은 여기서 증명되지 않는다. 실 PostgreSQL 독립성·인덱스
마이그레이션 왕복은 ``tests/postgres/test_file_access_log_pg.py`` 가 증명한다.
"""

from __future__ import annotations

import ast
import itertools
import json
import logging
from pathlib import Path

import pytest

import foms.api.files.routes as file_routes
from db import db_session
from foms.services import audit_writer
from models import AccessLog, Order, OrderAttachment, User

_counter = itertools.count(1)
_REPO_ROOT = Path(__file__).resolve().parents[2]
_R2_HOST = "https://account.r2.cloudflarestorage.com/"
_UA = "Mozilla/5.0 (FOMS-T6-Test)"
_IP = "203.0.113.9"

_CUSTOMER_PHONE = "010-7777-8888"
_CUSTOMER_ADDRESS = "서울시 강남구 테헤란로 999"


class FakeR2Storage:
    """R2 모드 storage stub — 허용되면 302 redirect 를 발급한다."""

    storage_type = "r2"

    def get_download_url(
        self,
        storage_key: str,
        expires_in: int = 3600,
        response_content_disposition: str | None = None,
    ) -> str:
        return f"{_R2_HOST}{storage_key}?X-Amz-Signature=fresh"


class FakeLocalStorage:
    """로컬 파일시스템 모드 storage stub — ``send_file`` 분기(미계측 경로)를 탄다."""

    storage_type = "local"

    def __init__(self, upload_folder: str) -> None:
        self.upload_folder = upload_folder


class DeadAuditEngine:
    """``engine.begin()`` 이 항상 실패하는 감사 engine (fail-open 주입용)."""

    def begin(self):
        from sqlalchemy.exc import SQLAlchemyError

        raise SQLAlchemyError("audit engine unavailable (injected)")


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _audit_isolation():
    """dedupe 캐시는 프로세스 전역이다 — 테스트마다 비워 격리한다."""
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


@pytest.fixture
def r2_storage(monkeypatch):
    """파일 라우트의 storage 를 R2 stub 으로 교체한다."""
    stub = FakeR2Storage()
    monkeypatch.setattr(file_routes, "get_storage", lambda: stub)
    return stub


@pytest.fixture
def fake_clock(monkeypatch):
    """dedupe 창을 제어하는 가짜 단조 시계(초 단위 수동 전진)."""

    class _Clock:
        def __init__(self) -> None:
            self.value = 1000.0

        def advance(self, seconds: float) -> None:
            self.value += seconds

    clock = _Clock()
    monkeypatch.setattr(audit_writer, "_monotonic", lambda: clock.value)
    return clock


def _make_user(role: str = "ADMIN") -> int:
    n = next(_counter)
    user = User(
        username=f"file-access-{n}", password="x", role=role,
        name=f"user-{n}", is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _make_order() -> int:
    order = Order(
        received_date="2026-08-06", customer_name="감사고객", phone=_CUSTOMER_PHONE,
        address=_CUSTOMER_ADDRESS, product="붙박이장", status="RECEIVED",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _make_attachment(order_id: int) -> OrderAttachment:
    n = next(_counter)
    att = OrderAttachment(
        order_id=order_id, filename=f"photo-{n}.jpg", file_type="image",
        category="measurement", file_size=10,
        storage_key=f"orders/{order_id}/attachments/photo-{n}.jpg",
    )
    db_session.add(att)
    db_session.commit()
    return att


def _client(app, user_id: int | None):
    client = app.test_client()
    if user_id is not None:
        with client.session_transaction() as sess:
            sess["user_id"] = user_id
    return client


def _get(app, user_id: int, path: str):
    """UA/IP 를 명시한 GET (기록된 값과 대조하기 위해 고정한다)."""
    return _client(app, user_id).get(
        path,
        headers={"User-Agent": _UA},
        environ_base={"REMOTE_ADDR": _IP},
        follow_redirects=False,
    )


def _rows(action: str | None = None) -> list[AccessLog]:
    db_session.expire_all()
    query = db_session.query(AccessLog).order_by(AccessLog.id)
    if action is not None:
        query = query.filter(AccessLog.action == action)
    return query.all()


def _payload(row: AccessLog) -> dict:
    return json.loads(row.additional_data)


def _order_key(order_id: int, name: str = "photo.jpg") -> str:
    return f"orders/{order_id}/attachments/{name}"


# --------------------------------------------------------------------------
# 1. 기본 기록 — view / presigned / download
# --------------------------------------------------------------------------
def test_view_302_records_access_log_with_ip_ua_and_payload(app, r2_storage):
    """R2 302 발급 시 AccessLog 1건 — 주체·IP·UA·file key·order id 가 실제로 저장된다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        resp = _get(app, user_id, f"/api/files/view/{key}")
        assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
        assert _R2_HOST in resp.headers["Location"]

        rows = _rows()
        assert len(rows) == 1, [(r.action, r.additional_data) for r in rows]
        row = rows[0]
        assert row.action == "FILE_VIEW"
        assert row.user_id == user_id
        assert row.ip_address == _IP
        assert row.user_agent == _UA
        assert row.timestamp is not None
        assert _payload(row) == {"storage_key": key, "order_id": order_id}


def test_download_records_file_download_action(app, r2_storage):
    """다운로드는 별도 action 으로 기록된다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        assert _get(app, user_id, f"/api/files/download/{key}").status_code == 302

        rows = _rows()
        assert [r.action for r in rows] == ["FILE_DOWNLOAD"]
        assert _payload(rows[0])["storage_key"] == key


def test_presigned_issue_records_file_presigned_action(app, r2_storage):
    """서명 URL 발급도 기록된다(앱 밖 열람 권한을 넘기는 행위)."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        resp = _get(app, user_id, f"/api/files/presigned-urls/{key}")
        assert resp.status_code == 200
        assert resp.get_json()["success"] is True

        rows = _rows()
        assert [r.action for r in rows] == ["FILE_PRESIGNED"]
        assert _payload(rows[0])["storage_key"] == key


def test_non_order_key_records_without_order_id(app, r2_storage):
    """``order-drafts/...`` 는 주문 id 가 아니다 — order_id 없이 file key 만 기록한다."""
    with app.app_context():
        user_id = _make_user()
        key = f"order-drafts/{user_id}/draft.jpg"

        assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302

        rows = _rows()
        assert len(rows) == 1
        assert _payload(rows[0]) == {"storage_key": key}


# --------------------------------------------------------------------------
# 2. view 10분 dedupe (결정 ③)
# --------------------------------------------------------------------------
def test_view_is_deduped_within_ten_minutes(app, r2_storage, fake_clock):
    """같은 (사용자, file key) 재열람은 10분 창 안에서 행을 추가하지 않는다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        for _ in range(3):
            assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302
        assert len(_rows()) == 1

        # 창 안(9분 59초)에서는 여전히 억제된다.
        fake_clock.advance(599)
        assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302
        assert len(_rows()) == 1


def test_view_records_again_after_window_with_suppressed_count(app, r2_storage, fake_clock):
    """창이 만료되면 다시 기록하고, 억제된 횟수를 payload 에 실어 보고한다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        for _ in range(3):
            _get(app, user_id, f"/api/files/view/{key}")
        fake_clock.advance(601)
        assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302

        rows = _rows()
        assert len(rows) == 2, [_payload(r) for r in rows]
        assert "suppressed" not in _payload(rows[0])
        assert _payload(rows[1])["suppressed"] == 2


def test_view_dedupe_is_per_file_key(app, r2_storage):
    """다른 파일은 같은 창 안이어도 각각 기록된다(dedupe 축 = file key)."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        keys = [_order_key(order_id, "a.jpg"), _order_key(order_id, "b.jpg")]

        for key in keys:
            assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302

        assert [_payload(r)["storage_key"] for r in _rows()] == keys


def test_view_dedupe_is_per_user(app, r2_storage):
    """다른 사용자의 같은 파일 열람은 억제되지 않는다(주체별 독립)."""
    with app.app_context():
        order_id = _make_order()
        key = _order_key(order_id)
        first, second = _make_user(), _make_user()

        for user_id in (first, second):
            assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302

        assert [r.user_id for r in _rows()] == [first, second]


# --------------------------------------------------------------------------
# 3. download/presigned 는 dedupe 없음
# --------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("path_prefix", "action"),
    [("download", "FILE_DOWNLOAD"), ("presigned-urls", "FILE_PRESIGNED")],
)
def test_repeated_download_and_presigned_are_not_deduped(
        app, r2_storage, path_prefix, action):
    """반복 다운로드/발급은 매 건 기록된다 — 반복 반출은 그 자체로 감사 대상이다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        for _ in range(3):
            _get(app, user_id, f"/api/files/{path_prefix}/{key}")

        assert [r.action for r in _rows()] == [action] * 3


def test_view_dedupe_does_not_suppress_download_of_same_file(app, r2_storage):
    """view 억제 창이 열려 있어도 같은 파일의 다운로드는 따로 기록된다(action 별 독립)."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        _get(app, user_id, f"/api/files/view/{key}")
        _get(app, user_id, f"/api/files/view/{key}")       # 억제
        _get(app, user_id, f"/api/files/download/{key}")   # 기록돼야 한다

        assert [r.action for r in _rows()] == ["FILE_VIEW", "FILE_DOWNLOAD"]


# --------------------------------------------------------------------------
# 4. fail-open — 기록 실패가 파일 응답을 죽이지 않는다
# --------------------------------------------------------------------------
def test_audit_engine_failure_does_not_break_file_response(
        app, r2_storage, monkeypatch, caplog):
    """감사 engine 이 죽어도 302 는 그대로 나가고 경고 로그만 남는다(행 0)."""
    monkeypatch.setattr(audit_writer, "get_audit_engine", lambda: DeadAuditEngine())

    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        with caplog.at_level(logging.WARNING, logger="foms.services.audit_writer"):
            resp = _get(app, user_id, f"/api/files/view/{key}")

        assert resp.status_code == 302, resp.get_data(as_text=True)[:300]
        assert _R2_HOST in resp.headers["Location"]
        assert _rows() == []
        assert any("access_logs 독립 기록 실패" in r.getMessage() for r in caplog.records), [
            r.getMessage() for r in caplog.records]


def test_audit_engine_failure_does_not_break_download_or_presigned(
        app, r2_storage, monkeypatch):
    """download/presigned 도 동일하게 정상 응답한다(감사 실패 무영향)."""
    monkeypatch.setattr(audit_writer, "get_audit_engine", lambda: DeadAuditEngine())

    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        assert _get(app, user_id, f"/api/files/download/{key}").status_code == 302
        presigned = _get(app, user_id, f"/api/files/presigned-urls/{key}")
        assert presigned.status_code == 200 and presigned.get_json()["success"] is True
        assert _rows() == []


def test_writer_returns_false_and_records_nothing_on_engine_failure(app, monkeypatch):
    """writer 는 실패를 전파하지 않고 False 를 반환한다."""
    from sqlalchemy.exc import SQLAlchemyError

    def _boom():
        raise SQLAlchemyError("injected")

    monkeypatch.setattr(audit_writer, "get_audit_engine", _boom)
    with app.app_context():
        assert audit_writer.write_access_log_detached(
            "FILE_VIEW", additional_data={"storage_key": "orders/1/x.jpg"}) is False
        assert _rows() == []


# --------------------------------------------------------------------------
# 5. 미계측 경로 · 비-접근은 기록 없음
# --------------------------------------------------------------------------
def test_local_storage_send_file_branch_is_not_instrumented(app, monkeypatch, tmp_path):
    """로컬 스토리지 ``send_file`` 분기는 미계측 — 스펙이 수용한 한계를 계약으로 고정한다."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)

        target = tmp_path / "orders" / str(order_id) / "attachments"
        target.mkdir(parents=True)
        (target / "photo.jpg").write_bytes(b"jpeg-bytes")
        monkeypatch.setattr(
            file_routes, "get_storage", lambda: FakeLocalStorage(str(tmp_path)))

        resp = _get(app, user_id, f"/api/files/view/{key}")
        assert resp.status_code == 200
        assert resp.data == b"jpeg-bytes"
        assert _rows() == [], "로컬 분기는 계측 대상이 아니다(운영은 R2)"


def test_local_presigned_fallback_is_not_instrumented(app, monkeypatch, tmp_path):
    """로컬 모드 presigned 는 서명 URL 을 발급하지 않는다(앱 경유 URL 반환 — 접근 아님)."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        key = _order_key(order_id)
        monkeypatch.setattr(
            file_routes, "get_storage", lambda: FakeLocalStorage(str(tmp_path)))

        resp = _get(app, user_id, f"/api/files/presigned-urls/{key}")
        assert resp.status_code == 200
        assert resp.get_json()["view_url"] == f"/api/files/view/{key}"
        assert _rows() == []


def test_denied_access_is_not_recorded(app, r2_storage):
    """권한 거부(403)는 '접근'이 아니다 — 행을 만들지 않는다."""
    with app.app_context():
        user_id = _make_user(role="STAFF")
        # attachment row 로도 resolve 되지 않는 raw key → 403
        resp = _get(app, user_id, "/api/files/view/random/unowned-object.jpg")
        assert resp.status_code == 403
        assert _rows() == []


def test_anonymous_request_never_reaches_instrumentation(app, r2_storage):
    """비로그인 접근은 ``@login_required`` 가 로그인 화면으로 돌린다 — 파일 접근 자체가 없다.

    (writer 는 ``user_id=None`` + IP 기록을 지원하지만, 현 라우트 구조에서는 그 경로가
    성립하지 않는다는 사실을 계약으로 고정한다.)
    """
    with app.app_context():
        order_id = _make_order()
        resp = _client(app, None).get(
            f"/api/files/view/{_order_key(order_id)}", follow_redirects=False)

        assert resp.status_code == 302
        assert "/login" in resp.headers["Location"]
        assert _rows() == []


def test_deleted_attachment_404_is_not_recorded(app, r2_storage):
    """T4 tombstone 차단(404)과 공존 — 삭제 첨부 접근 시도는 기록 없이 404 다."""
    from foms.services.datetime_kst import now_utc_naive

    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()
        att = _make_attachment(order_id)
        key = att.storage_key

        # 살아있는 동안은 302 + 기록 1건
        assert _get(app, user_id, f"/api/files/view/{key}").status_code == 302
        assert len(_rows()) == 1

        att.deleted_at = now_utc_naive()
        db_session.commit()

        resp = _get(app, user_id, f"/api/files/view/{key}")
        assert resp.status_code == 404
        assert len(_rows()) == 1, "404 는 접근이 아니다 — 추가 행이 생기면 안 된다"


def test_missing_object_404_is_not_recorded(app, monkeypatch):
    """서명 URL 발급 실패(객체 없음) 시에도 기록하지 않는다(302 를 안 냈으므로)."""

    class _EmptyR2(FakeR2Storage):
        def get_download_url(self, storage_key, expires_in=3600,
                             response_content_disposition=None):
            return None

    monkeypatch.setattr(file_routes, "get_storage", lambda: _EmptyR2())
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()

        resp = _get(app, user_id, f"/api/files/view/{_order_key(order_id)}")
        assert resp.status_code == 404
        assert _rows() == []


# --------------------------------------------------------------------------
# 6. PII 금지 · 계측 위치 고정
# --------------------------------------------------------------------------
def test_additional_data_carries_no_customer_pii(app, r2_storage):
    """additional_data 는 file key·주문 id 만 담는다(고객 전화·주소 금지)."""
    with app.app_context():
        user_id = _make_user()
        order_id = _make_order()

        _get(app, user_id, f"/api/files/view/{_order_key(order_id)}")

        row = _rows()[0]
        assert set(_payload(row)) <= {"storage_key", "order_id", "suppressed"}
        blob = row.additional_data
        assert _CUSTOMER_PHONE not in blob and _CUSTOMER_ADDRESS not in blob


def test_storage_adapter_method_is_not_instrumented():
    """``get_download_url`` **메서드 내부** 계측 금지 — 호출부 14곳(채널·WAM·헬스체크) 오염."""
    body = (_REPO_ROOT / "foms/services/storage.py").read_text(encoding="utf-8")
    assert "audit_writer" not in body and "access_log" not in body.lower(), (
        "storage adapter 안에서 감사 기록을 하면 사용자 접근이 아닌 내부 호출까지 기록된다 — "
        "계측은 foms/api/files/routes.py 의 라우트 호출부 3곳에만 둔다."
    )


def test_instrumentation_is_exactly_three_route_call_sites():
    """계측 지점은 파일 라우트 3곳뿐이다(신규 계측이 늘면 스펙 재확인 강제)."""
    body = (_REPO_ROOT / "foms/api/files/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(body)
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_record_file_access"
    ]
    assert len(calls) == 3, [getattr(c, "lineno", None) for c in calls]

    actions = {
        ast.unparse(c.args[0]) for c in calls if c.args
    }
    assert actions == {"ACTION_FILE_VIEW", "ACTION_FILE_PRESIGNED", "ACTION_FILE_DOWNLOAD"}

    # order_routes(첨부 CRUD)는 T6 범위 밖 — 계측이 새면 안 된다.
    other = (_REPO_ROOT / "foms/api/files/order_routes.py").read_text(encoding="utf-8")
    assert "record_file_access" not in other


# --------------------------------------------------------------------------
# 7. 인덱스 마이그레이션 정합
# --------------------------------------------------------------------------
def test_migration_defines_indexes_and_downgrade():
    """마이그레이션은 인덱스 2개를 만들고 downgrade 로 전부 되돌린다(models import 금지)."""
    path = _REPO_ROOT / "migrations/versions/access_log_00_access_log_indexes.py"
    body = path.read_text(encoding="utf-8")
    tree = ast.parse(body)
    funcs = {n.name: ast.unparse(n) for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}

    assert "import models" not in body and "from models" not in body  # 상수 동결 원칙
    assert "down_revision: Union[str, None] = 'attach_life_00'" in body
    for token in ("USER_TIME_INDEX", "TIME_INDEX"):
        assert token in funcs["upgrade"], f"upgrade 에 {token} 없음"
        assert token in funcs["downgrade"], f"downgrade 에 {token} 없음"
    assert "create_index" in funcs["upgrade"]
    assert "drop_index" in funcs["downgrade"]
    assert "ix_access_logs_user_id_timestamp" in body
    assert "ix_access_logs_timestamp" in body


def test_access_log_model_columns_are_unchanged():
    """기존 스키마 그대로 사용한다(AccessLog 컬럼 추가 금지 — T6 파일 경계)."""
    assert {c.key for c in AccessLog.__table__.columns} == {
        "id", "user_id", "action", "ip_address", "user_agent",
        "additional_data", "timestamp",
    }


# --------------------------------------------------------------------------
# 8. writer 단위 계약
# --------------------------------------------------------------------------
def test_write_access_log_detached_serialises_payload_as_json(app):
    """additional_data 는 JSON 문자열로 격납된다(정렬 키 · 한글 원문 유지)."""
    with app.app_context():
        assert audit_writer.write_access_log_detached(
            "FILE_VIEW",
            user_id=None,
            ip="10.0.0.1",
            user_agent="ua",
            additional_data={"storage_key": "orders/9/한글.jpg", "order_id": 9},
        ) is True

        row = _rows()[0]
        assert row.user_id is None
        assert json.loads(row.additional_data) == {
            "storage_key": "orders/9/한글.jpg", "order_id": 9}
        assert "한글" in row.additional_data, "ensure_ascii=False 여야 SQL 조회가 읽힌다"


def test_write_access_log_detached_truncates_oversized_payload(app, monkeypatch):
    """비정상적으로 큰 payload 는 값을 잘라 줄이되 **유효한 JSON** 을 유지한다."""
    monkeypatch.setattr(audit_writer, "ACCESS_ADDITIONAL_DATA_LIMIT", 80)
    with app.app_context():
        assert audit_writer.write_access_log_detached(
            "FILE_VIEW", additional_data={"storage_key": "x" * 500}) is True

        blob = _rows()[0].additional_data
        assert len(blob) <= 80
        payload = json.loads(blob)  # 깨진 JSON 이면 여기서 red — SQL 전용 원장의 생명선
        assert payload["truncated"] is True
        assert payload["storage_key"] == "x" * 32


def test_write_access_log_detached_falls_back_to_valid_json_when_limit_is_tiny(
        app, monkeypatch):
    """상한이 값 트림으로도 안 맞으면 최소 유효 JSON 으로 떨어진다(깨진 문자열 금지)."""
    monkeypatch.setattr(audit_writer, "ACCESS_ADDITIONAL_DATA_LIMIT", 20)
    with app.app_context():
        assert audit_writer.write_access_log_detached(
            "FILE_VIEW", additional_data={"storage_key": "y" * 500}) is True
        assert json.loads(_rows()[0].additional_data) == {"truncated": True}


def test_write_access_log_detached_survives_unserialisable_payload(app):
    """직렬화 불가 값이 들어와도 예외를 던지지 않는다(감사 때문에 응답이 죽으면 안 된다)."""
    with app.app_context():
        assert audit_writer.write_access_log_detached(
            "FILE_VIEW", additional_data={"storage_key": object()}) is True
        assert "object object" in _rows()[0].additional_data


def test_access_view_window_is_ten_minutes_and_separate_from_denial_window():
    """열람 창(10분)은 접근거부 창(60초)과 별도 파라미터다(결정 ③)."""
    assert audit_writer.ACCESS_VIEW_DEDUPE_WINDOW_SECONDS == 600.0
    assert audit_writer.DEDUPE_WINDOW_SECONDS == 60.0


def test_record_file_access_without_window_never_dedupes(app, fake_clock):
    """창을 주지 않으면 같은 키 연타도 전부 기록된다(download/presigned 계약)."""
    with app.app_context():
        for _ in range(3):
            assert audit_writer.record_file_access(
                "FILE_DOWNLOAD", storage_key="orders/1/a.jpg", user_id=1) is True
        assert len(_rows()) == 3


def test_local_storage_branch_has_no_recording_call():
    """소스 수준 확인 — ``send_file`` 두 분기 어디에도 기록 호출이 없다."""
    body = (_REPO_ROOT / "foms/api/files/routes.py").read_text(encoding="utf-8")
    tree = ast.parse(body)
    send_file_lines = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "send_file"
    ]
    assert len(send_file_lines) == 2
    record_lines = [
        node.lineno for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        and node.func.id == "_record_file_access"
    ]
    # 모든 기록 호출은 R2 분기(각 send_file 보다 위)에 있다.
    for record_line in record_lines:
        assert any(record_line < sf for sf in send_file_lines)

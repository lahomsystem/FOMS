"""AUDIT-LOG T8: security_logs 구조화 계약 테스트 (SQLite 도메인 레인).

스펙: ``docs/specs/2026-08-05-system-audit-logging-design.md`` §4 T8·§7,
플랜: ``docs/plans/2026-08-05-system-audit-logging-plan.md`` T8.

검증 대상:

1. 구조화 저장 — 관리자 사용자 수정이 ``action='USER_UPDATE'`` · ``target_type/target_id``
   · ``detail.changes.role.{from,to}`` 로 남는다(자유 텍스트 파싱 없이 SQL 질의 가능).
2. ``additional_data`` 격납 — T8 이전에 **버려지던** dict 가 ``detail`` 에 남는다(결함 해소).
3. 하위호환 — 구조화 인자 없이 부르는 기존 호출부는 그대로 저장되고 컬럼은 NULL.
4. 독립 기록(403/CSRF) — ``action``·``detail.endpoint/reason`` 이 채워진다.
5. admin 감사 화면 — ``action`` 필터가 실제로 행을 줄이고, ``detail`` 표시가 XSS 이스케이프.
6. 우선 호출부 — 로그인 성공/실패·부트스트랩·승인·재설정 요청 처리·계정 전환 action 태그.

**SQLite 레인의 한계(명시)**: JSONB 타입·마이그레이션 왕복·인덱스는 여기서 증명되지
않는다(``JSONColumn`` 이 SQLite 에서 JSON 으로 떨어지고 스키마는 ``create_all`` 부트스트랩).
``tests/postgres/test_security_log_structured_pg.py`` 가 실 PostgreSQL 로 고정한다.
"""

from __future__ import annotations

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import Order, SecurityLog, User
from foms.services import audit_writer
from foms.web.auth.routes import log_access

_STRONG_PW = "Abcdef12"
_RESET_PW = "Zxcvbn99"


# --------------------------------------------------------------------------
# 픽스처 / 헬퍼
# --------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _audit_isolation():
    """dedupe 캐시는 프로세스 전역이다 — 테스트마다 비워 격리한다."""
    audit_writer.reset_dedupe_cache()
    yield
    audit_writer.reset_dedupe_cache()


@pytest.fixture(autouse=True)
def _reset_rate_limits(app):
    """/register·/login 은 rate limit 이 걸려 있다(메모리 버킷이 프로세스 수명 동안 누적)."""
    for limiter in app.extensions.get("limiter", set()):
        limiter.reset()
    yield


@pytest.fixture
def policy_on(app):
    """이 테스트 동안만 주문 정책 가드를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


@pytest.fixture
def guard_on(app):
    """이 테스트 동안만 공용 CSRF/Origin write guard 를 강제 활성화하고 원복한다."""
    sentinel = object()
    prev = app.config.get("WRITE_GUARD_ENABLED", sentinel)
    app.config["WRITE_GUARD_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    else:
        app.config["WRITE_GUARD_ENABLED"] = prev


def _make_user(username, *, role="STAFF", team=None, is_active=True, raw_password=_STRONG_PW):
    """User 를 만들고 정수 id 를 반환한다(요청 teardown 후 detach 대비)."""
    user = User(
        username=username,
        password=generate_password_hash(raw_password),
        role=role,
        team=team,
        name=f"{username}-name",
        is_active=is_active,
    )
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id):
    fresh = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = fresh.id
        sess["username"] = fresh.username
        sess["role"] = fresh.role


def _make_order(status="RECEIVED"):
    order = Order(
        received_date="2026-08-07",
        customer_name="감사 대상",
        phone="010-0000-0000",
        address="Seoul",
        product="Wardrobe",
        status=status,
        manager_name="Alice",
        is_erp_order=True,
        structured_data={"workflow": {"stage": status}},
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _log(app, *args, **kwargs):
    """``log_access`` 를 app context 안에서 직접 호출한다(``get_db`` 가 ``g`` 를 쓴다)."""
    with app.app_context():
        log_access(*args, **kwargs)


def _rows(action=None):
    """현재 security_logs 행을 id 순으로(선택적으로 action 필터)."""
    db_session.expire_all()
    query = db_session.query(SecurityLog)
    if action is not None:
        query = query.filter(SecurityLog.action == action)
    return query.order_by(SecurityLog.id).all()


# --------------------------------------------------------------------------
# 1. 구조화 저장 — 관리자 사용자 수정
# --------------------------------------------------------------------------
def test_edit_user_writes_structured_action_target_and_detail(client, app):
    """role 변경이 action/target/detail.changes.role from→to 로 저장된다."""
    admin_id = _make_user("t8-admin", role="ADMIN")
    target_id = _make_user("t8-target", role="STAFF", team="CS")
    _login(client, admin_id)

    resp = client.post(f"/admin/users/edit/{target_id}", data={
        "username": "t8-target",
        "name": "t8-target-name",
        "role": "ADMIN",
        "team": "CS",
        "is_active": "on",
    })
    assert resp.status_code == 302, resp.get_data(as_text=True)[:400]

    rows = _rows("USER_UPDATE")
    assert len(rows) == 1, [(r.action, r.message) for r in _rows()]
    row = rows[0]
    assert row.target_type == "user"
    assert row.target_id == target_id
    assert row.user_id == admin_id
    assert row.detail["changes"]["role"] == {"from": "STAFF", "to": "ADMIN"}
    # message 의미는 그대로 유지된다(사람용 요약 — 스펙 §4 T8).
    assert "role STAFF→ADMIN" in row.message


def test_edit_user_without_tracked_change_has_no_changes_detail(client, app):
    """감사 대상 필드가 그대로면 detail 은 NULL 이고 action/target 만 남는다."""
    admin_id = _make_user("t8-admin-nochange", role="ADMIN")
    target_id = _make_user("t8-target-nochange", role="STAFF", team="CS")
    _login(client, admin_id)

    client.post(f"/admin/users/edit/{target_id}", data={
        "username": "t8-target-nochange",
        "name": "이름만 변경",
        "role": "STAFF",
        "team": "CS",
        "is_active": "on",
    })

    rows = _rows("USER_UPDATE")
    assert len(rows) == 1
    assert rows[0].detail is None
    assert rows[0].target_id == target_id


def test_admin_password_reset_row_is_structured_without_secret(client, app):
    """비밀번호 재설정은 별도 action 행이며 detail 에도 비밀번호가 없다."""
    admin_id = _make_user("t8-pw-admin", role="ADMIN")
    target_id = _make_user("t8-pw-target", role="STAFF", team="CS")
    _login(client, admin_id)

    client.post(f"/admin/users/edit/{target_id}", data={
        "username": "t8-pw-target",
        "name": "t8-pw-target-name",
        "role": "STAFF",
        "team": "CS",
        "is_active": "on",
        "new_password": _RESET_PW,
    })

    rows = _rows("USER_PASSWORD_RESET")
    assert len(rows) == 1
    assert rows[0].target_type == "user" and rows[0].target_id == target_id
    db_session.expire_all()
    saved_hash = db_session.get(User, target_id).password
    for row in _rows():
        serialized = f"{row.message}{row.detail}"
        assert _RESET_PW not in serialized
        assert saved_hash not in serialized


# --------------------------------------------------------------------------
# 2. additional_data → detail 격납 (기존 유실 결함 해소)
# --------------------------------------------------------------------------
def test_additional_data_is_stored_in_detail(app):
    """T8 이전에 버려지던 ``additional_data`` dict 가 detail 에 남는다."""
    _log(app, "주문 일괄 복원", None, {"count": 3, "order_ids": [1, 2]})

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].detail == {"count": 3, "order_ids": [1, 2]}


def test_additional_data_and_detail_merge_with_detail_winning(app):
    """둘 다 오면 병합하고, 같은 키는 명시 인자인 detail 이 이긴다."""
    _log(app, "병합 검증", None, {"count": 1, "legacy": True},
               detail={"count": 99, "reason": "explicit"})

    detail = _rows()[0].detail
    assert detail == {"count": 99, "legacy": True, "reason": "explicit"}


def test_non_dict_additional_data_is_not_lost(app):
    """dict 이 아닌 레거시 값도 버리지 않고 ``additional_data`` 키에 담는다."""
    _log(app, "비-dict 격납", None, "raw-string-payload")

    assert _rows()[0].detail == {"additional_data": "raw-string-payload"}


def test_unserializable_detail_does_not_kill_the_write(app):
    """직렬화 불가 값이 섞여도 감사 행은 남는다(감사 부가정보 < 업무 — 스펙 §3 원칙 4)."""
    import datetime

    _log(app, "직렬화 검증", None, {"when": datetime.datetime(2026, 8, 7, 1, 2, 3)})

    rows = _rows()
    assert len(rows) == 1
    assert rows[0].detail["when"].startswith("2026-08-07")


def test_oversized_detail_is_replaced_by_truncation_marker(app):
    """비정상적으로 큰 payload 는 JSONB 를 부풀리지 않고 표식으로 대체된다."""
    _log(app, "상한 검증", None, {"blob": "x" * (audit_writer.SECURITY_DETAIL_LIMIT + 100)})

    detail = _rows()[0].detail
    assert detail["truncated"] is True
    assert "blob" not in detail


# --------------------------------------------------------------------------
# 3. 무인자 하위호환
# --------------------------------------------------------------------------
def test_legacy_call_without_structured_args_still_writes_null_columns(app):
    """구조화 인자 없이 부르는 기존 호출부는 그대로 저장되고 컬럼은 전부 NULL."""
    _log(app, "레거시 무인자 호출")

    rows = _rows()
    assert len(rows) == 1
    row = rows[0]
    assert row.message == "레거시 무인자 호출"
    assert row.action is None
    assert row.target_type is None
    assert row.target_id is None
    assert row.detail is None


def test_detached_writer_defaults_to_null_structured_columns(app):
    """독립 writer 도 구조화 인자를 안 주면 NULL 로 남는다(하위호환)."""
    assert audit_writer.write_security_log_detached("독립 레거시 호출") is True

    row = _rows()[0]
    assert (row.action, row.target_type, row.target_id, row.detail) == (None, None, None, None)


# --------------------------------------------------------------------------
# 4. 403 / CSRF 독립 기록의 구조화
# --------------------------------------------------------------------------
def test_api_403_records_structured_action_and_detail(client, app, policy_on):
    """주문 정책 403 이 ``ACCESS_DENIED`` + endpoint·reason detail 로 남는다."""
    viewer_id = _make_user("t8-deny-viewer", role="VIEWER")
    _login(client, viewer_id)
    oid = _make_order("COMPLETED")

    resp = client.post(f"/api/orders/{oid}/settlement/issue", json={"issued": True})
    assert resp.status_code == 403

    rows = _rows("ACCESS_DENIED")
    assert len(rows) == 1, [(r.action, r.message) for r in _rows()]
    assert rows[0].user_id == viewer_id
    assert rows[0].detail["endpoint"]
    assert rows[0].detail["reason"]


def test_csrf_block_records_structured_action_and_detail(client, app, guard_on):
    """CSRF 차단이 ``WRITE_BLOCKED`` + reason detail 로 남는다."""
    uid = _make_user("t8-csrf-user", role="STAFF", team="CS")
    _login(client, uid)
    oid = _make_order()

    resp = client.post(f"/api/orders/{oid}/call-log", json={"result": "connected"})
    assert resp.status_code == 403

    rows = _rows("WRITE_BLOCKED")
    assert len(rows) == 1, [(r.action, r.message) for r in _rows()]
    assert rows[0].detail["reason"] == "invalid_csrf_token"
    assert rows[0].detail["endpoint"]


def test_suppressed_count_lands_in_detail(app):
    """dedupe 억제 카운트는 message 뿐 아니라 detail 로도 질의 가능해야 한다."""
    clock = {"now": 100.0}
    original = audit_writer._monotonic
    audit_writer._monotonic = lambda: clock["now"]
    try:
        for _ in range(3):
            audit_writer.record_access_denied(
                "억제 detail 검증", user_id=None, ip="10.0.0.7", endpoint="ep",
                action="policy:X", structured_action="ACCESS_DENIED",
                detail={"endpoint": "ep", "reason": "X"})
        clock["now"] += 61
        audit_writer.record_access_denied(
            "억제 detail 검증", user_id=None, ip="10.0.0.7", endpoint="ep",
            action="policy:X", structured_action="ACCESS_DENIED",
            detail={"endpoint": "ep", "reason": "X"})
    finally:
        audit_writer._monotonic = original

    rows = _rows("ACCESS_DENIED")
    assert len(rows) == 2
    assert "suppressed" not in rows[0].detail
    assert rows[1].detail["suppressed"] == 2


def test_record_access_denied_does_not_mutate_caller_detail(app):
    """호출부가 넘긴 detail dict 은 절대 변형되지 않는다(공유 상수 오염 방지)."""
    payload = {"endpoint": "ep", "reason": "X"}
    audit_writer.record_access_denied(
        "무변형 검증", user_id=1, endpoint="ep", action="policy:X",
        structured_action="ACCESS_DENIED", detail=payload)
    audit_writer.reset_dedupe_cache()
    audit_writer.record_access_denied(
        "무변형 검증", user_id=1, endpoint="ep", action="policy:X",
        structured_action="ACCESS_DENIED", detail=payload)

    assert payload == {"endpoint": "ep", "reason": "X"}


# --------------------------------------------------------------------------
# 5. admin 감사 화면 — 필터 + detail 노출 이스케이프
# --------------------------------------------------------------------------
def _seed_admin(client):
    admin_id = _make_user("t8-audit-admin", role="ADMIN")
    _login(client, admin_id)
    return admin_id


def test_admin_audit_action_filter_narrows_rows(client, app):
    """action 필터가 다른 action 행을 실제로 제외한다."""
    _seed_admin(client)
    _log(app, "필터대상 행", None, action="USER_UPDATE", target_type="user", target_id=7)
    _log(app, "비대상 행", None, action="LOGIN_OK")

    resp = client.get("/security_logs?action=USER_UPDATE")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "필터대상 행" in body
    assert "비대상 행" not in body

    # 필터 없으면 둘 다 보인다(필터가 진짜 원인임을 고정).
    body_all = client.get("/security_logs").get_data(as_text=True)
    assert "필터대상 행" in body_all and "비대상 행" in body_all


def test_admin_audit_target_filter_narrows_rows(client, app):
    """target_type/target_id 필터가 대상별 조회를 만든다."""
    _seed_admin(client)
    _log(app, "대상 7 행", None, action="USER_UPDATE", target_type="user", target_id=7)
    _log(app, "대상 8 행", None, action="USER_UPDATE", target_type="user", target_id=8)

    body = client.get("/security_logs?target_type=user&target_id=7").get_data(as_text=True)
    assert "대상 7 행" in body
    assert "대상 8 행" not in body


def test_admin_audit_search_filter_still_works(client, app):
    """기존 ILIKE 자유 검색은 그대로 동작한다(회귀 가드)."""
    _seed_admin(client)
    _log(app, "검색되는 고유문구 ZZTOP", None)
    _log(app, "검색 안 되는 행", None)

    body = client.get("/security_logs?search=ZZTOP").get_data(as_text=True)
    assert "ZZTOP" in body
    assert "검색 안 되는 행" not in body


def test_admin_audit_escapes_detail_payload(client, app):
    """detail 에 스크립트가 저장돼 있어도 화면에는 실행 가능한 형태로 나가지 않는다."""
    _seed_admin(client)
    _log(app, "XSS 검증 행", None, action="USER_UPDATE",
               detail={"note": "<script>alert(1)</script>"})

    body = client.get("/security_logs?action=USER_UPDATE").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in body
    # 정보는 남되 escape 된 형태여야 한다.
    assert "alert(1)" in body


def test_admin_audit_pagination_preserves_filters(client, app):
    """페이지네이션 링크가 필터를 유지하고 2페이지가 정상 렌더된다(50행 초과 경로)."""
    _seed_admin(client)
    with app.app_context():
        for index in range(55):
            log_access(f"페이지네이션 행 {index:03d}", None,
                       action="USER_UPDATE", target_type="user", target_id=1)

    first = client.get("/security_logs?action=USER_UPDATE")
    assert first.status_code == 200
    body = first.get_data(as_text=True)
    assert "page=2" in body and "action=USER_UPDATE" in body

    second = client.get("/security_logs?action=USER_UPDATE&page=2")
    assert second.status_code == 200
    # 55행 중 51~55행이 2페이지에 온다(가장 오래된 = 마지막 페이지).
    assert "페이지네이션 행 000" in second.get_data(as_text=True)


def test_admin_audit_shows_actor_name(client, app):
    """행위자 컬럼이 빈 괄호가 아니라 실제 사용자명을 보여준다(구 템플릿 회귀)."""
    admin_id = _seed_admin(client)
    _log(app, "행위자 표기 검증", admin_id, action="USER_UPDATE")

    body = client.get("/security_logs?action=USER_UPDATE").get_data(as_text=True)
    assert "t8-audit-admin" in body


# --------------------------------------------------------------------------
# 6. 우선 호출부 action 태그
# --------------------------------------------------------------------------
def test_login_success_and_failure_actions(client, app):
    """로그인 성공/실패가 LOGIN_OK / LOGIN_FAIL 로 구분되고 대상은 없다."""
    _make_user("t8-login", role="STAFF")

    client.post("/login", data={"username": "t8-login", "password": "wrong-pw"})
    client.post("/login", data={"username": "t8-login", "password": _STRONG_PW})

    fails = _rows("LOGIN_FAIL")
    oks = _rows("LOGIN_OK")
    assert len(fails) == 1 and fails[0].detail["reason"] == "bad_password"
    assert len(oks) == 1 and oks[0].detail["username"] == "t8-login"
    assert (fails[0].target_type, oks[0].target_type) == (None, None)


def test_login_failure_for_unknown_username(client, app):
    """계정 없음 실패는 user_id NULL + username detail 로 추적 가능해야 한다."""
    _make_user("t8-exists", role="STAFF")

    client.post("/login", data={"username": "t8-ghost", "password": _STRONG_PW})

    fails = _rows("LOGIN_FAIL")
    assert len(fails) == 1
    assert fails[0].user_id is None
    assert fails[0].detail == {"reason": "unknown_username", "username": "t8-ghost"}


def test_register_bootstrap_action(client, app):
    """최초 관리자 부트스트랩이 USER_BOOTSTRAP + 대상 user 로 남는다."""
    assert db_session.query(User).count() == 0

    resp = client.post("/register", data={
        "username": "t8-first-admin",
        "name": "최초관리자",
        "team": "",
        "password": _STRONG_PW,
        "confirm_password": _STRONG_PW,
    })
    assert resp.status_code == 302

    created = db_session.query(User).filter_by(username="t8-first-admin").first()
    rows = _rows("USER_BOOTSTRAP")
    assert len(rows) == 1
    assert rows[0].target_type == "user" and rows[0].target_id == created.id
    assert rows[0].detail["role"] == "ADMIN"


def test_approve_user_action_and_changes(client, app):
    """가입 승인이 USER_APPROVE + role/team from→to detail 로 남는다."""
    admin_id = _make_user("t8-approve-admin", role="ADMIN")
    pending = User(
        username="t8-pending", password=generate_password_hash(_STRONG_PW),
        role="VIEWER", name="대기자", is_active=True, approval_status="PENDING",
    )
    db_session.add(pending)
    db_session.commit()
    pending_id = pending.id
    _login(client, admin_id)

    resp = client.post(f"/admin/users/approve/{pending_id}",
                       data={"role": "STAFF", "team": "CS"})
    assert resp.status_code == 302

    rows = _rows("USER_APPROVE")
    assert len(rows) == 1
    assert rows[0].target_id == pending_id
    assert rows[0].detail["changes"]["role"] == {"from": "VIEWER", "to": "STAFF"}


def test_handle_reset_request_action_and_status_change(client, app):
    """재설정 요청 처리가 RESET_REQUEST_HANDLE + status from→to 로 남는다."""
    from models import PasswordResetRequest

    admin_id = _make_user("t8-reset-admin", role="ADMIN")
    row = PasswordResetRequest(username_submitted="t8-someone", status="PENDING")
    db_session.add(row)
    db_session.commit()
    request_id = row.id
    _login(client, admin_id)

    resp = client.post(f"/admin/password-reset/{request_id}/handle", data={"action": "done"})
    assert resp.status_code == 302

    rows = _rows("RESET_REQUEST_HANDLE")
    assert len(rows) == 1
    assert rows[0].target_type == "password_reset_request"
    assert rows[0].target_id == request_id
    assert rows[0].detail["changes"]["status"]["to"] == "DONE"


def test_switch_user_action(client, app):
    """계정 전환이 IMPERSONATE + 전환 대상 target 으로 남는다."""
    admin_id = _make_user("t8-imp-admin", role="ADMIN")
    target_id = _make_user("t8-imp-target", role="STAFF", team="CS")
    _login(client, admin_id)

    resp = client.post(f"/switch-user/{target_id}")
    assert resp.status_code in (302, 303), resp.status_code

    rows = _rows("IMPERSONATE")
    assert len(rows) == 1
    assert rows[0].user_id == admin_id
    assert rows[0].target_type == "user" and rows[0].target_id == target_id
    assert rows[0].detail["target_username"] == "t8-imp-target"


# --------------------------------------------------------------------------
# SEC-LOG-TIME-00 — 감사 화면 정렬 인덱스
# --------------------------------------------------------------------------
def test_time_index_migration_contract():
    """seclog_time_00 은 accesslog_detail_00 위에 얹히고 models.py 와 컬럼 구성이 같다."""
    import ast
    from pathlib import Path

    from models import SecurityLog

    repo_root = Path(__file__).resolve().parents[2]
    path = repo_root / "migrations/versions/seclog_time_00_security_log_timestamp_index.py"
    body = path.read_text(encoding="utf-8")
    tree = ast.parse(body)
    funcs = {n.name: ast.unparse(n) for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef)}

    assert "import models" not in body and "from models" not in body  # 상수 동결 원칙
    assert "down_revision: Union[str, None] = 'accesslog_detail_00'" in body
    assert "create_index" in funcs["upgrade"] and "drop_index" in funcs["downgrade"]
    assert "'timestamp', 'id'" in funcs["upgrade"], "정렬 tie-break 컬럼(id)이 빠졌다"

    model_index = next(ix for ix in SecurityLog.__table__.indexes
                       if ix.name == "ix_security_logs_timestamp_id")
    assert [c.name for c in model_index.columns] == ["timestamp", "id"]


def test_audit_screen_orders_by_the_indexed_key():
    """감사 화면 정렬 키가 인덱스 구성과 같다 — 한쪽만 바뀌면 인덱스가 조용히 무용지물이 된다."""
    import ast
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    body = (repo_root / "foms/web/admin/audit.py").read_text(encoding="utf-8")
    tree = ast.parse(body)
    ordered = [
        ast.unparse(node) for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
        and node.func.attr == "order_by"
    ]
    assert any("SecurityLog.timestamp.desc()" in call and "SecurityLog.id.desc()" in call
               for call in ordered), ordered

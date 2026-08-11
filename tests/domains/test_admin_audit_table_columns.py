"""관리자 감사 표 컬럼 폭 조절 배선 계약 (2026-08-10 사용자 요청).

운영 화면에서 시간 칸이 세 줄로 접히고 문장 칸이 좁았다. 사람마다 보려는 축이 달라
(어떤 날은 문장, 어떤 날은 JSON) 고정 폭으로는 답이 없어 **헤더 경계 드래그**로 폭을
조절하게 했다. 여기서 고정하는 것:

1. 두 감사 화면(보안 로그·파일 열람 기록)이 **폭 조절 대상으로 표시**된다.
2. 런타임(공용 ColumnResizer)과 배선 스크립트·CSS 가 **실제로 로드**된다.
3. 폭은 CSS 가 갖는다 — 템플릿에 인라인 ``style="width: …%"`` 를 되살리지 않는다
   (인라인이 남으면 드래그 결과가 다음 렌더에서 덮인다).
4. 캐시 무효화 표식(``?v=``)이 붙어 있다 — SW staticCacheFirst 때문에 없으면 옛 파일이 산다.
"""

from __future__ import annotations

import pathlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SECURITY_PATH = "/security_logs"
_FILE_PATH = "/admin/file-access-logs"


def _admin(username: str) -> int:
    user = User(username=username, password=generate_password_hash("pw"), role="ADMIN",
                name=f"{username}-name", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _login(client, user_id: int) -> None:
    fresh = db_session.get(User, user_id)
    with client.session_transaction() as sess:
        sess["user_id"] = fresh.id
        sess["username"] = fresh.username
        sess["role"] = fresh.role


def _render(app, path: str, username: str) -> str:
    with app.app_context():
        admin_id = _admin(username)
        db_session.add(SecurityLog(
            user_id=admin_id, message="주문 #1 (홍길동) — 주문 저장: 전체 저장",
            action="ORDER_STRUCTURED_SAVED", target_type="order", target_id=1,
            detail={"mode": "full", "customer_name": "홍길동"},
        ))
        db_session.commit()
        client = app.test_client()
        _login(client, admin_id)
        resp = client.get(path)
        assert resp.status_code == 200, path
        return resp.get_data(as_text=True)


@pytest.mark.parametrize(
    ("path", "table_key", "username"),
    [
        (_SECURITY_PATH, "security-logs", "cols-sec-admin"),
        (_FILE_PATH, "file-access-logs", "cols-file-admin"),
    ],
)
def test_audit_tables_opt_in_to_column_resize(app, path, table_key, username):
    """두 감사 표가 폭 조절 대상으로 표시되고 배선 자산이 함께 로드된다."""
    body = _render(app, path, username)

    assert f'data-foms-resizable-table="{table_key}"' in body, "폭 조절 opt-in 표식 없음"
    assert "admin-audit-table" in body
    assert "css/contexts/admin/audit-tables.css" in body, "표 CSS 미로드"
    assert "js/runtime/column-resizer.js" in body, "공용 리사이저 런타임 미로드"
    assert "js/admin/audit-table-columns.js" in body, "배선 스크립트 미로드"


@pytest.mark.parametrize(
    ("path", "username"),
    [(_SECURITY_PATH, "cols-sec-inline"), (_FILE_PATH, "cols-file-inline")],
)
def test_column_widths_are_not_hardcoded_inline(app, path, username):
    """폭은 CSS 가 갖는다 — 인라인 width 가 살아나면 드래그 결과가 렌더마다 덮인다.

    검사 대상은 **표 헤더(``<th>``)** 다 — 레이아웃 컨테이너의 ``width: 100%`` 는 별개 관심사다.
    """
    body = _render(app, path, username)
    assert "<th style=" not in body, "표 컬럼 폭이 인라인으로 돌아왔다"


@pytest.mark.parametrize("asset", [
    "static/css/contexts/admin/audit-tables.css",
    "static/js/admin/audit-table-columns.js",
])
def test_assets_exist_on_disk(asset):
    """템플릿이 가리키는 자산이 실제로 있다(오타·미커밋 방지)."""
    assert (_REPO_ROOT / asset).is_file(), asset


@pytest.mark.parametrize(
    ("path", "username"),
    [(_SECURITY_PATH, "cols-sec-ver"), (_FILE_PATH, "cols-file-ver")],
)
def test_assets_carry_cache_busting_version(app, path, username):
    """``?v=`` 없이 나가면 Service Worker 캐시가 옛 파일을 계속 서빙한다(프로젝트 함정)."""
    body = _render(app, path, username)
    for asset in ("css/contexts/admin/audit-tables.css", "js/admin/audit-table-columns.js"):
        index = body.find(asset)
        assert index != -1, asset
        assert body[index + len(asset):index + len(asset) + 3].startswith("?v="), f"{asset}: ?v= 없음"


def test_time_cell_is_marked_for_single_line_rendering(app):
    """시간 칸은 한 줄로 — 세 줄로 접히면 표가 세로로 늘어난다(운영 실측 불만)."""
    body = _render(app, _SECURITY_PATH, "cols-time-admin")
    assert 'class="audit-cell-time"' in body

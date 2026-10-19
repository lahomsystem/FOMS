"""감사 화면 가독성 3차 (2026-08-11 운영 실측 후속 2건).

1. **행위 배지가 영문 코드였다** — ``ORDER_CHECKLIST_UPDATED`` 처럼 길어 두 줄로 접혔고,
   업무 담당자가 뜻을 알 수 없었다. 표시 SSOT(``ACTION_LABELS``)에 자주 쓰이는 16종이
   빠져 있어 라벨이 있어도 코드가 그대로 나왔다.
2. **부가정보 JSON 이 행 높이를 153px 로 만들었다** — 한 화면에 6행. 기본은 접고 펼치면
   전체가 보이게 한다(기록을 지우는 게 아니라 접는 것).

여기서 고정하는 것: 라벨 커버리지(기록되는 코드에 라벨이 있다)·원문 코드 보존(title)·
접힘 기본값·펼침 시 내용 보존.
"""

from __future__ import annotations

import pathlib
import re

from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.audit_message_display import ACTION_LABELS, action_label
from models import AccessLog, SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_SECURITY_PATH = "/security_logs"
_FILE_PATH = "/admin/file-access-logs"


def _admin(username: str) -> int:
    user = User(username=username, password=generate_password_hash("pw"), role="ADMIN",
                name=f"{username}-name", is_active=True)
    db_session.add(user)
    db_session.commit()
    return user.id


def _client(app, admin_id: int):
    client = app.test_client()
    fresh = db_session.get(User, admin_id)
    with client.session_transaction() as sess:
        sess["user_id"] = fresh.id
        sess["username"] = fresh.username
        sess["role"] = fresh.role
    return client


def _emitted_action_codes() -> set[str]:
    """``action="CODE"`` 로 실제 기록되는 코드를 소스에서 모은다."""
    codes: set[str] = set()
    for path in (_REPO_ROOT / "foms").rglob("*.py"):
        text = path.read_text(encoding="utf-8", errors="replace")
        codes.update(re.findall(r"""action=['"]([A-Z][A-Z0-9_]+)['"]""", text))
    return codes


def test_every_emitted_action_has_business_label():
    """기록되는 행위 코드에는 업무 라벨이 있다 — 없으면 화면에 영문 코드가 그대로 뜬다."""
    missing = sorted(_emitted_action_codes() - set(ACTION_LABELS))
    assert not missing, f"라벨 없는 행위 코드: {missing}"


def test_file_access_actions_are_labeled():
    """파일 열람 3종도 라벨을 갖는다(두 화면이 같은 사전을 쓴다)."""
    for code in ("FILE_VIEW", "FILE_DOWNLOAD", "FILE_PRESIGNED"):
        assert action_label(code) != code, code


def test_unknown_action_still_shows_raw_code():
    """사전에 없는 코드는 감추지 않고 코드 그대로 보여준다(감사 기록 은닉 금지)."""
    assert action_label("SOME_FUTURE_ACTION") == "SOME_FUTURE_ACTION"


def test_security_badge_shows_label_and_keeps_code_in_title(app):
    """보안 로그 배지는 한글 라벨, 원문 코드는 ``title`` 로 남는다(필터 값이 코드다)."""
    with app.app_context():
        admin_id = _admin("audit3-badge-admin")
        db_session.add(SecurityLog(
            user_id=admin_id, message="주문 #1 (홍길동) — 체크리스트 변경",
            action="ORDER_CHECKLIST_UPDATED", target_type="order", target_id=1,
            detail={"field": "regional_blueprint_sent", "after": True},
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_SECURITY_PATH).get_data(as_text=True)

    assert ">체크리스트 변경</span>" in body, "업무 라벨이 배지에 없다"
    assert 'title="ORDER_CHECKLIST_UPDATED"' in body, "원문 코드가 title 에서 사라졌다"


def test_file_badge_shows_label_and_keeps_code_in_title(app):
    """파일 열람 화면 배지도 라벨 + 코드 title 규약을 따른다."""
    with app.app_context():
        admin_id = _admin("audit3-file-badge-admin")
        db_session.add(AccessLog(
            user_id=admin_id, action="FILE_VIEW", ip_address="127.0.0.1",
            user_agent="curl/8.4.0",
            detail={"storage_key": "orders/1/attachments/a.png", "order_id": 1},
            additional_data='{"storage_key": "orders/1/attachments/a.png", "order_id": 1}',
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_FILE_PATH).get_data(as_text=True)

    assert ">파일 열람</span>" in body
    assert 'title="FILE_VIEW"' in body


def test_detail_is_collapsed_by_default_but_content_survives(app):
    """부가정보는 기본 접힘이고, 접힌 상태에서도 내용은 문서에 남아 있다."""
    with app.app_context():
        admin_id = _admin("audit3-collapse-admin")
        db_session.add(SecurityLog(
            user_id=admin_id, message="주문 #2 저장", action="ORDER_STRUCTURED_SAVED",
            target_type="order", target_id=2,
            detail={"customer_name": "이가언", "mode": "full", "order_type": "주문"},
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_SECURITY_PATH).get_data(as_text=True)

    assert '<details class="audit-detail-toggle">' in body, "접이식으로 감싸지 않았다"
    assert "open" not in body.split('audit-detail-toggle"', 1)[1][:40], "기본이 펼침이다"
    assert "부가정보 3개" in body, "키 개수 요약이 없다"
    assert "이가언" in body, "접었더니 내용이 사라졌다(펼칠 게 없다)"


def test_collapsed_summary_stays_single_line():
    """접힘 줄이 두 줄로 접히면 행 높이를 줄인 의미가 없다."""
    css = (_REPO_ROOT / "static" / "css" / "contexts" / "admin" / "audit-tables.css").read_text(
        encoding="utf-8")
    block = css.split(".admin-audit-table .audit-detail-toggle > summary", 1)[1].split("}", 1)[0]
    assert "white-space: nowrap" in block
    assert "cursor: pointer" in block

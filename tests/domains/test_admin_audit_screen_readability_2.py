"""감사 화면 가독성 2차 수정 계약 (2026-08-11 운영 실측 4건).

운영 화면을 직접 보고 잡은 것:

1. **시간 끝자리 잘림** — ``2026-08-11 11:36:1`` 로 초의 마지막 글자가 사라졌다.
   %폭은 화면이 좁아지면 같이 줄어드는데 내용 길이는 고정이라 구조적으로 잘린다 → rem 고정.
2. **행위 배지 잘림** — ``ORDER_CHECKLIST_UPDATED`` 가 잘려 옆 칸 글자와 붙어 보였다 → 줄바꿈 허용.
3. **부가정보 한글이 ``\\uc774\\uac00\\uc5b8``** — Jinja ``tojson`` 이 ensure_ascii=True 라
   사람이 읽을 수 없었다 → 서버가 ensure_ascii=False 로 만든 문자열을 자동 escape 로 출력.
4. **보안 로그에 기간 필터 없음** — 2만 건을 날짜로 좁힐 수 없었다 → 파일 열람 화면과 같은
   KST 경계 규약으로 추가.

여기서 고정하는 것은 "다시 잘리지 않는다·다시 이스케이프로 보이지 않는다·기간이 실제로
걸린다·UA 원문이 사라지지 않는다" 네 가지다.
"""

from __future__ import annotations

import datetime
import pathlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.web.admin.audit import summarize_user_agent
from models import AccessLog, SecurityLog, User

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
_CSS = _REPO_ROOT / "static" / "css" / "contexts" / "admin" / "audit-tables.css"
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


# --- 1) 시간 칸 고정 폭 -------------------------------------------------------
def test_time_column_width_is_content_sized_not_percent():
    """시간 칸 폭은 rem 고정이다 — %면 화면이 좁아질 때 초 자리가 잘린다."""
    css = _CSS.read_text(encoding="utf-8")
    assert "width: 10rem;" in css, "시간 칸 고정 폭(rem)이 없다"
    for selector in ("--security > thead > tr > th:nth-child(1)",
                     "--file > thead > tr > th:nth-child(1)"):
        assert selector not in css, f"시간 칸에 %폭이 되살아났다: {selector}"


# --- 2) 배지 줄바꿈 -----------------------------------------------------------
def test_action_badge_wraps_instead_of_clipping():
    """긴 action 배지는 칸 안에서 접힌다(잘려서 옆 칸과 붙지 않는다)."""
    css = _CSS.read_text(encoding="utf-8")
    assert ".admin-audit-table > tbody > tr > td .badge" in css
    block = css.split(".admin-audit-table > tbody > tr > td .badge", 1)[1].split("}", 1)[0]
    assert "white-space: normal" in block
    assert "word-break: break-all" in block


# --- 3) 부가정보 한글 ---------------------------------------------------------
def test_detail_json_renders_hangul_not_unicode_escapes(app):
    """부가정보 JSON 의 한글이 화면에 그대로 보인다(``\\uXXXX`` 아님)."""
    with app.app_context():
        admin_id = _admin("audit2-detail-admin")
        db_session.add(SecurityLog(
            user_id=admin_id, message="주문 #1 (이가언) — 주문 저장",
            action="ORDER_STRUCTURED_SAVED", target_type="order", target_id=1,
            detail={"customer_name": "이가언", "field": "regional_blueprint_sent"},
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_SECURITY_PATH).get_data(as_text=True)

    assert "이가언" in body, "한글이 그대로 표시되지 않는다"
    assert "\\uc774" not in body, "유니코드 이스케이프가 화면에 남아 있다"


def test_detail_json_still_escapes_html(app):
    """한글을 살리면서도 HTML 은 escape 된다 — 저장형 XSS 회귀 방지."""
    with app.app_context():
        admin_id = _admin("audit2-xss-admin")
        db_session.add(SecurityLog(
            user_id=admin_id, message="주문 저장", action="ORDER_FIELD_UPDATED",
            target_type="order", target_id=2,
            detail={"after": "<script>alert('x')</script>", "customer_name": "홍길동"},
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_SECURITY_PATH).get_data(as_text=True)

    assert "<script>alert(" not in body, "스크립트 태그가 그대로 출력됐다"
    assert "&lt;script&gt;" in body


# --- 4) 보안 로그 기간 필터 ---------------------------------------------------
def test_security_log_date_filter_bounds_by_kst_day(app):
    """시작일·종료일이 KST 하루 경계로 걸린다(종료일 당일이 포함된다)."""
    with app.app_context():
        admin_id = _admin("audit2-date-admin")
        # KST 2026-08-09 08:00 → UTC 2026-08-08 23:00 (경계를 UTC 로 비교하면 전날로 샌다)
        db_session.add(SecurityLog(user_id=admin_id, message="이른 아침 기록",
                                   action="LOGIN_OK", timestamp=datetime.datetime(2026, 8, 8, 23, 0)))
        db_session.add(SecurityLog(user_id=admin_id, message="범위 밖 기록",
                                   action="LOGIN_OK", timestamp=datetime.datetime(2026, 8, 10, 5, 0)))
        db_session.commit()
        client = _client(app, admin_id)

        same_day = client.get(f"{_SECURITY_PATH}?date_from=2026-08-09&date_to=2026-08-09")
        body = same_day.get_data(as_text=True)

    assert same_day.status_code == 200
    assert "이른 아침 기록" in body, "KST 당일 기록이 범위에서 빠졌다"
    assert "범위 밖 기록" not in body, "범위 밖 기록이 섞였다"


def test_security_log_date_filter_survives_pagination_links(app):
    """페이지 이동 링크가 기간 필터를 잃지 않는다."""
    with app.app_context():
        admin_id = _admin("audit2-page-admin")
        for index in range(55):
            db_session.add(SecurityLog(user_id=admin_id, message=f"기록 {index}",
                                       action="LOGIN_OK",
                                       timestamp=datetime.datetime(2026, 8, 9, 3, index % 60)))
        db_session.commit()
        body = _client(app, admin_id).get(
            f"{_SECURITY_PATH}?date_from=2026-08-09&date_to=2026-08-09"
        ).get_data(as_text=True)

    assert "date_from=2026-08-09" in body, "다음/이전 링크에 기간이 실리지 않았다"
    assert "date_to=2026-08-09" in body


@pytest.mark.parametrize("bad", ["2026-13-40", "어제", "2026/08/09"])
def test_security_log_rejects_bad_date_without_error(app, bad):
    """형식이 틀린 날짜는 필터를 걸지 않고 화면이 살아 있다(500 금지)."""
    with app.app_context():
        admin_id = _admin(f"audit2-bad-{abs(hash(bad)) % 10000}")
        resp = _client(app, admin_id).get(f"{_SECURITY_PATH}?date_from={bad}")

    assert resp.status_code == 200


# --- 5) UA 요약 ---------------------------------------------------------------
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/150.0.0.0 Safari/537.36", "Chrome 150 · Windows"),
        ("Mozilla/5.0 (Linux; Android 10; K) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/150.0.0.0 Mobile Safari/537.36", "Chrome 150 · Android"),
        ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
         "Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0", "Edge 150 · Windows"),
        ("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 "
         "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1", "Safari 17 · iPhone"),
        ("", ""),
        (None, ""),
    ],
)
def test_user_agent_summary(raw, expected):
    """UA 요약은 브라우저·OS 두 축만 남긴다."""
    assert summarize_user_agent(raw) == expected


def test_unknown_user_agent_is_not_hidden():
    """알 수 없는 UA 도 감춰지지 않는다(감사 기록 은닉 금지)."""
    assert summarize_user_agent("curl/8.4.0").startswith("curl/8.4.0")


def test_file_access_screen_keeps_full_user_agent_in_title(app):
    """화면은 요약을 보여주되 원문을 ``title`` 로 보존한다."""
    full_ua = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
               "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36")
    with app.app_context():
        admin_id = _admin("audit2-ua-admin")
        db_session.add(AccessLog(
            user_id=admin_id, action="FILE_VIEW", ip_address="127.0.0.1", user_agent=full_ua,
            detail={"storage_key": "orders/1/attachments/a.png", "order_id": 1},
            additional_data='{"storage_key": "orders/1/attachments/a.png", "order_id": 1}',
        ))
        db_session.commit()
        body = _client(app, admin_id).get(_FILE_PATH).get_data(as_text=True)

    assert "Chrome 150 · Windows" in body, "요약이 표시되지 않는다"
    assert f'title="{full_ua}"' in body, "UA 원문이 title 에서 사라졌다"

"""FOMS 공지사항 관리자 화면(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5 · §6 B).

- 권한: ADMIN · MANAGER 만 200, 직원은 되돌려 보낸다(기존 ``role_required`` — 302), 로그인 없으면 로그인 화면.
- 쓰기 화면: 받는 쪽 칩(본사 전체 · 협력사 전체) · 받는 사람 수 · 보이는 방식 두 개 · 게시 시작 · 끝 · 고정 ·
  휴대폰 미리보기(본사만 · 협력사만 · 본사 + 협력사) 훅이 있다. 스크립트는 asset_url(``?v=``)로 싣는다.
- 고치기 화면은 지금 값을 ``data-notice`` 로 싣고, 지운 공지 · 없는 공지는 404.
- 인라인 style 없음 · 새 JS 300줄 · 파이썬 500줄 이하.
"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from models import Notice, User

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = [ROOT / "templates/admin/notices" / name for name in ("list.html", "form.html", "status.html")]
SCRIPTS = [ROOT / "static/js/admin" / name for name in ("notices-list.js", "notices-form.js", "notices-status.js")]
CSS = ROOT / "static/css/contexts/admin/notices.css"
PY_MODULE = ROOT / "foms/web/admin/notices.py"


def _login(client, role: str) -> int:
    user = User(username=f"notice-admin-{role.lower()}", password=generate_password_hash("pw"), role=role,
                team="CS", name=f"합성 {role}", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = user.id, user.username, role
    return user.id


def _notice(**kwargs) -> int:
    values = {"title": "11월 연휴 배송 <안내>", "body": "내용", "audience_staff_all": False,
              "audience_staff_teams": ["SALES"], "audience_partner_all": False, "audience_partner_org_ids": [7],
              "display_mode": "POPUP", "pinned": True, "created_by_name": "합성 관리자"}
    values.update(kwargs)
    notice = Notice(**values)
    db_session.add(notice)
    db_session.commit()
    return notice.id


def _data_attr(page: str, name: str) -> dict:
    match = re.search(rf'{name}="([^"]*)"', page)
    assert match, f"{name} 속성이 없다"
    return json.loads(html.unescape(match.group(1)))


# ── 권한 ─────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("role", ["ADMIN", "MANAGER"])
def test_admin_and_manager_get_list_and_new_pages(client, role):
    _login(client, role)
    for path in ("/admin/notices", "/admin/notices/new"):
        resp = client.get(path)
        assert resp.status_code == 200, path
        assert "공지" in resp.get_data(as_text=True)


def test_staff_is_turned_away_and_anonymous_goes_to_login(client):
    anon = client.get("/admin/notices")
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]

    _login(client, "STAFF")
    for path in ("/admin/notices", "/admin/notices/new"):
        resp = client.get(path)
        assert resp.status_code in (302, 403), path
        assert "/admin/notices" not in resp.headers.get("Location", ""), path


# ── 쓰기 화면 훅 ─────────────────────────────────────────────────────────
def test_form_page_has_chip_count_mode_period_and_preview_hooks(client):
    _login(client, "ADMIN")
    page = client.get("/admin/notices/new").get_data(as_text=True)
    for hook in ('data-notice-form', 'data-mode="new"', 'data-api-url="/api/admin/notices"',
                 'data-options-url="/api/admin/notices/audience-options"',
                 'data-audience-chips="staff"', 'data-audience-chips="partner"',
                 'data-audience-chip="staff-all"', 'data-audience-chip="partner-all"', 'data-audience-count',
                 'value="POPUP"', 'value="LIST"', 'data-notice-field="pinned"',
                 'data-notice-field="starts_at"', 'data-notice-field="ends_at"',
                 'data-preview-phone', 'data-preview-side="staff"', 'data-preview-side="partner"',
                 'data-preview-side="both"', 'data-preview-popup', 'data-preview-list'):
        assert hook in page, hook
    assert page.count('type="datetime-local"') == 2
    assert re.search(r'/static/js/admin/notices-form\.js\?v=[0-9a-f]{12}', page)
    assert re.search(r'/static/css/contexts/admin/notices\.css\?v=[0-9a-f]{12}', page)
    assert _data_attr(page, "data-notice") == {}


def test_list_and_status_pages_load_their_scripts(client):
    _login(client, "ADMIN")
    notice_id = _notice()
    page = client.get("/admin/notices").get_data(as_text=True)
    assert "data-notice-list" in page and 'href="/admin/notices/new"' in page
    assert re.search(r'/static/js/admin/notices-list\.js\?v=[0-9a-f]{12}', page)

    status = client.get(f"/admin/notices/{notice_id}/status")
    assert status.status_code == 200
    body = status.get_data(as_text=True)
    assert f'data-status-url="/api/admin/notices/{notice_id}/status"' in body
    assert 'data-status-tab="staff"' in body and 'data-status-tab="partner"' in body
    assert re.search(r'data-status-only-pending\s+checked', body), "'안 한 사람만' 은 기본으로 켠다"
    assert "<progress" in body and "11월 연휴 배송 &lt;안내&gt;" in body
    assert re.search(r'/static/js/admin/notices-status\.js\?v=[0-9a-f]{12}', body)


def test_edit_page_carries_current_values_and_hides_deleted(client):
    _login(client, "MANAGER")
    notice_id = _notice(starts_at=now_utc_naive().replace(hour=0, minute=0, second=0, microsecond=0))
    page = client.get(f"/admin/notices/{notice_id}/edit").get_data(as_text=True)
    state = _data_attr(page, "data-notice")
    assert state["id"] == notice_id and state["title"] == "11월 연휴 배송 <안내>"
    assert state["audience"] == {"staff_all": False, "staff_teams": ["SALES"], "partner_all": False,
                                 "partner_org_ids": [7]}
    assert state["display_mode"] == "POPUP" and state["pinned"] is True
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T09:00", state["starts_at"]), "UTC 0시 = 한국 9시"
    assert state["ends_at"] == ""
    assert 'data-mode="edit"' in page

    gone = _notice(title="지운 공지", deleted_at=now_utc_naive())
    for path in (f"/admin/notices/{gone}/edit", f"/admin/notices/{gone}/status", "/admin/notices/999999/edit"):
        assert client.get(path).status_code == 404, path


def test_admin_home_has_notice_button_apart_from_urgent(client):
    _login(client, "ADMIN")
    page = client.get("/admin").get_data(as_text=True)
    match = re.search(r'<a href="/admin/notices"[^>]*>', page)
    assert match, "관리자 첫 화면에 공지사항 단추"
    assert "foms-notice-entry-btn" in match.group(0) and "danger" not in match.group(0)
    assert "공지/알림 발송" in page


# ── 규약 ─────────────────────────────────────────────────────────────────
def test_no_inline_style_and_size_limits():
    entry = [line for line in (ROOT / "templates/admin/admin.html").read_text(encoding="utf-8").splitlines()
             if "notices_admin." in line]
    assert entry and all("style=" not in line for line in entry)
    for path in TEMPLATES:
        text = path.read_text(encoding="utf-8")
        assert "style=" not in text, path
        assert "<script>" not in text, f"{path}: 인라인 스크립트 없이 파일로 싣는다"
    for path in SCRIPTS:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) <= 300, path
        assert "style=" not in text and ".style." not in text, path
        assert not re.search(r"\.innerHTML\s*=", text), f"{path}: 글은 textContent 로만"
        assert "jQuery" not in text and "$(" not in text, path
        assert "data.success" in text and "catch (err)" in text, path
    assert len(PY_MODULE.read_text(encoding="utf-8").splitlines()) <= 500
    css = CSS.read_text(encoding="utf-8")
    assert "#e8f4fd" in css and "#0b5a8f" in css, "협력사 = 하늘색"
    assert "--foms-color-brand-" in css, "본사 = FOMS 보라 토큰"

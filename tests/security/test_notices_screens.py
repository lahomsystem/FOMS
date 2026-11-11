"""FOMS 공지사항 받는 사람 화면(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §5 · §6 C).

본사 /notices(본사 직원만, 협력사는 돌려보냄) · 협력사 /partner/notices · 본사 공용 레이아웃의 공지 창 훅 ·
협력사 공지 창이 두 출처(기존 PARTNER_NOTICE · 새 공지)를 다 다룸 · 인라인 style 없음.
대조군: 다른 협력사 공지 · 본사만 공지(협력사 목록에 안 보임) · 협력사만 공지(본사 목록에 안 보임) · 지운 공지.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from html import unescape
from pathlib import Path

from db import db_session
from foms.services.partners.notices import create_partner_notice
from models import Notice, User
from tests.security.partner_fixtures import _client, world  # noqa: F401 — pytest fixture 재노출

ROOT = Path(__file__).resolve().parents[2]


def _notice(title: str, **kw) -> int:
    row = Notice(title=title, body=kw.pop("body", f"{title} 본문"), created_by_name="라홈 본사", **kw)
    db_session.add(row)
    db_session.commit()
    return row.id


def _page(app, user_id: int, path: str):
    return _client(app, db_session.get(User, user_id)).get(path)


def test_staff_notice_list_shows_only_staff_notices(app, world):
    _notice("본사 전체 공지", audience_staff_all=True, pinned=True)
    _notice("CS 팀 공지", audience_staff_teams=["CS"], display_mode="POPUP")
    _notice("영업 팀만", audience_staff_teams=["SALES"])
    _notice("협력사만 공지", audience_partner_all=True)
    _notice("지운 공지", audience_staff_all=True, deleted_at=datetime(2026, 11, 1))

    resp = _page(app, world["staff"], "/notices")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "본사 전체 공지" in html and "CS 팀 공지" in html
    assert "영업 팀만" not in html and "협력사만 공지" not in html and "지운 공지" not in html
    assert html.index("본사 전체 공지") < html.index("CS 팀 공지")  # 고정 먼저
    assert "data-foms-notice-list" in html and "/api/notices/0/read" in html
    assert "is-unread" in html and "고정" in html

    unread = _page(app, world["staff"], "/notices?filter=unread").get_data(as_text=True)
    assert "본사 전체 공지" in unread and "is-active" in unread


def test_staff_notice_list_uses_mobile_shell_with_back(app, world, monkeypatch):
    """모바일 v2 코호트면 /notices 도 주문 수정처럼 셸(뒤로 가기 줄 · 아래 탭)을 쓴다 — PC 메뉴줄만 남아 ERP 로 못 돌아가던 결함(11-11).

    대조군: 코호트가 꺼진 사용자는 셸 없이 예전 모양 그대로.
    """
    _notice("본사 전체 공지", audience_staff_all=True)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(world["staff"]))
    html = _page(app, world["staff"], "/notices").get_data(as_text=True)
    assert "erp-mobile-v2-layout" in html
    assert "data-foms-shell-back" in html and 'data-foms-shell-back-href="/erp/dashboard"' in html
    assert re.search(r'foms-shell-title">\s*공지사항\s*<', html)
    assert "foms-notice-wrap--shell" in html and "본사 전체 공지" in html
    # 셸 틀만 붙고 꾸밈 CSS 가 빠지면 위 단추가 검은 네모로 나온다(11-11 운영 실화면) — 셸 CSS 묶음까지 실려야 한다.
    assert "foms-mobile-surfaces.css" in html and "foms-mobile-v2-critical-css" in html

    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "0")
    plain = _page(app, world["staff"], "/notices").get_data(as_text=True)
    assert "erp-mobile-v2-layout" not in plain and "data-foms-shell-back" not in plain
    assert "foms-mobile-surfaces.css" not in plain
    assert "본사 전체 공지" in plain


def test_popup_notice_chip_turns_to_done_after_ack(app, world):
    """확인 창 공지는 확인하기 전 '확인 필요', 확인한 뒤 '확인함'(스테이징 실화면 2026-11-02 — 확인 뒤에도 '확인 필요'가 남았다)."""
    from foms.services.notices.service import ack_notice

    nid = _notice("확인 창 공지", audience_staff_all=True, display_mode="POPUP")
    before = _page(app, world["staff"], "/notices").get_data(as_text=True)
    assert "확인 필요" in before and "확인함" not in before
    assert ack_notice(db_session, db_session.get(User, world["staff"]), nid)
    db_session.commit()
    after = _page(app, world["staff"], "/notices").get_data(as_text=True)
    assert "확인함" in after and "확인 필요" not in after


def test_partner_is_sent_away_from_staff_list(app, world):
    resp = _page(app, world["partner_a"], "/notices")
    assert resp.status_code == 302
    assert "/partner" in resp.headers["Location"]
    anon = app.test_client().get("/notices")
    assert anon.status_code == 302 and "/login" in anon.headers["Location"]


def test_partner_notice_list_shows_only_our_company(app, world):
    _notice("협력사 전체 공지", audience_partner_all=True)
    _notice("가나가구만", audience_partner_org_ids=[world["org_a"]])
    _notice("다라가구만", audience_partner_org_ids=[world["org_b"]])
    _notice("본사만 공지", audience_staff_all=True)

    resp = _page(app, world["partner_a"], "/partner/notices")
    assert resp.status_code == 200
    html = resp.get_data(as_text=True)
    assert "협력사 전체 공지" in html and "가나가구만" in html
    assert "다라가구만" not in html and "본사만 공지" not in html
    assert "foms-notice-popup.js" in html and "foms-notice.css" in html
    assert 'href="/partner/notices"' in html  # 머리줄 · 더보기 링크
    assert "foms-notice-wrap--shell" in html  # 폰 위 줄이 제목이라 큰 제목은 폰에서 숨긴다(11-11)
    staff = _page(app, world["staff"], "/partner/notices")
    assert staff.status_code in (302, 403)


def test_partner_popup_queues_old_partner_notice_then_new_notice(app, world):
    create_partner_notice(db_session, title="기존 협력사 공지", message="가", actor_user_id=None,
                          actor_name="라홈 본사", apply=True)
    db_session.commit()
    _notice("새 확인 공지", audience_partner_all=True, display_mode="POPUP")
    _notice("목록만 공지", audience_partner_all=True, display_mode="LIST")

    html = _page(app, world["partner_a"], "/partner").get_data(as_text=True)
    assert "data-pp-notice" in html and "partner-notice.js" in html
    raw = re.search(r'data-pp-notice-queue="([^"]*)"', html).group(1)
    queue = json.loads(unescape(raw))
    assert [(n["source"], n["title"]) for n in queue] == [("partner", "기존 협력사 공지"), ("notice", "새 확인 공지")]
    assert "기존 협력사 공지" in html and "1 / 2" in html
    assert "/api/partner/notices/0/ack" in html and "/api/notices/0/ack" in html


def test_staff_layout_hooks_notice_popup(app, world):
    html = _page(app, world["staff"], "/notices").get_data(as_text=True)
    assert "data-foms-notice-popup" in html and "foms-notice-popup.js" in html
    assert "/api/notices" in html and 'href="/notices"' in html and "data-foms-notice-unread" in html
    scripts = (ROOT / "templates/partials/shared/layout_scripts.html").read_text(encoding="utf-8")
    assert "partials/shared/notice_popup.html" in scripts
    popup = (ROOT / "templates/partials/shared/notice_popup.html").read_text(encoding="utf-8")
    assert "not current_user.partner_org_id" in popup  # 로그인 전 · 협력사 계정은 싣지 않는다


def test_popup_scripts_close_only_with_ok_and_handle_both_sources() -> None:
    js = (ROOT / "static/js/foms/foms-notice-popup.js").read_text(encoding="utf-8")
    assert "Escape" in js and "preventDefault" in js and "data.success" in js and "catch" in js
    assert "data.data.pending" in js and "FOMSUrgentAlert" not in js  # 서버가 정한 창 차례 · 긴급 빨간 창과 섞지 않는다
    pjs = (ROOT / "static/js/partner/partner-notice.js").read_text(encoding="utf-8")
    assert "data-pp-notice-new-url" in pjs and "data-pp-notice-queue" in pjs and "source" in pjs
    assert len(js.splitlines()) <= 300 and len(pjs.splitlines()) <= 300


def test_popup_scripts_skip_ended_notice_and_trap_focus_on_document() -> None:
    """확인이 4xx(404 — 지움 · 기간 끝 · 대상 바뀜)면 다음으로 넘어가고, 오류로 남기는 것은 네트워크 · 5xx 뿐.
    초점 가두기는 document 잡기 단계 focusin · keydown 이고 창이 닫히면 푼다(긴급 창과 같은 틀)."""
    for rel in ("static/js/foms/foms-notice-popup.js", "static/js/partner/partner-notice.js"):
        js = (ROOT / rel).read_text(encoding="utf-8")
        assert "resp.status >= 400 && resp.status < 500" in js, rel
        for kind in ("focusin", "keydown"):
            assert f"document.addEventListener('{kind}'" in js and f"document.removeEventListener('{kind}'" in js, rel
        assert "root.addEventListener('keydown'" not in js, rel  # 창 안에서만 듣던 옛 가두기
    popup = (ROOT / "templates/partials/shared/notice_popup.html").read_text(encoding="utf-8")
    assert "view='popup'" in popup


def test_notice_popup_sits_above_drawing_notes_below_urgent() -> None:
    def z(rel: str, selector: str) -> int:
        css = (ROOT / rel).read_text(encoding="utf-8")
        block = css[css.index(selector + " {"):]
        return int(re.search(r"z-index:\s*(\d+)", block[:block.index("}")]).group(1))

    notice = z("static/css/components/foms-notice.css", ".foms-notice-popup")
    notes = z("static/css/components/foms-drawing-alert.css", ".foms-drawing-notices")
    urgent = z("static/css/components/foms-urgent-alert.css", ".foms-urgent-alert")
    assert notes < notice < urgent


def test_notice_screens_have_no_inline_style() -> None:
    for rel in ("templates/notices/list.html", "templates/notices/_items.html",
                "templates/partials/shared/notice_popup.html", "templates/partner/notices.html",
                "templates/partner/partials/notice_modal.html"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "<style" not in text, rel
        assert "data-bs-dismiss" not in text, rel

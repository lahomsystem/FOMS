"""승인 대기 'AI 할 일 제안' 칸 — 점검 2차 고치기(w1-01 · 03 · 15 · 16 · 17 · 18) node · 가짜 DOM 시험.

- 이미 처리된 제안을 주소로 열면 결과(누가 · 언제)만 — 결정 단추 · 거절 칩 · 주문 바뀜 경고 없음(w1-03).
- 옆 창 결정 단추 한 줄 · '2주 승인율'(w1-15 · 16). 볼 수 없는 제안 주소는 쉬운 글(빨강 아님 — w1-18).
- '나중에'로 접은 AI 제안은 '나중에 볼 것' 수에 들고 그 줄에서 보인다(w1-17).
- '다시 확인' · '판 · 기록' 보기의 AI 직원 수가 승인 대기와 같다(w1-01).
재료(실제로 그린 화면 · 카드 · 길)는 ``test_brain_ds_inbox_erp`` 와 같이 쓴다. 합성 자료만.
"""

from __future__ import annotations

import re

import pytest

from tests.domains.test_brain_ds_inbox_erp import (  # noqa: F401 — 시험 재료(고정물) 같이 씀
    BASE_SCRIPTS, CARDS, INBOX, NODE, STATE, _detail, _get, _ok, _on, _routes, _scripts, page, people, run_node,
)

# ── 점검 2차 고치기(w1-03 · w1-15 · w1-16 · w1-17 · w1-18) ─────────────────────────────────────────────
@NODE
def test_decided_proposal_from_an_address_shows_who_when_and_no_buttons(page):
    """폰 알림 주소(?proposal=)로 이미 처리된 제안을 열면 결과만 — 결정 단추 · 거절 칩 · 주문 바뀜 경고가 없다(w1-03)."""
    done = _detail(CARDS[0], status="rejected", base_changed=True,
                   done={"status": "rejected", "label": "거절했어요 — 날짜가 틀림", "by": "합성 관리자", "at": "2030-01-02 10:00"})
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11", "replies": [_ok(done)]})
    body = """
      await api.click(api.q('[data-erp-card="11"] [data-erp-act="open"]'));
      const aside = api.q('[data-erp-aside]');
      return { text: api.text(aside), buttons: api.qa('[data-erp-aside] button').filter(api.shown).map(api.text),
               done: !!api.q('[data-erp-done="rejected"]') };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["done"] is True and "이미 처리된 제안이에요거절했어요 — 날짜가 틀림 · 합성 관리자 · 2030-01-02 10:00" in got["text"]
    assert got["buttons"] == [""]  # 닫기만
    assert "주문이 바뀌었어요" not in got["text"] and "거절 — 까닭" not in got["text"] and "승인하면 차례로" not in got["text"]


@NODE
def test_open_proposal_buttons_share_one_row_and_the_rate_reads_two_weeks(page):
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11", "replies": [_ok(_detail(CARDS[0]))]})
    body = """
      await api.click(api.q('[data-erp-card="11"] [data-erp-act="open"]'));
      const row = api.q('[data-erp-aside] .fb-erp-decide');
      return { row: row ? Array.from(row.childNodes).filter(api.shown).map(api.text) : null, text: api.text(api.q('[data-erp-aside]')) };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["row"] == ["승인", "고쳐서 승인", "나중에"] and "2주 승인율" in got["text"] and "14일" not in got["text"]


@NODE
def test_unreadable_proposal_address_says_it_plainly_not_in_red(page):
    """볼 수 없는(남의 · 지운) 제안 주소 — 빨간 '찾을 수 없습니다.' 대신 화면 말투(w1-18)."""
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/99",
                      "replies": [{"status": 404, "body": {"success": False, "data": None, "error": "찾을 수 없습니다."}}]})
    body = """
      const line = api.q('[data-erp-status]');
      return { text: api.text(line), error: line.classList.contains('is-error'), aside: api.shown(api.q('[data-ds-inbox-aside]')) };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes, search="?tab=inbox&proposal=99")
    assert got == {"text": "이 제안은 열 수 없어요 — 이미 없어졌거나 내가 맡은 할 일이 아니에요.", "error": False, "aside": False}


@NODE
def test_snoozed_ai_proposals_count_in_later_and_show_there(page):
    """'나중에'로 접은 AI 제안(15)은 '나중에 볼 것' 수에 들고, 그 줄을 열면 AI 칸에 그것만 보인다(w1-17)."""
    body = STATE + """
      const later = api.q('[data-ds-inbox-bin-nav="later"] [data-ds-inbox-bin-count]');
      const before = { count: api.text(later), pc: snap().pc };
      await api.click(api.q('[data-ds-inbox-bin-nav="later"]'));
      return { before: before, after: { pc: snap().pc, erp: api.shown(api.q('[data-ds-inbox-erp]')), count: api.text(api.q('[data-erp-count]')) } };"""
    got = run_node(page(), body, scripts=_scripts(), routes=_routes())
    assert got["before"] == {"count": "1", "pc": ["11", "12", "13"]}
    assert got["after"] == {"pc": ["15"], "erp": True, "count": "1"}


@NODE
@pytest.mark.parametrize("view", ["recheck", "releases"])
def test_recheck_and_releases_views_fill_the_same_agent_counts(app, people, monkeypatch, view):
    """'다시 확인' · '판 · 기록' 보기의 왼쪽 AI 직원 수도 승인 대기와 같다(w1-01 — 가운데 칸이 없어 수만 채우는 작은 스크립트)."""
    from pathlib import Path

    _on(monkeypatch, "brain_ui", "actions")
    html = _get(app, people["admin"], f"/brain?tab={view}").get_data(as_text=True)
    assert "js/brain/ds/ds-inbox-erp-nav.js" in html and 'data-erp-nav-api="/api/erp-actions"' in html
    assert "js/brain/ds/ds-inbox-erp.js" not in html  # 가운데 칸 스크립트는 승인 대기 보기에만
    inbox = _get(app, people["admin"], "/brain?tab=inbox").get_data(as_text=True)
    assert "ds-inbox-erp-nav.js" not in inbox and "data-erp-nav-api" not in inbox
    body = html[html.index(">", html.index("<body")) + 1:html.index("</body>")]
    body = re.sub(r"<script\b[\s\S]*?</script>|<link\b[^>]*>", "", body).replace("&#34;", "&quot;")
    root = Path(BASE_SCRIPTS[0]).parent
    scripts = [str(root / name) for name in ("brain-view.js", "brain-dom.js", "brain-review-view.js", "ds/ds-inbox-view.js",
                                             "ds/ds-inbox-kit.js", "ds/ds-inbox-erp-nav.js", "ds/ds-inbox.js")]
    routes = [{"method": "GET", "url": "/api/brain/recheck", "replies": [_ok({"items": [], "total": 0})]},
              {"method": "GET", "url": "/api/brain/releases", "replies": [_ok({"items": [], "page": 1, "pages": 1})]},
              {"method": "GET", "url": "/api/brain/inbox", "replies": [_ok({"cards": [], "counts": {"ai_waiting": 0}})]},
              {"method": "GET", "url": "/api/erp-actions/inbox", "replies": [_ok(INBOX)]}]
    look = """
      return { nav: ['cs', 'schedule', 'ops'].map(k => api.text(api.q('[data-erp-agent-count="' + k + '"]'))),
               muted: ['cs', 'schedule', 'ops'].map(k => api.q('[data-erp-agent-nav="' + k + '"]').classList.contains('fb-nav-item--muted')),
               later: api.text(api.q('[data-ds-inbox-bin-nav="later"] [data-ds-inbox-bin-count]')) };"""
    got = run_node(body, look, scripts=scripts, routes=routes, search=f"?tab={view}")
    assert got == {"nav": ["2", "1", "1"], "muted": [False, False, False], "later": "1"}

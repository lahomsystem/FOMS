"""승인 대기 'AI 할 일 제안' 칸(T8 · 판 ⑥ · ⑫ — 설계서 2026-11-14-foms-graft 3.5 · 3.6 · 5.5).

- 서버: 할 일 스위치가 꺼지면 자리 둘(왼쪽 · 가운데)이 비어 지금과 같다. 켜면 칸 머리 · 빈 목록 · 스크립트 셋(내용 지문 핀) ·
  왼쪽 AI 직원 셋(목록 AGENTS 와 같은 이름 · 아이콘). 회사 지식 화면은 못 열지만 AI 할 일 제안을 보는 사람(actions_viewer)은
  /brain · ?tab=inbox 에서 이 칸만(지식 칸 · 지식 API 주소 · 다른 탭 없음 — 다른 탭 · 카드는 404), 스위치 끔이면 지금처럼 404.
  항목 카드 화면의 위 줄 수는 할 일 스위치가 켜진 사람만 0 으로 자리를 그린다(틀이 /badge 로 고친다 — 질의 없음).
- 스크립트(node · 가짜 DOM · 실제로 그린 화면): 카드 셋 + 'n개 더 보기' · 수 · AI 직원 거르기 · 바로가기 카드 [주문에서 처리] ·
  옆 창(이유 · 바뀌는 칸 · 차례 · 2주 승인율 · 넣을 값) · 승인 · 409 기준 판 바뀜 → 새 카드 · 사람 고르기 전 [승인] 막힘 ·
  카드 거절 칩 · 폰 카드(폰 목록 맨 앞 · phone_ok 만 [승인]). 시공 팀 · 인원 글은 어디에도 없다(D211). 합성 자료만.
"""

from __future__ import annotations

import copy
import re
import shutil

import pytest

from db import db_session
from foms.services.ai_staff.registry import AGENTS
from foms.services.erp_actions.views import AGENT_KEYS
from foms.services.graft_flags import FLAGS
from tests.domains.test_brain_ds_inbox_js import SCRIPTS as BASE_SCRIPTS
from tests.domains.test_graft_cells import _ok, run_node
from tests.support.brain_screen_support import world

NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
SECRET_NAMES = ("여닫이 문짝", "문짝 재량 규칙", "문짝 맞춤 규칙")
CREW_WORDS = ("2팀", "3명", "폭 합", "÷ 300", "시공 인원")
OTHER_TABS = ("search", "table", "recheck", "releases", "map", "onto", "agents")


def _scripts() -> list[str]:
    from pathlib import Path

    ds = Path(BASE_SCRIPTS[0]).parent / "ds"
    return [str(ds / name) for name in ("ds-inbox-erp-card.js", "ds-inbox-erp-aside.js", "ds-inbox-erp.js")] + BASE_SCRIPTS


@pytest.fixture
def people(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    return {name: user.id for name, user in world(db_session).items()}


def _on(monkeypatch, *names: str) -> None:
    for name in names:
        monkeypatch.setenv(f"{FLAGS[name]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[name]}_COHORT", "all")


def _get(app, user_id: int, path: str):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client.get(path)


def test_switch_off_keeps_both_places_empty_like_today(app, people, monkeypatch):
    _on(monkeypatch, "brain_ui")
    body = _get(app, people["admin"], "/brain?tab=inbox").get_data(as_text=True)
    assert '<div class="fb-inbox-erp" data-ds-inbox-erp></div>' in body
    assert "data-erp-section" not in body and "data-erp-nav" not in body and "data-erp-agent-nav" not in body
    assert "brain-ds-inbox-erp.css" not in body and "ds-inbox-erp-card.js" not in body and "ds-inbox-erp.js" not in body
    for who in ("sales_mgr", "cs_staff"):  # 지식 화면을 못 여는 사람 — 지금처럼 404
        assert _get(app, people[who], "/brain?tab=inbox").status_code == 404


def test_actions_on_draws_the_section_nav_and_pinned_scripts(app, people, monkeypatch):
    _on(monkeypatch, "brain_ui", "actions")
    body = _get(app, people["admin"], "/brain?tab=inbox").get_data(as_text=True)
    strip, erp, know = (body.index("data-ds-inbox-strip"), body.index("data-erp-section"),
                        body.index('aria-label="지식 고침" data-ds-inbox-know'))
    assert strip < erp < know
    section = body[erp:body.index("</section>", erp)]
    assert "AI 할 일 제안" in section and "새로 붙음" in section
    assert "AI 직원이 FOMS 할 일을 제안해요 · 승인 전에는 아무것도 안 바뀌어요" in section
    assert re.search(r'css/contexts/brain/ds/brain-ds-inbox-erp\.css\?v=[0-9a-f]{12}', body)
    order = [re.search(rf'js/brain/ds/{name}\.js\?v=[0-9a-f]{{12}}" defer', body).start()
             for name in ("ds-inbox-erp-card", "ds-inbox-erp-aside", "ds-inbox-erp")]
    assert order == sorted(order) and order[-1] < body.index("js/brain/ds/ds-inbox.js")
    side = body[body.index('aria-label="승인 대기 길잡이"'):body.index("</nav>", body.index('aria-label="승인 대기 길잡이"'))]
    agents = re.findall(r'data-erp-agent-nav="(\w+)"><span class="f-i i-([\w-]+)" aria-hidden="true"></span>([^<]+)<', side)
    assert agents == [(key, AGENTS[key].icon[2:], AGENTS[key].label) for key in AGENT_KEYS]
    assert side.index("모두") < side.index("data-erp-nav") < side.index("지식 고침")
    assert not any(word in body for word in CREW_WORDS)


@pytest.mark.parametrize("who", ["sales_mgr", "cs_staff"])
def test_actions_only_viewer_gets_the_erp_part_only(app, people, monkeypatch, who):
    _on(monkeypatch, "brain_ui", "actions")
    user = people[who]
    for path in ("/brain", "/brain?tab=inbox"):
        resp = _get(app, user, path)
        assert resp.status_code == 200, path
        body = resp.get_data(as_text=True)
        assert "data-erp-section" in body and "data-erp-agent-nav" in body
        assert "data-ds-inbox-know" not in body and "data-inbox-url" not in body and "data-display" not in body
        assert not any(name in body for name in SECRET_NAMES)
        tabs = re.findall(r'data-ds-tab="(\w+)"', body[body.index("data-ds-tabs"):body.index("</span>", body.index("data-ds-tabs"))])
        assert tabs == ["inbox"]
        assert 'data-ds-count="inbox">0<' in body  # 틀이 /badge 합으로 고친다
    for tab in OTHER_TABS:
        assert _get(app, user, f"/brain?tab={tab}").status_code == 404, tab
    assert _get(app, user, "/brain/items/common/door").status_code == 404
    assert _get(app, people["viewer"], "/brain?tab=inbox").status_code == 404  # 실행할 할 일이 없는 사람


def test_item_page_top_count_is_drawn_lazily_only_with_actions(app, people, monkeypatch):
    _on(monkeypatch, "brain_ui")
    off = _get(app, people["admin"], "/brain/items/common/door").get_data(as_text=True)
    assert 'data-ds-count="inbox"' not in off and "data-badge-url" not in off  # 지금과 같다(수 없음)
    _on(monkeypatch, "actions")
    on = _get(app, people["admin"], "/brain/items/common/door").get_data(as_text=True)
    assert 'data-ds-count="inbox">0<' in on and 'data-badge-url="/api/erp-actions/badge"' in on


# ── 스크립트(node · 가짜 DOM · 실제로 그린 화면) ───────────────────────────
REJECT = [{"value": v, "label": t} for v, t in (("wrong_date", "날짜가 틀림"), ("misread", "손님 말을 잘못 읽음"),
                                                ("no_slot", "팀 자리 없음"), ("already_done", "이미 처리함"), ("other", "그 밖"))]


def _card(n: int, action: str, agent: str, *, mode: str = "run", phone_ok: bool = True, snoozed: bool = False) -> dict:
    labels = {"cs": "상담 AI", "schedule": "일정 AI", "ops": "운영 AI"}
    return {"id": n, "action": action, "action_label": f"할 일 {n}", "agent": agent, "agent_label": labels[agent],
            "title": f"할 일 {n} — #{n} 없음 → 11-21(토) 오전", "created_at": "2030-01-01 09:14", "order_id": n,
            "order_href": f"/erp/orders/{n}", "field": "시공 날", "before": "없음", "after": "11-21(토) 오전",
            "evidence": [{"kind": "cs_turn", "label": "상담 · 토요일 원함", "href": None},
                         {"kind": "order", "label": f"주문 #{n}", "href": f"/erp/orders/{n}"}],
            "level": 2, "mode": mode, "phone_ok": phone_ok, "base_changed": False, "status": "open", "snoozed": snoozed}


CARDS = [_card(11, "schedule_construction", "schedule"), _card(12, "register_as", "cs"),
         _card(13, "assign_draftsman", "ops", mode="link", phone_ok=False), _card(14, "add_construction_note", "cs"),
         _card(15, "add_construction_note", "cs", snoozed=True)]
INBOX = {"cards": CARDS, "counts": {"total": 4, "by_agent": {"cs": 2, "schedule": 1, "ops": 1}, "snoozed": 1},
         "reject_codes": REJECT, "est_seconds": 120}


def _detail(card: dict, **extra) -> dict:
    out = dict(copy.deepcopy(card), reason="손님이 토요일 오전이 좋다고 했어요.",
               changes=[{"field": "시공 날", "before": "없음", "after": "11-21(토) 오전"}],
               steps=["FOMS 시공일 · 시간대 쓰기 — 주문 화면 시공일 칸과 같은 기능", "손님 알림톡 1건 — 시공일 안내"],
               rate={"days": 14, "decided": 8, "approved": 7, "pct": 88},
               params=[{"name": "date", "label": "시공 날", "kind": "date", "value": "2030-11-21", "choices": []},
                       {"name": "time", "label": "시간대", "kind": "time_slot", "value": "오전",
                        "choices": [{"value": "", "label": "정하지 않음"}, {"value": "오전", "label": "오전"}]},
                       {"name": "notify_customer", "label": "손님에게 시공일 안내 보내기", "kind": "flag", "value": True,
                        "choices": []}],
               base_version=3, source_label="손님 상담에서 나옴", change_reason={"required": False, "codes": []},
               result=None, error_code=None)
    out.update(extra)
    return out


@pytest.fixture
def page(app, people, monkeypatch):
    """할 일 스위치를 켠 사람의 실제 승인 대기 화면 몸통(스크립트 · 링크 뺌 — 가짜 DOM 이 읽는 꼴)."""
    _on(monkeypatch, "brain_ui", "actions")

    def draw(who: str = "admin") -> str:
        body = _get(app, people[who], "/brain?tab=inbox").get_data(as_text=True)
        body = body[body.index(">", body.index("<body")) + 1:body.index("</body>")]
        body = re.sub(r"<script\b[\s\S]*?</script>|<link\b[^>]*>", "", body)
        return body.replace("&#34;", "&quot;")

    return draw


def _routes(*extra: dict) -> list[dict]:
    return [{"method": "GET", "url": "/api/brain/inbox", "replies": [_ok({"cards": [], "counts": {"ai_waiting": 0}})]},
            {"method": "GET", "url": "/api/erp-actions/inbox", "replies": [_ok(INBOX)]}, *extra]


def _gets(got: dict) -> list[str]:
    return [p["url"] for p in got["calls"] if p["method"] == "GET"]


STATE = """
  const ids = s => api.qa(s + ' [data-erp-card]').filter(api.shown).map(n => n.getAttribute('data-erp-card'));
  const snap = () => ({ pc: ids('[data-erp-cards]'), rest: api.text(api.q('[data-erp-rest]')),
    more: api.shown(api.q('[data-erp-more-row]')) && api.text(api.q('[data-erp-more-text]')),
    count: api.text(api.q('[data-erp-count]')),
    nav: ['cs', 'schedule', 'ops'].map(k => api.text(api.q('[data-erp-agent-count="' + k + '"]'))),
    strip: [api.shown(api.q('[data-ds-inbox-stat-box="actions"]')), api.text(api.q('[data-ds-inbox-stat="actions"]')),
            api.text(api.q('[data-ds-inbox-stat="today"]'))],
    aside: api.shown(api.q('[data-ds-inbox-aside]')) });
"""


@NODE
def test_pc_cards_three_then_more_counts_filter_and_link_card(page):
    body = STATE + """
      const first = snap();
      const card13 = api.q('[data-erp-card="13"]');
      const link = card13.querySelector('a.f-btn-primary');
      const c11 = api.text(api.q('[data-erp-card="11"]'));
      await api.click(api.q('[data-erp-act="more"]'));
      const all = snap();
      await api.click(api.q('[data-erp-agent-nav="cs"]'));
      const cs = [snap().pc, api.q('[data-erp-agent-nav="cs"]').classList.contains('is-selected')];
      return { first: first, all: all.pc, cs: cs, c11: c11, link: [api.text(link), link.getAttribute('href'),
               !!card13.querySelector('[data-erp-act="approve"]')], calls: api.posts };"""
    got = run_node(page(), body, scripts=_scripts(), routes=_routes())
    assert got["first"] == {"pc": ["11", "12", "13"], "rest": "4개 중 3개 · 남은 것 상담 AI 1", "more": "1개 더 보기",
                            "count": "4", "nav": ["2", "1", "1"], "strip": [True, "4", "4"], "aside": False}
    assert got["all"] == ["11", "12", "13", "14"]  # 나중에(snoozed)로 접은 15 는 없다
    assert got["cs"] == [["12", "14"], True]
    assert got["c11"].startswith("일정 AI할 일 11 — #11 없음 → 11-21(토) 오전01-01근거상담 · 토요일 원함주문 #11")
    assert got["c11"].endswith("시공 날없음에서11-21(토) 오전승인자세히거절날짜가 틀림손님 말을 잘못 읽음팀 자리 없음이미 처리함그 밖")
    assert got["link"] == ["주문에서 처리", "/erp/orders/13", False]
    assert _gets(got) == ["/api/brain/inbox", "/api/erp-actions/inbox"]


@NODE
def test_detail_aside_approve_base_changed_then_executed(page):
    changed = _detail(CARDS[0], base_version=4, title="할 일 11 — #11 11-20(금) 오후 → 11-21(토) 오전", base_changed=True)
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11", "replies": [_ok(_detail(CARDS[0]))]},
                     {"method": "POST", "url": "/api/erp-actions/proposals/11/approve", "replies": [
                         {"status": 409, "body": {"success": False, "error": "제안을 만든 뒤 주문이 바뀌었어요 — 바뀐 값으로 다시 봐 주세요.",
                                                  "data": {"code": "ACTION_BASE_CHANGED", "card": changed}}},
                         _ok({"status": "executed", "message": "시공일을 잡았어요.", "result": {}})]})
    body = STATE + """
      await api.click(api.q('[data-erp-card="11"] [data-erp-act="open"]'));
      const aside = api.q('[data-erp-aside]');
      const look = { text: api.text(aside), rows: api.qa('[data-erp-aside] tbody tr').map(api.text),
                     steps: api.qa('[data-erp-aside] ol li').map(api.text),
                     bar: aside.querySelector('.f-progress span').style.props.width,
                     form: api.shown(api.q('[data-erp-form]')), selected: api.q('[data-erp-card="11"]').classList.contains('is-selected'),
                     buttons: api.qa('[data-erp-aside] button').filter(api.shown).map(api.text) };
      await api.click(api.q('[data-erp-aside] [data-erp-act="approve"]'));
      const conflict = { status: api.text(api.q('[data-erp-aside] [data-erp-card-status]')), title: api.text(api.q('[data-erp-aside] h2')) };
      await api.click(api.q('[data-erp-aside] [data-erp-act="approve"]'));
      return { look: look, conflict: conflict, end: [api.shown(api.q('[data-ds-inbox-aside]')), api.text(api.q('[data-erp-status]'))],
               posts: api.posts.filter(p => p.method === 'POST'), calls: api.posts };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    look = got["look"]
    assert look["text"].startswith("일정 AI제안 자세히ERP 할 일 · 할 일 11새로 붙음할 일 11 — #11 없음 → 11-21(토) 오전"
                                   "2030-01-01 09:14 · 손님 상담에서 나옴이유손님이 토요일 오전이 좋다고 했어요.근거")
    assert "일정 AI · 할 일 11 14일 승인율88%" in look["text"]
    assert look["rows"] == ["시공 날없음11-21(토) 오전"]
    assert look["steps"] == ["1FOMS 시공일 · 시간대 쓰기 — 주문 화면 시공일 칸과 같은 기능", "2손님 알림톡 1건 — 시공일 안내"]
    assert look["bar"] == "88%" and look["form"] is False and look["selected"] is True
    assert look["buttons"] == ["", "승인", "고쳐서 승인", "나중에", "날짜가 틀림", "손님 말을 잘못 읽음", "팀 자리 없음", "이미 처리함", "그 밖"]
    assert not any(word in look["text"] for word in CREW_WORDS)
    assert got["conflict"] == {"status": "제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요",
                               "title": "할 일 11 — #11 11-20(금) 오후 → 11-21(토) 오전"}
    assert [p["body"]["base_version"] for p in got["posts"]] == [3, 4]  # 새 카드의 판으로 다시
    assert "edits" not in got["posts"][0]["body"]
    assert got["end"] == [False, "시공일을 잡았어요."]
    assert _gets(got).count("/api/erp-actions/inbox") == 3  # 처음 + 409 뒤 + 승인 뒤


@NODE
def test_people_must_be_picked_before_approve(page):
    pick = _detail(dict(CARDS[2], mode="run"), params=[{"name": "user_ids", "label": "도면 담당", "kind": "users", "value": [],
                    "choices": [{"value": 5, "label": "합성 도면 1"}, {"value": 6, "label": "합성 도면 2"}]}], base_version=7)
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/13", "replies": [_ok(pick)]},
                     {"method": "POST", "url": "/api/erp-actions/proposals/13/approve",
                      "replies": [_ok({"status": "executed", "message": "맡겼어요.", "result": {}})]})
    body = """
      await api.click(api.q('[data-erp-card="13"] [data-erp-act="open"]'));
      const gate = () => [api.qa('[data-erp-aside] [data-erp-act="approve"], [data-erp-aside] [data-erp-act="approve-edit"]')
                           .map(b => b.disabled), api.text(api.q('[data-erp-missing]'))];
      const before = { form: api.shown(api.q('[data-erp-form]')), gate: gate() };
      const box = api.q('[data-erp-param="user_ids"] input[value="5"]');
      box.checked = true;
      box.dispatchEvent(new CustomEvent('change'));
      const after = gate();
      await api.click(api.q('[data-erp-act="approve-edit"]'));
      return { before: before, after: after, posts: api.posts.filter(p => p.method === 'POST') };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["before"] == {"form": True, "gate": [[True, True], "넣어야 승인할 수 있어요: 도면 담당"]}
    assert got["after"] == [[False, False], ""]
    assert got["posts"][0]["body"] == {"base_version": 7, "view_ms": 0, "edits": {"user_ids": [5]}}


@NODE
def test_card_reject_chip_and_card_approve_read_the_detail_first(page):
    as_steps = ["FOMS AS 접수 — AS 접수 창과 같은 기능", "AS 기록에 접수 내용 · '접수됨' 줄"]  # 손님 알림톡 줄 없음 — 바로 승인
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/12",
                      "replies": [_ok(_detail(CARDS[1], params=[], steps=as_steps))]},
                     {"method": "POST", "url": "/api/erp-actions/proposals/12/approve",
                      "replies": [_ok({"status": "executed", "message": "AS 를 접수했어요.", "result": {}})]},
                     {"method": "POST", "url": "/api/erp-actions/proposals/11/reject", "replies": [_ok({"status": "rejected"})]})
    body = """
      const box = api.q('[data-erp-card="11"] [data-erp-reject-box]');
      const closed = api.shown(box);
      await api.click(api.q('[data-erp-card="11"] [data-erp-act="reject-open"]'));
      const opened = api.shown(api.q('[data-erp-card="11"] [data-erp-reject-box]'));
      await api.click(api.q('[data-erp-card="11"] [data-erp-code="misread"]'));
      const said = api.text(api.q('[data-erp-status]'));
      await api.click(api.q('[data-erp-card="12"] [data-erp-act="approve"]'));
      return { closed: closed, opened: opened, said: said, end: api.text(api.q('[data-erp-status]')),
               calls: api.posts.map(p => p.method + ' ' + p.url), posts: api.posts.filter(p => p.method === 'POST') };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["closed"] is False and got["opened"] is True
    assert got["said"] == "거절했어요 — 같은 제안은 다시 오지 않아요."
    assert got["posts"][0]["body"] == {"code": "misread", "view_ms": None}
    assert got["calls"][-3:] == ["GET /api/erp-actions/proposals/12", "POST /api/erp-actions/proposals/12/approve",
                                 "GET /api/erp-actions/inbox"]
    assert got["posts"][1]["body"] == {"base_version": 3, "view_ms": None} and got["end"] == "AS 를 접수했어요."


@NODE
def test_phone_cards_go_first_in_the_phone_list_and_only_phone_ok_can_approve(page):
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/13", "replies": [_ok(_detail(CARDS[2], params=[]))]})
    body = """
      const list = api.q('[data-ds-phone-list]');
      const cards = list.children.map(n => [n.getAttribute('data-erp-card'), !!n.querySelector('[data-erp-act="approve"]')]);
      const first = api.text(list.children[0]);
      await api.click(list.children[2].querySelector('[data-erp-act="open"]'));
      return { cards: cards, first: first, pc: api.text(list.children[2]),
               aside: api.shown(api.q('[data-ds-inbox-aside]')),
               asideButtons: api.qa('[data-erp-aside] button').filter(api.shown).map(api.text),
               help: api.qa('[data-erp-aside] .f-help').map(api.text) };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes, phone=True)
    assert got["cards"] == [["11", True], ["12", True], ["13", False], ["14", True]]
    assert got["first"] == "ERP 할 일일정 AI01-01할 일 11 — #11 없음 → 11-21(토) 오전없음에서11-21(토) 오전상담 · 토요일 원함승인"
    assert got["pc"].endswith("PC 에서 볼 것")
    assert got["aside"] is True and "승인" not in got["asideButtons"] and "나중에" in got["asideButtons"]
    assert "이 제안은 PC 에서 승인해요." in got["help"]


# ── 검수 R1 고침(R-02 · R-08 · R-22) ─────────────────────────────────────
NOTICE_FIRST = "손님에게 알림톡이 나가요 — 확인한 뒤 승인해 주세요."
NO_NOTICE_STEPS = ["FOMS 시공일 · 시간대 쓰기 — 주문 화면 시공일 칸과 같은 기능"]  # 알림톡을 쓸 수 없는 상태(스위치 끔)의 차례


def _approve_route(n: int) -> dict:
    return {"method": "POST", "url": f"/api/erp-actions/proposals/{n}/approve",
            "replies": [_ok({"status": "executed", "message": "실행했어요.", "result": {}})]}


CARD_APPROVE = """
  const where = __WHERE__;
  await api.click(where.querySelector('[data-erp-act="approve"]'));
  const aside = api.q('[data-erp-aside]');
  return { posts: api.posts.filter(p => p.method === 'POST').map(p => [p.url, p.body]),
           aside: api.shown(api.q('[data-ds-inbox-aside]')),
           status: aside ? api.text(aside.querySelector('[data-erp-card-status]')) : null,
           steps: aside ? api.qa('[data-erp-aside] ol li').map(api.text) : [],
           form: aside ? api.shown(aside.querySelector('[data-erp-form]')) : null };"""


@NODE
@pytest.mark.parametrize("phone", [False, True])
def test_card_approve_with_a_customer_notice_opens_the_aside_instead(page, phone):
    """R-02 — PC 카드 · 폰 카드 빠른 [승인]: 손님 알림톡(시공일 안내)이 같이 나가면 바로 보내지 않고 옆 창(그 줄)을 연다."""
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11", "replies": [_ok(_detail(CARDS[0]))]},
                     _approve_route(11))
    where = ("api.q('[data-ds-phone-list]').children.find(n => n.getAttribute('data-erp-card') === '11')" if phone
             else "api.q('[data-erp-cards] [data-erp-card=\"11\"]')")
    got = run_node(page(), CARD_APPROVE.replace("__WHERE__", where), scripts=_scripts(), routes=routes, phone=phone)
    assert got["posts"] == [] and got["aside"] is True and got["status"] == NOTICE_FIRST
    assert "2손님 알림톡 1건 — 시공일 안내" in got["steps"] and got["form"] is False


@NODE
def test_aside_approve_after_seeing_the_notice_posts_once(page):
    """R-02 — 옆 창에서 줄을 본 뒤 [승인]은 지금처럼 한 번 보낸다(넣을 값을 고치지 않았으면 edits 없음)."""
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11", "replies": [_ok(_detail(CARDS[0]))]},
                     _approve_route(11))
    body = CARD_APPROVE.replace("__WHERE__", "api.q('[data-erp-cards] [data-erp-card=\"11\"]')").replace(
        "  const aside = api.q('[data-erp-aside]');",
        "  await api.click(api.q('[data-erp-aside] [data-erp-act=\"approve\"]'));\n  const aside = null;")
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["posts"] == [["/api/erp-actions/proposals/11/approve", {"base_version": 3, "view_ms": 0}]]


@NODE
@pytest.mark.parametrize("detail_extra", [
    {"steps": NO_NOTICE_STEPS},  # 알림톡을 쓸 수 없는 상태 — 지금과 같다
    {"field": "손님 알림톡(시공일 안내)", "params": [],  # 알림톡 보내기 할 일 — 카드 칸이 곧 그 줄
     "steps": ["손님 알림톡 1건 — 시공일 안내(시공일 · 시간대만)"]},
])
def test_card_approve_without_a_hidden_notice_stays_one_click(page, detail_extra):
    routes = _routes({"method": "GET", "url": "/api/erp-actions/proposals/11",
                      "replies": [_ok(_detail(CARDS[0], **detail_extra))]}, _approve_route(11))
    got = run_node(page(), CARD_APPROVE.replace("__WHERE__", "api.q('[data-erp-cards] [data-erp-card=\"11\"]')"),
                   scripts=_scripts(), routes=routes)
    assert got["posts"] == [["/api/erp-actions/proposals/11/approve", {"base_version": 3, "view_ms": None}]]
    assert got["aside"] is False


@NODE
def test_only_same_origin_paths_become_links(page):
    """R-22 — 서버 주소는 '/' 로 시작하고 '//' · '/\\' 가 아닐 때만 링크, 아니면 글만(근거 칩 · [주문에서 처리])."""
    bad = ["//evil.example/x", "/\\evil.example", "javascript:alert(1)", "https://evil.example", None]
    card = dict(_card(21, "schedule_construction", "schedule"),
                evidence=[{"kind": "order", "label": f"근거 {i}", "href": href} for i, href in enumerate(bad)]
                + [{"kind": "order", "label": "근거 좋음", "href": "/erp/orders/21"}])
    link_card = dict(_card(22, "assign_draftsman", "ops", mode="link", phone_ok=False), order_href="//evil.example/o")
    inbox = dict(INBOX, cards=[card, link_card], counts={"total": 2, "by_agent": {"cs": 0, "schedule": 1, "ops": 1},
                                                         "snoozed": 0})
    routes = [{"method": "GET", "url": "/api/brain/inbox", "replies": [_ok({"cards": [], "counts": {"ai_waiting": 0}})]},
              {"method": "GET", "url": "/api/erp-actions/inbox", "replies": [_ok(inbox)]}]
    body = """
      const chips = api.qa('[data-erp-cards] [data-erp-card="21"] .f-chip');
      const go = api.q('[data-erp-cards] [data-erp-card="22"] .f-btn-primary');
      return { chips: chips.map(n => [n.tagName, n.getAttribute('href'), api.text(n)]),
               go: [go.tagName, go.getAttribute('href'), api.text(go)] };"""
    got = run_node(page(), body, scripts=_scripts(), routes=routes)
    assert got["chips"] == [["SPAN", None, f"근거 {i}"] for i in range(len(bad))] + [["A", "/erp/orders/21", "근거 좋음"]]
    assert got["go"] == ["SPAN", None, "주문에서 처리"]


def test_phone_approve_button_leaves_its_height_to_the_44px_shell_rule():
    """R-08 — 폰 ERP [승인]에 높이를 적지 않는다(틀의 '누르는 것 44px 이상'을 이기지 않게)."""
    from pathlib import Path

    css_dir = Path(BASE_SCRIPTS[0]).parents[2] / "css" / "contexts" / "brain" / "ds"
    erp = (css_dir / "brain-ds-inbox-erp.css").read_text(encoding="utf-8")
    rule = re.search(r"\.fb-erp-phone \.fb-phone-approve \{([^}]*)\}", erp).group(1)
    assert "min-height" not in rule and "height" not in rule
    assert all(int(px) >= 44 for px in re.findall(r"min-height:\s*(\d+)px", erp))
    shell = (css_dir / "brain-ds-shell.css").read_text(encoding="utf-8")
    assert re.search(r"\.fb-shell \.f-btn,[^{]*\{\s*min-height: 44px;", shell)


@NODE
def test_actions_only_viewer_page_reads_only_the_erp_api(page):
    body = STATE + "return { snap: snap(), calls: api.posts.map(p => p.url) };"
    got = run_node(page("sales_mgr"), body, scripts=_scripts(), routes=_routes())
    assert got["calls"] == ["/api/erp-actions/inbox"]
    assert got["snap"]["pc"] == ["11", "12", "13"] and got["snap"]["strip"] == [True, "4", "4"]

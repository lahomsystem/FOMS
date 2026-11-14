"""새 승인 대기 화면 스크립트(static/js/brain/ds/ds-inbox*.js — 설계서 2026-11-14-foms-graft 5.3 ~ 5.5 · 판 ⑥ · ⑫) node 시험.

- 순수 계산(``ds-inbox-view.js``): 숫자 띠 합 · 어림 · 묶음 줄 글 · 빈 묶음 한 줄 · 첫 장 미리 보기 · 주소의 묶음 · 폰 나누기
  (판정은 ``brain-review-view.js`` 의 actionsFor) · 'PC 에서 볼 것' 요약 · 등급 A 한꺼번에 대상 · 때 글.
- 화면: 옛 시험(``test_brain_fix_inbox_js``)의 가짜 DOM 을 그대로 빌려, 새 템플릿을 Flask 로 실제로 그려 싣는다 — 첫 화면 묶음 줄 ·
  길잡이 수 · F27(0개) · F24(표 줄은 꺼진 채 · 확인 창 한 번) · F05(폰 접기 · ③ 질문은 폰에서도) · F07(주소의 묶음 · 길잡이
  누름) · F08(고쳐서 승인 열고 닫기) · 거절 칩 · 나중에 · 등급 B 확인 · T8 약속(setCount · openAside · ds:inbox-ready).
fetch · confirm · 주소 바꾸기는 가짜로 받아 적는다(바깥으로 보내지 않는다). 합성 자료만.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from db import db_session
from foms.services.brain.display import display_table
from foms.services.graft_flags import FLAGS
from tests.domains.test_brain_fix_inbox_js import BULK, HARNESS, _card, _name_card
from tests.support.brain_screen_support import world

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/ds/ds-inbox-view.js"
REVIEW = ROOT / "static/js/brain/brain-review-view.js"
SCRIPTS = [str(ROOT / "static/js/brain" / name) for name in (
    "brain-view.js", "brain-dom.js", "brain-review-view.js", "ds/ds-inbox-view.js", "ds/ds-inbox-kit.js", "ds/ds-inbox-card.js",
    "ds/ds-inbox-table.js", "ds/ds-inbox-question.js", "ds/ds-inbox-phone.js", "ds/ds-inbox-act.js", "ds/ds-inbox.js")]
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def _node(expr: str, data: object = None):
    script = (f"const v = require({json.dumps(str(VIEW))}); const r = require({json.dumps(str(REVIEW))});"
              f"const data = {json.dumps(data, ensure_ascii=False)};"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
    return json.loads(out.stdout)


def _cards(**bins: int) -> list[dict]:
    out, n = [], 0
    for bin_, count in bins.items():
        for _ in range(count):
            n += 1
            out.append(_card(n, bin_))
    return out


# ── 순수 계산 ─────────────────────────────────────────────────────────────
@NODE
def test_strip_totals_add_up_like_the_board():
    """판 ⑥ 의 숫자 — ② 4 · ③ 1 · ⑥ 2 + AI 할 일 제안 7 = 오늘 결정할 것 14 · 어림 6분(줄 어림 2 + 1 + 1, AI 2)."""
    cards = _cards(content=4, decide=1, rules=2)
    got = _node("[v.stripTotals(data, 7), v.stripTotals(data), v.stripTotals([], 0), v.stripTotals(null, '3'),"
                " v.minutes(0, 25), v.minutes(1, 5), v.minutes(4, 25)]", cards)
    assert got[0] == {"today": 14, "minutes": 6, "knowledge": 7, "actions": 7}
    assert got[1] == {"today": 7, "minutes": 4, "knowledge": 7, "actions": 0}  # T8 이 없으면 지식 고침만
    assert got[2] == {"today": 0, "minutes": 0, "knowledge": 0, "actions": 0}
    assert got[3] == {"today": 3, "minutes": 1, "knowledge": 0, "actions": 3}
    assert got[4:] == [0, 1, 2]


@NODE
def test_bin_rows_peek_and_empty_line():
    cards = _cards(content=2, decide=1, rules=1) + [dict(_card(9, "zzz"), title="모르는 묶음")]
    cards[2]["main"]["op"] = "create"
    cards[2]["type"] = "question"
    cards[3]["main"]["link"] = {"kind": "applies_to", "from": "a", "to": "b", "from_label": "상판 규격", "to_label": "상판 재단"}
    display = display_table()
    rows, line, none, full = _node("[v.binRows(data.c, data.d), v.emptyLine(data.c), v.emptyLine([]), v.emptyLine(data.f)]",
                                   {"c": cards, "d": display, "f": _cards(names=1, content=1, decide=1, mark=1, calc=1, rules=1)})
    assert [(r["key"], r["title"], r["n"], r["mins"]) for r in rows] == [
        ("content", "② 새로 들어가거나 바뀌는 지식", 3, 1), ("decide", "③ 사장님이 정해 주실 것", 1, 1), ("rules", "⑥ 규칙 잇기", 1, 1)]
    assert rows[0]["line"] == "새로 들어가거나 바뀌는 내용이에요. 맞는지만 봐 주세요."
    assert rows[0]["peek"] == "배운 점 — 지식 1"  # 모르는 묶음(zzz)은 ②
    assert rows[1]["peek"] == "물어볼 것 — 지식 3 (새로)"
    assert rows[2]["peek"] == "상판 규격 → 상판 재단"
    assert line == "① 한글 이름 붙이기 · ④ 같은 값이 적힌 곳 표시 · ⑤ 계산기 제품 · 옵션 은 지금 없어요"
    assert none == "" and full == ""  # 카드가 0 이면 묶음 글 없이 '승인 대기가 없어요.'만(F27)


@NODE
def test_side_nav_short_names_match_the_bins():
    side = (ROOT / "templates/brain/ds/partials/inbox_side.html").read_text(encoding="utf-8")
    pairs = re.findall(r"\('(\w+)', '([^']+)'\)", side[side.index("bin_nav"):side.index("start_bin")])
    assert pairs == [tuple(x) for x in _node("v.BINS.map(b => [b.key, b.short])")]


@NODE
def test_address_and_query_keep_the_open_bin():
    got = _node("[['?tab=inbox&bin=names', '?bin=later', '?tab=inbox&bin=zzz', '?tab=inbox&bin=content2', '', null]"
                ".map(v.fromQuery), v.addressFor('/brain', ''), v.addressFor('/brain', 'mark')]")
    assert got == [["names", "later", "", "", "", ""], "/brain?tab=inbox", "/brain?tab=inbox&bin=mark"]


@NODE
def test_phone_split_uses_the_review_judgement_and_summarises_the_pc_box():
    cards = [_card(1, "content"), _card(2, "content", phone_ok=False), _card(3, "content", stale=True),
             _card(4, "decide", phone_ok=False), _card(5, "content"), _card(6, "mark", phone_ok=False)]
    cards[5]["main"]["link"] = {"kind": "copy_in", "from": "a", "to": "b"}
    got = _node("(() => { const s = v.phoneSplit(data.c, {c5: true}, r);"
                " return [s.phone.map(c => c.id), s.pc.map(c => c.id), v.pcSummary(s.pc, data.d)]; })()",
                {"c": cards, "d": display_table()})
    assert got == [["c1", "c4"], ["c2", "c3", "c5", "c6"], "배운 점 3 · 연결 1"]


@NODE
def test_bulk_scope_follows_the_open_bin():
    cards = [_card(1, "content"), _card(2, "content"), _card(3, "content", stale=True), _card(4, "content", bulk_ok=False),
             _card(5, "names"), _card(6, "decide"), _card(7, "rules")]
    got = _node("[v.bulkScope(data, '', ['names'], {}, r), v.bulkScope(data, '', [], {c2: true}, r),"
                " v.bulkScope(data, 'content', ['names'], {}, r), v.bulkScope(data, 'names', ['names'], {}, r),"
                " v.bulkScope(data, 'decide', [], {}, r), v.bulkScope(data, 'later', [], {}, r)]", cards)
    assert got == [[10, 20, 70], [10, 50, 70], [10, 20], [], [], []]


@NODE
def test_when_text():
    got = _node("[v.whenText('2026-11-08 10:00', '2026-11-08'), v.whenText('2026-11-08 10:00', '2026-11-09'), v.whenText('', 'x')]")
    assert got == ["10:00", "11-08", ""]


# ── 화면(가짜 DOM + 실제 새 템플릿) ────────────────────────────────────────
@pytest.fixture
def page(app, monkeypatch):
    """스위치 켠 ADMIN 의 새 승인 대기 화면 몸통(첫 <script> 앞까지) — 가짜 DOM 이 읽는 꼴로."""
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS['brain_ui']}_COHORT", "all")
    people = world(db_session)

    def draw(path: str = "/brain?tab=inbox", who: str = "admin") -> str:
        client = app.test_client()
        with client.session_transaction() as sess:
            sess["user_id"] = people[who].id
        body = client.get(path).get_data(as_text=True)
        start = body.index(">", body.index("<body")) + 1
        return body[start:body.index("<script", start)].replace("&#34;", "&quot;")  # 가짜 DOM 은 &quot; 만 읽는다

    return draw


def _run(html: str, body: str, *, cards: list, phone: bool = False, search: str = "?tab=inbox", confirm: list | None = None,
         before: str = "", after: str = "", tmp: Path | None = None):
    scripts = list(SCRIPTS)
    for name, code, first in (("before.js", before, True), ("after.js", after, False)):
        if code:
            path = tmp / name
            path.write_text(code, encoding="utf-8")
            scripts.insert(0 if first else len(scripts), str(path))
    payload = {"scripts": scripts, "html": html, "attrs": {"data-bulk-url": BULK}, "cards": cards, "phone": phone,
               "search": search, "confirm": confirm or [], "body": body}
    out = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


@NODE
def test_overview_draws_bin_rows_nav_counts_strip_and_bulk(page):
    cards = _cards(content=2, decide=1) + [_name_card(9)]
    body = """
      const nav = k => api.q('[data-ds-inbox-bin-nav="' + k + '"]');
      return {
        rows: api.qa('[data-ds-inbox-bins] [data-bin]').map(n => n.getAttribute('data-bin')),
        texts: api.qa('[data-ds-inbox-bins] li').map(api.text),
        nav: ['names', 'content', 'decide', 'mark', 'later'].map(k => [api.text(nav(k).querySelector('[data-ds-inbox-bin-count]')),
                                                                       nav(k).classList.contains('fb-nav-item--muted')]),
        all: nav('names').classList.contains('is-selected') || !api.q('[data-ds-nav="inbox"]').classList.contains('is-selected'),
        strip: ['today', 'minutes', 'knowledge'].map(k => api.text(api.q('[data-ds-inbox-stat="' + k + '"]'))),
        actions: api.shown(api.q('[data-ds-inbox-stat="actions"]')),
        bulk: api.shown(api.q('[data-ds-inbox-bulk]')) && api.text(api.q('[data-ds-inbox-bulk]')),
        open: api.shown(api.q('[data-ds-inbox-open]')), url: api.urls[api.urls.length - 1] };"""
    got = _run(page(), body, cards=cards)
    assert got["rows"] == ["names", "content", "decide"]
    assert got["texts"][1] == ("② 새로 들어가거나 바뀌는 지식2새로 들어가거나 바뀌는 내용이에요. 맞는지만 봐 주세요."
                               "배운 점 — 지식 1약 1분열기")  # 가짜 DOM 의 글은 칸 사이를 띄우지 않고 잇는다
    assert got["texts"][-1] == "④ 같은 값이 적힌 곳 표시 · ⑤ 계산기 제품 · 옵션 · ⑥ 규칙 잇기 은 지금 없어요"
    assert got["nav"] == [["1", False], ["2", False], ["1", False], ["0", True], ["0", True]]  # 0 은 흐리게
    assert got["all"] is False and got["open"] is False
    assert got["strip"] == ["4", "3", "4"] and got["actions"] is False
    assert got["bulk"] == "등급 A 2개 모두 승인"  # 첫 화면: 표 묶음(①)과 ③ 을 뺀 등급 A
    assert got["url"] == "/brain?tab=inbox"


@NODE
def test_nothing_to_decide_draws_one_empty_line_and_no_table_or_button(page):
    """F27 — 0개면 '승인 대기가 없어요.' 한 줄만(빈 표 · 0개 단추 없음)."""
    body = """return { bins: api.qa('[data-ds-inbox-bins] li').map(api.text), table: api.qa('table').length,
                       bulk: api.shown(api.q('[data-ds-inbox-bulk]')), minutes: api.text(api.q('[data-ds-inbox-stat="minutes"]')),
                       ai: api.shown(api.q('[data-ds-inbox-ai]')) };"""
    got = _run(page(), body, cards=[])
    assert got == {"bins": ["승인 대기가 없어요."], "table": 0, "bulk": False, "minutes": "0", "ai": False}


@NODE
def test_name_table_rows_start_unchecked_and_one_confirm_guards_the_approval(page):
    """F24 — 줄은 처음에 꺼진 채 · 체크 0이면 '체크한 줄이 없어요.' · 확인 창 취소면 안 보냄 · 확인이면 체크한 줄만."""
    cards = [_name_card(1), _name_card(2), _name_card(3, bulk_ok=False)]
    body = """
      const boxes = () => api.qa('[data-ds-row-check]');
      const button = api.q('[data-ds-table-apply]');
      const first = { checked: boxes().map(b => b.checked), disabled: boxes().map(b => b.disabled), label: api.text(button),
                      bulk: api.shown(api.q('[data-ds-inbox-bulk]')) };
      await api.click(button);
      const none = { status: api.text(api.q('[data-ds-table-status]')), confirms: api.confirms.length, posts: api.posts.length };
      boxes()[0].checked = true;
      await api.click(button);
      const cancelled = { confirms: api.confirms.slice(), posts: api.posts.length };
      boxes()[0].checked = true;
      boxes()[1].checked = true;
      api.q('[data-ds-row-name="20"]').value = '고친 한글 이름';
      api.answers.push(true);
      await api.click(api.q('[data-ds-table-apply]'));
      return { first: first, none: none, cancelled: cancelled, posts: api.posts };"""
    got = _run(page("/brain?tab=inbox&bin=names"), body, cards=cards, search="?tab=inbox&bin=names")
    assert got["first"] == {"checked": [False, False, False], "disabled": [False, False, True], "label": "체크한 줄 승인",
                            "bulk": False}
    assert got["none"] == {"status": "체크한 줄이 없어요.", "confirms": 0, "posts": 0}
    assert got["cancelled"] == {"confirms": ["체크한 1줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요)."], "posts": 0}
    assert got["posts"][0] == {"url": BULK, "body": {"ids": [10]}}
    assert got["posts"][1]["url"] == "/api/brain/proposals/20/apply"
    assert got["posts"][1]["body"]["edits"] == {"payload.pref_label": "고친 한글 이름"} and len(got["posts"]) == 2


@NODE
def test_phone_lists_one_field_cards_and_folds_the_rest_into_the_pc_box(page):
    """F05 · ⑫ — 폰: 승인할 수 있는 카드 + ③ 질문만 '폰에서 승인', 나머지는 처음부터 'PC 에서 볼 것'. 카드를 누르면 이유 · 거절."""
    cards = [_card(1, "content"), _card(2, "content", phone_ok=False), _card(3, "content", stale=True),
             _card(4, "decide", phone_ok=False)]
    body = """
      const list = () => api.qa('[data-ds-phone-list] [data-card-id]').map(n => n.getAttribute('data-card-id'));
      const card = api.q('[data-ds-phone-list] [data-card-id="c1"]');
      const more = card.querySelector('[data-ds-phone-more-box]');
      const before = api.shown(more);
      await api.click(card.querySelector('[data-ds-phone-toggle]'));
      const opened = { more: api.shown(more), chips: card.querySelectorAll('[data-reject-code]').length > 0,
                       reason: api.text(more).indexOf('이유 · 까닭') >= 0 };
      const pcBefore = api.shown(api.q('[data-ds-phone-pc-list]'));
      await api.click(api.q('[data-ds-phone-pc-toggle]'));
      const result = { list: list(), count: api.text(api.q('[data-ds-phone-count]')),
                       pc: api.qa('[data-ds-phone-pc-list] [data-card-id]').map(n => n.getAttribute('data-card-id')),
                       pcTitle: api.text(api.q('[data-ds-phone-pc-title]')), pcShown: [pcBefore, api.shown(api.q('[data-ds-phone-pc-list]'))],
                       approve: api.qa('[data-ds-phone-pc-list] [data-ds-act="apply"]').length, before: before, opened: opened };
      await api.click(card.querySelector('[data-ds-act="apply"]'));
      result.posts = api.posts;
      return result;"""
    got = _run(page(), body, cards=cards, phone=True)
    assert got["list"] == ["c1", "c4"] and got["count"] == "2"
    assert got["pc"] == ["c2", "c3"] and got["pcTitle"] == "PC 에서 볼 것 2" and got["pcShown"] == [False, True]
    assert got["approve"] == 0  # PC 에서 볼 것에는 승인 단추가 없다
    assert got["before"] is False and got["opened"] == {"more": True, "chips": True, "reason": True}
    assert got["posts"] == [{"url": "/api/brain/proposals/10/apply", "body": {"base_version": 1, "view_ms": 0}}]


@NODE
def test_phone_shows_three_cards_then_more(page):
    body = """
      const shown = () => api.qa('[data-ds-phone-list] [data-card-id]').filter(api.shown).length;
      const first = { shown: shown(), more: api.text(api.q('[data-ds-phone-more]')) };
      await api.click(api.q('[data-ds-phone-more]'));
      return { first: first, after: shown(), more: api.shown(api.q('[data-ds-phone-more]')) };"""
    got = _run(page(), body, cards=_cards(content=5), phone=True)
    assert got == {"first": {"shown": 3, "more": "2개 더 보기"}, "after": 5, "more": False}


@NODE
def test_open_bin_is_kept_in_the_address_and_switched_from_the_nav(page):
    """F07 — 주소의 bin 으로 그 묶음을 열고, 돌아가기 · 길잡이 누름 · 열기 단추로 바꿀 때 주소가 맞다. 없는 · 빈 bin 은 목록."""
    cards = [_card(1, "content"), _card(2, "names")]
    body = """
      const state = () => ({ title: api.text(api.q('[data-ds-inbox-title]')), bins: api.shown(api.q('[data-ds-inbox-bins]')),
                             back: api.shown(api.q('[data-ds-inbox-back]')), erp: api.shown(api.q('[data-ds-inbox-erp]')),
                             cards: api.ids('[data-ds-inbox-cards]'), url: api.urls[api.urls.length - 1] });
      const start = state();
      await api.click(api.q('[data-ds-inbox-back]'));
      const back = state();
      await api.click(api.q('[data-ds-bin-open="content"]'));
      const opened = state();
      await api.click(api.q('[data-ds-inbox-bin-nav="names"]'));
      const nav = Object.assign(state(), { picked: api.q('[data-ds-inbox-bin-nav="names"]').getAttribute('aria-current') });
      await api.click(api.q('[data-ds-nav="inbox"]'));
      return { start: start, back: back, opened: opened, nav: nav, all: state() };"""
    got = _run(page("/brain?tab=inbox&bin=content"), body, cards=cards, search="?tab=inbox&bin=content")
    assert got["start"] == {"title": "② 새로 들어가거나 바뀌는 지식", "bins": False, "back": True, "erp": False, "cards": ["c1"],
                            "url": "/brain?tab=inbox&bin=content"}
    assert got["back"]["title"] == "지식 고침" and got["back"]["bins"] is True and got["back"]["url"] == "/brain?tab=inbox"
    assert got["back"]["erp"] is True and got["opened"]["url"] == "/brain?tab=inbox&bin=content"
    assert got["nav"]["url"] == "/brain?tab=inbox&bin=names" and got["nav"]["picked"] == "page"
    assert got["nav"]["title"] == "① 한글 이름 붙이기" and got["nav"]["cards"] == []  # ① 은 표 한 장(ADMIN)
    assert got["all"]["url"] == "/brain?tab=inbox" and got["all"]["bins"] is True
    plain = """return { title: api.text(api.q('[data-ds-inbox-title]')), url: api.urls[api.urls.length - 1] };"""
    for search in ("?tab=inbox&bin=zzz", "?tab=inbox&bin=mark", "?tab=inbox&bin=later"):  # 없는 · 빈 묶음 · 접은 것 없음
        assert _run(page(), plain, cards=cards, search=search) == {"title": "지식 고침", "url": "/brain?tab=inbox"}, search


@NODE
def test_card_edit_reject_later_and_grade_b_confirm(page):
    """F08 · 거절 칩 · 나중에 · 등급 B 확인 — 열고 닫기만으로는 아무것도 안 보낸다."""
    cards = [_card(1, "content"), _card(2, "content")]
    cards[1]["main"]["confirm"] = {"field": "name", "value": "새 이름"}
    body = """
      const one = api.q('[data-ds-inbox-cards] [data-card-id="c1"]');
      const start = one.querySelector('[data-ds-act="edit"]');
      const look = () => ({ editor: api.shown(one.querySelector('[data-ds-edit-box]')),
                            save: api.shown(one.querySelector('[data-ds-act="edit-apply"]')), label: api.text(start),
                            expanded: start.getAttribute('aria-expanded') });
      const before = look();
      await api.click(start);
      const opened = look();
      await api.click(start);
      const closed = look();
      const sent = api.posts.length;
      await api.click(one.querySelector('[data-ds-act="reject"]'));
      const chips = one.querySelectorAll('[data-reject-code]').map(b => b.getAttribute('data-reject-code'));
      const two = api.q('[data-card-id="c2"]');
      await api.click(two.querySelector('[data-ds-act="apply"]'));
      const blocked = { posts: api.posts.length, status: api.text(two.querySelector('[data-ds-prop-status]')) };
      two.querySelector('[data-ds-confirm]').checked = true;
      await api.click(two.querySelector('[data-ds-act="apply"]'));
      const applied = api.posts[api.posts.length - 1];
      await api.click(api.q('[data-card-id="c1"] [data-ds-act="later"]'));
      const later = { cards: api.ids('[data-ds-inbox-cards]'), folded: api.ids('[data-ds-inbox-later]'),
                      title: api.text(api.q('[data-ds-inbox-later-title]')),
                      nav: api.text(api.q('[data-ds-inbox-bin-count="later"]')) };
      await api.click(api.q('[data-ds-inbox-bin-nav="later"]'));
      later.view = { title: api.text(api.q('[data-ds-inbox-title]')), cards: api.ids('[data-ds-inbox-cards]'),
                     url: api.urls[api.urls.length - 1] };
      return { before: before, opened: opened, closed: closed, sent: sent, chips: chips, blocked: blocked, applied: applied,
               later: later };"""
    got = _run(page("/brain?tab=inbox&bin=content"), body, cards=cards, search="?tab=inbox&bin=content")
    assert got["before"] == {"editor": False, "save": False, "label": "고쳐서 승인", "expanded": None}
    assert got["opened"] == {"editor": True, "save": True, "label": "고치기 닫기", "expanded": "true"}
    assert got["closed"] == {"editor": False, "save": False, "label": "고쳐서 승인", "expanded": "false"}
    assert got["sent"] == 0
    assert got["chips"] and not {"knowledge_right", "outside_right", "both_right"} & set(got["chips"])
    assert got["blocked"] == {"posts": 0, "status": "등급 B 제안이에요 — 핵심 값을 보고 확인 칸을 눌러 주세요."}
    assert got["applied"] == {"url": "/api/brain/proposals/20/apply",
                              "body": {"base_version": 1, "view_ms": 0, "confirm": {"field": "name", "value": "새 이름"}}}
    assert got["later"]["cards"] == ["c2"] and got["later"]["folded"] == ["c1"] and got["later"]["title"] == "나중에 볼 것 1개"
    assert got["later"]["nav"] == "1"
    assert got["later"]["view"] == {"title": "나중에 볼 것", "cards": ["c1"], "url": "/brain?tab=inbox&bin=later"}


@NODE
def test_t8_contract_counts_aside_and_ready_event(page, tmp_path):
    """T8 약속 — setCount('actions', n) 뒤 숫자 띠 · ds:inbox-ready(뿌리에서 위로) · openAside · closeAside · isPhone."""
    before = """document.body.addEventListener('ds:inbox-ready', function (e) {
      document.body.setAttribute('data-ready-view', e.detail.view); });"""
    after = """var api = window.FOMS_DS_INBOX;
      api.setCount('actions', 7);
      api.setCount('nope', 99);
      var note = document.createElement('p'); note.setAttribute('data-t8-detail', '1'); note.textContent = '제안 자세히';
      var aside = api.openAside(note);
      document.body.setAttribute('data-aside-open', String(!aside.hidden && !!aside.querySelector('[data-t8-detail]')));
      api.closeAside();
      document.body.setAttribute('data-aside-closed', String(aside.hidden && !aside.querySelector('[data-t8-detail]')));
      api.openAside(note);
      document.body.setAttribute('data-phone', String(api.isPhone()));"""
    body = """
      const b = api.root.parentNode;
      const out = { ready: b.getAttribute('data-ready-view'), mark: api.q('[data-ds-inbox]').getAttribute('data-ds-inbox-ready'),
                    aside: [b.getAttribute('data-aside-open'), b.getAttribute('data-aside-closed')],
                    phone: b.getAttribute('data-phone'),
                    strip: ['today', 'minutes', 'actions', 'knowledge'].map(k => api.text(api.q('[data-ds-inbox-stat="' + k + '"]'))),
                    actions: api.shown(api.q('[data-ds-inbox-stat="actions"]')) };
      out.again = api.shown(api.q('[data-ds-inbox-aside]'));
      return out;"""
    got = _run(page(), body, cards=_cards(content=4, decide=1, rules=2), before=before, after=after, tmp=tmp_path)
    assert got["ready"] == "inbox" and got["mark"] == "1" and got["aside"] == ["true", "true"] and got["phone"] == "false"
    assert got["strip"] == ["14", "6", "7", "7"] and got["actions"] is True and got["again"] is True

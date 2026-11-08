"""회사 지식 화면 다듬기 2차 — 일꾼 E(화면 JS · 템플릿, 사장님 11-08)를 node 로 실제 눌러 본다.

가짜 화면은 ``test_brain_fix_inbox_js`` 의 것(작은 HTML 읽개 · 고르개 · 사건 전달)을 그대로 쓰고, 실제 템플릿(tab_inbox.html ·
card_propose.html)을 Jinja 로 그려 넣는다. 유형 지도는 그림 라이브러리 자리에 가짜 모듈을 import() 시킨다.

- E1: ① · ④ 표 머리 첫 칸 = '모두 고르기' 체크 상자 — 쓸 수 있는 줄만 모두 켬/끔, 줄을 바꾸면 머리가 따라감(모두 · 일부 ·
  없음), 처음엔 꺼짐, 승인은 '체크한 줄 승인' → 확인 창 뒤에만.
- E2(F04): 확인 칸 글은 긴 값(글 칸 · 40자 넘음)이면 '<칸 이름> 확인했어요'까지만, 짧은 값은 값을 붙인다.
- E3(F25): 휴대폰 'PC 에서 결정해요' 줄의 '항목' → '지식' · '링크' → '연결'.
- E4(F20): 승인 대기 위 안내 '바로 바뀌고' · 셈 낱말 '개' · 한꺼번에 승인 실패 끝 '(카드로 하나씩 봐 주세요)'.
- E5(F16): '지우기 제안' 창 제목.
- E6(F18): 유형 지도 머리 '유형 N가지' = 지식 유형 수(표 · 칩 수와 같은 셈).
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from foms.services.brain.actions import specs
from foms.services.brain.browse import type_map_data
from foms.services.brain.constants import EXTERNAL_TYPES, TYPES
from foms.services.brain.display import display_table
from tests.domains.test_brain_fix_inbox_js import BULK, HARNESS, NODE, ROOT, SCRIPTS, _card, _inbox_html, _name_card

JS = ROOT / "static/js/brain"
ORIGINAL_BULK_REPLY = "{ applied: body.ids, failed: [] }"
# 한꺼번에 승인에서 input.fail 의 id 는 '못 함'으로 돌려주게(실패 글을 실제로 띄워 보려고)
FAILING_HARNESS = HARNESS.replace(ORIGINAL_BULK_REPLY, (
    "{ applied: body.ids.filter(i => !(input.fail || []).includes(i)),"
    " failed: body.ids.filter(i => (input.fail || []).includes(i)).map(i => ({ id: i })) }"))
CONFIRM_TWO = "체크한 2줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요)."
LONG_TEXT = "시공일은 실측 뒤 도면이 확정되면 담당 팀장이 손님과 통화해 정하고, 바뀌면 바로 알림톡으로 알려 드려요."

# 바뀐 상자를 실제 브라우저처럼 — 누르면 checked 가 바뀌고 change 가 위로 올라간다
TOGGLE = "const toggle = box => { box.checked = !box.checked; box.dispatchEvent({ type: 'change' }); };\n"


def _drive(body: str, *, html: str, attrs: dict, scripts: list, cards: list | None = None, phone: bool = False,
           search: str = "", confirm: list | None = None, fail: list | None = None):
    assert FAILING_HARNESS != HARNESS  # 가짜 한꺼번에 승인 답 꼴이 바뀌면 여기서 먼저 알린다
    payload = {"scripts": scripts, "html": html, "attrs": attrs, "cards": cards or [], "phone": phone, "search": search,
               "confirm": confirm or [], "fail": fail or [], "body": body}
    out = subprocess.run(["node", "-e", FAILING_HARNESS], input=json.dumps(payload, ensure_ascii=False),
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _inbox(body: str, *, cards: list, wide: str = "mark names", **kw):
    attrs = {"data-brain-page": "", "data-page-url": "/brain", "data-item-base": "/brain/items/", "data-start-tab": "inbox",
             "data-wide-bins": wide, "data-inbox-url": "/api/brain/inbox", "data-proposals-url": "/api/brain/proposals",
             "data-bulk-url": BULK, "data-display": json.dumps(display_table(), ensure_ascii=False),
             "data-actions": json.dumps(specs(), ensure_ascii=False)}
    return _drive(TOGGLE + body, html=_inbox_html(), attrs=attrs, scripts=SCRIPTS, cards=cards, **kw)


# ── E1 머리 '모두 고르기' ──────────────────────────────────────────────
@NODE
def test_head_box_selects_usable_rows_follows_rows_and_approval_still_needs_the_confirm():
    cards = [_name_card(1), _name_card(2), _name_card(3, bulk_ok=False)]  # 셋째 줄은 막힘(disabled)
    body = """
      const all = api.q('[data-brain-check-all]');
      const rows = () => api.qa('[data-brain-row-check]');
      const look = () => ({ all: all.checked, half: !!all.indeterminate, rows: rows().map(b => b.checked) });
      const first = Object.assign(look(), {
        label: all.getAttribute('aria-label'), type: all.getAttribute('type'), disabled: all.disabled,
        inHeadFirst: api.q('[data-brain-inbox] thead th').contains(all),
        head: api.qa('[data-brain-inbox] thead th').map(th => api.text(th)),
        buttons: api.qa('[data-brain-inbox] button').length, rowDisabled: rows().map(b => b.disabled) });
      toggle(all);
      const on = look();
      toggle(rows()[1]);
      const some = look();
      toggle(all);
      const fill = look();
      toggle(all);
      const off = look();
      toggle(rows()[0]);
      const one = look();
      toggle(rows()[1]);
      const both = look();
      const sentByBoxes = api.posts.length;
      await api.click(api.q('[data-brain-table-apply]'));
      const cancelled = { confirms: api.confirms.slice(), posts: api.posts.length };
      api.answers.push(true);
      await api.click(api.q('[data-brain-table-apply]'));
      return { first, on, some, fill, off, one, both, sentByBoxes, cancelled, posts: api.posts };"""
    got = _inbox(body, cards=cards, search="?tab=inbox&bin=names")
    first = got["first"]
    assert (first["label"], first["type"], first["disabled"], first["inHeadFirst"]) == ("모두 고르기", "checkbox", False, True)
    assert first["head"] == ["", "지금 이름", "새 한글 이름", "비슷한 말"]  # 칸 수는 그대로 넷 — '승인' 글 자리만 상자로
    assert first["buttons"] == 1  # 새 단추 없음('체크한 줄 승인' 하나)
    assert first["rowDisabled"] == [False, False, True]
    assert (first["all"], first["half"], first["rows"]) == (False, False, [False, False, False])  # 처음엔 꺼짐(F24)
    assert got["on"] == {"all": True, "half": False, "rows": [True, True, False]}  # 막힌 줄은 안 바뀜
    assert got["some"] == {"all": False, "half": True, "rows": [True, False, False]}  # 일부 → 반쯤
    assert got["fill"] == {"all": True, "half": False, "rows": [True, True, False]}  # 반쯤에서 누르면 모두
    assert got["off"] == {"all": False, "half": False, "rows": [False, False, False]}  # 다시 누르면 모두 끔
    assert got["one"] == {"all": False, "half": True, "rows": [True, False, False]}
    assert got["both"] == {"all": True, "half": False, "rows": [True, True, False]}  # 쓸 수 있는 줄이 다 켜지면 머리도 켬
    assert got["sentByBoxes"] == 0  # 고르기만으로는 아무것도 안 보낸다
    assert got["cancelled"] == {"confirms": [CONFIRM_TWO], "posts": 0}  # 확인 창 취소 = 안 보냄
    assert got["posts"] == [{"url": BULK, "body": {"ids": [10, 20]}}]  # 확인 뒤에만 · 막힌 줄(30) 빠짐


@NODE
def test_mark_table_has_the_same_head_box_and_an_all_blocked_table_disables_it():
    body = """
      const all = api.q('[data-brain-check-all]');
      const head = api.qa('[data-brain-inbox] thead th').map(th => api.text(th));
      toggle(all);
      return { head, label: all.getAttribute('aria-label'), all: all.checked,
               rows: api.qa('[data-brain-row-check]').map(b => b.checked), posts: api.posts.length };"""
    got = _inbox(body, cards=[_card(1, "mark"), _card(2, "mark")], search="?tab=inbox&bin=mark")
    assert got == {"head": ["", "지식", "같은 값이 적힌 곳"], "label": "모두 고르기", "all": True, "rows": [True, True],
                   "posts": 0}
    blocked = """return { all: api.q('[data-brain-check-all]').disabled, apply: api.q('[data-brain-table-apply]').disabled };"""
    got = _inbox(blocked, cards=[_name_card(1, bulk_ok=False)], search="?tab=inbox&bin=names")
    assert got == {"all": True, "apply": True}  # 쓸 수 있는 줄이 없으면 머리 상자도 못 누른다


# ── E2 확인 칸 글 · E3 휴대폰 줄 ───────────────────────────────────────
def _grade_b(n: int, field: str, label: str, value: str) -> dict:
    card = _card(n, "content", bulk_ok=False, fields=[{"field": field, "label": label, "before": "옛 값", "after": value}])
    card["main"].update({"grade": "B", "confirm": {"field": field, "value": value}})
    return card


@NODE
def test_confirm_line_drops_long_values_and_keeps_short_ones():
    cards = [_grade_b(1, "text", "정책 글", LONG_TEXT), _grade_b(2, "payload.value", "값", "600"),
             _grade_b(3, "name", "이름", "가" * 41), _grade_b(4, "name", "이름", "나" * 40),
             _grade_b(5, "text", "정책 글", "짧은 글")]
    body = """return api.qa('[data-brain-inbox] .brain-prop__confirm').map(n => api.text(n));"""
    got = _inbox(body, cards=cards, search="?tab=inbox&bin=content")
    assert got == ["정책 글 확인했어요", "값 확인했어요: 600", "이름 확인했어요", "이름 확인했어요: " + "나" * 40,
                   "정책 글 확인했어요"]  # 글 칸은 짧아도 이름까지만 · 40자까지는 값을 붙인다
    assert all(LONG_TEXT not in line for line in got)


@NODE
def test_phone_pc_only_line_says_knowledge_and_connection():
    body = """return { hint: api.text(api.q('[data-brain-later] .brain-prop__hint')),
                       title: api.text(api.q('[data-brain-later-title]')) };"""
    got = _inbox(body, cards=[_card(1, "content", phone_ok=False)], phone=True, search="?tab=inbox&bin=content")
    assert got["hint"] == "이 제안은 PC 에서 결정해요(칸이 여럿이거나 새 지식 · 은퇴 · 지우기 · 연결)."
    assert got["title"] == "PC 에서 볼 것 1개"


# ── E4 위 안내 · 셈 낱말 · 실패 끝 글 ───────────────────────────────────
@NODE
def test_inbox_intro_and_counts_use_one_word_and_failures_point_to_cards():
    cards = [_card(1, "content"), _card(2, "content"), _card(3, "content")]
    body = """
      const intro = api.text(api.q('[data-brain-bins-intro]'));
      const bulk = api.q('[data-brain-bulk]');
      const before = api.text(bulk);
      await api.click(api.q('[data-card-id="c3"] [data-brain-act="later"]'));
      const later = { title: api.text(api.q('[data-brain-later-title]')), bulk: api.text(bulk) };
      api.answers.push(true);
      await api.click(bulk);
      return { intro, before, later, confirm: api.confirms[0], status: api.text(api.q('[data-brain-inbox-status]')) };"""
    got = _inbox(body, cards=cards, search="?tab=inbox&bin=content", fail=[20])
    assert got["intro"] == "승인하면 바로 바뀌고, 바뀌기 전 내용은 수정 기록에 남아요."
    assert got["before"] == "등급 A 모두 승인 (3개)"
    assert got["later"] == {"title": "나중에 볼 것 1개", "bulk": "등급 A 모두 승인 (2개)"}
    assert got["confirm"] == "등급 A 제안 2개를 한꺼번에 승인할까요?"
    assert got["status"] == "승인 1개 · 못 함 1개(카드로 하나씩 봐 주세요)"  # 표 쪽과 같은 끝 글


@NODE
def test_table_approval_result_counts_with_the_same_word():
    body = """
      toggle(api.q('[data-brain-check-all]'));
      api.answers.push(true);
      await api.click(api.q('[data-brain-table-apply]'));
      return api.text(api.q('[data-brain-inbox-status]'));"""
    got = _inbox(body, cards=[_name_card(1), _name_card(2)], search="?tab=inbox&bin=names", fail=[10])
    assert got == "승인 1개 · 못 함 1개(카드로 하나씩 봐 주세요)"


# ── E5 지식 카드 '지우기 제안' 창 ───────────────────────────────────────
@NODE
def test_delete_proposal_title_says_ai_and_staff_can_no_longer_use_it():
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    propose = [a for a in specs() if a["stage"] == "propose" and a["name"] != "item_rollback"]  # 카드 화면과 같은 고르기
    html = env.get_template("brain/partials/card_propose.html").render(
        it={"open_changes": [], "status": "active"}, propose=propose, props=[], display=display_table())
    attrs = {"data-brain-card": "", "data-brain-key": "common/x", "data-brain-version": "1", "data-current": "{}",
             "data-proposals-url": "/api/brain/proposals", "data-inbox-page": "/brain?tab=inbox"}
    scripts = [str(JS / name) for name in ("brain-view.js", "brain-dom.js", "brain-review-view.js", "brain-item-actions.js")]
    body = """
      const open = async name => { await api.click(api.q('[data-brain-propose-open="' + name + '"]'));
        return { title: api.text(api.q('[data-brain-propose-title]')), form: api.shown(api.q('[data-brain-propose-form]')),
                 fields: api.shown(api.q('[data-brain-propose-fields]')) }; };
      return { remove: await open('propose_delete'), retire: await open('propose_retire'), posts: api.posts.length };"""
    got = _drive(body, html=html, attrs=attrs, scripts=scripts)
    assert got["remove"] == {"title": "승인되면 이 지식을 AI · 직원이 더는 못 써요. 연결도 끊기고, 수정 기록은 남아요.",
                             "form": True, "fields": False}
    assert got["retire"]["title"] == "승인되면 AI 가 더는 쓰지 않아요."  # 대조군: 은퇴 제안 글은 그대로
    assert got["posts"] == 0  # 창을 열기만 했다


# ── E6 유형 지도 머리 수 ───────────────────────────────────────────────
MAP_HARNESS = r"""
const fs = require('fs');
const { pathToFileURL } = require('url');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
function node() {
  const n = { textContent: '', classes: new Set(), listeners: {}, firstChild: null,
    classList: { toggle: (c, on) => { if (on) n.classes.add(c); else n.classes.delete(c); }, add: c => n.classes.add(c),
                 remove: c => n.classes.delete(c) },
    addEventListener: (t, fn) => { (n.listeners[t] = n.listeners[t] || []).push(fn); } };
  return n;
}
const canvas = node();
const status = node();
const root = node();
root.querySelector = s => ({ '[data-brain-map-canvas]': canvas, '[data-brain-map-status]': status })[s] || null;
root.querySelectorAll = () => [];
global.document = { body: {}, createElement: () => node(), createTextNode: t => ({ textContent: t }) };
global.window = { getComputedStyle: () => ({ fontFamily: 'sans-serif' }) };
global.fetch = async () => ({ status: 200, json: async () => ({ success: true, data: input.map }) });
require(input.view);
require(input.dom);
window.FOMS_BRAIN_CTX = { root: root, display: input.map.display, fire() {},
  urls: { cytoscape: pathToFileURL(input.cy).href, dagre: pathToFileURL(input.dagre).href, typeMap: '/api/brain/type-map' } };
require(input.mapJs);
root.listeners['brain:tab'].forEach(fn => fn({ detail: { tab: 'map' } }));
const started = Date.now();
(function wait() {
  if (status.textContent.indexOf('가지') >= 0 || status.classes.has('is-error') || Date.now() - started > 8000) {
    const made = globalThis.__FAKE_CY_ELEMENTS || [];
    const nodes = made.filter(e => e.group === 'nodes');
    process.stdout.write(JSON.stringify({ status: status.textContent, error: status.classes.has('is-error'),
      typeNodes: nodes.filter(e => e.classes.split(' ').includes('brain-map-type')).length,
      groupNodes: nodes.filter(e => e.classes.split(' ').includes('brain-map-group')).length }));
    return;
  }
  setTimeout(wait, 10);
})();
"""

# 그림 라이브러리 자리 — 받은 요소로 고르개(.클래스) · filter · data() 만 흉내 낸다
FAKE_CYTOSCAPE = """
export default function cytoscape(opts) {
  globalThis.__FAKE_CY_ELEMENTS = opts.elements;
  const wrap = list => ({ length: list.length, filter: fn => wrap(list.filter((e, i) => fn(e, i))) });
  const nodes = opts.elements.filter(e => e.group === 'nodes')
    .map(e => ({ classes: (e.classes || '').split(' '), data: k => (k ? e.data[k] : e.data) }));
  return { nodes: sel => wrap(nodes.filter(n => n.classes.includes(sel.replace(/^\\./, '')))),
           on() {}, elements: () => ({ removeClass() {} }), resize() {}, fit() {} };
}
cytoscape.use = () => {};
"""


@NODE
def test_type_map_head_counts_knowledge_types_like_the_table_and_chips(tmp_path: Path):
    (tmp_path / "cytoscape.mjs").write_text(FAKE_CYTOSCAPE, encoding="utf-8")
    (tmp_path / "dagre.mjs").write_text("export default function dagre() {}\n", encoding="utf-8")
    data = type_map_data({})
    payload = {"map": data, "view": str(JS / "brain-view.js"), "dom": str(JS / "brain-dom.js"),
               "mapJs": str(JS / "brain-map.js"), "cy": str(tmp_path / "cytoscape.mjs"), "dagre": str(tmp_path / "dagre.mjs")}
    out = subprocess.run(["node", "-e", MAP_HARNESS], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    got = json.loads(out.stdout)
    chips = [t for g in data["groups"] for t in g["types"] if not t["external"]]  # 지도 목록에서 표로 가는 칩
    assert got["error"] is False
    assert got["status"] == f"유형 {len(TYPES)}가지 — 마우스를 올리면 선 이름이 보여요."
    assert len(TYPES) == len(chips) == 24  # 지식 표 '유형' 고르기(TYPES) · 지도 칩 수와 같은 셈
    # 대조군: 그림에는 바깥 정본 · 사본 마디와 묶음 마디가 같이 있다 — 그것까지 세면 31 이었다(F18)
    assert got["typeNodes"] == len(TYPES) + len(EXTERNAL_TYPES) == 31
    assert got["groupNodes"] == len(data["groups"])

"""'승인 대기' 화면 고치기(회사 지식 점검 11-08 — F24 · F05 · F06 · F07 · F08 · F27)를 node 로 실제 돌려 본다.

가짜 DOM(작은 HTML 읽개 · 고르개 · 사건 전달) 위에 화면이 싣는 차례 그대로 brain-view · dom · page · review-view · 카드 ·
묶음 · 표 · 질문 · 제안함 스크립트를 싣고, 실제 템플릿(tab_inbox.html)을 Jinja 로 그려 넣는다. fetch · confirm · 주소 바꾸기는
가짜로 받아 적는다.

- F24: ① · ④ 표의 줄은 처음에 체크가 꺼져 있다 · '체크한 줄 승인' 한 단추 · 확인 창 하나(취소면 아무것도 안 보냄).
- F05: 휴대폰 폭에서 승인할 수 없는 카드는 처음부터 'PC 에서 볼 것' 접힘 칸에(③ 질문은 그대로 · PC 는 그대로).
- F06: 휴대폰 폭 탭 줄은 감싼다(옆으로 밀기 없음) — CSS.
- F07: 연 묶음이 주소(?tab=inbox&bin=)에 적히고, 그 주소로 들어오면 그 묶음 · 없거나 빈 묶음이면 목록.
- F08: '고쳐서 승인'을 누르면 '고치기 닫기'로 남고, 다시 누르면 닫힌다.
- F27: 결정할 것이 0이면(표 묶음이 없는 사람 포함) 빈 표 · 단추를 그리지 않는다.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import Environment, FileSystemLoader

from foms.services.brain.actions import specs
from foms.services.brain.display import display_table

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = [str(ROOT / "static/js/brain" / name) for name in (
    "brain-view.js", "brain-dom.js", "brain-page.js", "brain-review-view.js", "brain-inbox-card.js", "brain-inbox-bins.js",
    "brain-inbox-table.js", "brain-inbox-question.js", "brain-inbox.js")]
CSS = ROOT / "static/css/contexts/brain/brain.css"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
BULK = "/api/brain/proposals/bulk-apply"
CONFIRM_ONE = "체크한 1줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요)."

HARNESS = r"""
const vm = require('vm');
const fs = require('fs');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const VOID = new Set(['input', 'br', 'img', 'hr', 'meta', 'link']);

class Text {
  constructor(t) { this.nodeType = 3; this.data = String(t); this.parentNode = null; }
  get textContent() { return this.data; }
}

/** 고르개 한 마디(꼬리표 · #id · .클래스 · [속성] · [속성="값"]). */
function compound(sel) {
  const m = /^([a-zA-Z][\w-]*)?((?:#[\w-]+|\.[\w-]+|\[[^\]]+\])*)$/.exec(sel);
  if (!m) throw new Error('고르개 못 읽음: ' + sel);
  const out = { tag: m[1] ? m[1].toUpperCase() : null, ids: [], classes: [], attrs: [] };
  const re = /#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:="([^"]*)")?\]/g;
  let a;
  while ((a = re.exec(m[2] || ''))) {
    if (a[1]) out.ids.push(a[1]); else if (a[2]) out.classes.push(a[2]); else out.attrs.push([a[3], a[4]]);
  }
  return out;
}

function hit(node, c) {
  if (!node || node.nodeType !== 1) return false;
  if ((c.tag && c.tag !== node.tagName) || c.ids.some(i => i !== node.id)) return false;
  if (c.classes.some(k => !node.classList.contains(k))) return false;
  return c.attrs.every(([k, v]) => k in node.attrMap && (v === undefined || node.attrMap[k] === v));
}

class CustomEvent {
  constructor(type, init) { this.type = type; this.detail = (init || {}).detail; this.target = null; }
  preventDefault() {}
}

class El {
  constructor(tag) {
    this.nodeType = 1; this.tagName = tag.toUpperCase(); this.childNodes = []; this.attrMap = {}; this.parentNode = null;
    this.listeners = {}; this.disabled = false; this.checked = false; this.value = '';
  }
  get className() { return this.attrMap['class'] || ''; }
  set className(v) { this.attrMap['class'] = String(v); }
  get id() { return this.attrMap.id || ''; }
  get hidden() { return 'hidden' in this.attrMap; }
  set hidden(v) { if (v) this.attrMap.hidden = ''; else delete this.attrMap.hidden; }
  get classList() {
    const self = this;
    const list = () => self.className.split(/\s+/).filter(Boolean);
    const set = (c, on) => { const rest = list().filter(x => x !== c); self.className = (on ? rest.concat([c]) : rest).join(' '); };
    return { contains: c => list().includes(c), add: c => set(c, true), remove: c => set(c, false),
             toggle: (c, force) => { const on = force === undefined ? !list().includes(c) : !!force; set(c, on); return on; } };
  }
  setAttribute(k, v) { this.attrMap[k] = String(v); }
  getAttribute(k) { return k in this.attrMap ? this.attrMap[k] : null; }
  hasAttribute(k) { return k in this.attrMap; }
  removeAttribute(k) { delete this.attrMap[k]; }
  get firstChild() { return this.childNodes[0] || null; }
  get children() { return this.childNodes.filter(n => n.nodeType === 1); }
  appendChild(n) { if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this; this.childNodes.push(n); return n; }
  removeChild(n) { const i = this.childNodes.indexOf(n); if (i >= 0) this.childNodes.splice(i, 1); n.parentNode = null; return n; }
  get textContent() { return this.childNodes.map(n => n.textContent).join(''); }
  set textContent(v) {
    this.childNodes.forEach(n => { n.parentNode = null; });
    this.childNodes = [];
    if (String(v)) this.appendChild(new Text(v));
  }
  matches(sel) {
    return sel.split(',').some(part => {
      const chain = part.trim().split(/\s+/).map(compound);  // 자손 고르개(빈칸)만 — 오른쪽부터 조상으로
      if (!hit(this, chain[chain.length - 1])) return false;
      let n = this.parentNode;
      for (let i = chain.length - 2; i >= 0; i -= 1) {
        while (n && n.nodeType === 1 && !hit(n, chain[i])) n = n.parentNode;
        if (!n || n.nodeType !== 1) return false;
        n = n.parentNode;
      }
      return true;
    });
  }
  closest(sel) { for (let n = this; n && n.nodeType === 1; n = n.parentNode) if (n.matches(sel)) return n; return null; }
  querySelectorAll(sel) {
    const out = [];
    const walk = n => n.children.forEach(c => { if (c.matches(sel)) out.push(c); walk(c); });
    walk(this);
    return out;
  }
  querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
  contains(n) { for (; n; n = n.parentNode) if (n === this) return true; return false; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  dispatchEvent(ev) {
    if (!ev.target) ev.target = this;
    for (let n = this; n; n = n.parentNode) (n.listeners[ev.type] || []).forEach(fn => fn.call(n, ev));
    return true;
  }
  focus() { doc.activeElement = this; }
}

const doc = {
  activeElement: null, listeners: {}, body: new El('body'),
  createElement: t => new El(t), createTextNode: t => new Text(t),
  querySelector: s => doc.body.querySelector(s), querySelectorAll: s => doc.body.querySelectorAll(s),
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); },
};

function decode(s) {
  return s.replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").replace(/&amp;/g, '&');
}

function parseInto(parent, html) {
  const re = /<!--[\s\S]*?-->|<\/([a-zA-Z0-9]+)\s*>|<([a-zA-Z0-9]+)((?:\s+[^\s=>]+(?:="[^"]*")?)*)\s*\/?>|([^<]+)/g;
  let cur = parent;
  let m;
  while ((m = re.exec(html))) {
    if (m[1]) {
      let n = cur;
      while (n && n !== parent && n.tagName !== m[1].toUpperCase()) n = n.parentNode;
      if (n && n !== parent) cur = n.parentNode;
    } else if (m[2]) {
      const node = new El(m[2]);
      const are = /([^\s=]+)(?:="([^"]*)")?/g;
      let a;
      while ((a = are.exec(m[3] || ''))) node.setAttribute(a[1], decode(a[2] === undefined ? '' : a[2]));
      cur.appendChild(node);
      if (!VOID.has(m[2].toLowerCase())) cur = node;
    } else if (m[4] && m[4].trim()) {
      cur.appendChild(new Text(decode(m[4])));
    }
  }
}

const urls = [];
const posts = [];
const confirms = [];
const answers = (input.confirm || []).slice();
let cards = input.cards;
const win = {
  matchMedia: () => ({ matches: !!input.phone, addEventListener() {} }),
  performance: { now: () => 1000 },
  location: { search: input.search || '' },
  history: { replaceState(state, title, url) { urls.push(url); } },
  confirm(text) { confirms.push(text); return answers.length ? answers.shift() : false; },
};
async function fakeFetch(url, init) {
  const method = (init && init.method) || 'GET';
  let data;
  if (method === 'GET') {
    data = { cards: cards };
  } else {
    const body = JSON.parse(init.body);
    posts.push({ url: url, body: body });
    data = url === input.attrs['data-bulk-url'] ? { applied: body.ids, failed: [] } : { message: '했어요.' };
  }
  return { status: 200, json: async () => ({ success: true, data: data }) };
}

(async () => {
  const root = new El('div');
  Object.keys(input.attrs).forEach(k => root.setAttribute(k, input.attrs[k]));
  parseInto(root, input.html);
  doc.body.appendChild(root);
  const context = vm.createContext({ window: win, document: doc, fetch: fakeFetch, CustomEvent: CustomEvent,
                                     URLSearchParams: URLSearchParams, console: console });
  for (const file of input.scripts) vm.runInContext(fs.readFileSync(file, 'utf8'), context, { filename: file });
  const flush = async () => { for (let i = 0; i < 10; i += 1) await new Promise(r => setTimeout(r, 0)); };
  (doc.listeners.DOMContentLoaded || []).forEach(fn => fn());
  await flush();
  const api = {
    root: root, urls: urls, posts: posts, confirms: confirms, answers: answers,
    q: s => root.querySelector(s), qa: s => root.querySelectorAll(s),
    text: n => (n ? n.textContent.replace(/\s+/g, ' ').trim() : null),
    shown: n => { if (!n) return false; for (; n && n !== root; n = n.parentNode) if (n.hidden) return false; return true; },
    ids: s => root.querySelectorAll(s + ' [data-card-id]').map(n => n.getAttribute('data-card-id')),
    click: async n => { n.dispatchEvent(new CustomEvent('click')); await flush(); },
    tab: async name => { root.querySelector('[data-brain-tab="' + name + '"]').dispatchEvent(new CustomEvent('shown.bs.tab')); await flush(); },
  };
  const AsyncFunction = Object.getPrototypeOf(async function () {}).constructor;
  const out = await new AsyncFunction('api', input.body)(api);
  process.stdout.write(JSON.stringify(out));
})().catch(error => { process.stderr.write(String(error && error.stack || error)); process.exit(1); });
"""


def _inbox_html() -> str:
    env = Environment(loader=FileSystemLoader(str(ROOT / "templates")), autoescape=True)
    pane = env.get_template("brain/partials/tab_inbox.html").render(tab="inbox")
    tabs = ('<button type="button" data-brain-tab="inbox">승인 대기 <span data-brain-count="inbox">0</span></button>'
            '<button type="button" data-brain-tab="search">지식 찾기</button>')
    return tabs + pane


def _run(body: str, *, cards: list, wide: str = "", phone: bool = False, search: str = "", tab: str = "inbox",
         confirm: list | None = None):
    attrs = {"data-brain-page": "", "data-page-url": "/brain", "data-item-base": "/brain/items/", "data-start-tab": tab,
             "data-wide-bins": wide, "data-inbox-url": "/api/brain/inbox", "data-proposals-url": "/api/brain/proposals",
             "data-bulk-url": BULK, "data-display": json.dumps(display_table(), ensure_ascii=False),
             "data-actions": json.dumps(specs(), ensure_ascii=False)}
    payload = {"scripts": SCRIPTS, "html": _inbox_html(), "attrs": attrs, "cards": cards, "phone": phone, "search": search,
               "confirm": confirm or [], "body": body}
    out = subprocess.run(["node", "-e", HARNESS], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _card(n: int, bin_: str, *, phone_ok: bool = True, bulk_ok: bool = True, stale: bool = False,
          fields: list | None = None) -> dict:
    main = {"id": n * 10, "op": "update", "grade": "A", "ai": False, "action": None, "proposer": "사장님", "reason": "까닭",
            "photos": [], "evidence": [], "fields": fields or [{"field": "name", "before": "옛 이름", "after": "새 이름"}],
            "edit_extra": [], "base_version": 1, "base": {"changed": stale, "current": 2 if stale else 1}, "gates": [],
            "meaning": "", "confirm": None, "phone_ok": phone_ok, "bulk_ok": bulk_ok, "rollback_of": None, "link": None,
            "created_at": "2026-11-08 10:00", "sentence": "직원이 알게 될 글", "visible_to": "", "prices": [], "about": []}
    return {"id": f"c{n}", "type": "lesson", "key": f"key-{n}", "name": f"key-{n}", "title": f"지식 {n}", "exists": True,
            "bin": bin_, "main": main, "attached": [], "similar": None, "touches": None, "copies": 0}


def _name_card(n: int, *, bulk_ok: bool = True) -> dict:
    return _card(n, "names", bulk_ok=bulk_ok, phone_ok=False, fields=[
        {"field": "payload.pref_label", "before": None, "after": f"한글 이름 {n}"},
        {"field": "payload.aliases", "before": None, "after": ["가", "나"]}])


@NODE
def test_nothing_to_decide_draws_no_empty_table_or_button():
    """F27 — 표 묶음이 없는 사람(도면팀장 · data-wide-bins 빈 글)은 빈 ④ 표 · '0개 모두 승인' 단추가 떴다.

    원인: ``''.split(' ')`` 이 ``['']`` 라 묶음 목록(openBin '')이 표 묶음으로 읽혔다."""
    body = """return {
      table: api.qa('[data-brain-inbox] table').length, apply: api.qa('[data-brain-table-apply]').length,
      list: api.q('[data-brain-inbox]').children.length, status: api.text(api.q('[data-brain-inbox-status]')),
      intro: api.shown(api.q('[data-brain-bins-intro]')), note: api.shown(api.q('[data-brain-phone-note]')),
      bins: api.qa('[data-brain-bin-open]').map(b => b.getAttribute('data-brain-bin-open')) };"""
    for wide in ("", "mark names"):  # 도면팀장 · 관리자 모두 0개
        got = _run(body, cards=[], wide=wide)
        assert got == {"table": 0, "apply": 0, "list": 0, "status": "승인 대기가 없어요.", "intro": False, "note": False,
                       "bins": []}, wide
    # 표 묶음이 없는 사람에게 ② 카드가 있으면 묶음 목록만(목록 아래 빈 표 없음)
    got = _run(body, cards=[_card(1, "content")], wide="")
    assert got["table"] == 0 and got["apply"] == 0 and got["list"] == 0 and got["bins"] == ["content"]
    assert got["intro"] is True and got["status"] == ""


@NODE
def test_name_table_rows_start_unchecked_and_one_confirm_guards_the_approval():
    """F24 — 줄은 처음에 꺼진 채 · 체크 0이면 '체크한 줄이 없어요.' · 확인 창 취소면 안 보냄 · 확인이면 체크한 줄만."""
    cards = [_name_card(1), _name_card(2), _name_card(3, bulk_ok=False)]
    body = """
      const boxes = () => api.qa('[data-brain-row-check]');
      const button = api.q('[data-brain-table-apply]');
      const first = { checked: boxes().map(b => b.checked), disabled: boxes().map(b => b.disabled),
                      label: api.text(button), summary: api.text(api.q('[data-brain-inbox] .brain-icard__summary')) };
      await api.click(button);
      const none = { status: api.text(api.q('[data-brain-table-status]')), confirms: api.confirms.length, posts: api.posts.length };
      boxes()[0].checked = true;
      await api.click(button);
      const cancelled = { confirms: api.confirms.slice(), posts: api.posts.length };
      boxes()[0].checked = true;
      boxes()[1].checked = true;
      api.q('[data-brain-row-name="20"]').value = '고친 한글 이름';
      api.answers.push(true);
      await api.click(api.q('[data-brain-table-apply]'));
      return { first: first, none: none, cancelled: cancelled, last: api.confirms[api.confirms.length - 1], posts: api.posts };"""
    got = _run(body, cards=cards, wide="mark names", search="?tab=inbox&bin=names")
    assert got["first"]["checked"] == [False, False, False]
    assert got["first"]["disabled"] == [False, False, True]  # 쓸 수 있는지는 disabled 로만
    assert got["first"]["label"] == "체크한 줄 승인"
    assert got["first"]["summary"].endswith("체크한 줄만 승인해요.")
    assert got["none"] == {"status": "체크한 줄이 없어요.", "confirms": 0, "posts": 0}
    assert got["cancelled"] == {"confirms": [CONFIRM_ONE], "posts": 0}  # 취소 = 아무것도 안 보냄
    assert got["last"] == "체크한 2줄을 승인할까요? 승인하면 바로 바뀌어요(수정 기록은 남아요)."
    assert got["posts"][0] == {"url": BULK, "body": {"ids": [10]}}  # 안 고친 줄만 한꺼번에(끈 줄 · 막힌 줄 빠짐)
    assert got["posts"][1]["url"] == "/api/brain/proposals/20/apply"
    assert got["posts"][1]["body"]["edits"] == {"payload.pref_label": "고친 한글 이름"}
    assert len(got["posts"]) == 2


@NODE
def test_mark_table_uses_the_same_checked_rows_button():
    """F24 — ④ 단추도 'N개 모두 승인' 이 아니라 '체크한 줄 승인'(끈 줄은 빠진다)."""
    cards = [_card(1, "mark"), _card(2, "mark")]
    body = """return { label: api.text(api.q('[data-brain-table-apply]')), disabled: api.q('[data-brain-table-apply]').disabled,
                       checked: api.qa('[data-brain-row-check]').map(b => b.checked) };"""
    got = _run(body, cards=cards, wide="mark names", search="?tab=inbox&bin=mark")
    assert got == {"label": "체크한 줄 승인", "disabled": False, "checked": [False, False]}


@NODE
def test_phone_folds_cards_it_cannot_decide_into_the_pc_box():
    """F05 — 휴대폰: 승인 단추가 없는 카드(칸 여럿 · 기준 판 바뀜)는 처음부터 'PC 에서 볼 것' · ③ 질문 · PC 는 그대로."""
    content = [_card(1, "content"), _card(2, "content", phone_ok=False), _card(3, "content", stale=True)]
    body = """return { list: api.ids('[data-brain-inbox]'), later: api.ids('[data-brain-later]'),
                       box: api.shown(api.q('[data-brain-later-box]')), title: api.text(api.q('[data-brain-later-title]')) };"""
    phone = _run(body, cards=content, phone=True, search="?tab=inbox&bin=content")
    assert phone == {"list": ["c1"], "later": ["c2", "c3"], "box": True, "title": "PC 에서 볼 것 2개"}
    pc = _run(body, cards=content, phone=False, search="?tab=inbox&bin=content")
    assert pc["list"] == ["c1", "c2", "c3"] and pc["later"] == [] and pc["box"] is False
    question = _run(body, cards=[_card(4, "decide", phone_ok=False)], phone=True, search="?tab=inbox&bin=decide")
    assert question["list"] == ["c4"] and question["later"] == [] and question["box"] is False


@NODE
def test_open_bin_is_kept_in_the_address_and_reopened_from_it():
    """F07 — 주소의 bin 으로 그 묶음을 열고, 열고 닫을 때 · 탭을 갔다 와도 주소가 맞다. 없는 · 빈 bin 은 목록."""
    cards = [_card(1, "content"), _card(2, "names")]
    body = """
      const state = () => ({ open: api.shown(api.q('[data-brain-binbar]')), bins: api.shown(api.q('[data-brain-bins]')),
                             title: api.text(api.q('[data-brain-bin-title]')), url: api.urls[api.urls.length - 1] });
      const start = state();
      await api.click(api.q('[data-brain-bin-back]'));
      const back = state();
      await api.click(api.q('[data-brain-bin-open="names"]'));
      const names = state();
      await api.tab('search');
      const search = api.urls[api.urls.length - 1];
      await api.tab('inbox');
      return { start: start, back: back, names: names, search: search, again: state() };"""
    got = _run(body, cards=cards, search="?tab=inbox&bin=content")
    assert got["start"] == {"open": True, "bins": False, "title": "② 새로 들어가거나 바뀌는 지식 · 1개",
                            "url": "/brain?tab=inbox&bin=content"}
    assert got["back"]["open"] is False and got["back"]["bins"] is True and got["back"]["url"] == "/brain?tab=inbox"
    assert got["names"]["open"] is True and got["names"]["url"] == "/brain?tab=inbox&bin=names"
    assert got["search"] == "/brain?tab=search"
    assert got["again"]["open"] is True and got["again"]["url"] == "/brain?tab=inbox&bin=names"
    plain = """return { open: api.shown(api.q('[data-brain-binbar]')), url: api.urls[api.urls.length - 1] };"""
    for search in ("?tab=inbox&bin=zzz", "?tab=inbox&bin=mark", "?tab=inbox&bin=content2"):  # 없는 묶음 · 빈 묶음
        assert _run(plain, cards=cards, search=search) == {"open": False, "url": "/brain?tab=inbox"}, search


@NODE
def test_edit_button_stays_and_toggles_between_open_and_close():
    """F08 — '고쳐서 승인' → 칸 열림 · 단추는 남아 '고치기 닫기' → 다시 누르면 닫히고 글이 돌아온다."""
    body = """
      const start = api.q('[data-brain-act="edit"]');
      const look = () => ({ editor: api.shown(api.q('[data-brain-edit-box]')),
                            save: api.shown(api.q('[data-brain-act="edit-apply"]')), start: api.shown(start),
                            label: api.text(start), expanded: start.getAttribute('aria-expanded') });
      const before = look();
      await api.click(start);
      const opened = look();
      await api.click(start);
      const closed = look();
      await api.click(start);
      return { before: before, opened: opened, closed: closed, reopened: look(), posts: api.posts.length };"""
    got = _run(body, cards=[_card(1, "content")], search="?tab=inbox&bin=content")
    assert got["before"] == {"editor": False, "save": False, "start": True, "label": "고쳐서 승인", "expanded": None}
    assert got["opened"] == {"editor": True, "save": True, "start": True, "label": "고치기 닫기", "expanded": "true"}
    assert got["closed"] == {"editor": False, "save": False, "start": True, "label": "고쳐서 승인", "expanded": "false"}
    assert got["reopened"]["label"] == "고치기 닫기" and got["reopened"]["editor"] is True
    assert got["posts"] == 0  # 열고 닫기만으로는 아무것도 안 보낸다


def test_phone_tab_row_wraps_instead_of_scrolling_sideways():
    """F06 — 휴대폰 폭에서 탭 줄은 감싼다(옆으로 밀기 없음). 글자 · 단추 크기는 그대로."""
    css = CSS.read_text(encoding="utf-8")
    phone = css[css.index("@media (max-width: 640px) {"):]
    phone = phone[:phone.index("\n}")]
    rule = re.search(r"\.brain-tabs \{([^}]*)\}", phone)
    assert rule and "flex-wrap: wrap" in rule.group(1)
    assert "overflow-x" not in rule.group(1) and "nowrap" not in rule.group(1)
    assert not re.search(r"\.brain-tabs[^{]*\{[^}]*font-size", css)  # 탭 글자 크기는 안 줄인다

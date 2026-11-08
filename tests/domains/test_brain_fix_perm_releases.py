"""판 탭(설계서 7.5 화면 6) — '바뀐 것 보기' 줄 이름 · 되돌리기 확인 줄(점검 F01 일부 · F09).

- 서버 :func:`foms.services.brain.release_view.release_diff` 의 줄마다 화면 이름(``title`` · ``link_to_title``)은 카드 제목과
  같은 규칙 — 실음 칸 한글 이름(``pref_label``)이 있으면 그것, 없으면 이름(대조군: 한글 이름이 없는 항목은 이름 그대로).
- 화면 스크립트(static/js/brain/brain-releases.js)를 가짜 DOM 으로 실제로 돌려(node) 줄 글이 한글 이름을 쓰는지, 층 되돌리기
  확인 줄에 무엇이 되돌아가는지 한 줄(:mod:`foms.services.brain.rollback` 의 실제 동작)이 보이는지 본다.
합성 항목 · 합성 계정만.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from sqlalchemy import select

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.release_view import release_diff, release_page, shown_name
from foms.services.brain.scope import viewer_of
from tests.support.brain_screen_support import people
from tests.support.brain_support import create, link

ROOT = Path(__file__).resolve().parents[2]
RELEASES_JS = ROOT / "static/js/brain/brain-releases.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


def test_shown_name_prefers_a_korean_label_like_the_card_title():
    assert shown_name("시공일 확정 시점", "install-date-confirm") == "시공일 확정 시점"
    assert shown_name("  ", "install-date-confirm") == "install-date-confirm"  # 빈 한글 이름은 이름(대조군)
    assert shown_name(None, "plain") == "plain" and shown_name(7, "plain") == "plain"


def test_release_diff_rows_carry_the_korean_label_first(app):
    admin = people(db_session)["admin"]
    create(db_session, admin, "common/install-date", name="install-date-confirm",
           payload={"pref_label": "시공일 확정 시점"})
    create(db_session, admin, "common/plain", name="plain-name")
    create(db_session, admin, "common/fit-rule", item_type="spec", name="fit-rule",
           payload={"pref_label": "문짝 맞춤 규격"})
    link(db_session, admin, "applies_to", "common/fit-rule", "common/install-date")
    db_session.commit()
    number = db_session.execute(select(BrainChange.release_no).where(
        BrainChange.item_key == "common/install-date")).scalar_one()
    diff = release_diff(db_session, viewer_of(admin), number)
    rows = {(c["op"], c["key"]): c for layer in diff["layers"] for c in layer["changes"]}
    labelled = rows[("create", "common/install-date")]
    assert (labelled["title"], labelled["name"]) == ("시공일 확정 시점", "install-date-confirm")  # 이름은 그대로 남김
    assert rows[("create", "common/plain")]["title"] == "plain-name"  # 한글 이름 없음 → 이름(대조군)
    joined = rows[("link_add", "common/fit-rule")]
    assert (joined["title"], joined["link_to_title"]) == ("문짝 맞춤 규격", "시공일 확정 시점")
    assert (joined["name"], joined["link_to_name"]) == ("fit-rule", "install-date-confirm")
    page = release_page(db_session, viewer_of(admin))  # 같은 부분 질의(칸 하나 더함)로 판 목록도 그대로 센다
    assert page["items"][0]["number"] == number and page["items"][0]["layers"][0]["total"] == 4


BOOT = r"""
const vm = require('vm');
const fs = require('fs');
function Node(tag) {
  this.tag = tag; this.children = []; this.attrs = {}; this.listeners = {}; this.hidden = false; this.disabled = false;
  this.textContent = ''; this.className = '';
}
Node.prototype.appendChild = function (child) { this.children.push(child); return child; };
Node.prototype.setAttribute = function (name, value) { this.attrs[name] = String(value); };
Node.prototype.getAttribute = function (name) { return name in this.attrs ? this.attrs[name] : null; };
Node.prototype.addEventListener = function (type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); };
Node.prototype.focus = function () {};
Node.prototype.fire = function (type, event) { return Promise.all((this.listeners[type] || []).map((fn) => fn(event))); };
function el(tag, o) {
  const node = new Node(tag);
  o = o || {};
  if (o.cls) node.className = o.cls;
  if (o.text !== undefined && o.text !== null) node.textContent = String(o.text);
  Object.keys(o.attrs || {}).forEach((name) => node.setAttribute(name, o.attrs[name]));
  (o.children || []).forEach((child) => node.appendChild(child));
  return node;
}
function walk(node, out) { out.push(node); node.children.forEach((c) => walk(c, out)); return out; }
const data = JSON.parse(process.argv[2]);
const parts = { '[data-brain-releases]': new Node('ul') };
const root = new Node('div');
root.attrs['data-is-admin'] = '1';
root.querySelector = (sel) => parts[sel] || new Node('span');
const window = {
  FOMS_BRAIN_CTX: { root: root, urls: { releases: '/api/brain/releases' },
                    display: { ops: { create: '새로 만듦', link_add: '링크 더함' }, layers: { common: '공통 바탕' } },
                    actions: [{ name: 'release_rollback', label: '판 되돌리기' }] },
  FOMS_BRAIN_DOM: { el: el, clear: (n) => { n.children = []; }, setStatus: (n, t) => { n.textContent = t || ''; },
                    getJson: async (url) => ({ ok: true, data: url.indexOf('?') >= 0 ? data.page : data.diff }),
                    postJson: async () => ({ ok: true, data: { message: '' } }) },
  FOMS_BRAIN_VIEW: { linkInfo: () => ({ label: '적용' }), countsText: () => '새로 만듦 3',
                     pager: () => ({ hasPrev: false, hasNext: false }) },
  FOMS_BRAIN_REVIEW: { actionLabel: (actions, name) => actions.filter((a) => a.name === name)[0].label,
                       rollbackText: () => '' },
};
vm.runInContext(fs.readFileSync(process.argv[1], 'utf8'), vm.createContext({ window: window, console: console }));
(async () => {
  const settle = () => new Promise((done) => setTimeout(done, 0));
  await root.fire('brain:tab', { detail: { tab: 'releases' } });
  await settle();
  const nodes = () => walk(parts['[data-brain-releases]'], []);
  const buttons = nodes().filter((n) => n.tag === 'button');
  const ask = nodes().filter((n) => n.className === 'brain-release__ask')[0];
  const before = ask.hidden;
  await buttons.filter((b) => b.textContent === '이 층 판 되돌리기')[0].fire('click');
  const note = ask.children[0];
  const yes = ask.children.filter((n) => n.tag === 'button')[0];
  await buttons.filter((b) => b.textContent === '바뀐 것 보기')[0].fire('click');
  await settle();
  const lines = nodes().filter((n) => n.tag === 'li' && !n.className).map((n) => n.textContent);
  process.stdout.write(JSON.stringify({ before: before, after: ask.hidden, note: note.textContent,
    noteId: note.getAttribute('id'), describedBy: yes.getAttribute('aria-describedby'), yes: yes.textContent,
    lines: lines }));
})().catch((err) => { process.stderr.write(String(err && err.stack || err)); process.exit(1); });
"""


@NODE
def test_release_screen_uses_korean_names_and_says_what_rollback_undoes():
    data = {"page": {"items": [{"number": 7, "day": "2026-11-02", "import": False,
                                "layers": [{"layer": "common", "counts": {"create": 3}, "total": 3, "rollback": None}]}],
                     "total": 1, "page": 1, "pages": 1, "per_page": 10},
            "diff": {"number": 7, "layers": [{"layer": "common", "total": 3, "more": 0, "changes": [
                {"op": "create", "key": "common/install-date", "name": "install-date-confirm", "title": "시공일 확정 시점"},
                {"op": "create", "key": "common/plain", "name": "plain-name", "title": "plain-name"},
                {"op": "link_add", "key": "common/fit-rule", "name": "fit-rule", "title": "문짝 맞춤 규칙",
                 "link_kind": "applies_to", "link_to": "common/install-date", "link_to_name": "install-date-confirm",
                 "link_to_title": "시공일 확정 시점"}]}]}}
    out = subprocess.run(["node", "-e", BOOT, str(RELEASES_JS), json.dumps(data, ensure_ascii=False)],
                         capture_output=True, text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-600:]
    got = json.loads(out.stdout)
    assert got["before"] is True and got["after"] is False  # 첫 누름은 확인 줄만 연다
    assert got["note"] == ("이 판에서 새로 만든 지식은 지워지고, 고친 · 은퇴한 · 지운 지식과 연결은 이 판 전으로 "
                           "돌아가요. 기록은 남아요.")
    assert got["describedBy"] == got["noteId"] and got["yes"] == "판 7 공통 바탕 되돌리기"
    assert got["lines"] == ["새로 만듦 · 시공일 확정 시점", "새로 만듦 · plain-name",
                            "링크 더함 · 적용: 문짝 맞춤 규칙 → 시공일 확정 시점"]
    assert not any("install-date" in line or "fit-rule" in line for line in got["lines"])  # 영어 키 · 이름이 안 보인다


def test_rollback_note_matches_what_the_rollback_service_does():
    """확인 줄의 말이 :mod:`.rollback` 의 실제 동작 차례와 같은 뜻인지 — 만든 것 = 지우기, 그 밖 = 앞 판 값, 링크는 빼고 다시 더하기,
    되돌림은 새 판 · 이력에 남음(이 문장이 바뀌면 이 시험도 같이 본다)."""
    from foms.services.brain import rollback
    doc = rollback.__doc__ or ""
    assert "만든 것은 지우기" in doc and "그 판 앞 판으로" in doc and "다시 더하기" in doc and "이력에 남는다" in doc
    script = RELEASES_JS.read_text(encoding="utf-8")
    assert "새로 만든 지식은 지워지고" in script and "이 판 전으로 돌아가요" in script and "기록은 남아요" in script
    assert "은퇴하고" not in script  # 만든 것은 은퇴가 아니라 지우기(propose_delete)다

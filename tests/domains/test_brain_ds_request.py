"""문장으로 고치기 화면(설계서 2026-11-18-brain-sentence-change 4절 · 11절 '화면' · D246 · D247 · D249) — 서버가 그리는 자리 · 권한 · 스위치.

- 승인 대기 맨 위 한 줄 칸 · '문장으로 고친 것' 목록 길: 쓸 수 있는 사람(스위치 켬 + 관리자 · 층 승인자)에게만. 스위치를 끄거나 쓸 수
  없는 팀장(영업)이면 칸 · 스크립트 · CSS 가 없고 목록 보기(?tab=requests)는 404. 스위치를 켜지 않은 지금 화면은 그대로.
- 물어보기의 [바뀐 내용으로 넣기]: 따로 누르는 단추(type=button · 처음엔 잠김 · form 보내기 단추가 아님) — 쓸 수 있는 사람에게만.
- 묶음 화면 /brain/requests/<번호>: 미리 보기(줄 · 칸별 전 → 후 · 까닭 · 상태 · [빼기] · 못 고치는 줄은 빼기 없음 + 까닭 · 꼭 같이 경고 ·
  [이대로 고치기] · [버리기] 확인) → 반영 뒤 같은 화면이 보고(고친 것 · 못 고친 것 · 코드를 고쳐야 하는 것 · 같이 볼 것 링크 ·
  [이 묶음 되돌리기] 확인 · 빈 갈래 없음) · 되물음(물음 · 답 칸) · 관리자만 돈 줄. 스위치 끔 · 쓸 수 없는 사람 · 남의 묶음 · 없는
  묶음은 404.
- 스크립트 구문(node --check)과 순수 계산(뺀 줄 · 목록 글).
합성 지식 · 합성 계정만(금액 · 손님 글 · 직원 이름 없음). 가짜 AI 로만.
"""

from __future__ import annotations

import html
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from db import db_session
from foms.services.brain import change_request as cr
from foms.services.graft_flags import FLAGS
from models import User
from tests.domains.test_brain_change_request import APPLY_AT, answer_text, lvl, start_and_run, upd, world
from tests.support.brain_chat_support import NOW_KST, chat_on, fixed

ROOT = Path(__file__).resolve().parents[2]
JS = [ROOT / "static/js/brain/ds" / name for name in ("ds-request.js", "ds-request-start.js", "ds-request-list.js")]
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
NEW_TEXT = "도면 담당은 도면팀이 스스로 정한다."
FULL_ANSWER = dict(
    updates=[upd("common/rule/assign", text=NEW_TEXT)],
    links=[{"op": "add", "kind": "excludes", "from": "common/door", "to": "common/slide", "why": "같이 못 함"},
           {"op": "add", "kind": "requires", "from": "common/rule/assign", "to": "no/such", "why": "필요"}],
    settings=[lvl("ops.assign_draftsman", 0)],
    needs_code=["밤 훑기 규칙 둘은 코드 상수라 사람이 끈다"],
    also_look=["common/door — 같이 볼 것"])


def _flags(monkeypatch, *, change=True):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    for short in ("brain_ui", "brain_change_request") if change else ("brain_ui",):
        monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")


@pytest.fixture
def who(app, monkeypatch):
    _flags(monkeypatch)
    ids = {name: user.id for name, user in world(db_session).items()}
    chat_on(db_session, stage="all")
    return ids


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _body(resp) -> str:
    return resp.get_data(as_text=True)


def _start(user_id, answer=None):
    """시작 → 분석 줄 일을 바로 부름(WORKER 대신 — :func:`tests.domains.test_brain_change_request.start_and_run`)."""
    return start_and_run(db_session.get(User, user_id), "도면 담당은 도면팀에서 정해",
                         client=fixed(answer_text(**(answer or FULL_ANSWER))), now=NOW_KST)


def _scripts(body: str) -> list[str]:
    return re.findall(r'<script src="/static/js/brain/(?:ds/)?([\w-]+\.js)\?v=[0-9a-f]{12}" defer></script>', body)


def _lines(body: str) -> list[tuple[str, str]]:
    return re.findall(r'data-ds-req-line="(\d+)" data-state="(\w+)"', body)


def _cut(body: str, start: str, end: str = "</form>") -> str:
    at = body.index(start)
    return body[at:body.index(end, at)]


# ── 승인 대기 맨 위 칸 · 목록 길 ───────────────────────────────────────────
def test_inbox_top_input_only_for_people_who_can_use_it(app, who):
    body = _body(_client(app, who["admin"]).get("/brain?tab=inbox"))
    form = _cut(body, "data-ds-req-form")
    assert 'data-start-url="/api/brain/change-requests"' in form and 'data-request-base="/brain/requests/"' in form
    assert 'placeholder="바뀐 내용을 적어 주세요"' in form and 'maxlength="800"' in form
    assert re.search(r'type="submit" data-ds-req-submit>.*분석</button>', form)
    assert 'href="/brain?tab=requests" data-ds-req-list-link' in form
    assert body.index("data-ds-req-form") < body.index("data-ds-inbox-status")  # 승인 대기 맨 위
    assert "ds-request-start.js" in _scripts(body) and "brain-ds-request.css?v=" in body
    assert 'style="' not in body and "<script>" not in body.split("</head>")[1]
    for name in ("dr_mgr", "cs_mgr"):  # 층 승인자 팀장도
        assert "data-ds-req-form" in _body(_client(app, who[name]).get("/brain?tab=inbox")), name
    assert "data-ds-req-form" not in _body(_client(app, who["admin"]).get("/brain?tab=releases"))  # 판 보기에는 없다


def test_inbox_has_no_input_when_switch_off_or_not_allowed(app, who, monkeypatch):
    sales = _client(app, who["sales_mgr"]).get("/brain?tab=inbox")  # 화면을 못 여는 팀장(영업)
    assert sales.status_code == 404 or "data-ds-req" not in _body(sales)
    listed = _client(app, who["sales_mgr"]).get("/brain?tab=requests")  # 물어보기만 여는 사람은 물어보기로 간다(목록 없음)
    assert listed.status_code in (302, 404) and "data-ds-reqs" not in _body(listed)
    _flags(monkeypatch, change=False)
    resp = _client(app, who["admin"]).get("/brain?tab=inbox")
    body = _body(resp)
    assert resp.status_code == 200 and "data-ds-req" not in body and "ds-request" not in body
    assert "brain-ds-request.css" not in body
    assert _client(app, who["admin"]).get("/brain?tab=requests").status_code == 404


def test_requests_view_lists_through_the_api(app, who):
    resp = _client(app, who["admin"]).get("/brain?tab=requests")
    body = _body(resp)
    assert resp.status_code == 200 and '<h1 class="f-h3 fb-pc-only">문장으로 고친 것</h1>' in body
    assert 'data-ds-reqs data-list-url="/api/brain/change-requests"' in body
    tones = json.loads(html.unescape(re.search(r'data-tones="([^"]+)"', body).group(1)))
    assert len({tuple(v) for v in tones.values()}) == len(tones) == 8  # 상태마다 다른 색
    assert "data-ds-req-list-link" not in body and "data-ds-req-form" in body  # 칸은 있고 목록 링크는 없다(지금 그 자리)
    assert _scripts(body)[-3:] == ["ds-request-list.js", "ds-inbox.js", "ds-request-start.js"]
    assert "ds-inbox-card.js" not in body


# ── 물어보기 [바뀐 내용으로 넣기] ─────────────────────────────────────────
def test_ask_page_has_a_separate_button_for_change(app, who, monkeypatch):
    body = _body(_client(app, who["admin"]).get("/brain?tab=ask"))
    form = _cut(body, "data-ds-ask-form")
    button = re.search(r'<button class="f-btn f-push" type="button" disabled data-ds-ask-change[^>]*>', form)
    assert button and 'data-start-url="/api/brain/change-requests"' in button.group(0)
    assert form.index("data-ds-ask-change") < form.index("data-ds-ask-submit")
    assert 'type="submit" data-ds-ask-submit' in form  # 묻기는 그대로 form 보내기
    assert _scripts(body)[-1] == "ds-request-start.js"
    staff = _body(_client(app, who["cs_staff"]).get("/brain/ask"))  # 물어보기만 여는 직원 — 단추 없음
    assert "data-ds-ask-form" in staff and "data-ds-ask-change" not in staff and "ds-request-start.js" not in staff
    _flags(monkeypatch, change=False)
    off = _body(_client(app, who["admin"]).get("/brain?tab=ask"))
    assert "data-ds-ask-change" not in off and "ds-request-start.js" not in off
    assert 'class="f-btn f-btn-primary f-push" type="submit" data-ds-ask-submit' in off  # 지금 모양 그대로


# ── 묶음 화면 ────────────────────────────────────────────────────────────
def test_bundle_page_preview_then_report_then_revert(app, who):
    admin = who["admin"]
    view = _start(admin)
    assert view["status"] == "ready"
    client = _client(app, admin)
    resp = client.get(f"/brain/requests/{view['id']}")
    body = _body(resp)
    assert resp.status_code == 200 and 'style="' not in body and "<script>" not in body.split("</head>")[1]
    assert _scripts(body)[-1] == "ds-request.js" and "brain-ds-request.css?v=" in body
    assert '<p class="f-quote fb-req-text" data-ds-req-text>도면 담당은 도면팀에서 정해</p>' in body
    assert 'f-tag f-tag-primary">미리 보기</span>' in body
    states = dict(_lines(body))
    assert set(states.values()) == {"preview", "blocked"}
    skips = re.findall(r'data-ds-req-skip="(\d+)"', body)
    assert sorted(skips) == sorted(n for n, s in states.items() if s == "preview")  # 못 고치는 줄은 뺄 수 없다
    assert "못 고치는 까닭 · " in body and "틀리면 손님에게 '안 돼요'로 나가요 — 꼭 확인해 주세요" in body
    assert re.search(r'<span class="f-muted fb-req-field__before"><span class="f-sr">전: </span>도면 담당은 운영 AI', body)
    assert "data-ds-req-apply" in body and 'data-ds-req-confirm="discard"' in body and 'data-ds-req-confirm="revert"' not in body
    assert 'data-apply-url="/api/brain/change-requests/%d/apply"' % view["id"] in body
    assert "코드를 고쳐야 하는 것" in body and '<a href="/brain/items/common/door">여닫이 문짝</a>' in body
    assert "data-ds-req-cost" in body  # 관리자 — 돈 줄
    assert 'data-ds-req-part="done"' not in body

    preview = [int(n) for n, s in states.items() if s == "preview"]
    done = cr.apply(db_session, db_session.get(User, admin), view["id"], skip=[preview[-1]], now=APPLY_AT)
    db_session.commit()
    assert done["can_revert"] is True
    report = _body(client.get(f"/brain/requests/{view['id']}"))
    parts = re.findall(r'data-ds-req-part="(\w+)"', report)
    assert parts == ["done", "not_done", "needs_code", "also_look"]  # 빈 갈래(승인을 기다리는 것)는 없다
    assert "data-ds-req-skip=" not in report and "data-ds-req-apply" not in report
    assert 'data-ds-req-confirm="revert"' in report and "네, 되돌릴게요" in report
    assert 'data-ds-req-confirm="discard"' not in report

    cr.revert(db_session, db_session.get(User, admin), view["id"])
    db_session.commit()
    after = _body(client.get(f"/brain/requests/{view['id']}"))
    assert 'f-tag f-tag-minimal f-tag-success">되돌림</span>' in after and "data-ds-req-actions" not in after


def test_bundle_page_questions_and_answer_box(app, who):
    view = _start(who["admin"], dict(questions=["무엇을 얼마로 바꾸나요?"]))
    assert view["status"] == "asked" and view["can_answer"] is True
    body = _body(_client(app, who["admin"]).get(f"/brain/requests/{view['id']}"))
    assert "<span>무엇을 얼마로 바꾸나요?</span>" in body and "data-ds-req-answer-form" in body
    assert "data-ds-req-apply" not in body and 'data-ds-req-confirm="discard"' in body
    assert 'data-answer-url="/api/brain/change-requests/%d/answer"' % view["id"] in body


def test_bundle_page_is_404_for_others_and_when_off(app, who, monkeypatch):
    view = _start(who["dr_mgr"], dict(updates=[upd("drawing/rule/assign", text="도면팀 안에서 스스로 나눈다.")]))
    path = f"/brain/requests/{view['id']}"
    mine = _client(app, who["dr_mgr"]).get(path)
    assert mine.status_code == 200 and "data-ds-req-cost" not in _body(mine)  # 팀장에게 돈 줄 없음
    assert _client(app, who["admin"]).get(path).status_code == 200  # 관리자는 남의 묶음도 본다
    for name in ("cs_mgr", "sales_mgr", "cs_staff", "viewer"):  # 남의 묶음 · 쓸 수 없는 사람
        assert _client(app, who[name]).get(path).status_code == 404, name
    assert _client(app, who["admin"]).get("/brain/requests/999999").status_code == 404
    _flags(monkeypatch, change=False)
    assert _client(app, who["dr_mgr"]).get(path).status_code == 404
    assert _client(app, who["admin"]).get(path).status_code == 404


# ── 스크립트 ─────────────────────────────────────────────────────────────
@NODE
@pytest.mark.parametrize("path", JS, ids=lambda p: p.name)
def test_scripts_parse_and_stay_small(path):
    subprocess.run(["node", "--check", str(path)], check=True, capture_output=True, timeout=60)
    assert len(path.read_text(encoding="utf-8").splitlines()) < 300


@NODE
def test_pure_helpers():
    script = ("const r = require(%s); const l = require(%s);"
              "const b = (n, on) => ({getAttribute: k => k === 'aria-pressed' ? (on ? 'true' : 'false') : String(n)});"
              "process.stdout.write(JSON.stringify([r.skipList([b(3, true), b(1, true), b(2, false)]),"
              " l.whenText('2026-11-18T01:05:00'), l.whenText(''), l.countText({applied: 3, pending: 1}),"
              " l.countText({lines: 4}), l.tagClass({ready: ['primary', false]}, 'ready'), l.tagClass({}, 'zzz')]));"
              % (json.dumps(str(JS[0])), json.dumps(str(JS[2]))))
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, encoding="utf-8", timeout=60, check=True)
    assert json.loads(out.stdout) == [[1, 3], "11월 18일 10:05", "", "3곳 고침 · 승인 대기 1", "줄 4개", "f-tag f-tag-primary",
                                      "f-tag f-tag-minimal f-tag-primary"]

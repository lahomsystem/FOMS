"""새 물어보기 화면(판 ⑨ — 설계서 2026-11-14-foms-graft 3.7 · 5.2 ~ 5.5) — 서버가 그리는 자리 · 스크립트 · 순수 함수.

- 스위치 켬: ADMIN 의 ``?tab=ask`` · 물어보기만 여는 직원의 ``/brain/ask`` 가 ``brain/ds/ask.html`` 로 200 · 왼쪽 · 가운데 · 오른쪽 자리 ·
  인라인 스타일 0 · 스크립트는 defer + 내용 지문 핀 · 옛 화면을 그리는 스크립트(brain-ask.js · brain-ask-admin.js)는 싣지 않는다.
- 관리(설정 · 빈 지식 · 틀림 신고)는 ADMIN 만. ERP 읽기(``erp_read``)가 꺼진 사람은 안내 글이 지금 그대로 · 옆 창 자리가 없다.
- 순수 함수(node): 내 질문 목록 글 · ERP 답 옆 창 값(진짜 답 값으로 — 손님 이름 · 전화 · 주소 · 금액이 화면 값에 없다) ·
  erp 칸이 없는 답이면 옆 창 값이 없다(null).
- 스위치 끔: 옛 화면 그대로.
합성 계정 · 합성 지식 · 합성 주문 · 가짜 모델만(바깥 호출 없음).
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from contextlib import contextmanager
from pathlib import Path

import pytest
from flask import template_rendered

from db import db_session
from foms.services.brain.chat_answer import ask
from foms.services.graft_flags import FLAGS
from models import Order
from tests.support.brain_chat_support import FakeClient, chat_world, reply

ROOT = Path(__file__).resolve().parents[2]
VIEW = ROOT / "static/js/brain/ds/ds-ask-view.js"
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
OLD_DOM_SCRIPTS = ("brain-ask.js", "brain-ask-admin.js", "brain-page.js")
ORDER = 5201
NAME, ADDRESS, MEMO = "합성손님가", "합성시 가상구 시험길 9", "합성 내부 메모 글"
PHONE = "01" + "0" + "5551" + "2468"  # 합성 휴대폰(실행 때 만든다)
AMOUNT = 3141592
SECRETS = (NAME, PHONE, PHONE[-4:], ADDRESS, "시험길", str(AMOUNT), "3,141,592", MEMO)


@pytest.fixture
def ids(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    people = chat_world(db_session, stage="all")
    return {name: user.id for name, user in people.items()}


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


def _switch(monkeypatch, short):
    monkeypatch.setenv(f"{FLAGS[short]}_ENABLED", "1")
    monkeypatch.setenv(f"{FLAGS[short]}_COHORT", "all")


@contextmanager
def _rendered(app):
    names: list[str] = []

    def record(sender, template, context, **extra):
        names.append(template.name)

    template_rendered.connect(record, app)
    try:
        yield names
    finally:
        template_rendered.disconnect(record, app)


def _get(app, client, path):
    with _rendered(app) as names:
        resp = client.get(path)
    return resp, resp.get_data(as_text=True), names


def _scripts(body: str) -> list[str]:
    return re.findall(r'<script src="/static/js/brain/(?:ds/)?([\w-]+\.js)\?v=[0-9a-f]{12}" defer></script>', body)


def _side(body: str) -> str:
    start = body.index('<nav class="f-side fb-pc-only fb-ask-side" aria-label="물어본 것" data-ds-ask-side>')
    return body[start:body.index("</nav>", start)]


BASE_SCRIPTS = ["brain-view.js", "brain-dom.js", "ds-shell.js", "brain-ask-view.js", "ds-ask-view.js", "ds-ask-turn.js",
                "ds-ask.js"]


def test_switch_on_admin_draws_the_ask_screen_in_its_places(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    resp, body, names = _get(app, _client(app, ids["admin"]), "/brain?tab=ask")
    assert resp.status_code == 200 and names[0] == "brain/ds/ask.html"
    assert 'style="' not in body and "onclick" not in body and "<script>" not in body.split("</head>")[1]
    # 자리: 왼쪽 길잡이 → 가운데(안내 · 물음과 답 · 묻기 칸 · 관리) — ERP 읽기가 꺼져 옆 창 자리는 없다
    places = ["data-ds-ask-side", 'id="ds-main"', "data-ds-ask-state", "data-ds-ask-log", "data-ds-ask-form",
              'id="ds-ask-settings"', 'id="ds-ask-gaps"']
    assert [body.index(p) for p in places] == sorted(body.index(p) for p in places)
    assert "data-ds-ask-aside" not in body and 'data-erp="0"' in body
    for attr, value in (("data-state-url", "/api/brain/chat/state"), ("data-ask-url", "/api/brain/chat/ask"),
                        ("data-history-url", "/api/brain/chat/history"),
                        ("data-feedback-url", "/api/brain/chat/questions/0/feedback"),
                        ("data-settings-url", "/api/brain/chat/settings"), ("data-item-base", "/brain/items/")):
        assert f'{attr}="{value}"' in body, attr
    side = _side(body)
    assert re.findall(r'class="f-nav-heading">([^<]+)<', side) == ["오늘 물은 것 ", "지난 7일", "관리"]
    assert re.findall(r'data-ds-ask-admin-link="(\w+)"', side) == ["settings", "gaps", "wrong"]
    assert "data-ds-ask-new" in side and "data-ds-ask-today" in side and "data-ds-ask-week" in side
    # 안내 글 · 보기 글은 지금 그대로(ERP 읽기 꺼짐)
    assert "주문 상태 · 일정은 아직 못 답해요." in body and "새로 붙음" not in body
    assert 'placeholder="예: 슬라이딩 문은 깊이가 얼마나 필요해요?"' in body
    assert "보내기 전에 상담과 같은 가림을 거쳐요" in body
    assert _scripts(body) == BASE_SCRIPTS + ["ds-ask-admin.js"]
    assert not [n for n in OLD_DOM_SCRIPTS if f"/{n}?" in body]
    assert re.search(r"css/contexts/brain/ds/brain-ds-ask\.css\?v=[0-9a-f]{12}", body)
    display = json.loads(re.search(r'data-display="([^"]+)"', body).group(1).replace("&#34;", '"').replace("&#39;", "'")
                         .replace("&amp;", "&"))
    assert "confidences" in display and "layers" in display


def test_erp_read_on_adds_the_read_aside_place_and_the_new_line(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    _switch(monkeypatch, "erp_read")
    _resp, body, _n = _get(app, _client(app, ids["admin"]), "/brain?tab=ask")
    assert 'data-erp="1"' in body and "주문 상태 · 일정은 아직 못 답해요." not in body
    assert "주문 번호(#123)를 적으면 주문 · 방문도 읽어서 답해요. 읽기만 하고, 바꾸지는 않아요." in body
    assert 'placeholder="예: #123 시공 언제예요? · 슬라이딩 문은 깊이가 얼마나 필요해요?"' in body
    aside = body[body.index('<aside class="f-aside fb-ask-aside"'):body.index("</aside>")]
    assert 'aria-label="이 답이 읽은 것" data-ds-ask-aside hidden>' in aside  # 답에 erp 칸이 올 때까지 숨김
    assert "이 답이 읽은 것" in aside and "읽기만" in aside and "data-ds-ask-read" in aside
    assert body.index("data-ds-ask-form") < body.index("data-ds-ask-aside")  # 오른쪽 옆 창은 가운데 뒤
    for banned in ("2팀", "3명", "인원", "÷ 300", "L-", "H-"):
        assert banned not in aside


def test_chat_only_staff_gets_the_ask_page_without_admin_parts(app, ids, monkeypatch):
    _switch(monkeypatch, "brain_ui")
    client = _client(app, ids["staff"])
    assert client.get("/brain").headers["Location"].endswith("/brain/ask")
    resp, body, names = _get(app, client, "/brain/ask")
    assert resp.status_code == 200 and names[0] == "brain/ds/ask.html"
    assert "data-settings-url" not in body and "data-ds-ask-admin" not in body and "ds-ask-gaps" not in body
    assert "관리" not in _side(body) and _scripts(body) == BASE_SCRIPTS
    assert 'style="' not in body


def test_switch_off_keeps_the_old_screens(app, ids):
    client = _client(app, ids["admin"])
    resp, body, names = _get(app, client, "/brain?tab=ask")
    assert resp.status_code == 200 and names[0] == "brain/index.html" and "data-ds-ask" not in body
    assert "brain-ask.js" in body and "ds-ask" not in body
    resp, body, names = _get(app, _client(app, ids["staff"]), "/brain/ask")
    assert resp.status_code == 200 and names[0] == "brain/ask.html" and "data-brain-ask" in body and "ds-ask" not in body


# ── 순수 함수(node) ──────────────────────────────────────────────────────
def _node(expr: str, data: object = None):
    """node 로 순수 함수를 부른다 — 값은 표준 입력으로(명령 줄 길이 상한을 넘지 않게)."""
    script = (f"const v = require({json.dumps(str(VIEW))});"
              "const data = JSON.parse(require('fs').readFileSync(0, 'utf8'));"
              f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "-e", script], input=json.dumps(data, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60, check=True).stdout
    return json.loads(out)


def _order():
    """합성 ERP 주문 — 손님 · 금액 · 메모 칸에 비밀 글을 넣어 둔다(화면 값에 나오면 안 된다)."""
    data = {"parties": {"customer": {"name": NAME, "phone": PHONE}, "manager": {"name": "합성영업", "phone": PHONE}},
            "site": {"address_full": ADDRESS, "address_main": ADDRESS}, "payment": {"total": AMOUNT},
            "notes": {"memo": MEMO}, "items": [{"product_name": "합성 붙박이장", "price": AMOUNT, "memo": MEMO}],
            "schedule": {"measurement": {"date": "2026-11-20", "time": "오전"},
                         "construction": {"date": "2026-12-03", "time": "오후"}},
            "workflow": {"stage": "PRODUCTION"}}
    return Order(id=ORDER, received_date="2026-11-01", customer_name=NAME, phone=PHONE, address=ADDRESS, product=MEMO,
                 notes=MEMO, manager_name="합성영업", payment_amount=AMOUNT, status="RECEIVED", is_erp_order=True,
                 erp_stage_code="PRODUCTION", erp_stage_updated_at=datetime.datetime(2026, 10, 28, 3, 0),
                 erp_measurement_date="2026-11-20", erp_construction_date="2026-12-03", erp_phone_digits=PHONE,
                 erp_owner_team_code="PRODUCTION", structured_data=data)


@pytest.fixture
def erp_answer(app, ids, monkeypatch):
    """진짜 물어보기 길(가짜 모델)로 만든 ERP 답 값 · 내 질문 목록 값."""
    _switch(monkeypatch, "brain_ui")
    _switch(monkeypatch, "erp_read")
    db_session.add(_order())
    db_session.commit()
    from models import User

    admin = db_session.get(User, ids["admin"])
    fake = FakeClient(lambda _p: reply(answer="시공은 2026-12-03(목) 오후로 잡혀 있어요.", evidence_ids=[f"erp:order/{ORDER}"],
                                       unknown=False, kind="erp", confidence="high"))
    data = ask(db_session, admin, f"#{ORDER} 시공 언제로 옮겨 줄 수 있어요? 손님 번호 {PHONE}", client=fake)  # 지금 때 — 내 질문 목록은 지난 7일
    db_session.commit()
    history = _client(app, ids["admin"]).get("/api/brain/chat/history").get_json()["data"]
    return data, history


@NODE
def test_read_view_from_a_real_erp_answer_shows_only_server_values(erp_answer):
    data, _history = erp_answer
    assert data["kind"] == "erp" and data["erp"]["order"]["id"] == ORDER
    got = _node("[v.readView(data.erp), v.erpChips(data), v.kindTag(data), v.askedLine('합성영업', '10:42', data.erp)]", data)
    rv, chips, kind, line = got
    assert rv["title"] == f"#{ORDER}" and rv["stage"] == {"text": data["erp"]["order"]["stage_label"], "tone": "primary"}
    assert rv["products"] == "합성 붙박이장" and rv["manager"] == "합성영업" and rv["masked"] == "손님 · 현장"
    assert [(v["label"], v["st"], v["day"]) for v in rv["visits"]] == [("실측", "contract", "11-20 (금)"),
                                                                       ("시공", "site", "12-03 (목)")]
    assert rv["visits"][0]["time"] == "오전 예정" and rv["change"] is True  # 일정 바꾸기 질문 → '승인 대기로 가요' 줄
    assert [t["name"] for t in rv["tools"]][:3] == ["mask.apply", "erp.order.get", "erp.visit.list"]
    assert all(re.fullmatch(r"\d+\.\d초|0\.1초 아래", t["secs"]) for t in rv["tools"])
    assert chips[0] == {"text": f"주문 #{ORDER} · " + data["erp"]["order"]["stage_label"], "icon": "cube"}
    assert kind == {"text": "ERP 읽기", "tone": "primary", "minimal": True, "icon": "data-lineage"}
    assert line == "합성영업 · 10:42 · 1곳을 가려서 보냄"  # 가림 도구가 센 수만(글 없이)
    shown = json.dumps(got, ensure_ascii=False)
    assert not [s for s in SECRETS if s in shown]  # 화면 값에 손님 이름 · 전화 · 주소 · 금액 · 메모가 없다
    for banned in ("팀 ", "명", "사진", "L-", "÷"):
        assert banned not in json.dumps(rv["visits"], ensure_ascii=False)


@NODE
def test_history_rows_from_the_real_history_api(erp_answer):
    data, history = erp_answer
    got = _node("v.historyLists(data)", history)
    assert got["count"] == 1 and got["week"] == [] and got["empty"] is False
    row = got["today"][0]
    assert row["id"] == data["id"] and row["icon"] == "data-lineage" and row["sub"].startswith("ERP 읽음")
    assert PHONE not in row["text"] and PHONE[-4:] not in row["text"]  # 서버가 준 가린 글만
    assert re.fullmatch(r"\d\d:\d\d", row["when"])


@NODE
def test_history_item_text_for_each_kind_and_empty_list():
    rows = {"today": [{"id": 1, "text": "몰딩 높이?", "unknown": True, "erp": False, "certainty_label": "",
                       "ask_label": "도면팀", "asked_at": "2026-11-14T10:42"},
                      {"id": 2, "text": "슬라이딩 깊이?", "unknown": False, "erp": False, "certainty_label": "높음",
                       "ask_label": "", "asked_at": "2026-11-14T09:05"}],
            "week": [{"id": 3, "text": "출장비?", "unknown": False, "erp": True, "certainty_label": "보통",
                      "asked_at": "2026-11-12T16:00"}]}
    got = _node("[v.historyLists(data), v.historyLists({today: [], week: []}), v.historyLists(null)]", rows)
    full, empty, missing = got
    assert [(r["sub"], r["icon"], r["when"]) for r in full["today"]] == [("모름 · 도면팀", "help", "10:42"),
                                                                         ("회사 지식 · 높음", "properties", "09:05")]
    assert full["week"] == [{"id": 3, "text": "출장비?", "sub": "ERP 읽음 · 보통", "icon": "data-lineage", "when": "11-12"}]
    assert full["count"] == 2 and empty["empty"] is True and missing["count"] == 0


@NODE
def test_no_erp_means_no_aside_and_labels():
    got = _node("[v.readView(null), v.readView({order: null}), v.erpChips({kind: 'knowledge', erp: null}),"
                " v.kindTag({unknown: true}), v.kindTag({kind: 'knowledge'}), v.certaintyTag({certainty: 'medium'}),"
                " v.certaintyTag({unknown: true, certainty: 'high'}), v.secsLabel(0), v.secsLabel(40), v.secsLabel(1349),"
                " v.secsLabel(null), v.dayLabel('2026-11-20'), v.dayLabel('모름'),"
                " v.gapCounts({layers: {cs: [{wrong: 2}, {wrong: 0}], drawing: [{}]}}), v.gapCounts(null),"
                " v.askedLine('합성', '10:00', {tools: [{name: 'mask.apply', what: '가림 0곳'}]})]")
    assert got[0] is None and got[1] is None and got[2] == []  # erp 칸이 없으면 옆 창 값이 없다
    assert got[3]["text"] == "모름" and got[3]["tone"] == "warning" and got[4] is None
    assert got[5] == {"text": "보통", "tone": "warning"} and got[6] is None
    assert got[7:11] == ["0.1초 아래", "0.1초 아래", "1.3초", ""]
    assert got[11] == "11-20 (금)" and got[12] == "모름"
    assert got[13] == {"gaps": 3, "wrong": 2} and got[14] == {"gaps": 0, "wrong": 0}
    assert got[15] == "합성 · 10:00"


def test_ask_scripts_hide_the_aside_without_erp_and_bind_once():
    turn = (ROOT / "static/js/brain/ds/ds-ask-turn.js").read_text(encoding="utf-8")
    main = (ROOT / "static/js/brain/ds/ds-ask.js").read_text(encoding="utf-8")
    admin = (ROOT / "static/js/brain/ds/ds-ask-admin.js").read_text(encoding="utf-8")
    assert "if (!rv) {\n      aside.hidden = true;" in main and "reads[data.id] = dv.readView(data.erp);" in main
    assert "'방문 옮기기는 승인 대기로 가요'" in turn
    assert "__FOMS_DS_ASK_BOUND" in main and "__FOMS_DS_ASK_ADMIN_BOUND" in admin
    for js in (turn, main, admin, VIEW.read_text(encoding="utf-8")):
        assert "fetch(" not in js and ".innerHTML" not in js and ".style." not in js and len(js.splitlines()) <= 300

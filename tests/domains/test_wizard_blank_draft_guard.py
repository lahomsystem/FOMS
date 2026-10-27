"""마법사 빈 초안 가드 (2026-10-26 설계서 docs/plans/2026-10-26-wizard-empty-draft-cleanup-spec.md).

마법사를 열었다 닫기만 해도 떠날 때 저장(PUT)이 나가 아무것도 안 적힌 초안 행이 생겼다(운영 10-19
이후 약 3할, 홈 "작성 중" 띠에 빈 카드로 7일). 세 겹으로 막는다.

* 서버(D1): 행이 없고 값이 하나도 없는 payload 면 INSERT 하지 않는다(``saved: false``).
* 화면(D2): 연 그대로면 저장 요청 자체를 안 보낸다 — [복구] 전 덮어쓰기도 같이 막힌다.
* 이동(D3·D4): 수정 화면 저장 뒤 마법사(/add)로 돌아가지 않고, 끝난 마법사는 방문 기록에서 뺀다.

판정은 "저장하는 쪽으로" 틀려야 한다 — 한 칸이라도 값이 있으면 지금처럼 저장된다(양성 대조).
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
import textwrap
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from foms.services.datetime_kst import get_today_kst
from foms.services.order_draft_blank import is_blank_draft_data

ROOT = Path(__file__).resolve().parents[2]
DRAFT_JS = ROOT / "static/js/foms/draft.js"
WIZARD_JS = ROOT / "static/js/foms/wizard.js"
WIZARD_SEND_JS = ROOT / "static/js/foms/wizard-send.js"
SHARED_JS = ROOT / "static/js/orders/erp-order-shared.js"


def _today() -> str:
    return get_today_kst().strftime("%Y-%m-%d")


def _blank_data() -> dict:
    """마법사를 열자마자의 payload.data(화면 기본값만 든 모양)."""
    return {
        "customer_name": "", "phone": "", "orderer": "라홈", "address": "",
        "received_date": _today(),
        "items": [{
            "product_name": "",
            "spec_rows": [{"spec_width": "", "spec_depth": "", "spec_height": ""}],
            "internal": "상담", "color": "상담", "option_detail": "상담", "handle": "상담",
            "misc": "상담", "price": "", "measurement_date": "", "construction_date": "",
            "extra_input": "", "attachments": [],
        }],
        "schedule": {
            "measurement_date": "", "measurement_time": "", "construction_date": "",
            "construction_time": "", "sales_manager": "", "construction_manager": "",
            "load_date": "", "notes": "",
        },
        "flags": {"regional_order": False, "regional_construction_type": "", "factory2": False,
                  "urgent": False, "urgent_reason": ""},
        "deposit": "",
    }


def _set(data: dict, path: str, value) -> dict:
    """``a.b`` · ``items.0.c`` 경로에 값을 넣는다."""
    node = data
    parts = path.split(".")
    for part in parts[:-1]:
        node = node[int(part)] if part.isdigit() else node[part]
    last = parts[-1]
    if last.isdigit():
        node[int(last)] = value
    else:
        node[last] = value
    return data


#: 한 칸만 바꿔도 값이다(양성 대조). 마법사 collect* 가 보내는 칸을 전부 덮는다 — 아래 소스 계약이 대조.
_ONE_FIELD_CASES = [
    ("customer_name", "이화원"), ("phone", "010-0000-0000"), ("address", "노원 테스트로 1"),
    ("orderer", "하우드"), ("received_date", "2000-01-01"),
    ("items.0.product_name", "붙박이장"), ("items.0.spec_rows.0.spec_width", "3000"),
    ("items.0.spec_rows.0.spec_depth", "600"), ("items.0.spec_rows.0.spec_height", "2400"),
    ("items.0.internal", "선반"), ("items.0.color", "화이트"), ("items.0.option_detail", "LED"),
    ("items.0.handle", "무손잡이"), ("items.0.misc", "주방"), ("items.0.price", "1000000"),
    ("items.0.measurement_date", "2026-11-01"), ("items.0.construction_date", "2026-11-05"),
    ("items.0.extra_input", "추가"),
    ("items.0.attachments", [{"tmp_key": "order-drafts/1/new.x/a.jpg", "filename": "a.jpg"}]),
    ("schedule.measurement_date", "2026-11-01"), ("schedule.measurement_time", "10:00"),
    ("schedule.construction_date", "2026-11-05"), ("schedule.construction_time", "08:30"),
    ("schedule.sales_manager", "한용희"), ("schedule.construction_manager", "시공1"),
    ("schedule.load_date", "2026-11-04"), ("schedule.notes", "메모"),
    ("flags.regional_order", True), ("flags.regional_construction_type", "하우드"),
    ("flags.factory2", True), ("flags.urgent", True), ("flags.urgent_reason", "급함"),
    ("deposit", "100,000"),
]


# ---------------------------------------------------------------------------
# 판정 단위
# ---------------------------------------------------------------------------


def test_opened_wizard_payload_is_blank() -> None:
    assert is_blank_draft_data(_blank_data(), today_kst=_today()) is True


@pytest.mark.parametrize("path,value", _ONE_FIELD_CASES, ids=[c[0] for c in _ONE_FIELD_CASES])
def test_any_single_field_makes_it_not_blank(path, value) -> None:
    assert is_blank_draft_data(_set(_blank_data(), path, value), today_kst=_today()) is False


@pytest.mark.parametrize("deposit,blank", [("", True), ("0", True), ("0원", True),
                                           ("1,000", False), ("협의", False)])
def test_deposit_default_only_zero(deposit, blank) -> None:
    assert is_blank_draft_data(_set(_blank_data(), "deposit", deposit),
                               today_kst=_today()) is blank


def test_unknown_fields_count_as_values() -> None:
    """앞으로 생길 칸도 값이 있으면 값이다 — 판정이 칸 목록을 못 따라가도 저장하는 쪽으로 틀린다."""
    assert is_blank_draft_data({**_blank_data(), "new_field": "x"}, today_kst=_today()) is False
    assert is_blank_draft_data(_set(_blank_data(), "items.0.new_field", "x"),
                               today_kst=_today()) is False


def test_test_cases_cover_every_collected_wizard_field() -> None:
    """소스 계약: wizard.js collect* 가 보내는 칸이 양성 대조 목록에 다 있다(새 칸이 빠지면 red)."""
    js = WIZARD_JS.read_text(encoding="utf-8")
    sent: set[str] = set()
    for fn in ("collectBasic", "collectSchedule", "collectPayment", "collectFlags", "collectProducts"):
        start = js.index(f"function {fn}(")
        body = js[start:js.index("\n  }\n", start)]
        sent |= set(re.findall(r"^\s+(\w+):", body, flags=re.M))
    sent -= {"spec_rows"}  # 컨테이너 — 안의 가로·깊이·높이로 따진다
    covered = {path.split(".")[-1] for path, _ in _ONE_FIELD_CASES}
    assert sent, "collect* 에서 칸 이름을 하나도 못 읽었다"
    assert sorted(sent - covered) == []


# ---------------------------------------------------------------------------
# 서버 가드 (PUT /api/erp/order-draft)
# ---------------------------------------------------------------------------


@pytest.fixture
def wizard_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FOMS_WIZARD_NEW_ORDER_ENABLED", "true")


def _login(client, app, username: str) -> None:
    from db import db_session
    from models import User

    with app.app_context():
        if not db_session.query(User).filter_by(username=username).first():
            db_session.add(User(username=username, password=generate_password_hash("admin"),
                                role="ADMIN", team="CS", name="빈초안"))
            db_session.commit()
    client.post("/login", data={"username": username, "password": "admin"},
                follow_redirects=True)


def _put(client, key: str, data: dict, step: int = 1, if_match: str | None = None):
    headers = {"X-If-Match": if_match} if if_match else {}
    return client.put(
        "/api/erp/order-draft",
        data=json.dumps({"draft_key": key, "step": step,
                         "payload": {"schema_version": 1, "step": step, "data": data}}),
        content_type="application/json", headers=headers,
    )


def _rows(key: str) -> int:
    from db import db_session
    from models import OrderDraft

    db_session.expire_all()
    return db_session.query(OrderDraft).filter(OrderDraft.draft_key == key).count()


def test_blank_put_creates_no_row(client, app, wizard_enabled) -> None:
    _login(client, app, "blank_guard_1")
    resp = _put(client, "new.blank-1", _blank_data())

    body = resp.get_json()
    assert resp.status_code == 200
    assert body["success"] is True and body["saved"] is False
    assert _rows("new.blank-1") == 0
    listed = client.get("/api/erp/order-draft/list").get_json()
    assert [d for d in listed.get("drafts", []) if d["draft_key"] == "new.blank-1"] == []


def test_valued_put_creates_row(client, app, wizard_enabled) -> None:
    _login(client, app, "blank_guard_2")
    resp = _put(client, "new.blank-2", _set(_blank_data(), "address", "노원 테스트로 1"))

    assert resp.get_json()["saved"] is True and resp.get_json()["updated_at"]
    assert _rows("new.blank-2") == 1


def test_blank_then_valued_put_creates_row(client, app, wizard_enabled) -> None:
    _login(client, app, "blank_guard_3")
    _put(client, "new.blank-3", _blank_data())
    resp = _put(client, "new.blank-3", _set(_blank_data(), "customer_name", "이화원"))

    assert resp.get_json()["saved"] is True
    assert _rows("new.blank-3") == 1


def test_existing_row_is_still_updated_with_blank_payload(client, app, wizard_enabled) -> None:
    """행이 이미 있으면 빈 payload 라도 고친다 — 사용자가 일부러 다 지운 것일 수 있다."""
    _login(client, app, "blank_guard_4")
    first = _put(client, "new.blank-4", _set(_blank_data(), "customer_name", "이화원")).get_json()
    resp = _put(client, "new.blank-4", _blank_data(), if_match=first["updated_at"])

    assert resp.get_json()["saved"] is True
    draft = client.get("/api/erp/order-draft?key=new.blank-4").get_json()["draft"]
    assert draft["payload"]["data"]["customer_name"] == ""


def _full_data() -> dict:
    data = _blank_data()
    for path, value in (("customer_name", "CLAUDE-TEST-빈초안"), ("phone", "010-0000-0000"),
                        ("address", "서울 테스트로 1"), ("items.0.product_name", "붙박이장")):
        _set(data, path, value)
    return data


def test_submit_works_without_a_saved_row(client, app, wizard_enabled) -> None:
    """등록은 화면이 보낸 내용으로 한다 — 빈 PUT 만 했던 키(행 없음)여도 주문이 생긴다."""
    _login(client, app, "blank_guard_5")
    _put(client, "new.blank-5", _blank_data())
    resp = client.post("/api/erp/order-draft/submit", data=json.dumps({
        "draft_key": "new.blank-5",
        "payload": {"schema_version": 1, "step": 4, "data": _full_data()},
    }), content_type="application/json")

    assert resp.status_code == 200 and resp.get_json()["success"] is True


def test_blank_put_after_submit_does_not_resurrect(client, app, wizard_enabled) -> None:
    """운영 807: 등록 31초 뒤 같은 키로 빈 3단계 행이 되살아났다."""
    _login(client, app, "blank_guard_6")
    _put(client, "new.blank-6", _full_data(), step=4)
    client.post("/api/erp/order-draft/submit", data=json.dumps({
        "draft_key": "new.blank-6",
        "payload": {"schema_version": 1, "step": 4, "data": _full_data()},
    }), content_type="application/json")
    assert _rows("new.blank-6") == 0

    _put(client, "new.blank-6", _blank_data(), step=3)

    assert _rows("new.blank-6") == 0


def test_yesterday_received_date_is_a_value(client, app, wizard_enabled) -> None:
    """자정 경계: 어제 연 화면을 오늘 저장하면 접수일이 값이 된다(안전한 쪽으로 틀린다)."""
    _login(client, app, "blank_guard_7")
    yesterday = (get_today_kst() - datetime.timedelta(days=1)).strftime("%Y-%m-%d")
    _put(client, "new.blank-7", _set(_blank_data(), "received_date", yesterday))

    assert _rows("new.blank-7") == 1


# ---------------------------------------------------------------------------
# 이동 (D3·D4)
# ---------------------------------------------------------------------------


def test_finished_wizard_navigations_replace_history() -> None:
    wizard = WIZARD_JS.read_text(encoding="utf-8")
    send = WIZARD_SEND_JS.read_text(encoding="utf-8")
    assert "window.location.replace(readWizardExitHref(root))" in wizard
    assert "window.location.href = readWizardExitHref(root)" not in wizard
    assert "window.location.replace(href)" in send
    assert "window.location.replace(ORDER_EDIT_HREF_PREFIX" in send
    assert "window.location.href" not in send


def test_shell_pins_bumped() -> None:
    shell = (ROOT / "templates/orders/wizard/wizard_shell.html").read_text(encoding="utf-8")
    assert "js/foms/draft.js') }}?v=20261026b" in shell
    for name in ("wizard.js", "wizard-send.js"):
        assert f"js/foms/{name}') }}}}?v=2026102" in shell, name


@pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
def test_edit_save_never_returns_to_wizard_in_node() -> None:
    js = SHARED_JS.read_text(encoding="utf-8")
    start = js.index("function erpIsNewOrderWizardUrl(")
    fn_src = js[start:js.index("\n}\n", start) + 2]
    assert "if (erpIsNewOrderWizardUrl(targetUrl)) targetUrl = '/erp/dashboard';" in js
    harness = textwrap.dedent("""
        global.window = { location: { origin: "https://x.test" } };
        FN_SRC
        console.log(JSON.stringify([
          "/add", "/add?key=new.x&wizard=1&step=3", "https://x.test/add#top",
          "/erp/dashboard?focus_order=1", "/erp/measurement", "/add-on", "/edit/5"
        ].map(erpIsNewOrderWizardUrl)));
    """).replace("FN_SRC", fn_src)
    out = subprocess.run(["node", "-e", harness], capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout.strip()) == [True, True, True, False, False, False, False]


# ---------------------------------------------------------------------------
# 화면 가드 (draft.js) — 실제 fetch 를 센다
# ---------------------------------------------------------------------------

_NODE_PRELUDE = """
var winListeners = {}; var docListeners = {};
global.window = { addEventListener: function (n, f) { (winListeners[n] = winListeners[n] || []).push(f); } };
global.document = {
  visibilityState: "visible",
  addEventListener: function (n, f) { (docListeners[n] = docListeners[n] || []).push(f); },
  getElementById: function () { return null; },
};
global.navigator = { onLine: true };
var puts = 0; var nextPut = { success: true, saved: true, updated_at: "2026-10-26T05:00:00" };
var remoteDraft = null;
global.fetch = function (url, opts) {
  var method = (opts && opts.method) || "GET";
  if (method === "PUT") { puts += 1; }
  var body = method === "PUT" ? nextPut : { success: true, draft: remoteDraft };
  return Promise.resolve({ ok: true, status: 200, json: function () { return Promise.resolve(body); } });
};
function fire(name) { (winListeners[name] || []).forEach(function (f) { f(); }); }
function hide() { document.visibilityState = "hidden"; (docListeners.visibilitychange || []).forEach(function (f) { f(); }); document.visibilityState = "visible"; }
require(DRAFT_JS_PATH);
var data = { customer_name: "", orderer: "라홈" };
function makeClient() {
  var root = { getAttribute: function () { return "new.abcdef"; }, querySelectorAll: function () { return []; } };
  var c = new window.FomsDraftClient(root, {
    getPayload: function () { return { schema_version: 1, step: 1, data: JSON.parse(JSON.stringify(data)) }; },
    getStep: function () { return 1; },
    onRecovered: function () {},
  });
  c.bindAutosave();
  c.markBaseline();
  return c;
}
function sleep(ms) { return new Promise(function (r) { setTimeout(r, ms); }); }
function done(obj) { console.log(JSON.stringify(obj)); process.exit(0); }
"""


def _run_node(body: str) -> dict:
    script = (_NODE_PRELUDE + textwrap.dedent(body)).replace("DRAFT_JS_PATH", json.dumps(str(DRAFT_JS)))
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=60,
                         cwd=str(ROOT))
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout.strip().splitlines()[-1])


_needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")


@_needs_node
def test_untouched_wizard_sends_no_put() -> None:
    """열고 손대지 않고 떠남 — X(flush)·pagehide·beforeunload·hidden 모두 PUT 0회."""
    out = _run_node("""
        var c = makeClient();
        c.flush().then(function (ok) {
          fire("pagehide"); fire("beforeunload"); hide();
          return sleep(50).then(function () { done({ ok: ok, puts: puts }); });
        });
    """)
    assert out == {"ok": True, "puts": 0}


@_needs_node
def test_typing_saves_at_the_same_time_as_before() -> None:
    """한 글자 입력 → 디바운스 1초 뒤 PUT 1회(늦어지지 않는다)."""
    out = _run_node("""
        var c = makeClient();
        data.customer_name = "이";
        c.scheduleSave();
        sleep(1200).then(function () { done({ puts: puts }); });
    """)
    assert out == {"puts": 1}


@_needs_node
def test_leaving_right_after_typing_still_keepalives() -> None:
    """2026-09 유실 대책 회귀: 입력 직후(디바운스 전) 화면을 떠나도 keepalive PUT 이 나간다."""
    out = _run_node("""
        var c = makeClient();
        data.customer_name = "이";
        c.scheduleSave();
        fire("pagehide");
        sleep(50).then(function () { done({ puts: puts }); });
    """)
    assert out == {"puts": 1}


@_needs_node
def test_resume_screen_left_without_recover_does_not_overwrite() -> None:
    """이어쓰기 화면에서 [복구] 를 안 누르고 나가도 저장된 초안을 빈 내용으로 덮지 않는다(3.6)."""
    out = _run_node("""
        remoteDraft = { payload: { data: { customer_name: "이화원" } }, updated_at: "2026-10-25T05:00:00" };
        var c = makeClient();
        c.load().then(function () {
          return c.flush();
        }).then(function () {
          fire("pagehide"); hide();
          return sleep(50);
        }).then(function () {
          var before = puts;
          c.applyRemote(remoteDraft);   // [복구]
          return c.flush().then(function (ok) { done({ before: before, after: puts, ok: ok }); });
        });
    """)
    assert out == {"before": 0, "after": 1, "ok": True}


@_needs_node
def test_server_saved_false_is_not_shown_as_saved() -> None:
    """서버가 행을 안 만들었으면(saved:false) 저장 토큰도 안 바뀌고 가드도 그대로다."""
    out = _run_node("""
        nextPut = { success: true, saved: false, updated_at: "", step: 1 };
        var c = makeClient();
        data.orderer = "하우드";       // 화면 기준으론 바뀜(서버 판정과 어긋나도 저장하는 쪽)
        c.flush().then(function (ok) {
          done({ ok: ok, puts: puts, updatedAt: c.updatedAt, guardOff: c._guardOff });
        });
    """)
    assert out == {"ok": True, "puts": 1, "updatedAt": None, "guardOff": False}


@_needs_node
def test_changed_then_reverted_after_a_save_still_saves() -> None:
    """한 번 저장된 뒤에는 연 그대로로 되돌려도 저장한다(사용자가 일부러 지운 것)."""
    out = _run_node("""
        var c = makeClient();
        data.customer_name = "이";
        c.flush().then(function () {
          data.customer_name = "";
          return c.flush();
        }).then(function () { done({ puts: puts }); });
    """)
    assert out == {"puts": 2}

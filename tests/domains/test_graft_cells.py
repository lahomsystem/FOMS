"""접목판 분홍 칸(설계서 2026-11-14-foms-graft 6절 · 판 ② ③ ④) — 지금 화면에 더하는 AI 제안 자리.

- **스위치 끔 = 지금과 한 글자도 같다**: 고친 템플릿 아홉에서 접목판 칸을 떼어 낸 '오늘 판'을 템플릿 고르개로 끼워 그린
  화면과 지금 템플릿으로 그린 화면을 PC 대시보드 · 폰/태블릿 셸 대시보드 · 폰 작업 목록 · 태블릿 상세에서 견준다.
- 켬: 자리는 전역 스위치로만 갈린다(사람 목록 밖이어도 빈 자리는 같다 — 미리 그려 두는 조각에 사람마다 다른 값 없음).
  자리마다 정한 곳(현재 작업 칸 · 알림 단추 앞 · 레일 알림 앞 · 처리 대기 끝 · 폰 목록 줄 머리)에 hidden 으로.
- 태블릿 상세 'AI 제안' 상자: 칸 스위치가 켜진 사람에게 열린 제안이 있을 때만 · 단추 셋 · 거절 까닭 다섯 · 바로가기 제안은
  [주문에서 처리]. 시공 팀 · 인원 · '폭 합 ÷ 300' 글은 어디에도 없다(사용자 결정 D211).
- 스크립트(node · 가짜 DOM): /badge 한 번 + 보이는 주문 번호를 모아 /open 한 번 · 두 번 실려도 한 번만 묶임 · 칩 글 ·
  폰 칸 0 이면 숨김 · 상자 승인 · 거절. 합성 계정 · 합성 주문만 · 바깥으로 보내지 않는다(fetch 는 가짜).
"""

from __future__ import annotations

import datetime
import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from jinja2 import ChoiceLoader, DictLoader
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.erp_actions.lifecycle import propose
from foms.services.erp_sync_columns import sync_erp_flat_columns
from foms.services.graft_flags import FLAGS
from models import Order, User
from tests.domains.test_brain_fix_inbox_js import HARNESS

ROOT = Path(__file__).resolve().parents[2]
NODE = pytest.mark.skipif(shutil.which("node") is None, reason="node 없음")
CELLS_JS = ROOT / "static/js/foms/graft-cells.js"
TEMPLATES = ("partials/shared/layout_nav.html", "partials/shared/layout_head.html", "partials/shared/layout_scripts.html",
             "partials/shared/foms_tablet_rail.html", "partials/shared/erp_mobile_queue_card_v2.html",
             "orders/partials/dashboard_grid.html", "orders/partials/tablet_workqueue_grid.html",
             "orders/partials/tablet_dashboard_sheet.html", "orders/partials/dashboard_mobile_tower.html")
#: 접목판 칸 한 덩이 — 앞 줄바꿈 · (머리 주석) · {%- if 접목판 %} … {%- endif %}. 떼면 고치기 전 템플릿과 같은 글이 된다.
BLOCK = re.compile(r"\n[ \t]*(?:\{#-(?:(?!#\}).)*#\}\n[ \t]*)?\{%- if (?:graft_cell_slot\('\w+'\)|graft_cells_any\(\)|"
                   r"graft_proposal) %\}.*?\{%-? endif %\}", re.S)
CREW_WORDS = ("팀 3명", "2팀", "폭 합", "÷ 300", "시공 인원")


def _day(offset: int) -> str:
    return (get_today_kst() + datetime.timedelta(days=offset)).isoformat()


def _order(stage: str) -> Order:
    sd = {"workflow": {"stage": stage}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    return order


def _switch(monkeypatch, cohort: str, *names: str) -> None:
    for name in names:
        monkeypatch.setenv(f"{FLAGS[name]}_ENABLED", "1")
        monkeypatch.setenv(f"{FLAGS[name]}_COHORT", cohort)


@pytest.fixture
def world(app, monkeypatch):
    for env in FLAGS.values():
        monkeypatch.delenv(f"{env}_ENABLED", raising=False)
        monkeypatch.delenv(f"{env}_COHORT", raising=False)
    admin = User(username="gc_admin", password=generate_password_hash("pw"), role="ADMIN", name="합성 관리자", is_active=True)
    db_session.add(admin)
    db_session.commit()
    orders = [_order("RECEIVED"), _order("DRAWING")]
    rows = [propose(db_session, action="schedule_construction", proposed_by="agent:schedule", order=orders[0],
                    params={"date": _day(9), "time": "오전"}, reason="합성 이유", evidence=[], source_kind="sweep",
                    source_ref="1", level=2, now=now_utc_naive()),
            propose(db_session, action="assign_draftsman", proposed_by="agent:ops", order=orders[1], params={},
                    reason="합성 이유", evidence=[], source_kind="sweep", source_ref="2", level=1, now=now_utc_naive())]
    db_session.commit()
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = admin.id
    return {"app": app, "client": client, "admin": admin.id, "orders": [o.id for o in orders],
            "proposals": [r.id for r in rows]}


def _pages(world, monkeypatch) -> dict[str, str]:
    """견줄 화면 넷 — PC 대시보드 · 셸 대시보드(폰 홈 · 태블릿 표 · 레일) · 폰 작업 목록 · 태블릿 상세."""
    client = world["client"]
    out = {"pc": client.get("/erp/dashboard").get_data(as_text=True)}
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(world["admin"]))
    out["shell"] = client.get("/erp/dashboard").get_data(as_text=True)
    out["queue"] = client.get("/erp/dashboard?view=queue").get_data(as_text=True)
    out["sheet"] = client.get(f"/erp/dashboard/tablet-sheet/{world['orders'][0]}").get_data(as_text=True)
    monkeypatch.delenv("ERP_MOBILE_V2_ENABLED")
    monkeypatch.delenv("FOMS_V3_SHELL_COHORT")
    return out


def test_every_graft_block_is_cut_by_the_today_pattern():
    """떼어 낼 덩이가 템플릿마다 있고(아홉 모두), 뗀 글에는 접목판 흔적이 없다."""
    env_dir = ROOT / "templates"
    for name in TEMPLATES:
        source = (env_dir / name).read_text(encoding="utf-8")
        assert BLOCK.search(source), name
        assert "graft" not in BLOCK.sub("", source), name


def test_switches_off_render_exactly_like_today(world, monkeypatch):
    app = world["app"]
    now = _pages(world, monkeypatch)
    today = {name: BLOCK.sub("", (ROOT / "templates" / name).read_text(encoding="utf-8")) for name in TEMPLATES}
    original = app.jinja_env.loader
    app.jinja_env.cache.clear()
    monkeypatch.setattr(app.jinja_env, "loader", ChoiceLoader([DictLoader(today), original]))
    try:
        before = _pages(world, monkeypatch)
    finally:
        monkeypatch.setattr(app.jinja_env, "loader", original)
        app.jinja_env.cache.clear()
    for key in ("pc", "shell", "queue", "sheet"):
        assert now[key] == before[key], key
        assert "graft" not in now[key], key


def test_slots_follow_the_global_switch_only_and_sit_in_their_cells(world, monkeypatch):
    """전역으로 켜고 사람 목록은 다른 사람(999999) — 빈 자리는 그래도 같은 꼴로 그려진다(사람별 값 없음)."""
    _switch(monkeypatch, "999999", "brain_ui", "actions", "cell_pc", "cell_tablet", "cell_mobile")
    pages = _pages(world, monkeypatch)
    a, b = world["orders"]
    pc, shell, queue = pages["pc"], pages["shell"], pages["queue"]
    assert re.search(r'css/components/foms-graft-cells\.css\?v=[0-9a-f]{12}', pc)
    assert re.search(r'js/foms/graft-cells\.js\?v=[0-9a-f]{12}" defer', pc)
    quest = pc[pc.index(f'data-order-id="{a}"'):]
    quest = quest[quest.index('data-col-key="quest"'):quest.index('data-col-key="customer"')]
    assert f'<a class="foms-graft-chip" data-graft-slot="{a}" data-graft-cell="pc" hidden></a>' in quest
    nav = pc[pc.index('data-graft-badge="pc"') - 60:pc.index('id="global-notification-btn"')]
    assert 'class="position-relative foms-graft-nav" data-graft-badge="pc" hidden' in nav and "/brain?tab=inbox" in nav
    rail = shell[shell.index("foms-tablet-rail__spacer"):shell.index("foms-tablet-rail__notify")]
    assert 'data-graft-badge="tablet" hidden' in rail and "회사 지식" in rail
    tq = shell[shell.index(f'class="erp-main-row foms-tqrow" data-order-id="{a}"'):]
    tq = tq[tq.index('class="foms-tqcell-quest"'):]
    assert tq.index(f'data-graft-slot="{a}" data-graft-cell="tablet" hidden') < tq.index("</td>")
    quick = shell[shell.index('class="foms-tower__quick"'):]
    quick = quick[:quick.index("</section>")]
    assert quick.index("신규 접수 대기") < quick.index("data-graft-tile")
    assert re.search(r'class="foms-tower__quick-card foms-graft-tile"[^>]*data-graft-tile[^>]*hidden>', quick)
    assert "AI 제안 승인 대기" in quick
    head = queue[queue.index(f'<article class="queue-card foms-queue-card-v2" data-order-id="{b}"'):]
    head = head[head.index("<header"):head.index("</header>")]
    assert f'data-graft-slot="{b}" data-graft-cell="mobile" hidden' in head
    for text in pages.values():
        assert not any(word in text for word in CREW_WORDS)
    assert "tablet_sheet_ai_proposal" not in pages["sheet"] and "data-graft-box" not in pages["sheet"]  # 사람 목록 밖


def test_one_cell_switch_draws_only_its_own_slots(world, monkeypatch):
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_mobile")
    pages = _pages(world, monkeypatch)
    assert "data-graft-tile" in pages["shell"] and 'data-graft-cell="mobile"' in pages["queue"]
    assert 'data-graft-cell="pc"' not in pages["pc"] and 'data-graft-badge="pc"' not in pages["pc"]
    assert 'data-graft-badge="tablet"' not in pages["shell"] and 'data-graft-cell="tablet"' not in pages["shell"]
    assert "graft-cells.js" in pages["pc"]  # 칸 하나라도 켜지면 스크립트 한 줄


def test_tablet_sheet_box_for_the_switched_on_person(world, monkeypatch):
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_tablet")
    a, b = world["orders"]
    first, second = world["proposals"]
    client = world["client"]
    sheet = client.get(f"/erp/dashboard/tablet-sheet/{a}").get_data(as_text=True)
    box = sheet[sheet.index("data-graft-box"):sheet.index("data-graft-status")]
    assert sheet.index("현재 작업") < sheet.index("data-graft-box") < sheet.index("foms-tsheet-card__title")
    assert f'data-graft-box="{first}"' in box and "AI 제안 · 시공 잡기" in box and "일정 AI" in box
    assert 'data-graft-act="approve">승인</button>' in box and ">고쳐서</a>" in box and 'data-graft-act="reject-open"' in box
    assert f"/brain?tab=inbox&amp;proposal={first}" in box
    assert re.findall(r'data-graft-code="(\w+)">([^<]+)<', box) == [
        ("wrong_date", "날짜가 틀림"), ("misread", "손님 말을 잘못 읽음"), ("no_slot", "팀 자리 없음"),
        ("already_done", "이미 처리함"), ("other", "그 밖")]
    assert re.search(r'foms-graft-box__after">\d{2}-\d{2}\(\S\) 오전<', box)  # 날짜 + 시간대만
    assert not any(word in sheet for word in CREW_WORDS)
    link = client.get(f"/erp/dashboard/tablet-sheet/{b}").get_data(as_text=True)
    # 도면 담당 맡기기(T14 — run) — 사람을 골라야 해서 [승인] 대신 [고쳐서](승인 대기에서 고른다)
    assert f'data-graft-box="{second}"' in link and ">고쳐서</a>" in link and 'data-graft-act="approve"' not in link
    monkeypatch.setenv(f"{FLAGS['cell_tablet']}_COHORT", "999999")
    assert "data-graft-box" not in client.get(f"/erp/dashboard/tablet-sheet/{a}").get_data(as_text=True)


def test_sheet_box_template_has_no_inline_style_and_no_crew_words():
    for rel in ("templates/orders/partials/tablet_sheet_ai_proposal.html", "static/js/foms/graft-cells.js",
                "static/css/components/foms-graft-cells.css"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert 'style="' not in text and "innerHTML" not in text, rel
        assert not any(word in text for word in ("2팀", "3명", "폭 합", "÷ 300")), rel


def test_tablet_rules_stay_inside_the_tablet_query():
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    tablet = css[css.index("@media (min-width: 992px) and (orientation: landscape) and (pointer: coarse)"):]
    outside = css[:css.index("@media")]
    for name in ("foms-graft-box", "foms-tqcell-quest", "foms-graft-rail__icon"):
        assert name in tablet and f".{name} {{" not in outside.replace("[hidden]", "")
    assert all(line.strip().startswith(("body.erp-mobile-v2-layout", "}", "@media", "")) for line in tablet.splitlines())
    assert re.findall(r"font-size: (?!calc\(\d+(?:\.\d+)?px \* var\(--foms-fs, 1\)\))[^;]+;", css) == ["font-size: 0.85em;"]


# ── 스크립트(node · 가짜 DOM) ─────────────────────────────────────────────
FETCH = re.compile(r"async function fakeFetch\(url, init\) \{.*?\n\}\n", re.S)
ROUTED_FETCH = r"""async function fakeFetch(url, init) {
  const method = (init && init.method) || 'GET';
  posts.push({ url: url, method: method, body: init && init.body ? JSON.parse(init.body) : null });
  for (const r of (input.routes || [])) {
    if (r.method === method && url.indexOf(r.url) === 0) {
      const reply = r.replies.length > 1 ? r.replies.shift() : r.replies[0];
      return { status: reply.status || 200, json: async () => reply.body };
    }
  }
  return { status: 404, json: async () => ({ success: false, data: null, error: '없음' }) };
}
"""


def harness() -> str:
    """옛 회사 지식 시험의 가짜 DOM 에 길마다 답하는 fetch · insertBefore · style 을 더한 것."""
    text = FETCH.sub(lambda _m: ROUTED_FETCH, HARNESS, count=1)
    text = text.replace("this.listeners = {}; this.disabled = false;",
                        "this.listeners = {}; this.style = { props: {}, setProperty(k, v) { this.props[k] = v; } };"
                        " this.disabled = false;", 1)
    text = text.replace("  removeChild(n) {", "  insertBefore(n, ref) { if (!ref) return this.appendChild(n);"
                        " if (n.parentNode) n.parentNode.removeChild(n); n.parentNode = this;"
                        " this.childNodes.splice(this.childNodes.indexOf(ref), 0, n); return n; }\n  removeChild(n) {", 1)
    text = text.replace("  preventDefault() {}\n", "  preventDefault() {}\n  stopPropagation() {}\n", 1)
    text = text.replace("const win = {", "doc.body.parentNode = doc;  // 문서에 단 듣개까지 번진다\nconst win = {\n"
                        "  setTimeout: (fn, ms) => setTimeout(fn, ms),", 1)
    for piece in ("insertBefore(n, ref)", "setProperty", "input.routes", "stopPropagation() {}", "doc.body.parentNode = doc"):
        assert piece in text, piece
    return text


def run_node(html: str, body: str, *, scripts: list[str], routes: list[dict], phone: bool = False, search: str = "") -> dict:
    payload = {"scripts": scripts, "html": html, "attrs": {}, "cards": [], "phone": phone, "search": search,
               "confirm": [], "routes": routes, "body": body}
    out = subprocess.run(["node", "-e", harness()], input=json.dumps(payload, ensure_ascii=False), capture_output=True,
                         text=True, encoding="utf-8", timeout=60)
    assert out.returncode == 0, out.stderr[-1500:]
    return json.loads(out.stdout)


def _ok(data) -> dict:
    return {"body": {"success": True, "data": data, "error": None}}


def _slots_html(world, monkeypatch) -> str:
    """실제로 그린 빈 자리만 모은 조각(가짜 DOM 이 읽는 꼴) — 칩 둘(PC · 폰) · 위 아이콘 · 레일 · 폰 칸."""
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_pc", "cell_tablet", "cell_mobile")
    pages = _pages(world, monkeypatch)
    parts = [re.search(r'<div class="position-relative foms-graft-nav".*?</a></div>', pages["pc"], re.S).group(0),
             re.search(r'<a class="foms-tablet-rail__item foms-graft-rail".*?</a>', pages["shell"], re.S).group(0),
             re.search(r'<a class="foms-tower__quick-card foms-graft-tile".*?</a>', pages["shell"], re.S).group(0)]
    parts += re.findall(r'<a class="foms-graft-chip[^"]*" data-graft-slot="\d+" data-graft-cell="\w+" hidden></a>',
                        pages["pc"] + pages["queue"])
    return "".join(parts)


@NODE
def test_script_asks_badge_once_and_open_once_for_all_visible_orders(world, monkeypatch):
    a, b = world["orders"]
    first = world["proposals"][0]
    html = _slots_html(world, monkeypatch)
    routes = [{"method": "GET", "url": "/api/erp-actions/badge", "replies": [_ok(
                  {"on": {"actions": True, "pc": True, "tablet": True, "mobile": True}, "actions": 3, "knowledge": 11,
                   "total": 14, "labels": ["시공 잡기", "방문 옮기기(시공)", "AS 접수"]})]},
              {"method": "GET", "url": "/api/erp-actions/open", "replies": [_ok({"items": {str(a): {
                  "id": first, "action": "schedule_construction", "label": "시공 잡기", "agent_label": "일정 AI",
                  "can_decide": True}}})]}]
    body = """
      const chips = api.qa('[data-graft-slot]');
      return { calls: api.posts.map(p => p.method + ' ' + p.url),
               chips: chips.map(n => [n.getAttribute('data-graft-slot'), n.getAttribute('data-graft-cell'), api.shown(n),
                                      api.text(n), n.getAttribute('href')]),
               nav: [api.shown(api.q('[data-graft-badge="pc"]')), api.text(api.q('[data-graft-badge="pc"] [data-graft-count]'))],
               rail: api.shown(api.q('[data-graft-badge="tablet"]')),
               tile: [api.shown(api.q('[data-graft-tile]')), api.text(api.q('[data-graft-tile] [data-graft-count]')),
                      api.text(api.q('[data-graft-labels]'))] };"""
    got = run_node(html, body, scripts=[str(CELLS_JS), str(CELLS_JS)], routes=routes)  # 두 번 실려도 한 번만
    assert got["calls"][0] == "GET /api/erp-actions/badge" and len(got["calls"]) == 2
    assert got["calls"][1].startswith("GET /api/erp-actions/open?order_ids=")
    assert sorted(got["calls"][1].split("=")[1].split(",")) == sorted([str(a), str(b)])  # 한 번에 모아(겹침 없이)
    href = f"/brain?tab=inbox&proposal={first}"
    shown = [c for c in got["chips"] if c[2]]
    assert {c[1] for c in shown} == {"pc", "tablet", "mobile"}  # 같은 주문의 PC · 태블릿 표 · 폰 목록 줄 칩
    assert all(c[0] == str(a) and c[3:] == ["AI 제안 · 시공 잡기", href] for c in shown)
    assert all(not c[2] for c in got["chips"] if c[0] == str(b))  # 제안 없는 주문은 숨긴 채
    assert got["nav"] == [True, "14"] and got["rail"] is True
    assert got["tile"] == [True, "3", "시공 잡기 · 방문 옮기기(시공) · AS 접수"]


@NODE
def test_script_keeps_everything_hidden_when_off_or_not_visible(world, monkeypatch):
    html = _slots_html(world, monkeypatch)
    routes = [{"method": "GET", "url": "/api/erp-actions/badge", "replies": [_ok(
        {"on": {"actions": True, "pc": False, "tablet": False, "mobile": True}, "actions": 0, "knowledge": 0, "total": 0,
         "labels": []})]}]
    body = """return { calls: api.posts.map(p => p.url), shown: api.qa('[data-graft-badge], [data-graft-tile], [data-graft-slot]')
                       .filter(api.shown).length, count: api.shown(api.q('[data-graft-badge="pc"] [data-graft-count]')) };"""
    got = run_node(html, body, scripts=[str(CELLS_JS)], routes=routes)
    assert got["calls"][0] == "/api/erp-actions/badge" and len(got["calls"]) == 2  # 폰 칸만 켜짐 → 폰 칩만 묻는다
    asked = got["calls"][1].split("=")[1].split(",")
    assert sorted(asked) == sorted(re.findall(r'data-graft-slot="(\d+)" data-graft-cell="mobile"', html))
    assert got["shown"] == 0 and got["count"] is False  # 폰 칸 수 0 → 숨김
    denied = run_node(html, "return { calls: api.posts.map(p => p.url), shown: api.qa('[data-graft-badge], [data-graft-tile],"
                            " [data-graft-slot]').filter(api.shown).length };", scripts=[str(CELLS_JS)], routes=[])
    assert denied == {"calls": ["/api/erp-actions/badge"], "shown": 0}  # 404(볼 수 없는 사람) — 아무것도 안 보인다


# ── 검수 R1 고침(R-01 · R-02 태블릿 · R-21 · R-24) ──────────────────────────
_SOLAPI_READY = (("FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED", "1"), ("SOLAPI_API_KEY", "k"), ("SOLAPI_API_SECRET", "s"),
                 ("SOLAPI_SENDER_PHONE", "0200000000"), ("SOLAPI_PF_ID_HAUD", "PF-H"),
                 ("SOLAPI_TEMPLATE_CONSTRUCTION_ID_HAUD", "TPL-C-H"))


def _sheet_box(world, order_id: int) -> str:
    sheet = world["client"].get(f"/erp/dashboard/tablet-sheet/{order_id}").get_data(as_text=True)
    return sheet[sheet.index("data-graft-box"):sheet.index("data-graft-status")]


def _proposal_on(stage: str, action: str, params: dict, construction: str | None = None) -> int:
    """손님 휴대폰이 있는 합성 주문 하나 + 그 할 일을 맡은 AI 직원의 제안 하나 — 주문 번호."""
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "합성손님", "phone": "010-0000-0001"}}}
    if construction:
        sd["schedule"] = {"construction": {"date": construction, "time": "오전"}}
    order = Order(received_date="2030-01-01", customer_name="합성손님", phone="010-0000-0000", address="합성 주소",
                  product="합성 품목", status=stage, is_erp_order=True, structured_data=sd)
    sync_erp_flat_columns(order, sd)
    db_session.add(order)
    db_session.commit()
    agent = "agent:cs" if action == "move_construction" else "agent:schedule"
    assert propose(db_session, action=action, proposed_by=agent, order=order, params=params, reason="합성 이유",
                   evidence=[], source_kind="sweep", source_ref="3", level=2, now=now_utc_naive()) is not None
    db_session.commit()
    return order.id


def test_tablet_box_shows_only_edit_when_the_change_asks_for_a_reason(world, monkeypatch):
    """R-01 — 고객 컨펌 뒤 시공일 옮기기는 사유를 묻는 변경이라 상자에 [승인] 없이 [고쳐서](사유를 적는 승인 대기)만."""
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_tablet")
    oid = _proposal_on("CONFIRM", "move_construction", {"date": _day(12), "time": "오후"}, construction=_day(5))
    box = _sheet_box(world, oid)
    assert 'data-graft-act="approve"' not in box and ">고쳐서</a>" in box and 'data-graft-act="reject-open"' in box
    first = _sheet_box(world, world["orders"][0])  # 사유를 묻지 않는 시공 잡기(접수 단계)는 지금처럼 [승인]
    assert 'data-graft-act="approve">승인</button>' in first


def test_tablet_box_shows_the_customer_notice_line_only_when_it_goes_out(world, monkeypatch):
    """R-02 — 시공 잡기 승인이 손님 시공일 안내를 같이 보내면 상자에 그 한 줄. 알림톡을 쓸 수 없으면(스위치 끔) 지금과 같다."""
    import foms.services.kakao_alimtalk as kakao

    monkeypatch.setattr(kakao, "_solapi_send", lambda **kw: pytest.fail("그리기만 — 보내지 않는다"))
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_tablet")
    oid = _proposal_on("RECEIVED", "schedule_construction", {"date": _day(9), "time": "오전"})
    off = _sheet_box(world, oid)
    assert "data-graft-notice" not in off and "손님 알림톡" not in off and 'data-graft-act="approve"' in off
    for name, value in _SOLAPI_READY:
        monkeypatch.setenv(name, value)
    on = _sheet_box(world, oid)
    assert '<span class="foms-graft-box__notice" data-graft-notice>손님 알림톡 1건 — 시공일 안내</span>' in on
    assert on.index("foms-graft-box__after") < on.index("data-graft-notice") < on.index('data-graft-act="approve"')
    assert not any(word in on for word in CREW_WORDS)


def test_phone_card_chip_keeps_its_look_and_gets_a_44px_tap_area():
    """R-24 — 폰 목록 칩은 보이는 높이 22px 그대로, 보이지 않는 겹(::after)이 위아래 44px 를 덮는다. 칩은 겹을 자르지 않는다."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    card = re.search(r"\.foms-graft-chip--card \{(.*?)\}", css, re.S).group(1)
    tap = re.search(r"\.foms-graft-chip--card::after \{(.*?)\}", css, re.S).group(1)
    assert "min-height: 22px;" in card and "position: relative;" in card and "overflow" not in card
    assert "height: 44px;" in tap and "position: absolute;" in tap and "content: \"\";" in tap
    text = re.search(r"\.foms-graft-chip__text \{(.*?)\}", css, re.S).group(1)
    assert "overflow: hidden" in text and "text-overflow: ellipsis" in text


@NODE
def test_slot_of_a_switched_off_cell_stays_hidden_even_if_the_same_order_was_asked(world, monkeypatch):
    """R-21 — 같은 주문의 켜진 칸(태블릿) 답이 와도 꺼진 칸(폰 목록) 칩은 칠하지 않는다. 칩 글은 말줄임 글 칸 안."""
    a = world["orders"][0]
    first = world["proposals"][0]
    html = (f'<a class="foms-graft-chip" data-graft-slot="{a}" data-graft-cell="tablet" hidden></a>'
            f'<a class="foms-graft-chip foms-graft-chip--card" data-graft-slot="{a}" data-graft-cell="mobile" hidden></a>')
    routes = [{"method": "GET", "url": "/api/erp-actions/badge", "replies": [_ok(
                  {"on": {"actions": True, "pc": False, "tablet": True, "mobile": False}, "actions": 1, "knowledge": 0,
                   "total": 1, "labels": ["시공 잡기"]})]},
              {"method": "GET", "url": "/api/erp-actions/open", "replies": [_ok({"items": {str(a): {
                  "id": first, "action": "schedule_construction", "label": "시공 잡기", "agent_label": "일정 AI",
                  "can_decide": True}}})]}]
    body = """return api.qa('[data-graft-slot]').map(n => [n.getAttribute('data-graft-cell'), api.shown(n), api.text(n),
                     n.getAttribute('href'), api.text(n.querySelector('.foms-graft-chip__text'))]);"""
    got = run_node(html, body, scripts=[str(CELLS_JS)], routes=routes)
    href = f"/brain?tab=inbox&proposal={first}"
    assert got == [["tablet", True, "AI 제안 · 시공 잡기", href, "AI 제안 · 시공 잡기"], ["mobile", False, "", None, None]]


@NODE
def test_sheet_box_approve_and_reject_post_once(world, monkeypatch):
    _switch(monkeypatch, "all", "brain_ui", "actions", "cell_tablet")
    a = world["orders"][0]
    first = world["proposals"][0]
    sheet = world["client"].get(f"/erp/dashboard/tablet-sheet/{a}").get_data(as_text=True)
    box = re.search(r'<div class="foms-graft-box".*?data-graft-status></p>\s*</div>', sheet, re.S).group(0)
    base = re.search(r'data-graft-base="(\d+)"', box).group(1)
    routes = [{"method": "POST", "url": f"/api/erp-actions/proposals/{first}/approve",
               "replies": [{"status": 409, "body": {"success": False, "data": {"code": "ACTION_BASE_CHANGED"}, "error": "x"}},
                           _ok({"status": "executed", "message": "승인했어요."})]},
              {"method": "POST", "url": f"/api/erp-actions/proposals/{first}/reject", "replies": [_ok({"status": "rejected"})]}]
    body = """
      const ok = api.q('[data-graft-act="approve"]');
      await api.click(ok);
      const changed = [api.text(api.q('[data-graft-status]')), api.shown(ok)];
      await api.click(api.q('[data-graft-act="reject-open"]'));
      const open = api.shown(api.q('[data-graft-reasons]'));
      await api.click(api.q('[data-graft-code="no_slot"]'));
      return { changed: changed, open: open, posts: api.posts.filter(p => p.method === 'POST'),
               after: [api.text(api.q('[data-graft-status]')), api.qa('[data-graft-act]').filter(api.shown).length] };"""
    got = run_node(box, body, scripts=[str(CELLS_JS)], routes=routes)
    assert got["changed"] == ["제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요", False]
    assert got["open"] is True
    assert got["posts"] == [{"url": f"/api/erp-actions/proposals/{first}/approve", "method": "POST",
                             "body": {"base_version": int(base)}},
                            {"url": f"/api/erp-actions/proposals/{first}/reject", "method": "POST", "body": {"code": "no_slot"}}]
    assert got["after"] == ["거절했어요 — 같은 제안은 다시 오지 않아요.", 0]


def test_rail_tightens_only_while_the_company_knowledge_item_shows():
    """레일 '회사 지식' 칸이 보이면 칸 안쪽 여백을 줄여 알림 · 내 정보가 1180×820 화면 안에 남는다(11-14 사용자 지적 —
    잰 값 853px → 820px). 칸이 숨으면(스위치 끔) 규칙이 걸리지 않아 레일은 그대로다. 손가락 자리는 44px 이상."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    head = ".foms-tablet-rail:has(> .foms-graft-rail:not([hidden])) .foms-tablet-rail__item {"
    block = css[css.index(head):css.index("}", css.index(head))]
    assert "padding-top: 4px;" in block and "padding-bottom: 4px;" in block and "min-height: 44px;" in block
    assert ".foms-tablet-rail:has(> .foms-graft-rail:not([hidden])) .foms-tablet-rail__brand {" in css


def test_chip_never_widens_its_column_or_breaks_the_stage_badge():
    """11-14 사용자 지적 — 칩이 한 줄 폭으로 '현재 작업' 칸을 넓혀 태블릿 '단계' 배지가 '컨/펌'처럼 글자마다 꺾였다. 단계 배지는
    한 줄 · 칩은 fit-content + 낱말 사이 줄바꿈(PC · 태블릿 둘 다). max-content 면 가장 좁은 폭도 한 줄 폭이 되어 표를 밀어낸다."""
    css = (ROOT / "static/css/components/foms-graft-cells.css").read_text(encoding="utf-8")
    assert ".foms-tqcell-stage .foms-stage-badge { white-space: nowrap; }" in css
    tablet = css[css.index(".foms-tqcell-quest .foms-graft-chip {"):]
    tablet = tablet[:tablet.index("}")]
    assert "width: fit-content;" in tablet and "white-space: normal;" in tablet and "word-break: keep-all;" in tablet
    assert "td.erp-quest-cell > .foms-graft-chip { display: flex; width: fit-content; white-space: normal; word-break: keep-all; }" in css

"""생산 파트 표시 30초 받아 오기 — ``GET /api/production/part-marks`` · 화면 배선 · JS(설계서 §15.4 GET 줄 · §15.6 끝, P15-7).

되돌리면 실패하게 짠다. 대조군: 같은 시드에서 since 를 앞당기면 옛 줄도 나온다 · 살아 있는 생산 주문 줄은 나온다(남의
주문만 빠진다) · CS 직원은 200(협력사 · 프리랜서 · 생산 첫 화면을 못 보는 팀만 막힌다) · 주문 4건과 40건의 쿼리 수가 같다.
"""
from __future__ import annotations

import colorsys
import datetime
import re
from dataclasses import dataclass
from itertools import count
from pathlib import Path

import pytest
from sqlalchemy import event
from werkzeug.security import generate_password_hash

from db import db_session, engine
from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.production.part_board import PART_SYNC_OVERLAP_SECONDS, part_sync_cursor
from foms.services.sales_commission.settings import load_settings, save_freelancer
from models import Order, PartnerOrg, ProductionPartMark, User

ROOT = Path(__file__).resolve().parents[2]
SYNC = "/api/production/part-marks"
HOME = "/erp/production/home"
SYNC_JS = ROOT / "static/js/production/foms-production-parts-sync.js"
PARTS_JS = ROOT / "static/js/production/foms-production-parts.js"
VIEWER_JS = ROOT / "static/js/production/foms-production-parts-viewer.js"
PARTS_CSS = ROOT / "static/css/contexts/production/parts.css"
TPL = ROOT / "templates/production"
_seq = count(1)


@dataclass(frozen=True)
class Person:
    id: int
    username: str
    role: str


def _user(name: str, *, team: str | None = "PRODUCTION", role: str = "STAFF", part: str | None = None,
          partner_org_id: int | None = None) -> Person:
    user = User(username=f"pms_{next(_seq)}", password=generate_password_hash("x"), role=role, team=team, name=name,
                is_active=True, production_part=part, partner_org_id=partner_org_id)
    db_session.add(user)
    db_session.commit()
    return Person(user.id, user.username, user.role)


def _login(client, who: Person, *, ptr: str | None = None) -> None:
    with client.session_transaction() as sess:
        sess["user_id"], sess["username"], sess["role"] = who.id, who.username, who.role
    if ptr:
        client.set_cookie("foms_ptr", ptr, domain="localhost")


def _order(n: int = 2, *, stage: str = "PRODUCTION", erp: bool = True, deleted: bool = False) -> tuple[int, list[str]]:
    prefix = f"s{next(_seq)}"
    files = [{"key": f"{prefix}/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"{prefix}-s{j}"} for j in range(n)]
    today = get_today_kst().isoformat()
    sd = {"workflow": {"stage": stage}, "parties": {"customer": {"name": "받기고객"}}, "drawing_current_files": files,
          "schedule": {"construction": {"date": today}}}
    order = Order(received_date=today, customer_name="받기고객", phone="010-0000-0000", address="서울", product="거실장",
                  status="DELETED" if deleted else stage, is_erp_order=erp, erp_stage_code=stage,
                  erp_construction_date=today, structured_data=sd)
    db_session.add(order)
    db_session.commit()
    return order.id, [f["key"] for f in files]


def _mark(order_id: int, key: str, part: str, state: str, at: datetime.datetime, *, who: Person | None = None,
          name: str | None = None) -> None:
    done = state in ("DONE", "BASIC")
    db_session.add(ProductionPartMark(
        order_id=order_id, drawing_key=key, part=part, state=state,
        picked_by_user_id=who.id if who and state != "BASIC" else None, picked_by_name=name if state != "BASIC" else None,
        done_by_user_id=who.id if who and done else None, done_by_name=name if done else None,
        updated_by_user_id=who.id if who else None, updated_at=at,
    ))
    db_session.commit()


def _get(client, ids, since: str):
    return client.get(SYNC, query_string={"order_ids": ",".join(str(i) for i in ids), "since": since})


def _marks(resp) -> list[dict]:
    assert resp.status_code == 200, (resp.status_code, resp.get_data(as_text=True))
    body = resp.get_json()
    assert set(body) == {"success", "data", "error"} and body["success"] is True and body["error"] is None
    return body["data"]["marks"]


# --------------------------------------------------------------------------- #
# GET — since 뒤 줄만
# --------------------------------------------------------------------------- #
def test_only_rows_updated_after_since_come_back(client):
    park = _user("박재단", part="cut")
    oid, keys = _order(3)
    base = now_utc_naive()
    since = base.isoformat()
    _mark(oid, keys[0], "cut", "NEED", base - datetime.timedelta(minutes=5), who=park, name="박재단")  # 옛 줄
    _mark(oid, keys[1], "cut", "DONE", base + datetime.timedelta(seconds=3), who=park, name="박재단")
    _mark(oid, keys[2], "edge", "NEED", base + datetime.timedelta(seconds=4), who=park, name="박엣지")
    _login(client, _user("김재단", part="cut"))

    marks = _marks(_get(client, [oid], since))
    assert [(m["drawing_key"], m["part"]) for m in marks] == [(keys[1], "cut"), (keys[2], "edge")]
    done = marks[0]
    assert done["order_id"] == oid and done["state"] == "done" and done["done_by_name"] == "박재단"
    assert done["done_by_user_id"] == park.id and done["picked_by_name"] == "박재단"
    assert (done["word"], done["tone"]) == ("끝", "done")  # 다른 파트 한 줄 낱말도 서버가 준다(SSOT)
    assert (marks[1]["word"], marks[1]["tone"]) == ("중", "need")
    # 대조군: since 를 앞당기면 옛 줄도 나온다(거르기가 since 때문임을 보인다)
    older = (base - datetime.timedelta(hours=1)).isoformat()
    assert len(_marks(_get(client, [oid], older))) == 3
    # 경계: updated_at == since 는 안 나온다(> since)
    assert [m["drawing_key"] for m in _marks(_get(client, [oid], (base + datetime.timedelta(seconds=3)).isoformat()))] == [keys[2]]


def test_server_time_is_server_clock_cursor_and_usable_as_next_since(client):
    oid, keys = _order(1)
    _login(client, _user("상담", team="CS"))
    before = now_utc_naive()
    data = _get(client, [oid], before.isoformat()).get_json()["data"]
    after = now_utc_naive()
    cursor = datetime.datetime.fromisoformat(data["server_time"])
    overlap = datetime.timedelta(seconds=PART_SYNC_OVERLAP_SECONDS)
    assert before - overlap <= cursor <= after - overlap  # 서버 시계 − 커밋 지연 겹침(기기 시계 아님)
    assert part_sync_cursor(datetime.datetime(2026, 11, 13, 9, 0, 0)) == "2026-11-13T08:59:45.000000"
    # 그 값을 다음 since 로 그대로 되보내도 받는다(꼴이 맞다)
    assert _marks(_get(client, [oid], data["server_time"])) == []


def test_other_peoples_order_ids_are_dropped_silently(client):
    park = _user("박재단", part="cut")
    live, live_keys = _order(1)
    gone, gone_keys = _order(1, deleted=True)
    not_erp, ne_keys = _order(1, erp=False)
    other_stage, os_keys = _order(1, stage="RECEIVED")
    at = now_utc_naive() + datetime.timedelta(seconds=5)
    for oid, keys in ((live, live_keys), (gone, gone_keys), (not_erp, ne_keys), (other_stage, os_keys)):
        _mark(oid, keys[0], "cut", "NEED", at, who=park, name="박재단")
    _login(client, _user("김재단", part="cut"))
    since = (at - datetime.timedelta(minutes=1)).isoformat()
    marks = _marks(_get(client, [gone, not_erp, other_stage, 987654321, live], since))
    assert [m["order_id"] for m in marks] == [live]  # 대조군: 살아 있는 생산 주문은 나온다


def test_partner_freelancer_and_non_home_team_are_refused(client):
    oid, keys = _order(1)
    _mark(oid, keys[0], "cut", "NEED", now_utc_naive() + datetime.timedelta(seconds=5))
    since = now_utc_naive().isoformat()
    _login(client, _user("상담", team="CS"))
    assert len(_marks(_get(client, [oid], since))) == 1  # 대조군: 우리 직원(읽기 전용)은 받는다

    org = PartnerOrg(name=f"협력{next(_seq)}")
    db_session.add(org)
    db_session.commit()
    _login(client, _user("협력직원", team=None, role="PARTNER", partner_org_id=org.id))
    refused = _get(client, [oid], since)
    assert refused.status_code in (302, 403) and b"drawing_key" not in refused.get_data()

    fl = _user("프리영업", team="SALES")
    save_freelancer(db_session, fl.id, {"match_name": f"프리{next(_seq)}", "start_month": "2020-01", "tax_type": "NONE",
                                        "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    _login(client, fl)
    refused = _get(client, [oid], since)
    assert refused.status_code == 403 and b"drawing_key" not in refused.get_data()

    _login(client, _user("도면사람", team="DRAWING"))  # 생산 첫 화면을 못 보는 팀 — 이 길의 문지기
    refused = _get(client, [oid], since)
    assert refused.status_code == 403 and refused.get_json()["success"] is False


def test_bad_query_values_are_400(client):
    oid, _ = _order(1)
    _login(client, _user("상담", team="CS"))
    since = now_utc_naive().isoformat()
    assert client.get(SYNC, query_string={"order_ids": str(oid)}).status_code == 400  # since 없음
    assert _get(client, [oid], "어제").status_code == 400
    assert client.get(SYNC, query_string={"order_ids": "1,x", "since": since}).status_code == 400
    many = _get(client, range(1, 302), since)
    assert many.status_code == 400 and many.get_json()["data"]["code"] == "TOO_MANY"
    assert _get(client, range(1, 301), since).status_code == 200  # 대조군: 300건까지는 받는다


def _count(fn):
    seen = {"n": 0, "sql": []}

    def _before(conn, cursor, statement, params, context, executemany):
        seen["n"] += 1
        seen["sql"].append(statement)

    event.listen(engine, "before_cursor_execute", _before)
    try:
        result = fn()
    finally:
        event.remove(engine, "before_cursor_execute", _before)
    return result, seen


#: 실측(2026-11-13, SQLite 레인): 요청 하나 = 2(로그인 사용자 · 표시 줄 ⋈ 주문 한 번). 상한 = 실측 + 30% 내림.
SYNC_QUERY_CAP = 2


def test_query_count_is_one_read_whatever_the_order_count(client):
    park = _user("박재단", part="cut")
    at = now_utc_naive() + datetime.timedelta(seconds=5)
    small, large = [], []
    for bucket, n in ((small, 4), (large, 40)):
        for _ in range(n):
            oid, keys = _order(2)
            _mark(oid, keys[0], "cut", "NEED", at, who=park, name="박재단")
            _mark(oid, keys[1], "edge", "DONE", at, who=park, name="박엣지")
            bucket.append(oid)
    _login(client, _user("김재단", part="cut"))
    since = now_utc_naive().isoformat()
    _get(client, small, since)  # 세션 첫 요청의 last_login 쓰기를 미리 치운다(요청마다 나는 쿼리가 아니다)
    resp4, q4 = _count(lambda: _get(client, small, since))
    resp40, q40 = _count(lambda: _get(client, large, since))
    assert len(_marks(resp4)) == 8 and len(_marks(resp40)) == 80
    assert q4["n"] == q40["n"] <= SYNC_QUERY_CAP, (q4["n"], q40["n"], [s[:80] for s in q4["sql"]])
    reads = [s for s in q40["sql"] if "production_part_marks" in s]
    assert len(reads) == 1 and "JOIN orders" in reads[0] and "production_part_marks.order_id IN" in reads[0]


# --------------------------------------------------------------------------- #
# 화면 배선 — sync.js 가 실리고 첫 since 가 서버가 그린 시각
# --------------------------------------------------------------------------- #
@pytest.fixture
def cohort(monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


@pytest.mark.parametrize("who", ["part", "readonly"])
def test_home_loads_sync_js_with_server_since(client, cohort, who):
    _order(2)
    account = _user("김재단", part="cut") if who == "part" else _user("상담", team="CS")
    _login(client, account, ptr="coarse")
    before = now_utc_naive()
    resp = client.get(HOME if who == "part" else HOME + "?tab=parts&part=cut")
    after = now_utc_naive()
    html = resp.get_data(as_text=True)
    assert resp.status_code == 200 and "data-pp-card" in html
    assert re.search(r'js/production/foms-production-parts-sync\.js\?v=\d{8}[a-z]" defer', html)
    found = re.findall(r'data-pp-since="([^"]+)"', html)
    assert len(found) == 1
    since = datetime.datetime.fromisoformat(found[0])
    overlap = datetime.timedelta(seconds=PART_SYNC_OVERLAP_SECONDS)
    assert before - overlap <= since <= after - overlap
    # 다른 파트 한 줄 낱말마다 받아 오기가 찾을 자리
    assert re.search(r'class="fph-by pp-w-none" data-pp-other="edge"', html)


def test_home_without_board_has_no_sync_js(client, cohort):
    _order(1)
    _login(client, _user("관리자", team="CS", role="ADMIN"), ptr="fine")  # 마우스 PC — 판 없음
    html = client.get(HOME).get_data(as_text=True)
    assert "foms-production-parts-sync.js" not in html and "data-pp-since" not in html


# --------------------------------------------------------------------------- #
# JS 정적 단언
# --------------------------------------------------------------------------- #
def test_sync_js_every_30s_only_when_visible_and_online():
    src = SYNC_JS.read_text(encoding="utf-8")
    assert "var SYNC_EVERY_MS = 30000;" in src and "bound.syncTimer = window.setInterval(" in src
    assert src.count("setInterval(") == 1 and "setTimeout(" not in src
    # 셸 조각 교체로 다시 돌면 화면마다 한 번 묶고, 타이머는 문서에 하나 — 지금 화면의 받기만 부른다(11-14)
    assert "if (!bound.syncTimer) {" in src and "bound.syncTick = tick;" in src
    assert "document.visibilityState === 'visible'" in src and "navigator.onLine !== false" in src
    assert "document.contains(root)" in src[src.index("function canSync()"):]  # 떠난 화면은 받지 않는다
    tick = src[src.index("function tick()"):]
    assert tick.index("!canSync()") < tick.index("fetchChunk(")
    assert "window.__FOMS_PROD_PARTS_BOUND" in src and "if (bound.sync === root) { return; }" in src
    assert "body.success === true" in src and "try {" in src and ".catch(" in src
    assert "var MAX_IDS = 300;" in src


def test_sync_js_since_comes_only_from_server():
    src = SYNC_JS.read_text(encoding="utf-8")
    assignments = re.findall(r"(?<![\w.])since = ([^;]+);", src)
    assert assignments == ["holder.getAttribute('data-pp-since') || ''", "next"], assignments
    assert "var next = results[0].server_time;" in src and "next = r.server_time;" in src
    assert not re.search(r"Date\.now|new Date|performance\.now|getTime\(", src), "기기 시계로 since 를 만들면 안 된다"


def test_sync_js_reuses_parts_card_fixer_not_a_copy():
    sync = SYNC_JS.read_text(encoding="utf-8")
    parts = PARTS_JS.read_text(encoding="utf-8")
    assert "window.FomsPartsCards = { apply: applyMark, find: findCard, held:" in parts
    assert "window.FomsPartsCards" in sync and "cards.apply(card, mark)" in sync and "cards.held(card)" in sync
    for name in ("applyMark", "renderAct", "bumpCounts", "membership", "findCard"):
        assert f"function {name}(" not in sync, f"{name} 를 받아 오기 JS 에 복사하면 안 된다"
    # 내 확인 창 · 저장 중 카드는 건너뛰고, 그 판은 since 를 옮기지 않는다
    assert "if (cards.held(card)) { complete = false; return; }" in sync
    assert "if (applyMarks(marks)) { since = next; }" in sync
    assert "pending.cards.indexOf(card) >= 0" in parts


def test_parts_js_binds_writes_only_with_modal():
    """읽기 전용(확인 창 없음)은 parts.js 가 카드 고치기만 내보내고 누름 · 쓰기를 묶지 않는다(D55 · P15-7)."""
    src = PARTS_JS.read_text(encoding="utf-8")
    export = src.index("window.FomsPartsCards = { apply: applyMark")
    stop = src.index("if (!modal) { return; }")
    click = src.index("root.addEventListener('click'")
    assert export < stop < click and src.count("addEventListener(") == 1  # 누름은 창 문 뒤(화면마다 한 번)
    # Esc 는 창 문 뒤에서 내보내고, 문서 리스너는 viewer 가 문서에 한 번만 단다(셸 조각 교체로 다시 돌아도 안 쌓인다, 11-14)
    assert src.index("window.FomsPartsCards.onEscape = function") > stop and "document.addEventListener" not in src
    assert "if (!root || !board || !modal)" not in src  # 창이 없어도 고치기는 내보낸다
    assert "var WRITABLE = !!(modal && cfg.writable);" in src
    render = src[src.index("function renderAct("):src.index("function applyMark(")]
    assert "if (!WRITABLE) { return; }" in render and "if (WRITABLE) { box.appendChild(el('button'" in render
    assert "var canUndo = WRITABLE &&" in render


def test_broken_image_becomes_text_on_card_and_viewer():
    viewer = VIEWER_JS.read_text(encoding="utf-8")
    assert "var BROKEN_TEXT = '그림을 못 불러왔어요';" in viewer
    listener = viewer[viewer.index("root.addEventListener('error'"):]
    listener = listener[:listener.index("}, true);") + 9]
    assert "markBroken(img)" in listener and "pp-thumb" in listener and "img === vImg" in listener
    assert "img.complete && img.naturalWidth === 0" in viewer  # defer 전에 실패한 그림도 잡는다
    assert "clearBroken(vImg);" in viewer  # 크게 보기는 장을 바꿀 때 글을 지운다
    for path in [*(TPL / "partials").glob("home_parts*.html"), TPL / "home.html", SYNC_JS, PARTS_JS, VIEWER_JS]:
        assert not re.search(r"onerror\s*=|\.onerror\b", path.read_text(encoding="utf-8")), path.name
    css = PARTS_CSS.read_text(encoding="utf-8")
    assert "content: \"그림을 못 불러왔어요\"" not in css  # 글은 CSS 가 아니라 JS 가 넣는다
    tokens = dict(re.findall(r"(--fph-[a-z]+-\d+):\s*(#[0-9a-f]{6})", css))
    rule = re.search(r"\.pp-img\.is-broken, \.pp-vimg\.is-broken \{([^}]*)\}", css).group(1)
    bg = tokens[re.search(r"background: var\((--fph-[a-z]+-\d+)\)", rule).group(1)]
    _, _, sat = colorsys.rgb_to_hls(*(int(bg[i:i + 2], 16) / 255 for i in (1, 3, 5)))
    assert sat >= 0.3, f"못 불러온 그림 칸이 무채색이에요(D52): {bg}"
    text = re.search(r"\.pp-broken \{([^}]*)\}", css).group(1)
    assert re.search(r"color: var\(--fph-[a-z]+-700\)", text)


def test_confirm_list_shows_broken_note_for_missing_picture():
    """일괄 확인 창 줄: 카드 그림을 못 받아 숨긴 경우 숨은 그림을 복사하지 않고 같은 안내 글을 넣는다(로컬 E2E 11-13)."""
    import pathlib

    src = pathlib.Path("static/js/production/foms-production-parts.js").read_text(encoding="utf-8")
    assert "img && !img.hidden ? Object.assign(img.cloneNode(false), { loading: 'eager', decoding: 'sync' })" in src
    assert "el('span', 'pp-broken', '그림을 못 불러왔어요')" in src


def test_switch_head_fits_one_row_without_waste():
    """관리자 · 읽기 전용 장 머리: 날짜 · 파트 고르기 · 일괄 · 칸 단추 한 줄(사용자 "쓸데없이 낭비되는 공간 없게", 11-13).
    일괄 단추가 보이면 '안 본 도면 N장' 글은 뺀다(단추에 장 수), 아랫줄로 미는 규칙(flex-basis 100%)은 없다."""
    import pathlib

    css = pathlib.Path("static/css/contexts/production/parts.css").read_text(encoding="utf-8")
    tpl = pathlib.Path("templates/production/partials/home_parts.html").read_text(encoding="utf-8")
    assert '.pp-head--switch .pp-bulk:has([data-pp-act="bulk"]:not([hidden])) .pp-unseen { display: none; }' in css
    assert "flex-basis: 100%" not in css.split(".pp-head--switch", 1)[1]
    assert "pp-head--switch" in tpl

"""켜진 프리랜서의 생산 첫 화면(``/erp/production/home``) — 자기 주문만 · 보기만.

사장님 결정(2026-11-27): "새 화면에 '내 주문만' 만들어 보내기" · [확인했어요]는 "회사 영업처럼 보이게" · 옛 주소는 "이것도 지우기".
묶음 파일 foms/services/auth/freelancer_screens/production.py, 거르기 한 곳 foms/services/production/home_scope.py.

① 읽기 길 전수(라우트 표 래칫) — 생산 화면 · 생산 API 의 모든 GET 길이 "허용+범위 / 거절" 로 적혀 있다. 새 길은 빨강.
② 프리랜서 가 로 모든 허용 길(탭 다섯 × PC · 태블릿 · 폰, 조각, 판, 시트 · 인쇄): 남의 주문 · 묘비의 이름 · 번호 · 전화 끝자리 0,
   숫자(전체 · 탭 건수 · 띠 · 바뀐 것)는 내 주문으로 센 값.
③ 음성 대조군 — 회사 영업 직원 · 꺼진 프리랜서는 같은 길에서 전부 본다. 거르기를 끄면 프리랜서에게도 남의 주문이 보인다.
④ 남의 번호(주소 · query · 판 조각 · 시트 · 인쇄 · 없는 번호) = 404. 문지기 표를 빼도 핸들러가 한 번 더 막는다.
⑤ 쓰기 전수 — 생산 쓰기 여덟: 내 것 403 · 남의 것 404(주문 그대로), [확인했어요]: 내 것 200 · 남의 것 404.
⑥ 화면 표식 — [확인했어요] 말고 쓰기 표식 0. 도면 카드 읽기(바뀐 기록)도 안 그린다.
⑧ 담당에서 빠지면 다음 요청부터 사라진다. 프리랜서로 켜면 다음 요청부터 내 주문만.
⑨ 쿼리 수 — 프리랜서 날짜 탭 ≤ 직원 날짜 탭 + 1.
모든 이름 · 번호는 가짜 값이다.
"""
from __future__ import annotations

import copy
from contextlib import contextmanager

import pytest
from sqlalchemy import event
from sqlalchemy.orm.attributes import flag_modified

import foms.services.auth.freelancer_scope as scope
import foms.services.production_home_read_model as home_read_model
import foms.web.production.home as home_page
from db import db_session, engine
from foms.services import dashboard_counts
from foms.services.auth.freelancer_order_rights import CLOSED_ORDER_ENDPOINTS, OWN_ORDER_ENDPOINTS
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_DENIED_MSG,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    FREELANCER_ORDER_QUERY_ARGS,
    FREELANCER_ORDER_VIEW_ARGS,
)
from foms.services.auth.freelancer_screens import production as bundle
from foms.services.production.part_access import VIEW_NONE, VIEW_READONLY, part_view_mode
from models import Order, OrderEvent, OrderFreelancerLink
from tests.support.freelancer_production_home_seed import (
    DEVICES,
    HOME,
    MATCH_OFF,
    SHELL,
    client_for,
    designate,
    leaks,
    linked_order_ids,
    make_order,
    named_user,
    seed_world,
    tomorrow,
)

_FL_HOME = "/erp/dashboard"
_TABS = ("date", "steps", "changes", "all", "parts")
_MISSING = 99_999_999
_ACK = 'data-kanban-action="change-ack"'
#: 쓰기 · 도면 카드 표식 — 프리랜서 응답에 하나도 없어야 한다([확인했어요] ``_ACK`` 만 남는다).
_WRITE_MARKERS = ("data-tablet-sheet-action", "data-foms-home-step-done", "data-foms-step-finish", "data-foms-sheet-step=",
                  "data-foms-sheet-reopen", "data-foms-prod-edit", "data-pp-", "data-foms-sheet-loglink")


@pytest.fixture()
def world(app, monkeypatch):
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")
    with dashboard_counts._cache_lock:
        dashboard_counts._cache.clear()
    return seed_world()


def _get(app, user, path: str, device: str | None = None, headers: dict | None = None, *, status: int = 200) -> str:
    resp = client_for(app, user, device).get(path, headers=headers or {})
    assert resp.status_code == status, (path, device, resp.status_code)
    return resp.get_data(as_text=True)


def _list_paths() -> list[tuple[str, dict | None]]:
    """주문 번호 없는 허용 길 — 탭 다섯 · 확인한 것 더 보기 · 날 조각 · 셸 조각(§3-3 의 1 ~ 7)."""
    day = tomorrow()
    paths: list[tuple[str, dict | None]] = [(f"{HOME}?tab={tab}", None) for tab in _TABS]
    paths += [(f"{HOME}?tab=changes&done=all", None), (f"{HOME}?view=day&day={day}", None),
              (f"{HOME}?tab=parts&view=day&day={day}", None)]
    paths += [(f"{HOME}?tab={tab}&view=fragment", SHELL) for tab in _TABS]
    return paths


def _order_paths(order_id: int) -> list[str]:
    return [f"/erp/production/sheet/{order_id}", f"/erp/production/print/{order_id}"]


def _panel(order_id: int) -> str:
    return f"{HOME}?tab=steps&view=panel&step=cut&order={order_id}"


# --------------------------------------------------------------------------
# ① 읽기 길 전수 — 라우트 표 래칫
# --------------------------------------------------------------------------
_SCOPED, _DENIED = "허용+범위", "거절"
_READ_ROUTES = {
    "erp_production_page.erp_production_home": _SCOPED,          # 탭 · 조각 · 판 · 숫자(view=counts) · ?order= (query 검사 + 들머리 거르기)
    "erp_production_page.erp_production_sheet_page": _SCOPED,    # URL 번호 검사 + 핸들러 user_can_read_order
    "erp_production_page.erp_production_print_sheet": _SCOPED,   # 같은 두 겹
    "erp_production_page.erp_production_part_thumb": _DENIED,    # 도면 카드 작은 그림
    "production_part_marks.api_part_marks_since": _DENIED,       # 도면 카드 30초 받아 오기
    "production_part_marks.api_part_sheet": _DENIED,             # PC 도면 창
    "production_part_marks.api_part_history": _DENIED,           # 바뀐 기록
    "erp_orders_production.api_production_steps_get": _DENIED,   # 공정 읽기(지우는 길)
}
#: 다음 조각이 라우트째 지우는 길 — 지워진 뒤 표에만 남아도 된다(없는 길도 문지기 기본 거부다).
#: 옛 보드 · 옛 옆 시트 라우트는 2026-11-27 지웠다(표에서도 뺐다). 공정 읽기 GET 은 뒤에 지운다(설계서 §6-3).
_GOING_AWAY = {"erp_orders_production.api_production_steps_get"}


def _production_rules(app, *, read: bool) -> list:
    """주소나 endpoint 이름에 production 이 든 규칙 — ``read`` 면 GET 길, 아니면 쓰기 길."""
    rules = []
    for rule in app.url_map.iter_rules():
        if "production" not in rule.rule and "production" not in rule.endpoint:
            continue
        methods = rule.methods - {"HEAD", "OPTIONS"}
        if ("GET" in methods) if read else bool(methods - {"GET"}):
            rules.append(rule)
    return rules


def _table_gap(app, table: dict, *, read: bool) -> tuple[list[str], list[str]]:
    """(표에 없는 길, 표에만 있는 길)."""
    found = {rule.endpoint for rule in _production_rules(app, read=read)}
    return sorted(found - set(table)), sorted(set(table) - found)


def test_every_production_read_route_is_classified(world, app):
    new, stale = _table_gap(app, _READ_ROUTES, read=True)
    assert new == [], "표에 없는 생산 읽기 길 — 프리랜서에게 어떻게 답하는지 적어라(허용이면 '내 주문만' 거르기와 함께)"
    assert set(stale) <= _GOING_AWAY
    scoped = {endpoint for endpoint, kind in _READ_ROUTES.items() if kind == _SCOPED}
    assert scoped == set(bundle.ALLOWED_ENDPOINTS)  # 문은 셋뿐
    rules = {rule.endpoint: rule for rule in _production_rules(app, read=True)}
    for endpoint in scoped:
        assert endpoint in FREELANCER_ALLOWED_ENDPOINTS
        assert endpoint in FREELANCER_ORDER_VIEW_ARGS or endpoint in FREELANCER_ORDER_QUERY_ARGS, endpoint
        assert rules[endpoint].methods <= {"GET", "HEAD", "OPTIONS"}, endpoint  # GET 만 — 묶음에 방법 제한이 없는 까닭
    assert FREELANCER_ORDER_QUERY_ARGS["erp_production_page.erp_production_home"] == ("order", "focus_order")
    # 거절 길: 허용 목록 · "내 주문 일 API" 어디에도 없고, 내 주문 번호로 불러도 문지기가 막는다(화면 302 · API 403).
    client = client_for(app, world.fl_a, "pc")
    for endpoint in sorted(set(_READ_ROUTES) - scoped - set(stale)):
        assert endpoint not in FREELANCER_ALLOWED_ENDPOINTS and endpoint not in OWN_ORDER_ENDPOINTS, endpoint
        rule = rules[endpoint]
        path = rule.build({arg: world.own.id for arg in rule.arguments}, append_unknown=False)[1]
        resp = client.get(f"{path}?order_id={world.own.id}&order_ids={world.own.id}&focus_order={world.own.id}")
        if "/api/" in path:
            assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG, endpoint
        else:
            assert resp.status_code == 302 and resp.headers["Location"].endswith(_FL_HOME), endpoint
        assert world.own.customer not in resp.get_data(as_text=True), endpoint
    # 음성 대조군(모집단 안): 표에서 한 줄을 빼면 래칫이 정확히 그 길을 잡는다.
    trimmed = {k: v for k, v in _READ_ROUTES.items() if k != "production_part_marks.api_part_history"}
    assert _table_gap(app, trimmed, read=True)[0] == ["production_part_marks.api_part_history"]


# --------------------------------------------------------------------------
# ② · ③ · ⑥ 모든 허용 길 — 프리랜서는 내 것만, 회사 영업 직원은 전부
# --------------------------------------------------------------------------
@pytest.mark.parametrize("device", sorted(DEVICES))
def test_every_allowed_path_shows_only_own_orders(world, app, device):
    for path, headers in _list_paths():
        mine = _get(app, world.fl_a, path, device, headers)
        own = world.own_tomb if "tab=changes" in path else world.own
        assert own.customer in mine, (path, "내 주문이 안 보인다")
        assert leaks(mine, world.foreign) == [], path
        assert [m for m in _WRITE_MARKERS if m in mine] == [], path
        assert (_ACK in mine) is ("tab=changes" in path), path  # [확인했어요]만 — 회사 영업처럼
        # 음성 대조군(같은 길 · 같은 기기): 회사 영업 직원은 남의 주문 · 묘비도 본다.
        control = _get(app, world.staff, path, device, headers)
        expected = world.other_tombs if "tab=changes" in path else [world.b_order, world.staff_order]
        assert [o.customer for o in expected if o.customer not in control] == [], path
    for path in _order_paths(world.own.id):
        mine = _get(app, world.fl_a, path, device)
        assert world.own.customer in mine and leaks(mine, world.foreign) == [], path
        assert [m for m in _WRITE_MARKERS if m in mine] == [], path
    for path in _order_paths(world.b_order.id):
        assert world.b_order.customer in _get(app, world.staff, path, device), path


def test_leak_needles_are_visible_to_staff(world, app):
    """음성 대조군: 새는지 보는 세 가지(이름 · 전화 끝자리 · 주문 번호)가 직원 화면에는 실제로 실린다 — 빈 검사가 아니다."""
    body = _get(app, world.staff, f"{HOME}?tab=all", "tablet")
    for order in world.others:
        assert {what for _name, what in leaks(body, [order])} == {"이름", "전화 끝자리", "주문 번호"}, order.customer
    assert {what for _name, what in leaks(_get(app, world.fl_a, f"{HOME}?tab=all", "tablet"), [world.own])} == {
        "이름", "전화 끝자리", "주문 번호"}


def test_step_panel_fragment_is_own_only(world, app):
    """'내 공정' 판 하나 조각(태블릿 가로) — 내 줄은 열리고, 직원은 남의 줄도 연다."""
    mine = _get(app, world.fl_a, _panel(world.own.id), "tablet")
    assert world.own.customer in mine and leaks(mine, world.foreign) == []
    assert [m for m in _WRITE_MARKERS if m in mine] == []
    assert world.b_order.customer in _get(app, world.staff, _panel(world.b_order.id), "tablet")


def _home_ctx(app, user, monkeypatch, query: str = "") -> dict:
    """첫 화면이 템플릿에 넘기는 값(행 · 총계 · 탭 건수 · 띠 · 받은함)."""
    captured: dict = {}

    def _fake_render(_template_name, **ctx):
        captured.clear()
        captured.update(ctx)
        return ""

    monkeypatch.setattr(home_page, "render_template", _fake_render)
    assert client_for(app, user, "tablet").get(HOME + query).status_code == 200
    return dict(captured)


def _numbers(ctx: dict) -> dict:
    days = ctx["days"]
    return {"rows": sorted(r["id"] for r in ctx["rows"]), "total": ctx["total"], "all": ctx["counts"]["all"],
            "prod": ctx["counts"]["prod"], "making": ctx["counts"]["making"], "changed": ctx["counts"]["changed"],
            "strip": sum(b["total"] for b in days["strip"] + days["footer"])}


def test_counts_are_own_only(world, app, monkeypatch):
    """전체 N건 · 탭 건수 · 띠 숫자 · 바뀐 것 = 내 주문으로 센 값. 직원은 주문 5 · 묘비 3."""
    own = world.own.id
    assert _numbers(_home_ctx(app, world.fl_a, monkeypatch)) == {
        "rows": [own], "total": 1, "all": 1, "prod": 1, "making": 1, "changed": 1, "strip": 1}
    changes = _home_ctx(app, world.fl_a, monkeypatch, "?tab=changes")["changes"]
    assert changes["count"] == 1 and [item["id"] for item in changes["inbox"]] == [world.own_tomb.id]
    everything = sorted([own] + [o.id for o in world.others])
    staff = _numbers(_home_ctx(app, world.staff, monkeypatch))
    assert staff["rows"] == everything and staff["total"] == 5 and staff["all"] == 5 and staff["changed"] == 3
    assert staff["making"] == 4 and staff["strip"] == 5  # 생산 단계 넷(시공 단계 하나는 제작 완료)
    # '지난 주문 숨김 수'(캡에 밀려 안 읽은 수)도 같은 거른 조회에서 센다 — 캡을 0 으로 두면 직원은 남의 옛 주문 1, 프리랜서는 0.
    monkeypatch.setattr(home_read_model, "PRODUCTION_KANBAN_MAX_ROWS", 0)
    with app.test_request_context("/"):
        assert home_read_model.build_production_home(db_session, world.staff)[1] == {"past_hidden": 1, "total": 5}
        assert home_read_model.build_production_home(db_session, world.fl_a)[1] == {"past_hidden": 0, "total": 1}


def _counts(app, user) -> dict:
    resp = client_for(app, user, "tablet").get(f"{HOME}?view=counts")
    assert resp.status_code == 200 and resp.headers["Cache-Control"] == "private, no-store"
    body = resp.get_json()
    assert body["success"] is True and body["error"] is None
    return body["data"]["counts"]


def test_counts_view_is_own_only(world, app, monkeypatch):
    """위 탭 숫자만(``?view=counts`` — 도면 카드 쓰기 뒤 parts-fresh.js)도 행 · 묘비 두 들머리가 '내 주문만'.

    프리랜서 가 = 내 주문 1 · 내 묘비 1, 직원 대조군 = 남은 공정 4 · 바뀐 것 3(위 시험의 화면 숫자와 같은 값).
    음성 대조: 이 길의 묘비 들머리만 거르기를 끄면 남의 취소 주문 수가 '바뀐 것'에 샌다(2026-11-27 고친 자리).
    """
    assert _counts(app, world.fl_a) == {"making": 1, "changed": 1}
    assert _counts(app, world.staff) == {"making": 4, "changed": 3}
    monkeypatch.setattr(home_page, "production_home_mine_only", lambda user: False)  # 행은 읽기 모델이 여전히 거른다
    assert _counts(app, world.fl_a) == {"making": 1, "changed": 3}


def test_inactive_freelancer_and_switched_off_filter_see_everything(world, app, monkeypatch):
    """음성 대조군 둘: 꺼진 프리랜서는 보통 영업 직원이고, 거르기 함수를 끄면 켜진 프리랜서에게도 남의 주문이 실린다."""
    for path in (f"{HOME}?tab=all", f"{HOME}?tab=changes"):
        body = _get(app, world.off, path, "tablet")
        expected = world.other_tombs if "changes" in path else world.others
        assert [o.customer for o in expected if o.customer not in body] == [], path
    assert world.b_order.customer in _get(app, world.off, _order_paths(world.b_order.id)[0], "tablet")
    for module in (home_read_model, home_page):
        monkeypatch.setattr(module, "production_home_mine_only", lambda user: False)
    assert leaks(_get(app, world.fl_a, f"{HOME}?tab=all", "tablet"), world.others) != []
    assert leaks(_get(app, world.fl_a, f"{HOME}?tab=changes", "tablet"), world.other_tombs) != []


# --------------------------------------------------------------------------
# ④ 남의 번호 — 404, 그 주문 글 없음
# --------------------------------------------------------------------------
def _foreign_paths(order_id: int) -> list[tuple[str, str | None]]:
    return [(f"{HOME}?order={order_id}", None), (f"{HOME}?focus_order={order_id}", None),
            (f"{HOME}?tab=all&order={order_id}", "pc"), (_panel(order_id), "tablet"),
            *[(path, None) for path in _order_paths(order_id)]]


def test_foreign_order_numbers_are_404(world, app):
    targets = [world.b_order.id, world.staff_order.id, world.other_tombs[0].id, _MISSING]
    for order_id in targets:
        for path, device in _foreign_paths(order_id):
            body = _get(app, world.fl_a, path, device, status=404)
            assert leaks(body, world.foreign) == [], path
    # 내 번호와 남의 번호를 같이 실어도 404(문지기는 실린 번호를 모두 본다).
    _get(app, world.fl_a, f"{HOME}?order={world.own.id}&order={world.b_order.id}", status=404)
    # 내 번호는 열린다 — 위 404 가 길이 통째로 막혀서가 아니다.
    for path, device in _foreign_paths(world.own.id):
        assert world.own.customer in _get(app, world.fl_a, path, device), path
    # 대조군: 회사 영업 직원은 같은 주소로 남의 주문을 연다.
    for path, device in _foreign_paths(world.b_order.id):
        assert world.b_order.customer in _get(app, world.staff, path, device), path
    # 옛 주소 둘은 내 번호든 남의 번호든 프리랜서에게 닫혀 있다(넘겨주기 없음 — 문지기가 프리랜서 홈으로 보낸다).
    client = client_for(app, world.fl_a)
    for order_id in (world.own.id, world.b_order.id):
        for old in (f"/erp/production/dashboard?focus_order={order_id}", f"/erp/production/tablet-sheet/{order_id}"):
            resp = client.get(old)
            assert resp.status_code == 302 and resp.headers["Location"].endswith(_FL_HOME), old
            assert leaks(resp.get_data(as_text=True), world.foreign + [world.own]) == [], old


def test_handlers_hold_the_line_without_gate_tables(world, app, monkeypatch):
    """둘째 겹: 문지기 주문 번호 표가 비어도 핸들러(``_home_order_or_404`` · 들머리 거르기)가 남의 주문을 내주지 않는다."""
    monkeypatch.setattr(scope, "FREELANCER_ORDER_VIEW_ARGS",
                        {k: v for k, v in FREELANCER_ORDER_VIEW_ARGS.items() if k not in bundle.ORDER_VIEW_ARGS})
    monkeypatch.setattr(scope, "FREELANCER_ORDER_QUERY_ARGS",
                        {k: v for k, v in FREELANCER_ORDER_QUERY_ARGS.items() if k not in bundle.ORDER_QUERY_ARGS})
    for order_id in (world.b_order.id, world.staff_order.id, world.other_tombs[0].id, _MISSING):
        for path in _order_paths(order_id):
            assert leaks(_get(app, world.fl_a, path, status=404), world.foreign) == [], path
        body = _get(app, world.fl_a, f"{HOME}?tab=all&order={order_id}", "pc")  # 문지기를 지나도 행이 내 것뿐이다
        # 주소에 내가 넣은 번호는 화면 링크([다시 받기] · 탭 주소)에 되비친다 — 그 번호 말고 주문 글(이름 · 전화)은 없다.
        assert world.own.customer in body and [hit for hit in leaks(body, world.foreign) if hit[1] != "주문 번호"] == []
        _get(app, world.fl_a, _panel(order_id), "tablet", status=404)
    assert world.own.customer in _get(app, world.fl_a, _order_paths(world.own.id)[0])


# --------------------------------------------------------------------------
# ⑤ 쓰기 전수
# --------------------------------------------------------------------------
_CLOSED, _ACK_OPEN, _OUT_OF_SCOPE = "내 것 403 · 남의 것 404", "내 것 200 · 남의 것 404", "생산 화면 밖(그대로)"
_WRITE_ROUTES = {
    **{f"erp_orders_production.api_production_{name}": _CLOSED
       for name in ("start", "complete", "rework", "cancel", "uncomplete", "steps", "defect", "hold")},
    "erp_orders_production.api_production_change_ack": _ACK_OPEN,
    "erp_orders_production.api_set_logistics_status": _OUT_OF_SCOPE,
    "production_part_marks.api_part_mark": _DENIED,
    "production_part_marks.api_part_marks_basic": _DENIED,
    "erp_orders_drawing_request.api_production_drawing_request": _DENIED,
    "erp_orders_drawing_request.api_production_drawing_request_photo": _DENIED,
    "erp_orders_factory_done.api_production_factory_done": _DENIED,
}


def _state(order_ids) -> dict:
    """주문마다 (mutation_version, 이벤트 수)."""
    db_session.expire_all()
    return {oid: (db_session.get(Order, oid).mutation_version,
                  db_session.query(OrderEvent).filter(OrderEvent.order_id == oid).count()) for oid in order_ids}


def _post(client, rule, order_id: int):
    return client.post(rule.build({arg: order_id for arg in rule.arguments}, append_unknown=False)[1],
                       json={"order_id": order_id})


def test_every_production_write_is_closed_except_change_ack(world, app):
    assert _table_gap(app, _WRITE_ROUTES, read=False) == ([], [])  # 새 생산 쓰기 길은 여기서 분류를 요구받는다
    closed = {endpoint for endpoint, kind in _WRITE_ROUTES.items() if kind == _CLOSED}
    assert closed == set(CLOSED_ORDER_ENDPOINTS) and len(closed) == 8
    assert not closed & set(OWN_ORDER_ENDPOINTS) and not closed & FREELANCER_ALLOWED_ENDPOINTS
    assert "erp_orders_production.api_production_change_ack" in OWN_ORDER_ENDPOINTS
    rules = {rule.endpoint: rule for rule in _production_rules(app, read=False)}
    client = client_for(app, world.fl_a, "tablet")
    watched = [world.own.id, world.own_tomb.id, world.b_order.id, world.staff_order.id, world.other_tombs[0].id]
    before = _state(watched)
    for endpoint in sorted(closed):
        mine = _post(client, rules[endpoint], world.own.id)
        assert mine.status_code == 403 and mine.get_json()["error"] == FREELANCER_DENIED_MSG, endpoint
        for other in (world.b_order.id, world.staff_order.id, _MISSING):
            theirs = _post(client, rules[endpoint], other)
            assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG, endpoint
    for endpoint in sorted(e for e, kind in _WRITE_ROUTES.items() if kind == _DENIED):
        resp = _post(client, rules[endpoint], world.own.id)
        assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG, endpoint
    assert _state(watched) == before  # 주문 · 이벤트 그대로
    # [확인했어요] — 내 주문 · 내 묘비는 200, 남의 주문 · 남의 묘비 · 없는 주문은 404.
    ack = rules["erp_orders_production.api_production_change_ack"]
    for other in (world.b_order.id, world.staff_order.id, world.other_tombs[0].id, _MISSING):
        theirs = _post(client, ack, other)
        assert theirs.status_code == 404 and theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG
    for own in (world.own.id, world.own_tomb.id):
        resp = _post(client, ack, own)
        assert resp.status_code == 200 and resp.get_json()["success"] is True
    after = _state(watched)
    for oid in watched:
        mine = oid in (world.own.id, world.own_tomb.id)
        assert after[oid] == (before[oid][0], before[oid][1] + (1 if mine else 0)), oid
    assert world.own_tomb.customer not in _get(app, world.fl_a, f"{HOME}?tab=changes", "tablet")  # 확인한 묘비는 빠진다
    # 대조군: 회사 영업 직원의 같은 쓰기는 문지기가 아니라 API 쓰기 판정이 답한다(프리랜서 403 이 문지기 것임을 보인다).
    staff = _post(client_for(app, world.staff, "tablet"), rules["erp_orders_production.api_production_start"], world.own.id)
    assert staff.status_code == 403 and (staff.get_json() or {}).get("error") != FREELANCER_DENIED_MSG


def test_closed_write_answers_come_from_the_gate_tables(world, app, monkeypatch):
    """음성 대조군: 닫아 둔 목록에서 빼면 남의 주문 답이 404 → 403 으로 바뀐다(위 404 가 그 목록에서 나온다)."""
    client = client_for(app, world.fl_a)
    path = f"/api/orders/{world.b_order.id}/production/start"
    assert client.post(path, json={}).status_code == 404
    monkeypatch.setitem(CLOSED_ORDER_ENDPOINTS, "erp_orders_production.api_production_start", ())
    resp = client.post(path, json={})
    assert resp.status_code == 403 and resp.get_json()["error"] == FREELANCER_DENIED_MSG


# --------------------------------------------------------------------------
# ⑥ 화면 표식 — 쓰기 표식이 진짜 표식인지(음성 대조군), 도면 카드 읽기
# --------------------------------------------------------------------------
def test_write_markers_are_real_for_writers_and_parts_are_closed_for_freelancer(world, app):
    lead = named_user("STAFF", "PRODUCTION", "가짜반장", production_lead=True)
    # 공정 칸 · [끝] 표식은 2026-11-27 "도면이 주"부터 도면 0장 주문에만 그려진다 — 대조군은 도면 없는 주문으로
    zero = make_order(9901, "가짜고객영", "9901", manager="가짜직원", extra={"drawing_current_files": []})
    sheet = _get(app, lead, _order_paths(zero.id)[0], "tablet")
    steps = _get(app, lead, f"{HOME}?tab=steps", "tablet")
    assert "data-tablet-sheet-action" in sheet and "data-foms-sheet-step=" in sheet
    assert "data-tablet-sheet-action" in _get(app, lead, _order_paths(world.own.id)[0], "tablet")  # 도면 있는 주문도 큰 단추는 있다
    assert "data-foms-home-step-done" in steps and "data-foms-step-finish" in steps
    assert "data-pp-" in _get(app, world.staff, f"{HOME}?tab=parts", "tablet")  # 직원(읽기 전용)은 도면 카드 판을 본다
    # 프리랜서: 도면 카드 보기 모드 none — 판 · [도면 카드로 보기] 없음, ?tab=parts 는 날짜 탭으로.
    with app.test_request_context("/"):
        assert part_view_mode(world.fl_a) == VIEW_NONE
        assert part_view_mode(world.staff) == VIEW_READONLY and part_view_mode(world.off) == VIEW_READONLY
    assert "tab=parts" not in _get(app, world.fl_a, f"{HOME}?tab=date", "tablet")
    assert "tab=parts" in _get(app, world.staff, f"{HOME}?tab=date", "tablet")


def test_sheet_history_link_only_for_part_readers(world, app, monkeypatch):
    """작업 시트 [바뀐 기록 보기 ›]는 바뀐 기록 API 를 부를 수 있는 사람만(``parts_read``) — 프리랜서에게는 안 그린다."""
    real = home_page.build_production_sheet_view

    def _with_cards(*args, **kwargs):
        return {**real(*args, **kwargs), "uses_cards": True}

    monkeypatch.setattr(home_page, "build_production_sheet_view", _with_cards)
    path = _order_paths(world.own.id)[0]
    assert "data-foms-sheet-loglink" in _get(app, world.staff, path, "tablet")
    assert "data-foms-sheet-loglink" not in _get(app, world.fl_a, path, "tablet")


# --------------------------------------------------------------------------
# ⑧ 담당에서 빠지면 · 프리랜서로 켜면 — 다음 요청부터
# --------------------------------------------------------------------------
def test_unassigned_order_disappears_from_next_request(world, app):
    assert world.own.customer in _get(app, world.fl_a, f"{HOME}?tab=all", "tablet")
    order = db_session.get(Order, world.own.id)
    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["manager"]["name"] = "다른담당"
    order.structured_data, order.manager_name = sd, "다른담당"
    flag_modified(order, "structured_data")
    db_session.commit()
    assert world.own.id not in linked_order_ids(world.fl_a)  # 저장 훅이 연결 줄을 지웠다
    assert leaks(_get(app, world.fl_a, f"{HOME}?tab=all", "tablet"), [world.own]) == []
    for path in _order_paths(world.own.id):
        _get(app, world.fl_a, path, status=404)
    _get(app, world.fl_a, f"{HOME}?order={world.own.id}", status=404)


def test_designation_switches_scope_on_next_request(world, app):
    """꺼진 프리랜서를 켜면 다음 요청부터 내 주문만(연결 표가 비어 있으면 빈 화면) — 직원 시절 화면이 남지 않는다."""
    assert leaks(_get(app, world.off, f"{HOME}?tab=all", "tablet"), world.others) != []
    designate(world.off, MATCH_OFF, active=True)
    assert db_session.query(OrderFreelancerLink).filter_by(user_id=world.off.id).count() == 0
    body = _get(app, world.off, f"{HOME}?tab=all", "tablet")
    assert leaks(body, world.others + [world.own]) == []
    _get(app, world.off, _order_paths(world.b_order.id)[0], status=404)


# --------------------------------------------------------------------------
# ⑨ 쿼리 수
# --------------------------------------------------------------------------
@contextmanager
def _statements():
    seen: list[str] = []

    def _before(_conn, _cursor, statement, *_a, **_k):
        seen.append(" ".join(str(statement).split()))

    event.listen(engine, "before_cursor_execute", _before)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", _before)


def test_freelancer_date_tab_query_count(world, app):
    """프리랜서 날짜 탭 쿼리 ≤ 직원 날짜 탭 + 1(연결 표는 같은 문장의 하위 질의, 묘비 판정이 연결 표를 한 번 읽는다)."""
    counts = {}
    for name, user in (("staff", world.staff), ("fl", world.fl_a)):
        client = client_for(app, user, "tablet")
        assert client.get(f"{HOME}?tab=date").status_code == 200  # 데우기(템플릿 · 설정 캐시)
        with _statements() as seen:
            assert client.get(f"{HOME}?tab=date").status_code == 200
        counts[name] = len(seen)
    assert counts["fl"] <= counts["staff"] + 1, counts

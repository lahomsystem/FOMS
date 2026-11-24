"""장의 공장 — 도면팀 화면(설계서 2026-11-23 §8-5 · §5-1 · §11, 3단계 ④). 이름은 모두 지어낸 값이다.

마법사(탭 앞 2공장 표시 · 도구 줄 공장 지정) · 작업실 '현재 버전' 타일 · 보낼 시트 칸 · 전달 창 한 줄 · '바뀜' 목록 공장 바뀜 줄.
API · 규칙은 ``test_drawing_sheet_factory_api.py`` · ``test_drawing_sheet_factory_rules.py``.

되돌리면 실패: 2공장 장이 없는 주문에 공장 그림이 생김(지금 화면이 바뀜) · 영업 · 생산 · 협력사 · 프리랜서에 고르는 칸이나 쓰기 JS ·
시공 대기 이후에 고르는 칸 · 생산에 내려간 장을 묻지 않고 옮김(confirmed=false) · 안 보낸 장을 물음 · 확인 물음을 거절 감사로 남김 ·
응답에 주문 버전 없음 · 마법사가 자동 저장 문지기를 건너뛰어 저장 · 탭 표시를 글 노드로 넣음(이름 바꾸기가 표시를 덮음) ·
'바뀜'에 공장 바뀜 없음 · 안 보낸 시트만 옮긴 것이 '바뀜'에 뜸 · 새 JS 300줄 · 인라인 스타일 · 글자 calc 아님.
대조군: 2공장 장이 있는 주문은 영업에게도 표시만 보인다.
"""
from __future__ import annotations

import copy
import datetime
import re
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from sqlalchemy.orm.attributes import flag_modified

from db import db_session
from foms.services.datetime_kst import now_utc_naive
from foms.services.orders.drawing_factory import SHEET_FACTORY_EVENT
from foms.services.orders.drawing_factory_view import (
    pending_split_text,
    split_text,
    wizard_factory_view,
    workbench_factory_view,
)
from foms.services.production_change_alerts import SHEET_FACTORY_CHANGE_EVENT, collect_production_change_alerts
from foms.web.drawing import wizard as wizard_route
from models import Order, ProductionPartMark, SecurityLog, User
from tests.support.production_part_claim_seed import fresh, login, make_order, make_user

ROOT = Path(__file__).resolve().parents[2]
JS = {name: (ROOT / f"static/js/drawing/{name}").read_text(encoding="utf-8")
      for name in ("sheet-factory.js", "wizard-factory.js", "workbench-sheet-factory.js")}
CSS = (ROOT / "static/css/contexts/drawing/sheet-factory.css").read_text(encoding="utf-8")
MACROS = (ROOT / "templates/drawing/partials/sheet_factory_macros.html").read_text(encoding="utf-8")


def _sd(n: int = 3, *, stage: str = "PRODUCTION", two_sheets=(), two_files=(), uploads: int = 0) -> dict:
    """순수 함수용 주문 JSON — 시트 n장(모두 확정 도면) + 직접 올린 파일 ``uploads`` 장."""
    files = [{"key": f"k/d{j}.png", "filename": f"d{j}.png", "sheet_id": f"s-{j}"} for j in range(n)]
    files += [{"key": f"k/u{j}.pdf", "filename": f"u{j}.pdf"} for j in range(uploads)]
    sd = {"workflow": {"stage": stage}, "drawing_current_files": files,
          "drawing_wizard": {"sheets": [{"id": f"s-{j}", "name": f"시트{j}"} for j in range(n + 1)]}}
    if two_sheets or two_files:
        sd["drawing_factory"] = {"sheets": {f"s-{j}": 2 for j in two_sheets}, "files": {f"k/u{j}.pdf": 2 for j in two_files}}
    return sd


# --------------------------------------------------------------------------- #
# 화면 값(순수) — None 이면 지금 화면 그대로
# --------------------------------------------------------------------------- #
def test_no_second_factory_and_cannot_set_means_no_view_at_all():
    sd = _sd()
    assert wizard_factory_view(sd, can_set=False, stage="PRODUCTION") is None
    assert workbench_factory_view(sd, order_id=1, can_set=False, stage="PRODUCTION") is None
    assert split_text(sd) == ""


def test_setter_gets_selector_view_without_page_time_confirm_list():
    sd = _sd(2)
    view = workbench_factory_view(sd, order_id=7, can_set=True, stage="PRODUCTION")
    assert view == {"order_id": 7, "can_set": True, "by_key": {}, "by_sheet": {}, "split_text": ""}
    assert wizard_factory_view(sd, can_set=True, stage="PRODUCTION") == {"can_set": True, "by_sheet": {}}
    # 생산에 내려간 장인지는 화면이 연 때 값으로 안 가른다 — 서버가 CONFIRM_REQUIRED 로 물어 온다(아래 API 시험)


@pytest.mark.parametrize("stage", ["CONSTRUCTION", "CS", "COMPLETED"])
def test_after_production_only_marks_remain(stage):
    sd = _sd(2, stage=stage, two_sheets=(1,))
    view = workbench_factory_view(sd, order_id=1, can_set=True, stage=stage)
    assert view["can_set"] is False and view["by_key"] == {"k/d1.png": 2}
    assert wizard_factory_view(_sd(2, stage=stage), can_set=True, stage=stage) is None  # 2공장도 없고 못 바꾼다


def test_split_text_counts_sheets_and_uploads_and_pending_line():
    sd = _sd(3, two_sheets=(1,), two_files=(0,), uploads=1)
    assert split_text(sd) == "1공장 2장 · 2공장 2장"
    pending = [{"sheet_id": "s-1"}, {"sheet_id": "s-2"}, {"sheet_id": "s-3"}]
    assert pending_split_text(pending, {"s-1": 2}) == "보낼 도면 3장 — 1공장 2장 · 2공장 1장"
    assert pending_split_text(pending, {}) == ""  # 1공장뿐이면 한 줄이 없다


@pytest.mark.parametrize(("team", "role", "ok"), [
    ("CS", "ADMIN", True), ("DRAWING", "STAFF", True), ("DRAWING", "MANAGER", True), ("PRODUCTION", "STAFF", False),
    ("PRODUCTION", "MANAGER", False), ("SALES", "STAFF", False), ("CS", "STAFF", False), ("DRAWING", "VIEWER", False),
])
def test_save_send_config_carries_factory_right(monkeypatch, team, role, ok):
    monkeypatch.setattr(wizard_route, "can_transfer_drawing", lambda user, order: False)
    monkeypatch.setattr(wizard_route, "is_drawing_hotfix_stage", lambda order: False)
    user = SimpleNamespace(id=3, role=role, team=team, is_active=True, partner_org_id=None)
    cfg = wizard_route._save_send_config(user, SimpleNamespace(id=1, partner_org_id=None))
    assert cfg["can_set_factory"] is ok


# --------------------------------------------------------------------------- #
# 실제 화면(작업실 · 마법사)
# --------------------------------------------------------------------------- #
def _order(*, stage: str = "PRODUCTION", two=(), pending=(0, 1)) -> tuple[int, list[str], tuple[str, ...]]:
    """생산 주문 + 마법사 시트 · 전달 대기(시트 ``pending``) — ``two`` 는 2공장 시트 번호."""
    seed = make_order(3)
    order = db_session.get(Order, seed.id)
    sd = copy.deepcopy(order.structured_data)
    sids = [f["sheet_id"] for f in sd["drawing_current_files"]]
    sd["workflow"]["stage"] = stage
    sd["drawing_status"] = "CONFIRMED"
    sd["drawing_wizard"] = {"v": 1, "sheets": [{"id": s, "name": f"시트{j}"} for j, s in enumerate(sids)],
                            "pending": {sids[j]: {"key": f"w/p{j}.png", "sheet_name": f"시트{j}", "at": "11/24"} for j in pending}}
    if two:
        sd["drawing_factory"] = {"sheets": {sids[j]: 2 for j in two}, "files": {}}
    order.structured_data = sd
    order.erp_stage_updated_at = now_utc_naive() - datetime.timedelta(days=1)  # '바뀜' 창 시작(UTC) — 만든 시각(지역 시계)에 기대지 않게
    flag_modified(order, "structured_data")
    db_session.commit()
    return seed.id, sids, seed.keys


def _page(client, url: str) -> str:
    resp = client.get(url)
    assert resp.status_code == 200, url
    return resp.get_data(as_text=True)


def test_workbench_without_second_factory_is_unchanged_for_sales_and_production(client):
    oid, _sids, _keys = _order()
    for team in ("SALES", "PRODUCTION"):
        login(client, make_user("최유나", team=team))
        html = _page(client, f"/erp/drawing-workbench/{oid}")
        assert "dsf-" not in html and "sheet-factory" not in html  # 표시 · 고르는 칸 · CSS · JS 아무것도 없다
        assert '<div class="small text-muted mb-1">최신 전달본(번호순)</div>' in html


def test_workbench_drawing_team_gets_tile_and_pending_selectors(client):
    oid, sids, keys = _order(two=(1,))
    login(client, make_user("오가람", team="DRAWING"))
    html = _page(client, f"/erp/drawing-workbench/{oid}")
    tiles = re.findall(r'<div class="dsf-sel" role="group" aria-label="공장 지정" data-dsf-sel data-order-id="%d" data-key="([^"]+)"'
                       r' data-label="도면 (\d)/3 · [^"]+">' % oid, html)
    assert [k for k, _n in tiles] == list(keys) and [n for _k, n in tiles] == ["1", "2", "3"]
    assert html.count('data-fac="2" aria-pressed="true"') == 2  # 타일 2번 · 보낼 칸 시트1
    assert '<span class="dsf-split" data-dsf-split> · 1공장 2장 · 2공장 1장</span>' in html
    assert f'data-sheet-id="{sids[1]}" data-label="시트1"' in html and 'data-confirm="1"' not in html  # 보낼 칸 = 시트로
    assert html.count("drawing-gateway-thumb-wrap me-2 mb-2 position-relative dsf-wrap") == 3  # 고르는 칸이 있는 타일만 넓힐 수 있게
    assert '<div class="dsf-send" data-dsf-send>보낼 도면 2장 — 1공장 1장 · 2공장 1장</div>' in html
    assert "js/drawing/sheet-factory.js" in html and "js/drawing/workbench-sheet-factory.js" in html
    assert "dsf-chip" not in html  # 고르는 사람에게 표시를 따로 두지 않는다(고르기가 곧 표시)


def test_workbench_sales_sees_marks_only_when_second_factory_exists(client):
    oid, _sids, _keys = _order(two=(1,))
    login(client, make_user("최유나", team="SALES"))
    html = _page(client, f"/erp/drawing-workbench/{oid}")
    assert "data-dsf-sel" not in html and html.count('<span class="dsf-chip">2공장</span>') == 2  # 타일 1 · 보낼 칸 1
    assert "sheet-factory.css" in html and "js/drawing/sheet-factory.js" not in html  # 쓰기 JS 는 안 싣는다


def test_workbench_after_production_drawing_team_sees_marks_not_selectors(client):
    oid, _sids, _keys = _order(stage="CONSTRUCTION", two=(0,))
    login(client, make_user("오가람", team="DRAWING"))
    html = _page(client, f"/erp/drawing-workbench/{oid}")
    assert "data-dsf-sel" not in html and '<span class="dsf-chip">2공장</span>' in html


def test_wizard_config_and_scripts_follow_right(client):
    oid, sids, _keys = _order(two=(2,))
    login(client, make_user("오가람", team="DRAWING"))
    html = _page(client, f"/erp/drawing-workbench/{oid}/wizard")
    assert '"factory": {"by_sheet": {"%s": 2}, "can_set": true}' % sids[2] in html
    assert "js/drawing/sheet-factory.js" in html and "js/drawing/wizard-factory.js" in html and "sheet-factory.css" in html
    login(client, make_user("최유나", team="SALES"))
    sales = _page(client, f"/erp/drawing-workbench/{oid}/wizard")
    assert '"factory": {"by_sheet": {"%s": 2}, "can_set": false}' % sids[2] in sales
    assert "js/drawing/wizard-factory.js" in sales and "js/drawing/sheet-factory.js" not in sales  # 탭 표시만
    plain, _s, _k = _order()
    none = _page(client, f"/erp/drawing-workbench/{plain}/wizard")
    assert '"factory": null' in none and "sheet-factory" not in none and "wizard-factory" not in none


# --------------------------------------------------------------------------- #
# '바뀜' 목록 — 공장 바뀜(§11)
# --------------------------------------------------------------------------- #
def test_factory_change_after_production_shows_in_change_list(client):
    oid, sids, _keys = _order(pending=())
    login(client, make_user("오가람", team="DRAWING"))
    resp = client.post(f"/api/orders/{oid}/drawing/sheet-factory", json={"items": [{"sheet_id": sids[2], "factory": 2}]})
    assert resp.status_code == 200, resp.get_json()
    result = collect_production_change_alerts(db_session, [fresh(oid)], None)[oid]
    [item] = [a for a in result["alerts"] if a["kind"] == "factory"]
    assert item["label"] == "공장 바뀜" and item["detail"] == "도면 3/3 1공장 → 2공장" and item["by_name"] == "오가람"
    assert isinstance(item["by_id"], int) and result["history"] == result["alerts"]


def test_unsent_sheet_only_change_is_not_a_production_change(client):
    oid, _sids, _keys = _order(pending=())
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"]["sheets"].append({"id": "new-sheet", "name": "새 시트"})
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()
    login(client, make_user("오가람", team="DRAWING"))
    assert client.post(f"/api/orders/{oid}/drawing/sheet-factory",
                       json={"items": [{"sheet_id": "new-sheet", "factory": 2}]}).status_code == 200
    result = collect_production_change_alerts(db_session, [fresh(oid)], None)[oid]
    assert not [a for a in result["history"] if a["kind"] == "factory"]


def test_change_event_name_is_one_value():
    assert SHEET_FACTORY_CHANGE_EVENT == SHEET_FACTORY_EVENT == "DRAWING_SHEET_FACTORY_CHANGED"


# --------------------------------------------------------------------------- #
# JS · CSS · 템플릿 구조
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("name", sorted(JS))
def test_new_js_is_small_valid_and_bound_once(name):
    src = JS[name]
    assert len(src.splitlines()) < 300  # 새 JS 300줄 래칫
    assert "style=" not in src and ".style." not in src  # 인라인 스타일 0
    assert re.search(r"if \(window\.(__\w+_BOUND|FomsSheetFactory)\) return;", src)  # 조각 다시 실행해도 한 번만
    node = shutil.which("node")
    if node:
        done = subprocess.run([node, "--check", str(ROOT / f"static/js/drawing/{name}")], capture_output=True, text=True)
        assert done.returncode == 0, done.stderr


def test_fetch_is_guarded_and_success_checked():
    src = JS["sheet-factory.js"]
    assert src.count("fetch(") == 1 and src.index("try {") < src.index("fetch(") < src.index("} catch (e)")
    assert "data && data.success" in src and "data.error" in src  # 서버 글 그대로
    assert "/drawing/sheet-factory'" in src and "idempotency_key" in src


def test_css_fonts_scale_and_factory_two_is_not_grey():
    sizes = re.findall(r"font-size:\s*([^;]+);", CSS)
    assert sizes and all(re.fullmatch(r"calc\(\d+px \* var\(--foms-fs, 1\)\)", s.strip()) for s in sizes), sizes
    assert "--dsf-fac2-line: #0d9488" in CSS and "--dsf-fac2-700: #0f6b63" in CSS  # 설계서 §8-9 · §10 값
    rules = re.sub(r"/\*.*?\*/", "", CSS, flags=re.S)
    chip = re.search(r"\.dws-tab\.dws-tab-has-fac::before,\s*\.dsf-chip \{([^}]*)\}", rules).group(1)
    assert '.dws-tab.dws-tab-has-fac::before { content: "2공장";' in rules  # 탭 표시 = 글 노드 아님
    assert "color: var(--dsf-fac2-700)" in chip and "border: 1.5px solid var(--dsf-fac2-line)" in chip
    assert "@media (pointer: coarse)" in rules and "calc(44px / var(--foms-ui-zoom, 1))" in rules
    assert ".btn" not in rules  # 전역 .btn !important 함정을 피한다


def test_macro_markup_has_no_inline_style_and_uses_pressed_buttons():
    assert "style=" not in MACROS
    assert 'role="group" aria-label="공장 지정"' in MACROS and MACROS.count('aria-pressed="{{') == 2
    for tpl in ("templates/drawing/partials/workbench_detail_body.html", "templates/drawing/wizard.html"):
        added = [ln for ln in (ROOT / tpl).read_text(encoding="utf-8").splitlines() if "dsf-" in ln or "sheet-factory" in ln]
        assert added and not [ln for ln in added if "style=" in ln], tpl


# --------------------------------------------------------------------------- #
# 3단계 ④ 검토 고침 — 확인은 서버가 묻는다 · 주문 버전 · 협력사 · 프리랜서 · 새 시트 · 탭 표시
# --------------------------------------------------------------------------- #
def _post(client, oid: int, item: dict, **body):
    return client.post(f"/api/orders/{oid}/drawing/sheet-factory", json={"items": [item], **body})


def test_production_current_sheet_is_asked_once_then_moved_with_new_version(client):
    oid, sids, keys = _order(pending=())
    login(client, make_user("오가람", team="DRAWING"))
    before = fresh(oid).mutation_version
    asked = _post(client, oid, {"key": keys[0], "factory": 2}, confirmed=False)
    assert asked.status_code == 409 and asked.get_json()["data"]["code"] == "CONFIRM_REQUIRED"
    assert "drawing_factory" not in fresh(oid).structured_data and fresh(oid).mutation_version == before  # 쓰기 0
    db_session.expire_all()
    assert db_session.query(SecurityLog).filter_by(action="DRAWING_SHEET_FACTORY_REFUSED", target_id=oid).count() == 0
    done = _post(client, oid, {"key": keys[0], "factory": 2}, confirmed=True)
    assert done.status_code == 200 and done.get_json()["data"]["mutation_version"] == before + 1 == fresh(oid).mutation_version
    same = _post(client, oid, {"key": keys[0], "factory": 2}, confirmed=False)  # 같은 값 = 묻지 않고 버전 그대로 알려 준다
    assert same.status_code == 200 and same.get_json()["data"]["mutation_version"] == before + 1


def test_unsent_sheet_and_pre_production_are_not_asked_and_blocked_sheet_is_blocked_first(client):
    oid, _sids, keys = _order(pending=())
    order = db_session.get(Order, oid)
    sd = copy.deepcopy(order.structured_data)
    sd["drawing_wizard"]["sheets"].append({"id": "new-sheet", "name": "새 시트"})
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.add(ProductionPartMark(order_id=oid, drawing_key=keys[1], part="cut", state="DONE", done_by_name="김재단",
                                      picked_by_name="김재단"))
    db_session.commit()
    login(client, make_user("오가람", team="DRAWING"))
    assert _post(client, oid, {"sheet_id": "new-sheet", "factory": 2}, confirmed=False).status_code == 200  # 안 보낸 시트
    blocked = _post(client, oid, {"key": keys[1], "factory": 2}, confirmed=False)  # 막힐 장은 확인 창 없이 막힘 글부터
    assert blocked.status_code == 409 and blocked.get_json()["data"]["code"] == "SHEET_HAS_WORK"
    drawing, _s, dkeys = _order(stage="DRAWING", pending=())
    assert _post(client, drawing, {"key": dkeys[0], "factory": 2}, confirmed=False).status_code == 200  # 생산 전 = 묻지 않음


def test_partner_and_freelancer_get_no_selector_or_write_js(client):
    from foms.services.sales_commission.settings import load_settings, save_freelancer
    oid, _sids, _keys = _order(two=(1,))
    partner = make_user("협력도면", team="DRAWING", role="PARTNER", partner_org_id=9)  # 협력사 계정(PARTNER-01)
    freelancer = make_user("프리영업", team="SALES")
    save_freelancer(db_session, freelancer.id, {"match_name": "프리영업", "start_month": "2020-01", "tax_type": "NONE",
                                                 "active": True}, base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    for person in (partner, freelancer):
        assert wizard_route._save_send_config(db_session.get(User, person.id), fresh(oid))["can_set_factory"] is False
        login(client, person)
        for url in (f"/erp/drawing-workbench/{oid}", f"/erp/drawing-workbench/{oid}/wizard"):  # 지금은 협력사 302 · 프리랜서 404
            body = client.get(url).get_data(as_text=True)
            assert "data-dsf-sel" not in body and "js/drawing/sheet-factory.js" not in body
            assert "workbench-sheet-factory.js" not in body and '"can_set": true' not in body
        refused = _post(client, oid, {"key": _keys[0], "factory": 2})  # 지금은 협력사 401 · 프리랜서 403
        assert refused.status_code in (401, 403) and fresh(oid).structured_data["drawing_factory"]["files"] == {}


def test_wizard_never_saves_by_itself_and_marks_tab_without_text_node():
    src = JS["wizard-factory.js"]
    assert "core.save" not in src and "아직 저장되지 않은 시트예요. [저장]한 뒤 공장을 지정해 주세요." in src
    assert "insertBefore(mark" not in src and "classList.toggle('dws-tab-has-fac'" in src  # 이름 바꾸기가 표시를 덮지 않게
    shared = JS["sheet-factory.js"]
    assert "confirmed: !!confirmed" in shared and "res.code === 'CONFIRM_REQUIRED'" in shared and "send(true)" in shared
    bench = JS["workbench-sheet-factory.js"]
    assert "data-mutation-version" in bench and "res.data.mutation_version" in bench

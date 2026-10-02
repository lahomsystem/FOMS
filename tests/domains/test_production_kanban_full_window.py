"""태블릿 칸반 전량 렌더 회귀 고정 (page 윈도 소실 버그).

R1 시공일 정렬 도입 후, 시공일 변경으로 rank>page_size 가 된 카드가 page1 윈도에서만
렌더돼 사라진 회귀. 칸반은 정렬 전량(캡 300)을 소비해야 한다.

- (a) 51건 시드 → rank51 주문이 kanban_orders 에 존재(page1 orders 엔 없음).
- (b) orders 는 여전히 50건 페이지.
- (c) 캡 초과 → 상위 N 제한 + kanban_capped=True.
- (d) changed_count 는 kanban(보드 전체) 기준.
- (e) P3-4: 칸반을 안 그리는 요청(마우스 PC·옛 셸)은 전량 조회·가공·묘비 조회를 건너뛰고
  PC 리스트 페이지 행만 읽는다. 페이지 행은 칸반을 계산할 때와 같다.
"""

from __future__ import annotations

import datetime

from werkzeug.security import generate_password_hash

import foms.web.production.dashboard as pd
from db import db_session
from models import Order, OrderEvent, User

_T0 = datetime.datetime(2026, 7, 1, 0, 0, 0)


def _make_user(username="kanban_admin"):
    u = User(
        username=username,
        password=generate_password_hash("pw"),
        role="ADMIN",
        name=username,
        is_active=True,
    )
    db_session.add(u)
    db_session.commit()
    return u


def _login(client, user, monkeypatch):
    """칸반은 모바일 v2 셸 + 터치에서만 그리고 계산한다 — 그 조건(쿠키 없음 = 터치로 봄)으로 로그인."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _make_prod_order(cdate: str) -> Order:
    order = Order(
        received_date="2026-07-01",
        customer_name=f"고객{cdate}",
        phone="010-0000-0000",
        address="Seoul",
        product="붙박이장",
        status="PRODUCTION",
        is_erp_order=True,
        structured_data={"workflow": {"stage": "PRODUCTION"}},
        erp_stage_code="PRODUCTION",
        erp_construction_date=cdate,
        erp_stage_updated_at=_T0,
    )
    db_session.add(order)
    db_session.commit()
    return order


def _get_ctx(client, monkeypatch, query=""):
    captured = {}

    def _fake_render(template_name, **ctx):
        captured.update(ctx)
        return ""

    monkeypatch.setattr(pd, "render_template", _fake_render)
    res = client.get("/erp/production/dashboard" + query)
    assert res.status_code == 200
    return captured


def test_rank51_order_in_kanban_but_not_page1(client, monkeypatch):
    user = _make_user("kanban_a")
    _login(client, user, monkeypatch)
    # 51건: 시공일 asc 정렬 시 마지막(가장 늦은 날짜)이 rank 51.
    ids_by_rank = []
    for i in range(1, 52):
        o = _make_prod_order(f"2026-08-{i:02d}" if i <= 31 else f"2026-09-{i - 31:02d}")
        ids_by_rank.append(o.id)
    rank51_id = ids_by_rank[-1]

    ctx = _get_ctx(client, monkeypatch)
    kanban_ids = {r["id"] for r in ctx["kanban_orders"]}
    page_ids = {r["id"] for r in ctx["orders"]}

    # (a) rank51 은 칸반엔 있고 page1 엔 없다 — 회귀 고정.
    assert rank51_id in kanban_ids
    assert rank51_id not in page_ids
    # (b) orders 는 50건 페이지, kanban 은 전량 51.
    assert len(ctx["orders"]) == 50
    assert len(ctx["kanban_orders"]) == 51
    assert ctx["kanban_capped"] is False


def test_cap_limits_kanban_and_flags(client, monkeypatch):
    user = _make_user("kanban_b")
    _login(client, user, monkeypatch)
    monkeypatch.setattr(pd, "PRODUCTION_KANBAN_MAX_ROWS", 3)
    for i in range(1, 5):  # 4건 > cap 3
        _make_prod_order(f"2026-08-{i:02d}")

    ctx = _get_ctx(client, monkeypatch)
    assert ctx["kanban_capped"] is True
    assert len(ctx["kanban_orders"]) == 3
    # PC 리스트는 페이지네이션(50)이라 4건 전부.
    assert len(ctx["orders"]) == 4


def test_changed_count_is_kanban_based(client, monkeypatch):
    user = _make_user("kanban_c")
    _login(client, user, monkeypatch)
    ids_by_rank = []
    for i in range(1, 52):
        o = _make_prod_order(f"2026-08-{i:02d}" if i <= 31 else f"2026-09-{i - 31:02d}")
        ids_by_rank.append(o.id)
    rank51_id = ids_by_rank[-1]
    # rank51(=page1 밖) 주문에 시공일 변경 이벤트(윈도 이후) → has_changes.
    ev = OrderEvent(
        order_id=rank51_id,
        event_type="CONSTRUCTION_DATE_CHANGED",
        payload={"from": "2026-09-20", "to": "2026-09-25"},
        created_at=_T0 + datetime.timedelta(days=3),
    )
    db_session.add(ev)
    db_session.commit()

    ctx = _get_ctx(client, monkeypatch)
    page_ids = {r["id"] for r in ctx["orders"]}
    assert rank51_id not in page_ids            # page1 밖임을 확인
    # 보드 전체 기준이라 page 밖 변경도 카운트된다(구 버그: page 기준이면 0).
    assert ctx["changed_count"] == 1
    changed = [r["id"] for r in ctx["kanban_orders"] if r.get("has_changes")]
    assert changed == [rank51_id]


# --------------------------------------------------------------------------- #
# (e) P3-4 — 칸반을 안 그리는 요청은 칸반 데이터를 만들지 않는다
# --------------------------------------------------------------------------- #
def _seed_51():
    ids_by_rank = []
    for i in range(1, 52):
        o = _make_prod_order(f"2026-08-{i:02d}" if i <= 31 else f"2026-09-{i - 31:02d}")
        ids_by_rank.append(o.id)
    return ids_by_rank


def _spy_kanban_work(monkeypatch):
    """가공에 들어간 행 수와 묘비 조회 횟수를 센다(원래 함수는 그대로 돈다)."""
    seen = {"enriched_rows": [], "tombstones": 0}
    original_enrich = pd.build_production_enriched_rows
    original_tombs = pd.collect_production_tombstones

    def _enrich(rows, *args, **kwargs):
        seen["enriched_rows"].append(len(rows))
        return original_enrich(rows, *args, **kwargs)

    def _tombs(*args, **kwargs):
        seen["tombstones"] += 1
        return original_tombs(*args, **kwargs)

    monkeypatch.setattr(pd, "build_production_enriched_rows", _enrich)
    monkeypatch.setattr(pd, "collect_production_tombstones", _tombs)
    return seen


def test_mouse_pc_skips_kanban_full_set_and_keeps_same_page_rows(client, monkeypatch):
    user = _make_user("kanban_pc")
    _login(client, user, monkeypatch)
    ids_by_rank = _seed_51()
    seen = _spy_kanban_work(monkeypatch)

    # 대조군: 쿠키 없음(= 터치로 봄) — 지금처럼 전량 51행을 가공하고 묘비를 센다.
    touch = _get_ctx(client, monkeypatch)
    assert seen["enriched_rows"] == [51] and seen["tombstones"] == 1
    assert len(touch["kanban_orders"]) == 51

    # 마우스 PC: 칸반 미렌더 → 페이지 50행만 가공, 묘비 조회 없음, 칸반 값은 빈 값.
    seen["enriched_rows"].clear()
    seen["tombstones"] = 0
    client.set_cookie("foms_ptr", "fine", domain="localhost")
    pc = _get_ctx(client, monkeypatch)
    assert seen["enriched_rows"] == [50]
    assert seen["tombstones"] == 0
    assert pc["kanban_orders"] == []
    assert pc["kanban_capped"] is False
    assert pc["changed_count"] == 0
    assert pc["tombstones"] == []
    assert pc["tablet_prod_kpis"] == {}
    # PC 리스트·요약은 칸반 계산 여부와 무관하게 같다.
    assert [r["id"] for r in pc["orders"]] == [r["id"] for r in touch["orders"]]
    assert pc["total_orders"] == touch["total_orders"] == 51
    assert pc["total_pages"] == touch["total_pages"] == 2

    # 2쪽도 같은 정렬로 착지한다(rank51 하나).
    page2 = _get_ctx(client, monkeypatch, "?page=2")
    assert [r["id"] for r in page2["orders"]] == [ids_by_rank[-1]]


def test_legacy_shell_touch_skips_kanban(client, monkeypatch):
    """옛 셸은 터치여도 칸반을 안 그린다(템플릿 조건의 다른 반쪽) — 계산도 건너뛴다."""
    user = _make_user("kanban_legacy")
    _login(client, user, monkeypatch)
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "")
    _make_prod_order("2026-08-01")
    seen = _spy_kanban_work(monkeypatch)
    client.set_cookie("foms_ptr", "coarse", domain="localhost")

    ctx = _get_ctx(client, monkeypatch)
    assert ctx["kanban_orders"] == []
    assert seen["tombstones"] == 0
    assert len(ctx["orders"]) == 1


def test_kanban_gate_matches_template_condition():
    """뷰의 판정이 템플릿의 칸반 include 조건과 같은 두 값에 묶여 있어야 한다."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[2]
    body = (root / "templates/production/partials/dashboard_body.html").read_text(encoding="utf-8")
    assert (
        "{% if erp_mobile_v2_enabled and coarse_pointer_surfaces %}\n"
        "    {% include 'production/partials/tablet_kanban_body.html' %}"
    ) in body
    src = (root / "foms/web/production/dashboard.py").read_text(encoding="utf-8")
    assert "kanban_wanted = is_mobile_v2_shell(resolve_shell_variant_cached(" in src
    assert "and wants_coarse_pointer_surfaces(request)" in src

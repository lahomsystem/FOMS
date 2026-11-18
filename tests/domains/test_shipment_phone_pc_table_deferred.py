"""출고 폰 PC 표 생략 · 늦게 받기 계약 (2026-11-18).

폰(모바일 셸 · 터치 + 992 미만 창)에선 셸 CSS(foms-shipment-mobile.css 의 max-width 991.98px)가 출고 PC 표면
(.erp-shipment-desktop-shell)째 숨겨 세로 · 가로 모두 PC 표가 안 보인다. 그래서 서버는 그 속(필터 · 날짜 패널 · 변경 배너 ·
협력사 판 · PC 표)을 자리표로 바꾸고(dashboard_main.html ship_omit_pc_table), 폰이 표를 쓰는 두 곳을 이렇게 잇는다:
  - [AS 추천](shipment-dashboard.js collectTargetOrderIds): 자리표의 data-ship-as-rec-rows(표 줄과 같은 키)를 표 줄 재배치와
    같은 비교로 줄 세워 같은 주문을 같은 순서로 보낸다.
  - [저장](image-export.js): 누른 그때 자리표 주소(ship_pc_table=1)로 같은 화면을 받아 표만 끼운다.
넓은 창 · 쿠키 없음 · 이상값 · 마우스 PC 는 지금 그대로다. 표면 공통 계약은 test_phone_viewport_surfaces.py.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from models import User

ROOT = Path(__file__).resolve().parents[2]
SHELL_HEADERS = {"X-FOMS-ERP-SHELL": "1"}
PHONE = {"foms_ptr": "coarse", "foms_vw": "narrow", "foms_scr": "915"}
CONTROLS = [
    ("no-cookies", {}),
    ("tablet-landscape", {"foms_ptr": "coarse", "foms_vw": "wide", "foms_scr": "1280"}),
    ("big-tablet-portrait", {"foms_ptr": "coarse", "foms_vw": "tall", "foms_scr": "1366"}),
    ("mouse-pc", {"foms_ptr": "fine", "foms_vw": "wide", "foms_scr": "1920"}),
    ("narrow-mouse-window", {"foms_ptr": "fine", "foms_vw": "narrow", "foms_scr": "1920"}),
    ("odd-value", {"foms_ptr": "coarse", "foms_vw": "NARROW", "foms_scr": "915"}),
]


def _login(client, monkeypatch, username: str) -> None:
    user = User(username=username, password=generate_password_hash("x"), role="ADMIN", team="CS", name=username, is_active=True)
    db_session.add(user)
    db_session.commit()
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(user.id))
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role


def _body(client, path: str, cookies: dict[str, str]) -> str:
    for name, value in cookies.items():
        client.set_cookie(name, value, domain="localhost")
    response = client.get(f"{path}?view=fragment", headers=SHELL_HEADERS)
    assert response.status_code == 200, f"{path} -> {response.status_code}"
    return response.get_data(as_text=True)


def _ship_seed_rows(today: str) -> list[int]:
    """출고 날짜 창에 든 가짜 주문 넷(AS 1 포함) — [AS 추천] 키 · 표 줄을 견줄 재료."""
    from models import Order, OrderScheduleDate

    ids = []
    for i, (workers, mgr, status) in enumerate([
        (["가짜기사B"], "가짜영업2", "CONSTRUCTION"),
        ([" 가짜기사A ", "가짜기사C"], "가짜영업1", "SHIPMENT"),
        ([], "", "CONSTRUCTION"),
        (["가짜기사A"], "가짜영업1", "AS_RECEIVED"),
    ]):
        sd = {"workflow": {"stage": status}, "shipment": {"construction_workers": workers},
              "schedule": {"construction": {"date": today}}, "items": [{"product_name": "붙박이장", "spec_width": "1200"}]}
        kind = "construction"
        if status == "AS_RECEIVED":
            sd["schedule"] = {"as_visit": {"date": today}}
            kind = "as_visit"
        o = Order(received_date=today, customer_name=f"가짜출고{i}", phone="010-0000-0000", address="가짜시 가짜로 1",
                  product="붙박이장", status=status, manager_name=mgr, is_erp_order=True, structured_data=sd,
                  erp_stage_code=status, scheduled_date=today)
        db_session.add(o)
        db_session.flush()
        db_session.add(OrderScheduleDate(order_id=o.id, kind=kind, date=today, source="beta_schedule"))
        ids.append(o.id)
    db_session.commit()
    return ids


def test_shipment_phone_pc_table_deferred_and_comes_back_on_request(client, monkeypatch) -> None:
    """출고 폰: PC 표 대신 자리표(받을 주소 · [AS 추천] 줄 키)만 오고, 그 주소(ship_pc_table=1)로 받으면 표가 온다.

    표면째 숨는 폭(992 미만)이 쿠키 경계(foms_vw)와 같아 폰 가로에서도 표는 안 보인다 — 늦게 받는 쪽은 [저장]
    (image-export.js)뿐이다. 키는 표 줄의 data-order-id · 시공자 칸 첫 값 · data-manager 와 같고 AS 줄은 빠진다.
    """
    import json

    from foms.services.erp_display import get_today_kst

    _login(client, monkeypatch, "pvs_ship_pc_table")
    ids = _ship_seed_rows(get_today_kst().isoformat())
    body = _body(client, "/erp/shipment", PHONE)
    assert 'id="shipment-dashboard-table"' not in body and 'class="shipment-row"' not in body
    m = re.search(r'data-ship-pc-table-src="([^"]+)"', body)
    assert m, "폰 출고에 PC 표 자리표 주소가 없다"
    src = m.group(1).replace("&amp;", "&")
    assert "ship_pc_table=1" in src and "foms_shell=fragment" in src, src
    keys = json.loads(re.search(r"data-ship-as-rec-rows='([^']*)'", body).group(1))
    assert sorted(k[0] for k in keys) == sorted(ids[:3]), keys  # AS 줄(ids[3])은 뺀다
    assert [k for k in keys if k[0] == ids[1]] == [[ids[1], "가짜기사A", "가짜영업1"]]
    assert [k for k in keys if k[0] == ids[2]] == [[ids[2], "", ""]]

    forced = client.get(src, headers=SHELL_HEADERS)
    assert forced.status_code == 200
    html = forced.get_data(as_text=True)
    assert 'id="shipment-dashboard-table"' in html and "data-ship-pc-table-deferred" not in html
    for oid in ids:
        assert f'id="shipment-row-{oid}" data-order-id="{oid}" class="shipment-row"' in html, oid
    row = re.search(rf'<tr id="shipment-row-{ids[1]}"[^>]*>', html).group(0)
    assert 'data-as="0"' in row and 'data-manager="가짜영업1"' in row


@pytest.mark.parametrize(("tag", "cookies"), CONTROLS, ids=[c[0] for c in CONTROLS])
def test_shipment_wide_windows_keep_pc_table(client, monkeypatch, tag, cookies) -> None:
    """대조군(태블릿 · PC · 좁힌 마우스 창 · 쿠키 없음 · 이상값): PC 표 그대로, 자리표 · x-ignore 없음."""
    _login(client, monkeypatch, "pvs_ship_ctl_" + tag.replace("-", "_"))
    body = _body(client, "/erp/shipment", cookies)
    assert 'id="shipment-dashboard-table"' in body
    assert "data-ship-pc-table-deferred" not in body
    assert "x-ignore" not in body


def test_shipment_phone_x_ignore_on_mobile_surface_only(client, monkeypatch) -> None:
    """폰 출고: x-ignore 는 모바일 표면(section)에만 — 뿌리에 걸면 그 안 모바일 셸의 Alpine 토스트 호스트가 죽는다.

    Alpine 지시어는 토스트 호스트(#foms-alpine-toast-root)뿐이고 모두 x-ignore 표면보다 앞에 있어야 한다.
    """
    _login(client, monkeypatch, "pvs_ship_xignore")
    body = _body(client, "/erp/shipment", PHONE)
    assert body.count("x-ignore") == 1
    sec = re.search(r'<section class="foms-shell-body foms-mobile-v2-dashboard erp-shipment-mobile-v2" x-ignore', body)
    assert sec, "폰 출고 모바일 표면에 x-ignore 가 없다"
    root = re.search(r'<div class="erp-pro erp-mobile-shell erp-dashboard-shipment"[^>]*>', body).group(0)
    assert "x-ignore" not in root
    toast = body.index('id="foms-alpine-toast-root"')
    alpine = [m.start() for m in re.finditer(
        r'\s(?:x-(?:data|show|text|init|model|on:|bind|cloak|transition|if|for|effect|html|ref)\b|@[a-z]+[.=]|:class=)', body)]
    assert alpine and toast < sec.start()
    assert all(pos < sec.start() for pos in alpine), "x-ignore 표면 안(또는 뒤)에 Alpine 지시어가 있다"


def test_shipment_deferred_table_js_wiring() -> None:
    """자리표 ↔ JS 배선: [저장]이 표를 받아 끼우고, [AS 추천]은 표 없이 줄 키를 표와 같은 비교로 줄 세운다."""
    export = (ROOT / "static/js/shipment/image-export.js").read_text(encoding="utf-8")
    dash = (ROOT / "static/js/shipment/shipment-dashboard.js").read_text(encoding="utf-8")
    cols = (ROOT / "static/js/shipment/dashboard-columns.js").read_text(encoding="utf-8")
    assert "'[data-ship-pc-table-deferred]'" in export and "data-ship-pc-table-src" in export
    assert "if (!liveTable) liveTable = await loadDeferredPcTable();" in export
    assert "window.__fomsShipApplyRowSort()" in export and "'foms:ship-pc-table-loaded'" in export
    assert "document.addEventListener('foms:ship-pc-table-loaded', init);" in cols
    assert "window.__fomsShipApplyRowSort = applyShipmentWorkerSortAndColors;" in dash
    assert "if (!tbody) return collectTargetOrderIdsWithoutTable();" in dash
    assert "data-ship-as-rec-rows" in dash and ".sort(__shipDashCompareRowKeys)" in dash
    assert "rows.sort(function (a, b) { return __shipDashCompareRowKeys(rowKey(a), rowKey(b)); });" in dash
    assert "'#shipment-dashboard-table, [data-ship-pc-table-deferred]'" in dash

"""출발 · 상차 완료 시각은 한국 시각으로 — 시공 태블릿 '출고' 칸 · 패킹 시트 머리 · 공장 상차 완료 단추(2026-11-24 고침).

패킹 API 는 ``departed_at`` · ``factory_loaded[f].at`` 을 UTC(+00:00) ISO 로 적는다. 시공 태블릿 첫 화면은 그 글자의 11 ~ 16 자를
그대로 잘라 "출발 05:48"(한국 14:48)로 보였다 — 값이 틀린 것이라 한국 시각으로 바꿔 보인다. 시간대 없는 옛 값은 한국 시각으로 본다
(패킹 시트 머리 JS 가 ``new Date()`` 로 기기 시각 = 한국으로 읽는 것과 같게). UTC 자정 근처 값(한국 날짜가 넘어가는 때)을 같이 본다.
폰 카드는 "출발 보고됨"(시각 없음)이라 해당 없음.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.construction.tablet_first import _packing_fields
from foms.services.datetime_kst import format_datetime_kst
from foms.services.erp_display import get_today_kst
from models import Order, User

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("raw,shown", [
    ("2026-11-24T05:48:41.123456+00:00", "출발 14:48"),  # 실측 결함 값(예전 "출발 05:48")
    ("2026-11-23T15:30:00+00:00", "출발 00:30"),  # UTC 자정 전 — 한국은 다음 날 0시 30분
    ("2026-11-23T14:59:59+00:00", "출발 23:59"),  # 한국 자정 바로 전
    ("2026-11-23T15:00:00Z", "출발 00:00"),
    ("2026-11-12T07:40:00", "출발 07:40"),  # 시간대 없는 옛 값 = 한국 시각(지금 시험 값 그대로)
    ("bad", "출발"),
    ("2026-11-24", "출발"),  # 짧은 값은 지금처럼 시각 없이
])
def test_tablet_departed_time_is_kst(raw, shown):
    assert _packing_fields({"shipment": {"packing": {"items": [], "departed_at": raw}}}) == (shown, "departed")


def test_tablet_departed_after_real_report_matches_kst_clock(client):
    """실제 출발 보고(API) 뒤 — 태블릿 글 = 저장한 UTC 시각을 한국 시각으로."""
    u = User(username="kst-ship", password=generate_password_hash("x"), role="STAFF", team="SHIPMENT", name="가짜출고",
             is_active=True)
    db_session.add(u)
    o = Order(received_date=get_today_kst().isoformat(), customer_name="가짜", phone="010-0000-0000", address="가짜시",
              product="장", status="CONSTRUCTION", is_erp_order=True, structured_data={"items": [{"product_name": "장"}]})
    db_session.add(o)
    db_session.commit()
    with client.session_transaction() as s:
        s["user_id"], s["username"], s["role"] = u.id, u.username, u.role
    keys = [i["key"] for i in client.get(f"/api/erp/shipment/packing/{o.id}").get_json()["data"]["items"]]
    client.post(f"/api/erp/shipment/packing/{o.id}", json={"updates": [{"key": k, "checked": True} for k in keys]})
    data = client.post(f"/api/erp/shipment/packing/{o.id}", json={"departed": True}).get_json()["data"]
    assert data["departed_at"].endswith("+00:00")
    db_session.remove()
    sd = db_session.get(Order, o.id).structured_data
    assert _packing_fields(sd)[0] == "출발 " + format_datetime_kst(data["departed_at"], "%H:%M")


def _node_view(values: list[str]) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("node 없음")
    script = (
        "global.window = {};"
        f"require({json.dumps(str(ROOT / 'static/js/shipment/foms-packing-factory-view.js'))});"
        "const V = window.FomsPackingFactoryView;"
        f"const vals = {json.dumps(values)};"
        "console.log(JSON.stringify({hm: vals.map(V.hm), when: vals.map(V.when)}));"
    )
    env = dict(os.environ, TZ="UTC")  # 기기 시간대가 UTC 여도 한국 시각으로 그린다
    out = subprocess.run([node, "-e", script], capture_output=True, text=True, encoding="utf-8", env=env, check=True)
    return json.loads(out.stdout)


def test_factory_load_button_and_sheet_head_times_are_kst():
    """[1공장 상차 완료 HH:MM 이름] · 출발 보고됨 머리(새 모듈) — 한국 시각 · 자정은 00시(24시 아님)."""
    got = _node_view(["2026-11-23T15:30:00+00:00", "2026-11-23T14:59:59+00:00", "2026-11-24T05:48:41+00:00"])
    assert got["hm"] == ["00:30", "23:59", "14:48"]
    assert got["when"][0] == "2026. 11. 24. 오전 12:30"


def test_old_packing_sheet_formats_with_seoul_zone():
    """지금 패킹 시트(foms-packing.js)의 출발 보고됨 · 줄 체크 시각도 Asia/Seoul 로 그린다(모든 toLocale 호출)."""
    for path in ("static/js/shipment/foms-packing.js", "static/js/shipment/foms-packing-factory-view.js"):
        src = (ROOT / path).read_text(encoding="utf-8")
        calls = re.findall(r"toLocale(?:Date|Time)String\('ko-KR', \{([^}]*)\}\)", src)
        assert calls and all("timeZone: 'Asia/Seoul'" in c for c in calls), path
        assert "hour12: false" not in src

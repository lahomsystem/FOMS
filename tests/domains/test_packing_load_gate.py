"""상차 완료는 그 공장 제작 완료 뒤에만(사장님 2026-11-24) — 공장 꼴(2공장 장이 섞인) 주문의 [N공장 상차 완료] · 옛 출발 보고 단추.

판정은 한 곳 ``drawing_factory.factory_made`` — 출고 상차 줄의 "(제작 중)" 꼬리와 같은 함수다. 생산 단계면 그 공장 완료 표지
(``production.factory_done``)가 살아 있어야, 시공 대기 이후면 표지 없이도 완료, 생산 전 · 단계 모름은 아직 아님.
줄 체크 · 누락 신고 · 줄 더하기는 막지 않는다(패킹 체크는 제작 단계와 상관없이 늘). 1공장뿐인 주문(옛 꼴)은 그대로.
이름은 모두 지어낸 값이다.

되돌리면 실패: 제작 중 공장 상차 완료가 됨 · 옛 출발 보고 단추로 돌아감 · 줄 체크가 막힘 · 상차 줄 "(제작 중)"과 단추 판정이 어긋남 ·
1공장뿐인 주문 출발 보고가 막힘.
"""
from __future__ import annotations

import copy
from pathlib import Path

import pytest

from db import db_session
from foms.services.orders.drawing_factory import factory_made, load_split
from models import Order, OrderEvent
from tests.domains.test_packing_factory_api import URL, _check, _fresh, _keys, _order, _sd, _user

ROOT = Path(__file__).resolve().parents[2]
NOT_DONE = "PACKING_FACTORY_NOT_DONE"


def _making(*, done: tuple[int, ...] = (), stage: str = "PRODUCTION", **kw) -> dict:
    """생산 중인 섞인 주문(1공장 3장 · 2공장 2장) — ``done`` 공장은 완료 표지(지금 그 공장 장 key 전부)."""
    sd = _sd(**kw)
    sd["workflow"]["stage"] = stage
    marks = {}
    for f in done:
        keys = [e["key"] for j, e in enumerate(sd["drawing_current_files"]) if (2 if j in (3, 4) else 1) == f]
        marks[str(f)] = {"keys": keys, "at": "2026-11-24T05:00:00+00:00", "by_name": "윤검수"}
    if marks:
        sd["production"] = {"factory_done": marks}
    return sd


def _events(oid: int, kind: str) -> int:
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type=kind).count()


def test_load_refused_before_factory_done_and_nothing_written(client):
    """① 1공장 줄을 모두 체크했어도 1공장 제작 완료 전이면 400 — 기록 · 이벤트 · 버전 그대로."""
    _user(client, team="SHIPMENT")
    oid = _order(_making())
    data = client.get(URL.format(oid)).get_json()["data"]
    assert _check(client, oid, _keys(data, 1)).status_code == 200  # ⑤ 줄 체크는 막지 않는다
    before, version = _fresh(oid), db_session.get(Order, oid).mutation_version
    res = client.post(URL.format(oid), json={"loaded": 1})
    body = res.get_json()
    assert res.status_code == 400 and body["data"] == {"code": NOT_DONE, "factory": 1}
    assert body["error"] == "1공장 제작 완료 뒤에 상차 완료할 수 있어요."
    assert _fresh(oid) == before and db_session.get(Order, oid).mutation_version == version
    assert "factory_loaded" not in before["shipment"]["packing"] and _events(oid, "PACKING_FACTORY_LOADED") == 0


def test_load_after_factory_done(client):
    """② 1공장 완료 표지가 살아 있으면 상차 완료 — 2공장은 아직(제작 중)이라 출발 보고는 안 됨."""
    _user(client, team="SHIPMENT")
    oid = _order(_making(done=(1,)))
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 1) + _keys(data, 2))
    ok = client.post(URL.format(oid), json={"loaded": 1})
    assert ok.status_code == 200 and ok.get_json()["data"]["groups"][0]["loaded"] is not None
    two = client.post(URL.format(oid), json={"loaded": 2})
    assert two.status_code == 400 and two.get_json()["data"] == {"code": NOT_DONE, "factory": 2}
    assert ok.get_json()["data"]["departed_at"] is None


def test_load_after_order_left_production_without_marks(client):
    """③ 시공 대기로 넘어간 주문은 공장 표지가 없어도 모두 완료 — 두 공장 상차 완료 → 출발 보고."""
    _user(client, team="SHIPMENT")
    oid = _order(_making(stage="CONSTRUCTION"))
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 1) + _keys(data, 2))
    assert client.post(URL.format(oid), json={"loaded": 1}).status_code == 200
    gone = client.post(URL.format(oid), json={"loaded": 2}).get_json()["data"]
    assert gone["departed_at"]


def test_old_depart_button_has_the_same_gate(client):
    """④ 공장 꼴 주문의 옛 [상차 완료 → 출발 보고] — 제작 완료 전 공장이 하나라도 있으면 거절(아무것도 안 씀)."""
    _user(client, team="SHIPMENT")
    oid = _order(_making(done=(1,)))
    data = client.get(URL.format(oid)).get_json()["data"]
    _check(client, oid, _keys(data, 1) + _keys(data, 2))
    before = _fresh(oid)
    res = client.post(URL.format(oid), json={"departed": True})
    assert res.status_code == 400 and res.get_json()["data"] == {"code": NOT_DONE, "factory": 2}
    assert _fresh(oid) == before and _events(oid, "PACKING_DEPARTED") == 0


def test_checks_issue_and_add_are_not_gated(client):
    """⑤ 패킹 체크는 제작 단계와 상관없이 — 체크 · 누락 신고 · 줄 더하기 모두 200(제작 완료 전 두 공장)."""
    _user(client, team="SHIPMENT")
    oid = _order(_making())
    data = client.get(URL.format(oid)).get_json()["data"]
    k2 = _keys(data, 2)
    assert _check(client, oid, k2).status_code == 200
    assert client.post(URL.format(oid), json={"updates": [{"key": k2[0], "issue": "damaged"}]}).status_code == 200
    assert client.post(URL.format(oid), json={"add": {"label": "상판 유리", "factory": 2}}).status_code == 200


@pytest.mark.parametrize("stage,done,made", [
    ("PRODUCTION", (), [False, False]),
    ("PRODUCTION", (2,), [False, True]),
    ("PRODUCTION", (1, 2), [True, True]),
    ("CONSTRUCTION", (), [True, True]),  # 시공 대기 이후 = 모두 완료
    ("CONFIRM", (), [False, False]),  # 생산 전 = 아직(상차 줄엔 꼬리 없음 — 생산 단계가 아니라서)
])
def test_get_groups_made_matches_load_line(client, stage, done, made):
    """⑥ GET 공장 묶음 ``made`` = 출고 상차 줄 판정(같은 함수) — 생산 단계에선 "(제작 중)"이 붙은 공장만 made False."""
    _user(client, team="SHIPMENT")
    sd = _making(stage=stage, done=done)
    oid = _order(copy.deepcopy(sd))
    groups = client.get(URL.format(oid)).get_json()["data"]["groups"]
    assert [g["made"] for g in groups] == made == [factory_made(sd, f) for f in (1, 2)]
    split = load_split(sd)
    assert [f["done"] for f in split["factories"]] == made
    if stage == "PRODUCTION":
        tails = [part.endswith("(제작 중)") for part in split["text"].removeprefix("상차 ").split(" · ")]
        assert tails == [not m for m in made]


def test_plain_order_departure_not_gated(client):
    """⑦ 1공장뿐인 주문(옛 꼴)은 손대지 않음 — 생산 단계여도 지금처럼 출발 보고, 응답 칸 그대로(made 칸 없음)."""
    _user(client, team="SHIPMENT")
    oid = _order(_making(f2=()))
    data = client.get(URL.format(oid)).get_json()["data"]
    assert "groups" not in data and "made" not in str(data.keys())
    _check(client, oid, [i["key"] for i in data["items"]])
    gone = client.post(URL.format(oid), json={"departed": True})
    assert gone.status_code == 200 and gone.get_json()["data"]["departed_at"]


def test_button_reason_line_in_view_js():
    """화면: 제작 완료 전 공장 단추는 꺼지고(줄을 다 체크해도) 단추 바로 아래 까닭 한 줄 — 새 상자 없음."""
    view = (ROOT / "static/js/shipment/foms-packing-factory-view.js").read_text(encoding="utf-8")
    assert "b.disabled = !g.can_check || g.checked < g.total || g.made === false;" in view
    assert "' 제작 완료 뒤에 상차 완료할 수 있어요.'" in view and "'foms-pf__why'" in view
    css = (ROOT / "static/css/components/foms-packing-factory.css").read_text(encoding="utf-8")
    assert ".foms-pf__why {" in css and "border" not in css.split(".foms-pf__why {", 1)[1].split("}", 1)[0]

"""FCOMM-01 긴급 호출 받는 사람 목록 (스테이징 T18 남은 것 2).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.3 · D23(긴급 호출 열기).

* 창(static/js/foms/urgent-call.js)은 사람을 골라 ``target_user_ids`` 로 보낸다 — 팀만으로는 못 보낸다. 그래서 켜진
  프리랜서에게는 내 주문을 맡는 팀(상담 · 도면 · 출고 · 회계) 직원만 이름 · 팀으로 주고 직급(role)은 뺀다.
* 보내기도 같은 사람에게만(목록에 없는 사람 번호를 직접 넣어도 422). 시스템 계정은 뺀다.
* 대조군: 보통 직원은 전원 · 직급까지 그대로 받고, 아무에게나 보낸다.
"""
from __future__ import annotations

import pytest

from foms.services.auth.freelancer_scope import FREELANCER_URGENT_TARGET_MSG, FREELANCER_URGENT_TARGET_TEAMS
from tests.domains.test_auth_finance import _make_user
from tests.security.test_freelancer_edit_guards import _client, _freelancer

_NOTIFY = {"X-FOMS-Notification-Write": "1"}
_ALL_TEAMS = ("CS", "SALES", "DRAWING", "PRODUCTION", "CONSTRUCTION", "SHIPMENT", "ACCOUNTING")


@pytest.fixture
def w(app):
    fl = _freelancer()
    # 요청 뒤 세션이 닫혀 객체가 떨어지므로 번호만 들고 다닌다.
    staff_ids = {team: _make_user("STAFF", team).id for team in _ALL_TEAMS}
    admin_id = _make_user("ADMIN", None).id
    viewer = _make_user("STAFF", "CS")
    return {"fl_id": fl.id, "staff": staff_ids, "admin": admin_id,
            "client": _client(app, fl), "staff_client": _client(app, viewer)}


def _targets(client) -> list[dict]:
    resp = client.get("/erp/api/urgent-targets")
    assert resp.status_code == 200, resp.get_data(as_text=True)[:300]
    body = resp.get_json()
    assert body["success"] is True
    return body["targets"]


def test_freelancer_gets_reduced_targets(w):
    targets = _targets(w["client"])
    ids = {t["id"] for t in targets}
    assert targets, "프리랜서도 부를 사람이 있어야 한다"
    for team, uid in w["staff"].items():
        assert (uid in ids) == (team in FREELANCER_URGENT_TARGET_TEAMS), team
    assert w["admin"] not in ids and w["fl_id"] not in ids
    assert all(str(t["team"]).upper() in FREELANCER_URGENT_TARGET_TEAMS for t in targets)
    # 창이 쓰는 칸(번호 · 이름 · 팀)만 — 직급은 없다
    assert all("role" not in t for t in targets)
    assert all({"id", "name", "team", "selection_team", "team_label"} <= set(t) for t in targets)


def test_staff_targets_unchanged(w):
    """대조군: 보통 직원은 모든 팀 · 관리자까지, 직급 칸도 그대로."""
    targets = _targets(w["staff_client"])
    ids = {t["id"] for t in targets}
    assert set(w["staff"].values()) | {w["admin"]} <= ids
    assert all("role" in t for t in targets)


def test_freelancer_send_limited_to_listed_teams(w):
    client = w["client"]
    ok = client.post("/erp/api/urgent-call", headers=_NOTIFY,
                     json={"target_user_ids": [w["staff"]["DRAWING"]], "message": "도면 확인 부탁해요"})
    assert ok.status_code == 200, ok.get_json()
    for label, denied in (("SALES", w["staff"]["SALES"]), ("PRODUCTION", w["staff"]["PRODUCTION"]), ("ADMIN", w["admin"])):
        resp = client.post("/erp/api/urgent-call", headers=_NOTIFY,
                           json={"target_user_ids": [w["staff"]["CS"], denied], "message": "확인 부탁해요"})
        assert resp.status_code == 422, (label, resp.get_json())
        assert resp.get_json()["message"] == FREELANCER_URGENT_TARGET_MSG


def test_staff_can_send_to_anyone(w):
    """대조군: 보통 직원은 영업 · 생산 · 관리자에게도 보낸다."""
    resp = w["staff_client"].post(
        "/erp/api/urgent-call", headers=_NOTIFY,
        json={"target_user_ids": [w["staff"]["SALES"], w["staff"]["PRODUCTION"], w["admin"]],
              "message": "확인 부탁해요"})
    assert resp.status_code == 200, resp.get_json()


def test_inactive_freelancer_is_normal_staff(app, w):
    off = _freelancer(active=False)
    targets = _targets(_client(app, off))
    assert set(w["staff"].values()) <= {t["id"] for t in targets}
    assert all("role" in t for t in targets)

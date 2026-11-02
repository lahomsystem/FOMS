"""FOMS 공지사항 API 권한(설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §4).

관리자 API 는 ADMIN · MANAGER 만(직원 · 협력사 403, 로그인 안 함 401). 받는 사람 API 는 본사 · 협력사 둘 다 쓰지만
자기 공지만 — 협력사는 본사 전용 공지 · 다른 회사 공지를 못 보고 못 확인한다(404). 검증 실패는 400.
대조군: 같은 공지를 받는 사람은 보고 확인한다. 쓰기 정책 엔진을 켠 운영 모양에서도 협력사 확인이 지나간다.
"""
from __future__ import annotations

import pytest

from db import db_session
from models import Notice, NoticeAck, SecurityLog, User
from tests.security.partner_fixtures import _client, _user, world  # noqa: F401 — pytest fixture 재노출


def _payload(**audience) -> dict:
    return {"title": "공지 제목", "body": "본문", "audience": audience, "display_mode": "POPUP", "pinned": False,
            "starts_at": "", "ends_at": ""}


def _create(app, world, **audience) -> int:
    client = _client(app, db_session.get(User, world["admin"]))
    resp = client.post("/api/admin/notices", json=_payload(**audience))
    assert resp.status_code == 201, resp.get_json()
    return resp.get_json()["data"]["id"]


@pytest.fixture
def manager(app):
    return _user(role="MANAGER", team="CS", name="매니저").id


@pytest.fixture
def policy_on(app):
    """운영처럼 쓰기 정책 엔진(AUTH-01)을 켠다(테스트 기본은 꺼짐)."""
    sentinel = object()
    prev = app.config.get("AUTH_POLICY_ENABLED", sentinel)
    app.config["AUTH_POLICY_ENABLED"] = True
    yield
    if prev is sentinel:
        app.config.pop("AUTH_POLICY_ENABLED", None)
    else:
        app.config["AUTH_POLICY_ENABLED"] = prev


_ADMIN_CALLS = [
    ("get", "/api/admin/notices", None),
    ("get", "/api/admin/notices/audience-options", None),
    ("post", "/api/admin/notices", "payload"),
    ("get", "/api/admin/notices/{id}", None),
    ("put", "/api/admin/notices/{id}", "payload"),
    ("delete", "/api/admin/notices/{id}", None),
    ("get", "/api/admin/notices/{id}/status", None),
]


@pytest.mark.parametrize("who", ["staff", "sales", "partner_a"])
@pytest.mark.parametrize("method, path, body", _ADMIN_CALLS)
def test_admin_api_forbidden_for_staff_and_partner(app, world, who, method, path, body):
    nid = _create(app, world, staff_all=True)
    client = _client(app, db_session.get(User, world[who]))
    kwargs = {"json": _payload(staff_all=True)} if body else {}
    resp = getattr(client, method)(path.format(id=nid), **kwargs)
    assert resp.status_code == 403
    assert resp.get_json()["success"] is False
    assert db_session.get(Notice, nid).deleted_at is None
    assert db_session.query(Notice).count() == 1


def test_admin_api_requires_login(app, world):
    client = _client(app, None)
    assert client.get("/api/admin/notices").status_code == 401
    assert client.get("/api/notices").status_code == 401


def test_manager_can_manage_and_audit_is_written(app, world, manager):
    client = _client(app, db_session.get(User, manager))
    resp = client.post("/api/admin/notices", json=_payload(staff_teams=["SALES"], partner_org_ids=[world["org_a"]]))
    assert resp.status_code == 201
    data = resp.get_json()["data"]
    nid = data["id"]
    assert data["audience_label"] == "본사: 영업 + 협력사: 가나가구"
    assert data["created_by_name"] == "매니저"

    listed = client.get("/api/admin/notices").get_json()["data"]["items"]
    assert [(r["id"], r["ack"]) for r in listed] == [(nid, {"total": 3, "acked": 0})]  # 영업 1 + 가나 2

    opts = client.get("/api/admin/notices/audience-options").get_json()["data"]
    assert opts["counts"]["by_org"][str(world["org_a"])] == 2

    upd = client.put(f"/api/admin/notices/{nid}", json={**_payload(staff_all=True), "title": "고침"})
    assert upd.status_code == 200 and upd.get_json()["data"]["title"] == "고침"
    status = client.get(f"/api/admin/notices/{nid}/status").get_json()["data"]
    assert status["partner"]["total"] == 0 and status["staff"]["total"] >= 3

    assert client.delete(f"/api/admin/notices/{nid}").status_code == 200
    assert client.delete(f"/api/admin/notices/{nid}").status_code == 404
    assert client.get(f"/api/admin/notices/{nid}/status").status_code == 404
    assert client.get("/api/admin/notices").get_json()["data"]["items"] == []
    actions = [r.action for r in db_session.query(SecurityLog).filter(SecurityLog.target_type == "notice")
               .order_by(SecurityLog.id)]
    assert actions == ["NOTICE_CREATED", "NOTICE_UPDATED", "NOTICE_DELETED"]


@pytest.mark.parametrize("payload", [
    {"title": "", "audience": {"staff_all": True}, "display_mode": "LIST"},
    {"title": "t", "audience": {}, "display_mode": "LIST"},
    {"title": "t", "audience": {"staff_all": True}, "display_mode": "X"},
    {"title": "t", "audience": {"staff_all": True}, "display_mode": "LIST",
     "starts_at": "2026-11-05T10:00", "ends_at": "2026-11-04T10:00"},
    {"title": "t", "audience": {"partner_org_ids": ["abc"]}, "display_mode": "LIST"},
])
def test_validation_returns_400(app, world, payload):
    client = _client(app, db_session.get(User, world["admin"]))
    resp = client.post("/api/admin/notices", json=payload)
    assert resp.status_code == 400
    body = resp.get_json()
    assert body["success"] is False and body["error"]
    assert db_session.query(Notice).count() == 0


def test_partner_cannot_see_or_ack_staff_only_notice(app, world):
    nid = _create(app, world, staff_all=True)
    partner = _client(app, db_session.get(User, world["partner_a"]))
    listed = partner.get("/api/notices")
    assert listed.status_code == 200
    assert listed.get_json()["data"]["items"] == []
    assert partner.post(f"/api/notices/{nid}/ack").status_code == 404
    assert partner.post(f"/api/notices/{nid}/read").status_code == 404
    assert db_session.query(NoticeAck).count() == 0
    # 대조군: 본사 직원은 보고 확인한다.
    staff = _client(app, db_session.get(User, world["staff"]))
    data = staff.get("/api/notices").get_json()["data"]
    assert [i["id"] for i in data["items"]] == [nid] and data["unread"] == 1
    assert [p["id"] for p in data["pending"]] == [nid]
    ack = staff.post(f"/api/notices/{nid}/ack")
    assert ack.status_code == 200 and ack.get_json()["data"]["pending"] == []


def test_partner_cannot_see_other_company_notice(app, world):
    nid = _create(app, world, partner_org_ids=[world["org_b"]])
    other = _client(app, db_session.get(User, world["partner_a"]))
    assert other.get("/api/notices").get_json()["data"]["items"] == []
    assert other.post(f"/api/notices/{nid}/ack").status_code == 404
    mine = _client(app, db_session.get(User, world["partner_b"]))
    assert [i["id"] for i in mine.get("/api/notices").get_json()["data"]["items"]] == [nid]
    assert mine.post(f"/api/notices/{nid}/read").get_json()["data"]["unread"] == 0


def test_partner_ack_passes_policy_engine(app, world, policy_on):
    """운영에서는 쓰기 정책 엔진이 켜져 있다 — 협력사 · 본사 확인이 거기서 막히면 안 된다."""
    nid = _create(app, world, staff_all=True, partner_all=True)
    for who in ("partner_a", "staff"):
        client = _client(app, db_session.get(User, world[who]))
        resp = client.post(f"/api/notices/{nid}/ack")
        assert resp.status_code == 200, (who, resp.get_json())
    assert db_session.query(NoticeAck).filter(NoticeAck.ack_at.isnot(None)).count() == 2
    # 협력사는 관리자 쓰기를 엔진 · 문지기에서 못 지난다.
    partner = _client(app, db_session.get(User, world["partner_a"]))
    assert partner.delete(f"/api/admin/notices/{nid}").status_code == 403


def test_inactive_partner_org_hides_notices(app, world):
    from models import PartnerOrg

    nid = _create(app, world, partner_all=True)
    org = db_session.get(PartnerOrg, world["org_a"])
    org.is_active = False
    db_session.commit()
    client = _client(app, db_session.get(User, world["partner_a"]))
    resp = client.post(f"/api/notices/{nid}/ack")
    assert resp.status_code in (401, 403, 404)
    assert db_session.query(NoticeAck).count() == 0


def test_partner_sees_neutral_audience_label_without_other_company_names(app, world):
    """협력사 직원에게는 다른 협력사 이름 · 본사 팀 구성을 보이지 않는다(응답 · 페이지). 본사 직원은 전체 라벨 그대로."""
    both = _create(app, world, staff_teams=["SALES"], partner_org_ids=[world["org_a"], world["org_b"]])
    only = _create(app, world, partner_org_ids=[world["org_a"], world["org_b"]])
    partner = _client(app, db_session.get(User, world["partner_a"]))
    resp = partner.get("/api/notices")
    labels = {i["id"]: i["audience_label"] for i in resp.get_json()["data"]["items"]}
    assert labels == {both: "본사 · 협력사 공지", only: "협력사 공지"}
    text = resp.get_data(as_text=True)
    assert "다라가구" not in text and "영업" not in text
    page = partner.get("/partner/notices").get_data(as_text=True)
    assert "본사 · 협력사 공지" in page and "협력사 공지" in page
    assert "다라가구" not in page and "본사: 영업" not in page
    # 대조군: 본사 직원(영업)은 받는 쪽 전체 라벨을 본다.
    sales = _client(app, db_session.get(User, world["sales"]))
    staff_labels = {i["id"]: i["audience_label"] for i in sales.get("/api/notices").get_json()["data"]["items"]}
    assert staff_labels == {both: "본사: 영업 + 협력사: 가나가구 · 다라가구"}


def test_popup_view_returns_only_pending_and_unread(app, world):
    """본사 공용 창은 ?view=popup — 목록(items) · 목록 본문을 싣지 않고 확인 안 한 창 공지만."""
    popup = _create(app, world, staff_all=True)
    listed_client = _client(app, db_session.get(User, world["admin"]))
    resp = listed_client.post("/api/admin/notices", json={**_payload(staff_all=True), "display_mode": "LIST",
                                                          "body": "목록만 본문 표식"})
    assert resp.status_code == 201
    staff = _client(app, db_session.get(User, world["staff"]))
    got = staff.get("/api/notices?view=popup")
    data = got.get_json()["data"]
    assert set(data) == {"pending", "unread"} and data["unread"] == 2
    assert [p["id"] for p in data["pending"]] == [popup] and data["pending"][0]["body"] == "본문"
    assert "목록만 본문 표식" not in got.get_data(as_text=True)
    ack = staff.post(f"/api/notices/{popup}/ack").get_json()["data"]
    assert ack == {"pending": [], "unread": 1}
    # 기본 목록 계약(items · unread · pending)은 그대로.
    assert set(staff.get("/api/notices").get_json()["data"]) == {"items", "unread", "pending"}


def test_ack_after_notice_ended_is_404(app, world):
    """창을 띄운 뒤 공지가 지워지면 확인은 404 — 창 스크립트는 이것을 "이미 끝난 공지"로 보고 넘어간다."""
    nid = _create(app, world, staff_all=True)
    admin = _client(app, db_session.get(User, world["admin"]))
    assert admin.delete(f"/api/admin/notices/{nid}").status_code == 200
    staff = _client(app, db_session.get(User, world["staff"]))
    assert staff.post(f"/api/notices/{nid}/ack").status_code == 404
    assert db_session.query(NoticeAck).count() == 0

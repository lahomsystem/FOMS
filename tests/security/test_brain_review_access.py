"""제안함 · 다시 확인 · 판 되돌리기 API 권한 · CSRF(설계서 7.5 'API' · 11절 '화면 권한 시험' · D101 · ⑤-3).

- 결정할 수 없는 사람(다른 팀 MANAGER · STAFF · VIEWER)은 읽기 · 쓰기 모두 **404**, 층 승인자도 자기가 결정할 수 없는
  제안(사장님 몫 · 다른 층 · 볼 수 없는 범위)은 404 — 없는 제안과 같은 답. 제안은 그대로 열린 채(대조군: ADMIN 은 넣음).
- 쓰기는 공용 CSRF 가드 뒤(토큰 없으면 403 · 상태 변화 0), 정책 manifest 에 등재(MANAGER_MUTATION · 판 되돌리기 ADMIN_OPS).
- 결정한 사람은 로그인 사용자에서만 — 본문의 사람 칸은 읽지 않는다. 결정 숫자는 ADMIN 만.
합성 계정 · 합성 항목만.
"""

from __future__ import annotations

import os

import pytest
from itsdangerous import URLSafeSerializer

from db import db_session
from foms.persistence.brain.models import BrainChange
from foms.services.brain.store import current_object
from foms.services.orders.order_mutation_policy import load_policy_manifest
from foms.services.request_write_guard import _CSRF_SALT, _CSRF_SESSION_KEY
from models import SecurityLog
from tests.support.brain_review_support import review_world

READS = ("/api/brain/inbox", "/api/brain/inbox/count", "/api/brain/recheck")
WRITES = {
    "brain_review_api.brain_propose": "MANAGER_MUTATION",
    "brain_review_api.brain_apply": "MANAGER_MUTATION",
    "brain_review_api.brain_reject": "MANAGER_MUTATION",
    "brain_review_api.brain_bulk_apply": "MANAGER_MUTATION",
    "brain_review_api.brain_recheck_confirm": "MANAGER_MUTATION",
    "brain_review_api.brain_release_rollback": "ADMIN_OPS",
}


def _client(app, user_id):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
    return client


@pytest.fixture
def ids(app):
    world = review_world(db_session)
    return {"people": {n: u.id for n, u in world["people"].items()}, "changes": world["changes"]}


def _status(change_id):
    db_session.expire_all()
    return db_session.get(BrainChange, change_id).status


@pytest.mark.parametrize("name", ["sales_mgr", "cs_staff", "viewer"])
def test_people_who_cannot_decide_get_404_on_every_read_and_write(app, ids, name):
    client = _client(app, ids["people"][name])
    for path in READS + ("/api/brain/metrics",):
        assert client.get(path).status_code == 404, path
    change = ids["changes"]["cs"]
    for path, body in ((f"/api/brain/proposals/{change}/apply", {"base_version": 1}),
                       (f"/api/brain/proposals/{change}/reject", {"code": "other"}),
                       ("/api/brain/proposals/bulk-apply", {"ids": [change]}),
                       ("/api/brain/proposals", {"action": "propose_retire", "key": "common/door", "base_version": 1, "reason": "x"}),
                       ("/api/brain/recheck/confirm", {"key": "common/fit", "version": 1}),
                       ("/api/brain/releases/1/rollback", {"layer": "common", "confirm_number": 1})):
        resp = client.post(path, json=body)
        assert resp.status_code == 404, path
        assert resp.get_json() == {"success": False, "data": None, "error": "찾을 수 없습니다."}
    assert _status(change) == "open"


def test_approver_gets_404_for_a_proposal_they_may_not_decide_and_admin_applies_it(app, ids):
    ch = ids["changes"]
    cs = _client(app, ids["people"]["cs_mgr"])
    price = cs.post(f"/api/brain/proposals/{ch['price']}/apply", json={"base_version": 1, "approved_by": 1})
    missing = cs.post("/api/brain/proposals/999999/apply", json={"base_version": 1})
    hidden = cs.post(f"/api/brain/proposals/{ch['hidden']}/reject", json={"code": "other"})
    assert price.status_code == missing.status_code == hidden.status_code == 404
    assert price.get_json() == missing.get_json() == hidden.get_json()  # 있는지도 알리지 않는다
    assert _status(ch["price"]) == "open" and _status(ch["hidden"]) == "open"
    assert [c["main"]["id"] for c in cs.get("/api/brain/inbox").get_json()["data"]["cards"]] == [ch["cs"]]
    admin = _client(app, ids["people"]["admin"])
    need = admin.post(f"/api/brain/proposals/{ch['price']}/apply", json={"base_version": 1})
    assert need.status_code == 400 and need.get_json()["data"] == {"code": "BRAIN_CONFIRM", "field": "text"}
    done = admin.post(f"/api/brain/proposals/{ch['price']}/apply",
                      json={"base_version": 1, "confirm": {"field": "text", "value": "지역별 운임 새 기준"}, "view_ms": 800})
    assert done.status_code == 200 and done.get_json()["data"]["version"] == 2
    db_session.expire_all()
    assert db_session.get(BrainChange, ch["price"]).decided_by == ids["people"]["admin"]  # 로그인 사용자 — 본문 아님


def test_conflict_reject_and_reproposal_answers(app, ids):
    ch, people = ids["changes"], ids["people"]
    cs = _client(app, people["cs_mgr"])
    stale = cs.post(f"/api/brain/proposals/{ch['cs']}/apply", json={"base_version": 3})
    assert stale.status_code == 409 and stale.get_json()["data"] == {"code": "BRAIN_BASE_CHANGED", "current_version": 1}
    rejected = cs.post(f"/api/brain/proposals/{ch['cs']}/reject", json={"code": "wrong_number", "view_ms": 2500})
    assert rejected.status_code == 200 and rejected.get_json()["data"]["code"] == "wrong_number"
    again = cs.post(f"/api/brain/proposals/{ch['cs']}/reject", json={"code": "other"})
    assert again.status_code == 409 and again.get_json()["data"]["code"] == "BRAIN_TARGET"  # 이미 결정됨
    same = cs.post("/api/brain/proposals", json={"action": "propose_edit", "key": "cs/lesson/photo", "base_version": 1,
                                                 "after": {"name": "사진 먼저 꼭 받기"}, "reason": "다시"})
    assert same.status_code == 409 and same.get_json()["data"] == {"code": "BRAIN_REJECTED_BEFORE",
                                                                   "reject_code": "wrong_number"}


def test_human_proposals_need_only_a_visible_item(app, ids):
    cs = _client(app, ids["people"]["cs_mgr"])
    made = cs.post("/api/brain/proposals", json={"action": "propose_edit", "key": "common/door", "base_version": 1,
                                                 "after": {"text": "여닫이 문짝 고칠 말"}, "reason": "상담 중 알게 됨",
                                                 "proposed_by": "agent:nope"})
    assert made.status_code == 200
    change = db_session.get(BrainChange, made.get_json()["data"]["change_id"])
    assert change.proposed_by == f"user:{ids['people']['cs_mgr']}" and change.status == "open"
    audit = db_session.query(SecurityLog).filter_by(action="BRAIN_PROPOSE", target_id=change.id).one()
    assert audit.user_id == ids["people"]["cs_mgr"] and audit.detail == {"op": "update", "grade": "B_LIGHT",
                                                                         "rollback_of": None}
    assert change.action == "propose_edit"
    assert "고칠 말" not in audit.message  # 감사 줄은 코드 · 숫자만
    assert cs.post("/api/brain/proposals", json={"action": "propose_edit", "key": "drawing/rule/final", "base_version": 1,
                                                 "after": {"text": "숨은 항목"}, "reason": "x"}).status_code == 404
    bad = cs.post("/api/brain/proposals", json={"action": "propose_edit", "key": "common/door", "base_version": 1,
                                                "after": {"visibility": "price"}, "reason": "x"})
    assert bad.status_code == 400 and bad.get_json()["data"]["code"] == "BRAIN_SHAPE"
    retire = cs.post("/api/brain/proposals", json={"action": "propose_retire", "key": "common/door", "base_version": 1,
                                                   "reason": "안 파는 제품"})
    assert retire.status_code == 200 and retire.get_json()["data"]["grade"] == "B"
    assert current_object(db_session, "common/door").status == "active"  # 제안일 뿐 — 은퇴는 승인 뒤


def test_writes_need_a_csrf_token(app, ids):
    client = _client(app, ids["people"]["cs_mgr"])
    change = ids["changes"]["cs"]
    app.config["WRITE_GUARD_ENABLED"] = True
    try:
        for path, body in ((f"/api/brain/proposals/{change}/apply", {"base_version": 1}),
                           (f"/api/brain/proposals/{change}/reject", {"code": "other"}),
                           ("/api/brain/proposals", {"action": "propose_retire", "key": "common/door", "base_version": 1,
                                                     "reason": "x"}),
                           ("/api/brain/recheck/confirm", {"key": "common/fit", "version": 1})):
            blocked = client.post(path, json=body)
            assert blocked.status_code == 403 and blocked.headers.get("X-Write-Guard") == "blocked", path
        assert _status(change) == "open"
        assert client.get("/api/brain/inbox").status_code == 200  # 읽기는 토큰 없이
        seed = os.urandom(16).hex()
        with client.session_transaction() as sess:
            sess[_CSRF_SESSION_KEY] = seed
        token = URLSafeSerializer(app.secret_key, salt=_CSRF_SALT).dumps(seed)
        passed = client.post(f"/api/brain/proposals/{change}/apply", json={"base_version": 1},
                             headers={"X-CSRF-Token": token})
        assert passed.status_code == 200
    finally:
        app.config.pop("WRITE_GUARD_ENABLED", None)
    assert _status(change) == "applied"


def test_release_rollback_and_metrics_are_admin_only(app, ids):
    people = ids["people"]
    cs, admin = _client(app, people["cs_mgr"]), _client(app, people["admin"])
    assert cs.get("/api/brain/metrics").status_code == 404
    metrics = admin.get("/api/brain/metrics?days=7")
    assert metrics.status_code == 200 and metrics.get_json()["data"]["days"] == 7
    assert cs.post("/api/brain/releases/1/rollback", json={"layer": "common", "confirm_number": 1}).status_code == 404
    unconfirmed = admin.post("/api/brain/releases/1/rollback", json={"layer": "common"})
    assert unconfirmed.status_code == 400
    done = admin.post("/api/brain/releases/1/rollback", json={"layer": "common", "confirm_number": 1})
    assert done.status_code == 200 and done.get_json()["data"]["number"] == 1
    assert current_object(db_session, "common/door") is None  # 판 1 공통 층 = 만들기들 → 지워짐


def test_recheck_confirm_over_http(app, ids):
    admin = _client(app, ids["people"]["admin"])
    listed = admin.get("/api/brain/recheck").get_json()["data"]
    assert [i["key"] for i in listed["items"]] == ["common/fit", "common/shipping"]
    count = admin.get("/api/brain/inbox/count").get_json()["data"]
    assert count["inbox"]["open"] == 4 and count["recheck"]["total"] == 2 and count["recheck"]["line"]
    done = admin.post("/api/brain/recheck/confirm", json={"key": "common/fit", "version": 1, "view_ms": 700})
    assert done.status_code == 200 and done.get_json()["data"]["version"] == 2
    busy = admin.post("/api/brain/recheck/confirm", json={"key": "common/shipping", "version": 1})
    assert busy.status_code == 409 and busy.get_json()["data"]["code"] == "BRAIN_OPEN_PROPOSAL"


def test_write_routes_are_listed_in_the_policy_manifest(app):
    routes = load_policy_manifest()["routes"]
    for endpoint, policy in WRITES.items():
        assert routes[endpoint]["policy_id"] == policy and routes[endpoint]["mode"] == "guard", endpoint
    brain_writes = {r.endpoint for r in app.url_map.iter_rules()
                    if r.endpoint.startswith("brain_") and not r.endpoint.startswith("brain_chat_api.")
                    and r.methods - {"GET", "HEAD", "OPTIONS"}}
    assert brain_writes == set(WRITES)  # 읽기 블루프린트(brain_api · brain_web)에는 쓰기가 없다(물어보기는 test_brain_chat_access)


def test_the_page_shows_inbox_and_recheck_tabs_with_scoped_counts(app, ids):
    cs = _client(app, ids["people"]["cs_mgr"]).get("/brain?tab=inbox").get_data(as_text=True)
    admin = _client(app, ids["people"]["admin"]).get("/brain?tab=inbox").get_data(as_text=True)
    assert 'data-brain-count="inbox">1<' in cs and 'data-brain-count="inbox">4<' in admin
    assert 'data-brain-count="recheck">0<' in cs and 'data-brain-count="recheck">2<' in admin
    assert 'data-is-admin="0"' in cs and 'data-is-admin="1"' in admin
    card = _client(app, ids["people"]["cs_mgr"]).get("/brain/items/common/door").get_data(as_text=True)
    assert "data-brain-propose-open=\"propose_edit\"" in card and "brain-item-actions.js" in card

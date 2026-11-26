"""생산 넘어간 주문의 도면 수정 D4 — 공장 [도면 수정 요청] API · 사진 길 · 알림 · 도면 판 단추(설계서 2026-11-25 §2-4 · §4-1 · §4-2 · N3 · §6).

* 누가(§4-1): 관리자 · 반장 = 모든 도면(남의 공장 도면 포함 — 설계서 표 그대로), 파트 계정 = 자기 공장 도면만. 남의 공장(파트) · 영업 ·
  도면팀 · 보기만(생산팀 파트 · 반장 아님 · VIEWER) · 협력사 = 403 ``REQUEST_FORBIDDEN``. 생산 단계 아님 = 409 ``INVALID_STAGE``.
* 몸(§4-2): 사유 빈 글 400 · 도면 0장 400 · 사진 4장 400 · 사진 경로 이상 400 · 지금 도면에 없는 장 409 ``FIX_NOT_CURRENT``.
* 쓰기: 요청 한 건(``state: open`` · D2 가 읽는 모양) · 버전 +1 · ``OrderEvent PRODUCTION_DRAWING_REQUESTED`` · 감사. 머리글
  ``Idempotency-Key`` 가 같으면 한 건만(두 번째는 같은 요청을 돌려줌 — 버전 · 이벤트 · 알림 0).
* 바로 막힘(사장님 "요청하면 바로 막기"): 그 도면만 — 도면 누름 409 · [제작 완료] 409 · 공장 꼴 패킹 줄 409. 다른 장은 그대로.
* 알림(사장님 "영업 수정 요청과 똑같이"): 종(``target_team='DRAWING'`` → 도면팀 state) + 폰(enqueue 한 번) + 확인 창(실시간 ``interrupt``),
  받는 사람 = 도면팀 전원 + 관리자. 제목 "공장 도면 수정 요청". 폰 배너 · 벨 링크 = 작업실 그 주문 요청사항 칸.

되돌리면 실패: 남의 공장 파트 계정 200 · 생산 단계 아닌 주문 200 · 사유 없이 200 · 사진 4장 200 · 요청 뒤 그 도면 누름 200 · 같은 열쇠 두 번에
두 건 · 알림이 영업에게 감. 대조군: 요청 없는 주문은 전과 같다. 이름은 모두 지어낸 값이다(실제 알림 · 폰 발송 없음 — 가짜로 받는다).
"""
from __future__ import annotations

import html as htmllib
import io
import json
import re
from types import SimpleNamespace

import pytest

import foms.api.production.drawing_request as request_api
from db import db_session
from foms.api.notifications import _resolve_notification_deep_link
from foms.services.notifications import push_sender
from foms.services.orders import drawing_fix as fx
from foms.services.orders.order_mutation_policy import load_policy_manifest
from foms.services.production.part_mark_gates import DRAWING_REVISING, REVISING_MESSAGE
from foms.services.request_write_guard import load_write_guard_manifest
from foms.services.storage import StorageAdapter
from models import Notification, NotificationUserState, Order, OrderEvent, PartnerOrg, SecurityLog
from tests.support.production_factory_seed import TABLET, factory_user, mixed_order, set_cookies
from tests.support.production_part_claim_seed import code, fresh, login, make_order, make_user, mark
from tests.support.production_steps_seed import mark_order_inspected

URL = "/api/orders/{oid}/production/drawing-request"
PHOTO = "/api/orders/{oid}/production/drawing-request/photo"
FORBIDDEN = "도면 수정 요청은 반장이나 그 도면 파트 담당만 할 수 있어요."
OTHER1 = "1공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."
OTHER2 = "2공장에서 작업하는 도면이에요. [다시 받기]를 눌러 주세요."


class FakeStorage:
    """사진 올리기를 받아만 두는 가짜 저장소(실제 저장소 손 안 댐). 파일 종류 판정은 진짜 저장소 함수 그대로."""

    get_file_type = StorageAdapter.get_file_type

    def __init__(self, key_override=None):
        self.saved: list[str] = []
        self.key_override = key_override

    def upload_file(self, file_obj, filename, folder):
        file_obj.read()
        key = self.key_override or f"{folder}/20261125_120000_{len(self.saved):08d}_photo.jpg"
        self.saved.append(key)
        return {"success": True, "key": key}


@pytest.fixture
def sent(monkeypatch):
    """폰 · 실시간 알림을 가짜로 받는다 — ``push`` = enqueue 한 알림 id, ``emits`` = (받는 사람, 실을 것)."""
    box = SimpleNamespace(push=[], emits=[], storage=FakeStorage())
    monkeypatch.setattr(request_api, "enqueue_push_for_notification", lambda nid, **k: box.push.append(nid))
    monkeypatch.setattr(request_api, "emit_erp_notification_to_users", lambda ids, data: box.emits.append((set(ids), data)))
    monkeypatch.setattr(request_api, "get_storage", lambda: box.storage)
    return box


@pytest.fixture
def who():
    return SimpleNamespace(
        lead=make_user("박반장", lead=True), part=factory_user("최엣지", part="edge"),
        part2=factory_user("한엣지", part="edge", factory=2), admin=make_user("한관리", team=None, role="ADMIN"),
        drawer=make_user("김도면", team="DRAWING"), drawer2=make_user("오도면", team="DRAWING", role="MANAGER"),
        sales=make_user("이영업", team="SALES"), readonly=make_user("남생산", team="PRODUCTION"),
        viewer=make_user("문보기", team="PRODUCTION", role="VIEWER"),
    )


def _post(client, oid: int, js: list[int], *, seed=None, note: str = "측판 길이가 실측과 달라요", photos=None, idem=None):
    keys = (seed or fresh(oid)).keys if seed is not None else [f["key"] for f in fresh(oid).structured_data["drawing_current_files"]]
    body = {"targets": [{"key": keys[j]} for j in js], "note": note}
    if photos is not None:
        body["photos"] = photos
    return client.post(URL.format(oid=oid), json=body, headers={"Idempotency-Key": idem} if idem else {})


def _requests(oid: int) -> list[dict]:
    return (fresh(oid).structured_data.get("drawing_fix") or {}).get("requests") or []


def _events(oid: int) -> list[OrderEvent]:
    db_session.expire_all()
    return db_session.query(OrderEvent).filter_by(order_id=oid, event_type="PRODUCTION_DRAWING_REQUESTED").all()


# --- 누가(§4-1) ------------------------------------------------------------------


@pytest.mark.parametrize("name, js", [("lead", [1]), ("part", [0, 1]), ("admin", [2, 3])])
def test_lead_admin_and_own_factory_part_can_request(client, sent, who, name, js):
    seed = mixed_order(4, f2=(2, 3))                      # 도면 3 · 4 = 2공장
    login(client, getattr(who, name))
    res = _post(client, seed.id, js, seed=seed)
    assert res.status_code == 200, res.get_json()
    req = res.get_json()["data"]["request"]
    assert req["state"] == "open" and req["from"] == "factory" and req["numbers"] == [j + 1 for j in js]
    assert req["by_name"] == getattr(who, name).name and req["note"] == "측판 길이가 실측과 달라요" and req["checked"] is False
    assert [r["id"] for r in _requests(seed.id)] == [req["id"]]


@pytest.mark.parametrize("name", ["lead", "part"])
def test_lead_and_part_cannot_request_another_factory_drawing(client, sent, who, name):
    """사장님 2026-11-25 답 "자기 공장 도면만" — 반장도 파트 계정처럼 자기 공장 도면만(카드 쓰기 공장 문과 같은 판정 · 같은 글)."""
    seed = mixed_order(4, f2=(2, 3))
    login(client, getattr(who, name))
    res = _post(client, seed.id, [3], seed=seed)                          # 도면 4 = 2공장(두 사람 모두 1공장)
    assert res.status_code == 403 and code(res) == "REQUEST_FORBIDDEN"
    assert res.get_json()["error"] == OTHER2 and _requests(seed.id) == []
    login(client, who.admin)                                               # 대조군: 관리자는 모든 도면
    assert _post(client, seed.id, [3], seed=seed).status_code == 200


@pytest.mark.parametrize("name", ["part2", "sales", "drawer", "readonly", "viewer"])
def test_other_factory_part_sales_drawing_readonly_and_viewer_are_refused(client, sent, who, name):
    seed = mixed_order(4, f2=(2, 3))
    before = fresh(seed.id).mutation_version
    login(client, getattr(who, name))
    res = _post(client, seed.id, [0], seed=seed)          # 도면 1 = 1공장(2공장 파트 계정에겐 남의 공장)
    want = OTHER1 if name == "part2" else FORBIDDEN       # 남의 공장 도면 = 카드 쓰기 공장 문의 지금 글
    assert res.status_code == 403 and code(res) == "REQUEST_FORBIDDEN" and res.get_json()["error"] == want
    assert _requests(seed.id) == [] and fresh(seed.id).mutation_version == before and not sent.push


def test_part_account_mixed_pick_with_another_factory_drawing_is_refused_whole(client, sent, who):
    seed = mixed_order(4, f2=(2, 3))
    login(client, who.part)
    res = _post(client, seed.id, [0, 2], seed=seed)       # 1공장 + 2공장
    assert res.status_code == 403 and code(res) == "REQUEST_FORBIDDEN" and _requests(seed.id) == []


def test_partner_account_is_refused(client, sent):
    partner = PartnerOrg(name="가짜협력사")
    db_session.add(partner)
    db_session.commit()
    seed = make_order(3)
    login(client, make_user("허협력", team="PRODUCTION", role="PARTNER", part="cut", partner_org_id=partner.id))
    assert _post(client, seed.id, [0], seed=seed).status_code == 403 and _requests(seed.id) == []


@pytest.mark.parametrize("stage", ["CONSTRUCTION", "CONFIRM"])
def test_only_production_stage_orders(client, sent, who, stage):
    seed = make_order(3, extra={"workflow": {"stage": stage}})
    login(client, who.lead)
    res = _post(client, seed.id, [0], seed=seed)
    assert res.status_code == 409 and code(res) == "INVALID_STAGE"
    assert res.get_json()["error"] == "생산 단계 주문이 아니에요. [다시 받기]를 눌러 주세요." and _requests(seed.id) == []


# --- 몸(§4-2) --------------------------------------------------------------------


def _photo(oid: int, j: int) -> dict:
    return {"key": f"orders/{oid}/drawing_gateway/revisions/p{j}.jpg", "filename": f"p{j}.jpg"}


@pytest.mark.parametrize("note, js, photos, want, text", [
    ("   ", [0], None, "REQUEST_NOTE_REQUIRED", "사유를 적어 주세요."),
    ("측판", [], None, "REQUEST_PICK", "수정할 도면을 골라 주세요."),
    ("측판", [0], "four", "REQUEST_PHOTOS", "사진은 3장까지 올릴 수 있어요."),
    ("측판", [0], "bad", "REQUEST_PHOTOS", "사진을 다시 올려 주세요."),
])
def test_body_refusals(client, sent, who, note, js, photos, want, text):
    seed = make_order(3)
    login(client, who.lead)
    if photos == "four":
        photos = [_photo(seed.id, j) for j in range(4)]
    elif photos == "bad":
        photos = [{"key": "orders/999999/drawing_gateway/revisions/x.jpg", "filename": "x.jpg"}]   # 남의 주문 경로
    res = _post(client, seed.id, js, seed=seed, note=note, photos=photos)
    assert res.status_code == 400 and code(res) == want and res.get_json()["error"] == text
    assert _requests(seed.id) == []


def test_three_photos_are_kept_as_key_and_name_only(client, sent, who):
    seed = make_order(3)
    login(client, who.lead)
    photos = [{**_photo(seed.id, j), "view_url": "javascript:alert(1)"} for j in range(3)]
    res = _post(client, seed.id, [1], seed=seed, photos=photos)
    assert res.status_code == 200, res.get_json()
    assert _requests(seed.id)[0]["photos"] == [_photo(seed.id, j) for j in range(3)]


def test_drawing_not_in_current_files_is_refused(client, sent, who):
    seed = make_order(3)
    login(client, who.lead)
    res = client.post(URL.format(oid=seed.id), json={"targets": [{"key": "orders/1/gone.png"}], "note": "측판"})
    assert res.status_code == 409 and code(res) == "FIX_NOT_CURRENT" and _requests(seed.id) == []


# --- 쓰기 · 멱등 · 바로 막힘 ---------------------------------------------------------


def test_one_request_event_audit_and_version_and_the_same_key_makes_it_once(client, sent, who):
    seed = make_order(3)
    login(client, who.part)
    before = fresh(seed.id).mutation_version
    first = _post(client, seed.id, [1], seed=seed, idem="k-1")
    again = _post(client, seed.id, [1], seed=seed, idem="k-1")
    assert first.status_code == 200 and again.status_code == 200, again.get_json()
    assert again.get_json()["data"]["request"]["id"] == first.get_json()["data"]["request"]["id"]
    assert again.get_json()["data"]["changed"] is False and first.get_json()["data"]["changed"] is True
    assert len(_requests(seed.id)) == 1 and fresh(seed.id).mutation_version == before + 1
    assert len(_events(seed.id)) == 1 and len(sent.push) == 1 and len(sent.emits) == 1
    payload = _events(seed.id)[0].payload
    assert payload["numbers"] == [2] and payload["by_name"] == "최엣지" and payload["idents"] == _requests(seed.id)[0]["targets"]
    db_session.expire_all()
    assert db_session.query(SecurityLog).filter_by(action="PRODUCTION_DRAWING_REQUESTED", target_id=seed.id).count() == 1
    log = fresh(seed.id).structured_data["drawing_fix"]["log"]
    assert [(row["act"], row["numbers"], row["by_name"]) for row in log] == [("request", [2], "최엣지")]
    other = _post(client, seed.id, [2], seed=seed, idem="k-2")          # 다른 열쇠 = 새 요청(도면 2 는 이미 막혀 다른 장)
    assert other.status_code == 200 and len(_requests(seed.id)) == 2


def test_request_blocks_that_drawing_at_once_for_marks_and_complete(client, sent, who):
    seed = make_order(3)
    login(client, who.lead)
    res = _post(client, seed.id, [1], seed=seed)
    data = res.get_json()["data"]
    assert data["keys"] == [seed.keys[1]] and data["block"] == {"kind": "revise", "text": "도면 고치는 중", "why": REVISING_MESSAGE}
    sd = fresh(seed.id).structured_data
    assert fx.blocked(sd).whole is False and [r["no"] for r in fx.blocked_entries(sd)] == [2]
    login(client, who.part)                                                 # 엣지 파트 계정
    refused = mark(client, seed, 1, "edge", "take", "none")
    assert refused.status_code == 409 and code(refused) == DRAWING_REVISING and refused.get_json()["data"]["numbers"] == [2]
    assert mark(client, seed, 0, "edge", "take", "none").status_code == 200  # 다른 장은 계속 작업
    mark_order_inspected(seed.id)
    login(client, who.lead)
    done = client.post(f"/api/orders/{seed.id}/production/complete", json={})
    assert done.status_code == 409 and done.get_json()["code"] == DRAWING_REVISING and done.get_json()["numbers"] == [2]


def test_request_blocks_the_factory_packing_line_of_that_drawing(client, sent, who):
    seed = mixed_order(3, f2=(2,), extra={"items": [{"product_name": "가짜장"}]})
    login(client, who.lead)
    assert _post(client, seed.id, [1], seed=seed).status_code == 200
    login(client, who.admin)
    url = f"/api/erp/shipment/packing/{seed.id}"
    sid = fresh(seed.id).structured_data["drawing_current_files"][1]["sheet_id"]
    res = client.post(url, json={"updates": [{"key": f"sheet:{sid}", "checked": True}]})
    assert res.status_code == 409 and res.get_json()["data"]["code"] == DRAWING_REVISING
    other = fresh(seed.id).structured_data["drawing_current_files"][0]["sheet_id"]
    assert client.post(url, json={"updates": [{"key": f"sheet:{other}", "checked": True}]}).status_code == 200


def test_control_order_without_a_request_is_unchanged(client, sent, who):
    """대조군: 요청이 없는 주문은 막힘 없음 · 누름 · 제작 완료 지금 그대로, 다른 주문 요청이 섞이지 않는다."""
    busy, free, made = make_order(3), make_order(3), make_order(3)
    login(client, who.lead)
    assert _post(client, busy.id, [0], seed=busy).status_code == 200
    sd = fresh(free.id).structured_data
    assert "drawing_fix" not in sd and fx.blocked(sd).idents == frozenset()
    login(client, who.part)
    assert mark(client, free, 0, "edge", "take", "none").status_code == 200
    mark_order_inspected(made.id)
    login(client, who.lead)
    assert client.post(f"/api/orders/{made.id}/production/complete", json={}).status_code == 200


# --- 알림(§6) --------------------------------------------------------------------


def test_notification_goes_to_whole_drawing_team_and_admins_like_a_sales_request(client, sent, who):
    seed = make_order(3, extra={"parties": {"customer": {"name": "정하늘"}}})
    login(client, who.lead)
    assert _post(client, seed.id, [1, 2], seed=seed, note="측판 길이").status_code == 200
    db_session.expire_all()
    note = db_session.query(Notification).filter_by(order_id=seed.id).one()
    assert (note.notification_type, note.target_team, note.title) == ("DRAWING_FACTORY_REQUEST", "DRAWING", "공장 도면 수정 요청")
    assert note.message == f"주문 #{seed.id} (정하늘) 공장 도면 수정 요청이 접수되었습니다. 대상: 2, 3번 도면 (2건). 사유: 측판 길이"
    states = {s.user_id for s in db_session.query(NotificationUserState).filter_by(notification_id=note.id)}
    assert {who.drawer.id, who.drawer2.id} <= states and not states & {who.sales.id, who.lead.id, who.part.id}
    assert sent.push == [note.id]
    (ids, data), = sent.emits
    assert {who.drawer.id, who.drawer2.id, who.admin.id} <= ids and not ids & {who.sales.id, who.readonly.id}
    assert data["interrupt"] is True and data["notification_type"] == "DRAWING_FACTORY_REQUEST" and data["customer_name"] == "정하늘"


def test_push_banner_and_bell_links_open_the_requests_section(app):
    note = Notification(id=77, order_id=5801, notification_type="DRAWING_FACTORY_REQUEST", title="공장 도면 수정 요청",
                        message="사유: 남기지 않음", is_urgent=False)
    payload = push_sender._build_payload(note, "정하늘")
    assert payload["title"] == "공장 도면 수정 요청 · 정하늘" and "사유" not in payload["body"]
    assert payload["body"] == "주문 #5801 (정하늘) 공장 도면 수정 요청이 접수되었습니다."
    assert payload["data"]["deep_link"] == "/erp/drawing-workbench/5801?tab=requests"
    assert _resolve_notification_deep_link(note, {})["deep_link_url"] == "/erp/drawing-workbench/5801?tab=requests"
    assert "DRAWING_FACTORY_REQUEST" in push_sender._HIGH_URGENCY_TYPES and "DRAWING_FACTORY_REQUEST" in push_sender._DEFAULT_P1_TYPES
    rejected = Notification(id=78, order_id=5801, notification_type="DRAWING_FACTORY_REQUEST_REJECTED", title="도면 수정 요청 반려",
                            message="", is_urgent=False)
    assert push_sender._build_payload(rejected, "정하늘")["title"] == "도면 수정 요청 반려 · 정하늘"
    assert "DRAWING_FACTORY_REQUEST_REJECTED" in push_sender._DEFAULT_P1_TYPES


# --- 사진 길 ---------------------------------------------------------------------


def _upload(client, oid: int, name: str = "측판.jpg"):  # noqa: D103
    return client.post(PHOTO.format(oid=oid), data={"file": (io.BytesIO(b"\xff\xd8fake"), name)},
                       content_type="multipart/form-data")


def test_production_accounts_upload_a_photo_into_the_revision_folder(client, sent, who):
    seed = make_order(3)
    login(client, who.part)
    res = _upload(client, seed.id)
    assert res.status_code == 200, res.get_json()
    file = res.get_json()["data"]["file"]
    assert file["key"].startswith(f"orders/{seed.id}/drawing_gateway/revisions/") and file["filename"] == "측판.jpg"
    assert file["view_url"] == f"/api/files/view/{file['key']}"
    login(client, who.lead)                                  # 올린 사진으로 요청하면 저장 검사를 지난다
    ok = _post(client, seed.id, [0], seed=seed, photos=[{"key": file["key"], "filename": file["filename"]}])
    assert ok.status_code == 200 and _requests(seed.id)[0]["photos"] == [{"key": file["key"], "filename": "측판.jpg"}]


def test_photo_route_refuses_others_wrong_stage_and_foreign_key(client, sent, who):
    seed = make_order(3)
    login(client, who.sales)
    assert _upload(client, seed.id).status_code == 403
    later = make_order(3, extra={"workflow": {"stage": "CONSTRUCTION"}})
    login(client, who.lead)
    assert code(_upload(client, later.id)) == "INVALID_STAGE"
    sent.storage.key_override = "orders/1/somewhere/else.jpg"
    bad = _upload(client, seed.id)
    assert bad.status_code == 400 and code(bad) == "REQUEST_PHOTOS" and bad.get_json()["error"] == "사진을 다시 올려 주세요."


# --- 매니페스트 · 도면 판 단추 ----------------------------------------------------------


def test_routes_are_in_both_manifests_as_production_edit_guard():
    policy, guard = load_policy_manifest()["routes"], load_write_guard_manifest()["routes"]
    for endpoint, rule in (("api_production_drawing_request", "/api/orders/<int:order_id>/production/drawing-request"),
                           ("api_production_drawing_request_photo",
                            "/api/orders/<int:order_id>/production/drawing-request/photo")):
        name = f"erp_orders_drawing_request.{endpoint}"
        assert policy[name] == {"mode": "guard", "policy_id": "PRODUCTION_EDIT", "rule": rule}
        assert guard[name] == {"mode": "guard", "rule": rule}


@pytest.fixture
def cohort(monkeypatch):
    """도면 판은 모바일 v2 셸 + 터치 기기에서만 그린다(test_production_factory_screens 와 같은 준비)."""
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", "all")


def _board(client, user, url: str = "/erp/production/home?day=none") -> str:
    login(client, user)
    set_cookies(client, TABLET)
    return client.get(url).get_data(as_text=True)


def _card_opts(html: str, oid: int) -> dict[int, list[dict] | None]:
    """판의 그 주문 카드마다 [도면 수정 요청] 창 고르기(단추가 없으면 None) — 카드 칸만 읽는다(페이지 통째 낱말 아님)."""
    out = {}
    for m in re.finditer(r'<article class="pp-card[^"]*"\s+data-pp-card data-order-id="%d"[^>]*data-no="(\d+)"(.*?)</article>' % oid,
                         html, re.S):
        btn = re.search(r'<button type="button" class="foms-prod-home__btn pp-req" data-pp-req data-pp-req-opts="([^"]*)">', m.group(2))
        out[int(m.group(1))] = json.loads(htmllib.unescape(btn.group(1))) if btn else None
    return out


def _modal(html: str) -> str:
    start = html.index('<div id="foms-part-request-modal"')
    return html[start:html.index('<div class="pp-view"', start)]


def test_board_button_only_on_own_factory_unblocked_cards_and_dialog_only_for_requesters(client, sent, who, cohort):
    seed = mixed_order(4, f2=(2, 3))
    sids = [f["sheet_id"] for f in fresh(seed.id).structured_data["drawing_current_files"]]
    html = _board(client, who.part)
    mine = [{"no": 1, "sheet_id": sids[0]}, {"no": 2, "sheet_id": sids[1]}]          # 고르기 = 자기 공장 장만(도면 3 · 4 = 2공장)
    assert _card_opts(html, seed.id) == {1: mine, 2: mine}
    modal = _modal(html)
    assert "어느 도면인가요?" in modal and "사진 (있으면 올려 주세요 · 3장까지)" in modal and ">요청 보내기</button>" in modal
    assert re.search(r'<input type="file" accept="image/\*" multiple hidden data-foms-no-capture data-pp-rq-file>', modal)
    assert re.search(r'foms-production-drawing-request\.js\?v=\d{8}[a-z]" defer', html)
    login(client, who.lead)
    assert _post(client, seed.id, [0], seed=seed).status_code == 200
    blocked = _card_opts(_board(client, who.part), seed.id)
    assert blocked == {1: None, 2: [{"no": 2, "sheet_id": sids[1]}]}   # 막힌 카드는 단추 없음 · 남은 카드 창에서도 막힌 장이 빠진다
    readonly = _board(client, who.readonly, "/erp/production/home?tab=parts&day=none")   # 읽기 전용은 '도면 카드' 화면에서 판을 본다
    assert _card_opts(readonly, seed.id) == {1: None, 2: None} and 'id="foms-part-request-modal"' not in readonly


def test_lead_dialog_lists_own_factory_only_and_admin_lists_all(client, sent, who, cohort):
    """창 고르기 = 판 단추와 같은 함수 — 반장은 자기 공장 장만(사장님 답), 관리자는 두 공장 모두."""
    seed = mixed_order(4, f2=(2, 3))
    sids = [f["sheet_id"] for f in fresh(seed.id).structured_data["drawing_current_files"]]
    lead = _card_opts(_board(client, who.lead, "/erp/production/home?tab=parts&day=none"), seed.id)
    assert lead == {1: [{"no": 1, "sheet_id": sids[0]}, {"no": 2, "sheet_id": sids[1]}]} | {2: lead[1]}
    admin = _card_opts(_board(client, who.admin, "/erp/production/home?tab=parts&day=none"), seed.id)
    assert admin[1] == [{"no": n + 1, "sheet_id": sids[n]} for n in range(4)]


def test_order_whose_drawings_are_all_blocked_shows_no_button(client, sent, who, cohort):
    """대조군: 고를 도면이 0장인 주문(도면 모두 막힘)은 어느 카드에도 단추가 없다."""
    seed = mixed_order(2, f2=())
    login(client, who.lead)
    assert _post(client, seed.id, [0, 1], seed=seed).status_code == 200
    assert _card_opts(_board(client, who.part), seed.id) == {1: None, 2: None}


# --- 검토 고침(막힌 도면 · 사진 길 · 멱등) -------------------------------------------------


def test_request_that_overlaps_an_already_blocked_drawing_is_refused_with_that_block_text(client, sent, who):
    seed = make_order(3)
    login(client, who.lead)
    assert _post(client, seed.id, [1], seed=seed).status_code == 200
    login(client, who.part)
    res = _post(client, seed.id, [0, 1], seed=seed)                        # 도면 2 는 이미 열린 공장 요청으로 막힘
    assert res.status_code == 409 and code(res) == "REQUEST_BLOCKED" and res.get_json()["error"] == REVISING_MESSAGE
    assert len(_requests(seed.id)) == 1
    assert _post(client, seed.id, [0], seed=seed).status_code == 200      # 대조군: 안 막힌 장만이면 된다


def test_photo_route_refuses_an_order_with_no_drawing_of_mine_but_not_for_blocks(client, sent, who):
    other = mixed_order(2, f2=(0, 1))                                      # 모두 2공장 — 1공장 파트 계정 몫 0장
    login(client, who.part)
    res = _upload(client, other.id)
    assert res.status_code == 403 and code(res) == "REQUEST_FORBIDDEN" and not sent.storage.saved
    mine = make_order(2)
    login(client, who.lead)
    assert _post(client, mine.id, [0, 1], seed=mine).status_code == 200      # 내 공장 도면이 모두 막혀도
    login(client, who.part)
    assert _upload(client, mine.id).status_code == 200                      # 사진 길은 막힘을 보지 않는다(사람 · 공장만)


def test_lead_photo_on_an_order_of_another_factory_only_is_refused(client, sent, who):
    other = mixed_order(2, f2=(0, 1))                                      # 모두 2공장 — 1공장 반장 몫 0장
    login(client, who.lead)
    assert code(_upload(client, other.id)) == "REQUEST_FORBIDDEN" and not sent.storage.saved
    login(client, who.admin)                                               # 대조군: 관리자는 된다
    assert _upload(client, other.id).status_code == 200


def test_photo_route_takes_only_image_files(client, sent, who):
    seed = make_order(2)
    login(client, who.part)
    res = _upload(client, seed.id, name="견적.pdf")
    assert res.status_code == 400 and code(res) == "REQUEST_PHOTOS" and res.get_json()["error"] == "사진을 다시 올려 주세요."
    assert not sent.storage.saved


def test_photo_over_one_mebibyte_passes_the_body_cap(client, sent, who):
    """폰 사진은 1 MiB 를 넘는다 — 몸 상한 목록에 영업 창구 업로드와 같은 줄로 있어야 413 이 아니다."""
    seed = make_order(2)
    login(client, who.part)
    big = io.BytesIO(bytes([0xFF, 0xD8]) + b"0" * (2 * 1024 * 1024))
    res = client.post(PHOTO.format(oid=seed.id), data={"file": (big, "big.jpg")}, content_type="multipart/form-data")
    assert res.status_code == 200, (res.status_code, res.get_data(as_text=True)[:200])


def test_replay_without_the_request_line_is_closed_not_empty(client, sent, who):
    seed = make_order(2)
    login(client, who.lead)
    assert _post(client, seed.id, [0], seed=seed, idem="k-gone").status_code == 200
    order = db_session.get(Order, seed.id)
    order.structured_data = {**order.structured_data, "drawing_fix": {"requests": []}}   # 손으로 지운 자료
    db_session.commit()
    res = _post(client, seed.id, [0], seed=seed, idem="k-gone")
    assert res.status_code == 409 and code(res) == "REQUEST_CLOSED"

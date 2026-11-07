"""FCOMM-01 3단계 겹 2: 프리랜서 주문 단위 판정 계약 (플랜 T15).

설계서 docs/specs/2026-11-06-freelancer-sales-commission_SPEC.md §6.1 · §6.3 겹 2 · §6.5, 검수 원장 A2 · A8 · A9.

* 분류 래칫: 허용 목록의 **모든** endpoint 가 "주문 번호가 어디 실리나"(URL · query · 본문 · 핸들러 · 없음) 중
  하나로 적혀 있다. 허용 endpoint 의 정수 URL 인자는 모두 주문 번호 표 또는 "주문 아님" 표에 있다(url_map 으로 센다).
  음성 대조군: 모집단 안 endpoint 하나를 표에서 빼면 래칫이 잡고, 문지기도 그 문을 지나게 된다.
* URL 주문 번호를 받는 허용 (endpoint, 방법)마다: 내 주문은 문지기를 지나고 실제 요청도 범위 404 가 아니며,
  남의 주문은 범위 404(API · 쓰기 = 404 JSON, 화면 = 404 화면).
* query: 모바일 홈 · 실측 판 ``?focus_order=`` / 모바일 홈 ``?order=`` 남의 주문 404. 내 수수료 ``?order=`` 는 허용(문서화).
* 본문: 올리기 세션(1장 · 여러 장) ``folder``, 마법사 초안 저장 ``order_id`` · 첨부 ``tmp_key``, 등록 ``tmp_key``.
* ``user_can_read_order``: 프리랜서 내 것 / 남의 것, 프리랜서 아닌 직원 · 꺼진 프리랜서는 전역, 협력사 그대로.
  파일 관문 · 채널톡 ``/foms`` 가 같이 바뀐다.
* 담당에서 빠지면(훅이 연결 줄을 지움) 다음 요청부터 404. ``CREATOR`` 줄은 남는다.
* 내가 만든 초안은 연결 줄이 없어도 열린다. 등록된 뒤 · 남이 만든 초안은 아니다.
"""
from __future__ import annotations

import copy
import itertools

import pytest
from flask import g
from sqlalchemy.orm.attributes import flag_modified
from werkzeug.exceptions import NotFound

import foms.api.files.routes as file_routes
import foms.services.auth.freelancer_orders as fl_orders
import foms.services.auth.freelancer_scope as scope
from db import db_session
from foms.services.auth.freelancer_orders import freelancer_can_access_order
from foms.services.auth.freelancer_scope import (
    FREELANCER_ALLOWED_ENDPOINTS,
    FREELANCER_METHOD_LIMITS,
    FREELANCER_ORDER_BODY_CHECKS,
    FREELANCER_ORDER_NOT_FOUND_MSG,
    FREELANCER_ORDER_QUERY_ARGS,
    FREELANCER_ORDER_VIEW_ARGS,
    freelancer_gate,
)
from foms.services.channel_quick_actions import _load_readable_order
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.sales_commission.settings import add_rate, load_settings, save_freelancer
from models import Order, OrderEvent, OrderFreelancerLink, PartnerOrg, User
from tests.domains.test_auth_finance import _login, _make_user

_seq = itertools.count(1)
_RATE = {"effective_month": "2030-01", "lahom_bp": 400, "haud_bp": 600, "personal_bp": 800}

# 허용 endpoint 의 정수 URL 인자 중 주문 번호가 아닌 것(내 알림 state · 공지 — 핸들러가 본인 것만 다룬다).
_NON_ORDER_INT_ARGS: dict[str, set[str]] = {
    "notices_api.ack_notice": {"notice_id"},
    "notices_api.read_notice": {"notice_id"},
    "notices_api.notice_image": {"notice_id", "idx"},
    "notifications.api_notification_ack": {"notification_id"},
    "notifications.api_notification_archive": {"notification_id"},
    "notifications.api_notification_mark_read": {"notification_id"},
    # 첨부 번호 — 핸들러가 (attachment_id, URL order_id) 둘 다로 찾는다(남의 주문 첨부는 없는 것).
    "attachments.api_order_attachments_delete": {"attachment_id"},
    "attachments.api_order_attachments_patch": {"attachment_id"},
}
# 주문 번호를 핸들러가 key 에서 찾아 ``user_can_read_order`` 로 보는 것(파일 관문 3종).
_HANDLER_CHECKED = {"files.view", "files.presigned_urls", "files.download"}
# query 에 주문 번호가 있지만 일부러 열어 둔 것 — 달만 고르고 주문 내용은 내보내지 않는다(문지기 주석 참고).
_QUERY_EXEMPT = {"sales_commission_web.my_commission"}
# 주문 번호를 받지 않는 허용 endpoint(초안 토큰 · 초안 키 · 알림 · 공지 번호는 모두 본인 것만 다룬다).
_NO_ORDER_ID = {
    "static", "favicon", "auth.logout", "auth.switch_back", "auth.profile", "foms_rum.ingest_rum_event",
    "notifications.api_notifications_list", "notifications.api_notifications_badge",
    "notifications.api_notification_mark_read", "notifications.api_notifications_mark_all_read",
    "notifications.api_notification_ack", "notifications.api_notification_archive",
    "notifications.api_notifications_archive_all", "notifications.api_notifications_pending_interrupts",
    "notifications.api_notifications_pending_urgent", "notifications_push.vapid_public_key",
    "notifications_push.subscribe", "notifications_push.push_test", "notifications_push.push_event",
    "notifications_push_state.mobile_state", "notices_web.notice_list", "notices_api.list_notices",
    "notices_api.read_notice", "notices_api.ack_notice", "notices_api.notice_image",
    "erp_dashboard.erp_dashboard_field_calendar", "erp_dashboard.erp_dashboard_field_ops",
    "erp_measurement.api_erp_measurement_summary", "erp_measurement.api_erp_measurement_undated",
    "order_pages.add_order", "erp_orders_structured.api_erp_create_draft",
    "erp_orders_structured.api_erp_draft_autosave", "erp_orders_structured.api_erp_get_draft",
    "erp_orders_structured.api_erp_discard_draft", "erp_order_draft.api_get_order_draft",
    "erp_order_draft.api_delete_order_draft", "erp_order_draft.api_list_order_drafts",
    "erp_order_draft.api_upload_order_draft_attachment", "erp_order_draft_send.api_draft_alimtalk_preview",
    "erp_order_draft_send.api_draft_alimtalk_send", "erp_order_draft_send.api_draft_channel_push_preview",
    "erp_order_draft_send.api_draft_channel_push_send", "address.search",
    "erp_orders_structured.api_parse_order_text", "events.api_change_reason_codes",
    "notifications.api_urgent_targets",
    # 계산기 설정 목록(제품 · 규격 선택지 · 추가 옵션) — 주문 폼 제품 고르기용 읽기, 주문 번호 없음.
    "wdcalculator.api_wdcalculator_get_products", "wdcalculator.api_wdcalculator_get_spec_field_presets",
    "wdcalculator.api_wdcalculator_get_categories",
}


# --------------------------------------------------------------------------
# 시드(가짜 값)
# --------------------------------------------------------------------------
def _freelancer(*, active: bool = True) -> User:
    user = _make_user("STAFF", "SALES")
    user.match_name = f"가짜범위담당{next(_seq)}"
    version, _cfg, _changed = save_freelancer(
        db_session, user.id,
        {"match_name": user.match_name, "start_month": "2030-01", "tax_type": "NONE", "active": active},
        base_version=load_settings(db_session)[0], actor_user_id=None)
    db_session.commit()
    add_rate(db_session, user.id, _RATE, base_version=version, actor_user_id=None)
    db_session.commit()
    return user


def _order(manager: str = "남의담당", *, status: str = "MEASURE", draft: bool = False) -> int:
    sd = {
        "parties": {"manager": {"name": manager}, "orderer": {"name": "라홈"}, "customer": {"name": "범위고객"}},
        "schedule": {"measurement": {"date": "2030-01-05"}},
        "items": [{"product_name": "가짜장", "price": 1_000_000}],
        "workflow": {"stage": "MEASURE"},
    }
    if draft:
        sd["meta"] = {"draft": True}
    order = Order(
        received_date="2030-01-01", customer_name="범위고객", phone="010-0000-0000", address="가짜시",
        product="가짜장", status=status, manager_name=manager, is_erp_order=True, structured_data=sd,
        erp_stage_code="MEASURE", erp_measurement_date="2030-01-05",
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _link(order_id: int, user: User, relation: str = "MANAGER_PRIMARY") -> None:
    db_session.add(OrderFreelancerLink(order_id=order_id, user_id=user.id, relation=relation))
    db_session.commit()


def _links(order_id: int, user: User) -> set[str]:
    rows = db_session.query(OrderFreelancerLink.relation).filter_by(order_id=order_id, user_id=user.id).all()
    return {r for (r,) in rows}


def _client(app, user: User):
    client = app.test_client()
    _login(client, user)
    return client


@pytest.fixture
def world(app):
    fl = _freelancer()
    # 내 주문은 담당 뱃지도 나다 — 저장 훅이 연결 줄을 다시 셀 때(퀘스트 승인 등 실제 저장) 그대로 남는다.
    own, other = _order(manager=fl.match_name), _order()
    if not _links(own, fl):
        _link(own, fl)
    return {"fl": fl, "own": own, "other": other}


def _int_args(rule) -> set[str]:
    return {a for a, c in rule._converters.items() if type(c).__name__ == "IntegerConverter"}


def _allowed_rules(app):
    return [r for r in app.url_map.iter_rules() if r.endpoint in FREELANCER_ALLOWED_ENDPOINTS]


def _methods(rule) -> list[str]:
    limits = FREELANCER_METHOD_LIMITS.get(rule.endpoint)
    return [m for m in sorted(rule.methods - {"HEAD", "OPTIONS"}) if limits is None or m in limits]


def _path(rule, order_id: int) -> str:
    return rule.build({a: order_id for a in rule.arguments}, append_unknown=False)[1]


def _gate(app, user, method, path, json=None):
    """문지기 함수만 부른 결과 — None(통과) · "abort404"(화면 404) · (응답, 상태)."""
    with app.test_request_context(path, method=method, json=json):
        g.current_user = user
        try:
            return freelancer_gate()
        except NotFound:
            return "abort404"


def _is_scope_404(result) -> bool:
    if result == "abort404":
        return True
    if isinstance(result, tuple):
        resp, status = result
        return status == 404 and (resp.get_json(silent=True) or {}).get("error") == FREELANCER_ORDER_NOT_FOUND_MSG
    return False


def _resp_is_scope_404(resp) -> bool:
    if resp.status_code != 404:
        return False
    body = resp.get_json(silent=True)
    return body is None or body.get("error") == FREELANCER_ORDER_NOT_FOUND_MSG


# --------------------------------------------------------------------------
# 분류 래칫
# --------------------------------------------------------------------------
def _unclassified_int_args(app, view_table) -> list[tuple[str, list[str]]]:
    missing = []
    for rule in _allowed_rules(app):
        covered = set(view_table.get(rule.endpoint, ())) | _NON_ORDER_INT_ARGS.get(rule.endpoint, set())
        if _int_args(rule) - covered:
            missing.append((rule.endpoint, sorted(_int_args(rule) - covered)))
    return missing


def test_every_allowlisted_endpoint_is_classified(app):
    """허용 endpoint 마다 주문 번호 자리를 하나로 적는다 — 새로 허용한 endpoint 는 여기서 분류를 요구받는다."""
    classified = (set(FREELANCER_ORDER_VIEW_ARGS) | set(FREELANCER_ORDER_QUERY_ARGS)
                  | set(FREELANCER_ORDER_BODY_CHECKS) | _HANDLER_CHECKED | _QUERY_EXEMPT | _NO_ORDER_ID)
    assert sorted(FREELANCER_ALLOWED_ENDPOINTS - classified) == []
    assert sorted(classified - FREELANCER_ALLOWED_ENDPOINTS) == []
    # 주문 번호를 받는다고 적은 것과 "없음" 으로 적은 것이 겹치지 않는다.
    order_carrying = set(FREELANCER_ORDER_VIEW_ARGS) | set(FREELANCER_ORDER_QUERY_ARGS) | set(FREELANCER_ORDER_BODY_CHECKS)
    assert order_carrying & _NO_ORDER_ID == set()


def test_every_int_url_arg_is_order_or_known_non_order(app):
    assert _unclassified_int_args(app, FREELANCER_ORDER_VIEW_ARGS) == []
    rules = {r.endpoint: r for r in _allowed_rules(app)}
    for endpoint, names in FREELANCER_ORDER_VIEW_ARGS.items():
        assert set(names) <= _int_args(rules[endpoint]), endpoint
    # 음성 대조군(모집단 안): 표에서 하나를 빼면 래칫이 정확히 그것을 잡는다.
    trimmed = {k: v for k, v in FREELANCER_ORDER_VIEW_ARGS.items() if k != "events.api_order_events"}
    assert _unclassified_int_args(app, trimmed) == [("events.api_order_events", ["order_id"])]


# --------------------------------------------------------------------------
# URL 주문 번호 — 허용 (endpoint, 방법) 전수
# --------------------------------------------------------------------------
def _url_order_cases(app):
    return [(rule, method) for rule in _allowed_rules(app) if rule.endpoint in FREELANCER_ORDER_VIEW_ARGS
            for method in _methods(rule)]


def test_url_order_id_gate_own_passes_other_404(app, world):
    fl, own, other = world["fl"], world["own"], world["other"]
    cases = _url_order_cases(app)
    assert {r.endpoint for r, _m in cases} == set(FREELANCER_ORDER_VIEW_ARGS)
    leaks, blocked = [], []
    for rule, method in cases:
        if _gate(app, fl, method, _path(rule, own)) is not None:
            blocked.append((rule.endpoint, method))
        if not _is_scope_404(_gate(app, fl, method, _path(rule, other))):
            leaks.append((rule.endpoint, method))
    assert blocked == []
    assert leaks == []


def test_url_order_id_real_requests(app, world, monkeypatch):
    """실제 요청: 내 주문은 범위 404 가 아니다(핸들러의 보통 검증 오류는 괜찮다). 남의 주문은 404.

    알림톡 보내기 · 채널 확인은 바깥(Solapi)을 부르지 않게 바꿔 둔다(D22 로 연 문)."""
    import foms.api.kakao as kakao_api

    monkeypatch.setattr(kakao_api, "is_configured", lambda *a, **k: True)
    monkeypatch.setattr(kakao_api, "send_alimtalk", lambda *a, **k: {"sent": False, "error": "test_stub"})
    monkeypatch.setattr(kakao_api, "confirm_channel", lambda *a, **k: {"error": "no_history", "checked": False})
    client = _client(app, world["fl"])
    wrong = []
    for rule, method in _url_order_cases(app):
        mine = client.open(_path(rule, world["own"]), method=method, json={} if method != "GET" else None)
        if _resp_is_scope_404(mine) or mine.status_code >= 500:
            wrong.append(("own", rule.endpoint, method, mine.status_code))
        theirs = client.open(_path(rule, world["other"]), method=method, json={} if method != "GET" else None)
        if theirs.status_code != 404:
            wrong.append(("other", rule.endpoint, method, theirs.status_code))
        elif "/api/" in rule.rule or method != "GET":
            assert theirs.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG, rule.endpoint
    assert wrong == []


def test_missing_table_entry_lets_other_order_through(app, world, monkeypatch):
    """음성 대조군: 표에서 빼면 남의 주문이 문지기를 지난다 — 위 전수 시험이 표를 실제로 본다는 증거."""
    trimmed = {k: v for k, v in FREELANCER_ORDER_VIEW_ARGS.items() if k != "events.api_order_events"}
    monkeypatch.setattr(scope, "FREELANCER_ORDER_VIEW_ARGS", trimmed)
    assert _gate(app, world["fl"], "GET", f"/api/orders/{world['other']}/events") is None
    assert _is_scope_404(_gate(app, world["fl"], "GET", f"/api/orders/{world['other']}/field-changes"))


# --------------------------------------------------------------------------
# query 주문 번호
# --------------------------------------------------------------------------
def test_query_order_ids(app, world):
    client = _client(app, world["fl"])
    own, other = world["own"], world["other"]
    assert set(FREELANCER_ORDER_QUERY_ARGS) <= FREELANCER_ALLOWED_ENDPOINTS
    assert client.get(f"/erp/dashboard?focus_order={other}").status_code == 404
    assert client.get(f"/erp/dashboard?focus_order={own}&focus_order={other}").status_code == 404
    assert client.get(f"/erp/dashboard?order={other}").status_code == 404
    assert client.get(f"/erp/measurement?focus_order={other}").status_code == 404
    assert client.get(f"/erp/dashboard?focus_order={own}").status_code == 200
    assert client.get(f"/erp/measurement?focus_order={own}").status_code == 200
    # 정수가 아니거나 0 이면 핸들러도 버린다 — 막지 않는다.
    assert client.get("/erp/dashboard?focus_order=abc&order=0").status_code == 200
    # 일부러 열어 둔 것: 내 수수료 ?order= 는 달만 고른다.
    assert client.get(f"/erp/my-commission?order={other}").status_code == 200


# --------------------------------------------------------------------------
# 본문 주문 번호
# --------------------------------------------------------------------------
def test_body_checks_are_allowlisted(app):
    assert set(FREELANCER_ORDER_BODY_CHECKS) <= FREELANCER_ALLOWED_ENDPOINTS


@pytest.mark.parametrize("path,extra", [
    ("/api/upload/session", {"filename": "x.jpg", "size": 10}),
    ("/api/upload/session/batch", {"files": [{"filename": "x.jpg", "size": 10}]}),
])
def test_upload_session_folder(app, world, path, extra):
    fl, own, other = world["fl"], world["own"], world["other"]
    for folder in (f"orders/{other}/attachments", f" orders/{other}/measurement",
                   f"orders/{own}/../{other}/attachments"):
        assert _is_scope_404(_gate(app, fl, "POST", path, {**extra, "folder": folder})), folder
    assert _gate(app, fl, "POST", path, {**extra, "folder": f"orders/{own}/attachments"}) is None
    resp = _client(app, fl).post(path, json={**extra, "folder": f"orders/{own}/attachments"})
    assert not _resp_is_scope_404(resp) and resp.status_code < 500, resp.status_code
    assert _client(app, fl).post(path, json={**extra, "folder": f"orders/{other}/attachments"}).status_code == 404


def _draft_body(key: str, tmp_key: str | None = None, **extra) -> dict:
    items = [{"product_name": "가짜장", "attachments": [{"tmp_key": tmp_key, "filename": "x.jpg"}]}] if tmp_key else []
    return {"draft_key": key, "step": 1, "payload": {"data": {"items": items}}, **extra}


@pytest.mark.parametrize("method,path", [("PUT", "/api/erp/order-draft"), ("POST", "/api/erp/order-draft/submit")])
def test_wizard_draft_body(app, world, method, path):
    fl, own, other = world["fl"], world["own"], world["other"]
    outsider = _make_user("STAFF", "SALES")
    denied = [
        _draft_body("new.a", f"orders/{other}/attachments/x.jpg"),
        _draft_body("new.a", f"order-drafts/{outsider.id}/new.a/x.jpg"),
        _draft_body("new.a", f"order-drafts/{fl.id}/../{outsider.id}/x.jpg"),
        _draft_body("new.a", "uploads/legacy/x.jpg"),
    ]
    if method == "PUT":
        denied.append(_draft_body("new.a", order_id=other))
        denied.append(_draft_body("new.a", order_id=str(other)))
    for body in denied:
        assert _is_scope_404(_gate(app, fl, method, path, body)), body
    for body in (_draft_body("new.a", f"order-drafts/{fl.id}/new.a/x.jpg"),
                 _draft_body("new.a", f"orders/{own}/attachments/x.jpg"),
                 _draft_body("new.a", order_id=own), _draft_body("new.a")):
        assert _gate(app, fl, method, path, body) is None, body
    resp = _client(app, fl).open(path, method=method, json=_draft_body("new.a", order_id=other))
    assert resp.status_code == 404 and resp.get_json()["error"] == FREELANCER_ORDER_NOT_FOUND_MSG


def test_non_freelancer_body_is_not_checked(app, world):
    """대조군: 프리랜서가 아닌 영업 직원은 남의 주문 폴더도 문지기가 상관하지 않는다."""
    staff = _make_user("STAFF", "SALES")
    body = {"filename": "x.jpg", "size": 10, "folder": f"orders/{world['other']}/attachments"}
    assert _gate(app, staff, "POST", "/api/upload/session", body) is None


# --------------------------------------------------------------------------
# user_can_read_order · 파일 관문 · 채널톡
# --------------------------------------------------------------------------
class _FakeR2Storage:
    storage_type = "r2"

    def get_download_url(self, storage_key, expires_in=3600, response_content_disposition=None):
        return f"https://account.r2.cloudflarestorage.com/{storage_key}?X-Amz-Signature=fake"


def test_read_scope_freelancer_own_only(app, world):
    fl = world["fl"]
    assert user_can_read_order(fl, db_session.get(Order, world["own"])) is True
    assert user_can_read_order(fl, db_session.get(Order, world["other"])) is False
    assert user_can_read_order(fl, None) is False
    off = _freelancer(active=False)
    for user in (_make_user("STAFF", "SALES"), _make_user("STAFF", "CS"), _make_user("ADMIN", None), off):
        assert user_can_read_order(user, db_session.get(Order, world["other"])) is True, user.username


def test_read_scope_partner_unchanged(app, world):
    org = PartnerOrg(name="가짜협력사", is_active=True)
    db_session.add(org)
    db_session.commit()
    partner = User(username=f"fcomm-partner-{next(_seq)}", password="x", role="PARTNER", team=None,
                   name="협력사사람", partner_org_id=org.id, is_active=True)
    db_session.add(partner)
    order = db_session.get(Order, world["other"])
    order.partner_org_id = org.id
    db_session.commit()
    assert user_can_read_order(partner, order) is True
    assert user_can_read_order(partner, db_session.get(Order, world["own"])) is False


def test_file_gate_follows_freelancer_scope(app, world, monkeypatch):
    monkeypatch.setattr(file_routes, "get_storage", lambda: _FakeR2Storage())
    client = _client(app, world["fl"])
    for kind in ("view", "download", "presigned-urls"):
        own = client.get(f"/api/files/{kind}/orders/{world['own']}/attachments/x.jpg")
        assert own.status_code in (200, 302), (kind, own.status_code)
        assert client.get(f"/api/files/{kind}/orders/{world['other']}/attachments/x.jpg").status_code in (403, 404)


def test_channel_quick_action_follows_freelancer_scope(app, world):
    with app.app_context():
        assert _load_readable_order(world["fl"], str(world["own"])) is not None
        assert _load_readable_order(world["fl"], str(world["other"])) is None


# --------------------------------------------------------------------------
# 담당에서 빠짐 · CREATOR · 초안
# --------------------------------------------------------------------------
def _set_manager(order_id: int, name: str) -> None:
    order = db_session.get(Order, order_id)
    sd = copy.deepcopy(order.structured_data)
    sd["parties"]["manager"]["name"] = name
    order.structured_data = sd
    flag_modified(order, "structured_data")
    db_session.commit()


def test_removed_from_badge_revokes_on_next_request_creator_keeps(app):
    fl = _freelancer()
    client = _client(app, fl)
    managed = _order(manager=fl.match_name)
    created = _order(manager=fl.match_name)
    _link(created, fl, "CREATOR")
    assert _links(managed, fl) == {"MANAGER_PRIMARY"}  # 저장 훅이 붙였다
    assert client.get(f"/api/orders/{managed}/structured").status_code == 200
    assert client.get(f"/api/orders/{created}/structured").status_code == 200

    _set_manager(managed, "다른담당")
    _set_manager(created, "다른담당")
    assert _links(managed, fl) == set()
    assert _links(created, fl) == {"CREATOR"}
    assert client.get(f"/api/orders/{managed}/structured").status_code == 404
    assert client.get(f"/erp/orders/{managed}/mobile").status_code == 404
    assert client.get(f"/api/orders/{created}/structured").status_code == 200


def test_own_draft_opens_without_links(app):
    fl = _freelancer()
    client = _client(app, fl)
    resp = client.post("/api/orders/erp/draft", json={"draft_token": f"tok-{next(_seq)}"})
    draft_id = resp.get_json()["order_id"]
    db_session.query(OrderFreelancerLink).filter_by(order_id=draft_id).delete()  # 훅이 못 붙인 경우
    db_session.commit()
    assert client.get(f"/api/orders/{draft_id}/structured").status_code == 200

    # 등록(승격)된 뒤에는 연결 표만 본다.
    db_session.get(Order, draft_id).status = "RECEIVED"
    db_session.commit()
    assert client.get(f"/api/orders/{draft_id}/structured").status_code == 404


def test_draft_rules_seeded(app):
    fl, other_staff = _freelancer(), _make_user("STAFF", "SALES")
    mine = _order(manager="", status="DRAFT", draft=True)
    theirs = _order(manager="", status="DRAFT", draft=True)
    db_session.add_all([
        OrderEvent(order_id=mine, event_type="ORDER_DRAFT_CREATED", payload={}, created_by_user_id=fl.id),
        OrderEvent(order_id=theirs, event_type="ORDER_DRAFT_CREATED", payload={}, created_by_user_id=other_staff.id),
    ])
    db_session.commit()
    assert _links(mine, fl) == set()
    assert freelancer_can_access_order(db_session, fl, mine) is True
    assert freelancer_can_access_order(db_session, fl, theirs) is False
    assert freelancer_can_access_order(db_session, fl, 999_999) is False


def test_access_is_cached_per_request(app, world, monkeypatch):
    calls = []
    real = fl_orders._access_query
    monkeypatch.setattr(fl_orders, "_access_query", lambda db, u, o: calls.append((u, o)) or real(db, u, o))
    with app.test_request_context("/"):
        for _ in range(3):
            assert freelancer_can_access_order(db_session, world["fl"], world["own"]) is True
    assert len(calls) == 1
    freelancer_can_access_order(db_session, world["fl"], world["own"])  # 요청 밖은 저장하지 않는다
    assert len(calls) == 2

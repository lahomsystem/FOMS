"""C9 회귀 — 도면팀이 폰(v2 셸)만으로 수정요청 반영 체크를 하고 수정본을 보낼 수 있다.

배경(원장 `docs/plans/2026-09-29-drawing-defects-verification-ledger.md` C9):
    도면 상세(`/erp/drawing-workbench/<id>`, foms/web/drawing/workbench.py 상세 라우트)는
    v2 코호트면 모바일 표면(`workbench_mobile_handoff.html`, `d-lg-none`)과 PC 표면
    (`.dw-legacy-detail.d-none.d-lg-block`)을 **한 응답에 함께** 싣는다. 폰 폭(<992px)에서는
    PC 표면이 `d-none` 이라 안 보인다.

    수정요청(RETURNED) 상태에서 미체크 요청이 하나라도 있으면 수정본 전달이 막힌다 — 화면
    (workbench.py `transfer_gated_by_revision_checklist`)과 서버(erp_orders_drawing.py
    `perform_drawing_transfer`, 400) 둘 다. 예전에는 막힘을 푸는 "반영 완료" 체크
    (POST /api/orders/<id>/request-revision-check)가 PC 요청사항 칸(`.js-revision-check`)에만 있어
    폰만 쓰는 도면 담당은 영영 막혔다.

고친 방식(새 엔드포인트 없음):
    모바일 대화 스레드의 수정요청 말풍선 안에 반영 체크 버튼을 둔다
    (`data-drawing-handoff-action="revision-check"`, static/js/foms/drawing-handoff.js). 요청
    식별값·본문은 PC 토글과 같은 계약이다. 하단 바의 회색 '전달 대기' 아래에는 막힌 이유 한 줄.

이 파일이 고정하는 것:
    1. 막기 정책 자체는 그대로다(전제 B·C — 미체크면 화면도 서버도 막는다).
    2. 도면팀이 들어오는 세 경로(직접 · 웹푸시 딥링크 · 알림 벨 딥링크) 모두, 폰 폭에서 보이는
       영역에 반영 체크 컨트롤이 있다.
    3. 그 버튼이 싣는 값 그대로 API 를 부르면 체크가 저장되고, 다시 연 화면의 하단 바가
       '수정본 전달' 로 풀리며, 전달 창의 실제 업로드 경로로 올린 수정본을 전달 API 가
       200 으로 받는다(끝까지 한 번 — 합성 key 가 아니라 업로드가 돌려준 key).

왜 문자열 검색이 아니라 파서인가:
    같은 응답에 숨은 PC 마크업(`.js-revision-check`)이 그대로 남아 있어 전체 HTML 검색은 오탐이다.
    그래서 bs4 + html.parser 로 조상 사슬을 따라가 "폰 폭에서 보이는가"를 가른다.
    자신이나 조상에 `d-none` 이 있으면 폰 폭에서 안 보인다(`d-lg-none` 은 폰 폭에서 보인다).

음성 대조:
    같은 응답의 PC 요청사항 칸 `.js-revision-check` 버튼이 탐지기에 걸리고 폰 폭에서는 숨는다는
    것을 먼저 확인한다 — "모바일에 있다"가 탐지기 오탐이 아님을 보인다.

계약 주의:
    test_drawing_mobile_back_to_workbench.py 의 DETAIL_TOP_BLOCKS(=5) — 컨트롤은 새 섹션이 아니라
    기존 대화 스레드의 수정요청 말풍선 안에 있다.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_drawing as drawing_routes
import foms.api.drawing.erp_orders_revision as revision_api
import foms.api.files.order_routes as order_routes
import foms.services.storage as storage_module
from db import db_session
from foms.api.notifications import _resolve_notification_deep_link
from foms.services.datetime_kst import get_today_kst
from foms.services.notifications.push_sender import _deep_link as push_deep_link
from models import Notification, Order, User

DRAWING_KEY = "orders/c9/drawing/plan-1.png"
SALES_NAME = "영업담당C9"
HANDOFF_JS = Path(__file__).resolve().parents[2] / "static/js/foms/drawing-handoff.js"


def _make_user(username: str, *, role: str, team: str, name: str) -> User:
    user = User(
        username=username,
        password=generate_password_hash("pw"),
        role=role,
        team=team,
        name=name,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    return user


def _login(client, who: dict) -> None:
    # 요청 뒤에는 세션이 닫혀 ORM 객체가 분리되므로 원시값(dict)으로 로그인한다.
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _who(user: User) -> dict:
    return {"id": user.id, "username": user.username, "role": user.role}


def _transferred_order(drawing_assignee_id: int) -> Order:
    """1차 전달까지 끝난(TRANSFERRED) 도면 1장 주문. 도면 담당 = drawing_assignee_id."""
    order = Order(
        received_date=get_today_kst().strftime("%Y-%m-%d"),
        customer_name="C9 고객",
        phone="010-0000-0009",
        address="서울 송파구",
        product="붙박이장",
        status="DRAWING",
        manager_name=SALES_NAME,
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "C9 고객"}, "manager": {"name": SALES_NAME}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": "TRANSFERRED",
            "assignments": {"drawing_assignee_user_ids": [drawing_assignee_id]},
            "drawing_current_files": [
                {
                    "key": DRAWING_KEY,
                    "filename": "plan-1.png",
                    "view_url": f"/api/files/view/{DRAWING_KEY}",
                }
            ],
            "drawing_transfer_history": [
                {
                    "action": "TRANSFER",
                    "by_user_id": drawing_assignee_id,
                    "by_user_name": "도면담당C9",
                    "at": "2026-09-20 01:00:00",
                    "note": "1차 전달",
                    "files": [],
                }
            ],
        },
    )
    db_session.add(order)
    db_session.commit()
    return order


class _UploadStorage:
    """전달 창 업로드(POST /api/orders/<id>/attachments)만 받는 스토리지 대역."""

    def upload_file(self, file_obj, filename, folder="uploads"):
        key = f"{folder}/c9_{filename}"
        return {"success": True, "key": key, "url": f"/fake/{key}", "filename": key.rsplit("/", 1)[-1]}

    def get_file_type(self, filename):
        return "image"

    def _generate_thumbnail(self, *a, **k):
        return None


def _hidden_on_phone(tag) -> bool:
    """자신이나 조상에 `d-none`(또는 hidden 속성)이 있으면 폰 폭(<992px)에서 안 보인다."""
    node = tag
    while node is not None and getattr(node, "name", None) not in (None, "[document]"):
        classes = node.get("class") or []
        if "d-none" in classes or node.has_attr("hidden"):
            return True
        node = node.parent
    return False


def _is_revision_check_control(tag) -> bool:
    """request-revision-check 를 부르는 컨트롤(또는 그 식별 data 속성을 든 요소)인가."""
    classes = tag.get("class") or []
    if "js-revision-check" in classes:
        return True
    for name, value in tag.attrs.items():
        text = " ".join(value) if isinstance(value, list) else str(value)
        if "revision-check" in name or "revision-check" in text:
            return True
        if name == "data-request-at":
            return True
    return False


def _landing_url(kind: str, order_id: int) -> str:
    """도면팀이 이 주문 상세에 들어오는 실제 경로 3가지."""
    if kind == "direct":
        return f"/erp/drawing-workbench/{order_id}"
    notif = (
        db_session.query(Notification)
        .filter(Notification.order_id == order_id, Notification.notification_type == "DRAWING_REVISION")
        .one()
    )
    if kind == "push":
        # 웹푸시 알림 탭 → foms/services/notifications/push_sender.py `_deep_link`.
        return push_deep_link(notif)
    # 알림 벨 목록 → foms/api/notifications `_resolve_notification_deep_link`.
    sd = db_session.get(Order, order_id).structured_data
    return _resolve_notification_deep_link(notif, sd)["deep_link_url"]


def _returned_by_sales(client, monkeypatch) -> tuple[dict, dict, int]:
    """영업이 실제 라우트로 수정요청 → RETURNED + review_check 없는 REQUEST_REVISION 1건."""
    # 알림 실시간·웹푸시 발송은 이 흐름과 무관하다(기존 테스트와 같은 차단).
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr(
        revision_api, "enqueue_push_for_notification", lambda *a, **k: None, raising=False
    )
    monkeypatch.setattr(drawing_routes, "emit_erp_notification_to_users", lambda *a, **k: None)

    drafter = _who(_make_user("c9_drafter", role="STAFF", team="DRAWING", name="도면담당C9"))
    sales = _who(_make_user("c9_sales", role="MANAGER", team="SALES", name=SALES_NAME))
    order_id = _transferred_order(drafter["id"]).id

    _login(client, sales)
    res = client.post(
        f"/api/orders/{order_id}/request-revision",
        json={"note": "상부장 높이 2385 → 2290", "target_drawing_keys": [DRAWING_KEY]},
    )
    assert res.status_code == 200, res.get_data(as_text=True)
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert sd["drawing_status"] == "RETURNED"
    revision = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"]
    assert len(revision) == 1 and not (revision[0].get("review_check") or {}).get("checked")
    return drafter, sales, order_id


def _open_on_phone(client, monkeypatch, drafter: dict, url: str):
    _login(client, drafter)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(drafter["id"]))
    response = client.get(url)
    assert response.status_code == 200
    soup = BeautifulSoup(response.get_data(as_text=True), "html.parser")
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None, "v2 모바일 표면(workbench_mobile_handoff.html)이 렌더되지 않았다"
    assert not _hidden_on_phone(handoff)
    return soup, handoff


@pytest.mark.parametrize("landing", ["direct", "push", "bell"])
def test_drawing_team_can_check_revision_on_phone_when_returned(client, monkeypatch, landing):
    """RETURNED + 미체크 요청: 폰 폭에서 보이는 영역에 반영 체크 컨트롤이 있다(세 진입 경로 모두)."""
    drafter, _sales, order_id = _returned_by_sales(client, monkeypatch)

    url = _landing_url(landing, order_id)
    assert url.startswith(f"/erp/drawing-workbench/{order_id}"), url
    soup, handoff = _open_on_phone(client, monkeypatch, drafter, url)

    # 전제 B: 게이트가 모바일에 걸려 있다 — 하단 바 주 버튼이 '전달 대기' + 막힌 이유 한 줄.
    primary = handoff.select_one(".foms-drawing-action-bar .foms-drawing-action-bar__btn--primary")
    assert primary is not None
    assert primary.has_attr("disabled")
    assert "전달 대기" in primary.get_text(" ", strip=True)
    reason = primary.select_one(".foms-drawing-action-bar__reason")
    assert reason is not None, "막힌 이유 한 줄이 없다"
    assert "1건 반영 체크 필요" in reason.get_text(" ", strip=True)

    # 전제 C: 서버도 같은 이유로 막는다 — 막기 정책 자체는 바뀌지 않았다.
    blocked = client.post(f"/api/orders/{order_id}/transfer-drawing", json={"files": []})
    assert blocked.status_code == 400
    assert "반영 완료" in (blocked.get_json() or {}).get("message", "")

    # 음성 대조: 탐지기는 PC 요청사항 칸의 반영 체크 버튼을 찾고, 그 버튼은 폰 폭에서 숨는다.
    all_controls = [t for t in soup.find_all(True) if _is_revision_check_control(t)]
    pc_controls = [t for t in all_controls if t.find_parent(class_="dw-legacy-detail") is not None]
    assert any("js-revision-check" in (t.get("class") or []) for t in pc_controls), (
        "이 사용자에게 PC 반영 체크 버튼이 렌더되지 않았다 — 대조군이 무너졌다"
    )
    assert all(_hidden_on_phone(t) for t in pc_controls)

    # 본 단언: 폰 폭에서 보이는 반영 체크 컨트롤이 수정요청 말풍선 안에 있다.
    phone_controls = [t for t in all_controls if not _hidden_on_phone(t)]
    assert phone_controls, f"폰 폭에서 보이는 반영 체크 컨트롤이 없다 (landing={landing}, url={url})"
    button = handoff.select_one('[data-drawing-handoff-action="revision-check"]')
    assert button is not None and button in phone_controls
    assert button.find_parent(class_="foms-drawing-thread__bubble") is not None
    # PC 인라인 스크립트가 붙잡는 클래스는 모바일 버튼에 없다(핸들러 이중 실행 방지).
    assert "js-revision-check" not in (button.get("class") or [])


def test_phone_check_unblocks_retransfer_end_to_end(client, monkeypatch):
    """폰 버튼이 싣는 값 그대로 체크 → 다시 연 화면이 '수정본 전달' → 실제 전달 200."""
    drafter, _sales, order_id = _returned_by_sales(client, monkeypatch)
    detail_url = f"/erp/drawing-workbench/{order_id}"
    _soup, handoff = _open_on_phone(client, monkeypatch, drafter, detail_url)

    button = handoff.select_one('[data-drawing-handoff-action="revision-check"]')
    assert button is not None
    assert button["data-order-id"] == str(order_id)
    assert button["data-next-checked"] == "true"
    assert "미완료" in button.find_parent(class_="foms-drawing-thread__check").get_text(" ", strip=True)

    # drawing-handoff.js toggleRevisionCheck 가 만드는 본문과 같은 모양으로 부른다.
    by_user_id = button.get("data-by-user-id") or ""
    payload = {
        "request_at": button["data-request-at"],
        "by_user_id": int(by_user_id) if by_user_id else None,
        "checked": button["data-next-checked"] == "true",
    }
    checked = client.post(f"/api/orders/{order_id}/request-revision-check", json=payload)
    assert checked.status_code == 200, checked.get_data(as_text=True)
    assert (checked.get_json() or {}).get("success") is True

    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    review = [h for h in sd["drawing_transfer_history"] if h.get("action") == "REQUEST_REVISION"][0]
    assert review["review_check"]["checked"] is True
    assert review["review_check"]["checked_by_user_id"] == drafter["id"]

    # 다시 연 폰 화면: 막힘이 풀려 '수정본 전달' 이 전달 모달을 연다. 이유 줄은 사라진다.
    _soup, handoff = _open_on_phone(client, monkeypatch, drafter, detail_url)
    primary = handoff.select_one(".foms-drawing-action-bar .foms-drawing-action-bar__btn--primary")
    assert primary is not None and not primary.has_attr("disabled")
    assert "수정본 전달" in primary.get_text(" ", strip=True)
    assert primary.get("data-bs-target") == "#dwTransferModal"
    assert handoff.select_one(".foms-drawing-action-bar__reason") is None
    check_row = handoff.select_one(".foms-drawing-thread__check.is-checked")
    assert check_row is not None and "반영 완료" in check_row.get_text(" ", strip=True)
    undo = check_row.select_one('[data-drawing-handoff-action="revision-check"]')
    assert undo is not None and undo["data-next-checked"] == "false"

    # 실제 전달 모달 흐름(1차 리뷰 R2): 수정본 파일을 전달 창 업로드 경로로 올리고, 그
    # 업로드가 돌려준 key 로 전달 API 를 부른다. 합성 key 를 쓰면 M10(업로드가 전달에서 빠짐)이
    # 가려진다 — 이 흐름은 2c-1(M10) 전까지 400 이었다.
    monkeypatch.setattr(storage_module, "_storage_instance", _UploadStorage())
    monkeypatch.setattr(order_routes, "ASYNC_ATTACHMENT_THUMBNAIL", False)
    uploaded = client.post(
        f"/api/orders/{order_id}/attachments",
        data={"file": (io.BytesIO(b"PNG-v2"), "plan-2.png"), "category": "drawing",
              "note": "[도면 전달 첨부] 수정본"},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200, uploaded.get_data(as_text=True)
    new_key = uploaded.get_json()["attachment"]["storage_key"]
    transferred = client.post(
        f"/api/orders/{order_id}/transfer-drawing",
        json={"files": [{"key": new_key, "filename": "plan-2.png"}], "is_retransfer": True},
    )
    assert transferred.status_code == 200, transferred.get_data(as_text=True)
    db_session.expire_all()
    sd = db_session.get(Order, order_id).structured_data
    assert sd["drawing_status"] == "TRANSFERRED"
    assert [f["key"] for f in sd["drawing_current_files"]] == [new_key]


def test_sales_sees_check_state_but_no_toggle(client, monkeypatch):
    """체크 권한(can_toggle_revision_check = 도면 작업 참여자)이 없는 영업은 상태만 본다."""
    _drafter, sales, order_id = _returned_by_sales(client, monkeypatch)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(sales["id"]))
    _login(client, sales)
    response = client.get(f"/erp/drawing-workbench/{order_id}")
    assert response.status_code == 200
    handoff = BeautifulSoup(response.get_data(as_text=True), "html.parser").select_one(
        ".erp-mobile-shell.foms-drawing-handoff"
    )
    assert handoff is not None
    assert handoff.select_one(".foms-drawing-thread__check") is not None
    assert handoff.select_one('[data-drawing-handoff-action="revision-check"]') is None


def test_handoff_js_sends_the_pc_toggle_contract():
    """모바일 토글 JS 가 PC 토글과 같은 엔드포인트·본문 키를 쓰고, 실패를 삼키지 않는다."""
    source = HANDOFF_JS.read_text(encoding="utf-8")
    assert "'/request-revision-check'" in source
    for needle in ("request_at: requestAt", "by_user_id:", "checked:", "data.success", "catch (err)"):
        assert needle in source, needle
    assert "'revision-check'" in source

"""M12·M11 회귀 — 모바일 도면 상세의 수정요청 참고사진 보기와 '전달 취소' 노출 조건.

원장 `docs/plans/2026-09-29-drawing-defects-verification-ledger.md`:

M12 (모바일 스레드에서 참고사진을 못 연다):
    모바일 대화 스레드의 수정요청 말풍선은 "첨부 N건" 글자뿐이었다. 이제 이미지면 작은 썸네일
    (누르면 GlobalImageViewer), 그 밖의 파일이면 열기 링크를 둔다. URL 은 이력에 저장된
    ``view_url`` 을 쓰지 않는다 — 수정요청 API 가 본문을 검증 없이 저장하므로(원장 M5, 2차)
    ``javascript:`` 나 바깥 주소가 들어올 수 있다. 서버가 key 로 URL 을 만들고, key 는
    ``orders/<이 주문 id>/drawing_gateway/`` 아래 정본 경로만 링크한다(다른 key 는 개수만).
    링크 대상 ``/api/files/view/<key>`` 는 key 의 주문 읽기 권한을 다시 검사한다.

M11 ('전달 취소' 가 서버가 거절하는 상태에서도 보인다):
    서버(cancel-transfer)는 TRANSFERRED 에서만 받는데, 모바일은 CONFIRMED 만 뺐고 PC 는 조건이
    없었다. 권한 플래그 ``can_cancel_transfer``(workbench.py) 한 곳에 상태 조건을 넣어 두 표면이
    같은 값을 본다. 모바일 버튼은 PC 버튼(#btn-cancel-transfer)을 대신 누르므로 둘의 존재가 같아야 한다.

참고: 누락 점검 프로브(저장소 밖 scratchpad/omis/test_omis_probe.py p5·p5b)를 저장소 규약으로 새로 썼다.
"""

from __future__ import annotations

import pytest
from bs4 import BeautifulSoup
from werkzeug.security import generate_password_hash

import foms.api.drawing.erp_orders_revision as revision_api
from db import db_session
from foms.services.datetime_kst import get_today_kst
from foms.web.drawing.workbench import _revision_reference_files
from models import Order, User

SALES_NAME = "영업담당M12"


def _user(username: str, *, role: str, team: str, name: str) -> dict:
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
    return {"id": user.id, "username": user.username, "role": user.role}


def _login(client, who: dict) -> None:
    with client.session_transaction() as sess:
        sess["user_id"] = who["id"]
        sess["username"] = who["username"]
        sess["role"] = who["role"]


def _order(drafter_id: int, *, status: str = "TRANSFERRED", confirmed: bool = False) -> int:
    """도면 1장을 1차 전달한 주문. confirmed=True 면 수령 확정까지 끝난 모양으로 둔다."""
    history = [
        {
            "action": "TRANSFER",
            "by_user_id": drafter_id,
            "by_user_name": "도면담당M12",
            "at": "2026-09-20 01:00:00",
            "note": "1차 전달",
            "files": [],
        }
    ]
    if confirmed:
        history.append({
            "action": "CONFIRM_RECEIPT",
            "by_user_name": SALES_NAME,
            "at": "2026-09-21 01:00:00",
            "files": [{"key": "orders/m12/drawing/plan-1.png", "filename": "plan-1.png"}],
        })
    order = Order(
        received_date=get_today_kst().strftime("%Y-%m-%d"),
        customer_name="M12 고객",
        phone="010-0000-0012",
        address="서울 강동구",
        product="붙박이장",
        status="DRAWING",
        manager_name=SALES_NAME,
        is_erp_order=True,
        structured_data={
            "parties": {"customer": {"name": "M12 고객"}, "manager": {"name": SALES_NAME}},
            "workflow": {"stage": "DRAWING"},
            "drawing_status": status,
            "assignments": {"drawing_assignee_user_ids": [drafter_id]},
            "drawing_current_files": [
                {"key": "orders/m12/drawing/plan-1.png", "filename": "plan-1.png"}
            ],
            "drawing_transfer_history": history,
        },
    )
    db_session.add(order)
    db_session.commit()
    return order.id


def _quiet_notifications(monkeypatch) -> None:
    monkeypatch.setattr(revision_api, "emit_erp_notification_to_users", lambda *a, **k: None)
    monkeypatch.setattr(
        revision_api, "enqueue_push_for_notification", lambda *a, **k: None, raising=False
    )


def _request_revision(client, sales: dict, order_id: int, files: list | None = None) -> None:
    _login(client, sales)
    res = client.post(
        f"/api/orders/{order_id}/request-revision",
        json={"note": "손잡이 위치 변경", "files": files or []},
    )
    assert res.status_code == 200, res.get_data(as_text=True)


def _phone_page(client, monkeypatch, who: dict, order_id: int) -> BeautifulSoup:
    _login(client, who)
    monkeypatch.setenv("ERP_MOBILE_V2_ENABLED", "true")
    monkeypatch.setenv("FOMS_V3_SHELL_COHORT", str(who["id"]))
    response = client.get(f"/erp/drawing-workbench/{order_id}")
    assert response.status_code == 200
    return BeautifulSoup(response.get_data(as_text=True), "html.parser")


def _hidden_on_phone(tag) -> bool:
    node = tag
    while node is not None and getattr(node, "name", None) not in (None, "[document]"):
        if "d-none" in (node.get("class") or []) or node.has_attr("hidden"):
            return True
        node = node.parent
    return False


# --------------------------------------------------------------------------- M12


def test_phone_thread_opens_reference_photos_with_server_built_urls(client, monkeypatch):
    """이 주문 drawing_gateway key 만 썸네일·링크가 되고, 저장된 view_url 과 남의 key 는 안 실린다."""
    _quiet_notifications(monkeypatch)
    drafter = _user("m12_drafter", role="STAFF", team="DRAWING", name="도면담당M12")
    sales = _user("m12_sales", role="MANAGER", team="SALES", name=SALES_NAME)
    oid = _order(drafter["id"])

    ok_img = f"orders/{oid}/drawing_gateway/revisions/20260929_101010_ab12cd34_ref.jpg"
    ok_pdf = f"orders/{oid}/drawing_gateway/revisions/20260929_101011_ef56ab78_spec.pdf"
    foreign = f"orders/{oid + 1}/drawing_gateway/revisions/20260929_101012_00aa11bb_other.jpg"
    traversal = f"orders/{oid}/drawing_gateway/../measurement/secret.jpg"
    measurement = f"orders/{oid}/measurement/20260929_101013_22cc33dd_site.jpg"
    files = [
        # 수정요청 API 는 이 값을 검증 없이 저장한다(M5) — 화면은 이 URL 을 쓰면 안 된다.
        {"key": ok_img, "filename": "ref.jpg",
         "view_url": "javascript:alert(1)", "download_url": "https://evil.example/steal"},
        {"key": ok_pdf, "filename": "spec.pdf"},
        {"key": foreign, "filename": "other.jpg", "view_url": f"/api/files/view/{foreign}"},
        {"key": traversal, "filename": "secret.jpg", "view_url": f"/api/files/view/{traversal}"},
        {"key": measurement, "filename": "site.jpg", "view_url": f"/api/files/view/{measurement}"},
    ]
    _request_revision(client, sales, oid, files)

    soup = _phone_page(client, monkeypatch, drafter, oid)
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    assert handoff is not None and not _hidden_on_phone(handoff)

    thumbs = handoff.select('[data-drawing-handoff-open="reference"]')
    assert len(thumbs) == 1, [str(t) for t in thumbs]
    thumb = thumbs[0]
    assert thumb["data-handoff-view-url"] == f"/api/files/view/{ok_img}"
    assert thumb["data-handoff-download-url"] == f"/api/files/download/{ok_img}"
    assert thumb.select_one("img")["src"] == f"/api/files/view/{ok_img}"
    group = thumb.find_parent(attrs={"data-handoff-ref-group": True})
    assert group is not None
    bubble = group.find_parent(class_="foms-drawing-thread__bubble")
    assert bubble is not None and "수정 요청" in bubble.get_text(" ", strip=True)
    assert not _hidden_on_phone(thumb)

    file_link = handoff.select_one("a.foms-drawing-thread__ref--file")
    assert file_link is not None
    assert file_link["href"] == f"/api/files/view/{ok_pdf}"
    assert file_link.get("target") == "_blank" and "noopener" in (file_link.get("rel") or [])

    mobile_markup = str(handoff)
    for leaked in (foreign, traversal, measurement, "javascript:", "evil.example"):
        assert leaked not in mobile_markup, f"모바일 표면에 실리면 안 되는 값이 있다: {leaked}"
    count = bubble.find("small", string=lambda s: bool(s) and "첨부" in s)
    assert count is not None and "첨부 5건" in count.get_text() and "3건은 여기서 열 수 없음" in count.get_text()

    # 링크 대상 라우트가 이 key 를 이 사용자에게 허용한다(권한 403·경로 400 이 아님).
    viewed = client.get(f"/api/files/view/{ok_img}")
    assert viewed.status_code not in (400, 403), viewed.get_data(as_text=True)


def test_revision_reference_files_accepts_only_this_orders_gateway_keys():
    """판정 헬퍼 단위 — 정규화·안전 문자·주문 일치·drawing_gateway 접두를 모두 통과해야 링크한다."""
    good = "orders/7/drawing_gateway/revisions/20260929_101010_ab12cd34_ref.png"
    rows, hidden = _revision_reference_files(7, [
        {"key": good},
        {"key": f" {good}"},                                          # 앞뒤 공백
        {"key": "orders/7/drawing_gateway//revisions/x.png"},          # 비정규 경로
        {"key": "orders/7/drawing_gateway/revisions/한글.png"},         # 안전 문자 밖
        {"key": "orders/8/drawing_gateway/revisions/x.png"},           # 다른 주문
        {"key": "orders/7/drawing/x.png"},                             # 도면 창구 밖
        {"key": None},
        "orders/7/drawing_gateway/revisions/raw-string.png",           # dict 가 아님
    ])
    assert [r["key"] for r in rows] == [good]
    assert rows[0] == {
        "key": good,
        "filename": "20260929_101010_ab12cd34_ref.png",
        "view_url": f"/api/files/view/{good}",
        "download_url": f"/api/files/download/{good}",
        "is_image": True,
    }
    assert hidden == 7
    assert _revision_reference_files(None, [{"key": good}]) == ([], 1)
    assert _revision_reference_files(7, None) == ([], 0)


# --------------------------------------------------------------------------- M11


@pytest.mark.parametrize("state", ["TRANSFERRED", "RETURNED", "CONFIRMED"])
def test_cancel_transfer_button_only_when_server_accepts(client, monkeypatch, state):
    """'전달 취소' 는 TRANSFERRED 에서만 PC·모바일 둘 다에 보이고, 그 밖의 상태는 서버도 400 이다."""
    _quiet_notifications(monkeypatch)
    drafter = _user("m11_drafter", role="STAFF", team="DRAWING", name="도면담당M12")
    sales = _user("m11_sales", role="MANAGER", team="SALES", name=SALES_NAME)
    if state == "CONFIRMED":
        oid = _order(drafter["id"], status="CONFIRMED", confirmed=True)
    else:
        oid = _order(drafter["id"])
    if state == "RETURNED":
        _request_revision(client, sales, oid)  # 실제 라우트로 RETURNED 를 만든다

    db_session.expire_all()
    assert db_session.get(Order, oid).structured_data["drawing_status"] == state

    soup = _phone_page(client, monkeypatch, drafter, oid)
    handoff = soup.select_one(".erp-mobile-shell.foms-drawing-handoff")
    pc = soup.select_one(".dw-legacy-detail")
    assert handoff is not None and pc is not None
    mobile_cancel = handoff.select_one('.foms-drawing-action-bar [data-drawing-handoff-action="cancel"]')
    pc_cancel = pc.select_one("#btn-cancel-transfer")
    # 모바일 버튼은 PC 버튼을 대신 누른다 — 둘의 존재가 같아야 한다.
    assert (mobile_cancel is None) == (pc_cancel is None)

    if state == "TRANSFERRED":
        # 대조군: 서버가 받는 상태에서는 도면 담당에게 보인다(탐지기가 버튼을 찾을 수 있다).
        assert mobile_cancel is not None, "TRANSFERRED 인데 모바일 '전달 취소' 가 없다"
        return

    assert mobile_cancel is None, f"{state} 모바일 바에 서버가 거절하는 '전달 취소' 가 있다"
    refused = client.post(f"/api/orders/{oid}/cancel-transfer", json={})
    assert refused.status_code == 400
    assert "TRANSFERRED" in (refused.get_json() or {}).get("message", "")

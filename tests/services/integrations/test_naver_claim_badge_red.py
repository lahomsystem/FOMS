"""취소·반품 배지는 **끝난 건도 빨강**이다 (2026-09-03 사용자 지시).

이력 탭 상태 칸이 `취소 완료 09-02` 를 회색(`wb-st__b--slate`)으로 식혔다. 그 회색이
"이 집은 평범하다"로 읽혀, 담당자가 목록을 훑을 때 취소된 집을 그냥 지나쳤다.

색 축은 **단계가 아니라 돈의 축**이다(`claim_money_back` = `is_money_back_claim`):

* 요청 · 처리중 · 완료 → 빨강. 끝났다는 것이 "안 중요해졌다"는 뜻이 아니다.
* 거부 → 빨강이 아니다. 주문도 결제도 살아 있다(R-8, 2026-08-28
  `test_naver_claim_reject_display`). 이 파일은 그 계약을 **뒤집지 않는다**.

같은 축을 쓰는 자리가 넷이라(이력 상태 칸 · 처리 목록 집 배지 · 상세 pane 상품주문 표 ·
이력 상세) 판정을 서버가 한 번 하고 화면은 클래스만 고른다.
"""

from __future__ import annotations

import pathlib

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.promotion import summarize_snapshot
from models import ExternalOrderLink, User

WORKBENCH_TEMPLATE = pathlib.Path("templates/admin/naver_workbench.html")

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return f"red{_SEQ[0]}"


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 연다 — 화면이 열려야 배지를 볼 수 있다."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client) -> User:
    user = User(username=f"red_admin_{_uid()}", password=generate_password_hash("pw"),
                role="ADMIN", team="CS", name="관리자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _link(status: str) -> ExternalOrderLink:
    external_id = f"PO-RED-{_uid()}"
    order_no = f"N-RED-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no},
        "productOrder": {"productOrderId": external_id, "productName": "붙박이장",
                         "claimStatus": status, "placeOrderStatus": "OK",
                         "shippingAddress": {"name": "이수취", "tel1": "010-4444-5555",
                                             "baseAddress": "서울 강남구 1",
                                             "detailedAddress": "101호"}},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot), sync_status="COLLECTED",
                             place_order_status="OK")
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 1. 판정은 서버가 한 번 — 요약이 색 축을 직접 들고 있다
# --------------------------------------------------------------------------- #

def test_summary_carries_the_money_axis_not_just_the_blocking_axis(app):
    """``claim_money_back`` 은 진행 여부가 아니라 돈이 되돌아가는가를 말한다."""
    done = summarize_snapshot(_link("CANCEL_DONE").raw_snapshot)
    rejected = summarize_snapshot(_link("CANCEL_REJECT").raw_snapshot)
    clean = summarize_snapshot(_link("").raw_snapshot)

    assert done["claim_money_back"] is True
    assert rejected["claim_money_back"] is False
    assert clean["claim_money_back"] is False


# --------------------------------------------------------------------------- #
# 2. 이력 탭 상태 칸 — 끝난 취소가 회색이 아니다
# --------------------------------------------------------------------------- #

def test_history_status_paints_a_finished_cancel_red(app, client, workbench_on):
    """`취소 완료` 배지가 ``wb-st__b--red`` 로 온다(예전에는 ``--slate``)."""
    _login(client)
    _link("CANCEL_DONE")

    body = client.get("/admin/naver-ingest/triage?tab=all").get_data(as_text=True)

    assert 'wb-st__b--red">취소 완료' in body
    assert 'wb-st__b--slate">취소 완료' not in body


def test_history_status_keeps_a_rejected_claim_out_of_red(app, client, workbench_on):
    """**음성 대조군** — 거부는 여전히 빨강이 아니다(R-8 을 뒤집지 않는다)."""
    _login(client)
    _link("RETURN_REJECT")

    body = client.get("/admin/naver-ingest/triage?tab=all").get_data(as_text=True)

    assert 'wb-st__b--red">반품 거부' not in body
    assert "반품 거부" in body, "사실이 사라졌다"


# --------------------------------------------------------------------------- #
# 3. 처리 탭 목록 — 끝난 취소가 회색 배지로 남지 않는다
# --------------------------------------------------------------------------- #

def test_work_list_badge_is_red_for_a_finished_cancel(app, client, workbench_on):
    """집 배지도 같은 축을 쓴다 — `bg-secondary` 로 식히지 않는다."""
    _login(client)
    _link("CANCEL_DONE")

    body = client.get("/admin/naver-ingest/triage?tab=work").get_data(as_text=True)

    assert 'bg-danger">취소 완료' in body
    assert 'bg-secondary">취소 완료' not in body


# --------------------------------------------------------------------------- #
# 4. 화면은 클래스만 고른다 — 판정 사슬을 템플릿에 두지 않는다
# --------------------------------------------------------------------------- #

def test_template_reads_the_server_axis_instead_of_rebuilding_the_chain(app):
    """템플릿의 색 분기는 ``claim_money_back`` 한 값만 본다(단계 사슬 부활 금지)."""
    markup = WORKBENCH_TEMPLATE.read_text(encoding="utf-8")

    assert "row.claim_money_back" in markup
    assert "group.claim_money_back" in markup
    # 예전 사슬(단계별 색 표)이 되살아나면 도크·처리 탭과 판정이 두 벌이 된다.
    assert "'done': 'slate'" not in markup

"""재결제 뒤 **정리 안 된 옛 네이버 주문** 띠·일괄 다시 읽기 계약 테스트 (NVREPAY-02).

**왜 필요한가**: 옛 주문의 살아 있음은 지금까지 그 주문 pane 을 연 사람에게만 보였다
(`order_candidates.origin_facts`). 그런데 옛 주문을 취소·반품하지 않으면 고객은 같은
물건값을 두 번 낸 상태로 남고 옛 주문은 네이버에서 정산·발송이 그대로 돈다 — 아무도
pane 을 안 열면 아무도 모르는 사실이었다. 이 파일은 그 수가 목록 화면에 항상 있고,
모집단 전체를 한 번에 다시 읽을 수 있고, **화면이 보낸 목록을 서버가 믿지 않는다**는
세 가지를 문다.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from werkzeug.security import generate_password_hash

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import group_key_text
from foms.services.integrations.naver_commerce.order_candidates import (
    pending_origin_cleanup,
)
from models import ExternalOrderLink, Order, User

TRIAGE_PATH = "/admin/naver-ingest/triage"
REFRESH_PATH = "/admin/naver-ingest/origin-cleanup/refresh"
REPO_ROOT = Path(__file__).resolve().parents[3]
TEMPLATE_PATH = REPO_ROOT / "templates" / "admin" / "naver_workbench.html"

_SEQ = [0]


def _uid() -> str:
    _SEQ[0] += 1
    return str(_SEQ[0])


@pytest.fixture()
def workbench_on(monkeypatch):
    """워크벤치 게이트를 켠다(전역 on + 코호트 all)."""
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_WORKBENCH_COHORT", "all")
    yield


def _login(client, *, role: str = "ADMIN") -> User:
    user = User(username=f"nvorig_{role.lower()}_{_uid()}",
                password=generate_password_hash("pw"), role=role, team="CS",
                name=f"{role} 사용자", is_active=True)
    db_session.add(user)
    db_session.commit()
    with client.session_transaction() as sess:
        sess["user_id"] = user.id
        sess["username"] = user.username
        sess["role"] = user.role
    return user


def _order(*, name: str = "정리대상") -> Order:
    order = Order(received_date="2026-08-01", customer_name=name, phone="010-3333-4444",
                  address="서울 강남구 1 101호", product="붙박이장", status="RECEIVED")
    db_session.add(order)
    db_session.commit()
    return order


def _link(*, order_no: str, order_id: int, relation: str, claim_status: str = "",
          amount: int = 500000, send_date: str = "",
          refreshed_at: str = "", collected_at: str = "") -> ExternalOrderLink:
    """붙어 있는 수집 링크 1건.

    Args:
        order_no: 네이버 주문번호(집 키).
        order_id: 붙은 FOMS 주문 id.
        relation: ``NEW``/``ADDON``/``REPAY``.
        claim_status: 클레임 상태 원문(빈 값이면 클레임 없음 = 살아 있음).
        amount: 결제 금액.
        send_date: 있으면 발송 처리된 집으로 본다(반품 갈래).
        refreshed_at: 마지막으로 다시 읽은 시각(ISO). 없으면 수집 시각이 기준이 된다.
        collected_at: 이 링크를 **수집한** 시각(ISO). 비우면 지금(``created_at`` 기본값).
            ``order_candidates._dispatch_view`` 의 ``read_at`` 은
            ``max(refreshed_at, created_at)`` 이라, "언제 읽었나"를 시험하려면 수집 시각도
            함께 과거로 못 박아야 한다. 안 그러면 두 링크의 ``created_at`` 이 같은 1ms
            눈금에 떨어질 때만 판정이 뒤집혀 간헐 실패가 된다.

    Returns:
        저장된 링크.
    """
    external_id = f"PO-ORIG-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": "김주문",
                  "ordererTel": "010-1111-2222"},
        "productOrder": {
            "productOrderId": external_id, "productName": "붙박이장",
            "totalPaymentAmount": amount,
            "claimStatus": claim_status or None,
            "claimType": "CANCEL" if claim_status else None,
        },
    }
    if send_date:
        snapshot["delivery"] = {"deliveryStatus": "DELIVERING", "sendDate": send_date}
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             sync_status="LINKED", external_order_no=order_no,
                             raw_snapshot=snapshot, group_key=group_key_text(snapshot),
                             relation=relation, order_id=order_id,
                             triage_state={"claim_sync": {"refreshed_at": refreshed_at}}
                             if refreshed_at else None)
    if collected_at:
        link.created_at = datetime.fromisoformat(collected_at)
    db_session.add(link)
    db_session.commit()
    return link


# --------------------------------------------------------------------------- #
# 판정 — 모집단은 '재결제가 붙은 주문의 살아 있는 NEW 집' 뿐이다
# --------------------------------------------------------------------------- #

def test_alive_new_origin_is_counted(app):
    """재결제를 붙였는데 옛 NEW 집이 살아 있으면 정리 대기다."""
    order = _order()
    _link(order_no=f"N-ORIG-A-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-A-{_uid()}", order_id=int(order.id), relation="REPAY")

    result = pending_origin_cleanup(db_session)

    mine = [row for row in result["rows"] if row["order_id"] == int(order.id)]
    assert len(mine) == 1, "옛 집 1개가 정리 대기로 잡혀야 한다"
    assert mine[0]["dispatched"] is False, "발송 전이면 취소 갈래"


def test_canceled_origin_is_not_counted(app):
    """고객이 이미 취소한 옛 집은 할 일이 아니다."""
    order = _order()
    _link(order_no=f"N-ORIG-B-{_uid()}", order_id=int(order.id), relation="NEW",
          claim_status="CANCEL_DONE")
    _link(order_no=f"N-REPAY-B-{_uid()}", order_id=int(order.id), relation="REPAY")

    result = pending_origin_cleanup(db_session)

    assert [row for row in result["rows"] if row["order_id"] == int(order.id)] == []


def test_addon_household_is_not_an_origin(app):
    """추가결제는 **대체된 옛 주문이 아니다** — 운영 #4854 가 이 자리에서 잘못 지목됐다."""
    order = _order()
    _link(order_no=f"N-ADDON-C-{_uid()}", order_id=int(order.id), relation="ADDON")
    _link(order_no=f"N-REPAY-C-{_uid()}", order_id=int(order.id), relation="REPAY")

    result = pending_origin_cleanup(db_session)

    assert [row for row in result["rows"] if row["order_id"] == int(order.id)] == []


def test_order_without_repay_is_not_counted(app):
    """재결제가 안 붙은 주문은 이 띠의 모집단이 아니다(음성 대조군)."""
    order = _order()
    _link(order_no=f"N-ORIG-D-{_uid()}", order_id=int(order.id), relation="NEW")

    result = pending_origin_cleanup(db_session)

    assert [row for row in result["rows"] if row["order_id"] == int(order.id)] == []


def test_dispatched_origin_takes_the_return_branch(app):
    """발송 뒤에는 취소가 아니라 반품이다 — 화면이 갈래를 이 값으로 고른다."""
    order = _order()
    _link(order_no=f"N-ORIG-E-{_uid()}", order_id=int(order.id), relation="NEW",
          send_date="2026-08-20T10:00:00.000+09:00")
    _link(order_no=f"N-REPAY-E-{_uid()}", order_id=int(order.id), relation="REPAY")

    result = pending_origin_cleanup(db_session)

    mine = [row for row in result["rows"] if row["order_id"] == int(order.id)]
    assert mine and mine[0]["dispatched"] is True


def test_origin_read_before_new_payment_is_stale(app):
    """새 결제를 받은 뒤로 옛 집을 안 읽었으면 ``stale`` 이다.

    이 구간이 "고객이 스스로 취소했는데 우리가 또 취소를 거는" 위험이 사는 자리다.
    """
    order = _order()
    _link(order_no=f"N-ORIG-F-{_uid()}", order_id=int(order.id), relation="NEW",
          refreshed_at="2026-08-01T00:00:00", collected_at="2026-08-01T00:00:00")
    _link(order_no=f"N-REPAY-F-{_uid()}", order_id=int(order.id), relation="REPAY",
          refreshed_at="2026-08-27T00:00:00", collected_at="2026-08-27T00:00:00")

    result = pending_origin_cleanup(db_session)

    mine = [row for row in result["rows"] if row["order_id"] == int(order.id)]
    assert mine and mine[0]["stale"] is True


# --------------------------------------------------------------------------- #
# 화면 — 목록에 수가 있어야 한다(pane 을 안 열어도 보인다)
# --------------------------------------------------------------------------- #

def test_workbench_strip_shows_pending_origin(client, workbench_on):
    """처리 탭에 정리 대기 띠와 일괄 버튼이 뜬다."""
    _login(client)
    order = _order(name="띠대상")
    _link(order_no=f"N-ORIG-G-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-G-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert "재결제 뒤 정리 안 된 옛 네이버 주문" in body
    assert 'id="wb-origin-refresh-all"' in body
    assert "data-wb-origin-cleanup=" in body


def test_history_tab_does_not_show_the_strip(client, workbench_on):
    """이력 탭은 지난 기록을 보는 자리라 할 일을 띄우지 않는다(유령 띠와 같은 규율)."""
    _login(client)
    order = _order()
    _link(order_no=f"N-ORIG-H-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-H-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "all"}).get_data(as_text=True)

    assert "재결제 뒤 정리 안 된 옛 네이버 주문" not in body


def test_strip_sends_people_to_the_old_household_pane(client, workbench_on):
    """띠는 옛 집 pane 으로 가는 길을 **계속 낸다**.

    2026-09-01 에 띠에서 바로 쏘는 버튼이 생겼지만 pane 링크를 걷어내지 않았다 — 띠가
    보여주는 것은 주문번호·건수·금액·발송여부까지고, 클레임 상태·보류·형제 건은 pane 에만
    있다. 맥락을 더 보고 싶은 사람의 길을 없애지 않는다.
    """
    _login(client)
    order = _order()
    origin = _link(order_no=f"N-ORIG-I-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-I-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert f"link_id={origin.id}" in body


# --------------------------------------------------------------------------- #
# 띠에서 바로 쏘기 (2026-09-01 사용자 결정) — 불가역이라 조건을 못 박는다
# --------------------------------------------------------------------------- #

def test_strip_offers_cancel_before_dispatch(client, workbench_on):
    """발송 전이면 띠 줄이 **취소** 버튼을 낸다 — 갈래는 ``dispatched`` 가 고른다."""
    _login(client)
    order = _order(name="띠취소")
    origin = _link(order_no=f"N-ORIG-J-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-J-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert "wb-origin-act" in body
    assert f'data-link-id="{origin.id}"' in body
    assert 'data-kind="cancel"' in body


def test_strip_offers_return_after_dispatch(client, workbench_on):
    """발송 뒤에는 **반품 접수**다 — 취소를 보내면 네이버가 거절한다."""
    _login(client)
    order = _order(name="띠반품")
    _link(order_no=f"N-ORIG-K-{_uid()}", order_id=int(order.id), relation="NEW",
          send_date="2026-08-20T10:00:00.000+09:00")
    _link(order_no=f"N-REPAY-K-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'data-kind="return"' in body
    assert "반품 접수" in body


def test_stale_row_is_marked_so_the_screen_can_refuse(client, workbench_on):
    """낡은 줄은 **표식이 붙는다** — 그 값 위에서 불가역을 쏘지 않는다.

    ``stale`` 은 "새 결제를 받은 뒤로 이 옛 주문을 한 번도 안 읽었다"는 뜻이다. 그 사이
    고객이 스스로 취소했을 수 있어, 화면은 모달을 열지 않고 다시 읽기부터 건다.
    """
    _login(client)
    order = _order(name="띠낡음")
    _link(order_no=f"N-ORIG-L-{_uid()}", order_id=int(order.id), relation="NEW",
          refreshed_at="2026-08-01T00:00:00", collected_at="2026-08-01T00:00:00")
    _link(order_no=f"N-REPAY-L-{_uid()}", order_id=int(order.id), relation="REPAY",
          refreshed_at="2026-08-27T00:00:00", collected_at="2026-08-27T00:00:00")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'data-stale="1"' in body


def test_strip_modals_carry_the_irreversible_four(client, workbench_on):
    """띠 모달이 불가역 4종 세트를 진다 — pane 보다 보여주는 것이 적어서 더 그렇다."""
    _login(client)
    order = _order(name="띠모달")
    _link(order_no=f"N-ORIG-M-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-M-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    assert 'id="wb-modal-origin-cancel"' in body
    assert 'id="wb-modal-origin-return"' in body
    assert "되돌릴 수 없습니다" in body
    # 재진술 자리와 필요한 입력(사유). 값은 JS 가 눌린 줄에서 옮겨 적는다.
    assert 'id="wb-origin-cancel-who"' in body
    assert 'id="wb-origin-cancel-reason"' in body
    assert 'id="wb-origin-return-reason"' in body
    # 사유 목록은 **서버 화이트리스트가 정본**이다 — 화면이 따로 목록을 들면 둘이 갈리고,
    # 목록 밖 코드는 네이버 400 이다(되돌릴 수 없는 경로라 받아 보고 배우지 않는다).
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_REASONS,
        RETURN_REASONS,
    )

    cancel_block = body.split('id="wb-origin-cancel-reason"')[1].split("</select>")[0]
    for code in CANCEL_REASONS:
        assert f'value="{code}"' in cancel_block, code
    return_block = body.split('id="wb-origin-return-reason"')[1].split("</select>")[0]
    assert {c for c in RETURN_REASONS} == {
        part.split('"')[0] for part in return_block.split('value="')[1:] if part.split('"')[0]
    }, "반품 사유는 취소와 다른 목록이다"


def test_strip_return_modal_offers_approve_but_leaves_it_off(client, workbench_on):
    """승인 체크는 있되 **기본은 꺼짐**이다 — 켜면 환불이 확정되고 무를 API 가 없다."""
    _login(client)
    order = _order(name="띠승인")
    _link(order_no=f"N-ORIG-N-{_uid()}", order_id=int(order.id), relation="NEW",
          send_date="2026-08-20T10:00:00.000+09:00")
    _link(order_no=f"N-REPAY-N-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    box = body.split('id="wb-origin-return-approve"')[1].split(">")[0]
    assert "checked" not in box, "승인 체크가 기본으로 켜져 있다"
    assert "환불이 확정됩니다" in body


def test_strip_ids_do_not_collide_with_the_pane(client, workbench_on):
    """띠 모달 id 는 pane 과 겹치지 않는다 — 겹치면 어느 입력을 읽는지 갈린다."""
    _login(client)
    order = _order(name="띠아이디")
    _link(order_no=f"N-ORIG-O-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-O-{_uid()}", order_id=int(order.id), relation="REPAY")

    body = client.get(TRIAGE_PATH, query_string={"tab": "work"}).get_data(as_text=True)

    for element_id in ("wb-origin-cancel-reason", "wb-origin-return-reason",
                       "wb-origin-return-approve", "wb-modal-origin-cancel",
                       "wb-modal-origin-return"):
        assert body.count(f'id="{element_id}"') == 1, element_id


# --------------------------------------------------------------------------- #
# 일괄 다시 읽기 — 서버가 대상을 다시 센다
# --------------------------------------------------------------------------- #

def test_bulk_refresh_ignores_the_client_link_list(client, workbench_on, monkeypatch):
    """화면이 보낸 link_id 를 쓰지 않는다 — 남의 집을 읽게 할 수 있는 자리다."""
    _login(client)
    order = _order()
    origin = _link(order_no=f"N-ORIG-J-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-J-{_uid()}", order_id=int(order.id), relation="REPAY")
    other = _link(order_no=f"N-OTHER-J-{_uid()}", order_id=int(_order().id), relation="NEW")
    origin_id, other_id = int(origin.id), int(other.id)

    seen: list[int] = []
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda link_id, user_id=None: seen.append(int(link_id)) or True)

    response = client.post(REFRESH_PATH, json={"link_ids": [other_id]})

    assert response.status_code == 200
    assert other_id not in seen, "화면이 시킨 집을 읽으면 안 된다"
    assert origin_id in seen, "서버가 다시 센 집만 읽는다"


def test_bulk_refresh_reports_queue_outage(client, workbench_on, monkeypatch):
    """큐가 막혀 하나도 못 넣으면 성공이라고 말하지 않는다(503)."""
    _login(client)
    order = _order()
    _link(order_no=f"N-ORIG-K-{_uid()}", order_id=int(order.id), relation="NEW")
    _link(order_no=f"N-REPAY-K-{_uid()}", order_id=int(order.id), relation="REPAY")

    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda link_id, user_id=None: False)

    response = client.post(REFRESH_PATH, json={})

    assert response.status_code == 503
    assert response.get_json()["success"] is False


def test_bulk_refresh_is_quiet_when_nothing_pending(client, workbench_on, monkeypatch):
    """정리할 집이 없으면 큐를 건드리지 않는다(빈 호출로 네이버를 두드리지 않는다)."""
    _login(client)
    called: list[int] = []
    monkeypatch.setattr("foms.services.jobs.queue.enqueue_naver_refresh",
                        lambda link_id, user_id=None: called.append(int(link_id)) or True)

    response = client.post(REFRESH_PATH, json={})

    assert response.status_code == 200
    assert response.get_json()["data"]["queued"] == 0
    assert called == []


# --------------------------------------------------------------------------- #
# 계약 등재 — 신규 mutation 라우트 4종
# --------------------------------------------------------------------------- #

def test_route_is_registered_in_both_manifests():
    """write guard·mutation policy 매니페스트 **둘 다** 등재돼야 한다(별개 파일)."""
    endpoint = "admin.naver_ingest_origin_cleanup_refresh"
    guard = json.loads((REPO_ROOT / "docs" / "harness"
                        / "foms_write_guard_manifest.json").read_text(encoding="utf-8"))
    policy = json.loads((REPO_ROOT / "docs" / "harness"
                         / "foms_order_mutation_policy_manifest.json").read_text(encoding="utf-8"))

    assert endpoint in json.dumps(guard), "write guard 매니페스트 누락"
    assert endpoint in json.dumps(policy), "mutation policy 매니페스트 누락"


def test_audit_action_has_a_korean_label():
    """새 감사 action 은 한글 업무 라벨이 있어야 한다(없으면 감사 화면에 영문 코드)."""
    from foms.services.audit_message_display import ACTION_LABELS

    assert ACTION_LABELS.get("NAVER_ORIGIN_CLEANUP_REFRESH_ENQUEUE")


def test_template_pins_moved_together():
    """CSS·JS 를 고쳤으면 ``?v`` 핀이 함께 움직인다(SW staticCacheFirst)."""
    markup = TEMPLATE_PATH.read_text(encoding="utf-8")

    assert markup.count("?v=20260901d") == 2

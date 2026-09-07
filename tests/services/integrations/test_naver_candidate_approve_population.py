"""옛 결제 승인 — **화면 대상 == 서버 대상** 계약 테스트 (CEO FIX 2026-09-07).

승인은 되돌릴 수 없다. 승인 시점에 환불이 확정되고, 취소 승인에는 거절 API 가 아예
없다(철회는 구매자만 한다). 그래서 이 파일이 지키는 문장은 하나뿐이다:

    **서버가 실제로 보낼 목록**(:func:`fulfillment.links_of_group` + 서버 술어)과
    **화면이 재진술한 목록**(후보 행의 ``naver_*_approve_groups[*]["targets"]``)이
    글자 그대로 같다.

세 장면은 전부 **모집단이 갈리는 자리**다 — 화면을 만드는 쪽이 *이 후보 주문에 붙은*
링크만 보면, 서버가 주문번호로 다시 모으는 형제가 통째로 빠진다:

1. 같은 집에 ``productOrder`` 래퍼가 **없는 평평한 링크**가 섞여 있다.
2. 같은 집 형제 1건이 **다른 FOMS 주문**에 붙어 있다.
3. 같은 집 형제 1건이 **아직 아무 데도 안 붙어 있다**.

세 장면 모두 고치기 전 코드에서 `화면 [1,2] != 서버 [1,2,3]` 로 red 였다 — 음성
대조군이 이미 서 있는 자리다.

판정에 조건을 **다시 구현하지 않는다.** 기대값은 서버가 쓰는 그 함수·그 술어를 그대로
불러서 만든다. 테스트가 조건을 손으로 적으면 두 벌이 갈리고, 갈리는 순간 이 파일은
사고를 못 잡는다.

파일을 새로 판 이유: ``test_naver_candidate_claim_approve.py`` 가 491줄이라 500줄
파일 상한 여유가 없다. 픽스처는 ``naver_candidate_pair_helpers`` 한 벌을 공유한다.
"""

from __future__ import annotations

import pytest

from db import db_session
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.fulfillment import (
    is_cancel_approvable,
    links_of_group,
)
from foms.services.integrations.naver_commerce.mapping import group_key_text
from models import ExternalOrderLink

from tests.services.integrations.naver_candidate_pair_helpers import (  # noqa: F401
    _candidate_row,
    _link,
    _login,
    _order,
    _uid,
    workbench_on,
)

#: 옛 집 링크 1건의 결제 금액. 0 이 아니어야 "평평한 원본도 금액을 읽는다"를 본문으로
#: 볼 수 있다(리더가 ``raw_snapshot["productOrder"]`` 직독이면 0 이 나온다).
AMOUNT = 1_230_000


@pytest.fixture()
def approve_on(monkeypatch):
    """승인 게이트 2종을 켠다(라우트와 같은 env 두 개)."""
    monkeypatch.setenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", "1")
    yield


# --------------------------------------------------------------------------- #
# 장면 만들기
# --------------------------------------------------------------------------- #

def _flat_link(*, order_no: str, tel: str, amount: int, claim: str,
               order_id: int | None = None, name: str = "쌍판정고객") -> ExternalOrderLink:
    """``productOrder`` 래퍼가 **없는** 수집 링크 1건(``order`` 래퍼만 있다).

    네이버 배치 조회는 상세를 평평하게 주기도 한다 — :func:`mapping.unwrap_detail` 이
    양쪽 모양을 다 받아 주는 이유가 그것이고, 서버 술어는 그 함수로 원본을 푼다.
    화면 쪽이 ``raw_snapshot["productOrder"]`` 를 직독하고 없으면 건너뛰면, **이 모양의
    링크만** 승인 목록에서 조용히 빠진다. 그 1건이 사람이 모르는 환불이 된다.

    집 키(``(주문번호, 수취인 전화, 주소)``)는 :func:`mapping.group_key` 가 같은
    ``unwrap_detail`` 로 뽑으므로 중첩 링크와 **같은 집**이 된다.

    Args:
        order_no: 네이버 주문번호(같은 값이면 같은 집 후보).
        tel: 수취인 전화.
        amount: 결제 금액.
        claim: ``claimStatus`` 원문.
        order_id: 붙어 있는 FOMS 주문 id. None 이면 미연결.
        name: 수취인명.

    Returns:
        저장된 :class:`ExternalOrderLink`.
    """
    external_id = f"PO-FLAT-{_uid()}"
    snapshot = {
        "order": {"orderId": order_no, "ordererName": name, "ordererTel": tel},
        "productOrderId": external_id,
        "productName": "붙박이장",
        "totalPaymentAmount": amount,
        "claimStatus": claim,
        "shippingAddress": {"name": name, "tel1": tel,
                            "baseAddress": "경기 성남 분당 백현로 206",
                            "detailedAddress": "410동 1203호"},
    }
    link = ExternalOrderLink(channel=CHANNEL, external_id=external_id,
                             external_order_no=order_no, raw_snapshot=snapshot,
                             group_key=group_key_text(snapshot),
                             sync_status="LINKED" if order_id else "COLLECTED",
                             order_id=order_id)
    db_session.add(link)
    db_session.commit()
    return link


def _server_targets(link_id: int) -> list[int]:
    """**서버가 실제로 보낼** 취소 승인 대상의 링크 id — 라우트와 같은 함수·같은 술어.

    :func:`fulfillment.approve_cancel` 이 하는 일 그대로다:
    :func:`fulfillment.links_of_group` 으로 집을 모으고
    :func:`fulfillment.is_cancel_approvable` 로 고른다. 여기서 조건을 손으로 다시 적으면
    이 파일이 지키려는 등식의 한쪽을 테스트가 만들어 내는 꼴이 된다.

    Args:
        link_id: 그 집의 아무 링크 id.

    Returns:
        오름차순 링크 id 목록.
    """
    rows = links_of_group(db_session, link_id)
    return sorted(int(row.id) for row in rows if is_cancel_approvable(row))


def _screen_targets(current, order_id: int) -> tuple[list[int], dict]:
    """화면이 재진술한 취소 승인 대상 — 후보 표가 실제로 싣는 값.

    Args:
        current: 지금 보고 있는 수집 링크(아직 안 붙은 새 결제).
        order_id: 후보 주문 id.

    Returns:
        ``(오름차순 링크 id 목록, 집 한 칸)``. 집이 없으면 ``([], {})``.
    """
    groups = _candidate_row(current, order_id)["naver_cancel_approve_groups"]
    assert len(groups) <= 1, f"옛 집은 한 채인데 {len(groups)}채로 갈렸다"
    if not groups:
        return ([], {})
    group = groups[0]
    return (sorted(int(target["link_id"]) for target in group["targets"]), group)


def _scene(*, flat: bool = False, sibling_order: bool = False,
           sibling_unlinked: bool = False) -> dict:
    """옛 집 1채(상품주문 3건) + 아직 안 붙은 새 결제 1건짜리 장면.

    세 건 모두 ``CANCEL_REQUEST`` 라 **서버 대상은 언제나 3건**이다. 갈리는 것은 세 번째
    건이 화면 모집단에 들어오느냐뿐이라, 등식이 깨지면 원인이 한 가지로 좁혀진다.

    Args:
        flat: 세 번째 건을 ``productOrder`` 래퍼 없는 원본으로 만든다.
        sibling_order: 세 번째 건을 **다른 FOMS 주문**에 붙인다.
        sibling_unlinked: 세 번째 건을 **아무 데도 안 붙인** 채로 둔다.

    Returns:
        ``{"current", "order_id", "house_link_id", "expect_third"}``.
        ``house_link_id`` 는 그 집의 아무 링크 id(서버 기대값을 뽑는 입구)다.
    """
    tel = f"010-7742-{_uid()}"
    order_no = f"N-OLD-{_uid()}"
    order_id = _order(tel=tel)
    kept = [_link(order_no=order_no, tel=tel, amount=AMOUNT, claim="CANCEL_REQUEST",
                  order_id=order_id) for _ in range(2)]
    if flat:
        third = _flat_link(order_no=order_no, tel=tel, amount=AMOUNT,
                           claim="CANCEL_REQUEST", order_id=order_id)
    elif sibling_order:
        # 같은 집인데 **다른 주문**에 붙어 있다. 전화가 다르므로 그 주문은 이 후보 표에
        # 안 나온다 — 그런데도 서버는 이 건을 함께 보낸다(집을 주문번호로 모으므로).
        other_id = _order(tel=f"010-2211-{_uid()}", name="다른주문고객")
        third = _link(order_no=order_no, tel=tel, amount=AMOUNT,
                      claim="CANCEL_REQUEST", order_id=other_id)
    elif sibling_unlinked:
        third = _link(order_no=order_no, tel=tel, amount=AMOUNT,
                      claim="CANCEL_REQUEST", order_id=None)
    else:
        raise AssertionError("장면을 하나는 골라야 한다")
    current = _link(order_no=f"N-NEW-{_uid()}", tel=tel, amount=AMOUNT)
    return {"current": current, "order_id": order_id,
            "house_link_id": int(kept[0].id), "third_id": int(third.id),
            "kept_ids": [int(row.id) for row in kept]}


# --------------------------------------------------------------------------- #
# 세 장면 — 셋 다 "화면 목록 == 서버 목록"으로만 판정한다
# --------------------------------------------------------------------------- #

def test_flat_snapshot_sibling_is_a_target(client, workbench_on, approve_on):
    """① 같은 집에 ``productOrder`` 래퍼 없는 평평한 링크가 섞여 있어도 대상에 든다.

    승인 축은 래퍼 유무와 **무관하다**(서버 술어가 ``unwrap_detail`` 로 푼다). 화면이
    래퍼 가드 아래에서 대상을 모으면 이 1건이 통째로 빠져, 화면은 2건이라 적고 서버는
    3건을 보낸다.
    """
    _login(client)
    scene = _scene(flat=True)

    server = _server_targets(scene["house_link_id"])
    screen, group = _screen_targets(scene["current"], scene["order_id"])

    assert scene["third_id"] in server, "전제가 깨졌다 — 평평한 건이 서버 대상이 아니다"
    assert screen == server, "화면 대상과 서버 대상이 갈렸다(평평한 원본이 빠진다)"
    assert group["product_order_count"] == len(server), \
        "'나머지 N건' 을 세는 집 전체 수도 서버가 보는 집과 같아야 한다"
    flat_target = next(t for t in group["targets"] if t["link_id"] == scene["third_id"])
    assert flat_target["amount"] == AMOUNT, \
        "평평한 원본의 금액이 0 이다 — 모달 줄이 지금 집 승인 모달과 다른 리더를 쓴다"
    assert flat_target["external_id"], "대상에 상품주문번호가 없다 — 모달이 무엇인지 못 적는다"


def test_sibling_on_another_order_is_a_target(client, workbench_on, approve_on):
    """② 같은 집 형제가 **다른 FOMS 주문**에 붙어 있어도 대상에 든다.

    서버는 집을 네이버 주문번호로 모은다 — 그 집에 우리 주문이 몇 개 걸려 있는지는 보지
    않는다. 화면이 '이 후보 주문에 붙은 링크'로만 세면 그 형제가 빠지고, 사람은 자기가
    누른 것보다 1건 더 나가는 것을 모른 채 승인한다.
    """
    _login(client)
    scene = _scene(sibling_order=True)

    server = _server_targets(scene["house_link_id"])
    screen, group = _screen_targets(scene["current"], scene["order_id"])

    assert scene["third_id"] in server, "전제가 깨졌다 — 남의 주문에 붙은 형제가 서버 대상이 아니다"
    assert screen == server, "화면 대상과 서버 대상이 갈렸다(남의 주문에 붙은 형제가 빠진다)"
    assert group["product_order_count"] == len(server)


def test_unlinked_sibling_is_a_target(client, workbench_on, approve_on):
    """③ 같은 집 형제가 **아직 아무 데도 안 붙어 있어도** 대상에 든다.

    미연결 형제는 후보 표를 만드는 조회(``order_id.in_(...)``)에 애초에 안 잡힌다.
    그런데 서버는 보낸다 — 여기가 화면과 서버가 가장 조용히 갈리는 자리다.
    """
    _login(client)
    scene = _scene(sibling_unlinked=True)

    server = _server_targets(scene["house_link_id"])
    screen, group = _screen_targets(scene["current"], scene["order_id"])

    assert scene["third_id"] in server, "전제가 깨졌다 — 미연결 형제가 서버 대상이 아니다"
    assert screen == server, "화면 대상과 서버 대상이 갈렸다(미연결 형제가 빠진다)"
    assert group["product_order_count"] == len(server)


def test_group_link_id_points_at_the_old_house(client, workbench_on, approve_on):
    """음성 대조군 — 버튼이 무는 ``link_id`` 는 **옛 집** 링크지 지금 집이 아니다.

    이 값이 승인 라우트가 받는 주소다. 지금 집(붙이려는 새 결제) 링크를 넘기면 살아
    있는 결제의 환불이 나가고, 되돌릴 방법이 없다.
    """
    _login(client)
    scene = _scene(sibling_unlinked=True)

    _screen, group = _screen_targets(scene["current"], scene["order_id"])

    assert group["link_id"] != int(scene["current"].id), \
        "버튼이 지금 집을 물었다 — 살아 있는 새 결제가 승인된다"
    assert group["link_id"] in scene["kept_ids"] + [scene["third_id"]], \
        "버튼이 그 옛 집에 없는 링크를 물었다"
    assert _server_targets(group["link_id"]) == _server_targets(scene["house_link_id"]), \
        "버튼이 무는 링크로 서버가 모으는 집이 다른 집이다"

"""정리 계획 카드에서 **옛 결제 취소·반품 승인** — 계약 테스트 (2026-09-07).

붙이기 후보 주문에 붙어 있는 **옛 네이버 집**을, 그 카드에서 그대로 승인하는 자리다.
승인은 **되돌릴 수 없다** — 승인 시점에 환불이 확정되고, 취소 승인에는 거절 API 가
아예 없다(철회는 구매자만 한다). 그래서 이 파일이 지키는 것은 한 문장으로 줄어든다:

    **화면이 말하는 건수 == 서버가 보낼 건수**, 그리고 **화면이 가리키는 집 == 서버가
    승인할 집**.

그래서 판정은 전부 서버 술어(:func:`fulfillment.is_cancel_approvable` /
:func:`~fulfillment.is_return_approvable`)가 고른 목록과, 그 목록이 **렌더 본문까지**
따라왔는지로 본다. 테스트가 조건을 다시 구현하면 두 벌이 갈리고, 갈리는 순간 이 파일은
사고를 못 잡는다.

픽스처는 ``naver_candidate_pair_helpers`` 한 벌을 공유한다 — 복사해 나누면 같은 상황을
두 파일이 다르게 재현한다.

운영 대조 데이터(production, 2026-09-07 read-only): 지금 집 링크 2215(``PAYED``·미연결) ·
후보 주문 #5158 · 옛 집 ``2026090498433601`` 링크 2162~2170 = ``CANCEL_REQUEST`` **9건**.
취소 승인 대상 9건 · 반품 승인 대상 0건 · POST 대상은 그 집 최소 링크 2162 · 지금 집
2215 는 어디에도 안 나온다.
"""

from __future__ import annotations

import re

import pytest

from db import db_session
from models import User

from tests.services.integrations.naver_candidate_pair_helpers import (  # noqa: F401
    _candidate_row,
    _link,
    _login,
    _order,
    _pane,
    _reconcile_plans,
    _uid,
    workbench_on,
)

#: 옛 집 링크 1건의 결제 금액. 0 이 아니어야 모달 줄 금액과 카드 합계가 **같은 리더**
#: (``productOrder.totalPaymentAmount``)에서 나오는지 본문으로 볼 수 있다.
AMOUNT = 1_230_000

#: 운영 대조군 건수(링크 2162~2170). 9 를 그대로 재현한다 — "다건이면 다건만큼"을
#: 임의의 작은 수로 줄이면 집 묶기 실수가 1건짜리 우연에 가려진다.
OLD_LINK_COUNT = 9

CANCEL_9 = ["CANCEL_REQUEST"] * OLD_LINK_COUNT

#: 새 모달 id 규칙 — **집 대표 링크 id** 로 문서 안에서 유일해진다.
CANCEL_MODAL_ID = "wb-modal-plan-cancel-approve-{link_id}"
RETURN_MODAL_ID = "wb-modal-plan-return-approve-{link_id}"

#: 지금 집(pane 위쪽) 전용 모달 id. **재사용하면 안 된다** — 대상이 후보마다 다른데
#: id 를 물려쓰면 후보 카드의 버튼이 지금 집 모달을 연다.
GROUP_MODAL_IDS = ('id="wb-modal-cancel-approve"', 'id="wb-modal-return-approve"')


@pytest.fixture()
def approve_on(monkeypatch):
    """승인 게이트 2종을 켠다.

    게이트는 **따로 판다**(라우트와 같은 env 두 개) — 한쪽을 켜는 것이 다른 쪽을 열면
    안 된다. 기본값이 꺼짐이라 켜지 않으면 버튼이 아예 안 뜬다.
    """
    monkeypatch.setenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", "1")
    monkeypatch.setenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", "1")
    yield


# --------------------------------------------------------------------------- #
# 장면 만들기 — 지금 집 1건 + 후보 주문에 붙어 있는 옛 집 여러 채
# --------------------------------------------------------------------------- #

def _house(claims: list[str], *, order_no: str = "", tel: str = "") -> dict:
    """옛 집 한 채의 설계도.

    Args:
        claims: 그 집 링크들의 ``claimStatus`` 원문(건수 = 목록 길이).
        order_no: 네이버 주문번호. 비우면 새로 만든다. **분할배송을 재현할 때만**
            두 채에 같은 값을 준다.
        tel: 수취인 전화. 비우면 후보 주문과 같은 번호를 쓴다. 집 키는
            ``(주문번호, 수취인 전화, 주소)`` 라, 같은 주문번호로 두 채를 가르려면
            이 축을 다르게 준다.

    Returns:
        :func:`_scene` 이 읽는 설계도 dict.
    """
    return {"claims": list(claims), "order_no": order_no, "tel": tel}


def _scene(houses: list[dict]) -> dict:
    """후보 1건짜리 장면을 만든다 — 옛 집은 붙어 있고, 지금 집은 아직 안 붙었다.

    Args:
        houses: :func:`_house` 설계도 목록.

    Returns:
        ``{"current", "current_id", "order_id", "houses"}``. ``houses`` 한 칸은
        ``{"order_no", "links": [(link_id, external_id)]}`` 이다 — 요청이 끝나면
        ORM 인스턴스가 detach 되므로 뒤에도 쓰는 값은 처음부터 스칼라로 들고 다닌다.
    """
    tel = f"010-3383-{_uid()}"
    order_id = _order(tel=tel)
    built = []
    for house in houses:
        order_no = house["order_no"] or f"N-OLD-{_uid()}"
        links = [_link(order_no=order_no, tel=house["tel"] or tel, amount=AMOUNT,
                       claim=claim, order_id=order_id)
                 for claim in house["claims"]]
        built.append({"order_no": order_no,
                      "links": [(int(link.id), link.external_id) for link in links]})
    current = _link(order_no=f"N-NEW-{_uid()}", tel=tel, amount=AMOUNT)
    return {"current": current, "current_id": int(current.id), "order_id": order_id,
            "houses": built}


def _become_staff(client, user: User) -> None:
    """방금 로그인한 사람을 실무자로 낮춘다 — 라우트(DB)와 화면(세션) 두 축을 함께.

    트리아지 화면은 STAFF 도 열 수 있고(규격 입력이 CS 접수 담당 일이라), 승인만
    ADMIN·MANAGER 다. 그래서 역할을 낮춰도 화면은 열리고 **버튼만** 사라져야 한다.

    Args:
        client: 테스트 클라이언트.
        user: :func:`_login` 이 만든 사용자.

    Returns:
        None.
    """
    user.role = "STAFF"
    db_session.commit()
    with client.session_transaction() as sess:
        sess["role"] = "STAFF"


# --------------------------------------------------------------------------- #
# 본문 읽기 — 화면이 실제로 낸 태그만 본다(템플릿 변수를 흉내내지 않는다)
# --------------------------------------------------------------------------- #

def _flat(text: str) -> str:
    """줄바꿈·들여쓰기를 공백 하나로 접는다 — 템플릿 줄바꿈에 문장 검사가 걸리지 않게."""
    return re.sub(r"\s+", " ", text)


def _attr(tag: str, name: str) -> str:
    """여는 태그에서 속성 값 하나를 꺼낸다(없으면 빈 문자열)."""
    match = re.search(rf'{name}="([^"]*)"', tag)
    return match.group(1) if match else ""


def _approve_buttons(body: str, *, kind: str = "") -> list[str]:
    """정리 계획 카드의 **승인 여는 버튼** 태그만 잘라 낸다.

    모달 안 확인 버튼(``wb-plan-approve-confirm``)은 뺀다 — 여는 버튼과 확인 버튼을
    같은 목록에 담으면 "버튼이 없다"는 음성 대조군이 절반만 보게 된다.

    Args:
        body: 렌더 본문.
        kind: ``cancel`` 또는 ``return``. 주면 그 축만 남긴다.

    Returns:
        여는 태그 목록(문서 순서).
    """
    tags = []
    for tag in re.findall(r"<button[^>]*>", body):
        if not re.search(r'class="[^"]*\bwb-plan-approve(?!-)', tag):
            continue
        if kind and _attr(tag, "data-kind") != kind:
            continue
        tags.append(tag)
    return tags


def _modal_chunk(body: str, modal_id: str) -> str:
    """그 모달 하나의 본문만 잘라 낸다 — 옆 집 모달의 글자가 섞이지 않게.

    ``<div>`` 짝을 세어 **그 모달이 닫히는 자리까지**만 자른다. "다음 모달이 시작하는
    자리"로 자르면 문서의 마지막 모달이 뒤따르는 본문을 통째로 삼켜, "옆 집 대상이 안
    섞였다"는 음성 대조군이 조용히 헐거워진다.

    Args:
        body: 렌더 본문.
        modal_id: 자를 모달의 id.

    Returns:
        그 모달 한 덩어리의 HTML.
    """
    at = body.find(f'id="{modal_id}"')
    assert at >= 0, f"모달 {modal_id} 이 본문에 없다"
    start = body.rfind("<div", 0, at)
    assert start >= 0, f"모달 {modal_id} 의 여는 태그를 못 찾았다"
    depth = 0
    for match in re.finditer(r"<div\b|</div>", body[start:]):
        depth += -1 if match.group(0) == "</div>" else 1
        if depth == 0:
            return body[start:start + match.end()]
    raise AssertionError(f"모달 {modal_id} 이 닫히지 않았다")


# --------------------------------------------------------------------------- #
# 1. 대상 — 서버 술어가 고른 것만, 그 집 링크와 함께
# --------------------------------------------------------------------------- #

def test_old_cancel_requests_load_every_link_as_a_target(client, workbench_on, approve_on):
    """옛 집이 취소 요청 9건이면 승인 대상도 **9건**이고, 각 대상이 그 집 링크다.

    운영 대조군(후보 #5158 · 옛 집 링크 2162~2170) 그대로다. 건수를 따로 센 필드를
    두지 않는 것도 함께 못박는다 — 두 수가 갈리면 불가역 경로의 과대 진술이다.
    """
    _login(client)
    scene = _scene([_house(CANCEL_9)])
    house = scene["houses"][0]
    old_ids = [link_id for link_id, _ in house["links"]]

    row = _candidate_row(scene["current"], scene["order_id"])
    groups = row["naver_cancel_approve_groups"]

    assert len(groups) == 1, "옛 집은 한 채다 — 집이 갈리면 버튼도 갈린다"
    group = groups[0]
    assert set(group) == {"link_id", "external_order_no", "product_order_count", "targets"}, \
        "집 한 칸 모양이 계약과 다르다 — 승인 건수는 targets 길이 하나뿐이다"
    assert group["external_order_no"] == house["order_no"]
    assert group["product_order_count"] == OLD_LINK_COUNT
    assert [t["link_id"] for t in group["targets"]] == sorted(old_ids), \
        "대상의 link_id 가 그 옛 집 링크가 아니다"
    assert [t["external_id"] for t in group["targets"]] \
        == [ext for _, ext in sorted(house["links"])]
    assert all(t["amount"] == AMOUNT for t in group["targets"]), \
        "금액이 카드 합계와 다른 리더에서 나왔다"
    assert row["naver_return_approve_groups"] == [], "취소 요청이 반품 축을 열었다"

    plans = _reconcile_plans(scene["current"], scene["order_id"])
    assert plans["REPAY"]["naver_cancel_approve_groups"] == groups
    assert plans["ADDON"]["naver_cancel_approve_groups"] == groups, \
        "승인 대상은 관계(REPAY/ADDON)와 무관하다 — 관계별로 다르면 화면이 흔들린다"


def test_the_group_button_points_at_the_old_household_not_the_new_payment(
        client, workbench_on, approve_on):
    """POST 대상은 **그 집 링크**다 — 지금 집 링크는 버튼 어디에도 없다.

    지금 집(붙이려는 새 결제) 링크를 넘기면 라우트가 그 집 형제를 모아 **살아 있는
    결제**를 환불시킨다. 되돌릴 곳이 없다. 그래서 음성 대조군은 "옛 집이 맞다"가 아니라
    "지금 집 id 가 승인 버튼 태그에 한 번도 안 나온다"로 센다.
    """
    _login(client)
    scene = _scene([_house(CANCEL_9)])
    old_ids = [link_id for link_id, _ in scene["houses"][0]["links"]]
    current_id = scene["current_id"]

    row = _candidate_row(scene["current"], scene["order_id"])
    group = row["naver_cancel_approve_groups"][0]
    body = _pane(client, link_id=current_id)

    assert group["link_id"] in old_ids
    assert group["link_id"] == min(old_ids), "대표는 집 안 최소 id 로 결정론적이어야 한다"
    assert group["link_id"] != current_id

    tags = _approve_buttons(body)
    assert tags, "승인 버튼이 렌더되지 않았다"
    assert {_attr(tag, "data-link-id") for tag in tags} == {str(min(old_ids))}
    assert not re.search(rf"\b{current_id}\b", " ".join(tags)), \
        "지금 집 링크 id 가 승인 버튼 태그에 실렸다"


# --------------------------------------------------------------------------- #
# 2. 렌더 — 버튼·모달이 그 집 링크 id 로 유일하게 난다
# --------------------------------------------------------------------------- #

def test_the_plan_card_renders_a_cancel_approve_button_with_its_own_modal(
        client, workbench_on, approve_on):
    """정리 계획 카드에 승인 버튼이 있고, 모달 id 가 **그 집 링크 id** 로 유일하다."""
    _login(client)
    scene = _scene([_house(CANCEL_9)])
    house = scene["houses"][0]
    rep = min(link_id for link_id, _ in house["links"])

    body = _pane(client, link_id=scene["current_id"])
    flat = _flat(body)
    modal_id = CANCEL_MODAL_ID.format(link_id=rep)

    tags = _approve_buttons(body, kind="cancel")
    assert len(tags) == 1, "집 하나에 버튼 하나여야 한다"
    assert _attr(tags[0], "data-link-id") == str(rep)
    assert _attr(tags[0], "data-bs-target") == f"#{modal_id}"
    assert body.count(f'id="{modal_id}"') == 1, "모달 id 가 문서에 중복이다"
    for reused in GROUP_MODAL_IDS:
        assert reused not in body, "지금 집 전용 모달 id 를 재사용했다"
    assert f"네이버 취소 승인 — 환불 확정 {OLD_LINK_COUNT}건" in flat
    assert f"옛 결제({house['order_no']})만 승인합니다" in flat, \
        "이 버튼이 무엇을 건드리는지 버튼 옆에 항상 적혀 있어야 한다"


def test_the_modal_restates_every_target_not_just_the_count(
        client, workbench_on, approve_on):
    """모달이 **건수가 아니라 목록**을 재진술한다 — 안 나가는 건은 적지 않는다.

    한 집에 요청 7건 · 이미 완료 2건을 섞는다(음성 대조군을 모집단 안에서 고른다).
    승인 대상 7건의 상품주문번호는 전부 모달에 있고, 완료된 2건은 없어야 한다.
    """
    _login(client)
    scene = _scene([_house(["CANCEL_REQUEST"] * 7 + ["CANCEL_DONE"] * 2)])
    house = scene["houses"][0]
    settled = {ext for _, ext in house["links"][7:]}

    row = _candidate_row(scene["current"], scene["order_id"])
    group = row["naver_cancel_approve_groups"][0]
    body = _pane(client, link_id=scene["current_id"])
    chunk = _modal_chunk(body, CANCEL_MODAL_ID.format(link_id=group["link_id"]))
    flat = _flat(chunk)

    assert len(group["targets"]) == 7
    assert group["product_order_count"] == 9
    for target in group["targets"]:
        assert target["external_id"] in flat, "모달이 대상 목록을 재진술하지 않는다"
    for external_id in settled:
        assert external_id not in flat, "이미 승인된 건을 모달이 대상으로 적었다"
    assert f"{AMOUNT:,}" in flat, "금액이 모달에 없다 — 무엇에 얼마가 걸렸는지 못 읽는다"
    assert "나머지" in flat, "집 9건 중 7건만 나가는데 나머지 2건을 말하지 않는다"
    assert "되돌릴 수 없습니다" in flat, "불가역 경고가 없다"
    assert "data-foms-no-autodismiss" in chunk, \
        ".alert 는 5초 뒤 자동으로 닫힌다 — 불가역 경고가 사라지면 안 된다"
    # 모달은 **건수로 단정하지 않는다**(감수한 한계). 목록은 이 주문에 붙은
    # 링크만 보는데, 서버(``fulfillment._links_of_group``)는 같은 집 형제를
    # 주문번호로 다시 모으므로 아직 안 붙은 형제가 있으면 **더 나간다**.
    # "N건을 승인합니다"로 적으면 그 차이가 사람이 모르는 환불이 된다.
    assert "아래 상품주문" in flat, "모달이 목록 대신 건수로 단정한다"
    assert f"취소 요청 {len(group['targets'])}건" not in flat, \
        "모달이 보낼 건수를 단정했다 — 서버가 더 보낼 수 있다"
    # 확인 버튼은 후보·집 수만큼 나온다 — ``id`` 를 달면 문서에 중복이 생긴다.
    confirm = re.search(r"<button[^>]*wb-plan-approve-confirm[^>]*>", chunk)
    assert confirm is not None, "모달에 확인 버튼이 없다"
    assert _attr(confirm.group(0), "data-link-id") == str(group["link_id"])
    assert _attr(confirm.group(0), "data-kind") == "cancel"
    assert " id=" not in confirm.group(0), "확인 버튼에 id 를 달았다(절대 규칙 1)"


# --------------------------------------------------------------------------- #
# 3. 음성 대조군 — 열리면 안 되는 자리에서 안 열린다
# --------------------------------------------------------------------------- #

def test_a_settled_old_household_shows_no_approve_button(client, workbench_on, approve_on):
    """옛 집이 이미 ``CANCEL_DONE`` 이면 승인할 것이 없다 — 버튼도 모달도 없다."""
    _login(client)
    scene = _scene([_house(["CANCEL_DONE"] * OLD_LINK_COUNT)])

    row = _candidate_row(scene["current"], scene["order_id"])
    body = _pane(client, link_id=scene["current_id"])

    assert row["naver_cancel_approve_groups"] == []
    assert row["naver_return_approve_groups"] == []
    assert _approve_buttons(body) == []
    assert "wb-modal-plan-cancel-approve-" not in body, "빈 모달이 문서에 남았다"


def test_staff_sees_no_approve_button(client, workbench_on, approve_on):
    """실무자(STAFF)에게는 버튼이 없다 — 라우트와 **같은 조건**으로 렌더한다.

    서버 축(후보 행의 대상 목록)은 그대로 있어야 한다. 닫는 것은 화면 조건 하나이고,
    화면만 열고 라우트를 닫으면(또는 그 반대면) 눌린 버튼이 403 을 받는다.
    """
    user = _login(client)
    _become_staff(client, user)
    scene = _scene([_house(CANCEL_9)])

    row = _candidate_row(scene["current"], scene["order_id"])
    body = _pane(client, link_id=scene["current_id"])

    assert row["naver_cancel_approve_groups"], "서버 축까지 닫으면 원인이 안 갈린다"
    assert _approve_buttons(body) == []
    assert "wb-modal-plan-cancel-approve-" not in body


def test_the_approve_gates_open_each_axis_on_its_own(client, workbench_on, monkeypatch):
    """게이트를 끄면 버튼이 없고, 취소만 꺼도 **반품 버튼은 남는다**.

    한쪽 게이트가 다른 쪽을 열면 첫 실호출이 두 배선의 동시 검증이 되어, 실패했을 때
    어느 쪽이 틀렸는지 안 갈린다(승인 게이트를 따로 판 이유 그대로).
    """
    _login(client)
    scene = _scene([_house(["CANCEL_REQUEST"] * 2), _house(["RETURN_REQUEST"] * 3)])
    link_id = scene["current_id"]

    monkeypatch.delenv("FOMS_NAVER_CANCEL_APPROVE_ENABLED", raising=False)
    monkeypatch.delenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", raising=False)
    off_body = _pane(client, link_id=link_id)

    monkeypatch.setenv("FOMS_NAVER_RETURN_APPROVE_ENABLED", "1")
    return_only_body = _pane(client, link_id=link_id)

    assert _approve_buttons(off_body) == [], "게이트가 꺼졌는데 버튼이 있다"
    assert "wb-modal-plan-cancel-approve-" not in off_body
    assert "wb-modal-plan-return-approve-" not in off_body
    assert _approve_buttons(return_only_body, kind="cancel") == [], \
        "반품 게이트가 취소 버튼을 열었다"
    assert len(_approve_buttons(return_only_body, kind="return")) == 1


def test_split_shipment_splits_the_button_into_two_households(
        client, workbench_on, approve_on):
    """같은 주문번호라도 **분할배송이면 집이 둘**이고, 모달은 자기 집만 재진술한다.

    주문번호만으로 묶으면 두 집이 한 버튼에 합쳐진다 — 모달은 5건을 재진술하는데 서버
    (``_links_of_group``)는 그 집 몫만 보낸다. 집 키는 화면 큐와 같은 규칙
    ``(주문번호, 수취인 전화, 주소)`` 다.
    """
    _login(client)
    shared_no = f"N-SPLIT-{_uid()}"
    scene = _scene([
        _house(["CANCEL_REQUEST"] * 2, order_no=shared_no),
        _house(["CANCEL_REQUEST"] * 3, order_no=shared_no, tel=f"010-3384-{_uid()}"),
    ])
    everyone = {ext for house in scene["houses"] for _, ext in house["links"]}

    row = _candidate_row(scene["current"], scene["order_id"])
    groups = row["naver_cancel_approve_groups"]
    body = _pane(client, link_id=scene["current_id"])

    assert len(groups) == 2, "분할배송 두 집이 한 버튼에 합쳐졌다"
    assert {g["external_order_no"] for g in groups} == {shared_no}
    assert sorted(len(g["targets"]) for g in groups) == [2, 3]
    assert len(_approve_buttons(body, kind="cancel")) == 2

    for group in groups:
        chunk = _flat(_modal_chunk(body, CANCEL_MODAL_ID.format(link_id=group["link_id"])))
        mine = {t["external_id"] for t in group["targets"]}
        for external_id in mine:
            assert external_id in chunk
        for external_id in everyone - mine:
            assert external_id not in chunk, "옆 집 대상이 이 모달에 섞였다"


# --------------------------------------------------------------------------- #
# 4. 승인은 정리 실행을 **앞당기지 않는다**
# --------------------------------------------------------------------------- #

def test_approving_does_not_open_the_reconcile_run_button(client, workbench_on, approve_on):
    """승인 버튼이 있다고 ``정리 실행``이 열리지 않는다 — 워커가 확정시킨 뒤에 열린다.

    승인은 큐에 들어가고 워커가 네이버로 보낸다. 그 확정이 돌아와 집계 코드가
    ``all_done`` 이 되면 기존 규칙(``run_gate``)이 저절로 연다. 화면이 그 흐름을
    앞당기면 확정되지 않은 옛 결제 위에서 붙이기가 실행된다.
    """
    _login(client)
    scene = _scene([_house(CANCEL_9)])

    plans = _reconcile_plans(scene["current"], scene["order_id"])
    body = _pane(client, link_id=scene["current_id"])

    for relation in ("REPAY", "ADDON"):
        assert plans[relation]["can_run"] is False
        assert plans[relation]["run_block"], "왜 못 누르는지가 화면에 없다"
        assert plans[relation]["naver_cancel_approve_groups"], "승인 대상까지 사라졌다"
    run_button = re.search(r"<button[^>]*wb-plan-run[^>]*>", body)
    assert run_button is not None
    assert "disabled" in run_button.group(0), "확정 전인데 정리 실행이 열렸다"
    assert _approve_buttons(body, kind="cancel"), "승인 버튼은 그 자리에 있어야 한다"
    # 맺음말 훈수는 뗐다(2026-09-08). 잠금 사유는 run_block 한 곳이 들고, 그 본문이
    # 비활성 `정리 실행` 옆에 찍힌다 — 문장 사본이 아니라 그 배선을 문다.
    assert "네이버가 아직 취소를 확정하지 않았습니다" in plans["REPAY"]["run_block"]
    assert _flat(plans["REPAY"]["run_block"]) in _flat(body), \
        "잠금 사유가 화면에서 사라졌다 — 그 사유가 곧 이 버튼이 필요한 이유다"


# --------------------------------------------------------------------------- #
# 5. 반품 축도 한 벌
# --------------------------------------------------------------------------- #

def test_a_return_request_household_opens_only_the_return_button(
        client, workbench_on, approve_on):
    """옛 집이 반품 요청이면 **반품 승인만** 뜬다 — 취소 승인은 안 뜬다."""
    _login(client)
    scene = _scene([_house(["RETURN_REQUEST"] * 3)])
    rep = min(link_id for link_id, _ in scene["houses"][0]["links"])

    row = _candidate_row(scene["current"], scene["order_id"])
    body = _pane(client, link_id=scene["current_id"])

    assert row["naver_cancel_approve_groups"] == []
    groups = row["naver_return_approve_groups"]
    assert len(groups) == 1
    assert len(groups[0]["targets"]) == 3
    assert groups[0]["link_id"] == rep

    assert _approve_buttons(body, kind="cancel") == []
    tags = _approve_buttons(body, kind="return")
    assert len(tags) == 1
    assert _attr(tags[0], "data-bs-target") == f"#{RETURN_MODAL_ID.format(link_id=rep)}"
    assert "네이버 반품 승인 — 환불 확정 3건" in _flat(body)

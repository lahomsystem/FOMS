"""발주확인·발송처리 실행 (NAVER-INGEST-02 T16-G) — **WORKER 전용**.

네이버 HTTP 는 WORKER 에서만 나간다(커머스API 호출 IP 3슬롯 = Railway static IP 3개, 여유 0).
web 은 :func:`foms.services.jobs.queue.enqueue_naver_fulfillment` 로 enqueue 만 한다.

되돌릴 수 없는 조작이다
-----------------------
발송처리는 구매자에게 "물건이 출발했다"로 보이고 정산·구매확정 시계를 돌린다. 그래서:

* **멱등** — 링크의 ``triage_state['fulfillment']`` 에 처리 시각을 남기고, 값이 있으면
  네이버를 다시 부르지 않는다. 네이버의 400(이미 처리됨)을 정상 흐름으로 삼지 않는다.
  발송처리는 신호가 **한 벌 더** 있다(2026-08-26 T5): 원본 스냅샷의
  ``delivery.sendDate``. 판매자센터에서 사람이 직접 보낸 발송은 우리 표식에 없어서,
  그 신호를 안 보면 이미 나간 집에 두 번째 호출이 그대로 나간다
  (:func:`_naver_dispatched_at`).
* **실패는 조용히 넘기지 않는다** — 사유 문장을 상태에 남겨 화면이 그대로 보여준다.
* 배송방법은 자사 배송이라 ``DIRECT_DELIVERY``(직접 전달). 택배사·송장이 없다.
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.orm import Session

from foms.services.datetime_kst import now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import CONFIRMED_PLACE_STATUSES
from models import ExternalOrderLink

logger = logging.getLogger(__name__)

__all__ = [
    "FulfillmentError",
    "household_key",
    "links_of_group",
    "STATE_KEY",
    "DIRECT_DELIVERY",
    "clear_failure",
    "confirm_place_order",
    "dispatch_order",
    "cancel_order",
    "record_task_failure",
    "BANNED_CLAIM_REASONS",
    "CANCEL_REASONS",
    "OFFICIAL_CANCEL_REASONS",
    "OFFICIAL_RETURN_REASONS",
    "RETURN_REASONS",
    "RETURN_COLLECT_METHOD",
    "request_return",
    "is_return_pending",
    "reject_return",
    "is_return_rejectable",
    "RETURN_REJECT_REASON_MAX",
    "RETURN_REJECTABLE_STATUSES",
    "RETURN_REJECT_FILLS",
    "HEALTHY_SYNC_STATUSES",
    "CLOSE_NOW_RELATIONS",
]

#: ``triage_state`` 안에서 이 기능이 쓰는 키. 도크 체크·클레임 동기화와 다른 축이다.
STATE_KEY = "fulfillment"

#: 자사 배송(택배사·송장 없음)의 배송방법 코드.
DIRECT_DELIVERY = "DIRECT_DELIVERY"

#: 발주확인 없이도 바로 발송처리로 닫는 관계(2026-08-22 결정 D1 → **D1 개정 2026-08-24**).
#:
#: 추가결제(ADDON)만 여기 남는다 — 차액만 더 받은 것이라 **물건이 따로 나가지 않는다**.
#: "배송 시작"이 사실을 왜곡하지 않으므로 발주확인 전에 바로 닫아도 된다.
#:
#: 재결제(REPAY)는 **뺐다**(D1 개정 2026-08-24). 재결제는 원 주문을 취소하고 그 물건값을
#: 다시 낸 것이다 — **원 주문의 물건이 나중에 한 번 나간다**. "물건이 따로 나가지 않는다"
#: 는 ADDON 논리이고 REPAY 에는 거짓이다. 출고 전에 닫으면 구매자에게 "배송 시작"이 먼저
#: 뜨고 구매확정·정산 시계가 돌며, ``dispatched_any`` 가 되어 취소 버튼까지 사라진다
#: (되돌릴 수 없다). 2026-08-19 스펙 §3 원안(REPAY = 신규와 같게)으로 되돌린 것이다.
#:
#: 재결제·신규(NEW·빈값)는 발주확인이 먼저다. 발주확인 버튼은 그대로 열려 있고
#: (``can_confirm``) 확인 뒤 발송처리가 열리므로 **막다른 길은 없다** — 비용은 클릭 1회다.
CLOSE_NOW_RELATIONS = ("ADDON",)

#: 판매자가 **보낼 수 있는** 취소 사유 코드 전체 (2026-08-28 확인).
#: 출처: commerce-api 공개 토론 #1170 "반품/교환 배송비의 부담 주체는 어떻게 확인하나요?"
#: (마지막 변경 2026-08-03) 의 **클레임 사유 코드별 귀책 주체** 표. 취소·반품·교환의 사유
#: 코드 집합은 동일하다(#3335).
#:
#: **반품에는 있던 잠금이 취소에는 없었다.** :data:`OFFICIAL_RETURN_REASONS` 와 그 부분집합
#: 계약 테스트가 반품 쪽에만 있어서, 취소는 "우리 목록 안인가"만 자기 자신과 대조하고 있었다
#: (:func:`cancel_order` 의 화이트리스트 검사). 같은 축의 같은 구멍이다 —
#: `WRONG_DELAYED_DELIVERY` 를 읽기 값만 보고 반품 목록에 넣었다가 뺀 사고(2026-08-27)가
#: 취소에서 반복될 자리였다. **읽기로 오는 코드가 쓰기로 받는 코드보다 넓다**(공식 #1137).
#:
#: `ETC` 는 표에 있지만 **여기 넣지 않는다** — 취소 요청·반품 요청 API 호출 시 사유로
#: 설정할 수 없다(#3335). 읽기로는 올 수 있어 매핑 쪽에서는 계속 다룬다.
OFFICIAL_CANCEL_REASONS = (
    # 구매자 귀책
    "INTENT_CHANGED", "COLOR_AND_SIZE", "WRONG_ORDER", "SIMPLE_INTENT_CHANGED",
    "MISTAKE_ORDER", "DELAYED_DELIVERY_BY_PURCHASER", "PRODUCT_UNSATISFIED_BY_PURCHASER",
    # 판매자 귀책
    "PRODUCT_UNSATISFIED", "DELAYED_DELIVERY", "SOLD_OUT", "DROPPED_DELIVERY", "BROKEN",
    "INCORRECT_INFO", "WRONG_DELIVERY", "WRONG_OPTION", "WRONG_DELAYED_DELIVERY",
    "BROKEN_AND_BAD", "UNDER_QUANTITY",
)

#: 판매자 직접취소 사유 코드 → 사람이 읽는 라벨 (커머스API 2.86.0 "취소 요청").
#: 네이버가 아는 값만 보낸다 — 목록 밖 코드는 400 이고, 되돌릴 수 없는 경로라 미리 막는다.
#: :data:`OFFICIAL_CANCEL_REASONS` 의 부분집합임을 계약 테스트가 잠근다.
#:
#: **`SOLD_OUT` 은 여기 없다 — 절대 보내지 않는다**(사용자 지시 2026-09-01).
#: 공식 #2823: "'상품 품절' 사유로 인한 판매 취소 시 대상 상품 또는 조합형/표준형 옵션
#: 조합의 **재고는 품절 처리**됩니다. 조건에 따라 판매자 불이익이 발생할 수 있습니다
#: (판매관리 프로그램 패널티)."
#:
#: 2026-08-28 에는 "진짜 품절 취소는 정당한 용례"라며 **삭제를 기각**하고 라벨에 결과만
#: 적어 뒀었다. 그 판단이 뒤집혔다 — 우리 스토어는 시공 제품이라 품절 취소가 실제 업무에
#: 없고, 목록에 남겨 두는 것만으로 **누가 한 번 고르면 팔던 상품이 네이버에서 내려가고
#: 패널티가 붙는다**. 되돌릴 수 없는 경로에서 "고르기 전에 보이게" 는 충분한 방어가 아니다.
#:
#: **화면에서만 빼지 않고 이 화이트리스트에서 지운다.** 라우트와 서비스가 둘 다 이 dict 로
#: 검사하므로, 지우면 열린 탭·북마크·직접 호출로도 나가지 못한다
#: (:data:`BANNED_CLAIM_REASONS` 와 계약 테스트가 되살아나는 것을 막는다).
#:
#: 재결제 목적(구매자와 협의한 대리 취소)의 올바른 코드는 `INTENT_CHANGED` 다 —
#: 구매자 귀책이고, 공식이 인정한 사용 사유 "구매자와의 협의하에 구매자의 주문 취소 의사를
#: 대리하여 판매자가 클레임 처리를 진행하는 경우"(#2823)에 해당한다.
CANCEL_REASONS = {
    "INTENT_CHANGED": "구매 의사 취소",
    "COLOR_AND_SIZE": "색상 및 사이즈 변경",
    "WRONG_ORDER": "다른 상품 잘못 주문",
    "PRODUCT_UNSATISFIED": "서비스 불만족",
    "DELAYED_DELIVERY": "배송 지연",
    "INCORRECT_INFO": "상품 정보 상이",
}

#: **보내면 안 되는 사유 코드** — 네이버가 아는 값이지만 우리가 고르면 제재로 돌아온다.
#:
#: `SOLD_OUT` 은 대상 상품·옵션 조합을 **품절 처리**하고 판매관리 패널티 대상이다
#: (공식 #2823). 우리 업무에 품절 취소가 없으므로 얻는 것은 없고 잃는 것만 있다.
#:
#: 이 튜플은 목록에서 사라진 것을 **다시 못 넣게 하는 계약**이다 — 코드를 지우기만 하면
#: 다음 사람이 "범례에 있으니 넣자"로 되돌린다. 읽기 쪽(:data:`OFFICIAL_CANCEL_REASONS`·
#: :data:`OFFICIAL_RETURN_REASONS`)에는 그대로 둔다: 네이버가 그 값을 보내오면 우리는
#: **읽어야** 하고, 읽는 것과 보내는 것은 다른 축이다.
BANNED_CLAIM_REASONS = ("SOLD_OUT",)

#: 판매자가 **보낼 수 있는** 반품 사유 코드 전체(2026-08-27 확인). 네이버 직원 답변이
#: `returnReason` 범례로 직접 제시한 11종이며, 설계서 §6 Q3(미결이던 "코드 표 전체")의 답이다.
#: 출처: commerce-api 공개 토론 #639.
#:
#: **읽기 값은 이보다 많다** — 네이버 공식 답변 #1137: "실제 주문 데이터로 제공되는 클레임
#: 사유 코드는 판매자가 커머스API로 클레임 요청을 할 때 선택할 수 있는 코드보다 더 많다."
#: `MISTAKE_ORDER`·`SIMPLE_INTENT_CHANGED`·`WRONG_DELAYED_DELIVERY` 등이 그런 읽기 전용
#: 코드다. **스냅샷에서 봤다는 것은 보낼 수 있다는 뜻이 아니다.**
OFFICIAL_RETURN_REASONS = (
    "INTENT_CHANGED", "COLOR_AND_SIZE", "WRONG_ORDER", "PRODUCT_UNSATISFIED",
    "DELAYED_DELIVERY", "SOLD_OUT", "DROPPED_DELIVERY", "BROKEN",
    "INCORRECT_INFO", "WRONG_DELIVERY", "WRONG_OPTION",
)

#: 판매자 반품 접수 사유 코드 → 사람이 읽는 라벨 (T8-S1).
#: **취소 코드와 다른 목록이다** — `CANCEL_REASONS` 를 재사용하지 않는다.
#:
#: 우리 업무에서 **실제로 발생하는 사유만** 둔다(사용자 확인 2026-08-27). 우리 스토어의
#: 반품은 **실물이 없다** — 시공 제품이라 시공 전에는 물건이 고객 집에 갈 수 없고,
#: 반품은 곧 **발송 처리된 주문건의 주문 취소**다(발송 전은 취소, 발송 후는 반품).
#: 그래서 실제 사유는 셋뿐이다: ① 고객 변심·주문 취소 ② 색상·사이즈 변경
#: ③ 실측 후 최종 견적이 주문 금액과 달라 **재결제하려고** 하는 반품.
#: 범례에 "금액 정정·재결제" 코드는 **없다**(11종 전수 확인). ① 은 `INTENT_CHANGED`,
#: ② 는 `COLOR_AND_SIZE`, ③ 은 담당자가 둘 중 실제에 맞는 쪽을 고른다(아래 참조).
#:
#: **`WRONG_DELAYED_DELIVERY` 를 뺐다 — 보낼 수 없는 코드였다.** 위 범례 11종 밖이다.
#: 스테이징 관측(392행 전수: 등장 18회 / 링크 9건)은 네이버가 **준** 값(읽기)이지
#: 우리가 **보낼 수 있다는** 증명이 아니다.
#: 릴리즈 노트 #705: "반품 요청 또는 취소 요청 시 대상 주문건의 클레임 요청 사유 중
#: **실제 사용이 불가능한 코드가 포함되어 제공된 것을 확인**하였습니다." 반품 접수는
#: 실호출 0회라 이 400 을 아무도 만난 적이 없었다.
#:
#: **나머지 9종을 안 넣는다.** 배송 지연·품절·파손·오배송은 실물이 오가지 않는 우리
#: 업무에서 발생할 수 없다. 목록에 있으면 언젠가 누가 고른다.
#:
#: **제재 경고 전문(#2823)** — 앞절만 인용하면 우리 매핑을 겨누는 뒷절이 사라진다:
#: "실제 취소 사유(클레임 요청 사유)와 다른 사유로 취소 클레임을 처리하거나 **구매자의
#: 주문 취소(청약 철회) 의사가 없음에도 임의로 주문을 취소하는 경우** 고의적 부당행위로
#: 간주하여 판매자 불이익이 발생할 수 있습니다."
#: 뒷절이 사례 ③(재결제 목적)을 정확히 겨눈다. 그래서 이 목록으로 보내는 것은
#: **고객이 그 주문의 취소에 동의한 건에 한한다** — 판매자가 금액을 고치려고 임의로
#: 넣는 것이 아니다. 이 조건을 화면 경고로 띄웠다가 **뺐다**(사용자 결정 2026-08-27):
#: 담당자가 이미 아는 내용이라 화면만 복잡해진다. **업무 규칙으로 지킨다** — 코드나
#: 화면이 강제하지 않는다는 뜻이니, 나중에 이 자리를 손대는 사람은 조건이 사라진 것으로
#: 읽지 마라.
#:
#: 사례 ③(재결제)은 `INTENT_CHANGED` 와 `COLOR_AND_SIZE` 중 **담당자가 실제에 맞는 쪽을
#: 고른다**(사용자 결정 2026-08-27). 규격이 실제로 바뀌어 금액이 달라진 건이면 색상·사이즈
#: 변경이 사실이고, 그냥 그 주문을 접는 것이면 구매 의사 취소가 사실이다.
#:
#: **돈**: 여기 둘 다 **구매자 귀책**이다(#1170: "스마트스토어는 클레임 사유에 따라 대상
#: 클레임의 귀책 주체를 판별하며 귀책 주체에 따라 클레임 배송비의 부담자가 결정됩니다").
#: 실물 회수가 없는데도 상품에 설정된 반품배송비가 구매자에게 청구될 수 있다 — 실제 청구
#: 여부는 상세 응답의 `claimDeliveryFeeDemandAmount` 로만 판정한다(실물 1건 때 확인).
#:
#: **읽기 쪽은 좁히지 않는다** — `mapping` 이 스냅샷의 `returnReason` 을 그대로 보여주는
#: 것은 우리가 보낸 값이 아니라 네이버가 준 값이고, 목록에 없다고 화면에서 지우면
#: 사실이 사라진다. 좁히는 것은 **우리가 보내는 값**뿐이다.
RETURN_REASONS = {
    "INTENT_CHANGED": "구매 의사 취소",
    "COLOR_AND_SIZE": "색상 및 사이즈 변경",
}

#: 회수 방법 — **이 값 하나만 쓴다** (T8-S1).
#:
#: 실물 회수가 있어서가 아니다 — 시공 전 발송이라 고객 집에 간 물건 자체가 없고,
#: 반품은 주문(금액)만 움직인다. 이 값을 고정하는 이유는 **오발송을 막는 것**이다.
#:
#: 다른 코드(`RETURN_DESIGNATED`·`RETURN_DELIVERY`)를 보내면 **API 값이 무시되고
#: 상품정보에 설정된 택배사가 고객 집으로 자동 수거를 간다** — 우리가 부르지 않은
#: 택배차가 고객 집 앞에 서고, 되돌릴 수 없다. 그래서 다른 값은 **상수로도 두지 않는다**
#: (목록에 있으면 언젠가 누가 고른다).
#: 스테이징 실물 33건이 전부 이 값이고 송장번호는 한 건도 없다 — 네이버가 받는다는 관측이다.
RETURN_COLLECT_METHOD = "RETURN_INDIVIDUAL"

#: KST — 네이버는 발송일에 타임존이 붙은 ISO8601 을 요구한다.
KST = timezone(timedelta(hours=9))


class FulfillmentError(RuntimeError):
    """발주확인·발송처리 실패. 사유 문장을 그대로 사람에게 보여준다."""


def household_key(link: ExternalOrderLink) -> tuple[str, str, str]:
    """이 링크가 속한 '집' 키 — 화면이 집을 가르는 것과 **같은 규칙**.

    화면 큐(:func:`foms.web.admin.naver_ingest._group_queue`)는
    :func:`mapping.group_key` ``(주문번호, 수취인 전화, 주소)`` 로 집을 가른다.
    여기서 주문번호만 보면 **분할배송**(같은 주문번호·다른 주소)에서 화면이 두 줄로
    보여준 것을 워커가 한 번에 처리한다 — A집만 골랐는데 B집까지 네이버로 나가고,
    그 호출은 되돌릴 수 없다.

    Args:
        link: ``ExternalOrderLink`` 행.

    Returns:
        같은 값이면 같은 집. 원본이 깨져 키를 못 만들면 그 링크 혼자인 집으로 본다
        (화면과 같은 폴백 — 큐에서 조용히 사라지는 것보다 낫다).
    """
    from foms.services.integrations.naver_commerce.mapping import group_key

    try:
        key = group_key(link.raw_snapshot or {})
    except (ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.warning("[NAVER] 집 키 계산 실패(link %s): %s", link.id, exc)
        return ("__ungrouped__", str(link.id), "")
    if not any(part for part in key):
        # 원본이 비어 키가 통째로 빈 경우(예외는 안 난다) — 서로 다른 주문이 같은 키로
        # 붙어 한 집처럼 읽힌다. 그럴 땐 링크 단독으로 센다.
        return ("__ungrouped__", str(link.id), "")
    return key


def is_place_pending(link: ExternalOrderLink) -> bool:
    """이 상품주문에 **발주확인이 아직 남았는가** — 화면 재진술과 서버 처리의 공통 술어.

    :func:`confirm_place_order` 가 실제로 보낼 대상(``todo``)을 고르는 조건 그대로다.
    화면이 이 술어를 안 쓰고 집 전체 수로 재진술하면 "3건 보냅니다"라고 읽히는데 2건만
    나간다 — 계약 §0-2(모달 재진술 == 서버가 처리할 건수) 위반이다(2026-08-23 CEO 검수).

    판매자센터에서 손으로 확인한 건은 우리 상태 표식(``place_confirmed_at``)이 없고
    컬럼만 ``OK`` 라, 둘을 함께 본다.

    Args:
        link: 수집 링크.

    Returns:
        아직 발주확인이 안 된 건이면 True.
    """
    return not (_state(link).get("place_confirmed_at")
                or (link.place_order_status or "").strip().upper()
                in CONFIRMED_PLACE_STATUSES)


def _links_of_group(session: Session, link_id: int) -> list[ExternalOrderLink]:
    """같은 **집**의 링크 전부(한 집은 통째로 처리한다).

    1차로 같은 네이버 주문번호를 모으고(인덱스 있는 축), 그중 :func:`household_key` 가
    같은 것만 남긴다. 분할배송에서 화면이 가른 집과 서버가 처리하는 대상이 어긋나지 않게
    하는 자리다.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise FulfillmentError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    order_no = (link.external_order_no or "").strip()
    if not order_no:
        return [link]
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == CHANNEL,
                ExternalOrderLink.external_order_no == order_no)
        .order_by(ExternalOrderLink.id.asc())
        .all()
    )
    base_key = household_key(link)
    same_house = [row for row in rows if household_key(row) == base_key]
    return same_house or [link]


def links_of_group(session: Session, link_id: int) -> list[ExternalOrderLink]:
    """같은 **집**의 링크 전부 — 모듈 밖에서 쓰는 공개 이름.

    발주확인·발송처리·취소가 쓰는 집 판정(:func:`_links_of_group`)을 그대로 내보낸다.
    "다시 읽기"(T4)가 같은 집을 대상으로 삼아야 화면이 가른 집과 어긋나지 않는다 —
    집 판정을 부르는 쪽에서 다시 짜면 분할배송에서 남의 집이 섞인다.

    Args:
        session: DB 세션(읽기만 한다).
        link_id: 기준 수집 링크 id.

    Returns:
        같은 집의 링크 목록(수집 순서). 링크가 없으면 :class:`FulfillmentError`.
    """
    return _links_of_group(session, link_id)


def _claim_guard(session: Session, links: list[ExternalOrderLink], *,
                 action: str, stamp: datetime) -> None:
    """집 안에 진행 중인 클레임이 하나라도 있으면 네이버를 부르지 않는다.

    화면은 클레임 집을 잠그지만(집 단위), 화면만 믿으면 링크 id 를 아는 요청이 그대로
    통과한다. 발송처리는 구매자에게 "배송 시작"으로 보이고 되돌릴 수 없다 — 마지막 문을
    서버가 닫는다. 판정 기준은 화면과 같은 :func:`mapping.extract_claim` 이다.

    판정은 :func:`mapping.blocks_irreversible` 이다. 예전에는 ``claim["blocking"]`` 을 봤는데
    그 집합에 ``EXCHANGE_*`` 가 없어서 **교환이 도는 집에 불가역 반품 접수가 그대로
    나갔다** — 바로 아래 :func:`request_return` 이 주석으로 막는다고 적어 둔 경우다
    (R-4, 2026-08-28). ``blocking`` 은 "주문을 만들면 안 되는가"라 축이 다르다.

    **거절 사유를 상태에 남긴다.** web 은 enqueue 만 하고 즉시 "요청했습니다"로 답하므로,
    워커가 조용히 거절하면 사람은 보냈다고 믿는다 — 실패 띠가 유일한 통로다.

    Args:
        session: DB 세션.
        links: 한 집의 링크들.
        action: ``confirm`` / ``dispatch`` (화면 재시도가 이 값을 본다).
        stamp: 기록 시각.

    Raises:
        FulfillmentError: 클레임이 걸린 상품주문이 있을 때.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        blocks_irreversible, extract_claim,
    )

    for row in links:
        claim = extract_claim(row.raw_snapshot or {})
        if not blocks_irreversible(claim):
            continue
        reason = (f"취소·반품·교환이 걸린 주문입니다({claim.get('label') or '클레임'}) — "
                  "판매자센터에서 처리하세요.")
        _mark_failures({str(r.external_id): r for r in links},
                       {str(r.external_id): reason for r in links},
                       action=action, stamp=stamp)
        session.flush()
        raise FulfillmentError(reason)


#: 수집이 성공한 상태. 이 밖의 링크는 원본이 불완전할 수 있어 네이버로 보내지 않는다.
HEALTHY_SYNC_STATUSES = ("COLLECTED", "LINKED")


def _broken_collection_guard(session: Session, links: list[ExternalOrderLink], *,
                             action: str, stamp: datetime) -> None:
    """수집이 실패·보류된 상품주문이 섞인 집은 네이버를 부르지 않는다.

    화면(:func:`foms.web.admin.naver_ingest._place_groups`)이 ``FAILED``·``PENDING_REVIEW``
    를 목록에서 빼지만 **그건 화면일 뿐**이다. ``_links_of_group`` 은 상태를 안 보고,
    이력 탭의 '워크벤치' 링크는 ``PENDING_REVIEW`` 링크를 그대로 열어 준다 —
    그 집에서 발주확인 버튼이 열린다(2026-08-23 리뷰 H-B). 마지막 문은 서버가 닫는다.

    발주확인은 되돌릴 수 없다. 원본이 깨진 건을 네이버에 확정으로 보내면, 잘못 매핑된
    주문이 그대로 확정된다.

    Args:
        session: DB 세션.
        links: 한 집의 링크들.
        action: 화면 재시도가 보는 값(``confirm``).
        stamp: 기록 시각.

    Raises:
        FulfillmentError: 수집이 성공하지 않은 상품주문이 하나라도 있을 때.
    """
    broken = [row for row in links
              if (row.sync_status or "") not in HEALTHY_SYNC_STATUSES]
    if not broken:
        return
    reason = ("수집이 완료되지 않은 상품주문이 있는 건입니다"
              f"({', '.join(sorted({str(r.sync_status) for r in broken}))}) — "
              "수집을 먼저 정상화하세요.")
    _mark_failures({str(r.external_id): r for r in links},
                   {str(r.external_id): reason for r in links},
                   action=action, stamp=stamp)
    session.flush()
    raise FulfillmentError(reason)


def _cancel_guard(session: Session, links: list[ExternalOrderLink], *,
                  action: str, stamp: datetime) -> None:
    """집 안에 **우리가 취소한** 상품주문이 있으면 발주확인·발송처리를 보내지 않는다.

    :func:`_claim_guard` 로는 못 막는다 — 그건 ``raw_snapshot`` 의 네이버 클레임을 읽는데,
    우리가 방금 낸 취소는 **다음 수집 스윕 전까지 스냅샷에 없다**. 그 사이 발송처리를 누르면
    취소한 상품주문에 되돌릴 수 없는 호출이 나간다(2026-08-23 리뷰 [치명]).

    한 건이라도 취소됐으면 **집 전체**를 막는다. 부분 취소 실패는 남은 건을 발송할 상황이
    아니라 취소를 다시 보낼 상황이다.

    Args:
        session: DB 세션.
        links: 한 집의 링크들.
        action: ``confirm`` / ``dispatch`` (화면 재시도가 이 값을 본다).
        stamp: 기록 시각.

    Raises:
        FulfillmentError: 취소된 상품주문이 있을 때.
    """
    canceled = [row for row in links if _state(row).get("canceled_at")]
    if not canceled:
        return
    reason = ("취소한 주문입니다 — 발주확인·발송처리를 보내지 않습니다"
              f"(취소된 상품주문 {len(canceled)}건).")
    _mark_failures({str(row.external_id): row for row in links},
                   {str(row.external_id): reason for row in links},
                   action=action, stamp=stamp)
    session.flush()
    raise FulfillmentError(reason)


def _state(link: ExternalOrderLink) -> dict[str, Any]:
    """링크의 fulfillment 상태(없으면 빈 dict)."""
    state = link.triage_state if isinstance(link.triage_state, dict) else {}
    value = state.get(STATE_KEY)
    return dict(value) if isinstance(value, dict) else {}


def _write_state(link: ExternalOrderLink, patch: dict[str, Any]) -> None:
    """fulfillment 상태를 병합 저장한다(다른 축은 건드리지 않는다)."""
    state = copy.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    current = dict(state.get(STATE_KEY) or {})
    current.update(patch)
    state[STATE_KEY] = current
    link.triage_state = state
    flag_modified(link, "triage_state")


def _dispatch_timestamp(now: datetime) -> str:
    """네이버가 요구하는 발송일 형식(ISO8601 밀리초 + 타임존)."""
    kst = now.replace(tzinfo=timezone.utc).astimezone(KST) if now.tzinfo is None else now.astimezone(KST)
    return kst.strftime("%Y-%m-%dT%H:%M:%S.") + f"{kst.microsecond // 1000:03d}" + kst.strftime("%z")[:3] + ":" + kst.strftime("%z")[3:]


def _split_result(payload: Any, ids: list[str]) -> tuple[list[str], dict[str, str]]:
    """네이버 200 응답을 **건별 성공/실패**로 가른다.

    커머스API 는 HTTP 200 을 주면서 body 안에 건별 실패를 담는다
    (``failProductOrderInfos``). 그걸 안 보면 실패한 상품주문에도 성공 도장이 찍히고,
    멱등 규칙 때문에 **다시는 보내지지 않는다** — 조용한 미발송이 된다.

    모르는 모양의 응답(성공 목록 키도 실패 목록 키도 없는 body)은 예전처럼 전부 성공으로
    본다. 판단 근거가 없는데 실패로 몰면 이미 나간 호출을 사람이 다시 보내게 된다.

    Args:
        payload: 클라이언트가 돌려준 응답 payload.
        ids: 이번 호출로 보낸 상품주문번호 목록.

    Returns:
        ``(성공한 id 목록, {실패한 id: 사유})``.
    """
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        data = payload if isinstance(payload, dict) else {}

    failures: dict[str, str] = {}
    #: 상품주문번호가 없어 어느 건인지 모르는 실패 항목의 사유. 버리면 "실패 목록이 없다"가
    #: 되어 전부 성공 도장이 찍히고, 멱등 규칙 때문에 영영 재발송되지 않는다.
    unattributed: list[str] = []
    for row in (data.get("failProductOrderInfos") or []):
        if not isinstance(row, dict):
            continue
        reason = str(row.get("message") or row.get("failMessage")
                     or row.get("reason") or "네이버가 실패로 처리했습니다.")[:500]
        pid = str(row.get("productOrderId") or "").strip()
        if not pid:
            unattributed.append(reason)
            continue
        failures[pid] = reason

    raw_success = data.get("successProductOrderIds")
    if raw_success is None:
        infos = data.get("successProductOrderInfos")
        if isinstance(infos, list):
            raw_success = [row.get("productOrderId") for row in infos if isinstance(row, dict)]
    if isinstance(raw_success, list):
        reported_ok = {str(x) for x in raw_success if x}
        for pid in ids:
            # 성공 목록에도 실패 목록에도 없는 건 = 네이버가 처리했다고 말하지 않은 건.
            if pid not in reported_ok and pid not in failures:
                # 무기명 실패 사유가 함께 왔으면 그걸 붙인다 — 네이버가 준 진단을 버리면
                # 사람이 무엇을 고쳐야 하는지 알 수 없다.
                extra = ("; ".join(unattributed))[:400]
                failures[pid] = ("네이버가 성공 목록에 넣지 않았습니다."
                                 + (f" 사유: {extra}" if extra else ""))
    elif unattributed:
        # 실패는 왔는데 어느 건인지 모르고 성공 목록도 없다 — 누가 됐는지 알 수 없으므로
        # 아무에게도 성공 도장을 찍지 않는다(사람이 사유를 보고 다시 보낸다).
        # 무엇이 처리됐는지 알 수 없다. 성공 도장을 찍으면 진짜 안 나간 건이 영영 묻히고,
        # 안 찍으면 재시도가 이미 나간 건을 다시 부를 수 있다. 되돌릴 수 없는 쪽(미발송)을
        # 피하는 대신, 재시도 전에 판매자센터를 확인하라고 사유에 적는다.
        detail = "; ".join(unattributed)[:400]
        for pid in ids:
            if pid not in failures:
                failures[pid] = (f"네이버가 실패를 알렸으나 상품주문번호가 없습니다: {detail} "
                                 "— 다시 보내기 전에 판매자센터에서 처리 상태를 확인하세요.")
    elif not failures:
        return list(ids), {}

    return [pid for pid in ids if pid not in failures], failures


def _mark_failures(rows: dict[str, ExternalOrderLink], failures: dict[str, str],
                   *, action: str, stamp: datetime) -> None:
    """실패한 상품주문에 사유를 남긴다 — **어느 작업**이 실패했는지 함께.

    화면의 '실패한 집만 다시 시도' 가 이 값을 보고 같은 작업으로 재시도한다. 없으면
    발송처리 실패를 발주확인으로 재시도하게 되고, 그건 멱등 규칙에 걸려 조용히 넘어간 뒤
    실패 띠만 영원히 남는다.
    """
    for pid, reason in failures.items():
        row = rows.get(pid)
        if row is None:
            continue
        _write_state(row, {"last_error": reason, "last_error_at": stamp.isoformat(),
                           "last_error_action": action})


def confirm_place_order(session: Session, client: Any, *, link_id: int,
                        actor_user_id: Optional[int] = None,
                        now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발주확인 처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: :class:`~...client.NaverCommerceClient`.
        link_id: 기준 링크 id.
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"confirmed": [...], "skipped": [...]}`` — 이미 처리된 건은 skipped.

    Raises:
        FulfillmentError: 링크가 없거나 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="confirm", stamp=stamp)
    _cancel_guard(session, links, action="confirm", stamp=stamp)
    _broken_collection_guard(session, links, action="confirm", stamp=stamp)
    # 컬럼(place_order_status)도 함께 본다 — 판매자센터에서 손으로 발주확인한 형제를
    # 다시 보내면 네이버가 그 건을 실패로 돌려주고, 정상인데 빨간 띠가 남는다.
    # (발송처리 쪽 not_confirmed 판정은 이미 둘을 함께 본다.)
    todo = [row for row in links if is_place_pending(row)]
    # 이미 발주확인이 끝난 건에 낡은 실패 사유가 남아 있으면 지운다. 판매자센터에서 손으로
    # 처리한 집은 우리 재전송이 성공할 일이 없어, 안 지우면 빨간 띠가 영구히 남는다
    # (예전에는 재전송 성공이 지워 주던 자가치유 경로다).
    healed = False
    for row in links:
        if row in todo:
            continue
        if str(_state(row).get("last_error") or "").strip():
            _write_state(row, {"last_error": "", "last_error_at": "", "last_error_action": ""})
            healed = True
    if healed:
        session.flush()
    if not todo:
        return {"confirmed": [], "skipped": [row.external_id for row in links]}

    ids = [str(row.external_id) for row in todo]
    by_id = {str(row.external_id): row for row in todo}
    try:
        response = client.confirm_place_orders(ids)
    except Exception as exc:  # noqa: BLE001 - 사유를 상태에 남기고 그대로 올린다
        _mark_failures(by_id, {pid: str(exc)[:500] for pid in ids},
                       action="confirm", stamp=stamp)
        session.flush()
        logger.warning("[NAVER] 발주확인 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발주확인에 실패했습니다: {exc}") from exc

    ok_ids, failures = _split_result(response, ids)
    _mark_failures(by_id, failures, action="confirm", stamp=stamp)
    for pid in ok_ids:
        row = by_id[pid]
        _write_state(row, {"place_confirmed_at": stamp.isoformat(),
                           "place_confirmed_by": actor_user_id,
                           "last_error": "", "last_error_at": "", "last_error_action": ""})
        # 화면 필터가 보는 사본도 같이 올린다(다음 스윕을 기다리지 않게).
        row.place_order_status = "OK"
    session.flush()
    if failures:
        # 성공분은 위에서 확정했다 — 워커가 이 예외에서 commit 하므로 그 표식은 남고,
        # 재시도는 실패한 상품주문만 다시 보낸다.
        logger.warning("[NAVER] 발주확인 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail = "; ".join(f"{pid}: {reason}" for pid, reason in failures.items())
        raise FulfillmentError(f"발주확인 일부가 실패했습니다: {detail}")
    logger.info("[NAVER] 발주확인 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"confirmed": ok_ids, "skipped": [row.external_id for row in links if row not in todo]}


def clear_failure(session: Session, *, link_id: int,
                  actor_user_id: Optional[int] = None,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집의 **실패 사유만** 지운다 (네이버를 부르지 않는다 — web 에서 돌아도 된다).

    실패 사유는 성공한 재시도가 지운다. 그런데 사람이 판매자센터에서 손으로 해결하거나
    네이버가 "이미 처리됨"으로 답하면 우리 쪽 기록은 영원히 남아, 화면 위 빨간 띠가
    모든 탭·모든 사용자에게 고정된다. 그 띠를 사람이 닫는 자리가 여기다.

    **성공 표식(``place_confirmed_at``·``dispatched_at``)은 건드리지 않는다** — 지우면
    멱등이 깨져 네이버를 두 번 부르게 된다. 누가 언제 닫았는지는 상태에 남긴다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 링크 id(같은 집 전체가 함께 지워진다 — 형제가 남으면 띠가 다시 뜬다).
        actor_user_id: 닫은 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"cleared": 지운 상품주문 수, "link_ids": [...]}``.

    Raises:
        FulfillmentError: 링크를 찾을 수 없을 때.
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    cleared = 0
    for row in links:
        if not str(_state(row).get("last_error") or "").strip():
            continue
        _write_state(row, {"last_error": "", "last_error_at": "", "last_error_action": "",
                           "failure_cleared_at": stamp.isoformat(),
                           "failure_cleared_by": actor_user_id})
        cleared += 1
    session.flush()
    logger.info("[NAVER] 실패 기록 지움 link=%s 건수=%d", link_id, cleared)
    return {"cleared": cleared, "link_ids": [row.id for row in links]}


def _naver_dispatched_at(link: ExternalOrderLink) -> str:
    """네이버 **원본이 말하는** 발송 시각 — 없으면 빈 문자열(2026-08-26 T5).

    멱등의 두 번째 신호다. 우리 표식(``dispatched_at``)은 **우리가 눌러서 나간 발송**만
    안다 — 판매자센터에서 사람이 직접 발송처리한 집은 우리 쪽에 아무 흔적이 없어서,
    지금까지 그 집에 두 번째 호출이 그대로 나갔다. 되돌릴 수 없는 호출이라
    "네이버가 400 으로 막아 주겠지"에 기대지 않는다(이 모듈 첫머리의 규율).

    Args:
        link: 판정할 링크(상품주문 1건).

    Returns:
        ``delivery.sendDate`` 원문(공백 제거). 원본에 배송 블록이 없거나 발송 전이면
        빈 문자열 — **없는 값을 지어내지 않는다**.
    """
    from foms.services.integrations.naver_commerce.mapping import extract_delivery

    return str(extract_delivery(link.raw_snapshot or {}).get("send_date") or "").strip()


def _naver_dispatched_text(value: str) -> str:
    """발송 시각 하나를 사람이 읽는 KST 문자열로 편다(못 읽으면 원문 그대로).

    이 문장은 실패 띠·폴링 응답을 타고 **사람 눈앞에 그대로** 간다. 시각이 없으면
    "이미 있습니다"만 남아 판매자센터에서 어느 건을 봐야 할지 모른다.

    Args:
        value: ``delivery.sendDate`` 원문(오프셋이 붙어 온다).

    Returns:
        ``YYYY-MM-DD HH:MM`` 문자열. 못 읽으면 **원문 그대로** — 못 읽었다고 지우면
        문장이 "발송 기록이 없다"고 거짓말한다.
    """
    from foms.services.datetime_kst import format_datetime_kst

    return format_datetime_kst(value, "%Y-%m-%d %H:%M") or value


def dispatch_order(session: Session, client: Any, *, link_id: int,
                   delivery_method: str = DIRECT_DELIVERY,
                   actor_user_id: Optional[int] = None,
                   now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 발송처리한다 (WORKER 실행).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id.
        delivery_method: 배송방법 코드(기본 자사 직접 전달).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"dispatched": [...], "skipped": [...]}``. ``skipped`` 에는 우리 표식으로
        이미 나간 건과 **네이버 원본이 이미 발송을 말하는 건**(:func:`_naver_dispatched_at`)
        이 함께 들어간다 — 둘 다 네이버로 호출이 나가지 않은 건이다.

    Raises:
        FulfillmentError: 링크가 없거나 (:data:`CLOSE_NOW_RELATIONS` 밖의 집인데 —
            신규·재결제) 발주확인 전이거나 네이버 호출이 실패했을 때. **보낼 것이
            네이버 기록 때문에 하나도 남지 않은 집**도 여기로 온다(아래 참조).
    """
    stamp = now or now_utc_naive()
    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="dispatch", stamp=stamp)
    _cancel_guard(session, links, action="dispatch", stamp=stamp)
    # 관계 판정은 **집 단위**다(화면 배지와 같은 규칙). 붙이기가 집 전체를 함께 붙이지만
    # 백필 전 데이터는 형제 일부만 값이 있어, 한 건만 보면 화면과 서버가 갈린다.
    # **all** 이다: attach 이후 수집된 형제는 server_default 'NEW' 로 들어와 관계가 섞인다.
    # any 로 두면 그 NEW 형제까지 발주확인 없이 발송된다(2026-08-23 리뷰 F7).
    close_now = bool(links) and all(
        (row.relation or "").upper() in CLOSE_NOW_RELATIONS for row in links)
    # 신규·재결제 집은 발주확인이 먼저다 — 실제 출고 전 발송처리는 구매자에게 "배송 시작"
    # 으로 보이고 구매확정·정산 시계를 먼저 돌린다. 재결제는 원 주문의 물건이 **나중에 한 번
    # 나가므로** 여기 해당한다(D1 개정 2026-08-24). 추가결제만 물건이 따로 나가지 않아
    # 확인 뒤 바로 닫는다 — 네이버도 발송처리에서 발주확인을 함께 처리한다.
    not_confirmed = [] if close_now else [
        row for row in links
        if not (_state(row).get("place_confirmed_at")
                or (row.place_order_status or "").upper() == "OK")]
    if not_confirmed:
        # 거절도 화면에 닿아야 한다 — web 은 enqueue 만 하고 이미 "요청했습니다"로 답했다.
        # 사유는 **막힌 건에만** 찍는다. 집 전체에 찍으면 이미 발주확인이 끝난 형제까지
        # 실패 목록에 집혀(_failure_rows) 멀쩡한 건이 빨갛게 뜬다.
        reason = "발주확인이 먼저입니다(발주확인 전 상품주문이 있습니다)."
        _mark_failures({str(row.external_id): row for row in not_confirmed},
                       {str(row.external_id): reason for row in not_confirmed},
                       action="dispatch", stamp=stamp)
        session.flush()
        raise FulfillmentError(reason)

    # 멱등 신호 두 벌(2026-08-26 T5). ①은 우리가 눌러서 나간 발송, ②는 판매자센터에서
    # 사람이 직접 보낸 발송이다. ②는 우리 쪽에 흔적이 없어 지금까지 그대로 두 번째 호출이
    # 나갔다 — 구매자에게 '배송 시작'이 다시 뜨고 되돌릴 수 없다.
    ours_done = [row for row in links if _state(row).get("dispatched_at")]
    naver_done = [row for row in links
                  if row not in ours_done and _naver_dispatched_at(row)]
    todo = [row for row in links if row not in ours_done and row not in naver_done]
    if not todo:
        if naver_done:
            # **조용히 성공으로 돌려주지 않는다.** web 은 enqueue 만 하고 이미
            # "요청했습니다"로 답했다 — 아무 표식도 안 바뀌면 화면은 그대로고, 사람에게는
            # "눌렀는데 아무 일도 안 났다"로 보여 한 번 더 누른다(불가역 경로에서 재클릭은
            # 그 자체가 사고 경로다). 우리 표식으로 끝난 집은 화면이 이미 '발송처리 완료'
            # 라고 말하므로 조용해도 되지만, 이 집은 화면에 아무 말이 없다.
            # 사유는 **막힌 건에만** 찍는다(위 not_confirmed 와 같은 규율) — 집 전체에
            # 찍으면 우리가 정상 발송한 형제까지 실패 목록에서 빨갛게 뜬다.
            # 시각은 **그 상품주문 것**을 적는다. 대표 하나의 시각을 형제에게 돌려 쓰면
            # 화면이 그 건에 대해 없는 사실을 말하게 된다(발송은 건별로 찍힌다).
            reasons = {
                str(row.external_id):
                    ("네이버에 이미 발송 기록이 있습니다"
                     f"({_naver_dispatched_text(_naver_dispatched_at(row))}) — "
                     "발송처리를 보내지 않았습니다. 판매자센터에서 확인하세요.")
                for row in naver_done
            }
            reason = reasons[str(naver_done[0].external_id)]
            _mark_failures({str(row.external_id): row for row in naver_done},
                           reasons, action="dispatch", stamp=stamp)
            session.flush()
            logger.warning("[NAVER] 발송처리 생략 link=%s 네이버 기록=%d건",
                           link_id, len(naver_done))
            raise FulfillmentError(reason)
        return {"dispatched": [], "skipped": [row.external_id for row in links]}
    if naver_done:
        # 일부만 걸린 집은 남은 건을 그대로 보낸다 — 실패가 아니라 **뺀 것**이다.
        # 여기서 실패 사유를 찍으면 정상 처리된 집에 빨간 띠가 남는다.
        logger.info("[NAVER] 발송처리에서 네이버 기록분 제외 link=%s 제외=%d건 발송=%d건",
                    link_id, len(naver_done), len(todo))

    ids = [str(row.external_id) for row in todo]
    by_id = {str(row.external_id): row for row in todo}
    payload = [{"productOrderId": pid,
                "deliveryMethod": delivery_method,
                "dispatchDate": _dispatch_timestamp(stamp)}
               for pid in ids]
    try:
        response = client.dispatch_product_orders(payload)
    except Exception as exc:  # noqa: BLE001
        _mark_failures(by_id, {pid: str(exc)[:500] for pid in ids},
                       action="dispatch", stamp=stamp)
        session.flush()
        logger.warning("[NAVER] 발송처리 실패 link=%s: %s", link_id, exc)
        raise FulfillmentError(f"발송처리에 실패했습니다: {exc}") from exc

    ok_ids, failures = _split_result(response, ids)
    _mark_failures(by_id, failures, action="dispatch", stamp=stamp)
    for pid in ok_ids:
        _write_state(by_id[pid], {"dispatched_at": stamp.isoformat(),
                                  "dispatched_by": actor_user_id,
                                  "delivery_method": delivery_method,
                                  "last_error": "", "last_error_at": "",
                                  "last_error_action": ""})
    session.flush()
    if failures:
        logger.warning("[NAVER] 발송처리 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail = "; ".join(f"{pid}: {reason}" for pid, reason in failures.items())
        raise FulfillmentError(f"발송처리 일부가 실패했습니다: {detail}")
    logger.info("[NAVER] 발송처리 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"dispatched": ok_ids,
            "skipped": [row.external_id for row in links if row not in todo]}


def record_task_failure(session: Session, *, link_id: int, action: str, reason: str,
                        now: Optional[datetime] = None) -> None:
    """워커가 서비스 **바깥에서** 죽었을 때 사유를 남긴다(클라이언트 생성 실패·인증 만료 등).

    web 은 enqueue 뒤 즉시 "요청했습니다"로 답한다. 서비스가 남기는 실패 사유가 유일한
    통지 경로인데, `FulfillmentError` 가 아닌 예외는 워커가 rollback 해서 아무 흔적이
    없었다 — 특히 취소는 재시도 버튼도 없다(2026-08-23 리뷰). 실패해도 조용하지 않게 한다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 링크 id.
        action: ``confirm`` / ``dispatch`` / ``cancel``.
        reason: 사람에게 그대로 보여줄 사유 문장.
        now: 시각 주입(테스트).
    """
    stamp = now or now_utc_naive()
    try:
        links = _links_of_group(session, link_id)
    except FulfillmentError:
        # 이 함수 자체가 **마지막 통지 경로**다. 여기서 조용히 돌아서면 워커가 죽은
        # 사실이 어디에도 안 남는다 — 화면은 "요청했습니다"로 멈춰 있고, 취소는
        # 재시도 버튼도 없다. 사유를 못 남기더라도 **못 남겼다는 것은 남긴다**.
        logger.warning("[NAVER] 실패 사유 기록 실패(집을 못 찾음) link=%s action=%s 사유=%s",
                       link_id, action, str(reason)[:200], exc_info=True)
        return
    _mark_failures({str(row.external_id): row for row in links},
                   {str(row.external_id): str(reason)[:500] for row in links},
                   action=action, stamp=stamp)


def cancel_order(session: Session, client: Any, *, link_id: int, reason: str,
                 detail: Optional[str] = None, actor_user_id: Optional[int] = None,
                 now: Optional[datetime] = None) -> dict[str, Any]:
    """한 집을 **판매자 직접취소** 한다 (WORKER 실행, 스펙 §3.4).

    네이버 취소는 상품주문 1건씩이라(배치 없음) 집을 돌며 부른다. 한 건이 실패해도 나머지는
    계속 부른다 — 반쪽만 취소된 채 사람이 사유를 못 보는 상태가 제일 나쁘다.

    **FOMS 주문은 건드리지 않는다.** 네이버 쪽만 취소한다. 주문 취소는 주문 화면의 일이고,
    두 곳에서 상태를 쓰면 SSOT 가 갈린다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id(같은 집 전체가 함께 처리된다).
        reason: 취소 사유 코드(:data:`CANCEL_REASONS` 안의 값).
        detail: 취소 상세 사유(선택, 500자).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"canceled": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 링크가 없거나, 사유 코드가 목록 밖이거나, 이미 발송처리한
            집이거나, 클레임이 도는 집이거나, 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    code = str(reason or "").strip().upper()
    if code not in CANCEL_REASONS:
        # 네이버가 모르는 코드는 400 으로 돌아온다. 되돌릴 수 없는 경로라 호출 전에 막는다.
        raise FulfillmentError(f"취소 사유 코드가 올바르지 않습니다 ({reason}).")

    links = _links_of_group(session, link_id)
    _claim_guard(session, links, action="cancel", stamp=stamp)

    # 발송처리가 나간 집은 취소가 아니라 반품 흐름이다(네이버도 거절한다).
    #
    # **신호를 둘 본다.** 우리 표식(``dispatched_at``)만 보면 **판매자센터에서 사람이 직접
    # 발송한 집**을 놓친다 — 우리 쪽에 흔적이 없어서다. 그 집에 취소를 보내면 되돌릴 수 없는
    # 경로에서 400 을 받아 보며 배우는 꼴이 되고, 화면은 이미 다른 자리(정리 띠·관계 블록)에서
    # 같은 집을 "반품 건"이라고 부르고 있었다. 발송처리·반품 접수·반품 승인은 이미 두 신호를
    # 보는데(:func:`_naver_dispatched_at` 사용처) 취소만 빠져 있던 자리다.
    dispatched = [row for row in links
                  if _state(row).get("dispatched_at") or _naver_dispatched_at(row)]
    if dispatched:
        reason_text = ("이미 발송처리한 주문입니다 — 취소가 아니라 반품으로 처리해야 합니다"
                       "(판매자센터).")
        _mark_failures({str(row.external_id): row for row in dispatched},
                       {str(row.external_id): reason_text for row in dispatched},
                       action="cancel", stamp=stamp)
        session.flush()
        raise FulfillmentError(reason_text)

    todo = [row for row in links if not _state(row).get("canceled_at")]
    if not todo:
        return {"canceled": [], "skipped": [row.external_id for row in links]}

    ok_ids: list[str] = []
    failures: dict[str, str] = {}
    by_id = {str(row.external_id): row for row in todo}
    for pid, row in by_id.items():
        try:
            response = client.request_cancel_product_order(pid, reason=code, detail=detail)
        except Exception as exc:  # noqa: BLE001 - 사유 문장을 그대로 사람에게 보여준다
            logger.warning("[NAVER] 취소 실패 link=%s po=%s: %s", link_id, pid, exc)
            failures[pid] = str(exc)[:500]
            continue
        # 커머스API 는 HTTP 200 안에 건별 실패를 담는다 — 발주확인·발송처리와 같은 파서를 쓴다.
        succeeded, failed = _split_result(response, [pid])
        failures.update(failed)
        ok_ids.extend(succeeded)

    for pid in ok_ids:
        _write_state(by_id[pid], {"canceled_at": stamp.isoformat(),
                                  "canceled_by": actor_user_id,
                                  "cancel_reason": code,
                                  "cancel_detail": (detail or "")[:500],
                                  "last_error": "", "last_error_at": "",
                                  "last_error_action": ""})
    _mark_failures(by_id, failures, action="cancel", stamp=stamp)
    session.flush()
    if failures:
        logger.warning("[NAVER] 취소 부분 실패 link=%s 실패=%d", link_id, len(failures))
        detail_text = "; ".join(f"{pid}: {why}" for pid, why in failures.items())
        raise FulfillmentError(f"취소 일부가 실패했습니다: {detail_text}")
    logger.info("[NAVER] 취소 완료 link=%s 건수=%d", link_id, len(ok_ids))
    return {"canceled": ok_ids,
            "skipped": [row.external_id for row in links if row not in todo]}


def _return_state(link: ExternalOrderLink) -> dict[str, Any]:
    """``triage_state['return']`` 을 준다(없으면 빈 dict) — T8-S1 자기표식.

    ``fulfillment`` 축과 **다른 키**를 쓴다. 발송처리 상태와 반품 접수 상태는 서로
    다른 축이고, 한 dict 에 섞으면 `clear_failure` 같은 기존 조작이 반품 표식을
    같이 지운다.

    Args:
        link: 읽을 링크.

    Returns:
        반품 축 상태 dict(사본이 아니라 읽기용 참조).
    """
    state = link.triage_state or {}
    value = state.get("return")
    return value if isinstance(value, dict) else {}


def _write_return_state(link: ExternalOrderLink, patch: dict[str, Any]) -> None:
    """``triage_state['return']`` 에 patch 를 병합한다 (JSONB 수정 규약).

    Args:
        link: 쓸 링크.
        patch: 병합할 키/값.
    """
    state = copy.deepcopy(link.triage_state or {})
    bucket = state.get("return")
    if not isinstance(bucket, dict):
        bucket = {}
    bucket.update(patch)
    state["return"] = bucket
    link.triage_state = state
    flag_modified(link, "triage_state")



def is_return_pending(link: ExternalOrderLink) -> bool:
    """이 상품주문에 **반품 접수를 보낼 것인가** — 화면 재진술과 서버 처리의 공통 술어.

    :func:`request_return` 이 실제로 보낼 대상(``todo``)을 고르는 조건 그대로다.
    :func:`is_place_pending` 과 같은 이유로 여기 한 벌만 둔다 — 화면이 집 전체 수로
    재진술하면 "3건 반품 접수합니다"라고 읽히는데 서버는 발송된 1건만 보낸다.
    **불가역 경로라 그 과대 진술이 그대로 사고다**(계약 §0-2, 2026-08-27 CEO 지적).

    두 조건이다:

    - **나간 물건이어야 한다.** 안 나간 것은 반품이 아니라 취소다. 우리 표식과 네이버
      원본(``delivery.sendDate``)을 함께 본다 — 판매자센터에서 손으로 발송한 건은
      우리 표식이 없다.
    - **아직 우리가 접수하지 않았어야 한다.** 멱등은 우리 표식으로만 판정한다.
      네이버 ``requestChannel`` 은 API 접수분과 판매자센터 수동분을 갈라 주지 않는다.

    Args:
        link: 수집 링크.

    Returns:
        반품 접수를 보낼 건이면 True.
    """
    dispatched = bool(_state(link).get("dispatched_at") or _naver_dispatched_at(link))
    return dispatched and not _return_state(link).get("requested_at")

#: 반품 **승인**을 걸 수 있는 클레임 상태. 이 밖이면 부르지 않는다.
#:
#: 접수 직후에는 네이버 쪽 상태가 아직 안 넘어와 있을 수 있다. 그때 승인을 부르면
#: 400 이 나는데, 불가역 경로에서 400 을 받아 보고 배우지 않는다 — 상태를 먼저 읽고 건다.
#: 수거중·수거완료가 함께 있는 이유: 실물이 없는 우리 반품은 접수 직후 네이버가
#: `collectCompletedDate` 를 `returnCompletedDate` 와 같은 시각으로 찍고 지나간다
#: (운영 25건 전수 관측). 그 순간을 통과하는 건을 상태만 보고 막으면 안 된다.
RETURN_APPROVABLE_STATUSES = ("RETURN_REQUEST", "RETURN_REQUESTED",
                              "COLLECTING", "COLLECT_DONE")


def _approve_returns(client: Any, by_id: dict[str, ExternalOrderLink],
                     pids: list[str], *, stamp: datetime,
                     actor_user_id: Optional[int], link_id: int) -> list[str]:
    """접수 성공분을 **승인**한다 — 환불 확정 (T8-S2).

    건마다 **상세를 다시 읽고** 두 가지를 본 뒤에만 부른다:

    * **보류(`holdbackStatus`)가 걸려 있으면 승인하지 않는다.** 네이버는 보류가 걸린 건의
      승인을 막고, 우리는 **보류를 풀지 않는다** — 반품안심케어 건은 보류해제 자체가
      금지이고(공식), 해제가 반품비를 0원으로 초기화하는 갈래도 있다. 사람이
      판매자센터에서 판단할 일이다. (운영 25건 전수에 보류는 0건이고 사용자도 "한 번도
      걸린 적 없다"고 했다 — 그래서 **주 경로가 아니라 가드**다.)
    * 클레임 상태가 :data:`RETURN_APPROVABLE_STATUSES` 안이어야 한다.

    **여기서 기다리지 않는다.** 상태가 아직 안 넘어왔으면 그대로 두고 사유를 남긴다.
    sleep 루프를 돌면 워커를 점유하고, 실패를 "성공한 것처럼" 늦춘다. 접수는 이미 됐으니
    사람이 나중에 승인만 다시 누르면 된다 — 화면이 `승인 남음` 과 사유를 말한다.

    Args:
        client: 네이버 클라이언트.
        by_id: ``productOrderId`` → 링크 행.
        pids: 접수에 성공한 상품주문번호 목록.
        stamp: 이번 작업 시각.
        actor_user_id: 누른 사람.
        link_id: 기준 링크 id(로그용).

    Returns:
        승인에 성공한 ``productOrderId`` 목록.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        extract_claim,
        extract_claim_holdback,
        extract_external_id,
    )

    try:
        details = client.get_product_orders(pids)
    except Exception as exc:  # noqa: BLE001 - 못 읽으면 승인하지 않는다(사유는 남긴다)
        logger.error("[NAVER] 승인 전 재조회 실패 link=%s: %s", link_id, exc, exc_info=True)
        for pid in pids:
            _write_return_state(by_id[pid],
                                {"approve_skipped_reason": f"상태를 다시 읽지 못했습니다: {exc}"[:500]})
        return []

    by_pid = {extract_external_id(d): d for d in (details or []) if isinstance(d, dict)}
    approved: list[str] = []
    for pid in pids:
        row = by_id[pid]
        detail = by_pid.get(pid)
        if detail is None:
            _write_return_state(row, {"approve_skipped_reason": "승인 전 상태를 읽지 못했습니다."})
            continue
        holdback = extract_claim_holdback(detail)
        if holdback.get("holdback_status"):
            _write_return_state(row, {
                "approve_skipped_reason": (
                    f"네이버가 보류를 걸어 둔 건입니다({holdback['holdback_status']}) — "
                    "판매자센터에서 처리하세요. 보류 해제는 FOMS 가 하지 않습니다."),
                "holdback_status": holdback["holdback_status"],
                "holdback_block": holdback.get("holdback_block"),
            })
            logger.warning("[NAVER] 보류 걸린 건이라 승인 안 함 link=%s pid=%s status=%s",
                           link_id, pid, holdback["holdback_status"])
            continue
        status = str(extract_claim(detail).get("status") or "")
        if status not in RETURN_APPROVABLE_STATUSES:
            _write_return_state(row, {
                "approve_skipped_reason": (
                    f"승인할 수 있는 상태가 아닙니다(지금 {status or '알 수 없음'}) — "
                    "잠시 뒤 다시 승인하세요."),
            })
            continue
        try:
            response = client.approve_return_product_order(pid)
        except Exception as exc:  # noqa: BLE001 - 사유를 사람에게 그대로 보여준다
            _write_return_state(row, {"approve_skipped_reason": f"승인 실패: {exc}"[:500]})
            logger.error("[NAVER] 반품 승인 실패 link=%s pid=%s: %s", link_id, pid, exc,
                         exc_info=True)
            continue
        ok, fails = _split_result(response, [pid])
        if ok:
            _write_return_state(row, {"approved_at": stamp.isoformat(),
                                      "approved_by": actor_user_id,
                                      "approve_skipped_reason": ""})
            approved.extend(ok)
        for failed_pid, why in fails.items():
            _write_return_state(by_id[failed_pid],
                                {"approve_skipped_reason": f"승인 실패: {why}"[:500]})
    return approved


def request_return(session: Session, client: Any, *, link_id: int, reason: str,
                   detail: Optional[str] = None, actor_user_id: Optional[int] = None,
                   now: Optional[datetime] = None,
                   approve: bool = False) -> dict[str, Any]:
    """한 집의 **반품을 판매자가 접수**한다 (WORKER 실행, T8-S1).
    ``approve=True`` 면 접수 성공분을 **이어서 승인**한다 (T8-S2).

    취소와 같은 모양이다 — 네이버 반품 접수는 상품주문 1건씩이라 집을 돌며 부르고,
    한 건이 실패해도 나머지는 계속 부른다. 반쪽만 접수된 채 사람이 사유를 못 보는
    상태가 제일 나쁘다.

    **되돌릴 수 없다.** 접수하면 구매자에게 반품 진행이 보이고, 커머스API 로는 수거
    정보를 다시 바꿀 수 없다. ``approve=True`` 면 **환불까지 확정된다** — 그쪽은 되돌리는
    엔드포인트조차 없다.

    승인을 여기 붙인 이유(2026-08-31): 접수만 하고 승인은 판매자센터로 가야 하면 사람이
    두 군데를 왕복한다. 운영 실측이 그걸 보여줬다 — 접수 기능 실호출 **0회**인데 같은
    기간 사람은 판매자센터에서 **9건을 접수+승인 한 번에** 처리했다(22~60초).

    **FOMS 주문은 건드리지 않는다.** 네이버 쪽만 접수한다 — 취소와 같은 규율이다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id(같은 집 전체가 함께 처리된다).
        reason: 반품 사유 코드(:data:`RETURN_REASONS` 안의 값).
        detail: 반품 상세 사유(선택, 500자).
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"returned": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 링크가 없거나, 사유 코드가 목록 밖이거나, **아직 발송처리가
            안 된 집**이거나, 클레임이 이미 도는 집이거나, 네이버 호출이 실패했을 때.
    """
    stamp = now or now_utc_naive()
    code = str(reason or "").strip().upper()
    if code not in RETURN_REASONS:
        # 목록 밖 코드는 400 이다. 불가역 경로라 호출 전에 막는다(취소와 같은 규율).
        raise FulfillmentError(f"반품 사유 코드가 올바르지 않습니다 ({reason}).")

    links = _links_of_group(session, link_id)
    # 이미 클레임(취소·반품·교환)이 도는 집에 반품을 또 걸지 않는다.
    _claim_guard(session, links, action="return", stamp=stamp)

    # **발송 전이면 반품이 아니라 취소다** — `cancel_order` 의 거울상 가드.
    # 안 나간 물건을 반품으로 접수하면 구매자에게 없는 배송이 되돌아오는 것으로 보인다.
    dispatched = [row for row in links
                  if _state(row).get("dispatched_at") or _naver_dispatched_at(row)]
    if not dispatched:
        reason_text = ("아직 발송처리가 안 된 주문입니다 — 반품이 아니라 "
                       "취소로 처리해야 합니다.")
        _mark_failures({str(row.external_id): row for row in links},
                       {str(row.external_id): reason_text for row in links},
                       action="return", stamp=stamp)
        session.flush()
        raise FulfillmentError(reason_text)

    # 멱등 + **행 단위** 발송 판정 (2026-08-27 CEO). 위 가드는 "집에 발송분이 하나라도
    # 있는가"만 본다 — 분할발송이라 집 안에서 나간 것과 안 나간 것이 섞이는데, 거기서
    # 집 단위로만 통과시키면 **안 나간 상품주문에도 반품 요청이 나간다**(불가역).
    # 그래서 실제로 보낼 목록은 **그 행이 나갔는지**로 다시 거른다 —
    # 술어는 :func:`is_return_pending` 한 벌이고 화면도 같은 것을 센다.
    #
    # 멱등은 우리 표식으로만 판정한다 — 네이버 `requestChannel` 은 API 접수분과
    # 판매자센터 수동분을 갈라 주지 않는다(문서가 보증하지 않는 값에 불가역 경로를 걸지 않는다).
    todo = [row for row in links if is_return_pending(row)]
    if not todo:
        return {"returned": [], "skipped": [row.external_id for row in links]}

    ok_ids: list[str] = []
    failures: dict[str, str] = {}
    by_id = {str(row.external_id): row for row in todo}
    for pid, row in by_id.items():
        try:
            response = client.request_return_product_order(
                pid, reason=code, collect_method=RETURN_COLLECT_METHOD, detail=detail)
        except Exception as exc:  # noqa: BLE001 - 사유를 사람에게 그대로 보여준다
            failures[pid] = str(exc)[:500]
            logger.error("[NAVER] 반품 접수 실패 link=%s pid=%s: %s", link_id, pid, exc,
                         exc_info=True)
            continue
        ok, fails = _split_result(response, [pid])
        ok_ids.extend(ok)
        failures.update(fails)

    for pid in ok_ids:
        _write_return_state(by_id[pid], {
            "requested_at": stamp.isoformat(),
            "requested_by": actor_user_id,
            "reason": code,
            "collect_method": RETURN_COLLECT_METHOD,
        })
    if failures:
        _mark_failures(by_id, failures, action="return", stamp=stamp)
    session.flush()

    approved: list[str] = []
    if approve and ok_ids:
        # **접수에 성공한 건만** 승인한다. 실패한 건은 네이버에 반품 요청 자체가 없다.
        approved = _approve_returns(client, by_id, ok_ids, stamp=stamp,
                                    actor_user_id=actor_user_id, link_id=link_id)
        session.flush()

    if failures and not ok_ids:
        detail_text = "; ".join(f"{pid}: {why}" for pid, why in failures.items())
        raise FulfillmentError(f"반품 접수가 실패했습니다 — {detail_text}")
    logger.info("[NAVER] 반품 접수 link=%s 성공=%d 실패=%d 승인=%d", link_id, len(ok_ids),
                len(failures), len(approved))
    return {"returned": ok_ids, "approved": approved,
            "skipped": [pid for pid in failures]}


#: 반품 **거부**를 걸 수 있는 클레임 상태 (T8-S3).
#:
#: **문서가 정한 값이다**(커머스API 공개 문서 2026-09-01 원문): 거부 endpoint 는
#: "반품요청·수거중 상태를 반품철회로 전이"시킨다. 상태 흐름도의 R-2(거부) 분기도
#: 1단계 ``RETURN_REQUEST`` 또는 ``COLLECTING`` 에서만 갈라진다. ``RETURN_REQUESTED``
#: 는 읽기 쪽 별칭이다(:data:`mapping.CLAIM_STATUS_LABELS` 에 이미 있다).
#:
#: 승인(:data:`RETURN_APPROVABLE_STATUSES`)보다 여전히 **좁다** — ``COLLECT_DONE``
#: (수거 완료)은 넣지 않는다. 문서 서술이 거부 용례로 "회수된 상품에 문제"를 들긴 하지만
#: **상태 전이를 규정한 문장과 흐름도는 둘 다 수거완료를 거부 출발점으로 적지 않는다.**
#: 불가역 경로에서는 서술이 아니라 규정 문장을 따른다 — 400 을 받아 보며 배우지 않는다.
RETURN_REJECTABLE_STATUSES = ("RETURN_REQUEST", "RETURN_REQUESTED", "COLLECTING")

#: 거부 사유 문장 상한. **여전히 네이버 제한이 아니라 우리 상한이다.**
#: 2026-09-01 공개 문서 원문에도 ``rejectReturnReason`` 의 길이 제한이 **없다**
#: (타입 string·필수만 적혀 있다). 상한이 문서에 없는 것이 확인된 것이라, 취소·반품
#: 상세사유와 같은 500 자를 보수적으로 유지한다.
RETURN_REJECT_REASON_MAX = 500

#: 자주 쓰는 거부 문장 — **채워 넣기만 한다**(사용자 결정 2026-08-31: 문안은 자유 입력).
#:
#: 강제하지 않는 이유: 담당자가 자유 입력을 골랐다. 그래도 매번 처음부터 쓰게 두면 오타와
#: 감정 섞인 문장이 그대로 구매자에게 간다 — 되돌릴 수 없다. 그래서 버튼을 누르면 입력칸에
#: 들어가고 **그 자리에서 고칠 수 있게** 한다.
#:
#: 상황 5종은 사용자가 지목한 실제 업무다(제작 착수·시공 완료·사용 파손·기간 경과·실측 후).
#: **문장 자체는 초안이다** — 주문제작품 청약철회 제한은 조건이 걸리는 영역이라
#: 운영에 켜기 전에 사용자가 확정한다(설계서 §7 Q1).
RETURN_REJECT_FILLS = (
    {"label": "제작 착수",
     "text": "주문하신 상품은 고객님 치수에 맞춰 이미 제작에 들어가 재판매가 불가능하여 "
             "반품이 어렵습니다."},
    {"label": "시공 완료",
     "text": "시공이 완료된 건으로 원상 복구가 불가능하여 반품이 어렵습니다."},
    {"label": "사용·파손",
     "text": "제품에 사용·파손 흔적이 확인되어 반품 조건에 해당하지 않습니다."},
    {"label": "기간 경과",
     "text": "반품 가능 기간이 지나 단순 변심에 의한 반품이 어렵습니다."},
    {"label": "실측 후",
     "text": "실측 방문이 완료된 건으로 방문 비용이 발생하여 단순 변심에 의한 반품이 "
             "어렵습니다."},
)


def is_return_rejectable(link: ExternalOrderLink) -> bool:
    """이 상품주문에 **반품 거부를 보낼 것인가** — 화면과 서버의 공통 술어 (T8-S3).

    :func:`reject_return` 이 실제로 보낼 대상을 고르는 조건 그대로다. 한 벌만 두는 이유는
    :func:`is_return_pending` 과 같다 — 화면이 집 전체 수로 재진술하면 "3건 거부합니다"로
    읽히는데 서버는 요청이 걸린 1건만 보낸다. **불가역 경로에서 그 과대 진술이 곧 사고다.**

    조건 셋:

    1. 클레임 상태가 :data:`RETURN_REJECTABLE_STATUSES` 안이다(반품 **요청**·**수거중**).
    2. **보류가 걸려 있지 않다.** 걸렸으면 우리가 풀지 않는다 — 안심케어 건은 보류해제
       자체가 금지다(승인과 같은 규율).
    3. 아직 우리가 **승인·거부하지 않았다.** 멱등은 우리 표식으로만 판정한다 —
       네이버 ``requestChannel`` 은 API 분과 판매자센터 수동분을 갈라 주지 않는다.

    Args:
        link: 수집 링크.

    Returns:
        거부를 보낼 건이면 True.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        extract_claim,
        extract_claim_holdback,
    )

    snapshot = link.raw_snapshot or {}
    status = str(extract_claim(snapshot).get("status") or "")
    if status not in RETURN_REJECTABLE_STATUSES:
        return False
    if extract_claim_holdback(snapshot).get("holdback_status"):
        return False
    state = _return_state(link)
    return not (state.get("rejected_at") or state.get("approved_at"))


def reject_return(session: Session, client: Any, *, link_id: int, reason: str,
                  actor_user_id: Optional[int] = None,
                  now: Optional[datetime] = None) -> dict[str, Any]:
    """고객이 낸 반품 요청을 **거부**한다 (WORKER 실행, T8-S3).

    접수·승인과 같은 모양이다 — 상품주문 1건씩이라 집을 돌며 부르고, 한 건이 실패해도
    나머지는 계속 부른다. 반쪽만 처리된 채 사람이 사유를 못 보는 상태가 제일 나쁘다.

    **되돌릴 수 없다.** 거부하면 구매자에게 거부 사실과 **이 문장이 그대로** 간다.
    그래서 문장은 상태와 감사 로그 양쪽에 원문으로 남긴다 — 분쟁이 나면 무엇을 보냈는가가
    유일한 방어선이다.

    **FOMS 주문은 건드리지 않는다**(접수·취소와 같은 규율). 주문 이력에 표식을 남기는 것은
    라우트의 일이다 — 여기서 하면 워커 실패 때 이력만 남는다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        client: 커머스API 클라이언트.
        link_id: 기준 링크 id(같은 집 전체가 함께 처리된다).
        reason: 구매자에게 그대로 전달되는 거부 사유 문장.
        actor_user_id: 누른 사람(기록용).
        now: 시각 주입(테스트).

    Returns:
        ``{"rejected": [...], "skipped": [...]}``.

    Raises:
        FulfillmentError: 사유 문장이 비었거나, 거부할 건이 하나도 없거나,
            네이버 호출이 전부 실패했을 때.
    """
    stamp = now or now_utc_naive()
    text = str(reason or "").strip()
    if not text:
        # 빈 문장으로 불가역 API 를 때리지 않는다(사유 코드 화이트리스트와 같은 자리).
        raise FulfillmentError("거부 사유 문장을 입력하세요 — 구매자에게 그대로 전달됩니다.")
    text = text[:RETURN_REJECT_REASON_MAX]

    links = _links_of_group(session, link_id)
    if not links:
        raise FulfillmentError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")

    # 술어는 화면과 **한 벌**이다. 여기서 다시 구현하면 재진술 건수와 처리 건수가 갈린다.
    todo = [row for row in links if is_return_rejectable(row)]
    if not todo:
        raise FulfillmentError(
            "거부할 반품 요청이 없습니다 — 이미 처리됐거나, 네이버가 보류를 걸어 둔 "
            "건입니다(보류는 판매자센터에서 처리하세요).")

    ok_ids: list[str] = []
    failures: dict[str, str] = {}
    by_id = {str(row.external_id): row for row in todo}
    for pid, row in by_id.items():
        try:
            response = client.reject_return_product_order(pid, reason=text)
        except Exception as exc:  # noqa: BLE001 - 사유를 사람에게 그대로 보여준다
            failures[pid] = str(exc)[:500]
            logger.error("[NAVER] 반품 거부 실패 link=%s pid=%s: %s", link_id, pid, exc,
                         exc_info=True)
            continue
        ok, fails = _split_result(response, [pid])
        ok_ids.extend(ok)
        failures.update(fails)

    for pid in ok_ids:
        _write_return_state(by_id[pid], {
            "rejected_at": stamp.isoformat(),
            "rejected_by": actor_user_id,
            # 보낸 문장 원문. 요약하지 않는다 — 분쟁에서 필요한 것은 요약이 아니다.
            "reject_reason": text,
        })
    if failures:
        _mark_failures(by_id, failures, action="return-reject", stamp=stamp)
    session.flush()

    if failures and not ok_ids:
        detail_text = "; ".join(f"{pid}: {why}" for pid, why in failures.items())
        raise FulfillmentError(f"반품 거부가 실패했습니다 — {detail_text}")
    logger.info("[NAVER] 반품 거부 link=%s 성공=%d 실패=%d", link_id, len(ok_ids),
                len(failures))
    return {"rejected": ok_ids, "skipped": [pid for pid in failures]}

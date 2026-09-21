"""네이버 결제가 **전부 취소된** ERP 주문 찾기 — 유령 주문 (R-2 · 2026-08-25).

왜 필요한가
-----------
고객이 네이버 주문을 취소하면 ``claim_watch`` 가 그 사실을 목격해 링크에 표시하고 담당자에게
알린다. 그런데 **그 결제로 만들어진 ERP 주문은 아무도 건드리지 않는다** — 주문 상태를 자동으로
바꾸지 않는 것이 규율이기 때문이다(그 자체는 옳다: 취소가 곧 주문 폐기는 아니다).

문제는 그 다음이다. 취소 뒤 재결제가 들어오면 담당자가 새 집을 붙이지만, **재결제가 안 오면**
그 ERP 주문은 살아 있는 채로 남는다. 결제는 취소됐는데 주문은 접수 상태다.
2026-08-25 스테이징 실조회에서 그런 주문이 **3건** 나왔다(#4467 원주현 2,451,500원 ·
#4462 박선미 · #4466 강재상). **어떤 화면도 이 사실을 말하지 않는다.**

판정 기준(스펙 D-3)
-------------------
* 붙어 있는 네이버 링크가 **1건 이상**이고
* 그 링크가 **전부** 클레임(취소·반품) 상태이며
* 주문이 아직 살아 있다(``deleted_at IS NULL``).

부분 취소는 제외한다 — 일부만 취소된 주문은 정상 진행 중일 수 있고, 그걸 유령이라 부르면
띠가 거짓말을 한다.

확정 전 클레임 (2026-08-28)
---------------------------
예전에는 판정이 "``claimStatus`` 가 비어 있지 않은가" 한 비트였다. 그래서 **승인 전 취소
요청**(``CANCEL_REQUEST``)이 확정 취소와 같은 칸에 들어갔고, 템플릿이 `" 완료"` 를 덧붙여
화면은 `취소 완료` 라고 말했다. 그 목록이 곧 폐기(soft delete) 허가증이라, 아직 살아 있을
수 있는 주문에 폐기 버튼이 열렸다(운영 ``link 79`` / 주문 ``#4998``).

이제 단계(:data:`mapping.CLAIM_PHASES`)를 본다:

* ``done`` — 네이버가 확정. 폐기 버튼을 연다.
* ``requested``·``in_progress`` — 확정 전. **목록에는 남기고**(담당자가 알아야 한다)
  버튼은 잠근다.
* ``rejected`` — 거부·철회는 **주문이 살아 있다는 뜻**이라 클레임으로 세지 않는다.

**자동으로 지우지 않는다.** 목록과 근거를 내놓고 사람이 고른다.

2026-09-07: 행과 pane 이 ``measure`` 키(``orders.measure_progress.judge_measure_progress``)를
함께 낸다 — 실측 전 취소와 실측 후 취소는 회수·정산·응대가 다르다. **표시 축일 뿐이라
모집단·``can_discard`` 판정은 이 값을 한 글자도 보지 않는다.**
"""

from __future__ import annotations

import copy
import logging
from typing import Any, Optional

from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_kst
from foms.services.integrations.naver_commerce.grouping import resolve_group_key
from foms.services.integrations.naver_commerce.link_mirror import snapshot_from_mirror
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_BLOCK_KEYS,
    CLAIM_KIND_LABELS,
    CLAIM_PHASE_DONE,
    CLAIM_PHASE_PROGRESS,
    CLAIM_PHASE_REQUESTED,
    MONEY_BACK_CLAIM_KINDS,
    RELATION_LABELS,
    RETURN_BLOCK_KEYS,
    claim_kind,
    extract_claim,
)
from foms.services.orders.erp_policy_constants import STAGE_LABELS
from foms.services.orders.measure_progress import judge_measure_progress
from foms.services.orders.soft_delete import read_order_trash
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)

__all__ = ["find_ghost_orders", "find_partial_claim_orders", "judge_order_discard",
           "stage_label", "GHOST_LIST_LIMIT", "PARTIAL_LIST_LIMIT",
           "PARTIAL_PENDING_PHASES", "DISCARDABLE_STATUSES", "GHOST_CLAIM_KINDS",
           "GHOST_PROJECTION_BLOCK_KEYS",
           "REPAY_EXPECTED_SD_KEY", "REPAY_EXPECTED_BLOCK_TEXT",
           "read_repay_expected", "set_repay_expected", "clear_repay_expected"]

#: 유령 모집단에 넣는 단계. ``rejected``(거부·철회)는 주문이 살아 있다는 뜻이라 뺀다.
GHOST_CLAIM_PHASES = (CLAIM_PHASE_DONE, CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS)

#: 유령 모집단에 넣는 **종류**. 단계만 보면 ``EXCHANGE_DONE`` 이 확정 취소와 같은 칸에
#: 들어가 살아 있는 주문에 폐기 버튼이 열린다(R-2, 2026-08-28). 이 모듈 docstring 이
#: 모집단을 "취소·반품"이라 적어 놓고 코드는 종류를 안 본 자리다.
GHOST_CLAIM_KINDS = MONEY_BACK_CLAIM_KINDS

#: 띠에서 펼쳐 보여줄 최대 건수. 더 많으면 사람이 못 훑는다(수는 배지가 말한다).
GHOST_LIST_LIMIT = 20

#: 부분 취소 띠(:func:`find_partial_claim_orders`)가 세는 단계 — **확정 전**만.
#: 확정된 부분 취소는 재결제로 이미 정리된 정상 모양이 대부분이다(운영 실조회 2026-09-21:
#: 죽은 집 + 살아 있는 집이 공존하는 주문 24건 중 확정 전은 1건). 나머지의 정리는 옛 주문
#: 정리 띠(``order_candidates.pending_origin_cleanup``)가 이미 말한다 — 같은 사실을 두 띠가
#: 외치면 둘 다 안 읽힌다.
PARTIAL_PENDING_PHASES = (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS)

#: 부분 취소 띠의 펼침 상한 — 유령 띠와 같은 수로 둔다(두 띠가 다른 규칙이면 헷갈린다).
PARTIAL_LIST_LIMIT = GHOST_LIST_LIMIT

#: `취소 처리`(soft delete) 를 **사유 없이** 바로 열어 주는 진행 단계.
#:
#: 실측 이후 단계는 방문 기록·치수가 붙어 있어 접으면 그 이력이 화면에서 사라진다.
#: 그래서 예전에는 이 목록 **밖이면 아예 못 접게** 막았는데, 그러면 결제가 확정 취소된
#: 죽은 주문이 실측·도면 대시보드에 영원히 남는다(#5088 이 그 사례다). 재결제 짝이
#: 없으면 승계할 곳도 없다.
#:
#: **사용자 결정 2026-09-02**: 단계 제한을 없애되, 이 목록 밖은 **관리자가 사유 문장을
#: 적어야** 접힌다. 휴지통은 복구되므로 잃는 것은 없고, 남는 것은 "왜 접었나"다.
DISCARDABLE_STATUSES = ("RECEIVED",)

#: 사람이 손으로 켜는 **재결제 예정** 표시가 사는 ``structured_data`` 키.
#:
#: 왜 사람이 켜는가: :func:`find_repay_candidate_links` 는 **이미 네이버 큐에 들어온 집**만
#: 짝으로 찾는다. 아직 결제가 안 들어온 건은 구조적으로 `짝 없음` 이라, 고객이 다시 결제하기로
#: 했다는 사실은 시스템이 알 수 없다 — 담당자만 안다(사용자 결정 2026-09-14).
REPAY_EXPECTED_SD_KEY = "naver_repay_expected"

#: 표시에 붙이는 메모 한 줄의 최대 길이.
REPAY_EXPECTED_NOTE_MAX = 200

#: 표시가 켜져 있을 때 화면에 나가는 **잠금 사유**.
#: 마침표를 찍지 않는다 — pane 템플릿이 ``{{ ghost_discard.discard_block }}.`` 로 붙인다
#: (다른 갈래와 같은 규칙).
REPAY_EXPECTED_BLOCK_TEXT = "재결제 예정으로 표시돼 있습니다 — 결제가 들어오면 저절로 풀립니다"


#: 유령 스캔의 축소 스냅샷이 남기는 **클레임 블록 키**. 손으로 적지 않고
#: :mod:`mapping` 에서 파생한다 — 블록 이름이 늘 때 여기만 옛 목록으로 남으면 얇은 경로가
#: "클레임 없음" 으로 갈린다(R-7 이 정확히 그 사고였다: `claimStatus` 가 top-level
#: `return` 에만 실려 오는 반품에서 얇은 경로와 두꺼운 경로의 판정이 달라졌다).
GHOST_PROJECTION_BLOCK_KEYS = tuple(dict.fromkeys(
    tuple(CLAIM_BLOCK_KEYS) + tuple(RETURN_BLOCK_KEYS) + ("currentClaim", "beforeClaim")))


def _ghost_snapshot_projection(session):
    """유령 스캔이 읽는 경로만 담은 **축소 스냅샷** SQL 식.

    :func:`find_ghost_orders` 는 주문에 붙은 링크를 **전부** 읽는다. 그런데 판정이 보는 것은
    클레임 블록과 결제 금액뿐이고, 나머지(제품명·옵션·주소·배송 이력)는 한 술어도 읽지 않는다.
    2026-09-13 운영 실측: 그 전량이 **1,958KB**, 축소하면 **290KB** 로 줄고 조회 시간이
    788ms → 167ms 가 됐다(같은 연결·같은 489행). 파이썬 판정 자체는 어느 쪽이든 2ms 다 —
    비용은 파싱이 아니라 **읽어 오는 양**이다.

    판정 함수는 한 줄도 갈라지지 않는다. 축소 문서를 ``raw_snapshot`` 자리에 그대로 넣으므로
    :func:`_claim_of` 와 :func:`_fold_link` 가 같은 경로를 읽는다 — 술어가 아니라 **입력만**
    얇게 한다(같은 규율의 선례가 `naver_ingest._snapshot_projection` 이다).

    ``COALESCE`` 는 ``unwrap_detail`` 의 평평한 응답 폴백을 옮긴 것이다(``productOrder`` 가
    dict 가 아니면 최상위에서 찾는다).

    Args:
        session: 요청 스코프 DB 세션(방언 판정용).

    Returns:
        SQL 식. PostgreSQL 이 아니면 ``raw_snapshot`` 컬럼 그대로 — 결과는 같고 비용만
        옛 값이다(SQLite 테스트 레인 보호).
    """
    from sqlalchemy import func

    bind = session.get_bind()
    if getattr(getattr(bind, "dialect", None), "name", "") != "postgresql":
        return ExternalOrderLink.raw_snapshot
    raw = ExternalOrderLink.raw_snapshot
    return func.jsonb_build_object(
        "order", func.jsonb_build_object("claimStatus", raw["order"]["claimStatus"]),
        "productOrder", func.jsonb_build_object(
            "claimStatus", func.coalesce(raw["productOrder"]["claimStatus"],
                                         raw["claimStatus"]),
            "claimType", func.coalesce(raw["productOrder"]["claimType"],
                                       raw["claimType"]),
            # 금액 축(`_fold_link` 의 `amount_total`). 표시 전용처럼 보이지만 띠 문장이
            # 이 합계를 말한다 — 빼면 얇은 경로의 금액이 항상 0 이 된다.
            # **COALESCE 를 쓰지 않는다**: `_fold_link` 는 `productOrder` 안만 보므로,
            # 최상위 폴백을 넣으면 평평한 응답에서 얇은 경로가 두꺼운 경로보다 큰 금액을
            # 낸다(계약 테스트가 이 차이를 잡았다). 여기서는 동치가 먼저다.
            "totalPaymentAmount", raw["productOrder"]["totalPaymentAmount"]),
        *[arg for key in GHOST_PROJECTION_BLOCK_KEYS for arg in (key, raw[key])],
    )


def _claim_of(snapshot: Any) -> tuple[str, str, str]:
    """상품주문 스냅샷의 클레임 **상태·단계·종류**.

    판정 규칙은 :func:`mapping.extract_claim` 한 곳에만 둔다 — 예전에는 이 파일이
    "비어 있지 않은가"를 따로 판정해 SSOT 밖에 술어가 한 벌 더 있었다(2026-08-28).

    Args:
        snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``(상태 원문, 단계, 종류)``. 클레임이 없으면 전부 빈 문자열. 모르는 상태면 단계가 빈
        문자열이고, **빈 단계는 ``done`` 이 아니다**(모르면 폐기 버튼을 열지 않는다).
        종류도 같은 규율이다 — 모르는 종류는 모집단에 넣지 않는다.
    """
    if not isinstance(snapshot, dict) or not snapshot:
        return "", "", ""
    try:
        claim = extract_claim(snapshot)
    except (ValueError, TypeError, AttributeError) as exc:  # 목록 보조라 흐름을 막지 않는다
        logger.warning("[NAVER] 유령 판정 클레임 추출 실패: %s", exc)
        return "", "", ""
    return (str(claim.get("status") or "").strip(), str(claim.get("phase") or ""),
            claim_kind(claim))


def stage_label(status: Any) -> str:
    """진행 단계 코드를 **사람이 읽는 한글**로 (:data:`STAGE_LABELS` 가 정본).

    화면과 라우트 오류 문장이 ``MEASURE`` 같은 enum 을 그대로 찍어 왔다. 담당자에게
    그 낱말은 코드지 단계가 아니다 — 사용자 결정 2026-09-04.

    Args:
        status: ``Order.status``.

    Returns:
        한글 라벨. 모르는 코드는 원문 그대로(빈 값이면 빈 문자열).
    """
    text = str(status or "")
    return STAGE_LABELS.get(text, text)


def read_repay_expected(order) -> Optional[dict[str, Any]]:
    """재결제 예정 표시 — 있으면 ``{"at","by","by_name","note"}`` dict, 없으면 ``None``.

    ``structured_data`` 가 dict 가 아니거나 값이 dict 가 아니면 ``None`` 이다.
    **모르면 없는 것으로 읽는다** — 모양이 깨진 값이 휴지통을 잠그면 화면에서 푸는 길이
    없어진다(표시를 푸는 버튼도 이 값으로 그려지기 때문이다).

    Args:
        order: ERP 주문 ORM 인스턴스.

    Returns:
        표시 dict 또는 ``None``.
    """
    data = getattr(order, "structured_data", None)
    if not isinstance(data, dict):
        return None
    mark = data.get(REPAY_EXPECTED_SD_KEY)
    return mark if isinstance(mark, dict) else None


def set_repay_expected(order, *, actor_user_id: int, actor_name: str = "",
                       note: str = "") -> dict[str, Any]:
    """재결제 예정 표시를 켠다 — 제자리 수정, **커밋은 호출자**.

    ``at`` 은 ISO 가 아니라 **KST 표시 문자열**(``"YYYY-MM-DD HH:MM"``)이다. 화면이 아무
    변환 없이 그대로 찍는다 — ISO naive 로 두면 시각 표시 함수가 그 값을 UTC 로 읽어
    9시간이 밀린다.

    Args:
        order: ERP 주문 ORM 인스턴스.
        actor_user_id: 표시한 사람의 사용자 id.
        actor_name: 표시한 사람의 이름(화면에 그대로 나간다).
        note: 메모 한 줄. 앞뒤 공백을 떼고 :data:`REPAY_EXPECTED_NOTE_MAX` 로 자른다.

    Returns:
        저장한 표시 dict 그대로.
    """
    mark = {
        "at": now_kst().strftime("%Y-%m-%d %H:%M"),
        "by": int(actor_user_id),
        "by_name": str(actor_name or ""),
        "note": str(note or "").strip()[:REPAY_EXPECTED_NOTE_MAX],
    }
    data = copy.deepcopy(order.structured_data or {})
    data[REPAY_EXPECTED_SD_KEY] = mark
    order.structured_data = data
    flag_modified(order, "structured_data")
    return mark


def clear_repay_expected(order) -> bool:
    """재결제 예정 표시를 지운다 — 지울 게 있었으면 ``True``.

    해제는 **키 삭제**다(빈 dict 를 남기지 않는다) — 화면과 라우트가 ``if sd.get(키)``
    한 비트로 읽는다.

    지울 게 없으면 **deepcopy 도 flag_modified 도 하지 않는다**: ``structured_data`` 는
    TOAST 에 사는 값이라 건드리는 것만으로 쓰기 비용이 든다. 자동 해제 지점이 부르는
    함수라 아무 일도 안 하는 호출이 압도적으로 많다.

    Args:
        order: ERP 주문 ORM 인스턴스.

    Returns:
        지웠으면 ``True``, 표시가 없었으면 ``False``(호출이 무해하다).
    """
    data = getattr(order, "structured_data", None)
    if not isinstance(data, dict) or REPAY_EXPECTED_SD_KEY not in data:
        return False
    new = copy.deepcopy(data)
    new.pop(REPAY_EXPECTED_SD_KEY, None)
    order.structured_data = new
    flag_modified(order, "structured_data")
    return True


def _new_bucket() -> dict[str, Any]:
    """주문 하나의 링크를 접어 담을 빈 버킷.

    Returns:
        빈 버킷 dict.
    """
    return {
        "link_count": 0, "canceled": 0, "amount_total": 0,
        "order_nos": [], "claim_labels": set(), "phases": set(), "kinds": set(),
        # 워크벤치 pane 으로 보낼 대표 링크. 띠에서 불가역 버튼을 누르게 하지
        # 않는 대신(같은 행에 휴지통 버튼과 환불 버튼이 나란히 서면 사고
        # 대기다), **판단 재료가 있는 자리로 보낸다**.
        "lead_link_id": None,
    }


def _fold_link(bucket: dict[str, Any], *, snapshot: Any, order_no: Any,
               link_id: Any) -> tuple[str, str, str]:
    """링크 한 줄을 버킷에 접는다 — 모집단 판정의 **유일한 셈법**.

    :func:`find_ghost_orders`(전 링크 스캔)와 :func:`judge_order_discard`(주문 1건)가
    이 함수 하나를 쓴다. 셈법이 두 벌이 되면 띠와 pane 이 같은 주문을 다르게 판정한다 —
    이 기능의 안전(살아 있는 추가결제 집이 있으면 모집단에서 빠진다)이 바로 그 셈법이다.

    Args:
        bucket: :func:`_new_bucket` 이 만든 버킷(제자리 수정).
        snapshot: ``ExternalOrderLink.raw_snapshot``.
        order_no: ``ExternalOrderLink.external_order_no``.
        link_id: ``ExternalOrderLink.id``.

    Returns:
        그 링크의 ``(클레임 상태 원문, 단계, 종류)``.
    """
    bucket["link_count"] += 1
    if bucket["lead_link_id"] is None:
        bucket["lead_link_id"] = int(link_id)
    claim, phase, kind = _claim_of(snapshot)
    if phase in GHOST_CLAIM_PHASES and kind in GHOST_CLAIM_KINDS:
        bucket["canceled"] += 1
        bucket["claim_labels"].add(claim)
        bucket["phases"].add(phase)
        bucket["kinds"].add(kind)
    product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
    if isinstance(product_order, dict):
        amount = product_order.get("totalPaymentAmount")
        if isinstance(amount, int):
            bucket["amount_total"] += amount
    text = str(order_no or "").strip()
    if text and text not in bucket["order_nos"]:
        bucket["order_nos"].append(text)
    return claim, phase, kind


def _discard_verdict(bucket: dict[str, Any], status: str, *,
                     repay_expected: bool = False) -> dict[str, Any]:
    """버킷 + 진행 단계 → **판정 3종과 표시 문구**.

    띠(:func:`find_ghost_orders`)와 pane(:func:`judge_order_discard`)이 같은 함수를 쓴다.

    판정 두 축을 분리한다(사용자 결정 2026-09-02·2026-09-04):

    * **열리는가** — 붙은 링크가 **전부** 확정 취소·반품일 때만 연다(돈 축).
    * **사유가 필요한가** — 접수 이후 단계는 관리자가 왜 접는지 적어야 한다(이력 축).
      잠그지는 않는다.

    Args:
        bucket: :func:`_fold_link` 로 접은 버킷.
        status: ``Order.status``.
        repay_expected: 사람이 켠 '재결제 예정' 표시가 있는가
            (:func:`read_repay_expected`). 있으면 휴지통을 잠근다.

    Returns:
        ``claim_kind``·``claim_phase``·``claim_text``·``can_discard``·
        ``discard_needs_reason``·``discard_block``·``status_label``.
        잠금 사유는 **살아 있는 결제 → 확정 전 → 재결제 표시** 순으로 고른다
        (사람이 먼저 알아야 할 사실이 앞이다).
    """
    # 반품과 취소를 한 낱말로 뭉치지 않는다 — 사람이 보는 사실이 다르다.
    # 판정 축은 ``claimType``(:func:`mapping.claim_kind`)이다. 예전에는 상태 이름
    # 접두어를 봐서 ``COLLECTING``·``COLLECT_DONE`` 이 **취소**로 떨어졌다(R-1).
    kind = CLAIM_KIND_LABELS.get(
        "RETURN" if "RETURN" in bucket["kinds"] else "CANCEL", "취소")
    phases = bucket["phases"]
    if phases == {CLAIM_PHASE_DONE}:
        claim_phase, claim_text = "done", f"{kind} 완료"
    elif CLAIM_PHASE_DONE in phases:
        claim_phase, claim_text = "mixed", f"{kind} — 확정 전 포함"
    elif phases:
        claim_phase, claim_text = "pending", f"{kind} 요청 — 확정 전"
    else:
        # 클레임이 하나도 없는 주문 — 띠에는 오지 않고 pane 에서만 온다.
        claim_phase, claim_text = "", ""
    # 붙은 링크가 **전부** 클레임일 때만 유령이다. 부분 취소는 정상 진행 중일 수 있고,
    # 살아 있는 추가결제 집이 붙어 있는 주문도 여기서 걸러진다 — 이 기능의 안전이다.
    whole = bool(bucket["link_count"]) and bucket["canceled"] == bucket["link_count"]
    # **확정된 취소에만** 폐기 버튼을 연다. 확정 전에 접으면 취소가 거부됐을 때
    # 살아 있어야 할 주문이 휴지통에 있다. 이 조건은 돈의 문제라 바뀌지 않는다.
    #
    # 사람이 켠 '재결제 예정' 표시도 같은 자리에서 잠근다(사용자 결정 2026-09-14).
    # 되돌릴 수 있는 표시라 문턱은 휴지통보다 낮다 — 표시를 풀면 다시 열린다.
    can_discard = whole and claim_phase == "done" and not repay_expected
    if not whole:
        # 문장은 부르는 쪽이 사실(건수·살아 있는 집)로 다시 쓴다. 여기서는 축만 말한다.
        discard_block = "이 주문에는 아직 살아 있는 결제가 있습니다"
    elif claim_phase != "done":
        # 꼬리 훈수(`확정 후에 접으세요`)만 뗀다 — 잠금 사유는 앞 절이 온전히 든다.
        # 마침표는 pane 587 이 붙인다(다른 갈래와 같은 규칙) — 여기서는 안 찍는다.
        discard_block = "네이버가 아직 취소를 확정하지 않았습니다"
    elif repay_expected:
        # 앞의 두 사실이 지난 뒤에만 표시가 잠금 사유가 된다. 살아 있는 결제·확정 전은
        # 시스템이 아는 사실이고, 재결제 예정은 사람이 적어 둔 사실이라 뒤에 온다.
        discard_block = REPAY_EXPECTED_BLOCK_TEXT
    else:
        discard_block = ""
    return {
        "claim_kind": kind,
        # 단계와 **완성 문구**를 함께 낸다. 템플릿이 `" 완료"` 를 덧붙이던 시절에는
        # 확정 전 취소가 화면에서 `취소 완료` 로 읽혔다(2026-08-28).
        "claim_phase": claim_phase,
        "claim_text": claim_text,
        "can_discard": can_discard,
        # 접수 이후 단계는 접히긴 하되 **관리자가 사유를 적어야** 한다(2026-09-02).
        # 실측 방문·치수 같은 이력이 붙은 주문을 조용히 지우지 않게 하는 관문이다.
        "discard_needs_reason": status not in DISCARDABLE_STATUSES,
        "discard_block": discard_block,
        "status_label": stage_label(status),
    }


def find_ghost_orders(session, *, limit: int = GHOST_LIST_LIMIT) -> dict[str, Any]:
    """네이버 결제가 전부 취소된 살아 있는 주문 목록 (R-2).

    Args:
        session: 요청 스코프 DB 세션.
        limit: 목록에 담을 최대 건수(수는 전체를 센다).

    Returns:
        ``{"count": 전체 건수, "rows": [...]}``. 각 행은 주문 요약 + 네이버 사실 +
        ``can_discard``(취소 처리 버튼을 열지) + ``discard_block``(못 여는 이유) +
        ``discard_needs_reason``(접으려면 관리자 사유 문장이 필요한지) +
        ``measure``(실측 전/후 표시 축 — 판정에는 안 쓴다) +
        ``repay_expected``(사람이 켠 재결제 예정 표시 dict 또는 ``None``).
    """
    # **사본 컬럼만 읽는다**(NVMIRROR-01). `raw_snapshot` 은 평균 2,194 bytes 로 TOAST 임계를
    # 넘어 그 컬럼을 건드리는 순간 행마다 TOAST 를 한 번 더 읽는다 — 운영 실측으로 같은 스캔이
    # 버퍼 14,736·50.5ms 대 249·0.95ms 였다. 사본으로 판정하면 그 읽기가 아예 없다.
    #
    # 판정은 **한 벌 그대로** 쓴다: 사본을 `snapshot_from_mirror` 로 같은 모양 문서로 되돌려
    # 기존 `_fold_link` 에 넣는다. `if 사본 else 스냅샷` 으로 술어를 갈라 쓰면 R-7 이 재발한다.
    # 링크 읽기는 :func:`_mirror_link_rows` 한 벌이다 — 부분 취소 띠와 같은 리더를 쓴다.
    # 쿼리를 두 벌 두면 "백필 전 행을 어떻게 읽는가"가 띠마다 갈린다.
    buckets: dict[int, dict[str, Any]] = {}
    for order_id, snapshot, order_no, link_id in _mirror_link_rows(session):
        bucket = buckets.setdefault(order_id, _new_bucket())
        _fold_link(bucket, snapshot=snapshot, order_no=order_no, link_id=link_id)

    # 전부 취소된 것만 남긴다(부분 취소 제외 — 정상 진행 중일 수 있다).
    ghost_ids = [order_id for order_id, bucket in buckets.items()
                 if bucket["link_count"] and bucket["canceled"] == bucket["link_count"]]
    if not ghost_ids:
        return {"count": 0, "rows": []}

    orders = (
        session.query(Order)
        .filter(Order.id.in_(ghost_ids), Order.not_deleted_filter())  # perf-ok: id batch
        # 실측 축(judge_measure_progress)이 schedule_dates 관계를 읽는다 — N+1 방지 필수.
        # 같은 이유·같은 패턴이 foms/services/measurement_undated.py 에 있다.
        .options(selectinload(Order.schedule_dates))
        .all()
    )
    if not orders:
        return {"count": 0, "rows": []}

    views: list[dict[str, Any]] = []
    for order in orders:
        bucket = buckets[int(order.id)]
        status = str(order.status or "")
        # 사람이 켠 '재결제 예정' 표시. **모집단에서 빼지 않는다**(사용자 결정 2026-09-14:
        # 숨기지 않는다) — 행은 띠에 그대로 남고 휴지통 버튼만 잠긴다.
        repay = read_repay_expected(order)
        views.append({
            "order_id": int(order.id),
            "customer_name": order.customer_name or "",
            "phone": order.phone or "",
            "status": status,
            "received_date": order.received_date or "",
            "payment_amount": order.payment_amount or 0,
            "naver_order_nos": bucket["order_nos"],
            "naver_link_count": bucket["link_count"],
            "lead_link_id": bucket["lead_link_id"],
            "naver_amount_total": bucket["amount_total"],
            # 표시 축만 추가한다 — 폐기 판정(_discard_verdict)은 이 값을 안 본다.
            "measure": judge_measure_progress(order),
            "repay_expected": repay,
            **_discard_verdict(bucket, status, repay_expected=bool(repay)),
        })

    # 금액 큰 것부터 — 돈이 큰 유령이 더 급하다.
    views.sort(key=lambda row: (-int(row["naver_amount_total"] or 0), -row["order_id"]))
    return {"count": len(views), "rows": views[:limit]}


def _mirror_link_rows(session) -> list[tuple]:
    """띠 두 개가 쓰는 **링크 한 벌** — 사본 컬럼만 읽는다(NVMIRROR-01).

    ``raw_snapshot`` 은 평균 2,194 bytes 로 TOAST 임계를 넘어, 그 컬럼을 건드리는 순간
    행마다 TOAST 를 한 번 더 읽는다(운영 실측: 같은 스캔이 버퍼 14,736·50.5ms 대
    249·0.95ms). 그래서 사본으로 판정하고, 사본이 아직 없는 행(``claim_status IS NULL``
    = 백필 전)만 투영 스냅샷을 따로 읽는다.

    Args:
        session: 요청 스코프 DB 세션.

    Returns:
        ``(order_id, snapshot, external_order_no, link_id)`` 목록 — 스냅샷은 사본을
        :func:`link_mirror.snapshot_from_mirror` 로 되돌린 **판정용 문서**다. 판정 함수를
        두 벌로 갈라 쓰지 않으려고 모양을 맞춰 돌려준다(R-7).
    """
    rows = (
        session.query(ExternalOrderLink.order_id, ExternalOrderLink.claim_status,
                      ExternalOrderLink.claim_type, ExternalOrderLink.payment_amount,
                      ExternalOrderLink.external_order_no, ExternalOrderLink.id)
        .filter(ExternalOrderLink.order_id.isnot(None))
        .all()
    )
    stale_ids = [int(link_id) for _oid, claim_status, _t, _a, _no, link_id in rows
                 if claim_status is None]
    stale_snapshots: dict[int, Any] = {}
    if stale_ids:
        stale_snapshots = {
            int(link_id): snapshot
            for link_id, snapshot in session.query(
                ExternalOrderLink.id,
                _ghost_snapshot_projection(session).label("raw_snapshot"))
            .filter(ExternalOrderLink.id.in_(stale_ids))  # perf-ok: 백필 전 행만
            .all()
        }
    out: list[tuple] = []
    for order_id, claim_status, claim_type, amount, order_no, link_id in rows:
        snapshot = (stale_snapshots.get(int(link_id)) if claim_status is None
                    else snapshot_from_mirror(claim_status=claim_status,
                                              claim_type=claim_type,
                                              payment_amount=amount))
        out.append((int(order_id), snapshot, order_no, link_id))
    return out


def find_partial_claim_orders(session, *,
                              limit: int = PARTIAL_LIST_LIMIT) -> dict[str, Any]:
    """**집 하나가 통째로 취소·반품됐는데** 살아 있는 집이 남은 주문 (2026-09-21).

    유령 띠(:func:`find_ghost_orders`)는 일부러 "붙은 링크가 전부 취소"만 센다 — 부분
    취소는 정상 진행 중일 수 있어서다. 그런데 그 제외가 **추가결제가 붙은 주문의 본품
    반품을 통째로 감췄다**: 운영 #5268(김현정)은 본품 5건이 전부 ``RETURN_REQUEST`` 인데
    추가결제 집 6건이 살아 있어 띠 밖이었고, 담당자가 그 반품을 볼 자리가 화면에 없었다
    (2026-09-21 사용자 보고 — "네이버엔 반품 2건인데 FOMS 엔 1건").

    그래서 유령 판정은 **한 글자도 건드리지 않고** 띠를 하나 더 둔다. 모집단은 셋 다 참일
    때다:

    * 집(네이버 주문번호) 하나가 **그 집 링크 전부** 취소·반품이고,
    * 같은 ERP 주문에 클레임이 **없는 링크가 하나라도** 살아 있고,
    * 죽은 집의 클레임이 **아직 확정 전**(:data:`PARTIAL_PENDING_PHASES`)이다.

    셋째 조건이 이 띠를 할 일 목록으로 만든다(근거는 그 상수에 적었다).

    **불가역 버튼은 내지 않는다** — 행이 주는 것은 ``lead_link_id`` 뿐이고, 승인·거부는
    그 집 pane 에서 한다(유령 띠의 `열어서 승인하기` 와 같은 규율).

    Args:
        session: 요청 스코프 DB 세션.
        limit: 목록에 담을 최대 건수(수는 전체를 센다).

    Returns:
        ``{"count": 전체 건수, "rows": [...]}``. 각 행은 주문 요약 + 죽은 집의 클레임
        문구(``claim_text``·``claim_phase``·``claim_kind``) + ``dead_order_nos`` +
        ``alive_link_count`` + ``lead_link_id`` + ``measure``(표시 축).
    """
    # 집 축으로 접는다 — 유령 띠는 주문 축이라 버킷을 공유할 수 없다. 셈법 자체는
    # `_fold_link` 한 벌이라 "무엇을 취소로 세는가"는 두 띠가 같다.
    households: dict[int, dict[str, dict[str, Any]]] = {}
    for order_id, snapshot, order_no, link_id in _mirror_link_rows(session):
        by_no = households.setdefault(order_id, {})
        key = str(order_no or "").strip() or f"link:{int(link_id)}"
        bucket = by_no.setdefault(key, _new_bucket())
        _fold_link(bucket, snapshot=snapshot, order_no=order_no, link_id=link_id)

    picked: dict[int, dict[str, Any]] = {}
    for order_id, by_no in households.items():
        dead = [bucket for bucket in by_no.values()
                if bucket["link_count"] and bucket["canceled"] == bucket["link_count"]]
        alive_links = sum(bucket["link_count"] - bucket["canceled"]
                          for bucket in by_no.values())
        if not dead or not alive_links:
            continue
        pending = [bucket for bucket in dead
                   if bucket["phases"] & set(PARTIAL_PENDING_PHASES)]
        if not pending:
            continue
        # 여러 집이 걸리면 **링크 id 가 가장 작은** 집을 대표로 쓴다 — 렌더마다 흔들리지
        # 않게(유령 띠의 `lead_link_id` 와 같은 결정론).
        lead = min(pending, key=lambda bucket: int(bucket["lead_link_id"] or 0))
        picked[order_id] = {"lead": lead, "dead": dead, "alive_links": int(alive_links)}

    if not picked:
        return {"count": 0, "rows": []}

    orders = (
        session.query(Order)
        .filter(Order.id.in_(list(picked.keys())), Order.not_deleted_filter())  # perf-ok: id batch
        # 실측 축(judge_measure_progress)이 schedule_dates 관계를 읽는다 — N+1 방지 필수.
        .options(selectinload(Order.schedule_dates))
        .all()
    )
    if not orders:
        return {"count": 0, "rows": []}

    views: list[dict[str, Any]] = []
    for order in orders:
        found = picked[int(order.id)]
        lead, dead = found["lead"], found["dead"]
        verdict = _discard_verdict(lead, str(order.status or ""))
        dead_order_nos: list[str] = []
        for bucket in dead:
            for text in bucket["order_nos"]:
                if text not in dead_order_nos:
                    dead_order_nos.append(text)
        views.append({
            "order_id": int(order.id),
            "customer_name": order.customer_name or "",
            "phone": order.phone or "",
            "status": str(order.status or ""),
            "status_label": verdict["status_label"],
            "payment_amount": order.payment_amount or 0,
            # 금액은 **죽은 집**의 것이다 — 살아 있는 추가결제까지 더하면 환불 예정액을
            # 거짓말한다.
            "naver_amount_total": int(lead["amount_total"] or 0),
            "dead_order_nos": dead_order_nos,
            "dead_link_count": int(lead["link_count"]),
            "alive_link_count": found["alive_links"],
            "lead_link_id": lead["lead_link_id"],
            "claim_kind": verdict["claim_kind"],
            "claim_phase": verdict["claim_phase"],
            "claim_text": verdict["claim_text"],
            # 표시 축만 낸다 — 유령 띠와 같이 모집단 판정은 이 값을 보지 않는다.
            "measure": judge_measure_progress(order),
        })

    # 돈이 큰 것부터 — 유령 띠와 같은 정렬이라 두 띠를 위아래로 읽어도 순서가 같다.
    views.sort(key=lambda row: (-int(row["naver_amount_total"] or 0), -row["order_id"]))
    return {"count": len(views), "rows": views[:limit]}


def find_repay_candidate_links(session, phones: list[str]) -> dict[str, list[dict[str, Any]]]:
    """유령 주문의 전화번호로 **아직 아무 주문에도 안 붙은 집**을 찾는다 (재결제 짝 후보).

    유령 주문 옆에 "8/24 집이 큐에 대기 중" 이 함께 보이면 담당자가 그 자리에서
    재결제로 정리할지 판단할 수 있다. 실데이터 3건 중 2건(#4462·#4466)에 짝이 있었다.

    Args:
        session: DB 세션.
        phones: 유령 주문의 전화번호 목록.

    Returns:
        ``{전화번호: [{external_order_no, created_at, link_id}]}``.
    """
    from foms.services.phone_search import normalize_phone_digits

    wanted = {normalize_phone_digits(phone) for phone in phones if phone}
    wanted.discard("")
    if not wanted:
        return {}

    pairs: dict[str, list[dict[str, Any]]] = {}
    rows = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.order_id.is_(None),
                ExternalOrderLink.sync_status == "COLLECTED")
        .order_by(ExternalOrderLink.id.desc())
        .limit(500)  # perf-ok: 미연결 집만, 최신 우선
        .all()
    )
    for link in rows:
        snapshot = link.raw_snapshot if isinstance(link.raw_snapshot, dict) else {}
        product_order = snapshot.get("productOrder")
        if not isinstance(product_order, dict):
            continue
        shipping = product_order.get("shippingAddress")
        tel = normalize_phone_digits((shipping or {}).get("tel1")) if isinstance(shipping, dict) else ""
        if not tel or tel not in wanted:
            continue
        # 이미 취소된 집은 재결제 짝이 아니다 — 그것도 유령이다. 확정 전 취소도 같이
        # 뺀다(동작 불변). 거부·철회는 살아 있는 집이라 이제 후보에 남는다.
        if _claim_of(snapshot)[1] in GHOST_CLAIM_PHASES:
            continue
        seen = pairs.setdefault(tel, [])
        order_no = str(link.external_order_no or "")
        if any(row["external_order_no"] == order_no for row in seen):
            continue
        seen.append({
            "external_order_no": order_no,
            "link_id": int(link.id),
            "created_at": link.created_at,
        })
    return pairs


def attach_repay_candidates(session, ghosts: dict[str, Any]) -> None:
    """유령 목록 각 행에 재결제 짝 후보를 붙인다(제자리 수정).

    Args:
        session: DB 세션.
        ghosts: :func:`find_ghost_orders` 결과.

    Returns:
        None.
    """
    from foms.services.phone_search import normalize_phone_digits

    rows = ghosts.get("rows") or []
    if not rows:
        return
    pairs = find_repay_candidate_links(session, [row["phone"] for row in rows])
    for row in rows:
        digits = normalize_phone_digits(row["phone"]) or ""
        row["repay_candidates"] = pairs.get(digits, [])
def _alive_house_text(houses: list[dict[str, Any]]) -> str:
    """살아 있는 집 목록 → 사람이 읽는 한 토막(최대 2집 + 나머지 건수).

    Args:
        houses: ``external_order_no``·``relation``·``amount`` 를 가진 집 목록.

    Returns:
        ``"추가결제 2026...(1,082,140원)"`` 꼴. 목록이 비면 빈 문자열.
    """
    if not houses:
        return ""
    shown = [
        f"{RELATION_LABELS.get(house['relation'], '결제')} {house['external_order_no']}"
        f"({house['amount']:,}원)"
        for house in houses[:2]
    ]
    text = ", ".join(shown)
    if len(houses) > 2:
        text = f"{text} 외 {len(houses) - 2}집"
    return text


def _pair_amounts(session, order_nos: list[str]) -> dict[str, int]:
    """재결제 짝 후보 집의 **정확한 금액 합계**.

    :func:`find_repay_candidate_links` 는 최신 500행만 훑고 주문번호로 중복을 접는다 —
    거기서 금액을 세면 집이 상한에 걸려 잘렸을 때 화면이 **틀린 돈**을 말한다. 후보로
    뽑힌 주문번호만 다시 정확히 센다(후보는 많아야 몇 건이다).

    Args:
        session: DB 세션.
        order_nos: 후보 집의 네이버 주문번호 목록.

    Returns:
        ``{주문번호: 합계}``.
    """
    if not order_nos:
        return {}
    rows = (
        session.query(ExternalOrderLink.external_order_no, ExternalOrderLink.raw_snapshot)
        .filter(ExternalOrderLink.external_order_no.in_(order_nos),  # perf-ok: 후보 몇 건
                ExternalOrderLink.order_id.is_(None))
        .all()
    )
    totals: dict[str, int] = {}
    for order_no, snapshot in rows:
        product_order = snapshot.get("productOrder") if isinstance(snapshot, dict) else None
        amount = product_order.get("totalPaymentAmount") if isinstance(product_order, dict) else None
        totals[str(order_no or "")] = totals.get(str(order_no or ""), 0) + (
            amount if isinstance(amount, int) else 0)
    return totals


def _partial_discard_text(*, alive: dict[str, dict[str, Any]], house_keys: set[str],
                          group_key: str, bucket: dict[str, Any]) -> str:
    """부분 취소 주문의 **닫힌 사유 문장** — 세 갈래.

    왜 세 갈래인가: 한 주문에 옛 결제(취소된 집)와 재결제(살아 있는 집)가 함께 붙는다.
    예전에는 링크 축 한 줄로만 말해서 ``14건 중 9건만 취소됐습니다`` 가 나왔는데 사실은
    9건이 옛 집이고 5건이 지금 받은 새 결제였다. **링크 수와 집 수를 한 문장에 섞지
    않는다** — 집 축으로 말할 사실이 있을 때만 집 축으로 말한다. 죽은 집이 0집이면
    집 축은 ``3집 중 0집이 취소됐고`` 라는 헛소리가 되므로 링크 축으로 떨어뜨린다.

    문장 전용이라 **판정(``can_discard``)은 보지도 않는다** — 판정 축을 한 글자도
    바꾸지 않았다.

    Args:
        alive: 살아 있는 링크가 1건 이상인 집(묶음키 → 집 요약).
        house_keys: 이 주문에 붙은 **모든** 집의 묶음키(취소된 집 포함).
        group_key: pane 이 지금 열고 있는 집의 묶음키(없을 수 있다).
        bucket: :func:`_fold_link` 로 접은 버킷(링크 축 사실).

    Returns:
        화면에 그대로 찍히는 한 문장.
    """
    house_total = len(house_keys)
    alive_house_count = len(alive)
    dead_house_count = house_total - alive_house_count
    # 문장은 짧을수록 읽힌다(2026-09-08 담당자 지적) — 앞머리 설명과 맺음말을 걷어내고
    # 사실만 남긴다. 무엇을 해야 하는지는 버튼과 꼬리표가 이미 말한다.
    link_axis = ("부분 취소 건 — 상품주문 "
                 f"{bucket['link_count']}건 중 {bucket['canceled']}건만 취소됐습니다")
    if not group_key or group_key not in house_keys:
        # 이 주문에 없는 집이면 집 축으로 말할 사실이 없다.
        return link_axis
    if group_key not in alive:
        # 앞머리는 뒤 절의 요약이라 뺐다 — 판정을 먼저 놓는다(2026-09-08).
        # `이 집만` 이 아니라 `이전 주문` 이라고 말하는 이유(2026-09-08 담당자 지시):
        # 이 자리는 재결제가 살아 있고 지금 열려 있는 집이 죽은 갈래다. 담당자가 보는 것은
        # `집` 이 아니라 **옛 주문**이라, 화면 낱말이 사람 낱말을 따라간다.
        return ("이전 주문 취소 됐습니다 — "
                f"{_alive_house_text(list(alive.values()))}은 살아 있습니다")
    if dead_house_count >= 1:
        # 맺음말은 `정리 계획 열기` 버튼이 같은 화면에서 이미 말한다 — 숫자만 남긴다.
        return ("이 주문에 붙은 "
                f"{house_total}집 중 {dead_house_count}집만 취소됐습니다 — 이 집을 포함한 "
                f"{alive_house_count}집은 살아 있습니다")
    return link_axis


def judge_order_discard(session, order_id: int, *, group_key: str = "") -> dict[str, Any]:
    """**주문 하나**만 판정한다 — 워크벤치 집 pane 의 휴지통 버튼용.

    왜 따로 두는가
    --------------
    pane 은 '집' 화면이지만 휴지통은 **주문**을 접는다. pane 이 자기 축(집 단위)으로
    판정식을 새로 만들면 :func:`find_ghost_orders` 가 지키던 안전 —
    ``canceled == link_count`` 라서 살아 있는 추가결제 집이 붙어 있는 주문은 모집단에서
    자동으로 빠진다 — 이 사라진다. 그래서 셈법(:func:`_fold_link`)과 판정
    (:func:`_discard_verdict`)은 띠와 **같은 함수**를 쓰고, 이 함수가 바꾸는 것은
    조회 범위뿐이다(전 링크 스캔은 pane 마다 돌리기 무겁다).

    Args:
        session: 요청 스코프 DB 세션.
        order_id: 판정할 ERP 주문 id.
        group_key: pane 이 지금 열고 있는 집의 묶음키. **판정에는 쓰지 않는다** —
            닫힌 사유 문장이 '부분 취소'인지 '살아 있는 집 동거'인지 가르는 데만 쓴다.

    Returns:
        ``applicable``(이 주문에 클레임이 하나라도 있어 이 블록을 그릴지) ·
        ``can_discard`` · ``discard_needs_reason`` · ``discard_block`` 과
        화면이 재진술할 사실(``status_label``·``link_count``·``canceled_count``·
        ``claim_kind``·``repay_candidates``·``measure``·``repay_expected``·
        ``in_ghost_band``).
    """
    rows = (
        session.query(ExternalOrderLink.id, ExternalOrderLink.raw_snapshot,
                      ExternalOrderLink.external_order_no, ExternalOrderLink.group_key,
                      ExternalOrderLink.relation)
        .filter(ExternalOrderLink.order_id == int(order_id))  # perf-ok: 주문 1건
        .all()
    )
    # 블록을 안 그리는 경로라 휴지통 3종도 고정값이다. "이 주문이 휴지통인가" 의 화면
    # 정본은 pane 머리줄의 독립 키(``order_trashed``)이고, 여기 값은 **블록이 그려질 때만**
    # 사실을 말한다.
    blank = {"applicable": False, "can_discard": False, "discard_needs_reason": False,
             "discard_block": "", "repay_candidates": [], "repay_expected": None,
             "in_ghost_band": False,
             "trashed": False, "trashed_at_text": "", "trashed_note": ""}
    if not rows:
        return blank

    bucket = _new_bucket()
    alive: dict[str, dict[str, Any]] = {}
    # 취소된 링크의 집 키까지 **전부** 모은다 — 문장이 "몇 집 중 몇 집" 을 말하려면 죽은
    # 집도 세야 하기 때문이다. 이 집합은 **문장 전용**이고, 모집단 판정
    # (``canceled == link_count``)은 여전히 링크 축이라 판정 축은 그대로다.
    house_keys: set[str] = set()
    for link in rows:
        _, phase, kind = _fold_link(bucket, snapshot=link.raw_snapshot,
                                    order_no=link.external_order_no, link_id=link.id)
        house_key = resolve_group_key(link)
        house_keys.add(house_key)
        if phase in GHOST_CLAIM_PHASES and kind in GHOST_CLAIM_KINDS:
            continue
        # 살아 있는 링크(클레임이 없거나 거부·철회)는 **집 단위로** 모은다. 문장이
        # 상품주문마다 한 줄씩 나오면 사람이 몇 집인지 못 읽는다.
        house = alive.setdefault(house_key, {
            "external_order_no": str(link.external_order_no or ""),
            "relation": str(link.relation or "NEW"),
            "amount": 0,
        })
        product_order = (link.raw_snapshot.get("productOrder")
                         if isinstance(link.raw_snapshot, dict) else None)
        amount = product_order.get("totalPaymentAmount") if isinstance(product_order, dict) else None
        if isinstance(amount, int):
            house["amount"] += amount

    order = session.get(Order, int(order_id))
    # 휴지통 조건을 여기서 뺐다(2026-09-07). 접힌 순간 블록이 통째로 사라져 화면이
    # "휴지통으로 보냈다" 는 사실을 아무 데서도 말하지 않았다 — 모집단·판정식은 그대로다.
    if order is None or not bucket["canceled"]:
        # 클레임이 하나도 없는 주문에는 이 블록을 그리지 않는다 — pane 마다
        # `지금은 안 됨` 버튼이 상시로 서 있으면 그 자리는 아무도 안 읽는다.
        return blank

    status = str(order.status or "")
    # 띠와 **같은 값·같은 함수**. 표시가 있으면 판정이 잠기고 문구가 바뀐다.
    repay = read_repay_expected(order)
    verdict = _discard_verdict(bucket, status, repay_expected=bool(repay))
    trash = read_order_trash(order)
    whole = bucket["canceled"] == bucket["link_count"]
    if not whole:
        # 여기서만 문장을 사실로 다시 쓴다. **판정은 바꾸지 않는다.**
        verdict["discard_block"] = _partial_discard_text(
            alive=alive, house_keys=house_keys, group_key=group_key, bucket=bucket)
    if trash["trashed"]:
        # 휴지통 사실이 가장 먼저 읽혀야 한다. 이 덮어쓰기는 **좁히기만** 한다(True→False):
        # 라우트(``naver_ingest_ghost_discard``)는 이미 휴지통을 뺀 모집단으로 막고 있었고,
        # 이제 화면이 라우트와 같은 말을 한다. ``can_discard=False`` 라 아래 재결제 짝
        # 조회도 돌지 않는다.
        verdict["can_discard"] = False
        verdict["discard_block"] = "이미 휴지통에 있습니다 — 주문 목록 휴지통에서 되돌립니다"

    # 재결제 짝은 **열린 버튼에만** 경고로 붙인다(사용자 결정: 잠그지 않는다).
    # 닫힌 상태에서는 그릴 자리가 없으므로 조회도 하지 않는다.
    candidates: list[dict[str, Any]] = []
    if verdict["can_discard"]:
        from foms.services.phone_search import normalize_phone_digits

        pairs = find_repay_candidate_links(session, [order.phone or ""])
        candidates = pairs.get(normalize_phone_digits(order.phone or "") or "", [])
        totals = _pair_amounts(session, [row["external_order_no"] for row in candidates])
        for row in candidates:
            row["amount"] = totals.get(row["external_order_no"], 0)

    return {
        "applicable": True,
        "order_id": int(order.id),
        "customer_name": order.customer_name or "",
        "status": status,
        "link_count": bucket["link_count"],
        "canceled_count": bucket["canceled"],
        "repay_candidates": candidates,
        # 띠와 **같은 함수·같은 문구**. pane 용으로 다시 만들지 않는다.
        "measure": judge_measure_progress(order),
        # 사람이 켠 재결제 예정 표시 — 띠와 같은 키·같은 모양. 없으면 ``None`` 이다
        # (모양이 갈리면 pane 이 없는 값을 읽는다).
        "repay_expected": repay,
        # 이 주문이 지금 유령 띠 모집단에 들어 있는가 — 라우트(:func:`find_ghost_orders`:
        # 링크가 있고 전부 취소이며 휴지통이 아닌 주문)와 **같은 술어**를 서버가 한 벌로
        # 내려 준다. 화면이 ``link_count == canceled_count`` 를 손으로 다시 세면 판정 축이
        # 두 벌이 되어 pane 버튼이 라우트와 다른 말을 하게 된다.
        "in_ghost_band": bool(bucket["link_count"]) and whole and not trash["trashed"],
        # 표기 전용 사실을 먼저 깔고 **판정 키를 마지막에** 싣는다(기존 모양 유지).
        **trash,
        **verdict,
    }

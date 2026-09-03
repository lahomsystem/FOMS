"""수집분 → FOMS 주문 생성 (NAVER-INGEST-01 T12).

수집(:mod:`~foms.services.integrations.naver_commerce.ingest`)과 분리된 **두 번째 단계**다.
사람이 관리 화면에서 "주문 만들기"를 눌렀을 때만 돈다.

**네트워크를 쓰지 않는다** — 입력은 이미 저장된 ``ExternalOrderLink.raw_snapshot`` 이다.
그래서 web 프로세스에서 호출해도 안전하다(네이버 HTTP 는 여전히 WORKER 전용이라는 계약이
깨지지 않는다). 이 모듈을 ``ingest`` 안에 두지 않은 이유가 그것이다 — web 이 ``ingest`` 를
import 하면 WORKER 단일 출구 계약 테스트가 red 가 된다.

주문 생성은 ``create_order()`` 만 경유한다(raw ``Order(...)`` 금지 — ORDER-CREATE-01).
좌표는 주입하지 않는다: 네이버 좌표는 주문서 주소 기준이라 실제 시공 주소와 다를 수 있고,
주입하면 ``geocode_status='success'`` 로 굳어 재지오코딩에서도 빠진다.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.integrations.naver_commerce.constants import CHANNEL
from foms.services.integrations.naver_commerce.mapping import (
    NaverMappingError,
    build_payment_info,
    extract_claim,
    extract_place_status,
    group_key,
    map_group,
)
from foms.services.orders.order_create import create_order
from models import ExternalOrderLink, Order

logger = logging.getLogger(__name__)


class PromotionError(RuntimeError):
    """주문을 만들 수 없다(사유는 사람이 읽는 문장으로 담는다)."""


#: 주문 승격 대상 상태. 이미 주문이 붙은 형제는 제외한다 — 사람이 부분적으로 먼저
#: 만들었을 수 있고, 다시 묶으면 같은 상품주문이 두 주문에 들어간다.
PROMOTABLE_SYNC_STATUSES = ("COLLECTED", "PENDING_REVIEW")


def is_promotable(link: ExternalOrderLink) -> bool:
    """이 링크가 **주문 승격 대상**인가 — 화면 재진술과 서버 동작의 공통 술어.

    :func:`_group_siblings` 가 실제로 묶는 조건과 같은 술어다. 워크벤치 모달이 집 전체
    건수를 재진술하면(``member_count``) 이미 주문이 붙은 형제까지 세어 "3건을 주문
    1건으로 만듭니다"라고 읽히지만 서버는 2건만 옮긴다 — 남는 형제를 화면이 알리지도
    않는다(2026-08-23 리뷰 M-2). 술어를 여기 한 벌만 두고 양쪽이 나눠 쓴다.

    Args:
        link: 수집 링크.

    Returns:
        아직 주문이 없고 상태가 :data:`PROMOTABLE_SYNC_STATUSES` 면 True.
    """
    return (link.order_id is None
            and str(link.sync_status or "") in PROMOTABLE_SYNC_STATUSES)


#: 승격 시 품목 행에 남기는 **네이버 원본 결제액** 키. 화면 금액식(``price``)이 읽지 않는
#: 자리라 합계에 섞이지 않는다 — 사람이 "네이버에서 얼마 받았나"를 역산할 근거다.
ITEM_PAID_AMOUNT_KEY = "naver_paid_amount"


def apply_paid_amount_as_deposit(structured: dict) -> int:
    """네이버 실결제 총액을 품목 금액이 아니라 **예약금**으로 앉힌다 (승격 전용).

    2026-08-26 사용자 확정: 네이버에서 받은 돈은 계약 총액이 아니라 **선금**이다. 실측 전에는
    품목 금액이 정해지지 않았으므로 항목 금액을 비우고(0) 결제 총액만 예약금에 넣는다.
    실측 뒤 사람이 항목 금액을 채우면 그때부터 잔금이 표기된다(그 전까지 잔금 0).

    상품주문이 여러 건인 집도 같다 — :func:`map_group` 이 이미 묶음 합계를
    품목 행에 나눠 담아 뒀으므로 그 합이 곧 실결제 총액이다. 여기서 합산식을 새로 만들지
    않는다(집 합계 정본은 ``map_group`` 하나다).

    **품목 행은 지우지 않는다** — 품명·옵션·수량은 "무엇을 샀는가"이고, 그게 사라지면
    실측자가 규격을 채울 근거가 없다. 지운 금액도 잃지 않는다: 행마다
    ``items[].naver_paid_amount``, 집 단위는 ``naver.group_payment_total`` 에 남고,
    네이버 원본 결제 상세는 ``naver.payment`` 그대로다.

    다만 **행별 기록은 첫 폼 저장까지만** 산다. 폼 전체저장은 ``items`` 를 클라이언트 배열로
    통째 교체하고 그 배열은 ``data-erp`` 입력만 담으므로, ``naver_paid_amount`` 는
    ``naver_addons`` 와 같이 그때 사라진다. 집 단위(``naver.*``)는 보존 목록에 있어 살아
    남으므로 "얼마 받았나"는 계속 역산할 수 있다 — 잃는 것은 행별 배분이다.

    이 함수는 **갓 매핑한 dict 전용**이다. 이미 옮겨진 structured_data 에 다시 부르면
    품목 행이 이미 0이라 합계도 0이고, 그 0이 예약금을 덮는다. 아래 가드가 그 경우를
    막지만 애초에 두 번 부를 자리가 아니다(그래서 ``__all__`` 에 없다).

    ``totals`` 는 손대지 않는다 — ``create_order`` 안 ``recompute_totals`` 가 서버 권위로
    다시 계산한다(품목합 0 · 예약금 total → ``balance_amount`` 0).

    ``deposit_confirmed`` 는 ``False`` 로 둔다. 입금 확정 토글은 FINANCE 권한 게이트라
    수집이 대신 눌러 줄 수 없다(돈이 들어왔다는 판정은 사람 몫).

    이 정책은 **새 주문을 만들 때만** 돈다. 기존 주문에 붙이는 경로
    (:func:`attach_link_to_order`)는 지난 결정(2026-08-19)대로 금액을 기록만 하고
    예약금·출고가를 자동으로 바꾸지 않는다.

    Args:
        structured: :func:`map_group` 이 만든 structured_data. **in-place** 로 고친다
            (아직 DB 에 없는 dict 라 ``flag_modified`` 대상이 아니다).

    Returns:
        예약금으로 옮긴 실결제 총액(원).
    """
    if not isinstance(structured, dict):
        return 0

    # 품목 행 price → 원화 정수 규칙은 서버 재계산(recompute_totals)과 같은 것을 쓴다.
    # 여기서 읽은 값이 곧 "우리가 비운 items_total" 이라야 예약금과 어긋나지 않는다.
    # (순환 import 방지 위해 함수 지역 import — structured_form_projection 과 같은 이유.)
    from foms.services.erp_display import _erp_coerce_item_price_krw

    rows = [row for row in (structured.get("items") or []) if isinstance(row, dict)]
    # 합계를 **먼저** 센다. 세면서 같이 쓰면 아래 가드가 이미 덮어쓴 값을 보게 된다
    # (행별 원본이 0으로 지워진 뒤라 되돌릴 수 없다).
    total = sum(_erp_coerce_item_price_krw(row) for row in rows)

    payment = structured.get("payment")
    if not isinstance(payment, dict):
        payment = {}
        structured["payment"] = payment
    existing = int(payment.get("deposit") or 0)

    # **두 번 부르면 예약금이 사라진다** — 두 번째 호출은 price 가 이미 0이라 합계도 0이고,
    # 그 0으로 예약금·집 합계·행별 원본을 동시에 덮는다. 갓 매핑한 dict 위에서만 도는
    # 지금은 도달할 수 없지만, 재승격·보정 스크립트가 기존 주문 structured_data 에 한 번
    # 부르면 그 주문의 돈이 조용히 0이 된다. "이미 옮겨진 dict" 는 한 글자도 안 건드린다.
    if total == 0 and existing > 0:
        return existing

    for row in rows:
        row[ITEM_PAID_AMOUNT_KEY] = _erp_coerce_item_price_krw(row)
        row["price"] = 0

    payment["deposit"] = int(total)
    payment["deposit_confirmed"] = False

    naver = structured.get("naver")
    if isinstance(naver, dict):
        naver["group_payment_total"] = int(total)
    return int(total)


def promote_link_to_order(
    session: Session, *, link_id: int, actor_user_id: int, owner_user_id: int,
    now: Optional[datetime] = None,
) -> tuple[int, bool]:
    """수집 링크 1건을 FOMS 주문으로 만든다(이미 있으면 그대로 돌려준다).

    커밋은 호출자가 소유한다.

    Args:
        session: DB 세션.
        link_id: ``ExternalOrderLink.id``.
        actor_user_id: 생성 주체(이벤트 author).
        owner_user_id: 초기 owner(미배정 보류함 계정).
        now: 테스트용 시각 주입.

    Returns:
        ``(order_id, created)`` — ``created`` 는 이번 호출이 만들었는지 여부.
        버튼 두 번 눌러도 주문은 하나다(두 번째는 ``False``).

    Raises:
        PromotionError: 링크 부재 · 원본 없음 · 매핑 실패 · 이미 폐기된 상태.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .with_for_update()
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    if link.order_id:
        # 멱등: 동시 클릭·새로고침 재전송에도 주문은 하나다.
        return (int(link.order_id), False)
    if link.sync_status not in ("COLLECTED", "PENDING_REVIEW"):
        raise PromotionError(
            f"주문을 만들 수 있는 상태가 아닙니다 (현재 {link.sync_status})."
        )
    if not isinstance(link.raw_snapshot, dict) or not link.raw_snapshot:
        raise PromotionError("원본 스냅샷이 없어 주문을 만들 수 없습니다.")

    # 한 네이버 주문(본품 + 구성 옵션)을 한 FOMS 주문으로 묶는다 — T13.
    siblings = _group_siblings(session, link)

    # 취소·반품 건은 주문으로 만들지 않는다. 수집 필터가 productOrderStatus == PAYED
    # 하나뿐이라 **취소 요청 상태도 PAYED 로 수집된다**(2026-08-14 스테이징 실물 1건).
    # 화면 버튼만 잠그면 API 직접 호출로 뚫리므로 서비스에서 막는다.
    blocked = [row for row in siblings if extract_claim(row.raw_snapshot or {})["blocking"]]
    if blocked:
        claim = extract_claim(blocked[0].raw_snapshot or {})
        detail = f"{claim['label']}" + (f" · 사유 {claim['reason']}" if claim["reason"] else "")
        logger.warning("[NAVER] 클레임 건 주문 생성 차단 link=%s status=%s",
                       link_id, claim["status"])
        raise PromotionError(
            f"네이버에서 취소·반품이 진행 중인 주문입니다 ({detail}). "
            "네이버 판매자센터에서 상태를 확인한 뒤 진행하세요."
        )
    today = get_today_kst().strftime("%Y-%m-%d")
    try:
        order_fields, structured = map_group(
            [row.raw_snapshot for row in siblings], today=today)
    except NaverMappingError as exc:
        link.sync_status = "PENDING_REVIEW"
        link.failure_reason = str(exc)[:2000]
        raise PromotionError(f"원본을 주문으로 옮길 수 없습니다: {exc}") from exc

    # 네이버 결제액은 계약 총액이 아니라 **선금**이다 — 승격 경로에서만 자리를 옮긴다.
    apply_paid_amount_as_deposit(structured)

    order = create_order(
        session,
        actor_user_id=actor_user_id,
        owner_user_id=owner_user_id,
        order_fields=order_fields,
        structured_data=structured,
        is_erp_order=True,
        now=now or now_utc_naive(),
    )
    for row in siblings:
        row.order_id = order.id
        row.sync_status = "LINKED"
        row.failure_reason = None
    session.flush()
    logger.info("[NAVER] 수집분 주문 생성 link=%s(+%d) order=%s",
                link_id, len(siblings) - 1, order.id)
    return (int(order.id), True)


#: 기존 주문에 붙일 수 있는 관계. ``NEW`` 는 붙이기가 아니라 주문 생성 경로다.
ATTACHABLE_RELATIONS = ("ADDON", "REPAY")


#: 추가결제 기록이 사는 자리. 출고가·잔금 계산식은 건드리지 않는다(2026-08-19 사용자 확정).
EXTRA_PAYMENTS_KEY = "extra_payments"


#: 붙이기 **전에** 이 주문에 있던 예약금 — 네이버가 아닌 돈의 자리 (2026-09-03).
#: ERP 에 직접 등록한 주문에 추가결제를 붙이면 예약금은 `이 값 + 네이버 결제액` 이다.
#: 이 값이 없으면 도크가 네이버 결제액만 정답이라 말해, 원래 받았던 돈이 안내에서 증발한다.
NAVER_DEPOSIT_BASE_KEY = "naver_deposit_base"


def _extra_payment_entry(link: ExternalOrderLink, *, relation: str,
                         actor_user_id: Optional[int], now: datetime) -> dict[str, Any]:
    """링크 1건을 추가결제 기록 항목으로 만든다.

    Args:
        link: 붙이는 수집 링크.
        relation: ``ADDON`` 또는 ``REPAY``.
        actor_user_id: 누른 사람.
        now: 기록 시각(UTC naive).

    Returns:
        ``pricing.extra_payments`` 에 append 할 dict.
    """
    summary = summarize_snapshot(link.raw_snapshot)
    payment = build_payment_info(link.raw_snapshot or {})
    return {
        "external_id": link.external_id,
        "external_order_no": link.external_order_no,
        "relation": relation,
        "amount": summary["amount"] or 0,
        "product": summary["product"],
        "paid_at": payment["paid_at"][:16],
        "recorded_by": actor_user_id,
        "recorded_at": now.isoformat(),
    }


def _apply_extra_payments(order: Order, links: list[ExternalOrderLink], *, relation: str,
                          actor_user_id: Optional[int], now: datetime,
                          stamp_base: bool = False) -> int:
    """붙인 상품주문들의 결제 금액을 주문에 **기록**한다 (T16-F).

    **출고가·잔금·계약금을 자동으로 바꾸지 않는다.** 출고가는 규격 W·시공비와 얽혀 있어
    자동 가산이 다른 숫자까지 틀어놓는다(2026-08-19 사용자 확정: 기록만, 반영은 사람이).

    같은 ``external_id`` 가 이미 기록돼 있으면 건너뛴다(멱등 — 붙이기 두 번 눌러도 금액이
    두 번 쌓이면 안 된다).

    Args:
        order: 붙일 대상 주문.
        links: 붙는 링크들.
        relation: 관계값.
        actor_user_id: 누른 사람.
        now: 기록 시각.
        stamp_base: 네이버 돈이 이 주문에 **처음** 붙는가. 그러면 지금 예약금은 전부
            네이버 아닌 돈이므로 :data:`NAVER_DEPOSIT_BASE_KEY` 에 그 값을 새긴다 —
            도크가 "네이버 결제액 = 예약금 정답" 이라 말해 원래 받아 둔 돈을 안내에서
            지우던 자리다(2026-09-03 주문 #5112: 100,000원 증발). **처음 한 번만** 쓴다:
            두 번째 붙이기에서 다시 쓰면 사람이 이미 반영해 올려 둔 값이 바닥값으로
            둔갑해 안내가 그만큼 부풀어 오른다.

    Returns:
        새로 기록한 항목 수.
    """
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    data = copy.deepcopy(order.structured_data or {})
    pricing = data.get("pricing")
    if not isinstance(pricing, dict):
        pricing = {}
    existing = pricing.get(EXTRA_PAYMENTS_KEY)
    if not isinstance(existing, list):
        existing = []
    known = {str(row.get("external_id")) for row in existing if isinstance(row, dict)}

    based = False
    if stamp_base and not isinstance(pricing.get(NAVER_DEPOSIT_BASE_KEY), int):
        from foms.services.erp_display import erp_deposit_amount_from_structured

        pricing[NAVER_DEPOSIT_BASE_KEY] = int(
            erp_deposit_amount_from_structured(order.structured_data or {}) or 0)
        based = True

    added = 0
    for link in links:
        if str(link.external_id) in known:
            continue
        existing.append(_extra_payment_entry(link, relation=relation,
                                             actor_user_id=actor_user_id, now=now))
        known.add(str(link.external_id))
        added += 1
    if not (added or based):
        return 0

    pricing[EXTRA_PAYMENTS_KEY] = existing
    data["pricing"] = pricing
    order.structured_data = data
    flag_modified(order, "structured_data")
    return added


def _stamp_link_marker(order: Optional[Order]) -> bool:
    """붙인 주문의 **도크 렌더 게이트**(``structured_data['naver_linked']``)를 켠다.

    **이 한 줄이 없으면 붙이기 결과가 화면에 아예 나타나지 않는다.** 주문 편집 화면은
    게이트가 참일 때만 네이버 원본 도크를 렌더하고(``foms/web/orders/edit.py``), 방금
    기록한 추가결제(:data:`EXTRA_PAYMENTS_KEY`)를 읽는 코드는 그 도크 하나뿐이다
    (``dock.py._extra_payment_summary``). 게이트가 없으면 붙이기는 성공했는데 사람이 볼
    자리가 없다 — 2026-08-24 스테이징 실사례(주문 4485: 링크 264~269 가 REPAY 로 붙고
    1,610,780원이 기록됐는데 화면은 빈손).

    **2026-08-28 이전에는 이 자리가 출처 키를 찍었다.** 원래 도크 게이트가
    ``structured_data['source'] == SOURCE_MARKER`` 하나였기 때문에, 게이트를 켜려면 출처를
    덮어쓰는 수밖에 없었다. 그런데 그 키는 뜻이 둘이었다 — ① 주문 **출처**(누가 만들었나)
    ② 도크 **렌더 게이트**(보여 줄 원본이 있나). 그래서 예약금 건처럼 **ERP 에 직접 등록한
    주문**에 재결제를 붙이는 순간 그 주문이 네이버 출신으로 뒤집혔고, 주문 상세 뱃지가
    "네이버 스마트스토어에서 자동 수집된 주문입니다"라고 **거짓을 말했다**.

    **그렇다고 "그냥 안 찍기"는 오답이다** — 위 실사례가 정확히 그 상태였다. 그래서 뜻
    둘을 키 둘로 갈랐다(설계서 ``docs/specs/2026-08-28-naver-repay-origin-cancel_SPEC.md`` §7):

    * ``source`` = **출처 전용**. 작성자는 ``mapping.build_structured_data`` 하나뿐이고
      붙이기는 더 이상 이 키를 쓰지 않는다. 주문 상세 뱃지와 대시보드 ‘담당 미지정’
      모집단이 이 키를 계속 본다 — 둘 다 "자동 수집된 주문"을 뜻하므로 그게 맞다.
    * :data:`~foms.services.integrations.naver_commerce.constants.LINKED_MARKER_KEY`
      = **게이트 전용**. 여기서 찍는다. 출처를 주장하지 않는다.

    이미 옛 코드가 출처를 덮어써 버린 주문은 **소급 구별이 불가능하다**. 추정으로 되돌리면
    (‘링크가 붙어 있는데 NEW 관계가 없으면 ERP 출신’ 류) 추정이 데이터로 굳어 나중에 진짜와
    구별할 수 없으므로, 백필하지 않고 신규분부터 정확해지는 쪽을 택했다(설계서 §7.3).

    폼 저장이 이 키를 지우면 도크가 다시 닫힌다. 그래서 ``naver_linked`` 는 ERP 폼 저장
    보존 목록에 함께 올려 뒀다(``foms/api/erp_orders_structured.py`` 의
    ``_OPERATIONAL_TOP_LEVEL_KEYS``) — 2026-08-24 사고의 재발 경로가 정확히 그것이었다.

    Args:
        order: 대상 주문(None 이면 아무것도 하지 않는다).

    Returns:
        bool: 이번에 새로 켰으면 True(이미 켜져 있었으면 False — 멱등).
    """
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    from foms.services.integrations.naver_commerce.constants import LINKED_MARKER_KEY

    if order is None:
        return False
    data = order.structured_data
    if isinstance(data, dict) and data.get(LINKED_MARKER_KEY):
        return False
    updated = copy.deepcopy(data) if isinstance(data, dict) else {}
    updated[LINKED_MARKER_KEY] = True
    order.structured_data = updated
    flag_modified(order, "structured_data")
    logger.info("[NAVER] 네이버 도크 게이트 각인 order=%s", getattr(order, "id", None))
    return True


def _drop_extra_payments(order: Optional[Order], links: list[ExternalOrderLink]) -> int:
    """되돌리기 때 기록도 같이 걷어낸다 (T16-F).

    Args:
        order: 붙어 있던 주문(없으면 아무것도 하지 않는다).
        links: 되돌리는 링크들.

    Returns:
        지운 항목 수.
    """
    import copy

    from sqlalchemy.orm.attributes import flag_modified

    if order is None:
        return 0
    data = copy.deepcopy(order.structured_data or {})
    pricing = data.get("pricing")
    if not isinstance(pricing, dict):
        return 0
    rows = pricing.get(EXTRA_PAYMENTS_KEY)
    if not isinstance(rows, list) or not rows:
        return 0

    drop = {str(link.external_id) for link in links}
    kept = [row for row in rows
            if not (isinstance(row, dict) and str(row.get("external_id")) in drop)]
    removed = len(rows) - len(kept)
    if not removed:
        return 0

    pricing[EXTRA_PAYMENTS_KEY] = kept
    data["pricing"] = pricing
    order.structured_data = data
    flag_modified(order, "structured_data")
    return removed


def _mutation_hashes(*parts: Any) -> str:
    """scope/request hash — REV-00 receipt 용 sha256 hex."""
    import hashlib

    raw = "|".join(str(part) for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _record_extra_payments(session: Session, *, order_id: int,
                           links: list[ExternalOrderLink], relation: str,
                           actor_user_id: Optional[int], now: datetime,
                           stamp_base: bool = False) -> int:
    """추가결제 기록을 REV-00 mutation 계약(row lock·version bump·receipt)으로 남긴다.

    주문 JSONB 를 직접 쓰면 REV-99 writer 게이트에 걸린다 — 동시 편집과 부딪히면 남의 저장을
    덮어쓰기 때문이다. 기록도 같은 계약을 탄다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        order_id: 붙인 주문 id.
        links: 붙은 링크들.
        relation: ``ADDON``/``REPAY``.
        actor_user_id: 누른 사람(없으면 기록만 남기고 actor 는 0).
        now: 기록 시각.
        stamp_base: 네이버 돈이 이 주문에 **처음** 붙는가 — 그때의 예약금을 바닥값으로
            함께 새긴다(:data:`NAVER_DEPOSIT_BASE_KEY`).

    Returns:
        새로 기록한 항목 수.
    """
    from foms.services.orders.revision import execute_order_mutation

    recorded = 0

    def _mutate(sess: Session, orders: list[Order]) -> dict[int, list[str]]:
        nonlocal recorded
        target = orders[0]
        recorded = _apply_extra_payments(target, links, relation=relation,
                                         actor_user_id=actor_user_id, now=now,
                                         stamp_base=stamp_base)
        sess.flush()
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    external_ids = ",".join(sorted(str(row.external_id) for row in links))
    execute_order_mutation(
        session,
        actor_user_id=int(actor_user_id or 0),
        policy_id="NAVER_EXTRA_PAYMENT_RECORD",
        order_ids=[int(order_id)],
        scope_hash=_mutation_hashes("naver-attach", order_id),
        request_hash=_mutation_hashes(order_id, relation, external_ids),
        mutation=_mutate,
    )
    return recorded


def _erase_extra_payments(session: Session, *, order_id: Optional[int],
                          links: list[ExternalOrderLink],
                          actor_user_id: Optional[int]) -> int:
    """되돌리기 때 기록 제거도 같은 계약으로 한다.

    Args:
        session: DB 세션.
        order_id: 붙어 있던 주문 id(없으면 아무것도 하지 않는다).
        links: 되돌리는 링크들.
        actor_user_id: 누른 사람.

    Returns:
        지운 항목 수.
    """
    if not order_id:
        return 0

    from foms.services.orders.revision import execute_order_mutation

    removed = 0

    def _mutate(sess: Session, orders: list[Order]) -> dict[int, list[str]]:
        nonlocal removed
        target = orders[0]
        removed = _drop_extra_payments(target, links)
        sess.flush()
        return {target.id: [f"ORDER_DETAIL:{target.id}", "ORDERS_INDEX"]}

    external_ids = ",".join(sorted(str(row.external_id) for row in links))
    execute_order_mutation(
        session,
        actor_user_id=int(actor_user_id or 0),
        policy_id="NAVER_EXTRA_PAYMENT_ERASE",
        order_ids=[int(order_id)],
        scope_hash=_mutation_hashes("naver-detach", order_id),
        request_hash=_mutation_hashes(order_id, external_ids),
        mutation=_mutate,
    )
    return removed


def attach_link_to_order(session: Session, *, link_id: int, order_id: int,
                         relation: str, actor_user_id: Optional[int] = None,
                         now: Optional[datetime] = None) -> tuple[int, int, bool]:
    """수집분을 **기존 주문에 붙인다** — 새 주문을 만들지 않는다 (T16-E).

    차액 결제(ADDON)와 취소 후 재결제(REPAY)가 여기로 온다. 둘 다 새 집이 아니라 이미 있는
    집의 후속이라, 주문을 하나 더 만들면 같은 고객의 시공 건이 둘로 갈린다.

    묶음(집) 단위로 붙인다 — 네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 주므로
    한 건만 붙이면 나머지가 미아가 된다(:func:`_group_siblings` 와 같은 규칙).

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 수집 링크 id.
        order_id: 붙일 기존 FOMS 주문 id.
        relation: ``ADDON`` 또는 ``REPAY``.

    Returns:
        ``(붙인 링크 수, 주문 id, 실제로 바뀌었는가)``.

        세 번째 값이 ``False`` = **같은 주문에 같은 관계로 이미 붙어 있었다**(같은 버튼을
        두 번 누른 경우). 금액 기록은 원래 멱등이라 결과가 같지만, 호출자가 주문 변경
        이력에 줄을 더 쌓지 않도록 이 사실을 알려 준다(2026-08-25 정책).

    Raises:
        PromotionError: 관계값·링크·주문이 잘못됐거나, 취소·반품 건을 ADDON 으로 붙이려 할 때,
            또는 이미 **다른** 주문에 붙어 있을 때.
    """
    if relation not in ATTACHABLE_RELATIONS:
        raise PromotionError(f"붙일 수 없는 관계입니다 ({relation}).")

    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")

    order = session.get(Order, int(order_id))
    if order is None or order.deleted_at is not None or order.status == "DELETED":
        raise PromotionError(f"붙일 주문을 찾을 수 없습니다 (order {order_id}).")

    siblings = _group_siblings_for_attach(session, link)
    # 네이버 돈이 **처음** 붙는 주문이면, 지금 예약금은 전부 네이버 아닌 돈이다. 그 값을
    # 새겨 두지 않으면 도크가 "네이버 결제액 = 예약금 정답"이라 말해, ERP 에서 직접 받은
    # 예약금이 안내에서 통째로 사라진다(2026-09-03 주문 #5112 실사례: 100,000원 증발).
    first_naver_money = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.order_id == int(order_id),
                ExternalOrderLink.channel == CHANNEL)
        .first()
        is None
    )
    # 취소·반품 건은 추가결제로 붙이지 않는다 — 재결제(REPAY)는 원 주문이 취소된 경우라 허용.
    if relation == "ADDON":
        blocked = [row for row in siblings if extract_claim(row.raw_snapshot or {})["blocking"]]
        if blocked:
            claim = extract_claim(blocked[0].raw_snapshot or {})
            raise PromotionError(
                f"네이버에서 취소·반품이 진행 중인 주문입니다 ({claim['label']}). "
                "추가결제로 붙일 수 없습니다."
            )

    attached = 0
    changed = False
    for row in siblings:
        if row.order_id and int(row.order_id) != int(order_id):
            raise PromotionError(
                f"이미 다른 주문(#{row.order_id})에 붙어 있습니다. 먼저 되돌린 뒤 다시 붙이세요."
            )
        # 이 줄이 실제로 무엇을 바꾸는지 **쓰기 전에** 본다 — 같은 버튼을 두 번 눌렀을 때
        # 호출자가 이력에 줄을 더 쌓지 않게 하는 근거다.
        if (row.order_id is None or int(row.order_id) != int(order_id)
                or str(row.relation or "") != relation
                or str(row.sync_status or "") != "LINKED"
                or row.failure_reason):
            changed = True
        row.order_id = int(order_id)
        row.relation = relation
        row.sync_status = "LINKED"
        row.failure_reason = None
        attached += 1
    session.flush()
    stamped = _stamp_link_marker(order)
    # 금액은 **기록만** 한다 — 출고가·잔금 계산식은 그대로다(T16-F).
    # 기록 자체는 REV-00 mutation 계약(row lock·version bump·receipt)을 탄다.
    recorded = _record_extra_payments(session, order_id=int(order_id), links=siblings,
                                      relation=relation, actor_user_id=actor_user_id,
                                      now=now or now_utc_naive(),
                                      stamp_base=first_naver_money)
    logger.info("[NAVER] 수집분 기존 주문 연결 link=%s(+%d) order=%s relation=%s 결제기록 %d건",
                link_id, attached - 1, order_id, relation, recorded)
    # 도크 게이트 켜기·금액 기록도 '바뀜'이다 — 링크 행이 그대로여도 주문 쪽이 움직였으면
    # 이력에 남을 값이 있다.
    return (attached, int(order_id), bool(changed or recorded or stamped))


def detach_link_from_order(session: Session, *, link_id: int,
                           actor_user_id: Optional[int] = None) -> tuple[int, Optional[int]]:
    """붙이기를 되돌린다 (T16-E) — 사람이 관계를 잘못 골랐을 때.

    ``NEW`` 로 만든 주문(승격)은 되돌리지 않는다. 그건 주문 삭제 문제라 이 경로의 일이 아니다.

    Args:
        session: DB 세션(호출자가 commit 을 소유한다).
        link_id: 기준 수집 링크 id.

    Returns:
        ``(되돌린 링크 수, 원래 붙어 있던 주문 id)``.

    Raises:
        PromotionError: 링크가 없거나, 붙이기로 연결된 건이 아닐 때.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        raise PromotionError(f"수집 기록을 찾을 수 없습니다 (link {link_id}).")
    if link.relation not in ATTACHABLE_RELATIONS:
        raise PromotionError("붙이기로 연결된 건이 아닙니다(주문 생성분은 되돌릴 수 없습니다).")

    previous_order_id = int(link.order_id) if link.order_id else None
    siblings = [row for row in _group_siblings_for_attach(session, link)
                if row.relation in ATTACHABLE_RELATIONS]
    # 붙일 때 남긴 결제 기록도 함께 걷어낸다 — 안 지우면 되돌린 금액이 주문에 남는다(T16-F).
    _erase_extra_payments(session, order_id=previous_order_id, links=siblings,
                          actor_user_id=actor_user_id)
    for row in siblings:
        row.order_id = None
        row.relation = "NEW"
        row.sync_status = "COLLECTED"
    session.flush()
    logger.info("[NAVER] 붙이기 되돌림 link=%s(+%d) order=%s",
                link_id, len(siblings) - 1, previous_order_id)
    return (len(siblings), previous_order_id)


def summarize_link_household(session: Session, *, link_id: int,
                             relations: Optional[tuple[str, ...]] = None) -> dict[str, Any]:
    """이력에 남길 **집** 요약 — 외부 주문번호·상품주문 건수·금액 합계 (스펙 2026-08-24 R3).

    붙이기·되돌리기 라우트가 주문 변경 이력(``OrderEvent``)에 적을 숫자를 만든다. 집 판정을
    라우트에서 다시 짜면 화면·발주확인과 어긋난 숫자가 이력에 박히므로(집 세기 SSOT 이탈),
    붙이기와 **같은** 묶음 함수(:func:`_group_siblings_for_attach`)를 그대로 쓴다.

    **변경 전에 부른다.** 되돌리기는 ``relation`` 을 ``NEW`` 로 되돌리므로 뒤에 부르면 관계값도
    대상 집합도 이미 사라져 있다.

    Args:
        session: DB 세션(읽기만 한다).
        link_id: 기준 수집 링크 id.
        relations: 셀 관계값(``None`` 이면 집 전체 — 붙이기는 집이 통째로 움직인다).
            되돌리기는 :data:`ATTACHABLE_RELATIONS` 만 걷어내므로 같은 값을 넘긴다.

    Returns:
        ``{"external_order_no", "relation", "product_order_count", "amount_total"}``.
        링크가 없으면 빈 요약(건수 0)을 돌려준다 — 이력 기록이 붙이기를 깨지 않는다.
    """
    link = (
        session.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == CHANNEL)
        .first()
    )
    if link is None:
        return {"external_order_no": "", "relation": "",
                "product_order_count": 0, "amount_total": 0}

    rows = _group_siblings_for_attach(session, link)
    if relations is not None:
        rows = [row for row in rows if row.relation in relations]
    total = 0
    for row in rows:
        amount = summarize_snapshot(row.raw_snapshot).get("amount")
        total += int(amount) if isinstance(amount, int) else 0
    return {
        "external_order_no": (link.external_order_no or "").strip(),
        "relation": (link.relation or "").strip(),
        "product_order_count": len(rows),
        "amount_total": total,
    }


def _group_siblings_for_attach(session: Session,
                               link: ExternalOrderLink) -> list[ExternalOrderLink]:
    """붙이기·되돌리기 대상 묶음 — 같은 **집**의 링크 전부.

    승격용 :func:`_group_siblings` 는 **주문이 없는** 링크만 모은다(부분 생성 방어). 붙이기는
    반대로 이미 같은 주문에 붙은 형제까지 함께 다뤄야 되돌리기가 반쪽이 되지 않는다.

    주문번호로만 묶으면 안 된다 — 분할배송(같은 주문번호·다른 주소)에서 A집을 붙이면
    B집 링크까지 남의 주문으로 넘어가고 큐에서 사라진다. 집 판정은 화면·발주확인과
    같은 규칙(:func:`fulfillment.household_key` = ``mapping.group_key``)을 쓴다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import household_key

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


def _group_siblings(session: Session, link: ExternalOrderLink) -> list[ExternalOrderLink]:
    """같은 묶음(주문번호·수취인 전화·주소)의 **주문 미생성** 링크들을 모은다.

    묶음 키에 전화·주소가 들어가는 이유는 분할배송이다 — 같은 주문번호라도 수취인이 다르면
    합치면 안 된다(남의 주소로 시공 나가는 사고).

    이미 주문이 붙은 형제는 제외한다. 사람이 부분적으로 먼저 만들었을 수 있고, 그때 다시
    묶으면 같은 상품주문이 두 주문에 들어간다.

    Args:
        session: DB 세션.
        link: 기준 링크(반드시 결과에 포함된다).

    **순서가 의미를 갖는다**: 추가옵션 귀속(:mod:`attribution`)이 수집 순서를 읽으므로
    기준 링크를 앞으로 끌어내면 안 된다 — 그러면 본품 2개짜리 집이 ``M M a a`` 배치로
    보여 옵션이 한 본품에 몰린다(2026-08-19 스테이징 실사고: 12건이 180cm 본품에 몰림).
    그래서 **기준 링크를 포함한 전체를 id(수집) 순으로** 돌려준다.

    Returns:
        묶을 링크 목록 — **수집 순서(id 오름차순)**.
    """
    key = group_key(link.raw_snapshot or {})
    order_no = key[0]
    if not order_no:
        return [link]

    candidates = (
        session.query(ExternalOrderLink)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.external_order_no == order_no,
            ExternalOrderLink.order_id.is_(None),
            # 술어 SSOT — 화면 재진술(:func:`is_promotable`)과 같은 목록을 쓴다.
            ExternalOrderLink.sync_status.in_(PROMOTABLE_SYNC_STATUSES),
            ExternalOrderLink.id != link.id,
        )
        .with_for_update()
        .order_by(ExternalOrderLink.id)
        .all()
    )
    siblings = [link]
    for row in candidates:
        if isinstance(row.raw_snapshot, dict) and group_key(row.raw_snapshot) == key:
            siblings.append(row)
    return sorted(siblings, key=lambda row: row.id)


def summarize_snapshot(raw_snapshot: Any) -> dict[str, Any]:
    """목록 표시용 요약(고객·제품·수량·금액·옵션 원문)을 원본에서 뽑는다.

    주문이 아직 없어도 사람이 무엇을 받았는지 보고 판단할 수 있어야 한다. 매핑이 실패하는
    원본도 있으므로 **실패해도 빈 값으로 돌려준다**(목록이 통째로 죽으면 안 된다).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        dict: ``customer_name``·``product``·``options``·``quantity``·``amount``·``order_date``
        + 클레임 표시(``claim_*``) + 발주 상태(``place_*`` — T16-A).
    """
    empty = {"customer_name": "", "product": "", "options": "",
             "quantity": None, "amount": None, "order_date": "",
             "claim_label": "", "claim_blocking": False,
             # 원본이 없거나 깨졌으면 "발주확인 여부를 모른다" — 완료로 읽지 않는다.
             "place_status": "", "place_label": "", "place_confirmed": False,
             "shipping_due": "",
             # 쿠폰 축(2026-08-25). 원본이 깨졌으면 "쿠폰 없음"이 아니라 **모름**이다 —
             # 0 장으로 단정하면 화면이 "쿠폰 없음"이라고 거짓말한다.
             "coupon_known": False, "coupon_count": 0,
             "coupon_discount": 0, "coupon_seller_burden": 0}
    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return empty
    try:
        from foms.services.integrations.naver_commerce.mapping import unwrap_detail

        _order, product_order, shipping = unwrap_detail(raw_snapshot)
    except (NaverMappingError, ValueError, TypeError, AttributeError) as exc:
        logger.warning("[NAVER] 목록 요약 실패(빈 값으로 표시): %s", exc)
        return empty

    product_order = product_order or {}
    shipping = shipping or {}
    quantity = product_order.get("quantity")
    amount = product_order.get("totalPaymentAmount")
    claim = extract_claim(raw_snapshot)
    place = extract_place_status(raw_snapshot)
    return {
        "customer_name": str(shipping.get("name") or "").strip(),
        "product": str(product_order.get("productName") or "").strip(),
        "options": str(product_order.get("productOption") or "").strip(),
        "quantity": int(quantity) if isinstance(quantity, int) else None,
        "amount": int(amount) if isinstance(amount, int) else None,
        "order_date": str((_order or {}).get("orderDate") or "")[:10],
        # 목록에서도 취소 건을 알아볼 수 있어야 한다(빈 문자열이면 정상 주문).
        "claim_label": claim["label"],
        "claim_blocking": claim["blocking"],
        # 발주확인 여부는 수집 시점 원본에 이미 들어온다 — 네이버 호출 0회로 표시한다(T16-A).
        "place_status": place["status"],
        "place_label": place["label"],
        "place_confirmed": place["confirmed"],
        "shipping_due": place["shipping_due"][:10],
        # 쿠폰 — 담당자가 금액을 볼 때 같이 봐야 하는 사실이다. 장수·할인액만이 아니라
        # **판매자 부담분**을 따로 낸다: 네이버 100% 부담 쿠폰은 우리 정산액을 깎지 않는다.
        **_coupon_facts(raw_snapshot),
    }


def _coupon_facts(raw_snapshot: Any) -> dict[str, Any]:
    """이 상품주문에 적용된 쿠폰 요약 (2026-08-25).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``coupon_known``(원본을 읽었는가) · ``coupon_count`` · ``coupon_discount``
        · ``coupon_seller_burden``. 부담 비율이 없는 쿠폰은 부담액에 더하지 않는다
        (모르는 값을 0 으로 세면 "우리 부담 없음"으로 읽힌다).
    """
    from foms.services.integrations.naver_commerce.mapping import (
        build_payment_info,
        unwrap_detail,
    )

    unknown = {"coupon_known": False, "coupon_count": 0,
               "coupon_discount": 0, "coupon_seller_burden": 0}
    try:
        _order, product_order, _shipping = unwrap_detail(raw_snapshot)
        # 상품주문으로 보이지 않으면 **읽은 게 아니다.** 여기서 0 장을 돌려주면 화면이
        # "쿠폰 사용 안 함" 이라고 단정하는데, 사실 원본은 그 말을 한 적이 없다.
        # 판정은 `productOrderId` 로 한다 — 실데이터 250건 전부가 갖고 있고,
        # `unwrap_detail` 은 낯선 dict 를 그대로 상품주문 취급해 돌려주기 때문이다.
        if not isinstance(product_order, dict) or not product_order.get("productOrderId"):
            return unknown
        coupons = build_payment_info(raw_snapshot)["coupons"]
    except (NaverMappingError, ValueError, TypeError, AttributeError, KeyError) as exc:
        logger.warning("[NAVER] 쿠폰 요약 실패(모름으로 표시): %s", exc)
        return unknown
    return {
        "coupon_known": True,
        "coupon_count": len(coupons),
        "coupon_discount": sum(int(row["discount_amount"] or 0) for row in coupons),
        "coupon_seller_burden": sum(int(row["seller_burden_amount"] or 0)
                                    for row in coupons
                                    if row.get("seller_burden_amount") is not None),
    }


# ``apply_paid_amount_as_deposit`` 은 **일부러 빼 둔다**. 갓 매핑한 dict 전용이라
# 이미 옮겨진 주문에 다시 부르면 안 되는데, __all__ 에 있으면 "쓰라고 만든 것" 으로 읽힌다.
__all__ = ["PromotionError", "promote_link_to_order", "summarize_snapshot",
           "attach_link_to_order", "detach_link_from_order", "ATTACHABLE_RELATIONS",
           "EXTRA_PAYMENTS_KEY", "ITEM_PAID_AMOUNT_KEY", "NAVER_DEPOSIT_BASE_KEY"]

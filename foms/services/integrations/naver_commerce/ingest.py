"""네이버 수집 파이프라인 — 변경분 조회 → 필터 → 상세 → **링크 보관** (NAVER-INGEST-01 §3.3, T12).

**주문을 만들지 않는다.** 스윕의 결과물은 ``ExternalOrderLink`` 행(원본 스냅샷 포함)이고,
FOMS 주문은 사람이 관리 화면에서 "주문 만들기"를 눌렀을 때
:mod:`~foms.services.integrations.naver_commerce.promotion` 이 만든다.

왜 나눴나(2026-08-14 사용자 결정): 결제완료가 곧 FOMS 주문은 아니다. 자동 생성은 사람이
보기도 전에 대시보드·퀘스트·지오코딩 큐를 채우고, 되돌리려면 주문 삭제까지 해야 한다.
수집은 놓치면 복구가 어렵고(그래서 자동), 생성은 판단이다(그래서 수동).

**WORKER 프로세스 전용**이다. web 에서 부르면 커머스API센터에 등록되지 않은 IP 라 차단된다
(IP 슬롯 3개를 WORKER 가 전부 쓴다 — 스펙 §3.1). web 의 "지금 수집" 은 rq enqueue 만 한다.

멱등 규칙(두 겹):

1. 조회 전 ``ExternalOrderLink`` 에 이미 있는 ``productOrderId`` 를 걸러낸다(호출 절약).
2. 그래도 동시 실행이 겹치면 ``UNIQUE (channel, external_id)`` 가 DB 에서 막는다. 그때는
   실패가 아니라 **정상 skip** 으로 센다. 앱 선체크만으로는 체크와 INSERT 사이 창을 못 막는다.

매핑은 수집 시점에도 1회 돌려 필수값을 검증한다. 실패하면 ``PENDING_REVIEW`` 로 남긴다 —
"주문 만들기를 눌렀는데 그제서야 실패"를 막는다(쓰레기 주문 생성 방지 — 스펙 §5).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from foms.services.datetime_kst import get_today_kst, now_utc_naive
from foms.services.integrations.naver_commerce.accounts import (
    IngestAccountError as _IngestAccountError,
    resolve_ingest_account_ids as _resolve_ingest_account_ids,
)
from foms.services.integrations.naver_commerce.constants import (
    ACTOR_USERNAME as _ACTOR_USERNAME,
    CHANNEL as _CHANNEL,
    OWNER_USERNAME as _OWNER_USERNAME,
)
from foms.services.integrations.naver_commerce.claim_watch import refresh_claims
from foms.services.integrations.naver_commerce.mapping import (
    COLLECTIBLE_STATUS,
    NaverMappingError,
    extract_external_id,
    map_detail,
)
from models import ExternalOrderLink

logger = logging.getLogger(__name__)

# 상수 정본은 constants.py 다(의존성 없는 모듈). web 화면도 같은 값을 알아야 하는데 이 모듈을
# import 하면 web 이 수집 파이프라인을 끌어오게 되어 WORKER 단일 출구 계약이 흐려진다.
CHANNEL = _CHANNEL
ACTOR_USERNAME = _ACTOR_USERNAME
OWNER_USERNAME = _OWNER_USERNAME


@dataclass
class SyncResult:
    """한 번의 수집 실행 결과(운영 로그·관리 화면 표시용)."""

    changed: int = 0            # 변경분 이벤트 총건수
    candidates: int = 0         # 그중 결제완료(PAYED) 후보
    fetched: int = 0            # 상세를 실제로 받아온 건수
    collected: int = 0          # 링크로 보관한 건수(T12 — 주문은 만들지 않는다)
    skipped: int = 0            # 이미 수집된 건(멱등 skip)
    pending_review: int = 0     # 매핑 실패로 보류한 건
    claims_refreshed: int = 0   # 수집 후 변경분 재조회로 원본을 갱신한 건 (T14-F)
    claims_flagged: int = 0     # 그중 취소·반품 상태인 건
    claims_notified: int = 0    # 그로 인해 보낸 알림 건수
    quiet_collected: int = 0    # 처음 본 비결제완료 건(큐 밖으로 수집 — D1)
    dropped_by_status: dict[str, int] = field(default_factory=dict)  # 상태별 버린 건수(D3)
    link_ids: list[int] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        """JSON 출력용 dict(runner --json 이 그대로 찍는다).

        ``created`` 는 **항상 0** 으로 함께 싣는다 — 워터마크에 남은 옛 요약과 관리 화면이
        같은 키를 읽어 오므로 키를 없애면 과거 실행 기록 표시가 깨진다.
        """
        return {
            "changed": self.changed,
            "candidates": self.candidates,
            "fetched": self.fetched,
            "collected": self.collected,
            "created": 0,
            "skipped": self.skipped,
            "pending_review": self.pending_review,
            "claims_refreshed": self.claims_refreshed,
            "claims_flagged": self.claims_flagged,
            "claims_notified": self.claims_notified,
            "quiet_collected": self.quiet_collected,
            "dropped_by_status": dict(self.dropped_by_status),
            "link_ids": list(self.link_ids),
            "errors": list(self.errors),
        }


# 계정 해석기는 ``accounts`` 로 옮겼다(주문 생성이 web 에서도 일어나므로 — WORKER 단일 출구
# 계약 때문에 web 이 이 모듈을 import 하면 안 된다). 기존 호출자·테스트를 위해 이름만 남긴다.
IngestAccountError = _IngestAccountError
resolve_ingest_accounts = _resolve_ingest_account_ids


def existing_external_ids(session: Session, external_ids: list[str]) -> set[str]:
    """이미 링크된 ``productOrderId`` 집합을 배치 조회로 구한다(N+1 금지)."""
    if not external_ids:
        return set()
    rows = (
        session.query(ExternalOrderLink.external_id)
        .filter(
            ExternalOrderLink.channel == CHANNEL,
            ExternalOrderLink.external_id.in_(external_ids),
        )
        .all()
    )
    return {row[0] for row in rows}


def _record_pending(session: Session, *, external_id: str, detail: dict, reason: str) -> None:
    """매핑 실패 건을 주문 없이 보류 링크로 남긴다(원본 보존).

    보류분도 매칭 축 사본을 채운다 — 보류라고 해서 "안 붙은 집" 짚기에서 빠지면,
    사람이 손볼 건일수록 화면이 조용해진다.
    """
    _order, product_order, _shipping = _safe_unwrap(detail)
    match_keys = _match_key_values(detail)
    session.add(
        ExternalOrderLink(
            channel=CHANNEL,
            external_id=external_id,
            order_id=None,
            external_order_no=str((_order or {}).get("orderId") or "") or None,
            raw_snapshot=detail,
            sync_status="PENDING_REVIEW",
            place_order_status=_place_status_value(detail),
            group_key=_group_key_value(detail),
            recipient_name=match_keys["recipient_name"],
            recipient_phone_digits=match_keys["recipient_phone_digits"],
            orderer_phone_digits=match_keys["orderer_phone_digits"],
            failure_reason=reason[:2000],
        )
    )
    session.flush()


def _place_status_value(detail: dict) -> Optional[str]:
    """원본에서 발주 상태를 뽑아 컬럼에 넣을 값으로 만든다(없으면 None).

    정본은 ``raw_snapshot`` 이고 이 컬럼은 필터 전용 사본이다 — 추출이 실패해도 수집은
    막지 않는다(못 받은 주문은 되돌릴 수 없다).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        상태 문자열(최대 20자) 또는 None.
    """
    try:
        from foms.services.integrations.naver_commerce.mapping import extract_place_status

        status = extract_place_status(detail)["status"]
    except (ValueError, TypeError, AttributeError, KeyError) as exc:  # 표시용 값이라 흐름을 막지 않는다
        logger.warning("[NAVER] 발주 상태 추출 실패(무시): %s", exc)
        return None
    return status[:20] or None


def _match_key_values(detail: dict) -> dict[str, Optional[str]]:
    """원본에서 매칭 축 사본(수령인명·수취인 전화·주문자 전화)을 뽑는다.

    ``_group_key_value`` 와 같은 규약이다 — 정본은 ``raw_snapshot`` 이고 이 값들은 SQL 이
    "오늘 실측인데 안 붙은 집"을 좁힐 수 있게 두는 필터 전용 사본이다. 추출이 실패해도
    수집은 막지 않는다(못 받은 주문은 되돌릴 수 없다).

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        ``{"recipient_name", "recipient_phone_digits", "orderer_phone_digits"}``.
        못 뽑으면 값은 None(읽는 쪽이 옛 스캔 경로로 폴백한다).
    """
    empty = {"recipient_name": None, "recipient_phone_digits": None,
             "orderer_phone_digits": None}
    try:
        from foms.services.integrations.naver_commerce.order_candidates import _snapshot_keys

        keys = _snapshot_keys(detail)
    except (ValueError, TypeError, AttributeError, KeyError, ImportError) as exc:
        logger.warning("[NAVER] 매칭 축 사본 추출 실패(무시): %s", exc)
        return empty
    return {
        "recipient_name": (keys.get("name") or "")[:80] or None,
        "recipient_phone_digits": (keys.get("recipient_phone") or "")[:20] or None,
        "orderer_phone_digits": (keys.get("orderer_phone") or "")[:20] or None,
    }


def _group_key_value(detail: dict) -> Optional[str]:
    """원본에서 묶음('집') 키를 만들어 컬럼에 넣을 값으로 만든다(못 만들면 None).

    ``_place_status_value`` 와 같은 규약이다 — 정본은 ``raw_snapshot`` 이고 이 컬럼은
    이력 표가 SQL 로 집을 셀 수 있게 하는 사본이다. 추출이 실패해도 수집은 막지 않는다
    (못 받은 주문은 되돌릴 수 없다). 값이 없으면 읽는 쪽이 주문번호로 폴백한다.

    Args:
        detail: 상품주문 상세 1건.

    Returns:
        묶음키 문자열 또는 None.
    """
    try:
        from foms.services.integrations.naver_commerce.mapping import group_key_text

        return group_key_text(detail) or None
    except (ValueError, TypeError, AttributeError, KeyError) as exc:  # 표시용 사본이라 흐름을 막지 않는다
        logger.warning("[NAVER] 묶음키 계산 실패(무시): %s", exc)
        return None


def _safe_unwrap(detail: dict) -> tuple[dict, dict, dict]:
    """매핑 모듈의 unwrap 을 쓰되 실패해도 흐름을 막지 않는다."""
    from foms.services.integrations.naver_commerce.mapping import unwrap_detail

    try:
        return unwrap_detail(detail)
    except Exception as exc:  # noqa: BLE001 - 보류 기록 경로라 실패해도 진행한다
        logger.warning("[NAVER] 상세 unwrap 실패(보류 기록은 계속): %s", exc, exc_info=True)
        return ({}, {}, {})


#: 상태 문자열이 아예 없는 변경 이벤트를 셀 때 쓰는 자리표시 키(D3 카운터용).
UNKNOWN_STATUS = "UNKNOWN"


def _feed_status_map(changed: list[dict]) -> dict[str, str]:
    """변경 이벤트 목록을 ``{상품주문번호: 대표 상태}`` 로 접는다.

    같은 상품주문에 이벤트가 여러 개 실려 오면 ``PAYED`` 를 우선한다 — 결제완료 이벤트가
    하나라도 있으면 그 건은 지금까지와 똑같이 처리 큐 안으로 들어가야 한다.

    Args:
        changed: ``last-changed-statuses`` 응답 항목 목록.

    Returns:
        상품주문번호 → 상태(대문자) 사전. 번호가 없는 항목은 버린다.
    """
    folded: dict[str, str] = {}
    for entry in changed or []:
        if not isinstance(entry, dict):
            continue
        external_id = str(entry.get("productOrderId") or "")
        if not external_id:
            continue
        if folded.get(external_id) == COLLECTIBLE_STATUS:
            continue
        folded[external_id] = str(entry.get("productOrderStatus") or "").upper() or UNKNOWN_STATUS
    return folded


def _partition_feed(
    folded: dict[str, str], known: set[str], *, collect_all: bool,
) -> tuple[list[str], set[str], dict[str, int]]:
    """변경 피드를 후보/조용한 후보/버린 것으로 가른다 (D1·D3).

    규칙 세 줄이 전부다:

    * ``PAYED`` 는 지금까지와 똑같이 후보다(처리 큐 안).
    * **우리가 모르는** 상품주문번호는 상태와 무관하게 후보로 삼되 '조용한' 쪽에 넣는다.
      결제가 스윕 시작보다 앞서고 그 뒤 상태 변경만 있는 주문은 결제완료 이벤트를 영영
      다시 주지 않아, 상태로 거르면 어느 경로에도 안 걸린다(운영 실측 2026-09-02).
      수집 대상 상태를 열거하는 방식은 쓰지 않는다 — 관측하지 못한 상태에서 같은 누락이
      되풀이된다.
    * 이미 아는 번호의 비결제완료 이벤트는 지금처럼 상세를 조회하지 않는다(호출량 불변).
      대신 상태별로 세어 남긴다 — 무음으로 버리면 사후 규명이 불가능하다.

    Args:
        folded: :func:`_feed_status_map` 결과.
        known: 이미 링크가 있는 상품주문번호 집합.
        collect_all: True 면 상태로 거르지 않는다(과거 구간 소급 수집).

    Returns:
        ``(후보 번호 목록, 조용히 넣을 번호 집합, 상태별 버린 건수)``.
    """
    if collect_all:
        return (list(folded.keys()), set(), {})
    candidates: list[str] = []
    quiet: set[str] = set()
    dropped: dict[str, int] = {}
    for external_id, status in folded.items():
        if status == COLLECTIBLE_STATUS:
            candidates.append(external_id)
        elif external_id in known:
            dropped[status] = dropped.get(status, 0) + 1
        else:
            candidates.append(external_id)
            quiet.add(external_id)
    return (candidates, quiet, dropped)


def ingest_detail(
    session: Session, detail: dict, *, today: str, now: Optional[datetime] = None,
    reviewed: bool = False, reviewed_reason: str = "backfill",
) -> str:
    """상세 1건을 **링크로만** 보관한다(주문은 만들지 않는다). 결과 코드를 돌려준다.

    T12 에서 수집과 주문 생성을 분리했다. 스윕은 원본을 그대로 남기고(``COLLECTED``),
    ``create_order()`` 는 사람이 관리 화면에서 "주문 만들기"를 누를 때
    :mod:`~foms.services.integrations.naver_commerce.promotion` 이 부른다.

    왜: 결제완료가 곧 FOMS 주문은 아니다. 자동 생성은 사람이 보기도 전에 대시보드·퀘스트·
    지오코딩 큐를 채워 되돌리기가 비싸다. 수집은 놓치면 안 되고(자동), 생성은 판단이다(수동).

    매핑은 이 시점에도 한 번 돌린다 — 필수값이 없으면 ``PENDING_REVIEW`` 로 남겨
    "나중에 주문 만들기를 눌렀는데 그제서야 실패"하는 상황을 막는다.

    Args:
        session: 호출자 소유 세션(커밋은 호출자).
        detail: 상품주문 상세 1건.
        today: 접수일 대체값(매핑 검증용).
        now: 테스트용 시각 주입.
        reviewed: True 면 만든 링크를 **확인 완료로 표시**해 처리 큐에 넣지 않는다.
            과거 구간 소급 수집이 쓰는 자리다 — 백필은 "과거 원본을 확보"하는 일이지 "지금
            처리할 일"이 아니다. 표시하지 않으면 90일치 전 주문이 통째로 처리 탭에 쌓인다
            (스테이징 실측 2026-09-01: 링크 1,560건 = 798집이 큐에 밀려들었다).
            정기 스윕이 뒤늦게 처음 본 비결제완료 건도 같은 규율로 넣는다.
        reviewed_reason: ``reviewed`` 표식을 남길 때 쓸 ``triage_state`` 키
            (``"backfill"`` = 과거 긁어오기, ``"sweep_unknown"`` = 스윕이 처음 본 건).

    Returns:
        ``"collected"`` / ``"skipped"`` / ``"pending_review"``.
    """
    external_id = extract_external_id(detail)
    if not external_id:
        # 멱등 키가 없으면 링크 행조차 만들 수 없다(UNIQUE 키의 절반이 빈다).
        raise NaverMappingError("productOrderId 가 없어 링크를 만들 수 없다")

    try:
        map_detail(detail, today=today)
    except NaverMappingError as exc:
        _record_pending(session, external_id=external_id, detail=detail, reason=str(exc))
        return "pending_review"

    order_no = str((_safe_unwrap(detail)[0] or {}).get("orderId") or "") or None
    # 백필 표식은 **두 벌**이다: 큐를 비우는 ``reviewed_at`` 과, 나중에 "이건 소급분"임을
    # 되짚을 ``triage_state.backfill``. 시각만 남기면 사람이 확인한 것과 구분되지 않는다.
    match_keys = _match_key_values(detail)
    stamp = now_utc_naive() if reviewed else None
    state = {reviewed_reason: {"at": stamp.isoformat()}} if reviewed else None
    savepoint = session.begin_nested()
    try:
        session.add(
            ExternalOrderLink(
                channel=CHANNEL,
                external_id=external_id,
                order_id=None,
                external_order_no=order_no,
                raw_snapshot=detail,
                sync_status="COLLECTED",
                # 발주 상태 사본 — 목록 필터가 JSONB 를 스캔하지 않게 한다(T16-B).
                place_order_status=_place_status_value(detail),
                # 묶음키 사본 — 이력 표가 확인 큐와 같은 정의로 집을 셀 수 있게 한다.
                group_key=_group_key_value(detail),
                # 매칭 축 사본 — 없으면 "안 붙은 집" 매칭이 300행 캡 스캔으로 떨어진다.
                recipient_name=match_keys["recipient_name"],
                recipient_phone_digits=match_keys["recipient_phone_digits"],
                orderer_phone_digits=match_keys["orderer_phone_digits"],
                reviewed_at=stamp,
                triage_state=state,
            )
        )
        session.flush()
        savepoint.commit()
    except IntegrityError:
        # UNIQUE (channel, external_id) — 동시 실행이 먼저 만든 것. 실패가 아니라 skip.
        savepoint.rollback()
        logger.info("[NAVER] 중복 수집 차단(UNIQUE) — productOrderId=%s", external_id)
        return "skipped"
    return "collected"


def sync_naver_orders(
    session: Session, *, client: Any, start: datetime, end: datetime,
    dry_run: bool = False, now: Optional[datetime] = None,
    notify_claims: bool = True, collect_all: bool = False,
    mark_reviewed: bool = False,
) -> SyncResult:
    """한 구간을 수집한다(호출자가 commit 을 소유한다).

    Args:
        session: DB 세션.
        client: :class:`~foms.services.integrations.naver_commerce.client.NaverCommerceClient`.
        start: 구간 시작(워터마크).
        end: 구간 끝(보통 지금).
        dry_run: True 면 조회까지만 하고 링크를 만들지 않는다.
        now: 테스트용 시각 주입.
        notify_claims: False 면 취소·반품 상태는 반영하되 **알림을 만들지 않는다**
            (과거 구간 소급 수집 — 지난 클레임으로 알림을 대량 발송하지 않기 위해).
        collect_all: True 면 **상태로 거르지 않고** 변경 목록에 뜬 상품주문을 전부 후보로
            삼는다. 과거 구간 소급 수집 전용이다 — 변경 피드의 ``productOrderStatus`` 는
            이벤트 당시가 아니라 **현재 상태**라서(스테이징 실측 2026-09-01: 06-04~08-16
            이벤트 1,300건 중 PAYED 0건), 오래된 주문은 이미 배송완료·구매확정으로 넘어가
            결제완료 필터에 하나도 안 걸린다. 결과가 "긁었는데 0건"이라 조용히 실패한다.
            ``lastChangedType`` 으로 이벤트 축을 좁히는 길도 있으나 그 enum 값이 공개
            문서에 없어(지어내지 않는다) 상세 조회 결과를 정본으로 삼는다.
        mark_reviewed: True 면 만든 링크를 확인 완료로 표시해 처리 큐에 넣지 않는다
            (:func:`ingest_detail` 의 ``reviewed``).

    수집 술어는 :func:`_partition_feed` 가 정본이다. ``PAYED`` 는 종전대로 처리 큐 안으로
    가고, **처음 보는** 상품주문번호는 상태와 무관하게 큐 밖(확인 완료 표시)으로 받는다.
    이미 아는 번호의 비결제완료 이벤트는 상세를 조회하지 않고 상태별로 세기만 한다.

    Returns:
        :class:`SyncResult` 집계.
    """
    result = SyncResult()
    changed = client.get_last_changed_statuses(start, end)
    result.changed = len(changed)

    # 수집 **이후** 생긴 취소·반품 반영 (T14-F). 같은 변경 목록을 재사용하므로
    # 바뀐 게 없으면 추가 호출도 0회다. dry-run 은 읽기만 하는 모드라 건너뛴다.
    if not dry_run:
        claim_stats = refresh_claims(session, client=client, changed=changed, now=now,
                                     notify=notify_claims)
        result.claims_refreshed = claim_stats["refreshed"]
        result.claims_flagged = claim_stats["claimed"]
        result.claims_notified = claim_stats["notified"]

    folded = _feed_status_map(changed)
    known = existing_external_ids(session, list(folded.keys()))
    candidate_ids, quiet_ids, dropped = _partition_feed(folded, known, collect_all=collect_all)
    result.candidates = len(candidate_ids)
    result.dropped_by_status = dropped

    already = {oid for oid in candidate_ids if oid in known}
    result.skipped += len(already)
    fresh_ids = [oid for oid in candidate_ids if oid not in already]
    if not fresh_ids:
        return result

    details = client.get_product_orders(fresh_ids)
    result.fetched = len(details)
    if dry_run:
        logger.info("[NAVER] dry-run — 상세 %d건 조회, 저장 없음", len(details))
        return result

    # 시스템 계정은 **주문 생성 시점**에만 필요하다(promotion). 수집은 계정이 없어도
    # 멈추면 안 된다 — 못 받은 주문은 되돌릴 수 없고, 계정 문제는 나중에 고칠 수 있다.
    today = get_today_kst().strftime("%Y-%m-%d")
    for detail in details:
        quiet = extract_external_id(detail) in quiet_ids
        try:
            outcome = ingest_detail(session, detail, today=today, now=now,
                                    reviewed=mark_reviewed or quiet,
                                    reviewed_reason="sweep_unknown" if quiet else "backfill")
        except NaverMappingError as exc:
            result.errors.append(str(exc))
            continue
        if outcome == "collected":
            result.collected += 1
            if quiet:
                result.quiet_collected += 1
            link = (
                session.query(ExternalOrderLink)
                .filter(ExternalOrderLink.channel == CHANNEL,
                        ExternalOrderLink.external_id == extract_external_id(detail))
                .first()
            )
            if link:
                result.link_ids.append(int(link.id))
        elif outcome == "skipped":
            result.skipped += 1
        else:
            result.pending_review += 1
    return result


def run_sweep(
    session: Session, *, client: Any = None, dry_run: bool = False,
    now: Optional[datetime] = None,
) -> dict[str, Any]:
    """워터마크 구간을 1회 수집하고 결과 dict 를 돌려준다(러너·rq job 공용 진입점).

    성공하면 워터마크를 구간 끝으로 전진시키고, 실패하면 **전진시키지 않고** 사유만
    기록한다 — 다음 실행이 같은 구간을 다시 훑는다(유실 방지). 커밋은 이 함수가 한다
    (러너/워커가 tx 를 소유하지 않는 단발 실행이라).

    Args:
        session: DB 세션.
        client: 미지정이면 환경변수로 클라이언트를 만든다(WORKER 전용).
        dry_run: True 면 조회까지만 하고 아무것도 만들지 않으며 워터마크도 안 움직인다.
        now: 테스트용 시각 주입(KST aware).

    Returns:
        집계 dict(``window`` 구간 + :meth:`SyncResult.as_dict`).
    """
    from foms.services.integrations.naver_commerce import watermark as wm
    from foms.services.integrations.naver_commerce.client import KST, NaverCommerceClient

    current = now or datetime.now(KST)
    start, end = wm.resolve_window(session, now=current)
    payload: dict[str, Any] = {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "dry_run": bool(dry_run),
    }
    if start >= end:
        payload.update(SyncResult().as_dict())
        payload["note"] = "구간 없음(워터마크가 최신)"
        return payload

    client = client if client is not None else NaverCommerceClient()
    try:
        result = sync_naver_orders(session, client=client, start=start, end=end,
                                   dry_run=dry_run)
    except Exception as exc:
        session.rollback()
        wm.record_failure(session, error=str(exc), now=current)
        session.commit()
        payload.update(SyncResult().as_dict())
        payload["failed"] = str(exc)
        raise
    payload.update(result.as_dict())
    if not dry_run:
        wm.advance(session, success_to=end, summary=result.as_dict(), now=current)
        payload["expiry_alert"] = _check_app_expiry(session, current)
    session.commit()
    return payload


def _check_app_expiry(session: Session, current: datetime) -> Optional[int]:
    """앱 인증 만료 임박 알림을 태운다. 여기서 나는 오류가 수집을 되돌리면 안 된다.

    수집은 이미 성공했고 워터마크도 전진했다. 부가 알림 실패로 예외를 올리면 호출자가
    tx 를 롤백해 **성공한 수집이 통째로 사라진다** — 부가 기능이 본체를 죽이는 구조는 금지.
    """
    from foms.services.integrations.naver_commerce import app_expiry

    try:
        return app_expiry.check_and_notify(session, today=current.date(), now=now_utc_naive())
    except Exception as exc:  # noqa: BLE001 - 부가 알림 실패가 수집을 되돌리지 않게
        logger.warning("[NAVER] 앱 만료 알림 실패(수집은 유지): %s", exc, exc_info=True)
        return None


__all__ = [
    "ACTOR_USERNAME",
    "CHANNEL",
    "OWNER_USERNAME",
    "IngestAccountError",
    "SyncResult",
    "existing_external_ids",
    "ingest_detail",
    "resolve_ingest_accounts",
    "run_sweep",
    "sync_naver_orders",
]

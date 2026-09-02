"""네이버 수집 관리 화면 (NAVER-INGEST-01 §3.7).

수집은 사람이 안 보는 데서 도는 배경 작업이라, **지금 잘 돌고 있는지**와 **사람 손이 필요한
건**을 한 화면에서 보여줘야 한다. 이 화면이 답하는 질문은 셋이다:

1. 마지막으로 언제까지 수집했나(워터마크), 마지막 실행이 실패했나.
2. 사람이 봐야 할 보류(``PENDING_REVIEW``)·실패 건이 있나.
3. 앱 인증이 언제 만료되나(만료되면 수집이 조용히 전면 중단된다).

"지금 수집" 은 **rq enqueue 만** 한다. 네이버 HTTP 는 WORKER 에서만 나가야 한다 —
커머스API센터 호출 IP 한도(3)와 Railway static outbound IP(3)가 같아 여유가 0이라,
web 에서 부르면 등록되지 않은 IP 라 차단된다. 취향이 아니라 제약이다.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Optional

from flask import (abort, g, jsonify, redirect, render_template, request, session,
                   url_for)
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql.elements import ColumnElement

from db import get_db
from foms.services.datetime_kst import (format_datetime_kst, get_today_kst,
                                        now_kst, now_utc_naive)
from foms.services.integrations.naver_commerce.constants import SELLER_CENTER_URL
from foms.services.integrations.naver_commerce.fulfillment import CLOSE_NOW_RELATIONS
from foms.services.integrations.naver_commerce.mapping import (
    CLAIM_BLOCK_KEYS,
    RETURN_BLOCK_KEYS,
)
from foms.services.integrations.naver_commerce.order_candidates import find_order_candidates
from foms.services.integrations.naver_commerce.promotion import (
    is_promotable,
    summarize_link_household,
    summarize_snapshot,
)
from foms.services.jobs.queue import (enqueue_naver_backfill, enqueue_naver_order_sync,
                                     get_rq_runtime_status)
from foms.web.admin.routes import admin_bp
from foms.web.auth import log_access, login_required, role_required
from models import ExternalOrderLink, Order, OrderEvent

logger = logging.getLogger(__name__)

#: 한 페이지에 보여줄 수집 이력 행 수(관리자 cold path 라 페이지네이션으로 충분).
PAGE_SIZE = 50

#: 트리아지 큐가 한 번에 읽는 링크 수. 한 집이 상품주문 여러 건으로 오므로 묶음 PAGE_SIZE
#: 개를 채우려면 링크는 그보다 많이 필요하다(실측 평균 3건/집).
#: 250(=PAGE_SIZE*5)에서 **1500** 으로 올렸다(2026-08-24). 스테이징이 큐 링크 229건이라
#: 곧 닿는데, 닿으면 "일부 집이 안 보입니다" 띠가 **상시 발동**한다 — 늘 켜진 경고는 아무도
#: 안 읽고 정작 진짜로 잘릴 때 못 알아챈다. 올릴 수 있게 된 근거는 nav 뱃지가 판정에
#: 필요한 경로만 읽도록 바뀐 것이다(:func:`_snapshot_projection` — 스펙 2026-08-24).
#: **상한을 올려도 오늘 비용은 늘지 않는다** — 비용은 상한이 아니라 실제 행수에 비례한다.
QUEUE_LINK_FETCH_LIMIT = 1500

#: 처리 탭 목록의 집 상한. 캡은 **병합 뒤 한 곳에서만** 건다 — 원천별로 걸면 큐가 50에서
#: 잘려 "잘렸다" 띠가 켜지는데 화면에는 발주확인 전 집이 더해져 58줄이 보이는, 사람이
#: 읽을 수 없는 상태가 된다(2026-08-24 스테이징 실화면). 50은 실제 운영 물량(58집)보다
#: 작아서 상시 발동했다 — 상한은 "평소에는 안 닿는 안전장치"여야 한다.
#: 링크 상한만 올리면 **이 캡이 대신 상시 발동한다**(링크 1500 ÷ 평균 3.2건/집 ≈ 470집).
#: 그래서 200 → 500 으로 함께 올린다(2026-08-24).
WORK_GROUP_LIMIT = 500

#: 상태 필터 닫힌집합. 임의 문자열이 그대로 쿼리에 들어가지 않게 한다.
VALID_STATUSES = ("COLLECTED", "LINKED", "PENDING_REVIEW", "FAILED")

#: 이력 탭 찾기 낱말의 최대 길이. 사람이 치는 칸이라 짧다 — 상한을 두는 이유는 길이가
#: 아니라 **의도치 않은 긴 문자열이 ILIKE 패턴으로 들어가는 것**을 막기 위해서다.
HISTORY_FIND_MAX = 50

#: 발주확인이 끝난 것으로 보는 컬럼 값(mapping.CONFIRMED_PLACE_STATUSES 와 같은 집합).
#: 이 값이 아니면 전부 "아직"이다 — NULL(모름)도 아직으로 본다(놓치는 쪽보다 낫다).
CONFIRMED_PLACE_VALUES = ("OK",)

#: 이력 탭 FOMS 축 낱말(계약 §2.4). 칩과 행 배지가 이 dict **한 벌**을 함께 쓴다 —
#: 두 벌로 적으면 한 화면이 같은 축을 두 낱말로 부른다.
HISTORY_FOMS_LABELS = {
    "collected": "받아옴",
    "linked": "주문 만듦",
    "closed": "주문 접음",
    "review": "확인 필요",
    "failed": "받기 실패",
}

#: 이력 탭 상태 칩 정의 — ``(질의값, FOMS 축 키, 꼬리)``. 순서가 곧 화면 순서다.
#: 라벨을 여기 손으로 적지 않는 이유: 칩 라벨이 **배지 낱말에서 파생**돼야
#: "칩과 행이 같은 낱말을 쓴다"를 계약 테스트가 검증할 수 있다(2026-08-30 CEO 지적 3).
#: 손으로 두 벌 적으면 칩만 '받아옴 · 주문 전', 배지만 '받아옴' 으로 조용히 갈린다.
_HISTORY_STATUS_CHIP_SPECS = (
    ("COLLECTED", "collected", " · 주문 전"),
    ("LINKED", "linked", ""),
    ("PENDING_REVIEW", "review", ""),
    ("FAILED", "failed", ""),
)

#: 이력 탭 상태 칩(화면 순서). ``(질의값, 화면 낱말)`` 쌍.
#: **모든 라벨은 대응하는 배지 낱말로 시작한다** — 꼬리는 붙일 수 있어도 앞머리는 못 바꾼다.
HISTORY_STATUS_CHIPS = tuple(
    (query, HISTORY_FOMS_LABELS[state] + tail)
    for query, state, tail in _HISTORY_STATUS_CHIP_SPECS
)

#: 관계 축 낱말. 이력 집의 ``relation`` 은 **항상 세 값 중 하나**다(신규는 ``NEW``) —
#: 처리 탭 집(:func:`_group_queue`)이 신규를 빈 문자열로 주는 것과 규약이 다르다.
#: 화면이 `신규 결제` 배지를 찍어야 하기 때문이다. 두 규약을 서로 옮기지 마라.
HISTORY_RELATION_LABELS = {"NEW": "신규 결제", "ADDON": "추가결제", "REPAY": "재결제"}


def order_has_spec_rows(order: Any) -> bool:
    """주문에 규격표가 한 행이라도 입력됐는지 (CS 완료 판정용).

    규격 SSOT 는 ``structured_data['items'][*]['spec_rows']`` 다(품목 안에 있다 —
    최상위 ``spec_rows`` 를 보면 항상 비어 있는 것으로 잘못 읽는다).

    Args:
        order: :class:`models.Order` 또는 None.

    Returns:
        규격 행이 하나라도 있으면 True.
    """
    data = getattr(order, "structured_data", None)
    if not isinstance(data, dict):
        return False
    items = data.get("items")
    if not isinstance(items, list):
        return False
    for item in items:
        rows = item.get("spec_rows") if isinstance(item, dict) else None
        if isinstance(rows, list) and rows:
            return True
    return False


def _payment_summary(raw_snapshot: Any) -> dict[str, Any]:
    """이력 표에 실을 결제 요약(결제일·수단·할인 합계).

    Args:
        raw_snapshot: ``ExternalOrderLink.raw_snapshot``.

    Returns:
        ``{"paid_at", "means", "discount"}`` — 원본이 없으면 빈 값.
    """
    from foms.services.integrations.naver_commerce.mapping import build_payment_info

    if not isinstance(raw_snapshot, dict) or not raw_snapshot:
        return {"paid_at": "", "means": "", "discount": 0}
    payment = build_payment_info(raw_snapshot)
    discount = payment["product_discount_amount"] + sum(
        coupon["discount_amount"] for coupon in payment["coupons"])
    return {"paid_at": payment["paid_at"][:16], "means": payment["means"],
            "discount": discount}


def _backfill_defaults() -> dict[str, str]:
    """소급 수집 날짜 칸의 기본값(시작·종료, ``YYYY-MM-DD``).

    끝은 어제다 — 오늘 구간은 5분 주기 정상 스윕이 이미 맡는다. 시작은 상한
    (:data:`~foms.services.integrations.naver_commerce.backfill.MAX_RANGE`)만큼 앞이다.

    Returns:
        ``{"start", "end"}``.
    """
    from foms.services.integrations.naver_commerce import backfill as bf

    end = get_today_kst() - datetime.timedelta(days=1)
    start = end - bf.MAX_RANGE + datetime.timedelta(days=1)
    return {"start": start.isoformat(), "end": end.isoformat()}


def _watermark_view(db) -> dict[str, Any]:
    """워터마크 상태를 화면 표시용으로 편다."""
    from foms.services.integrations.naver_commerce import watermark as wm

    state = wm.read_state(db)
    return {
        "last_success_to": state.get("last_success_to"),
        "last_run_at": state.get("last_run_at"),
        "last_error": state.get("last_error"),
        "last_summary": state.get("last_summary") or {},
    }


def _watermark_rev(view: dict[str, Any]) -> str:
    """워터마크 상태의 **지문** — 화면은 이 값이 바뀌는 것만 본다.

    "지금 수집" 은 큐에 넣고 바로 답한다(네이버 HTTP 는 WORKER 단일 출구). 그래서 버튼을
    누른 직후의 화면은 아직 옛 상태다. 화면이 "언제 끝났는지" 알려면 물어볼 곳이 필요한데,
    그 자리에서 성공/실패를 **다시 판정하면 판정이 두 벌**이 된다. 여기서는 워커가 쓴
    워터마크 원문의 지문만 만들고, 무엇을 보여줄지는 화면이 정한다
    (:func:`_fulfillment_state` 의 ``rev`` 와 같은 규율).

    성공(전진)이든 실패(사유 기록)든 ``last_run_at`` 이 함께 바뀌므로 두 결말 모두 지문이
    움직인다. ``hash()`` 는 쓰지 않는다 — ``PYTHONHASHSEED`` 로 프로세스마다 값이 달라져
    web·워커 사이에서 못 쓴다.

    Args:
        view: :func:`_watermark_view` 결과.

    Returns:
        16자 16진 지문 문자열.
    """
    marks = [
        str(view.get("last_run_at") or ""),
        str(view.get("last_success_to") or ""),
        str(view.get("last_error") or ""),
        json.dumps(view.get("last_summary") or {}, sort_keys=True, ensure_ascii=False),
    ]
    return hashlib.sha1("|".join(marks).encode("utf-8")).hexdigest()[:16]


def _run_summary_text(summary: Any) -> str:
    """마지막 실행 집계를 사람 말 한 줄로 — 화면 문구(``수집 N · 건너뜀 N · 보류 N``).

    문구는 ``templates/admin/naver_workbench.html`` 의 수집 카드와 **같은 말**로 맞춘다.
    폴링 결과가 카드와 다른 단어를 쓰면 같은 숫자를 두 가지로 읽게 된다.

    Args:
        summary: ``last_summary``(:meth:`SyncResult.as_dict` 결과) 또는 빈 값.

    Returns:
        요약 문장. 집계가 없으면 빈 문자열.
    """
    if not isinstance(summary, dict) or not summary:
        return ""
    return "수집 {collected} · 건너뜀 {skipped} · 보류 {pending}".format(
        collected=int(summary.get("collected") or 0),
        skipped=int(summary.get("skipped") or 0),
        pending=int(summary.get("pending_review") or 0),
    )


def _expiry_view(db) -> dict[str, Any]:
    """앱 인증 만료 상태(남은 일수 포함)."""
    from foms.services.integrations.naver_commerce import app_expiry

    expires_on = app_expiry.read_expiry_date(db)
    if expires_on is None:
        return {"expires_on": None, "days_left": None}
    return {
        "expires_on": expires_on.strftime("%Y-%m-%d"),
        "days_left": (expires_on - datetime.date.today()).days,
    }


def _history_group_key(link: ExternalOrderLink) -> str:
    """이력 표의 페이지·묶음 키 — 확인 큐와 **같은 정의**(주문번호·수취인 전화·주소).

    값은 수집 시점에 ``group_key`` 컬럼에 복사해 둔다. 주소는 ``raw_snapshot`` 안에서
    파이썬으로 조립해야 나오므로 SQL 이 못 세기 때문이다(:func:`_group_key_col`).

    컬럼이 비면 예전 규칙(주문번호)으로 떨어진다 — 이 컬럼이 생기기 전 행과 backfill 전
    행을 위한 폴백이다. 정확도는 예전만 못해도 화면은 죽지 않는다.
    """
    from foms.services.integrations.naver_commerce.grouping import resolve_group_key

    return resolve_group_key(link)


def _group_key_col():
    """이력 표의 묶음 키 SQL 식 — 파이썬 :func:`_history_group_key` 와 같은 규칙.

    총계·상태별 건수·페이지 키가 **모두 같은 식**을 써야 숫자가 갈리지 않는다.
    식 자체는 nav 뱃지와도 공유한다(`grouping` 모듈) — 두 벌로 갈라지면 지금 고친
    "화면마다 집 수가 다르다" 결함이 그대로 재발한다.

    Returns:
        묶음키(없으면 주문번호, 그것도 없으면 ``link:<id>``) 라벨 ``gk`` 컬럼 식.
    """
    from foms.services.integrations.naver_commerce.grouping import group_key_expression

    return group_key_expression()


def _status_group_counts(db, *, find: str = "") -> dict[str, int]:
    """상태별 **묶음 수**를 센다 — 필터 버튼 숫자를 표 총계와 같은 단위로 맞춘다.

    링크 행으로 세면 "전체 36 · 수집됨(주문 전) 102" 처럼 부분이 전체보다 커 보인다
    (2026-08-19 스테이징 실화면). 필터는 "그 상태 링크가 하나라도 있는 집"을 고르므로
    (:func:`_link_rows`), 숫자도 같은 술어로 세야 한다 — ``(묶음키, 상태)`` 쌍을 한 번씩만
    세면 정확히 그 값이다.

    Args:
        db: 요청 스코프 DB 세션.
        find: 이력 탭 찾기 낱말(:func:`_history_find_clause`). 목록을 좁히면 칩 숫자도
            함께 좁혀야 한다 — 3주문만 보이는 화면에서 칩이 743주문이라고 말하면
            사람은 나머지 740을 찾아 헤맨다(칩 단위 불일치와 같은 실패 모양).

    Returns:
        ``{상태: 그 상태 링크를 하나 이상 가진 묶음 수}`` (VALID_STATUSES 전 키 포함).
    """
    key_col = _group_key_col()
    query = (
        db.query(key_col, ExternalOrderLink.sync_status)
        .filter(ExternalOrderLink.channel == "NAVER")
    )
    find_clause = _history_find_clause(find)
    if find_clause is not None:
        query = query.filter(find_clause)
    pairs = query.group_by(key_col, ExternalOrderLink.sync_status).all()
    counts = {name: 0 for name in VALID_STATUSES}
    for _key, link_status in pairs:
        if link_status in counts:
            counts[link_status] += 1
    return counts


def _place_pending_clause():
    """'발주확인 전' 조건 — 완료값이 아니거나 아직 모르는(NULL) 링크.

    ``raw_snapshot`` (JSONB) 대신 ``place_order_status`` 컬럼을 본다. JSONB 로 필터하면
    인덱스 없는 스캔이 되고, 그건 이 저장소의 hot path 금지 규칙이다(T16-B).
    """
    from sqlalchemy import or_

    return or_(ExternalOrderLink.place_order_status.is_(None),
               ExternalOrderLink.place_order_status.notin_(CONFIRMED_PLACE_VALUES))


def _place_pending_group_count(db, *, find: str = "") -> int:
    """'발주확인 전' 묶음 수 — 필터 버튼 숫자(다른 버튼과 같은 집 단위).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        발주확인이 아직인 링크를 하나 이상 가진 묶음 수.
    """
    key_col = _group_key_col()
    query = (
        db.query(key_col)
        .filter(ExternalOrderLink.channel == "NAVER", _place_pending_clause())
    )
    find_clause = _history_find_clause(find)
    if find_clause is not None:
        query = query.filter(find_clause)
    return query.group_by(key_col).count()


def _dispatch_pending_clause() -> ColumnElement[bool]:
    """'발송처리 전' 조건 — **정본은 서비스 계층**이다.

    본문은 :func:`foms.services.integrations.naver_commerce.bulk_dispatch.dispatch_pending_clause`
    로 옮겼다(2026-08-31, NAVER-BULKDISPATCH-01 T1). 일괄 발송처리 선별이 같은 술어를
    써야 하는데, 서비스가 web 을 import 할 수는 없어서다. 여기 한 벌을 더 적으면 두 술어가
    갈라지고, 그건 화면 큐(우리 표식만)와 워커(두 신호)가 이미 어긋나 있던 결함과 같은
    모양이다.

    이 이름을 남겨 두는 이유: 이력 탭 칩과 **부분 인덱스 조건식 일치 계약 테스트**가
    이 자리에서 import 한다.

    Returns:
        SQLAlchemy 불리언 식(``and_`` 두 조각).
    """
    from foms.services.integrations.naver_commerce.bulk_dispatch import (
        dispatch_pending_clause,
    )

    return dispatch_pending_clause()


def _dispatch_pending_group_count(db, *, find: str = "") -> int:
    """'발송처리 전' 묶음 수 — 칩 숫자(다른 칩과 **같은 집 단위**).

    링크 행으로 세면 부분이 전체보다 커 보인다(2026-08-19 스테이징 실화면). 필터는
    "그 조건 링크가 하나라도 있는 집"을 고르므로(:func:`_link_rows`) 숫자도 같은 술어로
    ``(묶음키)`` 를 한 번씩만 세야 한다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        발송 기록이 아직 없는 링크를 하나 이상 가진 묶음 수.
    """
    key_col = _group_key_col()
    query = (
        db.query(key_col)
        .filter(ExternalOrderLink.channel == "NAVER", _dispatch_pending_clause())
    )
    find_clause = _history_find_clause(find)
    if find_clause is not None:
        query = query.filter(find_clause)
    return query.group_by(key_col).count()


def _relation_clause() -> ColumnElement[bool]:
    """추가결제·재결제 링크 조건 — 관계 컬럼 하나로 끝난다(JSONB 를 안 탄다).

    값은 ``CheckConstraint`` 가 이미 막는 닫힌집합이라 그대로 센다.

    Returns:
        SQLAlchemy 불리언 식(``relation IN ('ADDON','REPAY')``).
    """
    return ExternalOrderLink.relation.in_(("ADDON", "REPAY"))


def _relation_group_count(db, *, find: str = "") -> int:
    """추가결제·재결제 묶음 수 — 칩 숫자(다른 칩과 같은 집 단위).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``relation`` 이 ADDON·REPAY 인 링크를 하나 이상 가진 묶음 수.
    """
    key_col = _group_key_col()
    query = (
        db.query(key_col)
        .filter(ExternalOrderLink.channel == "NAVER", _relation_clause())
    )
    find_clause = _history_find_clause(find)
    if find_clause is not None:
        query = query.filter(find_clause)
    return query.group_by(key_col).count()


#: 클레임이 없는 링크가 쓰는 반품 축 자리값 — :func:`_return_axis_view` 를 **부르지
#: 않기 위한** 것이다. 링크마다 부르면 쪽당 50집 × 멤버 수만큼 빈 값을 만드는 헛일이
#: 붙는다(2026-08-30 CEO 지적 — 링크당 파싱). 키는 이력 표가 읽는 것만 담는다.
_EMPTY_RETURN_AXIS: dict[str, Any] = {
    "return_completed_at": "",
    "refund_expected_at": "",
    "refund_expected_pending": False,
    "collect_completed_at": "",
    "refund_done": False,
}


def _history_member_axes(link: ExternalOrderLink,
                         summary: dict[str, Any]) -> dict[str, Any]:
    """이력 멤버(링크) 한 건의 축 원재료 — 집계에 쓸 값만 뽑는다(**추가 쿼리 0**).

    ``claim_label``(이미 실려 있다)·``claim_phase``·``claim_kind`` 는 **같은 링크의 같은**
    :func:`mapping.extract_claim` **결과**여야 한다. 라벨은 A 링크에서, 단계는 B 링크에서
    뽑으면 화면이 "취소 요청"이라 적으면서 "확정됨"으로 칠한다(계약 §2.1).

    :func:`extract_claim` 은 :func:`promotion.summarize_snapshot` 안에서 이미 한 번 돈다.
    여기서 한 번 더 부르는 것은 **순수 파이썬 파싱**이라 쿼리가 0이고, 대신 여러 화면이
    공유하는 ``summarize_snapshot`` 을 안 건드린다(레인 격리).

    Args:
        link: 이력 페이지가 **이미 읽어 둔** 링크(여기서 새로 조회하지 않는다).
        summary: 같은 링크의 :func:`promotion.summarize_snapshot` 결과(재계산 금지).
            ``claim_label`` 이 비어 있으면 반품 축을 **아예 파싱하지 않는다**.

    Returns:
        멤버 dict 에 합칠 축 값들 — ``relation``·``claim_*``·``shipping_due``·
        ``dispatch``(:func:`_dispatch_view` 결과 그대로)·``fulfillment``.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        claim_kind,
        claim_reason_text,
        extract_cancel_axis,
        extract_claim,
    )

    claim = extract_claim(link.raw_snapshot or {})
    kind = claim_kind(claim)
    # 반품 축은 **클레임이 있는 링크에만** 판다. 판정에 쓰는 술어(``claim_label``)는
    # :func:`_history_claim` 이 멤버를 고를 때 쓰는 것과 **같은 값**이라, 라벨을 준 멤버는
    # 반드시 축도 갖는다(둘이 갈리면 화면이 라벨만 있고 날짜가 없는 집을 만든다).
    axis = _return_axis_view(link) if summary["claim_label"] else _EMPTY_RETURN_AXIS
    # 취소 축은 **따로** 판다. 반품 축이 ``cancel`` 블록을 일부러 빼기 때문에(취소 블록의
    # 환불 필드가 반품 진행으로 새던 결함) 순수 취소 건은 확정 시각도 환불 상태도 영영
    # 빈 값이었다 — 목업의 `취소 완료 08-27` 이 그래서 안 나왔다(2026-08-30).
    # 반품 축에 ``cancel`` 을 도로 넣지 않는다: 고친 누출을 되살리는 짓이다.
    cancel = (extract_cancel_axis(link.raw_snapshot or {})
              if summary["claim_label"] and kind == "CANCEL" else None)
    return {
        "relation": (link.relation or "").strip().upper(),
        "claim_phase": claim["phase"],
        "claim_kind": kind,
        # 사유는 **코드 라벨**이다 — 목업 확정본의 `단순 변심`·`색상·사이즈 변경` 이
        # :data:`mapping.CLAIM_REASON_LABELS` 의 낱말이다. 고객이 쓴 원문
        # (``detailed_reason``)은 길이가 안 정해져 있어 좁은 상태 칸에 못 싣는다 —
        # 원문은 pane 이 그대로 낸다(축이 다르다).
        "claim_reason": claim_reason_text(claim["reason"]),
        # 반품 축 시각 3종 — 이미 KST `YYYY-MM-DD HH:MM` 로 펴진 값이다.
        # "끝난 뒤의 환불 예정"은 미래형 거짓말이라 확정된 집에서는 빈 값으로 준다.
        "claim_done_at": (_dispatch_time_text(cancel["cancel_completed_at"])
                          if cancel else axis["return_completed_at"]),
        "claim_refund_expected_at": ("" if cancel else axis["refund_expected_at"]
                                     if axis["refund_expected_pending"] else ""),
        # 취소 건에는 수거가 없다 — 반품 축 값을 그대로 쓰면 취소 집에 `수거 완료` 가 뜬다
        # (2026-08-27 에 고친 누출의 거울상). 취소로 판정된 멤버는 반품 조각을 안 낸다.
        "claim_collect_done_at": ("" if cancel else axis["collect_completed_at"]),
        # 환불 완료도 축을 따라간다 — 취소 건의 환불 상태는 취소 블록에만 있다.
        "claim_refund_done": (cancel["refund_done"] if cancel else axis["refund_done"]),
        "shipping_due": summary["shipping_due"],
        # 발송 판정은 **재작성하지 않는다** — pane 과 같은 파서를 그대로 접는다.
        "dispatch": _dispatch_view(link),
        "fulfillment": (link.triage_state or {}).get("fulfillment") or {},
    }


def _history_relation(members: list[dict[str, Any]]) -> tuple[str, Optional[int]]:
    """집의 관계 축 — ``NEW``/``ADDON``/``REPAY`` 와 **그 관계를 정한 멤버**의 주문 id.

    우선순위는 처리 탭(:func:`_group_queue`)과 같다: ``ADDON`` 이 하나라도 있으면 ``ADDON``,
    없고 ``REPAY`` 가 있으면 ``REPAY``, 아니면 ``NEW``.

    상대 주문번호는 **대표(lead)가 아니라 관계를 정한 그 멤버**에서 뽑는다. 대표는 금액
    최대 링크라, 형제 일부만 ADDON 인 섞인 집에서는 ``NEW`` 형제일 수 있다. 그러면 화면이
    "추가결제 → #(엉뚱한 주문번호)"를 찍는데 사람이 눌러서 실제로 들어가는 번호다
    (2026-08-30 CEO 지적 2). 백필 전 데이터는 형제 일부만 값이 있어 섞인 집이 실재한다.

    Args:
        members: **대표 먼저** 정렬된 집 멤버 목록.

    Returns:
        ``(relation, related_order_id)``. ``NEW`` 이거나 관계 멤버에 아직 주문이 없으면
        두 번째 값은 ``None`` — 그때 화면은 화살표와 번호를 **아예 내지 않는다**(배지 낱말만).
    """
    for name in ("ADDON", "REPAY"):
        matched = [row for row in members if row["relation"] == name]
        if not matched:
            continue
        # 관계 멤버 중 주문이 붙은 첫 건. 전부 미생성이면 번호를 지어내지 않는다.
        linked = next((row["order_id"] for row in matched if row["order_id"]), None)
        return (name, int(linked) if linked else None)
    return ("NEW", None)


def _history_fail(members: list[dict[str, Any]]) -> dict[str, str]:
    """집의 실패 축 — 발주확인·발송처리 공용(계약 §2.3-E).

    ``fulfillment['last_error']`` 가 비어 있지 않은 **첫 멤버**(대표 먼저)를 쓴다. 작업이
    안 적힌 옛 기록은 ``confirm`` 으로 본다 — :func:`_failure_rows` 와 **같은 규칙**이다
    (규칙이 두 벌이 되면 같은 실패를 두 화면이 다른 작업 이름으로 부른다).

    Args:
        members: **대표 먼저** 정렬된 집 멤버 목록.

    Returns:
        ``{"action", "action_label", "reason", "at"}``. 실패가 없으면 네 값 모두 빈 문자열.
    """
    for row in members:
        state = row["fulfillment"]
        reason = str(state.get("last_error") or "").strip()
        if not reason:
            continue
        action = str(state.get("last_error_action") or "confirm").strip().lower()
        action = action if action in FULFILLMENT_ACTION_LABELS else "confirm"
        return {
            "action": action,
            "action_label": FULFILLMENT_ACTION_LABELS[action],
            "reason": reason,
            # 시각 파서는 한 벌이다. 원문을 슬라이스하면 ① UTC 를 그대로 찍어
            # 같은 칸의 발송 시각(KST)과 9시간 어긋나고 ② 못 읽는 값도 잘라 낸다.
            "at": _dispatch_time_text(state.get("last_error_at")),
        }
    return {"action": "", "action_label": "", "reason": "", "at": ""}


def _history_dispatch(members: list[dict[str, Any]]) -> dict[str, Any]:
    """집의 발송 축 집계 — :func:`_dispatch_view` 결과를 **그대로 접는다**.

    새 파서를 만들지 않는 이유: 우리 표식과 네이버 ``sendDate`` 를 나란히 놓는 규칙이 두
    벌이 되면 pane 과 이력 표가 서로 다른 발송 사실을 말한다.

    Args:
        members: 집 멤버 목록(순서 무관 — 전부 합·최솟값·any 다).

    ``mismatch_ours_at`` 을 ``ours_at`` 과 **따로** 센다: 경고 줄이 둘을 한 문장에 붙이는데,
    멤버가 [정상 발송 09:00, 어긋남 16:02] 이면 접힌 ``ours_at`` 은 09:00 이고 화면은
    **네이버가 기록한 그 09:00** 을 "네이버 기록 없음" 이라 말한다(2026-08-30 CEO 지적).
    되돌릴 수 없는 호출의 유실 자리를 가리키는 문장이라 틀린 시각이 특히 나쁘다.

    Returns:
        ``{"done_count", "total", "ours_at", "naver_at", "mismatch", "mismatch_ours_at"}``.
        시각은 빈 값이 아닌 것 중 **가장 이른 값**이고, 하나도 없으면 빈 문자열.
    """
    views = [row["dispatch"] for row in members]
    ours = [view["ours_at"] for view in views if view["ours_at"]]
    naver = [view["naver_at"] for view in views if view["naver_at"]]
    mismatch_ours = [view["ours_at"] for view in views
                     if view["mismatch"] and view["ours_at"]]
    return {
        "done_count": sum(1 for view in views if view["ours_at"] or view["naver_at"]),
        "total": len(members),
        "ours_at": min(ours) if ours else "",
        "naver_at": min(naver) if naver else "",
        # 우리는 보냈다는데 네이버가 침묵하는 링크가 하나라도 있으면 집 전체에 표식을 단다.
        "mismatch": any(view["mismatch"] for view in views),
        # 경고 줄이 쓰는 유일한 시각 — **어긋난 그 링크**의 우리 발송 시각이다.
        "mismatch_ours_at": min(mismatch_ours) if mismatch_ours else "",
    }


def _history_shipping_due(members: list[dict[str, Any]]) -> dict[str, Any]:
    """집의 발송기한 — 멤버 중 **가장 이른 기한**(계약 §2.2).

    처리 탭(:func:`_group_queue`)은 ``next()``(첫 값)를 쓰지만 이력은 가장 이른 값이다 —
    이력은 "이 집이 언제까지였나"를 묻는 화면이라 제일 급한 날짜가 답이다.

    Args:
        members: 집 멤버 목록(순서 무관).

    날짜는 **한 번만** 판다. 예전에는 초과일수만 ``try`` 로 감싸고 표시값은 무방비
    슬라이스(``due[5:]``)라, ``due='20260902'`` 같은 값이 오면 화면에 `발송기한 902` 가
    찍혔다 — 못 읽는 값을 "지났다"고 단정하지 않겠다는 의도가 옆 필드에서 샜다
    (2026-08-30 CEO 지적). 못 읽으면 **표시값도 빈 값**이고 원문은 ``shipping_due`` 에
    그대로 남는다.

    Returns:
        ``{"shipping_due"(원문 그대로), "shipping_due_text"(MM-DD|""),
        "shipping_due_over_days"(int, 음수는 0)}``.
    """
    dues = [row["shipping_due"] for row in members if row["shipping_due"]]
    due = min(dues) if dues else ""
    parsed: Optional[datetime.date] = None
    if due:
        try:
            parsed = datetime.date.fromisoformat(due)
        except (TypeError, ValueError):
            parsed = None
    if parsed is None:
        return {"shipping_due": due, "shipping_due_text": "", "shipping_due_over_days": 0}
    return {"shipping_due": due, "shipping_due_text": parsed.strftime("%m-%d"),
            "shipping_due_over_days": max(0, (get_today_kst() - parsed).days)}


def _history_foms_state(lead: dict[str, Any], statuses: list[str]) -> str:
    """집의 FOMS 축 상태(계약 §2.3-A) — 위에서부터 먼저 맞는 것.

    3번(``closed``)은 :func:`_link_rows` 가 **이미 읽어 둔** ``Order`` 객체로 판정한다
    (추가 쿼리 0). 그 조회는 soft delete 를 안 거르므로 삭제된 주문도 객체로 잡히는데,
    화면이 그것을 ``주문 만듦`` 이라 말하면 접힌 주문이 살아 있는 것처럼 보인다.

    Args:
        lead: 대표 멤버 dict(``order_id``·``_order`` 를 읽는다).
        statuses: 집 안 링크 상태 목록(중복 제거된 것).

    Returns:
        :data:`HISTORY_FOMS_LABELS` 의 키 하나.
    """
    if "FAILED" in statuses:
        return "failed"
    if "PENDING_REVIEW" in statuses:
        return "review"
    if not lead["order_id"]:
        return "collected"
    order = lead["_order"]
    # ``status``·``deleted_at`` 은 :class:`models.Order` 의 **실제 컬럼**이라 기본값이
    # 붙는 ``getattr`` 은 영영 안 쓰이고, 컬럼 이름이 바뀌면 예외 대신 조용히
    # ``linked`` 로 떨어진다(2026-08-30 CEO 지적). 없을 수 있는 것은 주문 자체뿐이다.
    if order is None or str(order.status or "").upper() == "DELETED" or order.deleted_at:
        return "closed"
    return "linked"


def _household_claim(claims: list[dict[str, Any]], *, fallback_label: str) -> dict[str, str]:
    """집의 취소·반품 배지 — **첫 라벨이 아니라 집계**다 (NVCLAIM-ORDER-01 T5).

    ``next((s["claim_label"] for s in members if s["claim_label"]), "")`` 는 4건 중 3건만
    반품된 집에서 `반품 완료` 를 내놓는다. 담당자는 그 배지를 보고 집을 끝난 것으로 읽었고,
    본품 1건은 ``DELIVERING`` 인 채 환불되지 않았다(2026-09-01 황민철, ERP 주문 5026).
    **화면 문구가 아니라 사고의 직접 원인이라 배지를 집계로 바꾼다.**

    집계 규칙과 낱말표는 취소 띠와 **같은 모듈 한 벌**을 쓴다
    (:func:`order_candidates.aggregate_claim`) — 두 벌로 두면 같은 집을 두 화면이 다르게
    부른다.

    라벨을 **``partial`` 에서만** 집계 낱말로 바꾸는 이유: 집 전체가 같은 단계인 집은
    라인 라벨이 더 정확하다(`수거 중`·`환불 대기`처럼 단계까지 말한다). 첫 라벨이 거짓말을
    하는 것은 **부분 상태 하나뿐**이라, 고치는 것도 거기 하나다. 판정 축은 라벨이 아니라
    ``claim_code`` 다 — 낱말이 바뀌어도 분기가 안 죽는다(order_candidates.py:235).

    Args:
        claims: 집 멤버의 :func:`mapping.extract_claim` 결과 목록(**표시 순서 그대로**).
        fallback_label: 부분 상태가 아닐 때 쓸 라인 라벨(기존 first-non-empty 값).

    Returns:
        ``{"claim_code", "claim_kind", "claim_label"}``.
    """
    from foms.services.integrations.naver_commerce.order_candidates import aggregate_claim

    agg = aggregate_claim(claims)
    return {
        "claim_code": agg["claim_code"],
        "claim_kind": agg["claim_kind"],
        "claim_label": agg["claim_label"] if agg["claim_code"] == "partial" else fallback_label,
    }


def _history_claim(members: list[dict[str, Any]]) -> dict[str, Any]:
    """집의 취소·반품 축 — **라벨을 준 그 멤버**의 단계·종류·사유를 함께 가져온다.

    라벨은 A 링크, 단계는 B 링크에서 뽑으면 화면이 "취소 요청"이라 적으면서 "확정됨"으로
    칠한다(계약 §2.1). 그래서 멤버를 먼저 고르고 그 멤버에서 전부 뽑는다.

    날짜·사유는 순수 파싱이라 **추가 쿼리가 0**이다(목업 확정본의 ``반품 완료 08-26`` ·
    ``단순 변심 · 환불 예정 08-30`` 이 이 값들이다 — 2026-08-30 CEO 지적 4).

    Args:
        members: 집 멤버 목록. 순서는 **기존 ``claim_label`` 선택과 같아야** 한다
            (표시 순서 그대로 — 대표 먼저로 바꾸면 라벨이 조용히 다른 건으로 바뀐다).

    Returns:
        ``{"label","phase","kind","reason","done_text","refund_expected_text",
        "collect_done_text","refund_done"}``. 클레임이 없으면 문자열은 전부 빈 값이다.
    """
    row = next((row for row in members if row["claim_label"]), None)
    if row is None:
        return {"label": "", "code": "alive", "phase": "", "kind": "", "reason": "",
                "done_text": "", "refund_expected_text": "", "collect_done_text": "",
                "refund_done": False}
    # 배지 낱말만 집계로 바꾼다(T5) — 단계·사유·날짜는 **그 멤버의 사실**이라 그대로 둔다.
    # ``claim_kind`` 는 이미 풀린 종류라 ``type`` 자리에 그대로 넣는다
    # (:func:`mapping.claim_kind` 가 ``type`` 을 먼저 본다).
    aggregate = _household_claim(
        [{"phase": member["claim_phase"], "type": member["claim_kind"]} for member in members],
        fallback_label=row["claim_label"])
    return {
        "label": aggregate["claim_label"],
        # 코드가 판정 축이다 — 화면이 한국어 낱말을 ``==`` 로 비교하지 않게 함께 싣는다.
        "code": aggregate["claim_code"],
        "phase": row["claim_phase"],
        "kind": row["claim_kind"],
        "reason": row["claim_reason"],
        # `YYYY-MM-DD HH:MM` → `MM-DD`. 날짜로 못 읽으면 빈 문자열이라 화면이 줄을 안 낸다
        # (슬라이스로 자르면 원문 그대로 온 값이 잘려 거짓 날짜가 된다 — CEO 지적 7).
        "done_text": _history_month_day(row["claim_done_at"]),
        "refund_expected_text": _history_month_day(row["claim_refund_expected_at"]),
        "collect_done_text": _history_month_day(row["claim_collect_done_at"]),
        "refund_done": row["claim_refund_done"],
    }


def _history_pipe_note(*, fail: dict[str, Any], dispatch_state: str,
                       dispatch: dict[str, Any], due: dict[str, Any]) -> tuple[str, str]:
    """파이프 옆 부속 문구 ``(종류, 낱말)`` — 위에서부터 먼저 맞는 것 **하나만**(계약 §3.2).

    판정표와 같은 이유로 서버가 정한다: 템플릿 ``{% elif %}`` 사슬에 두면 HTML 문자열
    매칭 말고는 시험할 방법이 없다(2026-08-30 CEO 지적 4 — 판정을 옮기고도 이 다섯 줄이
    템플릿에 남아 있었다).

    Args:
        fail: :func:`_history_fail` 결과.
        dispatch_state: :func:`_history_dispatch_step` 이 정한 상태 키.
        dispatch: :func:`_history_dispatch` 결과.
        due: :func:`_history_shipping_due` 결과.

    Returns:
        ``(종류, 낱말)``. 종류는 ``when``(문장 톤) · ``over``(빨강 배지) · ``""``(안 낸다).
        발송이 끝난 집의 꼬리는 **시각 + 출처 한 낱말**이다 — 우리가 보냈으면
        ``{ours_at} · ERP발송``, 판매자센터에서 나갔으면 ``{naver_at} · 판매자센터``.
    """
    if fail["action"] in ("confirm", "dispatch") and fail["at"]:
        return ("when", fail["at"])
    if dispatch_state == "done" and dispatch["ours_at"]:
        # 우리 기록이 있으면 **우리가 보낸 것**이다 — 시각도 우리 기록의 시각을 쓴다.
        # 네이버 sendDate 를 쓰면 "ERP발송" 이라 적어 놓고 네이버가 적은 시각을 보여
        # 주체와 시각이 갈린다(2026-08-31 사용자 결정: 시각 + 출처 한 낱말로 단순화).
        return ("when", f"{dispatch['ours_at']} · ERP발송")
    if dispatch_state == "done" and dispatch["naver_at"]:
        # 우리 기록이 없는 발송 = 판매자센터에서 직접 나간 것이다.
        return ("when", f"{dispatch['naver_at']} · 판매자센터")
    if dispatch_state == "done":
        return ("", "")
    if due["shipping_due_over_days"] > 0:
        return ("over", f"발송기한 {due['shipping_due_over_days']}일 지남")
    if due["shipping_due_text"]:
        return ("when", f"발송기한 {due['shipping_due_text']}")
    return ("", "")


def _history_place_step(*, done: int, total: int, fail_action: str) -> tuple[str, str]:
    """발주확인 칸의 ``(상태 키, 낱말)`` — 위에서부터 먼저 맞는 것 하나(계약 §2.3-B).

    판정을 템플릿 ``{% set %}`` 사슬에 두면 HTML 문자열 매칭 말고는 시험할 방법이 없고,
    같은 부품이 처리 탭·도크에 실릴 때 판정이 두 벌이 된다(2026-08-30 CEO 지적).
    낱말은 목업 확정본이 정본이라 **한 글자도 바꾸지 않는다**.

    Args:
        done: 집 안 발주확인 완료 링크 수.
        total: 집 안 링크 수.
        fail_action: :func:`_history_fail` 이 준 작업 이름(``confirm``·``dispatch``·…).

    Returns:
        ``(상태 키, 화면 낱말)``. 상태 키는 레인 B 의 ``.wb-pipe__s--*`` 와 짝이다.
    """
    if fail_action == "confirm":
        return ("bad", "발주확인 실패")
    if done == total:
        # 여러 건이 묶인 집만 N/M 을 붙인다 — `1/1` 은 세는 재미밖에 없다.
        return ("done", f"발주확인 완료 {done}/{total}" if total > 1 else "발주확인 완료")
    if done > 0:
        return ("now", f"발주확인 {done}/{total}")
    return ("now", "발주확인 할 차례")


def _history_dispatch_step(*, dispatch: dict[str, Any], moot: bool, fail_action: str,
                           place_done: int, place_total: int) -> tuple[str, str]:
    """발송 칸의 ``(상태 키, 낱말)`` — 위에서부터 먼저 맞는 것 하나(계약 §2.3-C).

    완료를 **글자로** 낸다: "배지가 없으면 완료" 는 화면 규칙을 외운 사람만 읽는다.
    ``moot`` 인 집은 ``발송 안 함``(회색)이다 — ``발송처리 할 차례``(주황)로 두면
    "지금 해라"는 뜻이 되어 되돌릴 수 없는 호출을 부른다.

    Args:
        dispatch: :func:`_history_dispatch` 결과.
        moot: 클레임이 걸려 이제 발송이 안 나가는 집인가(:func:`_history_naver_axis`).
        fail_action: :func:`_history_fail` 이 준 작업 이름.
        place_done: 집 안 발주확인 완료 링크 수.
        place_total: 집 안 링크 수.

    Returns:
        ``(상태 키, 화면 낱말)``. ``todo`` 는 **회색 이름만** 내는 자리라 클래스가 없다.
    """
    done, total = dispatch["done_count"], dispatch["total"]
    if fail_action == "dispatch":
        return ("bad", "발송처리 실패")
    if dispatch["mismatch"]:
        return ("bad", "네이버 기록 없음")
    if moot:
        return ("skip", "발송 안 함")
    if done == total and done > 0:
        return ("done", f"발송처리 완료 {done}/{total}" if total > 1 else "발송처리 완료")
    if done > 0:
        return ("now", f"발송처리 {done}/{total}")
    if place_done == place_total:
        return ("now", "발송처리 할 차례")
    return ("todo", "발송처리")


#: 클레임 배지에 붙는 미확정 꼬리(목업 `취소 요청 · 확정 전`). 네이버가 아직 확정하지
#: 않은 두 단계에만 붙고, 라벨 자체는 손대지 않는다 — 정본은 ``CLAIM_STATUS_LABELS`` 다.
_CLAIM_UNSETTLED_TAIL = " · 확정 전"

#: 수거 완료 배지 낱말(``CLAIM_STATUS_LABELS['COLLECT_DONE']``). 꼬리와 겹치는지 볼 때 쓴다.
_CLAIM_COLLECT_DONE_LABEL = "수거 완료"


def _history_month_day(value: str) -> str:
    """``YYYY-MM-DD HH:MM`` 을 ``MM-DD`` 로 줄인다 — **읽히는 값만**.

    :func:`_history_shipping_due` 가 이미 같은 함정을 한 번 밟았다(2026-08-30 CEO 지적 7):
    ``[5:10]`` 슬라이스는 날짜가 아닌 값도 잘라 낸다. 시각은 못 읽으면 원문을 그대로
    남기는 규약이라(:func:`_dispatch_time_text`) ``PENDING_REFUND_2026`` 같은 원문이
    그대로 올 수 있고, 그때 화면은 ``반품 완료 NG_RE`` 라고 적는다.

    Args:
        value: ``_dispatch_time_text`` 가 준 문자열(빈 값·원문일 수 있다).

    Returns:
        ``MM-DD``. 날짜로 못 읽으면 빈 문자열 — 화면은 그 조각을 통째로 안 낸다.
    """
    text = (value or "").strip()
    if len(text) < 10:
        return ""
    try:
        parsed = datetime.date.fromisoformat(text[:10])
    except (TypeError, ValueError):
        return ""
    return parsed.strftime("%m-%d")


def _history_claim_text(claim: dict[str, Any]) -> tuple[str, str]:
    """취소·반품 줄이 찍는 두 문자열 — 배지 낱말과 그 뒤 작은 글자(계약 §3.3).

    목업 확정본이 정본이다: 배지는 `반품 완료 08-26` 처럼 **확정 라벨 뒤에 날짜**를 달고,
    작은 글자는 `단순 변심 · 환불 예정 08-30` · `수거 완료 08-25 · 환불 완료` 처럼
    사유·수거·환불 조각을 잇는다. 서버가 조립하는 이유는 판정표와 같다 — 템플릿에 두면
    HTML 문자열 매칭 말고는 시험할 방법이 없다(2026-08-30 CEO 지적 4).

    **값이 있는 조각만 낸다.** 빈 조각을 빈 칸이나 ``–`` 로 채우면 "값이 없다"와 "우리가
    모른다"가 화면에서 같은 모양이 된다. 날짜는 **확정된 건에만** 붙인다 — 미확정 건에
    붙이면 아직 안 끝난 일에 끝난 날짜를 적는 셈이다.

    Args:
        claim: :func:`_history_claim` 결과.

    Returns:
        ``(배지 낱말, 작은 글자)``. 클레임이 없으면 둘 다 빈 문자열이다.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        CLAIM_PHASE_PROGRESS,
        CLAIM_PHASE_REQUESTED,
    )

    if not claim["label"]:
        return ("", "")
    badge = claim["label"]
    collect_text = claim["collect_done_text"]
    # `수거 완료` 집은 배지 낱말이 이미 그 사건이다. 꼬리에 `수거 완료 08-25` 를 또 적으면
    # 한 줄에 같은 낱말이 두 번 선다(2026-08-30 CEO 지적 3). 날짜는 배지로 올리고 꼬리에서
    # 뺀다 — 그 날짜는 **끝난 하위 사건의 시각**이라 미확정 건에 붙어도 거짓이 아니다.
    collect_on_badge = bool(collect_text) and badge.startswith(_CLAIM_COLLECT_DONE_LABEL)
    if collect_on_badge:
        badge += " " + collect_text
    if claim["phase"] in (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS):
        badge += _CLAIM_UNSETTLED_TAIL
    elif claim["done_text"]:
        badge += " " + claim["done_text"]
    parts = [part for part in (
        claim["reason"],
        f"수거 완료 {collect_text}" if collect_text and not collect_on_badge else "",
        f"환불 예정 {claim['refund_expected_text']}" if claim["refund_expected_text"] else "",
        "환불 완료" if claim["refund_done"] else "",
    ) if part]
    return (badge, " · ".join(parts))


def _history_naver_axis(*, place_done_count: int, dispatch: dict[str, Any],
                        fail: dict[str, str], claim: dict[str, Any],
                        statuses: list[str]) -> dict[str, bool]:
    """네이버 축의 두 예외 판정(계약 §2.3-C·D).

    - ``dispatch_moot``: 발송이 0건인데 클레임이 걸려 **더 안 나가는** 집.
      ``발송처리 할 차례``(주황)로 두면 "지금 해라"는 뜻이 되어 되돌릴 수 없는 호출을 부른다.
    - ``naver_skipped``: 네이버 축에 말할 것이 **아예 없는** 집 — 수집 자체가 실패했거나,
      발주확인·발송 전에 취소가 확정됐다. 반대로 발주확인·발송이 이미 있었던 집(반품 완료)은
      파이프를 그대로 낸다 — 그 일은 실제로 일어났다.

    Args:
        place_done_count: 집 안 발주확인 완료 링크 수.
        dispatch: :func:`_history_dispatch` 결과.
        fail: :func:`_history_fail` 결과.
        claim: :func:`_history_claim` 결과.
        statuses: 집 안 링크 상태 목록(중복 제거된 것).

    Returns:
        ``{"dispatch_moot": bool, "naver_skipped": bool}``.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        CLAIM_PHASE_DONE,
        CLAIM_PHASE_PROGRESS,
        CLAIM_PHASE_REQUESTED,
    )

    phase = claim["phase"]
    moot = dispatch["done_count"] == 0 and phase in (
        CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS, CLAIM_PHASE_DONE)
    quiet = (place_done_count == 0 and dispatch["done_count"] == 0
             and not fail["action"]) and (
        all(status == "FAILED" for status in statuses)
        or (phase == CLAIM_PHASE_DONE and claim["kind"] in ("CANCEL", "RETURN")))
    return {"dispatch_moot": moot, "naver_skipped": quiet}


def _history_pipe_fields(*, group_size: int, place_done_count: int,
                         dispatch: dict[str, Any], fail: dict[str, str],
                         naver_axis: dict[str, bool],
                         due: dict[str, Any]) -> dict[str, Any]:
    """네이버 파이프 두 칸이 행에 싣는 필드 한 벌 — **재료와 판정 결과를 함께** 준다.

    판정(``*_state``·``*_text``)을 재료 옆에서 만드는 이유: 둘이 떨어지면 재료만 보고
    화면 낱말을 다시 짐작하는 코드가 다른 곳에 생긴다(그 짐작이 템플릿 ``{% set %}``
    사슬이었다 — 2026-08-30 CEO 지적).

    Args:
        group_size: 집 안 링크 수(발주확인·발송 분모).
        place_done_count: 집 안 발주확인 완료 링크 수.
        dispatch: :func:`_history_dispatch` 결과.
        fail: :func:`_history_fail` 결과.
        naver_axis: :func:`_history_naver_axis` 결과.

    Returns:
        ``place_*``·``dispatch_*``·``naver_skipped`` 필드 dict.
    """
    place_state, place_text = _history_place_step(
        done=place_done_count, total=group_size, fail_action=fail["action"])
    dispatch_state, dispatch_text = _history_dispatch_step(
        dispatch=dispatch, moot=naver_axis["dispatch_moot"], fail_action=fail["action"],
        place_done=place_done_count, place_total=group_size)
    note_kind, note_text = _history_pipe_note(
        fail=fail, dispatch_state=dispatch_state, dispatch=dispatch, due=due)
    return {
        # 발주확인 N/M — ``place_pending`` 과 **같은 재료**로 센다
        # (``place_pending == (place_done_count < place_total)`` 이 항상 참이어야 한다).
        "place_done_count": place_done_count,
        "place_total": group_size,
        "place_state": place_state,
        "place_text": place_text,
        # 두 시각과 N/M 은 행에 싣지 않는다 — 부속 문구(`pipe_note_*`)와 파이프 낱말
        # (`dispatch_text`)이 이미 그 값을 담고 있고, 화면이 안 읽는 값을 남기면 다음
        # 사람이 "화면에 이미 있다"고 오독한다(같은 지적이 세 번째다).
        "dispatch_mismatch": dispatch["mismatch"],
        # 경고 줄 전용 시각 — **어긋난 그 링크**의 것이다. ``dispatch_ours_at`` 을 쓰면
        # 정상 발송된 형제의 시각을 "네이버 기록 없음" 이라 말한다.
        "dispatch_mismatch_ours_at": dispatch["mismatch_ours_at"],
        "dispatch_state": dispatch_state,
        "dispatch_text": dispatch_text,
        # 파이프 옆 부속 문구 — 종류는 템플릿이 CSS 클래스로만 옮긴다.
        "pipe_note_kind": note_kind,
        "pipe_note_text": note_text,
        "naver_skipped": naver_axis["naver_skipped"],
    }


def _history_group_axes(group: list[dict[str, Any]], *, lead: dict[str, Any],
                        ordered: list[dict[str, Any]],
                        statuses: list[str]) -> dict[str, Any]:
    """상태 칸이 읽는 축 필드 한 벌(계약 §2.2) — 재료는 **이 집의 멤버뿐**이다.

    집계를 행 조립에서 떼어 놓는 이유: 축이 늘어날 때마다 행 dict 이 부풀면 "무엇이
    기존 필드고 무엇이 새 축인지"가 안 보이고, 축끼리의 판정 순서(실패 > 어긋남 > 해당
    없음)가 dict 리터럴 사이에 흩어진다.

    **판정 결과를 싣는다**(재료가 아니라): 발주확인·발송 칸의 상태 키와 낱말, 취소·반품
    줄의 두 문자열이 전부 여기서 정해진다. 템플릿은 상태 키 → CSS 클래스 대응만 한다
    (계약 §5 의 "레인 C 가 매핑" 은 클래스 대응을 뜻하지 판정 자체를 뜻하지 않는다).

    Args:
        group: 집 멤버 목록(**표시 순서 그대로** — 클레임 라벨 선택이 이 순서에 걸린다).
        lead: 대표(금액 최대) 멤버.
        ordered: **대표 먼저** 정렬한 같은 멤버 목록(관계·실패가 이 순서를 쓴다).
        statuses: 집 안 링크 상태 목록(중복 제거된 것).

    Returns:
        행 dict 에 그대로 합칠 축 필드들(``foms_*``·``relation*``·``place_*``·
        ``dispatch_*``·``fail``·``claim_*``·``shipping_due*``).
    """
    claim = _history_claim(group)
    fail = _history_fail(ordered)
    dispatch = _history_dispatch(group)
    due = _history_shipping_due(group)
    relation, related_order_id = _history_relation(ordered)
    place_done_count = sum(1 for row in group if row["place_confirmed"])
    foms_state = _history_foms_state(lead, statuses)
    naver_axis = _history_naver_axis(place_done_count=place_done_count, dispatch=dispatch,
                                     fail=fail, claim=claim, statuses=statuses)
    claim_badge_text, claim_tail_text = _history_claim_text(claim)
    return {
        # FOMS 축. 라벨은 **서버가 실어** 준다 — 템플릿이 dict 를 다시 뒤지지 않는다.
        "foms_state": foms_state,
        "foms_label": HISTORY_FOMS_LABELS[foms_state],
        # 관계 축. 이력 집은 신규도 ``NEW`` 다(처리 탭 집은 빈 문자열 — 규약이 다르다).
        "relation": relation,
        "relation_label": HISTORY_RELATION_LABELS[relation],
        "related_order_id": related_order_id,
        # 네이버 파이프(발주확인·발송) 재료 + 판정 결과.
        **_history_pipe_fields(group_size=len(group), place_done_count=place_done_count,
                               dispatch=dispatch, fail=fail, naver_axis=naver_axis,
                               due=due),
        # 실패 축(발주확인·발송처리 공용). 실패가 없으면 네 값 모두 빈 문자열.
        "fail": fail,
        # 취소·반품 축 — 라벨·단계·사유가 전부 **같은 멤버**에서 나온 값들이다.
        # 화면이 읽는 것은 아래 넷뿐이다. 원재료(사유 코드·시각 3종)를 행에 또 실으면
        # 아무도 안 읽는 값이 되고, 다음 사람이 "화면에 이미 있다"고 오독한다.
        "claim_label": claim["label"],
        # 부분/전부 집계 코드(T5). 라벨은 표시 축이라 낱말이 바뀌고, 분기는 이쪽에 건다.
        "claim_code": claim["code"],
        "claim_phase": claim["phase"],
        "claim_badge_text": claim_badge_text,
        "claim_tail_text": claim_tail_text,
        # 발송기한은 부속 문구(`pipe_note_*`)가 이미 담는다 — 행에 따로 싣지 않는다.
    }


def _history_group_row(group: list[dict[str, Any]]) -> dict[str, Any]:
    """집(묶음) 하나를 이력 표의 **한 줄**로 접는다 — 재료는 ``group`` 뿐(추가 쿼리 0).

    Args:
        group: 한 집의 멤버 dict 목록(:func:`_link_rows` 가 이미 만들어 둔 것).

    Returns:
        이력 표 한 행. 기존 필드 + :func:`_history_group_axes` 의 축 필드.
    """
    # 대표(본품) = 금액 최대. 0원 구성이 제목이 되면 무슨 주문인지 알 수 없다.
    lead = max(group, key=lambda row: (row["amount"] or 0, -row["id"]))
    rest = [row for row in group if row["id"] != lead["id"]]
    amounts = [row["amount"] for row in group if row["amount"] is not None]
    quantities = [row["quantity"] for row in group if row["quantity"] is not None]
    pending = [row for row in group if not row["order_id"]
               and row["sync_status"] in ("COLLECTED", "PENDING_REVIEW")]
    # 묶음 안 상태를 중복 없이(표시 순서 유지) — 한 집에 성공/실패가 섞일 수 있다.
    statuses = list(dict.fromkeys(row["sync_status"] for row in group))
    return {
        "id": lead["id"],
        "external_id": lead["external_id"],
        "external_order_no": lead["external_order_no"],
        "sync_status": lead["sync_status"],
        "created_at": lead["created_at"],
        "order_id": lead["order_id"],
        "customer_name": lead["customer_name"],
        "product": lead["product"],
        "quantity": sum(quantities) if quantities else None,
        "amount": sum(amounts) if amounts else None,
        "payment": lead["payment"],
        "discount_total": sum(row["payment"]["discount"] for row in group),
        # 승격은 집 단위다 — 한 건이라도 취소·반품이면 promote_link_to_order 가 막는다
        # (promotion.py). 화면도 같은 판정으로 버튼을 잠가야 헛클릭이 안 난다.
        "claim_blocking": any(row["claim_blocking"] for row in group),
        # 발주확인은 상품주문 단위라 한 건만 남아도 그 집은 아직 끝난 게 아니다(T16-A).
        "place_pending": any(not row["place_confirmed"] for row in group),
        "failure_reason": next((row["failure_reason"] for row in group
                                if row["failure_reason"]), ""),
        "count": len(group),
        "extra_count": len(rest),
        "statuses": statuses,
        **_history_group_axes(group, lead=lead, ordered=[lead, *rest],
                              statuses=statuses),
        "pending_link_id": pending[0]["id"] if pending else None,
        "pending_count": len(pending),
        "next_step": ("주문 만들기" if pending
                      else ("규격 입력" if lead["order_id"]
                            and not order_has_spec_rows(lead["_order"]) else "")),
        # 펼침 목록도 대표 먼저(map_group·도크·확인 화면과 같은 순서 규칙).
        "members": [lead, *rest],
    }


def _history_find_term(raw: Optional[str]) -> str:
    """이력 탭 찾기 낱말을 정리한다 — 빈 값이면 빈 문자열(필터 없음).

    Args:
        raw: 쿼리스트링에서 온 원문.

    Returns:
        앞뒤 공백을 떼고 :data:`HISTORY_FIND_MAX` 로 자른 낱말.
    """
    return (raw or "").strip()[:HISTORY_FIND_MAX]


def _history_find_clause(term: str) -> Optional[ColumnElement]:
    """이력 탭 찾기 술어 — **SQL 로** 좁힌다(집 선정 단계에서 쓴다).

    파이썬으로 거르지 않는 이유: 쪽을 먼저 자른 뒤에 걸러내면 ``total``·``pages`` 가
    거짓말이 되고(캡 뒤 파이썬 분류 함정), 무엇보다 찾기가 **지금 쪽 50집**에만 닿는다 —
    16쪽짜리 이력에서 사람이 이름을 쳐도 0주문이 나온 그 결함이다(2026-09-02 사용자 보고).

    보는 자리(모두 컬럼이다 — JSONB 스캔 금지):
      * ``external_order_no`` — 네이버 주문번호(행 어디에도 글자로 없어 여기서만 찾힌다).
      * ``recipient_name`` — 스냅샷 수취인 이름의 컬럼 사본(주문이 아직 없는 수집분).
      * ``group_key`` — 집 키(주문번호·수취인 전화·주소를 이은 값).
      * 붙은 FOMS 주문의 ``customer_name``·``phone`` — ``orders`` 는 이 두 칸에 인덱스가
        있다(``ix_orders_customer_name_trgm`` · ``phone`` b-tree).
      * 숫자만 친 경우: 수취인·주문자 전화 숫자, 그리고 FOMS 주문번호 정확일치.

    ``product`` 는 못 본다 — 제품명은 ``raw_snapshot`` 파생값이라 SQL 이 닿지 못한다.
    그래서 placeholder 도 제품을 약속하지 않는다(칸이 못 하는 일을 적으면 또 오해가 난다).

    Args:
        term: :func:`_history_find_term` 이 정리한 낱말(빈 문자열이면 ``None`` 을 준다).

    Returns:
        ``or_`` 술어 또는 ``None``.
    """
    if not term:
        return None
    from sqlalchemy import or_, select

    pattern = f"%{term}%"
    digits = "".join(ch for ch in term if ch.isdigit())
    order_match = select(Order.id).where(
        or_(Order.customer_name.ilike(pattern), Order.phone.ilike(pattern)))
    clauses = [
        ExternalOrderLink.external_order_no.ilike(pattern),
        ExternalOrderLink.recipient_name.ilike(pattern),
        ExternalOrderLink.group_key.ilike(pattern),
        ExternalOrderLink.order_id.in_(order_match),  # perf-ok: orders 는 trgm 인덱스
    ]
    if digits:
        clauses.append(ExternalOrderLink.recipient_phone_digits.ilike(f"%{digits}%"))
        clauses.append(ExternalOrderLink.orderer_phone_digits.ilike(f"%{digits}%"))
        if len(digits) <= 9:
            # 화면이 FOMS 주문을 `#5053` 으로 보여준다 — 그 숫자를 그대로 쳐도 찾혀야 한다.
            clauses.append(ExternalOrderLink.order_id == int(digits))
    return or_(*clauses)


def _link_rows(db, *, status: Optional[str], page: int,
               place_pending: bool = False, dispatch_pending: bool = False,
               relation_filter: bool = False,
               find: str = "") -> tuple[list[dict], int]:
    """수집 이력을 **한 집 = 한 줄**로 묶어 돌려준다(T14-H).

    페이지는 묶음(네이버 주문번호) 단위로 센다 — 상품주문 단위로 자르면 페이지 끝에서 한
    집의 일부만 보인다. 상태 필터는 **묶음 선정에만** 쓰고, 뽑힌 묶음의 상품주문은 상태와
    무관하게 전부 싣는다(2026-08-18 사용자 확정: "해당 줄이 하나라도 있으면 보이기" —
    문제가 어느 집에서 났는지 맥락까지 보여야 한다).

    상태 칸이 읽는 축 필드(관계·발주확인/발송 N/M·어긋남·실패·클레임·발송기한)는 **이미
    읽은 페이지 링크로만** 만든다 — 추가 쿼리 0. 행마다 도는 함수(``origin_facts`` ·
    ``find_ghost_orders`` · ``find_order_candidates``)는 여기서 부르지 않는다(계약 §8).

    Args:
        db: 요청 스코프 DB 세션.
        status: 수집 상태 필터(:data:`VALID_STATUSES`) 또는 ``None``.
        page: 1부터 세는 쪽 번호.
        place_pending: '발주확인 남음' 칩.
        dispatch_pending: '발송처리 남음' 칩(:func:`_dispatch_pending_clause`).
        relation_filter: '추가결제·재결제' 칩(:func:`_relation_clause`).
        find: 찾기 낱말(:func:`_history_find_clause`). 다른 필터와 **같은 규약**이다 —
            해당 링크가 하나라도 있는 집을 고르고, 뽑힌 집의 상품주문은 전부 싣는다.
            ``total`` 도 좁혀진 총계라 쪽수·"N주문" 이 찾은 결과와 어긋나지 않는다.

    Returns:
        ``(묶음 목록, 묶음 총 개수)``.
    """
    from sqlalchemy import func

    key_col = _group_key_col()

    key_query = (
        db.query(key_col, func.max(ExternalOrderLink.created_at).label("last_at"))
        .filter(ExternalOrderLink.channel == "NAVER")
    )
    if status in VALID_STATUSES:
        key_query = key_query.filter(ExternalOrderLink.sync_status == status)
    if place_pending:
        # 상태 필터와 같은 규약: "해당 링크가 하나라도 있는 집"을 고른다.
        key_query = key_query.filter(_place_pending_clause())
    if dispatch_pending:
        # 같은 규약 — 발송 기록이 아직 없는 링크가 하나라도 있으면 그 집을 고른다.
        key_query = key_query.filter(_dispatch_pending_clause())
    if relation_filter:
        key_query = key_query.filter(_relation_clause())
    find_clause = _history_find_clause(find)
    if find_clause is not None:
        key_query = key_query.filter(find_clause)
    key_query = key_query.group_by(key_col)

    total = key_query.count()
    page_keys = [
        row[0] for row in key_query.order_by(func.max(ExternalOrderLink.created_at).desc(),
                                             key_col.desc())
        .offset((page - 1) * PAGE_SIZE)
        .limit(PAGE_SIZE)
        .all()
    ]
    if not page_keys:
        return ([], total)

    links = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                key_col.in_(page_keys))  # perf-ok: 페이지 키 batch(최대 PAGE_SIZE)
        .order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
        .all()
    )
    order_ids = [int(link.order_id) for link in links if link.order_id]
    orders = {}
    if order_ids:
        # N+1 금지 — 한 번에 당겨 dict 로 붙인다.
        orders = {
            order.id: order
            for order in db.query(Order).filter(Order.id.in_(order_ids)).all()
        }
    # 같은 네이버 주문번호로 함께 묶일 미생성 건수(사람이 버튼 누르기 전에 알아야 한다).
    pending_group_counts: dict[str, int] = {}
    order_nos = [link.external_order_no for link in links
                 if link.external_order_no and not link.order_id]
    if order_nos:
        from sqlalchemy import func as _func
        rows_group = (
            db.query(ExternalOrderLink.external_order_no, _func.count(ExternalOrderLink.id))
            .filter(ExternalOrderLink.channel == "NAVER",
                    ExternalOrderLink.external_order_no.in_(order_nos),  # perf-ok: 페이지 주문번호 batch
                    ExternalOrderLink.order_id.is_(None))
            .group_by(ExternalOrderLink.external_order_no)
            .all()
        )
        pending_group_counts = {no: int(cnt) for no, cnt in rows_group}

    members: dict[str, list[dict]] = {}
    order_of_key: list[str] = []
    for link in links:
        order = orders.get(int(link.order_id)) if link.order_id else None
        # 주문이 아직 없는 수집분(COLLECTED)은 원본 스냅샷에서 표시값을 뽑는다 —
        # 사람이 무엇을 받았는지 보고 "주문 만들기"를 누를지 판단해야 하기 때문이다.
        summary = summarize_snapshot(link.raw_snapshot)
        key = _history_group_key(link)
        if key not in members:
            members[key] = []
            order_of_key.append(key)
        members[key].append({
            "id": link.id,
            "external_id": link.external_id,
            "external_order_no": link.external_order_no,
            "sync_status": link.sync_status,
            "failure_reason": link.failure_reason,
            "created_at": format_datetime_kst(link.created_at),
            "order_id": link.order_id,
            "customer_name": getattr(order, "customer_name", None) or summary["customer_name"],
            "product": getattr(order, "product", None) or summary["product"],
            "options": summary["options"],
            "quantity": summary["quantity"],
            "amount": summary["amount"],
            "order_date": summary["order_date"],
            "payment": _payment_summary(link.raw_snapshot),
            "claim_label": summary["claim_label"],
            "claim_blocking": summary["claim_blocking"],
            "place_confirmed": _place_view(link)["confirmed"],
            "place_label": _place_view(link)["label"],
            # 상태 칸이 쓰는 축 원재료(관계·클레임 단계·발송·실패·발송기한).
            # 화면은 멤버를 직접 안 읽는다 — 아래 집계의 재료다(계약 §2.1).
            **_history_member_axes(link, summary),
            "_order": order,
        })

    rows = [_history_group_row(members[key]) for key in order_of_key]
    return (rows, total)


@admin_bp.route("/admin/naver-ingest")
@login_required
@role_required(["ADMIN"])
def naver_ingest_dashboard():
    """수집 이력·워터마크·만료일을 한 화면에 보여준다(읽기 전용).

    워크벤치 게이트가 켜진 사용자는 본진(``naver_ingest_triage``)의 '전체 이력' 탭으로
    보낸다 — 두 URL 왕복을 없애는 것이 개편의 출발점이었다. 걸어 둔 필터는 그대로 넘긴다
    (조건을 잃으면 사용자가 방금 좁힌 목록을 다시 만들어야 한다).
    게이트가 꺼져 있으면 이 화면이 예전 그대로 뜬다.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled

    if is_naver_workbench_enabled(session.get("user_id")):
        status_arg = (request.args.get("status") or "").strip().upper()
        return redirect(url_for(
            "admin.naver_ingest_triage",
            tab="all",
            status=status_arg if status_arg in VALID_STATUSES else None,
            place="PENDING" if (request.args.get("place") or "").strip().upper() == "PENDING" else None,
            page=request.args.get("page", type=int) or None,
        ))

    db = get_db()
    status = (request.args.get("status") or "").strip().upper()
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    place_pending = (request.args.get("place") or "").strip().upper() == "PENDING"
    rows, total = _link_rows(db, status=status if status in VALID_STATUSES else None,
                             page=page, place_pending=place_pending)
    counts = _status_group_counts(db)
    place_pending_count = _place_pending_group_count(db)
    return render_template(
        "admin/naver_ingest.html",
        rows=rows,
        total=total,
        page=page,
        page_size=PAGE_SIZE,
        status=status if status in VALID_STATUSES else "",
        counts=counts,
        place_pending=place_pending,
        place_pending_count=place_pending_count,
        watermark=_watermark_view(db),
        expiry=_expiry_view(db),
    )


def _place_view(link: ExternalOrderLink) -> dict[str, Any]:
    """링크의 발주 상태 표시값 — 컬럼 우선, 없으면 원본 스냅샷.

    컬럼만 보면 백필 전 데이터가 빈칸이 되고, 스냅샷만 보면 우리가 발주확인을 보낸 뒤에도
    "발주확인 전"으로 남는다(버튼이 사라지지 않는다). 둘을 이 순서로 합친다.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        extract_place_status,
        place_status_view,
    )

    column = (link.place_order_status or "").strip()
    if column:
        view = place_status_view(column)
    else:
        view = extract_place_status(link.raw_snapshot or {})
    shipping_due = extract_place_status(link.raw_snapshot or {})["shipping_due"]
    return {**view, "shipping_due": shipping_due}


def _dispatch_view(link: ExternalOrderLink) -> dict[str, Any]:
    """발송 결과 한 줄 — **우리 기록과 네이버가 말하는 것을 나란히** 놓는다 (F-2).

    발송처리는 우리가 눌러서 나가는 되돌릴 수 없는 호출인데, 지금까지 화면은 우리 쪽
    표식(``triage_state['fulfillment']['dispatched_at']``)만 읽었다. 네이버는 그 결과를
    원본 스냅샷의 ``delivery.sendDate``·``delivery.deliveryStatus`` 로 돌려주는데
    아무도 안 읽어서 **"우리는 보냈다는데 네이버에는 안 찍힌"** 어긋남이 화면에 없었다
    (``docs/guides/NAVER_FIELD_INVENTORY.md`` §2.4).

    시각 문자열을 사람이 읽는 형식으로 바꾸는 것은 화면 몫이라 여기서 한다
    (``extract_delivery`` 는 원문 그대로 준다). **읽을 수 없는 값은 원문을 그대로**
    남긴다 — 못 읽었다고 지우면 화면이 "발송 기록이 없다"고 거짓말을 한다.

    Args:
        link: pane 에 띄운 링크.

    Returns:
        ``ours_at``(우리 기록 KST) · ``naver_at``(네이버 sendDate KST) ·
        ``naver_status``·``naver_status_label``·``method``·``wrong_tracking`` ·
        ``known``(어느 한쪽이라도 말이 있는가) ·
        ``mismatch``(**우리 기록만 있고 네이버가 침묵하는가** — 되돌릴 수 없는 호출이
        유실된 자리다. 반대 방향은 판매자센터 직접 발송이라 경고가 아니다).
        ``known`` 이 False 면 화면은 **그 줄 자체를 내지 않는다**.
    """
    from foms.services.integrations.naver_commerce.mapping import extract_delivery

    delivery = extract_delivery(link.raw_snapshot or {})
    naver_at = _dispatch_time_text(delivery.get("send_date"))
    ours_at = _dispatch_time_text(
        ((link.triage_state or {}).get("fulfillment") or {}).get("dispatched_at"))
    return {
        "ours_at": ours_at,
        "naver_at": naver_at,
        "naver_status": delivery.get("status") or "",
        "naver_status_label": delivery.get("status_label") or "",
        "method": delivery.get("method") or "",
        "wrong_tracking": bool(delivery.get("wrong_tracking")),
        # 상태 라벨만 있고 시각이 없는 집도 말할 것이 있다(네이버가 배송 축을 갖고 있다).
        "known": bool(ours_at or naver_at or (delivery.get("status") or "")),
        # **우리는 보냈다는데 네이버가 침묵하는 쪽**만 어긋남이다 (2026-08-26 실데이터로 좁혔다).
        # 양방향으로 보면 "네이버에만 기록이 있는" 집까지 걸리는데, 스테이징 실데이터에서
        # 그것이 발송 줄 44건 중 41건이었다(우리 쪽만 있는 진짜 사고는 0건). 그 방향은
        # 사고가 아니라 **판매자센터에서 직접 나간 발송**이라, 경고를 달면 93% 가 상시
        # 경고가 되어 진짜 어긋남을 덮는다. 두 열은 그대로 나란히 있으니 사실은 안 사라진다.
        "mismatch": bool(ours_at) and not bool(naver_at),
    }


def _return_axis_view(link: ExternalOrderLink) -> dict[str, Any]:
    """반품 **진행**(수거·환불) 한 묶음 — T8-S0.

    클레임 배지는 "반품 요청"까지만 말한다. 그 다음 사람이 실제로 묻는 것은 **언제
    회수됐나 · 어디로 가야 하나 · 환불이 언제 나가나** 셋이고, 셋 다 원본 스냅샷에
    이미 들어 있는데 화면이 안 읽었다(``NAVER_FIELD_INVENTORY`` §2.5 — 회수지 15/281).
    F-1~F-3 와 같은 성질이라 **네이버로 나가는 호출은 0**이다.

    시각 문자열을 사람이 읽는 형식으로 바꾸는 것은 화면 몫이라 여기서 한다
    (:func:`mapping.extract_return_axis` 는 원문 그대로 준다). 못 읽는 값은 원문을
    그대로 남긴다 — 못 읽었다고 지우면 화면이 "기록이 없다"고 거짓말한다.

    Args:
        link: pane 에 띄운 링크.

    Returns:
        :func:`mapping.extract_return_axis` 결과에서 두 시각만 KST 문자열로 바꾼 dict.
        ``known`` 이 False 면 화면은 **그 줄 자체를 내지 않는다**.
    """
    from foms.services.integrations.naver_commerce.mapping import extract_return_axis

    axis = dict(extract_return_axis(link.raw_snapshot or {}))
    axis["collect_completed_at"] = _dispatch_time_text(axis["collect_completed_at"])
    axis["refund_expected_at"] = _dispatch_time_text(axis["refund_expected_at"])
    # 반품 완료 시각(R-5). 앞의 둘과 **같은 파서**를 쓴다 — 한 줄 안에서 시각 모양이
    # 갈리면 눈이 두 값을 비교하지 못한다.
    axis["return_completed_at"] = _dispatch_time_text(axis["return_completed_at"])
    return axis


def _dispatch_time_text(value: Any) -> str:
    """발송 시각 하나를 사람이 읽는 KST 문자열로 편다(못 읽으면 원문 그대로).

    Args:
        value: ISO 문자열 또는 ``None``. 네이버 ``sendDate`` 는 오프셋이 붙어 오고
            우리 표식은 UTC naive isoformat 이다 — 둘 다 같은 파서가 받는다.

    Returns:
        ``YYYY-MM-DD HH:MM`` 문자열. 값이 없으면 빈 문자열, 못 읽으면 원문.
    """
    text = str(value).strip() if value else ""
    if not text:
        return ""
    return format_datetime_kst(text, "%Y-%m-%d %H:%M") or text


def _triage_pane(db, link: ExternalOrderLink, *,
                 with_candidates: bool = True) -> dict[str, Any]:
    """한 건의 원본 ↔ FOMS 현재 값 대조 데이터를 만든다.

    옵션 원문을 크게 보여주는 것이 이 화면의 존재 이유다 — v1 은 규격을 파싱하지 않으므로
    사람이 이 문자열을 읽고 편집기에서 채운다.

    Args:
        db: 요청 스코프 DB 세션.
        link: 펼칠 링크.
        with_candidates: 붙일 만한 기존 주문 후보까지 찾는가. **읽기 전용 상세**
            (:func:`naver_ingest_triage_detail`)는 붙이기를 못 하므로 False 로 부른다 —
            그리지도 않을 값을 위해 후보 탐색과 정리 계획 조회를 돌리지 않는다.

    Returns:
        pane 컨텍스트 dict. ``with_candidates`` 가 False 면 ``candidates`` 는 빈 목록이다.
    """
    from foms.services.integrations.naver_commerce.mapping import (
        build_payment_info,
        extract_claim,
        extract_place_status,
        extract_shipping_memo,
        unwrap_detail,
    )

    from foms.services.integrations.naver_commerce.repay_reconcile import (
        attach_reconcile_plans,
    )

    order = db.get(Order, int(link.order_id)) if link.order_id else None
    naver_order, product_order, shipping = unwrap_detail(link.raw_snapshot or {})
    # 후보마다 **정리 계획**(R-3)을 미리 실어 둔다 — 관계를 고를 때마다 왕복하지 않는다.
    candidates = find_order_candidates(db, link) if with_candidates else []
    if candidates:
        attach_reconcile_plans(db, candidates)
    household = summarize_link_household(db, link_id=int(link.id))
    return {
        "link_id": link.id,
        "external_id": link.external_id,
        "created_at": format_datetime_kst(link.created_at),
        "order_id": link.order_id,
        "sync_status": link.sync_status,
        "naver": {
            "product_name": product_order.get("productName"),
            "option": product_order.get("productOption"),
            "quantity": product_order.get("quantity"),
            "amount": product_order.get("totalPaymentAmount"),
            "seller_product_code": product_order.get("sellerProductCode"),
            "shipping_due_date": product_order.get("shippingDueDate"),
            "orderer_name": naver_order.get("ordererName"),
            "orderer_tel": naver_order.get("ordererTel"),
            "recipient_name": shipping.get("name"),
            "recipient_tel": shipping.get("tel1"),
            "address": " ".join(
                part for part in (shipping.get("baseAddress"), shipping.get("detailedAddress"))
                if part
            ).strip(),
            # 실위치는 productOrder.shippingMemo (mapping.extract_shipping_memo 참조).
            # 원본 스냅샷에서 읽으므로 과거 수집분도 재처리 없이 그대로 보인다.
            "shipping_memo": extract_shipping_memo(link.raw_snapshot or {}),
            "recipient_tel2": shipping.get("tel2"),
            "product_id": product_order.get("productId"),
            "inflow_path": product_order.get("inflowPath"),
        },
        # CS 흐름은 ① 주문 만들기 ② ERP 규격 입력까지다. 담당자 지정은 이 단계가 아니라
        # 고객 통화 → 실측일 지정 → 실측 스케줄링 시점에 한다(2026-08-17 사용자 확정).
        "steps": {
            "order_created": bool(link.order_id),
            "spec_filled": order_has_spec_rows(order),
            # 추가결제는 사람이 확인을 끝낸 뒤에 발송처리한다(업무 규칙 T16-H).
            "reviewed": link.reviewed_at is not None,
        },
        # 발주확인·발송처리 처리 이력(멱등 기록). 값이 있으면 다시 부르지 않는다 — T16-G.
        "fulfillment": (link.triage_state or {}).get("fulfillment") or {},
        "edit_url": (url_for("order_edit.edit_order", order_id=int(link.order_id),
                             open="erp-order") if link.order_id else ""),
        # 취소·반품은 productOrderStatus 로는 안 보인다 — 별도 축으로 싣는다.
        "claim": extract_claim(link.raw_snapshot or {}),
        # 발송 결과(F-2) — 우리 기록과 네이버가 말하는 것을 나란히. 어긋나면 화면이 말한다.
        "dispatch": _dispatch_view(link),
        # 반품 진행(T8-S0) — 수거·환불·회수지. 배지가 말하지 않는 "그 다음"이 여기 있다.
        "return_axis": _return_axis_view(link),
        # 발주확인 여부(네이버 판매자센터 처리 상태). 표시 SSOT 는 컬럼이고(수집·스윕·우리
        # 발주확인이 갱신), 컬럼이 비면 원본 스냅샷으로 폴백한다 — T16-A/T16-G.
        "place": _place_view(link),
        # 이 수집분이 붙을 만한 기존 주문 후보 — 재결제·차액 결제 판별용(T16-C/D).
        # **자동으로 붙이지 않는다.** 근거와 함께 늘어놓고 사람이 고른다.
        "relation": link.relation,
        "candidates": candidates,
        # 정리 카드 1번 칸이 재진술할 **새 집** 숫자(집 단위 — 화면과 서버가 같은 값을 쓴다).
        "household": household,
        "seller_center_url": SELLER_CENTER_URL,
        "payment": build_payment_info(link.raw_snapshot or {}),
        "foms": {
            "customer_name": getattr(order, "customer_name", None),
            "phone": getattr(order, "phone", None),
            "address": getattr(order, "address", None),
            "product": getattr(order, "product", None),
            "options": getattr(order, "options", None),
            "payment_amount": getattr(order, "payment_amount", None),
        },
    }


class _ThinLink:
    """판정용 **얇은** 링크 행 — ``raw_snapshot`` 자리에 축소 문서가 들어간다.

    nav 뱃지는 **모든 페이지 렌더**에서 :func:`_work_groups` 를 돈다. 그런데 목록 판정에
    실제로 필요한 것은 스냅샷 전체가 아니라 몇 개 경로뿐이다 — 2026-08-24 실측으로
    3.3KB ``raw_snapshot`` 본문이 행 조회 비용의 **약 80%** 를 먹는 것을 확인했다
    (240행: 통째 22.3ms vs 스냅샷 제외 4.4ms). 파싱은 범인이 아니다
    (``summarize_snapshot`` 979회에 5.5ms).

    ORM 인스턴스로 만들지 않는 이유는 **세션 identity map** 이다. 같은 요청에서 pane 이
    이미 통째로 읽어 둔 링크를 뱃지 조회가 얇은 값으로 덮거나, 반대로 얇게 읽힌 인스턴스를
    pane 이 건드려 지연 로딩 N+1 이 나는 자리다. 읽기 전용 평행 객체를 쓰면 그 접점이 없다.

    ``ExternalOrderLink`` 와 **같은 속성 이름만** 노출한다 — ``household_key``·
    ``is_place_pending``·``is_promotable``·:func:`_place_view`·:func:`_dispatched_count`·
    ``summarize_snapshot`` 이 전부 속성 읽기뿐이라 그대로 통과한다(2026-08-24 확인).
    """

    __slots__ = ("id", "external_id", "external_order_no", "order_id", "sync_status",
                 "place_order_status", "relation", "group_key", "created_at",
                 "triage_state", "reviewed_at", "raw_snapshot")

    def __init__(self, id, external_id, external_order_no, order_id, sync_status,
                 place_order_status, relation, group_key, created_at, triage_state,
                 reviewed_at, raw_snapshot):
        self.id = id
        self.external_id = external_id
        self.external_order_no = external_order_no
        self.order_id = order_id
        self.sync_status = sync_status
        self.place_order_status = place_order_status
        self.relation = relation
        self.group_key = group_key
        self.created_at = created_at
        self.triage_state = triage_state
        # 두 모집단(확인 큐 / 발주확인 전)을 **한 번 읽고 파이썬에서 가르기** 위해 싣는다.
        self.reviewed_at = reviewed_at
        self.raw_snapshot = raw_snapshot


#: 얇은 경로가 싣는 컬럼. ``raw_snapshot`` 은 여기 없다 — 대신
#: :func:`_snapshot_projection` 이 만든 축소 문서가 마지막 자리에 붙는다.
_THIN_COLUMNS = (
    ExternalOrderLink.id,
    ExternalOrderLink.external_id,
    ExternalOrderLink.external_order_no,
    ExternalOrderLink.order_id,
    ExternalOrderLink.sync_status,
    ExternalOrderLink.place_order_status,
    ExternalOrderLink.relation,
    ExternalOrderLink.group_key,
    ExternalOrderLink.created_at,
    ExternalOrderLink.triage_state,
    ExternalOrderLink.reviewed_at,
)


#: 얇은 스냅샷이 **남기는** 최상위 키. 판정(:mod:`mapping`)이 읽는 것 전부다.
#:
#: 2026-08-28 (R-7): 여기에 `return`·`returnInfo`·`exchange`·`delivery` 가 **없었다.**
#: :func:`mapping._claim_blocks` 가 바로 그 이름들을 읽으므로, 입력을 얇게 한 것이 곧 술어를
#: 바꾼 것이었다 — `claimStatus` 가 top-level `return` 에만 실려 오는 반품에서 얇은 경로는
#: "클레임 없음", 두꺼운 경로는 "반품"으로 갈린다(배지 수 ≠ 목록. 이 저장소가 두 번 겪었다).
#: 목록은 :data:`mapping.CLAIM_BLOCK_KEYS`·:data:`mapping.RETURN_BLOCK_KEYS` 에서 만든다 —
#: 손으로 적으면 블록 이름이 늘 때 또 갈린다(계약 테스트가 이 파생을 잠근다).
#:
#: 2026-09-02: ``beforeClaim`` 추가. 커머스API 공지 #3608 이 **2026-10-28** 부터 구
#: 클레임 필드를 이 조회 API 응답에서 빼면서 대체 노드로 ``beforeClaim.exchange`` 를
#: 든다. :func:`mapping._claim_holders` 가 그 그릇을 읽게 됐으니 **얇은 경로도 같이**
#: 남겨야 한다 — 안 그러면 그날 이후 얇은 화면만 "클레임 없음"으로 갈린다(R-7 재발).
SNAPSHOT_PROJECTION_BLOCK_KEYS = tuple(dict.fromkeys(
    tuple(CLAIM_BLOCK_KEYS) + tuple(RETURN_BLOCK_KEYS)
    + ("currentClaim", "beforeClaim")))

#: 투영이 남기는 최상위 키 전체(블록 + 판정이 읽는 나머지).
#: ``delivery`` 는 :func:`mapping.extract_delivery` 가 읽고 `is_return_pending` 이 그것을 본다 —
#: 없으면 얇은 경로의 반품 대기 건수가 **항상 0** 이다.
SNAPSHOT_PROJECTION_KEYS = ("order", "productOrder", "delivery") + SNAPSHOT_PROJECTION_BLOCK_KEYS


def _snapshot_projection(db):
    """판정에 필요한 경로만 담은 **축소 스냅샷 문서**를 만드는 SQL 식.

    이 문서를 그대로 ``raw_snapshot`` 자리에 넣으면 뒤따르는 파이썬 코드가 **한 줄도
    갈라지지 않는다** — ``group_key``·``extract_claim``·``extract_place_status`` 가
    같은 함수로 같은 경로를 읽는다. 판정 함수를 두 벌로 만들면 계약 §2.4(뱃지 == 탭
    숫자 == 칩 '전체')가 깨진다. 이 저장소가 이미 두 번 겪은 결함이다(nav 67·탭 45 /
    nav 140·필터 43). 그래서 **술어가 아니라 입력만** 얇게 한다.

    ``COALESCE`` 는 ``unwrap_detail`` 의 **평평한 응답 폴백**(``detail["productOrder"]``
    가 dict 가 아니면 ``detail`` 자신을 쓴다)을 그대로 옮긴 것이다.

    싣지 않는 것은 전부 표시 전용이다 — 제품명·고객명·금액·옵션·주문일·발송기한.
    얇은 경로에서는 빈 값이 되고, 그 값들은 어떤 술어도 읽지 않는다.

    Args:
        db: 요청 스코프 DB 세션(방언 판정용).

    Returns:
        SQL 식. PostgreSQL 이 아니면 ``raw_snapshot`` 컬럼 그대로 — 결과는 같고 비용만
        옛날 값이다(SQLite 테스트 레인 보호).
    """
    from sqlalchemy import func

    bind = db.get_bind()
    if getattr(getattr(bind, "dialect", None), "name", "") != "postgresql":
        return ExternalOrderLink.raw_snapshot
    raw = ExternalOrderLink.raw_snapshot
    return func.jsonb_build_object(
        "order", func.jsonb_build_object(
            "orderId", raw["order"]["orderId"],
            "claimStatus", raw["order"]["claimStatus"],
            "placeOrderStatus", raw["order"]["placeOrderStatus"]),
        "productOrder", func.jsonb_build_object(
            "shippingAddress", func.coalesce(raw["productOrder"]["shippingAddress"],
                                             raw["shippingAddress"]),
            "claimStatus", func.coalesce(raw["productOrder"]["claimStatus"],
                                         raw["claimStatus"]),
            "claimType", func.coalesce(raw["productOrder"]["claimType"],
                                       raw["claimType"]),
            "placeOrderStatus", func.coalesce(raw["productOrder"]["placeOrderStatus"],
                                              raw["placeOrderStatus"])),
        # 발송 사실(`extract_delivery`)과 클레임 상세 블록. 이것을 빼면 얇은 경로만
        # 다른 답을 낸다 — 목록은 mapping 에서 파생해 손으로 적지 않는다(R-7).
        "delivery", raw["delivery"],
        *[arg for key in SNAPSHOT_PROJECTION_BLOCK_KEYS for arg in (key, raw[key])],
    )


def _fetch_links(db, *criteria, display: bool, order_by=None, limit=None):
    """링크 행을 읽는다 — ``display`` 가 문서의 두께만 정한다.

    술어·정렬·상한은 두 모드가 **같다**. 다른 것은 ``raw_snapshot`` 자리에 무엇이
    실리느냐뿐이다(:func:`_snapshot_projection`).

    Args:
        db: 요청 스코프 DB 세션.
        *criteria: WHERE 조건.
        display: True 면 ORM 인스턴스(스냅샷 통째), False 면 :class:`_ThinLink`.
        order_by: 정렬식 튜플(없으면 정렬 없음).
        limit: 조회 상한(없으면 없음).

    Returns:
        링크 행 목록.
    """
    if display:
        query = db.query(ExternalOrderLink).filter(*criteria)
    else:
        query = db.query(*_THIN_COLUMNS,
                         _snapshot_projection(db).label("raw_snapshot")).filter(*criteria)
    if order_by:
        query = query.order_by(*order_by)
    if limit is not None:
        query = query.limit(limit)
    rows = query.all()
    return rows if display else [_ThinLink(*row) for row in rows]


def _queue_links(db, *, display: bool = True) -> tuple[list[Any], bool]:
    """확인 대기 큐의 원천 링크 — 아직 사람이 보지 않은 수집분.

    큐에는 두 종류가 같이 온다: 아직 주문이 없는 수집분(``COLLECTED`` — 여기서 "주문
    만들기")과 주문은 생겼지만 사람이 아직 안 본 건(``LINKED`` + ``reviewed_at`` NULL).

    Args:
        db: 요청 스코프 DB 세션.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).

    Returns:
        ``(링크 목록(최신순), 조회 상한에 걸렸는지)``.
    """
    links = _fetch_links(
        db,
        ExternalOrderLink.channel == "NAVER",
        ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
        ExternalOrderLink.reviewed_at.is_(None),
        display=display,
        order_by=(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc()),
        limit=QUEUE_LINK_FETCH_LIMIT,
    )
    return links, len(links) == QUEUE_LINK_FETCH_LIMIT


def _orders_by_id(db, links: list[ExternalOrderLink]) -> dict[int, Order]:
    """링크가 가리키는 주문을 한 번에 당겨 ``{id: Order}`` 로 준다 (N+1 금지).

    Args:
        db: 요청 스코프 DB 세션.
        links: 주문 id 를 들고 있을 수 있는 링크 목록.

    Returns:
        ``{order_id: Order}`` — 주문이 붙은 링크가 없으면 빈 dict.
    """
    order_ids = [int(row.order_id) for row in links if row.order_id]
    if not order_ids:
        return {}
    return {order.id: order
            for order in db.query(Order).filter(Order.id.in_(order_ids)).all()}


def _link_by_id(db, link_id: int) -> Optional[ExternalOrderLink]:
    """수집 링크 1건을 채널까지 확인해 읽는다.

    Args:
        db: 요청 스코프 DB 세션.
        link_id: 링크 id.

    Returns:
        네이버 수집 링크(없으면 None).
    """
    return (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )


@admin_bp.route("/admin/naver-ingest/triage")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_triage():
    """수집 주문 트리아지 작업대 (스펙 §8.2).

    좌=확인 대기 큐, 우=네이버 원본 ↔ FOMS 현재 값 대조. **규격 입력은 여기서 하지 않는다** —
    ``spec_rows`` 는 폭(W)이 출고가·시공비와 결합돼 있어 두 번째 입력 UI 를 만들면 계산
    규칙이 갈라진다. 편집기가 규격 입력의 SSOT 로 남고 여기서는 링크만 건넨다.

    T14-A: 규격을 실제로 입력하는 사람이 CS 접수 담당이라 전 직원(STAFF 이상)에게
    개방한다. 수집 운영 화면(``naver_ingest_dashboard``)·"지금 수집"·raw 스냅샷은
    관리자 전용으로 남는다.
    """
    db = get_db()
    from foms.services.feature_flags import is_naver_workbench_enabled

    if is_naver_workbench_enabled(session.get("user_id")):
        return _render_workbench(db)

    # --- 아래는 게이트 OFF 경로(롤백 경로) — 예전 화면 그대로 둔다 ---
    pending, truncated = _queue_links(db)
    selected_id = request.args.get("link_id", type=int)
    selected = next((row for row in pending if row.id == selected_id), None)
    if selected is None and selected_id:
        # 확인 완료된 건은 큐에서 빠지지만 **대조 pane 은 열 수 있어야 한다** — 발주확인·
        # 발송처리 버튼이 거기 있고, 확인을 끝낸 뒤에 처리할 일도 있다(T16-H).
        selected = _link_by_id(db, selected_id)
    if selected is None and pending:
        selected = pending[0]

    queue = _group_queue(pending, _orders_by_id(db, pending), truncated=truncated)
    selected_group = next(
        (group for group in queue if selected is not None and selected.id in group["link_ids"]),
        None,
    )
    return render_template(
        "admin/naver_triage.html",
        queue=queue,
        pending_count=sum(len(group["link_ids"]) for group in queue),
        group_count=len(queue),
        selected=_triage_pane(db, selected) if selected is not None else None,
        selected_group=selected_group,
        sales_users=_active_sales_users(db),
    )


def _ghost_view(db) -> dict[str, Any]:
    """유령 주문 띠 데이터 (R-2 · 2026-08-25).

    네이버 결제가 **전부 취소**됐는데 살아 있는 ERP 주문이다. 지금까지 이 사실을 말하는
    화면이 하나도 없어서 스테이징에 3건이 아무에게도 안 보인 채 남아 있었다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``{"count": n, "rows": [...]}``. 조회가 실패해도 화면을 죽이지 않는다 —
        띠는 보조 정보고, 이게 목록을 막으면 본업이 멈춘다.
    """
    from foms.services.integrations.naver_commerce.ghost_orders import (
        attach_repay_candidates,
        find_ghost_orders,
    )

    try:
        ghosts = find_ghost_orders(db)
        attach_repay_candidates(db, ghosts)
        return ghosts
    except SQLAlchemyError as exc:  # 보조 정보라 흐름을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 유령 주문 조회 실패(띠 생략): %s", exc, exc_info=True)
        return {"count": 0, "rows": []}


def _origin_cleanup_view(db) -> dict[str, Any]:
    """재결제 뒤 **정리 안 된 옛 네이버 주문** 띠 데이터 (NVREPAY-02).

    관계 블록(:func:`_origin_view`)은 그 주문 pane 을 연 사람에게만 말한다. 그런데 옛
    주문을 취소·반품하지 않으면 고객 돈이 두 번 묶이고 옛 주문은 네이버에서 그대로 돈다.
    **아무도 pane 을 안 열면 아무도 모른다** — 그 수를 목록 화면이 늘 말하게 하는 자리다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``{"count", "rows", "truncated"}``. 유령 띠와 같은 규율로 **실패해도 화면을
        죽이지 않는다**(failopen — 로그로 남긴다). 이게 목록을 막으면 본업이 멈춘다.
    """
    from foms.services.integrations.naver_commerce.order_candidates import (
        pending_origin_cleanup,
    )

    try:
        return pending_origin_cleanup(db)
    except SQLAlchemyError as exc:  # 보조 정보라 흐름을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 옛 주문 정리 대기 조회 실패(띠 생략): %s", exc, exc_info=True)
        return {"count": 0, "rows": [], "truncated": False}


def _bulk_dispatch_view(db) -> dict[str, Any]:
    """**오늘 실측한 네이버 건** 띠가 말할 값 (NAVER-BULKDISPATCH-01 T2) — 읽기 전용.

    아직 버튼이 없다. 이 띠의 일은 "5시에 무엇이 나갈 것인가"를 **미리 보여주는 것**이다.

    조립은 :func:`bulk_dispatch.build_preview` 가 한다 — 실측 대시보드의 같은 띠와 **한
    함수를 공유**한다. 화면마다 따로 세면 두 화면이 다른 수를 말한다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``{"date", "count", "eligible", "blocked", "rows"}``.
    """
    from foms.services.datetime_kst import get_today_kst
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    # 워크벤치는 언제나 오늘만 본다 — 실행 버튼이 열려도 되는 날이라는 뜻이다.
    return {**build_preview(db, on_date=get_today_kst().strftime("%Y-%m-%d")),
            "is_today": True}


def _refresh_all_view(db) -> dict[str, Any]:
    """**전체 다시 읽기** 버튼이 말할 집 수 (NVREPAY-03).

    ADMIN 화면 조작이라 여기서만 센다 — STAFF·MANAGER 에게는 버튼 자체가 없다
    (수집 운영 조작은 '지금 수집'과 같은 기준).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``{"count": 대상 집 수, "skipped_done": 종결로 뺀 집, "skipped_recent":
        쿨다운으로 뺀 집, "eta": 걸릴 시간 한 마디}``. ``count`` 는 **제외를 거친 뒤**의
        수라 버튼이 그대로 쓴다 — "전체"라 적고 덜 읽으면 그게 조용한 절단이다.
        ``eta`` 는 툴팁·모달·라벨이 **같은 값**을 말하도록 서버에서 한 번만 만든다
        (NVREPAY-05 T2 — 세 자리가 따로 계산하면 같은 화면이 세 말을 한다).
        실패해도 화면을 죽이지 않는다(버튼만 빠진다).
    """
    from foms.services.integrations.naver_commerce.claim_watch import (
        refresh_all_eta_text,
        refreshable_household_link_ids,
    )

    try:
        _link_ids, total, skipped = refreshable_household_link_ids(db)
        return {"count": int(total),
                "skipped_done": int(skipped.get("done", 0)),
                "skipped_recent": int(skipped.get("recent", 0)),
                "eta": refresh_all_eta_text(int(total))}
    except SQLAlchemyError as exc:  # 보조 정보라 흐름을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 전체 다시 읽기 대상 조회 실패(버튼 생략): %s", exc, exc_info=True)
        return {"count": 0, "skipped_done": 0, "skipped_recent": 0, "eta": ""}


def _refresh_running_view(db) -> dict[str, Any]:
    """지금 **누가** 전체 다시 읽기를 돌리고 있나 (NVREPAY-05 T1).

    진행 표시가 누른 브라우저 안에만 있어서, 다른 관리자에게는 돌고 있는 중에도
    `다시 읽기 45주문` 으로 보였다 — 그래서 또 누른다. 감사 원장의 최근 요청과 워커
    스탬프만으로 세므로 새 저장소가 없다(:func:`claim_watch.running_refresh_all`).

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        돌고 있으면 ``{"running": True, "actor", "total", "done", "pending", "eta",
        "elapsed_seconds", "started_at"}``, 아니면 ``{"running": False}``. 실패해도
        화면을 죽이지 않는다(띠만 빠지고 버튼은 평소대로 보인다).
    """
    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    try:
        running = running_refresh_all(db)
    except SQLAlchemyError as exc:  # 보조 정보라 흐름을 막지 않는다(failopen — 로그로 남긴다)
        logger.warning("[NAVER] 전체 다시 읽기 진행 조회 실패(띠 생략): %s", exc, exc_info=True)
        return {"running": False}
    return {"running": True, **running} if running else {"running": False}


def _selected_offlist(link: Optional[ExternalOrderLink],
                      household: Optional[dict[str, Any]],
                      visible: Optional[list[dict[str, Any]]]) -> bool:
    """지금 상세에 연 집이 **왼쪽 목록에 없는** 집인가 (리뷰 M-3).

    ``?link_id=`` 는 목록 밖 집도 완전무장 상태로 연다 — 이력 탭의 `워크벤치` 링크가
    실제로 그 경로다(막으면 안 된다: 이력에서 찾은 집을 처리하러 가는 유일한 길이다).
    다만 화면이 그 사실을 말하지 않으면, 왼쪽에 없는 집에 불가역 버튼 4종이 열려 있는
    상태가 된다 — 사람은 "방금 누른 그 집" 을 목록에서 찾다가 다른 집을 누른다.

    판정은 **실제 목록 멤버십**으로 한다. 모집단 술어를 여기서 다시 구현하면
    (:func:`_work_groups` 의 원천 1·2 조건) 판정이 두 벌이 되어 조용히 갈린다 —
    v3 리뷰 H1 이 정확히 그 갈라짐에서 나왔다.

    Args:
        link: 상세에 띄운 링크(없으면 판정 불가 → False).
        household: 그 링크가 속한 집(:func:`_group_of_link` 결과).
        visible: 지금 화면에 그린 집 목록. ``None`` 이면 목록을 모르는 호출(pane
            프래그먼트)이라 판정하지 않는다 — 그 경로는 목록의 행을 눌러야 도달하므로
            **정의상 목록 안**이다.

    Returns:
        목록 밖 집이면 True.
    """
    if link is None or visible is None or household is None:
        return False
    # **집 단위**로 본다. 링크 id 로 비교하면 큐 모집단(COLLECTED|LINKED +
    # reviewed_at NULL)에 없는 형제(예: 매핑 실패로 PENDING_REVIEW 인 옵션 건)를 열었을 때
    # 그 집이 왼쪽에 멀쩡히 그려져 있는데도 "목록에 없는 집"이라고 말한다 — 왼쪽 행은
    # 심지어 aria-current 로 하이라이트까지 된다(2026-08-23 CEO 검수 높음-2).
    # 그러면 경고를 아무도 안 믿게 되고, 진짜 목록 밖 집에서 같은 문구가 흘러간다.
    house = set(household.get("link_ids") or [])
    return not any(house & set(group["link_ids"]) for group in visible)


def _origin_view(db, link: Optional[ExternalOrderLink],
                 household: Optional[dict[str, Any]]) -> dict[str, Any]:
    """붙어 있는 주문의 **옛 네이버 주문** 사실 — 관계 블록이 쓴다 (2026-08-28 NVREPAY-01).

    재결제로 붙인 뒤 담당자가 해야 할 다음 일은 **옛 주문을 네이버에서 취소(발송 전) 또는
    반품(발송 후)** 하는 것이다. 그런데 지금까지 화면은 붙이는 순간 옛 결제 정보를 통째로
    감췄다 — 그 정보가 `아직 안 붙은 집` 갈래에만 있었기 때문이다. 담당자는 판매자센터를
    따로 열어 주문번호로 찾아 들어가고 있었다.

    링크가 0건일 때 화면이 **"없습니다"라고 단정하지 않는** 이유는
    :func:`order_candidates.origin_facts` 의 docstring 과 설계서 §4.1 에 있다 — 수집이
    ``PAYED`` 만 가져오므로 첫 스윕 전에 이미 처리가 끝난 주문은 영영 안 들어오고,
    그 관측이 "정말 없음"과 똑같다.

    Args:
        db: 요청 스코프 DB 세션.
        link: pane 에 띄운 링크.
        household: 그 링크가 속한 집(:func:`_group_of_link` 결과).

    Returns:
        ``{link_count, claim_code, claim_label, alive_rows, stale_any, sweep}``.
        붙은 주문이 없으면 빈 값 — 템플릿은 관계 블록에서만 이걸 읽는다.
    """
    from foms.services.integrations.naver_commerce.order_candidates import origin_facts

    empty = {"link_count": 0, "claim_code": "", "claim_label": "",
             "alive_rows": [], "stale_any": False, "sweep": {}}
    if link is None or not link.order_id:
        return empty
    exclude = set(int(i) for i in ((household or {}).get("link_ids") or []))
    exclude.add(int(link.id))
    facts = origin_facts(db, link.order_id, exclude_link_ids=exclude,
                         since_at=link.created_at)
    for row in facts["alive_rows"]:
        row["read_at_text"] = _dispatch_time_text(row.get("read_at"))
        # 옛 집 pane 주소. 새 라우트가 아니라 **같은 트리아지 화면**이다 — 확인 큐에서
        # 빠진 집도 link_id 주소로 열리고(:func:`_selected_link`), pane 이 "목록에 없는
        # 집"이라고 말하되 버튼을 막지 않는다(:func:`_selected_offlist`). 그래서 옛 주문의
        # 취소·반품은 **그 집 자신의 화면에서** 기존 모달·기존 가드로 나간다.
        row["pane_url"] = url_for("admin.naver_ingest_triage", link_id=row["link_id"])
    # 링크가 0건일 때만 수집 상태를 곁들인다 — "안 보이는 이유"를 말할 수 있는 유일한 자리다.
    # 있는 건에 붙이면 화면만 시끄러워진다.
    sweep: dict[str, Any] = {}
    if not facts["link_count"]:
        from foms.services.integrations.naver_commerce.watermark import read_state

        try:
            state = read_state(db) or {}
            sweep = {"last_error": str(state.get("last_error") or "")[:200],
                     "last_run_at": _dispatch_time_text(state.get("last_run_at"))}
        except (ValueError, TypeError, AttributeError) as exc:  # 보조 정보라 흐름을 막지 않는다
            logger.warning("[NAVER] 수집 상태 조회 실패: %s", exc)
    facts["sweep"] = sweep
    return facts


def _pane_context(db, link: Optional[ExternalOrderLink],
                  *, visible: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    """상세 pane 컨텍스트 — 전체 렌더와 프래그먼트 응답이 **이 함수 하나**를 쓴다.

    계산 경로가 두 벌이 되면 모집단이 갈라진다. pane 의 집은 큐가 아니라
    :func:`_group_of_link`(주문번호 + 집 키 전체)로 만든다 — 큐 모집단은
    ``COLLECTED|LINKED`` + ``reviewed_at IS NULL`` 로 좁혀져 있는데 워커는 집 전체를
    처리한다. 그 차이가 모달 문장에 나오면 "상품주문 1건을 취소합니다"라고 읽고 2건이
    환불된다(2026-08-23 리뷰 F5/H).

    Args:
        db: 요청 스코프 DB 세션.
        link: pane 에 띄울 링크(None 이면 빈 pane).
        visible: 지금 화면에 그린 집 목록(전체 렌더만 넘긴다). 목록 밖 집을 열었을 때
            pane 이 그 사실을 말하게 하는 데만 쓴다(:func:`_selected_offlist`).

    Returns:
        ``selected``·``selected_group``·``selected_household_claimed``·``member_rows``·
        ``cancel_reasons``·``return_reasons``·``selected_offlist``.
    """
    from foms.services.feature_flags import (
        is_naver_cancel_approve_enabled,
        is_naver_return_approve_enabled,
        is_naver_return_reject_enabled,
    )
    from foms.services.integrations.naver_commerce.fulfillment import (
        CANCEL_REASONS,
        RETURN_REASONS,
        RETURN_REJECT_REASON_MAX,
    )
    from foms.services.integrations.naver_commerce.reject_templates import (
        load_templates as load_reject_templates,
        templates_version as reject_templates_version,
    )

    household = _group_of_link(db, link) if link is not None else None
    member_rows = _member_rows(db, household)
    return {
        "selected": _triage_pane(db, link) if link is not None else None,
        "selected_group": household,
        # 클레임 판정 모집단도 **형제 전부**다. 확인 완료돼 큐에서 빠진 형제의 취소를 큐
        # 묶음은 못 보는데, 발송처리는 되돌릴 수 없어 그 구멍이 그대로 사고가 된다.
        "selected_household_claimed": _household_has_claim(db, link),
        "member_rows": member_rows,
        # 집 단위 쿠폰 한 줄(2026-08-25) — 행 합계를 사람이 암산하지 않게 한다.
        "coupon_summary": _coupon_summary(member_rows),
        # 취소 사유는 네이버 코드가 SSOT 다 — 화면이 따로 목록을 들면 둘이 갈린다.
        "cancel_reasons": CANCEL_REASONS,
        # 반품 사유는 **취소와 다른 목록**이다(T8-S1). 화이트리스트 밖 코드는 라우트가
        # 튕기고 서비스가 한 번 더 본다 — 화면 select 를 믿지 않는다.
        "return_reasons": RETURN_REASONS,
        # 목록 밖 집을 열었는지(리뷰 M-3). 버튼을 막지 않는다 — 사실만 말한다.
        "selected_offlist": _selected_offlist(link, household, visible),
        # 붙어 있는 주문의 **옛 네이버 주문** — 재결제 뒤 정리 대상(NVREPAY-01).
        "selected_origin": _origin_view(db, link, household),
        # 반품 거부(T8-S3) 게이트. **꺼져 있으면 버튼 자체를 안 낸다** — 규격이 아직
        # 안 채워져서(설계서 §2) 눌러도 나가지 않는다. 라우트도 같은 게이트로 닫혀 있다:
        # 한쪽만 열면 열린 버튼이 403 을 받는다.
        "return_reject_enabled": is_naver_return_reject_enabled(),
        # 승인 게이트 2종(T9). **따로 판다** — 진짜 클레임 1건에서 취소 승인을 먼저 켜
        # 성공을 확인한 뒤 반품 승인을 켠다. 하나로 묶으면 첫 실호출이 두 배선의 동시
        # 검증이 되어, 실패했을 때 어느 쪽이 틀렸는지 안 갈린다.
        "cancel_approve_enabled": is_naver_cancel_approve_enabled(),
        "return_approve_enabled": is_naver_return_approve_enabled(),
        # 승인은 ADMIN·MANAGER 만(사용자 결정 2026-09-01). 라우트도 같은 조건이다 —
        # 한쪽만 좁히면 열린 버튼이 403 을 받는다.
        "claim_approve_can_act": (session.get("role") or "") in ("ADMIN", "MANAGER"),
        # 자주 쓰는 거부 문장(채워 넣기 전용)과 우리 글자수 상한. 화면이 목록을 따로 들면
        # 서버 상한과 갈린다 — 잘려 나간 문장이 그대로 구매자에게 간다.
        # 목록은 **DB 가 정본**이다(전역 공유). 저장된 적이 없으면 코드 기본 5종이 온다.
        "return_reject_fills": load_reject_templates(db),
        "return_reject_templates_version": reject_templates_version(db),
        # 문장을 고치는 것은 ADMIN 만(거부 실행은 MANAGER 까지). 라우트도 같은 조건이다.
        "return_reject_can_manage": (session.get("role") or "") == "ADMIN",
        "return_reject_reason_max": RETURN_REJECT_REASON_MAX,
        # sales_users 는 워크벤치 두 템플릿 어디서도 안 쓴다 — 넣어 두면
        # pane 조각 요청마다 User 전 행 조회가 1회씩 헛돈다(리뷰 M-5).
        # 게이트 OFF 경로(naver_triage.html)는 자기 자리에서 따로 부른다.
    }


def _selected_link(db, visible: list[dict[str, Any]]) -> Optional[ExternalOrderLink]:
    """pane 에 띄울 링크 — 주소가 지정한 것 우선, 없으면 보이는 목록의 첫 집.

    기본 선택은 **지금 보이는 목록 안에서** 고른다. 전체에서 고르면 필터를 걸었는데
    목록에 없는 집이 오른쪽에 펼쳐진다(목록엔 없는데 상세만 뜬다).

    Args:
        db: 요청 스코프 DB 세션.
        visible: 현재 필터로 걸러진 집 목록.

    Returns:
        링크(목록이 비고 지정도 없으면 None).
    """
    link_id = request.args.get("link_id", type=int)
    if link_id:
        link = _link_by_id(db, link_id)
        if link is not None:
            return link
    return db.get(ExternalOrderLink, int(visible[0]["id"])) if visible else None


def _render_workbench(db) -> str:
    """워크벤치(게이트 ON) 렌더 — 목록 하나 + 필터 칩 + 상세 pane.

    탭은 처리/이력 둘뿐이다. 예전 ``발주확인 전``·``취소·반품`` 탭은 같은 목록의 필터
    칩으로 내려왔다 — 한 집을 처리하려고 탭을 오가던 것이 이 개편의 출발점이다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        렌더된 HTML.
    """
    from foms.services.feature_flags import is_naver_bulk_dispatch_enabled

    active_tab = _active_tab()
    active_filter = _active_filter()
    active_sort = _active_sort()
    groups, work_truncated = _work_groups(db, sort=active_sort)
    visible = [group for group in groups if _group_matches_filter(group, active_filter)]
    # 수집 상태(워터마크·인증 만료일)는 이력 탭에 함께 싣는다. 게이트가 켜지면 옛 수집
    # 화면이 리다이렉트로 닫히는데, 그 화면에만 있던 값이라 여기 없으면 수집이 조용히
    # 멈춰도 아무도 모른다. ADMIN 전용은 그대로다.
    ingest_status = ({"watermark": _watermark_view(db), "expiry": _expiry_view(db)}
                     if active_tab == "all" and _can_view_history() else {})
    return render_template(
        "admin/naver_workbench.html",
        active_tab=active_tab,
        active_filter=active_filter,
        active_sort=active_sort,
        work_groups=visible,
        # 칩 숫자·스트립·탭 배지는 **필터 전 전체**에서 센다(칩을 눌러도 총량은 안 변한다).
        filter_counts=_filter_counts(groups),
        group_count=len(groups),
        # 스트립·탭 배지·nav 뱃지가 말하는 수 — 손댈 수 있는 집만(계약 §2.4).
        # 잠긴 집은 목록에는 남고 `locked_count` 로 따로 고지된다.
        actionable_count=_actionable_count(groups),
        locked_count=len(groups) - _actionable_count(groups),
        pending_count=sum(int(group["count"]) for group in groups),
        work_truncated=work_truncated,
        can_view_history=_can_view_history(),
        history=_history_view(db) if active_tab == "all" else {},
        ingest_status=ingest_status,
        # 소급 수집 날짜 칸의 기본값. 기본 범위는 90일(사용자 결정 2026-09-01)이고
        # 끝은 **어제**다 — 오늘 구간은 정상 5분 스윕이 이미 맡고 있다.
        backfill_defaults=_backfill_defaults(),
        # 실패는 어느 탭에 있든 보여야 한다 — 탭을 옮겼다고 사고가 사라지지 않는다.
        failures=_failure_rows(db),
        # 유령 주문(R-2): 네이버 결제가 전부 취소됐는데 살아 있는 ERP 주문.
        # 처리 탭에서만 낸다 — 이력 탭은 지난 기록을 보는 자리라 할 일을 띄우지 않는다.
        ghosts=_ghost_view(db) if active_tab == "work" else {"count": 0, "rows": []},
        # 재결제 뒤 정리 안 된 옛 네이버 주문(NVREPAY-02). 유령 띠와 같은 자리·같은 규율 —
        # 처리 탭에서만 낸다(이력 탭은 할 일을 띄우는 자리가 아니다).
        origin_cleanup=(_origin_cleanup_view(db) if active_tab == "work"
                        else {"count": 0, "rows": [], "truncated": False}),
        # 오늘 실측한 네이버 건(NAVER-BULKDISPATCH-01 T2). 처리 탭에서만 센다 — 이력 탭은
        # 지난 일을 보는 자리라 '오늘 5시에 나갈 것'이 낄 자리가 아니다.
        bulk_dispatch=(_bulk_dispatch_view(db) if active_tab == "work"
                       else {"date": "", "count": 0, "eligible": 0,
                             "blocked": 0, "rows": []}),
        # 전역 킬스위치. 코호트가 아니다 — 코호트를 쓰면 그 밖의 실측 담당자에게 실행
        # 라우트가 403 이 되어 진입점 두 곳 중 하나가 조용히 죽는다.
        naver_bulk_dispatch_enabled=is_naver_bulk_dispatch_enabled(),
        # 전체 다시 읽기(NVREPAY-03) — 탭과 무관한 수집 전체 조작이라 두 탭 모두에서 낸다.
        # ADMIN 이 아니면 세지도 않는다(버튼이 없으므로 쿼리도 필요 없다).
        refresh_all=(_refresh_all_view(db) if _can_view_history() else {"count": 0}),
        # 남이 눌러 놓은 다시 읽기(NVREPAY-05 T1) — 돌고 있으면 버튼 대신 진행을 그린다.
        # 버튼과 같은 자리·같은 권한이라 같은 조건에서만 센다.
        refresh_running=(_refresh_running_view(db) if _can_view_history()
                         else {"running": False}),
        **_pane_context(db, _selected_link(db, visible), visible=visible),
    )


@admin_bp.route("/admin/naver-ingest/triage/pane")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_triage_pane() -> str:
    """상세 pane 조각만 돌려준다 — 행을 눌러도 페이지를 통째로 다시 받지 않게.

    읽기 전용 GET 이다(mutation 이 아니라 write manifest 등재도 감사 라벨도 없다).
    컨텍스트는 전체 렌더와 **같은** :func:`_pane_context` 로 만든다 — 계산 경로를 두 벌로
    두면 모달이 재진술하는 건수와 서버가 처리할 건수가 갈린다.

    Query:
        ``link_id``: 열 링크 id(필수).

    Returns:
        pane 조각 HTML(레이아웃 없음). 게이트 OFF 는 404(그 화면에는 이 경로가 없다),
        ``link_id`` 누락은 400, 없는 링크는 404.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled

    if not is_naver_workbench_enabled(session.get("user_id")):
        abort(404)
    link_id = request.args.get("link_id", type=int)
    if not link_id:
        abort(400)
    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        abort(404)
    return render_template("admin/partials/naver_workbench_pane.html",
                           **_pane_context(db, link))


@admin_bp.route("/admin/naver-ingest/triage/detail")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_triage_detail() -> str:
    """이력 행의 **읽기 전용 상세** 조각 — 큐에서 빠진 집도 그 자리에서 볼 수 있게.

    큐에서 빠진(주문이 생긴) 집은 처리 목록에 없어서, 지금까지 네이버 원본을 보려면
    ERP 주문 편집 화면을 새 탭으로 열어야 했다. 그런데 거기에는 **원본이 없다** —
    옵션 원문·수취인·배송메모·클레임 사유·발송 결과는 수집 스냅샷에만 있다.

    **버튼을 하나도 두지 않는다**(이력 표의 절대 규칙 3). 이력에서 되돌릴 수 없는 호출
    (발주확인·발송처리·취소)이 나갈 수 있으면, 이미 끝난 집을 다시 건드리는 사고가
    난다. 그래서 pane 을 재사용하지 않고 **읽기 전용 템플릿**을 따로 둔다 —
    pane 을 그대로 띄우면 버튼이 따라오고, 문서에 pane 의 id 가 두 벌 생겨
    "5번째 행의 취소가 1번째 집으로 나가는" 절대 규칙 1 위반이 된다.

    데이터는 pane 과 **같은 함수**(:func:`_triage_pane`·:func:`_member_rows`)로 만든다.
    같은 집을 두 화면이 다르게 말하면 안 된다. 다만 후보 탐색은 끄고 부른다(붙이기가
    없으므로 그릴 값이 아니다).

    읽기 전용 GET 이다 — mutation 이 아니라 write manifest 등재도 감사 라벨도 없다.

    Query:
        ``link_id``: 열 링크 id(필수).

    Returns:
        상세 조각 HTML(레이아웃 없음). 게이트 OFF 는 404(그 화면에는 이 경로가 없다),
        ``link_id`` 누락은 400, 없는 링크는 404.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled

    if not is_naver_workbench_enabled(session.get("user_id")):
        abort(404)
    link_id = request.args.get("link_id", type=int)
    if not link_id:
        abort(400)
    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        abort(404)
    household = _group_of_link(db, link)
    member_rows = _member_rows(db, household)
    return render_template(
        "admin/partials/naver_workbench_detail.html",
        detail=_triage_pane(db, link, with_candidates=False),
        member_rows=member_rows,
        coupon_summary=_coupon_summary(member_rows),
    )


@admin_bp.route("/admin/naver-ingest/triage/fulfillment-state")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_fulfillment_state():
    """집의 워커 처리 표식만 돌려준다 — 화면이 "언제 뒤집혔는지" 물어보는 자리.

    불가역 3종(발주확인·발송처리·취소)은 큐에 들어가고 web 은 바로 답한다. 화면이 그
    직후에 갱신하면 아직 옛 상태다 — 사용자에게는 "눌러도 아무 일이 없다"로 보인다.
    화면은 이 경로를 짧게 폴링해 표식이 뒤집히면 그때 다시 그린다.

    읽기 전용 GET 이다(mutation 이 아니라 write manifest 등재도 감사 라벨도 없다).
    **판정은 하지 않는다** — 무엇을 눌러도 되는지는 pane 이 혼자 정한다
    (:func:`_fulfillment_state` docstring 참조).

    Query:
        ``link_id``: 기준 링크 id(필수). 이 링크가 속한 **집 전체**를 센다.

    Returns:
        ``{"success": True, "data": _fulfillment_state(...)}``. 게이트 OFF 는 404
        (그 화면에는 이 경로가 없다), ``link_id`` 누락은 400, 없는 링크는 404.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled

    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 쓸 수 없습니다."}), 404
    link_id = request.args.get("link_id", type=int)
    if not link_id:
        return jsonify({"success": False, "data": None,
                        "error": "link_id 가 필요합니다."}), 400
    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        return jsonify({"success": False, "data": None,
                        "error": "수집분을 찾을 수 없습니다."}), 404
    return jsonify({"success": True, "data": _fulfillment_state(db, link), "error": None})


@admin_bp.route("/admin/naver-ingest/triage/fulfillment-progress")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_fulfillment_progress():
    """벌크로 보낸 집들의 발주확인 진행 상황 — **조회 2회**(집 수와 무관).

    벌크는 집마다 폴링하지 않는다. 33집을 집마다 물으면 폴링 한 회차에 조회가 66번
    나가는데, 이 화면의 조회 비용은 이미 nav 뱃지 실측에서 드러났다(콜드 113ms).

    읽기 전용 GET 이다(mutation 아님). **판정은 하지 않는다** — 남은 건수 술어만
    서버 SSOT(`is_place_pending`)를 그대로 쓴다.

    Query:
        ``link_ids``: 쉼표로 이은 대표 링크 id(필수, 최대
        :data:`PROGRESS_LINK_ID_LIMIT` 개까지 본다).

    Returns:
        ``{"success": True, "data": _fulfillment_progress(...)}``. 게이트 OFF 는 404,
        ``link_ids`` 누락·형식 오류는 400.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled

    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 쓸 수 없습니다."}), 404
    raw = (request.args.get("link_ids") or "").strip()
    ids: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if chunk.isdigit():
            ids.append(int(chunk))
    if not ids:
        return jsonify({"success": False, "data": None,
                        "error": "link_ids 가 필요합니다."}), 400
    db = get_db()
    return jsonify({"success": True,
                    "data": _fulfillment_progress(db, ids[:PROGRESS_LINK_ID_LIMIT]),
                    "error": None})


#: 불가역 작업의 한글 라벨. 실패 띠와 폴링 응답이 **같은 표**를 쓴다 — 두 벌이면
#: 같은 실패가 화면 자리마다 다른 이름으로 불린다.
#:
#: **미등재 action 은 조용히 "발주확인"으로 읽힌다**(:func:`_fulfillment_state` 의 폴백).
#: T8-S3 의 ``return-reject`` 가 그 구멍에 빠져 있었고, T9 에서 승인 2종과 함께 등재했다.
#: 폴백 자체를 빈 문자열로 바꾸는 것은 화면 문구 회귀 범위가 넓어 별건으로 남긴다.
FULFILLMENT_ACTION_LABELS = {"confirm": "발주확인", "dispatch": "발송처리", "cancel": "취소",
                             "return": "반품 접수", "return-reject": "반품 거부",
                             "cancel-approve": "취소 승인", "return-approve": "반품 승인"}

#: 통합 화면의 탭 — 두 URL 왕복을 없앤 자리(설계 결정 1). v3 에서 ``place``·``claim`` 은
#: 탭이 아니라 **같은 목록의 필터 칩**으로 내려왔다(한 집 처리하려고 탭을 오가던 통증).
WORKBENCH_TABS = ("work", "all")

#: 처리 탭의 필터 칩. 술어 SSOT 는 :func:`_group_matches_filter` 하나뿐이다.
WORKBENCH_FILTERS = ("all", "place", "rel", "claim")

#: 없어진 탭 → 필터 이름. 옛 주소·북마크가 가리키던 목록을 그대로 보여준다.
LEGACY_TAB_FILTERS = {"place": "place", "claim": "claim"}


def _can_view_history() -> bool:
    """전체 이력 탭을 볼 수 있는가 — 기준은 수집 관리 화면과 **같다**(ADMIN 전용).

    트리아지는 규격을 입력하는 CS 담당(STAFF 이상)에게 열려 있지만, 수집 이력·상태
    집계·실패 사유는 ``naver_ingest_dashboard`` 가 ADMIN 으로 묶어 둔 자료다. 같은 자료를
    STAFF 도 여는 라우트 안에서 다시 내면 **회귀가 아니라 신규 노출**이 된다.

    Returns:
        현재 사용자가 ADMIN 이면 True.
    """
    user = getattr(g, "current_user", None)
    return bool(user) and str(getattr(user, "role", "") or "").upper() == "ADMIN"


def _active_tab() -> str:
    """``?tab=`` 을 읽어 유효한 탭 이름으로 정규화한다.

    없어진 탭(``place``·``claim``)은 처리 탭으로 흡수한다 — 열린 탭·북마크가 빈 화면으로
    떨어지지 않게. 그 주소가 뜻하던 갈래는 :func:`_active_filter` 가 같은 인자에서 다시
    읽어 필터로 되살린다.

    모르는 값은 조용히 기본 탭으로 떨어뜨린다 — 주소를 손으로 고쳐도 화면이 죽지 않는다.
    볼 권한이 없는 탭도 같은 자리로 떨어진다(403 대신 기본 탭 — 나머지 작업은 계속 된다).

    Returns:
        ``work`` 또는 ``all``.
    """
    raw = (request.args.get("tab") or "").strip().lower()
    tab = raw if raw in WORKBENCH_TABS else "work"
    if tab == "all" and not _can_view_history():
        return "work"
    return tab


def _active_filter() -> str:
    """``?f=`` 를 읽어 유효한 필터 이름으로 정규화한다.

    옛 주소(``?tab=place``·``?tab=claim``)는 탭이 사라졌어도 **그 뜻대로** 필터를 정한다.
    모르는 값은 조용히 ``all`` 로 떨어뜨린다(주소를 손으로 고쳐도 목록이 비지 않는다).

    Returns:
        :data:`WORKBENCH_FILTERS` 중 하나.
    """
    legacy = (request.args.get("tab") or "").strip().lower()
    if legacy in LEGACY_TAB_FILTERS:
        return LEGACY_TAB_FILTERS[legacy]
    raw = (request.args.get("f") or "").strip().lower()
    return raw if raw in WORKBENCH_FILTERS else "all"


def _group_matches_filter(group: dict[str, Any], name: str) -> bool:
    """집 하나가 필터 칩 조건에 맞는가 (계약 §2.2 술어 — 화면·숫자가 함께 쓰는 SSOT).

    Args:
        group: :func:`_work_groups` 가 만든 집.
        name: 필터 이름(:data:`WORKBENCH_FILTERS`).

    Returns:
        그 칩 목록에 보여야 하면 True. 모르는 이름은 ``all`` 로 본다.
    """
    if name == "place":
        return (bool(group.get("place_pending"))
                and not group.get("claim_blocking") and not group.get("canceled"))
    if name == "rel":
        return str(group.get("relation") or "").upper() in ("ADDON", "REPAY")
    if name == "claim":
        return bool(group.get("claim_blocking")) or bool(group.get("canceled"))
    return True


def _attach_row_flags(groups: list[dict[str, Any]]) -> None:
    """행 잠금·벌크 선택 가능 여부를 **서버가 한 번만** 판정해 집에 싣는다.

    이 판정이 서버(:func:`_group_matches_filter`)·목록 템플릿·pane 템플릿 세 곳에
    각각 구현돼 있었다. 그래서 한 곳만 고치면 나머지가 조용히 어긋난다 —
    2026-08-23 의 H1(잠겨야 할 집에 체크박스가 열려 벌크 발주확인 대상이 됐다)이
    정확히 그 갈라짐에서 나왔다. 술어를 한 벌로 만들고 화면은 값을 읽기만 한다.

    Args:
        groups: :func:`_work_groups` 가 만든 집 목록. 제자리에서 두 키를 채운다.
    """
    for group in groups:
        # `claim` 칩과 같은 술어여야 한다 — 잠긴 줄과 취소·반품 칩의 모집단은 하나다.
        group["locked"] = _group_matches_filter(group, "claim")
        # `place` 칩과 같은 술어. 발주확인 대상이 아닌 집은 애초에 고를 수 없다.
        group["can_pick"] = _group_matches_filter(group, "place")


#: 목록 정렬 닫힌집합. 임의 문자열이 정렬식으로 들어가지 않게 한다.
#: ``new`` = 접수 최신순(기본, v3 부터의 순서) · ``due`` = 발송기한 임박순.
WORKBENCH_SORTS = ("new", "due")

#: 발송기한이 없는 집을 임박순 정렬에서 **맨 뒤로** 보내는 자리표시 날짜.
#: 빈 문자열로 정렬하면 기한 없는 집이 제일 급한 것처럼 맨 앞에 온다.
_NO_DUE = "9999-12-31"


def _active_sort() -> str:
    """``?s=`` 를 읽어 유효한 정렬 이름으로 정규화한다.

    Returns:
        :data:`WORKBENCH_SORTS` 중 하나. 모르는 값은 조용히 ``new`` 로 떨어뜨린다
        (주소를 손으로 고쳐도 목록이 비지 않는다 — :func:`_active_filter` 와 같은 규칙).
    """
    raw = (request.args.get("s") or "").strip().lower()
    return raw if raw in WORKBENCH_SORTS else "new"


def _sort_groups(groups: list[dict[str, Any]], name: str) -> None:
    """집 목록을 제자리에서 정렬한다.

    **접수순(`new`)이 기본이지만 그냥 두면 안 된다.** 목록은 확인 큐(최신순) 뒤에
    '발주확인 전' 집(최신순)을 이어 붙인 두 덩어리라, 접수시각이 아래로 가다가 중간에서
    다시 최신으로 튄다 — 담당자는 목록이 시간순이라고 믿고 훑는데 그 믿음이 중간에서
    깨진다(2026-08-24 감사). 병합 뒤 **전역으로** 다시 정렬한다.

    화면 문자열(``created_at`` = ``"%m-%d %H:%M"``)로 정렬하면 연말에 뒤집힌다
    (12-31 > 01-02). 그래서 원본 시각 사본(``created_sort``)을 쓴다.

    ``due``(발송기한 임박순)의 동률은 접수 최신순으로 깬다 — 같은 기한이면 나중에 들어온
    집이 손이 덜 간 집이다. 기한이 없는 집은 :data:`_NO_DUE` 로 맨 뒤에 둔다.

    Args:
        groups: :func:`_work_groups` 가 만든 집 목록. **제자리에서** 정렬된다.
        name: :data:`WORKBENCH_SORTS` 중 하나.
    """
    if name == "due":
        # 잠긴 집(취소·반품)은 기한이 아무리 가까워도 **맨 뒤**다. 담당자가 "급한 것부터"
        # 보려고 누른 건데 손댈 수 없는 집이 상단을 차지하면 정렬이 거짓말을 한다
        # (2026-08-24 스테이징 실화면: 임박순 상단 6줄 중 4줄이 취소·반품이었다).
        groups.sort(key=lambda group: (bool(group.get("locked")),
                                       str(group.get("shipping_due") or _NO_DUE),
                                       _sort_stamp_desc(group)))
        return
    groups.sort(key=_sort_stamp_desc)


def _sort_stamp_desc(group: dict[str, Any]) -> float:
    """접수 최신순 정렬키(작을수록 최신). 시각이 없으면 맨 뒤로 보낸다."""
    stamp = group.get("created_sort")
    if stamp is None:
        return float("inf")
    return -stamp.timestamp()


def _actionable_count(groups: list[dict[str, Any]]) -> int:
    """**손댈 수 있는** 집 수 — 스트립·탭 배지·nav 뱃지가 함께 쓰는 SSOT.

    취소·반품 집은 목록에 남지만 어떤 액션도 되지 않는다(체크박스도 disabled). 그런데
    "처리할 집 N집"과 nav 뱃지가 그 집까지 세어서, 담당자가 매일 아침 보는 업무량이 실제
    처리 대상보다 컸다 — 2026-08-24 스테이징 실측으로 확인 큐 72집 중 **13집(18%)**이
    그런 집이었다.

    빼기만 하면 안 된다. 목록에서 지우면 STAFF 는 그 집을 다시 찾을 자리가 없다
    (이력 탭은 ADMIN 전용이고, '취소·반품' 칩의 모집단도 이 목록이다). 그래서 **목록은
    그대로 두고 숫자만 쪼갠다**: 스트립이 "처리 가능 62집 · 손대지 않음 13집"을 함께
    말하므로 62 + 13 = 75(칩 '전체')가 화면에서 맞아떨어진다. 한 화면 두 말이 아니라
    한 말의 분해다.

    술어는 `claim` 칩과 **같은 것**을 쓴다(:func:`_group_matches_filter`) — 잠긴 줄·
    취소·반품 칩·이 숫자의 모집단이 하나여야 한다.

    Args:
        groups: :func:`_work_groups` 의 전체 결과(필터 전).

    Returns:
        int: 손댈 수 있는 집 수. 정의상 ``filter_counts["all"] - filter_counts["claim"]``.
    """
    return sum(1 for group in groups if not _group_matches_filter(group, "claim"))


def _filter_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    """칩 4종의 숫자 — **필터를 걸기 전 전체**에서 센다.

    거른 뒤에 세면 지금 고른 칩만 제 숫자를 갖고 나머지가 0이 된다 — 사람은 다른 칩에
    몇 집이 남았는지 보려고 칩을 본다.

    Args:
        groups: :func:`_work_groups` 의 전체 결과.

    Returns:
        ``{"all": n, "place": n, "rel": n, "claim": n}``.
    """
    return {name: sum(1 for group in groups if _group_matches_filter(group, name))
            for name in WORKBENCH_FILTERS}


def _failure_rows(db) -> list[dict[str, Any]]:
    """마지막 실행에서 실패한 집 (설계 결정 7 — 실패 4단계의 데이터 원천).

    정본은 링크의 ``triage_state['fulfillment']['last_error']`` 다. 워커가 실패 사유를
    거기 적고(``fulfillment.py``), 성공하면 지운다. 예전에는 워커가 예외에 통째로
    rollback 해서 이 기록이 사라졌다 — 그래서 화면이 실패를 아예 보여줄 수 없었다.

    집 단위로 접는다 — 한 집의 상품주문 3건이 같은 이유로 실패하면 3줄이 아니라 1줄이다.

    Args:
        db: 요청 스코프 DB 세션.

    Returns:
        ``link_id``·``customer_name``·``external_order_no``·``reason``·``action``·
        ``action_label``·``at`` 목록(최근 순).
    """
    # 실패는 **실패했다는 사실로** 찾는다. 최근 수집분 N건을 읽어 파이썬으로 거르면,
    # 그 뒤로 수집이 쌓인 집의 실패가 조회 창 밖으로 밀려 화면에서 사라진다
    # (오래된 수집분이 오늘 발주확인에 실패하는 일은 흔하다).
    reason_col = ExternalOrderLink.triage_state["fulfillment"]["last_error"].as_string()
    links = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                reason_col.isnot(None), reason_col != "")
        .order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
        .limit(QUEUE_LINK_FETCH_LIMIT)
        .all()
    )
    from foms.services.integrations.naver_commerce.fulfillment import (
        failure_action,
        household_key,
    )

    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    for link in links:
        state = (link.triage_state or {}).get("fulfillment") or {}
        reason = str(state.get("last_error") or "").strip()
        if not reason:
            continue
        # 접는 규칙은 **재시도·확인함이 처리하는 단위와 같아야 한다**(둘 다 원본 3-튜플).
        # 컬럼(group_key)으로 접으면 백필 전 분할배송에서 두 집이 한 줄로 붙어, 건수가
        # 낮게 뜨고 한 번 눌러 한 집만 처리된다.
        key = f"{(link.external_order_no or '').strip()}|{household_key(link)}"
        action_now = str(state.get("last_error_action") or "").strip().lower()
        if key in seen:
            # 집당 1행으로 접되, **취소·반품 거절은 다른 실패에 가려지면 안 된다**
            # (2026-08-23 리뷰 F4, 반품은 T8-S1 에서 같은 규율로 추가). 가려지면 사람이
            # 방금 누른 조작의 사유를 못 보고, 남은 행은 retryable 이라 재시도 버튼이
            # 그 집에 반대 조작(발주확인·발송처리)을 쏜다.
            if action_now in ("cancel", "return"):
                rows[:] = [row for row in rows if row["_key"] != key]
                seen.discard(key)
            else:
                continue
        seen.add(key)
        summary = summarize_snapshot(link.raw_snapshot)
        # 어느 작업이 실패했는지 워커가 함께 적는다. 없으면(옛 기록) 발주확인으로 본다 —
        # 재시도를 항상 발주확인으로 보내면 발송처리 실패는 멱등 규칙에 걸려 조용히
        # 넘어가고 실패 띠만 영원히 남는다. 읽는 규칙은 :func:`fulfillment.failure_action`
        # 한 벌이다 — `확인함` 의 범위가 이 값으로 정해지므로(RC5 2차), 여기서 따로 읽으면
        # 띠에 보이는 줄과 지워지는 줄이 갈린다.
        action = failure_action(link)
        action = action if action in FULFILLMENT_ACTION_LABELS else "confirm"
        rows.append({
            "_key": key,
            "link_id": link.id,
            "customer_name": summary["customer_name"] or link.external_id,
            "external_order_no": link.external_order_no or "",
            "reason": reason,
            "action": action,
            "action_label": FULFILLMENT_ACTION_LABELS[action],
            # 취소·반품은 사유를 다시 골라야 해서 버튼 하나로 되보낼 수 없다. 재시도
            # 목록에 넣으면 그 집이 **발주확인**으로 나간다 — 취소·반품하려던 집에
            # 되돌릴 수 없는 반대 조작이 나가는 자리다. 상세 pane 에서 사유와 함께 다시 보낸다.
            "retryable": action in ("confirm", "dispatch"),
            # 시각 파서는 한 벌이다. 원문을 슬라이스하면 ① UTC 를 그대로 찍어
            # 같은 칸의 발송 시각(KST)과 9시간 어긋나고 ② 못 읽는 값도 잘라 낸다.
            "at": _dispatch_time_text(state.get("last_error_at")),
        })
    _mark_return_sendable(db, rows)
    return rows


def _mark_return_sendable(db, rows: list[dict[str, Any]]) -> None:
    """실패 행마다 **아직 안 보낸 반품 접수 건수**를 달아 준다 (NVCLAIM-ORDER-01 T7).

    반품 접수에 실패한 라인에는 ``return`` 축 기록이 **아예 없다** — 성공분만 기록을 받는다.
    그래서 그 라인의 ``last_error`` 가 "본품이 반품되지 않았다"는 유일한 DB 흔적이다(RC5).

    2차 배에서 ``fulfillment.clear_failure`` 를 작업 단위로 좁혔지만 **이 잠금은 남긴다.**
    좁히기가 막는 것은 "안 본 형제의 실패까지 함께 지우는 것"이고, 여기서 잃는 것은
    **사람이 실제로 보고 누른 그 줄**이다 — 반품 실패 줄에서 `확인함` 을 누르면 여전히
    그 유일한 흔적이 (강등되긴 해도) 화면에서 사라진다. 실패 라인에 ``return`` 축
    실패 기록을 남기는 일(설계서 T3)이 아직 배포되지 않은 한, 잠금이 마지막 문이다.

    술어는 :func:`fulfillment.return_sendable` 이다. ``is_return_pending`` 으로 세면
    판매자센터에서 사람이 손으로 끝낸 집까지 영원히 잠긴다 — 그쪽은 **우리 표식으로만**
    멱등을 판정하기 때문이다.

    조회는 실패 행이 있을 때만 1회다(집 형제는 실패 표식이 없어 위 조회에 안 잡힌다).

    Args:
        db: 요청 스코프 DB 세션.
        rows: :func:`_failure_rows` 가 만든 행 목록(**제자리에서** 필드를 올린다).

    Returns:
        None.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        household_key,
        return_sendable,
    )

    for row in rows:
        row["return_sendable_count"] = 0
    order_nos = sorted({row["external_order_no"] for row in rows if row["external_order_no"]})
    if not order_nos:
        return
    siblings = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                ExternalOrderLink.external_order_no.in_(order_nos))
        .all()
    )
    counts: dict[str, int] = {}
    for sibling in siblings:
        if not return_sendable(sibling):
            continue
        # 접는 키는 :func:`_failure_rows` 와 **글자 그대로 같아야** 한다 — 다르면 카운트가
        # 엉뚱한 줄에 붙어 잠글 집을 안 잠근다.
        key = f"{(sibling.external_order_no or '').strip()}|{household_key(sibling)}"
        counts[key] = counts.get(key, 0) + 1
    for row in rows:
        row["return_sendable_count"] = counts.get(row["_key"], 0)


def _history_view(db) -> dict[str, Any]:
    """전체 이력 탭 데이터 (W4).

    이력 표 자체는 기존 관리 화면과 **같은 함수**(:func:`_link_rows`)를 쓴다 — 집 묶음·
    페이징·클레임 표식 규칙이 두 벌이 되면 두 화면의 숫자가 또 갈린다.

    취소·반품 행은 빼지 않는다(설계 결정 2). 빼면 "그 주문 어디 갔지" 가 되고,
    회색으로 남기면 같은 자리에서 사실을 확인할 수 있다.

    Args:
        db: 요청 스코프 DB 세션.

    칩은 8개다: 전체 · 상태 4종(:data:`HISTORY_STATUS_CHIPS`) · 발주확인 남음 ·
    **발송처리 남음** · **추가결제·재결제**. 새 칩 둘의 숫자도 다른 칩과 **같은 집 단위**다 —
    링크 행으로 세면 부분이 전체보다 커 보인다(2026-08-19 스테이징 실화면).

    ``네이버 기록 없음`` 은 칩으로 만들지 않는다: 판정이 ``raw_snapshot`` 파생값(mismatch)이라
    SQL 로 못 거르고, 쪽을 자른 뒤 파이썬으로 세면 ``total``·``pages`` 가 거짓말이 된다
    (캡 뒤 파이썬 분류 함정). **행 배지로만** 둔다.

    찾기(``q``)는 **서버가** 한다(2026-09-02). 화면 필터로 두면 칸이 닿는 데가 지금 쪽
    50집뿐이라, 16쪽짜리 이력에서 이름을 쳐도 "0주문"이 나온다 — 사용자가 이 결함을
    실화면으로 보고했다. 좁힌 뒤의 ``total``·``pages``·칩 옆 숫자가 전부 같은 술어에서
    나오도록 :func:`_link_rows` 안에서 건다.

    Returns:
        ``rows``·``total``·``page``·``page_size``·``status``·``find``·``place_pending``·
        ``dispatch_pending``·``relation_filter``·``counts``·``status_chips`` 와
        칩 숫자 3종을 담은 dict.
    """
    status = (request.args.get("status") or "").strip().upper()
    status = status if status in VALID_STATUSES else ""
    place_pending = (request.args.get("place") or "").strip().upper() == "PENDING"
    # 읽기 규약은 기존과 같다 — 닫힌집합이고 모르는 값은 무시한다(필터가 조용히 안 걸린다).
    dispatch_pending = (request.args.get("dispatch") or "").strip().upper() == "PENDING"
    relation_filter = (request.args.get("rel") or "").strip().upper() == "ADDON_REPAY"
    try:
        page = max(1, int(request.args.get("page", 1)))
    except (TypeError, ValueError):
        page = 1

    find = _history_find_term(request.args.get("q"))

    rows, total = _link_rows(db, status=status or None, page=page,
                             place_pending=place_pending,
                             dispatch_pending=dispatch_pending,
                             relation_filter=relation_filter,
                             find=find)
    return {
        "rows": rows,
        "total": total,
        "page": page,
        "page_size": PAGE_SIZE,
        "pages": ((total - 1) // PAGE_SIZE) + 1 if total else 1,
        "status": status,
        "find": find,
        "place_pending": place_pending,
        "dispatch_pending": dispatch_pending,
        "relation_filter": relation_filter,
        # 칩 숫자도 **같은 낱말**로 좁힌다 — 목록만 좁히고 칩은 전체를 말하면
        # 한 화면이 두 모집단을 동시에 주장한다.
        "counts": _status_group_counts(db, find=find),
        # 칩 낱말의 **단일 출처**. 템플릿이 두 벌째 적으면 칩만 `받아옴 · 주문 전`,
        # 배지만 `받아옴` 으로 조용히 갈린다(상수 주석이 경고한 그 실패 모양).
        "status_chips": HISTORY_STATUS_CHIPS,
        "place_pending_count": _place_pending_group_count(db, find=find),
        "dispatch_pending_count": _dispatch_pending_group_count(db, find=find),
        "relation_count": _relation_group_count(db, find=find),
    }


def _place_groups(db, *, display: bool = True, links: Optional[list[Any]] = None,
                  truncated: Optional[bool] = None,
                  sibling: Optional["_SiblingIndex"] = None
                  ) -> tuple[list[dict[str, Any]], bool]:
    """'발주확인 전' 탭의 집 목록 (W2).

    모집단은 필터 버튼 숫자(:func:`_place_pending_group_count`)와 **같은 술어**여야 한다 —
    "21집" 이라고 써 놓고 목록이 19줄이면 사람이 나머지를 찾아 헤맨다.

    취소·반품 집은 뺀다. 발주확인 대상이 아니고, 목록에 두면 잘못 눌린다.

    Args:
        db: 요청 스코프 DB 세션.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).
        links: 호출자가 **이미 읽어 둔** 발주확인 전 링크(없으면 여기서 읽는다).
            :func:`_work_groups` 는 확인 큐와 이 목록을 한 번에 읽어 파이썬에서 가른다 —
            술어는 같고 조회만 한 벌이다.
        truncated: 그 목록이 조회 상한에 걸렸는지(``links`` 를 줬을 때만 쓴다).
        sibling: 미리 만든 :class:`_SiblingIndex` (없으면 형제를 여기서 다시 읽는다).

    Returns:
        ``(묶음 목록, 잘렸는지)``. 조용히 자르면 사람이 나머지를 찾아 헤맨다 —
        잘렸으면 화면이 그렇게 말한다.
    """
    prefetched = links is not None
    links = links if prefetched else _fetch_links(
        db,
        ExternalOrderLink.channel == "NAVER",
        # 수집이 성공한 건만 본다. v2 에서는 이 목록이 '발주확인 전' **탭 전용**이라
        # FAILED·PENDING_REVIEW 가 섞여도 뱃지·처리 큐에는 안 들어갔다. v3 가 이
        # 결과를 처리 목록·nav 뱃지와 합치면서, **수집이 깨진 링크가 "처리할 집"으로
        # 세어지고 벌크 발주확인 후보로 체크박스까지 열렸다**(2026-08-23 발견).
        # 발주확인은 네이버로 나가는 불가역 호출이다 — 원본이 불완전한 건을 그 대상에
        # 올리지 않는다. 보류·실패는 이력 탭과 실패 띠가 받는다.
        ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
        _place_pending_clause(),
        display=display,
        order_by=(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc()),
        limit=QUEUE_LINK_FETCH_LIMIT,
    )
    hit_cap = bool(truncated) if prefetched else len(links) == QUEUE_LINK_FETCH_LIMIT
    if not links:
        return [], False
    # 주문은 표시(고객명·다음 할 일)에만 쓴다 — 얇은 경로는 조회 자체를 내지 않는다.
    order_ids = [int(row.order_id) for row in links if row.order_id] if display else []
    orders = {}
    if order_ids:
        orders = {o.id: o for o in db.query(Order).filter(Order.id.in_(order_ids)).all()}
    # 상한은 **클레임을 걸러낸 뒤에** 건다. 앞에서 자르면 빠질 집이 상한을 먹어
    # "잘렸다"를 숨긴다(60집 중 5집이 취소면 46집만 보이고 경고가 안 뜬다).
    groups = _group_queue(links, orders, truncated=hit_cap,
                          limit=QUEUE_LINK_FETCH_LIMIT)
    # 우리가 취소한 집은 목록에서 뺀다. 컬럼(place_order_status)만 보는 SQL 술어로는 못 거른다
    # — 취소 표식은 triage_state(JSONB) 이고 hot path 에서 JSONB 를 스캔하지 않는다.
    # 탭 배지는 이 목록의 길이를 쓰므로 여기서 빼면 배지와 목록이 함께 줄어든다.
    groups = [group for group in groups if not group["canceled"]]
    # 클레임 판정은 **형제까지** 봐야 한다. 모집단을 '발주확인 전' 링크로 먼저 좁혔으므로,
    # 이미 발주확인이 끝난 형제가 취소돼도 이 목록 안에서는 안 보인다 — 그 집에 발주확인을
    # 보내면 네이버가 거절해 집 전체가 실패한다.
    blocked = (sibling.confirmed_claim_blocked if sibling is not None
               else _claim_blocked_group_keys(db, links, display=display))
    visible = [group for group in groups
               if not group["claim_blocking"] and group["key"] not in blocked]
    return visible[:WORK_GROUP_LIMIT], bool(len(visible) > WORK_GROUP_LIMIT or hit_cap)


def _row_place_pending(row: Any) -> bool:
    """:func:`_place_pending_clause` 의 **파이썬 쌍둥이** — 같은 컬럼, 같은 갈래.

    한 번 읽은 행을 두 모집단으로 가를 때 쓴다. SQL 술어와 갈리면 '발주확인 전' 칩
    숫자가 목록과 어긋나므로, 판정은 여기 한 줄과 :func:`_place_pending_clause` 한
    줄뿐이고 둘의 동치는 회귀 테스트가 못박는다.

    Args:
        row: 링크 행(ORM 또는 :class:`_ThinLink`).

    Returns:
        발주확인이 아직인 링크인가.
    """
    status = row.place_order_status
    return status is None or status not in CONFIRMED_PLACE_VALUES


def _work_source_links(db, *, display: bool) -> tuple[list[Any], bool]:
    """처리 탭의 두 원천을 **조회 한 번**으로 읽는다.

    원천 1(확인 큐 — ``reviewed_at`` NULL)과 원천 2('발주확인 전')는 같은 채널·같은
    ``sync_status`` 를 보고 크게 겹치는데 따로 읽고 있었다 — 2026-08-24 스테이징 구간
    실측에서 뱃지 콜드의 **36%**(34.5ms + 21.5ms)가 이 두 벌이었다. 술어를 OR 로 합쳐
    한 번 읽고 파이썬에서 가른다. 두 갈래의 술어는 그대로다.

    상한은 **합집합 하나**에 건다. 닿으면 두 원천 모두 불완전할 수 있으므로 잘림 표식을
    양쪽에 똑같이 준다 — 조용히 자르지 않는다(캡 발동은 :func:`_work_groups` 가 고지).

    Args:
        db: 요청 스코프 DB 세션.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).

    Returns:
        ``(합집합 링크(최신순), 조회 상한에 걸렸는지)``.
    """
    from sqlalchemy import or_

    rows = _fetch_links(
        db,
        ExternalOrderLink.channel == "NAVER",
        # 수집이 성공한 건만 본다(두 원천 공통) — 보류·실패는 이력 탭과 실패 띠가 받는다.
        ExternalOrderLink.sync_status.in_(("COLLECTED", "LINKED")),
        or_(ExternalOrderLink.reviewed_at.is_(None), _place_pending_clause()),
        display=display,
        order_by=(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc()),
        limit=QUEUE_LINK_FETCH_LIMIT,
    )
    return rows, len(rows) == QUEUE_LINK_FETCH_LIMIT


def _work_groups(db, *, display: bool = True,
                 sort: str = "new") -> tuple[list[dict[str, Any]], bool]:
    """처리 탭 목록 = 확인 큐 ∪ 발주확인 전 집 (집 단위 병합).

    두 목록을 따로 두면 같은 집이 화면마다 다른 숫자로 세어지고, 사람은 한 집을 끝내려고
    탭을 오간다. 하나로 합치고 갈래는 필터 칩(:func:`_group_matches_filter`)이 맡는다.

    원천 1 = 확인 큐(:func:`_queue_links` — ``COLLECTED|LINKED`` + ``reviewed_at`` NULL),
    원천 2 = :func:`_place_groups` (확인은 끝나 큐에서 빠졌지만 아직 발주확인 전인 집).
    같은 집이 양쪽에 있으면 **큐 쪽 dict 를 채택**하고 ``place_pending`` 만 합친다.

    ``request``·``session`` 을 읽지 않는다 — nav 뱃지가 모든 페이지 렌더에서 이 정의를
    그대로 쓴다(뱃지 67 · 탭 45 로 어긋나던 자리).

    ``display=False`` 는 **모집단을 바꾸지 않는다.** 술어·병합·캡 코드가 그대로고,
    ``raw_snapshot`` 자리에 판정 경로만 담은 축소 문서가 들어갈 뿐이다
    (:func:`_snapshot_projection`). 그래서 집 키 목록·필터 숫자·``truncated`` 가
    두 모드에서 **같아야 한다** — 계약 §2.4(뱃지 == 탭 숫자 == 칩 '전체')의 증명이 그것이고,
    회귀 테스트가 두 모드를 직접 비교해 못박는다. 달라지는 것은 표시 전용 필드
    (제품명·고객명·금액·다음 할 일 등)뿐이다.

    Args:
        db: 요청 스코프 DB 세션.
        display: 표시용 스냅샷·주문까지 싣는가. nav 뱃지(:func:`triage_count.
            _workbench_group_count`)는 세기만 하므로 False 로 부른다.
        sort: 목록 정렬(:data:`WORKBENCH_SORTS`). **모집단을 바꾸지 않는다** — 캡보다
            먼저 돌므로 캡이 자를 집만 달라진다.

    Returns:
        ``(집 목록, 조회 상한에 걸렸는지)``. 순서는 큐(수집 최신순) → 큐 밖 발주확인 전 집.
    """
    source, truncated = _work_source_links(db, display=display)
    # 술어는 SQL 과 같은 갈래를 파이썬에서 그대로 쓴다(`_row_place_pending`).
    pending = [row for row in source if row.reviewed_at is None]
    place_links = [row for row in source if _row_place_pending(row)]
    # 형제 판정은 여기서 **한 벌만** 만든다 — 아래 세 곳이 같은 색인을 나눠 쓴다.
    sibling = _build_sibling_index(db, _source_order_nos(source), display=display)
    # **캡 하나를 더 넘겨 받아** 잘렸는지 스스로 안다. `_group_queue` 는 상한까지만 돌려주는데
    # 그 사실을 아무도 안 봐서, 집이 50을 넘으면 화면이 조용히 51번째부터 버렸다 —
    # 링크 250 상한(`truncated`)에 걸릴 때만 안내 띠가 떴다. 캡으로 자른 뒤 아무 말도 안 하면
    # 사람은 나머지를 찾아 헤맨다(2026-08-14 대시보드 캡 결함과 같은 부류, CEO 검수 보통).
    # 캡은 여기서 걸지 않는다 — 병합이 끝난 뒤 한 곳에서 건다(아래). 원천마다 자르면
    # 큐가 잘려 띠가 켜지는데 화면 줄수는 캡보다 커지는, 서로 어긋난 상태가 된다.
    queue = _group_queue(pending, _orders_by_id(db, pending) if display else {},
                         truncated=truncated, limit=WORK_GROUP_LIMIT + 1)
    place_groups, place_truncated = _place_groups(
        db, display=display, links=place_links, truncated=truncated, sibling=sibling)

    merged: dict[Any, dict[str, Any]] = {}
    order_of_key: list[Any] = []
    for group in queue:
        merged[group["key"]] = dict(group, in_queue=True)
        order_of_key.append(group["key"])
    for group in place_groups:
        seen = merged.get(group["key"])
        if seen is not None:
            # 큐 dict 가 이긴다. 다만 '발주확인 전'은 원천 2 가 더 넓게 본다(큐 모집단은
            # 확인 대기로 좁혀져 있다) — 그 축만 합쳐야 칩 숫자가 목록과 맞는다.
            seen["place_pending"] = bool(seen["place_pending"] or group["place_pending"])
            continue
        merged[group["key"]] = dict(group, in_queue=False)
        order_of_key.append(group["key"])
    groups = [merged[key] for key in order_of_key]
    _mark_sibling_claims(db, pending, groups, display=display, sibling=sibling)
    _attach_household_counts(db, groups, display=display, sibling=sibling)
    # 잠금·선택 판정은 위 두 단계가 끝난 **뒤에** 한 번만 한다(형제 클레임이 반영된 값으로).
    _attach_row_flags(groups)
    # 정렬은 **캡보다 먼저** 한다. 뒤에 하면 캡이 자를 집을 정렬이 못 고른다 — 발송기한이
    # 임박한 집은 정의상 오래 전에 수집된 집이라 접수순 목록의 아래쪽에 있고, 캡이 먼저
    # 자르면 그 집이 화면 밖으로 밀린 뒤에야 정렬이 돈다.
    _sort_groups(groups, sort)
    # 캡 한 곳 — 병합 결과에만 건다. 닿으면 **로그를 남기고** 화면에도 말한다(조용히 자르면
    # 사람이 나머지를 찾아 헤맨다 — 2026-08-14 대시보드 캡 결함과 같은 부류).
    capped = len(groups) > WORK_GROUP_LIMIT
    if capped:
        logger.warning("[NAVER] 처리 목록 캡 발동: %s집 중 %s집만 보여준다",
                       len(groups), WORK_GROUP_LIMIT)
        groups = groups[:WORK_GROUP_LIMIT]
    return groups, bool(truncated or place_truncated or capped)


def _mark_sibling_claims(db, queue_links: list[Any],
                         groups: list[dict[str, Any]], *, display: bool = True,
                         sibling: Optional["_SiblingIndex"] = None) -> None:
    """이미 발주확인이 끝난 **형제**의 취소·반품을 집 전체에 반영한다.

    ``_place_groups`` 는 원천 2 안에서 이 검사를 하지만, 원천 1(확인 큐)은 안 한다.
    v2 에서는 체크박스가 원천 2 목록 루프 안에만 있어 구조적으로 문제가 없었는데,
    v3 가 두 목록을 합치면서 **원천 1 출신 집이 검사 없이 목록에 올라** 체크박스가
    열리고 잠금 표시도 안 됐다(2026-08-23 리뷰 H1). 그러면 목록은 "보내도 된다"고 하고
    상세는 "취소·반품이라 닫혀 있다"고 하는, 한 화면 안의 모순이 된다.

    Args:
        db: 요청 스코프 DB 세션.
        queue_links: 확인 큐 링크(형제 조회의 기준).
        groups: 병합된 집 목록. **제자리에서** ``claim_blocking`` 을 올린다.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).
        sibling: 미리 만든 :class:`_SiblingIndex` (없으면 형제를 여기서 다시 읽는다).
            색인은 두 원천의 주문번호 **합집합**으로 만들어져 옛 경로보다 넓어 보이지만,
            판정은 집키로 하고 집키가 목록에 있으려면 그 주문번호가 이미 기준 집합에
            들어 있다 — 결과는 같다(동치 회귀 테스트가 못박는다).
    """
    if not groups:
        return
    blocked = (sibling.confirmed_claim_blocked if sibling is not None
               else _claim_blocked_group_keys(db, queue_links, display=display))
    if not blocked:
        return
    for group in groups:
        if group["key"] in blocked:
            group["claim_blocking"] = True


def _attach_household_counts(db, groups: list[dict[str, Any]], *,
                             display: bool = True,
                             sibling: Optional["_SiblingIndex"] = None) -> None:
    """각 집에 **워커가 실제로 처리할 상품주문 수**(``household_count``)를 붙인다.

    ``count`` 는 화면 목록 모집단(확인 대기로 좁혀진 큐) 안의 수라, 확인이 끝난 형제가
    있으면 워커가 처리할 수보다 작다. 벌크 모달이 그 값을 재진술하면 "1건 보냅니다"라고
    읽고 3건이 나간다 — pane 은 ``_group_of_link`` 로 이미 고쳤는데 벌크만 남아 있었다
    (2026-08-23 리뷰 H2). 집 판정은 워커와 같은 :func:`fulfillment.household_key` 를 쓴다.

    조회는 주문번호 묶음 **한 번**이다(집마다 세면 N+1).

    Args:
        db: 요청 스코프 DB 세션.
        groups: 병합된 집 목록. 제자리에서 ``household_count`` 를 채운다.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).
        sibling: 미리 만든 :class:`_SiblingIndex`. 주면 대표 링크 조회·형제 조회를
            **둘 다 건너뛴다** — 같은 행을 세 벌로 읽던 자리다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import household_key

    if sibling is not None:
        _apply_household_counts(groups, sibling)
        return
    # 집 dict 에는 주문번호가 없다(대표 link id 만 있다) — 대표 링크에서 뽑는다.
    lead_ids = [int(g["id"]) for g in groups if g.get("id")]
    counts: dict[Any, int] = {}
    # 벌크 모달이 재진술할 건수 — 서버 confirm_place_order 는 이미 확인된 형제를 뺀다.
    # 집 전체 수로 말하면 "119건 보냅니다" 인데 그보다 적게 나간다(계약 §0-2, CEO 검수 보통).
    pending_counts: dict[Any, int] = {}
    blocking: set = set()
    canceled: set = set()
    order_nos = set()
    if lead_ids:
        # 대표 링크에서 필요한 것은 **주문번호 하나**다 — 스냅샷은 여기서 안 쓴다.
        leads = (
            db.query(ExternalOrderLink.external_order_no)
            .filter(ExternalOrderLink.id.in_(lead_ids))  # perf-ok: 페이지 대표 링크 batch
            .all()
        )
        order_nos = {(row[0] or "").strip() for row in leads if (row[0] or "").strip()}
    if order_nos:
        rows = _fetch_links(
            db,
            ExternalOrderLink.channel == "NAVER",
            ExternalOrderLink.external_order_no.in_(sorted(order_nos)),
            display=display,
        )
        from foms.services.integrations.naver_commerce.fulfillment import is_place_pending
        from foms.services.integrations.naver_commerce.mapping import extract_claim

        for row in rows:
            hkey = household_key(row)
            counts[hkey] = counts.get(hkey, 0) + 1
            if is_place_pending(row):
                pending_counts[hkey] = pending_counts.get(hkey, 0) + 1
            # 형제 전부를 이 한 번의 조회에서 판정한다. `_claim_blocked_group_keys` 는
            # `place_order_status='OK'` 형제의 **클레임만** 읽어서, ① 발주확인 전 형제의
            # 클레임 ② 우리가 낸 취소(`canceled_at`)를 놓쳤다 — 그 집은 행이 안 잠기고
            # 체크박스가 열려 벌크 발주확인 대상이 됐다(2026-08-23 리뷰 H-A).
            # 목록이 "보내도 된다"고 하는데 상세는 "닫혀 있다"고 하면 그건 화면의 거짓말이다.
            try:
                if (extract_claim(row.raw_snapshot or {}) or {}).get("blocking"):
                    blocking.add(hkey)
            except (ValueError, TypeError, AttributeError, KeyError) as exc:
                logger.warning("[NAVER] 형제 클레임 판정 실패(link %s): %s", row.id, exc)
            state = (row.triage_state or {}).get("fulfillment") or {}
            if state.get("canceled_at"):
                canceled.add(hkey)
    index = _SiblingIndex()
    index.counts, index.pending_counts = counts, pending_counts
    index.blocking, index.canceled = blocking, canceled
    _apply_household_counts(groups, index)


def _apply_household_counts(groups: list[dict[str, Any]], sibling: "_SiblingIndex") -> None:
    """형제 색인을 집 목록에 **제자리로** 얹는다 — 두 경로가 쓰는 한 벌의 규칙.

    Args:
        groups: 병합된 집 목록.
        sibling: :class:`_SiblingIndex`.
    """
    for group in groups:
        # 못 세면 화면이 아는 수로 떨어진다(작게 말하는 쪽이 크게 말하는 쪽보다 안전하지
        # 않다 — 그래서 이 값이 실패하면 모달이 집계를 숨기도록 템플릿이 판단한다).
        group["household_count"] = sibling.counts.get(group["key"], group["count"])
        # 못 세면 화면이 아는 수(집 안 발주확인 전 건수)로 떨어진다.
        group["household_place_pending"] = sibling.pending_counts.get(
            group["key"], group.get("place_pending_count") or group["count"])
        # 형제까지 본 잠금 판정. 같은 쿼리 결과를 재사용하므로 조회는 늘지 않는다.
        if group["key"] in sibling.blocking:
            group["claim_blocking"] = True
        if group["key"] in sibling.canceled:
            group["canceled"] = True


def _household_has_claim(db, link: Optional[ExternalOrderLink]) -> bool:
    """선택한 집(형제 전부)에 취소·반품이 걸려 있는가.

    큐 묶음(:func:`_group_queue`)의 ``claim_blocking`` 은 **확인 대기 링크만** 보므로,
    확인 완료돼 큐에서 빠진 형제의 취소를 못 본다. 발송처리는 되돌릴 수 없어 그 구멍이
    그대로 사고가 된다 — 선택된 집 하나만 형제 전부를 읽어 판정한다(조회 1회).

    Args:
        db: 요청 스코프 DB 세션.
        link: 선택된 링크(없으면 False).

    Returns:
        형제 중 하나라도 취소·반품이면 True.
    """
    if link is None:
        return False
    order_no = (link.external_order_no or "").strip()
    if not order_no:
        return bool(summarize_snapshot(link.raw_snapshot)["claim_blocking"])

    from foms.services.integrations.naver_commerce.fulfillment import household_key

    base_key = household_key(link)
    rows = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER",
                ExternalOrderLink.external_order_no == order_no)
        .all()
    )
    return any(summarize_snapshot(row.raw_snapshot)["claim_blocking"]
               for row in rows if household_key(row) == base_key)


class _SiblingIndex:
    """형제 행을 **한 번만** 읽어 만든 집 단위 판정 색인.

    같은 판정을 세 곳이 각자 조회했다: :func:`_claim_blocked_group_keys` 가 두 번
    (``_place_groups``·``_mark_sibling_claims``), :func:`_attach_household_counts` 가
    한 번. 셋 다 같은 ``external_order_no`` 집합으로 형제 행을 읽고 같은 스냅샷을 다시
    판정한다 — 2026-08-24 스테이징 구간 실측에서 뱃지 콜드 155.5ms 중 **74.0ms(48%)**
    가 이 세 벌이었다.

    **술어는 하나도 바꾸지 않는다.** 모집단·판정 함수는 그대로고 읽는 횟수만 줄인다 —
    뱃지와 화면이 다른 함수로 세는 순간 계약 §2.4(뱃지 == 탭 숫자 == 칩 '전체')가 깨진다
    (이 저장소가 두 번 겪었다: nav 67·탭 45 / nav 140·필터 43).

    ``claim_blocking`` 은 :func:`summarize_snapshot` 으로 판정한다. 옛 집계 경로는
    ``extract_claim`` 을 직접 불러 예외를 잡았는데, ``summarize_snapshot`` 은 같은
    ``claim["blocking"]`` 을 돌려주면서 깨진 원본에 대해 **예외 대신 False** 를 준다
    (판정값 동일, 실패 처리만 한 벌).

    Attributes:
        counts: ``{집키: 형제 상품주문 수}``.
        pending_counts: ``{집키: 발주확인 전 형제 수}``.
        blocking: 취소·반품이 걸린 집키 집합(형제 전체 기준).
        canceled: 우리가 취소한(``canceled_at``) 집키 집합.
        confirmed_claim_blocked: **이미 발주확인이 끝난** 형제가 취소·반품인 집키 집합
            — 옛 :func:`_claim_blocked_group_keys` 의 반환값과 같은 어휘다.
    """

    __slots__ = ("counts", "pending_counts", "blocking", "canceled",
                 "confirmed_claim_blocked")

    def __init__(self):
        self.counts: dict[Any, int] = {}
        self.pending_counts: dict[Any, int] = {}
        self.blocking: set = set()
        self.canceled: set = set()
        self.confirmed_claim_blocked: set = set()


def _source_order_nos(links: list[Any]) -> set:
    """링크 목록에서 네이버 주문번호 집합을 뽑는다(빈 값 제외).

    Args:
        links: 링크 행 목록.

    Returns:
        공백을 턴 주문번호 집합.
    """
    order_nos = {(row.external_order_no or "").strip() for row in links}
    order_nos.discard("")
    return order_nos


def _build_sibling_index(db, order_nos: set, *, display: bool) -> _SiblingIndex:
    """주문번호 집합의 형제 행을 **한 번 읽어** 집 단위 판정을 전부 만든다.

    Args:
        db: 요청 스코프 DB 세션.
        order_nos: 기준 주문번호 집합(:func:`_source_order_nos`).
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).

    Returns:
        :class:`_SiblingIndex`. 주문번호가 없으면 빈 색인.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        household_key,
        is_place_pending,
    )

    index = _SiblingIndex()
    if not order_nos:
        return index
    rows = _fetch_links(
        db,
        ExternalOrderLink.channel == "NAVER",
        ExternalOrderLink.external_order_no.in_(sorted(order_nos)),
        display=display,
    )
    for row in rows:
        hkey = household_key(row)
        index.counts[hkey] = index.counts.get(hkey, 0) + 1
        if is_place_pending(row):
            index.pending_counts[hkey] = index.pending_counts.get(hkey, 0) + 1
        # 원본 파싱은 행마다 **한 번**이다 — 옛 경로는 같은 행을 세 벌로 다시 풀었다.
        claim_blocking = summarize_snapshot(row.raw_snapshot)["claim_blocking"]
        if claim_blocking:
            index.blocking.add(hkey)
            # 발주확인이 끝난 형제의 클레임만 따로 센다 — 발주확인 전 형제의 클레임은
            # 이미 목록 안에 있어 `_group_queue` 가 판정했다(옛 SQL 술어와 같은 갈래).
            if (row.place_order_status or "") in CONFIRMED_PLACE_VALUES:
                index.confirmed_claim_blocked.add(hkey)
        if ((row.triage_state or {}).get("fulfillment") or {}).get("canceled_at"):
            index.canceled.add(hkey)
    return index


def _claim_blocked_group_keys(db, links: list[Any], *, display: bool = True) -> set:
    """주어진 링크들이 속한 집 중 **취소·반품이 걸린 집**의 묶음키.

    같은 네이버 주문번호의 형제 중 **이미 발주확인이 끝난 것만** 읽는다. 발주확인 전
    형제는 이미 목록 안에 있어 :func:`_group_queue` 가 클레임을 판정했다.
    한 상품주문만 취소돼도 그 집은 손대지 않는 집이다 — 큐의 다른 곳과 같은 규칙이다.

    Args:
        db: 요청 스코프 DB 세션.
        links: 기준이 되는 링크 목록.
        display: 표시용 스냅샷까지 싣는가(:func:`_fetch_links`).

    Returns:
        :func:`fulfillment.household_key` 3-튜플의 집합 — `group["key"]` 와 같은 어휘다.
    """
    # 반환 키는 `group["key"]` 와 **같은 어휘**여야 한다. 큐가 household_key 로 옮겨간 뒤
    # 여기만 mapping.group_key 로 남으면, 원본이 통째로 빈 집에서 ("","","") 와
    # ("__ungrouped__", id, "") 로 갈려 이 경로의 잠금이 조용히 안 걸린다(CEO 검수 하).
    from foms.services.integrations.naver_commerce.fulfillment import household_key

    order_nos = {(row.external_order_no or "").strip() for row in links}
    order_nos.discard("")
    if not order_nos:
        return set()
    # **모집단 밖 형제만** 읽는다 — 모집단 안(발주확인 전) 링크의 클레임은 이미
    # :func:`_group_queue` 가 `claim_blocking` 으로 판정했다. 여기서 다시 읽으면
    # 같은 원본을 두 번 파싱하고 조회도 그만큼 커진다.
    siblings = _fetch_links(
        db,
        ExternalOrderLink.channel == "NAVER",
        ExternalOrderLink.external_order_no.in_(sorted(order_nos)),
        ExternalOrderLink.place_order_status.in_(CONFIRMED_PLACE_VALUES),
        display=display,
    )
    blocked: set = set()
    for row in siblings:
        if not summarize_snapshot(row.raw_snapshot)["claim_blocking"]:
            continue
        # household_key 는 실패·빈 키 폴백을 자기가 들고 있다(예외를 던지지 않는다).
        blocked.add(household_key(row))
    return blocked


def _group_of_link(db, link: ExternalOrderLink) -> Optional[dict[str, Any]]:
    """큐에 없는 링크의 **집** — 확인 완료·조회 상한 밖 링크를 열었을 때 쓴다.

    pane 은 큐에서 빠진 집도 열 수 있다(발주확인·발송처리 버튼이 거기 있다). 그때 집이
    없으면 상품주문 표가 빈 표가 되고, 불가역 모달이 "상품주문 1건" 이라 말한다 —
    실제로는 형제 전부가 주문 하나로 합쳐진다. 건수 재진술이 거짓이 되는 자리다.

    묶음 규칙은 큐와 **같은 함수**(:func:`_group_queue`)를 쓴다. 규칙이 두 벌이 되면
    같은 집이 화면마다 다르게 묶인다.

    Args:
        db: 요청 스코프 DB 세션.
        link: 선택된 링크.

    Returns:
        그 링크가 속한 묶음(없으면 None).
    """
    return _household_of_link(db, link)[0]


def _household_of_link(db, link: ExternalOrderLink
                       ) -> tuple[Optional[dict[str, Any]], list[ExternalOrderLink]]:
    """:func:`_group_of_link` 의 본체 — 집과 **그 집을 만든 링크 행**을 함께 준다.

    링크 행까지 돌려주는 이유는 하나다: 폴링용 상태 조회
    (:func:`_fulfillment_state`)가 멤버의 ``triage_state`` 를 읽어야 하는데, 집만 받으면
    같은 링크를 한 번 더 조회하게 된다(조회 3회). 그루핑 규칙은 여기서도
    :func:`_group_queue` 하나뿐이다 — 규칙을 두 벌로 만들지 않는다.

    Args:
        db: 요청 스코프 DB 세션.
        link: 선택된 링크.

    Returns:
        ``(묶음(없으면 None), 주문번호로 읽은 링크 행 전부)``.
    """
    order_no = (link.external_order_no or "").strip()
    if order_no:
        rows = (
            db.query(ExternalOrderLink)
            .filter(ExternalOrderLink.channel == "NAVER",
                    ExternalOrderLink.external_order_no == order_no)
            .order_by(ExternalOrderLink.created_at.desc(), ExternalOrderLink.id.desc())
            .all()
        )
    else:
        rows = [link]
    order_ids = [int(row.order_id) for row in rows if row.order_id]
    orders = {}
    if order_ids:
        orders = {o.id: o for o in db.query(Order).filter(Order.id.in_(order_ids)).all()}
    groups = _group_queue(rows, orders, truncated=False)
    group = next((group for group in groups if link.id in group["link_ids"]), None)
    return group, rows


def _link_payment_amount(link: ExternalOrderLink) -> int:
    """상품주문 1건의 **결제 금액**(원). 못 읽으면 0 (T9).

    승인 모달이 "무엇에 얼마가 걸려 있나"를 줄로 재진술할 때 쓴다. 원본
    ``totalPaymentAmount`` 는 **결제 시점 값**이라 환불 예정액과 정확히 같지 않다
    (부분 환불·배송비) — 그래서 화면은 "환불액"이 아니라 **결제 금액**이라고 적는다.

    Args:
        link: 수집 링크.

    Returns:
        결제 금액(원). 값이 없거나 형식이 다르면 0.
    """
    from foms.services.integrations.naver_commerce.mapping import unwrap_detail

    # ``unwrap_detail`` 은 dict 가 아니면 빈 tuple 을 준다 — 예외를 안 던지므로 넓은
    # try 로 감싸지 않는다(로거 없는 broad catch 는 fail-open 인벤토리 게이트에 걸린다).
    _, product_order, _ = unwrap_detail(link.raw_snapshot or {})
    amount = (product_order or {}).get("totalPaymentAmount")
    return int(amount) if isinstance(amount, int) else 0


def _fulfillment_state(db, link: ExternalOrderLink) -> dict[str, Any]:
    """집의 **워커 처리 표식**만 요약한다 — 화면 판정은 하지 않는다.

    web 라우트는 큐에 넣고 바로 답한다(네이버 HTTP 는 WORKER 단일 출구). 그래서 버튼을
    누른 직후의 화면은 아직 옛 상태다. 화면이 "언제 뒤집혔는지" 알려면 물어볼 곳이
    있어야 하는데, 그 자리에서 ``can_confirm``·``can_dispatch`` 같은 **판정을 다시 만들면
    모집단이 두 벌이 된다**(v3 리뷰 H1 이 그 갈라짐에서 나왔다). 여기서는 워커가 쓴 원시
    표식과 그 지문만 돌려주고, 무엇을 눌러도 되는지는 :func:`_pane_context` 가 그대로
    혼자 정한다.

    집 정의도 :func:`_household_of_link`(주문번호 + ``household_key``)를 그대로 쓴다 —
    모달이 재진술하는 집과 폴링이 보는 집이 갈리면 안 된다(계약 §0-2).

    Args:
        db: 요청 스코프 DB 세션.
        link: 기준 링크(이 링크가 속한 **집 전체**를 센다).

    Returns:
        ``link_id``·``total``·``confirmed``·``dispatched``·``canceled``·``returned``·
        ``last_error``·``last_error_at``·``last_error_action``·``action_label``·``rev``.
        ``rev`` 는 표식 지문이다 — 성공이든 실패든 표식이 바뀌면 값이 바뀐다(워커는 성공
        시 ``last_error*`` 를 지우므로 그것도 변화다). ``hash()`` 는 쓰지 않는다
        (PYTHONHASHSEED 로 프로세스마다 달라져 워커·웹 사이에서 못 쓴다).
    """
    group, rows = _household_of_link(db, link)
    member_ids = set(group["link_ids"]) if group else {link.id}
    members = sorted((row for row in rows if row.id in member_ids), key=lambda row: row.id)
    if not members:
        members = [link]
    marks: list[str] = []
    confirmed = dispatched = canceled = returned = 0
    last_error = last_error_at = last_error_action = ""
    for row in members:
        state = (row.triage_state or {}).get("fulfillment") or {}
        at_confirm = str(state.get("place_confirmed_at") or "")
        at_dispatch = str(state.get("dispatched_at") or "")
        at_cancel = str(state.get("canceled_at") or "")
        at_error = str(state.get("last_error_at") or "")
        confirmed += 1 if at_confirm else 0
        dispatched += 1 if at_dispatch else 0
        canceled += 1 if at_cancel else 0
        returned += 1 if ((row.triage_state or {}).get("return") or {}).get("requested_at") else 0
        # 형제마다 따로 실패할 수 있다(발송처리는 건별로 성공/실패한다) — 가장 최근 것을
        # 대표로 보인다. 사유를 삼키지 않는 자리는 전체 렌더의 실패 띠가 계속 맡는다.
        if at_error and at_error > last_error_at:
            last_error_at = at_error
            last_error = str(state.get("last_error") or "")
            last_error_action = str(state.get("last_error_action") or "")
        # 다시 읽기(T4)는 fulfillment 표식을 하나도 안 건드린다 — 그 축(`claim_sync`)의
        # 시각을 지문에 함께 넣어야 화면이 "다시 읽기가 끝났다"를 볼 수 있다. 안 넣으면
        # 눌러도 화면이 영원히 안 바뀐다(사용자에게는 "아무 일도 안 일어남"으로 보인다).
        at_sync = str(((row.triage_state or {}).get("claim_sync") or {}).get("refreshed_at") or "")
        # 반품 접수(T8-S1)는 **다른 축**(`triage_state['return']`)에 찍힌다 — 여기 안 넣으면
        # 접수 버튼을 눌러도 지문이 안 바뀌어 화면이 영원히 "아직 안 끝났다"로 폴링한다.
        # 새 엔드포인트를 만들지 않는 이유이기도 하다(다시 읽기가 `claim_sync` 로 한 수법).
        at_return = str(((row.triage_state or {}).get("return") or {}).get("requested_at") or "")
        # 승인·거부(T8-S2/S3·T9)도 **또 다른 축**이다. 승인은 접수 표식을 안 찍고,
        # 거부는 반품 축의 다른 키에 찍는다 — 지문에 안 넣으면 버튼을 눌러도 화면이
        # 타임아웃까지 "기다리는 중"으로 남는다. 자동 다시 읽기에 기대면 안 된다:
        # 그 경로는 큐가 없으면 로그만 남기는 fail-open 이다.
        return_axis = (row.triage_state or {}).get("return") or {}
        cancel_axis = (row.triage_state or {}).get("cancel") or {}
        at_claim = "{0}~{1}~{2}".format(
            str(return_axis.get("approved_at") or ""),
            str(return_axis.get("rejected_at") or ""),
            str(cancel_axis.get("approved_at") or ""))
        marks.append(
            f"{row.id}|{at_confirm}|{at_dispatch}|{at_cancel}|{at_error}|{at_sync}"
            f"|{at_return}|{at_claim}")
    action = last_error_action.strip().lower()
    action = action if action in FULFILLMENT_ACTION_LABELS else ""
    return {
        "link_id": link.id,
        "total": len(members),
        "confirmed": confirmed,
        "dispatched": dispatched,
        "canceled": canceled,
        # 반품 접수가 나간 상품주문 수 — 화면이 "접수 끝났다"를 말하는 근거다.
        "returned": returned,
        "last_error": last_error,
        "last_error_at": last_error_at,
        "last_error_action": action,
        "action_label": FULFILLMENT_ACTION_LABELS.get(action, ""),
        "rev": hashlib.sha1(";".join(marks).encode("utf-8")).hexdigest()[:16],
    }


#: 벌크 진행 조회가 한 번에 볼 수 있는 집(대표 링크) 수 상한. 화면 목록 캡
#: (:data:`WORK_GROUP_LIMIT`)과 같은 수 — 벌크 대상은 정의상 화면 목록의 부분집합이다
#: (계약 §0-5). 넘어오면 자른다(조용히 늘어난 요청으로 조회가 커지지 않게).
PROGRESS_LINK_ID_LIMIT = WORK_GROUP_LIMIT


def _fulfillment_progress(db, link_ids: list[int]) -> dict[str, Any]:
    """벌크 대상 **집들 전체**의 발주확인 진행 상황 — 조회 2회(집 수와 무관).

    집마다 따로 물으면 조회가 집 수만큼 곱해진다(33집 × 30회 폴링 × 2 = 1980회).
    nav 뱃지 부하 실측(2026-08-24)에서 이 화면의 조회 비용이 이미 드러난 터라, 벌크는
    묶음키 SSOT(:func:`grouping.group_key_expression`)로 **한 번에** 걷는다.

    남은 건수 술어는 :func:`fulfillment.is_place_pending` **하나**다 — 모달이 재진술한
    건수와 같은 술어여야 "상품주문 119건 중 47건 완료"가 거짓이 되지 않는다(계약 §0-2).
    여기서도 화면 판정(무엇을 눌러도 되는지)은 하지 않는다.

    Args:
        db: 요청 스코프 DB 세션.
        link_ids: 벌크로 보낸 집들의 대표 링크 id.

    Returns:
        ``links``(대상 상품주문 수)·``place_pending``(아직 발주확인 남은 수)·
        ``failed_links``·``last_error``·``rev``.
    """
    from sqlalchemy import distinct

    from foms.services.integrations.naver_commerce.fulfillment import is_place_pending
    from foms.services.integrations.naver_commerce.grouping import group_key_expression

    empty = {"links": 0, "place_pending": 0, "failed_links": 0, "last_error": "", "rev": ""}
    if not link_ids:
        return empty

    gk = group_key_expression()
    keys = [row[0] for row in
            db.query(distinct(gk)).filter(ExternalOrderLink.id.in_(link_ids)).all()]
    if not keys:
        return empty
    rows = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.channel == "NAVER", gk.in_(keys))  # perf-ok: 묶음키 IN 배치
        .order_by(ExternalOrderLink.id)
        .all()
    )

    marks: list[str] = []
    pending = failed = 0
    last_error = last_error_at = ""
    for row in rows:
        state = (row.triage_state or {}).get("fulfillment") or {}
        at_error = str(state.get("last_error_at") or "")
        if is_place_pending(row):
            pending += 1
        if str(state.get("last_error") or "").strip():
            failed += 1
            if at_error > last_error_at:
                last_error_at = at_error
                last_error = str(state.get("last_error") or "")
        marks.append(f"{row.id}|{state.get('place_confirmed_at') or ''}|{at_error}")
    return {
        "links": len(rows),
        "place_pending": pending,
        "failed_links": failed,
        "last_error": last_error,
        "rev": hashlib.sha1(";".join(marks).encode("utf-8")).hexdigest()[:16],
    }


def _member_claim_view(link: ExternalOrderLink) -> dict[str, Any]:
    """상품주문 **1건**의 클레임·반품 상태 — 라인 표의 칸이 읽는 값 (NVCLAIM-ORDER-01 2차).

    이 칸이 없던 시절 어느 화면도 "이 집 4건 중 무엇이 반품됐고 무엇이 안 됐나"를 답하지
    못했다. 집 배지는 집계 하나였고 pane 의 반품 축(:func:`_return_axis_view`)은 **펼친
    링크 1건**만 봤다 — 황민철 집(ERP 5026)이 추가상품 3건만 환불된 채로 `반품 완료` 로
    읽힌 자리다.

    **코드가 판정 축이고 라벨은 표시 축이다**(``order_candidates.py`` CLAIM_CODE_LABELS
    주석, 2026-08-28). 그래서 화면이 분기할 값은 전부 여기서 **불리언으로** 굳혀 내보낸다 —
    템플릿이 ``claim_label`` 같은 한국어 문자열을 ``==`` 로 비교하면 낱말 한 번 손보는
    순간 분기가 조용히 죽는다.

    ``return_requested_at`` 은 **우리가 보낸 접수**다. 네이버가 말하는 상태
    (``claim_*``)와 **다른 사실**이라 한 칸에 합치지 않는다 — 이번 사고는 정확히 그 둘의
    틈이었다(우리는 4건 다 보냈다고 믿었고 네이버는 3건만 받았다).

    Args:
        link: 그 상품주문의 링크(**추가 조회 없음** — 이미 읽어 둔 원본만 판다).

    Returns:
        ``is_addon``(:func:`mapping.is_addon_detail` — 클레임 호출 순서를 가르는 축) ·
        ``claim_code``(네이버 원문 대문자, 없으면 빈 문자열) · ``claim_label`` ·
        ``claim_blocking`` · ``claim_pending``(확정 전) · ``return_requested_at``(KST).
    """
    from foms.services.integrations.naver_commerce.mapping import (
        CLAIM_PHASE_PROGRESS,
        CLAIM_PHASE_REQUESTED,
        extract_claim,
        is_addon_detail,
    )

    snapshot = link.raw_snapshot or {}
    claim = extract_claim(snapshot)
    ours = (link.triage_state or {}).get("return") or {}
    return {
        "is_addon": is_addon_detail(snapshot),
        "claim_code": str(claim["status"] or "").upper(),
        "claim_label": claim["label"],
        "claim_blocking": bool(claim["blocking"]),
        # 요청·처리중 = 네이버가 아직 확정하지 않았다. `반품 요청` 과 `반품 완료` 를
        # 같은 색으로 칠하면 환불 전 건이 끝난 것으로 읽힌다(2026-08-28 유령 사고).
        "claim_pending": claim["phase"] in (CLAIM_PHASE_REQUESTED, CLAIM_PHASE_PROGRESS),
        "return_requested_at": _dispatch_time_text(ours.get("requested_at")),
        # 접수 **실패** 기록(T3). `last_error` 와 다른 축이다 — 그쪽은 사람이 `확인함`
        # 으로 닫는 통지고, 이쪽은 닫아도 남는 사실이다. 이 칸이 없으면 띠를 닫은 뒤
        # "이 본품은 반품 접수가 실패한 채다"를 말하는 화면이 다시 0곳이 된다.
        "return_failed_at": _dispatch_time_text(ours.get("failed_at")),
        "return_failed_reason": str(ours.get("failed_reason") or ""),
    }


def _member_rows(db, selected_group: Optional[dict]) -> list[dict[str, Any]]:
    """선택한 집의 **상품주문 행 단위** 목록 (설계 결정 5·7).

    네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 준다. 예전 화면은 pane 이
    링크 1건이라 6건 묶음을 다 보려면 페이지를 6번 열어야 했다. 여기서 한 번에 편다.

    대조표를 2단으로 나누는 이유도 같다 — 집 단위 값(수취인·주소·결제)과 상품주문 행
    단위 값(옵션 원문·금액)은 단위가 다르다. 한 표에 섞으면 "네이버 1건 vs FOMS 묶음
    합계"로 어긋난다(03 감사 결함 #7).

    Args:
        db: 요청 스코프 DB 세션.
        selected_group: :func:`_group_queue` 가 만든 묶음(없으면 빈 목록).

    Returns:
        상품주문 행 목록(대표 먼저). 옵션 원문은 **자르지 않는다** — 사람이 이걸 보고
        규격을 채운다(도메인 규칙 6). ``partial_cancel`` 은 부분취소 잔여
        (:func:`extract_partial_cancel`) — ``is_partial`` 인 행만 화면이 원래 수량을 낸다.
    """
    from foms.services.integrations.naver_commerce.mapping import extract_partial_cancel

    if not selected_group:
        return []
    link_ids = list(selected_group.get("link_ids") or [])
    if not link_ids:
        return []
    links = {
        row.id: row
        for row in db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id.in_(link_ids))  # perf-ok: 한 집(최대 십수 건) batch
        .all()
    }
    rows: list[dict[str, Any]] = []
    for member in selected_group.get("members") or []:
        link = links.get(member["id"])
        if link is None:
            continue
        summary = summarize_snapshot(link.raw_snapshot)
        rows.append({
            "link_id": link.id,
            "external_id": link.external_id,
            "product": summary["product"],
            "options": summary["options"],
            "quantity": summary["quantity"],
            "amount": summary["amount"],
            "is_lead": member.get("is_lead", False),
            "place_confirmed": summary["place_confirmed"],
            # 쿠폰(2026-08-25) — 금액 옆에서 같이 읽혀야 하는 사실이다.
            "coupon_known": summary["coupon_known"],
            "coupon_count": summary["coupon_count"],
            "coupon_discount": summary["coupon_discount"],
            "coupon_seller_burden": summary["coupon_seller_burden"],
            # 부분취소 잔여(F-3) — 한 집에서 일부만 취소되면 지금 수량이 "원래 몇 개였는지"
            # 를 화면이 말하지 못했다. **초기값과 잔여값이 실제로 다른 행에서만** 낸다
            # (281/281 이 이 필드를 갖고 있어 존재 여부로 판정하면 전부 부분취소로 보인다).
            "partial_cancel": extract_partial_cancel(link.raw_snapshot or {}),
            # 라인별 클레임·반품 칸(NVCLAIM-ORDER-01 2차). 집 배지·집 반품 축과 **단위가
            # 다르다** — 이 표만이 "4건 중 어느 것이 안 됐나"를 말할 수 있다.
            **_member_claim_view(link),
        })
    return rows


def _coupon_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """집 전체의 쿠폰 합계 — 상세 머리에서 한 줄로 말하기 위한 값 (2026-08-25).

    행마다 따로 보면 "이 집에 쿠폰이 붙었나"를 사람이 암산해야 한다. 집이 6건씩 오는
    화면이라 그 암산이 실제로 안 된다.

    Args:
        rows: :func:`_member_rows` 결과.

    Returns:
        ``known``(전 행의 원본을 읽었는가) · ``count`` · ``discount`` · ``seller_burden``.
        한 행이라도 못 읽었으면 ``known=False`` 다 — 부분 합계를 전체인 양 말하지 않는다.
    """
    if not rows:
        return {"known": False, "count": 0, "discount": 0, "seller_burden": 0}
    return {
        "known": all(row.get("coupon_known") for row in rows),
        "count": sum(int(row.get("coupon_count") or 0) for row in rows),
        "discount": sum(int(row.get("coupon_discount") or 0) for row in rows),
        "seller_burden": sum(int(row.get("coupon_seller_burden") or 0) for row in rows),
    }


def _dispatched_count(links: list[ExternalOrderLink]) -> int:
    """이 링크들 중 **이미 발송처리가 나간** 상품주문 수.

    발송 표식은 링크(상품주문)마다 찍힌다 —
    :func:`fulfillment.dispatch_order` 가 건별로 성공/실패하기 때문에 한 집이
    "3건 중 2건만 나간" 상태로 남을 수 있다. 화면이 이 사실을 집 단위로 세지 않으면
    어느 형제로 상세를 열었느냐에 따라 취소 버튼이 있기도 없기도 한다(리뷰 M-4).

    Args:
        links: 한 집의 링크 목록.

    Returns:
        ``dispatched_at`` 표식이 있는 링크 수.
    """
    return sum(1 for row in links
               if ((row.triage_state or {}).get("fulfillment") or {}).get("dispatched_at"))


def _dispatched_any(links: list[ExternalOrderLink]) -> bool:
    """이 집에서 **하나라도 발송이 나갔나** — 취소/반품 갈래를 가르는 값.

    :func:`_dispatched_count` 와 달리 **신호를 둘 본다.** 우리 표식만 세면 판매자센터에서
    사람이 직접 발송한 집을 못 본다 — 그 집에서 화면은 취소 버튼을 열어 주고 반품 버튼은
    안 냈다. 정작 같은 화면의 정리 띠·관계 블록은 네이버 원본을 읽어 그 집을 "반품 건"
    이라고 부르고 있었다(2026-09-01 사용자 신고).

    서비스 쪽은 이미 두 신호를 본다 — :func:`fulfillment.is_return_pending`,
    ``dispatch_order``, ``_approve_returns``. 취소만 우리 표식뿐이었고 이 함수가 그 축을
    화면에서 맞춘다(``cancel_order`` 도 같은 날 두 신호로 고쳤다).

    Args:
        links: 한 집의 링크 목록.

    Returns:
        우리 표식이든 네이버 원본이든 발송 흔적이 하나라도 있으면 True.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        _naver_dispatched_at,
    )

    return any(((row.triage_state or {}).get("fulfillment") or {}).get("dispatched_at")
               or _naver_dispatched_at(row)
               for row in links)


def _group_queue(links: list[ExternalOrderLink], orders: dict,
                 *, truncated: bool, limit: Optional[int] = None) -> list[dict[str, Any]]:
    """확인 대기 링크를 **한 집 = 한 줄**로 묶는다 (T14-C).

    네이버는 본품과 구성 옵션을 각각 다른 상품주문으로 준다. 링크 1건 = 1행으로 두면
    같은 사람 이름이 3~4번 반복돼 몇 집이 밀렸는지 세지 못한다. 묶음 판정은 주문 생성과
    **같은 키**(:func:`mapping.group_key`)를 쓴다 — 화면과 실제 생성 결과가 갈리면
    "한 줄인데 주문 2건" 같은 사고가 난다.

    대표(본품)는 금액 최대 건이다(``map_group`` 규칙과 동일 — 0원 구성이 대표가 되면
    목록에 길이추가 옵션이 제목으로 뜬다).

    Args:
        links: 확인 대기 링크(최신순).
        orders: ``{order_id: Order}`` — FOMS 현재 값 우선 표시용.
        truncated: 조회 상한에 걸렸는지. 걸렸으면 마지막 묶음은 잘렸을 수 있어 버린다.
        limit: 돌려줄 묶음 수 상한(기본 :data:`PAGE_SIZE`). 호출자가 잘림을 알아채려면
            ``PAGE_SIZE + 1`` 을 주고 길이를 보면 된다.

    Returns:
        묶음 목록(최신 수집순). 각 항목은 대표 정보 + 구성 링크 목록.
    """
    # 집 키는 워커와 **같은 함수**로 만든다. 예전에는 여기서 group_key 를 직접 부르고
    # 실패 폴백을 따로 적어 뒀는데, `household_key` 에만 있던 두 번째 폴백(키가 통째로
    # 비면 링크 단독으로 센다)이 화면에는 없었다 — 서로 다른 빈 원본이 화면에서만 한 집으로
    # 붙어 보이고 워커는 따로 처리하는 갈라짐이었다(리뷰 L-1). 폴백을 한 벌만 둔다.
    from foms.services.integrations.naver_commerce.fulfillment import (
        addon_return_gap,
        household_exchange_in_flight,
        household_key,
        is_cancel_approvable,
        is_dispatch_pending,
        is_place_pending,
        is_return_approvable,
        is_return_pending,
        is_return_rejectable,
        return_sendable,
    )
    from foms.services.integrations.naver_commerce.mapping import extract_claim

    groups: dict[tuple, list[ExternalOrderLink]] = {}
    order_of_key: list[tuple] = []
    for link in links:
        key = household_key(link)
        if key not in groups:
            groups[key] = []
            order_of_key.append(key)
        groups[key].append(link)

    if truncated and order_of_key:
        # 상한에 걸리면 마지막 묶음은 구성 일부만 실려 왔을 수 있다 — 반쪽을 보여주느니 뺀다.
        order_of_key.pop()

    queue: list[dict[str, Any]] = []
    for key in order_of_key[:(limit if limit is not None else PAGE_SIZE)]:
        members = groups[key]
        lead = max(members, key=lambda row: (summarize_snapshot(row.raw_snapshot)["amount"] or 0,
                                             -row.id))
        order = orders.get(int(lead.order_id or 0))
        lead_summary = summarize_snapshot(lead.raw_snapshot)
        rest = [row for row in members if row.id != lead.id]
        # summarize_snapshot 은 원본 JSON 을 푸는 일이라 공짜가 아니다 — 멤버당 1회만 부르고
        # 아래 표식(클레임·발주)들이 같은 결과를 나눠 쓴다.
        ordered_summaries = [summarize_snapshot(row.raw_snapshot) for row in [lead, *rest]]
        member_summaries = ordered_summaries
        # 집 배지는 **집계**다(T5). 재료는 표시 순서(대표 먼저) 그대로 — 부분 상태가 아닐 때
        # 되돌아갈 라인 라벨이 예전 first-non-empty 값과 같아야 한다.
        household_claim = _household_claim(
            [extract_claim(row.raw_snapshot or {}) for row in [lead, *rest]],
            fallback_label=next((s["claim_label"] for s in member_summaries
                                 if s["claim_label"]), ""))
        dispatched_n = _dispatched_count(members)
        # 발송처리가 **실제로 나갈** 건수. 술어는 서버와 한 벌
        # (:func:`fulfillment.is_dispatch_pending` — 우리 표식 + 네이버 원본 sendDate).
        # `member_count - dispatched_count` 로 재진술하면 판매자센터에서 사람이 직접 보낸
        # 형제를 안 빼서 "3건 보냅니다"라고 읽히는데 서버는 1건만 보낸다. 불가역 경로의
        # 과대 진술이라 그 자체가 사고다(설계서 2026-08-29 §7-E).
        dispatch_pending_n = sum(1 for row in members if is_dispatch_pending(row))
        queue.append({
            "id": lead.id,
            # 묶음키 그대로 — 호출자가 이 집에 다른 판정(형제까지 본 클레임 등)을 붙일 때 쓴다.
            "key": key,
            "external_id": lead.external_id,
            # 네이버 주문번호 — 목록에서 집을 찾는 유일한 확실한 열쇠다(화면 글자에는
            # 안 나오고 '주문 #N' 배지는 FOMS 주문 id 라 서로 다른 번호다).
            "external_order_no": lead.external_order_no or "",
            # 목록은 접수순 정렬이라 **날짜·시각**은 필요하지만 초와 연도는 아무 결정도
            # 바꾸지 않는다. 이름 줄 오른쪽에 붙는 값이라 19자를 그대로 쓰면 긴 고객명이
            # 잘린다(2026-08-23 CEO 검수). 상세·이력 표의 시각 표기는 그대로 둔다.
            "created_at": format_datetime_kst(lead.created_at, "%m-%d %H:%M"),
            # 정렬 전용 원본 시각. 화면 문자열("%m-%d %H:%M")로 정렬하면 **연말에 뒤집힌다**
            # (12-31 > 01-02). 렌더에는 쓰지 않는다.
            "created_sort": lead.created_at,
            "customer_name": (getattr(order, "customer_name", None)
                              or lead_summary["customer_name"]),
            "product": lead_summary["product"],
            "order_id": lead.order_id,
            "sync_status": lead.sync_status,
            "count": len(members),
            "extra_count": len(rest),
            # 집 배지는 **집계**다(T5, NVCLAIM-ORDER-01). 예전에는 첫 라벨을 그대로 썼고,
            # 4건 중 3건만 반품된 집이 `반품 완료` 로 떠서 담당자가 집을 끝난 것으로 읽었다
            # (2026-09-01 황민철 — 본품 1건 미환불). 판정은 ``claim_code`` 로 한다.
            "claim_label": household_claim["claim_label"],
            "claim_code": household_claim["claim_code"],
            "claim_kind": household_claim["claim_kind"],
            "claim_blocking": any(s["claim_blocking"] for s in member_summaries),
            # 발주확인은 상품주문 단위다 — 하나라도 남아 있으면 그 집은 "발주확인 전"이다(T16-A).
            "place_pending": any(not _place_view(row)["confirmed"] for row in members),
            # 관계 축(추가결제·재결제) — 이 값은 **배지 라벨**이다. 붙이기는 집 전체를 함께
            # 붙이지만(attach_link_to_order) 백필 전 데이터는 형제 일부만 값이 있을 수 있어
            # 멤버 전체를 본다. 둘이 섞이면 ADDON 을 대표로 적는다 — **표기 우선순위일 뿐**
            # 버튼 동작은 바꾸지 않는다(옛 주석은 "ADDON 이 더 강한 제약"이라 했는데,
            # close_now 대상이 ADDON 뿐이라 사실이 아니다 — D1 개정 2026-08-24).
            # 아래 close_now 는 **집 전체**를 보므로 섞인 집은 어차피 close_now 가 아니다.
            "relation": ("ADDON" if any((row.relation or "") == "ADDON" for row in members)
                         else next((row.relation for row in members
                                    if (row.relation or "") == "REPAY"), "")),
            # 발주확인 전에도 발송처리 버튼을 열지 여부는 **집 전체가** CLOSE_NOW_RELATIONS 일
            # 때만이다(서버 dispatch_order 와 **같은 상수·같은 all 규칙** — any 로 두면
            # 섞인 집의 NEW 형제까지 발주확인 없이 나간다). 튜플을 여기 손으로 다시 적으면
            # 다음 개정에서 서버와 화면이 조용히 갈린다 — 실제로 갈릴 뻔했다(D1 개정
            # 2026-08-24: REPAY 를 뺄 때 이 자리가 하드코딩이었다).
            "close_now": all((row.relation or "").upper() in CLOSE_NOW_RELATIONS
                             for row in members),
            # 우리가 취소한 집은 더 손대지 않는다 — 버튼·모달·발주확인 전 탭에서 함께 뺀다.
            "canceled": any(((row.triage_state or {}).get("fulfillment") or {}).get("canceled_at")
                            for row in members),
            # 발송처리는 **상품주문(링크)마다** 찍힌다 — 워커가 건별로 성공/실패해서 한 집이
            # 부분 발송으로 남을 수 있다. pane 이 링크 1건의 표식만 보면 어느 형제로 열었느냐에
            # 따라 취소 버튼이 있기도 없기도 한다(리뷰 M-4). 판정을 집 단위로 한 번만 한다.
            #  · dispatched      = 집 전체가 나갔다(워커 dispatch_order 가 전부 skip 하는 상태)
            #  · dispatched_any  = 하나라도 나갔다(취소는 이 순간부터 반품 흐름 — 서버가 거절한다)
            "dispatched_count": dispatched_n,
            # `dispatched` 는 **우리가 다 보냈나**로 남긴다(2026-09-02 재확인). 두 신호로
            # 바꾸면 판매자센터가 보낸 집이 초록 '발송처리 완료' 배지로 덮이고, 잠금 사유
            # (누가·언제 보냈나 + "판매자센터에서 확인하세요")를 말하던 자리가 사라진다 —
            # 그 문장이 2026-08-26 T5 의 결과물이다. 네이버 신호는 `naver_sent_at`(잠금)과
            # `dispatch_pending_count`(건수)가 각각 맡는다.
            "dispatched": dispatched_n == len(members) and bool(members),
            # 갈래 판정은 **두 신호**다(우리 표식 + 네이버 원본) — `dispatched_count` 는
            # "우리가 눌러서 나간 수"라 뜻이 다르다. 섞으면 발송처리 모달 재진술이 흔들린다.
            "dispatched_any": _dispatched_any(members),
            # 모달 재진술이 읽는 값(위 계산 자리의 주석 참조) — 화면이 약속하는 건수는
            # 서버가 보낼 건수와 **같은 술어**에서 나온다.
            "dispatch_pending_count": dispatch_pending_n,
            # 주문 만들기가 **실제로 옮길** 형제 수. 집 전체 수(count)로 재진술하면 이미
            # 주문이 붙은 형제까지 세어 "3건을 주문 1건으로" 라고 읽히는데 서버는 2건만
            # 옮긴다(리뷰 M-2). 술어는 promotion 모듈 한 벌을 그대로 쓴다.
            "promotable_count": sum(1 for row in members if is_promotable(row)),
            # 발주확인이 **실제로 나갈** 건수. 서버 confirm_place_order 는 이미 확인된
            # 형제를 빼고 보낸다 — 집 전체 수로 재진술하면 과대 진술이 된다(계약 §0-2).
            "place_pending_count": sum(1 for row in members if is_place_pending(row)),
            # 반품 접수가 **실제로 나갈** 건수(T8-S1). 술어는 서버와 한 벌
            # (:func:`fulfillment.is_return_pending`) — 부분 발송 집에서 집 전체 수로
            # 재진술하면 "3건 반품 접수합니다"라고 읽히는데 서버는 나간 1건만 보낸다.
            # **불가역 경로라 그 과대 진술이 그대로 사고다**(2026-08-27 CEO 지적).
            "return_pending_count": sum(1 for row in members if is_return_pending(row)),
            # 반품 접수가 **정말 나갈** 건수(T6). ``return_pending_count`` 와 다르다 —
            # 그쪽은 우리 표식만 보는 멱등 판정이라, 형제가 이미 클레임에 걸려 서버
            # 라인 가드가 거절할 건까지 센다. 버튼·모달은 **이 값**에 건다
            # (:func:`fulfillment.return_sendable` — 서버와 한 벌).
            "return_sendable_count": sum(1 for row in members if return_sendable(row)),
            # 진행 중인 교환이 있는 집은 반품을 보내지 않는다(안전측). 화면 술어를
            # ``claim_blocking`` 으로 대신하면 안 된다 — 그쪽은 ``BLOCKING_CLAIM_STATUSES``
            # 라 ``EXCHANGE_*`` 를 담지 않아 서버보다 느슨하다(mapping.py:429).
            "exchange_in_flight": household_exchange_in_flight(members),
            # **범위 규격**(판매자센터 FAQ 3880, 감사 F2): 본품을 반품하려면 그 집의
            # 추가구성상품이 전부 처리돼 있어야 한다. 서버는 이 조건이 깨지면 한 건도
            # 안 보내고 거절하므로(:func:`fulfillment.addon_return_gap`), 화면도 같은
            # 술어로 버튼을 닫는다 — 갈리면 열린 버튼이 예외를 받는다. 대상 범위는
            # 서버가 고르는 것과 같은 술어(`return_sendable`)로 만든다.
            "return_scope_gap": [row.external_id for row in addon_return_gap(
                members, [row for row in members if return_sendable(row)])],
            # 거부가 **실제로 나갈** 건수(T8-S3). 접수와 같은 규율로 서버 술어
            # (:func:`fulfillment.is_return_rejectable`)를 그대로 쓴다 — 보류 걸린 건과
            # 이미 처리한 건은 여기서 빠진다.
            "return_rejectable_count": sum(1 for row in members if is_return_rejectable(row)),
            # 승인이 **실제로 나갈** 건수(T9). 거부와 같은 규율로 서버 술어를 그대로 쓴다.
            # 반품 승인은 ``return_awaiting_approval`` 이 아니라 이 술어에 건다 — 그 목록은
            # **우리가 접수한 건**만 담아서, 고객이 먼저 낸 반품(독립 승인의 주 대상)이
            # 통째로 빠진다.
            "cancel_approvable_count": sum(1 for row in members if is_cancel_approvable(row)),
            "return_approvable_count": sum(1 for row in members if is_return_approvable(row)),
            # 모달이 **건수가 아니라 목록**을 재진술한다(CEO 판정 2026-09-01). 집 하나에
            # 상품주문이 여럿이고 이 프로젝트는 집 묶기에서 이미 데였다 — "3건"만 쓰면
            # 살아 있어야 할 라인이 섞여도 사람이 못 본다. 금액은 결제 시점 값이라
            # 환불 예정액과 정확히 같지는 않다(부분 환불·배송비) — 그래서 화면이
            # "결제 금액"이라고 적는다.
            "cancel_approve_targets": [
                {"external_id": row.external_id,
                 "amount": _link_payment_amount(row)}
                for row in members if is_cancel_approvable(row)],
            "return_approve_targets": [
                {"external_id": row.external_id,
                 "amount": _link_payment_amount(row)}
                for row in members if is_return_approvable(row)],
            # 이미 우리가 접수한 건수 — 버튼을 닫고 "접수함"을 말하는 근거.
            "return_requested_count": sum(
                1 for row in members
                if ((row.triage_state or {}).get("return") or {}).get("requested_at")),
            # 승인까지 끝난 건수 (T8-S2).
            "return_approved_count": sum(
                1 for row in members
                if ((row.triage_state or {}).get("return") or {}).get("approved_at")),
            # **접수는 됐는데 승인이 안 된 건** — 이 상태가 제일 위험하다. 아무도 말 안 하면
            # 환불이 안 나간 채 잊힌다. 사유(보류·상태 미도달·호출 실패)를 함께 낸다.
            "return_awaiting_approval": [
                {"external_id": row.external_id,
                 "reason": str((((row.triage_state or {}).get("return") or {})
                                .get("approve_skipped_reason")) or "")}
                for row in members
                if (((row.triage_state or {}).get("return") or {}).get("requested_at")
                    and not ((row.triage_state or {}).get("return") or {}).get("approved_at")
                    and (((row.triage_state or {}).get("return") or {})
                         .get("approve_skipped_reason")))
            ],
            # 주문 만들기 POST 가 나갈 링크. 대표(최고금액)가 **이미 주문을 가진** 집에서
            # 대표 id 로 보내면 promote_link_to_order 가 그 주문을 멱등 반환만 하고
            # 형제는 하나도 안 옮긴다 — 화면은 "N건을 옮깁니다" 라고 말한 뒤 0건이 움직인다
            # (2026-08-23 CEO 검수 상). 승격 대상 중 최고금액 건을 기준으로 보낸다.
            "promotable_lead_id": next(
                (row.id for row, _ in sorted(
                    ((row, summary) for row, summary in zip([lead, *rest], ordered_summaries)
                     if is_promotable(row)),
                    key=lambda pair: (pair[1]["amount"] or 0, -pair[0].id), reverse=True)),
                None),
            "shipping_due": next((s["shipping_due"] for s in member_summaries if s["shipping_due"]), ""),
            # CS 가 다음에 할 일을 목록에서 바로 알아보게 한다.
            "next_step": ("주문 만들기" if not lead.order_id
                          else ("규격 입력" if not order_has_spec_rows(order) else "")),
            "link_ids": [row.id for row in members],
            # 펼침 목록도 **대표 먼저** — 사람이 처음 보는 줄이 0원 구성 옵션이면 본품을
            # 찾아 헤맨다(map_group·도크와 같은 순서 규칙).
            "members": [
                {"id": row.id,
                 "product": summary["product"],
                 "place_confirmed": summary["place_confirmed"],
                 "is_lead": row.id == lead.id}
                for row, summary in zip([lead, *rest], ordered_summaries)
            ],
        })
    return queue


def _active_sales_users(db) -> list[dict[str, Any]]:
    """담당자로 지정 가능한 활성 SALES 사용자(보류함 계정 제외)."""
    from foms.services.integrations.naver_commerce.constants import OWNER_USERNAME
    from foms.services.orders.order_mutation_policy import normalize_team
    from models import User

    rows = db.query(User).filter(User.is_active.is_(True)).all()
    return [
        {"id": u.id, "name": u.name or u.username}
        for u in rows
        if normalize_team(u.team) == "SALES" and u.username != OWNER_USERNAME
    ]


@admin_bp.route("/admin/naver-ingest/<int:link_id>/create-order", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_create_order(link_id: int):
    """수집분 1건을 FOMS 주문으로 만든다 (T12 — 수집과 생성 분리).

    수집은 자동이지만 생성은 사람의 판단이다. 이 버튼이 그 판단 지점이다.
    ``promote_link_to_order`` 는 ``create_order()`` 만 경유하므로 owner 배정·quest seed·
    ``ORDER_CREATED`` 이벤트·GEOCODE outbox 예약이 기존 주문과 동일하게 붙는다.

    멱등: 이미 주문이 붙은 링크는 새로 만들지 않고 그 주문 id 를 그대로 돌려준다
    (버튼 두 번 클릭·새로고침 재전송 방어).
    """
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        promote_link_to_order,
    )

    db = get_db()
    try:
        from foms.services.integrations.naver_commerce.accounts import resolve_ingest_account_ids

        actor_user_id, owner_user_id = resolve_ingest_account_ids(db)
    except Exception as exc:  # noqa: BLE001 - 계정 문제는 사용자에게 사유를 그대로 보여준다
        logger.warning("[NAVER] 수집 계정 확인 실패 link=%s: %s", link_id, exc)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    try:
        order_id, created = promote_link_to_order(
            db, link_id=link_id, actor_user_id=actor_user_id, owner_user_id=owner_user_id,
        )
        db.commit()
    except PromotionError as exc:
        db.commit()  # 매핑 실패 시 PENDING_REVIEW 기록은 남긴다(원인 추적).
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 생성 실패 전체를 tx 되돌리고 사유 반환
        db.rollback()
        logger.warning("[NAVER] 수집분 주문 생성 실패 link=%s: %s", link_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 주문 생성 (link {link_id} → order {order_id})",
        session.get("user_id"),
        action="NAVER_INGEST_CREATE_ORDER",
        target_type="order", target_id=order_id,
        detail={"link_id": link_id, "order_id": order_id, "created": created},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": order_id, "created": created,
                             # CS 는 만들자마자 규격을 넣으러 간다 — 화면이 새 탭으로 열어준다.
                             "edit_url": url_for("order_edit.edit_order",
                                                 order_id=order_id, open="erp-order")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/refresh", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_refresh(link_id: int):
    """이 주문을 네이버에서 **다시 읽는다** — T4(읽기 전용).

    자동 스윕은 네이버가 **변경 이벤트를 줄 때만** 그 건을 다시 읽는다. 이벤트가 안 오는
    건은 자동 경로로 **영영** 못 잡는다(`claim_watch` 머리말이 "취소가 변경 목록에 어떤
    이름으로 실리는지 실물로 확인되지 않았다"고 적어 뒀다). 그 구멍을 사람이 손으로
    메우는 자리다. 5분을 안 기다려도 되는 것은 덤이다.

    **네이버에 쓰는 것은 없다** — 나가는 호출은 상세 조회뿐이다. 그래도 큐를 거치는 이유는
    발송처리와 같다: 커머스API 에 등록된 호출 IP 가 WORKER 것뿐이라 web 에서 내면 차단된다.

    "아무 일도 안 일어난다"는 아니다 — 새로 발견된 취소·반품은 담당자·관리자 알림으로
    나간다(:func:`claim_watch.refresh_household` 참조). 그게 이 버튼의 목적이라 확인 모달은
    두지 않지만, **문구가 그 사실을 숨기지 않는다**.

    Args:
        link_id: 기준 수집 링크 id(그 링크가 속한 **주문 전체**를 다시 읽는다).

    Returns:
        ``{"success": True, "data": {"link_id", "queued", "rev"}}``. ``rev`` 는 화면이
        폴링으로 비교할 기준 지문이다(:func:`_fulfillment_state`). 큐를 쓸 수 없으면 503.
    """
    from foms.services.jobs.queue import enqueue_naver_refresh

    # 기준 지문은 **enqueue 앞에서** 잡는다 — 뒤에서 잡으면 워커가 이미 끝냈을 때 화면이
    # 뒤집힘을 영원히 못 본다(발송처리와 같은 이유, 같은 자리).
    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        return jsonify({"success": False, "data": None,
                        "error": "수집분을 찾을 수 없습니다."}), 404
    base_state = _fulfillment_state(db, link)

    if not enqueue_naver_refresh(link_id, session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "잠시 후 다시 시도하세요."}), 503

    log_access(
        f"네이버 다시 읽기 요청 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_REFRESH_ENQUEUE",
        detail={"link_id": link_id},
    )
    return jsonify({"success": True,
                    # `err_at` 은 **누르기 직전의 실패 시각**이다. 화면이 이 값과 비교해야
                    # 옛 발주확인 실패가 남아 있는 주문에서 "다시 읽기 실패"라고 잘못
                    # 말하지 않는다 — `last_error` 는 명시적으로 지울 때까지 남는 값이다
                    # (2026-08-26 CEO 리뷰 B3).
                    "data": {"link_id": link_id, "queued": True,
                             "rev": base_state["rev"],
                             "err_at": base_state["last_error_at"]},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/refresh-all", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_refresh_all():
    """**수집된 집 전부**를 네이버에서 다시 읽는다 — NVREPAY-03(읽기 전용).

    단건 :func:`naver_ingest_refresh` 와 나가는 호출이 **같다**(상세 조회뿐, 네이버에
    쓰는 것 없음). 다른 점은 대상이 집 하나가 아니라 **수집 목록 전체**라는 것이다.

    왜 필요한가: 자동 스윕은 네이버가 변경 이벤트를 준 건만 다시 읽는다
    (:func:`claim_watch.refresh_claims`). 이벤트가 안 오는 집은 자동 경로로 **영영**
    안 갱신되고, 그러면 화면의 상태·금액·클레임이 낡은 채로 남는다. 단건 버튼은 그 집
    pane 에 서 있어야 눌러서, "지금 이 목록 전체가 진짜인가"를 확인할 방법이 없었다.

    **ADMIN 전용**이다. 한 번에 수십~수백 집의 상세 조회가 나가므로 '지금 수집'
    (:func:`naver_ingest_run_now`)과 같은 기준으로 묶는다. STAFF·MANAGER 는 각 집의
    `다시 읽기` 를 그대로 쓴다.

    **집 전부를 읽지는 않는다** — :func:`claim_watch.refreshable_household_link_ids` 가
    종결된 집(취소·반품 완료, 구매확정)과 쿨다운 안에 이미 읽은 집을 뺀다. 뺀 수는
    응답에 실어 화면이 말하게 한다(조용한 절단 금지).

    Returns:
        ``{"success": True, "data": {"count", "queued", "failed", "truncated",
        "skipped_done", "skipped_recent", "since"}}``. ``count`` 는 제외를 거친 대상 집
        수, ``queued`` 는 큐에 들어간 수, ``since`` 는 진행 조회
        (:func:`naver_ingest_refresh_progress`)가 기준으로 쓸 시각이다. 큐가 아예 막혀
        하나도 못 넣으면 503. 대상이 0이면 큐를 건드리지 않고 200 으로 그렇게 말한다.
    """
    from foms.services.integrations.naver_commerce.claim_watch import (
        REFRESH_ALL_AUDIT_ACTION,
        REFRESH_ALL_LIMIT,
        refreshable_household_link_ids,
    )
    from foms.services.jobs.queue import enqueue_naver_refresh

    db = get_db()
    # 큐에 넣기 **전에** 시각을 잡는다 — 뒤에 잡으면 그 사이에 끝난 집이 진행 조회에서
    # 안 끝난 것으로 보인다(폴링이 영원히 안 끝난다).
    since = now_utc_naive()
    link_ids, total, skipped = refreshable_household_link_ids(db, now=since)
    base = {"count": int(total),
            "skipped_done": int(skipped.get("done", 0)),
            "skipped_recent": int(skipped.get("recent", 0)),
            "since": since.isoformat()}
    if not link_ids:
        return jsonify({"success": True,
                        "data": {**base, "queued": 0, "failed": 0, "truncated": False,
                                 "link_ids": []},
                        "error": None})

    user_id = session.get("user_id")
    queued = [link_id for link_id in link_ids if enqueue_naver_refresh(link_id, user_id)]
    failed = len(link_ids) - len(queued)
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "잠시 후 다시 시도하세요."}), 503

    log_access(
        f"네이버 전체 다시 읽기 요청 ({len(queued)}집 / 대상 {total}집 · "
        f"종결 {base['skipped_done']}집·최근 {base['skipped_recent']}집 제외)",
        session.get("user_id"),
        # 이 행이 **남의 화면이 읽는 진행 상태의 유일한 원천**이다(NVREPAY-05 T1) —
        # 태그·`queued` 를 바꾸면 다른 관리자 화면이 조용히 빈손이 된다.
        action=REFRESH_ALL_AUDIT_ACTION,
        detail={"queued": len(queued), "total": total, "failed": failed,
                "skipped_done": base["skipped_done"],
                "skipped_recent": base["skipped_recent"]},
    )
    return jsonify({"success": True,
                    "data": {**base, "queued": len(queued), "failed": failed,
                             "truncated": total > REFRESH_ALL_LIMIT,
                             # 진행 조회가 물을 대상이다. 화면이 고른 게 아니라 **서버가
                             # 넣은 것**을 그대로 돌려준다 — 두 목록이 갈리면 진행률이
                             # 영원히 안 찬다.
                             "link_ids": queued},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/triage/refresh-progress")
@login_required
@role_required(["ADMIN"])
def naver_ingest_refresh_progress():
    """**전체 다시 읽기**가 어디까지 갔는지 — 읽기 전용 GET, 조회 1회.

    왜 필요한가: 버튼은 큐에 넣고 라벨만 `다시 읽는 중` 으로 바꿔 뒀고, 끝났는지는
    아무도 말하지 않았다. 사람은 그걸 **멈춘 걸로 읽는다**(2026-08-30 운영에서 실제로
    그렇게 읽혀 28초 만에 다시 눌렸다). 벌크 발주확인이 이미 같은 문제를 같은 모양으로
    풀어놨다(:func:`naver_ingest_fulfillment_progress`) — 그 배선을 그대로 따른다.

    판정을 두 벌로 만들지 않는다: 끝난 집의 정의는 "그 집의 상품주문이 ``since`` 이후에
    다시 읽혔다" 하나뿐이고, 시각은 워커가 :func:`claim_watch._refresh_link` 에서 쓰는
    ``claim_sync.refreshed_at`` 를 그대로 본다. 새 상태 저장소를 만들지 않는다.

    Query:
        ``link_ids``: 요청이 큐에 넣은 대표 링크 id(쉼표 구분, 최대
        :data:`PROGRESS_LINK_ID_LIMIT` 개).
        ``since``: 요청 응답이 준 ISO 시각.

    Returns:
        ``{"success": True, "data": {"total", "done", "pending"}}``. 게이트 OFF 는 404,
        인자 누락·형식 오류는 400.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.claim_watch import (
        refreshed_household_counts,
    )

    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 쓸 수 없습니다."}), 404
    ids = [int(chunk) for chunk in (request.args.get("link_ids") or "").split(",")
           if chunk.strip().isdigit()]
    raw_since = (request.args.get("since") or "").strip()
    if not ids or not raw_since:
        return jsonify({"success": False, "data": None,
                        "error": "link_ids·since 가 필요합니다."}), 400
    try:
        since = datetime.datetime.fromisoformat(raw_since)
    except ValueError:
        return jsonify({"success": False, "data": None,
                        "error": "since 형식이 올바르지 않습니다."}), 400
    if since.tzinfo is not None:
        since = since.replace(tzinfo=None)

    db = get_db()
    ids = ids[:PROGRESS_LINK_ID_LIMIT]
    # 대표 링크가 아니라 **그 집 전체**가 대상이다 — 워커는 형제 상품주문을 같이 읽고
    # `refreshed_at` 도 형제마다 찍힌다. 대표 하나만 보면 끝났는데 안 끝난 것으로 보인다.
    order_nos = [row[0] for row in
                 db.query(ExternalOrderLink.external_order_no)
                 .filter(ExternalOrderLink.id.in_(ids)).distinct().all()]
    if not order_nos:
        return jsonify({"success": True, "data": {"total": 0, "done": 0, "pending": 0},
                        "error": None})
    # 세는 규칙은 남의 화면(:func:`naver_ingest_refresh_running`)과 **같은 함수**다.
    done, total = refreshed_household_counts(db, since, order_nos=order_nos)
    return jsonify({"success": True,
                    "data": {"total": total, "done": done, "pending": total - done},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/triage/refresh-running")
@login_required
@role_required(["ADMIN"])
def naver_ingest_refresh_running():
    """**남이 눌러 놓은** 전체 다시 읽기가 돌고 있나 — 읽기 전용 GET (NVREPAY-05 T1).

    :func:`naver_ingest_refresh_progress` 는 자기가 방금 큐에 넣은 링크 id 를 들고 물어야
    답한다. 그래서 진행 표시가 **누른 브라우저 안에만** 있었다: 다른 관리자가 같은 목록을
    열면 돌고 있는 중인데도 `다시 읽기 45주문` 이라 적혀 있고, 그래서 또 누른다. 한 사람이
    28초 만에 두 번 눌러 낭비된 것과 같은 낭비를 두 사람이 낸다.

    인자 없이 묻는다 — 답은 감사 원장의 **가장 최근 요청**과 워커 스탬프로 만든다
    (:func:`claim_watch.running_refresh_all`). 새 상태 저장소는 없다.

    Returns:
        ``{"success": True, "data": {"running": bool, ...}}``. 돌고 있으면 ``actor``·
        ``total``·``done``·``pending``·``eta``·``elapsed_seconds`` 가 함께 온다.
        게이트 OFF 는 404.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.claim_watch import running_refresh_all

    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 쓸 수 없습니다."}), 404
    running = running_refresh_all(get_db())
    return jsonify({"success": True,
                    "data": {"running": bool(running), **(running or {})},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/origin-cleanup/refresh", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_origin_cleanup_refresh():
    """정리 대기 중인 **옛 주문 전부**를 네이버에서 다시 읽는다 — NVREPAY-02(읽기 전용).

    단건 :func:`naver_ingest_refresh` 와 나가는 호출이 **같다**(상세 조회뿐, 네이버에
    쓰는 것 없음). 다른 점은 대상을 사람이 고르지 않는다는 것이다 — 재결제를 붙인 뒤
    아직 살아 있는 옛 집을 **서버가 다시 세어서** 그 집들만 큐에 넣는다.

    **화면이 보낸 목록을 믿지 않는다.** 클라이언트가 link_id 를 실어 보내면 그 사이에
    정리된 집이나 남의 집을 읽게 할 수 있다. 목록은 여기서 새로 만든다.

    왜 필요한가: 옛 주문의 살아 있음 판정은 **우리 스냅샷**이 근거인데, 자동 스윕은
    네이버가 변경 이벤트를 준 건만 다시 읽는다. 이벤트가 안 오면 영영 낡은 채로 남고,
    화면은 이미 고객이 취소한 주문을 "살아 있습니다"라고 말한다. 불가역 버튼 앞에 서기
    전에 모집단 전체를 한 번에 최신화하는 자리다.

    Returns:
        ``{"success": True, "data": {"count", "queued", "failed"}}``.
        ``count`` 는 정리 대기 집 수, ``queued`` 는 큐에 들어간 수다. 큐가 아예 막혀
        있으면(하나도 못 넣음) 503.
    """
    from foms.services.integrations.naver_commerce.order_candidates import (
        pending_origin_cleanup,
    )
    from foms.services.jobs.queue import enqueue_naver_refresh

    db = get_db()
    pending = pending_origin_cleanup(db)
    link_ids = [int(row["link_id"]) for row in pending["rows"] if row.get("link_id")]
    if not link_ids:
        return jsonify({"success": True,
                        "data": {"count": 0, "queued": 0, "failed": 0},
                        "error": None})

    user_id = session.get("user_id")
    queued = [link_id for link_id in link_ids if enqueue_naver_refresh(link_id, user_id)]
    failed = len(link_ids) - len(queued)
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "잠시 후 다시 시도하세요."}), 503

    log_access(
        f"옛 주문 일괄 다시 읽기 요청 ({len(queued)}집)",
        session.get("user_id"),
        action="NAVER_ORIGIN_CLEANUP_REFRESH_ENQUEUE",
        detail={"link_ids": queued, "failed": failed},
    )
    return jsonify({"success": True,
                    "data": {"count": pending["count"], "queued": len(queued),
                             "failed": failed},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/fulfillment", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_fulfillment(link_id: int):
    """발주확인·발송처리를 **큐에 넣는다** (T16-G).

    네이버 HTTP 는 WORKER 에서만 나간다(커머스API 호출 IP 3슬롯 계약). 여기서 직접 부르면
    등록되지 않은 IP 라 차단된다. 되돌릴 수 없는 조작이라 멱등은 WORKER 쪽 서비스가 맡는다.
    """
    payload = request.get_json(silent=True) or {}
    action = str(payload.get("action") or "").strip().lower()
    if action not in ("confirm", "dispatch"):
        return jsonify({"success": False, "data": None,
                        "error": "작업을 지정하세요(발주확인 또는 발송처리)."}), 400

    from foms.services.jobs.queue import enqueue_naver_fulfillment

    # 기준 지문은 **enqueue 앞에서** 잡는다. 뒤에서 잡으면 워커가 이미 끝냈을 때 화면이
    # 뒤집힘을 영원히 못 보고 타임아웃 문구로 접힌다. 화면이 POST 전에 따로 물어보게 하면
    # 그 사이 레이스가 생기고 왕복도 는다 — 레이스가 없는 유일한 지점이 여기다.
    db = get_db()
    link = _link_by_id(db, link_id)
    base_rev = _fulfillment_state(db, link)["rev"] if link is not None else ""

    queued = enqueue_naver_fulfillment(link_id, action, session.get("user_id"))
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    label = "발주확인" if action == "confirm" else "발송처리"
    log_access(
        f"네이버 {label} 요청 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_FULFILLMENT_ENQUEUE",
        detail={"link_id": link_id, "action": action},
    )
    return jsonify({"success": True,
                    # rev: 화면이 이 값이 바뀔 때까지 폴링한다(naver_ingest_fulfillment_state).
                    "data": {"link_id": link_id, "action": action, "queued": True,
                             "rev": base_rev},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/bulk-dispatch/state", methods=["GET"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def naver_ingest_bulk_dispatch_state():
    """오늘 발송처리 상황을 **띠와 같은 값**으로 돌려준다 (NAVER-BULKDISPATCH-02 T2).

    버튼을 누른 뒤 화면이 이걸 몇 초 간격으로 읽어 "요청했습니다"를 "N집 발송 완료"까지
    바꾼다. 사람이 새로고침해서 확인하던 것을 화면이 대신한다 — 1회차 운영에서 새로고침
    뒤에 띠가 통째로 사라져 결과를 알 수 없었던 것이 이 라우트가 생긴 이유다.

    **술어를 새로 만들지 않는다.** :func:`bulk_dispatch.build_preview` 를 그대로 부른다.
    진행률용 판정을 한 벌 더 두면 화면과 워커가 갈렸던 그 결함을 재생산한다.

    읽기 전용이라 감사 기록·매니페스트 등재 대상이 아니다(둘 다 상태 변경 메서드만 본다).
    권한은 실행과 같은 ADMIN·MANAGER — 이 값을 읽는 사람은 버튼을 가진 사람이다.

    Returns:
        ``{"success": True, "data": <build_preview 결과>, "error": None}``.
    """
    from foms.services.datetime_kst import get_today_kst
    from foms.services.integrations.naver_commerce.bulk_dispatch import build_preview

    today = get_today_kst().strftime("%Y-%m-%d")
    return jsonify({"success": True, "error": None,
                    "data": build_preview(get_db(), on_date=today)})


@admin_bp.route("/admin/naver-ingest/bulk-dispatch", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def naver_ingest_bulk_dispatch():
    """오늘 실측한 네이버 건을 **집마다 큐에 넣는다** (NAVER-BULKDISPATCH-01 T4).

    되돌릴 수 없는 조작이라 규율이 셋이다:

    1. **대상은 서버가 다시 계산한다.** 화면이 보낸 목록을 받지 않는다 — 화면이 낡았거나
       조작됐을 때 그대로 네이버로 나간다(옛 주문 정리 라우트가 같은 이유로 그렇게 한다).
    2. **상한**(:data:`bulk_dispatch.BULK_DISPATCH_LIMIT`)에 닿으면 잘린 사실을 응답·로그에
       남긴다. 조용한 절단은 "전부 보냈다"로 읽힌다.
    3. 네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약) — web 은 enqueue 만 한다.

    권한은 ADMIN·MANAGER 다. 읽기 전용인 전체 다시 읽기조차 규모를 이유로 ADMIN 인데,
    불가역 조작이 그보다 느슨할 수 없다.

    Returns:
        ``{"success": True, "data": {"date","queued","sent","total","truncated",
        "failed","limit"}}``. 큐가 통째로 죽었으면 503.
    """
    from foms.services.datetime_kst import get_today_kst
    from foms.services.feature_flags import is_naver_bulk_dispatch_enabled
    from foms.services.integrations.naver_commerce.bulk_dispatch import (
        BULK_DISPATCH_LIMIT,
        select_sendable,
    )
    from foms.services.jobs.queue import enqueue_naver_fulfillment

    if not is_naver_bulk_dispatch_enabled():
        return jsonify({"success": False, "data": None,
                        "error": "일괄 발송처리가 꺼져 있습니다."}), 404

    db = get_db()
    today = get_today_kst().strftime("%Y-%m-%d")
    targets, total = select_sendable(db, on_date=today)
    if not targets:
        return jsonify({"success": True, "error": None,
                        "data": {"date": today, "queued": 0, "sent": [], "total": 0,
                                 "truncated": False, "failed": 0,
                                 "limit": BULK_DISPATCH_LIMIT}})

    actor = session.get("user_id")
    queued = [target.link_id for target in targets
              if enqueue_naver_fulfillment(target.link_id, "dispatch", actor)]
    failed = len(targets) - len(queued)
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    truncated = total > len(targets)
    log_access(
        f"네이버 일괄 발송처리 요청 ({len(queued)}집 / 대상 {total}집"
        + (f" · 상한 {BULK_DISPATCH_LIMIT}집으로 잘림" if truncated else "")
        + (f" · 큐 실패 {failed}집" if failed else "") + ")",
        action="NAVER_INGEST_BULK_DISPATCH_ENQUEUE",
        user_id=session.get("user_id"),
        detail={"date": today, "link_ids": queued, "total": total,
                "failed": failed, "truncated": truncated},
    )
    logger.info("[NAVER] 일괄 발송처리 enqueue %s: 요청 %d집 / 대상 %d집 잘림=%s 실패=%d",
                today, len(queued), total, truncated, failed)
    return jsonify({"success": True, "error": None,
                    "data": {"date": today, "queued": len(queued), "sent": queued,
                             "total": total, "truncated": truncated,
                             "failed": failed, "limit": BULK_DISPATCH_LIMIT}})


@admin_bp.route("/admin/naver-ingest/ghost/<int:order_id>/discard", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_ghost_discard(order_id: int):
    """유령 주문을 **취소 처리**한다 — 휴지통으로 (R-2 · 2026-08-25).

    네이버 결제가 전부 취소됐는데 살아 있는 ERP 주문을 접는다. hard delete 가 아니라
    soft delete 라 휴지통에서 복구된다 — 그래서 불가역 4종 세트 모달을 두지 않고
    확인창 1회로 끝낸다(사용자 결정 D-3).

    **띠에 뜬 주문만 받는다.** 목록 밖 주문 id 를 받아 지우면 이 라우트가 범용 삭제
    경로가 되는데, 그건 주문 화면의 일이고 권한 규칙도 다르다.

    **접수 이후 단계도 접을 수 있다 — 단 관리자가 사유를 적어야 한다**(사용자 결정
    2026-09-02). 예전에는 접수 단계만 열어 뒀는데, 그러면 결제가 확정 취소된 죽은
    주문이 실측·도면 대시보드에 영원히 남았다(#5088). 재결제 짝이 없으면 승계할 곳도
    없다. 휴지통은 복구되므로 잃는 것은 없고, 남겨야 할 것은 **왜 접었나**다.

    바뀌지 않는 조건은 하나다: **네이버가 취소를 확정한 건만** 접는다. 확정 전에 접으면
    취소가 거부됐을 때 살아 있어야 할 주문이 휴지통에 있다.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.ghost_orders import find_ghost_orders
    from foms.services.orders.soft_delete import soft_delete_order

    # 워크벤치 전용 기능이다 — 게이트를 끄는 것이 롤백 경로이므로 라우트도 함께 닫는다.
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 취소 처리를 할 수 없습니다."}), 403

    db = get_db()
    ghosts = find_ghost_orders(db, limit=1000)
    target = next((row for row in ghosts["rows"] if row["order_id"] == int(order_id)), None)
    if target is None:
        return jsonify({"success": False, "data": None,
                        "error": "이 주문은 '네이버 결제가 전부 취소된 주문' 목록에 없습니다."}), 400
    # 확정 전 클레임에는 절대 열지 않는다. `can_discard` 가 이미 같은 판정을 담지만,
    # 이 라우트는 **되돌리기 어려운 동작**이라 목록 계산이 나중에 바뀌어도 조용히 열리지
    # 않게 여기서 한 번 더 잠근다(2026-08-28).
    if target.get("claim_phase") != "done":
        return jsonify({"success": False, "data": None,
                        "error": "네이버가 아직 취소를 확정하지 않았습니다 — 확정 후에 접으세요."}), 400
    if not target["can_discard"]:
        return jsonify({"success": False, "data": None,
                        "error": f"{target['discard_block']} — 재결제로 정리하세요."}), 400

    # 접수 이후 단계는 **관리자 + 사유 문장**이 있어야 접힌다. 화면도 같은 조건으로
    # 사유 칸을 띄운다 — 한쪽만 좁히면 열린 버튼이 400 을 받는다.
    note = str((request.get_json(silent=True) or {}).get("reason") or "").strip()[:500]
    if target.get("discard_needs_reason"):
        if (session.get("role") or "") != "ADMIN":
            return jsonify({"success": False, "data": None,
                            "error": f"{target['status']} 단계라 이력이 붙어 있습니다 — "
                                     "관리자만 사유를 적고 접을 수 있습니다."}), 403
        if not note:
            return jsonify({"success": False, "data": None,
                            "error": "왜 접는지 한 줄 적어 주세요 — 접수 이후 단계라 "
                                     "실측·도면 기록이 함께 화면에서 사라집니다."}), 400

    reason_text = "네이버 결제 전부 취소 — 워크벤치에서 정리"
    if note:
        reason_text = f"{reason_text} ({note})"
    try:
        soft_delete_order(db, order_id=int(order_id),
                          actor_user_id=int(session.get("user_id") or 0),
                          reason=reason_text)
        db.commit()
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 사람에게 그대로 보여준다
        db.rollback()
        logger.warning("[NAVER] 유령 주문 취소 처리 실패 order=%s: %s", order_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 유령 주문 취소 처리 (order {order_id}, 결제 전부 취소)",
        session.get("user_id"),
        action="NAVER_INGEST_GHOST_DISCARD",
        target_type="order", target_id=int(order_id),
        detail={"order_id": int(order_id),
                "naver_order_nos": target["naver_order_nos"],
                "naver_amount_total": target["naver_amount_total"],
                # 접수 이후 단계를 접은 건은 **왜 접었나**가 유일한 방어선이다.
                "stage": target["status"],
                "discard_note": note},
    )
    return jsonify({"success": True,
                    "data": {"order_id": int(order_id), "discarded": True},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/cancel", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_cancel(link_id: int):
    """판매자 직접취소를 **큐에 넣는다** (스펙 §3.4).

    네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약). 사유 코드는 화면 select 를
    믿지 않고 여기서 다시 본다 — 목록 밖 코드는 네이버 400 이고, 되돌릴 수 없는 경로다.

    FOMS 주문은 건드리지 않는다. 네이버 쪽만 취소한다(주문 취소는 주문 화면의 일이다).
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.fulfillment import CANCEL_REASONS

    # 취소는 워크벤치에만 있는 기능이다. 게이트를 끄는 것이 이 기능의 롤백 경로이므로
    # 라우트도 함께 닫는다 — 열어 두면 열린 탭·북마크가 게이트를 우회한다.
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 취소를 보낼 수 없습니다."}), 403

    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip().upper()
    detail = str(payload.get("detail") or "").strip()[:500]
    if reason not in CANCEL_REASONS:
        return jsonify({"success": False, "data": None,
                        "error": "취소 사유를 고르세요."}), 400

    from foms.services.jobs.queue import enqueue_naver_cancel

    # 기준 지문은 enqueue 앞에서(발주확인·발송처리와 같은 이유).
    db = get_db()
    link = _link_by_id(db, link_id)
    base_rev = _fulfillment_state(db, link)["rev"] if link is not None else ""

    queued = enqueue_naver_cancel(link_id, reason, detail or None, session.get("user_id"))
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    log_access(
        f"네이버 취소 요청 (link {link_id}, {CANCEL_REASONS[reason]})",
        session.get("user_id"),
        action="NAVER_INGEST_CANCEL_ENQUEUE",
        detail={"link_id": link_id, "reason": reason, "cancel_detail": detail},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "reason": reason, "queued": True,
                             "rev": base_rev},
                    "error": None})



@admin_bp.route("/admin/naver-ingest/<int:link_id>/return", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_return(link_id: int):
    """판매자 **반품 접수**를 큐에 넣는다 (T8-S1).

    네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약). 사유 코드는 화면 select 를
    믿지 않고 여기서 다시 본다 — 목록 밖 코드는 네이버 400 이고, **되돌릴 수 없는
    경로라 400 을 받아 보고 배우지 않는다**. 서비스가 호출 직전에 한 번 더 본다.

    회수 방법은 **화면이 고르지 않는다** — ``RETURN_COLLECT_METHOD`` 한 값이다.
    다른 코드를 보내면 우리가 부르지 않은 택배차가 고객 집으로 간다.

    접수는 ``RETURN_REQUEST`` 까지다. **승인·환불은 사람이 판매자센터에서** 한다.
    FOMS 주문은 건드리지 않는다(취소와 같은 규율).
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.fulfillment import RETURN_REASONS

    # 반품 접수는 워크벤치에만 있는 기능이다. 게이트를 끄는 것이 이 기능의 롤백 경로이므로
    # 라우트도 함께 닫는다 — 열어 두면 열린 탭·북마크가 게이트를 우회한다(취소와 같다).
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 반품을 접수할 수 없습니다."}), 403

    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip().upper()
    detail = str(payload.get("detail") or "").strip()[:500]
    # 승인까지 한 번에 (T8-S2). **기본은 꺼짐** — 켜면 환불이 확정되고 되돌리는
    # 엔드포인트가 없다. 화면 체크박스를 믿지 않고 여기서 불리언으로 정규화한다
    # (문자열 "false" 가 참으로 읽히면 안 켠 사람이 환불을 낸다).
    approve = payload.get("approve")
    if isinstance(approve, str):
        approve = approve.strip().lower() not in ("", "false", "0", "no", "n")
    approve = bool(approve)
    if reason not in RETURN_REASONS:
        return jsonify({"success": False, "data": None,
                        "error": "반품 사유를 고르세요."}), 400

    from foms.services.jobs.queue import enqueue_naver_return

    # 기준 지문은 enqueue 앞에서(취소와 같은 이유 — 워커가 뒤집기 전 값이어야 한다).
    db = get_db()
    link = _link_by_id(db, link_id)
    base_rev = _fulfillment_state(db, link)["rev"] if link is not None else ""

    queued = enqueue_naver_return(link_id, reason, detail or None, session.get("user_id"),
                                  approve=approve)
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    # 승인은 **다른 사건**이다 — 돈이 나간다. 감사 원장에서 접수와 갈라 읽을 수 있어야
    # "누가 환불을 냈나"에 답할 수 있다. 라벨은 `audit_message_display` 에 등재돼 있어야
    # 하고(미등재면 CI red), 그 등재가 이 갈래의 계약이다.
    log_access(
        (f"네이버 반품 접수+승인 요청 (link {link_id}, {RETURN_REASONS[reason]})"
         if approve else
         f"네이버 반품 접수 요청 (link {link_id}, {RETURN_REASONS[reason]})"),
        session.get("user_id"),
        action=("NAVER_INGEST_RETURN_APPROVE_ENQUEUE" if approve
                else "NAVER_INGEST_RETURN_ENQUEUE"),
        detail={"link_id": link_id, "reason": reason, "return_detail": detail,
                "approve": approve},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "reason": reason, "queued": True,
                             "approve": approve, "rev": base_rev},
                    "error": None})

@admin_bp.route("/admin/naver-ingest/reject-templates", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_save_reject_templates():
    """반품 거부 **상용구 문장**을 저장한다 — 회사 전체가 쓰는 한 벌 (T8-S3).

    거부 실행은 ``ADMIN``·``MANAGER`` 인데 **문장 편집은 ``ADMIN`` 만**이다
    (사용자 결정 2026-09-01). 문장은 구매자에게 그대로 가므로, 쓰는 사람과 정하는
    사람을 나눈다.

    **목록 전체를 덮어쓴다.** 항목 단위 병합은 삭제를 표현하지 못한다.
    동시 저장은 ``version`` 으로 막는다 — 관리자 둘이 각자 저장하면 뒤에 누른 쪽이
    앞사람 문장을 조용히 지운다(409 로 되돌려보내고 화면이 새로 고치라고 말한다).

    네이버로 나가는 호출은 **0** 이다. 우리 설정만 바꾼다.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.reject_templates import (
        RejectTemplateConflict,
        RejectTemplateError,
        save_templates,
    )

    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 문장을 저장할 수 없습니다."}), 403

    payload = request.get_json(silent=True) or {}
    raw_version = payload.get("version")
    try:
        if_match = int(raw_version) if raw_version is not None else None
    except (TypeError, ValueError):
        if_match = None

    db = get_db()
    try:
        result = save_templates(db, items=payload.get("templates"),
                                actor_user_id=session.get("user_id"),
                                if_match_version=if_match)
        db.commit()
    except RejectTemplateConflict as exc:
        db.rollback()
        return jsonify({"success": False, "data": {"version": exc.current_version},
                        "error": str(exc)}), 409
    except RejectTemplateError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 사람에게 그대로 보여준다
        db.rollback()
        logger.warning("[NAVER] 거부 상용구 저장 실패: %s", exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 반품 거부 상용구 저장 ({len(result['templates'])}개)",
        session.get("user_id"),
        action="NAVER_INGEST_REJECT_TEMPLATES_SAVE",
        # 어떤 문장이 언제 들어갔는지가 곧 "고객이 무슨 말을 받았나"의 뿌리다.
        detail={"templates": result["templates"], "version": result["version"]},
    )
    return jsonify({"success": True, "data": result, "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/return-reject", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def naver_ingest_return_reject(link_id: int):
    """고객이 낸 반품 요청을 **거부**한다 (T8-S3).

    접수·승인과 **다른 대상**이다: 접수는 *우리가* 반품을 내는 것이고, 거부는 *고객이 낸*
    요청을 되돌려보내는 것이다. 그래서 접수 모달의 체크박스가 아니라 별도 라우트다.

    **권한이 접수·승인보다 좁다**(``ADMIN``·``MANAGER``, 사용자 결정 2026-08-31).
    거부 문장은 구매자에게 그대로 가고 분쟁으로 돌아올 수 있어 쓰는 사람을 좁힌다.
    버튼도 **같은 조건**으로 렌더한다 — 한쪽만 좁히면 열린 버튼이 403 을 받는다.

    사유는 **코드가 아니라 문장**이다. 화이트리스트로 거를 수 없으니 여기서는 빈 문장만
    막고(빈 요청으로 불가역 API 를 때리지 않는다) 원문을 그대로 큐에 싣는다.

    네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약).
    """
    from foms.services.feature_flags import (
        is_naver_return_reject_enabled,
        is_naver_workbench_enabled,
    )
    from foms.services.integrations.naver_commerce.fulfillment import (
        RETURN_REJECT_REASON_MAX,
    )

    # 게이트 둘. 워크벤치 게이트는 화면 자체의 롤백 경로이고, 거부 게이트는 **규격이 아직
    # 안 채워졌다**는 사실을 코드로 잠근다(설계서 §2). 둘 중 하나라도 꺼져 있으면 닫는다.
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 반품을 거부할 수 없습니다."}), 403
    if not is_naver_return_reject_enabled():
        return jsonify({"success": False, "data": None,
                        "error": "반품 거부 기능이 아직 켜져 있지 않습니다."}), 403

    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()[:RETURN_REJECT_REASON_MAX]
    if not reason:
        return jsonify({"success": False, "data": None,
                        "error": "거부 사유 문장을 입력하세요 — 구매자에게 그대로 전달됩니다."}), 400

    from foms.services.jobs.queue import enqueue_naver_return_reject

    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        return jsonify({"success": False, "data": None,
                        "error": f"수집 기록을 찾을 수 없습니다 (link {link_id})."}), 400
    # 기준 지문은 enqueue 앞에서(접수·취소와 같은 이유 — 워커가 뒤집기 전 값이어야 한다).
    base_rev = _fulfillment_state(db, link)["rev"]
    # 집 요약도 **보내기 전에** 뽑는다(붙이기와 같은 규율).
    history = summarize_link_household(db, link_id=link_id)

    queued = enqueue_naver_return_reject(link_id, reason, session.get("user_id"))
    if not queued:
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    # 주문 이력에도 남긴다(사용자 결정 2026-08-31). 워크벤치를 안 여는 담당자가 나중에
    # "이 주문의 반품이 왜 안 받아들여졌나"를 읽는 자리는 여기뿐이다. 붙어 있는 주문이
    # 없으면 남길 자리도 없다 — 그때는 감사 로그만 남는다.
    if link.order_id:
        db.add(OrderEvent(
            order_id=int(link.order_id),
            event_type=RETURN_REJECT_EVENT_TYPE,
            payload={
                "link_id": int(link_id),
                "reason": reason,
                "external_order_no": history.get("external_order_no") or "",
                "product_order_count": int(history.get("product_order_count") or 0),
            },
            created_by_user_id=session.get("user_id"),
        ))
        db.commit()

    log_access(
        f"네이버 반품 거부 요청 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_RETURN_REJECT_ENQUEUE",
        target_type=("order" if link.order_id else None),
        target_id=(int(link.order_id) if link.order_id else None),
        # **보낸 문장을 그대로 남긴다.** 분쟁이 나면 요약이 아니라 원문이 필요하다.
        detail={"link_id": link_id, "reject_reason": reason},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "queued": True, "rev": base_rev,
                             "reason": reason},
                    "error": None})


def _enqueue_claim_approve(link_id: int, *, kind: str):
    """취소·반품 **승인** 두 라우트의 공통 몸통 (T9).

    두 승인은 게이트 이름·감사 action·이벤트 타입만 다르고 나머지가 같다. 한 벌로 두는
    이유는 거부 라우트가 남긴 교훈과 같다 — 갈래를 복사하면 ``base_rev`` 를 enqueue 앞에서
    뽑는 규율이나 큐 장애 503 같은 자리가 한쪽에서만 조용히 낡는다.

    Args:
        link_id: 기준 수집 링크 id(그 링크가 속한 집 전체가 함께 처리된다).
        kind: ``"cancel"`` 또는 ``"return"``.

    Returns:
        Flask 응답 튜플.
    """
    from foms.services.feature_flags import (
        is_naver_cancel_approve_enabled,
        is_naver_return_approve_enabled,
        is_naver_workbench_enabled,
    )
    from foms.services.jobs.queue import (
        enqueue_naver_cancel_approve,
        enqueue_naver_return_approve,
    )

    is_cancel = kind == "cancel"
    label = "취소" if is_cancel else "반품"

    # 게이트 둘. 워크벤치 게이트는 화면 자체의 롤백 경로이고, 승인 게이트는 **불가역
    # 환불을 당장 끌 수 있는가**를 코드로 쥔다. 둘 중 하나라도 꺼져 있으면 닫는다.
    # 버튼도 같은 조건으로 렌더한다 — 한쪽만 열면 열린 버튼이 403 을 받는다.
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": f"이 화면에서는 {label}을 승인할 수 없습니다."}), 403
    enabled = is_naver_cancel_approve_enabled() if is_cancel else is_naver_return_approve_enabled()
    if not enabled:
        return jsonify({"success": False, "data": None,
                        "error": f"{label} 승인 기능이 아직 켜져 있지 않습니다."}), 403

    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        return jsonify({"success": False, "data": None,
                        "error": f"수집 기록을 찾을 수 없습니다 (link {link_id})."}), 400
    # 기준 지문은 enqueue 앞에서(거부·접수와 같은 이유 — 워커가 뒤집기 전 값이어야 한다).
    base_rev = _fulfillment_state(db, link)["rev"]
    # 집 요약도 **보내기 전에** 뽑는다(붙이기와 같은 규율).
    history = summarize_link_household(db, link_id=link_id)

    enqueue = enqueue_naver_cancel_approve if is_cancel else enqueue_naver_return_approve
    if not enqueue(link_id, session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "작업 큐를 쓸 수 없습니다(REDIS_URL 미설정 또는 큐 장애). "
                                 "지금은 판매자센터에서 처리하세요."}), 503

    # 주문 이력에도 남긴다(거부와 같은 규율). 워크벤치를 안 여는 담당자가 나중에 "이 주문의
    # 돈이 왜 나갔나"를 읽는 자리는 여기뿐이다. 붙어 있는 주문이 없으면 감사 로그만 남는다.
    if link.order_id:
        db.add(OrderEvent(
            order_id=int(link.order_id),
            event_type=(CANCEL_APPROVE_EVENT_TYPE if is_cancel
                        else RETURN_APPROVE_EVENT_TYPE),
            payload={
                "link_id": int(link_id),
                "external_order_no": history.get("external_order_no") or "",
                "product_order_count": int(history.get("product_order_count") or 0),
            },
            created_by_user_id=session.get("user_id"),
        ))
        db.commit()

    log_access(
        f"네이버 {label} 승인 요청 (link {link_id})",
        session.get("user_id"),
        action=("NAVER_INGEST_CANCEL_APPROVE_ENQUEUE" if is_cancel
                else "NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE"),
        target_type=("order" if link.order_id else None),
        target_id=(int(link.order_id) if link.order_id else None),
        detail={"link_id": link_id,
                "external_order_no": history.get("external_order_no") or ""},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "queued": True, "rev": base_rev},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/cancel-approve", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def naver_ingest_cancel_approve(link_id: int):
    """구매자가 낸 **취소 요청을 승인**한다 (T9-G1).

    지금까지 화면은 취소 요청을 **알아차리기만** 했다 — "네이버가 아직 취소를 확정하지
    않았습니다"라고 적고, 확정시키는 방법은 판매자센터뿐이었다. 이 라우트가 그 자리를 연다.

    **되돌릴 수 없다.** 승인 시점에 결제 환불이 자동 처리되고, 취소를 **거절**하는 API 는
    존재하지 않는다(철회는 구매자만 한다).

    **권한이 취소처리(``STAFF`` 포함)보다 좁다**(``ADMIN``·``MANAGER``, 사용자 결정
    2026-09-01). 돈이 나가는 판단은 거부와 같은 층에 둔다.

    **ERP 주문은 건드리지 않는다.** 승인은 네이버 축만 움직인다 — 유령 주문을 접는 것은
    기존 폐기 버튼(``/ghost/<order_id>/discard``)이 계속 담당한다. 그쪽 잠금은 이 승인과
    다른 축이다(접수 단계를 지난 주문은 여전히 잠긴다).

    네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약).
    """
    return _enqueue_claim_approve(link_id, kind="cancel")


@admin_bp.route("/admin/naver-ingest/<int:link_id>/return-approve", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER"])
def naver_ingest_return_approve(link_id: int):
    """고객이 낸 **반품 요청을 승인**한다 — 접수와 분리된 독립 경로 (T9-G2).

    접수 모달의 ``승인까지 한 번에`` 체크박스(T8-S2)는 *우리가 낸* 반품에만 걸린다.
    **고객이 먼저 낸 반품**은 우리 접수 표식이 없어 그 경로로 못 간다. 그래서 화면이
    고객 반품 앞에서 내주던 불가역 버튼이 ``반품 거부`` 하나뿐이었다 — 승인 버튼이 없어
    담당자가 거부를 누르게 되는 구조였다.

    **되돌릴 수 없다.** 승인 시점에 환불이 확정된다.

    감사 action 을 접수+승인과 **일부러 갈라 둔다**(``..._APPROVE_ONLY_...``) — 원장에서
    "접수하면서 승인한 것"과 "이미 있던 반품을 승인한 것"이 구분돼야 한다.

    네이버 HTTP 는 WORKER 에서만 나간다(호출 IP 3슬롯 계약).
    """
    return _enqueue_claim_approve(link_id, kind="return")


@admin_bp.route("/admin/naver-ingest/<int:link_id>/fulfillment-clear", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_fulfillment_clear(link_id: int):
    """실패 기록을 **사람이 확인한 그 작업만** 지운다 (네이버 호출 없음).

    실패 사유는 성공한 재시도가 지운다. 판매자센터에서 손으로 해결한 건은 그 경로가
    없어 빨간 띠가 영원히 남는다 — 사람이 "확인했다"고 닫는 자리다.

    범위는 ``link_id`` 와 **같은 작업으로 실패한 형제들**이다(NVCLAIM-ORDER-01 RC5 2차,
    :func:`fulfillment.clear_failure`). 실패 띠는 집당 한 줄이고 그 줄은 작업 하나만
    말하므로, 집 전체를 지우면 사람이 본 적 없는 반품 실패까지 함께 사라진다 —
    반품 실패 라인에는 ``return`` 축 기록이 없어 그 사유가 유일한 증거다.

    성공 표식은 건드리지 않는다. 다른 작업의 실패가 남았으면 감사에 ``kept`` 로 적는다.
    """
    from foms.services.integrations.naver_commerce.fulfillment import (
        FulfillmentError,
        clear_failure,
    )

    db = get_db()
    try:
        result = clear_failure(db, link_id=link_id, actor_user_id=session.get("user_id"))
    except FulfillmentError as exc:
        return jsonify({"success": False, "data": None, "error": str(exc)}), 404
    db.commit()
    log_access(
        f"네이버 발주확인·발송처리 실패 기록 지움 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_FULFILLMENT_CLEAR",
        # `kept` 가 0이 아니면 **이 집에 확인 안 된 실패가 남아 있다**는 뜻이다. 원장에
        # 남겨야 나중에 "왜 띠가 다시 떴나"를 화면 밖에서 답할 수 있다.
        detail={"link_id": link_id, "cleared": result["cleared"],
                "kept": result["kept"], "cleared_action": result["action"]},
    )
    return jsonify({"success": True, "data": result, "error": None})


#: 붙이기·되돌리기가 주문 변경 이력에 남기는 이벤트 타입 (스펙 2026-08-24 R3 = 08-19 §7 Q3 안 B).
#: **라벨 사전(``foms/services/order_event_display.py``)에 반드시 함께 등재한다.** 빠지면
#: 화면에 영문 코드가 뜨는 게 아니라 한글 "기타 변경"으로 조용히 뭉개져 다른 미등재
#: 이벤트와 구분이 안 된다(``translate_event_type_to_korean`` 의 기본값).
ATTACH_EVENT_TYPE = "NAVER_ORDER_ATTACHED"
DETACH_EVENT_TYPE = "NAVER_ORDER_DETACHED"

#: 반품 거부가 주문 변경 이력에 남기는 이벤트 타입 (T8-S3). 위와 **같은 규율** —
#: 라벨 사전에 등재하지 않으면 화면이 "기타 변경"으로 조용히 뭉갠다.
RETURN_REJECT_EVENT_TYPE = "NAVER_RETURN_REJECTED"

#: 취소·반품 **승인**이 주문 변경 이력에 남기는 이벤트 타입 (T9). 거부만 이력에 남고
#: 환불은 안 남으면 장부가 한쪽으로 기운다 — 돈이 나간 사실이 워크벤치 밖에서 읽혀야 한다.
CANCEL_APPROVE_EVENT_TYPE = "NAVER_CANCEL_APPROVED"
RETURN_APPROVE_EVENT_TYPE = "NAVER_RETURN_APPROVED"


def _record_link_history(db: Session, *, order_id: int, link_id: int, event_type: str,
                         relation: str, summary: dict[str, Any]) -> None:
    """붙이기·되돌리기를 **주문 변경 이력**(``OrderEvent``)에 1건 남긴다 (스펙 2026-08-24 R3).

    주문 상태·단계는 한 글자도 건드리지 않는다 — 재결제로 원 네이버 주문이 취소돼도 FOMS
    주문은 살아 있고, 남길 것은 "무엇이 얼마 붙었나"라는 사실뿐이다(안 B).
    **append-only** — 되돌리기는 금액 기록만 걷어내고 붙임 이벤트는 지우지 않는다.

    호출자의 트랜잭션에 그대로 얹는다(commit 은 호출자 소유). 이력을 따로 커밋하면
    "붙었는데 이력이 없는" 상태가 새로 생기는데, 그것이 바로 R3 가 없애려는 결함이다.

    Args:
        db: 호출자 DB 세션(commit 하지 않는다).
        order_id: 이력을 붙일 FOMS 주문 id.
        link_id: 사람이 누른 기준 수집 링크 id.
        event_type: :data:`ATTACH_EVENT_TYPE` 또는 :data:`DETACH_EVENT_TYPE`.
        relation: 관계값(``ADDON``/``REPAY``).
        summary: :func:`summarize_link_household` 결과(집 요약).

    Returns:
        None — 실패는 예외로 올라가 호출자의 rollback 에 걸린다.
    """
    db.add(OrderEvent(
        order_id=int(order_id),
        event_type=event_type,
        payload={
            "relation": relation,
            "link_id": int(link_id),
            "external_order_no": summary.get("external_order_no") or "",
            "product_order_count": int(summary.get("product_order_count") or 0),
            "amount_total": int(summary.get("amount_total") or 0),
        },
        created_by_user_id=session.get("user_id"),
    ))


@admin_bp.route("/admin/naver-ingest/<int:link_id>/order-search")
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_order_search(link_id: int) -> str:
    """붙일 주문을 **이름·전화·주문번호로 찾는다** — 후보 0건일 때의 진입점 (T2).

    자동 후보는 세 축뿐이라(수취인 전화·주문자 전화·이름+주소) 재결제가 다른 이름·다른
    전화·다른 주소로 오면 0건이 되고, 그러면 붙이기 버튼이 화면에 아예 없다. 판정은
    :func:`search_orders_for_attach` 가 하고 이 라우트는 **조각만 그린다**.

    읽기 전용 GET 이다 — 아무것도 바꾸지 않으므로 write manifest 등재도 감사 라벨도 없다
    (:func:`naver_ingest_triage_pane` 과 같은 규율). 붙이는 것은 기존
    ``POST .../attach`` 가 그대로 한다 — 새 mutation 을 파지 않는다.

    Query:
        ``q``: 검색어(이름·전화·주문번호). 짧으면 조회하지 않고 그렇게 말한다.

    Returns:
        결과 조각 HTML(레이아웃 없음). 게이트 OFF 는 404(그 화면에는 이 경로가 없다),
        없는 링크는 404.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.order_candidates import (
        search_orders_for_attach,
    )

    if not is_naver_workbench_enabled(session.get("user_id")):
        abort(404)
    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        abort(404)
    return render_template(
        "admin/partials/naver_workbench_seek.html",
        seek=search_orders_for_attach(db, link, query=request.args.get("q", "")),
        seek_link_id=link_id,
    )


@admin_bp.route("/admin/naver-ingest/<int:link_id>/attach", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_attach_order(link_id: int):
    """수집분을 **기존 주문에 붙인다** (T16-E) — 차액 결제·재결제.

    새 주문을 만들지 않는다. 수집 판정이 결제완료 하나뿐이라 재결제·차액 결제도 새 집으로
    들어오는데, 그대로 "주문 만들기"를 누르면 같은 고객의 시공 건이 둘로 갈린다.

    관계 판정은 **사람이** 한다(후보 제시는 :mod:`order_candidates`). 이 라우트는 사람이
    고른 결과를 받아 적을 뿐이다.
    """
    from foms.services.integrations.naver_commerce.promotion import (
        PromotionError,
        attach_link_to_order,
    )

    payload = request.get_json(silent=True) or {}
    try:
        order_id = int(payload.get("order_id") or 0)
    except (TypeError, ValueError):
        order_id = 0
    relation = str(payload.get("relation") or "").strip().upper()
    if order_id <= 0:
        return jsonify({"success": False, "data": None, "error": "붙일 주문을 지정하세요."}), 400

    db = get_db()
    try:
        # 집 요약은 **변경 전에** 뽑는다 — 붙인 뒤에는 대상 집합·관계값이 이미 바뀌어 있다.
        history = summarize_link_household(db, link_id=link_id)
        attached, target_order_id, changed = attach_link_to_order(
            db, link_id=link_id, order_id=order_id, relation=relation,
            actor_user_id=session.get("user_id"))
        # 같은 버튼을 두 번 누르면 두 번째는 **아무것도 바꾸지 않는다**(금액 기록은 원래
        # 멱등). 그런데도 이력에 줄이 쌓이면 담당자가 "두 번 붙었나?" 를 의심하게 된다 —
        # 주문 변경 이력은 **무엇이 바뀌었나**를 말하는 자리다(2026-08-25 정책 확정).
        # 누가 눌렀는가는 아래 log_access 가 누른 횟수만큼 그대로 남긴다(감사 축은 불변).
        if changed:
            _record_link_history(db, order_id=target_order_id, link_id=link_id,
                                 event_type=ATTACH_EVENT_TYPE, relation=relation,
                                 summary=history)
        db.commit()
    except PromotionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 사람에게 그대로 보여준다
        db.rollback()
        logger.warning("[NAVER] 기존 주문 연결 실패 link=%s order=%s: %s",
                       link_id, order_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 기존 주문 연결 (link {link_id} → order {target_order_id}, {relation})",
        session.get("user_id"),
        action="NAVER_INGEST_ATTACH_ORDER",
        target_type="order", target_id=target_order_id,
        detail={"link_id": link_id, "order_id": target_order_id,
                "relation": relation, "attached": attached},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": target_order_id,
                             "relation": relation, "attached": attached,
                             "edit_url": url_for("order_edit.edit_order",
                                                 order_id=target_order_id, open="erp-order")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/reconcile", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_repay_reconcile(link_id: int):
    """**재결제 정리** — 붙이기와 ERP 기존 주문 처리를 한 트랜잭션으로 (R-3 · 2026-08-25).

    갈래 둘 중 하나를 실행한다:

    * ``SUCCEED`` 승계 — 새 집을 기존 주문에 붙인다. 주문은 그대로 두고 예약금은
      **안내만** 한다(D-1 확정 — 시스템이 넣지 않는다).
    * ``DISCARD`` 취소 처리 — 기존 주문을 휴지통으로 보낸다(soft delete). **붙이지 않는다** —
      휴지통에 든 주문에 새 집을 묶으면 ``주문 만들기`` 가 막힌다.

    **네이버로 나가는 호출은 0 이다.** 옛 결제 취소는 고객이 하거나 판매자센터에서 한다
    (스펙 §2.5 개정 — 불가역을 시스템이 대신 눌러 주지 않는다).

    **후보 목록에 있는 주문만 받는다.** 목록 밖 주문 id 를 받아 처리하면 이 라우트가 범용
    삭제·연결 경로가 되는데, 그건 주문 화면의 일이고 권한 규칙도 다르다.
    """
    from foms.services.feature_flags import is_naver_workbench_enabled
    from foms.services.integrations.naver_commerce.promotion import PromotionError
    from foms.services.integrations.naver_commerce.repay_reconcile import (
        ReconcileError,
        deposit_guidance,
        run_reconcile,
    )

    # 워크벤치 전용 기능이다 — 게이트를 끄는 것이 롤백 경로이므로 라우트도 함께 닫는다.
    if not is_naver_workbench_enabled(session.get("user_id")):
        return jsonify({"success": False, "data": None,
                        "error": "이 화면에서는 정리를 할 수 없습니다."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        order_id = int(payload.get("order_id") or 0)
    except (TypeError, ValueError):
        order_id = 0
    relation = str(payload.get("relation") or "").strip().upper()
    fork = str(payload.get("fork") or "").strip().upper()
    if order_id <= 0:
        return jsonify({"success": False, "data": None, "error": "정리할 주문을 지정하세요."}), 400

    db = get_db()
    link = _link_by_id(db, link_id)
    if link is None:
        return jsonify({"success": False, "data": None,
                        "error": f"수집 기록을 찾을 수 없습니다 (link {link_id})."}), 400

    candidate = next((row for row in find_order_candidates(db, link)
                      if int(row["order_id"]) == order_id), None)
    if candidate is None:
        return jsonify({"success": False, "data": None,
                        "error": "이 건의 기존 주문 후보가 아닙니다. 화면을 새로 고친 뒤 "
                                 "다시 고르세요."}), 400

    try:
        # 집 요약은 **변경 전에** 뽑는다 — 붙인 뒤에는 대상 집합·관계값이 이미 바뀌어 있다.
        history = summarize_link_household(db, link_id=link_id)
        result = run_reconcile(db, link_id=link_id, order_id=order_id, relation=relation,
                               fork=fork, actor_user_id=session.get("user_id"))
        # 붙이기가 실제로 무언가를 바꿨을 때만 주문 변경 이력에 줄을 남긴다
        # (같은 버튼 두 번 = 이력 한 줄 — 2026-08-25 정책). 감사 축은 아래 log_access.
        if result["fork"] == "SUCCEED" and result["changed"]:
            _record_link_history(db, order_id=result["order_id"], link_id=link_id,
                                 event_type=ATTACH_EVENT_TYPE, relation=relation,
                                 summary=history)
        # 여기 한 번의 커밋이 이 흐름의 전부다 — 둘 다 되거나 둘 다 안 된다.
        db.commit()
    except (ReconcileError, PromotionError) as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001 - 실패 사유를 사람에게 그대로 보여준다
        db.rollback()
        logger.warning("[NAVER] 재결제 정리 실패 link=%s order=%s fork=%s: %s",
                       link_id, order_id, fork, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    order = db.get(Order, int(order_id))
    # 예약금 안내는 **승계일 때만** 뜻이 있다(취소 처리는 주문이 휴지통으로 간다).
    deposit = (deposit_guidance(order, new_amount=candidate.get("new_amount_total") or 0,
                                relation=relation)
               if order is not None and result["fork"] == "SUCCEED" else None)

    log_access(
        f"네이버 재결제 정리 (link {link_id} → order {order_id}, {relation}/{fork})",
        session.get("user_id"),
        action="NAVER_INGEST_REPAY_RECONCILE",
        target_type="order", target_id=int(order_id),
        detail={"link_id": link_id, "order_id": int(order_id), "relation": relation,
                "fork": result["fork"], "attached": result["attached"],
                "discarded": result["discarded"],
                "external_order_no": history.get("external_order_no") or "",
                "amount_total": history.get("amount_total") or 0},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": int(order_id),
                             "relation": relation, "fork": result["fork"],
                             "attached": result["attached"],
                             "discarded": result["discarded"],
                             "deposit": deposit,
                             "edit_url": url_for("order_edit.edit_order",
                                                 order_id=int(order_id), open="erp-order")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/detach", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_detach_order(link_id: int):
    """붙이기를 되돌린다 (T16-E) — 관계를 잘못 골랐을 때.

    주문 생성분(``NEW``)은 되돌릴 수 없다. 그건 주문 삭제 문제라 이 경로의 일이 아니다.
    """
    from foms.services.integrations.naver_commerce.promotion import (
        ATTACHABLE_RELATIONS,
        PromotionError,
        detach_link_from_order,
    )

    db = get_db()
    try:
        # 되돌리기는 붙이기로 연결된 링크만 걷어낸다 — 같은 술어로 요약해야 숫자가 맞는다.
        history = summarize_link_household(db, link_id=link_id,
                                           relations=ATTACHABLE_RELATIONS)
        detached, previous_order_id = detach_link_from_order(
            db, link_id=link_id, actor_user_id=session.get("user_id"))
        if previous_order_id:
            _record_link_history(db, order_id=previous_order_id, link_id=link_id,
                                 event_type=DETACH_EVENT_TYPE,
                                 relation=history["relation"], summary=history)
        db.commit()
    except PromotionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("[NAVER] 연결 되돌리기 실패 link=%s: %s", link_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집분 연결 되돌림 (link {link_id} ← order {previous_order_id})",
        session.get("user_id"),
        action="NAVER_INGEST_DETACH_ORDER",
        target_type="order", target_id=previous_order_id,
        detail={"link_id": link_id, "order_id": previous_order_id, "detached": detached},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id, "order_id": previous_order_id,
                             "detached": detached},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/review", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_mark_reviewed(link_id: int):
    """"확인 완료" — 사람이 처리했다고 표시해 큐에서 뺀다 (스펙 §8.3).

    시스템이 "다 채웠는지"를 추측하지 않는다. 추측 규칙을 코드로 정하면 오판 여지가 생기고
    업무 기준이 바뀔 때마다 규칙을 고쳐야 한다. 사람이 누른 사실만 기록한다.
    """
    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404
    if link.reviewed_at is None:  # 이미 확인된 건은 시각을 덮지 않는다(첫 확인이 기록이다).
        link.reviewed_at = now_utc_naive()
        link.reviewed_by_user_id = session.get("user_id")
        db.commit()
    log_access(
        f"네이버 수집 확인 완료 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_MARK_REVIEWED",
        detail={"link_id": link_id, "external_id": link.external_id},
    )
    return jsonify({"success": True, "data": {"link_id": link_id}, "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/dock-state", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_dock_state(link_id: int):
    """도크 항목의 체크(반영 표시)·귀속(추가옵션→본품)을 저장한다 (T14-B).

    체크는 즉시 저장(팀 공유)이며 토글 가능하다 — ``reviewed_at`` 과 다른 축이다
    (저건 큐 이탈·첫 확인 시각 불변). 귀속은 **표시/체크리스트용**일 뿐 주문 데이터
    (items·spec_rows)는 절대 건드리지 않는다(폼 불가침 계약).

    Body(JSON, 부분 갱신): ``checked``(bool) / ``assigned_main``(str|null —
    형제 본품 external_id, ``"COMMON"``(주문 전체), 또는 null=미정).
    """
    import copy as copy_module

    from sqlalchemy.orm.attributes import flag_modified

    from foms.services.integrations.naver_commerce.dock import ASSIGN_COMMON

    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404

    body = request.get_json(silent=True) or {}
    if "checked" not in body and "assigned_main" not in body:
        return jsonify({"success": False, "data": None,
                        "error": "checked 또는 assigned_main 이 필요합니다."}), 400

    state = copy_module.deepcopy(link.triage_state) if isinstance(link.triage_state, dict) else {}
    user_id = session.get("user_id")
    now_str = now_utc_naive().strftime("%Y-%m-%d %H:%M:%S")

    if "checked" in body:
        if not isinstance(body["checked"], bool):
            return jsonify({"success": False, "data": None,
                            "error": "checked 는 true/false 여야 합니다."}), 400
        state["checked"] = body["checked"]
        state["checked_by"] = user_id
        state["checked_at"] = now_str

    if "assigned_main" in body:
        assigned = body["assigned_main"]
        if assigned is not None:
            assigned = str(assigned).strip()
            if assigned != ASSIGN_COMMON:
                # 같은 주문의 형제 링크 external_id 만 허용 — 임의 문자열 저장 금지.
                sibling_ids = {
                    row.external_id
                    for row in db.query(ExternalOrderLink.external_id)
                    .filter(ExternalOrderLink.channel == "NAVER",
                            ExternalOrderLink.order_id == link.order_id)
                    .all()
                } if link.order_id else set()
                if assigned not in sibling_ids:
                    return jsonify({"success": False, "data": None,
                                    "error": "귀속 대상이 이 주문의 본품이 아닙니다."}), 400
        state["assigned_main"] = assigned
        state["assigned_by"] = user_id
        state["assigned_at"] = now_str

    link.triage_state = state
    flag_modified(link, "triage_state")
    db.commit()
    log_access(
        f"네이버 도크 상태 저장 (link {link_id})",
        session.get("user_id"),
        action="NAVER_DOCK_STATE_SET",
        detail={"link_id": link_id, "external_id": link.external_id,
                "checked": state.get("checked"), "assigned_main": state.get("assigned_main")},
    )
    return jsonify({"success": True,
                    "data": {"link_id": link_id,
                             "checked": bool(state.get("checked")),
                             "assigned_main": state.get("assigned_main")},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:order_id>/assignee", methods=["POST"])
@login_required
@role_required(["ADMIN", "MANAGER", "STAFF"])
def naver_ingest_set_assignee(order_id: int):
    """수집 주문의 SALES 담당자를 지정한다 (스펙 §8.4).

    ``OrderAssignment`` 를 직접 만들지 않고 canonical
    :func:`~foms.services.orders.assignment.set_sales_assignee` 를 부른다 — 그래야 REV-00
    version bump·receipt·``SALES_ASSIGNEE_SET`` 이벤트·주문당 active owner 1명 제약이
    전부 따라온다.

    보류함(``naver_unassigned``)에서 실제 담당자로 옮기는 것도 **교체**라 사유가 필수다.
    화면이 사유를 보내지 않으므로 여기서 기본 사유를 채운다.
    """
    import hashlib
    import json as _json

    from foms.services.orders.assignment import set_sales_assignee
    from foms.services.orders.revision import RevisionError

    body = request.get_json(silent=True) or {}
    try:
        user_id = int(body.get("user_id"))
    except (TypeError, ValueError):
        return jsonify({"success": False, "data": None,
                        "error": "담당자(user_id)가 필요합니다."}), 400

    db = get_db()
    scope_hash = hashlib.sha256(f"SET_SALES_ASSIGNEE:{order_id}".encode("utf-8")).hexdigest()
    request_hash = hashlib.sha256(
        _json.dumps({"user_id": user_id}, sort_keys=True).encode("utf-8")
    ).hexdigest()
    try:
        set_sales_assignee(
            db, actor_user_id=int(session.get("user_id")), order_id=order_id,
            user_id=user_id, reason="네이버 수집 주문 담당자 지정",
            scope_hash=scope_hash, request_hash=request_hash,
        )
        db.commit()
    except RevisionError as exc:
        db.rollback()
        return jsonify({"success": False, "data": None, "error": str(exc)}), exc.status_code
    except Exception as exc:  # noqa: BLE001 - 사용자에게 사유를 돌려주고 tx 는 되돌린다
        db.rollback()
        logger.warning("[NAVER] 담당자 지정 실패 order=%s: %s", order_id, exc, exc_info=True)
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    log_access(
        f"네이버 수집 주문 담당자 지정 (order {order_id})",
        session.get("user_id"),
        action="NAVER_INGEST_SET_ASSIGNEE",
        target_type="order", target_id=order_id,
        detail={"order_id": order_id, "user_id": user_id},
    )
    return jsonify({"success": True, "data": {"order_id": order_id, "user_id": user_id},
                    "error": None})


@admin_bp.route("/admin/naver-ingest/<int:link_id>/snapshot")
@login_required
@role_required(["ADMIN"])
def naver_ingest_snapshot(link_id: int):
    """채널 원본 응답을 그대로 보여준다(**관리자 전용**).

    실번호·주소가 그대로 들어 있는 개인정보 덩어리라 열람 자체를 감사 원장에 남긴다.
    매핑을 고친 뒤 무엇이 잘못 들어왔는지 대조하는 것이 이 화면의 용도다.
    """
    db = get_db()
    link = (
        db.query(ExternalOrderLink)
        .filter(ExternalOrderLink.id == link_id, ExternalOrderLink.channel == "NAVER")
        .first()
    )
    if link is None:
        return jsonify({"success": False, "data": None, "error": "수집 이력을 찾을 수 없습니다."}), 404
    log_access(
        f"네이버 수집 원본 스냅샷 열람 (link {link_id})",
        session.get("user_id"),
        action="NAVER_INGEST_SNAPSHOT_VIEW",
        detail={"link_id": link_id, "external_id": link.external_id},
    )
    return jsonify({
        "success": True,
        "data": {
            "external_id": link.external_id,
            "sync_status": link.sync_status,
            "failure_reason": link.failure_reason,
            "snapshot": link.raw_snapshot,
        },
        "error": None,
    })


@admin_bp.route("/admin/naver-ingest/run", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_run_now():
    """"지금 수집" — rq 큐에 넣기만 한다(네이버 HTTP 는 WORKER 몫).

    큐가 없으면(REDIS_URL 미설정) 조용히 성공한 척하지 않고 실패를 알린다. 여기서 직접
    HTTP 를 내면 IP 가 달라 차단되므로 폴백은 존재하지 않는다.

    **큐가 살아 있어도 일할 워커가 0대면 넣지 않는다.** 넣으면 job 은 아무도 꺼내지 않는
    큐에 영원히 앉아 있는데 화면은 "넣었습니다"라고 말한다 — 사용자에게는 눌러도 아무 일이
    없는 것과 같고, 사유조차 없어 더 나쁘다. 판정은
    :func:`~foms.services.jobs.queue.get_rq_runtime_status` 하나로 한다
    (``push_sender.enqueue_push_for_notification`` 과 같은 형태).

    응답 ``data.rev`` 는 지금 워터마크의 지문이다(:func:`_watermark_rev`). 화면은 이 값을
    기준점으로 잡고 ``GET /admin/naver-ingest/run-state`` 를 폴링해 값이 바뀌면 수집이
    끝난 것으로 본다.

    Returns:
        성공: ``{"success": True, "data": {"queued", "rev", "worker_count",
        "worker_count_known"}}``. ``worker_count_known`` 이 False 면 ``worker_count`` 의
        0 은 "0대"가 아니라 **"못 셌다"** 는 뜻이다.
        워커 없음(**확실히 0대일 때만**)·큐 장애: 503 + 사람 말로 된 사유.
    """
    db = get_db()
    status = get_rq_runtime_status()
    worker_count = int(status.get("worker_count", 0) or 0)
    # **"0대"와 "못 셌다"를 가른다.** ping 은 통했는데 그 직후 ``Worker.count`` 가 실패하는
    # 짧은 창이 실재한다. 예전에는 그 실패가 조용히 0 이 되어, 워커가 멀쩡히 도는데도
    # 화면이 "한 대도 살아 있지 않습니다. WORKER 서비스를 확인하세요"라고 말했다 —
    # 사람을 엉뚱한 곳으로 보내는 문구다(2026-08-26 CEO 지적). 못 셌으면 막지 않고
    # 그대로 넣는다: 진짜로 큐가 죽었다면 바로 아래 enqueue 가 False 를 돌려주고
    # 그때는 "큐 장애"라는 **맞는** 사유가 나간다.
    worker_count_known = bool(status.get("worker_count_known", True))
    if status.get("state") == "reachable" and worker_count_known and worker_count == 0:
        log_access(
            "네이버 주문 수집 수동 실행 실패(워커 없음)",
            session.get("user_id"),
            action="NAVER_INGEST_RUN_NOW",
            detail={"queued": False, "reason": "no_worker", "worker_count": 0},
        )
        return jsonify({
            "success": False,
            "data": None,
            "error": "수집을 맡을 워커가 한 대도 살아 있지 않습니다. 지금 넣으면 아무도 "
                     "꺼내지 않는 큐에 남으므로 넣지 않았습니다. WORKER 서비스 상태를 "
                     "확인한 뒤 다시 눌러 주세요.",
        }), 503
    # 기준 지문은 **큐에 넣기 전에** 읽는다. enqueue 뒤에 읽으면 그 사이 워커가 스윕을
    # 끝냈을 때 기준점이 이미 새 값이라, 화면은 바뀔 리 없는 값을 90초 동안 지켜본다.
    base_rev = _watermark_rev(_watermark_view(db))
    queued = enqueue_naver_order_sync(dry_run=False)
    log_access(
        "네이버 주문 수집 수동 실행" + ("" if queued else " 실패(큐 없음)"),
        session.get("user_id"),
        action="NAVER_INGEST_RUN_NOW",
        detail={"queued": bool(queued), "worker_count": worker_count,
                "worker_count_known": worker_count_known},
    )
    if not queued:
        return jsonify({
            "success": False,
            "error": "작업 큐에 넣지 못했습니다(REDIS_URL 미설정 또는 큐 장애). "
                     "네이버 호출은 WORKER 에서만 가능하므로 web 직접 실행은 없습니다.",
        }), 503
    return jsonify({"success": True, "error": None, "data": {
        "queued": True,
        "rev": base_rev,
        "worker_count": worker_count,
        "worker_count_known": worker_count_known,
    }})


@admin_bp.route("/admin/naver-ingest/run-state")
@login_required
@role_required(["ADMIN"])
def naver_ingest_run_state():
    """수집 워터마크의 현재 상태만 돌려준다 — "지금 수집" 이 끝났는지 묻는 자리.

    "지금 수집" 은 enqueue 로 끝나고 실제 수집은 WORKER 가 몇 초~몇 분 뒤에 한다. 화면이
    F5 를 기다리는 대신 이 경로를 짧게 폴링해 ``rev`` 가 바뀌면 그때 다시 그린다.

    **읽기 전용 GET 이다** — mutation 이 아니라 write manifest 등재도 감사 라벨도 없다.
    다만 실행 이력은 수집 규모를 드러내므로 권한은 "지금 수집" 과 같은 ADMIN 으로 묶는다
    (:func:`naver_ingest_run_now`). 판정은 하지 않는다 — 성공/실패를 어떻게 보여줄지는
    화면 몫이고, 여기서는 워커가 쓴 값과 그 지문만 준다.

    Returns:
        ``{"success": True, "data": {"rev", "last_run_at", "last_summary", "last_error"},
        "error": None}``. ``last_summary`` 는 화면 문구와 같은 한 줄 문자열이다.
    """
    db = get_db()
    view = _watermark_view(db)
    return jsonify({"success": True, "error": None, "data": {
        "rev": _watermark_rev(view),
        "last_run_at": str(view.get("last_run_at") or ""),
        "last_summary": _run_summary_text(view.get("last_summary")),
        "last_error": str(view.get("last_error") or ""),
    }})


@admin_bp.route("/admin/naver-ingest/backfill", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_backfill():
    """"과거 주문 소급 수집" — 구간을 검사하고 rq 큐에 넣기만 한다(실행은 WORKER).

    수집 워터마크는 **앞으로만** 간다. 첫 실행(2026-08-25) 이전에 들어온 네이버 주문은
    FOMS 에 원본이 아예 없고, 원본이 없으면 붙이기 후보에도 일괄 발송 대상에도 나타나지
    않는다 — 붙이기로는 못 메우는 구멍이라 과거를 한 번 긁어와야 한다.

    구간 검사는 **넣기 전에** 여기서 한다. 큐에 들어간 뒤에 거절하면 사람은 "요청했다"는
    말만 듣고 아무 일도 안 일어난 것을 나중에야 안다. 판정 규칙 자체는 서비스와 같은
    함수(:func:`~foms.services.integrations.naver_commerce.backfill.validate_range`)를 쓴다
    — 두 벌이 되면 화면이 통과시킨 구간을 워커가 거절한다.

    "지금 수집" 과 같은 워커 판정 규율을 쓴다(확실히 0대일 때만 막는다).

    Body:
        ``from``·``to``: ``YYYY-MM-DD`` (form 또는 JSON). ``to`` 는 그날 끝까지로 읽는다.

    Returns:
        성공: ``{"success": True, "data": {"queued", "rev", "from", "to"}}``.
        구간 오류: 400. 워커 없음·큐 장애: 503 + 사람 말로 된 사유.
    """
    from foms.services.integrations.naver_commerce import backfill as bf

    payload = request.get_json(silent=True) if request.is_json else None
    payload = payload if isinstance(payload, dict) else {}
    raw_from = str(payload.get("from") or request.form.get("from") or "").strip()[:10]
    raw_to = str(payload.get("to") or request.form.get("to") or "").strip()[:10]
    try:
        begin = datetime.datetime.strptime(raw_from, "%Y-%m-%d")
        finish = datetime.datetime.strptime(raw_to, "%Y-%m-%d")
    except ValueError:
        return jsonify({
            "success": False, "data": None,
            "error": "날짜 형식이 올바르지 않습니다. 2026-06-03 처럼 시작일과 종료일을 적어 주세요.",
        }), 400
    # 종료일은 **그날 끝까지**로 읽는다. 날짜만 받아 0시로 두면 사람이 고른 마지막 날이
    # 통째로 빠지고, 그 침묵은 "그날은 주문이 없었다"로 읽힌다.
    finish = finish + datetime.timedelta(days=1) - datetime.timedelta(milliseconds=1)
    now = now_kst()
    try:
        begin, finish = bf.validate_range(begin, finish, now=now)
    except bf.BackfillRangeError as exc:
        return jsonify({"success": False, "data": None, "error": str(exc)}), 400

    db = get_db()
    status = get_rq_runtime_status()
    worker_count = int(status.get("worker_count", 0) or 0)
    worker_count_known = bool(status.get("worker_count_known", True))
    if status.get("state") == "reachable" and worker_count_known and worker_count == 0:
        log_access(
            "네이버 과거 주문 소급 수집 실패(워커 없음)",
            session.get("user_id"),
            action="NAVER_INGEST_BACKFILL_ENQUEUE",
            detail={"queued": False, "reason": "no_worker",
                    "from": begin.isoformat(), "to": finish.isoformat()},
        )
        return jsonify({
            "success": False, "data": None,
            "error": "수집을 맡을 워커가 한 대도 살아 있지 않습니다. 지금 넣으면 아무도 "
                     "꺼내지 않는 큐에 남으므로 넣지 않았습니다. WORKER 서비스 상태를 "
                     "확인한 뒤 다시 눌러 주세요.",
        }), 503

    base_rev = str(bf.read_state(db).get("rev") or "")
    queued = enqueue_naver_backfill(begin.isoformat(), finish.isoformat())
    log_access(
        "네이버 과거 주문 소급 수집 요청" + ("" if queued else " 실패(큐 없음)"),
        session.get("user_id"),
        action="NAVER_INGEST_BACKFILL_ENQUEUE",
        detail={"queued": bool(queued), "from": begin.isoformat(), "to": finish.isoformat(),
                "worker_count": worker_count, "worker_count_known": worker_count_known},
    )
    if not queued:
        return jsonify({
            "success": False, "data": None,
            "error": "작업 큐에 넣지 못했습니다(REDIS_URL 미설정 또는 큐 장애). "
                     "네이버 호출은 WORKER 에서만 가능하므로 web 직접 실행은 없습니다.",
        }), 503
    return jsonify({"success": True, "error": None, "data": {
        "queued": True,
        "rev": base_rev,
        "from": begin.isoformat(),
        "to": finish.isoformat(),
    }})


@admin_bp.route("/admin/naver-ingest/backfill-state")
@login_required
@role_required(["ADMIN"])
def naver_ingest_backfill_state():
    """소급 수집이 어디까지 갔는지만 돌려준다(읽기 전용 GET).

    백필은 창(하루)마다 커밋하며 진척을 남긴다. 화면은 이 경로를 폴링해 ``rev`` 가 바뀌면
    다시 그린다 — F5 를 기다리게 하면 사람은 멈춘 것으로 읽는다.

    **쓰기가 없다** — write manifest 등재도 감사 라벨도 없다(GET 은 대상 밖). 권한은
    실행과 같은 ADMIN 으로 묶는다.

    Returns:
        ``{"success": True, "data": {"rev", "running", "requested_from", "requested_to",
        "done_through", "last_summary", "last_error", "finished_at"}}``.
    """
    from foms.services.integrations.naver_commerce import backfill as bf

    state = bf.read_state(get_db())
    summary = state.get("last_summary") if isinstance(state.get("last_summary"), dict) else {}
    return jsonify({"success": True, "error": None, "data": {
        "rev": str(state.get("rev") or ""),
        "running": bool(state.get("running")),
        "requested_from": str(state.get("requested_from") or ""),
        "requested_to": str(state.get("requested_to") or ""),
        "done_through": str(state.get("done_through") or ""),
        "finished_at": str(state.get("finished_at") or ""),
        "last_error": str(state.get("last_error") or ""),
        "last_summary": dict(summary or {}),
    }})


@admin_bp.route("/admin/naver-ingest/app-expiry", methods=["POST"])
@login_required
@role_required(["ADMIN"])
def naver_ingest_set_app_expiry():
    """커머스API 앱 인증 만료일을 사람이 적어 둔다 — 만료 경고(T7)의 **입력면**.

    이 값은 API 로 못 읽는다. 커머스API센터 화면의 `인증 기한` 을 사람이 보고 옮겨 적는
    수밖에 없다. 저장 함수(:func:`~foms.services.integrations.naver_commerce.app_expiry.
    set_expiry_date`)는 처음부터 있었는데 **값을 넣을 자리가 화면에 없었다** — 그래서
    운영 카드는 늘 `미등록` 이었고, 만료되면 앱이 자동 휴면되어 수집이 전면 중단되는데도
    D-7 경고가 한 번도 뜰 수 없는 상태였다.

    되돌릴 수 있는 쓰기다(잘못 적었으면 다시 적으면 덮인다). 그래도 감사에는 남긴다 —
    수집이 멈춘 뒤 "누가 언제 무엇으로 바꿨나"를 묻게 되는 값이다.

    날짜가 바뀌면 :func:`set_expiry_date` 가 임계값 알림 이력을 지운다(갱신했으면 다시
    알려야 한다). 여기서 따로 손대지 않는다 — 규칙이 두 벌이 되면 갈린다.

    Body:
        ``expires_on``: ``YYYY-MM-DD`` (form 또는 JSON). 그 밖의 형식은 400.

    Returns:
        성공: ``{"success": True, "data": {"expires_on", "days_left"}, "error": None}``.
        형식 오류·상식 밖 연도: 400 + 사람 말로 된 사유.
    """
    raw = request.form.get("expires_on")
    if raw is None and request.is_json:
        raw = (request.get_json(silent=True) or {}).get("expires_on")
    raw = str(raw or "").strip()[:10]
    try:
        expires_on = datetime.datetime.strptime(raw, "%Y-%m-%d").date()
    except ValueError:
        return jsonify({
            "success": False, "data": None,
            "error": "날짜 형식이 올바르지 않습니다. 2027-02-23 처럼 적어 주세요.",
        }), 400
    # 오타 방지선. 연도 한 자리를 잘못 치면(2207) 화면이 `180일 남음` 대신 66,000일을
    # 말하고 만료 경고는 영원히 안 뜬다 — 조용히 무력화되는 자리라 여기서 막는다.
    today = datetime.date.today()
    if not (today - datetime.timedelta(days=365 * 5)
            <= expires_on <= today + datetime.timedelta(days=365 * 5)):
        return jsonify({
            "success": False, "data": None,
            "error": "만료일이 오늘로부터 5년 밖입니다. 연도를 다시 확인해 주세요.",
        }), 400

    db = get_db()
    from foms.services.integrations.naver_commerce import app_expiry

    app_expiry.set_expiry_date(db, expires_on)
    db.commit()
    log_access(
        f"네이버 커머스API 인증 만료일 등록 ({expires_on.isoformat()})",
        session.get("user_id"),
        action="NAVER_INGEST_SET_APP_EXPIRY",
        detail={"expires_on": expires_on.isoformat()},
    )
    # 남은 일수는 화면과 **같은 함수**로 만든다 — 두 벌이 되면 저장 직후 화면과
    # 새로고침한 화면이 다른 수를 말한다.
    return jsonify({"success": True, "error": None, "data": _expiry_view(db)})


__all__ = [
    "naver_ingest_dashboard",
    "naver_ingest_dock_state",
    "naver_ingest_mark_reviewed",
    "naver_ingest_set_assignee",
    "naver_ingest_triage",
    "naver_ingest_triage_pane",
    "naver_ingest_run_now",
    "naver_ingest_set_app_expiry",
    "naver_ingest_run_state",
    "naver_ingest_backfill",
    "naver_ingest_backfill_state",
    "naver_ingest_snapshot",
    "PAGE_SIZE",
    "VALID_STATUSES",
]

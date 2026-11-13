"""생산 파트 표시 받아 오기 API — 다른 사람 표시를 30초마다(설계서 §15.4 GET 줄 · §15.6 끝, P15-7).

``GET /api/production/part-marks?order_ids=1,2,3&since=<서버 시각>`` — ``updated_at > since`` 인 표시 줄만 돌려준다.

* 같은 Blueprint(``production_part_marks``)에 라우트만 더한다 — 쓰기 모듈(``part_marks.py``)이 500줄 래칫에 닿아 따로 둔다.
  ``foms/api/production/__init__.py`` 가 이 모듈을 import 해야 라우트가 붙는다.
* 문: 생산 첫 화면을 볼 수 있는 사람(:func:`can_view_production_home`) + 주문 읽기 범위(:func:`user_can_read_order`).
  협력사 · 켜진 프리랜서는 주문마다 판정이 갈리는 계정이라 이 화면 목록을 받지 않는다(403). 우리 직원은 주문 읽기가
  전역이라, 살아 있는 ERP 주문 · 생산 첫 화면 단계가 아닌 id(지운 주문 · 초안 · ERP 밖 주문 · 없는 id)는 **조용히 뺀다**.
* 쿼리 1(주문 수와 무관): 표시 줄 ⋈ 주문(기본 키) — ``order_id IN (…)`` 이 유일 제약
  ``uq_production_part_marks_order_key_part``(앞머리 ``order_id``)를 탄다.
* 응답 ``server_time`` = 다음 ``since``(:func:`part_sync_cursor` — 커밋 지연만큼 되감은 서버 시각). 기기 시계는 쓰지 않는다.
* 읽기라 쓰기 정책 가드 · CSRF 대상이 아니다(GET). 한 태블릿 시간당 120번(§15.6).
"""

from __future__ import annotations

import datetime
from typing import Any

from flask import g, jsonify, request
from sqlalchemy.exc import SQLAlchemyError

from db import get_db
from foms.api.production.part_marks import production_part_marks_bp
from foms.services.orders.order_mutation_policy import user_can_read_order
from foms.services.production.home_access import can_view_production_home
from foms.services.production.part_board import other_part_word, part_sync_cursor
from foms.services.production.part_mark_rules import mark_payload
from foms.services.production_home_read_model import PRODUCTION_HOME_STAGE_CODES
from models import Order, ProductionPartMark

#: 한 번에 받는 주문 수 상한(화면은 넘으면 나눠 부른다).
SYNC_MAX_ORDERS = 300
_SINCE_MAX_LEN = 40


class _BadRequest(Exception):
    """질의 값이 틀렸을 때(상태 · 코드 · 글)."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _fail(status: int, code: str, message: str):
    return jsonify({"success": False, "data": {"code": code}, "error": message}), status


def parse_order_ids(raw: Any) -> list[int]:
    """``order_ids`` 글(쉼표) → 겹침 없는 양의 정수 id 목록(보낸 순서).

    Raises:
        _BadRequest: 비었거나 숫자가 아닌 칸 · :data:`SYNC_MAX_ORDERS` 초과.
    """
    parts = [p.strip() for p in str(raw or "").split(",") if p.strip()]
    if not parts:
        raise _BadRequest(400, "BAD_REQUEST", "주문 번호가 없어요.")
    if len(parts) > SYNC_MAX_ORDERS:
        raise _BadRequest(400, "TOO_MANY", f"한 번에 주문 {SYNC_MAX_ORDERS}건까지만 받을 수 있어요.")
    ids: list[int] = []
    for part in parts:
        if not part.isdigit() or int(part) <= 0:
            raise _BadRequest(400, "BAD_REQUEST", "주문 번호가 올바르지 않아요.")
        if int(part) not in ids:
            ids.append(int(part))
    return ids


def parse_since(raw: Any) -> datetime.datetime:
    """``since`` 글(서버가 준 ISO 시각) → UTC naive datetime. 시간대가 붙어 있으면 UTC 로 바꾼다.

    Raises:
        _BadRequest: 없거나 ISO 시각이 아닐 때.
    """
    text = str(raw or "").strip()
    try:
        if not text or len(text) > _SINCE_MAX_LEN:
            raise ValueError(text)
        value = datetime.datetime.fromisoformat(text)
    except ValueError:
        raise _BadRequest(400, "BAD_SINCE", "받아 올 기준 시각이 올바르지 않아요. 다시 받아 주세요.") from None
    if value.tzinfo is not None:
        value = value.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    return value


def fetch_marks_since(db: Any, order_ids: list[int], since: datetime.datetime) -> list[ProductionPartMark]:
    """그 주문들 표시 줄 중 ``updated_at > since`` 인 줄 — 쿼리 한 번(주문 수와 무관).

    살아 있는 ERP 주문 · 생산 첫 화면 단계(``PRODUCTION_HOME_STAGE_CODES``, 첫 화면 행 쿼리와 같은 범위)만 남긴다.
    """
    return (
        db.query(ProductionPartMark)
        .join(Order, Order.id == ProductionPartMark.order_id)
        .filter(
            ProductionPartMark.order_id.in_(sorted(order_ids)),
            ProductionPartMark.updated_at > since,
            Order.active_filter(),
            Order.is_erp_order.is_(True),
            Order.erp_stage_code.in_(list(PRODUCTION_HOME_STAGE_CODES)),
        )
        .order_by(ProductionPartMark.updated_at.asc(), ProductionPartMark.id.asc())
        .all()
    )


def sync_mark_body(row: ProductionPartMark) -> dict[str, Any]:
    """카드가 쓰는 표시 한 장 — 쓰기 응답과 같은 꼴(``mark_payload``) + 다른 파트 한 줄 낱말(``word`` · ``tone``)."""
    payload = mark_payload(row)
    word = other_part_word(str(row.part), payload["state"])
    return {**payload, "order_id": int(row.order_id), "drawing_key": str(row.drawing_key), "part": str(row.part),
            "word": word["word"], "tone": word["tone"]}


@production_part_marks_bp.route("/part-marks", methods=["GET"])
def api_part_marks_since():
    """그 주문들의 ``since`` 뒤 바뀐 표시 줄 + 다음 ``since``(``server_time``). 볼 수 없는 사람 403."""
    user = getattr(g, "current_user", None)
    if user is None:
        return _fail(401, "AUTH_REQUIRED", "로그인이 필요해요.")
    # 주문 없이 묻는 읽기 범위 — 우리 직원은 전역 True, 협력사 · 켜진 프리랜서는 주문마다라 False(이 목록은 막는다).
    if not can_view_production_home(user) or not user_can_read_order(user, None):
        return _fail(403, "FORBIDDEN", "생산 화면을 볼 수 있는 직원만 받을 수 있어요.")
    try:
        order_ids = parse_order_ids(request.args.get("order_ids"))
        since = parse_since(request.args.get("since"))
    except _BadRequest as exc:
        return _fail(exc.status, exc.code, exc.message)
    server_time = part_sync_cursor()  # 읽기 **전** 시각 — 읽는 사이 쓴 줄은 다음 번에 겹쳐 받는다
    db = get_db()
    try:
        rows = fetch_marks_since(db, order_ids, since)
    except SQLAlchemyError:
        db.rollback()
        return _fail(500, "READ_FAILED", "표시를 받아 오지 못했어요. 잠시 뒤 다시 받아 주세요.")
    response = jsonify({"success": True, "data": {"marks": [sync_mark_body(r) for r in rows],
                                                  "server_time": server_time}, "error": None})
    response.headers["Cache-Control"] = "private, no-store"
    return response, 200

"""카카오 알림톡 수동 발송 API (v1 T4).

주문 상세에서 실측 예약 안내 알림톡을 사람이 확인하고 보내는 두 라우트다.

* ``GET  /api/kakao/alimtalk/preview/<order_id>`` — **서버 저장본**으로 렌더한 본문 +
  자격 판정 + 마지막 발송 이력.
* ``POST /api/kakao/alimtalk/send-manual/<order_id>`` — 같은 저장본으로 재렌더해 발송.

두 라우트 모두 **클라이언트가 보낸 본문 텍스트를 받지 않는다**(스펙 §6.4 F2) — 미리보기와
실제 발송이 같은 SSOT(``order.structured_data``)에서 나와야 위변조·불일치가 원천 차단된다.
CSRF/Origin 은 공용 write guard before_request(WRITE-GUARD-01)가 담당하므로 라우트에
별도 데코레이터를 두지 않는다(manifest 등재가 그 계약).
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Optional

from flask import Blueprint, jsonify, session

from db import get_db
from models import Order
from foms.web.auth import login_required, role_required
from foms.services.kakao_alimtalk import (
    _ineligible_reason,  # 자격 판정 SSOT — API 에서 재구현하면 발송/표시 판정이 갈린다
    is_configured,
    render_preview,
    send_alimtalk,
)

logger = logging.getLogger(__name__)

kakao_bp = Blueprint('kakao', __name__, url_prefix='/api/kakao')

#: push-manual 선례와 동일 권한(스펙 §6.4 L3). VIEWER 는 제외.
_ALIMTALK_ROLES = ['ADMIN', 'MANAGER', 'STAFF']

__all__ = ['kakao_bp']


def _load_order(order_id: int) -> Optional[Order]:
    """활성 주문 1건을 조회한다(삭제 주문은 발송 대상 아님).

    Args:
        order_id: 주문 id.

    Returns:
        주문 객체. 없거나 soft-delete 됐으면 ``None``.
    """
    return get_db().query(Order).filter(Order.id == order_id, Order.active_filter()).first()


def _envelope(data: Any, error: Optional[str], status: int = 200):
    """프로젝트 표준 응답 ``{success, data, error}`` 를 만든다."""
    return jsonify({'success': error is None, 'data': data, 'error': error}), status


@kakao_bp.route('/alimtalk/preview/<int:order_id>', methods=['GET'])
@login_required
@role_required(_ALIMTALK_ROLES)
def api_alimtalk_preview(order_id: int):
    """실측 예약 알림톡 미리보기(서버 렌더).

    Args:
        order_id: 주문 id (URL).

    Returns:
        ``data = {'text', 'eligible', 'ineligible_reason', 'last', 'configured'}``.
        ``text`` 는 저장본 기준 치환 결과이며, 미자격이어도 사유 확인용으로 함께 준다.
    """
    order = _load_order(order_id)
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    sd = order.structured_data or {}
    reason = _ineligible_reason(order, sd)
    return _envelope({
        'text': render_preview(sd),
        'eligible': reason is None,
        'ineligible_reason': reason,
        'last': sd.get('alimtalk_measurement'),
        'configured': is_configured(),
    }, None)


@kakao_bp.route('/alimtalk/send-manual/<int:order_id>', methods=['POST'])
@login_required
@role_required(_ALIMTALK_ROLES)
def api_alimtalk_send_manual(order_id: int):
    """실측 예약 알림톡 수동 발송(요청 body 는 읽지 않는다).

    멱등키는 항상 새 ``...:manual:{uuid4}`` 다 — 자동 발송만 멱등키로 막고, 수동
    재발송은 이력 확인 모달이 담당한다(스펙 D2). 발송자 user_id 는 감사용으로 이력에
    남는다.

    Args:
        order_id: 주문 id (URL).

    Returns:
        성공/실패 모두 200 + ``data = {'sent': bool, 'error': str | None}``.
        서버 미설정은 503, 대상 주문 없음은 404.
    """
    if not is_configured():
        return _envelope(None, 'not_configured', 503)
    if _load_order(order_id) is None:
        return _envelope(None, 'order_not_found', 404)

    result = send_alimtalk(
        order_id,
        manual_by=session.get('user_id'),
        dedupe_key=f'alimtalk:measure:{order_id}:manual:{uuid.uuid4()}',
    )
    logger.info("알림톡 수동 발송 (order_id=%s, sent=%s, error=%s)",
                order_id, result.get('sent'), result.get('error'))
    return _envelope(result, result.get('error'))

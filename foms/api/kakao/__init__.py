"""카카오 알림톡 수동 발송 API (v1 T4).

주문 상세에서 실측 예약 안내 알림톡을 사람이 확인하고 보내는 두 라우트다.

* ``GET  /api/kakao/alimtalk/preview/<order_id>`` — **서버 저장본**으로 렌더한 본문 +
  자격 판정 + 마지막 발송 이력.
* ``POST /api/kakao/alimtalk/send-manual/<order_id>`` — 같은 저장본으로 재렌더해 발송.
* ``POST /api/kakao/alimtalk/confirm-channel/<order_id>`` — 발송 1분 뒤 벤더에 한 번 물어
  실제 나간 채널(카톡/문자 대체발송)을 이력에 굳힌다(T15).

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
from foms.web.auth import log_access, login_required, role_required
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.kakao_alimtalk import (
    _ineligible_reason,  # 자격 판정 SSOT — API 에서 재구현하면 발송/표시 판정이 갈린다
    confirm_channel,
    is_configured,
    is_text_channel,
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
        성공/실패 모두 200 + ``data = {'sent': bool, 'error': str | None, 'last': dict}``.
        ``last`` 는 방금 기록된 발송 이력이다 — 화면의 발송 흔적 칩이 이걸로 즉시 갱신해
        추가 조회를 하지 않는다(T15). 서버 미설정은 503, 대상 주문 없음은 404.
    """
    if not is_configured():
        return _envelope(None, 'not_configured', 503)
    order = _load_order(order_id)
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    actor_user_id = session.get('user_id')
    result = send_alimtalk(
        order_id,
        manual_by=actor_user_id,
        dedupe_key=f'alimtalk:measure:{order_id}:manual:{uuid.uuid4()}',
    )
    logger.info("알림톡 수동 발송 (order_id=%s, sent=%s, error=%s)",
                order_id, result.get('sent'), result.get('error'))

    # 고객에게 나간 발송은 성공·실패 모두 감사에 남긴다(채널톡 발송 선례와 동일 계약).
    # 본문은 남기지 않는다 — 치환 텍스트에 고객 정보가 섞인다(원장 PII 최소화). 본문
    # 이력은 structured_data 의 alimtalk_measurement 가 이미 소유한다.
    sent = bool(result.get('sent'))
    error = result.get('error')
    # send_alimtalk 은 자기 세션에서 이력을 커밋했다 — 이 요청 세션의 사본은 낡았다.
    get_db().expire(order)
    result['last'] = (order.structured_data or {}).get('alimtalk_measurement')
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order_id, action='ALIMTALK_MANUAL_SENT',
                              note=None if sent else f'실패: {error}', **context),
        actor_user_id,
        action='ALIMTALK_MANUAL_SENT', target_type='order', target_id=int(order_id),
        detail={'sent': sent, 'error': error, 'template': 'measure', **context},
    )
    return _envelope(result, error)


@kakao_bp.route('/alimtalk/confirm-channel/<int:order_id>', methods=['POST'])
@login_required
@role_required(_ALIMTALK_ROLES)
def api_alimtalk_confirm_channel(order_id: int):
    """발송된 알림톡의 실제 채널(카톡 / 문자 대체발송)을 벤더에 한 번 물어 확정한다.

    화면의 발송 흔적 칩이 '카톡으로 나갔는지 문자로 나갔는지'를 표시하려면 이 확정이
    필요하다 — 접수 시점 type 은 항상 ``ATA`` 이고 카톡이 실패해야 벤더가 문자로 바꾼다.
    호출은 멱등이다: 이미 확정된 건은 벤더를 부르지 않고 저장된 값을 그대로 돌려준다.

    아직 확인할 수 없는 상태(발송 1분 미경과·발송 이력 없음)는 **오류가 아니라 정상**이라
    200 + error 코드로 조용히 돌려준다 — 화면은 칩을 그대로 두면 된다.

    Args:
        order_id: 주문 id (URL).

    Returns:
        ``data = {'channel', 'checked', 'cached', 'error'}``. 서버 미설정은 503,
        대상 주문 없음은 404.
    """
    order = _load_order(order_id)
    if order is None:
        return _envelope(None, 'order_not_found', 404)

    result = confirm_channel(order_id)
    error = result.get('error')
    if error == 'not_configured':
        return _envelope(result, error, 503)

    # 이번 호출이 실제로 벤더에 물어 확정한 경우에만 감사에 남긴다(캐시 반환은 소음).
    if result.get('checked') and not result.get('cached'):
        channel = result.get('channel')
        context = order_audit_context(order)
        note = '문자 대체발송' if is_text_channel(channel) else (channel or '확인 불가')
        log_access(
            describe_order_action(order_id=order_id, action='ALIMTALK_CHANNEL_CONFIRMED',
                                  note=note, **context),
            session.get('user_id'),
            action='ALIMTALK_CHANNEL_CONFIRMED', target_type='order', target_id=int(order_id),
            detail={'channel': channel, 'template': 'measure', **context},
        )
    return _envelope(result, error)

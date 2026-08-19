"""
채널톡 연동 API Blueprint.
수동 푸쉬, 웹훅 수신 등 채널톡 양방향 통신을 담당.
"""

import copy
import datetime
import hashlib
import json
import logging
import os
import traceback

from flask import Blueprint, g, jsonify, request
from sqlalchemy.orm.attributes import flag_modified

from db import get_db
from models import Order, OrderAttachment, OrderEvent
from foms.web.auth import log_access, login_required, role_required
from foms.services.attachment_sort import attachment_sort_key
from foms.services.audit_message_display import describe_order_action
from foms.services.orders.audit_order_context import order_audit_context
from foms.services.channel_as_attachments import (
    last_pushed_max_attachment_id,
    select_as_push_attachments,
)
from foms.services.channel_as_message import build_as_push_text
from foms.services.orders.as_log import decorate_entry
from foms.services.channel_client import is_configured
from foms.services.channel_dispatch import dispatch_order_event
from foms.services.channel_policy import (
    MAX_MANUAL_ATTACHMENTS,
    ChannelGroupRetiredError,
    get_routing_group_id,
)
from foms.services.orders.revision import execute_order_mutation
from foms.services.sidefx_outbox import enqueue_side_effect
from foms.services.storage import get_storage
from foms.services.channel_delivery import (
    check_legacy_only_success_after_cutover,
    get_delivery_metrics,
    get_queue_backlog,
)
from foms.services.jobs.queue import get_rq_runtime_status

logger = logging.getLogger(__name__)

_MAX_TEXT_LENGTH = 4000
_MIN_CHANGE_NOTE_LEN = 1
_MAX_CHANGE_NOTE_LEN = 500
_RETIRED_GROUP_MESSAGE = '이 채널톡 방(554075)으로의 PUSH 기능은 삭제되었습니다.'
# 전송 확인창에 내려보내는 첨부 후보 상한(미선택분 포함). 전송 상한(20)보다 넉넉해야
# 사용자가 기본 선정 밖의 파일을 되살릴 수 있다.
_PREVIEW_CANDIDATE_MAX = 40

# CHANNEL-WRITER-01: push 전송 결과 metadata 를 기록하는 typed command 상수.
# 전송(transport provider: dispatch_order_event/channel_functions)은 무변경 — 아래 이름들은
# 오직 metadata 기록 축(mutation_version/receipt/OrderEvent/side-effect outbox)에만 쓴다.
# message_id 는 한 send 의 안정적 신원이므로 idempotency/dedupe 축으로 삼는다(같은 send
# 결과를 두 번 기록해도 receipt replay + outbox dedupe 로 history/event 정확히 1).
_PUSH_POLICY_ID = 'CHANNEL_PUSH'             # execute_order_mutation receipt policy_id
_PUSH_EVENT_TYPE = 'CHANNELTALK_PUSH'        # OrderEvent.event_type
_PUSH_EFFECT_TYPE = 'CHANNEL_PUSH_RECORDED'  # side-effect outbox effect_type
_PUSH_SIDEFX_DOMAIN = 'ORDER_EVENT'          # outbox one-of FK 매트릭스 도메인
_PUSH_CHANGE_LOG_CAP = 20                    # structured_data 이력 change_log 보존 개수

# push_kind → (첨부 category, structured_data 이력 키, 그룹 환경변수명)
_PUSH_KIND_CONFIG = {
    'measurement': {
        'category': 'measurement',
        'history_key': 'channeltalk_push',
        'group_env': 'CHANNEL_GROUP_MEASUREMENT',
    },
    'drawing': {
        'category': 'drawing',
        'history_key': 'channeltalk_push_drawing',
        'group_env': 'CHANNEL_GROUP_DRAWING',
    },
    'as': {
        'category': 'as',
        'history_key': 'channeltalk_push_as',
        'group_env': 'CHANNEL_GROUP_AS',
    },
}

channel_integration_bp = Blueprint('channel_integration', __name__, url_prefix='/api/channel')

_MIME_MAP = {
    'jpg': 'image/jpeg', 'jpeg': 'image/jpeg', 'png': 'image/png',
    'gif': 'image/gif', 'webp': 'image/webp',
    'mp4': 'video/mp4', 'mov': 'video/quicktime', 'avi': 'video/avi',
    'mkv': 'video/x-matroska', 'webm': 'video/webm',
}


def _infer_mime(filename: str, file_type: str) -> str:
    """
    첨부파일 MIME 타입 추론.

    Args:
        filename: 파일명 (확장자 포함)
        file_type: OrderAttachment.file_type ('image' 또는 'video')

    Returns:
        MIME 타입 문자열
    """
    if filename and '.' in filename:
        ext = filename.rsplit('.', 1)[-1].lower()
        if ext in _MIME_MAP:
            return _MIME_MAP[ext]
    return 'video/mp4' if file_type == 'video' else 'image/jpeg'


def _parse_attachment_ids(raw) -> tuple:
    """전송 확인창이 지정한 첨부 id 목록 파싱 → ``(ids | None, 오류문구 | None)``.

    ``None`` 반환은 "지정 없음"(서버 기본 선정 규칙 사용)이고, 빈 리스트는 "첨부 없이
    본문만 전송"이라는 명시적 선택이라 서로 구분한다.

    Args:
        raw: 요청 payload 의 ``attachment_ids`` 원값.

    Returns:
        (첨부 id 리스트 또는 None, 사용자 문구 또는 None).
    """
    if raw is None:
        return None, None
    if not isinstance(raw, list):
        return None, 'attachment_ids 는 배열이어야 합니다.'
    # 전송 상한(20)은 배열 **앞쪽**을 남기는 절단이다. 여기서 거절하면 확인창이
    # 21장을 골랐을 때 지정 순서가 아니라 요청 실패가 된다(AS-SORT-01).
    # 확인창 후보 상한 밖의 초대형 배열만 막는다.
    if len(raw) > _PREVIEW_CANDIDATE_MAX:
        return None, f'첨부는 한 번에 최대 {_PREVIEW_CANDIDATE_MAX}개까지 지정할 수 있습니다.'
    ids = []
    for item in raw:
        # bool 은 int 의 하위형이라 명시적으로 배제한다(True 가 1번 첨부로 통과하는 것 방지).
        if isinstance(item, bool) or not isinstance(item, int):
            return None, 'attachment_ids 는 첨부 id(정수) 배열이어야 합니다.'
        if item not in ids:
            ids.append(item)
    return ids, None


def _push_mutation_hashes(
    order_id: int, push_kind: str, send_ref, is_resend: bool, change_note: str, group_id
) -> tuple:
    """(scope_hash, request_hash) — receipt 저장·same-key/different-hash 감지용 sha256.

    Args:
        order_id: 대상 주문 id(scope 축).
        push_kind: measurement/drawing/estimate(scope 축).
        send_ref: 전송 message_id(없으면 None) — request 신원.
        is_resend: 재전송 여부(request 내용).
        change_note: 재전송 변경 메모(request 내용).
        group_id: 전송 대상 채널 그룹(request 내용).

    Returns:
        (scope_hash, request_hash): 둘 다 64자 sha256 hex.
    """
    scope = hashlib.sha256(f"{_PUSH_POLICY_ID}:{order_id}:{push_kind}".encode()).hexdigest()
    request_payload = json.dumps(
        {
            'order_id': order_id,
            'push_kind': push_kind,
            'message_id': send_ref,
            'is_resend': is_resend,
            'change_note': change_note,
            'group_id': group_id,
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return scope, hashlib.sha256(request_payload.encode()).hexdigest()


def _record_push_metadata(
    db,
    *,
    order,
    history_key: str,
    push_kind: str,
    group_id,
    result: dict,
    is_resend: bool,
    change_note: str,
    pushed_by_name,
    actor_user_id,
    attachment_ids=None,
):
    """채널톡 push 전송 결과·metadata 를 typed command 로 원자 기록한다 (CHANNEL-WRITER-01).

    전송(dispatch_order_event)은 이 함수 밖에서 이미 끝났다(transport provider 무변경).
    여기서는 그 결과를 REV-00 ``execute_order_mutation`` 한 transaction 으로 묶어
    ``structured_data[history_key]`` 이력 + ``mutation_version`` bump + idempotency receipt +
    ``OrderEvent`` 1 + side-effect outbox **dedupe** enqueue 를 원자화한다. 같은 send 결과를
    두 번 기록(재시도)해도 receipt replay(같은 message_id) + outbox dedupe 로 history/event 는
    **정확히 1**(중복 폭주 없음). structured_data 수정은 lock 아래에서 copy.deepcopy +
    flag_modified 로 수행한다.

    Args:
        db: business transaction 세션(호출자 소유; 이 함수가 commit).
        order: 대상 Order(scope/order_ids 용, id 만 사용; 실제 write 는 lock 된 행에서).
        history_key: structured_data 이력 키(channeltalk_push[_drawing|_estimate]).
        push_kind: measurement/drawing/estimate.
        group_id: 전송된 채널 그룹 id(metadata).
        result: dispatch_order_event 반환 dict(``message_id`` 포함 가능).
        is_resend: 재전송이면 change_log 를 누적한다.
        change_note: 재전송 변경 메모(재전송이 아니면 '').
        pushed_by_name: 전송자 표시명(change_log 기록).
        actor_user_id: receipt/OrderEvent actor(로그인 사용자 id).
        attachment_ids: 이번에 실제로 전송한 첨부 id 목록(AS-FRESH-01 provenance).

    Returns:
        MutationResult: ``replayed`` 여부 포함. 호출자는 성공 응답만 만들면 된다.
    """
    msg_id = result.get('message_id')
    if not msg_id:
        logger.warning(
            "[채널톡 %s푸쉬] 전송 성공이나 message_id 미수신 (order_id=%s)", push_kind, order.id
        )
    sent_at = datetime.datetime.now(datetime.timezone.utc).isoformat()

    # message_id 없는 degraded 경로는 dedupe 축이 없으므로 idempotency/dedupe 를 끈다
    # (NULL 은 서로 distinct → 매번 새 receipt/outbox; 원본 동작과 동일하게 항상 기록).
    send_ref = str(msg_id) if msg_id else None
    # idempotency_key 는 String(64). ChannelTalk message id 는 짧지만 외부 입력이므로 64자
    # 초과 시 dedupe 를 끄고 계속 기록한다(500 대신 graceful — 원본 동작과 동일).
    if send_ref and len(send_ref) > 64:
        logger.warning(
            "[채널톡 %s푸쉬] message_id 길이 초과로 dedupe 생략 (order_id=%s, len=%s)",
            push_kind, order.id, len(send_ref),
        )
        send_ref = None
    idempotency_key = send_ref
    dedupe_key = (
        f"{_PUSH_EFFECT_TYPE}:{push_kind}:{order.id}:{send_ref}" if send_ref else None
    )
    scope_hash, request_hash = _push_mutation_hashes(
        order.id, push_kind, send_ref, is_resend, change_note, group_id
    )

    def _mutate(sess, orders):
        """row lock 아래에서 이력 write + OrderEvent 1 + side-effect dedupe enqueue."""
        o = orders[0]
        sd = copy.deepcopy(o.structured_data or {})
        prev = sd.get(history_key) or {}
        next_push = {
            'pushed': True,
            'message_id': msg_id,
            'group_id': group_id,
            'sent_at': sent_at,
            'is_modified': is_resend,
        }
        if is_resend:
            change_log = list(prev.get('change_log') or [])
            change_log.append({
                'at': sent_at,
                'by': pushed_by_name,
                'note': change_note,
                'message_id': msg_id,
            })
            next_push['change_log'] = change_log[-_PUSH_CHANGE_LOG_CAP:]
        # 발송 provenance(AS-FRESH-01 T9): 다음 PUSH 의 "미발송분" 판정 근거.
        # attachment_ids 는 **최신 1회분만** 둔다(누적하면 append-only JSONB 가 부푼다).
        # max_attachment_id 만 단조 유지 — 첨부를 0건 보낸 재전송이 기준선을 되돌리면
        # 이미 보낸 파일이 "미발송"으로 되살아난다.
        if attachment_ids is not None:
            ids = [int(i) for i in attachment_ids if isinstance(i, int)]
            next_push['attachment_ids'] = ids
            next_push['max_attachment_id'] = max([*ids, last_pushed_max_attachment_id(prev)])
        sd[history_key] = next_push
        o.structured_data = sd
        flag_modified(o, 'structured_data')

        event = OrderEvent(
            order_id=o.id,
            event_type=_PUSH_EVENT_TYPE,
            payload={
                'push_kind': push_kind,
                'history_key': history_key,
                'message_id': msg_id,
                'group_id': group_id,
                'is_resend': is_resend,
            },
            created_by_user_id=actor_user_id,
        )
        sess.add(event)
        sess.flush()  # event.id 확보(outbox one-of FK 참조)

        if dedupe_key:
            enqueue_side_effect(
                sess,
                source_domain=_PUSH_SIDEFX_DOMAIN,
                source_id=event.id,
                effect_type=_PUSH_EFFECT_TYPE,
                payload={'order_id': o.id, 'push_kind': push_kind, 'message_id': msg_id},
                dedupe_key=dedupe_key,
                provider_idempotency_key=send_ref,
            )
        return {o.id: [f"ORDER_DETAIL:{o.id}", "ORDERS_INDEX"]}

    try:
        outcome = execute_order_mutation(
            db,
            actor_user_id=actor_user_id,
            policy_id=_PUSH_POLICY_ID,
            order_ids=[order.id],
            scope_hash=scope_hash,
            request_hash=request_hash,
            mutation=_mutate,
            idempotency_key=idempotency_key,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    return outcome



def _audit_channel_push(order, push_kind: str, is_resend: bool, *,
                        actor_user_id, files_count: int | None = None) -> None:
    """채널톡 발송 1건을 구조화 감사로 남긴다(고객에게 나간 것은 반드시 추적 가능해야 한다).

    본문은 남기지 않는다 — 발송 텍스트에는 고객 정보가 섞인다(원장 PII 최소화).
    발송 본문 이력은 ``channel_delivery_logs`` 가 이미 소유한다.

    :param order: 대상 :class:`~models.Order`.
    :param push_kind: 발송 종류(``as``·``estimate`` 등).
    :param is_resend: 재발송 여부.
    :param actor_user_id: 발송자 user id.
    :param files_count: 함께 보낸 파일 수(있으면).
    """
    context = order_audit_context(order)
    log_access(
        describe_order_action(order_id=order.id, action="CHANNEL_PUSH_SENT",
                              note=f"{push_kind}{' 재발송' if is_resend else ''}", **context),
        actor_user_id,
        action="CHANNEL_PUSH_SENT", target_type="order", target_id=int(order.id),
        detail={"push_kind": push_kind, "is_resend": bool(is_resend),
                "files_count": files_count, **context},
    )


@channel_integration_bp.route('/push-manual', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_channel_push_manual():
    """
    ERP Beta 수동 채널톡 푸쉬.

    push_kind에 따라 변환 텍스트 + 해당 분류 첨부파일만 채널톡 그룹으로 전송합니다.
        - measurement(영발 PUSH): 실측 첨부 → 실측 그룹
        - drawing(발주 PUSH): 도면 첨부 → 도면 그룹(229625)
        - as(AS PUSH): AS 첨부 → AS 그룹(230351)

    Request JSON:
        order_id (int): 주문 ID
        text (str): 전송할 텍스트 (변환된 내용)
        push_kind (str): 'measurement'(기본) / 'drawing' / 'as'
        change_note (str, optional): 재전송 시 변경 내용 (1~500자, 필수)

    Returns:
        {success: bool, files_count: int, error: str}
    """
    db = get_db()
    try:
        payload = request.get_json(silent=True) or {}
        order_id = payload.get('order_id')
        text = (payload.get('text') or '').strip()
        push_kind = payload.get('push_kind') or 'measurement'
        change_note = (payload.get('change_note') or '').strip()

        if push_kind not in _PUSH_KIND_CONFIG:
            return jsonify({'success': False, 'message': f'지원하지 않는 push_kind: {push_kind}'}), 400
        kind_config = _PUSH_KIND_CONFIG[push_kind]

        if not order_id:
            return jsonify({'success': False, 'message': 'order_id가 없습니다.'}), 400
        # AS 본문은 서버가 저장된 주문으로 조립한다(SSOT). ERP 폼·AS 대시보드 어느 쪽에서
        # 쏘든 같은 문구가 나가야 하므로 클라이언트가 보낸 text 는 이 경로에서 신뢰하지 않는다.
        if push_kind != 'as':
            if not text:
                return jsonify({'success': False, 'message': '전송할 텍스트가 없습니다. 변환 버튼을 먼저 누르거나 내용을 입력해주세요.'}), 400
            if len(text) > _MAX_TEXT_LENGTH:
                return jsonify({'success': False, 'message': f'텍스트가 너무 깁니다 (최대 {_MAX_TEXT_LENGTH}자).'}), 400

        if not is_configured():
            msg = '채널톡 환경변수(CHANNEL_APP_SECRET, CHANNEL_ID)가 서버에 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        try:
            group_id = get_routing_group_id('manual', {'push_kind': push_kind})
        except ChannelGroupRetiredError as exc:
            logger.info("[채널톡 수동푸쉬] retired group blocked (group_id=%s, push_kind=%s)", exc.group_id, push_kind)
            return jsonify({
                'success': False,
                'message': _RETIRED_GROUP_MESSAGE,
                'error': _RETIRED_GROUP_MESSAGE,
            }), 410
        if not group_id:
            env_name = kind_config['group_env']
            msg = f'{env_name} 환경변수가 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': f'주문 #{order_id}을 찾을 수 없습니다.'}), 404

        if push_kind == 'as':
            text = build_as_push_text(order)
            if not text:
                return jsonify({
                    'success': False,
                    'message': 'AS 접수 내용이 없습니다. AS 접수를 먼저 등록한 뒤 다시 시도해주세요.',
                }), 400
            if len(text) > _MAX_TEXT_LENGTH:
                return jsonify({
                    'success': False,
                    'message': f'AS 접수 내용이 너무 깁니다 (최대 {_MAX_TEXT_LENGTH}자).',
                }), 400

        # 이전 푸쉬 이력 확인 (push_kind별 분리)
        sd = copy.deepcopy(order.structured_data or {})
        prev_push = sd.get(kind_config['history_key']) or {}
        is_resend = bool(prev_push.get('pushed'))

        if is_resend:
            if len(change_note) < _MIN_CHANGE_NOTE_LEN:
                return jsonify({
                    'success': False,
                    'message': f'재전송 시 변경 내용을 {_MIN_CHANGE_NOTE_LEN}자 이상 입력해주세요.',
                }), 400
        else:
            change_note = ''

        if change_note and len(change_note) > _MAX_CHANGE_NOTE_LEN:
            return jsonify({
                'success': False,
                'message': f'변경 내용은 최대 {_MAX_CHANGE_NOTE_LEN}자까지 입력할 수 있습니다.',
            }), 400

        # 해당 분류 첨부파일만. AS 기본 선정은 select_as_push_attachments 가
        # sort_order(없으면 id) 순으로 돌려준다. explicit ids 는 **배열 순서 그대로**.
        attachments = (
            db.query(OrderAttachment)
            .filter(
                OrderAttachment.order_id == order.id,
                OrderAttachment.category == kind_config['category'],
            )
            .order_by(OrderAttachment.id.asc())
            .all()
        )

        # AS 는 "이번 건의 최신 첨부"만 보낸다(AS-FRESH-01). 전량 발사는 옛 사진 혼입 +
        # 상한 20장을 오래된 것부터 채우는 최신 탈락을 함께 일으켰다. 클라이언트가
        # attachment_ids 를 지정하면(전송 확인창) 그 선택이 우선하되, 소속은 서버가 재검증한다.
        if push_kind == 'as':
            explicit_ids, id_error = _parse_attachment_ids(payload.get('attachment_ids'))
            if id_error:
                return jsonify({'success': False, 'message': id_error}), 400
            if explicit_ids is not None:
                allowed = {att.id: att for att in attachments}
                unknown = [i for i in explicit_ids if i not in allowed]
                if unknown:
                    return jsonify({
                        'success': False,
                        'message': '이 주문의 AS 첨부가 아닌 파일이 포함됐습니다.',
                    }), 400
                # AS-SORT-01: 확인창이 보낸 배열 순서 = 채널톡 dto.files 순서.
                # id 로 다시 정렬하면 지정 순서가 사라진다.
                attachments = [allowed[i] for i in explicit_ids]
            else:
                attachments = select_as_push_attachments(
                    sd, attachments, sd.get(kind_config['history_key'])
                )

        storage = get_storage()
        files = []
        sent_attachment_ids = []
        for att in attachments:
            if not att.storage_key:
                continue
            url = storage.get_download_url(att.storage_key, expires_in=3600)
            if url:
                files.append({
                    'fileName': att.filename or 'file',
                    'url': url,
                    'mime': _infer_mime(att.filename or '', att.file_type or 'image'),
                })
                sent_attachment_ids.append(att.id)
        # 지정 순서의 앞 20장만 전송(AS-SORT-01). provenance 와 files 를 같은 자리에서
        # 자른다 — dispatch 의 apply_attachment_policy 도 files[:20] 이지만, 여기까지
        # 21장을 넘기면 이력과 실제 전송이 어긋날 수 있다.
        files = files[:MAX_MANUAL_ATTACHMENTS]
        sent_attachment_ids = sent_attachment_ids[:MAX_MANUAL_ATTACHMENTS]

        current_user = getattr(g, "current_user", None)
        pushed_by_name = current_user.name if current_user else None

        # DispatchService를 통해 전송 (CT-A-04)
        dispatch_data = {
            'order_id': order.id,
            'customer_name': order.customer_name,
            'text': text,
            'is_retry': is_resend,
            'change_note': change_note,
            'files': files,
            'push_kind': push_kind,
            'pushed_by_name': pushed_by_name,
        }

        result = dispatch_order_event(
            event_type='manual',
            data=dispatch_data,
            raise_on_error=True
        )

        # 전송 성공 후 push 결과·metadata 를 typed command 로 원자 기록한다(push_kind별 분리):
        # structured_data 이력 + mutation_version bump + receipt + OrderEvent 1 + dedupe enqueue.
        _record_push_metadata(
            db,
            order=order,
            history_key=kind_config['history_key'],
            push_kind=push_kind,
            group_id=group_id,
            result=result,
            is_resend=is_resend,
            change_note=change_note,
            pushed_by_name=pushed_by_name,
            actor_user_id=current_user.id if current_user else None,
            attachment_ids=sent_attachment_ids,
        )

        _audit_channel_push(order, push_kind, is_resend,
                            actor_user_id=current_user.id if current_user else None,
                            files_count=len(files))
        return jsonify({'success': True, 'files_count': len(files)})

    except RuntimeError as e:
        # 채널톡 API 레벨 오류 (토큰 발급 실패, API 거부 등)
        err_msg = str(e)
        logger.error("[채널톡 수동푸쉬] RuntimeError: %s", err_msg)
        return jsonify({'success': False, 'message': f'채널톡 API 오류: {err_msg}', 'error': err_msg}), 502

    except Exception as e:
        err_msg = str(e)
        logger.error("[채널톡 수동푸쉬] 예외: %s\n%s", err_msg, traceback.format_exc())
        return jsonify({'success': False, 'message': f'서버 오류: {err_msg}', 'error': err_msg}), 500


def _as_log_labels(sd: dict) -> dict:
    """as_log 항목 id → ``1차 · 방안 8/13`` 출처 표기. 확인창에서 파일 출처를 보여준다."""
    entries = (sd.get('shipment') or {}).get('as_log')
    if not isinstance(entries, list):
        return {}
    labels = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        log_id = str(entry.get('id') or '')
        if not log_id:
            continue
        decorated = decorate_entry(entry)
        stamp = str(decorated.get('ts_abs') or '')[:10]
        month_day = ''
        if len(stamp) == 10 and stamp[4] == '-':
            month_day = f" {int(stamp[5:7])}/{int(stamp[8:10])}"
        labels[log_id] = f"{decorated['round']}차 · {decorated['type_label']}{month_day}"
    return labels


@channel_integration_bp.route('/push-preview', methods=['GET'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_channel_push_preview():
    """AS PUSH 전송 확인창 미리보기 — 나갈 본문 + 첨부 후보(기본 선정 표시).

    전송 직전에 "무엇이 나가는지"를 사람이 눈으로 확인하는 표면이다. 기본 선정은
    ``select_as_push_attachments`` 와 **같은 함수**를 쓴다 — 미리보기와 실제 전송이 다른
    규칙을 쓰면 확인창이 오히려 오해를 만든다.

    Query Args:
        order_id: 대상 주문 PK.
        push_kind: 현재는 ``as`` 만 지원(다른 값은 400).

    Returns:
        200 ``{success, text, files:[{id, filename, url, is_image, selected, source}]}`` /
        400 잘못된 인자 / 404 주문 없음.
    """
    db = get_db()
    push_kind = (request.args.get('push_kind') or 'as').strip()
    if push_kind != 'as':
        return jsonify({'success': False, 'message': 'AS PUSH 만 미리보기를 지원합니다.'}), 400
    try:
        order_id = int(request.args.get('order_id') or 0)
    except (TypeError, ValueError):
        order_id = 0
    if order_id <= 0:
        return jsonify({'success': False, 'message': 'order_id 가 없습니다.'}), 400

    order = db.query(Order).filter(Order.id == order_id, Order.active_filter()).first()
    if not order:
        return jsonify({'success': False, 'message': f'주문 #{order_id}을 찾을 수 없습니다.'}), 404

    sd = order.structured_data if isinstance(order.structured_data, dict) else {}
    attachments = (
        db.query(OrderAttachment)
        .filter(OrderAttachment.order_id == order.id, OrderAttachment.category == 'as')
        .order_by(OrderAttachment.id.asc())
        .all()
    )
    selected = select_as_push_attachments(sd, attachments, sd.get('channeltalk_push_as'))
    selected_ids = {att.id for att in selected}

    # 후보 = 최신 _PREVIEW_CANDIDATE_MAX 장 + 기본 선정분(회차 결합으로 더 오래된 것이
    # 뽑혔을 수 있다). 사용자가 옛 파일을 되살릴 수 있어야 하므로 미선택분도 함께 내린다.
    pool = {att.id: att for att in attachments[-_PREVIEW_CANDIDATE_MAX:]}
    pool.update({att.id: att for att in selected})

    labels = _as_log_labels(sd)
    storage = get_storage()
    # 선택분 = 전송 기본 순서(select 결과). 미선택은 그 아래(정렬 키).
    ordered = []
    seen = set()
    for att in selected:
        if att.id in pool and att.id not in seen:
            ordered.append(att)
            seen.add(att.id)
    rest = [att for att in pool.values() if att.id not in seen]
    rest.sort(key=attachment_sort_key)
    ordered.extend(rest)

    files = []
    for att in ordered:
        if not att.storage_key:
            continue
        preview_key = att.thumbnail_key or att.storage_key
        files.append({
            'id': att.id,
            'filename': att.filename or 'file',
            'url': storage.get_download_url(preview_key, expires_in=3600),
            'is_image': (att.file_type or 'image') == 'image',
            'selected': att.id in selected_ids,
            'source': labels.get(str(getattr(att, 'as_log_id', None) or ''), '이전 첨부'),
        })

    return jsonify({
        'success': True,
        'text': build_as_push_text(order),
        'files': files,
    })


_ESTIMATE_PUSH_HISTORY_KEY = 'channeltalk_push_estimate'
_MAX_ESTIMATE_IMAGE_BYTES = 15 * 1024 * 1024  # 15MB (견적서 PNG는 보통 수 MB 이내)
# PNG 시그니처(매직 바이트). mimetype 헤더는 위조 가능하므로 실제 바이트로 검증한다.
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def _safe_delete_estimate_upload(storage, key):
    """
    견적서 푸쉬 실패 시 방금 업로드한 오브젝트를 정리(고아 방지)한다.

    삭제 자체가 실패하더라도 원 응답(전송 실패)을 가려선 안 되므로 예외를 삼키되,
    반드시 로그로 남긴다(규칙: 로그 없는 실패 삼킴 금지).

    Args:
        storage: 스토리지 서비스 인스턴스
        key (str): 삭제할 오브젝트 키
    """
    if not key:
        return
    try:
        storage.delete_file(key)
    except Exception as exc:  # noqa: BLE001 - 정리 실패는 로그만 남기고 원 오류를 전달
        logger.warning("[채널톡 견적서푸쉬] 업로드 오브젝트 정리 실패 (key=%s): %s", key, exc)


@channel_integration_bp.route('/push-estimate', methods=['POST'])
@login_required
@role_required(['ADMIN', 'MANAGER', 'STAFF'])
def api_channel_push_estimate():
    """
    견적서 이미지 채널톡 푸쉬(견적서 방).

    견적서 미리보기는 라이브 폼 데이터(수동행·컬럼폭 포함)로 클라이언트가 html2canvas로
    렌더하므로 서버 재현이 불가능하다. 따라서 클라이언트가 캡처한 PNG를 multipart로 업로드받아
    스토리지(R2/S3)에 저장하고, 그 presigned URL을 첨부로 견적서 그룹(push_kind='estimate',
    CHANNEL_GROUP_ESTIMATE, 미설정 시 230395)으로 전송한다.

    Request (multipart/form-data):
        order_id (int): 주문 ID
        image (file): 견적서 PNG 이미지
        change_note (str, optional): 재전송 시 변경 내용 (1~500자, 필수)

    Returns:
        {success: bool, error: str}
    """
    db = get_db()
    try:
        order_id = request.form.get('order_id')
        change_note = (request.form.get('change_note') or '').strip()
        image = request.files.get('image')

        if not order_id:
            return jsonify({'success': False, 'message': 'order_id가 없습니다.'}), 400
        if image is None or not image.filename:
            return jsonify({'success': False, 'message': '견적서 이미지가 없습니다.'}), 400
        if (image.mimetype or '') != 'image/png':
            return jsonify({'success': False, 'message': '견적서 이미지는 PNG 형식만 지원합니다.'}), 400

        image.stream.seek(0, os.SEEK_END)
        image_size = image.stream.tell()
        image.stream.seek(0)
        if image_size <= 0:
            return jsonify({'success': False, 'message': '견적서 이미지가 비어 있습니다.'}), 400
        if image_size > _MAX_ESTIMATE_IMAGE_BYTES:
            return jsonify({'success': False, 'message': '견적서 이미지가 너무 큽니다 (최대 15MB).'}), 400

        # mimetype 헤더는 위조 가능하므로 실제 PNG 시그니처(매직 바이트)를 검증한다.
        magic = image.stream.read(len(_PNG_MAGIC))
        image.stream.seek(0)
        if magic != _PNG_MAGIC:
            return jsonify({'success': False, 'message': '견적서 이미지가 올바른 PNG 형식이 아닙니다.'}), 400

        if not is_configured():
            msg = '채널톡 환경변수(CHANNEL_APP_SECRET, CHANNEL_ID)가 서버에 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        try:
            group_id = get_routing_group_id('manual', {'push_kind': 'estimate'})
        except ChannelGroupRetiredError as exc:
            logger.info("[채널톡 견적서푸쉬] retired group blocked (group_id=%s)", exc.group_id)
            return jsonify({
                'success': False,
                'message': _RETIRED_GROUP_MESSAGE,
                'error': _RETIRED_GROUP_MESSAGE,
            }), 410
        if not group_id:
            msg = 'CHANNEL_GROUP_ESTIMATE 환경변수가 설정되지 않았습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 503

        order = db.query(Order).filter(Order.id == int(order_id), Order.active_filter()).first()
        if not order:
            return jsonify({'success': False, 'message': f'주문 #{order_id}을 찾을 수 없습니다.'}), 404

        sd = copy.deepcopy(order.structured_data or {})
        prev_push = sd.get(_ESTIMATE_PUSH_HISTORY_KEY) or {}
        is_resend = bool(prev_push.get('pushed'))

        if is_resend:
            if len(change_note) < _MIN_CHANGE_NOTE_LEN:
                return jsonify({
                    'success': False,
                    'message': f'재전송 시 변경 내용을 {_MIN_CHANGE_NOTE_LEN}자 이상 입력해주세요.',
                }), 400
        else:
            change_note = ''

        if change_note and len(change_note) > _MAX_CHANGE_NOTE_LEN:
            return jsonify({
                'success': False,
                'message': f'변경 내용은 최대 {_MAX_CHANGE_NOTE_LEN}자까지 입력할 수 있습니다.',
            }), 400

        storage = get_storage()
        upload_name = f'estimate_{order.id}.png'
        upload_result = storage.upload_file(image, upload_name, folder=f'estimate_push/{order.id}')
        if not upload_result or not upload_result.get('success'):
            err = (upload_result or {}).get('message') or '견적서 이미지 업로드에 실패했습니다.'
            return jsonify({'success': False, 'message': err, 'error': err}), 502
        upload_key = upload_result['key']

        download_url = storage.get_download_url(upload_key, expires_in=3600)
        if not download_url:
            _safe_delete_estimate_upload(storage, upload_key)
            msg = '견적서 이미지 다운로드 URL 생성에 실패했습니다.'
            return jsonify({'success': False, 'message': msg, 'error': msg}), 502

        current_user = getattr(g, "current_user", None)
        pushed_by_name = current_user.name if current_user else None

        dispatch_data = {
            'order_id': order.id,
            'customer_name': order.customer_name,
            'text': f'[견적서] {order.customer_name or ""}'.strip(),
            'is_retry': is_resend,
            'change_note': change_note,
            'files': [{
                'fileName': upload_result.get('filename') or upload_name,
                'url': download_url,
                'mime': 'image/png',
            }],
            'push_kind': 'estimate',
            'pushed_by_name': pushed_by_name,
        }

        # 전송 실패 시 방금 업로드한 오브젝트를 정리해 고아 파일/재시도 중복을 막는다.
        # (전송 성공 후에는 채널톡이 presigned URL을 참조하므로 삭제하지 않는다.)
        try:
            result = dispatch_order_event(
                event_type='manual',
                data=dispatch_data,
                raise_on_error=True,
            )
        except Exception:
            _safe_delete_estimate_upload(storage, upload_key)
            raise

        # 전송 성공 후 push 결과·metadata 를 typed command 로 원자 기록한다:
        # structured_data 이력 + mutation_version bump + receipt + OrderEvent 1 + dedupe enqueue.
        _record_push_metadata(
            db,
            order=order,
            history_key=_ESTIMATE_PUSH_HISTORY_KEY,
            push_kind='estimate',
            group_id=group_id,
            result=result,
            is_resend=is_resend,
            change_note=change_note,
            pushed_by_name=pushed_by_name,
            actor_user_id=current_user.id if current_user else None,
        )

        _audit_channel_push(order, 'estimate', is_resend,
                            actor_user_id=current_user.id if current_user else None)
        return jsonify({'success': True})

    except RuntimeError as e:
        err_msg = str(e)
        logger.error("[채널톡 견적서푸쉬] RuntimeError: %s", err_msg)
        return jsonify({'success': False, 'message': f'채널톡 API 오류: {err_msg}', 'error': err_msg}), 502

    except Exception as e:
        err_msg = str(e)
        logger.error("[채널톡 견적서푸쉬] 예외: %s\n%s", err_msg, traceback.format_exc())
        return jsonify({'success': False, 'message': f'서버 오류: {err_msg}', 'error': err_msg}), 500


# --- OPS-ROUTE-01 배포 단계 분리 노트 (machine detail) ---
# 사람용 ADMIN detail 은 아래 /health 세션 게이트로 로컬 검증 가능하다.
# machine detail(스크립트/모니터용)은 이 public 앱이 아니라 별도 최소 서비스
# (foms/ops_app.py + railway-ops-readiness.toml)의 /internal/ops/channel-readiness
# 에만 등록하고, 그 Railway service 에는 public domain 을 만들지 않는다
# (no-public-domain). 인증은 FOMS_OPS_READINESS_TOKEN(random ≥32 bytes, 미설정 시
# 부팅 실패)을 timing-safe 비교하고 응답은 no-store / Vary: Authorization /
# ETag·Last-Modified 0 을 쓴다. public 앱 blueprint 에는 /internal/ops/* 를 절대
# 등록하지 않는다(로컬 계약 테스트가 404 로 고정). 이 배선은 배포 단계 산출물이므로
# 본 packet 에서는 구현하지 않는다.


def _viewer_is_ops_admin() -> bool:
    """현재 요청 사용자가 ops detail 열람 권한(ADMIN/MANAGER)인지 판정한다.

    ``g.current_user`` 는 ``app.before_request(_set_current_user)`` 가 모든 요청에
    대해 설정한다(무인증이면 ``None``). 따라서 ``login_required`` 데코레이터 없이도
    공개 라우트 안에서 인증/권한을 분기할 수 있다.

    Returns:
        bool: ADMIN 또는 MANAGER 세션이면 True, 그 외(무인증 포함) False.
    """
    user = getattr(g, 'current_user', None)
    return bool(user and getattr(user, 'role', None) in ('ADMIN', 'MANAGER'))


def _apply_no_store(resp, *, private: bool):
    """민감 detail 응답에 캐시 재사용 차단 헤더를 적용한다. (OPS-ROUTE-01)

    logout→Back 또는 공유 프록시가 이전 body(운영 metric)를 한 byte 도 재사용하지
    못하도록 ``no-store`` 와 함께 ETag/Last-Modified 검증자를 제거한다. 응답 본문이
    세션 인증 여부에 따라 달라지므로 ``Vary: Cookie`` 로 캐시 분리를 강제한다.

    Args:
        resp: Flask 응답 객체.
        private: True 면 ``private, no-store``(ADMIN detail), False 면 ``no-store``
            (무인증 공개 최소 응답).

    Returns:
        헤더가 적용된 동일 응답 객체.
    """
    resp.headers['Cache-Control'] = 'private, no-store' if private else 'no-store'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Vary'] = 'Cookie'
    resp.headers.pop('ETag', None)
    resp.headers.pop('Last-Modified', None)
    return resp


def _evaluate_channel_readiness() -> tuple[dict, int]:
    """채널톡 연동 readiness 와 운영 detail 을 계산한다. (CT-00-03)

    readiness 판정에 더해 환경변수 존재/flag/worker·backlog·delivery metric 을 담은
    전체 payload 를 만든다. 무인증 공개 응답은 이 중 coarse ``readiness`` 만 노출하고,
    나머지 운영 detail 은 ADMIN/MANAGER 세션 뒤에서만 반환한다.

    Returns:
        (payload, status_code): payload 는 readiness/environment/flags/queue/metrics
        등 전체 detail, status_code 는 ready·degraded=200, fail=503.
    """
    flags = {
        'push': os.environ.get('CHANNEL_PUSH_ENABLED', 'false').lower() == 'true',
        'command': os.environ.get('CHANNEL_COMMAND_ENABLED', 'false').lower() == 'true',
        'wam': os.environ.get('CHANNEL_WAM_ENABLED', 'false').lower() == 'true',
        'webhook': os.environ.get('CHANNEL_WEBHOOK_ENABLED', 'false').lower() == 'true',
        'inbound_create': os.environ.get('CHANNEL_INBOUND_CREATE_ENABLED', 'false').lower() == 'true',
        'write_action': os.environ.get('CHANNEL_WRITE_ACTION_ENABLED', 'false').lower() == 'true',
    }
    environment = {
        'CHANNEL_APP_SECRET': bool(os.environ.get('CHANNEL_APP_SECRET')),
        'CHANNEL_ID': bool(os.environ.get('CHANNEL_ID')),
        'CHANNEL_SIGNING_KEY': bool(os.environ.get('CHANNEL_SIGNING_KEY')),
        'FOMS_BASE_URL': bool(os.environ.get('FOMS_BASE_URL')),
    }
    security = {
        'signature_verification': True,
        'replay_window_seconds': int(os.environ.get('CHANNEL_REPLAY_WINDOW_SECONDS', 300))
    }

    try:
        db = get_db()
        queue_runtime = get_rq_runtime_status()
        queue_state = queue_runtime['state']
        rq_worker_count = queue_runtime['worker_count']

        backlog_count = get_queue_backlog(db)
        legacy_success_drift = check_legacy_only_success_after_cutover(db)
        metrics = get_delivery_metrics(db)

        flag_violations = []
        if flags['inbound_create'] and not flags['webhook']:
            flag_violations.append('INBOUND_CREATE_REQUIRES_WEBHOOK')
        if flags['write_action'] and not (flags['command'] or flags['wam']):
            flag_violations.append('WRITE_ACTION_REQUIRES_COMMAND_OR_WAM')

        if not environment['FOMS_BASE_URL']:
            readiness = 'fail'
        elif (flags['command'] or flags['webhook']) and not environment['CHANNEL_SIGNING_KEY']:
            readiness = 'fail'
            flag_violations.append('INBOUND_FEATURES_REQUIRE_SIGNING_KEY')
        elif (flags['push'] or flags['webhook']) and rq_worker_count < 1:
            readiness = 'fail'
        elif flag_violations:
            readiness = 'fail'
        elif legacy_success_drift > 0:
            readiness = 'degraded'
        else:
            readiness = 'ready'

        return {
            'readiness': readiness,
            'environment': environment,
            'flags': flags,
            'flag_violations': flag_violations,
            'queue': {
                'state': queue_state,
                'worker_count': rq_worker_count,
                'backlog_count': backlog_count,
            },
            'metrics': metrics,
            'security': security,
            'legacy_only_success_after_cutover': legacy_success_drift,
        }, 200 if readiness != 'fail' else 503
    except Exception as e:
        logger.error("[ChannelTalk Health] failed: %s\n%s", e, traceback.format_exc())
        return {
            'readiness': 'fail',
            'environment': environment,
            'flags': flags,
            'flag_violations': ['CHANNEL_HEALTH_CHECK_FAILED'],
            'queue': {
                'state': 'unknown',
                'worker_count': 0,
                'backlog_count': 0,
            },
            'metrics': {},
            'security': security,
            'legacy_only_success_after_cutover': 0,
            'error': str(e),
        }, 503


@channel_integration_bp.route('/health', methods=['GET'])
def api_channel_health():
    """채널톡 연동 헬스체크. 무인증=coarse readiness 만, ADMIN/MANAGER 세션=운영 detail.

    OPS-ROUTE-01 / P0-18: 무인증 공개 응답에는 secret 존재 여부·worker/queue/delivery
    metric·raw exception/traceback 을 노출하지 않고 coarse ``readiness`` 만 반환한다.
    환경변수 존재·metric·flag_violations·error 를 포함한 운영 detail 은 ADMIN/MANAGER
    세션 뒤에서만 제공하며 ``private, no-store`` 로 캐시 재사용을 차단한다.

    machine detail(no-public-domain Railway ops service + random ≥32-byte bearer,
    ``Vary: Authorization``)의 프로덕션 배선은 배포 단계 산출물이다(모듈 상단 노트).

    Returns:
        (JSON, status): 무인증 → ``{"readiness": ...}``(no-store), ADMIN/MANAGER →
        전체 운영 detail(private, no-store). status 는 ready·degraded=200, fail=503.
    """
    payload, status = _evaluate_channel_readiness()
    if _viewer_is_ops_admin():
        return _apply_no_store(jsonify(payload), private=True), status
    return _apply_no_store(jsonify({'readiness': payload['readiness']}), private=False), status

@channel_integration_bp.route('/admin/delivery-status', methods=['GET'])
@login_required
@role_required(['ADMIN', 'MANAGER'])
def api_channel_admin_delivery_status():
    """
    운영 조회용 Admin API (최근 실패 내역, backlog 확인)
    """
    db = get_db()
    
    try:
        from models import ChannelDeliveryLog
        limit = request.args.get('limit', 50, type=int)
        
        logs = db.query(ChannelDeliveryLog)\
            .order_by(ChannelDeliveryLog.id.desc())\
            .limit(limit)\
            .all()
            
        result = []
        for log in logs:
            result.append({
                'id': log.id,
                'event_key': log.event_key,
                'source_type': log.source_type,
                'source_id': log.source_id,
                'status': log.status,
                'retry_count': log.retry_count,
                'last_error': log.last_error,
                'created_at': log.created_at.isoformat() if log.created_at else None,
            })
            
        return jsonify({
            'success': True,
            'metrics': get_delivery_metrics(db),
            'backlog_count': get_queue_backlog(db),
            'recent_logs': result
        })
    except Exception as e:
        logger.error("[ChannelAdmin] delivery_status 오류: %s", str(e), exc_info=True)
        return jsonify({'success': False, 'message': str(e)}), 500

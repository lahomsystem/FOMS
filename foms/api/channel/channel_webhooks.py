"""ChannelTalk Webhook 수신 endpoint (CHANNEL-WEBHOOK-AUTH-01).

provider token(``x-signature``, raw UTF-8 key + hex HMAC digest)은
``channel_security.require_channel_signature`` 가 검증하고(disabled → 404 provider-first,
bad token → 401, freshness 는 보조 anti-replay 이지 유일 auth 가 아님), 수용은
``channel_security.accept_webhook`` 의 **acceptance transaction** 으로만 2xx 를 낸다
(JCS hash + 30d dedup + versioned AES-256-GCM envelope + durable receipt/intent/job).
실 Order mutation 은 downstream worker 소관이라 이 endpoint 는 Order 를 건드리지 않는다.
"""

from flask import Blueprint, request, jsonify

from foms.services.channel_security import require_channel_signature, validate_webhook_config

channel_webhooks_bp = Blueprint('channel_webhooks', __name__, url_prefix='/api/channel/webhooks')


# CT-C-01: provider token(x-signature) 검증 + disabled 404 provider-first 게이트.
@channel_webhooks_bp.before_request
@require_channel_signature
def verify_webhooks_signature():
    """모든 Webhook 수신 Endpoint에 대해 provider token(X-Signature)을 검증한다."""
    pass


@channel_webhooks_bp.route('', methods=['POST'])
def handle_webhook():
    """CT-E: token 검증 뒤 acceptance transaction 으로 수용(2xx 는 receipt/job 커밋 뒤에만).

    ``receive_webhook`` (canonical inbound 파이프라인)을 acceptance 후 best-effort
    downstream dispatch 로 넘긴다 — durable job row 는 이미 커밋됐으므로 dispatch 실패가
    2xx 를 취소하지 않는다(부분 수용 0).
    """
    from foms.services.channel_inbound import receive_webhook
    from foms.services.channel_security import accept_webhook

    raw_body = request.get_data()
    payload = request.get_json(silent=True)
    status_code, response_data = accept_webhook(payload, raw_body, dispatch=receive_webhook)
    return jsonify(response_data), status_code


# 기동 시 enforce(CHANNEL_INBOUND_ENABLED=true) 상태의 필수 key 를 검증한다(fail-start).
# unset(dev/test)·명시적 false 면 no-op.
validate_webhook_config()

from flask import Blueprint, request, jsonify
from services.channel_security import require_channel_signature

channel_webhooks_bp = Blueprint('channel_webhooks', __name__, url_prefix='/api/channel/webhooks')

# CT-C-01: X-Signature 검증 적용
@channel_webhooks_bp.before_request
@require_channel_signature
def verify_webhooks_signature():
    """모든 Webhook 수신 Endpoint에 대해 X-Signature를 검증한다."""
    pass

@channel_webhooks_bp.route('', methods=['POST'])
def handle_webhook():
    """
    CT-E-01: 웹훅 수신, Receipt 로깅, Enqueue 처리
    CT-E-05: 2xx 반환은 Receipt DB 저장 + Async Enqueue 성공 이후에만
    """
    from services.channel_inbound import receive_webhook
    payload = request.json or {}
    
    status_code, response_data = receive_webhook(payload)
    return jsonify(response_data), status_code

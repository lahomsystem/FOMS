from flask import Blueprint, request, jsonify
from services.channel_security import require_channel_signature

channel_webhooks_bp = Blueprint('channel_webhooks', __name__, url_prefix='/api/channel/webhooks')

# CT-C-01: X-Signature 검증 적용
@channel_webhooks_bp.before_request
@require_channel_signature
def verify_webhooks_signature():
    """모든 Webhook 수신 Endpoint에 대해 X-Signature를 검증한다."""
    pass

# TODO: CT-E-01에서 수신기 및 검증 로직 추가

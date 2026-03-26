from flask import Blueprint, request, jsonify
from services.channel_security import require_channel_signature

channel_functions_bp = Blueprint('channel_functions', __name__, url_prefix='/api/channel/functions')

# CT-C-01: X-Signature 검증 적용
@channel_functions_bp.before_request
@require_channel_signature
def verify_functions_signature():
    """모든 Function Endpoint에 대해 X-Signature를 검증한다."""
    pass

# TODO: CT-D-01에서 /foms 명령어 응답 추가

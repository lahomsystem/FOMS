"""
ChannelTalk Inbound Security Verification (Phase C)
- X-Signature 검증 (CT-C-01)
- Replay Attack 방어 (CT-C-02)
- WAM Token 관리 (CT-C-03)
"""
import hmac
import hashlib
import os
import time
import logging
from functools import wraps
from flask import request, jsonify
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

logger = logging.getLogger(__name__)

CHANNEL_SIGNING_KEY = os.environ.get('CHANNEL_SIGNING_KEY', '')
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-foms-secret-key-123')

# WAM 세션용 토큰 생성기 (최대 1시간 유효)
wam_serializer = URLSafeTimedSerializer(SECRET_KEY, salt='wam-launch-token')

def verify_channel_signature(raw_body: bytes, signature: str) -> bool:
    """
    수신한 Body와 환경변수의 SIGNING_KEY를 이용해 X-Signature 검증.
    """
    if not CHANNEL_SIGNING_KEY or not signature:
        return False
    
    expected_hash = hmac.new(
        CHANNEL_SIGNING_KEY.encode('utf-8'),
        msg=raw_body,
        digestmod=hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_hash, signature)

def require_channel_signature(f):
    """
    ChannelTalk Webhook 및 Function Endpoint 용 데코레이터.
    - X-Signature 검증
    - (선택적) Replay 방어를 위한 timestamp 검증
    - HTML 리다이렉트 없이 순수 JSON 에러 반환
    """
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Feature Flag 점검 (수신을 전체 차단할지)
        # 만약 Blueprint 레벨에서 끄려면 별도 before_request를 활용해도 무방함.
        if os.environ.get('CHANNEL_INBOUND_ENABLED', 'true').lower() == 'false':
            return jsonify({'error': 'inbound_disabled', 'message': 'Channel inbound is disabled via feature flag'}), 503

        # 2. X-Signature 검증
        signature = request.headers.get('x-signature', '')
        if not signature:
            logger.warning("[ChannelSecurity] Missing x-signature header")
            return jsonify({'error': 'unauthorized', 'message': 'Missing x-signature'}), 401
            
        raw_body = request.get_data()
        if not verify_channel_signature(raw_body, signature):
            logger.warning("[ChannelSecurity] Invalid x-signature")
            return jsonify({'error': 'forbidden', 'message': 'Invalid signature'}), 403
            
        # 3. Replay 방지 로직 (5분 윈도우)
        payload = request.get_json(silent=True) or {}
        
        # Webhook payload에 있는 createdAt (ms) 확인
        created_at_ms = payload.get('entity', {}).get('createdAt')
        
        # Function payload의 경우 별도 규칙이 없다면 생략 (보통 x-signature로 충분)
        if created_at_ms and isinstance(created_at_ms, (int, float)):
            now_ms = time.time() * 1000
            diff_ms = now_ms - created_at_ms
            window_ms = int(os.environ.get('CHANNEL_REPLAY_WINDOW_SECONDS', 300)) * 1000
            
            # 과거 5분 초과 혹은 미래 시간(서버 시간 오차 고려 1분 허용)
            if diff_ms > window_ms or diff_ms < -60000:
                logger.warning("[ChannelSecurity] Stale payload or Replay attack detected. Diff: %.1f ms", diff_ms)
                return jsonify({'error': 'forbidden', 'message': 'Payload timestamp out of valid window'}), 403
                
        return f(*args, **kwargs)
    return decorated_function

def generate_wam_launch_token(manager_id: str, order_id: int = None) -> str:
    """
    Web App Messenger 구동 시 클라이언트에 전달할 일회용/단기 토큰 생성.
    """
    payload = {
        'manager_id': manager_id,
        'order_id': order_id,
        'iat': time.time()
    }
    return wam_serializer.dumps(payload)

def verify_wam_launch_token(token: str, max_age: int = 3600) -> dict:
    """
    WAM 토큰 검증. 최대 max_age 초 이내에만 유효.
    """
    try:
        return wam_serializer.loads(token, max_age=max_age)
    except SignatureExpired:
        logger.warning("[ChannelSecurity] WAM token expired")
        return None
    except BadSignature:
        logger.warning("[ChannelSecurity] Invalid WAM token")
        return None

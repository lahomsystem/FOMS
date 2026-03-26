from flask import Blueprint, request, jsonify, render_template, abort
from services.channel_security import verify_wam_launch_token

channel_wam_bp = Blueprint('channel_wam', __name__, url_prefix='/channel/wam')

# [ChannelTalk 연동 - Bootstrap 실행 범위 계약 (CT-00-05, CT-C-03)]
# 1. WAM(Web App Messenger)은 ERP 내부 사용자가 아닌 외부 '고객'이 접속하는 환경입니다.
# 2. app.py 의 전역 session이나 ERP 로그인(login_required)에 의존해서는 안 됩니다.
# 3. WAM Bootstrap 시 제공되는 JWT(또는 서명된 페이로드)만으로 세션을 독립적으로 구성해야 합니다.
# 4. 따라서 WAM 라우트는 app.py의 before_request (예: log_access 등)에서 예외 처리되거나 
#    별도의 Blueprint level before_request를 가져야 합니다.

@channel_wam_bp.before_request
def verify_wam_token():
    """
    CT-C-03: WAM 세션 독립화 및 토큰 검증
    모든 WAM API 및 페이지 요청은 유효한 launch_token 쿼리 파라미터를 요구합니다.
    """
    token = request.args.get('token')
    if not token:
        # TODO: HTML 페이지 요청인 경우 렌더링된 오류 페이지 반환 등 분기 필요
        return jsonify({'error': 'unauthorized', 'message': 'Missing WAM token'}), 401
        
    payload = verify_wam_launch_token(token)
    if not payload:
        return jsonify({'error': 'unauthorized', 'message': 'Invalid or expired WAM token'}), 401
        
    # request 객체에 검증된 payload 주입 (하위 라우트에서 사용)
    request.wam_payload = payload

# TODO: CT-D-02 등에서 WAM 주문 요약 등 실질적 렌더링 로직 추가

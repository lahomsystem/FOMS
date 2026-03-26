from flask import Blueprint, request, jsonify, render_template

channel_wam_bp = Blueprint('channel_wam', __name__, url_prefix='/channel/wam')

# [ChannelTalk 연동 - Bootstrap 실행 범위 계약 (CT-00-05)]
# 1. WAM(Web App Messenger)은 ERP 내부 사용자가 아닌 외부 '고객'이 접속하는 환경입니다.
# 2. app.py 의 전역 session이나 ERP 로그인(login_required)에 의존해서는 안 됩니다.
# 3. WAM Bootstrap 시 제공되는 JWT(또는 서명된 페이로드)만으로 세션을 독립적으로 구성해야 합니다.
# 4. 따라서 WAM 라우트는 app.py의 before_request (예: log_access 등)에서 예외 처리되거나 
#    별도의 Blueprint level before_request를 가져야 합니다.

# TODO: CT-C-05에서 WAM bootstrap / token 로직 추가

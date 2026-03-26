from flask import Blueprint, request, jsonify

channel_functions_bp = Blueprint('channel_functions', __name__, url_prefix='/api/channel/functions')

# TODO: CT-C-01 등에서 X-Signature 검증, CT-D-01에서 /foms 명령어 응답 추가

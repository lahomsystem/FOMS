from flask import Blueprint, request, jsonify

channel_webhooks_bp = Blueprint('channel_webhooks', __name__, url_prefix='/api/channel/webhooks')

# TODO: CT-E-01에서 수신기 및 검증 로직 추가

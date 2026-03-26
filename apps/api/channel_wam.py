from flask import Blueprint, request, jsonify, render_template

channel_wam_bp = Blueprint('channel_wam', __name__, url_prefix='/channel/wam')

# TODO: CT-C-05에서 WAM bootstrap / token 로직 추가

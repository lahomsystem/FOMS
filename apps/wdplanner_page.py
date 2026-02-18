"""WDPlanner 페이지 Blueprint: /wdplanner, /wdplanner/app, /wdplanner/app/<path>."""
import os
from flask import Blueprint, render_template, send_from_directory

from apps.auth import login_required

wdplanner_bp = Blueprint('wdplanner', __name__, url_prefix='')


@wdplanner_bp.route('/wdplanner')
@login_required
def wdplanner():
    """WDPlanner - 붙박이장 3D 설계 프로그램 (FOMS 레이아웃 포함)"""
    return render_template('wdplanner.html')


@wdplanner_bp.route('/wdplanner/app/<path:filename>')
@login_required
def wdplanner_static(filename):
    """WDPlanner 정적 파일 서빙 (JS, CSS, assets 등)"""
    return send_from_directory('static/wdplanner', filename)


@wdplanner_bp.route('/wdplanner/app')
@login_required
def wdplanner_app():
    """WDPlanner 앱 자체 (iframe 내부에서 로드)"""
    wdplanner_index = os.path.join('static', 'wdplanner', 'index.html')
    if os.path.exists(wdplanner_index):
        return send_from_directory('static/wdplanner', 'index.html')
    return render_template('wdplanner_setup.html')

"""FOMS Brain AX Designer page Blueprint: /wdplanner-v2."""

import os

from flask import Blueprint, render_template, send_from_directory

from foms.web.auth import login_required

designer_bp = Blueprint("designer", __name__, url_prefix="")


@designer_bp.route("/wdplanner-v2")
@login_required
def wdplanner_v2() -> str:
    """FOMS Brain AX Designer - 붙박이장 3D 설계 V2 (FOMS 레이아웃 포함)."""
    return render_template("designer/wdplanner_v2.html")


@designer_bp.route("/wdplanner-v2/app")
@login_required
def wdplanner_v2_app():
    """FOMS Brain Designer 앱 자체 (iframe 내부에서 로드)."""
    designer_index = os.path.join("static", "designer", "index.html")
    if os.path.exists(designer_index):
        return send_from_directory("static/designer", "index.html")
    return render_template("designer/wdplanner_v2_setup.html")


@designer_bp.route("/wdplanner-v2/app/<path:filename>")
@login_required
def wdplanner_v2_static(filename: str):
    """FOMS Brain Designer 정적 파일 서빙 (JS, CSS, assets 등)."""
    return send_from_directory("static/designer", filename)

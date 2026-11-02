"""AI 상담 초안 [보내기] · [수정하기] 짧은 화면(``/cs-agent/turns/<id>/send`` · ``/edit``) — 플랜 C10-3 · 설계서 17.2.1 링크 길.

채널톡 데스크(PC · 휴대폰 앱)의 내부 메모 링크 버튼이 이 화면을 연다. 로그인이 필요하다 — 로그인 화면을 거치면 이 주소로
돌아온다(``login_required`` 의 next — C10-0 에서 바깥 주소로 새는 구멍을 막았다). 상담 직원(CS 팀) · ADMIN 만 쓴다.

**GET 은 보여 주기만 한다** — 보내지 않고, 서명 표를 쓰지 않고, DB 를 쓰지 않는다(메신저 링크 미리 읽기 대비). 화면이 그
직원 · 그 차례 · 그 메모로 서명한 한 번용 표를 ``data-*`` 로 싣고, 화면 스크립트(``static/js/cs-agent/send-screen.js``)가
CSRF 와 함께 JSON API(:mod:`foms.api.cs_agent_send`)로 보낸다. 화면 재료는 :func:`foms.services.cs_agent.send_view.screen_view`.

자세한 이유에 붙인 사진 원본(설계서 17.6.1 (b))은 ``/cs-agent/turns/<id>/photos/<seq>`` 만이 보인다 — 권한(ADMIN · 올린 직원
24시간 — D94)을 본 뒤 비공개 저장소 바이트를 흘려보낸다(``no-store`` · ``nosniff`` · 저장한 꼴만). 서명 · 공개 URL 은 쓰지 않는다.
"""

from __future__ import annotations

from flask import Blueprint, abort, current_app, g, make_response, render_template, request

from db import get_db
from foms.services.cs_agent.edit_detail import DetailResult, photo_for_view
from foms.services.cs_agent.send_auth import can_use_send_screen
from foms.services.cs_agent.send_view import screen_view
from foms.services.datetime_kst import now_kst
from foms.web.auth import login_required

cs_agent_send_page_bp = Blueprint("cs_agent_send_page", __name__)

MODE_SEND, MODE_EDIT = "send", "edit"


def _screen(turn_id: int, mode: str):
    """두 화면 공통 — 권한(상담 직원 · ADMIN) → 재료(읽기만) → 렌더(캐시 · 색인 · 보낸 곳 주소 없음)."""
    user = getattr(g, "current_user", None)
    if not can_use_send_screen(user):
        response = make_response(render_template("cs/cs_agent_send.html", view=None, mode=mode, denied=True), 403)
    else:
        view = screen_view(get_db(), turn_id, user, chat_hint=request.args.get("c"),
                           secret_key=current_app.secret_key, now=now_kst())
        if view is None:
            abort(404)
        response = make_response(render_template("cs/cs_agent_send.html", view=view, mode=mode, denied=False,
                                                  chat_hint=request.args.get("c")))
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response


@cs_agent_send_page_bp.route("/cs-agent/turns/<int:turn_id>/send", methods=["GET"])
@login_required
def cs_agent_send_screen(turn_id: int):
    """보내기 확인 화면 — 보낼 글(메모의 '손님께 보낼 답')을 보이고 [보내기] · [수정하기] · [버리기]."""
    return _screen(turn_id, MODE_SEND)


@cs_agent_send_page_bp.route("/cs-agent/turns/<int:turn_id>/edit", methods=["GET"])
@login_required
def cs_agent_edit_screen(turn_id: int):
    """수정하기 화면 — 고치는 칸 · '고칠 말'(AI 다시 쓰기) · 고친 까닭 · 보내기 · 버리기."""
    return _screen(turn_id, MODE_EDIT)


@cs_agent_send_page_bp.route("/cs-agent/turns/<int:turn_id>/photos/<int:seq>", methods=["GET"])
@login_required
def cs_agent_edit_photo(turn_id: int, seq: int):
    """자세한 이유 사진 원본 — ADMIN · 올린 직원(24시간)만. 권한 밖 403 · 없음 · 지움 404(글 없이)."""
    user = getattr(g, "current_user", None)
    if not can_use_send_screen(user):
        abort(403)
    found = photo_for_view(get_db(), turn_id=turn_id, seq=seq, user=user, now=now_kst())
    if isinstance(found, DetailResult):
        abort(found.status)
    data, content_type = found
    response = make_response(data)
    response.headers["Content-Type"] = content_type
    response.headers["Cache-Control"] = "private, no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Content-Disposition"] = "inline"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["X-Robots-Tag"] = "noindex, nofollow"
    return response

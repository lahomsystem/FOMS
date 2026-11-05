"""채널톡 안 작은 창(WAM) ``/channel/wam/cs-draft`` — AI 초안 [보내기] · [수정하기]를 데스크 안에서(설계서 17.2.2).

채널톡 앱 'FOMS 연동'의 WAM 주소(``/channel/wam``) 뒤에 이름(``cs-draft``)과 ``/`` 를 붙여(스테이징 실측 11-05 —
``/channel/wam/cs-draft/``) 데스크가 iframe 으로 연다(채널톡 출처만 —
:mod:`foms.platform.security_headers`). **이 화면은 글 · 데이터가 없는 빈 틀이다** — 로그인이 없고, 글은 화면 스크립트
(``static/js/cs-agent/wam-draft.js``)가 채널톡 다리(``window.ChannelIOWam.callFunction``)로 서명 함수를 불러 받는다(누른
상담원은 채널톡이 서명한다 — :mod:`foms.services.cs_agent.wam_functions`). 앱 id 는 env ``CS_WAM_APP_ID``(공개 값).

옛 WAM 화면(:mod:`foms.api.channel.channel_wam` — 410 퇴역)과 블루프린트가 따로라 그쪽 앞 검사를 타지 않는다.
"""

from __future__ import annotations

import os

from flask import Blueprint, make_response, render_template

cs_draft_wam_bp = Blueprint("cs_draft_wam", __name__)

APP_ID_ENV = "CS_WAM_APP_ID"


@cs_draft_wam_bp.route("/channel/wam/cs-draft", methods=["GET"])
@cs_draft_wam_bp.route("/channel/wam/cs-draft/", methods=["GET"])
def cs_draft_wam():
    """빈 틀 — 앱 id 만 싣는다(글 · 차례 · 사람 정보 없음). 캐시하지 않는다."""
    response = make_response(render_template("cs/cs_agent_wam.html", app_id=os.environ.get(APP_ID_ENV, "").strip()))
    response.headers["Cache-Control"] = "no-store"
    return response

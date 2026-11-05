"""채널톡 안 작은 창(WAM) ``/channel/wam/cs-draft`` — AI 초안 [보내기] · [수정하기]를 데스크 안에서(설계서 17.2.2).

채널톡 앱 'FOMS 연동'의 WAM 주소(``/channel/wam``) 뒤에 이름(``cs-draft``)과 ``/`` 를 붙여(스테이징 실측 11-05 —
``/channel/wam/cs-draft/``) 데스크가 iframe 으로 연다(채널톡 출처만 —
:mod:`foms.platform.security_headers`). **이 화면은 글 · 데이터가 없는 빈 틀이다** — 로그인이 없고, 글은 화면 스크립트
(``static/js/cs-agent/wam-draft.js``)가 채널톡 다리(``window.ChannelIOWam.callFunction``)로 서명 함수를 불러 받는다(누른
상담원은 채널톡이 서명한다 — :mod:`foms.services.cs_agent.wam_functions`). 앱 id 는 env ``CS_WAM_APP_ID``(공개 값).

채널톡은 이 화면을 자기 주소(``app-store-api.channel.io/public/v1/apps/<앱>/wams/cs-draft/``)로 거쳐 연다(스테이징 실측 11-05 —
채널톡 다리 ``ChannelIOWam`` 도 그래야 붙는다). 그래서 화면의 꾸밈 · 스크립트는 ``/static`` 이 아니라 이 화면 아래 상대 주소
(``app.css`` · ``app.js``)로 같은 경로에서 내준다.

옛 WAM 화면(:mod:`foms.api.channel.channel_wam` — 410 퇴역)과 블루프린트가 따로라 그쪽 앞 검사를 타지 않는다.
"""

from __future__ import annotations

import logging
import os
import re

from flask import Blueprint, current_app, make_response, render_template, request, send_from_directory

logger = logging.getLogger(__name__)

cs_draft_wam_bp = Blueprint("cs_draft_wam", __name__)

APP_ID_ENV = "CS_WAM_APP_ID"
#: S1 시험 신호 — 영문 · 숫자 · 짧은 기호만(값 · 글 없음). 다른 꼴은 버린다.
_BEACON = re.compile(r"[A-Za-z0-9_.:,|-]{1,160}")


@cs_draft_wam_bp.route("/channel/wam/cs-draft", methods=["GET"])
@cs_draft_wam_bp.route("/channel/wam/cs-draft/", methods=["GET"])
def cs_draft_wam():
    """빈 틀 — 앱 id 만 싣는다(글 · 차례 · 사람 정보 없음). 캐시하지 않는다."""
    response = make_response(render_template("cs/cs_agent_wam.html", app_id=os.environ.get(APP_ID_ENV, "").strip()))
    response.headers["Cache-Control"] = "no-store"
    return response


#: 이 화면 아래에서 내주는 파일(상대 주소 이름 → static 안 자리).
_ASSETS = {"app.js": "js/cs-agent/wam-draft.js", "app.css": "css/contexts/cs/cs-wam.css"}


@cs_draft_wam_bp.route("/channel/wam/cs-draft/app.js", methods=["GET"], defaults={"name": "app.js"})
@cs_draft_wam_bp.route("/channel/wam/cs-draft/app.css", methods=["GET"], defaults={"name": "app.css"})
def cs_draft_wam_asset(name: str):
    """작은 창 꾸밈 · 스크립트 — 채널톡이 거쳐 여는 주소에서도 풀리게 화면 아래에서 내준다(정해진 두 파일만)."""
    response = send_from_directory(current_app.static_folder, _ASSETS[name], max_age=300)
    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@cs_draft_wam_bp.route("/channel/wam/cs-draft/beacon", methods=["GET"])
def cs_draft_wam_beacon():
    """S1 시험 신호 — 작은 창 스크립트가 단계 코드(다리 있음 · 받은 칸 이름 · 함수 결과)만 남긴다. 교차 출처 창이라 화면을 직접
    못 읽어서 둔다(S2 에서 뺀다). 꼴이 틀리면 버리고 늘 204."""
    code = request.args.get("c", "")
    if _BEACON.fullmatch(code):
        logger.info("[CS 작은 창] S1 신호 %s", code)
    return "", 204

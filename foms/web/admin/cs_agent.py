"""AI 상담팀원 관리 패널 화면(``/admin/cs-agent``, ADMIN 만) — 설계서 16.1 · 16.6 단계 1: 스위치 · 두뇌 · 기록 탭.

화면은 서버가 그린다(:func:`foms.services.cs_agent.panel.panel_state` — 숫자 · 코드 · 시각 · 직원 이름만). 쓰기는 작은
스크립트(``static/js/admin/cs-agent-panel.js``)가 JSON API(:mod:`foms.api.admin.cs_agent`)로 보내고 화면을 다시 읽는다.
"""

from __future__ import annotations

from flask import render_template

from db import get_db
from foms.services.cs_agent.panel import panel_state
from foms.services.datetime_kst import now_kst
from foms.web.admin.routes import admin_bp
from foms.web.auth import login_required, role_required

#: 차례 상태 · 감시 루프 결과 코드의 화면 이름(코드는 그대로 옆에 둔다).
STATE_LABELS = {"claimed": "일하는 중", "posting": "올리는 중", "posted": "메모 올림", "stored": "저장만",
                "skipped": "건너뜀", "failed": "실패"}
OUTCOME_LABELS = {"ok": "정상", "killed": "비상 정지로 쉼", "not_leader": "다른 컨테이너가 대표", "stopped": "멈춤 신호",
                  "pass_failed": "바퀴 실패"}


@admin_bp.route("/admin/cs-agent")
@login_required
@role_required(["ADMIN"])
def cs_agent_panel():
    """관리 패널(읽기 전용 렌더 — 쓰기는 JSON API).

    :return: ``admin/cs_agent.html`` 렌더 결과.
    """
    db = get_db()
    state = panel_state(db, now=now_kst())
    db.rollback()  # 읽기 트랜잭션을 닫는다(쓰기 없음)
    return render_template("admin/cs_agent.html", state=state, state_labels=STATE_LABELS,
                           outcome_labels=OUTCOME_LABELS)

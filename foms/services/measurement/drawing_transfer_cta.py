"""실측 대시보드 '도면 전달' CTA 빌더 (STATE-CONTROLS-04).

본공정 stage 축을 ``MEASURE`` → ``DRAWING`` 으로 넘기는 버튼의 **노출·활성 판정**만 만든다.
전이 자체는 화면이 기존 ``POST /api/orders/<id>/quest/approve`` 를 부르는 것으로 일어난다 —
새 API·새 전이 함수는 없다.

주의(이름 축 분리): ``foms/api/drawing/erp_orders_drawing.py`` 의 '도면 전달' 은 도면팀이 도면
**파일**을 넘기는 ``drawing_status`` 축이고 stage 를 바꾸지 않는다. 여기와 섞지 마라.

노출 잣대는 서버 게이트와 같아야 한다(화면이 서버보다 넓은 버튼을 내밀면 403 사고가 난다).
그래서 라우트와 **같은 술어**(:mod:`foms.services.orders.quest_approve_authz`)를 부른다.
"""

from __future__ import annotations

from foms.services.orders.erp_policy_constants import STAGE_NAME_TO_CODE
from foms.services.orders.erp_policy_data_access import get_stage
from foms.services.orders.erp_policy_quests import create_quest_from_template
from foms.services.orders.quest_approve_authz import (
    QUEST_APPROVE_ROLES,
    authorize_quest_approve,
    find_stage_quest,
)
from foms.services.orders.quest_approve_cta import build_approve_cta
from foms.services.orders.state_axes import read_as_status, read_main_stage

__all__ = [
    "DRAWING_TRANSFER_LABEL",
    "TEAM_MODE_BLOCKED_REASON",
    "build_drawing_transfer_ctas",
]


DRAWING_TRANSFER_LABEL = "도면 전달"
TEAM_MODE_BLOCKED_REASON = (
    "이 주문의 실측 퀘스트는 팀 승인 방식이라 여기서 도면 단계로 넘길 수 없습니다."
)

# AS 축이 열려 있는 동안은 단계를 옮기지 않는다. AS 전이는 workflow.stage 를 건드리지
# 않으므로 MEASURE 에서 AS 가 접수된 주문은 stage=MEASURE 로 남고, 상차 예정 알림 버킷은
# as_orders 를 다시 담는다(foms/web/measurement/dashboard.py). 그래서 화면에서만 걸러도
# 안 되고 여기 한 곳에서 막는다.
OPEN_AS_STATUSES = ("RECEIVED", "IN_PROGRESS")

# 라우트(quest.py)와 같은 역방향 표 — stage 코드 → 한글 단계 이름.
CODE_TO_STAGE_NAME = {v: k for k, v in STAGE_NAME_TO_CODE.items()}


def _hidden() -> dict:
    """숨김 항목의 정본 형태(키 5개 고정)."""
    return {
        "visible": False,
        "enabled": False,
        "label": "",
        "confirm": "",
        "blocked_reason": "",
    }


def build_drawing_transfer_ctas(db, orders, current_user) -> dict[int, dict]:
    """주문 id → 도면 전달 CTA dict.

    모든 주문에 대해 항상 한 항목을 만든다(숨김도 항목은 있다). 값의 키는 정확히
    ``visible`` / ``enabled`` / ``label`` / ``confirm`` / ``blocked_reason`` 5개다.

    추가 DB 쿼리는 0회다 — MEASURE 가 아닌 행은 stage 판정에서 끊기고, MEASURE 행의
    :func:`authorize_quest_approve` 는 ``CONSTRUCTION`` 일 때만 DB 를 본다.

    Args:
        db: DB 세션(권한 술어에 그대로 넘긴다).
        orders: 라우트가 이미 로드한 Order 목록(재조회하지 않는다).
        current_user: 현재 로그인 사용자(없으면 전부 숨김).

    Returns:
        ``{order.id: cta dict}``.
    """
    orders = list(orders or [])

    # 0. 라우트 데코레이터 role_required 가 막는 축. 원문 그대로 멤버십 비교(정규화 없음).
    if current_user is None or getattr(current_user, "role", None) not in QUEST_APPROVE_ROLES:
        return {order.id: _hidden() for order in orders}

    ctas: dict = {}
    for order in orders:
        ctas[order.id] = _build_one(db, order, current_user)
    return ctas


def _build_one(db, order, current_user) -> dict:
    """주문 1건의 CTA. 서버가 실제로 밟는 길과 1:1 순서로 판정한다."""
    sd = order.structured_data or {}

    # 1. 현재 단계 원문. 없으면 라우트가 400 '현재 단계가 없습니다' 를 낸다.
    raw_stage = get_stage(sd)
    if not raw_stage:
        return _hidden()

    # 2·3. 본공정 stage 축이 MEASURE 인가. 전이 엔진은 read_main_stage 를 expected_from 과
    #      비교하므로(어긋나면 409 STAGE_CONFLICT) 둘 다 본다.
    stage_code = STAGE_NAME_TO_CODE.get(raw_stage, raw_stage)
    if stage_code != "MEASURE":
        return _hidden()
    if read_main_stage(order) != "MEASURE":
        return _hidden()

    # 3-b. AS 축이 열려 있으면 숨긴다. AS 접수/진행 중인 주문은 stage 가 MEASURE 로
    #      남아 있어도 되돌리기 어려운 도면 전이를 붙이면 안 된다(계약 (e) 가 뺀 행).
    #      read_as_status 는 as_lifecycle 이 없는 레거시 주문도 status=AS_RECEIVED 에서
    #      'RECEIVED' 를 돌려주고, 추가 DB 쿼리도 없다.
    if read_as_status(order) in OPEN_AS_STATUSES:
        return _hidden()

    # 4. 현 단계 quest. 없으면 표시 전용으로 합성한다 — structured_data 에 저장하지 않는다.
    stage_name = CODE_TO_STAGE_NAME.get(raw_stage, raw_stage)
    quest, _index = find_stage_quest(sd, stage_name, raw_stage)
    if quest is None:
        quest = create_quest_from_template(stage_name, "", sd)
        if quest is None:
            return _hidden()

    # 5. 라우트와 같은 권한 술어. stage 인자도 라우트와 같이 정규화 전 원문을 넘긴다.
    allowed, _status, deny_msg = authorize_quest_approve(
        db, current_user, order, raw_stage, quest
    )

    # 6. team 승인 방식이면 1인 승인으로 단계가 넘어가지 않는다(라우트 기본값과 동일).
    approve_completes = quest.get("approval_mode", "team") == "assignee"

    enabled = bool(allowed and approve_completes)
    if enabled:
        blocked_reason = ""
    elif not allowed:
        blocked_reason = deny_msg
    else:
        blocked_reason = TEAM_MODE_BLOCKED_REASON

    return {
        "visible": True,
        "enabled": enabled,
        "label": DRAWING_TRANSFER_LABEL,
        "confirm": build_approve_cta(stage_code, order)["approve_confirm"],
        "blocked_reason": blocked_reason,
    }

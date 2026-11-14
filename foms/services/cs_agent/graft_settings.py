"""관리 패널 '접목(근거 줄 · 할 일 제안)' 칸 묶음 — 상담 AI 에 접목판 두 줄을 켜는 스위치 둘(설계서 2026-11-14-foms-graft 3.9 · 4절).

- 근거 줄(:data:`GRAFT_EVIDENCE_FIELD`): 초안이 쓴 회사 지식 키와 본인이 확인된 주문 키를 그 차례에 남기고(쓰인 곳 기록
  ``brain_usage_events`` — 읽은 쪽 ``cs_draft``), 채널톡 작은 창 [수정하기]에 근거 칩(셋까지)을 보인다.
- 할 일 제안(:data:`GRAFT_ACTIONS_FIELD`): 본인이 확인된 주문에서 규칙 셋(:mod:`.graft_step`)으로 ERP 할 일 제안을 만들고, 작은 창
  줄에 올릴 수 있는 제안(시공 메모 더하기)은 [같이 넣기] · [빼기]로 답 보내기와 같이 정한다.
- 처음 값은 둘 다 **끔**이다 — 끄면 초안 길 · 작은 창 · 함수 답이 지금과 글자까지 같다. 작은 창은 FOMS 로그인이 없어 사람별
  스위치(``FOMS_GRAFT_*``)를 쓰지 않고 이 칸으로만 가른다.

:mod:`.settings` 가 이 모듈을 부르므로 여기서는 칸 꼴(:mod:`.settings_field`)만 가져온다.
"""

from __future__ import annotations

from typing import Any

from foms.services.cs_agent.settings_field import KIND_BOOL, Field

__all__ = ["GRAFT_ACTIONS_FIELD", "GRAFT_EVIDENCE_FIELD", "GRAFT_FIELDS", "GROUP_GRAFT", "actions_on", "evidence_on"]

GROUP_GRAFT = "접목(근거 줄 · 할 일 제안)"
GRAFT_EVIDENCE_FIELD = "graft_evidence_enabled"
GRAFT_ACTIONS_FIELD = "graft_actions_enabled"

GRAFT_FIELDS: tuple[Field, ...] = (
    Field(GRAFT_EVIDENCE_FIELD, "근거 줄 보이기", KIND_BOOL, False, GROUP_GRAFT,
          help="켜면 AI 초안이 쓴 회사 지식과 확인된 주문을 상담 차례에 남기고, 채널톡 작은 창 [수정하기]에 근거 칩을 셋까지 "
               "보여요. 칩을 누르면 FOMS 의 지식 카드 · 주문 화면이 새 창으로 열려요. 끄면 지금 그대로예요"),
    Field(GRAFT_ACTIONS_FIELD, "할 일 제안 만들기", KIND_BOOL, False, GROUP_GRAFT,
          help="켜면 본인이 확인된 주문에서 AS 접수 · 시공 메모 · 방문 옮기기 제안을 규칙으로 만들어 승인 대기로 보내요. 시공 "
               "메모는 작은 창에 [같이 넣기] · [빼기] 줄로 보이고, [같이 넣기]를 고른 채 답을 보내면 보낸 직원 이름으로 바로 "
               "넣어요. 채널톡 상담원에 이어진 FOMS 계정이 있어야 해요. 끄면 지금 그대로예요"),
)


def evidence_on(cfg: Any) -> bool:
    """'근거 줄 보이기' 칸이 켜졌나(참일 때만).

    Args:
        cfg: :func:`.settings.read_settings` 값(``get`` 이 되는 것).

    Returns:
        켜졌으면 True.
    """
    return cfg.get(GRAFT_EVIDENCE_FIELD) is True


def actions_on(cfg: Any) -> bool:
    """'할 일 제안 만들기' 칸이 켜졌나(참일 때만).

    Args:
        cfg: :func:`.settings.read_settings` 값.

    Returns:
        켜졌으면 True.
    """
    return cfg.get(GRAFT_ACTIONS_FIELD) is True

"""도면 담당자 지정의 structured_data 쓰기 모양 — 수동 지정 API 와 마법사 자동 지정이 함께 쓴다.

``apply_drawing_assignees`` 는 호출자가 이미 deepcopy 한 ``sd`` dict 만 고친다(커밋·재대입·
``flag_modified`` 는 호출자 몫). 그래서 REV-00 잠금 쓰기 콜백 안에서도, 잠금 없는 기존 수동
지정 라우트에서도 같은 모양(assignments·drawing_assignees·shipment·workflow.history)을 남긴다.

``maybe_auto_assign_wizard_saver`` 는 2026-09-30 사용자 결정 "마법사로 저장하면 담당자 자동
지정" 의 판정이다: 도면 담당이 한 명도 없는 주문을 도면팀(DRAWING) 활성 사용자가 마법사로
저장하면 그 사람을 담당으로 넣는다. 도면팀이 아닌 관리자는 넣지 않는다.
"""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace
from typing import Iterable, Optional

from models import OrderEvent
from foms.services.orders.erp_policy_permissions import get_assignee_ids

#: 자동 지정 OrderEvent·감사의 change_method 값.
WIZARD_AUTO_ASSIGN_METHOD = 'WIZARD_AUTO'


def apply_drawing_assignees(sd: dict, assigned_users: Iterable, *, user_ids: list,
                            actor_name: str, note: str) -> dict:
    """``sd`` 에 도면 담당자 지정 모양을 쓴다(in-place). 이전 값을 돌려준다.

    :param sd: 호출자가 deepcopy 한 structured_data dict.
    :param assigned_users: 지정할 :class:`~models.User` 목록(id·name·team).
    :param user_ids: ``assignments.drawing_assignee_user_ids`` 에 그대로 넣을 id 목록.
    :param actor_name: 이력의 ``updated_by``.
    :param note: 이력 문장(예 ``도면 담당자 지정: 홍길동``).
    :returns: ``{'old_names': [...], 'old_ids': [...], 'names': 'a, b'}``.
    """
    users = list(assigned_users)
    old_assignees = sd.get('drawing_assignees') or []
    old_names = [a.get('name', '') for a in old_assignees if isinstance(a, dict)]
    assignments = sd.get('assignments')
    old_ids = assignments.get('drawing_assignee_user_ids', []) if isinstance(assignments, dict) else []

    if not isinstance(assignments, dict):
        assignments = {}
        sd['assignments'] = assignments
    assignments['drawing_assignee_user_ids'] = user_ids

    sd['drawing_assignees'] = [{'id': u.id, 'name': u.name, 'team': u.team} for u in users]

    shipment = sd.get('shipment')
    if not isinstance(shipment, dict):
        shipment = {}
    shipment['drawing_managers'] = [u.name for u in users]
    sd['shipment'] = shipment

    wf = sd.get('workflow')
    if not isinstance(wf, dict):
        wf = {}
    hist = wf.get('history')
    if not isinstance(hist, list):
        hist = []
    hist.append({
        'stage': wf.get('stage', 'DRAWING'),
        'updated_at': datetime.now().isoformat(),
        'updated_by': actor_name or 'Unknown',
        'note': note,
    })
    wf['history'] = hist
    sd['workflow'] = wf

    return {'old_names': old_names, 'old_ids': old_ids,
            'names': ', '.join(u.name for u in users)}


def should_auto_assign_wizard_saver(sd: dict, user) -> bool:
    """도면 담당이 비었고 ``user`` 가 도면팀 활성 사용자이면 참."""
    if user is None or not getattr(user, 'is_active', False):
        return False
    if (getattr(user, 'team', None) or '').strip() != 'DRAWING':
        return False
    return not get_assignee_ids(SimpleNamespace(structured_data=sd), 'DRAWING_DOMAIN')


def maybe_auto_assign_wizard_saver(session, order_id: int, sd: dict, user) -> Optional[dict]:
    """조건이 맞으면 ``sd`` 에 ``user`` 를 도면 담당으로 쓰고 OrderEvent 를 같은 세션에 싣는다.

    잠근 최신 ``sd`` 위에서 불러야 한다(같은 트랜잭션·같은 버전 +1). 알림은 보내지 않는다 —
    수동 지정 API 도 알림을 보내지 않는다.

    :returns: 지정했으면 ``{'user_id', 'name'}``, 아니면 None.
    """
    if not should_auto_assign_wizard_saver(sd, user):
        return None
    before = apply_drawing_assignees(
        sd, [user], user_ids=[int(user.id)], actor_name=user.name,
        note=f'도면 담당자 자동 지정: {user.name} (마법사 저장)',
    )
    session.add(OrderEvent(
        order_id=int(order_id),
        event_type='DRAWING_ASSIGNEE_SET',
        payload={
            'domain': 'DRAWING_DOMAIN',
            'action': 'DRAWING_ASSIGNEE_SET',
            'target': 'assignments.drawing_assignee_user_ids',
            'before': ', '.join(before['old_names']) if before['old_names'] else 'None',
            'after': user.name,
            'before_ids': before['old_ids'],
            'after_ids': [int(user.id)],
            'assignee_names': [user.name],
            'assignee_user_ids': [int(user.id)],
            'change_method': WIZARD_AUTO_ASSIGN_METHOD,
            'source_screen': 'drawing_wizard',
            'reason': '도면 담당자 자동 지정(마법사 저장)',
        },
        created_by_user_id=int(user.id),
    ))
    return {'user_id': int(user.id), 'name': user.name}

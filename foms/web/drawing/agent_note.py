"""AI 도면팀원 노트 화면 — 주간 노트(배운 것 · 바뀐 것)와 도면팀에 묻는 질문.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A3

- 도면팀 알림('AI 도면팀원 노트')을 누르면 여기로 온다(foms/api/notifications 의 깊은 링크).
- 최근 노트 4개를 새것부터 보인다. 질문은 닮은 두 그림과 고른 종류를 나란히 두고 답을 받는다
  (답하기는 도면팀 · 관리자만 — POST /api/drawing-agent/notes/<id>/answer, 정책 DRAWING_TEAM).
- 그림은 주문 그림 보기 길(asset-raw)로만 연다 — 로그인 · 주문 권한 검사를 그대로 탄다.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

from flask import g, render_template

from db import get_db
from foms.services import drawing_agent_notes as agent_notes
from foms.web.auth import login_required
from foms.web.drawing.workbench import erp_drawing_workbench_bp

SHOW_NOTES = 4
CHOICE_TEXT = agent_notes.CHOICE_TEXT
RULE_TEXT = {'head': '머리칸 빈칸', 'unsorted': '미분류 그림', 'dup': '같은 그림 두 번', 'outside': '테두리 밖 그림',
             'text': '작은 치수 글자', 'bom': '자재표 다름'}


def can_answer(user: Any) -> bool:
    return bool(user) and (getattr(user, 'role', '') == 'ADMIN' or (getattr(user, 'team', '') or '').upper() == 'DRAWING')


def _side_view(side: dict[str, Any]) -> dict[str, Any]:
    order, key = side.get('order'), side.get('key') or ''
    return {'label': side.get('label'), 'order': order,
            'src': f'/api/orders/{int(order)}/drawing-wizard/asset-raw?key={quote(key, safe="")}' if order and key else None}


def note_view(note: dict[str, Any]) -> dict[str, Any]:
    questions = []
    for q in note.get('questions') or []:
        ans = q.get('answer') if isinstance(q.get('answer'), dict) else None
        questions.append({'id': q.get('id'), 'sim': round(float(q.get('sim') or 0) * 100), 'a': _side_view(q.get('a') or {}),
                          'b': _side_view(q.get('b') or {}),
                          'answer': {'choice': ans.get('choice'), 'text': CHOICE_TEXT.get(ans.get('choice'), ''),
                                     'name': ans.get('name') or ''} if ans else None})
    stats = note.get('stats') or {}
    review = note.get('review') or {}
    return {'id': note.get('id'), 'title': note.get('title') or note.get('id'), 'stats': stats,
            'review': [{'rule': RULE_TEXT.get(rule, rule), 'seen': v.get('seen', 0), 'off': v.get('off', 0)} for rule, v in review.items()],
            'changes': note.get('changes') or [], 'questions': questions}


@erp_drawing_workbench_bp.route('/drawing-workbench/agent-note')
@login_required
def erp_drawing_agent_note():
    """AI 도면팀원 노트 — 노트가 아직 없으면 안내만."""
    book = agent_notes.load_book(get_db())
    notes = [note_view(n) for n in reversed(book['notes'][-SHOW_NOTES:])]
    return render_template('drawing/agent_note.html', notes=notes,
                           can_answer=can_answer(getattr(g, 'current_user', None)), choice_text=CHOICE_TEXT)

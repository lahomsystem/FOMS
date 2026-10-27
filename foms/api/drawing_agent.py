"""AI 도면팀원 — 학습 요약 읽기 길(읽기 전용 JSON, 토큰 하나로만).

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §3 · §4 (2026-10-27 사용자 승인 "추천대로")

``GET /api/drawing-agent/digest?kind=summary|memory|sheets|notes&since=<ISO>&after=<번호>&limit=<수>``

- 로그인 세션이 아니라 ``Authorization: Bearer <토큰>`` 으로만 연다(원격 연구 루틴 전용).
  서버는 토큰 원문을 모르고 환경 변수 ``FOMS_DRAWING_AGENT_TOKEN_SHA256`` 지문과만 맞춘다.
- 지문이 없으면 길이 꺼져 있다(**404**). 토큰이 없거나 틀리면 **401**. 토큰으로는 읽기만 된다.

``POST /api/drawing-agent/notes/<노트>/answer`` ``{qid, choice}`` — 주간 노트 질문에 답한다(로그인 세션 · 도면팀 · 관리자,
정책 DRAWING_TEAM). 토큰으로는 못 쓴다.
- 고객 정보는 담지 않는다 — 무엇을 빼는지는 :mod:`foms.services.drawing_agent_digest`.
- 응답은 캐시하지 않는다(``Cache-Control: no-store``).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from flask import Blueprint, current_app, g, jsonify, request

from db import get_db
from foms.services import drawing_agent_digest as agent_digest
from foms.services import drawing_agent_notes as agent_notes

logger = logging.getLogger(__name__)

drawing_agent_bp = Blueprint('drawing_agent', __name__, url_prefix='/api/drawing-agent')
_NOTE_ID = re.compile(r'^\d{4}-W\d{2}$')
_QID = re.compile(r'^q\d{1,2}$')


def _reply(payload: dict[str, Any], status: int = 200):
    resp = jsonify(payload)
    resp.status_code = status
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _fail(status: int, error: str, message: str):
    return _reply({'success': False, 'data': None, 'error': error, 'message': message}, status)


def _int_arg(name: str, default: int, lo: int, hi: int) -> int:
    raw = request.args.get(name)
    if raw is None or raw == '':
        return default
    value = int(raw)   # 숫자가 아니면 ValueError → 400
    return max(lo, min(hi, value))


@drawing_agent_bp.route('/digest', methods=['GET'])
def api_drawing_agent_digest():
    """학습 요약 한 쪽. ``memory`` · ``sheets`` 는 ``next`` 를 ``after`` 로 넘겨 이어 읽는다."""
    if not agent_digest.token_configured():
        return _fail(404, 'disabled', '학습 요약 길이 꺼져 있습니다.')
    if not agent_digest.token_ok(request.headers.get('Authorization')):
        logger.warning('DRAWING_AGENT_DIGEST_DENIED ip=%s', request.remote_addr)
        return _fail(401, 'unauthorized', '토큰이 맞지 않습니다.')
    kind = (request.args.get('kind') or 'summary').strip()
    if kind not in agent_digest.KINDS:
        return _fail(400, 'bad_kind', f'kind 는 {", ".join(agent_digest.KINDS)} 중 하나입니다.')
    try:
        since = agent_digest.parse_since(request.args.get('since'))
        after = _int_arg('after', 0, 0, 2**31 - 1)
        limit = _int_arg('limit', agent_digest.MAX_LIMIT.get(kind, 1), 1, agent_digest.MAX_LIMIT.get(kind, 1))
    except ValueError:
        return _fail(400, 'bad_query', 'since · after · limit 값을 읽지 못했습니다.')
    db = get_db()
    data: dict[str, Any] = {'kind': kind, 'version': agent_digest.DIGEST_VERSION}
    if kind == 'summary':
        data.update(agent_digest.summary(db))
    elif kind == 'memory':
        data.update(agent_digest.memory_page(db, since=since, after=after, limit=limit,
                                             secret=str(current_app.config.get('SECRET_KEY') or '')))
    elif kind == 'sheets':
        data.update(agent_digest.sheets_page(db, since=since, after=after, limit=limit))
    else:
        data.update(agent_digest.notes_digest(db, str(current_app.config.get('SECRET_KEY') or '')))
    return _reply({'success': True, 'data': data, 'error': None})


@drawing_agent_bp.route('/notes/<note_id>/answer', methods=['POST'])
def api_drawing_agent_note_answer(note_id: str):
    """주간 노트 질문에 답한다 — 고른 쪽으로 기억 이름표를 맞추고 답을 노트에 남긴다."""
    user = getattr(g, 'current_user', None)
    if user is None:
        return _fail(401, 'unauthorized', '로그인이 필요합니다.')
    if not (getattr(user, 'role', '') == 'ADMIN' or (getattr(user, 'team', '') or '').upper() == 'DRAWING'):
        return _fail(403, 'forbidden', '도면팀만 답할 수 있습니다.')
    body = request.get_json(silent=True) or {}
    qid, choice = body.get('qid'), body.get('choice')
    if (not _NOTE_ID.fullmatch(note_id or '') or not isinstance(qid, str) or not _QID.fullmatch(qid)
            or choice not in agent_notes.CHOICES):
        return _fail(400, 'bad_answer', '답 형식이 올바르지 않습니다.')
    db = get_db()
    try:
        note = agent_notes.answer(db, note_id, qid, choice, user)
    except agent_notes.NoteError as exc:
        db.rollback()
        return _fail(exc.status, 'bad_answer', exc.message)
    db.commit()
    ans = next(q for q in note['questions'] if q.get('id') == qid)['answer']
    return _reply({'success': True, 'error': None, 'data': {'question': {'id': qid, 'answer': {
        'choice': ans['choice'], 'text': agent_notes.CHOICE_TEXT[ans['choice']], 'name': ans.get('name') or ''}}}})

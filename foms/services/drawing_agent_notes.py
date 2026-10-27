"""AI 도면팀원 주간 노트 — 지난주 배운 것 · 바뀐 것 · 도면팀에 물어볼 것.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 A3 (2026-10-27 사용자 승인 "추천대로")

- FOMS-cron(매일 02:00 KST, tools/cron/drawing_agent_note.py)이 부른다. 그 주(월~일, KST) 노트가 아직 없을 때만 만든다
  — 월요일에 크론이 쉬어도 다음 날 만든다.
- 노트는 SystemSetting ``drawing_agent_notes`` 에 최근 26개만(주문 데이터를 바꾸지 않는다).
- 도면팀에 앱 안 알림을 남긴다(새벽이라 폰 푸시는 보내지 않는다). 알림을 누르면 /erp/drawing-workbench/agent-note.
- 물어볼 것: 지난 4주 사람이 고른 그림 중 아주 닮았는데(0.95, 같은 보기의 내부/도어는 0.985) 종류가 다른 두 장 — 3쌍까지,
  이미 물은 쌍은 다시 묻지 않는다.
- 답(도면팀 · 관리자): 'a' = 왼쪽이 맞음 → 오른쪽 그림 기억을 왼쪽 종류로, 'b' = 반대, 'both' = 그림마다 다름(기억은 그대로).
  답은 학습 요약(digest kind=notes)으로 연구 루틴에 가서 팀 기준(docs/drawing-agent/TEAM-RULES.md)이 된다.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
from sqlalchemy.orm.attributes import flag_modified

from foms.services.datetime_kst import now_utc_naive
from foms.services.drawing_agent_account import AGENT_NAME, ensure_agent_user
from foms.services.notifications.recipients import fan_out_new_notification
from models import DrawingPartMemory, Notification, Order, SystemSetting

SETTING_KEY = 'drawing_agent_notes'
NOTIFICATION_TYPE = 'DRAWING_AGENT_NOTE'
NOTE_URL = '/erp/drawing-workbench/agent-note'
KEEP_NOTES = 26
KEEP_ASKED = 500
MAX_QUESTIONS = 3
ASK_WINDOW_DAYS = 28
MAX_ASK_ROWS = 1500
MIN_SIM = 0.95
MIN_SIM_DOOR = 0.985
MAX_REVIEW_ORDERS = 300
CHOICES = ('a', 'b', 'both')
CHOICE_TEXT = {'a': '왼쪽이 맞아요', 'b': '오른쪽이 맞아요', 'both': '둘 다 맞아요(그림마다 달라요)'}
KST = timedelta(hours=9)
_CHANGES = Path(__file__).with_name("drawing_agent_changes.json")
_DOOR_PAIRS = (frozenset({'정면·내부', '정면·도어'}), frozenset({'입체·내부', '입체·도어'}))
REVIEW_RULES = ('head', 'unsorted', 'dup', 'outside', 'text', 'bom')   # review-memo.js 규칙 — 모르는 key 는 세지 않는다


class NoteError(ValueError):
    """잘못된 답(없는 노트 · 질문 · 고르기) — API 는 400/404 로 바꾼다."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def week_start(now_utc: datetime) -> datetime:
    """KST 기준 이번 주 월요일 00:00 을 UTC naive 로."""
    kst = now_utc + KST
    monday = (kst - timedelta(days=kst.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday - KST


def week_id(now_utc: datetime) -> str:
    year, week, _ = (now_utc + KST).isocalendar()
    return f'{year}-W{week:02d}'


def week_title(start_utc: datetime) -> str:
    """'10월 4주' — 지난주(노트가 정리하는 주) 월요일 기준."""
    last = start_utc + KST - timedelta(days=7)
    return f'{last.month}월 {(last.day - 1) // 7 + 1}주'


def _setting(db, *, lock: bool = False):
    q = db.query(SystemSetting).filter(SystemSetting.setting_key == SETTING_KEY)
    return (q.with_for_update() if lock else q).one_or_none()


def load_book(db) -> dict[str, Any]:
    row = _setting(db)
    value = row.setting_value if row is not None and isinstance(row.setting_value, dict) else {}
    notes = value.get('notes') if isinstance(value.get('notes'), list) else []
    asked = value.get('asked') if isinstance(value.get('asked'), list) else []
    return {'notes': notes, 'asked': asked, 'version': int(row.version or 0) if row is not None else 0}


def _store(db, book: dict[str, Any]) -> None:
    row = _setting(db, lock=True)
    if row is None:
        row = SystemSetting(setting_key=SETTING_KEY, version=0, description='AI 도면팀원 주간 노트 · 물어본 쌍(최근 26주)')
        db.add(row)
        db.flush()
    row.setting_value = {'notes': book['notes'][-KEEP_NOTES:], 'asked': book['asked'][-KEEP_ASKED:]}
    flag_modified(row, 'setting_value')
    row.version = int(row.version or 0) + 1


def load_changes() -> list[dict[str, str]]:
    try:
        items = json.loads(_CHANGES.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return []
    return [i for i in items if isinstance(i, dict) and isinstance(i.get('date'), str) and isinstance(i.get('text'), str)]


def _door_only(a: str, b: str) -> bool:
    return frozenset({a, b}) in _DOOR_PAIRS


def label_stats(db, start: datetime, end: datetime) -> dict[str, Any]:
    rows = (db.query(DrawingPartMemory.ai, DrawingPartMemory.label)
            .filter(DrawingPartMemory.src == 'user', DrawingPartMemory.active.is_(True),
                    DrawingPartMemory.updated_at >= start, DrawingPartMemory.updated_at < end).all())
    pairs: dict[tuple[str, str], int] = {}
    for ai, label in rows:
        if ai and ai != label:
            pairs[(ai, label)] = pairs.get((ai, label), 0) + 1
    top = sorted(pairs.items(), key=lambda kv: (-kv[1], kv[0]))[:3]
    return {
        'labels': len(rows),
        'agree': sum(1 for ai, label in rows if ai and ai == label),
        'changed': sum(pairs.values()),
        'top_changes': [[ai, label, n] for (ai, label), n in top],
        'new_rows': db.query(DrawingPartMemory.id).filter(DrawingPartMemory.created_at >= start,
                                                          DrawingPartMemory.created_at < end).count(),
    }


def review_stats(db, start: datetime, end: datetime) -> dict[str, dict[str, int]]:
    """그 주 그림을 다룬 주문의 시트 검수 메모 기록 — 메모마다 보인 시트 수 · 끈 시트 수."""
    order_ids = [oid for (oid,) in db.query(DrawingPartMemory.order_id)
                 .filter(DrawingPartMemory.updated_at >= start, DrawingPartMemory.updated_at < end)
                 .distinct().limit(MAX_REVIEW_ORDERS).all()]
    out: dict[str, dict[str, int]] = {}
    if not order_ids:
        return out
    for (sd,) in db.query(Order.structured_data).filter(Order.id.in_(order_ids)).all():
        wizard = sd.get('drawing_wizard') if isinstance(sd, dict) else None
        for sheet in (wizard.get('sheets') or []) if isinstance(wizard, dict) else []:
            review = sheet.get('review') if isinstance(sheet, dict) else None
            if not isinstance(review, dict):
                continue
            for field in ('seen', 'off'):
                for rule in {str(k).split(':', 1)[0] for k in (review.get(field) or [])} & set(REVIEW_RULES):
                    out.setdefault(rule, {'seen': 0, 'off': 0})[field] += 1
    return dict(sorted(out.items()))


def _side(row: DrawingPartMemory) -> dict[str, Any]:
    return {'mem': row.id, 'order': row.order_id, 'key': row.asset_key, 'label': row.label}


def find_questions(db, now: datetime, asked: list[str]) -> list[dict[str, Any]]:
    rows = (db.query(DrawingPartMemory)
            .filter(DrawingPartMemory.src == 'user', DrawingPartMemory.active.is_(True), DrawingPartMemory.feat.isnot(None),
                    DrawingPartMemory.updated_at >= now - timedelta(days=ASK_WINDOW_DAYS))
            .order_by(DrawingPartMemory.updated_at.desc()).limit(MAX_ASK_ROWS).all())
    rows = [r for r in rows if r.feat and len(r.feat) == 1536]
    if len(rows) < 2:
        return []
    versions: dict[str, int] = {}
    for r in rows:
        versions[r.feat_v] = versions.get(r.feat_v, 0) + 1
    main = max(versions, key=versions.get)
    rows = [r for r in rows if r.feat_v == main]
    if len(rows) < 2:
        return []
    feats = np.stack([np.frombuffer(r.feat, dtype='<f2').astype(np.float32) for r in rows])
    sims = feats @ feats.T
    seen = set(asked)
    found: list[tuple[float, int, int]] = []
    ii, jj = np.where(np.triu(sims >= MIN_SIM, k=1))
    for i, j in zip(ii.tolist(), jj.tolist()):
        a, b = rows[i], rows[j]
        if a.label == b.label or (a.order_id == b.order_id and a.asset_key == b.asset_key):
            continue
        sim = float(sims[i, j])
        if _door_only(a.label, b.label) and sim < MIN_SIM_DOOR:
            continue
        if f'{min(a.id, b.id)}-{max(a.id, b.id)}' in seen:
            continue
        found.append((sim, i, j))
    found.sort(key=lambda t: -t[0])
    out, used = [], set()
    for sim, i, j in found:
        if i in used or j in used:
            continue
        used.update((i, j))
        out.append({'id': f'q{len(out) + 1}', 'sim': round(sim, 3), 'a': _side(rows[i]), 'b': _side(rows[j]), 'answer': None})
        if len(out) >= MAX_QUESTIONS:
            break
    return out


def build_note(db, now: datetime, book: dict[str, Any]) -> dict[str, Any]:
    start = week_start(now)
    prev = start - timedelta(days=7)
    last_at = book['notes'][-1].get('created_at') if book['notes'] else None
    since_day = (last_at or (prev + KST).isoformat())[:10]
    return {
        'id': week_id(now), 'title': week_title(start), 'created_at': now.isoformat(timespec='seconds'),
        'window': [prev.isoformat(timespec='seconds'), start.isoformat(timespec='seconds')],
        'stats': label_stats(db, prev, start), 'review': review_stats(db, prev, start),
        'changes': [c for c in load_changes() if c['date'] >= since_day][-10:],
        'questions': find_questions(db, now, book['asked']),
    }


def summary_line(note: dict[str, Any]) -> str:
    s = note['stats']
    parts = [f"사람이 고른 그림 {s['labels']}장", f"AI 짐작과 같음 {s['agree']}장"]
    if s['top_changes']:
        ai, label, n = s['top_changes'][0]
        parts.append(f'자주 고친 것 {ai}→{label} {n}장')
    if note['questions']:
        parts.append(f"물어볼 것 {len(note['questions'])}개")
    return ' · '.join(parts)


def create_weekly_note(db, now: datetime) -> dict[str, Any] | None:
    """이번 주 노트가 없으면 만들고 도면팀에 알린다(커밋은 부르는 쪽). 이미 있으면 None."""
    book = load_book(db)
    if any(n.get('id') == week_id(now) for n in book['notes']):
        return None
    note = build_note(db, now, book)
    book['notes'].append(note)
    book['asked'].extend(f"{min(q['a']['mem'], q['b']['mem'])}-{max(q['a']['mem'], q['b']['mem'])}" for q in note['questions'])
    _store(db, book)
    agent = ensure_agent_user(db)
    notif = Notification(order_id=None, notification_type=NOTIFICATION_TYPE, target_team='DRAWING',
                         title=f"AI 도면팀원 노트 · {note['title']}", message=summary_line(note),
                         created_by_user_id=agent.id, created_by_name=AGENT_NAME)
    db.add(notif)
    db.flush()
    fan_out_new_notification(db, notif, actor_user_id=agent.id)
    return note


def answer(db, note_id: str, qid: str, choice: str, user) -> dict[str, Any]:
    """질문에 답한다(커밋은 부르는 쪽). 이미 답한 질문은 새 답으로 바꾸고 기억 이름표도 다시 맞춘다."""
    if choice not in CHOICES:
        raise NoteError('고를 수 있는 답은 a · b · both 입니다.')
    book = load_book(db)
    note = next((n for n in book['notes'] if n.get('id') == note_id), None)
    question = next((q for q in (note or {}).get('questions') or [] if q.get('id') == qid), None)
    if question is None:
        raise NoteError('노트나 질문을 찾지 못했습니다.', 404)
    ids = [question['a']['mem'], question['b']['mem']]
    rows = {r.id: r for r in db.query(DrawingPartMemory).filter(DrawingPartMemory.id.in_(ids)).all()}

    def sides(pick: str) -> tuple[dict[str, Any], dict[str, Any]]:
        return (question['a'], question['b']) if pick == 'a' else (question['b'], question['a'])

    prev = (question.get('answer') or {}).get('choice')
    if prev in ('a', 'b'):   # 답을 바꾸면 앞 답이 바꾼 이름표를 먼저 되돌린다(그 뒤 사람이 또 고친 것은 두고)
        right, wrong = sides(prev)
        row = rows.get(wrong['mem'])
        if row is not None and row.label == right['label']:
            row.label = wrong['label']
    if choice in ('a', 'b'):
        right, wrong = sides(choice)
        row = rows.get(wrong['mem'])
        if row is not None:
            row.label = right['label']
            row.src = 'user'
            row.updated_by = getattr(user, 'id', None)
    question['answer'] = {'choice': choice, 'by': getattr(user, 'id', None), 'name': getattr(user, 'name', None),
                          'at': now_utc_naive().isoformat(timespec='seconds')}
    _store(db, book)
    return copy.deepcopy(note)

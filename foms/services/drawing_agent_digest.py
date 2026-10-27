"""AI 도면팀원 학습 요약(digest) — 고객 정보 없이 마법사 학습 자료만 내준다.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §3 · §4 (2026-10-27 사용자 승인 "추천대로")

- 읽는 쪽: 원격 연구 루틴(Claude) — ``GET /api/drawing-agent/digest`` 를 읽기 전용 토큰 하나로만 연다.
  운영 읽기를 상시 허락하는 유일한 예외라서 고객 정보(이름 · 전화 · 주소 · 메모 글 · 그림 파일 · 사람 이름)는 아예 담지 않는다.
- 토큰은 서버에 원문을 두지 않는다. 환경 변수 ``FOMS_DRAWING_AGENT_TOKEN_SHA256`` 에 sha256 지문만 둔다
  (환경 변수가 새도 토큰은 모른다 — 2026-10-21 Railway env 유출 사고 교훈). 지문이 없으면 길 자체가 꺼진다.
- 그림 파일 이름에 고객 이름이 들어갈 수 있어 그림 key 는 지문(sha1 앞 16자)으로만 낸다. 주문은 번호만.
- 사람은 익명 번호('p' + HMAC 8자). 기준 맞추기에만 쓰고 사람 평가에 쓰지 않는다(설계서 §6).
- 시트 글자 상자는 자재표 숫자 줄(머리글 · 치수=수량 · 피닉스바 EA)만 골라 낸다 — 메모 글은 버린다.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import re
from datetime import datetime
from typing import Any

from foms.services.drawing_agent_notes import load_book
from models import DrawingPartMemory, Order

TOKEN_ENV = 'FOMS_DRAWING_AGENT_TOKEN_SHA256'
DIGEST_VERSION = 1
KINDS = ('summary', 'memory', 'sheets', 'notes')
MAX_LIMIT = {'memory': 500, 'sheets': 50}
_SHA256_HEX = re.compile(r'[0-9a-f]{64}')
_BOM_HEAD = re.compile(r'^\[\s*([^\]]{1,12}?)\s*\]\s*(.*)$')
_BOM_ROW = re.compile(r'^(\d{2,4})\s*(?:[*xX×＊]\s*(\d{2,4})\s*)?[=:＝]\s*(\d{1,3})\s*(?:EA)?$', re.IGNORECASE)
_BOM_EA = re.compile(r'^ㄴ?\s*피닉스바\s*(\d{1,3})\s*EA$', re.IGNORECASE)
_BOM_ALIAS = {'SR': 'SR', '스라': 'SR', 'EP': 'EP', 'DOOR': 'DOOR', '도어': 'DOOR', '옷봉': '옷봉', '마이다': '마이다'}
_IMAGE_FIELDS = ('x', 'y', 'w', 'h', 'natural_w', 'natural_h', 'rotation')
_PART_FIELDS = ('label', 'src', 'ai', 'conf', 'head', 'arr')
_CALC_FIELDS = ('in', 'out', 'rules', 'mode')


def token_configured() -> bool:
    return bool(_SHA256_HEX.fullmatch((os.environ.get(TOKEN_ENV) or '').strip().lower()))


def token_ok(authorization: str | None) -> bool:
    """``Authorization: Bearer <토큰>`` 이 환경 변수 지문과 맞는지(상수 시간 비교)."""
    expected = (os.environ.get(TOKEN_ENV) or '').strip().lower()
    if not _SHA256_HEX.fullmatch(expected) or not authorization:
        return False
    scheme, _, token = authorization.partition(' ')
    token = token.strip()
    if scheme != 'Bearer' or not (32 <= len(token) <= 256):
        return False
    got = hashlib.sha256(token.encode('utf-8')).hexdigest()
    return hmac.compare_digest(got, expected)


def family_of(text: str) -> str:
    """제품 이름 → 제품 종류 — 다시 가르치기 도구(tools/drawing_ai/retrain_data.py family_of)와 같은 규칙.

    요약에는 제품 이름 대신 이 네 갈래만 낸다(제품 칸 글에 무엇이 섞일지 모른다).
    """
    p = text or ''
    if re.search(r'냉장고', p):
        return '냉장고장'
    if re.search(r'부엌|주방|싱크|아일랜드|하부장|상부장|홈카페|홈바', p):
        return '주방'
    if re.search(r'붙박이|여닫이|슬라이딩|월플렉스|드레스', p):
        return '붙박이장'
    return '그 밖 장'


def _sheet_product_text(sheet: dict[str, Any], items: list[Any], order_product: str | None) -> str:
    words = []
    idx = sheet.get('product_index')
    if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(items):
        item = items[idx] if isinstance(items[idx], dict) else {}
        words.append(str(item.get('product_name') or item.get('name') or ''))
    words.append(str(sheet.get('name') or ''))
    words.append(str(order_product or ''))
    return ' '.join(w for w in words if w)


def key_hash(asset_key: str | None) -> str | None:
    if not asset_key:
        return None
    return hashlib.sha1(asset_key.encode('utf-8')).hexdigest()[:16]


def anon_id(user_id: int | None, secret: str) -> str | None:
    if user_id is None:
        return None
    mac = hmac.new(secret.encode('utf-8'), f'drawing-agent:{int(user_id)}'.encode('utf-8'), hashlib.sha256)
    return 'p' + mac.hexdigest()[:8]


def _iso(value: datetime | None) -> str | None:
    return value.isoformat(timespec='seconds') if value else None


def parse_since(raw: str | None) -> datetime | None:
    """``since`` 질의 값(ISO 날짜 · 시각, UTC naive 로 본다) — 못 읽으면 ValueError."""
    if not raw:
        return None
    value = datetime.fromisoformat(raw.strip().replace('Z', '+00:00'))
    return value.replace(tzinfo=None)


def bom_lines(texts: list[Any]) -> list[dict[str, Any]]:
    """시트 글자 상자들 → 자재표 숫자 줄 [{sec, a, b, q} | {sec, ea}] — 머리글 아래 숫자 줄만, 나머지 글은 버린다."""
    out: list[dict[str, Any]] = []
    for text in texts:
        if not isinstance(text, str):
            continue
        sec = None
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            head = _BOM_HEAD.match(line)
            if head:
                word = re.sub(r'\s+', '', head.group(1))
                sec = _BOM_ALIAS.get(word.upper()) or _BOM_ALIAS.get(word) or '기타'
                line = head.group(2).strip()
                if not line:
                    continue
            if sec is None:
                continue
            row = _BOM_ROW.match(line)
            if row:
                item = {'sec': sec, 'a': int(row.group(1)), 'q': int(row.group(3))}
                if row.group(2):
                    item['b'] = int(row.group(2))
                out.append(item)
                continue
            ea = _BOM_EA.match(line)
            if ea:
                out.append({'sec': sec, 'ea': int(ea.group(1))})
    return out


def _image(obj: dict[str, Any]) -> dict[str, Any]:
    item: dict[str, Any] = {'key': key_hash(obj.get('key'))}
    for name in _IMAGE_FIELDS:
        value = obj.get(name)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            item[name] = value
    if obj.get('locked') is True:
        item['locked'] = True
    part = obj.get('part')
    if isinstance(part, dict):
        item['part'] = {name: part[name] for name in _PART_FIELDS if name in part}
    return item


def sheet_digest(order_id: int, index: int, sheet: dict[str, Any], family: str = '그 밖 장') -> dict[str, Any]:
    """시트 하나 → 고객 정보 없는 학습 자료(머리칸 · 시트 이름 · 메모 글 없음, 제품은 네 갈래 종류만)."""
    objects = sheet.get('objects') if isinstance(sheet.get('objects'), list) else []
    images = [_image(o) for o in objects if isinstance(o, dict) and o.get('type') == 'image']
    texts = [o.get('text') for o in objects if isinstance(o, dict) and o.get('type') == 'text']
    item: dict[str, Any] = {'order': order_id, 'sheet': index, 'family': family, 'images': images, 'bom': bom_lines(texts)}
    if isinstance(sheet.get('product_index'), int):
        item['product_index'] = sheet['product_index']
    calc = sheet.get('calc')
    if isinstance(calc, dict):
        item['calc'] = {name: calc[name] for name in _CALC_FIELDS if name in calc and name != 'out'}
        if isinstance(calc.get('out'), str):   # 계산 글자도 숫자 줄로만(글자 칸이라 무엇이든 들어갈 수 있다)
            item['calc']['out'] = bom_lines([calc['out']])
    review = sheet.get('review')
    if isinstance(review, dict):
        item['review'] = {name: list(review[name]) for name in ('off', 'seen') if isinstance(review.get(name), list)}
    return item


def memory_row(row: DrawingPartMemory, secret: str) -> dict[str, Any]:
    return {
        'id': row.id, 'order': row.order_id, 'key': key_hash(row.asset_key),
        'feat': base64.b64encode(row.feat).decode('ascii') if row.feat else None, 'fv': row.feat_v,
        'ai': row.ai, 'conf': row.conf, 'head': row.head, 'label': row.label, 'src': row.src, 'active': bool(row.active),
        'by': anon_id(row.updated_by or row.created_by, secret), 'at': _iso(row.updated_at),
    }


def memory_page(db, *, since: datetime | None, after: int, limit: int, secret: str) -> dict[str, Any]:
    q = db.query(DrawingPartMemory).filter(DrawingPartMemory.id > after)
    if since is not None:
        q = q.filter(DrawingPartMemory.updated_at >= since)
    rows = q.order_by(DrawingPartMemory.id.asc()).limit(limit + 1).all()
    more = len(rows) > limit
    rows = rows[:limit]
    return {'items': [memory_row(r, secret) for r in rows], 'next': rows[-1].id if more and rows else None}


def sheets_page(db, *, since: datetime | None, after: int, limit: int) -> dict[str, Any]:
    """그림 기억이 있는 주문(= 마법사에서 그림을 다룬 주문)의 시트들. 주문 번호 순, ``after`` 다음부터."""
    q = db.query(DrawingPartMemory.order_id).filter(DrawingPartMemory.order_id > after)
    if since is not None:
        q = q.filter(DrawingPartMemory.updated_at >= since)
    order_ids = [oid for (oid,) in q.distinct().order_by(DrawingPartMemory.order_id.asc()).limit(limit + 1).all()]
    more = len(order_ids) > limit
    order_ids = order_ids[:limit]
    items: list[dict[str, Any]] = []
    if order_ids:
        rows = (db.query(Order.id, Order.structured_data, Order.product)
                .filter(Order.id.in_(order_ids)).order_by(Order.id).all())
        for oid, sd, product in rows:
            wizard = sd.get('drawing_wizard') if isinstance(sd, dict) else None
            sheets = wizard.get('sheets') if isinstance(wizard, dict) else None
            goods = sd.get('items') if isinstance(sd, dict) and isinstance(sd.get('items'), list) else []
            for index, sheet in enumerate(sheets if isinstance(sheets, list) else []):
                if isinstance(sheet, dict):
                    family = family_of(_sheet_product_text(sheet, goods, product))
                    items.append(sheet_digest(int(oid), index, sheet, family))
    return {'items': items, 'next': order_ids[-1] if more and order_ids else None}


def summary(db) -> dict[str, Any]:
    """한눈 수치 — 기억 줄 수 · 사람 이름표 수 · AI 와 다르게 고른 수 · 종류별 사람 이름표."""
    rows = db.query(DrawingPartMemory.label, DrawingPartMemory.ai, DrawingPartMemory.src,
                    DrawingPartMemory.active, DrawingPartMemory.feat_v).all()
    user_rows = [r for r in rows if r.src == 'user' and r.active]
    by_label: dict[str, int] = {}
    for r in user_rows:
        by_label[r.label] = by_label.get(r.label, 0) + 1
    versions: dict[str, int] = {}
    for r in rows:
        versions[r.feat_v or '-'] = versions.get(r.feat_v or '-', 0) + 1
    return {
        'memory': {
            'total': len(rows), 'user': len(user_rows), 'ai': sum(1 for r in rows if r.src == 'ai'),
            'user_changed_ai': sum(1 for r in user_rows if r.ai and r.ai != r.label),
            'user_by_label': dict(sorted(by_label.items())), 'feat_versions': dict(sorted(versions.items())),
        },
    }


def _note_side(side: dict[str, Any]) -> dict[str, Any]:
    return {'mem': side.get('mem'), 'order': side.get('order'), 'key': key_hash(side.get('key')), 'label': side.get('label')}


def notes_digest(db, secret: str) -> dict[str, Any]:
    """주간 노트 · 도면팀 답 — 그림 key 는 지문, 답한 사람은 익명 번호(이름은 빼고)."""
    items = []
    for note in load_book(db)['notes']:
        questions = []
        for q in note.get('questions') or []:
            ans = q.get('answer') if isinstance(q.get('answer'), dict) else None
            questions.append({
                'id': q.get('id'), 'sim': q.get('sim'), 'a': _note_side(q.get('a') or {}), 'b': _note_side(q.get('b') or {}),
                'answer': {'choice': ans.get('choice'), 'by': anon_id(ans.get('by'), secret), 'at': ans.get('at')} if ans else None,
            })
        items.append({key: note.get(key) for key in ('id', 'title', 'created_at', 'window', 'stats', 'review', 'changes')}
                     | {'questions': questions})
    return {'items': items}

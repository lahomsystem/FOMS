"""도면 마법사 그림 종류 — 다시 가르칠 자료 모으기(DB 읽기 전용 + 저장소 GetObject 만).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.5 · §3.7

- 정답 무게: 사람이 고르거나 고친 이름표(``src: user``) 1, 사람이 손대지 않고 전달한 AI 이름표 0.5.
  '전달'은 버전 스냅샷(``drawing_wizard.versions`` — 전달할 때의 시트 모습)에 AI 이름표로 들어 있는 것이다.
- '미분류'·닫힌 목록 밖 이름표·이름표 없는 그림·전달하지 않은 AI 이름표는 쓰지 않는다.
- 같은 그림(key)이 여러 번 나오면 사람 이름표가 이기고, 무게가 같으면 가장 늦은 것(현재 시트가 스냅샷보다 늦다).
- DB 에서는 주문의 ``drawing_wizard``·제품 이름(``items``·``product``)만 읽는다. 고객 정보 칸은 읽지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
from pathlib import Path
from typing import Iterable, Optional

LABELS = ('정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진', '그림 아님')
UNSURE = '미분류'
USER_WEIGHT = 1.0
CONFIRMED_WEIGHT = 0.5
#: 이름표(part)가 처음 생긴 날 — 그 전 버전 스냅샷에는 이름표가 없어 읽지 않는다.
DEFAULT_SINCE = '2026-10-22'

_SQL = (
    "SELECT id, structured_data->'drawing_wizard', structured_data->'items', product "
    "FROM orders WHERE structured_data ? 'drawing_wizard' ORDER BY id"
)


def family_of(text: str) -> str:
    """제품 이름 → 제품 종류(학습 때와 같은 규칙: 냉장고장 · 주방 · 붙박이장 · 그 밖 장)."""
    p = text or ''
    if re.search(r'냉장고', p):
        return '냉장고장'
    if re.search(r'부엌|주방|싱크|아일랜드|하부장|상부장|홈카페|홈바', p):
        return '주방'
    if re.search(r'붙박이|여닫이|슬라이딩|월플렉스|드레스', p):
        return '붙박이장'
    return '그 밖 장'


def sheet_product_text(sheet: dict, items: list, order_product: Optional[str]) -> str:
    """시트의 제품 이름 + 시트 이름 + 주문 제품 칸(제품 종류 판정용)."""
    words = []
    idx = sheet.get('product_index')
    if isinstance(idx, int) and not isinstance(idx, bool) and 0 <= idx < len(items or []):
        item = items[idx] if isinstance(items[idx], dict) else {}
        words.append(str(item.get('product_name') or item.get('name') or ''))
    words.append(str(sheet.get('name') or ''))
    words.append(str(order_product or ''))
    return ' '.join(w for w in words if w)


def _image_parts(sheet: dict) -> Iterable[tuple[dict, dict]]:
    for obj in sheet.get('objects') or []:
        if isinstance(obj, dict) and obj.get('type') == 'image' and isinstance(obj.get('key'), str):
            part = obj.get('part')
            if isinstance(part, dict):
                yield obj, part


def _record(order_id: int, sheet: dict, obj: dict, part: dict, family: str, delivered: bool) -> Optional[dict]:
    label, src = part.get('label'), part.get('src')
    if label not in LABELS:
        return None
    if src == 'user':
        weight = USER_WEIGHT
    elif src == 'ai' and delivered:
        weight = CONFIRMED_WEIGHT
    else:
        return None
    ai = part.get('ai') if part.get('ai') in LABELS else None
    return {
        'key': obj['key'], 'label': label, 'weight': weight, 'src': src, 'ai': ai,
        'conf': part.get('conf'), 'head': part.get('head'), 'order_id': order_id,
        'sheet_id': sheet.get('id'), 'family': family, 'delivered': delivered,
        'corrected': bool(src == 'user' and ai and ai != label),
    }


def records_for_order(order_id: int, dw: dict, items: list, order_product: Optional[str],
                      snapshots: list[dict]) -> list[dict]:
    """한 주문의 전달 스냅샷(오래된 것부터) + 현재 시트 → 그림별 정답 기록."""
    best: dict[str, dict] = {}

    def consider(sheet: dict, delivered: bool) -> None:
        family = family_of(sheet_product_text(sheet, items, order_product))
        for obj, part in _image_parts(sheet):
            rec = _record(order_id, sheet, obj, part, family, delivered)
            if rec is None:
                continue
            prev = best.get(rec['key'])
            if prev is None or rec['weight'] >= prev['weight']:
                best[rec['key']] = rec

    for snap in snapshots:
        if isinstance(snap, dict):
            consider(snap, True)
    for sheet in (dw or {}).get('sheets') or []:
        if isinstance(sheet, dict):
            consider(sheet, False)
    return list(best.values())


def snapshot_pointers(dw: dict, since: str = DEFAULT_SINCE) -> list[dict]:
    """``since`` 날짜 뒤의 버전 포인터(번호 순). 포인터의 ``at`` 은 'YYYY-MM-DD HH:MM'(KST)."""
    out = []
    for ptr in (dw or {}).get('versions') or []:
        if isinstance(ptr, dict) and isinstance(ptr.get('key'), str) and str(ptr.get('at') or '') >= since:
            out.append(ptr)
    return sorted(out, key=lambda p: p.get('v') or 0)


def summarize(records: list[dict]) -> dict:
    """정답 수(이름표·출처·제품 종류별), 고친 기록 수, 헷갈림(AI 짐작 → 사람 정답) 표."""
    def count(field: str) -> dict:
        out: dict = {}
        for r in records:
            out[str(r[field])] = out.get(str(r[field]), 0) + 1
        return dict(sorted(out.items(), key=lambda kv: -kv[1]))

    pairs: dict = {}
    for r in records:
        if r['corrected']:
            pairs[(r['ai'], r['label'])] = pairs.get((r['ai'], r['label']), 0) + 1
    confusion = [{'ai': a, 'label': b, 'n': n} for (a, b), n in sorted(pairs.items(), key=lambda kv: -kv[1])]
    return {
        'records': len(records), 'corrections': sum(1 for r in records if r['corrected']),
        'human': sum(1 for r in records if r['src'] == 'user'),
        'confirmed': sum(1 for r in records if r['src'] == 'ai'),
        'orders': len({r['order_id'] for r in records}),
        'per_label': count('label'), 'per_family': count('family'), 'confusion': confusion,
    }


class LocalStore:
    """로컬 개발 저장소(UPLOAD_FOLDER) — key 를 그 폴더 아래 경로로 읽는다."""

    def __init__(self, base: str) -> None:
        self.base = Path(base)

    def get(self, key: str) -> Optional[bytes]:
        path = (self.base / key).resolve()
        if self.base.resolve() not in path.parents or not path.is_file():
            return None
        return path.read_bytes()


class R2Store:
    """Cloudflare R2(S3 호환) — GetObject 만 쓴다. 자격은 환경 변수(R2_*)에서 읽는다."""

    def __init__(self) -> None:
        import boto3  # FOMS 환경에 있다(도구용 가상환경에서는 collect 를 돌리지 않는다)
        endpoint = os.environ.get('R2_ENDPOINT') or f"https://{os.environ['R2_ACCOUNT_ID']}.r2.cloudflarestorage.com"
        self.bucket = os.environ['R2_BUCKET_NAME']
        self.client = boto3.client(
            's3', endpoint_url=endpoint, region_name='auto',
            aws_access_key_id=os.environ['R2_ACCESS_KEY_ID'],
            aws_secret_access_key=os.environ['R2_SECRET_ACCESS_KEY'],
        )

    def get(self, key: str) -> Optional[bytes]:
        try:
            return self.client.get_object(Bucket=self.bucket, Key=key)['Body'].read()
        except Exception:  # 없는 그림·권한 — 그 그림만 빼고 계속(개수는 summary.missing)
            return None


def _load_snapshots(store, dw: dict, since: str) -> list[dict]:
    snaps = []
    for ptr in snapshot_pointers(dw, since):
        raw = store.get(ptr['key'])
        try:
            sheet = json.loads(raw.decode('utf-8')) if raw else None
        except (UnicodeDecodeError, json.JSONDecodeError):
            sheet = None
        if isinstance(sheet, dict):
            snaps.append(sheet)
    return snaps


def image_filename(key: str) -> str:
    ext = os.path.splitext(key)[1].lower() or '.png'
    return hashlib.sha1(key.encode('utf-8')).hexdigest()[:20] + ext


def collect(conn, store, out_dir: Path, since: str = DEFAULT_SINCE, download: bool = True) -> dict:
    """DB(읽기 전용 접속) + 저장소 → ``manifest.jsonl``·``summary.json``·(download 면) ``imgs/``."""
    out_dir.mkdir(parents=True, exist_ok=True)
    records: list[dict] = []
    with conn.cursor() as cur:
        cur.execute(_SQL)
        for order_id, dw, items, product in cur:
            if not isinstance(dw, dict):
                continue
            snaps = _load_snapshots(store, dw, since)
            records += records_for_order(order_id, dw, items if isinstance(items, list) else [], product, snaps)
    missing = 0
    if download:
        imgs = out_dir / 'imgs'
        imgs.mkdir(exist_ok=True)
        kept = []
        for rec in records:
            data = store.get(rec['key'])
            if not data:
                missing += 1
                continue
            rec['file'] = image_filename(rec['key'])
            (imgs / rec['file']).write_bytes(data)
            kept.append(rec)
        records = kept
    with (out_dir / 'manifest.jsonl').open('w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    summary = dict(summarize(records), missing=missing, since=since)
    (out_dir / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    return summary


def read_manifest(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]

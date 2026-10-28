"""AI 도면팀원 학습 요약 받기 · 다시 가르치기 입력 만들기 — 원격 연구 루틴(Claude)이 매주 쓰는 도구.

설계 정본: docs/plans/2026-10-27-drawing-ai-teammate-spec.md §2 B1 · §3 · §8
루틴 순서 정본: docs/research/drawing-agent/AGENT.md

받기:
  FOMS_DRAWING_AGENT_TOKEN=<토큰> python tools/drawing_ai/fetch_digest.py fetch --out <폴더> \\
      [--base https://lahom-production.up.railway.app] [--since 2026-10-01]
다시 가르치기 입력(tools/drawing_ai/retrain_head.py train 이 읽는 꼴):
  python tools/drawing_ai/fetch_digest.py to-retrain --digest <받은 폴더> --out <폴더>

- 토큰은 환경 변수 FOMS_DRAWING_AGENT_TOKEN 으로만 받는다 — 명령줄 · 출력 · 파일에 남기지 않는다.
- 받은 것: summary.json · memory.jsonl · sheets.jsonl · notes.json. 고객 정보는 서버가 이미 뺐다(그림 key 도 지문).
- 다시 가르치기 입력은 사람이 고른 이름표(src=user)만 쓴다(무게 1). 특징은 브라우저가 낸 것 그대로라
  지금 판(part-head.json)과 같은 공간이다. 그림은 내려받지 않는다.
- 종료 코드: 0 됨 · 2 길이 꺼짐(404) · 3 토큰 거절(401) · 4 그 밖 실패.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from collections import Counter
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DEFAULT_BASE = 'https://lahom-production.up.railway.app'
TOKEN_ENV = 'FOMS_DRAWING_AGENT_TOKEN'
LABELS = ('정면·내부', '정면·도어', '입체·내부', '입체·도어', '평면·상판', '서랍 단면', '부품 상세', '사진', '그림 아님', '탑뷰', '사이드뷰', '미분류')
FEAT_DIM = 768
EXIT = {404: 2, 401: 3}


class DigestError(RuntimeError):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


def _open(url: str, token: str) -> dict:
    req = Request(url, headers={'Authorization': f'Bearer {token}', 'Accept': 'application/json',
                                'User-Agent': 'foms-drawing-agent/1'})
    try:
        with urlopen(req, timeout=60) as resp:   # noqa: S310 — 주소는 고정 기본값이거나 --base 로 준 FOMS 주소
            return json.loads(resp.read().decode('utf-8'))
    except HTTPError as err:
        raise DigestError(err.code, f'HTTP {err.code}') from None
    except URLError as err:
        raise DigestError(0, f'연결 실패: {err.reason}') from None


def get(base: str, token: str, **params) -> dict:
    query = urlencode({k: v for k, v in params.items() if v not in (None, '')})
    body = _open(f"{base.rstrip('/')}/api/drawing-agent/digest?{query}", token)
    if not body.get('success'):
        raise DigestError(0, str(body.get('error') or 'success=false'))
    return body['data']


def pages(base: str, token: str, kind: str, since: str | None):
    after = 0
    while True:
        data = get(base, token, kind=kind, since=since, after=after)
        yield from data.get('items') or []
        if not data.get('next'):
            return
        after = data['next']


def fetch(base: str, token: str, out: Path, since: str | None = None) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    summary = get(base, token, kind='summary')
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf-8')
    counts = {}
    for kind in ('memory', 'sheets'):
        n = 0
        with (out / f'{kind}.jsonl').open('w', encoding='utf-8') as fh:
            for item in pages(base, token, kind, since):
                fh.write(json.dumps(item, ensure_ascii=False) + '\n')
                n += 1
        counts[kind] = n
    notes = get(base, token, kind='notes')
    (out / 'notes.json').write_text(json.dumps(notes, ensure_ascii=False, indent=1), encoding='utf-8')
    counts['notes'] = len(notes.get('items') or [])
    return counts


def _jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def to_retrain(digest: Path, out: Path) -> dict:
    """받은 요약 → features.npy · feature_keys.json · manifest.jsonl(retrain_head.py train 입력)."""
    import numpy as np

    families = {}
    for sheet in _jsonl(digest / 'sheets.jsonl'):
        for img in sheet.get('images') or []:
            if img.get('key'):
                families[img['key']] = sheet.get('family') or '그 밖 장'
    rows = [r for r in _jsonl(digest / 'memory.jsonl')
            if r.get('src') == 'user' and r.get('active') and r.get('feat') and r.get('label') in LABELS]
    version = Counter(r.get('fv') for r in rows).most_common(1)[0][0] if rows else None
    feats, keys, records = [], [], []
    for r in rows:
        if r.get('fv') != version:
            continue
        vec = np.frombuffer(base64.b64decode(r['feat']), dtype='<f2').astype(np.float32)
        norm = float(np.linalg.norm(vec))
        if vec.shape != (FEAT_DIM,) or not norm:
            continue
        key = f"{r['order']}:{r['key']}"
        feats.append(vec / norm)
        keys.append(key)
        ai = r.get('ai') if r.get('ai') in LABELS else None
        records.append({'key': key, 'label': r['label'], 'weight': 1.0, 'src': 'user', 'ai': ai, 'conf': r.get('conf'),
                        'head': r.get('head'), 'order_id': r['order'], 'sheet_id': None,
                        'family': families.get(r['key'], '그 밖 장'), 'delivered': False,
                        'corrected': bool(ai and ai != r['label'])})
    out.mkdir(parents=True, exist_ok=True)
    np.save(out / 'features.npy', np.stack(feats) if feats else np.zeros((0, FEAT_DIM), np.float32))
    (out / 'feature_keys.json').write_text(json.dumps(keys, ensure_ascii=False), encoding='utf-8')
    with (out / 'manifest.jsonl').open('w', encoding='utf-8') as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + '\n')
    return {'rows': len(records), 'feat_version': version, 'corrections': sum(r['corrected'] for r in records)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='AI 도면팀원 학습 요약 받기 · 다시 가르치기 입력')
    sub = parser.add_subparsers(dest='cmd', required=True)
    f = sub.add_parser('fetch')
    f.add_argument('--out', required=True)
    f.add_argument('--base', default=os.environ.get('FOMS_DRAWING_AGENT_BASE') or DEFAULT_BASE)
    f.add_argument('--since')
    r = sub.add_parser('to-retrain')
    r.add_argument('--digest', required=True)
    r.add_argument('--out', required=True)
    args = parser.parse_args(argv)
    if args.cmd == 'to-retrain':
        print(json.dumps(to_retrain(Path(args.digest), Path(args.out)), ensure_ascii=False))
        return 0
    token = (os.environ.get(TOKEN_ENV) or '').strip()
    if not token:
        print(f'{TOKEN_ENV} 환경 변수가 없습니다.', file=sys.stderr)
        return 3
    try:
        counts = fetch(args.base, token, Path(args.out), args.since)
    except DigestError as err:
        print(f'학습 요약을 받지 못했습니다 — {err}', file=sys.stderr)
        return EXIT.get(err.status, 4)
    print(json.dumps(counts, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())

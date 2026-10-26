"""도면 마법사 그림 종류 분류기 다시 가르치기 — 명령 모음(collect · embed · train).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.5 · §3.7 · 사용법 tools/drawing_ai/README.md

운영 읽기는 돌릴 때마다 사용자 허락을 받는다(DB 는 읽기 전용 접속, 저장소는 GetObject 만).

  1) collect (FOMS 파이썬)     RETRAIN_DB_URL=… R2_*=… python tools/drawing_ai/retrain_head.py collect --out <폴더>
  2) embed   (도구용 가상환경)  <venv 파이썬> tools/drawing_ai/retrain_head.py embed --data <폴더>
  3) train   (어느 쪽이든)      python tools/drawing_ai/retrain_head.py train --data <폴더> [--out <새 판.json>]

<폴더> 는 저장소 밖에 두고 다 쓰면 지운다(그림은 embed 가 특징을 뽑은 뒤 바로 지운다).
종료 코드: 0 통과(또는 단계 끝) · 2 입력 부족(고친 기록 100건 미만 등) · 3 판정 불통과.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import numpy as np

if __package__ in (None, ''):   # python tools/drawing_ai/retrain_head.py 로 바로 부를 때
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tools.drawing_ai import retrain_data as rd  # noqa: E402
from tools.drawing_ai import retrain_model as rm  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HEAD = ROOT / 'static' / 'js' / 'drawing' / 'part-head.json'


def _say(msg: str) -> None:
    """Windows cp949 콘솔에서도 한글이 깨지지 않게 UTF-8 바이트로 쓴다(계약 PS-ENC-01)."""
    buf = getattr(sys.stdout, 'buffer', None)
    if buf is None:
        print(msg)
        return
    buf.write((msg + '\n').encode('utf-8'))
    sys.stdout.flush()


def cmd_collect(args) -> int:
    url = os.environ.get('RETRAIN_DB_URL')
    if not url:
        _say('[collect] RETRAIN_DB_URL 환경 변수가 필요합니다(명령줄에 비밀번호를 쓰지 않게).')
        return 2
    import psycopg
    host = psycopg.conninfo.conninfo_to_dict(url).get('host', '?')
    if args.expect_host and host != args.expect_host:
        _say(f'[collect] DB 주소 {host} 가 --expect-host 와 다릅니다 — 멈춥니다.')
        return 2
    store = rd.LocalStore(args.local_storage) if args.local_storage else rd.R2Store()
    with psycopg.connect(url, connect_timeout=10) as conn:
        conn.read_only = True   # 접속 자체를 읽기 전용으로 — 실수로도 쓰지 못한다
        s = rd.collect(conn, store, Path(args.out), since=args.since, download=not args.no_download)
    _say(f"[collect] DB {host} · 정답 {s['records']}장(사람 {s['human']} · 전달 확인 {s['confirmed']}) · "
         f"고친 기록 {s['corrections']} · 주문 {s['orders']} · 못 받은 그림 {s['missing']}")
    return 0


def cmd_embed(args) -> int:
    from tools.drawing_ai import part_embed as pe
    data = Path(args.data)
    recs = [r for r in rd.read_manifest(data / 'manifest.jsonl') if r.get('file')]
    head = json.loads(Path(args.head).read_text(encoding='utf-8'))
    if args.model:
        model = Path(args.model)
        if pe.sha256_of(model) != head['model']['sha256']:
            _say('[embed] 모델 파일 sha256 이 part-head.json 과 다릅니다 — 멈춥니다.')
            return 2
    else:
        model = pe.ensure_model(head['model']['url'], head['model']['sha256'], Path(args.model_cache))
    feats = pe.embed_files([data / 'imgs' / r['file'] for r in recs], model)
    np.save(data / 'features.npy', feats.astype(np.float32))
    (data / 'feature_keys.json').write_text(json.dumps([r['key'] for r in recs], ensure_ascii=False), encoding='utf-8')
    if not args.keep_images:
        shutil.rmtree(data / 'imgs', ignore_errors=True)
    bad = int((np.linalg.norm(feats, axis=1) == 0).sum()) if len(feats) else 0
    _say(f"[embed] 특징 {len(feats)}장(읽지 못한 그림 {bad}) · 그림 폴더 {'남김' if args.keep_images else '지움'}")
    return 0


def load_dataset(data: Path, labels: list[str]) -> tuple[np.ndarray, list[dict]]:
    """특징과 정답 기록을 key 로 맞춘다(닫힌 목록 밖 이름표·0 벡터는 뺀다)."""
    recs = {r['key']: r for r in rd.read_manifest(data / 'manifest.jsonl')}
    keys = json.loads((data / 'feature_keys.json').read_text(encoding='utf-8'))
    feats = np.load(data / 'features.npy').astype(np.float64)
    idx = [i for i, k in enumerate(keys) if k in recs and recs[k]['label'] in labels and np.linalg.norm(feats[i]) > 0]
    return feats[idx], [recs[keys[i]] for i in idx]


def render_md(rep: dict) -> str:
    cur, cand = rep['test']['current'], rep['test']['candidate']
    lines = [f"# 그림 종류 분류기 다시 가르치기 — 지금 판 {rep['base']}", '',
             f"- 가르친 그림 {rep['train']['n']}장(사람 {rep['train']['human']} · 전달 확인 {rep['train']['confirmed']}), "
             f"고친 기록 {rep['train']['corrections']}건, 벌점 세기 λ={rep['lambda']}",
             f"- 시험 묶음(주문 20% · 사람 확인) {cand['n']}장", '',
             '| | 지금 판 | 새 판 |', '|---|---|---|',
             f"| 전체 | {cur['acc']:.1%} | {cand['acc']:.1%} |"]
    for fam, c in cand['per_family'].items():
        lines.append(f"| {fam}({c['n']}장) | {cur['per_family'].get(fam, {}).get('acc', 0):.1%} | {c['acc']:.1%} |")
    lines += ['', f"**판정: {'통과' if rep['verdict']['ok'] else '바꾸지 않음'}**"]
    lines += [f'- {r}' for r in rep['verdict']['reasons']]
    lines += ['', '## 헷갈림 표 — 사람이 고친 것(AI 짐작 → 사람 정답)']
    lines += [f"- {c['ai']} → {c['label']}: {c['n']}" for c in rep['corrections_confusion']] or ['- 없음']
    lines += ['', '## 새 판이 시험 묶음에서 틀린 것(정답 → 짐작)']
    lines += [f"- {c['label']} → {c['pred']}: {c['n']}" for c in rep['test_errors_candidate']] or ['- 없음']
    if rep.get('written'):
        lines += ['', f"새 판 {rep['new_version']} 파일: {rep['written']} — 저장소 part-head.json 바꾸기는 보통 코드 변경으로 합니다."]
    return '\n'.join(lines) + '\n'


def cmd_train(args) -> int:
    data = Path(args.data)
    head = json.loads(Path(args.head).read_text(encoding='utf-8'))
    labels = list(head['labels'])
    X, meta = load_dataset(data, labels)
    corrections = sum(1 for r in meta if r['corrected'])
    if corrections < args.min_corrections:
        _say(f'[train] 고친 기록 {corrections}건 — {args.min_corrections}건 이상일 때 가르칩니다.')
        return 2
    W0, b0 = np.array(head['W'], float), np.array(head['b'], float)
    if X.shape[1] != W0.shape[1]:
        _say(f'[train] 특징 차원 {X.shape[1]} 이 지금 판 {W0.shape[1]} 과 다릅니다 — 멈춥니다.')
        return 2
    y = np.array([labels.index(r['label']) for r in meta], dtype=int)
    w = np.array([r['weight'] for r in meta], float)
    orders = np.array([r['order_id'] for r in meta])
    fams = np.array([r['family'] for r in meta])
    human = np.array([r['src'] == 'user' for r in meta])
    hold = np.array([rm.in_holdout(o) for o in orders.tolist()], dtype=bool)
    tr, te = ~hold, hold & human
    lam, scores = rm.choose_lambda(X[tr], y[tr], w[tr], orders[tr].tolist(), W0, b0)
    W, b = rm.fit(X[tr], y[tr], rm.balanced_weights(y[tr], w[tr]), W0, b0, lam) if tr.any() else (W0, b0)
    th = float(head.get('threshold', 0.5))
    P0, P1 = rm.predict_proba(W0, b0, X[te]), rm.predict_proba(W, b, X[te])
    cur, cand = rm.evaluate(P0, y[te], fams[te], th), rm.evaluate(P1, y[te], fams[te], th)
    verdict = rm.judge(cur, cand, args.min_test, args.min_family, args.kitchen_gain)
    train_meta = [m for m, t in zip(meta, tr) if t]
    rep = {
        'base': head.get('version'), 'lambda': lam, 'lambda_scores': {str(k): v for k, v in scores.items()},
        'train': {'n': int(tr.sum()), 'human': sum(r['src'] == 'user' for r in train_meta),
                  'confirmed': sum(r['src'] == 'ai' for r in train_meta), 'corrections': corrections},
        'test': {'current': cur, 'candidate': cand}, 'verdict': verdict,
        'corrections_confusion': rd.summarize(meta)['confusion'],
        'test_errors_candidate': rm.confusion(y[te], P1.argmax(axis=1), labels),
    }
    if verdict['ok'] and args.out:
        per_label = {lab: int((y[tr] == i).sum()) for i, lab in enumerate(labels)}
        trained_on = {'n': int(tr.sum()), 'per_label': per_label, 'from': head.get('version'),
                      'from_n': (head.get('trained_on') or {}).get('n'), 'lambda': lam,
                      'human': rep['train']['human'], 'confirmed': rep['train']['confirmed']}
        new_head = rm.export_head(W, b, head, trained_on)
        Path(args.out).write_text(json.dumps(new_head, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
        rep.update(written=str(args.out), new_version=new_head['version'])
    (data / 'report.json').write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding='utf-8')
    (data / 'report.md').write_text(render_md(rep), encoding='utf-8')
    _say(f"[train] 시험 {cand['n']}장 · 지금 판 {cur['acc']:.1%} → 새 판 {cand['acc']:.1%} · "
         f"판정 {'통과' if verdict['ok'] else '바꾸지 않음'} · 보고서 {data / 'report.md'}")
    return 0 if verdict['ok'] else 3


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description='도면 마법사 그림 종류 분류기 다시 가르치기')
    sub = ap.add_subparsers(dest='cmd', required=True)
    c = sub.add_parser('collect', help='DB(읽기 전용)·저장소에서 정답 기록과 그림 모으기')
    c.add_argument('--out', required=True)
    c.add_argument('--since', default=rd.DEFAULT_SINCE, help='이 날짜 뒤 버전 스냅샷만(기본 이름표가 생긴 날)')
    c.add_argument('--local-storage', help='로컬 개발 저장소 폴더(없으면 R2_* 환경 변수로 R2)')
    c.add_argument('--expect-host', help='DB 주소가 이것과 다르면 멈춤')
    c.add_argument('--no-download', action='store_true', help='그림은 받지 않고 기록만')
    e = sub.add_parser('embed', help='그림 → 특징(onnxruntime, 도구용 가상환경)')
    e.add_argument('--data', required=True)
    e.add_argument('--head', default=str(DEFAULT_HEAD))
    e.add_argument('--model', help='이미 받은 model_quantized.onnx(sha256 을 맞춰 봄)')
    e.add_argument('--model-cache', default=str(Path.home() / '.cache' / 'foms-part-ai'))
    e.add_argument('--keep-images', action='store_true')
    t = sub.add_parser('train', help='지금 판에서 출발해 다시 가르치고 판정')
    t.add_argument('--data', required=True)
    t.add_argument('--head', default=str(DEFAULT_HEAD))
    t.add_argument('--out', help='판정 통과 때 새 판을 쓸 파일')
    t.add_argument('--min-corrections', type=int, default=100)
    t.add_argument('--min-test', type=int, default=30)
    t.add_argument('--min-family', type=int, default=10)
    t.add_argument('--kitchen-gain', type=float, default=0.01)
    return ap


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    return {'collect': cmd_collect, 'embed': cmd_embed, 'train': cmd_train}[args.cmd](args)


if __name__ == '__main__':
    sys.exit(main())

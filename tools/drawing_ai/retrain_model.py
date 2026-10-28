"""도면 마법사 그림 종류 분류기 — 다시 가르치기·판정(numpy 만).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.5 · §3.7

- 지금 판(W0, b0)에서 출발해, 멀어질수록 벌점(λ/2·‖W−W0‖²+‖b−b0‖²)을 주며 가중 교차 엔트로피를 줄인다.
  1단계 학습 자료(운영 그림)는 지웠으므로 지금 판의 가중치가 지난 학습의 기억이다.
- 무게는 정답 무게(사람 1 · 전달 확인 0.5)에 이름표별 균형(h1 의 class_weight=balanced 와 같은 뜻)을 곱한다.
- 벌점 세기 λ 는 가르치는 자료 안에서 주문 단위 5조각으로 나눠 맞혀 보며(가중 로그 손실) 고른다.
- 고정 시험 묶음: 주문 번호 해시로 정한 20% 주문의 사람 확인 그림. 그 주문의 그림은 가르치는 데 쓰지 않는다.
- 판정: 시험 30장↑ · 전체와 제품별(10장↑) 정확도가 지금 판 이상 · 주방 +1%p.
"""
from __future__ import annotations

import hashlib
from typing import Optional

import numpy as np

LAMBDAS = (0.3, 0.1, 0.03, 0.01, 0.003, 0.001)
DEFAULT_LAMBDA = 0.03
HOLDOUT_SHARE = 0.2
KITCHEN = '주방'


def in_holdout(order_id, share: float = HOLDOUT_SHARE) -> bool:
    """주문 번호만으로 정해지는 고정 시험 묶음(같은 주문은 늘 같은 쪽)."""
    h = int(hashlib.sha1(f'foms-part-holdout:{order_id}'.encode()).hexdigest()[:8], 16)
    return (h % 1000) < int(share * 1000)


def softmax(z: np.ndarray) -> np.ndarray:
    z = z - z.max(axis=1, keepdims=True)
    e = np.exp(z)
    return e / e.sum(axis=1, keepdims=True)


def predict_proba(W: np.ndarray, b: np.ndarray, X: np.ndarray) -> np.ndarray:
    return softmax(X @ W.T + b)


def balanced_weights(y: np.ndarray, w: np.ndarray) -> np.ndarray:
    """정답 무게 × 이름표별 균형(있는 이름표마다 무게 합이 같아지게)."""
    out = w.astype(float).copy()
    present = [c for c in np.unique(y) if w[y == c].sum() > 0]
    total = w.sum()
    for c in present:
        out[y == c] *= total / (len(present) * w[y == c].sum())
    return out


def fit(X: np.ndarray, y: np.ndarray, w: np.ndarray, W0: np.ndarray, b0: np.ndarray,
        lam: float, iters: int = 400) -> tuple[np.ndarray, np.ndarray]:
    """가속 경사 하강(Nesterov, 걸음 1/L) — 목적식이 볼록이라 늘 같은 답으로 간다."""
    k = W0.shape[0]
    Y = np.eye(k)[y]
    ws = w / w.sum()
    step = 1.0 / (0.5 * float((X * X).sum(axis=1).max()) + 0.5 + lam)
    W, b = W0.copy(), b0.copy()
    Wp, bp = W.copy(), b.copy()
    for t in range(1, iters + 1):
        mom = (t - 1) / (t + 2)
        Wv, bv = W + mom * (W - Wp), b + mom * (b - bp)
        G = (predict_proba(Wv, bv, X) - Y) * ws[:, None]
        Wp, bp = W, b
        W = Wv - step * (G.T @ X + lam * (Wv - W0))
        b = bv - step * (G.sum(axis=0) + lam * (bv - b0))
    return W, b


def weighted_log_loss(P: np.ndarray, y: np.ndarray, w: np.ndarray) -> float:
    p = np.clip(P[np.arange(len(y)), y], 1e-9, 1.0)
    return float((w * -np.log(p)).sum() / w.sum())


def choose_lambda(X, y, w, groups, W0, b0, folds: int = 5, iters: int = 200) -> tuple[float, dict]:
    """주문 단위 조각으로 나눠 λ 마다 맞혀 보고 가중 로그 손실이 가장 작은 λ. 주문이 적으면 기본값."""
    uniq = sorted(set(groups))
    if len(uniq) < folds:
        return DEFAULT_LAMBDA, {}
    fold_of = {g: int(hashlib.sha1(f'foms-part-fold:{g}'.encode()).hexdigest()[:8], 16) % folds for g in uniq}
    fid = np.array([fold_of[g] for g in groups])
    scores = {}
    for lam in LAMBDAS:
        losses = []
        for f in range(folds):
            tr, va = fid != f, fid == f
            if not va.any() or not tr.any():
                continue
            W, b = fit(X[tr], y[tr], balanced_weights(y[tr], w[tr]), W0, b0, lam, iters)
            losses.append(weighted_log_loss(predict_proba(W, b, X[va]), y[va], w[va]))
        scores[lam] = float(np.mean(losses)) if losses else float('inf')
    return min(scores, key=scores.get), scores


def evaluate(P: np.ndarray, y: np.ndarray, families: np.ndarray, threshold: float) -> dict:
    pred, conf = P.argmax(axis=1), P.max(axis=1)
    ok = pred == y
    auto = conf >= threshold
    per_family = {}
    for fam in sorted(set(families.tolist())):
        m = families == fam
        per_family[fam] = {'n': int(m.sum()), 'acc': round(float(ok[m].mean()), 4)}
    return {
        'n': int(len(y)), 'acc': round(float(ok.mean()), 4) if len(y) else 0.0,
        'auto_share': round(float(auto.mean()), 4) if len(y) else 0.0,
        'auto_acc': round(float(ok[auto].mean()), 4) if auto.any() else None,
        'per_family': per_family,
    }


def judge(cur: dict, cand: dict, min_n: int = 30, min_family: int = 10, kitchen_gain: float = 0.01) -> dict:
    """판 바꾸기 판정 — 하나라도 어기면 바꾸지 않는다(이유를 모두 적는다)."""
    if cand['n'] < min_n:
        return {'ok': False, 'reasons': [f"시험 그림 {cand['n']}장 — {min_n}장 이상이어야 판정합니다"]}
    reasons, ok = [], True
    if cand['acc'] + 1e-9 < cur['acc']:
        ok = False
        reasons.append(f"전체 정확도가 {cur['acc']:.1%} → {cand['acc']:.1%} 로 내려감")
    for fam, c in cand['per_family'].items():
        before = cur['per_family'].get(fam, {}).get('acc', 0.0)
        if c['n'] < min_family:
            reasons.append(f"{fam} 시험 {c['n']}장 — {min_family}장 미만이라 판정 생략")
            continue
        need = before + (kitchen_gain if fam == KITCHEN else 0.0)
        if c['acc'] + 1e-9 < need:
            ok = False
            reasons.append(f"{fam} {before:.1%} → {c['acc']:.1%}" + (f"(주방은 +{kitchen_gain:.0%}p 필요)" if fam == KITCHEN else ' 내려감'))
    if cand['per_family'].get(KITCHEN, {}).get('n', 0) < min_family:
        ok = False
        reasons.append(f"주방 시험 그림이 {min_family}장 미만 — 주방 +{kitchen_gain:.0%}p 를 확인할 수 없음")
    return {'ok': ok, 'reasons': reasons}


def confusion(y_true: np.ndarray, y_pred: np.ndarray, labels: list[str]) -> list[dict]:
    """틀린 것만(정답 → 짐작) 많은 순."""
    pairs: dict = {}
    for t, p in zip(y_true.tolist(), y_pred.tolist()):
        if t != p:
            pairs[(t, p)] = pairs.get((t, p), 0) + 1
    return [{'label': labels[t], 'pred': labels[p], 'n': n} for (t, p), n in sorted(pairs.items(), key=lambda kv: -kv[1])]


def next_version(version: str) -> str:
    digits = ''.join(ch for ch in str(version) if ch.isdigit())
    return f'h{int(digits) + 1 if digits else 1}'


def export_head(W: np.ndarray, b: np.ndarray, base: dict, trained_on: dict, version: Optional[str] = None,
                labels: Optional[list] = None) -> dict:
    """브라우저(part-ai.js)가 그대로 읽는 꼴 — 모델 주소·전처리·문턱은 지금 판을 그대로 잇는다. labels = 새 분류를 더한 목록."""
    head = dict(base)
    head.update(
        version=version or next_version(base.get('version', 'h0')),
        labels=list(labels or base['labels']),
        W=[[round(float(v), 5) for v in row] for row in W],
        b=[round(float(v), 5) for v in b],
        trained_on=trained_on,
    )
    return head

"""도면 마법사 그림 종류 — 그림 → 특징(768 숫자). 도구용 가상환경에서 돈다(onnxruntime 필요).

설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.1 · §3.7

- 모델: part-head.json 의 ``model``(DINOv2-small int8, Hugging Face 커밋 고정 주소 + sha256). 받으면 sha256 을 맞춰 본다.
- 전처리는 h1 을 가르칠 때와 같다: 흰 여백으로 정사각형 → 224×224(BICUBIC) → ImageNet 평균·표준편차.
- 투명 그림(마법사에 올린 스케치업 PNG 대부분 — 투명 칸의 색은 검정 0,0,0)은 흰 바탕에 얹는다. 브라우저(part-ai.js)가
  흰 캔버스에 그려 재기 때문이다. ``convert('RGB')`` 만 하면 바탕이 검게 되어 브라우저와 다른 특징으로 가르치게 된다.
- 특징: last_hidden_state 의 [CLS, 패치 평균] 을 이어 붙이고 L2 정규화.
- onnxruntime 은 FOMS 서버 환경(numpy 1.26.4 고정)에 넣지 않는다 — :func:`embed_files` 안에서만 부른다.
"""
from __future__ import annotations

import hashlib
import io
import urllib.request
from pathlib import Path

import numpy as np
from PIL import Image

SIZE = 224
MEAN = (0.485, 0.456, 0.406)
STD = (0.229, 0.224, 0.225)


def on_white(img: Image.Image) -> Image.Image:
    """투명 칸이 있는 그림은 흰 바탕에 얹어 RGB 로 — 브라우저가 흰 캔버스에 그리는 것과 같게."""
    if img.mode in ('RGBA', 'LA') or (img.mode == 'P' and 'transparency' in img.info):
        rgba = img.convert('RGBA')
        base = Image.new('RGBA', rgba.size, (255, 255, 255, 255))
        base.alpha_composite(rgba)
        return base.convert('RGB')
    return img.convert('RGB')


def prep(img: Image.Image) -> np.ndarray:
    """그림 1장 → (1, 3, 224, 224) float32."""
    img = on_white(img)
    w, h = img.size
    side = max(w, h)
    canvas = Image.new('RGB', (side, side), (255, 255, 255))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2))
    canvas = canvas.resize((SIZE, SIZE), Image.BICUBIC)
    x = np.asarray(canvas).astype(np.float32) / 255.0
    x = (x - np.array(MEAN, np.float32)) / np.array(STD, np.float32)
    return x.transpose(2, 0, 1)[None]


def pool(last_hidden: np.ndarray) -> np.ndarray:
    """(1, 토큰, d) → [CLS, 패치 평균] (2d,) 를 L2 정규화."""
    v = np.concatenate([last_hidden[0, 0], last_hidden[0, 1:].mean(axis=0)]).astype(np.float64)
    return v / (np.linalg.norm(v) + 1e-9)


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def ensure_model(url: str, sha256: str, cache_dir: Path) -> Path:
    """모델 파일을 캐시 폴더에 받아 두고 sha256 을 맞춰 본다(다르면 지우고 멈춘다)."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f'dinov2-small-int8-{sha256[:12]}.onnx'
    if not path.exists():
        with urllib.request.urlopen(url, timeout=120) as resp:   # Hugging Face 공개 파일(커밋 고정)
            path.write_bytes(resp.read())
    if sha256_of(path) != sha256:
        path.unlink()
        raise RuntimeError('모델 파일 sha256 이 part-head.json 과 다릅니다 — 받은 파일을 지웠습니다.')
    return path


def embed_files(paths: list[Path], model_path: Path) -> np.ndarray:
    """그림 파일들 → (N, 768). 읽지 못한 그림은 0 벡터(호출자가 걸러낸다)."""
    import onnxruntime as ort   # 도구용 가상환경에만 있다

    opts = ort.SessionOptions()
    opts.enable_cpu_mem_arena = False
    sess = ort.InferenceSession(str(model_path), sess_options=opts, providers=['CPUExecutionProvider'])
    name = sess.get_inputs()[0].name
    out_names = [o.name for o in sess.get_outputs()]
    feats = []
    for path in paths:
        try:
            img = Image.open(io.BytesIO(Path(path).read_bytes()))
            outs = dict(zip(out_names, sess.run(None, {name: prep(img)})))
            feats.append(pool(outs.get('last_hidden_state', next(iter(outs.values())))))
        except Exception:   # 깨진 그림 — 0 벡터로 두고 train 이 뺀다
            feats.append(np.zeros(768))
    return np.stack(feats) if feats else np.zeros((0, 768))

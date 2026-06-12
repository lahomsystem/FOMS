"""사용자 제공 스페이드 PNG를 그대로 FOMS 아이콘 마스터로 가져온다."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
ASSETS = ROOT / "docs" / "design" / "assets"
SOURCE_NAME = "foms-spade-source.png"
MASTER_PNG = STATIC / "icons" / "foms-spade-master-1024.png"
SVG_OUT = STATIC / "favicon.svg"
VIEWBOX = 64
MASTER_SIZE = 1024
# iOS/Android 홈화면 마스크(둥근 사각) 안전 영역 — 가장자리 잘림 방지
SAFE_CONTENT_RATIO = 0.58
SVG_RASTER_SIZE = 256


def _resolve_source() -> Path:
    """사용자 제공 스페이드 원본 경로를 찾는다."""
    repo_source = ASSETS / SOURCE_NAME
    if repo_source.exists():
        return repo_source
    cursor_assets = Path.home() / ".cursor" / "projects"
    matches = list(cursor_assets.glob("**/Layer_2-*.png"))
    matches.extend(cursor_assets.glob(f"**/{SOURCE_NAME}"))
    if matches:
        return matches[0]
    raise FileNotFoundError("user spade source image not found")


def _trim_content(img: Image.Image) -> Image.Image:
    """스페이드 실루엣만 남기고 여백을 제거한다."""
    rgba = img.convert("RGBA")
    arr = np.array(rgba)
    mask = (arr[..., 3] > 10) & (
        (arr[..., 0] < 245) | (arr[..., 1] < 245) | (arr[..., 2] < 245)
    )
    ys, xs = np.where(mask)
    if ys.size == 0:
        return rgba
    pad = 2
    left = max(0, int(xs.min()) - pad)
    top = max(0, int(ys.min()) - pad)
    right = min(rgba.width, int(xs.max()) + pad + 1)
    bottom = min(rgba.height, int(ys.max()) + pad + 1)
    return rgba.crop((left, top, right, bottom))


def _square_master(source: Path) -> Image.Image:
    """원본을 고해상도 정사각 마스터로 변환한다(안전 여백 포함)."""
    trimmed = _trim_content(Image.open(source))
    content_w, content_h = trimmed.size
    max_side = max(content_w, content_h)
    target = int(MASTER_SIZE * SAFE_CONTENT_RATIO)
    scale = target / max_side
    new_w = max(1, int(round(content_w * scale)))
    new_h = max(1, int(round(content_h * scale)))
    resized = trimmed.resize((new_w, new_h), Image.Resampling.LANCZOS)

    canvas = Image.new("RGBA", (MASTER_SIZE, MASTER_SIZE), (255, 255, 255, 255))
    offset = ((MASTER_SIZE - new_w) // 2, (MASTER_SIZE - new_h) // 2)
    canvas.paste(resized, offset, resized)
    return canvas


def _svg_from_master(master: Image.Image) -> str:
    """고해상도 래스터를 내장한 favicon.svg를 만든다."""
    buf = BytesIO()
    master.resize((SVG_RASTER_SIZE, SVG_RASTER_SIZE), Image.Resampling.LANCZOS).save(
        buf, format="PNG", optimize=True
    )
    data_uri = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'viewBox="0 0 {VIEWBOX} {VIEWBOX}" role="img" aria-label="FOMS favicon">\n'
        f'  <image xlink:href="{data_uri}" href="{data_uri}" x="0" y="0" width="{VIEWBOX}" height="{VIEWBOX}" />\n'
        f"</svg>\n"
    )


def main() -> None:
    """사용자 스페이드 원본을 마스터·favicon.svg로 저장한다."""
    source = _resolve_source()
    ASSETS.mkdir(parents=True, exist_ok=True)
    if source != ASSETS / SOURCE_NAME:
        Image.open(source).save(ASSETS / SOURCE_NAME)

    master = _square_master(ASSETS / SOURCE_NAME)
    MASTER_PNG.parent.mkdir(parents=True, exist_ok=True)
    master.save(MASTER_PNG, "PNG", optimize=True)
    SVG_OUT.write_text(_svg_from_master(master), encoding="utf-8")
    print(f"wrote {ASSETS / SOURCE_NAME}")
    print(f"wrote {MASTER_PNG.relative_to(ROOT)} ({MASTER_SIZE}px, safe={SAFE_CONTENT_RATIO})")
    print(f"wrote {SVG_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

"""사용자 제공 스페이드 PNG를 그대로 FOMS 아이콘 마스터로 가져온다."""

from __future__ import annotations

import base64
from io import BytesIO
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
ASSETS = ROOT / "docs" / "design" / "assets"
SOURCE_NAME = "foms-spade-source.png"
MASTER_PNG = STATIC / "icons" / "foms-spade-master-512.png"
SVG_OUT = STATIC / "favicon.svg"
VIEWBOX = 64


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


def _square_master(source: Path) -> Image.Image:
    """원본을 정사각 512px 마스터로 변환한다(재해석 없음)."""
    img = Image.open(source).convert("RGBA")
    width, height = img.size
    side = max(width, height)
    canvas = Image.new("RGBA", (side, side), (255, 255, 255, 255))
    canvas.paste(img, ((side - width) // 2, (side - height) // 2), img)
    return canvas.resize((512, 512), Image.Resampling.LANCZOS)


def _svg_from_master(master: Image.Image) -> str:
    """마스터 PNG를 내장한 favicon.svg를 만든다."""
    buf = BytesIO()
    master.resize((VIEWBOX, VIEWBOX), Image.Resampling.LANCZOS).save(buf, format="PNG", optimize=True)
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
    print(f"wrote {MASTER_PNG.relative_to(ROOT)}")
    print(f"wrote {SVG_OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

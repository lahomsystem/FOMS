"""사용자 제공 스페이드 마스터에서 FOMS PNG 아이콘 세트를 생성한다."""

from __future__ import annotations

import runpy
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
STATIC = ROOT / "static"
IMPORT_SCRIPT = ROOT / "tools" / "design" / "import_user_spade_icon.py"
MASTER_PNG = STATIC / "icons" / "foms-spade-master-512.png"


def main() -> None:
    """static/ 아래 favicon 및 PWA PNG 세트를 갱신한다."""
    if IMPORT_SCRIPT.exists():
        runpy.run_path(str(IMPORT_SCRIPT), run_name="__main__")

    if not MASTER_PNG.exists():
        raise FileNotFoundError(f"missing master icon: {MASTER_PNG}")

    master = Image.open(MASTER_PNG).convert("RGBA")
    targets = [
        (STATIC / "favicon.png", 64),
        (STATIC / "icons" / "foms-icon-180.png", 180),
        (STATIC / "icons" / "foms-icon-192.png", 192),
        (STATIC / "icons" / "foms-icon-512.png", 512),
    ]
    for path, size in targets:
        path.parent.mkdir(parents=True, exist_ok=True)
        master.resize((size, size), Image.Resampling.LANCZOS).save(path, "PNG", optimize=True)
        print(f"wrote {path.relative_to(ROOT)} ({size}px)")


if __name__ == "__main__":
    main()

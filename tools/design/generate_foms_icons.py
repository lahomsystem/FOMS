"""사용자 제공 스페이드 마스터에서 FOMS PNG 아이콘 세트를 생성한다."""

from __future__ import annotations

import json
import runpy
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from tools.design.foms_icon_version import ICON_CACHE_VERSION  # noqa: E402
STATIC = ROOT / "static"
IMPORT_SCRIPT = ROOT / "tools" / "design" / "import_user_spade_icon.py"
MASTER_PNG = STATIC / "icons" / "foms-spade-master-1024.png"
MANIFEST_PATH = STATIC / "manifest.json"


def _sync_manifest_icon_urls(version: str) -> None:
    """PWA manifest 아이콘 URL에 캐시 버전 쿼리를 붙인다."""
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for icon in data.get("icons", []):
        src = icon.get("src", "")
        base = src.split("?", 1)[0]
        icon["src"] = f"{base}?v={version}"
    MANIFEST_PATH.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main() -> None:
    """static/ 아래 favicon 및 PWA PNG 세트를 갱신한다."""
    if IMPORT_SCRIPT.exists():
        runpy.run_path(str(IMPORT_SCRIPT), run_name="__main__")

    if not MASTER_PNG.exists():
        raise FileNotFoundError(f"missing master icon: {MASTER_PNG}")

    _sync_manifest_icon_urls(ICON_CACHE_VERSION)
    print(f"synced {MANIFEST_PATH.relative_to(ROOT)} (v={ICON_CACHE_VERSION})")

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

"""인벤토리 생성물을 재생성하되, 의미 없는 변화는 되돌린다 (pre_push_smoke 게이트).

`docs/harness/*_inventory.json` 은 스캔 도구가 만드는 생성물이다. 코드가 바뀌면 낡고,
낡으면 계약 테스트(`test_inventory_matches_fresh_scan` 등)가 red 를 낸다 — 2026-09 CI red
의 반복 원인이었다. 그래서 푸시 전에 먼저 재생성한다.

그런데 그냥 재생성하면 안 된다. 스캔 결과에는 `lineno` 가 들어 있는데, 계약 테스트는
이것을 보지 않는다. 위쪽 코드가 한 줄만 늘어도 수백 개 `lineno` 가 밀리므로, 무조건
재생성하면 **의미 없는 줄번호 churn 이 모든 커밋에 낀다.** 공유 워킹트리에서는 그 churn 이
그대로 세션 간 충돌이 된다. 실제로 2026-09-22 기준 깨끗한 `origin/deploy` 에서 재생성만
해도 3개 파일 68줄이 lineno 때문에 바뀌었다(계약 테스트는 그 트리에서 전부 통과했다).

그래서 여기서는 재생성한 뒤 **의미 비교**를 한다. `lineno` 를 뺀 내용이 스캔 직전과 같으면
직전 내용을 도로 쓴다. 다르면 새 내용을 남기고 무엇이 바뀌었는지 알린다.

종료 코드는 항상 0 이다 — 이 단계는 판정이 아니라 준비다. 판정은 전체 스위트가 한다.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

# (스캔 도구, 그 도구가 쓰는 인벤토리)
SCANS: tuple[tuple[str, str], ...] = (
    ("tools/harness/audit_coverage_scan.py", "docs/harness/foms_audit_coverage_inventory.json"),
    ("tools/harness/failopen_scan.py", "docs/harness/foms_failopen_inventory.json"),
    ("tools/harness/order_mutation_writer_scan.py", "docs/harness/foms_order_mutation_writer_inventory.json"),
    ("tools/harness/orm_bypass_write_scan.py", "docs/harness/foms_orm_bypass_write_inventory.json"),
    ("tools/harness/state_writer_scan.py", "docs/harness/foms_state_writer_inventory.json"),
)

# 계약 테스트가 보지 않는 필드. 여기 있는 키는 "바뀌어도 의미 없음" 으로 친다.
NOISE_KEYS = frozenset({"lineno"})


def _strip_noise(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _strip_noise(v) for k, v in value.items() if k not in NOISE_KEYS}
    if isinstance(value, list):
        return [_strip_noise(v) for v in value]
    return value


def _current_bytes(path: Path) -> bytes | None:
    """스캔 직전의 워킹트리 내용. 없으면 None.

    HEAD 를 기준으로 삼지 않는 이유가 둘 있다. ① `git show` 는 줄끝을 LF 로 정규화해서
    돌려주므로, 그 바이트를 그대로 되쓰면 CRLF 체크아웃 환경에서 파일 줄끝이 통째로 바뀐다.
    ② 커밋하지 않은 의도적 인벤토리 수정(allowlist 추가 등)을 조용히 밟게 된다.
    """
    if not path.exists():
        return None
    return path.read_bytes()


def main(argv: list[str] | None = None) -> int:
    del argv
    meaningful: list[str] = []
    failed: list[str] = []

    for scan_rel, inventory_rel in SCANS:
        scan_path = ROOT / scan_rel
        inventory_path = ROOT / inventory_rel
        if not scan_path.exists():
            continue

        before = _current_bytes(inventory_path)

        proc = subprocess.run(
            [sys.executable, str(scan_path)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if proc.returncode != 0:
            failed.append(f"{scan_rel} (exit {proc.returncode})")
            continue

        if before is None or not inventory_path.exists():
            meaningful.append(inventory_rel)
            continue

        after = inventory_path.read_bytes()
        if after == before:
            continue

        try:
            same_meaning = _strip_noise(json.loads(before)) == _strip_noise(
                json.loads(after)
            )
        except json.JSONDecodeError:
            same_meaning = False

        if same_meaning:
            # 줄번호만 밀렸다 — 스캔 전 내용을 도로 쓴다.
            inventory_path.write_bytes(before)
        else:
            meaningful.append(inventory_rel)

    if failed:
        print("스캔 실행 실패(무시하고 진행 — 전체 스위트가 판정한다):")
        for item in failed:
            print(f"  {item}")

    if meaningful:
        print("인벤토리를 갱신했다 — 커밋에 포함하라:")
        for item in meaningful:
            print(f"  {item}")
    else:
        print("인벤토리 최신 (의미 있는 변화 없음)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

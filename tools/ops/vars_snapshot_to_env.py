"""오프사이트 환경변수 스냅샷(JSON) → 대피 구성용 서비스별 .env 파일.

    age -d -i <키> vars-latest.json.age | python tools/ops/vars_snapshot_to_env.py --out <저장소 밖 폴더>

입력: foms-ops-backup `secrets/vars-latest.json.age` 를 복호화한 JSON({서비스: {변수: 값}}), 표준 입력으로만 받는다
(평문을 디스크에 두지 않으려고). 출력: <out>/web.env·worker.env·sidefx.env·cron.env.
- Railway 가 넣는 `RAILWAY_*` 와 Railway Postgres·Redis 주소(새 서버에서는 docker-compose.yml 이 정한다)는 뺀다.
- 값은 화면에 찍지 않는다(개수만). 출력 폴더는 저장소 안이면 거부한다(.env 가 커밋되지 않게).
설계: docs/specs/2026-10-22-railway-exit-plan_SPEC.md 1단계 4번.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

#: 스냅샷 서비스 이름 → 대피 구성 env 파일 이름.
SERVICE_FILES: dict[str, str] = {"web": "web", "WORKER": "worker", "SIDEFX": "sidefx", "FOMS-cron": "cron"}

#: 새 서버에서 docker-compose.yml 이 정하는 연결 값 — 옛 Railway 값을 넘기면 없는 서버를 가리킨다.
DROP_EXACT: frozenset[str] = frozenset({
    "DATABASE_URL", "DATABASE_PUBLIC_URL", "PGHOST", "PGPORT", "PGUSER", "PGPASSWORD", "PGDATABASE",
    "REDIS_URL", "REDIS_PUBLIC_URL", "REDISHOST", "REDISPORT", "REDISUSER", "REDISPASSWORD",
    "REDIS_PASSWORD", "PORT", "FOMS_TRUSTED_PROXY_HOPS",
})


def convert(snapshot: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """서비스별로 옮길 변수만 남긴다. 스냅샷에 없는 서비스는 빈 묶음."""
    out: dict[str, dict[str, str]] = {}
    for service, name in SERVICE_FILES.items():
        values = snapshot.get(service, {})
        out[name] = {
            k: v for k, v in sorted(values.items())
            if not k.startswith("RAILWAY_") and k not in DROP_EXACT
        }
    return out


def render(values: dict[str, str]) -> str:
    """docker compose env_file 형식(KEY=VALUE 한 줄씩). 줄바꿈이 든 값은 거부한다."""
    lines = []
    for key, value in values.items():
        if "\n" in value or "\r" in value:
            raise SystemExit(f"{key}: 값에 줄바꿈이 있어 env 파일로 옮길 수 없다 — 손으로 처리")
        lines.append(f"{key}={value}")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", required=True, help="출력 폴더(저장소 밖)")
    args = parser.parse_args(argv)
    out_dir = Path(args.out).resolve()
    if out_dir == REPO_ROOT or REPO_ROOT in out_dir.parents:
        raise SystemExit("출력 폴더가 저장소 안이다 — 비밀값이 커밋될 수 있어 거부한다")
    snapshot = json.loads(sys.stdin.buffer.read())
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, values in convert(snapshot).items():
        (out_dir / f"{name}.env").write_text(render(values), encoding="utf-8")
        print(f"{name}.env: 변수 {len(values)}개")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

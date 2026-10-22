"""오프사이트 백업(foms-ops-backup) 덤프를 **빈** PostgreSQL 에 복원하고 숫자를 센다.

    python tools/ops/offsite_restore.py --key C:/Users/USER/foms-backup-key.txt --target <빈 DB DSN> [--fetch | --dump-age <파일>]

2026-10-22 첫 복원 리허설(RESTORE.md §8) 순서를 그대로 옮겼다:
  ① 받기 — `--fetch` 면 wrangler 로 R2 백업 버킷의 db/LATEST.json 과 그 덤프(먼저 `npx wrangler login`)
  ② sha256 대조(LATEST.json 이 있을 때) ③ age 복호화 ④ pg_restore ⑤ orders·users·alembic 세기 ⑥ 평문 덤프 삭제.
안전장치: 대상 DB 에 표가 하나라도 있으면 거부한다(운영 DSN 에 잘못 붙는 사고 방지, --clean 은 쓰지 않는다).
Railway 공개 주소(*.proxy.rlwy.net)는 `--allow-railway-target` 없이는 거부한다. 고객 데이터·접속 문자열은 출력하지 않는다.
설계: docs/specs/2026-10-22-railway-exit-plan_SPEC.md 1단계 3번.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

BUCKET_DEFAULT = "foms-backup"
CORE_TABLES = ("orders", "users", "order_field_changes", "security_logs")


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_target(dsn: str, allow_railway: bool) -> None:
    """대상이 비어 있고 Railway 공개 주소가 아닌지 확인한다. 아니면 SystemExit."""
    import psycopg

    host = urlsplit(dsn).hostname or ""
    if "rlwy.net" in host and not allow_railway:
        raise SystemExit(f"대상 호스트가 Railway 공개 주소({host}) — 운영일 수 있어 거부(--allow-railway-target)")
    with psycopg.connect(dsn, connect_timeout=15) as conn:
        n = conn.execute(
            "SELECT count(*) FROM pg_class c JOIN pg_namespace s ON s.oid = c.relnamespace "
            "WHERE c.relkind = 'r' AND s.nspname NOT IN ('pg_catalog', 'information_schema')"
        ).fetchone()[0]
    if n:
        raise SystemExit(f"대상 DB 에 표가 {n}개 있다 — 빈 DB 에만 복원한다(--clean 금지)")
    print(f"대상 확인: {host} · 빈 DB")


def fetch(bucket: str, work: Path) -> tuple[Path, dict]:
    """wrangler 로 LATEST.json 과 최신 덤프를 받는다."""
    npx = shutil.which("npx") or "npx"
    latest = work / "LATEST.json"
    subprocess.run([npx, "--yes", "wrangler", "r2", "object", "get", f"{bucket}/db/LATEST.json",
                    "--remote", "--file", str(latest)], check=True)
    meta = json.loads(latest.read_text(encoding="utf-8"))
    dump = work / "latest.dump.age"
    subprocess.run([npx, "--yes", "wrangler", "r2", "object", "get", f"{bucket}/{meta['key']}",
                    "--remote", "--file", str(dump)], check=True)
    return dump, meta


def count(dsn: str) -> None:
    import psycopg

    with psycopg.connect(dsn, connect_timeout=15) as conn:
        for t in CORE_TABLES:
            row = conn.execute("SELECT to_regclass(%s)", (f"public.{t}",)).fetchone()[0]
            n = conn.execute(f'SELECT count(*) FROM public."{t}"').fetchone()[0] if row else "표 없음"
            print(f"  {t}: {n}")
        print("  alembic_version:", conn.execute("SELECT version_num FROM alembic_version").fetchall())


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--key", required=True, help="age 개인키 파일")
    p.add_argument("--target", required=True, help="복원할 빈 DB 의 DSN")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--fetch", action="store_true", help="wrangler 로 R2 에서 최신 덤프를 받는다")
    src.add_argument("--dump-age", help="이미 받은 .dump.age 파일")
    p.add_argument("--bucket", default=BUCKET_DEFAULT)
    p.add_argument("--pg-bin", default="", help="pg_restore 가 있는 폴더(기본: PATH)")
    p.add_argument("--allow-railway-target", action="store_true")
    args = p.parse_args(argv)

    check_target(args.target, args.allow_railway_target)
    pg_restore = str(Path(args.pg_bin) / "pg_restore") if args.pg_bin else (shutil.which("pg_restore") or "pg_restore")
    age = shutil.which("age") or "age"
    with tempfile.TemporaryDirectory(prefix="foms-restore-") as tmp:
        work = Path(tmp)
        if args.fetch:
            enc, meta = fetch(args.bucket, work)
            got = sha256_of(enc)
            if got != meta.get("sha256"):
                raise SystemExit(f"sha256 불일치({got[:8]} ≠ {str(meta.get('sha256'))[:8]}) — 전송 손상 또는 교체")
            print(f"받음: {meta['key']} · sha256 {got[:8]} 일치")
        else:
            enc = Path(args.dump_age)
        plain = work / "restore.dump"
        subprocess.run([age, "-d", "-i", args.key, "-o", str(plain), str(enc)], check=True)
        proc = subprocess.run([pg_restore, "--no-owner", "--no-privileges", "--jobs", "4",
                               "--dbname", args.target, str(plain)],
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        errors = [ln for ln in (proc.stderr or "").splitlines() if "error" in ln.lower() or "오류" in ln]
        print(f"pg_restore exit {proc.returncode}, 오류 줄 {len(errors)}개")
        for ln in errors[:10]:
            print("   ", ln[:200])
        plain.unlink(missing_ok=True)  # 평문 덤프는 운영 데이터 전량 — 남기지 않는다
    count(args.target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

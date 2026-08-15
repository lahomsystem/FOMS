"""Railway Postgres 시점 복구(PITR) 조회 + 사고 조사용 fork 생성.

DATA-DOCTOR-01. 운영 볼륨은 **절대 건드리지 않는다** — 이 도구가 하는 쓰기는
``volumeInstancePITRRestore`` 로 *새 서비스* 를 만드는 것뿐이다. 원본 볼륨을 덮는
``volumeInstanceBackupRestore`` 는 구현하지 않는다(오조작 한 번이 운영 DB 통째 롤백).

사용:
    python tools/ops/railway_pitr.py list --project FOMS-PRODUCTION
    python tools/ops/railway_pitr.py fork --project FOMS-PRODUCTION \
        --at 2026-08-14T06:25:00Z --name foms-pitr-0814
    python tools/ops/railway_pitr.py drop --project FOMS-PRODUCTION --name foms-pitr-0814

fork 가 만든 서비스의 DSN 을 :mod:`tools.ops.data_doctor` 의 ``--snapshot-dsn`` 으로
넘기면 사고 직전 값을 **추론이 아니라 원본 그대로** 읽어 복구안을 만든다.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://backboard.railway.app/graphql/v2"

#: 운영 볼륨을 덮어쓰는 mutation. 이 도구는 호출하지 않는다(사고 확대 방지).
FORBIDDEN_MUTATIONS = ("volumeInstanceBackupRestore",)


def _load_token() -> str:
    """Railway CLI 설정에서 API 토큰을 읽는다.

    Returns:
        Bearer 토큰 문자열.

    Raises:
        SystemExit: 토큰이 없으면(=CLI 로그인 안 됨) 중단.
    """
    config_path = Path.home() / ".railway" / "config.json"
    if not config_path.exists():
        raise SystemExit("railway CLI 설정이 없습니다. `railway login` 먼저 실행하세요.")
    data = json.loads(config_path.read_text(encoding="utf-8"))
    token = (data.get("user") or {}).get("token")
    if not token:
        raise SystemExit("Railway 토큰을 찾지 못했습니다(~/.railway/config.json).")
    return token


def _graphql(token: str, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Railway GraphQL 요청 1건을 실행한다.

    Args:
        token: Bearer 토큰.
        query: GraphQL 문서.
        variables: 변수 dict(없으면 생략).

    Returns:
        ``data`` 하위 dict.

    Raises:
        SystemExit: HTTP 오류 또는 GraphQL errors 응답.
    """
    payload: dict[str, Any] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    req = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "railway-cli/4.0.0",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:400]
        raise SystemExit(f"GraphQL HTTP {exc.code}: {detail}") from exc
    if body.get("errors"):
        raise SystemExit(f"GraphQL errors: {json.dumps(body['errors'], ensure_ascii=False)[:400]}")
    return body.get("data") or {}


def _resolve_project(token: str, project_name: str) -> tuple[str, str]:
    """프로젝트 이름을 (project_id, environment_id) 로 해석한다.

    Railway API 의 ``projects`` 쿼리는 개인 토큰으로 빈 목록을 주는 경우가 있어(팀 스코프),
    **CLI 가 이미 링크해 둔 디렉토리 기록**(``~/.railway/config.json`` 의 ``projects``)에서
    이름을 찾는다. 링크된 적 없는 프로젝트는 해당 폴더에서 ``railway link`` 를 한 번 하면 된다.

    Args:
        token: Bearer 토큰(현재 미사용 — API 폴백 여지를 위해 유지).
        project_name: Railway 프로젝트 이름(예: ``FOMS-PRODUCTION``).

    Returns:
        (project_id, environment_id).

    Raises:
        SystemExit: 링크 기록에 이름이 없으면 중단.
    """
    config_path = Path.home() / ".railway" / "config.json"
    data = json.loads(config_path.read_text(encoding="utf-8"))
    for entry in (data.get("projects") or {}).values():
        if entry.get("name") == project_name and entry.get("project"):
            return entry["project"], entry.get("environment") or ""
    raise SystemExit(
        f"링크 기록에서 프로젝트를 찾지 못했습니다: {project_name}. "
        f"해당 폴더에서 `railway link --project {project_name}` 를 먼저 실행하세요."
    )


def _resolve_volume_instance(token: str, project_id: str, volume_name: str) -> str:
    """볼륨 이름 → volumeInstanceId.

    Args:
        token: Bearer 토큰.
        project_id: 프로젝트 id.
        volume_name: 볼륨 이름(기본 ``postgres-volume``).

    Returns:
        volumeInstanceId 문자열.

    Raises:
        SystemExit: 해당 볼륨 인스턴스가 없으면 중단.
    """
    data = _graphql(
        token,
        """query($id:String!){ project(id:$id){ volumes{ edges{ node{ name
             volumeInstances{ edges{ node{ id environmentId } } } } } } } }""",
        {"id": project_id},
    )
    for edge in ((data.get("project") or {}).get("volumes") or {}).get("edges", []):
        node = edge["node"]
        if node["name"] != volume_name:
            continue
        instances = [e["node"] for e in (node.get("volumeInstances") or {}).get("edges", [])]
        if instances:
            return instances[0]["id"]
    raise SystemExit(f"볼륨 인스턴스를 찾지 못했습니다: {volume_name}")


def cmd_list(args: argparse.Namespace) -> int:
    """백업 스케줄·백업 목록·복구 가능 창을 출력한다(읽기 전용).

    Args:
        args: ``project``·``volume`` 을 갖는 파싱된 인자.

    Returns:
        프로세스 종료 코드(0=성공).
    """
    token = _load_token()
    project_id, _env_id = _resolve_project(token, args.project)
    volume_instance_id = _resolve_volume_instance(token, project_id, args.volume)

    schedules = _graphql(
        token,
        """query($id:String!){ volumeInstanceBackupScheduleList(volumeInstanceId:$id){
             id name kind cron retentionSeconds } }""",
        {"id": volume_instance_id},
    ).get("volumeInstanceBackupScheduleList") or []
    backups = _graphql(
        token,
        """query($id:String!){ volumeInstanceBackupList(volumeInstanceId:$id){
             id name createdAt expiresAt usedMB } }""",
        {"id": volume_instance_id},
    ).get("volumeInstanceBackupList") or []

    print(f"volumeInstanceId: {volume_instance_id}")
    for sched in schedules:
        days = round((sched.get("retentionSeconds") or 0) / 86400, 1)
        print(f"스케줄: {sched['name']} kind={sched['kind']} cron={sched['cron']} 보존={days}일")
    ordered = sorted(backups, key=lambda b: b.get("createdAt") or "")
    print(f"백업 {len(ordered)}건")
    for backup in ordered:
        print(f"  {backup['createdAt']}  {backup['name']}  expires={backup.get('expiresAt')}")
    if ordered:
        print(f"복구 가능 창(가장 오래된 백업 기준): {ordered[0]['createdAt']} ~ 현재")
    print("주의: 보존창을 넘긴 시점은 복구 불가 — 사고 발견 즉시 fork 를 뜨는 게 안전하다.")
    return 0


def cmd_fork(args: argparse.Namespace) -> int:
    """지정 시각 상태를 **새 서비스**로 복원한다(운영 볼륨 불변).

    Args:
        args: ``project``·``volume``·``at``·``name``·``wait`` 를 갖는 파싱된 인자.

    Returns:
        프로세스 종료 코드(0=성공).
    """
    token = _load_token()
    project_id, _env_id = _resolve_project(token, args.project)
    volume_instance_id = _resolve_volume_instance(token, project_id, args.volume)

    print(f"PITR fork 요청: {args.at} → 새 서비스 '{args.name}' (원본 볼륨은 그대로)")
    _graphql(
        token,
        """mutation($vid:String!,$ts:DateTime!,$name:String!){
             volumeInstancePITRRestore(volumeInstanceId:$vid, targetTimestamp:$ts, newServiceName:$name) }""",
        {"vid": volume_instance_id, "ts": args.at, "name": args.name},
    )
    print("요청 접수. Railway 대시보드에서 새 서비스가 뜨면 DATABASE_PUBLIC_URL 을 확인하라:")
    print(f"  railway variables --service {args.name} --json")
    print("그 DSN 을 data_doctor 의 --snapshot-dsn 으로 넘기면 사고 직전 원본값으로 복구안을 만든다.")
    print(f"조사 끝나면 반드시 지워라: python tools/ops/railway_pitr.py drop "
          f"--project {args.project} --name {args.name}")
    return 0


def cmd_drop(args: argparse.Namespace) -> int:
    """조사용 fork 서비스를 삭제한다(비용·데이터 사본 정리).

    Args:
        args: ``project``·``name``·``yes`` 를 갖는 파싱된 인자.

    Returns:
        프로세스 종료 코드(0=성공, 2=취소/미발견).
    """
    token = _load_token()
    project_id, _env_id = _resolve_project(token, args.project)
    data = _graphql(
        token,
        """query($id:String!){ project(id:$id){ services{ edges{ node{ id name } } } } }""",
        {"id": project_id},
    )
    services = [e["node"] for e in ((data.get("project") or {}).get("services") or {}).get("edges", [])]
    target = next((s for s in services if s["name"] == args.name), None)
    if target is None:
        print(f"서비스를 찾지 못했습니다: {args.name}")
        return 2
    if not args.yes:
        print(f"삭제 대상: {args.name} ({target['id']}) — 실행하려면 --yes 를 붙여라.")
        return 2
    _graphql(token, """mutation($id:String!){ serviceDelete(id:$id) }""", {"id": target["id"]})
    print(f"삭제 완료: {args.name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """CLI 파서를 만든다.

    Returns:
        서브커맨드가 붙은 파서.
    """
    parser = argparse.ArgumentParser(description="Railway Postgres PITR 조회 + 조사용 fork")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="백업 스케줄·목록·복구 가능 창 조회(읽기 전용)")
    p_list.add_argument("--project", default="FOMS-PRODUCTION")
    p_list.add_argument("--volume", default="postgres-volume")
    p_list.set_defaults(func=cmd_list)

    p_fork = sub.add_parser("fork", help="지정 시각 상태를 새 서비스로 복원(운영 볼륨 불변)")
    p_fork.add_argument("--project", default="FOMS-PRODUCTION")
    p_fork.add_argument("--volume", default="postgres-volume")
    p_fork.add_argument("--at", required=True, help="ISO8601 UTC 예: 2026-08-14T06:25:00Z")
    p_fork.add_argument("--name", required=True, help="새 서비스 이름(예: foms-pitr-0814)")
    p_fork.add_argument("--wait", type=int, default=0, help="예약: 상태 폴링 초(현재 미사용)")
    p_fork.set_defaults(func=cmd_fork)

    p_drop = sub.add_parser("drop", help="조사용 fork 서비스 삭제")
    p_drop.add_argument("--project", default="FOMS-PRODUCTION")
    p_drop.add_argument("--name", required=True)
    p_drop.add_argument("--yes", action="store_true")
    p_drop.set_defaults(func=cmd_drop)
    return parser


def main(argv: list[str] | None = None) -> int:
    """엔트리포인트.

    Args:
        argv: 인자 목록(기본 ``sys.argv[1:]``).

    Returns:
        프로세스 종료 코드.
    """
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    sys.exit(main())

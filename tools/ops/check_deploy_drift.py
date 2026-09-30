"""머지됐는데 Railway 가 배포하지 않은 커밋을 찾는다 (읽기 전용).

2026-09-22 사건: PR #414 가 07:32:19Z 에 production 에 머지됐는데 Railway 가 배포를
만들지 않았다. 바로 앞(#412, 06:05)과 바로 뒤(#415, 07:45)는 2초 만에 배포됐고,
머지 커밋에 ``railway-app`` 체크수트도 생겼다 — **GitHub 은 이벤트를 보냈고 Railway 가
그 한 건을 흘렸다.** 저장소에는 아무 신호도 남지 않는다. CI 는 green 이고, 브랜치는
올라갔고, 아무도 실패를 보지 않는다. 그래서 1시간 13분 동안 운영이 옛 코드로 돌았다.

이 도구는 **브랜치 머리와 Railway 가 실제로 배포한 커밋을 대조**한다. 그 둘이 갈라져
있으면 누락이다. `ci_watch.py` 가 "CI 가 초록인가"를 보는 자리라면, 이 도구는
"그래서 그게 서버에 올라갔는가"를 본다 — 서로 다른 질문이고, 이번 건은 뒤엣것만 틀렸다.

읽기 전용이다. `railway link` 를 건드리지 않는다(프로젝트 id 를 `railway list --json`
에서 이름으로 찾고, 나머지는 GraphQL 로 id 를 명시해 조회한다 — 링크 오염 함정 회피).

사용:
    python tools/ops/check_deploy_drift.py                 # 두 환경 모두
    python tools/ops/check_deploy_drift.py --target production
    python tools/ops/check_deploy_drift.py --json

종료 코드: 0=일치(또는 배포 진행 중) · 1=누락 발견 · 2=판정 불가(토큰·CLI·API 문제).
판정 불가를 0 으로 뭉개지 않는다 — 조용한 초록이 이번 사건의 본질이었다.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

GRAPHQL_URL = "https://backboard.railway.com/graphql/v2"
# UA 가 없으면 같은 토큰·같은 쿼리도 403 이다(2026-09-11 실측).
USER_AGENT = "railwayapp/4.0.0"

# 배포가 아직 굴러가는 중인 상태들. 이건 누락이 아니다.
IN_FLIGHT = frozenset(
    {"BUILDING", "DEPLOYING", "INITIALIZING", "QUEUED", "WAITING", "NEEDS_APPROVAL"}
)
LIVE = frozenset({"SUCCESS"})


@dataclass(frozen=True)
class Target:
    label: str
    project: str
    environment: str
    service: str  # 프로젝트마다 웹 서비스 이름이 다르다: 운영 web, 스테이징 FOMS
    git_ref: str


TARGETS: tuple[Target, ...] = (
    Target("production", "FOMS-PRODUCTION", "production", "web", "origin/production"),
    Target("staging", "FOMS-DEV", "production", "FOMS", "origin/deploy"),
)


class Undetermined(RuntimeError):
    """판정 불가 — 초록으로 뭉개면 안 되는 상황."""


def _token() -> str:
    token = os.environ.get("RAILWAY_TOKEN")
    if token:
        return token
    config = Path.home() / ".railway" / "config.json"
    if not config.exists():
        raise Undetermined(
            "railway 토큰이 없다 — `railway login` 하거나 RAILWAY_TOKEN 을 설정하라"
        )
    try:
        return json.loads(config.read_text(encoding="utf-8"))["user"]["token"]
    except (json.JSONDecodeError, KeyError) as exc:
        raise Undetermined(f"~/.railway/config.json 에서 토큰을 못 읽었다: {exc}") from exc


def _graphql(token: str, query: str) -> dict[str, Any]:
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": query}).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": USER_AGENT,
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError) as exc:
        raise Undetermined(f"Railway GraphQL 호출 실패: {exc}") from exc
    if payload.get("errors"):
        raise Undetermined(f"Railway GraphQL 오류: {payload['errors']}")
    return payload["data"]


def _project_ids() -> dict[str, str]:
    """프로젝트 이름 -> id. `railway list --json` 은 링크를 바꾸지 않는다."""
    # Windows 에서는 railway 가 .CMD 라 PATH 문자열만으로는 못 찾는다(WinError 2).
    # nvm4w 는 전역 CLI 를 node 버전별로 격리하므로, 버전을 바꾸면 사라진 것처럼 보인다.
    railway = shutil.which("railway")
    if not railway:
        raise Undetermined(
            "railway CLI 를 찾을 수 없다 — 설치했는지, nvm4w 로 node 버전을 바꾸지 않았는지 보라"
        )
    try:
        proc = subprocess.run(
            [railway, "list", "--json"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise Undetermined(f"railway CLI 실행 실패: {exc}") from exc
    if proc.returncode != 0:
        raise Undetermined(f"railway list 실패(exit {proc.returncode}): {proc.stderr.strip()[:200]}")
    try:
        projects = json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise Undetermined(f"railway list 출력이 JSON 이 아니다: {exc}") from exc
    return {p["name"]: p["id"] for p in projects if p.get("name") and p.get("id")}


def _resolve(token: str, project_id: str, target: Target) -> tuple[str, str]:
    data = _graphql(
        token,
        f'query{{ project(id:"{project_id}"){{ '
        "services{edges{node{id name}}} environments{edges{node{id name}}} } }",
    )
    project = data.get("project") or {}
    services = {e["node"]["name"]: e["node"]["id"] for e in project.get("services", {}).get("edges", [])}
    environments = {
        e["node"]["name"]: e["node"]["id"] for e in project.get("environments", {}).get("edges", [])
    }
    if target.service not in services:
        raise Undetermined(
            f"{target.project} 에 서비스 '{target.service}' 가 없다 (있는 것: {sorted(services)})"
        )
    if target.environment not in environments:
        raise Undetermined(
            f"{target.project} 에 환경 '{target.environment}' 가 없다 (있는 것: {sorted(environments)})"
        )
    return environments[target.environment], services[target.service]


def _deployments(
    token: str, project_id: str, environment_id: str, service_id: str
) -> list[dict[str, Any]]:
    data = _graphql(
        token,
        "query{ deployments(first:20, input:{"
        f'projectId:"{project_id}", environmentId:"{environment_id}", serviceId:"{service_id}"'
        "}){ edges{ node{ id status createdAt meta } } } }",
    )
    return [e["node"] for e in data.get("deployments", {}).get("edges", [])]


def _git(*args: str) -> str:
    proc = subprocess.run(
        ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if proc.returncode != 0:
        raise Undetermined(f"git {' '.join(args)} 실패: {proc.stderr.strip()[:200]}")
    return proc.stdout.strip()


@dataclass
class Result:
    label: str
    ok: bool
    undetermined: bool = False
    head: str = ""
    deployed: str = ""
    status: str = ""
    behind: int = 0
    missed: list[str] = field(default_factory=list)
    note: str = ""


def check(target: Target, token: str, project_ids: dict[str, str]) -> Result:
    if target.project not in project_ids:
        raise Undetermined(
            f"Railway 에 프로젝트 '{target.project}' 가 없다 (있는 것: {sorted(project_ids)})"
        )
    project_id = project_ids[target.project]
    environment_id, service_id = _resolve(token, project_id, target)
    deployments = _deployments(token, project_id, environment_id, service_id)
    if not deployments:
        raise Undetermined(f"{target.label}: 배포 이력이 비어 있다")

    head = _git("rev-parse", target.git_ref)

    # 브랜치 머리가 배포 목록 어딘가에 있으면 Railway 는 그 커밋을 집었다.
    for node in deployments:
        meta = node.get("meta") or {}
        if (meta.get("commitHash") or "") == head:
            status = node.get("status") or "?"
            return Result(
                target.label,
                ok=status in LIVE or status in IN_FLIGHT,
                head=head,
                deployed=head,
                status=status,
                note="배포 진행 중" if status in IN_FLIGHT else "",
            )

    # 없으면 누락이다. 실제로 살아 있는 최신 배포와 견준다.
    live = next((n for n in deployments if (n.get("status") or "") in LIVE), deployments[0])
    live_sha = ((live.get("meta") or {}).get("commitHash")) or ""
    behind = 0
    missed: list[str] = []
    if live_sha:
        try:
            behind = int(_git("rev-list", "--count", f"{live_sha}..{head}"))
            # 승격은 머지 커밋으로 들어오지만, deploy 는 직접 푸시가 많다.
            # 머지가 하나도 없으면 일반 커밋으로 떨어뜨린다(빈 목록이 제일 쓸모없다).
            missed = _git(
                "log", "--oneline", "--merges", "-5", f"{live_sha}..{head}"
            ).splitlines()
            if not missed:
                missed = _git("log", "--oneline", "-5", f"{live_sha}..{head}").splitlines()
        except Undetermined:
            # 배포된 커밋이 로컬에 없을 수 있다(fetch 가 뒤처짐). 그래도 누락 판정은 유효하다.
            behind = -1
    return Result(
        target.label,
        ok=False,
        head=head,
        deployed=live_sha,
        status=live.get("status") or "?",
        behind=behind,
        missed=missed,
        note=f"마지막 배포 {live.get('createdAt')}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--target", choices=[t.label for t in TARGETS], help="한 환경만 검사")
    parser.add_argument("--json", action="store_true", dest="as_json", help="JSON 출력")
    args = parser.parse_args(argv)

    targets = [t for t in TARGETS if not args.target or t.label == args.target]

    try:
        token = _token()
        project_ids = _project_ids()
    except Undetermined as exc:
        print(f"[판정 불가] {exc}", file=sys.stderr)
        return 2

    results: list[Result] = []
    undetermined = False
    for target in targets:
        try:
            results.append(check(target, token, project_ids))
        except Undetermined as exc:
            undetermined = True
            results.append(Result(target.label, ok=False, undetermined=True, note=str(exc)))

    if args.as_json:
        print(json.dumps([r.__dict__ for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            if r.undetermined:
                print(f"[판정 불가] {r.label}: {r.note}")
                continue
            if r.ok:
                extra = f" ({r.note})" if r.note else ""
                print(f"[일치] {r.label}: {r.head[:8]} 배포됨 status={r.status}{extra}")
                continue
            behind = f"{r.behind}커밋" if r.behind >= 0 else "개수 불명(로컬에 없는 커밋)"
            print(f"[누락] {r.label}: 브랜치 {r.head[:8]} 인데 배포는 {r.deployed[:8] or '?'} — {behind} 뒤")
            if r.note:
                print(f"         {r.note}")
            for line in r.missed:
                print(f"         안 올라간 머지: {line}")
            print("         조치: Railway 대시보드에서 해당 커밋 배포, 또는 빈 커밋으로 재트리거")

    if undetermined:
        return 2
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())

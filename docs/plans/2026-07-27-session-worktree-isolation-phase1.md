# 세션별 Worktree 격리 (Phase 1) Implementation Plan — v2

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> v1 → v2: gstack-autoplan 듀얼 보이스 리뷰(Claude CEO 20건 + Claude Eng 25건, Codex는 CLI 비호환으로 [subagent-only] 격하) 반영 전면 개정. 판정 내역은 부록 B(Decision Audit Trail), 리뷰 요약은 부록 C.
>
> **v2.1 정정 (2026-07-27 구현 중 태스크 리뷰 F1)**: 본 문서 Task 2의 `cmd_sync` 코드 중 `--ledger-only` 경로는 결함 — 소유 검증이 rebase **후** SHA를 대상으로 돌아 충돌 복구가 항상 refuse된다(탈출구가 `--allow-foreign`뿐 = 세탁 방지 장치 무력화 훈련). 또한 dirty 판정은 CLI 부기 파일 2패턴만 pathspec 제외한다(`_status_porcelain`).
>
> **v2.2 재정정 (라운드 2)**: v2.1의 1차 수정(ORIG_HEAD 기준 검증)은 재리뷰에서 **신규 세탁 구멍**으로 실증 기각 — ORIG_HEAD는 merge/reset/pull도 갱신하며 영구 잔존. 2차 수정(충돌 마커 + ORIG_HEAD 일치)도 관통됨(abort→merge 재일치, continue 후 cherry-pick 불변). 3차 수정(patch-id 전단사 회계)은 방어에 성공했으나 잔여 슬랙(자기 커밋 순감 시 foreign 슬롯)과 false refuse 계열이 남았다.
>
> **v2.3 최종 설계 (라운드 4)**: 신뢰창 회계를 전부 폐기하고 **git post-rewrite 훅 ledger 승계**로 종결 — rebase/amend 완료 시 훅(`record_rewrite_ledger.py`)이 old→new SHA를 같은 세션으로 ledger에 append. 재작성 커밋이 "정식 own"이 되므로 sync는 **단일 union 검증**만 남는다(마커·patch-id·ORIG_HEAD 기계 전삭, net −55줄). cherry-pick/merge는 post-rewrite를 발화시키지 않아 foreign 차단력 유지. 훅은 `create`가 공유 훅 디렉터리에 1회 프로비저닝. 정본은 `tools/harness/session_worktree.py` + `record_rewrite_ledger.py` 구현.

**Goal:** 다중 에이전트 창(터미널 Claude CLI, Cursor 내 Claude/Codex)이 각자 `c:/tmp` 세션 worktree에서 작업해 **워킹트리 레이스·stash 오염·검증 대상 트리 오염**(타 창 WIP 섞인 트리에서 스모크·import 검증이 도는 문제)을 제거한다. **선택 표준** — 강제 아님, 단일 창은 공유 트리 유지.

**Architecture:** 소유권 판정을 ledger 재작성이 아니라 **`deploy_push_scope`의 세션-worktree 합집합(union) 규칙**으로 해결한다(세션 worktree의 ledger는 그 창 계보의 커밋만 담기므로, union ⊇ push 범위 = own). 수명주기는 슬림 CLI `tools/harness/session_worktree.py`(create/list/sync/cleanup)가 관장하되, ledger 스키마·타임스탬프는 `session_commit_ledger.py` SSOT 안에 새 공개 함수로 캡슐화한다. Claude CLI 세션은 네이티브 EnterWorktree/ExitWorktree 병용 가능(문서화).

**Tech Stack:** Python 3.12 stdlib + 기존 `session_commit_ledger.py`/`deploy_push_scope.py` + pytest.

**상위 설계 정본:** `docs/specs/2026-07-16-deploy-push-session-isolation-design.md` §2.6 Phase 1. 2026-07-16 토론 결론(전창 강제 비효율) 계승 — 강제하지 않는다.

## 전제(Premises) — 명시 판정

| # | 전제 | 판정 | 근거 |
|---|------|------|------|
| P1 | 동시 다창 코드 작업이 실제 발생한다 | **부분 검증** | ledger 세션 35개/11일; 본 설계 세션 중에도 타 창이 c:/tmp worktree 2개 정리·deploy push 실측. 단 "같은 시각 동시 편집" 빈도는 사용자만 답할 수 있음 → **승인 게이트 질문 1** |
| P2 | 워킹트리 레이스가 실질 손해를 낸다 | 정황 | 2026-07-16 push 혼입 사고(기록), stash 40개 누적, reflog 확인 규칙·stash clear 금지 규칙의 존재 자체 |
| P3 | 세션 worktree = 단일 세션 | **거짓** | worktree는 며칠 살고 session_id는 CLI 세션마다 새로 발급 → 키 누적. **v2에서 union 판정으로 재설계해 해소** |
| P4 | worktree 부트스트랩 비용 ≈ 0 | 참(단서) | DB fallback 하드코딩, 전역 python, 정적 자산 커밋됨. 단 **커밋된 상태 기준** — 메인 트리 미커밋/미추적 파일은 넘어가지 않음(문서화) |
| P5 | 훅이 worktree를 root로 인식 | 참 | Claude 훅=훅 파일 위치, Cursor 훅=workspace_roots (Eng 검증). Codex 창은 훅 없음 → ledger 미기록 → push 시 ask 유지(정상 동작) |
| P6 | 명시적 충돌 > 무언 레이스 | 조건부 | 핫파일(최근 200커밋 churn 상위: tablet 계약테스트 2종·layout_head·tablet-bundle.css)은 rebase 충돌 다발 예상 → **핫파일 작업은 공유 트리 직렬화 규칙**(Task 5) |
| P7 | 선택 도구를 사람이 기억해 쓴다 | 리스크 | `.cursor/worktrees/FOMS/*` 4개가 2026-01부터 detached 방치 = 같은 조작자가 worktree 도구를 버린 전례 → **kill criteria** 로 관리 |
| P8 | 동시 dev 서버가 필요하다 | 약함 | PORT는 충돌 위생일 뿐. 공유 PG·R2라 E2E 검증은 단일 서버 원칙 유지(문서화). run.py 기동 자체가 공유 DB에 DDL을 치는 문제는 Task 3에서 차단 |

**착수 조건(승인 게이트):** 지난 2주간 "두 창이 같은 시간대에 코드를 편집한" 작업이 3건 미만이면 Phase 1 축소 재검토(역할 분리 규칙 1줄로 대체하는 안이 CEO 보이스 권고). 3건 이상이면 본 플랜 진행.

**Kill criteria:** 도입 4주 후 usage 로그(`docs/harness/runtime/session_worktree_usage.log`) 기준 `create` 누계 3회 미만이면 CLI를 삭제하고 문서 절차만 남긴다.

## Global Constraints

- worktree 부모: `c:/tmp` / 경로 프리픽스 `foms-s-` / 브랜치 프리픽스 `session/` (기존 `foms-deploy-own-*`·`foms-prod-own-*`와 구분)
- 동시 세션 worktree 권장 상한 **2–3** (초과 시 경고 — 스펙 §2.6 계승)
- **강제 아님**: 단일 창·한 줄 수정·탐색·**핫파일 4종 작업**은 공유 메인 트리
- **DB/포트 격리는 Phase 2 비범위**. 단 (a) PORT env, (b) 세션 worktree에서 startup DDL 자동 차단, (c) alembic 코드 가드는 본 플랜 포함(공유 DB 오염 방지 최소선)
- rebase/cherry-pick 충돌 임의 해결 금지 (기존 guard 규칙)
- `.cursor/worktrees/**`·`foms-deploy-own-*`·`foms-prod-*`는 본 도구 불가침 (보고만)
- 커밋 메시지 한글 `git commit -F` / 신규 함수 docstring·타입힌트 필수
- **CLI·테스트 전부 UTF-8 강제** — 이 머신 콘솔은 cp949, 미처리 시 한글 출력에서 UnicodeDecodeError (Eng 실측)

## 리서치 확정 사실 (파일:라인 근거 있는 것만 — 휘발성 스냅샷 제외)

| 사실 | 근거 |
|------|------|
| ledger 경로 `<root>/docs/harness/runtime/session_commit_ledger.json`, gitignore → worktree별 독립 | `session_commit_ledger.py:18-20`, `.gitignore:110` |
| ledger 공개 API: `load_ledger/save_ledger/append_commit/normalize_session_id/session_shas/sha_in_list`; `_now_iso()`=tz-aware UTC | `session_commit_ledger.py:33,51,62,68,91,110,23` |
| scope 판정: `classify_deploy_scope(project_root, session_id) -> ScopeResult(kind, shas, foreign_shas, label)`, kind ∈ empty/own/foreign/unknown; **현재 세션 단일 기준** | `deploy_push_scope.py:14-24,60-109` |
| guard: deploy push → `_classify_deploy_push_scope`, 예외 시 ask 격상; `git worktree`는 미분류(allow) | `guard_policy.py:234-252,296-313,347-366` |
| commit ledger 기록 훅: 커맨드에 `"git commit"` 포함 시만 — `git cherry-pick`은 기록 안 됨(= cherry-pick 유입 커밋은 ledger 밖) | `record_commit_ledger.py:37`, `record_git_commit_ledger.py:21-33` |
| pytest는 이미 sqlite 격리 — DB 오염은 원래 없음 | `tests/conftest.py:9` |
| run.py 기동 시 startup task가 공유 DB에 DDL(init_db·컬럼 ensure·safe_migration) 실행; 플래그는 reloader 중복 방지용뿐 env opt-out 없음; 포트 5000 하드코딩 2곳 | `run.py:99-140,206,170,181` |
| 운영은 gunicorn(Procfile/railway.toml) — run.py·PORT 변경의 운영 영향 없음 | Eng 검증 |
| `pre_push_smoke.ps1` `$PSScriptRoot` 기준 + PATH python → worktree 무수정 동작; `verify_result.py` cwd 비의존; `ci_watch.py`는 worktree 루트에서 실행 필요 | `pre_push_smoke.ps1:51-52,98`, `verify_result.py:30-33`, `ci_watch.py:90-125` |
| worktree porcelain: detached 항목은 `branch` 줄 없이 `detached` 줄; locked 항목은 `locked` 줄 | git 문서 + Eng 실측 |
| `push_own_session_commits._cleanup`이 Windows 파일락 대응 패턴(check=False + rmtree) 보유 | `push_own_session_commits.py:148-153` |
| 네이티브 대안: Claude Code EnterWorktree/ExitWorktree(트리 dirty면 삭제 거부 기본), Agent `isolation:"worktree"` 실존 | 하네스 도구 목록 확인 |

## File Structure

- Modify: `tools/harness/session_commit_ledger.py` — 공개 함수 3개 추가 (Task 1)
- Modify: `tools/harness/deploy_push_scope.py` — 세션 worktree union 판정 (Task 1)
- Create: `tools/harness/session_worktree.py` — 수명주기 CLI (Task 2)
- Create: `tests/harness/test_session_worktree.py` — 계약 중심 테스트 (Task 1·2)
- Modify: `run.py` — PORT env + startup task 가드 (Task 3)
- Modify: `migrations/env.py` — 세션 worktree alembic 차단 (Task 4)
- Modify: `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/00-project-context.mdc` / `docs/harness/policy/DECISIONS.md` / 스펙 §2.6 링크 (Task 5)

v1의 `.worktreeinclude` 파일·글롭 엔진·SessionStart advisory·settings.local.json 정리·잔존 worktree 실사는 **삭제 또는 분리** — 부록 A·B 참조.

---

### Task 1: ledger·scope SSOT 확장 — union 소유 판정 + 계약 테스트

**모델 티어:** 표준(opus). 이 플랜의 핵심 가치가 이 태스크다.

**Files:**
- Modify: `tools/harness/session_commit_ledger.py` (함수 3개 추가)
- Modify: `tools/harness/deploy_push_scope.py` (import + 분기 1개)
- Test: `tests/harness/test_session_worktree.py` (신규 — scope 계약 파트)

**Interfaces:**
- Produces: `all_known_shas(project_root: str) -> list[str]` / `latest_session_id(project_root: str) -> str | None` / `set_session_shas(project_root: str, session_id: str | None, shas: list[str]) -> None` — Task 2의 sync가 사용
- Produces: `classify_deploy_scope`가 세션 worktree(경로 basename `foms-s-*`)에서는 **전 세션 union** 기준으로 own/foreign 판정. ledger가 빈 worktree(훅 없는 Codex 창)는 기존 unknown 경로 폴백(=ask 유지)

**설계 근거(구현자 필독):** worktree-로컬 ledger에는 "이 worktree에서 `git commit`으로 만든 커밋"만 쌓인다(훅이 명령 문자열로 감지, cherry-pick은 미기록). 따라서 union ⊇ push 범위 ⇔ 전부 이 창 계보 = own. cherry-pick/merge로 유입된 타 세션 커밋은 union에 없어 foreign → ask가 유지된다(Phase 0 의미 보존). 세션 키가 며칠 새 여러 개 쌓여도(P3 거짓 문제) union이라 무관.

- [ ] **Step 1: 실패 테스트 작성** — `tests/harness/test_session_worktree.py` 신규:

```python
"""세션 worktree 격리 Phase1 — scope 계약 + CLI 통합 테스트."""
import os
import subprocess
import sys
from pathlib import Path

import pytest

HARNESS = Path(__file__).resolve().parents[2] / "tools" / "harness"
SW = HARNESS / "session_worktree.py"
sys.path.insert(0, str(HARNESS))


def _run(cwd: Path, *args: str) -> subprocess.CompletedProcess:
    """CLI 실행 — 자식은 PYTHONUTF8=1로 cp949 사고 차단."""
    env = {**os.environ, "PYTHONUTF8": "1"}
    return subprocess.run(
        [sys.executable, str(SW), *args], cwd=cwd, env=env,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True,
        encoding="utf-8", errors="replace", check=True,
    )
    return r.stdout.strip()


@pytest.fixture()
def repo(tmp_path: Path) -> Path:
    """bare origin + deploy 브랜치 작업 클론 (origin/deploy 추적 ref 포함)."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "--bare", str(origin)], check=True, capture_output=True)
    work = tmp_path / "work"
    subprocess.run(["git", "clone", str(origin), str(work)], check=True, capture_output=True)
    _git(work, "config", "user.email", "t@t")
    _git(work, "config", "user.name", "t")
    (work / "a.txt").write_text("1", encoding="utf-8")
    _git(work, "add", "a.txt")
    _git(work, "commit", "-m", "init")
    _git(work, "branch", "-M", "deploy")
    _git(work, "push", "-u", "origin", "deploy")
    return work


def _make_wt(repo: Path, tmp_path: Path, name: str) -> Path:
    r = _run(repo, "create", "--name", name, "--parent", str(tmp_path / "wts"))
    assert r.returncode == 0, r.stderr
    wt = tmp_path / "wts" / f"foms-s-{name}"
    _git(wt, "config", "user.email", "t@t")
    _git(wt, "config", "user.name", "t")
    return wt


def _commit(wt: Path, fname: str, msg: str) -> str:
    (wt / fname).write_text(fname, encoding="utf-8")
    _git(wt, "add", fname)
    _git(wt, "commit", "-m", msg)
    return _git(wt, "rev-parse", "HEAD")


# ---- scope 계약 (Task 1) ----

def test_scope_union_own_across_sessions(repo: Path, tmp_path: Path) -> None:
    """세션 키가 여러 개 쌓여도 union이면 own — P3 거짓 문제의 해법 검증."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u1")
    s1 = _commit(wt, "b.txt", "day1")
    scl.append_commit(str(wt), "sid-day1", s1)
    s2 = _commit(wt, "c.txt", "day2")
    scl.append_commit(str(wt), "sid-day2", s2)
    # 오늘의 새 세션 id로도 own (union 규칙)
    assert classify_deploy_scope(str(wt), "sid-day3").kind == "own"


def test_scope_flags_unledgered_as_foreign(repo: Path, tmp_path: Path) -> None:
    """ledger 밖 커밋(cherry-pick/merge 유입 재현)은 foreign — 세탁 경로 차단 검증."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u2")
    s1 = _commit(wt, "b.txt", "mine")
    scl.append_commit(str(wt), "sid1", s1)
    _commit(wt, "d.txt", "foreign-like")  # ledger 미기록
    assert classify_deploy_scope(str(wt), "sid1").kind == "foreign"


def test_scope_empty_ledger_falls_back_to_unknown(repo: Path, tmp_path: Path) -> None:
    """훅 없는 창(Codex) 재현: ledger 없음 → 기존 unknown 경로(=ask) 유지."""
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "u3")
    _commit(wt, "b.txt", "no-hook")
    assert classify_deploy_scope(str(wt), "some-sid").kind == "unknown"
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/harness/test_session_worktree.py -k scope -v` / Expected: FAIL (`session_worktree.py` 없음 → `_make_wt` 실패; CLI 스텁을 Task 2 전에 만들 수 없으므로 **이 3건은 Task 2 완료 후 PASS가 정의** — Task 1 단계에서는 아래 Step 3 함수 단위로 임시 검증: `python -c "from session_commit_ledger import all_known_shas, set_session_shas, latest_session_id; print('API_OK')"`)

- [ ] **Step 3: 구현** — `session_commit_ledger.py` 말미에 추가:

```python
def all_known_shas(project_root: str) -> list[str]:
    """모든 세션의 SHA 합집합.

    세션 worktree 소유 판정용: worktree-로컬 ledger에는 이 worktree에서
    만든 커밋만 쌓이므로 union ⊇ push 범위 ⇔ own.
    """
    data = load_ledger(project_root)
    out: list[str] = []
    for entry in data.get("sessions", {}).values():
        out.extend(s for s in entry.get("shas", []) if isinstance(s, str))
    return out


def latest_session_id(project_root: str) -> str | None:
    """updated_at이 가장 최근인 세션 id. 세션이 없으면 None."""
    sessions = load_ledger(project_root).get("sessions", {})
    if not sessions:
        return None
    return max(sessions.items(), key=lambda kv: kv[1].get("updated_at", ""))[0]


def set_session_shas(project_root: str, session_id: str | None, shas: list[str]) -> None:
    """세션의 SHA 목록을 통째로 교체한다 (rebase 후 갱신 전용).

    스키마·타임스탬프(_now_iso, tz-aware UTC)는 이 SSOT가 관리한다 —
    외부에서 ledger dict를 직접 재작성하지 말 것.
    """
    sid = normalize_session_id(session_id)
    data = load_ledger(project_root)
    data.setdefault("sessions", {})[sid] = {
        "shas": [s.strip().lower() for s in shas if s and s.strip()],
        "updated_at": _now_iso(),
    }
    save_ledger(project_root, data)
```

`deploy_push_scope.py` — `import os` 추가, import 줄에 `all_known_shas` 추가, `classify_deploy_scope`의 `if not shas:` 블록 직후에 삽입:

```python
    if _is_session_worktree(project_root):
        union = all_known_shas(project_root)
        if union:
            foreign = tuple(s for s in shas if not sha_in_list(s, union))
            if not foreign:
                return ScopeResult("own", shas, (), "")
            preview = ", ".join(s[:8] for s in foreign[:5])
            return ScopeResult(
                "foreign",
                shas,
                foreign,
                (
                    f"세션 worktree ledger 밖 커밋({len(foreign)}/{len(shas)}: {preview}) "
                    f"— cherry-pick/merge 유입 여부 확인 필요"
                ),
            )
        # ledger가 빈 worktree(훅 미작동 창) → 아래 기존 세션 단일 기준으로 폴백
```

모듈 레벨 헬퍼 추가:

```python
def _is_session_worktree(project_root: str) -> bool:
    """세션 worktree(c:/tmp/foms-s-*) 여부 — 경로 basename 프리픽스 판정."""
    return os.path.basename(os.path.normpath(project_root)).startswith("foms-s-")
```

- [ ] **Step 4: 검증** — `python -c "import app; print('APP_OK')"` + 기존 가드 회귀: `python -m pytest tests/harness -k "deploy_push or guard" -v` (기존 스위트 존재 시) PASS
- [ ] **Step 5: 커밋** — `feat: 세션 worktree union 소유 판정 — ledger SSOT 확장`

---

### Task 2: `session_worktree.py` — 수명주기 CLI + 통합 테스트

**모델 티어:** 표준(opus).

**Files:**
- Create: `tools/harness/session_worktree.py`
- Test: `tests/harness/test_session_worktree.py` (Task 1 파일에 추가)

**Interfaces:**
- Consumes: Task 1의 `all_known_shas/latest_session_id/set_session_shas`, `sha_in_list`
- Produces: CLI `create [--name N] [--parent DIR]` / `list` / `sync [--path WT] [--ledger-only] [--allow-foreign]` / `cleanup [--remove] [--force-path WT --yes]`
- Exit codes: `0` ok / `2` refuse(사용법·소유 불명·비대상) / `3` rebase 충돌·진행 중 / `4` git 실패

**안전 규칙(절대):**
1. cleanup 기본은 **보고 전용(dry-run)** — 실제 제거는 `--remove` 명시. 자동 제거 대상은 clean AND merged AND `session/*` 브랜치 AND 비잠금(locked 줄 없음)만.
2. cwd가 대상 내부면 스킵(제거가 셸 cwd·훅 파괴 — 실사고 메모리).
3. 안전 경로는 **무-force remove + `branch -d`**. 실패 시 keep 보고(전파 금지 — push_own의 check=False 패턴).
4. `--force-path`는 `--yes` 동반 필수 + 제거 전 dirty 변경 `git stash create` SHA 출력 + 브랜치 백업 ref(`backup/...`) 생성 + **브랜치는 보존**.
5. detached·비세션 브랜치·`.cursor/worktrees/**`·`foms-deploy-own-*`·`foms-prod-*`는 불가침(보고만).
6. 모든 stdout/stderr UTF-8 reconfigure(cp949 사고 차단).

- [ ] **Step 1: 실패 테스트 추가** (Task 1 파일에 이어서):

```python
# ---- CLI (Task 2) ----

def test_create_makes_worktree_and_branch(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t1")
    assert wt.is_dir()
    assert _git(wt, "rev-parse", "--abbrev-ref", "HEAD") == "session/t1"


def test_create_refuses_existing_branch(repo: Path, tmp_path: Path) -> None:
    """-b + 사전 존재 검사 — 기존 세션 브랜치 리셋으로 커밋 유실 방지(-B 금지) 검증."""
    _make_wt(repo, tmp_path, "t2")
    r = _run(repo, "create", "--name", "t2", "--parent", str(tmp_path / "wts2"))
    assert r.returncode == 2
    assert "이미 존재" in (r.stdout + r.stderr)


def test_list_includes_detached(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t3")
    _git(wt, "checkout", "--detach")
    r = _run(repo, "list")
    assert r.returncode == 0
    assert "(detached)" in r.stdout


def test_sync_rebases_and_scope_is_own(repo: Path, tmp_path: Path) -> None:
    """핵심 계약: origin/deploy 전진 → sync → rebase 완료 + scope=own."""
    import session_commit_ledger as scl
    from deploy_push_scope import classify_deploy_scope

    wt = _make_wt(repo, tmp_path, "t4")
    old = _commit(wt, "b.txt", "session work")
    scl.append_commit(str(wt), "sid1", old)
    # 타 세션의 deploy 전진 재현
    (repo / "a.txt").write_text("2", encoding="utf-8")
    _git(repo, "add", "a.txt")
    _git(repo, "commit", "-m", "other session")
    _git(repo, "push", "origin", "deploy")
    r = _run(wt, "sync")
    assert r.returncode == 0, r.stderr
    assert _git(wt, "rev-parse", "HEAD") != old
    assert classify_deploy_scope(str(wt), "sid1").kind == "own"


def test_sync_refuses_unledgered_commits(repo: Path, tmp_path: Path) -> None:
    """ledger 밖 커밋 포함 시 sync 거부 — 세탁 경로 차단."""
    wt = _make_wt(repo, tmp_path, "t5")
    _commit(wt, "b.txt", "unledgered")
    r = _run(wt, "sync")
    assert r.returncode == 2
    assert "ledger 밖" in (r.stdout + r.stderr)


def test_sync_refuses_outside_session_worktree(repo: Path) -> None:
    r = _run(repo, "sync")
    assert r.returncode == 2


def test_cleanup_default_is_dry_run(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t6")
    r = _run(repo, "cleanup")
    assert r.returncode == 0
    assert "[removable]" in r.stdout
    assert wt.exists()


def test_cleanup_remove_flag_removes_merged_clean(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t7")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0, r.stderr
    assert not wt.exists()
    assert "session/t7" not in _git(repo, "branch", "--list", "session/t7")


def test_cleanup_keeps_dirty(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t8")
    (wt / "wip.txt").write_text("wip", encoding="utf-8")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
    assert "dirty" in r.stdout


def test_cleanup_keeps_unmerged(repo: Path, tmp_path: Path) -> None:
    wt = _make_wt(repo, tmp_path, "t9")
    _commit(wt, "c.txt", "unmerged work")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
    assert "unmerged" in r.stdout


def test_cleanup_keeps_non_session_branch(repo: Path, tmp_path: Path) -> None:
    """디렉터리명이 foms-s-*여도 브랜치가 session/*이 아니면 불가침."""
    wt = _make_wt(repo, tmp_path, "t10")
    _git(wt, "checkout", "-b", "experiment/x")
    r = _run(repo, "cleanup", "--remove")
    assert r.returncode == 0
    assert wt.exists()
```

- [ ] **Step 2: 실패 확인** — Run: `python -m pytest tests/harness/test_session_worktree.py -v` / Expected: 전건 FAIL(CLI 없음)

- [ ] **Step 3: 구현** — `tools/harness/session_worktree.py` 전문:

```python
"""세션별 worktree 격리 (Phase 1) 수명주기 CLI.

create : origin/deploy 기반 세션 worktree + session/<name> 브랜치 생성
list   : 세션 worktree 현황(브랜치·ahead·dirty·locked·detached)
sync   : rebase origin/deploy + ledger 갱신 (소유 검증 후)
cleanup: 기본 dry-run 보고, --remove 시 clean+merged만 제거

설계 정본: docs/plans/2026-07-27-session-worktree-isolation-phase1.md
소유 판정은 deploy_push_scope의 세션 worktree union 규칙과 한 쌍이다.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
import os
from pathlib import Path

WT_PREFIX = "foms-s-"
BRANCH_PREFIX = "session/"
DEFAULT_PARENT = "c:/tmp" if os.name == "nt" else "/tmp"
SOFT_LIMIT = 3  # ponytail: 스펙 §2.6 동시 상한 2-3, 초과는 경고만
USAGE_LOG = os.path.join("docs", "harness", "runtime", "session_worktree_usage.log")

EXIT_OK = 0
EXIT_REFUSE = 2
EXIT_CONFLICT = 3
EXIT_GIT = 4


def _utf8_stdio() -> None:
    """Windows cp949 콘솔에서 한글 출력 깨짐/UnicodeDecodeError 차단."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError):
            pass


def _git(cwd: Path | str, *args: str, check: bool = True) -> tuple[int, str]:
    """git 실행. (returncode, stdout). check=True면 실패 시 사람이 읽는 에러 + SystemExit(EXIT_GIT)."""
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True,
        text=True, encoding="utf-8", errors="replace",
    )
    if check and proc.returncode != 0:
        print(f"[git-error] git {' '.join(args)}\n{(proc.stderr or '').strip()}", file=sys.stderr)
        raise SystemExit(EXIT_GIT)
    return proc.returncode, (proc.stdout or "").strip()


def repo_root() -> Path:
    """현재 cwd가 속한 저장소(또는 worktree)의 최상위 경로."""
    return Path(_git(Path.cwd(), "rev-parse", "--show-toplevel")[1]).resolve()


def session_worktrees(root: Path) -> list[dict]:
    """foms-s-* worktree 목록. 각 항목 {'path','branch'(None=detached),'locked'}."""
    _, out = _git(root, "worktree", "list", "--porcelain")
    items: list[dict] = []
    cur: dict | None = None
    for line in out.splitlines() + [""]:
        if line.startswith("worktree "):
            cur = {"path": Path(line[len("worktree "):]).resolve(), "branch": None, "locked": False}
        elif line.startswith("branch ") and cur is not None:
            cur["branch"] = line[len("branch refs/heads/"):]
        elif line.startswith("locked") and cur is not None:
            cur["locked"] = True
        elif line == "" and cur is not None:
            if cur["path"].name.startswith(WT_PREFIX):
                items.append(cur)
            cur = None
    return items


def _usage_log(root: Path, msg: str) -> None:
    """kill criteria 측정용 사용 로그 1줄 append. 실패는 경고만(기능 무영향)."""
    try:
        p = root / USAGE_LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')} {msg}\n")
    except OSError as exc:
        print(f"[warn] usage log 기록 실패: {exc}", file=sys.stderr)


def _range_shas(wt: Path) -> list[str]:
    """origin/deploy..HEAD SHA 목록(오래된 순, 소문자)."""
    _, out = _git(wt, "log", "--reverse", "--format=%H", "origin/deploy..HEAD")
    return [s.strip().lower() for s in out.splitlines() if s.strip()]


def _ledger():
    """session_commit_ledger 모듈 지연 로드 (harness 디렉터리 sys.path 주입)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import session_commit_ledger
    return session_commit_ledger


def cmd_create(args: argparse.Namespace) -> int:
    """origin/deploy 기반 세션 worktree 생성. 기존 브랜치 재사용 금지(-b)."""
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)  # 오프라인 허용
    if _git(root, "rev-parse", "--verify", "origin/deploy", check=False)[0] != 0:
        print("[error] origin/deploy ref 없음 — 네트워크 연결 후 재시도", file=sys.stderr)
        return EXIT_GIT
    existing = session_worktrees(root)
    if len(existing) >= SOFT_LIMIT:
        print(f"[warn] 세션 worktree {len(existing)}개 활성 — 권장 상한 {SOFT_LIMIT}. cleanup 권장.")
    name = args.name or time.strftime("s%m%d-%H%M%S")
    branch = f"{BRANCH_PREFIX}{name}"
    if _git(root, "rev-parse", "--verify", f"refs/heads/{branch}", check=False)[0] == 0:
        print(f"[refuse] 브랜치 {branch} 이미 존재 — 다른 이름 사용 또는 cleanup 후 재시도", file=sys.stderr)
        return EXIT_REFUSE
    parent = Path(args.parent)
    parent.mkdir(parents=True, exist_ok=True)
    wt = parent / f"{WT_PREFIX}{name}"
    _git(root, "worktree", "add", "-b", branch, str(wt), "origin/deploy")
    env_src = root / ".env"
    if env_src.is_file():
        shutil.copy2(env_src, wt / ".env")
        print("[warn] .env 사본 복사됨 — c:/tmp 시크릿 잔존 주의(cleanup이 함께 삭제)")
    _usage_log(root, f"create {wt}")
    print(f"[ok] worktree: {wt}")
    print(f"[ok] branch  : {branch} (base origin/deploy)")
    print("주의: 메인 트리의 미커밋/미추적 변경은 이 worktree로 넘어오지 않는다.")
    print(f"다음: cd {wt}  →  claude / Cursor 폴더 열기 / codex exec")
    print("dev 서버: PORT=5001 python run.py (세션 worktree는 startup DDL 자동 생략)")
    return EXIT_OK


def cmd_list(_args: argparse.Namespace) -> int:
    """세션 worktree 현황 출력."""
    root = repo_root()
    rows = session_worktrees(root)
    if not rows:
        print("(세션 worktree 없음)")
        return EXIT_OK
    for it in rows:
        wt, branch = it["path"], it["branch"] or "(detached)"
        code, ahead = _git(wt, "rev-list", "--count", "origin/deploy..HEAD", check=False)
        _, dirty = _git(wt, "status", "--porcelain", check=False)
        flags = ("locked " if it["locked"] else "") + ("dirty" if dirty else "clean")
        print(f"{wt}  {branch}  ahead={ahead if code == 0 else '?'}  {flags}")
    return EXIT_OK


def _rebase_in_progress(wt: Path) -> bool:
    """rebase-merge/rebase-apply 디렉터리 존재 여부 (worktree는 .git이 파일이라 --git-path 필수)."""
    for sub in ("rebase-merge", "rebase-apply"):
        _, p = _git(wt, "rev-parse", "--git-path", sub)
        pp = Path(p) if os.path.isabs(p) else wt / p
        if pp.exists():
            return True
    return False


def cmd_sync(args: argparse.Namespace) -> int:
    """fetch + rebase origin/deploy + ledger 갱신. 세션 worktree 전용.

    소유 검증: rebase 전 범위가 이 worktree ledger union의 부분집합일 때만
    진행한다 — cherry-pick/merge로 유입된 타 세션 커밋의 세탁 차단.
    """
    wt = Path(args.path).resolve() if args.path else repo_root()
    if not wt.name.startswith(WT_PREFIX):
        print("[refuse] sync는 세션 worktree(foms-s-*) 안에서만 동작한다", file=sys.stderr)
        return EXIT_REFUSE
    scl = _ledger()

    if _rebase_in_progress(wt):
        print("[refuse] rebase 진행 중 — 해결 후 `git rebase --continue`, 그 다음 `sync --ledger-only`", file=sys.stderr)
        return EXIT_CONFLICT
    _, dirty = _git(wt, "status", "--porcelain", check=False)
    if dirty and not args.ledger_only:
        print("[refuse] 미커밋 변경 존재 — 커밋 후 sync 재시도", file=sys.stderr)
        return EXIT_REFUSE

    pre = _range_shas(wt)
    union = scl.all_known_shas(str(wt))
    unknown = [s for s in pre if not scl.sha_in_list(s, union)]
    if unknown and not args.allow_foreign:
        print(f"[refuse] ledger 밖 커밋 {len(unknown)}개 — 이 worktree에서 만든 커밋이 아님(cherry-pick/merge 유입?):", file=sys.stderr)
        for s in unknown[:10]:
            print(f"  {s[:10]}", file=sys.stderr)
        print("  소유가 확실하면 --allow-foreign으로 명시 승인.", file=sys.stderr)
        return EXIT_REFUSE

    if not args.ledger_only:
        _git(wt, "fetch", "origin", "deploy")
        r = subprocess.run(["git", "rebase", "origin/deploy"], cwd=str(wt))
        if r.returncode != 0:
            print("[conflict] rebase 충돌 — 임의 해결 금지. 해결 → `git rebase --continue` → `sync --ledger-only`", file=sys.stderr)
            return EXIT_CONFLICT

    post = _range_shas(wt)
    sid = scl.latest_session_id(str(wt)) or "unknown"
    scl.set_session_shas(str(wt), sid, post)
    print(f"[ok] sync 완료 — ledger 갱신 session={sid}, {len(post)}커밋")
    return EXIT_OK


def cmd_cleanup(args: argparse.Namespace) -> int:
    """세션 worktree 정리. 기본 dry-run 보고, --remove 시 clean+merged만 제거."""
    root = repo_root()
    _git(root, "fetch", "origin", "deploy", check=False)
    cwd = Path.cwd().resolve()
    for it in session_worktrees(root):
        wt, branch, locked = it["path"], it["branch"], it["locked"]
        force_this = bool(args.force_path) and Path(args.force_path).resolve() == wt
        if cwd == wt or wt in cwd.parents:
            print(f"[keep] {wt} — 현재 셸 cwd 내부 (다른 창에서 실행)")
            continue
        if force_this:
            if not args.yes:
                print("[refuse] --force-path는 --yes 동반 필수 (미커밋 변경 영구 소실 경고)", file=sys.stderr)
                return EXIT_REFUSE
            _force_remove(root, wt, branch)
            continue
        if locked:
            print(f"[keep] {wt} — locked. 해제: git worktree unlock \"{wt}\"")
            continue
        if branch is None:
            print(f"[keep] {wt} — detached HEAD, 수동 확인 필요")
            continue
        if not branch.startswith(BRANCH_PREFIX):
            print(f"[keep] {wt} — 비세션 브랜치({branch}), 불가침")
            continue
        code, dirty = _git(wt, "status", "--porcelain", check=False)
        if code != 0:
            print(f"[keep] {wt} — 상태 조회 실패")
            continue
        merged = _git(root, "merge-base", "--is-ancestor", branch, "origin/deploy", check=False)[0] == 0
        if dirty:
            print(f"[keep] {wt} — dirty (미커밋 변경 존재)")
        elif not merged:
            print(f"[keep] {wt} — unmerged (origin/deploy 미반영 커밋)")
        elif not args.remove:
            print(f"[removable] {wt} ({branch}) — 실제 제거: cleanup --remove")
        else:
            _safe_remove(root, wt, branch)
    _git(root, "worktree", "prune", check=False)
    return EXIT_OK


def _safe_remove(root: Path, wt: Path, branch: str) -> None:
    """clean+merged worktree 무-force 제거 + branch -d. 실패는 keep 보고(전파 금지)."""
    code, _ = _git(root, "worktree", "remove", str(wt), check=False)
    if code != 0:
        print(f"[keep] {wt} — remove 실패(파일 락 추정), 다음 cleanup에서 재시도")
        return
    _git(root, "branch", "-d", branch, check=False)
    _usage_log(root, f"remove {wt}")
    print(f"[removed] {wt} ({branch})")


def _force_remove(root: Path, wt: Path, branch: str | None) -> None:
    """dirty/unmerged 강제 제거 — dirty는 stash create로 dangling 백업, 브랜치는 보존+백업 ref."""
    _, stash_sha = _git(wt, "stash", "create", check=False)
    if stash_sha:
        print(f"[backup] 미커밋 변경 dangling 커밋 {stash_sha} — 복구: git stash store {stash_sha}")
    else:
        print("[warn] stash create 결과 없음 — 미추적 신규 파일은 백업되지 않는다")
    if branch:
        stamp = time.strftime("%Y%m%d-%H%M%S")
        backup = f"backup/{branch.replace('/', '-')}-{stamp}"
        _git(root, "branch", backup, branch, check=False)
        print(f"[backup] 브랜치 백업 ref: {backup}")
    _git(root, "worktree", "unlock", str(wt), check=False)
    code, _ = _git(root, "worktree", "remove", "--force", str(wt), check=False)
    if code != 0 and wt.exists():
        shutil.rmtree(wt, ignore_errors=True)  # push_own_session_commits._cleanup과 동일 폴백
        _git(root, "worktree", "prune", check=False)
    _usage_log(root, f"force-remove {wt}")
    print(f"[removed:force] {wt} — 브랜치 보존({branch})")


def main(argv: list[str] | None = None) -> int:
    """CLI 엔트리포인트."""
    _utf8_stdio()
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create", help="세션 worktree 생성")
    c.add_argument("--name", default=None)
    c.add_argument("--parent", default=DEFAULT_PARENT)
    c.set_defaults(fn=cmd_create)
    ls = sub.add_parser("list", help="세션 worktree 현황")
    ls.set_defaults(fn=cmd_list)
    s = sub.add_parser("sync", help="rebase origin/deploy + ledger 갱신")
    s.add_argument("--path", default=None)
    s.add_argument("--ledger-only", action="store_true")
    s.add_argument("--allow-foreign", action="store_true")
    s.set_defaults(fn=cmd_sync)
    cl = sub.add_parser("cleanup", help="세션 worktree 정리 (기본 dry-run)")
    cl.add_argument("--remove", action="store_true")
    cl.add_argument("--force-path", default=None)
    cl.add_argument("--yes", action="store_true")
    cl.set_defaults(fn=cmd_cleanup)
    args = p.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인** — Run: `python -m pytest tests/harness/test_session_worktree.py -v` / Expected: 전건 PASS (Task 1 scope 3건 포함)
- [ ] **Step 5: 커밋** — `feat: 세션 worktree 수명주기 CLI — create/list/sync/cleanup`

---

### Task 3: `run.py` — PORT env + 세션 worktree startup DDL 차단 (소형)

**모델 티어:** 소형 — 오케스트레이터 직접(§4-1) 또는 저가(haiku). **Files:** Modify `run.py`

**근거:** dev 서버 기동만으로 `_run_startup_tasks`(`run.py:99-140`)가 공유 `furniture_orders`에 init_db·컬럼 ensure·safe_migration DDL을 실행한다. 세션 worktree(타 브랜치)에서 기동하면 공유 DB 스키마가 그 브랜치 기준으로 바뀐다 — alembic 금지 규칙만으로는 못 막는 구멍.

- [ ] **Step 1: 수정** — `run.py:203-206` 부근:

```python
    _is_reloader_child = (os.environ.get('WERKZEUG_RUN_MAIN') == 'true')
    _in_session_worktree = os.path.basename(os.path.dirname(os.path.abspath(__file__))).startswith('foms-s-')
    _skip_startup = os.environ.get('FOMS_SKIP_STARTUP_TASKS', '1' if _in_session_worktree else '0') == '1'
    _should_run_startup_tasks = ((not _use_reloader) or _is_reloader_child) and not _skip_startup
```

포트 — `_run_dev_server` 진입부에 1줄 + 리터럴 2곳 치환(`run.py:170,181`):

```python
    port = int(os.environ.get('PORT', '5000'))
```

`socketio.run(..., port=port, ...)` / `app.run(..., port=port, ...)`. 세션 worktree에서 `_skip_startup` 시 안내 1줄 출력: `print('[INFO] 세션 worktree — startup DDL 생략 (FOMS_SKIP_STARTUP_TASKS=0으로 강제 실행 가능)')`.

- [ ] **Step 2: 검증** — `python -c "import app; print('APP_OK')"` → APP_OK. 메인 트리 `python run.py` 기동 로그에 startup task 정상 수행 확인(회귀 없음) 후 즉시 종료.
- [ ] **Step 3: 커밋** — `feat: dev 서버 PORT env + 세션 worktree startup DDL 자동 생략`

---

### Task 4: `migrations/env.py` — 세션 worktree alembic 차단 (소형)

**모델 티어:** 소형 — 오케스트레이터 직접(§4-1). **Files:** Modify `migrations/env.py`

**근거:** "세션 worktree에서 alembic 금지"를 문서로만 두면 훅 없는 Codex 창에는 도달하지 않는다. 코드로 강제(리뷰 합의: 문서 대신 코드).

- [ ] **Step 1: 수정** — `migrations/env.py` 상단(load_dotenv 이후):

```python
from pathlib import Path as _Path

_repo_root = _Path(__file__).resolve().parents[1]
if _repo_root.name.startswith("foms-s-"):
    raise RuntimeError(
        "세션 worktree에서 alembic 실행 금지 — 공유 DB 스키마가 이 브랜치 기준으로 바뀐다. "
        "마이그레이션은 메인 트리에서 실행하라."
    )
```

- [ ] **Step 2: 검증** — 메인 트리에서 `python -m alembic heads` 정상 동작(차단 미발동) 확인.
- [ ] **Step 3: 커밋** — `feat: 세션 worktree alembic 실행 코드 차단`

---

### Task 5: 정책·문서 갱신

**모델 티어:** 오케스트레이터 직접(§4-3). **Files:** `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `docs/harness/policy/DECISIONS.md`, `docs/specs/2026-07-16-deploy-push-session-isolation-design.md`(§2.6에 구현 링크 1줄)

- [ ] **Step 1:** 공통 내용(각 파일 어조로 축약):
  - **세션 worktree 선택 표준**: 동시 2+창 코드 편집 시 `python tools/harness/session_worktree.py create` → 해당 폴더에서 Claude CLI(`cd` 후 `claude`, 또는 네이티브 EnterWorktree) / Cursor(폴더 열기) / Codex(`codex exec`, cwd=worktree). 단일 창·한 줄 수정·탐색·**핫파일(tablet 계약테스트 2종·layout_head.html·foms-tablet-bundle.css) 작업**은 공유 트리 유지. 권장 상한 2–3.
  - **deploy 반영**: worktree에서 `git push origin HEAD:deploy`(guard union 판정 → own=allow). non-fast-forward 시 `session_worktree.py sync` 후 재push. 충돌 임의 해결 금지. **Codex 창(훅 없음)은 ledger 미기록 → push 시 ask 정상 — "전체 포함 승인"은 그 worktree 커밋 전수 확인 후에만**.
  - **메인 트리 동기화**: worktree push 후 메인 트리 작업 착수 전 `git pull --ff-only origin deploy` (stale 베이스 커밋 방지).
  - **미이전 경고**: worktree는 origin/deploy 기준 — 메인 트리 미커밋/미추적 파일은 넘어가지 않는다.
  - **검증**: `ci_watch.py`는 worktree 루트에서 실행. E2E·SW 검증은 단일 서버 원칙 유지(PORT는 충돌 위생일 뿐).
  - **정리**: 세션 종료 시 `cleanup`(dry-run 확인 → `--remove`). `.cursor/worktrees/**` 수동 조작 금지.
  - DECISIONS.md 항목: `[2026-07-27] 세션 worktree 격리 Phase 1 (선택 표준, union 소유 판정)` — 결정·이유·비범위(DB/포트=Phase 2)·kill criteria.
- [ ] **Step 2: 커밋** — `docs: 세션 worktree 격리 Phase1 절차·정책 반영`

---

## 검증 계획 (전체)

1. `python -m pytest tests/harness/test_session_worktree.py -v` 전건 PASS (핵심 계약 `test_sync_rebases_and_scope_is_own` 포함)
2. `python -c "import app; print('APP_OK')"`
3. **실전 E2E(실데이터 원칙)**: 메인 트리에서 `create` → worktree에서 더미 커밋(훅 경유 = ledger 기록) → `git push origin HEAD:deploy` 시 guard hook 로그에서 own/allow 판정 확인 → push 취소(`--dry-run`) → `cleanup --remove`
4. push 전 `scripts/ops/pre_push_smoke.ps1` exit 0 → push → `python tools/harness/ci_watch.py` green (worktree 루트에서)

## 리스크 레지스터 (v2)

| 리스크 | 완화 |
|--------|------|
| 핫파일 동시 수정 → rebase 충돌 다발 | 핫파일 4종은 공유 트리 직렬화 규칙(Task 5). 충돌 시 sync가 절차 안내 |
| 공유 PG에 브랜치별 스키마 혼입 | 3중: startup DDL 자동 생략(Task 3) + alembic 코드 차단(Task 4) + 문서(Task 5) |
| cleanup이 타 창 활성 worktree 제거 | dry-run 기본 + `--remove` 명시 + cwd·locked·dirty·unmerged·detached·비세션브랜치 6중 keep 가드 |
| sync가 타 세션 커밋 세탁 | rebase 전 union 부분집합 검증 — ledger 밖 커밋은 refuse(--allow-foreign 명시 승인만) |
| rebase 후 ledger stale → push ask 오탐 | sync가 `set_session_shas`로 갱신 + scope는 union 판정이라 세션 키 누적 무관 |
| worktree 방치 누적 | cleanup fetch 후 merged 판정(stale ref 오탐 제거) + detached도 보고 + kill criteria 4주 측정 |
| cp949 콘솔 인코딩 | CLI `_utf8_stdio()` + 테스트 `PYTHONUTF8=1` |
| 도구 미채택(shelf-ware) | kill criteria: 4주 create<3 → CLI 삭제·문서 절차만 유지 |

## 부록 A — 본 플랜에서 분리된 항목

1. **`.claude/settings.local.json` 절대경로 stale 항목 정리** — worktree 대응이 아니라 순수 정리(추적 파일이라 worktree에도 복사됨은 확인됨). 별도 chore로 즉시 처리 가능.
2. **잔존 worktree 실사** — `.cursor/worktrees/FOMS/{dqy,egl,gry,uev}`(2026-01 구커밋 detached, staged backup SQL 방치)와 `c:/tmp` 승격 잔존물. **파괴적 — 사용자 개별 승인 필요.** 실시간 `git worktree list`로 재조회 후 진행(스냅샷 신뢰 금지 — 본 설계 세션 중에도 목록이 변했다).
3. **SessionStart advisory** — 삭제 결정(타이밍 부적절: 세션 시작 후 알림은 재시작 비용 때문에 무시됨 + 제시 코드가 기존 컨텍스트 주입을 죽이는 NameError 리스크). 문서 절차로 대체.
4. **`remove_worktree` 헬퍼 push_own_session_commits.py와 공용화** — 후속 리팩터(ponytail: 지금은 패턴 복사 6줄, 중복 3곳 되면 추출).

## 부록 B — Decision Audit Trail (autoplan)

| # | 판정 대상 (보이스#) | 분류 | 원칙 | 결정 |
|---|---------------------|------|------|------|
| 1 | 단일세션 전제 거짓 (CEO#1, Eng#13/14) | Mechanical | P1 | union 소유 판정으로 재설계 — ledger 재작성 소유 추론 폐기 |
| 2 | sync 세탁 경로 (CEO#6, Eng#2) | Mechanical | P1 | rebase 전 union 부분집합 검증, 위반 시 refuse |
| 3 | ledger dict 직접 재작성 (Eng#12) | Mechanical | P4 | `set_session_shas` SSOT 공개 함수로 이동, `_now_iso` 재사용 |
| 4 | 네이티브 재발명 (CEO#2) | **Taste→게이트** | P3/P5 | 슬림 CLI 유지 권고(sync·cleanup 로직은 코드 필요, Cursor/Codex는 네이티브 도구 없음). 대안(3줄 절차+네이티브)은 게이트에 제시 |
| 5 | cp949 테스트 전멸 (Eng#1) | Mechanical | P1 | `_utf8_stdio` + `PYTHONUTF8=1` |
| 6 | cleanup 타 창 파괴 (Eng#3) | Mechanical | P5 | dry-run 기본 + `--remove` 명시 (lock 자동화는 해제 시점 부재로 기각) |
| 7 | remove 실패 전파 (Eng#4) | Mechanical | P4 | check=False + rmtree 폴백 (push_own 검증 패턴) |
| 8 | 안전 경로 --force (Eng#5) | Mechanical | P5 | 무-force + branch -d |
| 9 | force 데이터 소실 (Eng#6, CEO#12) | Mechanical | P1 | stash create 백업 + backup ref + --yes + 브랜치 보존 |
| 10 | startup DDL 구멍 (Eng#7) | Mechanical | P1 | 세션 worktree 자동 생략 + env 오버라이드 |
| 11 | advisory NameError·타이밍 (Eng#8, CEO#9) | Mechanical | P1(YAGNI) | Task 삭제 — 문서 대체 |
| 12 | create -B 리셋 (Eng#10) | Mechanical | P1 | -b + 사전 존재 검사 refuse |
| 13 | detached 누락 (Eng#11, CEO#8) | Mechanical | P1 | 파서 branch=None 수집 + keep 보고 |
| 14 | cleanup fetch 부재 (CEO#7, Eng#19) | Mechanical | P1 | cleanup 첫 줄 fetch |
| 15 | .worktreeinclude YAGNI (CEO#11, Eng#16) | Mechanical | P1(YAGNI) | 엔진 삭제 — `.env` 존재 시 copy2 1줄 |
| 16 | alembic 문서 규칙 무력 (CEO#15) | Mechanical | P5 | migrations/env.py 코드 차단 |
| 17 | 핵심 계약 테스트 부재 (CEO#14, Eng#20) | Mechanical | P1 | `classify == own` 계약 테스트 3건 추가 |
| 18 | 핫파일 rebase 역효과 (CEO#5) | Mechanical | P3 | 핫파일 4종 공유 트리 직렬화 규칙 |
| 19 | 메인 트리 stale deploy (Eng... CEO#13) | Mechanical | P1 | ff-pull 규칙 문서화 |
| 20 | 스코프 과대 (CEO#16) | Mechanical | P3 | Task 6·8 분리(부록 A), 8태스크→5태스크 |
| 21 | 휘발성 사실 표 (CEO#17) | Mechanical | P5 | 스냅샷 행 제거, 실시간 조회 원칙 |
| 22 | kill criteria 부재 (CEO#18) | Mechanical | P6 | 4주 create<3 → 삭제 + usage 로그 |
| 23 | Goal 과장 (CEO#10) | Mechanical | P5 | "검증 오염"→"검증 대상 트리 오염"으로 정정, pytest DB 주장 삭제 |
| 24 | 직렬화 리프레임 (CEO#19) | **Taste→게이트** | — | 단일 보이스 제기(Codex 불가로 교차 검증 불가). 착수 조건 질문으로 게이트 상정 |
| 25 | SOFT_LIMIT 실효성 (CEO#20) | Taste(minor) | P6 | 경고 유지(스펙 계승) — 차단은 과잉 |

## 부록 C — GSTACK REVIEW REPORT

- **파이프라인**: gstack-autoplan, [subagent-only] 모드 (Codex CLI 0.125 ↔ 계정 기본 모델 `gpt-5.6-sol` 비호환으로 2회 실패 후 규정 격하. 복구: `codex` CLI 업그레이드)
- **CEO 보이스(Claude opus, 독립)**: 20건 — critical 2(단일세션 전제 거짓·네이티브 재발명), high 8, medium 8, low 2. 주장 실측 검증: ledger 35세션/11일 ✓, stash 40 ✓, conftest sqlite ✓, worktree 목록 세션 중 변동 ✓
- **Eng 보이스(Claude opus, 독립, 재현 검증 포함)**: 25건 — critical 3(cp949 테스트 전멸·sync 세탁·cleanup 타 창 파괴), high 7, medium 11, low 4. 플랜의 훅 root/worktree 안전성 주장은 검증 후 이상 없음 확인
- **합의 테이블**: 세탁 경로·cleanup 안전·detached 누락·YAGNI·계약 테스트 부재 → **양 보이스 일치(CONFIRMED)**. 전략 리프레임(직렬화)은 CEO 단독 → 게이트 상정
- **처리**: 25건 판정 전건 v2 반영(부록 B). 잔여 게이트 항목 2건은 사용자 결정 — (1) 착수 조건(동시 편집 빈도), (2) CLI vs 네이티브+절차 문서

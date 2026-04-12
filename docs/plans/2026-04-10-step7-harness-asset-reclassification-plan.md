# Step 7 Harness Asset Reclassification Plan

> 상태: completed
> 범위: Step 7 (`docs/context` + harness runtime asset reclassification)
> 기준 Spec: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`

## 1. 목표
Step 7의 목표는 `docs/context`와 하네스 런타임 자산을 더 명확한 역할 단위로 재분류해, 앞으로 하네스 관련 경로가 `policy / bundles / runtime / logs` 기준으로 일관되게 관리되도록 만드는 것이다.

이번 Step 7은 단순 문서 정리가 아니라, 실제 하네스 계약 경로를 함께 바꾸는 구조 배치다. 따라서 `tools/harness/*`, Cursor/Claude hook, `tests/harness/*`, CI workflow, 활성 정책 문서를 같은 실행 흐름에서 동기화한다.

## 2. 결정된 타겟 레이아웃

### 2.1 Canonical target
- `docs/harness/policy/`
  - `DECISIONS.md`
  - `INCIDENT_TEMPLATE.md`
- `docs/harness/bundles/`
  - `HARNESS_BUNDLE_CURSOR.md`
  - `HARNESS_BUNDLE_CURSOR_HARNESS.md`
  - `HARNESS_BUNDLE_CLAUDE.md`
  - `HARNESS_BUNDLE_CLAUDE_HARNESS.md`
  - `HARNESS_BUNDLE_CODEX.md`
  - `HARNESS_BUNDLE_CODEX_HARNESS.md`
- `docs/harness/runtime/`
  - `EDIT_LOG.md`
  - `SESSION_LOG.md`
  - `COMPACT_CHECKPOINT.md`
  - `.session_stop_idempotency.json`
  - `.post_task_qc_debounce.json`
- `docs/harness/logs/`
  - `SHELL_GUARD_LOG.md`
  - `HOOK_RUNTIME_LOG.txt`
  - `HOOK_PAYLOAD_DEBUG.jsonl`
  - `HOOK_RAW_DUMP.txt`
  - `.hook_debug_once`
  - `.hook_raw_once`
  - `hook_stdin_err.txt`

### 2.2 `docs/context` after Step 7
- `docs/context/`는 incident/reference 성격 문서를 유지한다.
- 예: `INCIDENT_*`, `RCA-*`, `ERP_DASHBOARD_SCRIPTS_HIGHLIGHTING.md`
- 전환 이후 `docs/context/README.md`를 추가해 active harness asset이 `docs/harness/*`로 이동했음을 명시한다.

## 3. 범위

### 3.1 포함
- `tools/harness/manifest.yaml`
- `tools/harness/profiles/*.yaml`
- `tools/harness/run_codex.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `tools/harness/prompt_router.py`
- `.cursor/hooks/*.py`
- `.claude/hooks/*.py`
- `.gitignore`
- `.gitattributes`
- `tests/harness/*`
- `.github/workflows/harness-ci.yml`
- 활성 정책/운영 문서: `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/*.md`, `.claude/commands/*.md`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`, 관련 harness spec
- tracked harness asset의 새 canonical 위치 생성 및 old path 정리

### 3.2 제외
- `.cursor/hooks.json`의 hook script 물리 경로 변경
- `app.py`, `start.sh`, `Procfile`, `railway.toml`, `migrations/*`, `db.py`, `models.py`
- `templates/`, `static/` 물리 경로 변경
- historical run-record/old plan 전체 문자열 일괄 치환
- `business_calendar` / `/calendar` 축 재도입

## 4. 핵심 원칙

### 4.1 One-step contract sync
- bundle output, hook read/write path, CI drift glob, ignore rules, harness tests는 같은 배치에서 같이 바꾼다.

### 4.2 Path centralization first
- hook는 `shared_utils.py`, Claude hook는 `.claude/hooks/shared_utils.py`, harness Python tooling은 `tools/harness/paths.py`를 통해 canonical path를 한 곳에서 계산한다.

### 4.3 Runtime vs log separation
- `EDIT_LOG.md`, `SESSION_LOG.md`, `COMPACT_CHECKPOINT.md`는 active state이므로 `runtime/`으로 간다.
- guard/debug/runtime diagnostic 산출물은 `logs/`로 간다.

### 4.4 Historical docs minimal-touch
- 과거 run-record는 당시 상태를 설명하므로 Step 7에서 무차별 경로 치환하지 않는다.
- 대신 active guide/spec/policy만 새 canonical path로 갱신한다.

## 5. 실행 배치

### Batch 71 — parallel pre-audit
- 병렬 agent로 현재 coupling, CI risk, taxonomy를 확정한다.
- 산출물: `docs/plans/2026-04-10-step7-batch71-preaudit-run-record.md`

### Batch 72 — plan freeze
- Step 7 타겟 레이아웃과 must-update-together 집합을 문서화한다.
- 산출물: 본 문서

### Batch 73 — path foundation
- `tools/harness/paths.py` 추가
- Cursor/Claude hook path helper 도입
- prompt_router / wrapper script의 hard-coded path를 canonical constant 기반으로 전환

### Batch 74 — asset relocation
- `docs/harness/{policy,bundles,runtime,logs}` canonical asset 생성
- manifest/profile/CI/.gitignore/.gitattributes 동기화
- tracked asset old path 제거

### Batch 75 — active docs sync + bundle regen
- 활성 guide/rule/agent/command/spec 문서의 active path를 갱신
- `python tools/harness/build_context_bundle.py --all`로 bundle 재생성

### Batch 76 — post-audit closeout
- harness tests + shared baseline + APP_OK + full pytest 재검증
- AI_STATUS / ARCHIVE_INDEX / COMPACT_CHECKPOINT / root governance spec 갱신

## 6. 검증 게이트
- `python -m compileall -q .cursor/hooks`
- `python -m pytest tests/harness -q`
- `python tools/harness/verify_result.py --json`
- `python tools/harness/build_context_bundle.py --all`
- `python -c "import app; print('APP_OK')"`
- `python -m pytest -q`
- `ReadLints` for changed files
- `git status --short`로 new tracked local/log/generated drift 확인

## 7. 중단 조건
- hook가 old/new path split-brain 상태가 되면 즉시 중단
- bundle generated path와 CI drift glob이 어긋나면 즉시 중단
- `run_codex.ps1` / `run_gstack_qa.ps1` 기본 bundle path가 깨지면 즉시 중단
- 예상 밖의 runtime boot regression이 보이면 Step 7 범위를 줄이고 후속 batch로 분리

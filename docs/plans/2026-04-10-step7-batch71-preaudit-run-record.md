# Step 7 Batch 71 Pre-Audit Run Record

> 단계: Step 7
> 배치: Batch 71
> 상태: completed
> 목적: `docs/context` 및 harness runtime asset 재분류 전 coupling / risk / canonical target 확정

## 1. 수행 범위
- `docs/context/*`
- `tools/harness/*`
- `.cursor/hooks/*.py`
- `.claude/hooks/*.py`
- `tests/harness/*`
- `.github/workflows/*`
- active harness guide/rule/agent 문서

## 2. 동원 자원
- parallel explore agents
- code review agent
- devops/deploy 관점 점검
- context-manager 관점 점검
- repo-local code search + targeted file read

## 3. 핵심 발견

### 3.1 `docs/context`는 이미 runtime contract의 일부다
단순 참고 문서 디렉토리가 아니라 아래 축이 직접 의존하고 있었다.
- harness manifest/profile output
- Codex/QA PowerShell wrapper 기본 bundle path
- prompt_router의 harness path classification
- Cursor/Claude hook read/write path
- harness CI drift glob
- harness smoke/unit test fixture
- gitignore/gitattributes rule

### 3.2 하드코딩 지점이 넓게 퍼져 있다
대표 경로 의존 파일:
- `tools/harness/manifest.yaml`
- `tools/harness/profiles/*.yaml`
- `tools/harness/run_codex.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `tools/harness/prompt_router.py`
- `.cursor/hooks/shared_utils.py`
- `.cursor/hooks/session_stop.py`
- `.cursor/hooks/track_edits.py`
- `.cursor/hooks/pre_compact.py`
- `.cursor/hooks/auto_memory.py`
- `.cursor/hooks/session_start.py`
- `.cursor/hooks/post_task_quality_check.py`
- `.cursor/hooks/guard_shell.py`
- `.cursor/hooks/hook_payload_debug.py`
- `.claude/hooks/*.py`
- `tests/harness/test_context_bundle.py`
- `tests/harness/test_hooks_smoke.py`
- `.github/workflows/harness-ci.yml`
- `.gitignore`
- `.gitattributes`

### 3.3 활성 문서도 새 canonical path를 따라가야 한다
다음 문서는 historical run-record가 아니라 현재 운영 기준 문서라 갱신 필요:
- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/00-project-context.mdc`
- `.cursor/agents/grand-develop-master.md`
- `.cursor/agents/context-manager.md`
- `.claude/commands/{gdm,status,review}.md`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- 관련 harness spec 일부

## 4. taxonomy 결정

### 4.1 채택안
`docs/harness/{policy,bundles,runtime,logs}` + `docs/context`는 incident/reference 축 유지

### 4.2 채택 이유
- root governance spec 방향과 일치
- harness asset과 incident/reference 문서를 개념적으로 분리 가능
- future path drift를 줄이고 명확한 canonical home을 만든다

## 5. preserved tracked asset
구현 전 현재 내용을 읽어 보존 대상으로 확정한 tracked 파일:
- `docs/context/DECISIONS.md`
- `docs/context/INCIDENT_TEMPLATE.md`
- `docs/context/COMPACT_CHECKPOINT.md`
- `docs/context/SESSION_LOG.md`
- `docs/context/EDIT_LOG.md`
- `docs/context/SHELL_GUARD_LOG.md`
- `docs/context/INCIDENT_URGENT_NOTIFICATION_NOT_DELIVERED_2026-03-04.md`

정책:
- active tracked asset은 새 canonical 위치로 이동/재생성
- incident record는 `docs/context`에 남긴다
- historical plan/run-record는 Step 7에서 일괄 치환하지 않는다

## 6. 리스크

### high
- bundle path와 CI drift glob 미동기화
- hook old/new path split-brain
- `run_codex.ps1` default bundle path break

### medium
- prompt_router harness path classifier 누락
- tests fixture가 old path를 계속 가리킴
- ignore rule이 old path만 무시해 runtime junk가 tracked 상태로 노출

## 7. 결론
Step 7은 conservative subdir move보다, single coordinated contract sync가 더 안전하다. 다음 배치에서 plan freeze 후 path foundation과 asset relocation을 한 흐름으로 실행한다.

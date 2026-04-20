# Step 7 Batch 76 Run Record
> 작성일: 2026-04-11
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 문서: `docs/plans/2026-04-10-step7-harness-asset-reclassification-plan.md`, `docs/plans/2026-04-10-step7-batch71-preaudit-run-record.md`

- 일시: 2026-04-11
- 브랜치: `deploy`
- 실행자: AI agent
- 목적: Step 7(`docs/context` 및 harness runtime asset 재분류)의 후감리 verdict를 정리하고 상태 문서를 closeout한다
- 제외 축: 사용자 지시대로 `business_calendar` / `/calendar` 축은 계속 범위 밖으로 유지

## 1. 전체 판정
**Verdict: Step 7 closeout completed, harness asset reclassification is closed**

이유:
- `docs/context`에 섞여 있던 하네스 자산을 `docs/harness/{policy,bundles,runtime,logs}` canonical taxonomy로 재배치했다.
- `tools/harness/*`, Cursor/Claude hook, `tests/harness/*`, `.github/workflows/harness-ci.yml`, `.gitignore`, `.gitattributes`, active guide/rule/agent/command/spec 문서를 새 canonical path로 동기화했다.
- `python tools/harness/build_context_bundle.py --all`, `python -m pytest tests/harness/test_context_bundle.py tests/harness/test_hooks_smoke.py -q`, `python -m pytest -q`, `python -c "import app; print('APP_OK')"`, `python tools/harness/verify_result.py --json`, `ReadLints`까지 재통과했다.
- `docs/context`는 incident/reference 기록만 남기고 harness policy/runtime/generated 자산은 old path에서 제거했다.

## 2. 실제 변경 범위
- `tools/harness/paths.py`
- `tools/harness/prompt_router.py`
- `tools/harness/manifest.yaml`
- `tools/harness/profiles/*.yaml`
- `tools/harness/run_codex.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `.cursor/hooks/*.py`
- `.claude/hooks/*.py`
- `tests/harness/test_context_bundle.py`
- `tests/harness/test_hooks_smoke.py`
- `.gitignore`
- `.gitattributes`
- `.github/workflows/harness-ci.yml`
- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/*.mdc`
- `.cursor/agents/*.md`
- `.claude/commands/*.md`
- `.claude/agents/context-manager.md`
- `.agents/workflows/start-task.md`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- `docs/specs/2026-04-05-harness-auto-entry-routing_SPEC.md`
- `docs/specs/2026-04-05-harness-post-audit-hardening_SPEC.md`
- `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`
- `docs/specs/2026-04-06-harness-tracking-cleanup_SPEC.md`
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
- `docs/plans/2026-04-07-phase1-baseline-matrix.md`
- `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
- `docs/plans/2026-04-10-step7-harness-asset-reclassification-plan.md`
- `docs/plans/2026-04-10-step7-batch76-closeout-run-record.md`
- `docs/harness/`
- `docs/context/` (harness asset 제거)
- `docs/AI_STATUS.md`
- `docs/ARCHIVE_INDEX.md`

## 3. 사후감리 요약

### 3.1 결과 해석
- Step 7의 핵심 목표였던 “하네스 자산의 역할별 분리”가 실제 파일 이동과 계약 경로 동기화까지 포함해 완료됐다.
- `docs/harness/policy/`는 decision/template, `docs/harness/bundles/`는 generated bundle, `docs/harness/runtime/`은 session/edit/checkpoint/state, `docs/harness/logs/`는 hook/shell debug log의 canonical source가 됐다.
- `docs/context`는 더 이상 harness runtime dump 저장소가 아니며, incident/RCA/reference 문서만 남는 축으로 정리됐다.

### 3.2 migration detail
- `EDIT_LOG.md`는 old/new split-brain을 피하기 위해 새 canonical 파일에 최근 50개 window 기준으로 병합 보존했다.
- `COMPACT_CHECKPOINT.md`는 새 경로 쪽이 더 최신이어서 해당 파일을 canonical로 유지하고 old path 사본만 제거했다.
- `HOOK_PAYLOAD_DEBUG.jsonl`, `HOOK_RAW_DUMP.txt`는 새 경로에서 생성된 임시 최신 로그를 backup 후 old historical 로그에 재부착해 연속성을 보존했다.
- generated bundle은 old 파일을 단순 복사하지 않고 `build_context_bundle.py --all`로 재생성해 source-of-truth와 drift를 다시 맞췄다.

### 3.3 residual risk
- `docs/context/...` 문자열은 일부 historical run-record / 과거 계획 / runtime log 안에 남아 있다. 이것은 당시 상태를 설명하는 기록으로 Step 7 계획의 minimal-touch 원칙에 따라 유지했다.
- `docs/harness/runtime/SESSION_LOG.md`, `docs/harness/logs/HOOK_RAW_DUMP.txt`, `docs/harness/policy/DECISIONS.md` 안의 과거 경로 문자열은 historical fact이며 current canonical contract를 뜻하지 않는다.
- `business_calendar` / `/calendar` 축은 사용자 지시대로 이번 단계에서도 끝까지 제외했다.

## 4. 최종 검증 결과

### 4.1 hook compile smoke
- 실행:
  - `python -m compileall -q ".cursor/hooks"`
- 결과:
  - 성공

### 4.2 harness-focused tests
- 실행:
  - `python -m pytest tests/harness/test_context_bundle.py tests/harness/test_hooks_smoke.py -q`
- 결과:
  - `24 passed`

### 4.3 bundle regeneration
- 실행:
  - `python tools/harness/build_context_bundle.py --all`
- 결과:
  - 성공

### 4.4 app import smoke
- 실행:
  - `python -c "import app; print('APP_OK')"`
- 결과:
  - `APP_OK`

### 4.5 shared verification
- 실행:
  - `python tools/harness/verify_result.py --json`
- 결과:
  - `success: true`

### 4.6 full regression
- 실행:
  - `python -m pytest -q`
- 결과:
  - `431 passed, 3 warnings`
- 관찰 사항:
  - 기존 SQLAlchemy `Query.get()` legacy warning 3건 지속 (`foms/services/channel_inbound.py`, `tests/test_channel_webhooks.py`)

### 4.7 lint
- 실행:
  - `ReadLints`
- 결과:
  - 신규 lint 없음

## 5. 해석
- Step 7은 단순 문서 이동이 아니라 harness contract path migration이었고, 이번 closeout으로 runtime/CI/test/generated bundle까지 같은 taxonomy로 수렴했다.
- 앞으로 harness 관련 새 자산은 기본적으로 `docs/harness/` 아래 role별 하위 디렉터리에만 추가하면 된다.
- historical `docs/context` 문서를 일괄 rename하지 않은 것은 intentional이며, active contract와 archive를 분리한 상태가 현재 기준선이다.

## 6. 다음 단계
1. 거버넌스 자동 다음 단계는 Step 8(optional packaging 재평가)다.
2. Step 8을 열기 전에는 Step 7에서 정리된 `docs/harness/*` canonical path를 기준으로 추가 하네스 작업을 진행한다.
3. `business_calendar` / `/calendar` 축은 사용자 별도 지시 전까지 계속 제외한다.

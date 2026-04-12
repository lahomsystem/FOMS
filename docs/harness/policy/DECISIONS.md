# Architecture Decisions Log

> AI 세션 간 중요 기술/아키텍처 결정을 기록합니다.
> **규칙**: 최대 15개 유지. 초과 시 가장 오래된 것을 `docs/evolution/`로 이동.
> **검색**: 각 결정의 `키워드` 태그를 Grep 검색하여 관련 결정을 빠르게 찾을 수 있습니다.

---

### [2026-04-11] Step 8 packaging defer after re-evaluation
- **키워드**: packaging, src-layout, pyproject, railway, worker, alembic, app-root
- **결정**: Step 8에서는 repo-root `foms/` boundary를 current canonical runtime layout로 유지하고, full `src/foms` migration과 packaging-only `pyproject.toml` hardening은 모두 defer한다. packaging revisit는 `app:app` / Railway / worker / Alembic / tests import contract가 repo-root cwd에 의존하지 않도록 정리된 뒤 별도 ADR/plan로 다시 연다.
- **이유**: 현재 web/worker/alembic/test/harness가 root `app.py`, root `db.py`/`models.py`, `migrations/env.py`, `foms/services/jobs/tasks.py`의 repo-root depth contract, repo-root pytest/bootstrap에 강하게 결합돼 있다. 이 상태에서 `src` 이동이나 metadata만 추가하면 안정성보다 split-brain과 false-confidence 위험이 크다.
- **영향**: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`, `docs/plans/2026-04-11-step8-*`, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, future packaging ADR 및 boot/worker/alembic/test contract work

### [2026-04-11] Harness asset taxonomy canonicalization
- **키워드**: harness, docs-harness, taxonomy, context, bundle, runtime, logs
- **결정**: 하네스 policy/generated/runtime/log 자산은 `docs/harness/{policy,bundles,runtime,logs}`에만 둔다. `docs/context`는 incident/RCA/reference 문서만 유지하고, 경로 전환은 hooks/scripts/CI/bundles/tests를 같은 실행 배치에서 함께 갱신한다.
- **이유**: `docs/context` 한 축에 정책·생성물·런타임 상태·디버그 로그가 섞여 있으면 hook path, bundle output, CI drift, archive semantics가 함께 결합돼 split-brain과 복구 비용이 커진다.
- **영향**: `tools/harness/*`, `.cursor/hooks/*`, `.claude/hooks/*`, `tests/harness/*`, `.github/workflows/harness-ci.yml`, `.gitignore`, `.gitattributes`, `docs/harness/*`, `docs/context/*`

### [2026-04-06] Harness cleanup tracking boundary
- **키워드**: harness, cleanup, gitignore, debug, scratch, context
- **결정**: 저장소 정리는 raw hook debug 산출물(`HOOK_RAW_DUMP.txt`, `.hook_raw_once`)과 root scratch 파일(`temp_script.js`, `test_scripts.js`, `test.html`)만 제거하고, `AI_STATUS.md`, `AI_CHANGELOG.md`, `SESSION_LOG.md`, `EDIT_LOG.md`, `COMPACT_CHECKPOINT.md` 같은 컨텍스트 메모리 파일은 계속 추적한다.
- **이유**: raw debug/scratch 파일은 런타임·빌드·테스트 계약과 무관하지만, 컨텍스트 메모리 파일은 현재 하네스가 세션 복원과 상태 파악에 직접 사용하므로 같은 “로그”로 묶어 제거하면 메모리 설계 자체가 바뀐다.
- **영향**: `.gitignore`, `docs/specs/2026-04-06-harness-tracking-cleanup_SPEC.md`, `docs/context/HOOK_RAW_DUMP.txt`, `docs/context/.hook_raw_once`, `temp_script.js`, `test_scripts.js`, `test.html`

### [2026-04-05] Prompt-side harness auto-entry routing
- **키워드**: harness, hook, beforeSubmitPrompt, wrapper, routing, cursor
- **결정**: Cursor에서는 `beforeSubmitPrompt` 훅으로 사용자 프롬프트를 review / implement / qa / generic으로 분류하고, 해당할 때만 wrapper-first `agentMessage`를 자동 주입한다. 구현/하네스 코어 요청은 RPI와 `run_codex.ps1 -Profile implement -Plan ...` 경로를, QA 요청은 `run_gstack_qa.ps1` 경로를 우선 제시한다.
- **이유**: Cursor 훅은 전체 bundle 자동 주입이나 숨은 wrapper 실행을 지원하지 않으므로, 과장 없는 방식으로 가장 강한 자동화는 prompt-submit 시점의 짧은 시스템 라우팅 메시지다.
- **영향**: `.cursor/hooks.json`, `.cursor/hooks/before_submit_prompt.py`, `tools/harness/prompt_router.py`, `tests/harness/test_hooks_smoke.py`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

### [2026-04-05] Post-audit harness hardening contract
- **키워드**: harness, audit, hardening, exit-code, verify-result, spec, docs
- **결정**: Wave 3 구현 이후 감리에서 드러난 신뢰성 이슈는 별도 hardening batch로 분리해 수정한다. 우선순위는 wrapper 종료 코드 전달, deterministic spec 선택/표시, invalid `--spec` 구조화 실패, RPI 문구 단일화, bundle 진입 표현 정정이다.
- **이유**: 완료로 표시된 기능 위에 새 기능을 더하기 전에, CI와 운영자가 실패를 정확히 감지하고 문서가 실제 동작을 과장하지 않도록 신뢰 경계를 먼저 고정해야 한다.
- **영향**: `tools/harness/run_codex.ps1`, `tools/harness/run_gstack_qa.ps1`, `tools/harness/verify_result.py`, `tools/harness/spec_utils.py`, `.cursor/hooks/post_task_quality_check.py`, `tests/harness/*`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

### [2026-04-05] Wave 3 Codex auto level routing
- **키워드**: harness, wave3, codex, routing, level, override, qa
- **결정**: `run_codex.ps1`는 `low / medium / high / top` 4단계로 작업을 자동 분류하고, 기본적으로 `low/medium`은 daily bundle, `high/top`은 `_HARNESS` bundle을 선택한다. 수동 override는 `-AdditionalPrompt`의 fixed tag / 자연어 형식을 지원한다.
- **이유**: 고위험 하네스·코어 작업은 강한 컨텍스트와 검증이 필요하고, 일상 작업은 slim context를 유지해야 LLM 비용과 운영 복잡도를 함께 줄일 수 있다.
- **영향**: `tools/harness/run_codex.ps1`, `tools/harness/run_gstack_qa.ps1`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`, `tests/harness/test_run_codex_levels.py`

### [2026-04-05] 하네스 일상 번들 슬림화
- **키워드**: harness, bundle, token, Cursor, Claude, Codex
- **결정**: 기본 운영 번들에서는 `plan_harness_engineering_master`를 제거하고, `CLAUDE.md`는 Claude 전용 번들에만 포함
- **이유**: 마스터 플랜과 runner 비소유 문서를 상시 주입하면 토큰 비용이 커지고, 일상 작업에서는 필요성이 낮음
- **영향**: `tools/harness/profiles/cursor.yaml`, `tools/harness/profiles/claude.yaml`, `tools/harness/profiles/codex.yaml`, `docs/context/HARNESS_BUNDLE_*.md`

### [2026-04-05] 하네스 전용 확장 번들 분리
- **키워드**: harness, bundle, profile, context, codex
- **결정**: 일상 번들과 별도로 `_HARNESS` 확장 번들을 생성하고, `run_codex.ps1`는 하네스 관련 파일/계획을 감지하면 확장 번들을 자동 선택
- **이유**: 일상 작업은 저비용 slim context를 유지하면서도, 하네스 내부 작업은 계획/정책 전체를 자동으로 확보해야 품질 저하가 없음
- **영향**: `tools/harness/profiles/*-harness.yaml`, `tools/harness/run_codex.ps1`, `docs/context/HARNESS_BUNDLE_*_HARNESS.md`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

### [2026-04-05] Spec 탐색 규칙 단일화
- **키워드**: harness, spec, verify-result, hook, recursive
- **결정**: 최신 Spec 탐색은 `tools/harness/spec_utils.py`의 재귀 탐색 함수 하나로 통일
- **이유**: verify-result와 post-task hook이 서로 다른 Spec을 가리키면 검증 기준과 리마인더가 어긋남
- **영향**: `tools/harness/spec_utils.py`, `tools/harness/verify_result.py`, `.cursor/hooks/post_task_quality_check.py`

### [2026-02-27] 도면 파일 생명주기 설계 확정
- **키워드**: 도면, R2, 파일삭제, 생명주기
- **결정**: 발송 시 R2 물리 삭제 금지, 수령 확정 시 일괄 정리
- **이유**: 전달 취소 시 원본 복원 가능해야 함. 타임라인 히스토리에서 구 파일 참조 유지 필요
- **영향**: `apps/api/erp_orders_drawing.py` (REPLACE 시 삭제 코드 제거), `apps/api/erp_orders_draftsman.py` (수령 확정 시 정리 + db.commit)

### [2026-02-27] 지도 Auto-poll 방식 변경
- **키워드**: 지도, geocode, 폴링, iframe
- **결정**: geocode pending 시 `/api/generate_map` (Folium 전체 재생성) 대신 `/api/map_data` (좌표만 조회)로 폴링
- **이유**: iframe 전체 재로드가 "자꾸 refresh된다"는 UX 문제 유발
- **영향**: `templates/map_view.html` (15초 간격, 5회 제한)

### [2026-02-26] 업로드 로직 표준화 (배치+병렬)
- **키워드**: 업로드, 배치, 병렬, Presigned, UUID
- **결정**: AS/시공/도면 대시보드 모두 배치 Presigned URL 요청 + 병렬 업로드 (최대 10개 동시)
- **이유**: 업로드 속도 개선 + 파일명 충돌 방지 (UUID 포함 키)
- **영향**: `templates/partials/erp_dashboard_scripts_drawing.html`, `templates/erp_drawing_workbench_detail.html`, `services/storage.py`

### [2026-02-23] Direct R2 Upload (Phase D)
- **키워드**: R2, 직접업로드, Presigned PUT, 서버경유제거
- **결정**: 브라우저 → R2 Presigned PUT 직접 업로드. 앱 서버 파일 경유 없음
- **이유**: 서버 메모리/CPU 절약, 업로드 속도 향상
- **영향**: `services/storage.py`, `apps/api/attachments.py`, 모든 업로드 프론트엔드

### [2026-02-22] Railway Worker + Geocode 컬럼
- **키워드**: Railway, Worker, geocode, RQ, 비동기
- **결정**: Railway Worker 서비스 추가, `orders.lat/lng/geocode_status` 컬럼 추가, RQ Job Queue로 비동기 geocode
- **이유**: 지도 로드 시 실시간 Kakao API 호출 병목 제거
- **영향**: `railway-worker.toml`, `models.py`, `services/jobs/`

### [2026-02-20] Production 다중 사용자 확장
- **키워드**: Railway, Replica, Worker, DB풀, 확장
- **결정**: Web Replica 2개, Worker 1개, DB 풀 환경변수화
- **이유**: 동시 사용자 증가 대응
- **영향**: `railway.toml`, `db.py`

### [2026-02-16] Flask 유지 + 점진 고도화 (Strangler Fig)
- **키워드**: Flask, SvelteKit, 마이그레이션, Strangler
- **결정**: SvelteKit 전면 마이그레이션 대신 Flask 유지, Blueprint 분리 우선
- **이유**: 전면 마이그레이션 리스크 과대, 기존 스택 충분히 유효

### [2026-02-16] services/ 폴더 도입
- **키워드**: services, 비즈니스로직, Blueprint, 구조
- **결정**: `business_calendar`, `erp_policy`, `storage` → `services/` 이동
- **이유**: 비즈니스 로직 집중, `app.py`는 Blueprint 등록만 담당

### [2026-02-16] 컨텍스트 엔지니어링 시스템
- **키워드**: Hooks, Rules, Memory, 컨텍스트, AI메모리
- **결정**: Hooks + Rules + Memory (`docs/`) 통합 시스템
- **이유**: AI 세션 간 기억 상실, 지시 미준수 문제 해결

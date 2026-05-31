# Architecture Decisions Log

> AI 세션 간 중요 기술/아키텍처 결정을 기록합니다.
> **규칙**: 최대 15개 유지. 초과 시 가장 오래된 것을 `docs/evolution/`로 이동.
> **검색**: 각 결정의 `키워드` 태그를 Grep 검색하여 관련 결정을 빠르게 찾을 수 있습니다.

---

### [2026-05-31] Mobile tablet redesign P0~P3 (Decision Log D01–D10)
- **키워드**: mobile, tablet, ERP_MOBILE_V2, HTMX, Alpine, feature-flag, cohort, MIGRATION_ROADMAP
- **결정**: `docs/design/REVIEW_ENTRY.md` Decision Log D01–D10을 코드 SSOT로 실행. P0~P3는 feature flag default OFF + cohort 점진 출시. HTMX/Alpine는 new surface only(D06). 신규=마법사+OrderDraft, 수정=인라인+critical explicit save(D07). Bottom nav HTMX는 P3-01 별도 flag.
- **이유**: 70% 기존 ERP mobile shell 재사용, `erp-shell.js` 회귀 회피, ops 롤백은 cohort/env OFF로 즉시 가능.
- **영향**: `foms/services/feature_flags.py`, `foms/api/*`, `static/js/foms/*`, `templates/partials/shared/erp_mobile_*`, `tests/domains/test_p*_gate.py`, `docs/design/MIGRATION_ROADMAP.md`

### [2026-05-30] Global team skills surface
- **키워드**: skills, gstack, global-team-install, cursor, claude, codex, context
- **결정**: Cursor IDE 안에서 Claude·Codex 플러그인을 함께 쓰는 운영 모델은 `~/.claude/skills/gstack`을 단일 global team install source/runtime으로 사용한다. Repo-local `.agents/skills/gstack`, user-level `~/.cursor/skills`·`~/.codex/skills`의 gstack/caveman 복사본, `~/.claude/skills/gstack-*` top-level generated duplicate, 그리고 `~/.claude/skills/gstack/.{agents,cursor,factory,gbrain,hermes,kiro,openclaw,opencode,slate}` host trees는 discoverable skills 중복으로 보며 quarantine 대상으로 둔다.
- **이유**: Cursor context panel에서 Skills가 약 146K tokens(사용 context의 약 80%)를 점유했고, 조사 결과 1,209개 `SKILL.md` 중 normalized unique는 132개뿐이었다. 같은 gstack skill이 20벌 이상 발견되면 full-body/metadata 주입이 폭증해 일상 코딩 context가 고갈된다.
- **영향**: `~/.claude/skills/gstack`, `~/.cursor/skills`, `~/.codex/skills`, `.agents/skills`, `tools/harness/cleanup_global_skills.ps1`, `tools/harness/setup_gstack.ps1`, `tools/harness/run_gstack_qa.ps1`, `tools/harness/run_codex.ps1`

### [2026-05-28] Caveman default agenting style
- **키워드**: caveman, token, response-style, cursor, claude, codex, bundles
- **결정**: `caveman`을 수동 호출용 skill에만 두지 않고 FOMS 기본 응답 스타일로 승격한다. `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, 새 `.cursor/rules/20-caveman-default.mdc`, harness manifest/profile/bundle에 반영한다.
- **이유**: 웹 리서치상 caveman은 내부 추론이 아니라 agent-visible prose 절감 도구이며, 항상 적용하려면 skill 설치만으로는 부족하고 상위 규칙/세션 컨텍스트가 필요하다. 단, 보안 경고·파괴적 작업·migration·data deletion·force push·production deploy에서는 full clarity가 우선한다.
- **영향**: `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/rules/20-caveman-default.mdc`, `tools/harness/manifest.yaml`, `tools/harness/profiles/*.yaml`, `docs/harness/bundles/*`

### [2026-05-28] Fresh gstack + caveman skills boundary
- **키워드**: skills, gstack, caveman, cursor, claude, codex, safety-policy
- **결정**: 기존 gstack 파생/generated 중복 skills를 삭제하고 `garrytan/gstack` 원본 fresh install(`gstack-*` 네임스페이스)과 `Shawnchee/caveman-skill`의 `caveman`만 Cursor/Claude/Codex skills 계층에 둔다. FOMS 위험 명령 판단은 `tools/harness/safety_policy.py`로 공용화하고 Cursor/Claude guard가 이를 사용한다.
- **이유**: 이전 tree는 upstream source, generated host outputs, runtime assets, nested host packages가 섞여 있어 출처·중복·안전 우선순위가 불명확했다. fresh source와 공용 safety adapter를 분리해야 gstack 역할 skills와 caveman 압축이 FOMS hard safety/RPI 정책을 덮지 않는다.
- **영향**: `.agents/skills`, `~/.cursor/skills`, `~/.claude/skills`, `~/.codex/skills`, `tools/harness/safety_policy.py`, `.cursor/hooks/guard_shell.py`, `.claude/hooks/guard_shell.py`, `tools/harness/setup_gstack.ps1`, `docs/context/analysis/skills-fresh-rebuild-*.md`

### [2026-05-13] FOMS Brain AX Designer add-in stack boundary
- **키워드**: foms-brain, ax, designer, wdplanner-v2, r3f, babylon, langgraph, add-in, pgvector
- **결정**: WDPlanner 대체 제품인 FOMS Brain AX Designer는 기존 `Add In Program/WDPlanner`의 Babylon.js/Electron 구현을 확장하지 않고, `/wdplanner-v2` 병행 운영 add-in으로 새 React/Vite + R3F/Drei/Zustand 프론트를 둔다. AI orchestration은 FOMS backend/worker의 LangGraph가 담당하고, vector memory는 FOMS PostgreSQL + pgvector 경계를 우선한다. Next.js/Supabase는 독립 SaaS 전환 결정 전까지 도입하지 않는다.
- **이유**: 최초 AX 제품 목표는 R3F/Drei 기반 설계 UX와 LangGraph 중심 self-evolving ontology를 요구한다. 기존 WDPlanner의 Babylon/Electron 노하우 일부는 기능 inventory로 참고하되, FOMS 운영 경계에서는 Flask modular monolith + static add-in + API/worker 구조가 인증/DB/source-of-truth drift를 줄인다.
- **영향**: `docs/plans/2026-05-13-foms-brain-ax-designer-blueprint-v2-implementation-map.md`, future `Add In Program/FOMSBrainDesigner`, `static/designer`, `foms/web/designer`, `foms/api/designer`, `foms/services/designer`, `foms/persistence/designer`, `migrations/versions/*designer*`

### [2026-04-30] Shared harness task classifier
- **키워드**: harness, classifier, prompt-router, codex, claude, cursor, wave3
- **결정**: Cursor `beforeSubmitPrompt`, `run_codex.ps1`, Claude/Codex 플러그인 preflight가 `tools/harness/task_classifier.py`의 단일 결정적 JSON 분류 결과를 사용한다. 분류 결과는 `route_kind`, `level`, `context_mode`, runner별 bundle, RPI, 사용자 방향 확인, 자원 힌트를 포함한다.
- **이유**: 기존에는 `prompt_router.py`의 intent 분류와 `run_codex.ps1`의 Wave 3 level 분류가 분리되어 Cursor/Codex/Claude 경로 간 drift와 과장된 자동화 기대가 생겼다. 플러그인 hook 한계를 인정하되 같은 preflight 결과를 공유해야 운영 품질이 안정된다.
- **영향**: `tools/harness/task_classifier.py`, `tools/harness/prompt_router.py`, `tools/harness/run_codex.ps1`, `tests/harness/*`, `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`, `docs/harness/bundles/*`

### [2026-04-19] 견적 결제정보 accounts + 레거시 단일 필드 병행
- **키워드**: estimate, payment_info, accounts, 견적, ERP, 하위호환
- **결정**: `ESTIMATE_PAYMENT_INFO`는 다중 계좌 `accounts[]`를 정식 필드로 두고, 기존 단일 `bank`/`account`/`holder`는 프리뷰·API 소비자 하위 호환용으로 유지한다. 출고 설정 실측담당자 행의 너비는 인라인이 아니라 `.setting-mm-phone` 등 CSS 클래스로만 제어한다.
- **이유**: 계약서에 은행별 계좌를 나열해야 하며, 구버전 JSON/클라이언트는 단일 필드만 기대할 수 있다. 인라인 스타일은 프로젝트 UI 규칙과 충돌한다.
- **영향**: `foms/services/orders/estimate_defaults.py`, `static/js/orders/estimate-preview.js`, `static/css/foundation/erp-pro/09-mobile-erp-optimization.css`, `templates/shipment/partials/settings_body.html`

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

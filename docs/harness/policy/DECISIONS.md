# Architecture Decisions Log

> AI 세션 간 중요 기술/아키텍처 결정을 기록합니다.
> **규칙**: 최대 15개 유지. 초과 시 가장 오래된 것을 `docs/evolution/`로 이동.
> **검색**: 각 결정의 `키워드` 태그를 Grep 검색하여 관련 결정을 빠르게 찾을 수 있습니다.

---

### [2026-07-08] 분류기·Codex 래퍼 퇴역 (하네스 재설계 Phase 1a)
- **키워드**: harness, classifier, retirement, codex-wrapper, preflight, gstack-qa, phase1a
- **결정**: `tools/harness/task_classifier.py`(789줄)+preflight 훅(`user_prompt_submit.py`/`before_submit_prompt.py`/`prompt_router.py`)과 `tools/harness/run_codex.ps1`(855줄)을 원자 퇴역한다. QA 래퍼 체인(`run_gstack_qa.ps1`·`gstack_qa_skill.ps1`)도 공동 퇴역 — 소비자가 prompt_router(동시 퇴역)와 문서뿐이고, 실사용 QA는 이 체인을 거치지 않는 gstack browse/qa 스킬(Claude/Cursor 세션 내 Skill 호출) 경로이기 때문이다. 작업 레벨·RPI 판단은 문서 규칙(CLAUDE.md 새 세션 시작 프로토콜)으로 대체하고, 코어 변경 게이트는 Stop 훅·pre_push_smoke·branch protection이 코드로 강제한다. Codex 세컨드 오피니언은 on-demand `gstack-codex` 스킬로 대체한다. `setup_gstack.ps1`(벤더 런타임 점검)·`verify_result.py`·번들 도구는 보존.
- **이유**: 재설계 보고서 `docs/plans/2026-07-08-harness-control-system-redesign-report.md` §9.1·§9.2 — 분류기는 강제력 0 실측+레벨 오염 33%+RPI 게이트 우회 가능(N1)으로 4자 만장일치 폐기, Codex 래퍼는 90일간 막은 실패 0건·7월 활동 0·PS 레벨 함수 3종 죽은 코드로 만장일치 퇴역. 래퍼가 분류기의 유일한 구조적 소비자라 A+B는 단일 원자 변경으로 실행.
- **영향**: `tools/harness/{task_classifier,prompt_router}.py`·`tools/harness/{run_codex,run_gstack_qa,gstack_qa_skill}.ps1`·`tests/harness/{test_task_classifier,test_run_codex_levels}.py`·`.claude/hooks/user_prompt_submit.py`·`.cursor/hooks/before_submit_prompt.py` 삭제, `.claude/settings.json`(UserPromptSubmit 배선·allowlist)·`.cursor/hooks.json`(beforeSubmitPrompt)·`tests/harness/test_hooks_smoke.py`·`CLAUDE.md`·`AGENTS.md`·`.cursor/rules/00-project-context.mdc`·`docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`·`.agents/skills/gstack/VENDOR.md` 갱신

### [2026-07-05] Claude-main 하네스 업그레이드 (훅 패리티·MCP 정본화·Stop 게이트)
- **키워드**: claude, harness, hooks, mcp, stop-gate, preflight, classifier, korean-keywords
- **결정**: Claude Code를 메인 러너로 전환하며 (1) Claude 훅을 Cursor와 패리티로 확장 — `SessionStart`(AI_STATUS/RPI 안내 주입)·`UserPromptSubmit`(task_classifier preflight 자동 주입, low&비RPI는 생략)·`PreCompact`(COMPACT_CHECKPOINT 갱신) 신설, (2) Stop 훅을 조언성 리마인더에서 결정적 게이트로 승격 — `.py` 편집 pending 시 `import app` 실패면 exit 2로 턴 종료 차단, (3) 프로젝트 MCP 정본을 루트 `.mcp.json`으로 이동하고 `postgres`/`context7`만 유지 (`filesystem`·`memory`·`sequential-thinking`·`mcp-reasoner`·`markitdown` 퇴역 — 네이티브 도구/파일 메모리/extended thinking이 대체), (4) task_classifier 레벨 키워드에 한글 동의어 추가(영어 전용이라 한글 프롬프트 전부 low 오분류되던 결함), (5) CLAUDE.md에서 Cursor 러너 라우팅 절 제거(AGENTS.md/.cursor rules 소관). 플러그인 패키징(P5)은 가치 대비 유지비로 defer.
- **이유**: `.claude/settings.json`의 `mcpServers` 블록은 Claude Code가 인식하는 정본 위치가 아니고, Cursor 훅 8종 대비 Claude 훅 3종만 배선되어 Claude 메인 전환 시 자동 라우팅·체크포인트·검증 게이트가 사라진다. 2026 공식 best practice는 결정적 검증 게이트·MCP 최소화·CLAUDE.md 슬림화를 권고한다.
- **영향**: `.mcp.json`(신규), `.claude/settings.json`, `.claude/hooks/{session_start,user_prompt_submit,pre_compact}.py`(신규), `.claude/hooks/{track_edits,quality_check,shared_utils}.py`, `tools/harness/task_classifier.py`, `tests/harness/test_claude_stop_gate.py`(신규), `tests/harness/test_task_classifier.py`, `CLAUDE.md`, `docs/harness/bundles/*`(재생성), `docs/specs/2026-07-05-claude-main-harness-upgrade_SPEC.md`, `.gitignore`

### [2026-06-30] 모바일 안전 업로드 압축 표준
- **키워드**: 업로드, 모바일, 압축, Presigned, 병렬, R2
- **결정**: 이미지 압축 동시성과 R2 PUT 업로드 동시성을 분리한다. 모바일/coarse pointer는 압축 1개·업로드 3개, 데스크톱은 압축 2개·업로드 5개를 기본값으로 사용한다. batch presigned session은 `client_id`를 echo 하여 파일명이 중복돼도 frontend가 올바른 session/key를 매칭한다.
- **이유**: 2026-02-26의 최대 10개 병렬 표준은 direct upload 속도 개선에는 유효했지만, 클라이언트 이미지 압축이 도입된 뒤 모바일에서 CPU/RAM spike와 탭 종료 위험을 만들 수 있다. 압축 후 size로 session을 발급해야 서버 검증과 저장 metadata도 실제 업로드 파일과 일치한다.
- **영향**: `static/js/runtime/upload-progress.js`, `foms/api/files/direct_upload.py`, ERP/AS/시공/도면/채팅 업로드 UI

### [2026-06-17] GDM + bespoke specialist agent retirement
- **키워드**: gdm, retirement, gstack, caveman, cursor, claude, codex, agents
- **결정**: repo-local GDM(`grand-develop-master`, `GDM_EXECUTION_PLAN`)과 bespoke Cursor/Claude specialist agent 계층을 활성 운영 모델에서 퇴역한다. 앞으로 Cursor IDE, Cursor 내 Claude, Cursor 내 Codex는 `AGENTS.md`/`CLAUDE.md`/`.cursor/rules` 공통 정책, RPI·verify-result 워크플로, gstack skills, caveman response style을 기준으로 운영한다. 역사적 GDM audit/evolution/plan 문서는 archive evidence로 보존하되 현재 진입점으로 안내하지 않는다.
- **이유**: 현재 실제 운영은 caveman과 gstack skills 중심이며, GDM 및 bespoke agent 계층은 중복된 역할·명령·컨텍스트 표면을 만들어 일상 작업에서 discoverability와 토큰 비용을 악화시킨다. gstack/caveman 경계를 유지하면서 FOMS hard safety/RPI 정책을 상위 기준으로 두는 편이 더 단순하고 현재 사용 방식과 일치한다.
- **영향**: `.cursor/agents/*`, `.claude/agents/*`, `.claude/commands/{gdm,audit,backend,frontend,db,deploy,migrate,explore,evolve,rca,research,review}.md`, `.cursor/rules/14-incident-rca.mdc`, `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`, `docs/harness/bundles/*_HARNESS.md`, `tools/research_center/self_upgrade_manifest.json`, `tools/research_center/coding_research_center.py`, `tools/research_center/README.md`, `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `scripts/ops/sync_local_to_railway.ps1`, `docs/specs/2026-06-17-gdm-retirement_SPEC.md`, `docs/ARCHIVE_INDEX.md`, `docs/AI_STATUS.md`

### [2026-06-05] backup feature retirement + backups/ 거버넌스 제거
- **키워드**: backup, retirement, governance, dual-spec, PTC, allowlist, FOMS_RUNTIME_OUTPUT_ROOT, railway-postgresql
- **결정**: `SimpleBackupSystem` / `/api/simple_backup` / `/api/backup_status` / `backups/` 트리를 전부 폐기한다. production 백업 정본은 Railway PostgreSQL 자체 백업/스냅샷이며, 로컬 운영자 백업은 `scripts/ops/sync_local_to_railway.ps1` (`${FOMS_RUNTIME_OUTPUT_ROOT}/dumps/foms.dump`)로 단일화한다. PTC root allowlist + dual-spec(2026-04-07 §2.6.1, 2026-04-13 §2.2.1/§2.5) + clean-room 스크립트 + `.gitignore` + git 트리를 단일 PR에서 동시 갱신했다. backup 재도입 차단을 위한 별도 negative gate는 두지 않으며, allowlist exactness + RPI 절차가 게이트 역할을 한다.
- **이유**: `SimpleBackupSystem`은 Windows pg_dump.exe 경로 하드코딩 + ephemeral filesystem 가정으로 Railway Linux 컨테이너에서 시작부터 실패한다. admin UI 버튼은 production에서 silent fail만 일으켜 사용자 신뢰를 깎았다. 동시에 `backups/` 디렉터리를 quarantine으로 governance allowlist에 박아둔 채 `.gitkeep`만 트리에 두는 구조는 dual-spec lock과 PTC test의 짐만 늘렸다. 로컬 안전망(Phase 4 OrderScheduleDate)은 유지하되 출력은 `${FOMS_RUNTIME_OUTPUT_ROOT}/dumps/`로 합쳐 mental model을 0개 더한다.
- **영향**: `foms/api/backup.py` 삭제, `foms/services/admin/backup_service.py` 삭제, `foms/platform/blueprints.py` backup_bp 등록 제거, `templates/admin/admin.html` 백업 카드/버튼/JS 제거, `scripts/ops/simple_backup_system.py` 삭제, `scripts/maintenance/🚨_간단_백업.bat` 삭제, `scripts/ops/clone_prod_to_deploy.ps1` 삭제, `scripts/maintenance/backup_order_schedule_dates.py` 출력 경로 repath, `tests/contracts/runtime/test_ptc_physical_exactness.py` allowlist, `tests/contracts/runtime/foms_namespace_surface_tests.py` B11B 클러스터, `tools/harness/strict_canonical_b12_clean_room.ps1`, `.gitignore`, `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` §2.6.1, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` 6곳, `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` 4곳, `foms/README.md`, `backups/.gitkeep` 삭제, `docs/specs/2026-06-05-backup-feature-retirement_SPEC.md` 신규.

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

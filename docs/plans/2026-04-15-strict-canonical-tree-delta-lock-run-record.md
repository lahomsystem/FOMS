# Strict canonical tree delta lock

> **date:** 2026-04-15  
> **purpose:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` `§2.2.1 Final canonical tree` strict completion baseline  
> **scope:** post-Wave9 endgame 이후 남은 physical tree delta만 고정  
> **non-goal:** packaging / `src/foms` 재오픈, runtime/deploy frozen path 이동

## 1. Goal

- `2.2.1 Final canonical tree`를 **목표 그림**이 아니라 실제 저장소 정렬 기준으로 재고정한다.
- `apps/`와 루트 `services/`를 더 이상 “장기 허용 overlay”로 두지 않고, strict completion 완료 시 **거의 0에 가까운 thin wrapper/shim**만 남는 상태를 목표로 한다.
- 예전에 defer되었던 `WR-B1`, `WR-J1`, `WR-H1`를 이번 strict track에서 어떻게 처리할지 명시한다.

## 2. Canonical delta inventory

### 2.1 Backend / ownership tree

| 영역 | 현재 상태 | strict final state |
|------|-----------|--------------------|
| `foms/persistence/wdcalculator/` | 부재 | 생성 후 `wdcalculator_db.py`, `wdcalculator_models.py` 정렬 기준 마련 |
| `foms/web/` | `measurement`, `production`, `cs` 위주 | `orders`, `measurement`, `shipment`, `drawing`, `production`, `construction`, `cs`, `wdcalculator`, `admin`, `auth` 모두 채움 |
| `foms/api/` | `orders/` 외 다수 flat file | 컨텍스트 패키지 중심 정렬 (`channel`, `notifications`, `wdcalculator`, `admin`, `auth` 포함) |
| `foms/services/` | flat module + 일부 package 혼재 | `common/orders/measurement/shipment/drawing/production/construction/cs/wdcalculator/channel/files/notifications/auth/jobs` 중심 정렬 |
| `apps/` | live owner 다수 존재 | thin Flask wrapper / alias / import bridge만 허용 |
| root `services/` | explicit exception + live owner 다수 존재 | shim-only 또는 제거. live implementation 금지 |

### 2.2 Template / asset tree

| 영역 | 현재 상태 | strict final state |
|------|-----------|--------------------|
| `templates/` root | 도메인 페이지 단일 파일 다수 | 컨텍스트 루트로 이동, root page 제거 |
| `templates/partials/` | `erp_*`, `chat_*` 평면 배치 | `templates/partials/shared/` + 각 컨텍스트 partial 하위로 정리 |
| `templates/channel/wam/` 등 | ~~`templates/channel_wam/` 별도 family~~ → **흡수 완료** | `§2.2.1`의 `templates/channel/` 아래 WAM 페이지·파셜 (`channel/wam/*`, 루트 `channel/wam_*.html`) |
| `static/js/erp/`, `static/js/wam/` | ~~legacy family~~ → **§6.11 완료** | `runtime/` + `orders/` + `channel/` + context 폴더 |
| `static/css/erp-pro/`, `static/css/wam/` | ~~family 중심~~ → **§6.11 완료** | `css/foundation/` + `css/contexts/channel|shipment/` |

### 2.3 Support / hygiene tree

| 영역 | 현재 상태 | strict final state |
|------|-----------|--------------------|
| `tests/` | root `test_*.py` + `load/` 혼재 | `contracts/domains/harness/fixtures/support` 기준 정렬 |
| `scripts/` | root `.py`/`.ps1` 다수 잔존 | `ops/maintenance/migrations`만 사용 |
| `tools/` | root file / temp 산출물 존재 | `harness/smoke/research_center`만 허용 |
| `docs/` | ~~`analysis`, `validation`, `manual-artifacts` 등 상위 편차~~ → **§6.14 완료** | `specs/plans/evolution/guides/incidents/harness/context` 축 + `guides/validation/`, `context/analysis/`, `context/manual-artifacts/` |

## 3. Re-entry verdict for former defer rows

### 3.1 WR-B1 (`business_calendar` / `/calendar`)

- **기존 상태:** explicit exception / 별도 ADR 필요
- **strict completion verdict:** 예외 유지 종료. 이번 track에서 **반드시 정리 대상**으로 재진입
- **required end-state:**
  - `services/business_calendar.py`는 root implementation으로 남지 않는다.
  - `/calendar`와 관련 helper ownership은 `2.2.1` 컨텍스트 tree 안에서 설명 가능한 위치로 이동한다.
  - `business_calendar`는 “승인 전까지 제외”가 아니라, strict completion의 blocking gap으로 취급한다.

### 3.2 WR-J1 (`services.jobs.tasks` runtime-string)

- **기존 상태:** backward compatibility 이유로 no-code defer
- **strict completion verdict:** defer 종료. 이번 track에서 **worker/runtime compatibility drain strategy**를 포함해 해결
- **required end-state:**
  - root `services/jobs/*`가 canonical runtime contract를 대표하지 않는다.
  - queued-job compatibility가 필요하면 drain window 또는 transitional re-export를 두더라도, 최종 closeout 시 canonical owner는 `foms/services/jobs/*`만 남는다.
  - `_TASK_PATH_PREFIX` 등 runtime string contract는 final state 기준으로 재고정된다.

### 3.3 WR-H1 (notifications / attachments / chat / channel cluster)

- **기존 상태:** dedicated future owner-surface batch
- **strict completion verdict:** future batch가 아니라 **이번 track의 필수 본편**
- **required end-state:**
  - `apps/api/notifications.py`, `apps/api/attachments.py`, `apps/api/chat/*`, root `services/channel_*`는 live owner 상태를 벗어난다.
  - 최종 canonical owner는 `foms/api/notifications`, `foms/api/channel`, `foms/services/notifications`, `foms/services/channel` 쪽으로 수렴한다.
  - “high-risk라서 나중에”가 아니라 “high-risk이므로 별도 tranche로 처리하되 이번 전체 계획 안에서 완료”로 취급한다.

## 4. Batch boundary lock

1. **Delta lock**  
   strict final state와 re-entry verdict를 문서로 고정한다.
2. **Backend owner-tree tranche**  
   `foms/persistence/wdcalculator`, `foms/web/*`, `foms/api/*`, `foms/services/*`, `apps/`, root `services/`
3. **Template tree tranche**  
   `templates/*.html`, `templates/partials/*`, `templates/channel/*` (WAM 흡수 후 잔여: 루트 HTML·`partials/` 평면 정리)
4. **Asset tree tranche**  
   `static/js/*`, `static/css/*`
5. **Support tree tranche**  
   `tests/*`, `scripts/*`, `tools/*`, `docs/*`
6. **Final sweep**  
   strict tree scan + verification + status/docs closeout

## 5. Done criteria for this lock batch

- `2.2.1` strict completion의 해석이 한 문서에 고정돼 있다.
- `WR-B1`, `WR-J1`, `WR-H1`는 더 이상 “예외”나 “나중에”가 아니라 **이번 track의 mandatory tranche**로 분류돼 있다.
- 이후 배치에서 “이건 final tree 밖이지만 남겨도 되나?” 같은 모호한 판단을 하지 않아도 된다.

## 6. Tranche evidence (incremental)

### 6.1 WR-B1 `business_calendar` (2026-04-15)

- **Canonical owner:** `foms/services/common/business_calendar.py` (live implementation, `data/holidays_kr_*.json` 등).
- **Root:** `services/business_calendar.py`는 `foms.services.common.business_calendar`로만 re-export하는 **shim** (§3.1 “root implementation으로 남지 않는다” 충족).
- **Live callers:** `apps/`, `foms/`, `scripts/`에서 `from services.business_calendar` 사용 없음 (레거시 `backups/` 스냅샷만 참조).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_wr_b1_business_calendar_legacy_shim_reexports_canonical`.

### 6.2 WR-J1 `services.jobs` / RQ task paths (2026-04-15)

- **Canonical owner:** `foms/services/jobs/queue.py`, `foms/services/jobs/tasks.py` (enqueue 함수 경로 접두어 `_TASK_PATH_PREFIX = "foms.services.jobs.tasks"`).
- **Root:** `services/jobs/queue.py`, `services/jobs/tasks.py` — **shim-only** (`from foms.services.jobs...` re-export).
- **Legacy Redis:** 과거 `services.jobs.tasks.*` 문자열은 루트 shim import로 drain 가능.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_canonical_jobs_queue_uses_namespaced_rq_task_path_prefix`, legacy shim 동치 테스트.
- **Run record:** `docs/plans/2026-04-15-wr-j1-jobs-runtime-string-contract-run-record.md` (§2·§3 live truth 동기화).

### 6.3 WR-H1 high-risk API cluster (notifications / attachments / chat / channel) (2026-04-15)

- **Canonical owner (registration):** `foms/platform/blueprints.py`는 `notifications_bp`, `attachments_bp`, `chat_bp`, `register_chat_socketio_handlers`, channel 관련 BP를 **`foms.api.*`에서만** import·등록한다 (`from apps.api.notifications` 등 **금지**).
- **Legacy `apps.api`:** `apps/api/notifications.py`, `attachments.py`, `chat/__init__.py`는 `foms.api`로의 **re-export shim**; `channel_integration.py` 등은 `importlib`로 `foms.api.channel.*` 모듈에 치환된다.
- **Services:** 루트 `services/channel_*`는 `foms.services.channel_*` shim (기존 `foms_namespace_surface_tests` 동치 검증).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_wr_h1_high_risk_cluster_strict_canonical`.
- **Run record:** `docs/plans/2026-04-15-wr-h1-high-risk-cluster-continuation-lock-run-record.md` §2 이후 strict track 갱신본.

### 6.4 Template tree — `channel` / WAM physical path (2026-04-15)

- **Canonical layout:** `templates/channel/wam/` (기존 `templates/channel_wam/` 디렉터리), 루트 레거시 V1·에러 셸 `templates/channel/wam_index.html`, `templates/channel/wam_error.html`.
- **API:** `foms/api/channel/channel_wam.py`의 `render_template` / `_resolve_html_template()` 문자열을 `channel/wam_*.html`, `channel/wam/index.html`로 정렬.
- **Regression:** `tests/test_channel_wam_templates.py`, `tests/test_channel_wam_backend.py`, `tests/test_channel_quick_actions.py::test_channel_wam_page_renders_structured_summary`.
- **남은 템플릿 트랜치:** 루트 잔여 `erp_*.html`·`templates/partials/erp_*` 평면 → 컨텍스트 루트 + `partials/shared/` (§6.5 이후 후속).

### 6.5 Template tree — root `erp_*_dashboard` thin shims removed (2026-04-15)

- **Removed (canonical paths only):** `templates/erp_measurement_dashboard.html`, `templates/erp_completion_dashboard.html`, `templates/erp_production_dashboard.html` — 이전에는 `measurement/dashboard.html`, `cs/completion_dashboard.html`, `production/dashboard.html`만을 `{% extends %}` 하던 루트 thin 파일이었음.
- **Live `render_template`:** `foms/web/measurement/dashboard.py` → `measurement/dashboard.html`; `foms/web/cs/completion_dashboard.py` → `cs/completion_dashboard.html`; `foms/web/production/dashboard.py` → `production/dashboard.html` (변경 없음).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_erp_dashboard_thin_wrappers_removed`.

### 6.6 Template tree — shipment dashboard physical path (2026-04-15)

- **Canonical layout:** `templates/shipment/dashboard.html` (기존 루트 `templates/erp_shipment_dashboard.html` 물리 이동, 별도 thin wrapper 없음).
- **Live `render_template`:** `apps/erp_shipment_page.py` → `shipment/dashboard.html` (Blueprint `erp_shipment_page`는 `foms/web/shipment`에서 re-export되는 전환기 레이어로 유지).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_shipment_dashboard_template`.

### 6.7 Template tree — construction dashboard physical path (2026-04-15)

- **Canonical layout:** `templates/construction/dashboard.html` (기존 루트 `templates/erp_construction_dashboard.html` 물리 이동).
- **Live `render_template`:** `foms/web/construction/dashboard.py` → `construction/dashboard.html`.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_construction_dashboard_template`.

### 6.8 Template tree — AS/CS dashboard physical path (2026-04-15)

- **Canonical layout:** `templates/cs/as_dashboard.html` (기존 루트 `templates/erp_as_dashboard.html` 물리 이동; `cs/completion_dashboard.html`과 동일 컨텍스트 루트).
- **Live `render_template`:** `apps/erp_as_page.py` → `cs/as_dashboard.html` (Blueprint `erp_as_page`는 기존 전환기 레이어로 유지).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_as_cs_dashboard_template`.

### 6.9 Template tree — orders / drawing / shipment settings (루트 `erp_*` 물리 이동, 2026-04-15)

- **Canonical layout:**
  - `templates/orders/dashboard.html` ← `erp_dashboard.html`
  - `templates/orders/history_dashboard.html` ← `erp_history_dashboard.html`
  - `templates/shipment/settings.html` ← `erp_shipment_settings.html`
  - `templates/drawing/workbench_dashboard.html` ← `erp_drawing_workbench_dashboard.html`
  - `templates/drawing/workbench_detail.html` ← `erp_drawing_workbench_detail.html`
- **Live `render_template`:** `apps/erp_dashboard.py` → `orders/dashboard.html`; `apps/erp_history_page.py` → `orders/history_dashboard.html`; `foms/api/shipment/settings.py` → `shipment/settings.html`; `apps/erp_drawing_workbench.py` → `drawing/workbench_*.html`.
- **Ops:** `scripts/ops/erp_build_step_runner.py` 대시보드 MVP/3패널 스텝은 `templates/orders/dashboard.html` 존재 여부로 검증 (기존 `scripts/ops/templates/` 오타 경로 제거).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_orders_dashboard_templates`, `test_strict_canonical_shipment_settings_page_template`, `test_strict_canonical_drawing_workbench_templates`.

### 6.10 Template tree — `partials/shared` ERP 패밀리 (2026-04-15)

- **Canonical layout:** `templates/partials/shared/erp_*.html` — 기존 `templates/partials/erp_*.html` **평면** 물리 이동 (파일명 유지). 스펙 §2.2.1 `partials/shared/` 정렬.
- **Include 갱신:** 모든 `{% include %}`, `{% from %}` 문자열을 `partials/shared/erp_*`로 통일 (대시보드·주문·도면·CS·생산·측정·출고 등 페이지 템플릿 + shared 내부 상호 include).
- **Legacy standalone:** `templates/erp_object.html` → `templates/orders/object.html` (현재 저장소 내 `render_template` 참조 없음; 보관용 페이지 자산).
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_partials_shared_erp_family`, `test_strict_canonical_orders_object_standalone_template`.

### 6.11 Asset tree — `static/js` + `static/css` §2.2.1 taxonomy (2026-04-15)

- **JS:** `static/js/wam/*` → `static/js/channel/*`; `static/js/erp/common_utils.js` 및 `column-resizer.js`, `script.js`, `upload-progress.js`, `erp-mobile-shell.js` → `static/js/runtime/`; `beta-shared.js`, `estimate-preview.js`, `history-mobile.js` → `static/js/orders/`; 출고 대시보드 스크립트 → `static/js/shipment/`. 레거시 `static/js/erp/measurement*.js` 및 루트 `measurement-image-export.js` **제거** (canonical은 `static/js/measurement/*`만).
- **CSS:** `static/css/erp-pro.css` + `static/css/erp-pro/` → `static/css/foundation/`; `style.css`, `style-pro-max.css` → `static/css/foundation/`; `static/css/wam/*` → `static/css/contexts/channel/`; `shipment-dashboard-columns.css` → `static/css/contexts/shipment/`.
- **템플릿 `url_for('static', …)`:** `layout.html`, 측정·출고·채널(WAM)·Beta partial 등 전 경로 갱신.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_static_js_css_taxonomy`; `tests/test_measurement_legacy_shims.py`, `tests/test_erp_beta_shared_form_scripts.py` 경로 정렬.
- **Regression tests (post-§6.11 path drift):** `tests/test_channel_wam_templates.py` — V1 fallback shell이 `css/contexts/channel/tokens.css`를 참조함을 검증 (구 `css/wam/` 문자열 제거). `tests/test_menu_config.py` — 파일 부재/손상 시 `_default_menu_config()` 첫 항목이 `order_list`임을 검증 (`foms/services/menu_config.py`와 일치).

### 6.12 Support tree — `tests/` §2.2.1 taxonomy (2026-04-15)

- **Domain tests:** 루트 `tests/test_*.py` **65개** → `tests/domains/` ( `tests/domains/__init__.py` 추가). `tests/` 루트에는 `conftest.py`, `__init__.py`, 하위 패키지만 유지.
- **Load / k6:** `tests/load/` → `tests/harness/load/` (`run-k6.ps1` repo 루트 계산 `..\..\..` + 형제 경로; trace/cookie 기본 문자열 갱신). `.gitignore` 동일 경로로 갱신.
- **SQLite compat:** `tests/domains/test_sqlite_startup_compat.py` — `scripts/migrations`를 `sys.path`에 넣어 `safe_schema_migration` 수집 가능; 첨부 부트스트랩은 `foms.api.attachments_internal.legacy`의 `get_db` 패치 (canonical API surface에 `get_db` 없음).
- **경로 민감 테스트:** `test_channel_wam_templates.py`, `test_measurement_legacy_shims.py`, `test_wdcalculator_unsaved_exit_guard_contract_node.py` — `Path(__file__).parents[2]`로 repo root 복구.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_tests_support_tree_taxonomy`.
- **문서:** `tests/README.md`, `foms/services/README.md` — 도메인/검증 명령 경로 갱신.
- **~~잔여 (scripts/tools)~~ → §6.13에서 처리.**

### 6.13 Scripts/tools — §2.2.1 `scripts/` + `tools/` 물리 트리 (2026-04-15, final-sweep)

- **`scripts/`:** 루트에 있던 단독 `.py`/`.ps1` 전부 **버킷 이동** — `ops/`(배포·스모크·부하·admin·Railway 동기화 등), `maintenance/`(지오코드·백필·진단·스케줄 백업), `migrations/`(Alembic 래퍼, ERP flat 백필, `test_migration`, **WDC 마이그레이션**). `scripts/` 루트에는 디렉터리 3개만 남김.
- **`tools/`:** `tools/migrate_wdcalculator_from_separate_db.py` → `scripts/migrations/migrate_wdcalculator_from_separate_db.py`. `tools/request_log.txt` 제거 + `.gitignore`에 등록. `tools/README.md`를 §2.2.1(`harness|smoke|research_center`)에 맞게 재작성.
- **실행 경로 보정:** `scripts/ops/*`, `scripts/maintenance/*`, `scripts/migrations/backfill_erp_flat_columns.py` 등 — 이전 `scripts/` 단일 루트 기준 `sys.path`를 **저장소 루트**(`..`, `..`)로 수정.
- **문서:** 운영 절차 문서 25개 내 `scripts/...` 문자열을 새 경로로 일괄 갱신.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_scripts_taxonomy`, `test_strict_canonical_tools_taxonomy`; `test_geocode_backfill_script_*`는 `scripts/maintenance/geocode_backfill.py` 파일 로드로 변경.

### 6.14 Docs tree — §2.2.1 `docs/` 물리 트리 + 루트 operational 문서 (2026-04-15)

- **Non-canonical top-level dirs (retired):** `docs/analysis/`, `docs/manual-artifacts/`, `docs/validation/` → **이동**
  - `docs/context/analysis/` — 브라우저 감리·ERP 모바일 분석 등 reference 번들 (`.gitignore`: `docs/context/analysis/browser_audit_*/`).
  - `docs/context/manual-artifacts/` — 오피스 참고물·수동 아티팩트.
  - `docs/guides/validation/` — 스펙 검증 체크리스트 등 (예: measurement map rebuild validation).
- **Root `docs/*.md` (운영 문서) → `docs/guides/`:** `DEPLOY_NOTES.md`, `RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `railway-notifications-migration.md`, `SYSTEM_DOCUMENTATION.md`, `WDPLANNER_INTEGRATION.md` — `AGENTS`/훅이 고정 참조하는 `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md`, `docs/ARCHIVE_INDEX.md`만 `docs/` 루트에 유지.
- **스펙 본문:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.2.1 트리에 `guides/validation/`, `context/analysis/`, `context/manual-artifacts/` 노드 반영.
- **문서·스크립트 참조:** `.gitignore`, harness spec, 진화·플랜·인시던트·GDM 절차·`scripts/ops/sync_local_to_railway.ps1` 등 경로 문자열 갱신.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_docs_taxonomy`.

### 6.15 Root manuals/scripts/data — `SFC-B10A` (2026-04-15)

- **Scope (plan §6.13):** bat files → `scripts/maintenance/`; harness working files → `docs/context/analysis/`; migration/test/railway guides → `docs/guides/`; `menu_config.json` → `data/admin/`; address learning JSON → `data/address/`; dump/SQLite canonical homes → `data/dumps/`, `data/localdb/` (see batch10a run record).
- **Runtime / sync:** `menu_config` path, `sync_local_to_railway.ps1` dump path, `migrate_local_to_remote.py` SQLite path, `foms_address_learning.py` default file.
- **Harness:** `prompt_router.py` / `run_codex.ps1` exact-match paths for analysis working files.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_manual_artifacts_sfc_b10a`.
- **Run record:** `docs/plans/2026-04-15-strict-final-canonical-tree-batch10a-root-manuals-scripts-data-run-record.md`.

### 6.16 Root deploy/config/tooling — `SFC-B10B` (2026-04-15)

- **Scope (plan §6.14):** `.cursorrules` removed; root `config/` removed (no live imports; `foms.services.rate_limit` is SoT); `railway_bootstrap.py` → `scripts/ops/railway_bootstrap.py`; root `pyrightconfig.json` → `tools/harness/pyrightconfig.json` + `.vscode/settings.json` for Pylance `extraPaths`; legacy GAE/Heroku hints `app.yaml` + `runtime.txt` → `docs/context/manual-artifacts/legacy-deploy/`.
- **Ops/docs:** `sync_local_to_railway.ps1`, Railway migration guides, `README.md` (GAE sample path), `.cursor/agents/GDM_EXECUTION_PLAN.md`.
- **Contract lock:** `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_strict_canonical_root_deploy_tooling_artifacts_sfc_b10b`.
- **Run record:** `docs/plans/2026-04-15-strict-final-canonical-tree-batch10b-root-deploy-config-tooling-run-record.md`.

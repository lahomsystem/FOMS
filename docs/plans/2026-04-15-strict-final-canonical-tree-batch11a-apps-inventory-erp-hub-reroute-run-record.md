# SFC-B11A — Apps inventory refresh + ERP hub canonical reroute (partial)

## 입력 문서
- `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §6.15–6.16

## Family / risk
- `apps/` overlay freeze: embedded authoritative list must match live `Get-ChildItem apps -Recurse -File` (`.py` only, no `__pycache__`).
- **Delta:** 실행 계획 embedded 목록에 **`apps/erp.py`가 누락**되어 있었음. PowerShell 실측(2026-04-15)에 `apps/erp.py` 존재 → 계획서 bullet 추가 + 계약 테스트로 동결.

## 변경 요약
1. **Canonical ERP hub:** `apps/erp.py` 본문을 `foms/web/erp/hub.py`로 이전, `foms/web/erp/__init__.py`에서 공개 심볼 export.
2. **소비자 reroute (제품 코드):** `foms.platform.blueprints`, `foms/api/*` 다수, `apps/dashboards.py`, `apps/erp_as_page.py`가 `foms.web.erp` 또는 `foms.web.erp` 경유 import로 전환.
3. **`apps/erp.py`:** B11B 제거 전까지 **thin shim** (`from foms.web.erp.hub import *`) — 인벤토리 행은 유지.
4. **계약:** `test_strict_canonical_apps_py_inventory_sfc_b11a_freeze` — 59개 `apps/**/*.py` 경로 frozen set 일치.
5. **권한 바인딩 테스트:** `test_erp_pages_use_canonical_erp_permissions_imports`의 허브 모듈 키를 `apps.erp` → `foms.web.erp.hub`로 갱신.

## 금지 범위
- `apps/` 디렉터리 제거(B11B)는 **reroute ledger 100% 닫힘 전 불가** — 본 배치는 hub 1패밀리 + 인벤토리 동결만 수행.

## SG* / 검증
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed** (신규 1: `test_strict_canonical_apps_py_inventory_sfc_b11a_freeze`)

## Slice 2 — Auth canonical facade + consumer reroute (2026-04-15)

### 변경 요약
1. **Canonical facade:** `foms/web/auth/__init__.py`가 `apps.auth`에서 재노출: `ROLES`, `TEAMS`, `auth_bp`, `get_user_by_id`, `is_password_strong`, `log_access`, `login_required`, `role_required` (구현체는 B11B 전까지 `apps/auth.py` 유지).
2. **Bulk reroute:** `foms/**/*.py`, `apps/**/*.py` 중 **`foms/web/auth/__init__.py`를 제외한** 모든 파일에서 `from apps.auth import` → `from foms.web.auth import` (**56개 파일**). 예외 파일만 `from apps.auth import` 유지.
3. **제외:** `backups/**`는 기존대로 `apps.auth` 참조 유지.

### SG* / 검증 (slice 2 이후 재실행)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 3 — Blueprint registry: ERP shell pages via `foms.web.*` facades (2026-04-15)

### Family / risk
- `foms/platform/blueprints.py`는 앱 부트스트랩의 **단일 Blueprint 등록 허브**; 여기서의 `from apps.*`는 consumer debt로 간주.
- 구현체는 B11B 전까지 `apps/erp_dashboard.py` 등에 유지; **canonical import 경로**만 `foms.web.*`로 통일.

### 변경 요약
1. **신규 facade 패키지 (각 `__init__.py`만):**  
   `foms/web/erp_dashboard`, `erp_history_page`, `storage_dashboard`, `user_pages`, `dashboards`, `excel_import` — 각각 대응하는 `apps.*` 모듈에서 Blueprint 심볼 재노출.
2. **`foms/platform/blueprints.py`:** 위 6개 모듈에 대한 import를 전부 `from foms.web.<pkg> import <bp>` 로 전환. **`from apps.` 문자열 0건** (본 파일 기준).

### SG* / 검증 (slice 3)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

### 남은 `foms/**` 내 `from apps.` (slice 3 시점)
- `foms/web/auth`, `cs`, `drawing`, `shipment`, `orders` 및 slice 3 facade 패키지들 — 구현 이전 단계에서는 **단일 파일 choke-point**로 `apps.*` 유지.

## Slice 4 — Bounded-context web packages: thin `foms.web.*` facades for AS / drawing / shipment / orders (2026-04-15)

### 변경 요약
1. **신규 facade 패키지:** `foms/web/erp_as_page`, `erp_drawing_workbench`, `erp_shipment_page`, `order_edit`, `order_pages` — 각각 대응 `apps.*`에서 Blueprint 재노출.
2. **패키지 재export 정렬:** `foms/web/cs/__init__.py`, `drawing/__init__.py`, `shipment/__init__.py`, `orders/__init__.py`는 더 이상 `apps.*`를 직접 import하지 않고 위 facade를 경유.

### Slice 4 이후 `foms/**`에서 `from apps.` 허용 위치
- `foms/web/auth/__init__.py` 및 **slice 3·4 thin facade `__init__.py`만** (`apps/*` 구현체 직접 연결).

### SG* / 검증 (slice 4)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 5 — Domain tests: canonical `foms.api` imports (no `apps.api` in `tests/domains`) (2026-04-15)

### 변경 요약
1. **`tests/domains/`** 다섯 파일에서 `from apps.api import …` / `import apps.api.wdcalculator` 제거.
2. **대응 canonical 경로:**  
   - `channel_integration` → `import foms.api.channel.channel_integration as channel_integration` (monkeypatch 대상 모듈 동일)  
   - `erp_orders_structured` → `from foms.api import erp_orders_structured`  
   - `orders` blueprint 계약 → `import foms.api.orders as orders_api`  
   - WDCalculator 경로 상수 패치 → `import foms.api.wdcalculator.blueprint as wd_module` (레거시 `apps.api.wdcalculator` shim이 `blueprint` 모듈로 치환되던 것과 동일)

### SG* / 검증 (slice 5)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 6 — Contract runtime tests: `foms_namespace_surface_tests` canonical `foms.api` imports (2026-04-15)

### 변경 요약
1. **`tests/contracts/runtime/foms_namespace_surface_tests.py`** — 채널·ERP·orders 바인딩 검증용 import를 `apps.api` → **`foms.api` 모듈 경로**로 전환 (레거시 shim과 동일 객체).
2. **의도적 유지:** `test_wr_h1_high_risk_cluster_strict_canonical` 내 `import apps.api.* as legacy_*` 동등성 검증, `test_wr_o1_orders_adapter_shell_*` 의 `from apps.api import orders as legacy_orders` — **B11B 전 shim 계약 증명용**.

### SG* / 검증 (slice 6)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 7 — Order pages/edit facades: geocode enqueue re-export + contract imports (2026-04-15)

### 변경 요약
1. **`foms/web/order_pages/__init__.py`**, **`foms/web/order_edit/__init__.py`** — slice 4 Blueprint 재노출에 더해 **`enqueue_geocode_order_address`** 를 동일 `apps.*` 구현체에서 재노출(`__all__`에 `order_*_bp` + `enqueue_geocode_order_address`). jobs 큐 정본(`foms.services.jobs.tasks`)과 동일 객체 바인딩을 계약으로 고정.
2. **`tests/contracts/runtime/foms_namespace_surface_tests.py`** — `test_order_pages_uses_canonical_jobs_queue_import`, `test_order_edit_uses_canonical_jobs_queue_import` 가 **`import foms.web.order_pages` / `import foms.web.order_edit`** 로 검증하도록 정렬(직접 `apps.order_*` 모듈 import 제거).

### SG* / 검증 (slice 7)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 8 — Auth / ERP AS facade re-exports + contract imports (`foms.web.erp.hub`) (2026-04-15)

### 변경 요약
1. **`foms/web/auth/__init__.py`** — `detach_user_references_for_delete` 를 `apps.auth`에서 재노출(계약 `test_auth_uses_canonical_user_deletion_import`가 `import foms.web.auth`만으로 검증 가능).
2. **`foms/web/erp_as_page/__init__.py`** — `sanitize_as_content_html` 재노출(`test_erp_as_page_uses_canonical_as_content_safety_import` → `import foms.web.erp_as_page`).
3. **`test_erp_pages_use_canonical_erp_display_imports`** — 허브 모듈만 **`import foms.web.erp.hub as erp`** 로 전환(나머지 페이지 모듈은 아직 구현체 `apps.*`에서 `_ensure_dict` 등 전체 표면 검증 → B11B 전 동일).
4. **의도적 유지:** `getsource`·템플릿 경로 검증 등 **구현 모듈 원문**이 필요한 테스트는 `from apps import erp_dashboard` 등 유지.

### SG* / 검증 (slice 8)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 9 — ERP shell facades: `erp_display` / `erp_policy` 바인딩 심볼 재노출 (2026-04-15)

### 변경 요약
1. **Thin facade 재노출 (구현은 `apps.*` 유지):**  
   - `foms/web/erp_as_page` — `_ensure_dict`, `apply_erp_display_fields_to_orders`, `get_today_kst` (+ 기존 `sanitize_as_content_html`, `erp_as_page_bp`).  
   - `foms/web/erp_dashboard` — `_ensure_dict`, `_erp_get_stage`, `_erp_alerts`, `_erp_has_media`, `STAGE_LABELS`, `recommend_owner_team`.  
   - `foms/web/erp_drawing_workbench` — display 바인딩 6종.  
   - `foms/web/erp_shipment_page` — `_ensure_dict`, `apply_erp_display_fields_to_orders`, `get_today_kst`.  
   - `foms/web/order_edit` — `_ensure_dict` (+ 기존 bp·geocode enqueue).
2. **계약:** `test_erp_pages_use_canonical_erp_display_imports` 가 위 페이지 모듈을 전부 **`import foms.web.*`** 로 검증; `test_erp_dashboard_uses_canonical_erp_policy_import` → `import foms.web.erp_dashboard`.
3. **의도적 유지:** `inspect.getsource(apps.erp_dashboard)` 등 **구현 파일 원문**이 필요한 테스트(`test_erp_permissions_lazy_callers_use_canonical_import_paths`, 템플릿 경로·`erp_history_page` lazy 검증 등)는 `apps.*` 유지.

### SG* / 검증 (slice 9)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 10 — ERP view 함수 facade 재노출 + `getsource`/템플릿 계약을 `foms.web.*`로 (2026-04-15)

### 변경 요약
1. **구현체는 `apps/*` 유지**, **뷰 함수 객체**만 thin facade에서 재노출(동일 함수 객체 → `inspect.getsource`는 구현 파일 원문 유지):  
   `history_dashboard` (`erp_history_page`), `erp_dashboard` (`erp_dashboard`), `erp_shipment_dashboard`, `erp_as_dashboard`, `erp_drawing_workbench_dashboard`, `erp_drawing_workbench_detail`.
2. **`foms_namespace_surface_tests`:**  
   `test_erp_display_lazy_callers_use_canonical_import_paths`, `test_strict_canonical_*_template(s)` (shipment·AS·orders·history·drawing workbench) 가 **`import foms.web.*`** 로 검증.
3. **권한 lazy (후속 Slice 11):** 동일 검증을 **`_REPO_ROOT / "apps" / "erp_dashboard.py"`** 직접 읽기로 옮겨 `from apps import` 제거.

### SG* / 검증 (slice 10)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 11 — `test_erp_permissions_lazy_callers`: repo 파일 직접 읽기 → `from apps import` 0건 (2026-04-15)

### 변경 요약
1. **`test_erp_permissions_lazy_callers_use_canonical_import_paths`** 가 `inspect.getsource(erp_dashboard)` + `from apps import erp_dashboard` 대신 **`(_REPO_ROOT / "apps" / "erp_dashboard.py").read_text()`** 로 동일 문자열(지연 import `foms.services.erp_permissions`) 검증.
2. **`foms_namespace_surface_tests.py` 내 `from apps import`** 구문 **0건** (WR-H1·WR-O1 등 **`import apps.api.*` shim 대조**는 유지).

### SG* / 검증 (slice 11)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 12 — WR-O1: `apps/api/orders/__init__.py` repo 직접 읽기 (shim 문자열 계약) (2026-04-15)

### 변경 요약
1. **`test_wr_o1_orders_adapter_shell_collapsed_to_canonical_module`** — 레거시 shim **본문** 검증을 `inspect.getsource(legacy_orders)` 대신 **`(_REPO_ROOT / "apps" / "api" / "orders" / "__init__.py").read_text(encoding="utf-8")`** 로 수행.
2. **문자열 계약:** `"from foms.api.orders import (" in legacy_init`, `"@orders_bp.route" not in legacy_init` (re-export-only 셸 유지).
3. **의도적 유지:** `from apps.api import orders as legacy_orders`로 **`legacy_orders.orders_bp is canonical_orders.orders_bp`** 동일 객체 검증; canonical 쪽 route 문자열은 기존대로 **`inspect.getsource(api_orders)`** (정본 모듈).

### SG* / 검증 (slice 12)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed** (WR-O1 단일 + full suite)

## Slice 13 — WR-H1: high-risk cluster shim 파일 repo 직접 읽기 (re-export-only 문자열 계약) (2026-04-15)

### 변경 요약
1. **`test_wr_h1_high_risk_cluster_strict_canonical`** — `blueprints.py` 금지 문자열·기존 **`import apps.api.*` 동일 객체 검증**은 유지.
2. **추가:** `notifications` / `attachments` / `chat` 셸은 **`read_text`** 로 `from foms.api.* import` 포함·해당 Blueprint에 대한 **`@*_bp.route` 미포함** 문자열 계약.
3. **`channel_integration.py`:** `import_module("foms.api.channel.channel_integration")` 문자열로 모듈 alias 셸 고정.

### SG* / 검증 (slice 13)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed** (WR-H1 단일 + full suite)

## Slice 14 — WR-H1: `channel_webhooks` / `channel_functions` / `channel_wam` alias 셸 파일·모듈 동일성 (2026-04-15)

### 변경 요약
1. **`test_wr_h1_high_risk_cluster_strict_canonical`** — `channel_integration`과 동일 패턴으로 **`apps/api/channel_{webhooks,functions,wam}.py`** 를 `read_text`로 `import_module("foms.api.channel.<name>")` 문자열 고정.
2. **런타임:** `import apps.api.channel_*` 와 `import foms.api.channel.channel_*` 가 **동일 모듈 객체**임을 assert (`channel_integration`과 대칭).

### SG* / 검증 (slice 14)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **580 passed**

## Slice 15 — 보조 API shim: backup/tasks/events/debug/quest + wdcalculator alias (blueprints 등록 축) (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_wr_h1_aux_api_shim_shells_strict_canonical` — `foms/platform/blueprints.py` 에서 `foms.api` 로만 등록되는 보조 축에 대응하는 **`apps/api/{backup,tasks,events,debug,quest}.py`** 는 디스크 상 `from foms.api.*` 재노출·**`@*_bp.route` 없음**; **`apps/api/wdcalculator.py`** 는 `import_module("foms.api.wdcalculator.blueprint")` alias.
2. **런타임 동일성:** 각 `apps.api.*` 와 정본 모듈/블루프린트 객체가 동일(`wdcalculator`는 모듈 객체 `is` 정본 `blueprint`).

### SG* / 검증 (slice 15)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **581 passed** (신규 1)

## Slice 16 — WR-H1: ERP orders lane `apps/api/erp_orders_*` + `erp_estimates` shim (디스크·동일 객체) (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_wr_h1_erp_orders_lane_shim_shells_strict_canonical` — `blueprints.py` 에서 `foms.api` 로 등록되는 **ERP 주문 레인**에 대응하는 루트 `apps/api/erp_orders_{blueprint,structured,drawing,revision,draftsman,production,construction,cs,as,completion,confirm}.py` 및 **`erp_estimates.py`** 에 대해:
   - 디스크: 정본 `from foms.api.*` (또는 structured 는 `import_module("foms.api.erp_orders_structured")` + `sys.modules`)·해당 `@{bp}.route` 없음.
   - 런타임: 레거시 모듈의 Blueprint(및 structured 는 **모듈 객체 `is`**)가 정본과 동일.
2. **의도적 제외:** `attachments_internal/**`, `chat/*` 하위 파일·`erp_map` 등은 별 slice(패밀리 단위).

### SG* / 검증 (slice 16)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **582 passed** (신규 1)

## Slice 17 — WR-H1: `erp_map` + `attachments_internal` / `chat` `blueprint` 모듈 alias (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_wr_h1_erp_map_and_package_blueprint_shims_strict_canonical` —  
   - **`apps/api/erp_map.py`:** `from foms.api.erp_map import erp_map_bp`·`@erp_map_bp.route` 없음; 런타임 `erp_map_bp` 동일 객체.  
   - **`apps/api/attachments_internal/blueprint.py`**, **`apps/api/chat/blueprint.py`:** `import_module("foms.api.*.blueprint")` + `sys.modules` 치환·`@` 없음; 런타임 레거시 모듈 `is` 정본.  
   - **`apps/api/attachments_internal/__init__.py`:** docstring에 정본 패키지 경로 고정.
2. **후속:** slice 18에서 `attachments_internal`·`chat` 나머지 submodule alias를 전부 계약 처리.

### SG* / 검증 (slice 17)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **583 passed** (신규 1)

## Slice 18 — WR-H1: `attachments_internal`·`chat` 나머지 submodule `import_module` alias 전부 (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_wr_h1_attachments_internal_and_chat_submodule_alias_shims_strict_canonical` — slice 17에서 다룬 `blueprint` 외 **`attachments_internal` 5모듈**(`common`,`legacy`,`order_routes`,`search`,`direct_upload`)·**`chat` 7모듈**(`routes*`,`socketio_handlers`,`utils`)에 대해 디스크 `import_module("foms.api…")`·`sys.modules`·`@` 부재·런타임 모듈 `is` 정본.

### SG* / 검증 (slice 18)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **584 passed** (신규 1)

## Slice 19 — WR-H1: 루트 `erp_shipment_settings.py` re-export vs `foms.api.shipment.settings` (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_wr_h1_erp_shipment_settings_shim_strict_canonical` — **`apps/api/erp_shipment_settings.py`** 디스크에 `from foms.api.shipment.settings import`·**`@erp_shipment_bp.route` 없음**; 런타임 `erp_shipment_bp`·`erp_shipment_settings`·`api_erp_shipment_*` 함수가 정본과 **동일 객체**.
2. **코드 변경 없음:** shim은 이미 정본 재노출 형태로 존재(B11A ledger 잠금).

### SG* / 검증 (slice 19)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **585 passed** (신규 1)

## Slice 20 — B11A closeout: `apps/api/__init__.py` 빈 패키지 앵커 고정 (2026-04-15)

### 변경 요약
1. **신규 계약:** `test_b11a_apps_api_package_init_empty_strict_canonical` — `test_strict_canonical_apps_py_inventory_sfc_b11a_freeze`에 포함된 **`apps/api/__init__.py`** 가 본문 공백만(빈 파일)임을 고정. 인벤토리에 나열된 나머지 `apps/api/**` 모듈은 기존 WR-H1·WR-O1 계약으로 이미 커버됨.
2. **의도:** 루트 패키지 `__init__`에 로직·import가 쌓여 WR-H1 디스크 검증을 우회하는 것을 방지.

### SG* / 검증 (slice 20)
- `python -c "import app; print('APP_OK')"` — OK
- `python tools/harness/verify_result.py --json` — OK
- `pytest tests` — **586 passed** (신규 1)

## §6.15 실행 계획 대조 — `SFC-B11A` sign-off (2026-04-15)

`docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §**6.15** 목표·규칙에 대한 본 배치 최종 대응:

| §6.15 요구 | 증거 (본 배치) |
|------------|----------------|
| live `apps/**/*.py` 인벤토리가 embedded baseline과 동일 | `test_strict_canonical_apps_py_inventory_sfc_b11a_freeze` + `_APPS_PY_INVENTORY_SFC_B11A` (실행 계획 §6.15 bullet 목록과 동일 경로 집합) |
| drift 시 run record 먼저 | slice 1 및 이후 SG* 블록에 재검증 기록 |
| `apps/api/**` child family 잠금 | §6.15 하위 bullet: `attachments_internal/*`, `chat/*`, `orders/__init__`, `channel_*`, `erp_*`, 단일 파일 축 — 각각 WR-H1·WR-O1 계약(slice 2~20)으로 디스크·런타임 동등성 고정 |
| consumer canonical reroute (B11B 전) | `foms.platform.blueprints` 등은 `foms.api.*` / `foms.web.*` (slice 2~8·10 등); 레거시 `apps/*`는 thin shim·facade 경유로만 유지 |

**§6.16 `SFC-B11B` 경계:** `apps/` **디렉터리 제거**는 실행 계획 §**6.16** — *top-level `apps/*.py`·nested `apps/api/**` child family가 모두 0이 되기 전*에는 removal 선언 불가. 본 배치는 §**6.15** 범위(동결 + reroute + 계약)만 닫는다.

## 다음 legal batch
- **`SFC-B11B` (§6.16):** `docs/plans/2026-04-15-strict-final-canonical-tree-batch11b-apps-overlay-retirement-run-record.md` — `apps/` overlay retirement; 전제·게이트·readiness 스냅샷은 해당 문서 §6.16 대조.
- **`SFC-B11C`~`B12`:** `B11B` 이후 순서 (계획 §6.17~6.19).

## Blocker / defer
- 없음 (본 slice는 계획 §6.15 inventory refresh 규칙 준수 후 진행).

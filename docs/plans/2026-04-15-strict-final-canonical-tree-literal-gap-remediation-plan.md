# Strict Final Canonical Tree Literal Gap Remediation Plan
> 작성일: 2026-04-15 | 상태: draft-for-execution
> 목적: `SFC-B12` 이후에도 남아 있는 **literal subtree drift**와 **false-green verification gap**만 다시 여는 보완 실행계획
> 상위 기준: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.2.1, `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md`
> 직접 입력: `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/harness/policy/DECISIONS.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-batch6-template-namespace-freeze-run-record.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-batch7-template-namespace-relocation-run-record.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-batch11b-apps-overlay-retirement-run-record.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-batch12-clean-room-closeout-run-record.md`

## 1. What

이 문서는 기존 strict plan을 폐기하지 않는다.

- 기존 tranche가 닫은 것:
  - root exact-match
  - root overlay (`apps/`, root `services/`, `src/`) 제거
  - root helper retirement
  - root template 파일 0
  - clean-room script green
- 이 문서가 다시 여는 것:
  - `§2.2.1`과 **literal하게 맞지 않는 하위 namespace drift**
  - 그 drift를 잡지 못한 **검증 체계의 blind spot**

즉, 이 문서는 `SFC-B12`의 root closeout을 뒤집는 문서가 아니라, `B12`가 놓친 **subtree exactness tranche**를 별도로 닫는 실행 runbook이다.

## 2. Authoritative Truth

### 2.1 이미 green인 것

아래는 본 문서에서 다시 열지 않는다.

- repo root allowlist match
- `apps/`, root `services/`, `src/` 부재
- root standalone helper 제거
- root `templates/*.html` 0
- `tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD` green

### 2.2 hard audit에서 확인된 material gap

#### LG-T1. illegal template namespace

`§2.2.1`의 `templates/` top-level tree는 `partials/shared/` + context dirs만 허용한다.

그런데 live tree에는 아래가 남아 있다.

- `templates/shared/layout.html`
- `templates/errors/error_404.html`
- `templates/errors/error_500.html`

런타임도 아직 이 경로를 직접 사용한다.

- `foms/platform/http.py` -> `render_template("errors/error_500.html")`
- `foms/platform/http.py` -> `render_template("errors/error_404.html")`
- 다수 템플릿 -> `{% extends "shared/layout.html" %}`

이 상태는 root template debt 해소는 맞지만, literal `§2.2.1`과는 다르다.

#### LG-W1. `foms/web/*`가 final context owner로 흡수되지 못함

현재 `foms/web/` 아래에는 final tree에 없는 namespace가 남아 있다.

- `dashboards`
- `erp`
- `erp_as_page`
- `erp_dashboard`
- `erp_drawing_workbench`
- `erp_history_page`
- `erp_shipment_page`
- `excel_import`
- `order_edit`
- `order_pages`
- `storage_dashboard`
- `user_pages`

이들은 대부분 `apps/`를 root에서 제거하는 과정에서 **context package로 흡수되지 않고 namespaced legacy bucket으로 재배치된 결과**다.

#### LG-A1. `foms/api/chat`와 `foms/api/attachments_internal`가 final context owner로 흡수되지 못함

현재 `foms/api/` 아래에는 final tree에 없는 namespace가 남아 있다.

- `chat`
- `attachments_internal`

`chat`은 실제로 page route `/chat`까지 포함하고 있어, API-only package로 남기기보다 `web/channel` + `api/channel`로 나눠야 한다.

`attachments_internal`은 file/attachment API family이므로 `foms/api/files`로 흡수되어야 한다.

#### LG-S1. `foms/services/erp_policy_internal`가 drawn final tree 밖에 남아 있음

현재 `foms/services/erp_policy_internal/`는 live package로 존재하지만, `§2.2.1`의 drawn final tree에는 없다.

이 family는 public surface가 아니라 `foms/services/erp_policy.py`의 private implementation bucket이므로, public wrapper는 유지하되 implementation file을 `orders/` 아래 flat leaf로 펴서 닫는다.

#### LG-V1. B12 검증이 literal subtree mismatch를 잡지 못함

`SFC-B12`는 root exact-match와 기존 strict tests를 근거로 `strict physical-tree achieved`를 선언했다.

하지만 live repo에서 아래가 동시에 참이다.

- `strict_canonical_b12_clean_room.ps1`는 green이다.
- `templates/shared`, `templates/errors`, extra `foms/web/*`, extra `foms/api/*`는 여전히 남아 있다.

즉 현재 gate는 **root는 잘 보지만 subtree literal drift는 놓친다.**

### 2.3 이번 보완 계획의 scope

이 문서는 아래만 다룬다.

- `templates/shared`, `templates/errors` 제거
- `foms/web/*` extra namespace 흡수
- `foms/api/chat`, `foms/api/attachments_internal` 흡수
- `foms/services/erp_policy_internal`를 `orders/` 아래 flat leaf들로 해체
- strict tests + clean-room script를 subtree exactness까지 확장

`channel` page owner는 신규 기능 추가가 아니다. 현재 repo에 이미 `/chat` page route와 `templates/channel/chat.html`이 있으므로, spec 보충 규칙에 따라 그 page owner를 `foms/web/channel`로 **정렬**하는 작업이다.

이 문서는 아래를 다시 열지 않는다.

- root `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py` compatibility surface
- `foms/services/*` root-level leaf module 전체 재배치 논쟁
- packaging reopen
- 새 기능, 새 schema, JSON shape 변경

이번 tranche에서 service tree는 **`erp_policy_internal` 1개만** 예외적으로 다룬다. public import surface는 유지하되, `foms/services/erp_policy.py`는 새 flat leaf들을 바라보도록 **internal import reroute 범위에서만** 수정할 수 있다. private package는 `orders/` 아래 flat leaf들로 해체한다.

## 3. Decision Lock

### 3.1 shared-shell / error 처리

이번 보완 tranche는 아래를 고정한다.

1. `templates/shared/`와 `templates/errors/`는 **closeout 시 존재하면 안 된다**.
2. `templates/partials/shared/`에는 full-page layout을 두지 않는다.
3. 공용 page shell은 아래 방식만 허용한다.
   - 각 context가 자기 `templates/<context>/layout.html`을 소유
   - 공통 head/nav/body fragment는 `templates/partials/shared/*.html` partial로 include
4. 404/500은 dedicated global template namespace를 만들지 않는다.
   - 기본 경로: `foms/platform/http.py` 내부의 helper가 **inline HTML response**를 반환
   - 이유: global error page는 특정 context owner가 없고, `templates/errors/`를 다시 합법화하면 strict literal goal을 무너뜨린다.

### 3.2 channel page split

`/chat`은 human-facing page가 있으므로 spec 보충 규칙의 “page가 생기면 matching `foms/web/<context>`를 만든다”를 따른다.

- page route + page-only JS response: `foms/web/channel/routes.py`
- JSON/API/socket handlers: `foms/api/channel/*`

즉 `chat`은 독립 context가 아니라 `channel` context 안의 legacy family다.

### 3.3 verification precedence

closeout acceptance는 아래 둘을 **동시에** 만족해야 한다.

1. 강화된 strict tests green
2. 강화된 clean-room script green

기존 `B12` script green만으로는 더 이상 completion을 선언할 수 없다.

## 4. Closed-Set Target

### 4.1 `templates/` top-level allowed dirs

`channel`은 spec 보충 규칙의 “page가 생기면 matching template root를 만든다”에 따라 허용한다.

closeout 시 허용:

- `partials`
- `orders`
- `measurement`
- `shipment`
- `drawing`
- `production`
- `construction`
- `cs`
- `wdcalculator`
- `admin`
- `auth`
- `channel`

closeout 시 금지:

- `shared`
- `errors`

### 4.2 `foms/web/` top-level allowed dirs

`channel`은 spec 보충 규칙의 “human-facing page가 생기면 matching `foms/web/<context>`를 만든다”에 따라 허용한다.

closeout 시 허용:

- `orders`
- `measurement`
- `shipment`
- `drawing`
- `production`
- `construction`
- `cs`
- `wdcalculator`
- `admin`
- `auth`
- `channel`

closeout 시 금지:

- `dashboards`
- `erp`
- `erp_as_page`
- `erp_dashboard`
- `erp_drawing_workbench`
- `erp_history_page`
- `erp_shipment_page`
- `excel_import`
- `order_edit`
- `order_pages`
- `storage_dashboard`
- `user_pages`

### 4.3 `foms/api/` top-level allowed dirs

closeout 시 허용:

- `orders`
- `measurement`
- `shipment`
- `drawing`
- `production`
- `construction`
- `cs`
- `wdcalculator`
- `channel`
- `files`
- `notifications`
- `admin`
- `auth`

closeout 시 금지:

- `chat`
- `attachments_internal`

### 4.4 `foms/services/` top-level allowed dirs

closeout 시 허용:

- `common`
- `admin`
- `orders`
- `measurement`
- `shipment`
- `drawing`
- `production`
- `construction`
- `cs`
- `wdcalculator`
- `channel`
- `files`
- `notifications`
- `auth`
- `jobs`

closeout 시 금지:

- `erp_policy_internal`

## 5. Target Home Ledger

### 5.1 template shell / error target map

| current | final target |
|---|---|
| `templates/shared/layout.html` | `templates/<context>/layout.html` family + exact shared partial set (`layout_head.html`, `layout_nav.html`, `layout_flash.html`, `layout_scripts.html`) |
| `templates/errors/error_404.html` | retire template; inline helper in `foms/platform/http.py` |
| `templates/errors/error_500.html` | retire template; inline helper in `foms/platform/http.py` |

### 5.2 `foms/web/*` absorption map

| current package | final owner |
|---|---|
| `foms/web/dashboards/routes.py` | merge into `foms/web/measurement/dashboard.py` |
| `foms/web/order_pages/routes.py` | move to `foms/web/orders/listing.py` |
| `foms/web/order_edit/routes.py` | move to `foms/web/orders/edit.py` |
| `foms/web/erp_dashboard/routes.py` | move to `foms/web/orders/dashboard.py` |
| `foms/web/erp_history_page/routes.py` | move to `foms/web/orders/history.py` |
| `foms/web/erp_as_page/routes.py` | move to `foms/web/cs/as_dashboard.py` |
| `foms/web/erp_drawing_workbench/routes.py` | move to `foms/web/drawing/workbench.py` |
| `foms/web/erp_shipment_page/routes.py` | move to `foms/web/shipment/dashboard.py` |
| `foms/web/user_pages/routes.py` `/profile` | merge into `foms/web/auth/routes.py` |
| `foms/web/user_pages/routes.py` `/change-logs`, `/security_logs` | move to `foms/web/admin/audit.py` |
| `foms/web/storage_dashboard/routes.py` | move to `foms/web/admin/storage.py` |
| `foms/web/excel_import/routes.py` | move to `foms/web/admin/excel_import.py` |
| `foms/api/chat/routes_pages.py` `/chat`, `/chat/scripts.js` | move to `foms/web/channel/routes.py` |
| `foms/web/erp/hub.py` `erp_bp` filter registration | move to `foms/platform/blueprints.py` |
| `foms/web/erp/hub.py` `_normalize_for_search` | move to `foms/services/erp_display.py` |
| `foms/web/erp/__init__.py` re-exported display helpers | callers reroute to `foms.services.erp_display` and package retire |

### 5.3 `foms/api/*` absorption map

| current package | final owner |
|---|---|
| `foms/api/chat/routes_messages.py` | `foms/api/channel/messages.py` |
| `foms/api/chat/routes_rooms.py` | `foms/api/channel/rooms.py` |
| `foms/api/chat/routes_files.py` | `foms/api/channel/files.py` |
| `foms/api/chat/socketio_handlers.py` | `foms/api/channel/socketio_handlers.py` |
| `foms/api/chat/utils.py` | `foms/api/channel/utils.py` |
| `foms/api/chat/blueprint.py` | `foms/api/channel/blueprint.py` |
| `foms/api/chat/routes.py` | split callers to new `foms/api/channel/*` files, then delete |
| `foms/api/attachments_internal/search.py` | `foms/api/files/search.py` |
| `foms/api/attachments_internal/order_routes.py` | `foms/api/files/order_attachments.py` |
| `foms/api/attachments_internal/direct_upload.py` | `foms/api/files/direct_upload.py` |
| `foms/api/attachments_internal/common.py` | `foms/api/files/common.py` |
| `foms/api/attachments_internal/legacy.py` | `foms/api/files/legacy.py` |
| `foms/api/attachments_internal/blueprint.py` | `foms/api/files/blueprint.py` |

### 5.4 `foms/services/*` absorption map

| current package | final owner |
|---|---|
| `foms/services/erp_policy_internal/constants.py` | `foms/services/orders/erp_policy_constants.py` |
| `foms/services/erp_policy_internal/data_access.py` | `foms/services/orders/erp_policy_data_access.py` |
| `foms/services/erp_policy_internal/permissions.py` | `foms/services/orders/erp_policy_permissions.py` |
| `foms/services/erp_policy_internal/quests.py` | `foms/services/orders/erp_policy_quests.py` |
| `foms/services/erp_policy_internal/tasks.py` | `foms/services/orders/erp_policy_tasks.py` |
| `foms/services/erp_policy.py` internal imports | reroute to `foms.services.orders.erp_policy_*` flat leafs |

## 6. Fixed Batch Order

### 6.1 `SLG-B0` — Reopen gate + truth lock

docs-only.

필수 산출물:

- 이 보완 계획서 authoring
- live extra-dir inventory freeze
- `B12` green이 false-positive일 수 있다는 note를 run record에 남길 준비
- non-goal freeze: root compat persistence surface, packaging reopen

검증:

- no code change
- `APP_OK`

### 6.2 `SLG-B1` — Verification hardening freeze

docs/tests only.

필수 작업:

- `tests/contracts/runtime/foms_namespace_surface_tests.py`에 아래 새 gate를 설계하고 freeze
  - `templates/` top-level closed set
  - `foms/web/` top-level closed set
  - `foms/api/` top-level closed set
  - `foms/services/` top-level closed set
  - no `templates/shared/layout.html`
  - no `templates/errors/*`
  - no `render_template("errors/...")`
  - no `{% extends "shared/layout.html" %}`
  - no `{% extends ... %}` inside `templates/partials/shared/*.html`
  - no `<!DOCTYPE html>` or `<html` inside `templates/partials/shared/*.html`
  - no `foms/services/orders/erp_policy_internal/`
- `tools/harness/strict_canonical_b12_clean_room.ps1`를 확장해 root compare 외에 `templates/`, `foms/web/`, `foms/api/`, `foms/services/` subtree closed-set compare를 추가하는 설계를 문서화

추가 규칙:

- 이 batch는 test red를 허용한다.
- 아직 code가 landing되지 않았으므로 전체 suite green이 아니어도 된다.
- 단, 새 gate는 다음 batch가 구현할 drift를 정확히 가리켜야 하며 vague wording 금지.

### 6.3 `SLG-B2` — Template shell/error remediation

code batch.

필수 작업:

- 각 active template context에 `layout.html` 추가
  - `templates/orders/layout.html`
  - `templates/measurement/layout.html`
  - `templates/shipment/layout.html`
  - `templates/drawing/layout.html`
  - `templates/production/layout.html`
  - `templates/construction/layout.html`
  - `templates/cs/layout.html`
  - `templates/wdcalculator/layout.html`
  - `templates/admin/layout.html`
  - `templates/auth/layout.html`
  - `templates/channel/layout.html`
- 공통 shell fragment를 `templates/partials/shared/*.html`로 분리
- 공통 shell fragment 파일명은 아래 넷으로 고정한다
  - `templates/partials/shared/layout_head.html`
  - `templates/partials/shared/layout_nav.html`
  - `templates/partials/shared/layout_flash.html`
  - `templates/partials/shared/layout_scripts.html`
- 기존 모든 템플릿의 `{% extends "shared/layout.html" %}`를 context-owned path로 바꾼다
- `templates/shared/layout.html` 삭제
- `foms/platform/http.py`의 404/500 handler를 helper-generated inline HTML response로 전환
- `templates/errors/error_404.html`, `templates/errors/error_500.html` 삭제
- `foms/platform/http.py` build info의 template string 업데이트

검증:

- `rg -n 'shared/layout.html' templates foms` -> 0
- `rg -n 'errors/error_404.html|errors/error_500.html' foms templates` -> 0
- focused pytest + `APP_OK` + `verify_result.py --json`

### 6.4 `SLG-B3` — Web absorption I (`measurement` + `orders`)

code batch.

필수 작업:

- `foms/web/dashboards/routes.py` 내용을 `foms/web/measurement/dashboard.py`로 합친다
- `foms/web/order_pages/routes.py`를 `foms/web/orders/listing.py`로 이동
- `foms/web/order_edit/routes.py`를 `foms/web/orders/edit.py`로 이동
- `foms/web/erp_dashboard/routes.py`를 `foms/web/orders/dashboard.py`로 이동
- `foms/web/erp_history_page/routes.py`를 `foms/web/orders/history.py`로 이동
- blueprint registration과 import 경로를 새 owner 기준으로 갱신
- empty wrapper/old package dir 삭제

검증:

- `foms/web/dashboards`, `order_pages`, `order_edit`, `erp_dashboard`, `erp_history_page` dir 없음
- measurement/orders routes smoke
- focused pytest + `APP_OK`

### 6.5 `SLG-B4` — Web absorption II (`cs` + `drawing` + `shipment` + `admin/auth split`)

code batch.

필수 작업:

- `foms/web/erp_as_page/routes.py` -> `foms/web/cs/as_dashboard.py`
- `foms/web/erp_drawing_workbench/routes.py` -> `foms/web/drawing/workbench.py`
- `foms/web/erp_shipment_page/routes.py` -> `foms/web/shipment/dashboard.py`
- `foms/web/erp/hub.py` 해체
  - template filter registration은 `foms/platform`으로 이동
  - `_normalize_for_search` consumer는 `foms.services.erp_display`로 reroute
  - `_ensure_dict`, `_can_modify_sales_domain`, `apply_erp_display_fields*` consumer는 `foms.services.erp_display` 직접 import로 reroute
- `foms/web/user_pages/routes.py`를 route owner 기준으로 split
  - `/profile` -> `foms/web/auth/routes.py`
  - `/change-logs`, `/security_logs` -> `foms/web/admin/audit.py`
- `foms/web/storage_dashboard/routes.py` -> `foms/web/admin/storage.py`
- `foms/web/excel_import/routes.py` -> `foms/web/admin/excel_import.py`
- old package dir 삭제

검증:

- `foms/web/erp_as_page`, `erp_drawing_workbench`, `erp_shipment_page`, `user_pages`, `storage_dashboard`, `excel_import` dir 없음
- `foms/web/erp` dir 없음
- admin/auth/shipment/drawing/cs pages smoke
- focused pytest + `APP_OK`

### 6.6 `SLG-B5` — Channel page/API split + attachments absorption

code batch.

필수 작업:

- `foms/web/channel/routes.py` 생성
  - `/chat`
  - `/chat/scripts.js`
- `foms/api/chat/routes_pages.py` 제거
- `foms/api/chat/routes_messages.py` -> `foms/api/channel/messages.py`
- `foms/api/chat/routes_rooms.py` -> `foms/api/channel/rooms.py`
- `foms/api/chat/routes_files.py` -> `foms/api/channel/files.py`
- `foms/api/chat/blueprint.py` -> `foms/api/channel/blueprint.py`
- `foms/api/chat/socketio_handlers.py` -> `foms/api/channel/socketio_handlers.py`
- `foms/api/chat/utils.py` -> `foms/api/channel/utils.py`
- `foms/api/chat` 패키지 retire
- `foms/api/attachments_internal/*`를 `foms/api/files/*`로 흡수
- `foms/api/attachments_internal/blueprint.py` -> `foms/api/files/blueprint.py`
- `foms/api/attachments_internal/legacy.py` -> `foms/api/files/legacy.py`
- `foms/api/attachments_internal` 패키지 retire
- channel/files blueprints registration을 canonical owner 기준으로 정리

검증:

- `foms/api/chat`, `foms/api/attachments_internal` dir 없음
- `foms/web/channel` dir 존재
- chat page + chat API + attachment API smoke
- focused pytest + `APP_OK`

### 6.7 `SLG-B6` — Service subtree single-gap closure

code batch.

필수 작업:

- `foms/services/erp_policy_internal/constants.py` -> `foms/services/orders/erp_policy_constants.py`
- `foms/services/erp_policy_internal/data_access.py` -> `foms/services/orders/erp_policy_data_access.py`
- `foms/services/erp_policy_internal/permissions.py` -> `foms/services/orders/erp_policy_permissions.py`
- `foms/services/erp_policy_internal/quests.py` -> `foms/services/orders/erp_policy_quests.py`
- `foms/services/erp_policy_internal/tasks.py` -> `foms/services/orders/erp_policy_tasks.py`
- `foms/services/erp_policy.py`의 internal import 경로를 새 flat leaf들로 전환
- old `foms/services/erp_policy_internal` dir 삭제
- public import surface `from foms.services.erp_policy import ...`는 그대로 유지

검증:

- `foms/services/erp_policy_internal` dir 없음
- `foms/services/orders/erp_policy_internal` dir 없음
- `foms/services/orders/erp_policy_constants.py`, `erp_policy_data_access.py`, `erp_policy_permissions.py`, `erp_policy_quests.py`, `erp_policy_tasks.py` 존재
- quest/tasks/dashboard focused pytest + `APP_OK`

### 6.8 `SLG-B7` — Verification hardening land + closeout

docs/tests/tooling batch.

필수 작업:

- `SLG-B1`에서 설계한 closed-set tests를 최종 green 상태로 land
- `tools/harness/strict_canonical_b12_clean_room.ps1`를 subtree compare까지 확장
- `docs/AI_STATUS.md`의 `strict physical-tree achieved` 문구는 새 closeout 증거로만 갱신
- 새 final closeout run record 작성

closeout acceptance:

- `templates/shared` 없음
- `templates/errors` 없음
- `foms/web/*` extra namespace 없음
- `foms/api/chat` 없음
- `foms/api/attachments_internal` 없음
- `foms/services/erp_policy_internal` 없음
- `foms/services/orders/erp_policy_internal` 없음
- `foms/services/` top-level child set == `§4.4` allowlist
- 강화된 strict tests green
- 강화된 clean-room script green

## 7. Review Loop

이 plan을 따르는 다음 LLM은 각 code batch 직후 아래 3축 감리를 반드시 돌린다.

### 7.1 reviewer A — literal tree reviewer

확인 항목:

- closeout target에 없는 dir가 남았는가
- old dir 삭제 없이 new owner만 추가한 split-brain이 생겼는가
- `templates/shared`, `templates/errors` 같은 “새 generic bucket”이 재생성되었는가
- `foms/services/erp_policy_internal` 같은 known extra subtree가 다시 남아 있는가
- `foms/services/orders/erp_policy_internal` 같은 nested leftover가 새 canonical owner 아래 숨어 있지 않은가

### 7.2 reviewer B — runtime/import reviewer

확인 항목:

- blueprint registration이 새 owner를 가리키는가
- page route가 아직 API package에 남아 있지 않은가
- old package import가 runtime code에 남아 있지 않은가

### 7.3 reviewer C — proof reviewer

확인 항목:

- 새 strict tests가 실제 drift를 잡는가
- clean-room script가 subtree diff를 같이 보도록 확장되었는가
- `APP_OK`, `verify_result.py --json`, focused/full pytest의 증거가 run record에 있는가

### 7.4 stop rule

severity rubric:

- High
  - `§4` closed-set 위반이 실제로 남아 있음
  - old owner와 new owner가 동시에 남아 split-brain 상태
  - target-home이 둘 이상으로 열려 있음
  - batch가 behavior/schema/scope freeze를 넘는 변경을 요구함
  - gate가 green인데 계획이 정의한 금지 상태가 실제 디스크에 남아 있음
- Medium
  - single target-home은 고정됐지만 caller/test/tooling proof가 하나 이상 누락
  - closeout 증거는 있으나 focused regression 또는 clean-room 한 축이 비어 있음
  - directory retirement는 됐지만 old import/test reference가 남아 follow-up 없이는 재발 가능
  - shell/partial/layout split이 exact file contract 없이 기술돼 재구현 분기가 생김

아래 중 하나라도 참이면 다음 batch로 넘어가면 안 된다.

- High finding 1개 이상
- Medium finding 2개 이상
- `§4` closed-set 금지 dir가 1개라도 남아 있는데 gate가 green
- clean-room script가 subtree closed-set compare를 아직 수행하지 않는데 green만 보고 closeout을 주장함

## 8. First-Turn Operator Prompt

다음 LLM은 첫 턴에 아래 이해를 먼저 고정한다.

1. root cleanup은 다시 하지 않는다.
2. 이번 tranche는 `templates/shared|errors`, `foms/web/{dashboards,erp,erp_as_page,erp_dashboard,erp_drawing_workbench,erp_history_page,erp_shipment_page,excel_import,order_edit,order_pages,storage_dashboard,user_pages}`, `foms/api/{chat,attachments_internal}`, `foms/services/erp_policy_internal`, verification blind spot만 다룬다.
3. 첫 code batch 전에 `SLG-B1` verification hardening 설계를 읽고, closeout tests가 무엇을 잡아야 하는지 다시 적는다.
4. `shared-shell/error`는 generic bucket 유지가 아니라 **retire**가 목표다.
5. `/chat` page는 `web/channel`, chat JSON/socket은 `api/channel`, attachments는 `api/files`가 owner다.

## 9. Non-Negotiable Notes

- 기존 `B12` green은 historical evidence이지, 이번 tranche의 completion proof가 아니다.
- 이 문서는 `§2.2.1`을 느슨하게 바꾸기 위한 문서가 아니다.
- spec clarification 없이 `templates/shared`나 `templates/errors`를 재합법화하면 실패다.
- route behavior를 바꾸지 말고 owner path만 바꿔야 한다.
- split-brain 금지. old package를 남겨야 한다면 temporary shim이어야 하고, 같은 batch run record에 removal condition이 있어야 한다.

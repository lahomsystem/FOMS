# SFC-B6 — Template namespace freeze

> Batch: `SFC-B6`  
> 실행일: 2026-04-15  
> 성격: **docs** (실행 계획 `§6.9`, 카탈로그 §5)  
> 선행: `SFC-B5A` ~ `SFC-B5C`  
> Branch: **Branch A** (코드 변경 없음; `B7` 입력 동결)

## 1. 목표

- `templates/*.html` **루트 단일 레벨** 파일을 전수 분류하고 `SFC-B7`에서 적용할 **target namespace**를 고정한다.
- **§6.9 shared-shell / error 규칙**: `templates/partials/shared/`는 cross-context **partial 전용**이므로 `layout.html`·`error_404.html`·`error_500.html`을 그 디렉터리로 **그대로** 옮기는 경로는 금지. 본 배치에서는 **Branch B docs-stop 없이** B7에서 사용할 합법적 홈을 명시한다.

## 2. 루트 템플릿 전수 (exhaustive baseline)

PowerShell: `Get-ChildItem -Path templates -File -Filter "*.html"` (2026-04-15)

**총 25개** (`templates/<name>.html`, 하위 폴더 제외):

| # | 파일 |
|---|------|
| 1 | `add_order.html` |
| 2 | `add_user.html` |
| 3 | `admin.html` |
| 4 | `change_logs.html` |
| 5 | `chat.html` |
| 6 | `edit_order.html` |
| 7 | `edit_user.html` |
| 8 | `error_404.html` |
| 9 | `error_500.html` |
| 10 | `index.html` |
| 11 | `layout.html` |
| 12 | `login.html` |
| 13 | `map_view.html` |
| 14 | `metropolitan_dashboard.html` |
| 15 | `profile.html` |
| 16 | `regional_dashboard.html` |
| 17 | `register.html` |
| 18 | `security_logs.html` |
| 19 | `self_measurement_dashboard.html` |
| 20 | `storage_dashboard.html` |
| 21 | `trash.html` |
| 22 | `upload.html` |
| 23 | `user_list.html` |
| 24 | `wdplanner.html` |
| 25 | `wdplanner_setup.html` |

(계획서 §6.9 예시 리스트와 동일 범위; `chat.html` 포함 전수 일치. 추가 루트 파일 없음.)

## 3. 컨텍스트 분류 (필수 축)

| 분류 | 루트 파일 | B7 target 디렉터리 (고정) |
|------|-----------|---------------------------|
| orders-owned | `add_order.html`, `edit_order.html`, `index.html`, `trash.html` | `templates/orders/` |
| measurement-owned | `regional_dashboard.html`, `metropolitan_dashboard.html`, `self_measurement_dashboard.html`, `map_view.html` | `templates/measurement/` |
| admin-owned | `admin.html`, `change_logs.html`, `security_logs.html`, `storage_dashboard.html`, `upload.html` | `templates/admin/` |
| auth-owned | `login.html`, `register.html`, `profile.html`, `add_user.html`, `edit_user.html`, `user_list.html` | `templates/auth/` |
| channel-owned | `chat.html` | `templates/channel/` |
| wdcalculator-owned | `wdplanner.html`, `wdplanner_setup.html` | `templates/wdcalculator/` |
| shared-shell (full page, **not** partials bucket) | `layout.html` | `templates/shared/layout.html` |
| HTTP error pages | `error_404.html`, `error_500.html` | `templates/errors/error_404.html`, `templates/errors/error_500.html` |

### 3.1 §6.9 shared-shell 판정 (Branch B 회피)

- **금지**: 위 셋을 `templates/partials/shared/`로 **풀페이지 그대로** 이동.
- **B7 허용 홈**: `templates/shared/`(크로스 컨텍스트 **shell** 전용 신규 네임스페이스), `templates/errors/`(HTTP 오류 페이지 전용).  
  → partial은 기존대로 `templates/partials/shared/*`에만 두고, `layout.html` 이동 후 전역 `{% extends "shared/layout.html" %}` 등으로 갱신하는 것은 **B7 코드 배치**에서 수행.

## 4. File-by-file target-home ledger (B7 이행용)

| 현재 경로 | B7 이후 경로 |
|-----------|----------------|
| `templates/add_order.html` | `templates/orders/add_order.html` |
| `templates/edit_order.html` | `templates/orders/edit_order.html` |
| `templates/index.html` | `templates/orders/index.html` |
| `templates/trash.html` | `templates/orders/trash.html` |
| `templates/regional_dashboard.html` | `templates/measurement/regional_dashboard.html` |
| `templates/metropolitan_dashboard.html` | `templates/measurement/metropolitan_dashboard.html` |
| `templates/self_measurement_dashboard.html` | `templates/measurement/self_measurement_dashboard.html` |
| `templates/map_view.html` | `templates/measurement/map_view.html` |
| `templates/admin.html` | `templates/admin/admin.html` |
| `templates/change_logs.html` | `templates/admin/change_logs.html` |
| `templates/security_logs.html` | `templates/admin/security_logs.html` |
| `templates/storage_dashboard.html` | `templates/admin/storage_dashboard.html` |
| `templates/upload.html` | `templates/admin/upload.html` |
| `templates/login.html` | `templates/auth/login.html` |
| `templates/register.html` | `templates/auth/register.html` |
| `templates/profile.html` | `templates/auth/profile.html` |
| `templates/add_user.html` | `templates/auth/add_user.html` |
| `templates/edit_user.html` | `templates/auth/edit_user.html` |
| `templates/user_list.html` | `templates/auth/user_list.html` |
| `templates/chat.html` | `templates/channel/chat.html` |
| `templates/wdplanner.html` | `templates/wdcalculator/wdplanner.html` |
| `templates/wdplanner_setup.html` | `templates/wdcalculator/wdplanner_setup.html` |
| `templates/layout.html` | `templates/shared/layout.html` |
| `templates/error_404.html` | `templates/errors/error_404.html` |
| `templates/error_500.html` | `templates/errors/error_500.html` |

## 5. Current render caller ledger (제품 코드, `backups/**` 제외)

`render_template('...')` / `render_template("...")` 로 **직접** 참조되는 루트 템플릿:

| 템플릿 | 호출 모듈 (대표) |
|--------|------------------|
| `add_order.html` | `apps/order_pages.py` |
| `add_user.html` | `apps/auth.py` |
| `admin.html` | `foms/web/admin/routes.py` |
| `change_logs.html` | `apps/user_pages.py` |
| `chat.html` | `foms/api/chat/routes_pages.py` |
| `edit_order.html` | `apps/order_edit.py` |
| `edit_user.html` | `apps/auth.py` |
| `error_404.html` | `foms/platform/http.py` |
| `error_500.html` | `foms/platform/http.py` |
| `index.html` | `apps/order_pages.py` |
| `login.html` | `apps/auth.py` |
| `map_view.html` | `foms/api/erp_map.py` |
| `metropolitan_dashboard.html` | `apps/dashboards.py` |
| `profile.html` | `apps/user_pages.py`, `apps/auth.py` |
| `regional_dashboard.html` | `apps/dashboards.py` |
| `register.html` | `apps/auth.py` |
| `security_logs.html` | `apps/user_pages.py` |
| `self_measurement_dashboard.html` | `apps/dashboards.py` |
| `storage_dashboard.html` | `apps/storage_dashboard.py` |
| `trash.html` | `foms/web/orders/trash.py` |
| `upload.html` | `apps/excel_import.py` |
| `user_list.html` | `apps/auth.py` |
| `wdplanner.html` | `foms/web/wdcalculator/planner.py` |
| `wdplanner_setup.html` | `foms/web/wdcalculator/planner.py` |

### 5.1 `layout.html` (간접 참조)

- **직접** `render_template('layout.html')` 호출은 제품 코드 기준 **없음**.
- **다수 페이지**가 `{% extends "layout.html" %}` 로 참조 (grep: `templates/**/*.html`). B7에서 파일 이동 시 **전역 extends 문자열** 일괄 갱신 필요.

### 5.2 기타 참조 (`layout` 메타)

- `foms/platform/http.py`: 디버그/진단용 컨텍스트에 `"template": "templates/layout.html"` 문자열 포함 — B7에서 물리 경로 정렬 시 동기화 대상.

## 6. Dead legacy (`delete-after-proof`)

| 파일 | 판정 | 근거 |
|------|------|------|
| (해당 없음) | **live** | 위 25개 모두 `render_template` 또는 `extends` 체인으로 소비됨; 소비자 0인 루트 파일 없음 |

## 7. 검증

| 검증 | 결과 |
|------|------|
| 본 배치 코드/테스트 변경 | **없음** (docs-only) |
| `python -c "import app; print('APP_OK')"` | `APP_OK` (회귀 스모크) |
| `python tools/harness/verify_result.py --json` | `success: true` |

## 8. 다음 배치

- **`SFC-B7`** — Template namespace relocation (계획 §6.10): 루트 `templates/*.html` **0**, `templates/auth/` 실체화, `SG7` 감소, smoke/pytest.

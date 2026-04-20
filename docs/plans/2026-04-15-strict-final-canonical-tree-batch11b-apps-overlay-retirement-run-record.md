# SFC-B11B — Apps overlay retirement (§6.16) run record

> 상위: `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §**6.16**  
> 선행 종료: `SFC-B11A` (§6.15) — `docs/plans/2026-04-15-strict-final-canonical-tree-batch11a-apps-inventory-erp-hub-reroute-run-record.md` sign-off

## 목표 (계획서 그대로)

- Root에서 **`apps/` 디렉터리(overlay)를 제거**한다.
- `SF3` / `apps/` transition overlay **0**에 해당.

## 하드 게이트 (§6.16 추가 규칙)

1. **`B11A` reroute ledger가 100% 닫히기 전에는 실행 불가** — B11A는 §6.15 sign-off로 닫힘.
2. **top-level `apps/*.py`와 nested `apps/api/**` child family가 모두 0이 되기 전**에는 `apps/` directory removal을 **선언할 수 없다.**  
   - 여기서 **0**의 실무적 판정: 제품 런타임 경로에서 `apps`에 대한 **구현 소유권**이 canonical(`foms/*`)으로 옮겨졌고, **`foms/**`에 `from apps.` / `import apps`가 더 이상 필요 없음** + `apps/**`를 등록하는 진입점이 제거됨 + 계약 테스트가 새 트리를 검증하도록 갱신됨.

## 2026-04-15 — Readiness snapshot (GDM)

### `foms/web/*` — `apps.<module>` 구현 의존 제거 현황 (루트 `apps/*.py` 본문)

**2026-04-15:** 아래 12개 패키지 모두 **`foms/web/<pkg>/routes.py` 정본** + **`foms/web/<pkg>/__init__.py`는 `routes`만** + 루트 **`apps/<module>.py`는 재노출 shim** 패턴으로 정렬 완료. 제품 트리 `foms/**`에서 `from apps.` / `import apps` **0건** (실측).

| # | Facade 패키지 | 현재 의존 |
|---|----------------|-----------|
| 1 | `foms/web/auth` | **완료 (2026-04-15):** 구현 `foms/web/auth/routes.py`; `apps/auth.py`는 `foms.web.auth` 재노출 shim |
| 2 | `foms/web/dashboards` | **완료 (2026-04-15):** 구현 `foms/web/dashboards/routes.py`; `apps/dashboards.py`는 `foms.web.dashboards` 재노출 shim |
| 3 | `foms/web/user_pages` | **완료 (2026-04-15):** 구현 `foms/web/user_pages/routes.py`; `apps/user_pages.py`는 `foms.web.user_pages` 재노출 shim |
| 4 | `foms/web/storage_dashboard` | **완료 (2026-04-15):** 구현 `foms/web/storage_dashboard/routes.py`; `apps/storage_dashboard.py`는 `foms.web.storage_dashboard` 재노출 shim |
| 5 | `foms/web/excel_import` | **완료 (2026-04-15):** 구현 `foms/web/excel_import/routes.py`; `apps/excel_import.py`는 `foms.web.excel_import` 재노출 shim |
| 6 | `foms/web/erp_dashboard` | **완료 (2026-04-15):** 구현 `foms/web/erp_dashboard/routes.py`; `apps/erp_dashboard.py`는 `foms.web.erp_dashboard` 재노출 shim |
| 7 | `foms/web/erp_history_page` | **완료 (2026-04-15):** 구현 `foms/web/erp_history_page/routes.py`; `apps/erp_history_page.py`는 `foms.web.erp_history_page` 재노출 shim |
| 8 | `foms/web/erp_as_page` | **완료 (2026-04-15):** 구현 `foms/web/erp_as_page/routes.py`; `apps/erp_as_page.py`는 `foms.web.erp_as_page` 재노출 shim |
| 9 | `foms/web/erp_drawing_workbench` | **완료 (2026-04-15):** 구현 `foms/web/erp_drawing_workbench/routes.py`; `apps/erp_drawing_workbench.py`는 `foms.web.erp_drawing_workbench` 재노출 shim |
| 10 | `foms/web/erp_shipment_page` | **완료 (2026-04-15):** 구현 `foms/web/erp_shipment_page/routes.py`; `apps/erp_shipment_page.py`는 `foms.web.erp_shipment_page` 재노출 shim |
| 11 | `foms/web/order_pages` | **완료 (2026-04-15):** 구현 `foms/web/order_pages/routes.py`; `apps/order_pages.py`는 `foms.web.order_pages` 재노출 shim |
| 12 | `foms/web/order_edit` | **완료 (2026-04-15):** 구현 `foms/web/order_edit/routes.py`; `apps/order_edit.py`는 `foms.web.order_edit` 재노출 shim |

> 참고: `apps/erp.py` 등 일부 파일은 이미 `foms.web.erp.hub` 재노출 shim만 남음(B11A). B11B에서는 **디렉터리 삭제**까지 포함해 정리한다.

### `apps/api/**` thin shim

- 런타임은 `foms.api.*` 정본 + `apps.api.*` re-export 조합.  
- B11B 종료 시: **Blueprint 등록은 전부 `foms.api.*`**, `apps/api/**` 파일 **삭제** 후 `tests/contracts/runtime/foms_namespace_surface_tests.py` 내 WR-H1 / WR-O1 **legacy 대조 테스트**를 “삭제된 경로 불가” 또는 **정본-only** 계약으로 **재작성**해야 한다 (계획 §1 금지: 새 fail-open shim 추가 없음).

### 수용 검증 (배치 종료 시 필수)

- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `pytest tests` 전체 통과
- PowerShell: `Get-ChildItem apps -ErrorAction SilentlyContinue` → **경로 없음** (또는 git에서 제거 확인)
- `rg "from apps\\.|import apps" --glob "*.py" foms app.py run.py` (제품 트리) → **0건** (`backups/**`는 별도 정책)

## Slices

- B11B는 **파일 패밀리/의존 그래프**에 따라 여러 slice로 쪼개는 것이 안전하다. 각 slice 완료 시 본 문서에 동일 형식으로 **변경 요약 / SG* / pytest 카운트**를 기록한다.

### Slice B11B-1 — `auth` (2026-04-15)

- **변경:** `apps/auth.py` 본문 → `foms/web/auth/routes.py`; `foms/web/auth/__init__.py`는 `routes`에서만 재노출; 루트 `apps/auth.py`는 canonical 재노출 shim(레거시 `import apps.auth` 호환).
- **품질:** `log_access`의 bare `except:` → `except Exception:`.
- **검증:** `APP_OK`, `verify_result.py --json`, `pytest tests` **586 passed**.

### Slice B11B-2 — `dashboards` (2026-04-15)

- **변경:** `apps/dashboards.py` 본문 → `foms/web/dashboards/routes.py`; `foms/web/dashboards/__init__.py`는 `routes`에서만 재노출; 루트 `apps/dashboards.py`는 canonical 재노출 shim.
- **검증:** `APP_OK`, `verify_result.py --json`, `pytest tests` **586 passed**.

### Slice B11B-3 — `user_pages` (2026-04-15)

- **변경:** `apps/user_pages.py` 본문 → `foms/web/user_pages/routes.py`; `foms/web/user_pages/__init__.py`는 `routes`에서만 재노출; 루트 `apps/user_pages.py`는 canonical 재노출 shim.
- **검증:** `APP_OK`, `pytest tests` **586 passed**.

### Slice B11B-4 — `storage_dashboard` (2026-04-15)

- **변경:** `apps/storage_dashboard.py` 본문 → `foms/web/storage_dashboard/routes.py`; `foms/web/storage_dashboard/__init__.py`는 `routes`에서만 재노출; 루트 `apps/storage_dashboard.py`는 canonical 재노출 shim.
- **검증:** `APP_OK`, `verify_result.py --json`, `pytest tests` **586 passed**.

### Slice B11B-5 — `excel_import` (2026-04-15)

- **변경:** `apps/excel_import.py` 본문 → `foms/web/excel_import/routes.py`; `foms/web/excel_import/__init__.py`는 `routes`에서만 재노출; 루트 `apps/excel_import.py`는 canonical 재노출 shim.
- **검증:** `APP_OK`, `verify_result.py --json`, `pytest tests` **586 passed**.

### Slice B11B-6 — B11B-12 — ERP·주문 페이지 묶음 (2026-04-15)

- **변경:** `erp_dashboard`, `erp_history_page`, `erp_as_page`, `erp_drawing_workbench`, `erp_shipment_page`, `order_pages`, `order_edit` 각각 `apps/<module>.py` 본문 → `foms/web/<pkg>/routes.py`; 패키지 `__init__.py`는 `routes`에서만 재노출; 루트 `apps/<module>.py`는 canonical 재노출 shim.
- **계약:** `test_erp_pages_use_canonical_erp_permissions_imports` — `apps.*` 모듈 소스 대신 **`foms.web.*.routes`** 에서 `from foms.services.erp_permissions import` 확인. `test_erp_permissions_lazy_callers_use_canonical_import_paths` — 소스 경로를 **`foms/web/erp_dashboard/routes.py`** 로 갱신.
- **검증:** `APP_OK`, `verify_result.py --json`, `pytest tests` **586 passed**.

## Blocker (현재)

- **루트 `apps/*.py`에 남은 구현 본문 — 없음** (전부 shim). **남은 §6.16 본편:** `apps/api/**` thin shim 일괄 제거·Blueprint/registry 정본-only 전환·`tests/contracts/runtime/foms_namespace_surface_tests.py` WR-H1/WR-O1 갱신·`rg "from apps\\.|import apps"` 제품 트리 0·`apps/` 디렉터리 삭제 (clean-room).

## 다음 legal batch (계획 §4.1)

- `SFC-B11C` — root `services/` overlay retirement (§6.17) — **B11B 종료 후**

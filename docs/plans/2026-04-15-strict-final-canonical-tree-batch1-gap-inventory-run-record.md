# SFC-B1 — Exact gap inventory + scoreboard freeze

> Batch: `SFC-B1`  
> 실행일: 2026-04-15  
> 선행: `SFC-B0` — `docs/plans/2026-04-15-strict-final-canonical-tree-batch0-readiness-gate-run-record.md`  
> 입력: 실행 계획 `§3`, `§2.5`, `§6.2`; live repo root + `foms/`, `templates/`, `static/`, `apps/`, `services/`, `src/`

## 1. 목표

- strict gap을 family 단위로 authoritative 스냅샷으로 잠근다.  
- `SG1`~`SG7` **실측 baseline**을 본 문서에 고정한다.  
- `§2.5` root debt ledger를 live tree 기준으로 보정한다.

## 2. SG* scoreboard — baseline freeze (after `SFC-B1`)

| Metric | 의미 | provisional (계획 §3) | **B1 live (2026-04-15)** | closeout target |
|--------|------|----------------------|---------------------------|-----------------|
| `SG1` | overlay root count (`apps`, root `services`, `src`) | 3 | **3** | 0 |
| `SG2` | canonical → root helper import line count | 28 | **26** (`foms/` only; 아래 §3.1) | 0 |
| `SG3` | missing `§2.2.1` directory node count | 11 | **11** | 0 |
| `SG4` | root plain template render callsite lines | 14 | **46** (`foms/`+`apps/`; 아래 §3.2) | 0 |
| `SG5` | root non-spec artifact (vs B12 allow recipe + noise 제외) | 33 | **33** (아래 §3.3) | 0 |
| `SG6` | clean-room exact-match diff | 미측정 | **미측정** (`SFC-B12`) | 0 |
| `SG7` | root plain `templates/*.html` file count | 25 | **25** | 0 |

### 2.1 Supplementary (overlay, `SG2` 범위 밖 참고)

- `apps/**/*.py`에서 `from constants import` **8줄** (파일 8개: `erp_history_page`, `erp_dashboard`, `order_pages`, `excel_import`, `order_edit`, `storage_dashboard`, `dashboards`, `auth` 미포함 duplicate 확인됨 — 실제 8파일).  
- `apps/` 제거 후 소멸 예정이므로 strict `SG2` 본표는 **`foms/`만**으로 고정한다.

## 3. 측정 방법·근거

### 3.1 `SG2` — `foms/**/*.py`

| 부채 종류 | 측정 | 줄 수 |
|-----------|------|-------|
| `from constants import ...` | workspace grep `foms` | **16** |
| `foms_address_converter` / `foms_map_generator` / `map_config` / `erp_automation` / `erp_order_text_parser` / `simple_backup_system` | grep `foms/**/*.py` | **10** |
| **합계** | | **26** |

대표 파일: `foms/platform/app_factory.py`, `foms/api/erp_orders_structured.py`, `foms/api/backup.py`, `foms/services/jobs/tasks.py`(지연 import), `foms/api/measurement.py`, `foms/api/address.py`, `foms/api/erp_map.py`, `foms/api/measurement_map.py`, `foms/api/orders/nearby.py`.

> 계획서 provisional 28과의 차이: 동일 grep 기준으로 **26**으로 수렴. (이전 스냅샷은 줄 단위·모듈 단위 계산 차이 가능.)

### 3.2 `SG4` — root `templates/<name>.html` 직접 참조

**정의 (B1):** `foms/` 및 `apps/` 내 `*.py`에서, `render_template(` 호출에 **한 줄에** `'<name>.html'` / `"<name>.html"` 형태로 경로에 `/` 없이 지정한 줄 수. `backups/` 제외.

- `foms/`: **7**줄 (`foms/web/admin/routes.py` `admin.html`, `foms/web/orders/trash.py`, `foms/platform/http.py`×2, `foms/api/erp_map.py`, `foms/web/wdcalculator/planner.py`×2)  
- `apps/`: **39**줄 (다수 분기·`auth.py` 집중)  
- **합계: 46**

> 계획서 §2.3의 “14건”은 과거 스냅샷이다. B1에서는 **동일 정의로 재측정한 46**을 authoritative baseline으로 잠근다. `SFC-B6`에서 ledger·caller map으로 재검증한다.

### 3.3 `SG5` — B12 `allowedRoot` 대비 초과 항목

`docs/plans/...-execution-plan.md` `§6.19`의 `$allowedRoot` 배열과 `Get-ChildItem` 실제 루트를 `Compare-Object` 한 결과, **`=>`만** 세되 다음 **local noise는 제외** (계획 `§2.6`):

- 제외: `__pycache__`, `.pytest_cache`, `.gstack` (3)  
- **순수 SG5 계열: 36 − 3 = 33** — 계획 provisional **33**과 일치.

### 3.4 `SG3` — missing directory nodes (`Test-Path`)

| 경로 | 존재 |
|------|------|
| `foms/api/files` | 없음 (`foms/api/files.py` flat) |
| `foms/api/measurement` | 없음 (`measurement.py` flat) |
| `templates/auth` | 없음 |
| `static/js/{drawing,production,construction,cs,admin,auth}` | 모두 없음 |
| `static/css/{layout,components}` | 모두 없음 |

**합계: 11**

### 3.5 `SG1` / `SG7`

- `SG1`: `Test-Path` — `apps`, `services`, `src` 모두 존재 → **3**  
- `SG7`: `Get-ChildItem templates -File -Filter *.html` → **25** 파일 (계획 §2.3 목록과 동일 세트)

## 4. §2.5 Root debt ledger — live 보정 요약

계획서 표의 provisional target은 유효하다. live에서 **추가 확인**:

- 루트 `config/` 존재 — ledger 행과 일치.  
- `SCheduler/`, `Add In Program/` — 스펙 §2.2.1 허용 존; debt 아님.  
- B12 `allowedRoot`에는 `config/`가 없음 — **`SFC-B10A/B10B`**에서 consumer proof 후 이동 또는 정리 대상으로 유지.

## 5. Family register + 판정

| Family | B1 판정 | 비고 |
|--------|---------|------|
| constants/config | **mainline** | `SFC-B2`→`B3` |
| address/map helper | **mainline** | `SFC-B5A` |
| ERP helper | **mainline** | `SFC-B5B` |
| backup/helper | **mainline** | `SFC-B5C` |
| template namespace | **needs-split** (§6.9) | `layout`/`error_*`는 shared partial 분해 vs docs-stop — `SFC-B6`에서 선택 |
| static namespace | **mainline** | `SFC-B8` |
| API package-shape | **mainline** | `SFC-B9` |
| root manuals/scripts/data | **mainline** | `SFC-B10A` |
| root deploy/config/tooling | **mainline** | `SFC-B10B` |
| apps consumer migration | **mainline** | `SFC-B11A`→`B11B` |
| root `services/` retirement | **mainline** | `SFC-B11C` |
| `src/` retirement | **mainline** | `SFC-B11D` |

**Branch B (`docs-stop`):** 본 배치에서 필수 불명확으로 인한 중단 조건 없음.

## 6. 금지 범위

- `SFC-B1`는 **문서·인벤토리 전용**. runtime 코드·template 이동·테스트 변경 **없음**.

## 7. 검증

- Docs-only: `APP_OK` 생략 가능하나 회귀 없음 확인을 위해 선택 실행:

```text
python -c "import app; print('APP_OK')"
```

(실행 시 성공해야 함.)

## 8. SG* before / after (batch 단위)

| Metric | Before (B1 시작) | After (B1 종료) |
|--------|------------------|-----------------|
| SG1–SG7 | §3 provisional / 미기록 | 본 문서 §2 표 **freeze** |

## 9. 다음 legal batch

- **`SFC-B2`** — Root constants/config family freeze (`…batch2-…-run-record.md` 예정).

## 10. Blocker / defer

- 없음. `business_calendar` 등 기존 defer는 계획서 Out of scope 유지.

## 11. GDM 감리 Round 1 (B1 산출물)

| 검사 | 결과 |
|------|------|
| `SG*`가 수치로 고정되었는가 | 예 |
| §2.5 ledger와 live가 대응되는가 | 예 (요약 §4) |
| `SG4` 재측정이 계획 §2.3과 불일치하는 이유가 문서화되었는가 | 예 (§3.2) |
| 다음 배치(`SFC-B2`) 진입 가능한가 | 예 |

**판정:** **합격** — Round 2는 `SFC-B2` 산출물에 대해 substantive patch만.

# SLG-B0 — Reopen gate + truth lock (run record)

> 배치: `SLG-B0` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.1)  
> 실행일: 2026-04-15  
> 성격: **docs-only** — 코드 변경 없음

## 1. 목적

literal-gap remediation tranche 진입 전에 **live 디스크 기준 extra-namespace 인벤토리를 동결**하고, 본 tranche **non-goal**과 **`SFC-B12` 검증 한계**를 run record에 고정한다.

## 2. Non-goal freeze (이번 tranche에서 다시 열지 않음)

- Root `db.py` / `models.py` / `wdcalculator_db.py` / `wdcalculator_models.py` **compatibility surface** 재논의·이동
- **`src/foms`**, **packaging-only `pyproject.toml`**, **Wave 9 packaging reopen** — `docs/harness/policy/DECISIONS.md` [2026-04-11] Step 8 defer와 정합
- `foms/services/` top-level 전면 재배치(이번 tranche는 **`erp_policy_internal` 단일 갭**만 SLG-B6에서 처리)

## 3. `SFC-B12` green과 false-positive 위험 (note)

- `tools/harness/strict_canonical_b12_clean_room.ps1`는 **repo root 대비** exact-match에 최적화되어 있으며, **`templates/`·`foms/web/`·`foms/api/`·`foms/services/` subtree closed-set**은 당시 gate 범위에 포함되지 않았을 수 있다.
- 따라서 과거 **B12 green만으로** `templates/shared|errors`, extra `foms/web/*`, `foms/api/chat|attachments_internal`, `foms/services/erp_policy_internal` 부재를 **completion으로 단정하면 안 된다** (본 tranche SLG-B1~B7에서 보강).

## 4. Live extra-dir inventory freeze (증거 시점: 2026-04-15)

PowerShell: `Get-ChildItem -Path <path> -Directory` (Windows, repo root 기준).

### 4.1 `templates/` top-level (알파벳 순)

`admin`, `auth`, `channel`, `construction`, `cs`, `drawing`, **`errors`**, `measurement`, `orders`, `partials`, `production`, **`shared`**, `shipment`, `wdcalculator`

**§4.1 closed-set 대비:** 금지 항목 **`shared`**, **`errors`** 가 **아직 존재** (LG-T1, closeout 전).

### 4.2 `foms/web/` top-level (개발 산출물 `__pycache__` 제외)

`admin`, `auth`, `construction`, `cs`, **`dashboards`**, `drawing`, **`erp`**, **`erp_as_page`**, **`erp_dashboard`**, **`erp_drawing_workbench`**, **`erp_history_page`**, **`erp_shipment_page`**, **`excel_import`**, `measurement`, **`order_edit`**, **`order_pages`**, `orders`, `production`, `shipment`, **`storage_dashboard`**, **`user_pages`**, `wdcalculator`

**§4.2 closed-set 대비:** §4.2 **금지** 목록에 해당하는 디렉터리가 **전부 live로 존재** (LG-W1).

### 4.3 `foms/api/` top-level (`__pycache__` 제외)

`admin`, **`attachments_internal`**, `auth`, `channel`, **`chat`**, `construction`, `cs`, `drawing`, `files`, `measurement`, `notifications`, `orders`, `production`, `shipment`, `wdcalculator`

**§4.3 closed-set 대비:** 금지 **`chat`**, **`attachments_internal`** 존재 (LG-A1).

### 4.4 `foms/services/` top-level (`__pycache__` 제외)

`admin`, `auth`, `channel`, `common`, `construction`, `cs`, `drawing`, **`erp_policy_internal`**, `files`, `jobs`, `measurement`, `notifications`, `orders`, `production`, `shipment`, `wdcalculator`

**§4.4 closed-set 대비:** 금지 **`erp_policy_internal`** 존재 (LG-S1).  
허용 집합과 비교 시 **`channel`**, **`files`**, **`jobs`** 가 live top-level에 있음 — 본 tranche 범위는 §5.4 및 `erp_policy_internal` 해체이며, 전체 services 트리 전면 정렬은 non-goal(상기 §2).

## 5. 검증 (코드 변경 없음)

| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | **APP_OK** (2026-04-15 실행) |

`verify_result.py --json` / full pytest: B0 필수 산출물 아님 (계획서 §6.1: no code change + APP_OK).

## 6. SLG-B0 후 3축 review loop (요약)

| Reviewer | 결과 |
|----------|------|
| A — literal tree | drift가 §4와 계획서 §2.2와 **일치**함을 확인. split-brain 신규 발생 없음(코드 변경 없음). |
| B — runtime/import | 변경 없음 — 회귀 N/A. |
| C — proof | APP_OK 증거 확보. B12-only green을 본 tranche completion으로 쓰지 말 것은 §3에 명시. |

**Stop rule:** 해당 없음 (High/Medium 미발생, 금지 dir 잔존을 green으로 주장하지 않음).

## 7. 다음 배치

- **`SLG-B1`** — Verification hardening freeze (`tests/contracts/runtime/foms_namespace_surface_tests.py` gate 설계, `strict_canonical_b12_clean_room.ps1` subtree compare 설계 문서화).

## 8. 산출물 체크리스트 (§6.1)

- [x] 보완 계획서 baseline: `2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` (실행 입력으로 고정)
- [x] live extra-dir inventory freeze (본 문서 §4)
- [x] B12 false-positive 가능성 note (본 문서 §3)
- [x] non-goal freeze (본 문서 §2)
- [x] `APP_OK`

**`docs/AI_STATUS.md`:** SLG-B7 closeout 증거 전까지 갱신하지 않음 (오퍼레이터 규칙).

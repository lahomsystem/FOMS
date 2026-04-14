# Wave 6 Batch W6-B5 — Files helper package pilot canonicalization

> **batch ID:** W6-B5  
> **risk axis:** code / local pilot  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed** (PASS)  
> **git HEAD (시점):** `240781907c445669ba320142835a7c297f0ba769` — 작업 트리에 본 batch delta 반영(미커밋 가능).  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.6  
> **선행:** `W6-B4` (`docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md`)

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `foms/services/files/*`, flat/root shim, `apps/excel_import.py` (import만), tests, README | `business_calendar` touch, `storage`/channel/erp_policy/bootstrap 본편 refactor |
| | HTTP/upload 동작·반환 shape 변경 |

## 2. Delta summary

| 파일 | 변경 |
|------|------|
| `foms/services/files/file_utils.py` | **신규** — canonical |
| `foms/services/files/__init__.py` | **신규** |
| `foms/services/file_utils.py` | flat shim → 패키지 re-export |
| `services/file_utils.py` | root shim → 패키지 re-export |
| `apps/excel_import.py` | `from foms.services.files.file_utils import allowed_file` |
| `tests/test_file_utils.py` | 패키지 경로 import |
| `tests/test_foms_namespace_imports.py` | `test_files_package_submodule_matches_flat_and_legacy` |
| `foms/services/README.md` | files 섹션 W6-B5 반영 |

## 3. W6-B4 contract export (import smoke)

**Frozen symbol:** `allowed_file` (`docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md` §7).

## 4. Verification

| 검증 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | **PASS** |
| `python tools/harness/verify_result.py --json` | **PASS** |
| `python -m pytest tests/test_file_utils.py tests/test_foms_namespace_imports.py -q` | **PASS** (144 passed) |
| ReadLints (touched paths) | **PASS** |

### 4.1 Import smoke

```text
python -c "import services.file_utils as legacy; import foms.services.file_utils as flat; from foms.services.files import file_utils as pkg; export_name = 'allowed_file'; assert getattr(legacy, export_name) is getattr(pkg, export_name); assert getattr(flat, export_name) is getattr(pkg, export_name); print('W6_FILE_UTILS_NS_OK')"
```

**Result:** `W6_FILE_UTILS_NS_OK`

## 5. Direction Lock (§2.6)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | `files/file_utils`가 SoT. |
| 2 | **Y** | shim 유지, 제거는 Wave 8. |
| 3 | **Y** | flat 흡수. |
| 4 | **Y** | `files` helper context. |
| 5 | **Y** | 최소 파일 증가. |
| 6 | **적용** | README에 compat 명시. |
| 7 | **Y** | README 갱신. |
| 8 | **Y** | notifications와 대칭. |
| 9 | **Y** | excel import는 경로만. |
| 10 | **Y** | 확장자 로직 변경 없음. |

## 6. Outcome

- **PASS**

## 7. Next legal batch (Branch A)

**`W6-B6`** — Lane status register  
**Run record:** `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md`

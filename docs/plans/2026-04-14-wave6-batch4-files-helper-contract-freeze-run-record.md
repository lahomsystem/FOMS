# Wave 6 Batch W6-B4 — Files helper contract freeze

> **batch ID:** W6-B4  
> **risk axis:** docs / contract  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed** (PASS; §8.13 / `late-file-utils-stop` **미발동**)  
> **git HEAD (시점):** `240781907c445669ba320142835a7c297f0ba769` (문서-only; 작업 트리에 선행 batch delta 병존 가능)  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.5  
> **선행:** `W6-B3` 완료 (`docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md`)

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record, `foms/services/README.md` (files 섹션) | runtime 코드 변경 |
| | spec/archive reference wiring (W6-B7 전용 제외) |
| | `storage` 레인을 본 helper pilot에 포함하는 서술 |

## 2. Inputs consumed (계획서 §5.5 step 1)

| 파일 | 역할 |
|------|------|
| `foms/services/file_utils.py` | flat canonical 구현 (`allowed_file`, `allowed_erp_media_file`) |
| `services/file_utils.py` | 루트 shim |
| `apps/excel_import.py` | `allowed_file` 단일 caller (non-test product) |
| `tests/test_file_utils.py` | canonical 동작 |
| `tests/test_foms_namespace_imports.py` | `test_legacy_file_utils_shim_preserves_canonical_contract` |

## 3. Public callable / import contract table (freeze)

| 항목 | 고정 값 |
|------|---------|
| **Public API** | `allowed_file(filename: str) -> bool`, `allowed_erp_media_file(filename: str) -> bool` |
| **`__all__`** | `["allowed_file", "allowed_erp_media_file"]` (순서 고정) |
| **의존** | `constants.ALLOWED_EXTENSIONS`, `constants.ERP_MEDIA_ALLOWED_EXTENSIONS` |

## 4. Preferred package shape (§5.5 step 2 — 고정)

| 역할 | 경로 |
|------|------|
| **Canonical (post W6-B5)** | `foms/services/files/file_utils.py` |
| **Package marker** | `foms/services/files/__init__.py` |
| **Flat compat** | `foms/services/file_utils.py` |
| **Root compat** | `services/file_utils.py` |

## 5. Caller matrix (freeze 시점)

| Caller | Import | W6-B5 정렬 의도 |
|--------|--------|-----------------|
| `apps/excel_import.py` | `from foms.services.file_utils import allowed_file` | W6-B5에서 `foms.services.files.file_utils` 경로로 정렬 |
| `tests/test_file_utils.py` | `from foms.services.file_utils import ...` | 동일 배치에서 패키지 경로 + shim 동치 유지 |
| `tests/test_foms_namespace_imports.py` | legacy vs namespaced flat | 패키지 도입 후 동일 객체 검증 확장 |

## 6. `storage` 제외 (explicit)

동일 `files` 컨텍스트 이름을 쓰더라도 **`foms/services/storage.py` / singleton·런타임 init 레인은 본 pilot에 포함하지 않는다** (계획서 §5.5 step 3, §2.3 queue).

## 7. W6-B5 import smoke — 고정 export 심볼

계약에 공개 심볼이 2개이므로, **import smoke 1개 분기**에 쓸 대표 심볼을 아래로 고정한다: **`allowed_file`**

(동일 검증 루틴에서 `allowed_erp_media_file`도 `getattr`로 추가 assert 가능하나, 계획서 템플릿은 단일 `export_name`이므로 **`allowed_file`**를 run record 진실원으로 둔다.)

## 8. Direction Lock (§2.6)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | file_utils 레인 계약 표로 SoT 고정. |
| 2 | **N (B4)** | shim 유지; 감소는 W6-B5 이후/Wave 8. |
| 3 | **Y** | flat을 `files` 패키지 leaf로 흡수 예정(FR19). |
| 4 | **Y** | `files`가 helper 컨텍스트 패키지. |
| 5 | **Y** | 문서-only, 파일 수 동결. |
| 6 | **적용** | retirement는 Wave 8. |
| 7 | **Y** | README files 섹션 반영. |
| 8 | **Y** | notifications pilot과 대칭 패턴. |
| 9 | **Y** | docs vs code 경계 유지. |
| 10 | **Y** | 계약 문서화만. |

## 9. Verification (docs-only)

| 항목 | 결과 |
|------|------|
| Runtime 코드 변경 | **없음** |
| README / 본 run record 정합 | **일치** |
| Baseline 인용 | `W6-B0` repo sanity (`APP_OK` + `verify_result` 채택, 리비전 `2407819...`) |

## 10. Outcome

- **PASS** — file_utils lane contract 및 preferred shape **freeze** 완료.

## 11. Next legal batch (Branch A)

**`W6-B5`** — Files helper package pilot canonicalization  
**Run record:** `docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md` (시작 시 생성)

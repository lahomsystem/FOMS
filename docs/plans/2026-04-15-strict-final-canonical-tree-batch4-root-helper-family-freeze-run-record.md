# SFC-B4 — Root helper family freeze

> Batch: `SFC-B4`  
> 실행일: 2026-04-15  
> 성격: **docs-only** (실행 계획 `§6.5`)  
> 선행: `SFC-B0`~`SFC-B3`  
> 입력: `docs/plans/2026-04-15-strict-final-canonical-tree-100-percent-execution-plan.md` §6.5 authoritative family map

## 1. 목표

- 루트에 남은 **helper / config / artifact 부채**를 패밀리별로 분류해 **child batch 전용 입력 문서**로 동결한다.
- 본 배치는 **코드 변경 없음**. 실제 이동·import 제거는 **`SFC-B5A` / `B5B` / `B5C`** 등에서만 수행한다.

## 2. 금지 (본 배치)

1. 루트 파일 임의 rename/move 없이 **대규모 코드 수정**.  
2. 계획 §6.5에 없는 **새 패밀리 축 임의 추가** (필요 시 별도 Spec).  
3. `backups/**`를 SG 게이트 실측 대상에 포함한 수치 혼입.

## 3. Authoritative family map (계획 §6.5 + 저장소 실물 2026-04-15)

### 3.1 Address / map

| 자산 | 루트 존재 | 비고 |
|------|-----------|------|
| `foms_address_converter.py` | 예 | 루트 shim → `scripts/ops/foms_address_converter.py` 로드 |
| `foms_map_generator.py` | 예 | 동일 패턴 shim |
| `map_config.py` | 예 | 설정 모듈 (Kakao 등); **직접 구현** |

**제품 트리 소비자 (import baseline — B5A 입력):**  
`foms/api/address.py`, `foms/api/measurement.py`, `foms/api/measurement_map.py`, `foms/api/erp_map.py`, `foms/api/orders/nearby.py`, `foms/services/jobs/tasks.py`, `tests/domains/test_foms_map_generator.py`  
(`scripts/ops/*`·루트 shim 내부는 B5A 범위에서 canonical 경로로 수령.)

### 3.2 ERP parse / automation

| 자산 | 루트 존재 | 비고 |
|------|-----------|------|
| `erp_automation.py` | 예 | shim → `scripts/ops/erp_automation.py` |
| `erp_order_text_parser.py` | 예 | shim → `scripts/ops/erp_order_text_parser.py` |

**제품 트리 소비자 (B5B 입력):**  
`foms/api/erp_orders_structured.py` (`apply_auto_tasks`, `parse_order_text`); 계약 `tests/contracts/runtime/foms_namespace_surface_tests.py` (`erp_automation` 네임스페이스 검증).  
`scripts/ops/erp_build_step_runner.py` (지연 import).

### 3.3 Backup runtime helper

| 자산 | 루트 존재 | 비고 |
|------|-----------|------|
| `simple_backup_system.py` | 예 | shim → `scripts/ops/simple_backup_system.py` |

**제품 트리 소비자 (B5C 입력):**  
`foms/api/backup.py` — 계획 §6.8: 장기적으로 `foms/services/admin/backup_service.py`; `scripts/ops/simple_backup_system.py`는 operator entrypoint로 유지 가능하나 **런타임 직접 import 타깃이 되어서는 안 됨** (B5C에서 정리).

### 3.4 Residual research / data / helper

| 자산 | 루트 존재 |
|------|-----------|
| `foms_address_learning.py` | 예 (루트 + `scripts/ops/` 병존 가능) |
| `foms_advanced_address_processor.py` | 예 |
| `foms_address_learning_data.json` | 예 |
| `menu_config.json` | 예 (`backups/**`에 스냅샷 별도) |
| `config/` | 예 (`config/__init__.py`, `config/rate_limit.py`) |

후속 배치에서 데이터/학습 스크립트와 런타임 경계를 명시할 것.

### 3.5 Residual script / manual / deploy / data artifacts (예시 열거)

계획 §6.5 예시와 대조:

| 항목 | 존재 (2026-04-15) |
|------|-------------------|
| `build_wdplanner.bat` | 예 |
| `start_foms_utf8.bat` | 예 |
| `MIGRATION_GUIDE_RAILWAY.md` | 예 |
| `TEST_GUIDE.md` | 예 |
| `app.yaml` | 예 |
| `runtime.txt` | 예 |
| `railway_bootstrap.py` | 예 |
| `pyrightconfig.json` | 예 |
| `foms.dump` | **저장소에 미존재** (계획 예시; 로컬/CI 아티팩트일 수 있음) |

## 4. Child batch 라우팅 (고정)

| 다음 배치 | 범위 | 권장 canonical home (계획 §6.6~6.8) |
|-----------|------|-------------------------------------|
| `SFC-B5A` | address/map + `map_config` | `foms/services/common/address_converter.py`, `map_generator.py`, `geocode_config.py` |
| `SFC-B5B` | ERP helpers | `foms/services/orders/erp_automation.py`, `order_text_parser.py` |
| `SFC-B5C` | backup | `foms/services/admin/backup_service.py` + operator/script 경계 |

## 5. 검증 (docs-only)

| 검증 | 결과 |
|------|------|
| 코드 diff | 본 배치 **문서·상태 파일만** (run record, `AI_STATUS`, `AI_CHANGELOG`) |
| `python -c "import app; print('APP_OK')"` | B4 기록 시점 스모크 |

## 6. Direction Lock

- B4는 **맵 동결**만 수행한다. 루트 shim 제거·canonical 이전은 **B5A+**에서 검증 게이트와 함께 실행한다.

## 7. 다음 배치

- **`SFC-B5A`** — Address/map helper retirement (code): 제품 트리에서 루트 `foms_*` / `map_config` import 0, 계획 §6.6 검증.

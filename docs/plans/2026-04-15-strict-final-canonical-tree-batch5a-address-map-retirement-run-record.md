# SFC-B5A — Address / map helper retirement

> Batch: `SFC-B5A`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.6`)  
> 선행: `SFC-B4`  
> 권장 canonical home: `foms/services/common/address_converter.py`, `map_generator.py`, `geocode_config.py`

## 1. 목표

- 루트 `foms_address_converter.py`, `foms_map_generator.py`, `map_config.py` **제거** (importlib shim 포함).
- 제품·테스트 경로에서 위 모듈명 **직접 import 0** (`backups/**` 제외).
- 구현 본문은 **`foms/services/common/`** 단일 정본.

## 2. 수행 요약

| 항목 | 내용 |
|------|------|
| 정본 모듈 | `foms/services/common/address_converter.py`, `map_generator.py`, `geocode_config.py` (구 `map_config` 내용 이전), `__init__.py` |
| 루트 제거 | `foms_address_converter.py`, `foms_map_generator.py`, `map_config.py` |
| `scripts/ops/` | 얇은 재노출만 (`foms.services.common.*`에서 import) — 운영 스크립트 호환 |
| 소비자 갱신 | `foms/api/address.py`, `measurement.py`, `measurement_map.py`, `erp_map.py`, `orders/nearby.py`, `foms/services/jobs/tasks.py`, `tests/domains/test_foms_map_generator.py` |

## 3. 검증 증거

| 검증 | 결과 |
|------|------|
| `rg` 제품 트리 `from foms_address_converter\|from foms_map_generator\|from map_config` | `backups/**` 외 **0건** |
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests/domains/test_foms_map_generator.py` + `tests/contracts/runtime/foms_namespace_surface_tests.py` | 통과 (배치 실행 시 일괄) |
| `pytest tests` (full) | **574 passed** |

## 4. Scoreboard 메모

- B1의 `SG2` 축(루트 helper import 부담)에서 **address/map/map_config 3파일 + 관련 단일행 import** 제거분 반영. 정확한 SG2 재측정은 선택적 후속.

## 5. 다음 배치

- **`SFC-B5B`** — `erp_automation.py`, `erp_order_text_parser.py` retirement (계획 §6.7).

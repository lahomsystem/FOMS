# Wave 1 Batch W1-B3B — Root ops / utility Python → `scripts/ops/`
> batch ID: **W1-B3B**  
> risk axis: **filesystem / import 호환 (루트 shim + `sys.path` 부트스트랩)**  
> 실행일: 2026-04-13

## 1. 요약
- 루트에 있던 운영·유틸 Python 스크립트를 `scripts/ops/`로 이동하고, **runtime import 계약**을 깨지 않도록 루트에 **thin shim**(`importlib` 또는 `runpy`)을 남겼다.
- `map_config.py`는 `apps/api/address.py` 등에서 직접 import되므로 **루트 유지** (이동 없음).
- `scripts/ops/*.py` 직접 실행 시 저장소 모듈을 찾을 수 있도록 각 파일 상단에 **루트 `sys.path` 부트스트랩**(`Path(__file__).resolve().parents[2]`)을 추가했다.

## 2. canonical 위치 (`scripts/ops/`)
| 구역 | 파일 (대표) |
|------|----------------|
| ERP / 텍스트 | `erp_automation.py`, `erp_order_text_parser.py`, `erp_build_step_runner.py` |
| 백업 / DB init | `simple_backup_system.py`, `init_wdcalculator_db.py` |
| 지도 / 주소 실험 | `foms_map_generator.py`, `foms_address_converter.py`, `foms_address_learning.py`, `foms_advanced_address_processor.py` |

## 3. 루트 shim (모듈명·CLI 호환)
- **모듈 재노출:** `erp_automation.py`, `erp_order_text_parser.py`, `simple_backup_system.py`, `foms_map_generator.py`(클래스·`MAP_MARKER_NAME_MAX_LEN` 등), `foms_address_learning.py`, `foms_advanced_address_processor.py`, `foms_address_converter.py` — importlib로 `scripts/ops` 구현 로드.
- **CLI 위임:** `erp_build_step_runner.py`, `init_wdcalculator_db.py` — `runpy.run_path`로 `scripts/ops` 스크립트 실행.
- 안내 문구: `erp_build_step_runner.py` 내 예시는 `python scripts/ops/erp_build_step_runner.py ...` 형태로 갱신.

## 4. 검증 (실행 기록)
| 검사 | 결과 |
|------|------|
| APP_OK | 통과 (W1-B5에서 재확인) |
| `python tools/harness/verify_result.py --json` | 통과 |
| 루트 shim 일괄 import | 통과 |
| `pytest` (대표: `test_foms_map_generator`, `test_foms_namespace_imports` 일부) | 통과 |

## 5. Direction Lock
- product import 경로는 shim으로 보존. `apps/` 본문 대규모 수정 없이 filesystem만 정리.

## 6. Stop condition
- **미발동** (Wave 1 closeout은 W1-B5).

## 7. 산출물
- `scripts/ops/*.py` (canonical)
- 루트 동일 이름의 짧은 shim `.py`
- 본 run record: `docs/plans/2026-04-13-wave1-batch3b-root-ops-utilities-run-record.md`

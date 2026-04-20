# SFC-B3 — Root `constants.py` retirement

> Batch: `SFC-B3`  
> 실행일: 2026-04-15  
> 성격: **code** (실행 계획 `§6.4`)  
> 선행: `SFC-B0`, `SFC-B1`, `SFC-B2`  
> 입력: `SFC-B2` authoritative target map

## 1. 목표

- 루트 `constants.py` **삭제** (장기 shim 없음).
- 모든 제품 소비자를 `foms/services/orders/status_constants.py`, `upload_policy.py`, `estimate_defaults.py`, `storage_paths.py`로 **canonical import** 전환.
- 제품 트리에서 `from constants import` / `import constants` **0건** (`backups/**` 제외).

## 2. 수행 요약

| 항목 | 내용 |
|------|------|
| 신규 모듈 | `foms/services/orders/status_constants.py`, `estimate_defaults.py`; `foms/services/files/upload_policy.py`, `storage_paths.py` |
| 제거 | 루트 `constants.py` |
| 소비자 갱신 | `foms/` 16파일, `apps/` 8파일 (총 24; 동일 배치 내 일괄) |
| 백업 트리 | `backups/tier*/system_files/app.py` — 스냅샷 보존 정책상 **미변경** (구 `constants` 참조 유지; 제품 런타임과 무관) |

## 3. Scoreboard delta (B1 baseline 대비)

| ID | 항목 | B1 baseline | B3 후 (본 배치에서 확정한 것) |
|----|------|-------------|-------------------------------|
| SG2 | foms-side root-helper / constants 계열 단일행 import 부담 | **26** (B1 동결) | **루트 `constants` 소비 0** — 해당 축은 B2 맵 기준 canonical 모듈로 이전 완료. 잔여 SG2는 B4 이후 재측정. |

## 4. 검증 증거

| 검증 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | `APP_OK` |
| `python tools/harness/verify_result.py --json` | `success: true` |
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` | 159 passed |
| `pytest tests` (full) | 574 passed |
| `rg` 제품 트리 `from constants import` | `backups/**` 외 **0건** |

## 5. Direction Lock 질문 (계획 §4.3)

- **Q:** 루트 `constants.py`를 삭제한 뒤에도 레거시 백업 스냅샷이 구 import를 유지해도 되는가?  
- **A:** 예. `backups/`는 제품 트리가 아니며 B0 allowlist 밖 스냅샷이다. 제품 경로만 SG 게이트 대상으로 유지한다.

## 6. 다음 배치

- **`SFC-B4`** — Root helper family freeze (**docs-only**): address/map, ERP, backup, residual root config/data/docs/scripts 맵 고정.

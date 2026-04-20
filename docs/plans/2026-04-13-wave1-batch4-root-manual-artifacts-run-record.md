# Wave 1 Batch W1-B4 — Root manual / office artifact convergence
> batch ID: **W1-B4**  
> risk axis: **filesystem taxonomy (문서·배치 이동, 런타임 import 변경 없음)**  
> 실행일: 2026-04-13

## 1. 요약
- 루트에 흩어져 있던 **업무/참고 문서(.docx, .md)** 를 `docs/context/manual-artifacts/` 또는 `docs/`·`docs/guides/` 로 수렴했다.
- 수동 백업 배치 `🚨_간단_백업.bat` 는 `scripts/maintenance/` 로 이동했고, 실행 시 **저장소 루트로 `cd`** 한 뒤 기존과 동일하게 루트 shim `python simple_backup_system.py` 를 호출한다.

## 2. 이동 매핑 (git mv)
| 이전 (루트) | 이후 |
|-------------|------|
| `Cloudflair R2 API.docx` | `docs/context/manual-artifacts/Cloudflair R2 API.docx` |
| `Furniture Process.md` | `docs/context/manual-artifacts/Furniture Process.md` |
| `가구 주문 프로세스.docx` | `docs/context/manual-artifacts/가구 주문 프로세스.docx` |
| `개발자 구인 공고 내용.docx` | `docs/context/manual-artifacts/개발자 구인 공고 내용.docx` |
| `SYSTEM_DOCUMENTATION.md` | `docs/guides/SYSTEM_DOCUMENTATION.md` |
| `WDPLANNER_INTEGRATION.md` | `docs/guides/WDPLANNER_INTEGRATION.md` |
| `DEPLOYMENT_GUIDE.md` | `docs/guides/DEPLOYMENT_GUIDE.md` |
| `🚨_간단_백업.bat` | `scripts/maintenance/🚨_간단_백업.bat` |

## 3. 배치 파일 계약
- `scripts/maintenance/🚨_간단_백업.bat` 상단: `cd /d "%~dp0..\.."` 로 저장소 루트 확정.
- 백업 로직: `python simple_backup_system.py` (루트 shim → `scripts/ops/simple_backup_system.py`).

## 4. Decision: delete / merge / extend / add
- **add:** `docs/context/manual-artifacts/` (오피스 참고물 전용 디렉터리)
- **delete:** 없음 (가치 확인 없는 삭제 금지 준수)

## 5. Direction Lock (계획서 §7.2)
1. **SSOT:** 문서·배치의 “집”이 `docs/`·`scripts/maintenance/` 로 명확해짐.
2. **split-brain:** 루트에 동일 이름의 중복 문서 없음; shim 경로 변경 없음.
3. **delete/merge 검토:** 삭제 없이 이동만.
4. **chunk:** 디렉터리 1개 추가 + 파일 이동만.
5. **파일 수:** 루트에서 제거되어 clutter 순감.
6. **순증가:** 해당 없음.
7. **README:** Wave 1 B4 범위에서 필수 변경 아님 (`docs/guides/` 기존 구조 활용).
8. **10회 반복:** 루트 비제품 산출물이 반복적으로 `docs/` 로 귀결되는 패턴과 일치.
9. **경계:** product source(`apps/`, `services/` 등)와 분리 유지.

## 6. 검증
| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | W1-B5 closeout에서 재실행 |
| `python tools/harness/verify_result.py --json` | 동상 |
| 런타임 import 경로 변경 | **없음** (문서·배치만 이동) |

## 7. Stop condition
- **미발동** (Wave 1 전체 closeout은 W1-B5).

## 8. 산출물
- `docs/context/manual-artifacts/*` (4개 파일)
- `docs/guides/SYSTEM_DOCUMENTATION.md`, `docs/guides/WDPLANNER_INTEGRATION.md`
- `docs/guides/DEPLOYMENT_GUIDE.md`
- `scripts/maintenance/🚨_간단_백업.bat`
- 본 run record: `docs/plans/2026-04-13-wave1-batch4-root-manual-artifacts-run-record.md`

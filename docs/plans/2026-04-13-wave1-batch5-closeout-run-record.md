# Wave 1 Batch W1-B5 — Closeout + 검증 + 잔여 debt
> batch ID: **W1-B5**  
> risk axis: **감리·검증·문서 정합**  
> 실행일: 2026-04-13

## 1. Definition of Done (계획서 §10) 충족
| # | 조건 | 상태 |
|---|------|------|
| 1 | root allowlist·top-level taxonomy 문서 고정 | **충족** — W1-B1 run record + 본 Wave 산출물 |
| 2 | `src/` 역할 고정 | **충족** — W1-B2 + `src/README.md` |
| 3 | root standalone Python debt가 `scripts/` 등으로 수렴 시작, 잔여는 분류 | **충족** — W1-B3A/B3B + 아래 §4 |
| 4 | loose manual/office artifact 정리 | **충족** — W1-B4 |
| 5 | quarantine가 SoT 아님 | **충족** — B1·검색 기준 반영 |
| 6 | Wave 2가 taxonomy 재해석 불필요 | **충족** — controlling spec + run record 세트 |

## 2. 검증 매트릭스 (계획서 §6)
| 검사 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | **통과** |
| `python tools/harness/verify_result.py --json` | **`success: true`** |
| `pytest -q` | **545 passed** (경고 3건 — SQLAlchemy LegacyAPIWarning, 기존 이슈) |
| product → quarantine **Python import** | **없음** (`foms`, `apps`, `services`에서 `Add In Program`/`SCheduler` 패턴 미매칭) |

### 2.1 템플릿 내 운영자 안내 (예외 명시)
- `templates/wdplanner_setup.html`에 `cd "Add In Program\WDPlanner"` 등 **수동 빌드 절차** 문구가 남아 있음. 이는 런타임 import가 아니라 **운영자용 안내**이며, quarantine 계약(제품 소스로 쓰지 않음)과 충돌하지 않음. Wave 2에서 WDPLANNER 패키징 경로를 통일할 때 문구만 정리 가능.

## 3. Run record 파일명 정합 (계획서 §7.1)
| 계획서 규범 파일명 | 상태 |
|-------------------|------|
| `2026-04-13-wave1-batch1-root-allowlist-run-record.md` | 존재 |
| `2026-04-13-wave1-batch2-src-classification-run-record.md` | 존재 |
| `2026-04-13-wave1-batch3a-root-migration-helpers-run-record.md` | **생성·정합** (구 `batch3a-migrations-run-record.md` 대체) |
| `2026-04-13-wave1-batch3b-root-ops-utilities-run-record.md` | **생성** |
| `2026-04-13-wave1-batch4-root-manual-artifacts-run-record.md` | **생성** |
| `2026-04-13-wave1-batch5-closeout-run-record.md` | 본 문서 |

## 4. 잔여 루트·근접 debt (Wave 2+ 후보, 삭제 아님)
- `constants.py`, `config/`, 루트 `foms_*.py` 일부, `map_config.py`, `menu_config.json`, `railway_bootstrap.py` — B1 delta에 명시된 대로 **분류만** 되어 있으며 이동은 후속 Wave.
- 루트 **shim** (`simple_backup_system.py`, `foms_map_generator.py` 등): canonical은 `scripts/ops/`, retirement는 import 소비자 축소 후.

## 5. Wave 2 handoff (한 줄)
- 주소 학습 데이터/실험 스크립트·루트 `foms_*` 정리, `map_config` 소유권, 템플릿 내 quarantine 경로 문구 현대화.

## 6. Direction Lock (요약)
Wave 1은 **폴더 위생 + shim 보존**에 한정했고, 비즈니스 로직·스키마·`apps/` 대규모 리팩터는 범위 밖.

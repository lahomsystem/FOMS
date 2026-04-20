# Wave 1 Batch W1-B1 — Root allowlist + delta inventory + quarantine contract
> batch ID: **W1-B1**  
> 실행일: 2026-04-13  
> risk axis: **docs / taxonomy only** (런타임 경로·코드 이동 없음)

## 1. 요약
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`(controlling) §2.5 일곱 범주 taxonomy를 Wave 1 실행 관점에서 재확인했다.
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` §2.6과 Wave 1 operational allowlist의 관계를 **정합(reconcile)** 했다.
- Step 2 inventory(`2026-04-07-step2-root-hygiene-inventory.md`) 이후 **루트 델타**를 표로 고정했다.
- quarantine 3구역 및 “product → quarantine import 금지” 게이트를 문서상 재명시했다.
- §2.3 bounded context 표는 **Wave 1에서 변경하지 않으며** owner map source로만 링크한다.

## 2. §2.6 vs Wave 1 allowlist 정합
| 구분 | 내용 |
|------|------|
| **§2.6 역할** | 2026-04-07 시점 **최소 루트** 정책: 진입점·배포·의존성·공용 문서 + 예외 폴더 `foms/`, `templates/`, `static/`, `migrations/`, `scripts/`, `docs/`, `.cursor/`, `.agents/`, `tools/` |
| **Wave 1 allowlist 역할** | controlling spec **§2.5**를 실행 가능한 **운영용 7축 taxonomy**로 풀어 쓴 것. §2.6에 없는 항목은 모두 **controlling spec에 명시된** runtime contract·transition overlay·검증/IDE/quarantine이다. |
| **충돌 여부** | **없음.** §2.6의 “루트에 두면 안 되는 것”(로그·dump·scratch 등)은 그대로 적용. Wave 1은 그 위에 `db.py`/`models.py`/`wdcalculator_*`, `railway-worker.toml`, `tests/`, `data/`, `.claude/`, `.github/`, `.vscode/`, `apps/`, `services/`, `src/`, quarantine 폴더를 **이미 승인된 rebaseline §2.5**에서 허용 항목으로 명명한다. |
| **우선순위** | 세부 해석이 겹치면 **2026-04-13 modular monolith rebaseline SPEC**가 Wave 1 집행 기준이며, §2.6은 상위 거버넌스·금지 루트 산출물 규칙을 유지한다. |

## 3. Root delta (Step 2 Category D 대비 2026-04-13 스캔)
Step 2 문서에 없거나 이후 추가·재확인된 루트 항목(대표):

| 항목 | 분류 | 비고 |
|------|------|------|
| `constants.py` | transition / shared constant surface | canonical 정렬은 후속 Wave |
| `config/` | 설정/실험 트리 | product tree와 별도; 내용 검토는 Wave 2+ |
| `runtime.txt` | deploy/런타임 힌트 텍스트 | **W1-B2**에서 소비자(railway/build) 확인 후 freeze |
| `pyrightconfig.json`, `.python-version` | IDE/타입체인 | IDE supply chain |
| `.cursorrules`, `.dockerignore`, `.gcloudignore`, `.gitattributes` | repo 메타 | 허용 |
| `.gstack/` | 에이전트/도구 체인 | IDE/tooling |
| `railway_bootstrap.py` | ops/부트스트랩 스크립트 | **W1-B3B** 후보 |
| `foms_address_learning.py`, `foms_advanced_address_processor.py`, `foms_address_learning_data.json` | 주소 실험/데이터 | 루트 부채; 수렴은 Wave 2+ |
| `map_config.py`, `menu_config.json` | 런타임/설정 인접 | import 계약 확인 후 이동 |
| `app.yaml` | legacy GAE | Category D 유지 |
| `DEPLOYMENT_GUIDE.md`, `SYSTEM_DOCUMENTATION.md`, `WDPLANNER_INTEGRATION.md`, `TEST_GUIDE.md`, `RAILWAY_ENV_VARS.md`, `MIGRATION_*.md` | 루트 느슨한 문서 | **W1-B4 완료:** 배포·시스템·WDPLANNER 문서는 `docs/guides/`·`docs/`로 이동(본 표는 Step2 대비 스냅샷 유지). |
| `build_wdplanner.bat`, `start_foms_utf8.bat`, `🚨_간단_백업.bat`(로캘 파일명) | 수동 배치 | **W1-B4 완료:** `🚨_간단_백업.bat` → `scripts/maintenance/`; 나머지는 미이동(후속 검토). |
| `ops_browser_qa.db`, `foms.dump`, `furniture_orders.db`, `migration_ready.db` | 로컬 DB/dump | gitignore 가능; §2.6 금지 유형—저장소 추적 금지 유지 |
| 루트 `foms_*.py` 다수 (`foms_map_generator` 등) | ops/유틸 | **W1-B3B** 후보 |

## 4. Wave 1 operational allowlist (재확인)
`2026-04-13-wave1-root-folder-hygiene-execution-plan.md` §2.1.1 표와 동일하게 유지. 허용 밖 항목은 위 **delta** 및 historical Category D로 추적한다.

## 5. Quarantine 계약 (재고정)
| 경로 | 해석 |
|------|------|
| `backups/` | 백업·스냅샷·비교용 사본. **canonical product source 금지.** |
| `Add In Program/` | 사이드/실험·레거시 랩. **신규 product source 금지.** |
| `SCheduler/` | 동일하게 non-product 존. |

**Future batch gate:** `foms/`, `apps/`, 루트 `services/`, `templates/`, `static/`에서 `backups|Add In Program|SCheduler`로의 **런타임 import**가 생기면 구조 작업 중단 후 설계 재검토.

## 6. Bounded context owner map (§2.3)
- **Source of truth:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` §2.3 표.  
- Wave 1에서는 표 **내용 변경 없음** (문서 링크만 유지).

## 7. 후속 배치 후보 (고정)
| Batch | 후보 |
|-------|------|
| **W1-B2** | `src/`, `runtime.txt` 분류·freeze 규칙 |
| **W1-B3A** | root migration helper **한 패밀리**: `migrate_*.py`, `safe_schema_migration.py`, `web_migration.py`, `railway_migrate_team.py` → `scripts/migrations/` (계약: `run.py`/`apps/` 비수정 시 루트 shim 검토) |
| **W1-B3B** | root ops Python **한 패밀리**: `erp_*.py`, `init_wdcalculator_db.py`, `simple_backup_system.py`, `foms_map_generator.py`, `foms_address_converter.py` 등 → `scripts/ops/` + 필요 시 루트 shim |
| **W1-B4** | 루트 docx/md/bat → `docs/`, `scripts/maintenance/` |

## 8. Decision: delete / merge / extend / add
- **delete:** 없음 (문서 배치).
- **merge:** §2.6 설명을 run record에 흡수(중복 spec 파일 생성 없음).
- **extend:** 본 run record가 Step 2 inventory의 **delta 연장** 역할.
- **add:** 본 run record 파일 1개 **필수 산출물**.

## 9. Direction Lock (10문항) — 요약 답변
1. 예 — taxonomy 단일 기준 강화.  
2. split-brain 감소(문서 기준 정렬).  
3. 예, 새 파일은 run record만.  
4. 해당 없음(문서).  
5. product/wrapper/test 코드 변화 없음.  
6. 해당 없음.  
7. README 본 배치 필수 아님(W1-B2에서 src README 검토).  
8. 예.  
9. 예 — quarantine·product 경계 명시.  
10. 구조/거버넌스만, 기능 변경 없음.

## 10. 검증
| 검사 | 결과 |
|------|------|
| docs-only | 예 (`docs/plans/*`, 필요 시 `docs/ARCHIVE_INDEX.md`만) |
| runtime path 변경 | 없음 |
| `git status` | 문서 추가/수정만 반영될 것 |

## 11. Stop condition
- **미발동.** controlling spec과 충돌 없음.

## 12. 산출물
- 본 파일: `docs/plans/2026-04-13-wave1-batch1-root-allowlist-run-record.md`

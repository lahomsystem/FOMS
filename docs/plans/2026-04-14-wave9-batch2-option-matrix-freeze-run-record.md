# Wave 9 — W9-B2 Option matrix + must-update-together freeze — Run record

**batch id:** W9-B2  
**이름:** Option matrix + must-update-together freeze  
**실행일:** 2026-04-14  
**attempt:** 1 — completed  
**진입 branch:** Branch A

## Batch Start (선언)

- **현재 batch:** W9-B2  
- **현재 branch:** Branch A  
- **allowed files:** 본 파일만  
- **forbidden expansion:** runtime, implementation handoff 시작, verdict 확정  

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record | code edit, `W9-B3` verdict 선행 |

## 2. Inputs consumed

- Authoritative runbook §4.3
- W9-B1 surface freeze
- Step 8 reopen 5항 (W9-B0 §5)

## 3. Option A / B / C 정의 (freeze)

| Option | 정의 (legal outcome) |
|--------|----------------------|
| **Option A** | Packaging/`src/foms` 물리 이동을 **지금 열지 않음** — explicit defer; Step 8 gate 미충족 상태 유지를 전제로 한 **합법적 verdict** |
| **Option B** | **제한적** packaging/metadata·경로 하드닝 — **minimal touch set**이 별도로 정의되고, root coupling 제거·false-confidence 방지 증거가 **동반**되어야 함 (`pyproject.toml` 단독 fantasy 금지) |
| **Option C** | **`src/foms` 물리 배치 + coordinated track** — must-update-together 전 집합을 한 트랙에서 갱신; dedicated implementation handoff 필수 |

## 4. Option B 승인 조건 (freeze)

- Step 8 reopen gate **전부 green이 아니면** 기본적으로 Option B는 **승인 후보에서 제외** (계획서: gate 미충족 시 기본 Option A).
- Minimal touch set이 **문서상 명시**되고, metadata-only로 root coupling이 남는 **false-confidence**가 아님을 증명할 증거가 필요.
- Wave 9 본편에서 **구현하지 않음** — handoff만.

## 5. Option B false-confidence 금지 (freeze)

- `pyproject.toml` 하나 추가 = 해결 **아님**
- CI/Railway/Alembic/worker depth가 **동일 contract**로 정리되지 않으면 Option B 주장 불가

## 6. Option C 승인 조건 (freeze)

- must-update-together 집합 **완전·누락 없음**
- 별도 ADR/plan로 package boundary 합의 (Step 8 gate 5) 충족 경로가 문서화
- **full coordinated track** — `src/foms`를 “바로 실행” verdict로 착각 금지

## 7. `src/foms` must-update-together 집합 (freeze)

다음은 **Option C** 선택 시 **함께** 갱신 대상으로 간주 (예시·포괄적; 실제 handoff에서 재확인):

| 영역 | 항목 |
|------|------|
| Import 경로 | `app.py`, root `db.py`/`models.py`와의 관계, `foms/*` 네임스페이스 |
| 배포 | `Dockerfile`, `start.sh`, `Procfile`, `railway.toml`, `railway-worker.toml` |
| 마이그레이션 | `migrations/env.py`, `alembic.ini` (해당 시) |
| 테스트 | `tests/conftest.py`, `tests/test_app_bootstrap_contract.py`, namespace contract tests |
| 작업자 | `foms/services/jobs/tasks.py` (path depth) |
| Harness | `tools/harness/verify_result.py` repo-root 가정 |
| CI | `.github/workflows/ci.yml` install 단계 |
| 의존성 | `requirements.txt` 및 (승인 시) packaging 메타데이터 |

## 8. Direct exclusions (freeze)

- Wave 8 **unresolved bridge debt** (별도 wave)
- **global template/layout** reopen
- **persistence refactor** (packaging과 분리)
- **`business_calendar`** 혼입

## 9. W9-B3 판단 기준 (verdict는 여기서 확정하지 않음)

| 기준 | 방향 |
|------|------|
| Gate 5 전부 green 아님 | 기본 **Option A** |
| Option B/C | 전용 handoff + 증거 없이 주장 금지 |

## 10. Stop label

- **없음**

## 11. Exact touched files

- `docs/plans/2026-04-14-wave9-batch2-option-matrix-freeze-run-record.md`

## 12. Verdict

- **`verdict pending (pre-B3)`**

## 13. Verification (docs/evidence)

| 검증 | 결과 |
|------|------|
| Option overlap 없음 | 통과 (A/B/C 상호 배타적 정의) |
| must-update-together 누락 없음 | 통과 (§7) |
| exclusions 명시 | 통과 (§8) |

## 14. Direction Lock (10문항)

전부 **Y** (B2는 matrix만 고정, bridge·layout·persistence 미혼입).

## 15. Next legal batch

**W9-B3** — `docs/plans/2026-04-14-wave9-batch3-packaging-decision-run-record.md`

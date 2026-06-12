# 백업 기능 폐기 + `backups/` 거버넌스 제거 Spec
> 작성일: 2026-06-05 | 상태: ✅ 완료 (2026-06-05, 9커밋 sequential, PTC green)

## 0. 한 줄 요약

`SimpleBackupSystem` / `/api/simple_backup` / `/api/backup_status` / `backups/` 트리를 전부 폐기한다. production 백업 정본은 Railway PostgreSQL의 자체 백업/스냅샷이며, 로컬 운영자 백업은 이미 정착된 `scripts/ops/sync_local_to_railway.ps1` (`FOMS_RUNTIME_OUTPUT_ROOT/dumps/foms.dump`) 워크플로로 통일한다.

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물

- `templates/admin/admin.html`에 "🚨 시스템 백업 실행" 버튼 + 백업 상태 카드 없음.
- `/api/simple_backup`, `/api/backup_status` 엔드포인트 존재 안 함 (404).
- `foms/api/backup.py`, `foms/services/admin/backup_service.py` 모듈 부재.
- `backups/` 디렉터리 git 트리·`.gitignore`·governance allowlist에서 완전 제거.
- `tests/contracts/runtime/test_ptc_physical_exactness.py`의 `_PTC_ROOT_ALLOWLIST`에 `"backups"` 없음.
- 듀얼-스펙(`2026-04-07` §2.6.1, `2026-04-13` §2.2.1/§2.5/§2.6/§3.x) + PTC plan(§4.1, §4.5) + clean-room 스크립트 동기화 완료.
- `docs/specs/2026-06-05-backup-feature-retirement_SPEC.md` (이 파일) + `docs/harness/policy/DECISIONS.md` 결정 기록 존재.

### 1.2 기능 요구사항

1. **Production runtime**에서 backup 관련 라우트 등록 안 됨 (`/api/simple_backup` POST → 404).
2. **Admin UI**에서 backup 카드/버튼/JS 모두 제거. 다른 admin 기능(menu_config, 채널 모니터링)은 영향 없음.
3. **Operator CLI** `python -m foms.services.admin.backup_service` 작동 안 함 (모듈 부재가 정확).
4. **Phase 4 안전망 유지**: `backup_order_schedule_dates.py` + `restore_order_schedule_dates.py`는 폐기하지 않고 출력 경로만 `${FOMS_RUNTIME_OUTPUT_ROOT}/dumps/order_schedule_dates-*.json`로 repath.
5. **PTC test green**: `pytest tests/contracts/runtime/test_ptc_physical_exactness.py` exact-allowlist 매칭.
6. **풀 회귀 테스트 green**: `pytest -v --ignore=tests/visual -p no:playwright`.
7. **APP_OK**: `python -c "import app; print('APP_OK')"`.

### 1.3 예외/제약 조건

- `docs/evolution/BACKUP_RESTORE_VERIFICATION.md`, `docs/evolution/GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md`, `docs/specs/2026-03-20-production-backup-and-restore-plan.md`, `docs/plans/2026-04-15-strict-final-canonical-tree-batch5c-*-run-record.md` 등 **historical evidence는 보존**한다 (수정 금지). 여기서 본 Spec으로 link-back만 추가.
- backup 관련 negative gate(=재도입 차단 watchdog 테스트)는 **추가하지 않는다.** PTC root allowlist + dual-spec lock + RPI 절차가 이미 재도입 게이트 역할을 한다. 추가 테스트는 governance noise.
- `scripts/ops/clone_prod_to_deploy.ps1` 폐기 — `sync_local_to_railway.ps1` (FOMS_RUNTIME_OUTPUT_ROOT/dumps 정본)로 대체.
- `.cursor`, `.github`, `.vscode` 등 다른 root allowlist 항목은 **건드리지 않는다.** scope = `backups/` 단일.
- 본 Spec은 hot-fix가 아닌 RPI 거버넌스 변경. 한 PR 안에서 코드+스펙+테스트 동시 갱신 필수 (PTC test exactness 위반 방지).

## 2. How — 어떻게 만드는가

### 2.1 수정·삭제·신규 파일

#### 삭제 (6)

| 파일 | 사유 |
|------|------|
| `foms/api/backup.py` | Blueprint 자체 폐기 |
| `foms/services/admin/backup_service.py` | `SimpleBackupSystem` 폐기 |
| `scripts/ops/simple_backup_system.py` | operator CLI shim — 위임 대상 부재 |
| `scripts/maintenance/🚨_간단_백업.bat` | 위임 대상 부재 |
| `scripts/ops/clone_prod_to_deploy.ps1` | docs 인입 0건, sync_local_to_railway.ps1로 대체 |
| `backups/.gitkeep` (디렉터리 자체) | governance 제거 동시성 |

#### 수정 (12)

| 파일 | 변경 내용 |
|------|----------|
| `foms/platform/blueprints.py` | L78 `from foms.api.backup import backup_bp` 제거; L155 `app.register_blueprint(backup_bp)` 제거 |
| `templates/admin/admin.html` | 백업 카드(L47-50), 백업 상태 JS 함수(`renderBackupStatus`/`loadBackupStatus`/`backupStatusRefresh`), 백업 버튼 click handler(L235-260) 전부 제거. 메뉴 config form/채널 모니터링 부분만 남긴다. |
| `scripts/maintenance/backup_order_schedule_dates.py` | `_default_output_path()` 출력 root를 `FOMS_RUNTIME_OUTPUT_ROOT` 환경변수 기반으로 전환 (미설정 시 `%USERPROFILE%\FOMS-runtime\dumps`). 헬프 문자열도 동기. |
| `tests/contracts/runtime/test_ptc_physical_exactness.py` | `_PTC_ROOT_ALLOWLIST`에서 `"backups"` 제거 |
| `tests/contracts/runtime/foms_namespace_surface_tests.py` | `test_b11b_canonical_api_cluster_importable()`에서 L731 `from foms.api.backup import backup_bp` + L746 `assert backup_bp is not None` 제거 |
| `tools/harness/strict_canonical_b12_clean_room.ps1` | L90 `$allowedRoot` 배열에서 `'backups'` 제거 |
| `.gitignore` | L71-75 `backups/*` + `!backups/.gitkeep` + 주석 3줄 제거 |
| `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` | §2.6.1 (L158) `backups` 항목 제거; "런타임 출력 정본" 단락에서 `backups/` 언급 제거 |
| `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` | L83 quarantine 표 row 삭제; L242 트리에서 `backups/` 줄 제거; L269/271/345/357/487 quarantine 3구역 → 2구역으로 갱신 (`Add In Program`, `SCheduler`만 남김) |
| `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` | L38/65/172/337 `backups` 언급 제거; §4.1 allowlist 동기 |
| `foms/README.md` | L27 quarantine 트리 목록에서 `backups/` 제거 |
| `docs/harness/policy/DECISIONS.md` | "2026-06-05: backup feature retirement" 결정 항목 추가 |

#### 신규 (1)

| 파일 | 내용 |
|------|------|
| `docs/specs/2026-06-05-backup-feature-retirement_SPEC.md` | 본 파일 |

### 2.2 아키텍처 방향

- **기존 패턴 100% 준수.** PTC-B1/B5와 동일한 dual-spec lock + PTC test exact set + clean-room 동시 갱신 패턴.
- **새 패턴 도입 0.** `FOMS_RUNTIME_OUTPUT_ROOT/dumps/`는 이미 정본 컨벤션 (`scripts/ops/sync_local_to_railway.ps1`, `scripts/migrations/migrate_local_to_remote.py` 사용 중).
- **참고 코드:**
  - `scripts/ops/sync_local_to_railway.ps1` — `FOMS_RUNTIME_OUTPUT_ROOT` 처리 표준 패턴
  - `scripts/migrations/migrate_local_to_remote.py:18-19` — Python 측 동일 패턴
  - `docs/plans/2026-04-15-strict-final-canonical-tree-batch5c-backup-helper-retirement-run-record.md` — 이전 retirement 패턴 참조

### 2.3 의존성 및 영향 범위

- **DB 마이그레이션:** 없음. 데이터 모델 변경 0.
- **Production runtime:** `/api/simple_backup`, `/api/backup_status` 호출 의존성 0 (Admin UI 외 inbound caller 없음 — grep 검증 완료). External 호출자 없음.
- **로컬 운영자:** `🚨_간단_백업.bat` 사용자에게 release notes로 `sync_local_to_railway.ps1` 사용법 안내. 본 Spec link.
- **Documentation drift:** `docs/evolution/`의 backup 보존 검증 문서들은 **history**로 유지하되, 본 Spec이 retirement 시점을 정의한다.
- **CI 영향:** 본 PR이 머지되면 GitHub Actions `pytest tests`가 backups 없는 트리에 대해 실행. PTC exact match가 같은 PR 안에서 정합되어야 함 (커밋 순서 §3 참조).
- **gitignore 정리:** `backups/*` + `!backups/.gitkeep` 5줄 제거 후, `backups/` 패턴 자체 무존재. 의도. 누군가 로컬에서 `backups/` 만들면 untracked로 남고, 이는 정책상 정확.

## 3. Steps — 실행 단계 (커밋 순서 강제)

import-clean 보장을 위해 sequential. 각 커밋 직후 `python -c "import app; print('APP_OK')"` 통과 보장.

- [ ] **C1**: `feat(backup): repath order_schedule_dates dump to FOMS_RUNTIME_OUTPUT_ROOT/dumps`
  - `scripts/maintenance/backup_order_schedule_dates.py` `_default_output_path()` repath
- [ ] **C2**: `refactor(admin): remove dead backup UI from admin.html`
  - 백업 카드 + JS + 버튼 제거 (HTML/JS만, blueprint는 다음 커밋)
- [ ] **C3**: `refactor(api): remove backup blueprint registration`
  - `foms/platform/blueprints.py` import + register 제거
  - `foms/api/backup.py` 삭제
- [ ] **C4**: `refactor(services): remove SimpleBackupSystem`
  - `foms/services/admin/backup_service.py` 삭제
- [ ] **C5**: `chore(ops): remove dead operator backup scripts`
  - `scripts/ops/simple_backup_system.py` 삭제
  - `scripts/maintenance/🚨_간단_백업.bat` 삭제
  - `scripts/ops/clone_prod_to_deploy.ps1` 삭제
- [ ] **C6**: `test: remove backup_bp from b11b canonical cluster import test`
  - `tests/contracts/runtime/foms_namespace_surface_tests.py` 2줄 제거
- [ ] **C7**: `governance: remove backups/ from PTC allowlist + dual-spec + clean-room`
  - `tests/contracts/runtime/test_ptc_physical_exactness.py` allowlist
  - `tools/harness/strict_canonical_b12_clean_room.ps1`
  - `docs/specs/2026-04-07-...SPEC.md` §2.6.1
  - `docs/specs/2026-04-13-...SPEC.md` 6곳
  - `docs/plans/2026-04-16-...plan.md` 4곳
  - `foms/README.md` quarantine 문구
- [ ] **C8**: `chore: rm backups/.gitkeep + .gitignore cleanup`
  - `git rm backups/.gitkeep`
  - `.gitignore` L71-75 제거
- [ ] **C9**: `docs: add 2026-06-05 backup retirement SPEC + DECISIONS entry`
  - 본 Spec 파일 (이미 디스크에 있음 — 상태를 ✅ 완료로 변경)
  - `docs/harness/policy/DECISIONS.md` 결정 추가

> **주의**: C7 + C8은 PTC test가 같은 시점에 일치해야 한다. 현실적으로는 C7 직전엔 broken (allowlist에 `backups` 있는데 트리는 그대로) → C7+C8을 **연속 두 커밋**으로 보고 push 전 둘 다 통과. 안전 옵션: C7과 C8을 한 커밋으로 합쳐도 됨.

## 4. 검증 기준

각 커밋 직후:
- [ ] `python -c "import app; print('APP_OK')"` 통과

전체 완료 후 (push 전 mandatory):
- [ ] `python tools/harness/verify_result.py --json`
- [ ] `python -m pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q` (PTC exact-allowlist green)
- [ ] `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` (B11B import cluster green)
- [ ] `python -m pytest -v --ignore=tests/visual -p no:playwright` (전체 회귀)
- [ ] `powershell -NoProfile -File tools/harness/strict_canonical_b12_clean_room.ps1` (clean-room 정합)
- [ ] `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` (이건 PTC test 미포함이라 위 pytest 직접 돌린 것이 정본 검증)

수동 확인:
- [ ] `git ls-tree HEAD | grep backups` → 출력 없음
- [ ] `grep -rn "backups" foms/ scripts/ templates/ tests/ tools/` → 결과 0건 (도큐먼트 외)
- [ ] Admin 페이지 로드 시 콘솔 에러 없음, 메뉴 config form 정상

## 5. 위험 & 완화

| 위험 | 완화 |
|------|------|
| Production 의존자 존재 | grep 검증으로 inbound caller 0건 확인. Admin UI 단일 진입점. |
| 로컬 운영자가 batch 사용 중 | release notes에 `sync_local_to_railway.ps1` 대체 안내. 본 Spec link. |
| Phase 4 OrderScheduleDate 안전망 손실 | `backup_order_schedule_dates.py` + `restore_*.py` 보존 + repath. |
| historical doc broken link | `docs/evolution/*` 보존; 본 Spec이 link-back 진입점. |
| Spec drift (dual-spec 일부만 갱신) | 단일 PR 안에서 §2.6.1 + 모듈러-모놀리스 + PTC plan + 테스트 동시 처리. PTC test exact set이 자동 게이트. |
| `_PTC_ROOT_ALLOWLIST` exactness fail (트리 vs allowlist 시점 어긋남) | C7 + C8을 인접 커밋(또는 한 커밋)으로 처리. push 전 PTC test 직접 돌림. |
| 재도입 방지 부재 | 별도 negative test 추가 안 함. PTC root exactness + dual-spec lock + RPI 검토가 자연스러운 게이트. backup 재도입 = §2.6.1 수정 = RPI = 본 Spec 갱신 필요 = governance review. |

## 6. 참고 자료

### 관련 결정
- `docs/harness/policy/DECISIONS.md` — 본 Spec과 함께 새 결정 추가
- `docs/specs/2026-03-20-production-backup-and-restore-plan.md` — production DR 표준 (Railway PostgreSQL + R2)

### 관련 진화/이력
- `docs/evolution/BACKUP_RESTORE_VERIFICATION.md` — 과거 검증 (보존)
- `docs/evolution/GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md` — 과거 분석 (보존)
- `docs/plans/2026-04-15-strict-final-canonical-tree-batch5c-backup-helper-retirement-run-record.md` — 직전 retirement 패턴 (보존)

### 관련 인프라
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` — §2.6.1 갱신
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` — quarantine 갱신
- `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md` — PTC plan 갱신
- `tests/contracts/runtime/test_ptc_physical_exactness.py` — root exactness gate
- `tools/harness/strict_canonical_b12_clean_room.ps1` — clean-room canonicalization

### 운영자 대체 워크플로
- `scripts/ops/sync_local_to_railway.ps1` — pg_dump → `${FOMS_RUNTIME_OUTPUT_ROOT}/dumps/foms.dump`
- `scripts/migrations/migrate_local_to_remote.py` — local SQLite → Railway
- `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md` — 표준 가이드

### Production 백업 정본
- Railway PostgreSQL 자체 백업/스냅샷 (별도 운영)
- Cloudflare R2 — 첨부 자산 백업 (별도 운영)

## 7. 승인

| 역할 | 이름 | 일자 | 상태 |
|------|------|------|------|
| 작성 | AI Agent (CEO mode) | 2026-06-05 | 🟢 |
| 검토 | 사용자 (더블체크 요청) | 2026-06-05 | 🟢 |
| 승인 | 사용자 (Production backup = Railway PostgreSQL 확정) | 2026-06-05 | 🟢 |
| 실행 | 9커밋 sequential (6fbb5159 → 60628eac → C9) | 2026-06-05 | ✅ |

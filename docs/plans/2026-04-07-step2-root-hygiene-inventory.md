# FOMS Step 2 Root Hygiene Inventory
> 작성일: 2026-04-07
> 상태: Step 2 종료 inventory
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 조건: `docs/plans/2026-04-07-phase1-baseline-run-record.md`의 `Conditional Go`
> 상태 메모: `docs/plans/2026-04-07-step2-batch1-run-record.md`, `docs/plans/2026-04-07-step2-batch2-run-record.md`, `docs/plans/2026-04-07-step2-closeout-run-record.md`, `docs/plans/2026-04-07-phase1-baseline-run-record.md` 기준 `Batch 1`, `Batch 2`, closeout 실행 완료. 후속 구현으로 `run.py`는 root file log를 기본 생성하지 않으며, file logging은 `FOMS_STARTUP_LOG_PATH` opt-in으로만 동작한다. legacy `app_startup.log` 삭제와 root 기본 경로 미재생성 검증까지 끝나 Step 2는 종료되었다.

## 1. 목적
이 문서는 `Step 2: 루트 hygiene 정리`의 현재 상태 inventory다. `Batch 0`에서 초기 분류를 고정했고, `Batch 1`과 `Batch 2` 이후에는 남은 로컬 예외와 후속 금지 범위를 유지한다.

- 지금도 건드리면 안 되는 계약 파일
- `Batch 1`에서 완료된 로컬 생성물 정리 결과
- `Batch 2`에서 정리한 tracked 항목과 후속 상태
- 이후 별도 slice로 넘겨야 할 정책 부채

이 inventory는 초기 분류 문서이면서, `Batch 1` 이후에는 다음 배치 진입 기준을 유지하는 기준 문서다.

## 2. Batch 0 기준 루트 스냅샷
MCP `list_directory_with_sizes` 기준:

- 루트 총계: `77 files`, `23 directories`
- 결합 크기: `115.14 MB`
- 대용량 상위 항목:
  - `app_startup.log` `102.61 MB`
  - `migration_ready.db` `9.14 MB`
  - `foms.dump` `1.24 MB`
  - `all_changes.txt` `846.36 KB`
  - `all_templates_changes.txt` `846.36 KB`

해석:
- 현재 루트는 계약 파일보다 생성물/역사 산출물이 눈에 띄게 섞여 있다.
- 특히 log/db/dump 성격 파일이 루트 집중도를 크게 해치고 있다.

### 2.1 Closeout 후 현재 상태
- `run.py`는 후속 구현으로 root `app_startup.log`를 기본 생성하지 않는다. file logging은 `FOMS_STARTUP_LOG_PATH`를 명시했을 때만 활성화된다.
- legacy `app_startup.log`는 closeout에서 삭제 완료했고, `python app.py` 재기동 검증에서도 root 기본 경로에 다시 생기지 않음을 확인했다.
- `.pytest_cache/`와 `__pycache__/`는 내용 정리를 완료했다. 다만 로컬 import/test 실행 시 빈 뼈대나 cache 파일이 다시 생길 수 있다.
- `foms.dump`, `furniture_orders.db`, `migration_ready.db`는 현재 이 working tree에는 존재하지 않는다.

## 3. 절대 동결 대상
다음 항목은 `Step 2`에서 이동/리팩터/삭제하지 않는다.

- `app.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `alembic.ini`
- `db.py`
- `models.py`
- `wdcalculator_db.py`
- `wdcalculator_models.py`
- `migrations/`
- `templates/`
- `static/`
- `.cursor/hooks.json`
- `tools/harness/*`
- `tests/harness/*`
- `docs/harness/bundles/HARNESS_BUNDLE_*.md`

추가로 루트에 남겨도 되는 공용/계약 문서:
- `README.md`
- `AGENTS.md`
- `CLAUDE.md`
- `requirements.txt`

## 4. Category A — 로컬 생성물, 수동 삭제 후보
다음 항목은 repo 계약 파일이 아니며, 현재 git 기준으로 ignore 또는 cache 성격이다. 다만 **사용자 데이터 또는 로컬 복구 가치가 있을 수 있으므로 자동 삭제는 금지**하고, 백업 확인 후 수동 정리를 권장한다.

| 경로 | git 상태 | 근거 | 권장 조치 |
|------|----------|------|-----------|
| `app_startup.log` | ignored | 구현 전 dev startup 경로가 root file log를 직접 생성했던 legacy artifact | closeout에서 삭제 완료, 현재 코드는 기본적으로 재생성하지 않음 |
| `foms.dump` | ignored | `scripts/ops/sync_local_to_railway.ps1`, `docs/guides/RAILWAY_LOCAL_TO_REMOTE_SYNC.md`, `MIGRATION_RAILWAY_R2.md`에서 로컬 dump 파일로 사용 | **백업 확인 후** 로컬 정리 후보 |
| `furniture_orders.db` | ignored | 마이그레이션 가이드/템플릿에서 로컬 SQLite 파일로 언급 | **백업 확인 후** 로컬 정리 후보 |
| `migration_ready.db` | ignored | 임시 migration-ready DB, 현재 `9.14 MB` | **백업 확인 후** 로컬 정리 후보 |
| `.pytest_cache/` | ignored | pytest cache | 로컬 정리 후보 |
| `__pycache__/` | ignored | Python bytecode cache | 로컬 정리 후보 |

실행 원칙:
- `foms.dump`, `furniture_orders.db`, `migration_ready.db`는 데이터 보존 여부를 먼저 확인한다.
- `app_startup.log`의 root 재생성 경로는 `run.py` 후속 구현과 closeout 재기동 검증으로 차단 확인했다.
- file logging이 필요하면 `FOMS_STARTUP_LOG_PATH`로 명시적 opt-in만 허용한다.

현재 상태 메모:
- 현재 working tree 기준 Category A의 root blocker 잔여는 없다.
- dump/db 3종은 이 클론에는 존재하지 않아 Batch 1 후속 정리 대상이 아니다.

## 5. Category B — tracked cleanup 대상 (Batch 2에서 삭제됨)
다음 항목은 root 정책에 어긋나는 tracked 산출물/로그였고, `Batch 2`에서 삭제를 완료했다. 아래 표는 **삭제 전 분류 근거**와 **현재 상태**를 함께 남긴 기록이다.

| 경로 | 분류 | 근거 | 현재 판단 |
|------|------|------|-----------|
| `all_changes.txt` | 비교 산출물 | 파일 내용이 `git diff`/commit patch dump 형태, repo 참조 없음 | Batch 2에서 삭제됨 |
| `all_js_changes.txt` | 비교 산출물 | `0 B`, tracked 상태, repo 참조 없음 | Batch 2에서 삭제됨 |
| `all_templates_changes.txt` | 비교 산출물 | `git diff`/commit patch dump 형태, repo 참조 없음 | Batch 2에서 삭제됨 |
| `db_check_log.txt` | 로그 산출물 | DB connection check 오류 로그만 포함 | Batch 2에서 삭제됨 |
| `migration_error.txt` | 로그 산출물 | 단일 인코딩 오류 메시지 파일 | Batch 2에서 삭제됨 |
| `migration_log.txt` | 로그 산출물 | `migrate_attachment_user.py` traceback 로그 | Batch 2에서 삭제됨 |
| `head_erp_scripts_core.html` | 추출 산출물 추정 | standalone HTML/JS fragment, repo 참조 없음 | Batch 2에서 삭제됨 |
| `(noop)` | 빈 notebook artifact | 내용이 비어 있는 notebook, repo 참조 없음 | Batch 2에서 삭제됨 |

주의:
- `head_erp_scripts_core.html`는 이름상 추출/중간 산출물로 보이지만, 제거 전 1회 육안 확인이 필요하다.
- 현재 Batch 2 실행 전 검토 기준으로 위 표 항목은 모두 `git ls-files` 상 tracked 상태였다.

## 6. Category C — harness 계약 때문에 지금 못 건드리는 루트 파일
다음 항목은 root 정책상 이상적이지 않지만, 현재 harness/runner 문서와 코드에서 직접 참조하고 있어 `Step 2`에서 움직이면 안 된다.

| 경로 | 근거 | 판정 |
|------|------|------|
| `task_plan.md` | `tools/harness/prompt_router.py`, `tools/harness/run_codex.ps1`, 여러 harness spec에서 직접 참조 | Step 2 이동 금지 |
| `findings.md` | `tools/harness/prompt_router.py`, `tools/harness/run_codex.ps1`, 여러 harness spec에서 직접 참조 | Step 2 이동 금지 |
| `progress.md` | `tools/harness/prompt_router.py`, `tools/harness/run_codex.ps1`, harness spec에서 직접 참조 | Step 2 이동 금지 |

결론:
- 이 3개는 root hygiene 대상처럼 보이지만 실제로는 harness contract 파일이다.
- 위치 변경은 `tools/harness/*` 변경과 같이 가야 하므로 `Step 7` 이전에는 손대지 않는다.

## 7. Category D — 루트 정책 부채이지만 Step 2 비대상
다음 항목은 루트에 있는 것이 이상적이지 않지만, 지금은 단순 hygiene 정리보다 별도 주제 정리가 우선이다.

### 7.1 개발/배포/운영 자산
| 경로 | 근거 | 판정 |
|------|------|------|
| `run.py` | 현재 `python app.py`가 내부적으로 위임하는 dev startup 구현 | 유지, 별도 판단 |
| `app.yaml` | `README.md`, `SYSTEM_DOCUMENTATION.md`에서 참조되는 legacy GAE 설정 | README truth sync 후 판단 |
| `railway-worker.toml` | `DECISIONS.md`, incident/docs에서 worker config path로 참조 | 유지, 별도 판단 |

### 7.2 루트 utility / migration scripts
| 경로 | 근거 | 판정 |
|------|------|------|
| `migrate_as_orders.py` | migration utility 성격 | `scripts/` 정리 slice로 이관 검토 |
| `migrate_attachment_user.py` | migration utility 성격 | `scripts/` 정리 slice로 이관 검토 |
| `migrate_blueprint_field.py` | migration utility 성격 | `scripts/` 정리 slice로 이관 검토 |
| `migrate_local_attachment_user.py` | migration utility 성격 | `scripts/` 정리 slice로 이관 검토 |
| `migrate_local_to_remote.py` | docs에서 직접 언급 | `scripts/` 정리 slice로 이관 검토 |
| `migrate_local_uploads_to_r2.py` | docs에서 직접 언급 | `scripts/` 정리 slice로 이관 검토 |
| `railway_migrate_team.py` | migration utility 성격 | `scripts/` 정리 slice로 이관 검토 |
| `safe_schema_migration.py` | migration guide에서 직접 언급 | `scripts/` 정리 slice로 이관 검토 |
| `web_migration.py` | docs/plans/evolution에서 직접 언급 | `scripts/` 정리 slice로 이관 검토 |
| `erp_automation.py` | docs/evolution/plans에서 직접 언급 | utility 정리 slice로 검토 |
| `erp_build_step_runner.py` | docs/plans/evolution에서 직접 언급, workflow 성격 | utility 정리 slice로 검토 |
| `erp_order_text_parser.py` | docs/plans에서 직접 언급 | utility 정리 slice로 검토 |
| `init_wdcalculator_db.py` | WDCalculator utility 성격 | persistence/ops 정리 slice로 검토 |
| `simple_backup_system.py` | backup/security audit 문맥에서 언급 | ops 정리 slice로 검토 |

### 7.3 수동 문서/업무 자산
| 경로 | 근거 | 판정 |
|------|------|------|
| `Cloudflair R2 API.docx` | 업무 참고 문서, runtime 참조 없음 | `docs/` 또는 외부 저장소로 이관 검토 |
| `Furniture Process.md` | 과거 계획 문서에서만 언급 | `docs/` 이관 검토 |
| `가구 주문 프로세스.docx` | 업무 문서, runtime 참조 없음 | `docs/` 또는 외부 저장소로 이관 검토 |
| `개발자 구인 공고 내용.docx` | 업무 문서, runtime 참조 없음 | `docs/` 또는 외부 저장소로 이관 검토 |
| `🚨_간단_백업.bat` | 수동 운영 배치 파일 | `scripts/manual/` 또는 ops 문서로 이관 검토 |

## 8. Step 2에서 실제로 먼저 할 배치
### Batch 0 — inventory only (완료)
- 현재 문서 작성
- 아직 삭제/이동 없음

### Batch 1 — 로컬 생성물 정리 (부분 완료)
- `app_startup.log`
- `.pytest_cache/`
- `__pycache__/`
- 필요 시 `foms.dump`, `furniture_orders.db`, `migration_ready.db`

조건:
- 데이터 보존 필요 없음 확인
- git tracked 대상 아님 확인

실행 결과:
- 완료: `.pytest_cache/`, `__pycache__/` 내용 정리
- 완료: legacy `app_startup.log` 삭제 및 root 기본 경로 미재생성 확인
- 현재 미존재: `foms.dump`, `furniture_orders.db`, `migration_ready.db`

### Batch 2 — tracked artifact cleanup PR (실행 완료)
- `all_changes.txt`
- `all_js_changes.txt`
- `all_templates_changes.txt`
- `db_check_log.txt`
- `migration_error.txt`
- `migration_log.txt`
- `(noop)`
- 필요 시 `head_erp_scripts_core.html`

조건:
- repo 내 참조 없음 재확인
- cleanup 후 `APP_OK`, `verify_result.py --json`, `pytest -q`, staging smoke 재실행
- worker 미검증 상태에서는 Step 2 범위를 hygiene/tracked cleanup으로만 한정

실행 결과:
- `(noop)`, `all_*changes.txt`, `db_check_log.txt`, `migration_error.txt`, `migration_log.txt`, `head_erp_scripts_core.html` 삭제 완료
- `APP_OK`, `verify_result.py --json`, `pytest -q`, staging login smoke 재통과

## 9. 지금 하지 말아야 할 것
- `task_plan.md`, `findings.md`, `progress.md` 이동
- `run.py`, `app.yaml`, `railway-worker.toml` 삭제
- root migration utility 스크립트 일괄 이동
- 수동 문서/docx 일괄 삭제
- boot/runtime/persistence/harness 계약 파일 변경

## 10. 추천 판정
현재 시점에서 `Step 2`는 종료 가능 상태를 넘어 closeout까지 완료되었다.

1. 사용자 승인 후 local `python app.py` / reloader 프로세스를 정리했다.
2. legacy `app_startup.log`를 삭제했다.
3. `python app.py` 재기동 검증에서 root `app_startup.log` 기본 미재생성을 확인했다.
4. 필요 시 file logging은 계속 `FOMS_STARTUP_LOG_PATH`로만 명시적 활성화한다.
5. `Category D`는 이후 별도 주제별 slice로 다룬다.

즉, `Step 2`의 근본 원인 수정과 closeout 검증이 모두 완료되었다. worker basic smoke도 이미 확인되었으므로, 다음 구조 변경 판단은 `Step 2` 잔여가 아니라 `Step 3`를 어떤 범위와 shim 전략으로 시작할지에 달려 있다.

# FOMS Repository Structure Governance Spec
> 작성일: 2026-04-07 | 상태: 🟢 승인됨

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
FOMS 저장소를 장기적으로 정리할 때 따라야 하는 공통 거버넌스 규칙과 단계별 실행 기준을 정의한다. 이 Spec의 목적은 "파일을 어디로 옮길지"보다 먼저, 어떤 경계를 유지해야 하고 어떤 순서로 움직여야 안전한지를 고정하는 것이다.

최종적으로는 다음 상태를 목표로 한다.
- 제품 런타임 코드와 AI/하네스/운영 메타 자산의 경계가 명확하다.
- 루트 디렉터리는 최소 진입점/배포/공용 문서만 남긴다.
- Flask 앱은 유지하되, `platform / web / api / services / persistence` 역할이 분리된 모듈러 모놀리식 구조로 진화한다.
- 구조 개편은 대규모 일괄 이동이 아니라, 검증 가능한 단계별 이행으로 수행한다.

### 1.2 기능 요구사항
1. 모든 구조 개편 단계는 현재 운영 계약인 `app:app`, `sh start.sh`, `alembic upgrade head`, `APP_OK` 검증 경로를 보존해야 한다.
2. 루트 디렉터리에 둘 수 있는 파일과 둘 수 없는 파일의 기준을 명확히 정의해야 한다.
3. 제품 코드의 표준 위치와 향후 목표 구조를 명시해야 한다.
4. AI/하네스/문서/로그/생성물의 분류 기준을 명시해야 한다.
5. 구조 개편은 저위험 단계와 고위험 단계를 분리해야 하며, 한 PR에서 여러 위험 축을 동시에 건드리지 않아야 한다.
6. `db.py`/`models.py`와 `wdcalculator_db.py`/`wdcalculator_models.py`는 서로 다른 persistence lifecycle로 취급해야 하며, 별도 승인 없는 통합을 금지한다.
7. `app.py` 슬림화는 허용하되, 부팅 순서와 monkey patch/runtime bootstrap 순서를 바꾸지 않아야 한다.
8. 하네스 관련 경로 변경은 `tools/harness/*`, `.cursor/hooks.json`, `tests/harness/*`, `docs/harness/bundles/HARNESS_BUNDLE_*.md`, CI 경로를 같은 단계에서 함께 갱신해야 한다.
9. 대형 구조 변경은 먼저 1개 도메인 vertical slice로 시범 적용한 뒤 확대해야 한다.
10. 구조 개편과 비즈니스 로직 변경은 원칙적으로 같은 PR에서 섞지 않아야 한다.
11. 목표 구조는 폴더 이름만 바꾸는 것이 아니라, `platform -> web/api -> services -> persistence` 의존성 방향을 강제해야 한다.
12. 전환 기간 동안 `apps/`와 `foms/`가 공존할 수 있으나, 한 모듈의 source of truth는 한 경로에만 있어야 하며 이전 경로는 shim/re-export 용도로만 사용해야 한다.
13. Railway web 프로세스와 worker 프로세스는 동일한 구조 개편 안전망 아래 검증해야 한다.
14. 구조 개편 PR에서 새로운 Alembic revision, 스키마 변경, persistence lifecycle 통합은 별도 승인 없이는 금지한다.
15. Alembic/autogenerate 결과는 수동 검토가 전제되어야 하며, downgrade rehearsal 또는 명시적 forward-only 예외와 backup/rollback 계획 중 하나가 반드시 있어야 한다.
16. JSONB/`structured_data` 변경 계약(`copy.deepcopy` + `flag_modified`)은 persistence 개편 중에도 유지되어야 한다.

### 1.3 예외/제약 조건
- 이번 Spec은 "전체 구조 개편을 한 번에 실행"하는 문서가 아니라, "구조 개편을 안전하게 진행하기 위한 운영 기준" 문서다.
- Flask를 유지한다. FastAPI, Next.js, 마이크로서비스 전환 같은 기술 스택 재작성은 이번 범위에서 제외한다.
- 초기 단계에서는 `app.py`, `start.sh`, `Procfile`, `railway.toml`, `Dockerfile`, `alembic.ini`, `migrations/`, `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py`의 위치 변경을 금지한다.
- 초기 단계에서는 `docs/harness/bundles/HARNESS_BUNDLE_*.md`, `.cursor/hooks.json`, `tools/harness/*` 경로 변경을 금지한다.
- `templates/`와 `static/`는 Flask 자산 경로 계약과 연결되어 있으므로 별도 승인 없는 위치 변경을 금지한다.
- fail-open이 필요한 경우에도 로그 없는 묵시적 실패 삼키기는 금지한다.
- 운영 장애 대응 또는 보안 hotfix는 구조 개편보다 우선하며, 이 경우는 별도 예외 승인 경로로 처리한다.

### 1.4 Non-goals — 이번 Spec의 비범위
- 신규 기능 추가
- 성능 최적화만을 위한 구조 변경
- DB 스키마 변경
- main persistence와 WDCalculator persistence 통합
- `templates/` / `static/` 물리 이동
- 전면 패키지화 또는 `src/` 레이아웃 즉시 전환

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `docs/specs/2026-04-07-repo-structure-governance_SPEC.md` | 구조 개편 거버넌스 기준 정의 |
| `docs/ARCHIVE_INDEX.md` | 본 Spec 인덱싱 |
| `README.md` | 구조 개편 시작 시 실제 운영 기준(Railway/Flask)과 문서 진실도 정렬 필요 |
| `app.py` | 후속 Phase에서 slim entrypoint/compatibility adapter로 축소 예정 |
| `start.sh` | 후속 Phase에서 경로/부팅 계약 검증 대상 |
| `Procfile` | 후속 Phase에서 `app:app` 계약 검증 대상 |
| `railway.toml` | 후속 Phase에서 시작 경로/배포 계약 검증 대상 |
| `Dockerfile` | 후속 Phase에서 build/runtime contract 검증 대상 |
| `alembic.ini` | 후속 Phase에서 migration 경로 계약 검증 대상 |
| `migrations/env.py` | 후속 Phase에서 `Base.metadata` import contract 검증 대상 |
| `db.py` | 후속 Phase에서 main persistence shim or package 진입점 후보 |
| `models.py` | 후속 Phase에서 main persistence shim or package 진입점 후보 |
| `wdcalculator_db.py` | 후속 Phase에서 WDCalculator persistence 분리 경계 유지 대상 |
| `wdcalculator_models.py` | 후속 Phase에서 WDCalculator persistence 분리 경계 유지 대상 |
| `.cursor/hooks.json` | 후속 Phase에서 meta/harness 경로 재구성 시 영향 범위 |
| `tools/harness/*` | 후속 Phase에서 docs/context 경로 변경 시 영향 범위 |
| `docs/context/*` | 후속 Phase에서 `bundles / runtime / logs` 재분류 대상 |

### 2.2 아키텍처 방향
- FOMS는 장기적으로 `Flask 기반 모듈러 모놀리식`으로 정리한다.
- 부팅과 런타임 wiring은 `platform` 계층이 소유하고, 페이지 라우트는 `web`, JSON/API 라우트는 `api`, 비즈니스 로직은 `services`, DB/모델은 `persistence`가 소유하는 구조를 목표로 한다.
- 구조 개편 초기에는 import 호환성을 위해 루트 `app.py`, `db.py`, `models.py`를 compatibility adapter 또는 shim으로 유지할 수 있다.
- `templates/`와 `static/`는 초기에는 현 위치를 유지하고, 이후 별도 승인된 단계에서만 이동을 검토한다.
- `wdcalculator`는 main app persistence와 별도 lifecycle을 유지한다. 별도 DB/동일 DB+schema 전략 통합은 이 Spec 범위 밖의 별도 ADR 대상이다.

### 2.3 모듈 경계와 의존성 규칙
- `web`은 `services`를 호출할 수 있으나 `persistence`를 직접 소유하지 않는다.
- `api`는 `services`를 호출할 수 있으나 `persistence`를 직접 소유하지 않는다.
- `services`는 `persistence`와 순수 helper/domain 유틸을 사용할 수 있으나 `web`/`api`/`platform`에 의존하지 않는다.
- `persistence`는 `web`/`api`/`platform`을 import하지 않는다.
- `platform`은 bootstrap/registration/extension wiring만 소유하며, 비즈니스 로직을 포함하지 않는다.
- 전환기에는 자동 lint가 없더라도 각 구조 PR에서 import 방향을 리뷰 체크리스트로 검증한다.

### 2.4 현재 구조와 목표 구조의 관계
| 현재 위치 | 전환기 상태 | 장기 목표 |
|------|------|------|
| `apps/api/*` | legacy 유지 가능, 새 소스 생성 금지 또는 최소화 | `foms/api/*` |
| `apps/*.py` 페이지 블루프린트 | legacy 유지 가능, slice 단위 shim 허용 | `foms/web/*` |
| `services/*.py` | 점진 이관, 기존 import는 shim 허용 | `foms/services/*` |
| `db.py`, `models.py` | 루트 shim/adapter 유지 | `foms/persistence/main/*` |
| `wdcalculator_db.py`, `wdcalculator_models.py` | 루트 shim/adapter 유지 | `foms/persistence/wdcalculator/*` |
| `docs/context/*` | 현 경로 유지 | `docs/harness/{bundles,runtime,logs}` |

전환기 규칙:
- `apps/`와 `foms/`는 병행될 수 있다.
- 단, 한 도메인의 실질 구현은 한 경로만 source of truth로 삼는다.
- 이전 경로는 compatibility shim, re-export, import bridge 용도로만 허용한다.

### 2.5 목표 구조 (장기 방향)
```text
repo root
  app.py
  start.sh
  railway.toml
  Procfile
  Dockerfile
  alembic.ini
  requirements*.txt
  README.md
  AGENTS.md
  CLAUDE.md

  foms/
    platform/
    web/
    api/
    services/
    persistence/
      main/
      wdcalculator/

  templates/
  static/
  migrations/
  scripts/
  docs/
    specs/
    guides/
    archive/
    harness/
      bundles/
      runtime/
      logs/
```

`run.py`는 현재 `python app.py`가 내부적으로 위임하는 개발용 startup 구현이며, production 계약은 아니다. 이 파일은 local/dev startup 동작을 담당하지만 `app:app` 계약을 대체하지 않는다. 현재 dev file logging은 `FOMS_STARTUP_LOG_PATH`를 명시했을 때만 opt-in으로 활성화한다.

### 2.6 루트 디렉터리 허용 정책

요약: 구조 거버넌스(본 문서)와 `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`는 **같은 루트/taxonomy 정본**을 가리키도록 in-place 동기화한다. 상위 sibling spec을 새로 만들지 않으며, 수렴 실행은 `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`(PTC)를 따른다.

#### 2.6.1 Final root allowlist (exact set; dual-spec lock)

아래 집합이 **커밋 트리·clean-room·contract proof** 기준의 정본 루트 엔트리다. `2026-04-13` §2.2.1 final-form tree는 이 집합을 도식화한 것이며, **집합 자체는 본 절 §2.6.1이 우선**한다.

**허용 디렉터리 (표기 그대로):**

- `.agents`
- `.claude`
- `.cursor`
- `.github`
- `.vscode`
- `Add In Program`
- `backups`
- `data`
- `docs`
- `foms`
- `migrations`
- `SCheduler`
- `scripts`
- `static`
- `templates`
- `tests`
- `tools`

**허용 파일 (표기 그대로):**

- `.dockerignore`
- `.gcloudignore`
- `.gitattributes`
- `.gitignore`
- `.python-version`
- `AGENTS.md`
- `alembic.ini`
- `app.py`
- `CLAUDE.md`
- `db.py`
- `Dockerfile`
- `models.py`
- `Procfile`
- `README.md`
- `railway.toml`
- `railway-worker.toml`
- `requirements.txt`
- `run.py`
- `start.sh`
- `wdcalculator_db.py`
- `wdcalculator_models.py`

**명시적 금지 (루트 또는 저장소 추적 관점에서 최종 closeout 대상):** `.gstack/`, `.pytest_cache/`, `.tmp_strict_tree_verify/`, 루트 `__pycache__/`, 루트 `*.db`, 루트 `*.dump` — 상세는 PTC 계획서 §3.5·§4.1.

전환기 오버레이(`apps/`, 루트 `services/` 등)는 `2026-04-13` §2.2.2 및 본 문서 Step 3 이후 기록대로 **최종 트리 정본과 별도**로 규율한다. PTC 최종 수용 기준에서 요구하는 committed tree에는 위 허용 집합 외 루트 엔트리가 없어야 한다.

#### 2.6.2 `data/` 및 로컬 런타임 산출물 (dual-spec; PTC)

- `data/`는 **버전 관리되는 비밀 아님 참조·설정·시드**만 허용한다.
- 금지(저장소 트리): `data/dumps/`·`data/localdb/`·`data/*.db`·repo 안 dump/SQLite/브라우저 QA용 DB 등 **런타임 산출물**.
- 로컬 운영자/검증 산출물의 정본 루트는 환경 변수 **`FOMS_RUNTIME_OUTPUT_ROOT`** 이다. 미설정 시 기본값은 **`%USERPROFILE%\FOMS-runtime`** (Windows). 하위 경로 계약: `dumps\foms.dump`, `localdb\furniture_orders.db`, `localdb\migration_ready.db`, `localdb\ops_browser_qa.db` — 상세는 PTC 계획서 §3.4.

#### 2.6.3 FR20 — bounded context local `README.md` 정본 위치 (PTC)

- **page-first** bounded context(`orders`, `measurement`, `shipment`, `drawing`, `production`, `construction`, `cs`, `wdcalculator`, `admin`, `auth`): 정본은 **`foms/web/<context>/README.md`** 에 정확히 하나.
- **API-first** context(`channel`, `files`, `notifications`): 정본은 **`foms/api/<context>/README.md`** 에 정확히 하나.
- 금지: 한 context에 README 다중, `templates/`·`static/`에 canonical entrypoint로서의 중복 README.
- 내용 요구: 목적, 주요 모듈, 읽기 순서, 금지 의존성 — `2026-04-13` §1.2.20. 이행 표는 PTC 계획서 §4.2.

#### 2.6.4 루트에 두면 안 되는 것 (기존 hygiene)

- 로그 파일 (`*.log`)
- DB dump / SQLite / 임시 DB (`*.db`, `foms.dump`, migration-ready db 등) — §2.6.2의 외부 루트로만
- scratch HTML/JS
- 수작업 비교 산출물 (`all_changes.txt` 류)
- 일회성 마이그레이션/실험 스크립트

### 2.7 초기 단계 정의와 금지 이동 목록
이 Spec에서 `초기 단계`는 `Step 0 ~ Step 2`를 의미한다.

초기 단계에서 허용되는 것:
- 문서화
- inventory 작성
- baseline 검증 구축
- 루트 hygiene 정리

초기 단계에서 금지되는 것:
- boot-critical 파일의 경로 이동
- persistence 경로 이동
- harness 경로 이동
- `tests/harness/*` 경로 이동
- template/static 경로 이동

다음 항목은 초기 단계에서 직접 이동하지 않는다.
- `app.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `alembic.ini`
- `migrations/`
- `db.py`
- `models.py`
- `wdcalculator_db.py`
- `wdcalculator_models.py`
- `templates/`
- `static/`
- `.cursor/hooks.json`
- `tools/harness/*`
- `tests/harness/*`
- `docs/harness/bundles/HARNESS_BUNDLE_*.md`

경로 이동 금지와 내용 리팩터 허용 범위는 아래와 같다.

| 대상 | 초기 단계 경로 이동 | 초기 단계 내용 수정 |
|------|------|------|
| `app.py` | 금지 | 허용 안 함. inventory와 계약 정의만 허용 |
| 루트 로그/dump/scratch | 허용 | 허용 |
| `README.md` | 해당 없음 | 허용 |
| `db.py`, `models.py`, `wdcalculator_*` | 금지 | 허용 안 함 |
| `.cursor/hooks.json`, `tools/harness/*` | 금지 | 허용 안 함 |

### 2.8 의존성 및 영향 범위
- 배포 영향: `start.sh`, `Procfile`, `railway.toml`, `Dockerfile`, Railway service 설정
- 런타임 영향: `app.py`, gunicorn, gevent/SocketIO/Redis/WhiteNoise/Compress 초기화 순서
- DB 영향: `db.py`, `models.py`, `wdcalculator_db.py`, `wdcalculator_models.py`, `alembic.ini`, `migrations/env.py`
- 하네스 영향: `.cursor/hooks.json`, `.cursor/hooks/*`, `tools/harness/*`, `tests/harness/*`, `.github/workflows/harness-ci.yml`
- CI 영향: `.github/workflows/ci.yml`, `.github/workflows/harness-ci.yml`
- 문서 영향: `README.md`, `docs/context/*`, `docs/guides/*`, `docs/specs/*`

### 2.9 Railway / process model 계약
- Production web 계약은 `start.sh` -> `gunicorn ... app:app` 기준으로 본다.
- Worker 계약은 `USE_RQ_WORKER=1` 경로 또는 동등한 Railway worker 서비스 기준으로 본다.
- 구조 개편으로 web 경로를 바꾸는 단계에서는 worker 경로도 같은 변경 단위에서 함께 검증해야 한다.
- gunicorn worker class, timeout, graceful timeout, gevent 전제는 runtime contract의 일부로 간주한다.

### 2.10 롤백 원칙
- 구조 변경은 기본적으로 `git revert` 가능한 작은 단위로 쪼갠다.
- 배포 실패 시 Railway는 이전 정상 릴리스를 기준으로 되돌릴 수 있어야 한다.
- Alembic 관련 실패는 `downgrade`를 기계적으로 수행하지 않고, 사전 rehearsal이 있는 경우에만 사용한다.
- rehearsal이 없는 경우에는 forward fix 또는 backup/restore runbook을 우선한다.

## 3. Steps — 실행 단계
- [x] Step 0: 구조 거버넌스와 용어를 승인한다.
  - 결정할 것: 루트 허용 파일, 구조/네임스페이스에 직접 영향을 주는 도메인 용어(`measurement` vs `field`, `drawing` vs `design`), 초기 금지 이동 목록
  - Gate: 본 Spec 승인
  - Stop 조건: 도메인 명칭이나 경계에 합의가 안 되면 실제 이동 작업 시작 금지

- [x] Step 1: baseline 검증 패키지를 고정한다.
  - 실행 문서: `docs/plans/2026-04-07-phase1-baseline-matrix.md`
  - 최소 기준: `APP_OK`, `verify_result.py --json`, pytest 범위, 핵심 smoke checklist, harness bundle drift check 기준, web/worker process baseline
  - Gate: 현 구조에서 재현 가능한 기준 확보
  - Stop 조건: baseline이 재현되지 않으면 구조 변경 착수 금지

- [x] Step 2: 루트 hygiene 정리를 수행한다.
  - 실행 inventory: `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
  - 진행 상태: `Batch 1`/`Batch 2`/closeout 실행 완료. `run.py`는 기본적으로 root file log를 만들지 않고, file logging은 `FOMS_STARTUP_LOG_PATH` opt-in으로만 동작한다. 사용자 승인 후 legacy local dev 프로세스를 종료하고 기존 `app_startup.log`를 삭제했으며, `python app.py` 재기동 검증에서 root 기본 경로 미재생성까지 확인했다.
  - 참고: staging project(`FOMS-DEV`) 기준 worker basic smoke와 env parity는 `docs/plans/2026-04-07-phase1-baseline-run-record.md`에서 확인 완료
  - 대상: 로그, dump, scratch, local DB, 일회성 스크립트, 비교 산출물
  - 비대상: 부팅/배포/DB/harness 계약 파일
  - Gate: `app:app`, `start.sh`, `alembic`, `APP_OK` 불변
  - Stop 조건: 루트 정리 중 import/runtime 참조가 발견되면 그 항목 이동 보류

- [ ] Step 3: runtime namespace(`foms/`)와 호환 shim을 먼저 도입한다.
  - 진행 상태: `Batch 1`/`Batch 2(map_snapshot)`/`Batch 3(request_utils)`/`Batch 4(measurement_manager_colors)`/`Batch 5(geocode_helpers)`/`Batch 6(erp_shipment_settings)`/`Batch 7(erp_display, staged)`/`Batch 8(persistence import alignment)`/`Batch 9(erp_order_detail)`/`Batch 10(db_url_resolver + erp_utils)`/`Batch 11(erp_sync_columns, staged)`/`Batch 12(erp_product_items)`/`Batch 13(erp_sync_columns caller cleanup)`/`Batch 14(channel_event_payloads)`/`Batch 15(as_content_safety)`/`Batch 16(order_display_utils)`/`Batch 17(erp_template_filters)`/`Batch 18(order_geocode)`/`Batch 19(menu_config)`/`Batch 20(channel_wam_view_models)`/`Batch 21(file_utils)`/`Batch 22(channel_wam_read_model)`/`Batch 23(channel_wam_telemetry)`/`Batch 24(channel_wam_attachments)`/`Batch 25(channel_wam_service)`/`Batch 26(channel_identity)`/`Batch 27(channel_security)`/`Batch 28(order_storage_cleanup)`/`Batch 29(rate_limit)`/`Batch 30(realtime_notifications)`/`Batch 31(user_deletion)`/`Batch 32(db_indexes)`/`Batch 33(estimate_service)`/`Batch 34(channel_client)`/`Batch 35(order_attachment_thumbnail)`/`Batch 36(order_date_sync)`/`Batch 37(channel_policy)`/`Batch 38(channel_dispatch)`/`Batch 39(channel_delivery)`/`Batch 40(channel_inbound)`/`Batch 41(context_processors)`/`Batch 42(erp_permissions)`/`Batch 43(channel_quick_actions)`/`Batch 44(app_init)`/`Batch 45(order_date_sync_event)`/`Batch 46(storage)`/`Batch 47(storage caller cleanup)`/`Batch 48(erp_policy)`/`Batch 49(jobs package)`/`Batch 50(jobs caller cleanup)`/`Batch 51(erp_display caller cleanup)`/`Batch 52(erp_permissions caller cleanup)`/`Batch 53(channel_delivery caller cleanup)`/`Batch 54(as_content_safety caller cleanup)` 실행 완료.
    `foms/` package skeleton과 `foms/persistence/main/{db,models}.py` thin shim을 추가했고, 이어서 `foms/services/map_snapshot.py`, `foms/services/request_utils.py`, `foms/services/measurement_manager_colors.py`, `foms/services/geocode_helpers.py`, `foms/services/erp_shipment_settings.py`, `foms/services/erp_display.py`, `foms/services/erp_order_detail.py`, `foms/services/db_url_resolver.py`, `foms/services/erp_utils.py`, `foms/services/erp_sync_columns.py`, `foms/services/erp_product_items.py`, `foms/services/channel_event_payloads.py`, `foms/services/as_content_safety.py`, `foms/services/order_display_utils.py`, `foms/services/erp_template_filters.py`, `foms/services/order_geocode.py`, `foms/services/menu_config.py`, `foms/services/channel_wam_view_models.py`, `foms/services/file_utils.py`, `foms/services/channel_wam_read_model.py`, `foms/services/channel_wam_telemetry.py`, `foms/services/channel_wam_attachments.py`, `foms/services/channel_wam_service.py`, `foms/services/channel_identity.py`, `foms/services/channel_security.py`, `foms/services/order_storage_cleanup.py`, `foms/services/rate_limit.py`, `foms/services/realtime_notifications.py`, `foms/services/user_deletion.py`, `foms/services/db_indexes.py`, `foms/services/estimate_service.py`, `foms/services/channel_client.py`, `foms/services/order_attachment_thumbnail.py`, `foms/services/order_date_sync.py`, `foms/services/channel_policy.py`, `foms/services/channel_dispatch.py`, `foms/services/channel_delivery.py`, `foms/services/channel_inbound.py`, `foms/services/context_processors.py`, `foms/services/erp_permissions.py`, `foms/services/channel_quick_actions.py`, `foms/services/app_init.py`, `foms/services/order_date_sync_event.py`, `foms/services/storage.py`, `foms/services/erp_policy.py`에 더해 `foms/services/jobs/queue.py`, `foms/services/jobs/tasks.py`를 실제 service source of truth로 이동했다.
    legacy `services/map_snapshot.py`, `services/request_utils.py`, `services/measurement_manager_colors.py`, `services/geocode_helpers.py`, `services/erp_shipment_settings.py`, `services/erp_display.py`, `services/erp_order_detail.py`, `services/db_url_resolver.py`, `services/erp_utils.py`, `services/erp_sync_columns.py`, `services/erp_product_items.py`, `services/channel_event_payloads.py`, `services/as_content_safety.py`, `services/order_display_utils.py`, `services/erp_template_filters.py`, `services/order_geocode.py`, `services/menu_config.py`, `services/channel_wam_view_models.py`, `services/file_utils.py`, `services/channel_wam_read_model.py`, `services/channel_wam_telemetry.py`, `services/channel_wam_attachments.py`, `services/channel_wam_service.py`, `services/channel_identity.py`, `services/channel_security.py`, `services/order_storage_cleanup.py`, `services/rate_limit.py`, `services/realtime_notifications.py`, `services/user_deletion.py`, `services/db_indexes.py`, `services/estimate_service.py`, `services/channel_client.py`, `services/order_attachment_thumbnail.py`, `services/order_date_sync.py`, `services/channel_policy.py`, `services/channel_dispatch.py`, `services/channel_delivery.py`, `services/channel_inbound.py`, `services/context_processors.py`, `services/erp_permissions.py`, `services/channel_quick_actions.py`, `services/app_init.py`, `services/order_date_sync_event.py`, `services/storage.py`, `services/erp_policy.py`, `services/jobs/queue.py`, `services/jobs/tasks.py`는 각각 공개 API만 재수출하는 thin shim으로 유지했고, 실제 호출부는 배치별로 canonical import를 정리했다. `services/jobs/__init__.py`는 package-level shim으로 정리해 `from services.jobs import queue` 계약도 유지했다.
    특히 Batch 31을 통해 `apps/auth.py`/`apps/api/attachments.py`의 user deletion import를, Batch 32를 통해 `services/app_init.py`의 DB index lazy import를, Batch 33을 통해 `apps/api/erp_estimates.py`의 estimate helper import를, Batch 34를 통해 `services/channel_dispatch.py`/`apps/api/channel_integration.py`/`services/jobs/tasks.py`의 ChannelTalk client import를, Batch 35를 통해 `apps/api/attachments.py`의 thumbnail scheduler import를, Batch 36을 통해 `services/app_init.py`/`scripts/maintenance/backfill_phase4_dates.py`/`services/order_date_sync_event.py`의 order date sync import를, Batch 37을 통해 `services/channel_dispatch.py`/`services/channel_delivery.py`의 channel policy import를, Batch 38을 통해 `apps/api/channel_integration.py`/`services/jobs/tasks.py`의 channel dispatch import를, Batch 39를 통해 `foms/services/channel_dispatch.py`/`apps/api/channel_integration.py`/`services/jobs/queue.py`와 canonical-facing ChannelTalk smoke tests의 channel delivery import를, Batch 40을 통해 `apps/api/channel_webhooks.py`/`services/jobs/tasks.py`와 inbound webhook-focused tests의 channel inbound import를, Batch 41을 통해 `app.py`/`tests/test_menu_config.py`의 context processor import를, Batch 42를 통해 `app.py`의 ERP permission import를, Batch 43을 통해 `foms/services/channel_wam_service.py`/`apps/api/channel_functions.py`/`tests/test_channel_quick_actions.py`의 quick-action import를, Batch 44를 통해 `app.py`의 WSGI auto-init import를 canonical path로 전환했다. Batch 45는 production caller 변경 없이 dead-stub `order_date_sync_event` 자체를 canonical source로 정리하고 shim contract를 고정했다. Batch 46은 `foms/services/storage.py`를 canonical source로 이동하고 `services/storage.py`를 thin shim으로 고정한 뒤, `foms/services/order_attachment_thumbnail.py`, `foms/services/channel_wam_attachments.py`, `foms/services/order_storage_cleanup.py`, `foms/services/channel_quick_actions.py`, `foms/services/context_processors.py`, `foms/services/channel_dispatch.py`의 storage import를 canonical path로 전환했다. Batch 47은 이어서 `app.py`, `apps/admin.py`, `apps/api/attachments.py`, `apps/api/files.py`, `apps/api/channel_integration.py`, `apps/api/chat/routes.py`, `apps/api/chat/utils.py`, `apps/api/erp_orders_blueprint.py`, `apps/api/erp_orders_draftsman.py`, `apps/api/erp_orders_drawing.py`, `services/jobs/tasks.py`의 live storage caller를 canonical path로 정리했다. Batch 48은 `foms/services/erp_policy.py`를 canonical source로 고정하고 repo root `data/` 경로를 `Path(__file__).resolve().parent.parent.parent / "data"`로 계산하며, `business_days_until`는 lazy helper로 감싸 import-time `business_calendar` 결합을 낮췄다. 이어서 `app.py`, `erp_automation.py`, `apps/api/erp_orders_{drawing,draftsman,revision,structured}.py`, `apps/api/quest.py`, `apps/api/personal_board.py`, `apps/erp_{dashboard,drawing_workbench,construction_page,production_page}.py`, `foms/services/erp_display.py`, `foms/services/channel_event_payloads.py`의 ERP policy caller를 canonical import로 정리했다. Batch 49는 `foms/services/jobs/{queue,tasks}.py`를 canonical source로 추가하고 `services/jobs/{queue,tasks}.py`는 thin shim, `services/jobs/__init__.py`는 package-level shim으로 고정했다. 이때 enqueue 문자열은 의도적으로 `services.jobs.tasks.*`를 유지했고, `foms/services/channel_inbound.py`와 `foms/services/order_attachment_thumbnail.py`의 internal jobs caller만 먼저 canonical import로 전환했다. Batch 50은 이어서 `apps/api/channel_integration.py`, `apps/api/erp_measurement.py`, `apps/api/erp_orders_structured.py`, `apps/api/erp_shipment_settings.py`, `apps/api/orders.py`, `apps/api/erp_map.py`, `apps/order_pages.py`, `apps/order_edit.py`, `scripts/maintenance/geocode_backfill.py`의 live jobs caller를 canonical path로 정리하고, `erp_measurement.py`와 `erp_map.py`의 sync fallback task import 및 `geocode_backfill.py`의 queue resolver까지 canonical `foms.services.jobs` 경로로 전환했다. Batch 51은 Batch 7에서 staged 상태로 남아 있던 `erp_display` caller cleanup을 닫는 후속 배치로, `apps/erp.py`, `apps/erp_as_page.py`, `apps/erp_construction_page.py`, `apps/erp_dashboard.py`, `apps/erp_drawing_workbench.py`, `apps/erp_history_page.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_production_page.py`, `apps/erp_shipment_page.py`, `apps/order_edit.py`, `apps/order_trash.py`, `apps/api/erp_map.py`, `apps/api/erp_measurement.py`, `apps/api/erp_orders_as.py`, `apps/api/erp_orders_completion.py`, `apps/api/erp_orders_structured.py`, `apps/api/orders.py`, `apps/api/personal_board.py`의 live `erp_display` import를 canonical `foms.services.erp_display` path로 정리했다. Batch 52는 이어서 Batch 42에서 canonical source로 고정한 `erp_permissions` caller cleanup을 닫는 후속 배치로, `apps/erp.py`, `apps/erp_as_page.py`, `apps/erp_construction_page.py`, `apps/erp_dashboard.py`, `apps/erp_drawing_workbench.py`, `apps/erp_measurement_dashboard.py`, `apps/erp_production_page.py`, `apps/erp_shipment_page.py`, `apps/order_edit.py`, `apps/api/erp_map.py`, `apps/api/erp_measurement.py`, `apps/api/erp_orders_as.py`, `apps/api/erp_orders_confirm.py`, `apps/api/erp_orders_construction.py`, `apps/api/erp_orders_cs.py`, `apps/api/erp_orders_draftsman.py`, `apps/api/erp_orders_drawing.py`, `apps/api/erp_orders_production.py`, `apps/api/erp_orders_revision.py`, `apps/api/erp_shipment_settings.py`, `apps/api/orders.py`, `apps/api/quest.py`의 live `erp_permissions` import를 canonical `foms.services.erp_permissions` path로 정리했다. Batch 53은 이어서 Batch 39에서 canonical source로 고정한 `channel_delivery` caller cleanup을 닫는 후속 배치로, `apps/api/erp_measurement.py`, `apps/api/erp_orders_structured.py`, `apps/api/erp_shipment_settings.py`의 live lazy import를 canonical `foms.services.channel_delivery` path로 정리했다. Batch 54는 이어서 Batch 15에서 canonical source로 고정한 `as_content_safety` caller cleanup을 닫는 후속 배치로, `apps/erp_as_page.py`의 마지막 live `as_content_safety` import를 canonical `foms.services.as_content_safety` path로 정리했다. 그 결과 `apps/` 기준 남은 legacy `services.*` import는 사용자 제외 범위인 `business_calendar`만 남는다. 그 이전에는 Batch 4/5/6/7을 통해 `foms/services/map_snapshot.py`가 `services.measurement_manager_colors`, `services.geocode_helpers`, `services.erp_shipment_settings`, `services.erp_display`를 직접 참조하던 legacy 간선 네 개를 제거했고, Batch 8을 통해 `foms/services/*` 내부의 root `db`/`models` 직접 import를 `foms.persistence.main.*` 경로로 정렬했으며, Batch 9를 통해 dashboard caller의 `erp_order_detail` 경로를, Batch 10을 통해 `apps/api/erp_orders_as.py`와 order schedule backup/restore script의 utility import를 canonical path로, Batch 12를 통해 `apps/erp_drawing_workbench.py`/`apps/erp_measurement_dashboard.py`/`apps/erp_history_page.py`의 `erp_product_items` import를 canonical path로, Batch 14를 통해 `apps/api/erp_measurement.py`/`apps/api/erp_orders_structured.py`/`apps/api/erp_shipment_settings.py`와 `tests/test_channel_push_messages.py`의 `channel_event_payloads` import를 canonical path로, Batch 15를 통해 `apps/api/orders.py`/`apps/api/erp_orders_as.py`/`apps/erp_as_page.py`/`apps/erp_shipment_page.py`의 `as_content_safety` import를 canonical path로, Batch 16를 통해 `apps/order_pages.py`/`apps/order_trash.py`/`apps/excel_import.py`의 `order_display_utils` import를 canonical path로, Batch 17을 통해 `apps/erp.py`/`apps/erp_shipment_page.py`의 `erp_template_filters` import를 canonical path로, Batch 18을 통해 `apps/order_edit.py`/`apps/api/erp_orders_structured.py`/`apps/api/erp_measurement.py`/`apps/api/erp_map.py`의 `order_geocode` import를 canonical path로, Batch 19를 통해 `services/context_processors.py`/`apps/admin.py`의 `menu_config` import를 canonical path로, Batch 20을 통해 `services/channel_wam_service.py`/`services/channel_wam_attachments.py`/`services/channel_wam_telemetry.py`의 `channel_wam_view_models` import를 canonical path로, Batch 21을 통해 `apps/excel_import.py`의 파일 확장자 검증 helper를 canonical `file_utils.allowed_file()`로 전환했고, Batch 22를 통해 `services/channel_wam_service.py`의 `channel_wam_read_model` import를 canonical path로, Batch 23을 통해 `apps/api/channel_wam.py`의 telemetry import를 canonical path로, Batch 24를 통해 `apps/api/channel_wam.py`/`services/channel_wam_service.py`의 attachment import와 WAM backend monkeypatch target을 canonical path로 전환했으며, Batch 25를 통해 `apps/api/channel_wam.py`의 WAM service helper import를 canonical path로, Batch 26을 통해 `apps/api/channel_wam.py`의 manager identity import와 `services/channel_quick_actions.py`의 lazy identity import를 canonical path로, Batch 27을 통해 `apps/api/channel_wam.py`/`apps/api/channel_functions.py`/`apps/api/channel_webhooks.py`의 security import와 `services/channel_policy.py`/`services/channel_client.py`의 WAM short-link lazy import를 canonical path로, Batch 28을 통해 `apps/order_trash.py`의 영구 삭제 storage cleanup import를 canonical path로, Batch 29를 통해 `app.py`의 limiter bootstrap import를 canonical path로, Batch 30을 통해 `apps/api/notifications.py`/`apps/api/erp_orders_drawing.py`/`apps/api/erp_orders_revision.py`의 realtime notification import를 canonical path로 전환했다.
    Batch 7/11은 호출부 전면 교체 대신 일부 핵심 경로만 먼저 canonical import로 전환한 staged 배치였고, Batch 13은 그중 `erp_sync_columns` staged cleanup을 닫는 후속 배치였다. Batch 8/9/10/11/12/13/14/15/16/17/18/19/20/21/22/23/24/25/26/27/28/29/30/31/32/33/34/35/36/37/38/39/40/41/42/43/44/45/46/47/48/49/50/51/52/53/54는 사용자 요청에 따라 `business_calendar`/`/calendar` 축을 의도적으로 제외한 구조 정렬 배치다.
    `MAP_NS_OK`/`REQUEST_NS_OK`/`MEASUREMENT_COLORS_NS_OK`/`GEOCODE_HELPERS_NS_OK`/`ERP_SHIPMENT_SETTINGS_NS_OK`/`ERP_DISPLAY_NS_OK`/`ERP_DISPLAY_CALLERS_NS_OK`/`PERSISTENCE_NS_OK`/`ERP_ORDER_DETAIL_NS_OK`/`UTILITY_NS_OK`/`ERP_SYNC_COLUMNS_NS_OK`/`ERP_PRODUCT_ITEMS_NS_OK`/`CHANNEL_EVENT_PAYLOADS_NS_OK`/`AS_CONTENT_SAFETY_NS_OK`/`AS_CONTENT_SAFETY_CALLERS_NS_OK`/`ORDER_DISPLAY_UTILS_NS_OK`/`ERP_TEMPLATE_FILTERS_NS_OK`/`ORDER_GEOCODE_NS_OK`/`MENU_CONFIG_NS_OK`/`CHANNEL_WAM_VIEW_MODELS_NS_OK`/`FILE_UTILS_NS_OK`/`CHANNEL_WAM_READ_MODEL_NS_OK`/`CHANNEL_WAM_TELEMETRY_NS_OK`/`CHANNEL_WAM_ATTACHMENTS_NS_OK`/`CHANNEL_WAM_SERVICE_NS_OK`/`CHANNEL_IDENTITY_NS_OK`/`CHANNEL_SECURITY_NS_OK`/`ORDER_STORAGE_CLEANUP_NS_OK`/`RATE_LIMIT_NS_OK`/`REALTIME_NOTIFICATIONS_NS_OK`/`CHANNEL_CLIENT_NS_OK`/`ORDER_ATTACHMENT_THUMBNAIL_NS_OK`/`ORDER_DATE_SYNC_NS_OK`/`CHANNEL_POLICY_NS_OK`/`CHANNEL_DISPATCH_NS_OK`/`CHANNEL_DELIVERY_NS_OK`/`CHANNEL_DELIVERY_CALLERS_NS_OK`/`CHANNEL_INBOUND_NS_OK`/`CONTEXT_PROCESSORS_NS_OK`/`ERP_PERMISSIONS_NS_OK`/`ERP_PERMISSIONS_CALLERS_NS_OK`/`CHANNEL_QUICK_ACTIONS_NS_OK`/`APP_INIT_NS_OK`/`ORDER_DATE_SYNC_EVENT_NS_OK`/`STORAGE_NS_OK`/`STORAGE_CALLERS_NS_OK`/`ERP_POLICY_NS_OK`/`JOBS_NS_OK`/`JOBS_CALLERS_NS_OK`/`APP_OK`/`verify_result.py --json`/`pytest`를 재통과했고, 자동 전감리 기준 `storage`, `erp_policy`, `services.jobs`, `erp_display`, `erp_permissions`, `channel_delivery`, `as_content_safety` caller cleanup까지 마무리했다. `business_calendar` 모듈 자체와 `/calendar` 축은 사용자 지시에 따라 migration scope 밖으로 계속 제외한다. 사용자 제외 범위를 빼면 Step 3 active app/API caller cleanup은 사실상 종료 상태이며, 다음 자동 단계는 Step 5(vertical slice pilot) 전감리다.
  - 방향: 새 코드는 목표 구조(`platform / web / api / services / persistence`)에 넣고, 기존 import는 shim으로 유지
  - Gate: 루트 `app.py`, `db.py`, `models.py`에서 기존 import contract 유지
  - Stop 조건: 한 단계에서 여러 도메인 source of truth가 동시에 생기면 중단

- [x] Step 4: `app.py`를 slim entrypoint로 축소한다.
  - 진행 상태: `Batch 55(bootstrap contract freeze)`/`Batch 56(blueprint registry extraction)`/`Batch 57(HTTP bootstrap extraction)`/`Batch 58(realtime/limiter extraction)`/`Batch 59(app factory extraction)`/`Batch 60(closeout)` 실행 완료
  - 실행 기록: `docs/plans/2026-04-10-step4-batch55-bootstrap-contract-freeze-run-record.md`, `docs/plans/2026-04-10-step4-batch56-blueprint-registry-extraction-run-record.md`, `docs/plans/2026-04-10-step4-batch57-http-bootstrap-extraction-run-record.md`, `docs/plans/2026-04-10-step4-batch58-realtime-limiter-extraction-run-record.md`, `docs/plans/2026-04-10-step4-batch59-app-factory-extraction-run-record.md`, `docs/plans/2026-04-10-step4-batch60-closeout-run-record.md`
  - 결과: root `app.py`는 early runtime patch + canonical 공개 심볼 + `build_app()` 호출 + `run_auto_init()`/`main()` 분기만 남는 thin adapter로 축소됐고, bootstrap 구현은 `foms/platform/{blueprints,http,realtime,app_factory}.py`로 분리됐다
  - 방향: `foms/platform` 또는 동등한 namespace 아래로 extension/bootstrap/blueprint registration을 분리하되 `app:app` 계약 유지
  - Gate: gevent/SocketIO/Redis/WhiteNoise/Compress/teardown 순서 보존 검증 + gunicorn process model 검증
  - Stop 조건: 부팅 순서 변경 또는 production-only side effect 의심 시 즉시 중단

- [x] Step 5: vertical slice 1개를 시범 이관한다.
  - 진행 상태: `measurement` slice로 `Batch 61(contract freeze)`/`Batch 62(shared helper extraction)`/`Batch 63(canonical page/API modules)`/`Batch 64(map delegation)`/`Batch 65(template/JS namespace move)`/`Batch 66(closeout)` 실행 완료
  - 실행 기록: `docs/plans/2026-04-10-step5-batch61-contract-freeze-run-record.md`, `docs/plans/2026-04-10-step5-batch62-helper-extraction-run-record.md`, `docs/plans/2026-04-10-step5-batch63-canonical-modules-run-record.md`, `docs/plans/2026-04-10-step5-batch64-map-delegation-run-record.md`, `docs/plans/2026-04-10-step5-batch65-template-js-move-run-record.md`, `docs/plans/2026-04-10-step5-batch66-closeout-run-record.md`
  - 결과: `foms/web/measurement/dashboard.py`, `foms/api/measurement.py`, `foms/api/measurement_map.py`, `foms/services/measurement_dates.py`가 measurement slice의 canonical source of truth가 되었고, legacy `apps/*` / template / JS path는 alias shim 또는 wrapper로 유지됐다
  - 후감리 메모: summary API / map query / dashboard 본문의 주문 집합 차이는 Step 5 신규 회귀가 아니라 pre-migration legacy contract 유지였음을 확인했고, 관련 docstring만 실제 계약에 맞게 정정했다
  - Gate: 시범 slice는 구조만 바꾸고 비즈니스 동작은 바꾸지 않는다. 새 Alembic revision 금지
  - Stop 조건: slice 안에서 persistence 계약 변경이 필요하면 slice 작업 중단 후 별도 ADR 작성

- [x] Step 6: 대형 파일 분해 필요성을 inventory하고 별도 Spec으로 분리한다.
  - 진행 상태: `Batch 67(parallel pre-audit)`/`Batch 68(inventory)`/`Batch 69(separate decomposition spec)`/`Batch 70(closeout)` 실행 완료
  - 실행 기록: `docs/plans/2026-04-10-step6-large-file-inventory-plan.md`, `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`, `docs/plans/2026-04-10-step6-batch67-preaudit-run-record.md`, `docs/plans/2026-04-10-step6-batch68-inventory-run-record.md`, `docs/plans/2026-04-10-step6-batch69-decomposition-spec-run-record.md`, `docs/plans/2026-04-10-step6-batch70-closeout-run-record.md`, `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
  - 결과: large-file split 규칙을 root governance spec에서 분리했고, Tier A anchor candidate(`apps/api/orders.py`, `templates/wdcalculator/partials/wdcalculator_scripts.html`, `templates/partials/erp_beta_js.html`, `apps/api/chat/routes.py`, `foms/services/erp_policy.py`, `static/css/erp-pro.css`)를 inventory source of truth로 고정했다
  - Gate: Step 6는 docs-only다. actual decomposition execution은 future batch로 따로 계획하고 contract freeze/verification baseline을 먼저 깐다
  - Stop 조건: inventory 범위를 넘어 실제 런타임 refactor/schema/public path break가 필요해지면 즉시 중단하고 별도 execution plan/ADR로 분리

- [x] Step 7: docs/context 및 harness runtime 자산을 재분류한다.
  - 진행 상태: `Batch 71(parallel pre-audit)`/`Batch 72(plan freeze)`/`Batch 73(path foundation)`/`Batch 74(asset relocation)`/`Batch 75(active docs sync + bundle regen)`/`Batch 76(closeout)` 실행 완료
  - 실행 기록: `docs/plans/2026-04-10-step7-harness-asset-reclassification-plan.md`, `docs/plans/2026-04-10-step7-batch71-preaudit-run-record.md`, `docs/plans/2026-04-10-step7-batch76-closeout-run-record.md`
  - 결과: harness canonical 자산이 `docs/harness/{policy,bundles,runtime,logs}`로 분리됐고, `tools/harness/*` / Cursor·Claude hook / CI / tests / active guide/spec/rule 문서가 새 경로 기준으로 동기화됐다. `docs/context`는 incident/reference 기록만 남는다
  - Gate: bundle regeneration, `tests/harness`, `verify_result.py --json`, `APP_OK`, hook compile smoke, full `pytest`, lint까지 재통과
  - Stop 조건: bundle drift 또는 hook path break가 발생하면 즉시 롤백

- [x] Step 8: optional packaging(`src/foms` 등) 여부를 재평가한다.
  - 진행 상태: `Batch 77(parallel pre-audit)`/`Batch 78(plan freeze)`/`Batch 79(packaging decision freeze)`/`Batch 80(closeout)` 실행 완료
  - 실행 기록: `docs/plans/2026-04-11-step8-batch77-preaudit-run-record.md`, `docs/plans/2026-04-11-step8-optional-packaging-reevaluation-plan.md`, `docs/plans/2026-04-11-step8-batch79-packaging-decision-run-record.md`, `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`
  - 결과: current repo-root `foms/` package boundary를 유지하고 full `src/foms` migration 및 packaging-only `pyproject.toml` hardening은 둘 다 defer했다. 현재 `app:app`, `start.sh`, Railway/worker command, `migrations/env.py`, `tests/conftest.py`, root `db.py`/`models.py`/`apps/*`, `foms/services/jobs/tasks.py` repo-root depth contract가 repo-root layout에 강하게 결합돼 있어, packaging benefit보다 운영/검증 break risk가 더 크다고 판정했다.
  - Gate: `python tools/harness/build_context_bundle.py --all`, `python -m pytest tests/harness/test_context_bundle.py tests/harness/test_hooks_smoke.py -q`, `python -c "import app; print('APP_OK')"`, `python tools/harness/verify_result.py --json`, `python -m pytest -q`, `ReadLints` 재통과
  - Re-open 조건: web boot/worker/Alembic/tests import contract가 repo-root cwd에 의존하지 않도록 정리되고, CI/local/Railway가 같은 install contract를 공유하며, Step 6 future decomposition churn이 해당 surface에서 끝난 뒤 별도 ADR/plan으로 재개

## 4. 검증 기준
본 절 체크박스는 정책 baseline이다. Batch별 실제 실행/통과 여부와 예외는 해당 run record에서 관리한다.

- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 또는 동등한 shared verification baseline 통과
- [ ] `python -m pytest -q` 또는 승인된 테스트 subset 통과
- [ ] 하네스 관련 경로를 건드린 경우 `python -m pytest tests/harness -q` 통과
- [ ] 하네스 관련 경로를 건드린 경우 `python tools/harness/build_context_bundle.py --all` 통과 및 generated bundle drift 정리 완료
- [ ] `start.sh` 경로를 건드린 경우 web 부팅 경로(`app:app`) 유지 확인
- [ ] web runtime 계약을 건드린 경우 gunicorn/gevent/timeout/graceful shutdown 설정 보존 확인
- [ ] worker가 존재하는 경우 worker 경로와 env parity smoke 확인
- [ ] 배포/부팅 경로를 건드린 경우 Railway staging 또는 동등 환경에서 smoke 확인
- [ ] `alembic.ini`/`migrations`/DB 경로를 건드린 경우 `alembic current`, `alembic heads`, `alembic upgrade head` 통과
- [ ] 가능한 경우 empty DB 기준 `alembic upgrade head` 검증
- [ ] Alembic/autogenerate 사용 시 수동 검토 완료, downgrade rehearsal 또는 explicit forward-only 예외/backup plan 기록
- [ ] `migrations/env.py` 또는 model import root를 건드린 경우 `Base.metadata` target contract 검증
- [ ] `db.py`/`models.py`/`wdcalculator_*`를 건드린 경우 main DB와 WDCalculator DB/schema 모두 smoke 확인
- [ ] JSONB/`structured_data` 관련 persistence 리팩터는 `copy.deepcopy` + `flag_modified` 계약 유지 확인
- [ ] 구조 정리 단계에서는 비즈니스 로직 diff 없이 파일 배치와 import 경로만 바뀌는지 리뷰 확인
- [ ] 구조 정리 PR에서 새로운 Alembic revision이 섞이지 않았는지 확인
- [ ] `.github/workflows/ci.yml`, `.github/workflows/harness-ci.yml`가 영향 범위와 함께 green인지 확인
- [ ] 루트에 새로 추적되는 local/log/generated 파일이 없는지 `git status`로 확인

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md`의 `Harness cleanup tracking boundary`
- 관련 결정: `docs/harness/policy/DECISIONS.md`의 `Spec 탐색 규칙 단일화`
- 관련 결정: `docs/harness/policy/DECISIONS.md`의 `services/ 폴더 도입`
- 관련 자료: `docs/ARCHIVE_INDEX.md`
- 관련 실행 문서: `docs/plans/2026-04-07-phase1-baseline-matrix.md`
- 관련 실행 inventory: `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`
- 관련 실행 기록: `docs/plans/2026-04-07-step2-batch1-run-record.md`
- 관련 실행 기록: `docs/plans/2026-04-07-step2-batch2-run-record.md`
- 관련 실행 기록: `docs/plans/2026-04-07-step2-closeout-run-record.md`
- 관련 가이드: `docs/guides/SPEC_TEMPLATE.md`
- 관련 운영 문서: `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- 관련 상태 문서: `docs/AI_STATUS.md`

## 6. 승인 조건
본 절은 현재 시점의 진행 상태가 아니라, 구조 개편 전반에 적용되는 승인 게이트 정책을 정의한다.

본 Spec 승인 전에는 다음만 허용한다.
- 구조 개편 관련 조사
- baseline 검증 기준 정리
- 루트 파일 inventory 작성
- README/문서 진실도 교정 계획 수립

본 Spec 승인 후에만 다음을 허용한다.
- 루트 hygiene 정리 실행
- `app.py` slim entrypoint 작업
- vertical slice 시범 이관
- docs/context/harness 재분류 작업

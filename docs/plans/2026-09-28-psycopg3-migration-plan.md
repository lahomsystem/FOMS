# psycopg3 전환 계획 — DB 연결 부품 교체

- 작성 2026-09-28 · 기준 코드 `origin/deploy` `806b2e761` · 상태: **단계 1 운영(PR #435) · 단계 2 운영(PR #445) · 단계 3 구현(deploy, 스테이징 확인 중)**
- 근거: `docs/plans/2026-09-28-foms-language-migration-assessment-report.md` 판정 "백엔드 = 같은 언어 현대화 축소판(상향 + psycopg3)". Flask 3.1 상향은 끝났고(PR #431, production `ec7e5d843`), 이 문서는 남은 절반이다.
- 이 작업은 DB 계층 코어 변경이다 → 단계마다 사용자 승인 뒤 구현.

## 0. 한 줄 요약

드라이버 이름을 한 곳으로 모으고(1단계, 동작 변화 0), psycopg2 를 설치된 채로 둔 상태에서 psycopg3 로 바꾼 뒤(2단계, 되돌리기 한 줄), 직접 psycopg2 를 쓰는 도구까지 옮기고 나서 psycopg2 를 뺀다(3단계).

## 1. 왜 하나, 얼마나 급한가

얻는 것:
- **psycogreen 제거.** gevent 웹 서버가 DB 를 기다리는 동안 다른 요청을 처리하게 해 주는 부품인데, 2020-02-22 이후 새 판이 없다. psycopg3 는 3.1.14 부터 이 일을 스스로 한다.
- **SQLAlchemy 2.1 대비.** 2.1 은 드라이버를 적지 않은 `postgresql://` 주소의 기본값을 psycopg2 에서 psycopg3 로 바꾼다. 지금 구조로 2.1 에 올리면 SIDEFX·cron·alembic 이 **조용히** 다른 드라이버로 붙는다. 1단계만 해도 이 위험은 없어진다.

얻지 못하는 것(정직하게):
- psycopg2 는 멈춘 부품이 아니다. 2.9.13 이 2026-09-09 에 나왔다.
- 속도가 빨라진다는 근거는 없다. 분석 보고서의 순이득 모델에서도 이 작업의 환산 이득은 0 이다(보고서 ① C1-B 행).

그래서 급하지 않다. **1단계는 이득이 분명하고 위험이 작아서 바로 해도 좋다.** 2·3단계는 선택이다.

## 2. 전수 범위 (`origin/deploy` `806b2e761`, 테스트 제외 앱·도구)

### A. 드라이버를 명시해 연결을 만드는 곳 — 3곳
| 곳 | 하는 일 |
|---|---|
| `db.py:21-28` · `:59-68` | 본 엔진. `_ensure_psycopg2_driver` + `psycopg2.connect` creator |
| `foms/services/audit_writer.py:117-129` | 감사 로그 전용 소형 풀. 같은 creator 규약 |
| `wdcalculator_db.py:26-33` · `:86-100` | 계산기 엔진. `options=-c search_path=...` 를 넘긴다 |
| `foms/services/db_url_resolver.py:138` | 주소 → 연결 인자 변환. 이름이 `postgresql_psycopg2_connect_kwargs_from_url` |

### B. 드라이버를 적지 않은 `postgresql://` 로 엔진을 만드는 곳
SQLAlchemy 2.0 은 이 주소를 psycopg2 로 연다(공식 문서: psycopg2 가 "remains the default dialect for the postgresql:// dialect series"). **psycopg2 를 먼저 빼면 아래가 전부 멈춘다.**

운영에서 도는 곳:
| 서비스 | 곳 |
|---|---|
| SIDEFX | `foms/services/sidefx_worker.py:135` (`tools/ops/run_domain_side_effect_outbox.py:312` 가 부름) |
| FOMS-cron | `tools/cron/cleanup_order_drafts.py:62` · `tools/ops/purge_order_mutation_receipts.py:185` · `tools/ops/purge_audit_logs.py:377` |
| 배포 전 단계 | `migrations/env.py:127-129` (`predeploy.sh` 의 `alembic upgrade head`) · `alembic.ini:87` |

그 밖(운영 도구·일회성): `foms/services/orders/repair_order_state_axes.py:331`, `tools/ops/` 의 audit_as_axis_drift·backfill_as_axis_status·check_feature_cutover_modes·check_naver_repay_origin_alive·check_worker_redeploy_safe·list_active_users·purge_domain_side_effect_outbox·reconcile_ops_approval_reservations, `scripts/` 의 diagnose_measurement_date_missing·migrate_* 6개.

### C. psycopg2 를 직접 부르는 곳
| 곳 | 비고 |
|---|---|
| `tools/ops/ensure_schema.py:8,17` | **`predeploy.sh` 가 배포마다 실행.** 3단계 전에 반드시 옮겨야 한다 |
| `tools/ops/data_doctor.py:43-92,471-539` | `RealDictCursor` · `extras.Json` |
| `tools/ops/bulk_complete_past_construction_core.py:25-82,353-412` · `bulk_complete_past_construction.py:56,155,190` | 같음 |
| `tools/ops/naver_return_watch.py:75-77` | 연결만 |
| `scripts/migrations/migrate_as_orders.py` · `railway_migrate_team.py` | 일회성. 옮기거나 보관 표시 |

### D. 오류 코드 읽기 — 3곳
`foms/services/app_init.py:86` · `:135`, `foms/services/db_indexes.py:46` 가 `orig.pgcode == "55P03"` 로 잠금 대기 초과를 판정한다. psycopg3 오류에는 `pgcode` 가 없고 `sqlstate` 만 있다(3.3.6 `errors.py:456`, `pgcode` 0건). 두 번째 조건인 클래스 이름 `LockNotAvailable` 은 psycopg3 에도 같아서(`errors.py:1543`) 판정은 깨지지 않지만 첫 조건은 죽은 코드가 된다.

### E. gevent
`app.py:7-13` psycogreen 패치, `requirements.txt:67` `psycopg2-binary==2.9.9`, `:116` `psycogreen>=1.0`. gevent 는 웹(gunicorn `-k gevent`, `start.sh:127`·`Procfile:3`)에서만 켜진다. WORKER·SIDEFX·cron 은 gevent 를 쓰지 않는다.

### F. 테스트
`tests/postgres/conftest.py:118-120,168` · `test_migration_chain.py:112` · `tests/domains/test_channel_webhook_auth.py:124` · `test_soft_delete_core.py:65` · `tests/postgres/test_bulk_complete_past_construction_pg.py:38` · `tests/domains/test_db_url_resolver.py:84-86` · 표면 계약 `tests/contracts/runtime/foms_namespace_surface_tests.py:417` · `tests/harness/test_postgres_guard.py:22`.

### G. 확인했고 문제없는 것
- `yield_per`(서버 쪽 커서) 약 20곳: SQLAlchemy psycopg 방언도 지원한다. 2단계에서 PG 레인으로 확인한다.
- `SET LOCAL lock_timeout/statement_timeout` (`app_init.py:46-47`, `db_indexes.py:40-41`): 값이 SQL 문자열 안에 들어 있어 바인딩 방식과 무관하다.
- `:값 IS NULL` 꼴 SQL: 줄 단위 검색 0건. (여러 줄 SQL 은 이 검색이 못 잡는다 → 결정 1 로 막는다.)
- SQLAlchemy 2.0.24~2.0.54 변경 기록의 psycopg3 수정 3건(2상 커밋 2건, JSONB `path_match`/`path_exists` 1건)은 FOMS 가 쓰지 않는 기능이다(사용 0). **SQLAlchemy 2.0.23 은 그대로 둔다.**
- CI 워크플로·`foms/build_compatibility.json` 의 psycopg 언급 0. PG 레인 테스트 파일 75개.

## 3. 외부 사실 (확인 2026-09-28)

| 사실 | 출처 |
|---|---|
| psycopg 최신 3.3.6 (2026-09-18), 파이썬 3.10~3.15, Windows·Linux cp312 바이너리 있음 | https://pypi.org/pypi/psycopg/json · https://pypi.org/pypi/psycopg-binary/json |
| psycopg2-binary 최신 2.9.13 (2026-09-09) | https://pypi.org/pypi/psycopg2-binary/json |
| psycogreen 최신 1.0.2 (2020-02-22) | https://pypi.org/pypi/psycogreen/json |
| gevent 최신 26.9.0 (2026-09-16) | https://pypi.org/pypi/gevent/json |
| psycopg3 는 3.1.14 부터 gevent 를 스스로 지원, psycogreen 불필요 | https://www.psycopg.org/psycopg3/docs/advanced/async.html |
| psycopg3 는 **불러오는 순간** gevent 패치 여부를 보고 기다리는 방식을 정한다 | 3.3.6 소스 `psycopg/waiting.py:505-562` https://github.com/psycopg/psycopg/blob/3.3.6/psycopg/psycopg/waiting.py |
| 값을 서버로 따로 보낸다: `SET`·DDL 에 값 불가, `IN %s` 튜플 불가, `IS %s` 불가, 값이 있으면 여러 문장 불가, `with conn:` 이 연결을 닫음, `RealDictCursor` → `dict_row` | https://www.psycopg.org/psycopg3/docs/basic/from_pg2.html |
| 오류 코드는 `sqlstate`, `pgcode` 없음 | 3.3.6 소스 `psycopg/errors.py` https://github.com/psycopg/psycopg/blob/3.3.6/psycopg/psycopg/errors.py |
| SQLAlchemy 방언 `postgresql+psycopg://`, `cursor_factory=ClientCursor` 로 psycopg2 식 바인딩 가능 | https://docs.sqlalchemy.org/en/20/dialects/postgresql.html (Using a different Cursor class) |
| SQLAlchemy 2.1 은 `postgresql://` 기본 드라이버를 psycopg3 로 바꿈 | https://docs.sqlalchemy.org/en/21/changelog/migration_21.html |
| SQLAlchemy 2.0 최신 2.0.54 (2026-09-15) | https://docs.sqlalchemy.org/en/20/changelog/changelog_20.html |

## 4. 설계 결정

1. **처음 전환은 `ClientCursor`(값을 SQL 에 끼워 보내는 psycopg2 식)로 한다.** 앱 코드의 `text(` 호출이 901곳이고 대부분의 테스트가 SQLite 에서 돈다. 서버 바인딩의 차이(여러 줄 `IS NULL`, `SET` 값, 여러 문장, `IN` 튜플)를 테스트가 다 잡지 못한다. `ClientCursor` 면 이 차이가 거의 없어지고, 자동 준비문(prepared statement) 문제도 생기지 않는다. 서버 바인딩은 따로 이득이 측정될 때만 연다.
2. **드라이버 이름은 `foms/services/db_url_resolver.py` 한 곳에서만 정한다.** 엔진을 만드는 모든 곳은 이 모듈의 함수를 거친다. 계약 테스트가 이를 강제한다.
3. **2단계 동안 psycopg2 는 설치된 채로 둔다.** 되돌리기가 상수 한 줄 + 커밋 하나로 끝나고, 빌드가 바뀌지 않는다.
4. **SQLAlchemy 2.0.23 은 그대로 둔다**(2절 G). 올리는 일은 별도 작업이다.
5. **패키지는 `psycopg[binary]==3.3.6` 로 고정한다.** Dockerfile(web)은 이미 `libpq5` 를 설치하지만, WORKER·cron·SIDEFX 는 nixpacks 빌드라서 바이너리 판이 안전하다.

## 5. 단계

### 단계 0 — 사전 확인 (코드 변경 0)
1. 운영·스테이징 `DATABASE_URL` 이 PgBouncer 같은 연결 중계기를 거치는지 **호스트 이름만** 확인한다(값 출력 금지). 결정 1 이면 결과와 상관없이 안전하지만, 나중에 서버 바인딩을 열 때 필요한 사실이다.
2. 기준선: 스테이징 대표 화면 응답 시간(`tools/perf/staging_perf_gate.py` 방법론)을 전환 전에 잰다.
3. gevent 협력 시험의 **음성 대조군**: 로컬 PG 에서 gevent 패치 뒤 연결 8개가 `SELECT pg_sleep(0.5)` 를 동시에 돌린다. psycopg2+psycogreen 이면 약 0.5초, psycogreen 을 빼면 약 4초가 나와야 시험이 막힘을 잡아낼 수 있다는 증거가 된다.

#### 단계 0 결과 (2026-09-29)
1. **연결 중계기 없음**: 스테이징·운영 web 의 `DATABASE_URL` 호스트는 둘 다 `postgres.railway.internal:5432`(PgBouncer·pooler 아님). 준비문 문제 없음.
2. **응답 시간 기준선**: deploy 마다 도는 `perf-gate (staging)` CI 기록을 그대로 쓴다(따로 재지 않음).
3. **gevent 협력 시험 + 음성 대조**(로컬 PostgreSQL 17, 연결 8개 × `pg_sleep(0.5)`, 직렬이면 4초):
   - 패치 없음 **4.09초**(줄 섬) · `app.py` 실제 패치 블록 **0.52초**(겹침) · gevent 패치만 하고 psycogreen 없음 **4.06초** → 지금은 psycogreen 이 협력을 만든다.
   - psycopg 3.3.6 미리 보기(작업 폴더 venv 에만 설치, `ClientCursor`, psycogreen 없음): 패치 없음 4.08초 · 패치 뒤 import **0.515초**. 패치 **전** import 도 0.515초였는데, Windows 에서는 psycopg 가 C 대기 함수(`wait_c`)를 아예 안 쓰기 때문이다(`waiting.py:549` 의 `sys.platform != "win32"`) → **순서 위험은 Linux(운영·CI)에서만 재현**된다. 그래서 정적 계약으로 막는다.
   - 영구 시험: `tests/postgres/test_gevent_db_cooperation_pg.py`(+ 자식 프로세스 `gevent_db_probe.py`, `app.py` 의 실제 패치 블록을 AST 로 꺼내 실행 — 앱 import 없음) · `tests/contracts/runtime/test_gevent_patch_runs_first.py`(`app.py` 에서 패치 블록 앞에는 `import os` 뿐). 단계 2 에서 psycogreen 을 빼도 같은 시험이 그대로 판정한다.

### 단계 1 — 한 곳으로 모으기 (드라이버는 여전히 psycopg2, 동작 변화 0)
할 일:
- `db_url_resolver.py` 에 `PG_SQLALCHEMY_DRIVER = "psycopg2"`, `sqlalchemy_url(url)`(드라이버를 붙이는 유일한 함수, PostgreSQL 이 아니면 그대로), `postgres_dbapi_connect(kw)`(DBAPI 연결을 여는 유일한 함수)를 둔다. `postgresql_psycopg2_connect_kwargs_from_url` → `postgresql_connect_kwargs_from_url` 로 이름을 바꾸고 표면 계약(`foms_namespace_surface_tests.py:417`)을 함께 고친다.
- `db.py`·`wdcalculator_db.py` 의 `_ensure_psycopg2_driver` 2벌을 지우고 새 함수로 바꾼다.
- 2절 B 의 모든 `create_engine` 호출과 `migrations/env.py` 가 새 함수를 거치게 한다. `alembic.ini:87` 의 드라이버 표기도 없앤다.
- 2절 D 3곳을 `db_url_resolver.pg_error_code(exc)`(= `sqlstate` 없으면 `pgcode`) 하나로 바꾼다.
- 계약 테스트 추가: (a) `postgresql+psycopg` 문자열이 `db_url_resolver.py` 밖(테스트 제외)에 없다, (b) 저장소의 `create_engine(` 호출이 새 함수를 거친다, (c) `.pgcode` 직접 읽기가 헬퍼 밖에 없다.

완료 기준: 전체 스위트 + PG 레인 통과, `pre_push_smoke.ps1` exit 0, deploy CI green, 스테이징 `/healthz` 반영, SIDEFX 하트비트·cron 다음 실행(KST 02:00) 성공 로그. 운영 승격은 사용자 요청 시.
되돌리기: 커밋 되돌림(동작 변화가 없으므로 위험 낮음).

#### 단계 1 구현 기록 (2026-09-28, 브랜치 `session/pgdriver`)
- 정본: `foms/services/db_url_resolver.py` — `PG_SQLALCHEMY_DRIVER`·`sqlalchemy_url`·`postgres_dbapi_connect`·`pg_error_code`. `_ensure_psycopg2_driver`·`_normalize_postgres_url` 복사본(db.py·wdcalculator_db.py·migrations/env.py) 삭제.
- 경유시킨 곳: creator 3곳(db·audit_writer·wdcalculator_db), 운영 경로 5곳(SIDEFX `make_engine_from_env`, cron `cleanup_order_drafts`·`purge_audit_logs`·`purge_order_mutation_receipts`, SIDEFX 보존 `purge_domain_side_effect_outbox`), alembic `env.py`·`alembic.ini`, 운영 도구 8곳, `scripts/maintenance/diagnose_measurement_date_missing.py`. 독립 스크립트(cron·purge·list_active_users)는 저장소 루트를 `sys.path` 에 넣는 기존 관용(`check_worker_redeploy_safe.py:34`)을 따랐다.
- 테스트 레인도 상수를 따른다: `tests/postgres/conftest.py` `_raw_connect` → `postgres_dbapi_connect`, 레인 엔진 4곳 `drivername=f"postgresql+{PG_SQLALCHEMY_DRIVER}"` — 단계 2 에서 상수만 바꾸면 PG 레인이 새 드라이버로 돈다.
- 계약 `tests/domains/test_pg_driver_single_source.py`: 드라이버 문자열·`pgcode`/`sqlstate` 읽기·앱 코드의 psycopg import 가 정본 밖에 0, 엔진을 만드는 파일은 모두 `sqlalchemy_url(` 사용, 운영 경로 5곳이 `postgres://` 를 받아 `postgresql+<정본>` 엔진을 만든다(옛 코드는 `postgresql` 이라 실패 — 음성 대조 확인). 스캐너 자체의 음성 대조 포함.
- 범위 밖으로 남긴 것: `scripts/migrations/`(§8-2 결정 대기), 2절 C 의 psycopg2 직접 사용 도구(단계 3).

### 단계 2 — 드라이버 전환 (psycopg2 는 설치 유지)
할 일:
- `requirements.txt` 에 `psycopg[binary]==3.3.6` 추가. `psycopg2-binary` 는 남긴다.
- `PG_SQLALCHEMY_DRIVER = "psycopg"`, creator 3곳을 `psycopg.connect(**kw, cursor_factory=ClientCursor)` 로. `wdcalculator_db` 의 `options` 인자는 psycopg3 도 같은 이름으로 받는다(libpq 인자).
- `app.py:7-13` 의 psycogreen 블록과 `requirements.txt:116` 삭제.
- 시험 추가 (PG 레인, `tests/postgres/`):
  - gevent 협력: 새 프로세스에서 `gevent.monkey.patch_all()` → `import app` 과 같은 순서로 psycopg 를 불러와 8개 동시 `pg_sleep(0.5)` 가 1.5초 안에 끝난다. 대조군: 패치 없이 돌리면 4초 이상(시험이 막힘을 잡는다는 증명).
  - 불러오는 순서: `app.py` 에서 gevent 패치가 `db` 등 psycopg 를 끌어오는 import 보다 먼저 온다(3절 `waiting.py` 사실 때문).
  - JSONB 왕복(`structured_data` 쓰기 → `flag_modified` → 다시 읽기), `yield_per` 스트리밍, 잠금 대기 초과가 `pg_error_code == "55P03"` 로 잡히는지.

완료 기준: 단계 1 기준 + 스테이징에서 로그인·대표 화면 4개·시험 주문(`CLAUDE-TEST-`) 생성·첨부 올리기·삭제·Socket.IO·RQ 잡 1건·SIDEFX 한 바퀴·배포 전 단계 alembic 로그 정상, 응답 시간이 단계 0 기준선보다 나쁘지 않음. 운영 승격 뒤 1주 동안 운영 오류 로그에 psycopg 관련 새 예외 0.
되돌리기: `PG_SQLALCHEMY_DRIVER = "psycopg2"` 한 줄 + psycogreen 블록 복원 커밋. psycopg2 가 설치돼 있으므로 빌드 변경 없음.

#### 단계 2 구현 기록 (2026-09-29)
- `PG_SQLALCHEMY_DRIVER = "psycopg"`, `postgres_dbapi_connect` = `psycopg.connect(..., cursor_factory=ClientCursor)`, `requirements.txt` 에 `psycopg[binary]==3.3.6` 추가·psycogreen 삭제(psycopg2-binary 는 유지), `app.py` psycogreen 블록 삭제.
- **첫 PG 레인에서 2건 실패 → 근본 수정**
  1. `test_access_log_detail_pg`: `AmbiguousParameter`(`$1` = 서버 쪽 바인딩). URL 로 만든 엔진은 creator 를 안 거쳐 ClientCursor 가 빠졌다 → `db_url_resolver` 의 `Engine` `connect` 이벤트가 모든 psycopg 연결에 `ClientCursor` 를 건다. 시험 `tests/postgres/test_psycopg_client_binding_pg.py`(음성 대조: 기본 커서는 같은 SQL 에서 `AmbiguousParameter`).
  2. `test_migration_chain`: `DROP INDEX CONCURRENTLY cannot run inside a transaction block`. 마이그레이션 7개가 `execute(text("COMMIT"))` 뒤 DDL 을 돌렸는데, psycopg2 는 트랜잭션 상태를 추적하지 않아 통했고 psycopg 는 새 BEGIN 을 연다 → `op.get_context().autocommit_block()`. 계약: 마이그레이션에 문자열 COMMIT 금지. (운영·스테이징 DB 는 이미 적용된 파일이라 동작 변화 없음, 빈 DB 새 구축에만 영향.)
- 결과: 전체 11038 passed, PG 레인(로컬 PostgreSQL 17) **798 passed**(gevent 협력 시험이 psycogreen 없이 통과 포함).

### 단계 3 — 정리 (psycopg2 삭제)
할 일:
- 2절 C 의 도구를 psycopg3 로 옮긴다: `RealDictCursor` → `row_factory=dict_row`, `extras.Json` → `psycopg.types.json.Jsonb`, `with conn:` 이 연결을 닫는 차이 확인. **`ensure_schema.py` 가 먼저**(배포 전 단계).
- 2절 F 테스트의 `drivername="postgresql+psycopg2"` 를 새 함수로.
- `requirements.txt:67` `psycopg2-binary` 삭제. 계약 테스트: `import psycopg2` 0건.

완료 기준: 단계 2 기준 + 새 빌드(4개 서비스 모두) 성공, `railway deployment list` 로 서비스 4종 SUCCESS.
되돌리기: `psycopg2-binary` 한 줄 복원(빌드 필요).

#### 단계 3 구현 기록 (2026-09-29)
- 배포 전 단계 `tools/ops/ensure_schema.py`: 손으로 URL 을 풀던 `psycopg2.connect` → `postgres_dbapi_connect(postgresql_connect_kwargs_from_url(...))`(저장소 루트 import 경로 부트스트랩 추가). `postgres://`·`?sslmode=` 주소도 같은 키로 풀리는 것 확인.
- 운영 도구: `data_doctor.py`·`bulk_complete_past_construction_core.py`(+ 진입 스크립트) 는 `psycopg.connect(dsn, cursor_factory=ClientCursor)` + `row_factory=dict_row` + `Jsonb`, 읽기 전용은 `conn.read_only = True`. `naver_return_watch.py` 는 `autocommit=True` + `default_transaction_read_only=on`(옛 `set_session(readonly=True, autocommit=True)`). `with conn:` 로 연결을 쓰던 곳은 없었다(psycopg 에선 연결을 닫는 차이 — 해당 없음).
- 일회성 스크립트 `scripts/migrations/` 7개(§8-2): 보관만 하지 않고 옮겼다 — 엔진은 `sqlalchemy_url`, 직접 연결은 `postgres_dbapi_connect`.
- `pg_error_code` 는 `sqlstate` 만 읽는다(psycopg2 `pgcode` 분기 삭제). `requirements.txt` 에서 `psycopg2-binary` 삭제.
- 계약: `tests/domains/test_pg_driver_single_source.py::test_psycopg2_is_gone_from_code_tests_and_requirements` — `foms`·`tools`·`scripts`·`migrations`·`tests`·루트에서 `import psycopg2`·`psycopg2.connect/extras` 0건, requirements 에 없음(음성 대조 포함).
- **PG 레인에서 1건 실패 → 근본 수정**: `test_bulk_complete_past_construction_pg` 에서 `syntax error at or near "'(COMPLETED,...)'"`. psycopg2 는 파이썬 튜플을 `IN (a, b)` 목록으로 풀었고 psycopg 는 따옴표 문자열 하나로 보낸다 → 리스트(text[]) + `= ANY(%(x)s)`/`<> ALL(%(x)s)`. 같은 모양은 저장소 전체에서 이 도구 2곳뿐(SQLAlchemy `text()` 의 `IN :x` 는 0건). 계약 `test_no_tuple_placeholder_after_in`(음성 대조 포함).
- 결과: psycopg2·psycogreen 을 지운 가상환경에서 전체 11059 passed, PG 레인 797 passed + 수정 뒤 해당 시험 통과.

## 6. 위험

| 위험 | 막는 방법 |
|---|---|
| 드라이버 없는 주소가 psycopg2 삭제 뒤 멈춤 (SIDEFX·cron·alembic) | 단계 1 계약 테스트 + psycopg2 는 단계 3 에서야 삭제 |
| gevent 대응이 꺼져 웹 요청이 줄 섬 | 단계 2 협력 시험 + 대조군 + import 순서 계약 |
| 서버 바인딩 차이로 드문 SQL 이 운영에서만 실패 | 결정 1 (`ClientCursor`) |
| 오류 코드 판정이 한쪽만 살아 있음 | 단계 1 `pg_error_code` 헬퍼 |
| 타입 차이(시간대 객체 종류, UUID·날짜 표현)로 화면 값이 바뀜 | PG 레인 + 스테이징 대표 화면 비교. 알려진 예: `tests/postgres/test_purge_order_mutation_receipts.py:113` 의 UUID 정규화 |
| 배포 전 단계(`ensure_schema.py`) 실패로 배포 자체가 막힘 | 단계 3 에서 가장 먼저, 스테이징에서 배포 1회로 확인 |

## 7. 멈춤 조건

- 단계 0 의 대조군이 차이를 못 보이면(두 경우 모두 빠르거나 모두 느림) 협력 시험을 믿을 수 없으므로 단계 2 에 들어가지 않는다.
- 단계 2 스테이징에서 응답 시간이 기준선보다 나빠지면 원인을 잴 때까지 운영 승격을 멈춘다.
- cherry-pick 충돌이 나면 다른 창 작업에 의존한다는 신호이므로 임의로 풀지 않는다.

## 8. 사용자가 정할 것

1. 어디까지 할지: 단계 1만 / 단계 2까지 / 단계 3까지.
2. 일회성 스크립트(`scripts/migrations/` 6개)를 옮길지, 보관 표시만 할지.
3. 서버 바인딩(psycopg3 기본 방식)을 나중에라도 열지 — 지금 계획은 열지 않는다.

작업량은 분석 보고서의 범위(psycopg3 몫 0.3 / 1 / 3 주, 원장 `:151`)를 그대로 쓴다. 이 문서는 새로 추정하지 않는다.

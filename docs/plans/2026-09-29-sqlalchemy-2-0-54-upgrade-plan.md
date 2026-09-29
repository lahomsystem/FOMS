# SQLAlchemy 2.0.23 → 2.0.54 상향 계획

- 작성 2026-09-29 · 기준 `origin/deploy` · 상태: **승인 대기**
- 종류: DB 계층 코어 변경 → 계획 승인 뒤 구현.

## 0. 쉬운 요약

DB 도구(SQLAlchemy)를 같은 2.0 줄의 최신판 2.0.54(2026-09-15)로 올린다. 2.0.24~2.0.54 변경 기록을 모두 읽고 FOMS 가 쓰는 곳과 맞대 보았는데 **지금 코드를 깨는 항목은 찾지 못했다**. 조심할 것은 두 가지다. ① 2.1 이 이미 나왔으므로(2.1.0 2026-09-24, 2.1.1 2026-09-25) 버전을 **정확히 고정**해야 한다. ② ORM 조회 경로의 버그 수정 한 건이 FOMS 구조(전역 `do_orm_execute` 훅 + `yield_per`)를 지나므로 시험으로 확인한다.

## 1. 확인한 사실

| 항목 | 사실 | 출처 |
|---|---|---|
| 목표판 | 2.0 최신 2.0.54(2026-09-15). 전체 최신은 2.1.1 | https://pypi.org/pypi/SQLAlchemy/json (확인 2026-09-29) |
| 지금 | `requirements.txt` `SQLAlchemy==2.0.23`, Flask-SQLAlchemy 3.1.1(`sqlalchemy>=2.0.16`, 상한 없음) | `requirements.txt:95`, PyPI |
| 바이너리 | cp312 win_amd64·manylinux 휠 있음(Dockerfile `python:3.12-slim`) | PyPI |

### FOMS 에 닿는 변경 기록 (https://docs.sqlalchemy.org/en/20/changelog/changelog_20.html)

| 판 | 항목 | FOMS 영향 |
|---|---|---|
| 2.0.50 (#13301) | `do_orm_execute` 훅이 두 번째 컴파일에 `yield_per`·로더 상태를 새지 않게 수정 | FOMS 는 전역 훅(`foms/services/attachment_visibility.py`) + `selectinload` 17곳 + `yield_per` 16곳 → **버그 수정이지만 그 길을 지나므로 시험 필수** |
| 2.0.42 (#10927) | PG 14+ 에서 JSONB 는 `col -> 'k'` 대신 `col['k']` 로 그림 → 기존 식 인덱스와 안 맞을 수 있음 | 지금은 영향 없음: FOMS 의 JSON 칸은 모두 `JSON().with_variant(JSONB, …)`(바탕 형 JSON)이라 `->` 가 유지된다(조사 결과, 상향 뒤 컴파일로 재확인). **앞으로 바탕 형을 JSONB 로 바꾸면 부분 인덱스 `ix_external_order_link_dispatch_pending` 가 안 쓰일 수 있음** |
| 2.0.36 (#11994) | JSON/JSONB bind cast 위치 이동 | 없음 — FOMS 는 `bind_typing = NONE`(cast 안 그림) |
| 2.0.53 (#13548) | connect 이벤트가 예외를 던질 때 연결 누수 수정 | 이득 — `db_url_resolver` 의 connect 리스너 |
| 2.0.43 (#12784) | psycopg 자동 커밋 감지 옵션 추가(기본 꺼짐) | 없음 |
| 2.0.36 (#11917) | ORM UPDATE 뒤 `onupdate` 칸 새로 읽기 | 없음 — `Query.update` 9곳 모두 `synchronize_session=False` |
| 2.0.26·29 | insertmanyvalues(여러 행 INSERT) 수정 | 낮음 — 백필 `add_all` 6곳 |
| 2.0.24 (#10662) | `URL.render_as_string` 비번 인코딩 | 낮음 — PG 레인 시험 5곳(로컬 비번에 특수문자 있을 때만) |

### 방언 하위 클래스(`foms/services/db_url_resolver.py`)
2.0.23 과 2.0.54 소스 비교: `create_server_side_cursor`·방언 레지스트리 등록·`_supports_statement_cache`(클래스 자신의 `__dict__`)·`bind_typing` 판정은 **바뀌지 않았다**. 지금 계약(`test_pg_driver_single_source.py`)이 그대로 유효하다.

### DISTINCT ON (SQLite 시험 레인 경고)
- 호출 4곳: `foms/api/erp_map.py:135`, `foms/web/shipment/dashboard.py:306·382·557`.
- 2.0.54·2.1.1 모두 **아직 경고**(오류 아님). 다만 지금도 SQLite 레인에서는 DISTINCT ON 이 조용히 무시되어 이 네 경로의 중복 제거가 시험되지 않는다 → PG 레인 시험이 있는지 상향 작업에서 확인하고, 없으면 하나 더한다. 2.1 에서는 `postgresql.distinct_on()` 으로 바꿔야 한다(2.1 상향 때 할 일).

## 2. 할 일

1. `requirements.txt:95` → `SQLAlchemy==2.0.54`(정확 고정 — `-U` 금지, 2.1 로 뛴다).
2. 새 계약: `requirements.txt` 의 SQLAlchemy 가 `==2.0.x` 로 고정돼 있는지(2.1 우발 상향 방지).
3. 컴파일 확인 시험(하나로): `Order.structured_data["a"]["b"].as_string()` 가 여전히 `->`/`->>` 로 그려지는지(부분 인덱스 보호), 문자열 id 비교에 `::` 가 없는지.
4. `do_orm_execute` + `yield_per` + `selectinload` 조합을 지나는 PG 레인 시험이 있는지 확인, 없으면 추가(첨부 가시성 훅이 걸린 모델을 `yield_per` 로 읽기).
5. 계획 문서 `2026-09-28-psycopg3-migration-plan.md` §2-G 의 "SQLAlchemy 2.0.23 은 그대로 둔다" 문장을 이 계획으로 연결.

## 3. 검증

- `python -c "import app; print('APP_OK')"`, `sqlalchemy.__version__ == "2.0.54"`.
- 전체 시험 + PG 레인(PostgreSQL 17) — 경고 요약을 상향 전후로 비교(DISTINCT ON 개수 같아야, 새 경고 없어야).
- 스테이징: pre-push smoke, perf-gate CI, 배포 로그에 `cprf`(캐시) 경고 없음, 출고 대시보드·`yield_per` 경로(알림 수신자·정산 내보내기)·하트비트 확인.

## 4. 되돌리기

`requirements.txt` 한 줄(빌드 필요). DB 변경 없음.

## 5. 사용자가 정할 것

1. 이 계획대로 2.0.54 상향 진행 여부.
2. 2.1 상향은 따로(DISTINCT ON 4곳 교체 포함) — 지금은 하지 않는다.

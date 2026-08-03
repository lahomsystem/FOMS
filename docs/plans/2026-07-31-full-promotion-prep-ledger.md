# deploy 전체 승격 준비 — 진행 원장

> 이 파일이 compact 이후의 인계문이다. 재개 시 이것부터 읽는다.
> 관련: 승격 절차 플랜 `docs/plans/2026-07-30-full-deploy-to-production-promotion.md`

## 지금까지 (2026-07-31 완료)

**사고**: ERP 폼 입력이 저장 없이 채널톡으로만 발송돼 DB에 유실. 원인 = `erpRunChannelPush()`가 라이브 DOM에서 텍스트를 조립해 발송하면서 저장을 전혀 호출하지 않음. 운영 서빙 JS로 확증.

**규모(운영 실측)**: 7월 푸시 166건 중 **91건(55%)이 저장 없이 종료**. 6월은 14건 중 11건. 예외가 아니라 일상 패턴. 유실 확증은 4414 1건뿐인데, 이유는 사용자가 채널톡 본문을 붙여줘 대조가 가능했기 때문. **푸시 본문은 서버 어디에도 저장되지 않는다**(`ChannelDeliveryLog.rendered_text_snapshot`은 아무도 안 채우는 죽은 컬럼, 마지막 행 2026-06-18) → 나머지 건은 원리적으로 판정 불가.

**해결(운영 반영 완료)**: PR #34 머지 → production `e766dd25`.
- 3파일 +48 −3, 마이그레이션 0, 롤백 = revert 1분
- 서빙 실물 확인: `/healthz` commit `e766dd25…`, `edit/4414`가 `erp-order-shared.js?v=20260730b` 서빙(기존 `20260722c`에서 범프 → SW cache-first 뚫림), 게이트가 `erpGenerateConversionText()`보다 앞

**deploy에만 있는 것**: `f5c5ceb3`(If-Match 낙관 잠금 + Quest dirty 가드), `31df9343`(failopen inventory), `1b3452a6`(승격 플랜 문서). deploy HEAD = `1b3452a6`.

## 승격 규모 (재조사 불필요)

| 항목 | 값 |
|---|---|
| `origin/production` | `e766dd25` (PR #34 머지 후) |
| `origin/deploy` | `1b3452a6` |
| 커밋 / 파일 | 349 / 829 (+126,059 −44,212) — **PR #34 머지로 약간 줄었을 것, 재측정 필요** |
| 미적용 마이그레이션 | **29개** (`ops_approval_00` ~ `wiz_pending_00`) |
| 신규 테이블 | 39개 / 기존 테이블 추가 컬럼 18개(NOT NULL 4개) |
| 운영 DB | PG **17.10**, 90MB, `orders` 3,606행, 활성 커넥션 1 |
| 운영 사용자 28명 | SALES 8 · CONSTRUCTION 10 · CS 4 · DRAWING 3 · MANAGER/CS 2 · ADMIN 1. **SHIPMENT 팀 없음** |
| production PR CI | `perf-gate` 1개뿐, `required_status_checks: null`(GitHub 미강제, red여도 머지됨) |

---

## ✅ 승격 완료 (2026-08-01 14:12 KST)

**PR #35 머지 → `origin/production` = `0aae8d9f`.** deploy `980810bb` 전체(356커밋·838파일) 반영.

| 검증 항목 | 결과 |
|---|---|
| Railway web 배포 | `693df33d` **SUCCESS** (140초) |
| 서빙 커밋 | `/healthz` = `0aae8d9f` ✅ |
| alembic | `phase_0a_notif_user_states` → **`wiz_pending_00`** (29개 전부 적용) |
| 테이블 수 | 45 → **84** |
| 데이터 무손상 | orders 3,608→3,614(승격 중 신규 주문) · users 28 · order_events 11,044→11,054 · attachments 2,344 |
| `security_principal_versions` | 28행 = users 28 일치 |
| 스모크 11경로 | **전부 200** (dashboard 710ms · as 627ms · construction 582ms) |
| WORKER / FOMS-cron | 둘 다 SUCCESS, 에러 로그 0 |
| 백업 | `/c/tmp/foms-backups/foms-production-pre-promote.dump` (4.1MB, `pg_restore --list` 검증) |

**운영 실물 확인된 이번 세션 수정:**
- T1 시공자 마스터: 시공자 탭 존재 · `capacity` 입력 18개 · `off_dates` 입력 20개 · "이관되었습니다" 문구 제거 · 월력 CSS 링크 정상
- 사고 수정(채널톡 푸시 게이트): `erpRunChannelPush` 본문 내 `isDirty(393) → 확인문구(462) → 저장(635) → 텍스트조립(847)` 순서 정상, If-Match 배선 확인

**승격 시 못 한 것**: WORKER 0 스케일. Railway CLI에 스케일 명령이 없다(`down`은 배포 제거라 비가역 위험). RQ 워커는 잡 단위 실패라 프로세스가 죽지 않는 구조라 진행했고, 결과적으로 에러 0.

## 승격 후 후속 작업 진행 (2026-08-03)

5-에이전트 분석 → 우선순위대로 착수. deploy `ac9a58c3`.

| # | 항목 | 상태 |
|---|---|---|
| ① | RQ 실패 잡 관측 | **DONE** `ac9a58c3` |
| ② | `/erp/history` 301 여분 홉 | **DONE** `b8f31bcb` |
| ③ | CI PG 16 → 17 | **DONE** `b8f31bcb` |
| ④ | construction 렌더 +22ms 분리 실험 | PENDING |

### ① RQ 실패 잡 — 운영에 시체 2,544건 (실측)

`tools/ops/rq_failed_jobs.py` 신규. **운영 Redis 읽기 전용 실조회 결과**:

| 잡 | 건수 | 마지막 실패 | 에러 |
|---|---|---|---|
| `foms.services.jobs.tasks.push_order_to_channeltalk` | 2,213 | 2026-06-18 | ChannelTalk 403 `unauthorizedActionError` (group READ) |
| `services.jobs.tasks.push_order_to_channeltalk` | 331 | 2026-04-20 | `issueToken 오류: token fetch fail from auth` |

**살아있는 실패가 아니다** — 그 함수는 이미 retired(`foms/services/jobs/tasks.py:132`, 계약 테스트 `test_tasks_legacy_push_order_to_channeltalk_drains_without_dispatch`가 고정). 현재 채널 푸시는 RQ가 아니라 `sidefx_outbox`(DB 큐)로 간다. 두 변종은 모듈 경로 리팩터 전후 사본이다.

**단 침묵 위험은 실증됐다**: 시체 2,544건이 Redis에 1년 상주하며 새 실패를 묻는다.

**⚠️ `rq requeue --all`은 절대 쓰면 안 된다** — 퇴역 잡 2,544건을 전부 재실행한다. 그래서 도구는 이름 필터 + dry-run 기본(`--apply` 필요)으로 만들었고 `--all` 위임을 거부했다.

**미결(사용자 승인 필요)**: 운영 Redis에서 이 2,544건을 비울지. `FailedJobRegistry` 정리는 운영 Redis **쓰기**라 승인 없이 안 했다.

### ② `/erp/history` 301 — 진범은 `fragment_path()`

원장 앞선 기록보다 상류였다. `tools/perf/staging_perf_gate.py`의
```python
return f"{primary_path.rstrip('/')}?view=fragment"   # SSOT 의 끝 슬래시를 깎았다
```
SSOT `ERP_PRIMARY_NAV_PATHS`는 `/erp/history/`(슬래시 있음)인데 `rstrip('/')`이 떼서 `/erp/history?view=fragment`를 만들었다. history blueprint만 `url_prefix='/erp/history' + route('/')` 구조라 Flask `strict_slashes`가 301을 냈고, `measure_path`가 `allow_redirects` 기본값으로 따라가 **여분 왕복이 TTFB에 통째로 섞였다**.

나머지 8개 경로는 원래 슬래시가 없어 `rstrip`이 no-op — **history만 걸린 사각**이다. 실사용자는 영향 없다(앱 내부는 전부 `url_for`).

수정 후 SSOT 생성 경로 9개 ↔ 예산 키가 정확히 일치(누락 0·잉여 0). **`ttfb_delta_min_ms` 재시드는 CI 관측 후 별도로** — 심판석은 CI 러너다.

### ③ CI PG 17

PG17 "Migration to Version 17" 비호환 17개 항목을 이 저장소가 쓰는 기능과 전수 대조 → **해당 0건**(`CREATE INDEX CONCURRENTLY`·`gin_trgm_ops`·partial unique index·`DISTINCT ON`·`FOR UPDATE SKIP LOCKED`). `MERGE`/`JSON_TABLE`/generated column/custom trigger 미사용.

**검증**: 로컬 PG 17.9 클러스터에서 `tests/postgres` **659 passed**.

마이너는 floating(메이저만 고정) — 운영 17.10과 패치 레벨이 정확히 같지는 않다.

### ④ construction 렌더 +22ms — **미확정, 내 앞선 "환경 탓" 판단이 반증됨**

A2가 내 가설을 확인해주지 않았다.

| | 7/28 | 현재 스테이징 | 현재 운영 |
|---|---|---|---|
| construction 렌더 min | 16ms | 28.6 | **23.9** |
| ms/KB 단가 | 0.211 | 0.373 | **0.336** |

- **운영도 1.6배다.** 데이터가 더 많은데 스테이징보다 빠르다 → "스테이징 컨테이너 1대만 맛이 갔다"로 설명 안 됨.
- **반증**: `shipment`는 같은 컨테이너에서 안 느려졌다(9~12 → 8.3). 균일 CPU 저하 모델은 ~19ms를 예측한다. "shipment 자체 최적화" 구원 가설도 로컬 A/B에서 old/new 1.30ms 동일로 실패.
- **`render_ms`는 순수 Jinja CPU다** — `render_template()` 호출만 감싸고 창 내부 SQL 0건(`foms/web/construction/dashboard.py:215-239` 직접 확인). DB도 네트워크도 아니다.
- 코드 무죄는 더 강해짐: 독립 A/B에서 construction **0.80→0.70ms**, 출력 **133,646B 완전 동일**.
- 7/28의 16ms는 운 좋은 저점이 아니다 — 3개 런이 `(9,16,13,9,12,1)`을 자릿수까지 재현.

**2026-08-03 내가 직접 재실행한 스테이징-DB A/B** (같은 스테이징 DB·같은 머신, 체크아웃만 `bb09d3fd` ↔ deploy HEAD, 5라운드):

| 경로 | 쿼리 old→new | 렌더 old→new | 바이트 old→new |
|---|---|---|---|
| **construction/dashboard** | 15→15 | **13.5 → 10.3ms** | **555,316 = 555,316 (동일)** |
| production/dashboard | 9→9 | 7.5 → 5.6 | 320,555 (동일) |
| dashboard | 9→9 | 10.3 → 10.1 | 511,028 (동일) |
| as | 5→**6** | 14.0 → 16.9 | 666,831 → 685,636 (+18.8KB) |
| shipment | 5→5 | 1.6 → 2.4 | 45,473 → 45,636 (+163) |

**construction은 출력이 바이트 단위로 동일한데 새 코드가 오히려 빨라졌다.** `as`만 느려졌고 쿼리 +1·바이트 +18.8KB라 AS 타임라인 기능의 정당한 몫이다. A2와 독립적으로 같은 결론 — **코드 무죄 확정**.

**남은 결론**: 환경(컨테이너 실행 성능)이 유일한 잔여 설명이나 **양성 증명은 못 했다**. 같은 내용을 7/28엔 16ms(0.0143 ms/KB), 지금은 28.6ms(0.0256 ms/KB)에 렌더한다.

**미해소 반례**: `shipment`가 같은 컨테이너에서 안 느려졌다. 이 A/B에서 shipment 바이트는 old/new 거의 동일(+163)이라 "content가 줄어 상쇄됐다"는 구원 가설을 이 하네스로는 지지할 수 없다(스테이징 실측 wire는 20,266→18,278로 −10%인데, 그 감소는 코드가 아니라 스테이징 데이터/상태 차이에서 온다).

**최종 판정: 코드 무죄(확정) · 환경(미증명) · shipment 반례(미해소).** 완전 분리는 현 컨테이너에 `bb09d3fd`를 실제 배포해야만 가능하다 — 별도 Railway 서비스 기동이 필요한 큰 작업이라 여기서 멈춘다. **예산은 건드리지 않았다.**

### A3 부수 발견 (별도 트랙)

- **CI에 Redis가 아예 없다** — 버전 갭이 아니라 커버리지 0. 5개 워크플로 전부 redis 서비스 컨테이너 없음. 2026-07-21 Redis 장애로 전 요청 500 난 사고를 재현할 CI가 지금도 없다.
- **`requirements.txt`에 서버 무관 패키지 8줄** — `poetry`·`pyinstaller`·`PyQt5`(3줄)·`pywebview`. 145줄 중 8줄이 운영 이미지에 함께 설치된다. 21개가 `>=` floating이라 CI·스테이징·운영이 다른 버전을 설치할 수 있다(lockfile 없음).
- **PG 레인은 마이그레이션 체인을 검증하지 않는다** — `Base.metadata.create_all`로 스키마를 만든다(첫 마이그레이션이 create-table 없이 `add_column`부터라 빈 DB에서 실행 불가). 승격 때 29개가 돈 건 내가 스테이징에서 실제 왕복을 돌려봤기 때문이지 CI 보장이 아니다.

### A4 설계 결론 (T8)

**"그냥 nullable"은 금지.** 실측: `sorted([None, 3])` → TypeError → before_request **500**. 단독 NULL이면 `[None]`이 truthy라 **STAFF 전원 403 락아웃**. `release_assignment`의 `user_id == user_id`는 SQL NULL 비교라 회수도 불가.

**답**: `CHECK (user_id IS NOT NULL OR NOT active)` — NULL을 released 행에만 허용. 롤백 안전성의 핵심이기도 하다(구 코드가 팀 폴백만 보게 됨).

**핵심 비대칭**: 삭제를 막는 건 `order_create.py:188`이 만드는 SALES `INITIAL_OWNER` 행인데, `assignment=` 지정 정책은 **CONSTRUCTION·DRAWING 둘뿐**이라 SALES 배정은 오늘 어떤 권한 경로도 안 읽는다(write-only).

`assigned_by_user_id`는 읽는 코드 **0건** → `SET NULL` 안전. `FeatureCutoverMarker`는 **거부 유지가 정답**(family PK, 15개 고정, 트리거가 UPDATE·DELETE 둘 다 RAISE).

**이 변경은 일방향**이다 — `downgrade()`가 `pass`일 수밖에 없다(NOT NULL 복구는 정의상 파괴적).

### A5 잔여 결함

- **`str(None)` 유령 휴무일**: 배차는 무사(`shipment_read_model.py:135`가 `'YYYY-MM-DD'`와만 비교 → inert). **UI 휴무일수만 틀리고 클릭으로 못 지운다.** 내 T1 수정은 신규만 막고, 기존 오염은 재저장 때마다 영속(이미 문자열이라 가드 통과). 과거 오염 여부 **미확정** — 확인 쿼리 설계됨(`@>` 멤버십), 미실행.
- **정리 대상**: worktree 4개 삭제 가능(`as-delete-reapply`·`as-map-kakao`·`bugfix/full-system-remediation`·`promote/2026-08-01-full`, 전부 병합·clean). `fomstest`(5433 PG15 사용자 dev 인스턴스 위 빈 DB) — 가드로 Claude Code에선 못 지움. stash 41개는 타 세션 WIP 혼재로 손대지 않음.

---

### 승격 후 후속 (차단 아님)

1. **construction 대시보드 서버 렌더 +22ms** — 7/28 16ms → 8/1 38ms. dTTFB 판정값은 154(예산 147)지만 그중 실제 서버 몫은 +22ms고 나머지 +38은 healthz base가 260→222로 빨라져 생긴 착시다(절대 min 351→376). 코드 A/B에서 기여분 0, wire +399B. **예산 재시드 금지 — 원인 미규명.**
2. **CI PG Lane이 PostgreSQL 16, 운영은 17.10** — 한 세대 낮은 구조적 사각. 이번 FK 건은 공통 동작이라 무영향이었고 로컬 17.9로 교차 검증(659 passed)했다.
3. **T8: 사용자 삭제 FK 근본 수정** — `OrderAssignment.user_id`/`assigned_by_user_id`에 `ON DELETE SET NULL` + nullable화 마이그레이션. 현재는 "삭제 거부"로 동작.
4. `normalize_erp_shipment_workers`의 `str(None)` → `'None'` 결함(읽기 SSOT, 쓰기 측은 차단됨).
5. `/erp/history` trailing-slash 301 여분 홉.

### ⑤ ORM↔마이그레이션 타입 드리프트 3건 ✅ DONE (`typedrift_00`, deploy `b2dc9b83`)

MIGCHAIN-01 왕복 검증이 `create_all` 스키마와 마이그레이션 스키마를 처음 컬럼 단위로 대조하며 드러난 3건. **데이터 문제가 아니라 마이그레이션 작성 실수**다.

| 테이블.컬럼 | models.py | 마이그레이션이 만든 것 | 만든 파일 |
|---|---|---|---|
| `system_setting_receipts.read_receipt_id` | `UUIDColumn`(=`postgresql.UUID`) | `sa.String(36)` | `shipment_reference_00` |
| `system_setting_receipts.response_body` | `JSONColumn`(=`JSONB`) | `sa.JSON()` | `shipment_reference_00` |
| `channel_inbound_worker_heartbeats.metadata_json` | `JSONColumn`(=`JSONB`) | `sa.JSON()` | `channel_inbound_00` |

**의도의 증거**: 같은 역할의 형제 테이블 `order_mutation_receipts`는 `rev_00`에서 `postgresql.UUID` / `postgresql.JSONB`로 **정확히** 만들어져 있다(운영 실측 확인: `uuid` / `jsonb`). 처음부터 uuid·jsonb가 맞았고 위 두 마이그레이션만 빠뜨렸다.

**기존 레인이 못 잡은 이유**: SQLite 레인은 타입 구분이 없고, PG 레인은 `create_all`(= ORM 타입)로 부트스트랩하므로 **양쪽 다 jsonb만 본다.** 마이그레이션을 실제로 돌리는 경로는 predeploy와 MIGCHAIN-01 둘뿐이다.

**영향**: 현재 기능 결함 0 — 두 컬럼 모두 whole-row read/write만 하고 JSONB 전용 연산자(`@>`·`?`·GIN) 사용처가 0건이다. 위험은 앞으로다: models.py가 jsonb라 선언하므로 누군가 jsonb 연산자를 쓰면 **두 레인 모두 green이고 운영에서만 깨진다.**

**비용**: 운영 실측 `system_setting_receipts` 0행(48kB), `channel_inbound_worker_heartbeats` 0행(16kB) → `ALTER TYPE` 재작성 비용 사실상 없음. `read_receipt_id`는 `str(uuid4())`로만 채워져 `::uuid` 캐스트가 항상 성립.

UNIQUE 제약 이름(`uq_system_setting_receipt_read_id` → create_all 기본 이름)도 함께 맞춰 `_KNOWN_INDEX_NAME_DRIFT`도 비웠다. **두 알려진-드리프트 목록 모두 빈 집합** — 새 드리프트가 생기면 즉시 red.

검증: PG 레인 전수 **660 passed**(로컬 PG 17.9 포트 5440), `pre_push_smoke` exit 0, `APP_OK`. **운영 적용은 다음 승격 predeploy 시점**(승격은 사용자 명시 요청 시에만).

### 이 세션에서 배운 하네스 함정 (반복 금지)

- **`ci_watch.py`는 워크플로 1개만 본다.** 저장소에 7개 있다. 그 exit 0을 "CI green"으로 옮겨 적어 PG Lane 3연속 red를 놓쳤다. 판정은 반드시 `gh run list --branch <b>`로 **커밋별 전 워크플로 나열**.
- **SQLite 레인은 FK를 강제하지 않는다.** FK 관련 수정은 PG 레인 없이는 검증 불가. 로컬 PG가 없으면 설치된 바이너리로 `initdb` + `pg_ctl`로 격리 클러스터를 띄울 수 있다(포트 충돌 주의 — 5433에 기존 PG 15가 있었다).
- **`tests/postgres/conftest.py`는 비로컬 호스트를 거부한다**(Railway DSN 차단 가드). 우회하지 말 것.
- **`synchronize_session=False` 대량 UPDATE 뒤 단언은 `expire_all()` 필수.** 안 하면 identity-map의 낡은 값을 검증한다(실측: DB는 NULL인데 객체는 옛 id).
- **`wait_staging_deploy.py` 타임아웃(600s)은 성능 실패가 아니다.** Railway 배포 지연과 레이스.

## 진행 상황 (2026-07-31 갱신)

작업 브랜치: `session/s0731-092912` (worktree `c:\tmp\foms-s-s0731-092912`, base `origin/deploy 1b3452a6`)

| task | 상태 | 비고 |
|---|---|---|
| T1 시공자 마스터 | **DONE** `f0c03ac9` | 범위 축소(아래 정정 1). 미푸시 |
| T2 설계변경 정책 | **DONE** `f0c03ac9` | 2건 수정, 1건은 정상이라 유지(정정 3) |
| T3 출고 설정 권한 | **결재 완료 — 변경 없음** | 관리자 3명 유지(사용자 결정) |
| T4 사용자 삭제 FK | IN PROGRESS | 1줄 아님, 대상 22개(정정 4) |
| T5 롤백 리허설 | **DONE — 롤백 가능 확인** | 스테이징 왕복 성공. "롤백 불가" 서술 폐기 |
| T6 perf-gate 진단 | PENDING | |
| T7 운영 조치 | PENDING | |

### 재개 후 확인된 정정 4건 (원장 원문이 틀렸던 부분)

1. **T1 범위 축소.** `397891a6`(origin/deploy)이 **per-order** 시공자 이름 배열을 이미 복구했다(`foms/services/shipment/writer.py`). 남은 건 **전역 마스터**(`capacity`·`off_dates`)뿐이었고 그것을 `f0c03ac9`가 처리했다. 두 경로를 혼동하지 말 것.
2. **T3는 "매니페스트 1줄"이 아니다.** `SHIPMENT_REFERENCE` policy_id가 매니페스트 `:480`과 [`foms/api/shipment/settings.py:52`](../../foms/api/shipment/settings.py#L52) 두 곳에 핀돼 있다. 또 `teams=("SHIPMENT",)`라도 **ADMIN/MANAGER는 통과**한다 → 운영에서 3명이 편집 가능. "공집합"이 아니라 "STAFF 25명 제외". `tests/postgres/test_shipment_reference.py:72`가 `SALES/CS → 403`을 의도적으로 못 박고 있어 정책을 넓히면 그 테스트를 **의도적으로** 바꿔야 한다. → 기계적 수정이 아니라 결재 사항으로 이동(아래 결재 목록).
3. **T2는 4개 엔드포인트 중 2개만 오배정이었다.** `api_order_request_revision_check`는 본문이 `is_drawing_workbench_participant`를 요구하므로 `DRAWING_ASSIGNED`가 **정상**이다. `api_ack_drawing_order_change`도 정상. 이 둘을 바꾸면 새 회귀를 만든다.
4. **T4는 "1줄"이 아니다.** `models.py`의 `users.id` FK를 전수 조사한 결과 `ondelete` 없고 `user_deletion.py`도 모르는 컬럼이 **22개**다(`SystemSettingReceipt`·`NotificationUserState`·`NotificationEvent`×2·`NotificationPushSubscription`·`SecurityPrincipalVersion`·`OpsApprovalRequest`·`OrderMutationReceipt`·`OrderAssignment`×3·`FeatureCutoverMarker`·`WDCLinkRuntimeState`·`AddressLearningRequest`·`UploadDraft`·`SecuritySigningState`·`AuthRateKeyState`·`ChannelInboundKeyState`·`ChannelCreateFlag`·`InstallationWorker`·`OrderInstallationAssignment`×2). 각각 nullify/행삭제/삭제거부 판정이 필요하다. 브리프: `scratchpad/T4-brief.md`.

---

## 남은 작업

### T1. 시공기사 마스터 편집 경로 복구 ✅ DONE (`f0c03ac9`)

**가장 큰 차단 사유. 유일하게 revert로도 복구 안 되는 손상.**

deploy가 출고 설정의 "시공자" 탭을 삭제하고 "별도 관리 화면으로 이관되었습니다"라고 안내하는데(`templates/shipment/partials/settings_body.html:10`) **이관처가 존재하지 않는다**.

확인된 사실:
- production `settings_body.html`: `off_dates|capacity` 매치 **9건** / deploy: **0건**
- `foms/services/shipment_reference.py:46` `_ALLOWED_FIELDS = {construction_time, drawing_managers, measurement_managers, site_extra}` → `construction_workers` 포함 시 **400**(`:284`)
- 같은 파일 `:19` 주석: "이미 저장된 `construction_workers` 값은 **보존**한다(출고 대시보드가 계속 읽는다)" — 읽기만 살리고 쓰기를 없앤 뒤 이관처를 안 만든 것이 설계 의도상 확정
- `models.py` `InstallationWorker` 컬럼: `id·external_worker_id·display_name·phone·is_active·user_id·created_at·updated_at·deactivated_at` → **`capacity` 없음, `off_dates` 없음**
- `foms/services/crew/workers.py:11` 자백: "route/endpoint 실배선은 하류(SHIPMENT-REFERENCE-01) — 여기선 라이브러리만". 그런데 SHIPMENT-REFERENCE-01이 `construction_workers`를 소관 밖으로 뺐다.
- crew 관리 라우트/템플릿 grep 결과 **0개**

**읽기 경로는 살아있다**: `load_erp_shipment_settings()`(`foms/services/erp_shipment_settings.py:202`)가 `SystemSetting`에서 로드 → `foms/web/shipment/dashboard.py:400,675`가 `normalize_erp_shipment_workers(settings.get('construction_workers', []))`로 자수 계산 → `templates/shipment/partials/dashboard_main.html:291,322,328`이 `자수 {{ remaining_capacity }}` · 휴무 렌더.

**증상**: 기존 값이 남아 화면은 정상으로 보이고 **숫자만 얼어붙는다**. 기사가 휴가를 내도 `off_dates`에 넣을 수 없고 배차는 그를 계속 가용으로 계산 → 휴무 기사에게 배차가 나가 현장 펑크. 조용히 틀려서 발견까지 몇 주. ADMIN도 못 고침(권한이 아니라 경로 부재).

**권고 수정(최소)**: CREW-00 신규 화면을 만들지 말고, 삭제된 시공자 탭 + `construction_workers` 저장 경로를 되살린다.
- `_ALLOWED_FIELDS`에 `construction_workers` 복귀 + 검증 로직(다른 4종과 동일 패턴)
- `settings_body.html`에 시공자 탭 섹션 복원(production 버전 참조: `git show origin/production:templates/shipment/partials/settings_body.html`)
- 저장 payload 배선 복원

**완료 기준**: 출고 설정에서 기사 `capacity`·`off_dates` 편집 후 저장 → 200 → 출고 대시보드 자수/휴무에 반영. `python -c "import app; print('APP_OK')"` + 관련 테스트 green.

**실제 구현(`f0c03ac9`)**:
- `shipment_reference.py`: `_ALLOWED_FIELDS`에 `construction_workers` 복귀 + `_validate_construction_workers`/`_coerce_worker_capacity`/`_normalize_off_dates`. 저장 형태는 읽기 SSOT가 그대로 소비하는 `{name, capacity, off_dates}` dict.
- **key 부재 = 보존, 삭제 = 빈 리스트 명시.** 부분 저장 클라이언트가 마스터를 통째로 지우는 것을 서버·클라이언트 양쪽에서 차단.
- `settings_body.html`: 기본/시공자 2탭 + 휴무 월력 복원. production의 `document` 전역 `shown.bs.tab` 리스너는 **이식하지 않았다**(fragment 재실행마다 누적 = 가드 G4 위반). 즉시 초기화 + `li.dataset.calInitialized` 가드로 대체.
- 인라인 `<style>`은 `static/css/components/foms-shipment-worker-calendar.css`로 분리(`?v=20260731a` 핀).
- 계약 테스트 11건 추가(읽기-쓰기 왕복 무손실 포함). `test_schema_rejects_construction_workers_400`은 삭제된 동작을 지키던 테스트라 제거.
- 부수 발견: `str(None).strip()` → `'None'`이 휴무일로 저장되던 결함. 쓰기 측에서 차단했다. **읽기 SSOT `normalize_erp_shipment_workers`에는 같은 결함이 남아 있다**(기존 데이터에 `'None'` 있으면 여전히 통과) — 후속 후보.
- 미검증: PG 레인 테스트 6건 skip(로컬 PostgreSQL 없음), 브라우저 실동작.

**검증 실행**: `pytest -k "policy or manifest or revision or shipment_reference"` → `259 passed, 52 skipped`. `import app` → `APP_OK`.

### T2. 설계변경 요청 매니페스트 오배정 수정 ✅ DONE (`f0c03ac9`)

**실제 수정**: `api_order_request_revision`·`api_order_cancel_revision_request` 2건만 `ERP_EDIT`로. `api_order_request_revision_check`(본문이 `is_drawing_workbench_participant` 요구)와 `api_ack_drawing_order_change`는 `DRAWING_ASSIGNED`가 정상이라 유지.

아래는 원래 분석(보존):

정책과 데코레이터가 **서로의 통과 집합을 배타적으로 만든다** → 실질 통과자 **ADMIN 1명뿐**.

| 대상 | 정책 `DRAWING_ASSIGNED`(teams=DRAWING) | `@erp_edit_required`(CS/SALES) | 결과 |
|---|---|---|---|
| CS/SALES 12명 | **403** | — | 차단 |
| DRAWING 3명 | 통과 | **403** | 차단 |
| ADMIN 1명 | 통과 | 통과 | 유일 통과 |

근거: `docs/harness/foms_order_mutation_policy_manifest.json:433` = `DRAWING_ASSIGNED` / `foms/api/drawing/erp_orders_revision.py:38` = `@erp_edit_required` / `foms/services/orders/order_mutation_policy.py:139`.
코드가 자백: `foms/web/drawing/workbench.py:851` — `can_request_revision = is_admin or (can_sales_domain and not is_drawing_team)` = UI는 "도면팀에 안 보임"으로 렌더.

**업무 영향**: 도면 전달분은 반드시 "수령확정" 또는 "수정요청"으로 빠져나가야 한다(`templates/orders/partials/dashboard_grid.html:248`). 수정요청이 막히면 고객 변경 건이 "확정 대기"에 고이고, 영업의 유일한 대안은 잘못된 도면을 확정해 생산으로 넘기는 것 — 더 나쁘다.

**수정**: 매니페스트 `DRAWING_ASSIGNED` → `ERP_EDIT` (1줄). `api_order_cancel_revision_request`(`:428`)도 동일 — 현재 정책 하에선 통과자 0명이다(`erp_orders_revision.py:302`가 `is_drawing_team` 명시 배제).

### T3. 출고 설정 정책 ✅ 결재 완료 — 변경 없음 (2026-07-31)

**사용자 결정: 관리자 3명(ADMIN/MANAGER) 유지.** CS/SALES 25명으로 넓히지 않는다. 코드 변경 0. T1이 되살린 시공자 마스터(자수·휴무) 편집도 관리자 전용으로 운영한다. 승격 차단 목록에서 제외.

후속 관찰 항목(차단 아님): 현장 요청이 관리자를 거쳐야 하므로 휴무 반영이 늦어질 수 있다. 승격 후 실사용 빈도를 보고 재검토.

> **정정**: policy_id가 매니페스트 `:480`과 `foms/api/shipment/settings.py:52` **두 곳**에 핀돼 있어 1줄이 아니다. 그리고 ADMIN/MANAGER 3명은 통과하므로 기능이 죽은 건 아니다 — STAFF 25명만 제외. `tests/postgres/test_shipment_reference.py:72`가 `SALES/CS → 403`을 못 박고 있어 정책을 넓히면 그 테스트를 의도적으로 수정해야 한다. **사업 판단 필요** → 아래 결재 목록으로 이동.

아래는 원래 분석(보존):

`SHIPMENT_REFERENCE = teams=("SHIPMENT",)`(`order_mutation_policy.py:147`)인데 운영에 SHIPMENT 팀원 0명 → STAFF 통과 집합이 공집합.

**수정**: 매니페스트에서 `SHIPMENT_REFERENCE` → `SHIPMENT_EDIT`(이미 `("CS","SALES","SHIPMENT")`, `:145`) 1줄.

부수 문제(후속 가능): `templates/shipment/partials/settings_body.html`이 `can_edit_erp` 변수를 받고도 쓰지 않아(grep 0건) CS/SALES에게 편집 폼과 저장 버튼이 그대로 보인다 → "눌렀는데 안 됨" = 이번 사고와 같은 형태의 경험.

### T4. 사용자 삭제 FK ✅ 구현 완료 — **단, 결재 필요한 동작 변경 1건 포함**

`users.id` FK 22개를 전수 판정했다.

- **nullify 14건**: `NotificationEvent`×2, `OpsApprovalRequest.approved_by`, `OrderAssignment.released_by`, `AddressLearningRequest`, `UploadDraft`, singleton 설정 5종(`WDCLinkRuntimeState`·`SecuritySigningState`·`AuthRateKeyState`·`ChannelInboundKeyState`·`ChannelCreateFlag`), `InstallationWorker.user_id`, `OrderInstallationAssignment`×2
- **행 삭제 4건**: `NotificationPushSubscription`(개인 기기 구독), `SecurityPrincipalVersion`(PK·사용자당 1행), `SystemSettingReceipt`/`OrderMutationReceipt`(`expires_at`+retention purge로 소멸 설계된 일시 행)
- **삭제 거부 3건**: `FeatureCutoverMarker.approved_by_admin_user_id`(PG 트리거가 UPDATE/DELETE 자체를 RAISE), `OrderAssignment.user_id`/`assigned_by_user_id`(NOT NULL + 권한 판정 정본)

표에 없던 추가 발견: `notification_events.user_state_id` → `notification_user_states.id` FK에 `ON DELETE`가 없어 상태 행을 먼저 지우면 감사 로그가 FK 위반을 낸다. 전용 헬퍼가 감사 행의 링크만 NULL로 끊고 상태 행을 삭제한다.

**⚠️ 결재 필요 — 사용자 삭제가 사실상 불가능해진다**: `foms/services/orders/order_create.py:188`이 **주문 생성 때마다** `OrderAssignment(user_id=owner, assigned_by_user_id=actor)`를 만든다. `user_id`·`assigned_by_user_id` 모두 `nullable=False`라 nullify 불가, 행 삭제는 주문 소유권/배정 이력을 조용히 없앤다 → 구현은 **거부**를 택했다(되돌릴 수 있고 손실이 없는 쪽).

결과: 승격 후 **주문을 만들거나 배정받은 사용자는 삭제 불가**, "계정 비활성화를 사용하세요" 안내. 운영에서 오늘은 삭제가 되므로 **명백한 동작 변경**이다. 기존 3,606건은 `assignment_backfill.py`가 CLI 전용이라 자동 백필되지 않지만, 승격 후 신규 주문부터 즉시 적용된다.

선택지:
- (a) **거부 유지** — 현재 구현. 감사·권한 이력 무손실. 잘못 만든 계정도 주문 1건 만들었으면 삭제 불가.
- (b) **행 삭제로 전환** — `_BLOCKING_USER_REFERENCE_FIELDS`에서 `_DELETE_USER_REFERENCE_FIELDS`로 2줄 이동. 삭제는 되지만 배정 이력이 사라진다.
- (c) **근본 수정** — 마이그레이션으로 `assigned_by_user_id`/`user_id`에 `ON DELETE SET NULL` + nullable화. 별건 작업.

**미검증**: `tests/postgres/test_user_deletion_fk.py` 3건 **SKIP**(로컬 `FOMS_TEST_DATABASE_URL` 없음). 실 FK 강제 검증은 CI PG 레인에서만 확인된다. sqlite 레인은 FK pragma가 없어 IntegrityError 자체는 재현 못 하고 정리 결과만 검증한다.

**red 검증됨**: 구현 2파일을 되돌리면 신규 통합 테스트 3건이 실제로 빨강.

아래는 원래 계획(보존):

`ops_approval_00:37`이 `security_principal_versions.user_id`를 `ON DELETE` 없이 FK로 걸고 전 사용자를 seed. `foms/services/user_deletion.py`는 이 테이블을 참조하지 않음(0건, production·deploy byte-identical) → 삭제 시 IntegrityError.

**수정**: `user_deletion.py:42` `_DELETE_USER_REFERENCE_FIELDS`에 `(SecurityPrincipalVersion, "user_id")` 추가. 신규 receipt/assignment 테이블도 같이 검토.

### T5. 롤백 레시피 리허설 ✅ DONE — **DB 롤백 가능 확인** (2026-07-31)

스테이징(FOMS-DEV, `maglev.proxy.rlwy.net:24958`)에서 실제 왕복 실행. 사용자 승인 후 진행.

| 단계 | 명령 | 결과 |
|---|---|---|
| 사전 | `alembic current` | `wiz_pending_00 (head)`, 테이블 **84개** |
| 다운 | `alembic downgrade phase_0a_notif_user_states` | **EXIT=0**, 29개 전부 역방향 통과 |
| 확인 | `alembic current` | `phase_0a_notif_user_states`, 테이블 **45개** |
| 복원 | `alembic upgrade head` | **EXIT=0** |
| 검증 | 테이블 목록 diff | **IDENTICAL** (84개), `alembic current` = `wiz_pending_00 (head)` |
| 앱 | `GET lahom-dev/healthz` | `200`, `{"commit":"1b3452a6…","status":"ok"}` |

**결론: 원장·플랜의 "롤백 불가" 서술은 폐기한다. DB 롤백은 실동작한다.** `downgrade(): pass`(startup_schema_00)도 체인을 막지 않았다.

**단, 롤백에는 비용이 있다 — 신규 39개 테이블의 데이터가 전부 소멸한다.** downgrade가 drop한 테이블(84→45): `order_assignments`·`order_mutation_receipts`·`order_as_cycles`·`production_runs`·`installation_workers`·`drawing_revisions`·`upload_tickets`·`channel_webhook_*`·`ops_approval_*`·`security_principal_versions` 등. `orders`(3,409행)·`users`(30행) 등 기존 테이블은 무손상. 승격 후 이 테이블들에 쌓인 운영 데이터는 롤백 시 **복구 불가**다 → 롤백 판단이 늦을수록 손실이 커진다.

**플랜 롤백 절차의 진짜 결함(정정)**: 원장이 지목한 `git checkout HEAD -- migrations/ models.py` 누락은 증상이고, 근본은 **순서**다. 코드만 되돌려 배포하면 DB는 `wiz_pending_00`인데 스크립트 디렉터리엔 그 리비전이 없어 alembic이 `Can't locate revision`으로 죽는다. 올바른 순서:

1. **먼저 DB를 내린다** — `alembic downgrade phase_0a_notif_user_states` (운영 DSN, 수동 실행)
2. **그 다음 코드 revert 배포** — `git revert -m 1 <머지SHA>`. 되돌린 트리의 alembic head가 `phase_0a_notif_user_states`이므로 `predeploy.sh`의 `alembic upgrade head`는 no-op으로 통과한다. `git checkout HEAD -- migrations/` 같은 우회는 불필요하다.
3. WORKER 재기동, `/healthz` commit 확인

리허설 로그: `scratchpad/rwdev/downgrade.log`·`upgrade.log` (세션 임시 — 필요하면 승격 전에 플랜 문서로 옮길 것).

**미검증**: 39개 테이블에 리허설 **전** 데이터가 있었는지 기록하지 않았다(사전 행수 미수집). 운영 롤백 시 손실 규모를 정량화하려면 승격 직전에 운영 기준 행수를 따로 떠야 한다.

아래는 원래 계획(보존):

플랜의 롤백 절차에 `git checkout HEAD -- migrations/ models.py`가 **빠져 있다**. 그대로 실행하면 29개 마이그레이션 파일이 트리에서 사라지고 alembic이 `wiz_pending_00`을 못 찾아 `predeploy.sh`(`set -e`)가 죽는다 → **롤백 배포가 라이브되지 않고 이후 모든 배포가 같은 이유로 실패한다.**

**할 것**: 스테이징에서 end-to-end 1회 리허설.
1. `git revert -m 1 <머지SHA> --no-commit && git checkout HEAD -- migrations/ models.py`
2. predeploy green + 앱 부팅 확인
3. **같은 리허설에서 `alembic downgrade phase_0a_notif_user_states` 실제 실행** — pending 29개 중 28개가 실제 `op.*` downgrade를 가지고 `startup_schema_00`의 `pass`는 성공 통과하므로 **동작할 가능성이 높다(미검증)**. 성공하면 DB 롤백이 살아나 승격 리스크가 급감한다. 이 15분이 최고 수익률.

### T6. perf-gate 계측 진단 (PENDING, 별도 트랙)

블로킹 실행 시 **9개 경로 전부 FAIL**. 그런데 wire가 20,980~21,023으로 균일하고 raw가 전부 ~91,390 — 예산이 9K~97K로 10배 다른 대시보드가 같은 크기를 낼 수 없다. ETag 누락 + 조건부 304 실패 동반. **성능 회귀가 아니라 계측기 고장으로 판단.**

deploy push 런은 `--advisory`라 항상 exit 0이어서 가려져 있었다(`perf-gate.yml:53-59`). 블로킹은 PR/dispatch에서만.

**주의**: 예산 재시드로 초록을 만드는 건 정책 위반(회귀 은닉). 근본 진단 먼저. `required_status_checks: null`이라 승격을 실제로 막지는 않는다.

### T7. 운영 조치 (PENDING)

- **주문 4414 복구**: 채널톡 본문 기준 **항목견적 1,828,560 / 할인 11,060 / 주소 `(공실)`** 재입력. 자동 복구 경로 없음.
- **사용자 공지**: 사고·사과를 **먼저**, "푸시가 1~2초 느려지는 건 정상 — 그 시간이 입력을 지키는 시간"을 명시. 설명 없는 지연은 버그로 신고되고, 신고가 반복되면 사용자가 신고를 그만둔다.
- 승격 시: **WORKER 0 스케일**(`predeploy.sh:17`이 `USE_RQ_WORKER=1`에서 마이그레이션 스킵 → 신 코드 + 구 스키마 창), Railway 스냅샷, 금요일 금지.

---

## 결재 결과 (2026-07-31 — 8건 전부 확정)

| 안건 | 결정 | 후속 작업 |
|---|---|---|
| 출고 기준목록 편집 권한 (T3) | **관리자 3명 유지** | 없음 (코드 변경 0) |
| 사용자 삭제 FK (T4) | **나중에 제대로 고치기** — 지금은 거부 유지, 다음에 DB 구조 수정 | **T8**(백로그): 마이그레이션으로 `OrderAssignment.user_id`/`assigned_by_user_id`에 `ON DELETE SET NULL` + nullable화. 승격 차단 아님 |
| WDC 계산기 마스터 권한 | **잠그지 않는다 — 운영 현행(로그인한 누구나) 유지** | **W1**: 매니페스트 wdcalculator 12건 `MASTER_MUTATION` → `WDC_CALCULATE`(`teams="*", viewer=True`). `notifications.api_notifications_delete_all`은 그대로 |
| 폼 저장 암묵 단계전이 제거 (`e8293513`) | **새 방식 유지, 공지 없음** | 없음 |
| AS 대시보드 autosave 퇴역 (`be6c2a19`) | **새 방식 유지, 단 저장 버튼 가시성 확인 후 적용** | **W2**: 버튼 존재/가시/dirty표시 3판정 후 필요시 최소 수정. 자동저장 복구 금지 |
| 주문 4414 복구 | **복구 안 함** | 없음 |
| 사고 공지 | **공지 안 함** | 없음 |
| 승격 방식 | **남은 준비 끝내고 349커밋 한 번에** | W1·W2·W3 완료 후 재확인 |
| perf-gate (T6) | **진단한다** (예산 재시드 금지) | **W3**: 9경로 동일 응답의 정체 규명 |

## 승격 전 반드시 결재받을 것 (사업 판단) — ✅ 전부 결재 완료, 아래는 근거 기록

- **출고 기준목록 편집 권한 (T3)**: 시공시간·도면담당자·실측담당자·현장주소·**시공자 마스터**를 누가 편집하는가. 현재 `SHIPMENT_REFERENCE = teams=("SHIPMENT",)`인데 운영에 SHIPMENT 팀원 0명 → **ADMIN/MANAGER 3명 전용**. 넓히면 CS/SALES 25명. 넓히려면 policy 정의 + `settings.py:52` + 매니페스트 + `test_shipment_reference.py:72` 4곳을 함께 바꿔야 한다. **T1이 시공자 마스터 편집을 되살렸으므로 이 결정이 곧 "누가 기사 자수·휴무를 관리하느냐"다.**
- **WDC 마스터 13종**: 오늘 `@login_required`만이라 **VIEWER 포함 로그인한 누구나 삭제 가능**. 승격 후 ADMIN·MANAGER 3명으로 제한(`MASTER_MUTATION` teams=()). 방향은 옳으나 STAFF 25명이 막힌다. 편집 진입점은 `/wdcalculator/product-settings` 한 곳뿐이고 주문 폼은 GET만 하므로 빈도는 낮을 것으로 추정(운영 확인: `SELECT updated_at FROM wdcalculator_product_settings;` — 6개월 넘었으면 논쟁 종료). **권고: 정책 유지 + 페이지에 `role_required(["ADMIN","MANAGER"])` 1줄로 "안 보임" 처리.** "보이는데 눌러도 안 됨"이 훨씬 비싸다.
- **quest 승인 권한 강화**(`2391174c`): `can_edit_erp` 폴백 제거, actor 팀이 현 단계 요구 팀과 불일치하면 403. 4번째 권한 회귀 후보인데 아직 영향 범위 미측정.
- **폼 저장의 암묵 단계전이 제거**(`e8293513`): 저장해도 단계가 자동으로 안 넘어간다. 28명 전원의 매일 습관이 바뀌고, **이번 사고 직후라 "또 저장이 안 됐다"로 읽힌다.** 공지 필수.
- **AS 대시보드 autosave 퇴역**(`be6c2a19`): 입력 유실 사고 직후에 자동저장을 없애는 타이밍. 명시 저장이 눈에 띄는지 확인 필요.

---

## 함정 (같은 실수 반복 금지)

- **perf-gate "success"를 green으로 읽지 마라.** deploy push 런은 `--advisory`라 측정이 FAIL이어도 exit 0이다. 실제 판정은 `gh workflow run perf-gate.yml --ref deploy` 후 확인.
- **`alembic history -r A:head`의 줄 수 = pending 아니다.** 시작 리비전 자신이 포함된다. pending은 29개.
- **`downgrade(): pass`는 롤백을 막지 않는다.** alembic에서 성공 반환하고 리비전을 내린다.
- **`CONSTRUCTION_DATE_CHANGED {"from":""}`는 유실 지문이 아니다.** 전체 1,020건(시공일)·1,719건(실측일)에서 나오는 정상 워크플로다. 4414가 확증인 근거는 푸시 본문과 DB의 **산술 모순**(항목견적 1,828,560 / 출고가 1,817,500 → 할인 11,060 필요, DB는 discount 0).
- **공유 워킹트리다.** 타 세션이 상시 커밋 중. 커밋은 자기 파일만 `git add`, push는 `python tools/harness/push_own_session_commits.py --shas <SHA>`.
- **pre_push_smoke가 타 세션 미추적 파일 때문에 실패할 수 있다.** 깨끗한 worktree(`origin/deploy` + 자기 커밋)에서 재실행해 증명할 것.
- **`policy_can` UI 은닉이 `FINANCE_MUTATION` 하나에만 배선돼 있다.** 나머지 20여 개 정책은 UI가 열려 있어 모든 권한 회귀가 "보이는데 눌러도 안 됨"으로 나타난다.

## 재개 방법

1. 이 파일 + `docs/AI_STATUS.md` 상단 40줄 읽기
2. `git fetch origin deploy production` 후 규모 재측정(PR #34 머지로 바뀌었다)
3. T1부터 착수. T2·T3·T4는 각 1줄이라 T1과 함께 한 브랜치로 묶어도 된다.
4. 승격 절차 자체는 `docs/plans/2026-07-30-full-deploy-to-production-promotion.md` (단, 그 문서의 리스크 2 "롤백 불가" 서술은 이 원장 T5 기준으로 정정 필요)

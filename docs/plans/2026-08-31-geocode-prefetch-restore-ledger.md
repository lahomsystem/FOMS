# 지오코딩 사전변환 복원 — 진행 원장 (2026-08-31)

## 한 줄 요약

2026-07-27 커밋 4개가 주문 생성·주소수정의 지오코딩 예약을 살아있는 RQ 큐에서 **소비자 없는 SIDEFX outbox**로 옮겼고, 그 소비자(SIDEFX 워커)는 운영에 배포된 적이 없다. 그래서 신규 주문은 좌표 없이 생성되고, 사용자가 지도를 여는 순간에야 한 건씩(건당 약 2.9초) 변환된다.

---

## 1. 증상 (사용자 보고, 2026-08-31)

> `https://lahom-production.up.railway.app/map_view?date=2026-09-01&status=ALL&dashboard=measurement&q=`
> 지도 변환이 너무 오래 걸린다. 예전에는 열자마자 이미 변환이 돼 있었는데, 지금은 지도를 열어야 변환을 시작하고 하나씩 너무 느리다. 어떤 주문은 이미 변환이 돼 있고 어떤 건 그때 변환을 시작한다.

---

## 2. 근본 원인

### 2.1 회귀 커밋 (전부 `production`·`deploy` 양쪽에 존재)

| SHA | 날짜 | 제목 | 사라진 것 |
|---|---|---|---|
| `56c9ec33` | 2026-07-27 | ORDER-CREATE-01: canonical Order 생성자 | `/add` 두 어댑터의 `enqueue_geocode_order_address` 2곳 |
| `d537d843` | 2026-07-27 | DATA-MEASUREMENT-01: 지오코드 outbox | `update_address`·실측 필드 저장의 postcommit RQ enqueue + 동기 폴백 |
| `eac1b0cd` | 2026-07-27 | ORDER-COPY-01: 주문 복사 fresh identity | 주문 복사 경로의 postcommit 지오코드 폴백 |
| `f077fdbb` | 2026-07-27 | DRAFT-LIFECYCLE-01: ERP draft 생명주기 | 마법사 finalize → `create_order` 경유(outbox 예약만) |

제거 자체는 의도적이었다 — `docs/harness/foms_bugfix_progress_ledger.md:230,236,250` 에 "postcommit geocode 폴백 제거(write path=order_geocode_outbox enqueue GEOCODE SIDEFX)"로 기록돼 있다. 문제는 **소비자 배포가 후속 패킷으로 미뤄진 채 끝나지 않은 것**이다.

### 2.2 소비자 부재 — 2중 결손

1. **서비스 미등록**: `railway-domain-sidefx.toml` 은 존재하지만 Railway 서비스로 등록된 적이 없다. 운영 서비스 목록 = `Redis / web / WORKER / FOMS-cron / Postgres`.
   - `docs/plans/2026-07-30-full-deploy-to-production-promotion.md:517` — Step 2 워커 등록 체크박스가 `- [ ]` 미완료
   - `docs/specs/2026-08-13-naver-order-ingest_SPEC.md:146-150` — "production에 SIDEFX 서비스가 없다… 예약된 outbox 행이 소비되지 않고 쌓인다"를 이미 명시
   - `docs/plans/2026-08-13-naver-order-ingest-ledger.md:29-31` — 같은 내용을 "절대 지킬 함정"으로 등재
2. **핸들러 미등록**: `tools/ops/run_domain_side_effect_outbox.py:192` 가 등록하는 핸들러는 `STORAGE_DELETE` 하나뿐. `register_handler("GEOCODE", ...)` 는 저장소 전체에 0건. 미등록 effect_type 은 `foms/services/sidefx_worker.py:130-133` 에서 `NoHandlerError` → 재시도 10회 → `DEAD`.

즉 **서비스를 지금 켜도 GEOCODE 는 처리되지 않는다.**

---

## 3. 운영 DB 실측 증거 (2026-08-31, 읽기 전용 조회)

```
side_effect_worker_heartbeats            : 0행                 ← 워커가 한 번도 돈 적 없음
domain_side_effect_outbox (전 행 PENDING, attempts=0)
    CHANNEL_PUSH_RECORDED 1087 / STORAGE_DELETE 418 / STAGE_NOTIFICATION 110
    GEOCODE 83 / SHARE_ALIMTALK 1        (최초 2026-08-03 ~ 최종 2026-08-31)
orders.geocode_status (미삭제)           : success 3670 / NULL 81 / failed 37
생성→지오코딩 10초 이내 처리             : 2026-08 이후 0건 (2026-06~07 332건)
마지막 즉시 변환                          : 주문 4544, 2026-07-27 08:21:42 UTC
```

`GEOCODE 83` 과 `geocode_status NULL 81` 이 대응한다.

### 3.1 증상 재구성 (질문 URL 그대로)

`measurement_date = 2026-09-01` 실측 15건 중 **9건이 2026-08-31 01:38:22 → 01:38:48 UTC 사이 26초 동안 한 건씩** 변환됐다. 건당 2.9초. 나머지 6건은 이전 지도 열람에서 이미 채워진 상태였다. 이것이 "어떤 건 이미 돼 있고 어떤 건 그때 시작한다"의 정체다.

### 3.2 경로별 갈림 (같은 주문도 어느 화면에서 손댔느냐로 결과가 다르다)

| 경로 | 큐 | 결과 |
|---|---|---|
| ERP 주문 저장(structured PUT) 주소변경 — `foms/api/erp_orders_structured.py:1262` | RQ (살아있음) | 미리 변환됨 |
| 구 주문 수정 폼 — `foms/web/orders/edit.py:283` | RQ | 미리 변환됨 |
| 주문 생성 전부(마법사·엑셀·복사·채널·폼) — `foms/services/orders/order_create.py:203-207` | outbox (죽음) | 지도 열 때 변환 |
| 지도 화면 주소수정 — `foms/api/erp_map.py:794` | outbox (죽음) + `pending` 마킹 | **영구 고착** |
| 실측 대시보드 인라인 주소수정 — `foms/api/measurement/routes.py:428` | outbox (죽음) + `pending` 마킹 | **영구 고착** |

영구 고착이 생기는 이유: 재큐 술어가 `pending` 을 건너뛴다(`foms/api/measurement/map.py:45` 는 `!= 'pending'`, `foms/api/erp_map.py:281-286` 은 `not stored_geocode_status`). 백필 CLI 2종도 `pending` 을 대상에서 제외한다. 2026-08-31 시점 운영에는 `pending` 잔존 0건이지만 구조적 위험은 남아 있다.

---

## 4. 체감 지연 증폭기 3종

1. **프론트 전체 재로딩** — `templates/measurement/map_view.html:1901-1905`. pending 1건이 풀릴 때마다 부분 갱신이 아니라 `loadMap()` 전체 재실행 → `showLoading()` 으로 지도를 가리고, 재fetch·전체 재렌더·`setBounds` 로 뷰포트까지 리셋. 게다가 `applyOrdersAndPoll()` 이 `geocodePollRetries = 1` 로 되돌려(`:1973`) 백오프가 항상 1.5초 첫 칸으로 회귀. 결과: **핀 1개 = 깜빡임 1회 + 시점 리셋 1회**.
2. **워커 동시성 1** — `rq worker default` 단일 프로세스, 완전 직렬. 건당 최대 6전략 × (주소 API + 키워드 API) = 최대 12회 카카오 호출, 각 timeout 10초(`foms/services/common/address_converter.py:96-101,310-346`).
3. **failed 매번 재큐** — `foms/api/measurement/map.py:45` 가드가 `!= 'pending'` 뿐이라 `failed` 37건이 지도를 열 때마다 다시 큐에 들어가 워커를 점유하고 진짜 pending 을 뒤로 민다.

클라이언트 폴링 예산은 1500/3000/6000/12000/20000ms = 누계 42.5초(`map_view.html:1563-1570`). 미변환이 15건을 넘으면 `일부 주소가 변환되지 않았습니다` 배너로 끝난다.

---

## 5. 판정 루프 (red-capable)

```
python <scratchpad>/geocode_red.py
```
RED 조건 = ① SIDEFX heartbeat 0행 ② GEOCODE outbox PENDING > 0 ③ 좌표 없는 주문 > 0 ④ 최근 14일 즉시(10초내) 변환 0건.

**2026-08-31 실행 결과: `VERDICT: RED` (exit 1)** — heartbeat 0 / GEOCODE PENDING 81 / 좌표 없는 주문 117 / 최근 14일 즉시 변환 0.

수정 후 이 명령이 GREEN(exit 0)이 되어야 완료다.

---

## 6. 작업 목록

| # | 작업 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | 좌표 스윕 루프 (`scripts/maintenance/run_geocode_sweep.py` + `start.sh` 배선) — 새 Railway 서비스 없이 WORKER 컨테이너 재사용 | `import app` APP_OK + 신규 테스트 통과 + `--once` 로컬 실행 정상 | **DONE** |
| T2 | 프론트 부분 갱신 (`templates/measurement/map_view.html` 폴링 분기) | 기존 map 계약 테스트 2종 무회귀 + 신규 계약 테스트 통과 | **DONE** |
| T3 | GEOCODE 핸들러 등록 + measurement failed 재큐 백오프 | SIDEFX 테스트 + domains 지도 테스트 통과 | **DONE** |
| T4 | 밀린 121건 소진 | 좌표 없는 주문 0건 | T1 배포로 자동 해소(수동 백필 선택) |
| T5 | SIDEFX 워커 서비스 Railway 등록 (사용자 결정 필요 — §7) | heartbeat 행 생성 + outbox PENDING 소진 | BLOCKED (사용자 승인) |
| T6 | `docs/AI_STATUS.md` 갱신 | 상단 40줄에 현재 상태 반영 | **DONE** |

T1~T3 는 서로 파일이 겹치지 않아 병렬 진행한다. T4 는 T1 의 스윕 루프가 배포되면 자동으로 소진되므로 별도 실행은 선택 사항이다.

### T6 완료 기록 (2026-08-31)

`docs/AI_STATUS.md` 진행 중 섹션에 1줄 등재. 상단 40줄 예산이 이미 3993/4000 으로 가득 차 있어 신규 항목 자리가 없었다 — hygiene 계약(`tests/harness/test_hook_log_hygiene.py::test_ai_status_head_budget`)이 요구하는 대로 압축했다: `> 최신:` 줄의 상세를 AI_CHANGELOG 로 넘기고, 2026-08-10 ROUTE-02 줄을 줄였다(그 줄의 "잔여=좌표 백필"은 T1 스윕이 대체하므로 함께 정리). 최종 3980자, 계약 `15 passed`.

**주의: 이 파일은 다중 세션 공유 hot 파일이다.** 다음 세션이 항목을 추가하려면 또 예산 초과가 난다 — 낡은 완료 항목을 `## 기록 보관`으로 내리는 정리가 곧 필요하다.

### T3 완료 기록 (2026-08-31)

- **판정·저장 SSOT 추출**: `foms/services/geocode_helpers.py` 에 `apply_geocode_to_order(order, *, converter=None, now=None) -> str` 신설. 기존 RQ 태스크의 판정 순서를 그대로 옮겼다(주소 없음 → `failed` 기록 / `address_hash` 일치+좌표 존재 → skip / 변환 → success·failed). 반환 상수 4종.
  - `foms/services/jobs/tasks.py:65` 는 이제 세션 소유만 한다(41줄 삭제). `db_session.remove()` 는 RQ 쪽에만 남아 SIDEFX handler 계약과 충돌하지 않는다.
  - `geocoded_at` 기록 시각을 `datetime.datetime.now()` → `now_utc_naive()` 로 교정(naive=UTC 규약). 새 백오프가 같은 시간축으로 비교하려면 필요하다.
- **신규 handler** `foms/services/geocode_delivery_handler.py` — `storage_delete_handler.py` 계약 준수(자기 commit 없음, 예외=재시도). payload 에 order_id 없음 / 주문 삭제됨 / 주소 빈 값 / 변환 실패는 **성공 종료**로 처리해 DEAD 로 쌓이지 않게 했다. 재전달 멱등(해시+좌표 일치 시 외부 호출 0회). 외부 HTTP 구간 내내 Order row 를 잠그지 않는다(결과가 주소로 결정되므로 last-write-wins 안전).
- **등록**: `tools/ops/run_domain_side_effect_outbox.py:206` `register_handler("GEOCODE", handle_geocode, replace=True)`. 파일 docstring 에 현재 등록 handler 목록을 명시했다.
- **failed 재큐 백오프**: `foms/api/measurement/map.py` 에 `FAILED_GEOCODE_REQUEUE_INTERVAL = 24시간` + `_should_requeue_geocode()`. `pending`→False(기존 유지), `failed`→`geocoded_at` 기준 24시간 경과 시에만 True(시각 없는 레거시 행은 1회 재시도), `NULL`→즉시 True. 범용 경로(`erp_map.py`)의 영구 제외를 따라가지 않고 백오프로만 제한했다. `foms/api/cs/as_map.py` 가 같은 헬퍼를 재사용하므로 AS 지도에도 적용된다.
- **T1 과의 정합 확인**: 스윕이 enqueue 전에 `pending` 을 찍으므로, 지도 경로는 `_should_requeue_geocode` 가 pending 에 False 를 돌려 중복 enqueue 하지 않는다. 두 경로가 서로를 밀어내지 않는다.
- **계약 테스트 갱신**: `tests/contracts/runtime/foms_namespace_surface_tests.py` 의 `geocode_helpers.__all__` 정확일치 계약에 새 공개 심볼 5개를 등재(계약 약화가 아니라 목록 갱신).
- 신규 테스트: `tests/postgres/test_sidefx_geocode_handler.py`(실 worker 경로 5건) / `tests/domains/test_geocode_delivery_handler.py`(11건) / `tests/domains/test_measurement_map_geocode_requeue.py`(8건).
- CEO 재검증: diff 직접 확인(계약 테스트 수정이 목록 갱신인지 포함), `python -m pytest tests/domains/ -q -k "geocode or map"` → `156 passed`, `python -m pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q` → `178 passed, 1 failed`(실패는 타 세션 `integrations` 건 동일), `import app` → `APP_OK`.
- PostgreSQL 레인은 구현자가 격리 클러스터(5441)를 새로 만들어 실제 실행: `tests/postgres/test_sidefx_geocode_handler.py` 5 passed, SIDEFX 인접 스위트 73 passed. (기존 5440 클러스터는 template1 파손으로 사용 불가.)

### T1 완료 기록 (2026-08-31)

- 신규 `foms/services/geocode_candidates.py` — 후보 선별 술어 SSOT `build_missing_geocode_query()`. 백필 CLI(`tools/ops/backfill_geocode_missing.py`)가 여기에 위임하도록 바꿔 술어 2벌을 없앴다.
- 신규 `scripts/maintenance/run_geocode_sweep.py` — `--once` / `--loop --interval` / `--batch` / `--include-failed` / `--json`. SIGTERM·SIGINT graceful shutdown. `REDIS_URL` 부재 시 exit 1(무음 성공 금지).
- `start.sh:27-38` — `USE_RQ_WORKER=1` 분기에 `FOMS_GEOCODE_SWEEP_ENABLED` 게이트로 배선(escalation 루프와 같은 패턴). 새 Railway 서비스 불요. 개행 `lf` 유지 확인.
- **중복 enqueue 방지**(코디네이터 교정 반영): enqueue **전에** `geocode_status='pending'` + `geocoded_at=now_utc_naive()` 를 커밋한다. 대상 술어는 `status IS NULL` 즉시 / `pending` 은 `geocoded_at IS NULL OR geocoded_at < now-600s` / `failed` 는 옵션. `PENDING_RETRY_SECONDS = 600`(최악 소진 50건 × 2.9초 ≈ 145초의 약 4배 여유).
  - `geocoded_at` 을 시도 표식으로 쓸 수 있는 근거: `foms/services/geocode_helpers.py` 의 `apply_geocode_to_order` 가 성공·실패·주소없음 모두 `geocoded_at` 을 기록한다. 반대로 `foms/services/order_geocode.py:88-92` `reset_order_geocode_on_address_change` 는 `pending` 만 찍고 `geocoded_at` 을 안 건드려 NULL 로 남는 계열이 있다 → "시각 불명 = 오래된 것 = 포함"으로 처리해 영구 고착 구제를 유지했다.
  - 시계는 `now_utc_naive()` 로 통일(로컬 `datetime.now()` 를 쓰면 dev(KST)에서 9시간 어긋나 나이 판정이 뒤집힌다).
- 신규 테스트 `tests/domains/test_geocode_sweep.py` 14건.
- CEO 재검증: 술어·`start.sh` diff 직접 확인, `python -m pytest tests/domains/test_geocode_sweep.py -q` → `14 passed`, `import app` → `APP_OK`.
- **커버리지 확인**: 운영에서 좌표 없는 주문 121건 중 스윕 술어가 잡는 건 120건. 빠지는 1건(#2285)은 `Order.address='-'` 이면서 `structured_data.site` 주소도 비어 있어 애초에 변환 불가 — 실질 갭 없음.

**잔존 리스크(경계 밖, 미수정)**: `foms/services/measurement_route.py:212` 가 아직 `datetime.datetime.now()` 로 같은 `geocoded_at` 컬럼을 쓴다. 운영 컨테이너 TZ 가 UTC 라 값은 같고 로컬에서만 최대 9시간 어긋난다.

**무관한 red(타 세션)**: `tests/contracts/runtime/foms_namespace_surface_tests.py::test_slg_literal_gap_foms_services_top_level_dirs_closed_set` 이 red 다. 원인은 다른 세션의 미추적 디렉토리 `foms/services/integrations/`(네이버 작업)가 §4.4 허용목록에 없어서다 — 직접 실행해 실패 메시지의 `'integrations'` 로 확인했다. 이번 작업과 무관하므로 손대지 않는다. **push 전에 해당 세션의 조치가 필요하다.**

### T2 완료 기록 (2026-08-31)

- `templates/measurement/map_view.html` +52/-13. 카카오 렌더가 살아 있으면 pending 해소를 `FomsMapViewKakao.updateMarkers`(preserveView) 부분 갱신으로 처리하고, 부분 갱신 수단이 없는 folium 폴백에서만 기존 전체 재로딩을 유지한다.
- 백오프: 진행이 있었던 회차는 재시도 횟수를 소모하지 않고 간격을 유지한다(1.5초로 되감으면 서버 연타). 무진행 시에는 기존 1500/3000/6000/12000/20000 회차·타이밍이 그대로 보존된다 — 추적 검증함.
- 전체 상한 신설: `GEOCODE_POLL_MAX_ROUNDS = 120`, `GEOCODE_POLL_MAX_ELAPSED_MS = 300000`. 상한 도달 시 기존 경고 배너로 종료.
- 배너 문구를 남은 건수 노출로 변경(`주소 변환 중... 3건 남음 (3초 후 갱신)`).
- 담당자 저장 후 전체 재로딩 경로(`tests/domains/test_map_view_manager_contract.py:36-41` 강제)는 무변경.
- 신규 계약 테스트: `tests/domains/test_map_view_geocode_poll_contract.py`.
- CEO 재검증: `git diff` 직접 확인 + `python -m pytest tests/domains/test_map_view_geocode_poll_contract.py tests/domains/test_map_view_manager_contract.py tests/domains/test_map_mobile_sheet_contract.py -q` → `23 passed`.

---

## 7. SIDEFX 워커 활성화 위험 평가 (T5 결정 근거)

### 7.1 STORAGE_DELETE 418건 — **안전 확인됨**

활성화 시 R2 실파일 418개가 삭제된다. 조회 결과:

```sql
-- 대기 중 키가 살아있는 첨부에 물려 있는지
total_keys=418, live_refs=0, live_attach=0
```

**살아있는 첨부가 참조하는 키는 0건.** 전부 사용자가 이미 앱에서 삭제한 첨부의 R2 고아 파일이다. 삭제는 원래 의도된 동작이다.

### 7.2 진짜 위험 — 핸들러 없는 1198건이 DEAD 로 떨어진다

핸들러가 없는 effect_type: `CHANNEL_PUSH_RECORDED` 1087, `STAGE_NOTIFICATION` 110, `SHARE_ALIMTALK` 1.
워커를 켜면 이 1198건이 각각 10회 재시도(지수 backoff 5초~3600초) 후 `DEAD` 로 확정된다. 데이터 파괴는 없지만:

- 로그 폭주와 DB 갱신 부하가 발생한다
- 한 번 `DEAD` 가 되면 나중에 해당 핸들러가 배포돼도 자동 실행되지 않는다

8월분 푸시·단계 알림은 이미 시효가 지났으므로 DEAD 가 합당할 수 있으나, **켜기 전에 이 1198건을 어떻게 처리할지(그대로 DEAD 허용 / 사전 purge / 핸들러 동반 배포) 결정해야 한다.** 관련 도구: `tools/ops/purge_domain_side_effect_outbox.py`.

### 7.3 참고

- `foms/services/orders/order_import.py:372 _require_scan_ready` 가 SIDEFX 워커 heartbeat 를 요구한다 → 워커 부재 시 엑셀 import 가 `ScanNotReadyError` 로 실패한다. 워커 활성화의 부수 이득.
- 네이버 수집 스펙이 대응책으로 적어둔 `skip_geocode` 파라미터는 아직 미구현이다(저장소 grep 0건).

---

## 8. 검증 명령

```bash
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_geocode_sweep.py tests/domains/test_map_view_manager_contract.py tests/domains/test_map_mobile_sheet_contract.py -q
python <scratchpad>/geocode_red.py          # GREEN(exit 0) 이어야 완료
powershell -File scripts/ops/pre_push_smoke.ps1   # push 직전 exit 0
```

---

## 9. 조사 방법 메모

CEO 총괄 + 4개 조사팀 병렬(읽기 경로 / outbox 파이프라인 / 프론트 렌더 / git 회귀 이력) + CEO 직접 운영 DB 조회. 커밋 특정은 서브에이전트 보고를 그대로 쓰지 않고 `git log`·`git show`·`git branch --contains` 로 재검증했다.

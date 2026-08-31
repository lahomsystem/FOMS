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
| T5 | SIDEFX 워커 서비스 Railway 등록 | heartbeat 행 생성 + outbox PENDING 소진 | BLOCKED (§10 — CLI로 Config Path 지정 불가) |
| T7 | deploy 푸시 · production 승격 | CI green + PR 머지 | **DONE** — deploy `44f8d1ee`, production `365b1280` (PR #207) |
| T8 | 운영 스윕 켜기 (`FOMS_GEOCODE_SWEEP_ENABLED=1` + 재배포) | 지도에 뜰 수 있는 주문의 좌표 미달 0건 | **DONE** — §12 |
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

## 9. 승격 기록 (2026-08-31)

- 로컬 커밋 `b6fc4ae3` → deploy `44f8d1ee` → production `365b1280`(PR #207, `b8b57b83`).
- **로컬 스모크는 red 였는데 내 변경 때문이 아니었다.** 타 세션의 미추적 디렉토리 `foms/services/integrations/` 가 네임스페이스 폐쇄집합 계약을 깨고 있었다. 남의 계약을 대신 고치거나 남의 작업 파일을 옮기지 않고, **원격 tip 기준 클린 워크트리**(`c:/tmp/geo-push`)에서 검증했다 — 그 트리에는 미추적 디렉토리가 없으므로 계약이 정상 통과한다(330 passed).
- **`start.sh` cherry-pick 충돌**: 타 세션이 같은 자리에 네이버 수집 블록을 넣어뒀다. 기능 의존이 아니라 **같은 삽입 지점의 독립 블록 2개**였으므로, 정규식 keep-both 없이 손으로 두 개의 독립 `if` 로 명시 병합하고 `bash -n` 으로 검증했다.
- **AI_STATUS 충돌 2회**: deploy 계보에서는 원격 버전을 취해 내 줄만 다시 넣었고(원격 tip 은 이미 정리돼 2627자라 여유가 있었다 — 로컬에서 하던 압축은 낡은 계보 기준이었다), production 승격에서는 규칙대로 코드만 옮기고 문서는 production 버전을 유지했다.
- 승격 도중 `origin/deploy` 가 두 번 움직여 rebase 후 재검증·재푸시했다.
- **승격 트리에서 본 스위트 직접 실행**: `tests/domains` + `tests/contracts` → **5389 passed, 5 skipped**. 승격 PR 이 본 스위트를 안 도는 알려진 구멍을 이걸로 메웠다. PR 검사 4종(test·pg-lane·harness·perf-gate) 전부 SUCCESS.
- **deploy 의 FOMS CI red 는 내 것이 아니었다**: 내 푸시 직전 tip `f6c49ae5` 에서 이미 red(타 세션 정산 대시보드 커밋이 `test_settlement_dashboard_render.py` 를 docs 전용 서브셋에 등재하지 않음). 그 세션이 `86e91a1f` 로 자체 수정했다.

## 10. T5 가 막힌 이유 — CLI 로는 SIDEFX 서비스를 만들 수 없다

`railway add` 는 서비스 생성·repo 연결·변수 설정까지만 지원하고 **Config Path 지정 옵션이 없다**. Config Path 없이 만들면 공용 `railway.toml`(`startCommand = "sh start.sh"`)을 상속해 gunicorn 이 하나 더 뜰 뿐 SIDEFX 워커가 되지 않는다. 필요한 변수는 `DATABASE_URL`(+ STORAGE_DELETE 핸들러용 `R2_*`)이고 WORKER 가 이미 전부 갖고 있다.

선택지는 둘이다:
1. **대시보드에서 등록**(설계 정본): 새 service → Settings → Config Path = `railway-domain-sidefx.toml`, 변수는 WORKER 것 복사.
2. **`start.sh` 에 배선**(설계 이탈): escalation·네이버·좌표 스윕과 같은 패턴으로 WORKER 컨테이너에 얹는다. 코드 변경이라 승격 사이클이 한 번 더 필요하다.

## 11. 운영 반영 결과 (2026-08-31)

- production 머지 `365b1280` → Railway 자동 배포. WORKER 는 `FOMS_GEOCODE_SWEEP_ENABLED=1` 설정이 재배포를 한 번 더 트리거해 05:23:32 배포가 **새 코드 + 새 변수**를 함께 실었다(SUCCESS 확인).
  - 참고: 기존 기록은 `railway variables --set` 이 재배포를 안 건다고 돼 있으나, 이번에는 새 배포가 생성됐다. 어느 쪽이든 **부팅 시각으로 확인**하는 규율은 그대로 유효하다.
- 워커 로그에서 스윕 기동 확인: `[geocode-sweep] started (interval=60s batch=50 include_failed=False pending_retry=600s)`, 첫 라운드 `scanned=50 queued=50 skipped=0 failed=0`.
- **좌표 소진**: 좌표 없는 주문 121건 → 약 20분 만에 소진. 최종 판정(2026-08-31):

  | 지표 | 값 |
  |---|---|
  | 지도에 뜰 수 있는(active) 주문 중 좌표 없음 — 실패 제외 | **0건** |
  | 같은 모집단, 실패 포함 | 23건 (주소 자체가 틀려 카카오가 못 찾는 건, 24시간 백오프로 재시도) |
  | 최근 20분 변환 | 78건 |

- **남은 5건은 유령이다**: `geocode_status` 가 NULL 로 남은 5건(4237·4266·4301·4409·4600)은 전부 `structured_data.meta.draft = true` 인 ERP draft 라 `Order.active_filter()` 가 제외한다. 지도 쿼리도 같은 필터를 쓰므로 화면에 뜨지 않는다 — 스윕이 안 집는 것이 정상이다.
- **판정 루프 주의**: `geocode_red.py` 는 SIDEFX heartbeat > 0 을 GREEN 조건에 넣었기 때문에, SIDEFX 서비스가 없는 한 영원히 RED 다. 이 단계의 올바른 지표는 위 표의 "active 주문 중 좌표 없음(실패 제외) = 0" 이다.

---

## 12. 후속 작업 — 엑셀 업로드(가져오기) 기능 제거 (2026-08-31)

지오코딩 조사 중 SIDEFX 워커 미배포의 부작용으로 "엑셀 업로드가 `ScanNotReadyError` 로 막힌다"는 사실이 드러났고, 사용자가 **"엑셀 업로드는 FOMS 어디에도 필요 없으니 기능과 코드 모두 삭제"** 를 지시했다. deploy 커밋 `d61dccd8`.

### 12.1 착수 전 확인한 것 (오삭제 방지)

- **`foms/web/admin/excel_import.py` 는 통째로 지우면 안 된다.** 같은 파일·같은 Blueprint 에 보존 대상인 `download_excel()`(주문목록 엑셀 내보내기)이 있다.
- 운영 실사용 판정(읽기 전용 조회):

  | 지표 | 값 |
  |---|---|
  | `order_import_artifacts` 행 수 | **0** |
  | 마지막 업로드 감사 기록 | **2025-05-28** (15개월 전) |
  | 마지막 엑셀 **다운로드** 기록 | **2026-07-03** → 보존 확정 |
  | `domain_side_effect_outbox.order_import_artifact_id` non-null | 0 |
  | R2 `order_imports/` 오브젝트 | 0 |

- **기존 주문 안전**: `orders` 에는 아티팩트 참조 컬럼이 없다. 링크는 아티팩트→주문 단방향 JSONB(`resource_order_ids`) 뿐이라 삭제해도 주문 행은 무사하다.

### 12.2 사용자 결정 2건

1. **화면·코드는 전부 삭제하되 DB 표는 남긴다** — 표를 지우려면 신규 마이그레이션과 outbox one-of CHECK 8→7 재작성이 따라오는데, 표가 비어 있어 실익이 없다.
2. **감사 원장의 패킷도 정리한다** — `ORDER-IMPORT-01` 제거 + 하드코딩 개수 하향.

### 12.3 감사 원장 정리가 필요했던 이유

`ORDER-IMPORT-01` 이 `tests/harness/test_bugfix_packet_manifest.py` 의 하드코딩 목록(`EXPECTED_PACKETS` 124개·`REV99_DEPENDS_ON` 111개)과 `tools/ops/check_foms_remediation_readiness.py:66 EXPECTED_PACKETS = 124` 에 박혀 있어 **어느 쪽이든 red 가 나는 구조**였다:
- 패킷을 두면 → `created_tests` 경로 부재로 배포 게이트 red
- 패킷을 지우면 → 하드코딩 개수 3곳이 red

해결: 패킷 제거 + 124→123 + 111→110. `REV-99` 와 `STATE-GUARD-01` 의 `depends_on` 에서도 제거했다(두 패킷이 참조 중이었다). `STATE-GUARD-01` 의 transitive closure 단언은 부분집합(`<=`)이라 영향 없음을 먼저 확인했다.

### 12.4 함정 — JSON 통째 재작성

`json.dumps(indent=2)` 로 `foms_bugfix_packet_tests.json` 을 다시 쓰자 **6495줄이 바뀌었다**(원본은 1-space 들여쓰기). 되돌린 뒤 줄 단위 국소 편집으로 다시 해서 **−29줄**로 맞췄다. 생성물이 아닌 수기 JSON 은 파싱→덤프 왕복을 하지 마라.

### 12.5 남긴 것 (의도적)

- 엑셀 다운로드 전부(주문목록·수납장 내보내기)
- `OrderImportArtifact` 모델·테이블·마이그레이션 (빈 표)
- `allowed_file` / `ALLOWED_EXTENSIONS` — **유일 소비자가 사라져 dead code 가 됐다.** `tests/contracts/runtime/foms_namespace_surface_tests.py` 가 `file_utils.__all__` 을 정확일치로 고정하고 있어 지우려면 계약 2곳을 함께 고쳐야 한다. `foms/services/README.md` 에 "caller 없음"으로 명시해 뒀다. **다음에 정리할 거리.**

### 12.6 커버리지 소실 없음

삭제된 `tests/postgres/test_order_import.py::test_worker_expiry_scan_dispatches_provider` 는 `tests/postgres/test_upload_02.py:384` 에 동명의 **상위집합** 테스트가 이미 있다(`"reclaim" in res` 를 추가로 검증). 이관하지 않았다.

### 12.7 검증

`pre_push_smoke` PASSED(349 passed) · `tests/domains` + `tests/contracts` + `tests/harness` **6034 passed, 5 skipped** · 잔존 참조 전수 grep 0건(DB 표 계약 제외) · SIDEFX 워커 진입점 import 정상.

## 13. 조사 방법 메모

CEO 총괄 + 4개 조사팀 병렬(읽기 경로 / outbox 파이프라인 / 프론트 렌더 / git 회귀 이력) + CEO 직접 운영 DB 조회. 커밋 특정은 서브에이전트 보고를 그대로 쓰지 않고 `git log`·`git show`·`git branch --contains` 로 재검증했다.

---

## 14. 후속 — 실측 대시보드 체감 지연 조사와 "동선 추천" 제거 (2026-08-31)

사용자가 "실측 대시보드에서 날짜 클릭이 예전보다 느려진 것 같다, 자연스러운 건지 측정하라"고 했다.

### 14.1 측정 결과 — 날짜 클릭 자체는 회귀가 아니다

production 실측(claude_master 해제 → 측정 → **재잠금 완료**):

| 항목 | 실측 | 예산 | 판정 |
|---|---|---|---|
| dTTFB(날짜 프래그먼트 − healthz) | 100~171ms | 200ms | 이내 |
| 전송 바이트(br) | 22.7~34.3KB | 50KB | 이내 |
| 압축 | `content-encoding: br` | — | 정상 |
| 간헐 최대 | 1.5~1.7s | — | 알려진 한국↔싱가포르 tail |

오늘 날짜에서만 도는 발송처리 미리보기 추가 쿼리(`1c1d21bf`)도 A/B 결과 벌점이 없었다(오늘 160ms vs 다른 날 171/151/100ms). 지오코딩 커밋은 실측 대시보드를 건드리지 않았다(지도 전용).

### 14.2 진짜로 찾은 것 — 동선 API 중앙값 5초

```
/api/erp/measurement/route  (production 실측)
  2026-09-01: min 224ms / 중앙값 4867ms / 최대 5029ms
  2026-09-02: min 187ms / 중앙값 5376ms / 최대 5782ms
  2026-08-31: min 267ms / 중앙값 490ms  / 최대 11239ms
```

꼬리만 느린 게 아니라 **중앙값이 5초**라 알려진 네트워크 tail과 성격이 다르다. 원인은 `_build_route_points` 가 주문에 **이미 저장된 `lat`/`lng` 를 확인하지 않고** 매번 `convert_address()` 를 부른 것 — 바로 아래에서 `_store_geocode_coords` 로 저장해 놓고 다음 호출 때 자기가 저장한 값을 안 썼다. 프로세스 내 LRU 가 살아 있을 때만 빨라서 min 과 중앙값이 이중 분포로 갈렸다.

### 14.3 사용자 결정 — "동선 추천 (MVP) 모달과 관련된 모든 것 삭제"

근거: "제대로 맞지도 않고 실제 동선과 크게 달라 의미 없다"(최근접 이웃 직선거리 추정).

**착수 전 조사로 막은 오삭제 3건**:
1. **`/api/erp/measurement/route` 엔드포인트를 지우면 안 된다.** 응답의 `route` 키(추정이 아니라 예약 순서)를 동선 스트립이 쓰고, **v3 영업 홈 마운트(`persona_home_sales.html:122`)에는 `data-route-inline` 속성이 없어 항상 이 API 로 폴백**한다(직접 확인). 지우면 그 화면의 띠가 죽는다 → 엔드포인트는 유지하고 `optimized_*` 키만 제거.
2. **`static/js/measurement/foms-route-strip.js` 를 파일 통째로 지우면 안 된다.** 안에 히어로 방문 카운트다운(`paintCountdown`)이 살고 v2·v3 두 표면이 쓴다.
3. **`static/css/measurement/foms-route-strip.css` 도 마찬가지.** 절반이 히어로·진행요약·완료배지이고, `.foms-route-c0~c7` 팔레트는 지도(`map-view-kakao.js`)와 공유하는 SSOT 다.

또 **`/api/erp/measurement/route-eta` 는 추정과 무관**하다(스트립의 실도로 ETA 전용) — 보존.

### 14.4 제거·수리한 것

- 모달 `#routePlanModal`("동선 추천 (MVP)") + PC "동선" 버튼 + 모바일 동선 칩
- `dashboard.js` 의 Route Plan 블록(`loadRoutePlan`)
- `_haversine_km`·`_order_nearest_neighbor`, 응답의 `optimized_route`·`optimized_total_distance_km`
- 호출자 0건이던 dead code `_query_route_orders`
- **5초 수리**: `_build_route_points` 가 저장 좌표를 먼저 쓰고, 없을 때만 변환 폴백. 판정 기준은 `_stored_coords` 헬퍼 하나로 인라인 fast path 와 통일했다(두 벌로 갈리면 화면마다 지점 집합이 달라진다). 변환기 객체 생성도 폴백이 실제로 필요할 때로 지연.

**판단해서 살린 것**: 모달 푸터의 "동선 지도 보기"(`route=1`)는 추정이 아니라 **방문 시간순** 폴리라인이고 저장소 전체에서 유일한 입구였다. 모달과 함께 지우면 멀쩡한 기능이 고아가 되므로 툴바·모바일 칩 옆으로 이관했다. (푸터의 "지도(핀) 보기"는 툴바 지도 버튼이 같은 목적지로 리다이렉트해 중복이라 함께 삭제.)

### 14.5 남은 진단 공백

**실측 대시보드에만 `X-FOMS-EPT-B7-RENDER-MS` 헤더가 없다.** 주문·출고·생산·건설·AS·이력 6개에는 붙어 있는데 `foms/web/measurement/dashboard.py` 만 빠졌다 — 이 화면은 서버 렌더와 네트워크를 분리할 수단이 원천적으로 없어 이번에도 간접 지표로 우회했다. **다음에 붙일 거리.**

### 14.6 캐시 핀

`dashboard.js` 를 고쳤으므로 SW `staticCacheFirst` 함정에 대비해 핀 3곳을 범프했다(`20260810b`→`20260831a`): `measurement-entry.js:10 MEAS_JS_V`, `dashboard.html:17`, 그리고 **`dashboard_scripts.html:1 measurement_js_v`** — 마지막 것은 entry 자체의 핀이라 안 올리면 SW 가 옛 entry 를 주어 앞의 두 범프가 무효가 된다.

---

## 15. 승격 진행 현황 (2026-08-31 마감 시점)

| 작업 | deploy | production |
|---|---|---|
| 지도 지연 근본 수정 | `44f8d1ee` | **`365b1280` 운영 반영 완료** (좌표 소진 121→0, 스윕 정상 순환) |
| 엑셀 업로드 제거 | `d61dccd8` (CI 4/4) | 승격 PR 대기 |
| 동선 추천 제거 + 5초 수리 | `be52d9c3` (CI 4/4) | 승격 PR 대기 |

승격 워크트리 `c:/tmp/promo2` 에 세 커밋을 체리픽했다(`e5fe53a0`·`dc2777d1`·`316ac61e`).

### 15.1 리베이스에서 막은 충돌 (동선 제거)

타 세션이 **같은 자리**에 "실측일 미정 주문 모아보기" 버튼·모달을 넣어 3구간이 충돌했다. 자동 병합에 맡겼으면 한쪽이 통째로 사라질 자리라 손으로 갈랐다:

- 버튼 줄 — 내 "동선 지도" 링크 + 타 세션 "실측일 미정" 버튼 **둘 다 보존**
- 모달 구간 — 동선 추천 모달 40줄만 제거, 새 모달 49줄 보존
- JS 블록 — 동선 블록 61줄 제거, 실측일 미정 166줄 보존 + 주석 번호 재정합(중복 1줄 포함)

추가로 두 가지가 딸려 나왔다:

1. **타 세션 계약 파손** — `tests/domains/test_measurement_undated_ui_contract.py::test_undated_button_is_last_in_filter_actions` 가 내가 지운 `id="btn-route-plan"` 을 **위치 기준점**으로 삼고 있었다(`ValueError: substring not found`). 기준점을 현재 요소(`&route=1` 동선 지도 링크)로 갱신했다. **삭제가 남의 위치 계약을 깨뜨릴 수 있다는 사례다.**
2. **인벤토리 줄밀림** — 코드 삭제로 `foms_failopen_inventory.json`·`foms_order_mutation_writer_inventory.json` 의 `lineno` 가 밀렸다. 스모크가 재생성한 결과를 커밋에 포함해야 CI 가 green 이다.

### 15.2 승격 체리픽 충돌 3건 (성격별 처리)

- `foms_audit_coverage_inventory.json` — 생성물. 승격 트리에서 **재생성**(가져오지 않음).
- `tests/domains/test_settlement_aggregation.py` — 정산 대시보드가 아직 운영에 없어 파일 자체가 없다. 그 변경은 **가져오지 않음**.
- `docs/AI_STATUS.md` — 문서 계보 차이. 규칙대로 **코드만 승격, 문서는 production 버전 유지**(2회 발생).

### 15.3 남은 일

1. 승격 트리 본 스위트 + 스모크 (진행 중)
2. 승격 PR 생성 → 검사 4종 → 머지
3. 승격 후 운영 화면 확인 — 실측 대시보드에서 "동선" 버튼이 사라지고 "동선 지도" 링크가 그 자리에 있는지, 엑셀 다운로드는 살아 있는지

# 진행 원장 — 네이버 과거 주문 소급 수집(백필) · NAVER-INGEST-BACKFILL

- 계획서: `docs/plans/2026-09-01-naver-ingest-backfill-plan.md`
- 워크트리: `c:\tmp\foms-s-s0901-132716` (session/s0901-132716, origin/deploy 기준)
- 시작 HEAD: `c2b0fd9c`

## Task 상태

| task | 상태 | 완료 기준 |
|---|---|---|
| T1 클라이언트 `more` 이어받기 | DONE | 2쪽 이어붙임·`moreSequence` 전달·루프 상한 테스트 green |
| T2 `backfill.py` 서비스 | DONE | 워터마크 불변·중복 skip·창 분할·재개·알림 0·범위 상한 테스트 green |
| T3 큐·태스크·라우트 + 등재 6종 | DONE | 등재 계약 green + smoke 사각 3종 직접 실행 |
| T4 워크벤치 화면 + 자산 핀 | DONE | 템플릿 계약 green·핀 전수 일치 |
| T5 스테이징 1회 백필 검증 | DONE | 보존 기간 실측·링크 증가·후보 노출·중복 0·429 0 |
| T6 게이트·푸시 | DONE(CI 4/4 green) | pre_push_smoke exit 0 + CI 전 워크플로 green |
| T7 매칭 축 사본 컬럼(캡 함정 해소) | DONE(CI 대기) |
| T8 원본 없는 건 안내(곁가지) | PENDING | 잔여 있을 때만 |

## 문서 근거 — 조회 가능 기간 (2026-09-01)

`https://apicenter.commerce.naver.com/llms/get-v1-pay-order-seller-product-orders-last-changed-statuses.md`

- `lastChangedFrom` 필수(inclusive) · `lastChangedTo` 생략 시 **from + 24시간** 자동.
- 응답 최대 **300건**, `limitCount` 는 300 초과 지정해도 300 캡.
- 초과분은 `data.more{moreFrom, moreSequence}` 로 이어받기. 응답은 시간순 정렬.
- **과거 조회 상한(보존 기간)에 대한 문장이 문서에 없다.** → 스테이징 실측으로 채운다(T5).

대안 `GET /v1/pay-order/seller/product-orders`(조건형 스냅샷): `from` 필수·`to` 생략 시 +24시간,
`pageSize` 1~300, `page` 페이징, `rangeType` 으로 기준 일시 선택. 다만 **문서가 동기화
용도에는 last-changed 폴링을 권한다**, 그리고 `rangeType` enum 이 llms 문서에 없다
(지어내지 않는다). → 백필도 last-changed 경로를 쓴다.

`intro-제약사항.md`: 429 = `GW.RATE_LIMIT`, Token bucket(앱·API 단위), 버스트는 한도의 2배.

## 기록

- 2026-09-01 착수. 워크트리 신규 생성. 사용자 결정 3건(범위 90일 · 클레임 반영하되 알림 off ·
  진입점은 워크벤치 화면 버튼).
- 착수 전 발견: `get_last_changed_statuses` 가 `data.more` 를 안 읽어 **창당 300건 초과분이
  조용히 잘린다**(정상 스윕에서는 드물지만 하루 창 백필은 확실히 걸린다). T1 로 선행 수정.
- T1 DONE: `_changed_window` 신설 — 창 안에서 `data.more{moreFrom, moreSequence}` 이어받기,
  `limitCount=300` 명시, 쪽수 상한 50(초과 시 경고 로그), 항목 0건 + more 만 오면 정지.
  창 끝(`lastChangedTo`)은 이어받는 동안 고정한다. 신규 4개 포함 client 테스트 32 passed.
  red-check: `more` 읽기를 끄면 3개가 빨개진다(확인함).
- T2 DONE: `backfill.py` 신설 — 하루 창 순회(`iter_time_windows`)·창마다 커밋·별도 상태키
  `naver_backfill_state`(워터마크 불변)·구간 규칙(빈 구간/미래/90일 초과는 **호출 0회**로 거절)·
  창 사이 0.5초 간격·한 창 실패해도 앞 창 성과 보존 + 사유 기록.
  수집 본체는 `sync_naver_orders` 를 그대로 쓴다(집 묶기·매핑·멱등 한 코드).
  알림 억제는 `refresh_claims(notify=False)` → `sync_naver_orders(notify_claims=False)` 로 배선.
  신규 13개 + 기존 3파일 = 94 passed. red-check: `notify_claims=True` 로 되돌리면 알림 억제
  테스트가 빨개진다(ADMIN 수신자를 만들어 두고 잰다 — 받을 사람이 없으면 반증이 안 된다).
- T3 DONE: `enqueue_naver_backfill`(job timeout 2h) + `run_naver_backfill_task`(WORKER 전용,
  웹푸시 없음 — 백필은 알림을 안 만든다) + 라우트 2종
  (`POST /admin/naver-ingest/backfill`·`GET /admin/naver-ingest/backfill-state`, 둘 다 ADMIN).
  구간 검사는 **큐에 넣기 전에** 서비스와 같은 `validate_range` 로 한다. 종료일은 그날 끝까지.
  등재: write guard manifest · policy manifest(ADMIN_OPS) · ACTION_LABELS
  `NAVER_INGEST_BACKFILL_ENQUEUE` · audit coverage 인벤토리 재생성(204/0 unaudited) ·
  `log_access` 행위자 인자 · 네임스페이스 계약(tasks `__all__`) · web 금지 심볼에 `run_backfill` 추가.
  신규 라우트 테스트 9 passed, 등재 게이트 51 + write guard 41 passed.
- T4 DONE: 워크벤치 수집 상태 카드에 '과거 주문 소급 수집' 칸(시작·종료 날짜 + 버튼 +
  진행 문구). 기본값은 **어제까지 90일**(오늘 구간은 정상 5분 스윕 몫). 진행은
  `backfill-state` 를 5초 간격 폴링해 '어디까지 마쳤다'를 말하고, 끝나면 화면을 다시 받는다
  (끝을 안 말하면 사람이 다시 누른다 — 전체 다시 읽기에서 겪은 함정).
  진행 문구는 `data-foms-no-autodismiss`(.alert 5초 자동닫힘 함정).
  자산 핀 `?v=20260901b`(CSS·JS 동반 + 계약 2곳 함께 범프). integrations 1294 passed.
- T6: `pre_push_smoke` exit 0(377 passed) · smoke 사각 3종(policy manifest·ACTION_LABELS·
  docs-scope) 직접 실행 green · 로컬 본 스위트 7831 passed(visual 레인은 file-backed SQLite
  전제라 로컬 미실행 — CI 몫). deploy push `ece12afe2`(자기 커밋 5개만 cherry-pick).
  중간 함정 2건: (1) 셰이프 계약이 `jobs.queue.__all__` 을 정확일치로 못박아 신규 enqueue
  헬퍼 등재가 필요했다(smoke 가 잡아 줌), (2) 승격용 임시 워크트리에서 failopen 인벤토리가
  충돌 — 재생성으로 해소(타 세션 커밋 하나 반영 후 rebase).

## 조회 가능 기간 — 스테이징 실측 (2026-09-01)

문서에 상한 문장이 없어 실측했다(모두 스테이징, 읽기 위주):

| 구간 | 결과 |
|---|---|
| 2025-09-01 (1년 전) | 변경 이벤트 **32건** 수신 — 오류 없음. **1년 전 데이터가 실제로 온다.** |
| 2023-09-01 (3년 전) | 0건, **오류 없음**(400 아님) — 없는 건지 안 주는 건지는 이 관측으로 못 가른다 |
| 2026-06-04~08-31 (89일) | 창 90개 · 변경 1,997건 · 신규 링크 1,560 · 이미 있던 것 437 · 오류 0 · 소요 약 2분 |

→ **90일은 규격 안에서 확실히 된다**(1년 전도 데이터가 오므로 여유가 크다). 호출 간격은
창 사이 0.5초 + 워커 동시성 1, 실행 중 429 0건.

## T5 검증 결과 (스테이징)

- 첫 실행은 **수집 0건**이었다 — 정상 스윕 필터(`is_collectible`, 결제완료)로 걸렀기 때문.
  변경 피드의 `productOrderStatus` 는 **현재 상태**라 오래된 주문은 하나도 안 걸린다
  (06-04~08-16 이벤트 1,300건 중 PAYED 0건). `collect_all` 로 수정 → 1,560건 수집.
- 두 번째 발견: 백필분이 **처리 탭을 덮었다**(대기 집 138 → 798). 백필은 지금 처리할 일이
  아니므로 `reviewed_at` + `triage_state.backfill` 로 큐 밖에 둔다. 스테이징 기존 1,564행도
  같은 모양으로 표시해 원상 복구(대기 798 → 138).
- 수정 후 재실행(2026-05-20~05-22): 신규 50건 전부 `reviewed_at`·백필 표식 보유,
  처리 큐 138 유지, **중복 링크 0**(같은 상품주문 2행 0건), 오류 0.

## 미해결 — 운영 실행 전에 닫아야 한다 (T7)

`find_unlinked_matches`(오늘 실측 ↔ 안 붙은 수집분 매칭)는 미연결 링크를
**`id` 내림차순 300행**만 훑는다(`UNLINKED_SCAN_CAP`). 운영에 90일 백필을 넣으면 미연결이
1,500행대가 되어 **캡이 즉시 걸리고, 최신 300행(=백필분)이 그 자리를 다 차지**한다.
띠가 조용히 잘리고 기존 미연결분이 밀린다(경고 로그는 남는다).

축이 `raw_snapshot` 안의 전화·수령인명이라 SQL 로 좁힐 수 없는 것이 원인이다. 정공법은
매칭 축 사본 컬럼(수령인명·전화 뒷자리)을 링크에 두고 SQL 로 좁히는 것 — 마이그레이션 1개 +
기존 행 채움 + 매칭 함수 재작성.

## T7 — 매칭 축 사본 컬럼 (사용자 결정: 지금 제대로 고친다)

- 마이그레이션 `naverbf_00`: `external_order_links` 에 `recipient_name`·
  `recipient_phone_digits`·`orderer_phone_digits` + **미연결 전용 부분 인덱스** 3개
  (`WHERE order_id IS NULL` — 붙고 나면 매칭 대상이 아니라 인덱스가 이력 전체로 안 자란다).
  `group_key` 와 같은 규약의 사본이다(정본은 `raw_snapshot`).
- 수집·보류 기록 양쪽에서 사본을 채운다(`ingest._match_key_values` — 값 추출은 후보 화면과
  **같은 함수** `_snapshot_keys` 재사용).
- `find_unlinked_matches` 재작성: 사본 있는 행은 SQL 이 직접 좁히고(IN + 부분 인덱스),
  사본 없는 옛 행만 종전 300행 스캔으로 폴백. 두 갈래를 링크 id 로 합친다.
- 기존 행 채움: `tools/ops/backfill_link_match_keys.py`(배치·dry-run). 값이 안 나오는 행은
  빈 문자열로 표시해 같은 배치가 무한히 다시 걸리지 않게 한다.
- 회귀 테스트: 매칭 대상보다 **더 최신인 미연결 320행**을 쌓아도 그 집을 짚는다
  (예전 코드로는 캡에 걸려 못 짚는다 — red-check 확인).
- PG 레인 계약: 마이그레이션 왕복 2회 + 인덱스 술어가 `WHERE (order_id IS NULL)` 인지.
  로컬은 PG 없음으로 skip — CI PostgreSQL Lane 이 판정한다.
- 로컬 전수(visual·postgres 제외) 7,789 passed · pre_push_smoke exit 0.

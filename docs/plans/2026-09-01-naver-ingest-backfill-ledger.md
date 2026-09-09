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
| T7 매칭 축 사본 컬럼(캡 함정 해소) | DONE |
| T8 '여기서는 못 보낸다' 구별 | DONE | 잔여 있을 때만 |

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

### T7 스테이징 실데이터 검증 (2026-09-01)

- 마이그레이션이 스테이징에 반영된 뒤 `tools/ops/backfill_link_match_keys.py --batch 500`
  실행 — 2,099행 전부 채움(사본 없음 0행).
- 실데이터 시드로 확인: 미연결 링크 중 **가장 오래된 id=20**(김용오, 08-12 주문)의 수령인·
  전화로 오늘 실측 주문을 하나 만들고 `GET /admin/naver-ingest/bulk-dispatch/state` 호출 →
  `unlinked: 1`, 근거 `전화 일치`. 미연결이 2,000행인 상태라 **예전 코드였다면 id 내림차순
  300행 캡 밖이라 못 짚었을 자리**다. 확인 후 시드 주문 삭제.
- CI 전 워크플로 green(head `92e727f5`): FOMS CI · Harness CI · FOMS PostgreSQL Lane ·
  perf-gate 4/4. PG 레인 통과 수 724 → 726 으로 늘어 신규 마이그레이션 계약 2개가 실제로
  돌았음을 확인.
- 도중 CI red 1회: 타 세션 리비전(`sharehist_00`)과 **alembic head 2개** 충돌 →
  no-op 병합 리비전 `merge_naverbf_share` 로 해소.

## 남은 일

1. **운영 실행(사용자 승인 필요)** — 순서가 있다: ① 운영 배포 반영 확인 ②
   `tools/ops/backfill_link_match_keys.py` 로 기존 링크 사본 채움 ③ 워크벤치에서 90일 백필
   1회 ④ 오늘 실측 띠에 짚히는지 확인. 워커 재배포는 하지 않는다(큐 전면 정지 —
   `tools/ops/check_worker_redeploy_safe.py`).
2. **T8(곁가지)** — "네이버 원본이 없는 건"과 "네이버 주문이 아닌 건"을 화면이 구별하지
   못한다. 운영 백필 뒤에도 남는 건이 있어야 판단할 수 있어 미착수.

## 운영 승격·실행 완료 (2026-09-01)

- 승격 PR **#241** 머지 — production `003ed052`. 검사 4종(test·pg-lane·harness·perf-gate)
  전부 SUCCESS, mergeStateStatus=CLEAN. 승격 트리에서 본 스위트 직접 실행 7,791 passed +
  pre_push_smoke exit 0(승격 PR 이 안 도는 관문).
- completeness 는 `missing baseline deps=104`(운영이 cherry-pick 으로 받아 SHA 만 다른 docs
  계보 잔재)로 멈춰 **내 diff 가 기대는 것들을 내용으로 확인**하고 `--allow-incomplete`:
  `find_unlinked_matches`·`_snapshot_keys`·`UNLINKED_SCAN_CAP`·`sharehist_00`(병합 리비전의
  부모) 모두 운영에 존재.
- 승격 충돌 3건: audit coverage 인벤토리(재생성)·failopen 인벤토리(재생성)·`AI_STATUS`
  (운영 계보 목록은 그대로 두고 내 한 줄만 얹고, 예산 초과분은 08-23 완료 항목 1건 이관).
- **승격 직전에 잡은 함정**: 운영 워크벤치 자산 핀이 이미 `?v=20260901b`(타 세션이 같은 값을
  썼다)인데 그 자산에는 소급 수집 CSS·JS 가 없었다. 같은 핀으로 올렸으면 SW staticCacheFirst
  때문에 워크벤치를 이미 연 사용자는 **옛 JS 로 버튼이 안 먹는다.** `20260901c` 로 올려 해소.

### 운영 백필 1회 실행 (사용자 명시 승인 — 측정 계정 사용도 함께 승인)

`claude_master` 잠금 해제(is_active 만) → 워크벤치 라우트로 2026-06-04~08-31 실행 → 재잠금.

| 것 | 값 |
|---|---|
| 창 | 90개 |
| 변경 이벤트 | 1,979건 |
| 새 링크 | **1,790** |
| 이미 있던 것 | 189 |
| 보류·오류 | 0 · 0 (429 없음) |
| 소요 | 약 100초 |

실행 뒤 확인(읽기 전용):

- 총 링크 2,033 · 소급 표식 1,790 · **처리 큐 집 1** — 큐를 안 덮었다.
- 사본 없는 미연결(60일) 71행 < 캡 300 — 폴백 갈래 안전(운영 채움 스크립트 실행 불필요).
- **오늘 실측 띠가 안 붙은 집 2건을 짚는다**: 이다영(주문 5050·`2026071029026201`)·
  서영훈(주문 4611·`2026080398404991`, 링크 5행) — 둘 다 전화 일치. 백필 이전에는
  원본이 없어 짚을 수조차 없던 건들이다.
- 오늘 발송 대상은 6집 전부 발송 완료 상태(eligible 0).

**남은 판단**: 사용자가 말한 "오늘 실측 11건"중 띠에 뜬 것은 2건이다. 나머지는 전화·수령인명
두 축이 다 어긋나거나 네이버 유래가 아닐 수 있다 — 곁가지 T8(원본 없는 건 vs 네이버 아닌 건
구별)이 그 자리를 맡는다. 미착수.

## T8 — 화면이 '네이버 아닌 건'을 구별한다 (2026-09-01)

운영 전수 확인(음성 대조군 포함)이 판정을 열었다. 오늘 실측 19건 중 링크 없는 13건에 대해
**이름 축·전화 축 둘 다** 수집 원본을 조회한 결과:

- 서영훈(#4611)·이다영(#5050)만 원본 존재(각 5행·1행) → 붙이면 대상이 되는 집(띠가 짚는다).
- 나머지 11건은 **이름 0행·전화 0행** — 백필로 90일치 1,790건을 받은 뒤에도 없다.
  접수일이 전부 백필 구간(06-04~08-31) 안이므로 **이 스토어 네이버 주문이 아니다.**

구현:

- `coverage_start()` — 수집이 실제로 훑은 구간의 시작. 정본은 백필 상태(`requested_from`).
  백필을 안 돌렸으면 **모른다**고 답한다(모름을 아는 척하면 진짜 네이버 건을 판매자센터로
  떠넘기게 된다).
- `classify_unsendable()` — 그날 실측인데 링크도 짝도 없는 주문을 둘로 가른다:
  접수일이 커버리지+여유(14일) 안이면 `foreign`("네이버 주문이 아닙니다"),
  밖이면 `unknown`("수집 범위 밖 — 판매자센터 확인"). 여유 14일을 두는 이유는 ERP 접수일이
  네이버 주문일보다 **뒤**일 수 있어 경계에서 단정하면 틀리기 때문이다.
- 두 띠(워크벤치·실측 대시보드)가 같은 값(`build_preview`)을 렌더한다. **띄우는 조건은
  종전 그대로** — 대상이 있거나 붙일 짝이 있을 때만. 못 보내는 건은 곁들이는 정보다
  (그것만으로 띠를 띄우면 네이버와 무관한 날에도 화면이 떠들고, 매일 뜨는 안내는 안 읽힌다).
- 계약 함정 1건: 발송 선별 모듈은 소스에 `request` 라는 글자를 담을 수 없다(화면 필터 상속
  금지 계약이 소스를 훑는다). 상태 키 접근자를 `backfill.read_window_start()` 로 옮겨 해소.
- 검증: 신규 4개 포함 unlinked 17 passed · integrations 1,312 passed · 로컬 전수 7,836 passed ·
  pre_push_smoke exit 0. red-check: 커버리지 판정을 끄면 `foreign` 계약이 빨개진다(확인함).
- 자산 핀 `?v=20260901d`(계약 3곳 동반).

### T8 운영 승격 (2026-09-02, PR #246 · production `8945a1df`)

검사 4종 SUCCESS · mergeStateStatus=CLEAN · 승격 트리에서 본 스위트 직접 실행 7,807 passed +
pre_push_smoke exit 0. 승격 충돌 1건(이 원장 꼬리 — 운영 계보에 없던 절, keep-both 로 이어붙임).

운영 화면은 이제 오늘 실측분에 대해 세 갈래로 말한다:
① 붙이면 대상이 되는 집(원본 있음) ② 여기서는 못 보내는 건(수집 범위 안인데 원본 없음 —
네이버 주문이 아님) ③ 확인이 필요한 건(수집 범위 밖 — 모름).

## 세션 종료 상태 (2026-09-02)

- T1~T8 전부 DONE. 운영 반영 완료(PR #241 백필 본체 · #246 못 보내는 건 구별).
- 운영 백필 1회 실행 완료(신규 링크 1,790). 워터마크는 그대로다.
- 남은 사람 손: 띠가 짚은 2집(이다영 #5050 · 서영훈 #4611)을 워크벤치에서 주문에 붙이기.
  붙이면 오늘 발송 대상에 들어온다. **자동으로 붙이지 않는다 — 사람의 판단이다.**

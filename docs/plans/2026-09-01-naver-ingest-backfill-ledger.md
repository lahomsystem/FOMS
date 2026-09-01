# 진행 원장 — 네이버 과거 주문 소급 수집(백필) · NAVER-INGEST-BACKFILL

- 계획서: `docs/plans/2026-09-01-naver-ingest-backfill-plan.md`
- 워크트리: `c:\tmp\foms-s-s0901-132716` (session/s0901-132716, origin/deploy 기준)
- 시작 HEAD: `c2b0fd9c`

## Task 상태

| task | 상태 | 완료 기준 |
|---|---|---|
| T1 클라이언트 `more` 이어받기 | DONE | 2쪽 이어붙임·`moreSequence` 전달·루프 상한 테스트 green |
| T2 `backfill.py` 서비스 | DONE | 워터마크 불변·중복 skip·창 분할·재개·알림 0·범위 상한 테스트 green |
| T3 큐·태스크·라우트 + 등재 6종 | PENDING | 등재 계약 green + smoke 사각 3종 직접 실행 |
| T4 워크벤치 화면 + 자산 핀 | PENDING | 템플릿 계약 green·핀 전수 일치 |
| T5 스테이징 1회 백필 검증 | PENDING | 보존 기간 실측·링크 증가·후보 노출·중복 0·429 0 |
| T6 게이트·푸시 | PENDING | pre_push_smoke exit 0 + CI 전 워크플로 green |
| T7 원본 없는 건 안내(곁가지) | PENDING | 잔여 있을 때만 |

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

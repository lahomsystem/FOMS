# 계획 — 네이버 과거 주문 소급 수집(백필) · NAVER-INGEST-BACKFILL

- 선행 원장: `docs/plans/2026-08-31-naver-bulk-dispatch-result-ui-ledger.md` §T9
- 선행 설계: `docs/specs/2026-08-31-naver-bulk-dispatch_SPEC.md`
- 진행 원장: `docs/plans/2026-09-01-naver-ingest-backfill-ledger.md`

## 문제

수집 첫 실행이 `2026-08-25 00:44` 이고 워터마크는 **앞으로만** 간다. 그보다 과거의
네이버 주문은 FOMS 에 원본(`ExternalOrderLink`)이 아예 없다. 원본이 없으면 붙이기
후보에도, 일괄 발송 대상에도, "안 붙은 수집분" 띠에도 나타날 수 없다. 오늘(09-01)
실측 16건 중 11건이 링크 없이 남은 이유가 이것이다(접수일 08-03·08-04·08-13·08-18·08-22 등).

## 문서 근거 (2026-09-01 확인, `apicenter.commerce.naver.com/llms/`)

`get-v1-pay-order-seller-product-orders-last-changed-statuses.md`:

- `lastChangedFrom` 필수(inclusive), `lastChangedTo` 생략 시 **+24시간 자동 적용**.
- 응답 상한 **300건**(`limitCount` 는 300 초과 지정해도 300 으로 캡).
- 초과분은 `data.more{moreFrom, moreSequence}` 로 **이어 받아야 한다**. 응답은 시간순
  정렬이고 `moreFrom` 은 못 준 첫 항목의 일시, `moreSequence` 는 같은 일시 안의 구분자다.
- **과거 조회 상한(보존 기간)은 문서에 없다.** 못 찾은 것이 아니라 적혀 있지 않다 →
  스테이징에서 읽기 전용으로 실측해 원장에 적는다.

`get-v1-pay-order-seller-product-orders.md`(조건형 스냅샷 조회, 대안):

- `from` 필수·`to` 생략 시 +24시간, `rangeType`(주문일·결제일 등), `pageSize` 1~300, `page` 페이징.
- 문서 자체가 "**동기화 용도라면 last-changed-statuses 폴링 방식이 더 안전**"이라고 적는다.
- `rangeType` enum 값이 llms 문서에 **없다**(OAS 참조). 값을 지어내지 않는다.

`intro-제약사항.md`: rate limit 은 앱·API 단위 Token bucket, 초과 시 429 `GW.RATE_LIMIT`.
자사 스토어 앱은 전 API 2 RPS(선행 조사).

**채택**: 백필도 `last-changed-statuses` 를 쓴다. 이미 검증된 경로이고, 상세는 같은
`product-orders/query` 로 받아 `ingest_detail` 이 링크를 만든다 → 집(group_key) 묶기·
매핑·멱등이 정상 수집과 **한 코드**로 유지된다. `rangeType` 추측이 필요 없다.

## 사용자 결정 (2026-09-01)

1. 기본 범위 **90일**(실행 시 날짜 직접 지정도 가능).
2. 과거 건의 취소·반품 상태는 **반영하되 알림은 끈다**.
3. 실행 진입점은 **워크벤치 화면 버튼**(관리자).

## 설계

### 워터마크는 건드리지 않는다

되돌리면 정상 스윕이 같은 구간을 다시 훑고, "성공한 구간 끝까지만 전진" 규율이 깨진다.
백필은 **독립 함수 + 독립 상태 키**(`naver_backfill_state`)로 돌고, 끝나도 워터마크는
제자리다. 중복은 기존 두 겹(사전 `existing_external_ids` + `UNIQUE (channel, external_id)`)이
그대로 막는다.

### 창 순회와 호출 예산

- 하루(23시간 59분) 단위 창을 **과거에서 현재 방향으로** 순회, 창마다 커밋한다
  (중간에 끊겨도 진척이 남는다 — 백필 상태에 `done_through` 기록).
- 창마다: 변경분 1회(+`more` 쪽수만큼) + 상세 `ceil(신규/100)`회. 90일이면 변경분
  최소 90회. 호출 사이 `0.5초` 간격(2 RPS 의 절반) → 90일 백필 ≈ 수 분.
- 워커 동시성 1 이 방벽이다. replica 를 올리지 않는다.

### `more` 페이징 (선행 결함)

지금 `get_last_changed_statuses` 는 `data.more` 를 **안 읽는다**. 한 창에 변경이 300건을
넘으면 조용히 잘린다 — 정상 스윕(5분 주기)에서는 드물지만 하루 창을 훑는 백필은 확실히
걸린다. 클라이언트에서 이어받기를 구현한다(무한 루프 방지 상한 포함).

### 화면

워크벤치 관리 영역에 "과거 주문 소급 수집" — 시작·끝 날짜(기본 90일 전~어제), 실행 버튼,
진행 표시(백필 상태 폴링). 실행은 enqueue 만 하고 네이버 HTTP 는 WORKER 가 낸다.

## Task

| task | 내용 | 완료 기준 |
|---|---|---|
| T1 | 클라이언트 `more` 이어받기 + `limitCount=300` 명시 | 2쪽 이어붙임·`moreSequence` 전달·루프 상한 테스트 green, 기존 client 테스트 green |
| T2 | `backfill.py` — 구간 순회·창마다 커밋·상태 기록·클레임 반영(알림 off)·워터마크 불변 | 신규 테스트: 워터마크 불변·중복 skip·창 분할·중단 후 재개·알림 0건·범위 상한(90일) 초과 거부 |
| T3 | 큐·태스크·라우트 2종(POST 실행 / GET 상태) + 등재 6종 | 등재 계약 테스트 green + smoke 사각 3종(policy manifest·ACTION_LABELS·docs-scope) 직접 실행 |
| T4 | 워크벤치 화면 폼·진행 표시·자산 핀 범프 | 템플릿 계약 green, 핀 `?v=` 계약 파일 전수 일치 |
| T5 | 스테이징 1회 실행 — 보존 기간 실측·링크 증가·붙이기 후보 노출·중복 0·429 0 | 실측값이 원장에 있고, 워크벤치 후보에 과거 집이 뜬다 |
| T6 | 게이트·푸시 | `pre_push_smoke` exit 0 + `gh run list` 전 워크플로 green |
| T7 | (곁가지) 백필 후에도 원본 없는 건 안내 문구 | 잔여가 있을 때만 착수 — 없으면 원장에 "해당 없음" |

## 안 하는 것

- 운영 실행(사용자 승인 후 별도).
- 워커 재배포(큐 전면 정지 — `tools/ops/check_worker_redeploy_safe.py` 로 판정 후 사용자 결정).
- 자동 주문 생성. 백필은 링크만 만든다(붙이기·주문 만들기는 사람이 한다).

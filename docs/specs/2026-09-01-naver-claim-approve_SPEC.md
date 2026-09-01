# 네이버 클레임 승인 — 취소 승인 신설 + 반품 승인 독립 경로 (T9)

> 2026-09-01 · 워크트리 `C:\tmp\nvclaimapv` (base `ffcc47ba3` = origin/deploy)
> 선행: `2026-08-31-naver-return-approve_SPEC.md`(반품 승인, 운영 `c462bdb9`)
> · `2026-08-31-naver-return-reject_SPEC.md`(반품 거부, 운영 ON `7976fb2c`)
> CEO 판정·적대 검수 반영본.

## 1. 문제

화면이 클레임을 **알아차리기만** 한다. 승인은 판매자센터에서 사람이 한다.

- **취소 요청 승인이 없다.** `claim/cancel/approve` 는 저장소 전체 0건
  (`mapping.py:361,371` 의 `cancel_approved_at` 은 네이버가 주는 **읽기** 필드).
- **반품 승인에 독립 경로가 없다.** `_approve_returns`(`fulfillment.py:1000`)는
  `request_return` 안(`:1193`)에서만 불린다. 고객이 먼저 낸 반품은 우리
  `requested_at` 이 없어 pane 의 "승인 남음" 목록(`naver_ingest.py:3559-3568`)에도
  **안 뜬다** — 화면이 재진술조차 안 한다.
- **비대칭이 위험하다.** 고객 반품 앞에서 화면이 내주는 불가역 버튼이 `반품 거부`
  하나뿐이다. 승인 버튼이 없어서 담당자가 거부를 누르게 되는 구조다.

### 1-1. 화면의 "취소 처리 잠김"은 이 스펙이 푸는 것이 아니다

유령 띠 할 일 칸(`naver_workbench.html:178`)의 잠금은
`can_discard = status in ("RECEIVED",) and claim_phase == "done"`(`ghost_orders.py:174`)
— **ERP 휴지통 잠금**이다. 사유가 둘이다:

| 사유 | 이 스펙이 푸나 |
|---|---|
| "네이버가 아직 취소를 확정하지 않았습니다" | **푼다** (승인하면 `claim_phase=done`) |
| "`MEASURE` 단계라 이력이 붙어 있습니다" | **못 푼다** — `DISCARDABLE_STATUSES` 정책 별건 |

스크린샷의 `#5088` 은 **둘 다** 해당한다. 승인해도 그 주문의 ERP 정리는 남는다.

## 2. 규격 (2026-09-01 공식 문서 원문 확인)

정본 `https://apicenter.commerce.naver.com/llms/llms.txt` + endpoint `.md`
+ `wiki-주문-주문-상태-변경-흐름도.md` (로그인·JS 없이 HTTP 200).
원문 사본은 착수 시 원장에 첨부한다 — `approvalData` 사고의 재발 방지.

| 기능 | 엔드포인트 | body | 출발 상태(규정 문장) |
|---|---|---|---|
| 취소 승인 | `POST /v1/pay-order/seller/product-orders/{pid}/claim/cancel/approve` | **없음** | `CANCEL_REQUEST` · `CANCELING` |
| 반품 승인 | `POST .../claim/return/approve` | **없음** | 흐름도 R-1 = `COLLECT_DONE` |

- 응답 `data.successProductOrderIds` / `data.failProductOrderInfos`, idempotent, 400=전이 불가.
- 흐름도 분기 C: `approveCancelApplication` → 환불 → `CANCEL_DONE`.
- **`claim/cancel/reject` 는 존재하지 않는다.** 취소 철회는 구매자만 한다. 만들지 않는다.
- 보류·보류해제는 선행 스펙대로 **영구 비구현**.
  주의: 코드·주석에 보류 API **경로 문자열**을 적으면 CI red
  (`test_naver_return_approve.py:146-147` 가 모듈 소스 전체를 훑는다). 낱말로만 쓴다.

## 3. 범위

### 목표
- **G1 취소 승인** — pane 에서 `claim/cancel/approve` 실행.
- **G2 반품 승인 독립 경로** — 접수와 분리된 승인 버튼을 pane 에 둔다.

### 비목표 (CEO 판정)
- 취소 거부(API 부재) · 보류/보류해제(영구 비구현) · 교환 4종.
- **일괄 승인** — 돈이 건마다 다르다.
- **승인 후 ERP 주문 자동 폐기** — 불가역 둘을 한 버튼에 묶지 않는다. §1-1 은 별건.
- **유령 띠 버튼** — pane 전용. 근거: ① 띠 행에 `link_id` 가 없다(`ghost_orders.py:181-199`)
  ② 띠는 주문 단위·라우트는 집 단위라 부분 승인이 전건으로 보인다
  ③ 같은 행에 `주문 취소 처리`(휴지통·복구 가능)와 `취소 승인`(환불·불가역)이 나란히 서면
  사고 대기 상태다. 띠는 "취소 처리 잠김" 대신 **그 집 pane 링크**로 바꾼다.

## 4. 설계

### 4-1. 클라이언트 (`naver_commerce/client.py`)
`approve_cancel_product_order(pid)` — `approve_return_product_order`(:619)와 같은 모양.
**body 없음, Content-Type 헤더도 없음.** 빈 pid → `ValueError`.
계약 테스트는 `test_naver_return_approve.py:200` 의 AST 판정을 **신규 메서드까지
파라미터화**한다(`json_body` 금지·지어낸 필드 금지·경로 존재).

### 4-2. 서비스 (`naver_commerce/fulfillment.py`)
- `CANCEL_APPROVABLE_STATUSES = ("CANCEL_REQUEST", "CANCEL_REQUESTED", "CANCELING")`
  — 흐름도 규정 문장. `CANCEL_DONE`·`CANCEL_REJECT` 는 계약 테스트의 음성 대조군.
- `is_cancel_approvable(link)` / **`is_return_approvable(link)`** —
  `is_return_rejectable`(:1250)과 같은 3조건(상태 · 보류값 없음 · 우리 표식 없음).
  `is_return_approvable` 는 `RETURN_APPROVABLE_STATUSES`(:996) 4종을 그대로 쓴다
  — **넓히지도 좁히지도 않는다**(운영 25건 전수 관측 근거).
- `approve_cancel(...)` / `approve_return(...)` — 공개 진입점.
  - `_approve_returns`(:1000) **시그니처·부작용을 손대지 않는다**. 래퍼가
    `by_id`(pid→link 전수) 와 `pids`(선별분)를 만들어 넘긴다 → 접수 경로 회귀 0.
  - `_claim_guard`(:312) 를 **부르지 않는다** — 반품 요청 자체가
    `blocks_irreversible=True`(`mapping.py:526-536`)라 전건 거절된다.
  - 대상 0건이면 `reject_return`(:1315)처럼 `FulfillmentError` 를 올린다(조용한 성공 금지).
- 표식은 **네이버 읽기 필드와 이름을 겹치지 않게**:
  `triage_state['cancel']['approved_at' / 'approved_by' / 'approve_skipped_reason']`
  (반품 축 `triage_state['return']` 과 대칭). `_state` 의 `canceled_at`("우리가 취소를 냈다")과
  같은 칸에 섞지 않는다.
- 승인 실패는 `_mark_failures`(:516) 로 fulfillment 축에도 남긴다 — 안 그러면
  `_fulfillment_state.last_error`(`naver_ingest.py:3177-3202`)에 안 들어가 화면이
  "완료"라고 거짓말한다.

### 4-3. 큐·워커
- `queue.py`: `enqueue_naver_cancel_approve` · `enqueue_naver_return_approve`
  (`enqueue_naver_return_reject`:321 과 같은 모양, `job_timeout="5m"`).
- `tasks.py`: action `cancel-approve` · `return-approve` 분기 + **docstring Args 갱신**(:379).
- `REFRESH_AFTER_ACTIONS`(:332)에 둘 추가 → **`test_naver_refresh_after_action.py:124`
  의 완전일치 집합도 같이 갱신**(안 하면 즉시 CI red).
- `FULFILLMENT_ACTION_LABELS`(`naver_ingest.py:2254`)에 새 action 2종 등재.
  미등재 action 은 `:535` 폴백으로 **"발주확인 실패"로 오표기**된다
  (기존 `return-reject` 도 같은 구멍 — 함께 등재하고 폴백 개선은 별건 기록).
- `_fulfillment_state` marks(`naver_ingest.py:3200-3202`)에 승인·거부 표식 추가 —
  안 넣으면 폴링 지문이 안 뒤집혀 화면이 타임아웃까지 "기다리는 중".
- **요청 스레드에서 네이버를 부르지 않는다**(IP 3슬롯 계약). 큐 불가 시 503.

### 4-4. 라우트 (`foms/web/admin/naver_ingest.py`)

| 라우트 | 권한 | 게이트 |
|---|---|---|
| `POST /admin/naver-ingest/<link_id>/cancel-approve` | ADMIN·MANAGER | 워크벤치 + `FOMS_NAVER_CANCEL_APPROVE_ENABLED` |
| `POST /admin/naver-ingest/<link_id>/return-approve` | ADMIN·MANAGER | 워크벤치 + `FOMS_NAVER_RETURN_APPROVE_ENABLED` |

- **게이트 2개로 분리** — 단계 점등(G1 먼저 ON → 진짜 1건 성공 → G2 ON)을 위해.
  배선 3자리: `feature_flags.py` 판정 함수 · `_pane_context`(:1983) 키 · 라우트 가드.
  **web 전용. worker 에 변수를 넣지 않는다**(재배포 = 큐 전면 정지).
- `base_rev` 낙관적 잠금 · 큐 불가 503.
- **감사 action 신규 2종** — 기존 `NAVER_INGEST_RETURN_APPROVE_ENQUEUE`(:160)는
  **접수+승인 체크박스가 이미 쓴다**(`naver_ingest.py:4271`). 재사용하면 "누가 환불을
  냈나"가 안 갈린다. → `NAVER_INGEST_CANCEL_APPROVE_ENQUEUE` ·
  `NAVER_INGEST_RETURN_APPROVE_ONLY_ENQUEUE`
- **OrderEvent 를 승인에도 남긴다** — 거부만 주문 이력에 남고 환불은 안 남는
  장부가 되지 않게. 새 event_type 2종 + `order_event_display.py:444` 분기 등재
  (미등재면 이력이 "변경 이력"으로 추락).

### 4-5. 화면 (`naver_workbench_pane.html` · `naver-workbench.js`)
- 버튼 조건: `can_cancel_approve` = 게이트 ON **and** `cancel_approvable_count > 0`
  **and** role ∈ {ADMIN, MANAGER}. `can_return_approve` 는 `is_return_approvable`
  카운트에 건다 — `return_awaiting_approval`(:3559)에 걸면 **G2 주 대상(고객이 낸 반품)에
  버튼이 안 생긴다**. 라우트 role 과 렌더 조건은 **같은 값**(한쪽만 좁히면 열린 버튼이 403).
- 모달은 불가역 4종 세트 + **건수가 아니라 목록**: 승인 대상 상품주문번호·금액을 줄로
  재진술한다(집 묶기 오판 전력). 버튼 문구에 돈을 넣는다 — "네이버 취소 승인 — 환불 확정".
- 실패는 `failProductOrderInfos` 원문을 그대로 보여준다. 400 을 삼키지 않는다.
- `?v=` 핀 범프(`naver_workbench.html:1191`) — SW staticCacheFirst.

## 5. 등재처 (빠지면 CI red)

1. `docs/harness/foms_write_guard_manifest.json` (`test_write_guard.py:103`)
2. `docs/harness/foms_order_mutation_policy_manifest.json` + `policy_id`
   (`test_auth_enforcement.py:125` — **pre_push_smoke 사각**)
3. `docs/harness/foms_audit_coverage_inventory.json` **재생성**
   (`tools/harness/audit_coverage_scan.py` — 훅 자동 재생성 목록 밖, 수동)
4. `audit_message_display.py` `ACTION_LABELS`
   (`test_admin_audit_screen_readability_3.py:56` — **smoke 사각**)
5. `order_event_display.py` 이벤트 문구 + `OrderEvent` event_type 상수
6. 새 계약 테스트가 `docs/` 를 읽으면 `ci.yml` 문서 서브셋 등재 (CI-DOCSCOPE-01)

## 6. 검증 (완료 기준)

- 신규 계약 테스트 `tests/services/integrations/test_naver_claim_approve.py` —
  거부 37종과 같은 규율: 선로 요청(경로·body 없음·pid 단건) · 게이트 off 403+DOM 부재 ·
  role · 술어 양성/음성 대조군 · 보류 skip · 멱등 · 감사+OrderEvent · `REFRESH_AFTER_ACTIONS`.
- `python -m pytest tests/services/integrations/ tests/domains/test_write_guard.py
  tests/domains/test_auth_enforcement.py tests/domains/test_admin_audit_screen_readability_3.py
  tests/domains/test_audit_coverage_inventory.py -q` 전부 green.
- `python -c "import app; print('APP_OK')"` · `scripts/ops/pre_push_smoke.ps1` exit 0.
- **운영 실호출 검증은 못 한다** — 2026-09-01 스냅샷 대상 0건
  (없음 185 / RETURN_DONE 25 / CANCEL_DONE 18). 게이트 꺼진 채 승격하고,
  진짜 클레임 1건이 올 때 사용자가 G1 부터 켠다.

## 7. 결정 (사용자, 2026-09-01)

- **범위**: G1·G2 **둘 다** 만든다.
- **Q1 권한**: **ADMIN·MANAGER 만** — 반품 거부와 같은 층. 돈이 나가는 판단은 취소처리
  (STAFF 포함)와 같은 등급이 아니다.
- **Q2 게이트**: **2개로 분리**(`FOMS_NAVER_CANCEL_APPROVE_ENABLED` ·
  `FOMS_NAVER_RETURN_APPROVE_ENABLED`) — 단계 점등을 하려면 하나로 묶을 수 없다.
- **Q3 버튼 위치**: **pane 전용**. 유령 띠는 "취소 처리 잠김" 대신 그 집 pane 링크만 낸다.
- **ERP 휴지통 축**(`DISCARDABLE_STATUSES = ("RECEIVED",)`)은 **이번 범위 밖** — 별건으로 둔다.
  §1-1 대로 승인해도 접수 단계를 지난 주문은 계속 잠긴다.

진행 기록: `docs/plans/2026-09-01-naver-claim-approve-ledger.md`

# 주문 변경 사유 (ORDER-REASON-00) — 스펙

- 작성: 2026-08-13
- 상태: **사용자 승인 완료** (2026-08-13 결정 3건 + 플랜 승인)
- 기준 코드: `origin/deploy` `e496a9d2` (worktree `session/reason0813`)
- 선행: ORDER-DIFF-00/01/02(운영 반영) · ORDER-ITEM-UID(deploy, 운영 승격 대기)

## 1. 문제

변경 기록 체인은 "무엇이 어떻게 바뀌었나"까지 답한다. 남은 공백은 **"왜"** 다.
금액·일정·취소 분쟁에서 원장이 값의 변화만 보여주면 "고객이 요청한 변경"과 "우리 입력 실수"가
구별되지 않는다. 둘은 책임 소재가 정반대인데 기록상 동일하게 보인다.

## 2. 결정 (사용자, 2026-08-13)

| 질문 | 결정 |
|---|---|
| 사유를 언제 받나 | **중요한 변경일 때만** (금액·일정·단계/취소) |
| 어떻게 적나 | **목록 선택** 5종 + `기타`만 메모 |
| 인라인 저장 | **저장 후 배너**로 1클릭 첨부(모달 금지 — blur 자동저장 흐름이 끊긴다) |
| 보존 정책 | 운영 실측 먼저(ORDER-RETENTION-00, 별도) — 완전 삭제는 하지 않는다 |

## 3. 설계

### 3.1 판정은 서버 사후 SSOT (핵심 결정)

"이 저장이 중요 변경인가"를 **저장 전에 클라이언트가** 판정하면 경로 목록과 판정 로직이
서버·클라 2벌이 된다(둘이 어긋나는 순간 조용히 안 묻거나 헛묻는다). 그래서 순서를 뒤집는다:

1. 저장은 지금과 똑같이 즉시 성공한다(사유가 저장을 막지 않는다 — 영업 손실 금지).
2. 서버가 이미 계산해 둔 `diff` 로 중요 여부를 판정하고, 응답에
   `change_reason_required: true` + `change_set` 을 실어 보낸다.
3. 화면은 저장 성공 **직후** 사유를 붙인다(PC 전체 저장=모달, 인라인=배너).

판정 로직 1벌, 저장 경로 무영향, PC·인라인·태블릿이 같은 흐름을 쓴다.

### 3.2 중요 경로 (`SENSITIVE_PATH_TEMPLATES`)

`structured_diff` 가 만든 `path` 를 `path_template_of` 로 정규화해 이 집합과 대조한다
(품목 인덱스 무관).

- **금액(입력 경로만, 임계 초과분만)**: `payment.deposit` · `payment.discount` ·
  `payment.free_input` · `items.*.price` — **|변화| ≥ 50,000원 또는 이전 값의 5% 이상**일 때만
  묻는다(사용자 결정 2026-08-13). 숫자로 못 읽는 값은 묻는 쪽으로 본다.
- **일정**: `schedule.measurement.date/time` · `schedule.construction.date/time` ·
  `schedule.as_visit.date/time` · `items.*.measurement_date` · `items.*.construction_date`
- **단계/취소**: `workflow.stage`
- **품목 구성**: `items.*` 의 `op ∈ {add, remove}`

> **`totals.*` 를 뺀 이유 (2026-08-13 구현 중 실측)**: `totals` 는 전부 서버 파생값이다 —
> `structured_form_projection` 이 매 저장마다 품목 단가·`payment` 입력에서 재계산한다
> (`final_amount = balance = contract_total - deposit - discount`). 넣어 두면 저장된 totals 가
> 낡은 주문에서 **전화번호만 고친 저장이 "금액 변경"으로 판정**돼 사유 창이 아무 때나 뜬다
> (테스트로 재현). 진짜 금액 변경은 그 값을 만든 입력 경로가 함께 바뀌므로 놓치지 않는다.
> 품목 통째 추가·삭제는 개별 필드 변경이 아니라 `add`/`remove` 1건으로만 남아 별도로 잡는다.

여기 없는 경로만 바뀐 저장은 사유를 묻지 않는다(기록은 기존대로 남는다).

### 3.3 사유 코드

| code | 라벨 | 메모 |
|---|---|---|
| `customer_request` | 고객 요청 | 선택 |
| `site_condition` | 현장 사정 | 선택 |
| `input_correction` | 입력 오류 정정 | 선택 |
| `internal_adjustment` | 내부 조정 | 선택 |
| `other` | 기타 | **필수**(최대 200자) |
| `unspecified` | (미입력) | 서버 전용 — 화면이 붙이지 않고 지나간 경우의 집계 키 |

라벨은 원장에 굽지 않는다 — 읽는 시점에 표시 SSOT 가 붙인다(ORDER-DIFF-00 과 같은 규칙).

### 3.4 스키마 — `order_change_reasons`

마이그레이션 `orderreason_00_order_change_reasons` (down_revision = `naver_link_00`).

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `id` | BigInteger PK | 원장 계열 공통 |
| `change_set_id` | String(36) NOT NULL **UNIQUE** | 저장 1회 = 사유 1행. `order_field_changes.change_set_id` · `security_logs.detail.change_set` 과 같은 값 |
| `order_id` | Integer NOT NULL | **FK 없음**(감사 원장 공통 — 주문 purge 가 이력을 지우면 안 된다) |
| `reason_code` | String(32) NOT NULL | §3.3 |
| `reason_note` | String(200) NULL | `other` 일 때만 필수 |
| `actor_user_id` | Integer NULL | 사유를 적은 사람(저장자와 다를 수 있다) |
| `created_at` | DateTime NOT NULL | `now_utc_naive` |

인덱스: `ux_order_change_reasons_change_set`(unique) · `ix_order_change_reasons_code_time`
(`reason_code`,`created_at` — "입력 오류 정정 월 몇 건") · `ix_order_change_reasons_order_time`.

**행마다 사유를 복제하지 않는 이유**: 저장 1회의 사유는 하나다. `order_field_changes` 에
컬럼을 붙이면 같은 문자열이 변경 필드 수만큼 늘어나고, 집계는 `DISTINCT` 를 타야 한다.

### 3.5 API

**첨부** `POST /api/orders/<order_id>/change-reason`

```json
{"change_set": "<uuid4>", "code": "customer_request", "note": ""}
```

- 규칙: 해당 change set 이 이 주문 것이어야 한다 / 저장 후 **24시간 이내**만 첨부 가능
  (무한 소급 입력 방지) / 본인 change set 만, ADMIN 은 전체 / **이미 사유가 있으면 409**
  (감사 원장은 덮어쓰지 않는다).
- 감사 action `ORDER_CHANGE_REASON_SET` — `ACTION_LABELS` 등재 필수.

**저장 응답 확장** — `PUT /api/orders/<id>/structured` · `PATCH .../structured/fields`
성공 응답에 `change_reason_required`(bool) · `change_set`(str) 추가. 기존 키는 그대로 둔다.

**조회 확장** — `GET /api/orders/<id>/field-changes` 의 change set 마다
`reason: {code, label, note}` 또는 `null`.

### 3.6 detail 예산

`security_logs.detail` 에는 `reason_code` 만 넣는다(≈40바이트). `_DETAIL_CHANGES_BUDGET`
3,200 을 건드리지 않도록 **변경 목록보다 먼저** 예산에서 뺀다.

## 3.7 빈도 실측 (2026-08-13, 운영 데이터 83개 저장 묶음)

| 규칙 | 사유를 묻는 비율 |
|---|---|
| 금액 무조건(초안) | 67% |
| **금액 임계 5%/5만원(채택)** | **63%** |
| 금액 10만원 이상 | 61% |
| 금액 축 제외(일정·단계·품목만) | 40% |

축별 기여: 금액 49% · 일정 34%(시공일 27%가 최대) · 품목 추가삭제 13% · 단계 0%.

> **금액 임계로는 빈도가 거의 안 줄어든다**(67 → 63%). 대부분의 저장이 일정도 함께 건드리기
> 때문이다. 빈도를 실제로 줄이려면 **일정 축**(특히 시공일)을 손봐야 한다 — 초안 리포트의
> "C안 30~40% 추정"은 실측으로 반증됐다. 임계 자체는 잔돈 조정을 걸러내는 값이므로 유지한다.

## 4. 비목표

- 보존/아카이브 **구현** (ORDER-RETENTION-00 실측 후 별도 승인)
- 되돌리기(revert), 과거 change set 소급 입력(24시간 창 밖)
- 사유 통계 화면 — 원장 질의로 가능하게 만드는 것까지가 이번 범위

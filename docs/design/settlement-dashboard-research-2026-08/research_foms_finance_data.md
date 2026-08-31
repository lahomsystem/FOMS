# FOMS 정산 대시보드 설계용 재무 raw data 전수 인벤토리

조사일 2026-08-31, 읽기 전용 (코드 미수정). 브랜치 `deploy`.

---

## 0. 핵심 요약 (TL;DR)

- Order 테이블에는 `deposit_amount`/`balance_amount` 컬럼이 **없다**. 그 이름의 컬럼은
  `OrderEstimate`(견적서, models.py:1485-1486)에만 있고, 실제 주문 금액 SSOT는
  `structured_data`(JSONB) 안 `payment.*`/`totals.*` 키다.
- 출고가(grand total) 공식은 **한 곳에 고정**되어 있다:
  `foms/services/erp_display.py:297-323` `erp_shipping_price_from_structured()`
  → `max(0, 품목합(items_total) + 자유입력(free_input) - 할인(discount))`
- 잔금 = 출고가 − 예약금. 단, **읽기 경로가 3갈래**로 나뉘어 있어 낡은 `totals`가 저장된
  주문에서는 화면마다 잔금이 살짝 달라질 수 있다 (§2 참고). 정산 대시보드는 이 드리프트를
  피하려면 반드시 하나의 소스만 채택해야 한다.
- 이미 "정산" 이름이 붙은 화면이 존재한다: `foms/web/cs/completion_dashboard.py`
  (시공완료 대시보드, 태블릿 금액 그리드 + KPI + CSV 내보내기). 신규 정산 대시보드는
  이 화면과 기능이 겹칠 가능성이 높다 — 설계 전 이 파일을 반드시 참고.
- 로컬 postgres MCP 조회는 **연결됐지만 데이터가 QA 시드 10건뿐**(운영 데이터 아님).
  월별 규모 실측은 이번 조사에서 불가 — §4에 근거와 대안 표기.
- 네이버 채널 연동은 **v1 스펙이 "승인 대기" 상태**(`docs/specs/2026-08-13-naver-order-ingest_SPEC.md`)이고,
  반품·취소·교환 동기화는 v1 비목표로 명시되어 있다. `external_order_links` 테이블(채널 구분 SSOT 후보)은
  마이그레이션·모델은 존재하나 읽기 화면에서 아직 널리 조인되지 않는다.

---

## 1. models.py Order 모델 전체 금액/날짜/상태 컬럼

`Order` 클래스: `models.py:21-202`

| 컬럼 | 라인 | 타입 | 용도/비고 |
|---|---|---|---|
| `received_date` | 25 | String | 접수일(레거시, non-ERP 주문용 문자열 날짜) |
| `received_time` | 26 | String | 접수시각(레거시 문자열) |
| `status` | 33 | String, idx | 워크플로 상태(§4 값 목록) |
| `original_status` | 34 | String | 상태 강제변경 전 원래 값 보관 |
| `deleted_at` | 35 | String | soft-delete 마커(NULL 아니면 삭제됨) |
| `created_at` | 36 | DateTime | 행 생성 시각(자동, `datetime.datetime.now`) — **ERP 주문 접수일 대체 후보** |
| `measurement_date` | 39 | String | 실측일(레거시). ERP 주문은 값이 들어오지만 **실제 SSOT 아님** |
| `measurement_time` | 40 | String | 실측시간 — **ERP 주문은 사실상 항상 NULL**(§3 함정) |
| `completion_date` | 41 | String | 설치완료일(레거시) — ERP 주문에서는 안 채워짐(로컬 시드 실측 8/8 NULL, §4) |
| `manager_name` | 42 | String | 담당자 |
| `payment_amount` | 43 | Integer, default 0 | **결제 금액(예약금) 플랫 동기화 컬럼**. `foms/services/erp_sync_columns.py:57-59`가 `erp_deposit_amount_from_structured()` 결과를 매 저장 시 이 컬럼에 미러링(SQL 레벨 검색/정렬용, JSONB 파싱 회피) |
| `scheduled_date` | 46 | String | 설치 예정일 |
| `as_received_date` | 47 | String | AS 접수일 |
| `as_completed_date` | 48 | String | AS 완료일 |
| `is_regional` | 51 | Boolean | 지방 주문 |
| `is_self_measurement` | 52 | Boolean | 자가실측 |
| `is_cabinet` | 54 | Boolean | 수납장 주문 |
| `cabinet_status` | 55 | String | RECEIVED/IN_PRODUCTION/SHIPPED |
| `regional_*` (업로드/발송 플래그 5종) | 56-63 | Boolean/String | 지방 주문 관리 체크리스트 |
| `construction_type` | 62 | String(50) | 시공 구분 |
| `shipping_scheduled_date` | 66 | String | 상차 예정일 |
| `shipping_fee` | 69 | Integer, default 0 | **배송비**(수납장 대시보드용 — structured_data 자유입력 배송비와 별도 축) |
| `blueprint_image_url` | 72 | Text | 도면 이미지 |
| `lat`/`lng`/`geocode_status`/`geocoded_at`/`address_hash` | 77-81 | — | 지오코딩(비금액) |
| `is_erp_order` | 87 | Boolean, idx | ERP 구조화 주문 여부 |
| `raw_order_text` | 88 | Text | 원문 붙여넣기 |
| `structured_data` | 89 | JSONB | **금액/일정 정본 저장소** |
| `structured_schema_version` | 90 | Integer | 스키마 버전 |
| `structured_confidence` | 91 | String(20) | 파서 신뢰도 |
| `structured_updated_at` | 92 | DateTime | JSONB 최종 수정 시각 |
| `mutation_version` | 96 | Integer | 낙관적 잠금(REV-00) |
| `erp_measurement_date` | 99 | String(10), idx | 실측일 플랫 동기화(첫 날짜만, §3 함정) |
| `erp_construction_date` | 100 | String(10), idx | 시공일 플랫 동기화(첫 날짜만) |
| `erp_stage_code` | 103 | String(30), idx | 워크플로 stage 플랫 컬럼 |
| `erp_urgent` | 104 | Boolean, idx | 긴급 플래그 |
| `erp_drawing_updated_at` | 105 | DateTime | 도면 단계 갱신 시각 |
| `erp_stage_updated_at` | 106 | DateTime, idx | **stage 전이 진실값**(대시보드 60일 컷오프 기준, 160-192행) |
| `erp_owner_team_code` | 107 | String(20), idx | 담당 팀 |
| `erp_phone_digits` | 108 | String(20), idx | 전화 숫자만(검색용) |
| `channel_source_seq` | 113 | Integer, default 0 | ChannelTalk 연동 시퀀스(**주문 유입 채널과 무관** — 상담 메시지 동기화용) |

관련 다른 모델:

- `OrderScheduleDate` (`models.py:205-236`): `order_id`, `kind`('measurement'/'construction'/'shipping'/'as_visit' 등), `date`, `source`, `item_index`, `item_id`. **복수 일정 SSOT**(§3).
- `OrderEstimate` (`models.py:1456-1522`): 견적서/계약서. `total_amount`(1484), `deposit_amount`(1485), `balance_amount`(1486), `payment_info`(JSONB, 1488), `status`(1490, DRAFT 등), `estimate_date`/`construction_date`(문자열). **주문 본체와 별개 레코드** — N건 발급 가능.
- `ExternalOrderLink` (`models.py:3283-`): 외부 채널 연동 링크(§4). `channel`(String(20), default 'NAVER'), `external_id`, `order_id`(FK, SET NULL), `raw_snapshot`(JSONB, 원본 응답), `sync_status`('LINKED'/'PENDING_REVIEW'/'FAILED').
- `NotificationEvent.channel`(1402), `ChannelDeliveryLog`(1558-)의 `source_type`/`target_type` — 이름은 "channel"이지만 **알림 발송 채널**(카카오/웹푸시 등)이지 주문 유입 채널이 아니다. 정산 설계 시 혼동 주의.

---

## 2. structured_data(JSONB) 안 금액 관련 키 전수 + 출고가 계산 SSOT

### 2.1 실제 운영 JSONB 형태 (로컬 DB 실측 샘플, 스키마 신뢰 가능)

```json
"totals": {
  "items_total": 670000,
  "free_input_amount": 0,
  "contract_total": 670000,
  "deposit_amount": 0,
  "discount_amount": 0,
  "balance_amount": 670000,
  "final_amount": 670000,
  "shipping_price": 670000
},
"payment": {  // 폼 입력 원본(선호 소스)
  "deposit": ..., "discount": ..., "free_input": "...",
  "cash_receipt": "...", "balance_note": "...",
  "deposit_confirmed": bool, "balance_confirmed": bool
},
"payments": { ... }  // 레거시 폴백 블록(구주문). {"value"/"raw": ...} dict 형태 가능
```

### 2.2 키·추출 함수 인벤토리

| structured_data 경로 | 의미 | 추출 함수 | 경로:라인 |
|---|---|---|---|
| `payment.deposit` / `payments.deposit` | 예약금(선금) | `erp_deposit_amount_from_structured` | `foms/services/erp_display.py:261-276` |
| `payment.deposit` (중복 구현) | 동일 | `_extract_deposit_amount` | `foms/services/orders/structured_form_projection.py:212-222` |
| `totals.items_total` 또는 `items[].price` 합 | 품목합 | `erp_payment_amount_from_structured` | `foms/services/erp_display.py:279-294` |
| `items[].price` | 품목 단가(원 정수 정규화) | `_erp_coerce_item_price_krw` | `foms/services/erp_display.py:198-215` |
| `payment.discount` 또는 `totals.discount_amount` | 할인 | `_extract_discount_amount` | `foms/services/estimate_service.py:225-236` |
| `payment.free_input` (텍스트, "라벨:금액" 멀티라인) | 자유입력(배송비 등 잡금액) | `_extract_free_input_text` / `_extract_free_input_amount` | `foms/services/estimate_service.py:239-251, 297-304` |
| `payment.cash_receipt` | 현금영수증 요청 자유텍스트 | `_payment_text_value` | `foms/services/order_payment_sync.py:70-94` |
| `payment.balance_note` | 잔금 메모 | 〃 | 〃 |
| `payment.deposit_confirmed` / `payment.balance_confirmed` | 입금 확인 토글 | `_payment_bool_value` | `foms/services/order_payment_sync.py:97-120` |
| `flags.factory2` | 2공장 전용 결제계좌 여부 | `is_factory2_order` | `foms/services/orders/structured_form_projection.py:314-319`(estimate_service 버전 별도) |
| `settlement.deductions[]` (department/amount/reason/created_by) | **정산 차감 항목**(비용 청구) | `_completion_settlement_memo` | `foms/web/cs/completion_dashboard.py:417-442` |
| `settlement.cash_receipt.{issued, note}` | 현금영수증 발행 기록 | `_cash_receipt_issued` | `foms/web/cs/completion_dashboard.py:88-102` |
| `shipment.as_billing.{type('free'/'paid'), amount, reason, confirmed, decided_at, decided_by}` | **AS 유상/무상 청구** | `as_billing_badge_kind` / `as_billing_state_text` | `foms/services/as_dashboard_display.py:259-289` |
| `as_lifecycle.cycles[].billing_snapshot` | AS 사이클별 청구 스냅샷(이력) | — | 로컬 샘플 실측(주문 id=5) |
| `naver.payment.{means, coupons, unit_price, option_price, product_discount_amount, expected_settlement_amount, paid_at}` | 네이버 원본 결제 스냅샷(수집 시 원문 보존, **화면 표시용 아님**) | — | 로컬 샘플 실측(주문 id=3), §4 |
| `naver.claim.{type, label, reason, status, blocking, requested_at}` | 네이버 클레임(반품/교환/취소) 메타 — **금액 필드 없음**(v1 비목표라 매핑 안 됨) | — | 로컬 샘플 실측 |
| `naver.grouped_count` | 네이버 "집"(가구) 단위 묶음 개수 | — | 로컬 샘플 실측 |
| `pricing.extra_payments[]` | 추가 결제 목록(레거시/일부 주문만, 빈 배열 다수) | — | 로컬 샘플 실측(id=2) |
| `pricing.contract_total` / `pricing.total` / `pricing.balance` / `pricing.deposit` | 레거시 pricing 블록 폴백 | `mobile_amount_summary` | `foms/services/erp_mobile_order_display.py:355-367` |

### 2.3 출고가·잔금 계산 SSOT — 원문 인용

**공식 출고가 정의(정책, `foms/services/erp_display.py:299-304`):**

> 출고가 = max(0, 품목합 + 자유입력(배송 등) - 할인)로, 읽기전용 요약 표면
> (대시보드 상세·모바일 상세·실측 readonly)이 표시하는 grand total이다.
> 잔금 = 출고가 - 예약금 관계를 유지하며, 저장된 totals.items_total(품목합)은
> 바꾸지 않고 파생만 한다.

**서버 저장 시점 재계산(신뢰 소스, `foms/services/orders/structured_form_projection.py:114-163`
`recompute_totals()`):** 저장(PUT) 때마다 클라이언트가 보낸 `totals`는 **폐기**하고
`items[].price` + `payment.free_input` + `payment.discount` + `payment.deposit`에서
서버가 전량 재계산 후 `structured_data['totals']`에 기록:
```python
contract_total = items_total + free_input
balance = max(0, contract_total - deposit - discount)
totals = {
    "items_total": items_total, "free_input_amount": free_input,
    "contract_total": contract_total, "deposit_amount": deposit,
    "discount_amount": discount, "balance_amount": balance,
    "final_amount": balance, "shipping_price": max(0, contract_total - discount),
}
```

**주의 — 읽기 경로 3갈래 드리프트 위험:**
1. `erp_display.py`/`estimate_service.py` (대시보드 상세·완료 대시보드·이력 시트): 저장된
   `totals`를 **무시**하고 items/payment에서 매번 재파생.
2. `structured_form_projection.recompute_totals`: **저장 시점**에만 재계산해 `totals`에 기록.
3. `erp_mobile_order_display.mobile_amount_summary` (`foms/services/erp_mobile_order_display.py:332-347`,
   원문 인용): "**다만 파생 소스는 완료 대시보드·이력 시트와 다르다.** 그 둘은 저장 totals 를
   무시하고 매번 재파생하는데, 여기서는 저장된 `totals.final_amount`/`balance_amount` 를 먼저
   쓰고 없을 때만 재파생한다. totals 가 낡은 주문에서는 두 화면의 잔금이 갈릴 수 있다."

→ **정산 대시보드를 새로 만든다면 `erp_shipping_price_from_structured` +
`estimate_service._balance_after_payments` 계열(항상 재파생, 저장값 불신)을 채택하는 것이
가장 안전** — 이미 완료 대시보드·이력 화면이 이 방식을 쓴다.

**PAYMENT_CHANGED 감사 이벤트(`foms/services/order_payment_sync.py`):** 금액 관련 쓰기 경로가
전체저장 PUT·결제확인 토글·자동저장·워커 등 여러 곳에 흩어져 있어, `Session.before_flush`
단일 지점에서 `payment.deposit`/`discount`/`free_input`/`cash_receipt`/`balance_note`/
`deposit_confirmed`/`balance_confirmed` 7개 필드의 변경을 `OrderEvent(event_type='PAYMENT_CHANGED')`로
감사 기록한다(43-51행 필드 목록). **정산 대시보드의 "변경 이력" 요구가 있다면 이 이벤트를
그대로 재사용 가능.**

---

## 3. 날짜 축 후보와 함정

| 후보 | 위치 | 상태 |
|---|---|---|
| `Order.received_date` | models.py:25 | 레거시 non-ERP 문자열 날짜. ERP 주문에도 값은 들어가지만 접수 "시각"까지는 없음 |
| `Order.created_at` | models.py:36 | 행 생성 datetime. **ERP 주문 접수일 축으로는 이게 정확** — 부트스트랩/백필이 아닌 한 실제 접수 시각과 일치 |
| `Order.measurement_time` | models.py:40 | **함정: ERP 주문은 사실상 항상 NULL.** `foms/services/measurement_time.py:1-14` 모듈 docstring 원문: "ERP 주문은 `orders.measurement_time` 컬럼이 비어 있고(운영 확인: 실측 일정이 잡힌 ERP 주문 전부 NULL) 실제 시각은 `structured_data.schedule.measurement.time`에 자유 텍스트로 들어간다." 로컬 시드로도 재확인(§4, has_measurement_time=0/8) |
| `structured_data.schedule.measurement.time` | — | 실측 시각 **정본**(자유텍스트: "10시"/"오후"/"1시~2시" 등). 정렬 키는 `foms/services/measurement_time.py:71-`의 `parse_measurement_time_minutes()`가 분단위 정수로 통일 |
| `Order.erp_measurement_date` / `erp_construction_date` | models.py:99-100 | 플랫 동기화 컬럼(D-day SQL 필터용, 인덱스 있음). **첫 날짜만** 담는다 — 복수 일정(콤마 구분) 주문에서는 불완전 |
| `OrderScheduleDate` 테이블 | models.py:205-236 | **복수 일정 SSOT.** `kind`별(`measurement`/`construction`/`shipping`/`as_visit`) 1:N 행. 날짜 술어(대시보드 카운트 등)는 반드시 이 테이블 EXISTS 조인으로 판정해야 한다 — `foms/services/orders/dashboard_control_tower.py:52-70` 주석: "erp_measurement_date/erp_construction_date 싱크 컬럼은 첫 날짜만 담는다. 날짜 술어는 전 날짜를 행으로 펼친 order_schedule_dates EXISTS/조인이 정본" |
| `Order.completion_date` | models.py:41 | 레거시 "설치완료일" 컬럼. **ERP 주문에서는 비어 있음**(로컬 시드 실측: is_erp_order=True 8건 전부 completion_date NULL, §4) |
| `structured_data.schedule.construction.date` | — | 완료 대시보드가 실제로 쓰는 "완료일" — `foms/web/cs/completion_dashboard.py:140` `((sd.get("schedule") or {}).get("construction") or {}).get("date")`. **정산 대시보드의 "완료월" 축은 이 경로를 따라가야 함** (`_completion_month_key`, 51-65행) |
| `Order.erp_stage_updated_at` | models.py:106 | stage 전이 진실값(대시보드 활성 컷오프 기준, 160-192행) — 정산 마감 판정에 쓸 수 있는 "최근 상태 변경 시각" 축 |
| `structured_updated_at` | models.py:92 | JSONB 최종 수정 시각 — 활성 필터 폴백 축(dashboard_active_filter 3단 폴백 179-189행) |

**요약 함정 패턴**: `measurement_time`뿐 아니라 `completion_date`도 ERP 주문에서는 레거시
컬럼이 비고 structured_data가 정본인 동일 패턴이 반복된다. 정산 대시보드 설계 시 **레거시
문자열 컬럼을 날짜 축으로 채택하기 전 반드시 `is_erp_order=True` 모집단에서 NULL율을 확인할 것.**

---

## 4. 채널·상태·AS/반품 금액 흐름

### 4.1 상태(status)·stage 값 목록

`foms/services/orders/erp_policy_constants.py:14-26` `STAGE_LABELS`:

| 코드 | 라벨 |
|---|---|
| RECEIVED | 주문접수 |
| MEASURE | 실측 |
| DRAWING | 도면 |
| CONFIRM | 고객컨펌 |
| PRODUCTION | 생산 |
| CONSTRUCTION | 시공 |
| CS | CS |
| COMPLETED | 완료 |
| AS | AS처리 |
| AS_RECEIVED | AS접수 |
| AS_COMPLETED | AS완료 |

그 외 `Order.status`에서 실제 쓰이는 값: `DRAFT`(ERP draft, `Order.erp_draft_filter`,
models.py:132-143), `DELETED`(soft-delete, `not_deleted_filter`, models.py:126-130).
정산 알림 대상 상태 SSOT: `ORDER_SETTLEMENT_ALERT_TARGET_STATUSES = ("COMPLETED", "AS_RECEIVED", "AS_COMPLETED")`
(`erp_policy_constants.py:11`) — **이미 "정산 대상"이라는 개념이 상태값 3종으로 코드에 존재**.

### 4.2 채널 구분(네이버 등 유입)

- **채널 SSOT 후보**: `ExternalOrderLink.channel`(`models.py:3283-`, 마이그레이션
  `migrations/versions/naver_link_00_external_order_links.py`). `UNIQUE(channel, external_id)`,
  기본값 `'NAVER'`. 채널 확장(쿠팡 등)을 막지 않는 설계.
- **주의**: 이 테이블은 v1 스펙(`docs/specs/2026-08-13-naver-order-ingest_SPEC.md`, 상태
  "**승인 대기**")의 산출물로, **신규 주문 자동 수집(생성 방향)만 목표**다. 원문 인용
  (SPEC 50-55행): "비목표 (v1에서 안 한다) — ... 역방향 쓰기(발주확인·발송처리·송장 push) ...
  다채널(쿠팡·11번가 등) 일반화 ... **반품·교환·취소 동기화**." 즉 **반품/취소 금액 동기화는
  현재 스코프 밖**이며, `structured_data.naver.claim`은 상태/사유 메타만 있고 금액 필드가 없다
  (로컬 샘플 실측, §2.2).
- `Order.channel_source_seq`(models.py:113)와 `ChannelDeliveryLog`/`NotificationEvent.channel`은
  **채널톡/알림 발송 채널**이지 주문 유입 채널이 아니므로 혼동 주의.
- `structured_data.naver.source = 'NAVER_SMARTSTORE'` 같은 값도 실측됨(로컬 샘플 id=3) — 유입
  채널 판정에 `ExternalOrderLink` 조인 대신 이 필드를 직접 읽는 것도 가능해 보이나, 이 필드가
  전량 채워지는지(비-네이버 주문은 키 자체가 없는지)는 이번 조사에서 코드로 확인하지 못함
  (추가 조사 필요 항목으로 남김).

### 4.3 AS/반품 금액 흐름

- **AS 유상/무상 청구**: `structured_data.shipment.as_billing`
  `{type: 'free'|'paid', amount, reason, confirmed, decided_at, decided_by}`.
  배지 SSOT: `as_billing_badge_kind()` → `'paid' | 'paid_unconfirmed' | 'undecided' | None(무상)`,
  `foms/services/as_dashboard_display.py:259-277`. 상태 텍스트 SSOT:
  `as_billing_state_text()`(279-289행, 예: "유상 확정 · 150,000원").
- **AS 사이클 이력**: `structured_data.as_lifecycle.cycles[]`(cycle_id/opened_at/transitions/
  billing_snapshot) — 청구 판정이 사이클마다 스냅샷으로 남는다(로컬 샘플 id=5 실측, 2회
  AS 사이클 모두 `type: 'free'`).
- **반품(네이버)은 실물 반환 없이 금액만 움직인다** — 프로젝트 메모리 확정 사실(가구는
  시공 제품이라 발송 후 "반품"은 금전 클레임뿐). 이번 코드 조사로는 반품 시 실제 환불액이
  적립되는 structured_data 키를 찾지 못했다 — `naver.claim`에는 상태/사유만 있고 금액이 없어
  (§2.2), **반품 금액 자체는 현재 FOMS 안에 구조화 데이터로 존재하지 않는 것으로 보인다**
  (§6 갭 참고).
- **정산 차감(settlement.deductions[])**은 AS/시공 이후 비용 청구(부서 귀속: 영업/도면/공장/
  시공팀/고객, `SETTLEMENT_DEPARTMENT_OPTIONS`, `foms/web/cs/completion_dashboard.py:35-41`)이며
  AS 청구(as_billing)와는 별개 축이다 — 하나는 "AS가 유상인가", 다른 하나는 "정산 시 어느
  부서 비용으로 얼마를 차감하는가".

---

## 5. 실데이터 규모 감각

**postgres MCP 연결 성공, 그러나 로컬 dev DB(`furniture_orders`)는 QA 시드 10건뿐 —
운영 규모 실측 불가.** (프로젝트 메모리 `project_local_dev_db_drift` 기지 사실과 일치.)

```
SELECT current_database(), count(*) FROM orders;
→ furniture_orders, 10건
```

- status 분포(로컬 시드, **비대표**): AS_RECEIVED 5 / RECEIVED 3 / AS_COMPLETED 2 — 이름(`QA 관리자`,
  `al_...` id 패턴)으로 볼 때 E2E 테스트 픽스처.
- ERP 주문(is_erp_order=True) 8건 중 `measurement_date`/`scheduled_date`는 8/8 채워짐, `measurement_time`/
  `completion_date`/`erp_measurement_date`/`erp_construction_date`는 8/8 NULL — §3 함정의 방향성은
  재확인했으나, 표본이 작아 "운영 확인"이라는 measurement_time.py의 기존 주장을 이번 조사가 갈음하지는
  못한다(그 주장은 코드 주석상 별도 운영 조사 근거).
- **월별 주문수·출고가 합계·예약금/잔금 분포는 이번 세션에서 실측 불가.** 대체 근거:
  - `Order.dashboard_active_filter(days=60)`(models.py:160-192)가 "완료 후 60일 경과분 제외"를
    기본 대시보드 모집단으로 삼는다는 사실 자체가, 활성 주문 규모가 일 단위 대시보드 렌더링에서
    다뤄질 만한(수백~수천 이하) 스케일임을 시사한다 — 그러나 이는 설계상 추론이지 측정치가 아니다.
  - 과거 세션 메모리에 "수도권 444건", "45집"류 부분 모집단 숫자가 등장하나, 이는 각기 다른 버그
    조사의 특정 필터 결과이며 **월별 총량이나 금액 스케일의 근거로 재사용하기에는 부적합**하다
    (표본 정의가 다르고, 이번 조사로 재검증하지 않음). 정확한 월별 규모·금액 스케일은 운영 DB
    직접 조회(`docs/guides/REAL_SERVER_TEST_ACCOUNT.md` 절차, 별도 승인 필요)로 후속 조사 권장.

**결론**: 정산 대시보드의 "규모" 전제(월 몇 건, 평균 출고가 등)는 **이번 조사로 확정하지 못했다.**
설계 전 운영 DB 판독 전용 조회(1회, 사용자 승인 하) 또는 Railway `DATABASE_PUBLIC_URL` 읽기전용
경로(`project_production_live_diagnosis_recipe` 메모리 참고)로 별도 실측을 권장한다.

---

## 6. 미래 기능별 필요 데이터 갭

| 미래 기능 | 현재 있는 것 | 없는 것(추가 필요 데이터) |
|---|---|---|
| **결제 수단** | `naver.payment.means`(네이버 수집 주문 원본에만, 화면 미노출) | 일반(비네이버) 주문의 결제수단 필드 자체가 없음. 계좌이체/카드/현금 구분을 `payment.*`에 신규 키로 추가 필요. 카드 결제 시 PG 수수료율도 별도 필요 |
| **수금 일자 기록** | `payment.deposit_confirmed`/`balance_confirmed`(bool 토글만) + `PAYMENT_CHANGED` 이벤트(변경 시각은 `OrderEvent.created_at`으로 간접 추적 가능) | 토글이 **언제** True가 됐는지는 이벤트 로그를 역산해야 함 — 직접 조회용 "입금 확인일" 필드(`payment.deposit_confirmed_at`/`balance_confirmed_at`) 부재. 부분 입금(분할 수금) 이력도 구조 없음 |
| **정산 마감** | `settlement.deductions[]`(비용 차감), `SETTLEMENT_DEPARTMENT_OPTIONS`(부서 귀속) — 완료 대시보드에 "정산상태: 완료/대기" 2단계만 존재(`settlement_issued` bool, `foms/web/cs/completion_dashboard.py:163-165`) | 마감 확정 시각·마감 책임자·마감 취소(재오픈) 이력 없음. 월별 마감 잠금(마감 후 금액 수정 차단) 개념 없음 |
| **세금계산서** | 없음(전수 검색 결과 무매치) | 발행 여부/번호/발행일/사업자등록번호 매핑 전부 신규. `settlement.cash_receipt`(현금영수증)와 유사한 `settlement.tax_invoice{issued, number, issued_at, business_no}` 신설이 자연스러운 확장 지점 |
| **채널 수수료(네이버 등)** | `naver.payment.expected_settlement_amount`(네이버 정산 예정액, 수집 원본에만 존재·미가공) | FOMS 쪽 출고가와 네이버 정산액의 **차액(수수료)**을 계산/저장하는 로직이 없음. 채널별 수수료율 마스터 테이블도 없음. `ExternalOrderLink.raw_snapshot`을 파싱하면 원본은 있으나 정형화된 필드로 승격되어 있지 않음 |
| **반품/취소 환불액** | `naver.claim.{type,status,reason}`(상태 메타만) | 환불 금액 자체가 구조화되어 있지 않음(§4.3). v1 스펙이 명시적으로 반품 동기화를 비목표로 뒀기 때문 — 후속 스펙 필요 |

---

## 조사 메모(완료 기준 대비)

- 5개 섹션 모두 채움.
- 로컬 postgres MCP 조회는 **성공**했으나 데이터가 QA 시드 10건뿐이라 운영 규모 실측에는
  사용하지 못함 — §5에 근거·대안 명시.

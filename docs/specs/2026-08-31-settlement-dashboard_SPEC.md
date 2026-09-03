# 정산 대시보드 v1 (SETTLE-DASH-01) — 실구현 스펙

- 작성: 2026-08-31
- 상태: **승인됨 (2026-08-31, 사용자)** — 운영 DB 읽기전용 실측(Q1·Q2 카운트 동승) 1회도 함께 허용됨. 구현은 새 세션에서 M1부터.
- 목업 확정본: `docs/design/mockups/settlement-dashboard-v1-executive.html` (V1 경영진 스타일, 색상 전략 B+D+매출 막대 금액구간 램프 적용 — `docs/plans/2026-08-31-settlement-dashboard-mockup-ledger.md` T11·T13)
- 근거 리서치: `docs/design/settlement-dashboard-research-2026-08/` 5파일. 본 스펙의 경로:라인 인용은 전부 2026-08-31 deploy 트리에서 재검증했다.
- 관련: 완료 대시보드(`foms/web/cs/completion_dashboard.py`), AUTH 정책 SSOT(`foms/services/orders/order_mutation_policy.py`), NAVER-INGEST-01(`docs/specs/2026-08-13-naver-order-ingest_SPEC.md`)

> 인용 정정: `research_personas.md` 는 정책 레지스트리를 `erp_policy_permissions.py` 로 인용했으나,
> `POLICY_REGISTRY`/`evaluate_policy`/`user_can`/`user_can_read_order` 의 실제 위치는
> `foms/services/orders/order_mutation_policy.py` 다(라인 번호는 리서치 인용과 일치 — 102/114/216/289/482).
> `erp_policy_permissions.py`(129줄)는 도메인 수정 헬퍼만 담는다. 본 스펙은 실경로 기준으로 쓴다.

---

## 1. 목표 / 비목표

**목표 (v1) — 읽기 전용 집계 대시보드 1페이지**

1. **날짜별 출고가 매출**: 일/주/월 granularity + 전월 비교 + 누적 보기 (목업 필터바 실동작 사양 그대로).
2. **수금·미수**: 미수금 잔액 KPI + 미수금 aging 버킷(≤7/8–30/31–60/61–90/91+일).
3. **채널·단계 집계**: 채널별(일반/네이버) 매출 비중, 진행 단계별 물린 금액.
4. **정산 처리 현황**: 청구완료/대기 비율, 현금영수증 발행 대기 건수, AS 유상 확정, 부서 귀속 차감 합.
5. 완료 대시보드의 **200건 캡에 영향받지 않는 전량 집계** (§4).
6. 신규 **read-only 권한 정책** `SETTLEMENT_DASHBOARD_READ` 게이트 (§5).

**비목표 (v1에서 안 한다 — §11 로드맵으로 분리)**

- 원가/마진 — 데이터 자체가 코드베이스에 없다(`research_personas.md` 부록: `margin|cost_price|원가` 전수 grep 무매치).
- 매출 목표 입력·목표 대비 진행률 (목업 "예정" 배지 카드).
- 현금흐름 30일 예측 (목업 "예정" 배지 카드).
- 월 마감 잠금·마감 확정 이력.
- 세금계산서, 채널 수수료 자동 대사, 반품 환불액 집계.
- 수금일(입금 확인일) 실기록 — 현재는 `deposit_confirmed`/`balance_confirmed` bool 토글뿐(§3.5 근사 정의).
- **쓰기(mutation) 일절 없음.** 정산 청구·현금영수증 발행·입금 확인 액션은 기존 완료 대시보드
  (`foms/web/cs/completion_dashboard.py` + `foms/api/cs/dashboard.py`)가 계속 담당한다.

---

## 2. 왜 새 화면인가 (기존 화면과의 관계)

이미 "정산" 이름이 붙은 화면이 있다: 완료 대시보드 태블릿 금액 그리드
(`foms/web/cs/completion_dashboard.py` — 행 파생 `_completion_row` :125-184, KPI `_compute_completion_kpis` :219-247, CSV :563-595).
그러나 이 화면은 **작업 큐**다:

- 로더가 최신 **200건 캡**(`_COMPLETION_BROWSE_LIMIT = 200`, `foms/api/cs/dashboard.py:41`, 적용 :155)
  — 전사 월별 집계에 쓰면 과소 산정된다.
- 집계가 행 단위 파이썬 후처리(월 필터·KPI)라 기간 축 차트·전월 비교가 없다.

정산 대시보드 v1은 이 화면의 **파생 규칙(금액·상태·완료일)은 전부 재사용**하고, 모집단·집계만 새로 만든다.

---

## 3. 데이터 계약

### 3.1 금액 — 항상 재파생, 저장 totals 불신 (절대 규칙)

| 지표 | 정의 | 파생 SSOT | 경로:라인 |
|---|---|---|---|
| 출고가(grand total) | `max(0, 품목합 + 자유입력 − 할인)` | `erp_shipping_price_from_structured` | `foms/services/erp_display.py:297-323` |
| 품목합 | `totals.items_total` 또는 `items[].price` 합 | `erp_payment_amount_from_structured` | `foms/services/erp_display.py:279-294` |
| 예약금 | `payment.deposit`(→레거시 `payments`) | `erp_deposit_amount_from_structured` | `foms/services/erp_display.py:261-276` |
| 할인 | `payment.discount` 등 | `_extract_discount_amount` | `foms/services/estimate_service.py:225` |
| 자유입력(배송 등) | `payment.free_input` "라벨:금액" 멀티라인 텍스트 | `_extract_free_input_amount` | `foms/services/estimate_service.py:297` |
| 잔금 | `출고가 − 예약금` (예약금 미기입=0) | 완료 대시보드 불변식 | `foms/web/cs/completion_dashboard.py:153-155`, `estimate_service.py:307 _balance_after_payments` |

**저장된 `totals.*` 를 읽지 않는 근거(드리프트 회피)**: 읽기 경로가 3갈래로 갈라져 있다.
완료 대시보드·이력 시트는 저장 totals 를 무시하고 매번 재파생하는데, 모바일 요약
(`mobile_amount_summary`, `foms/services/erp_mobile_order_display.py:332-`)은 저장된
`totals.final_amount`/`balance_amount` 를 먼저 쓴다(:344-346 docstring이 이 차이를 자인).
totals 가 낡은 주문에서는 화면마다 잔금이 갈린다. **정산 대시보드는 재파생 계열
(`erp_shipping_price_from_structured` + `estimate_service` 헬퍼)만 쓴다** — 완료 대시보드와 동일 계열.
같은 이유로 **출고가 공식을 SQL로 재구현하는 것도 금지**한다: `free_input` 은 자유 텍스트 파싱이라
SQL 재현 = SSOT 이중화 = 모바일 드리프트와 같은 부류의 회귀를 새로 만드는 일이다(§4 설계가 이 제약을 따른다).

참고: `Order.payment_amount`(models.py:43)는 예약금의 플랫 미러(`foms/services/erp_sync_columns.py:57-59`가
저장 시 `erp_deposit_amount_from_structured` 결과를 동기화)다. **출고가에는 이런 플랫 컬럼이 없다** — §10 Q4.

### 3.2 정산 대상 상태 3종 SSOT

```python
ORDER_SETTLEMENT_ALERT_TARGET_STATUSES = ("COMPLETED", "AS_RECEIVED", "AS_COMPLETED")
```
`foms/services/orders/erp_policy_constants.py:11`. 완료 대시보드도 이 상수를 alias 로 쓴다
(`foms/api/cs/dashboard.py:24,38`). **신규 상수를 만들지 않고 이걸 import 한다.**

- 매출·수금·미수·aging·채널·정산 현황 카드의 모집단 = 이 3종 + `Order.active_filter()`(models.py:146 — soft-delete·ERP draft 제외).
- 예외 1곳: "진행 단계별 물린 금액" 카드만 **완료 전** 모집단(§4.4).
- `Order.dashboard_active_filter(days=60)`(models.py:161-)는 쓰지 않는다 — 완료 후 60일 경과분을 제외하는
  운영 대시보드용 필터라, 과거 월 정산 집계에서 데이터가 증발한다.

### 3.3 날짜 축 = 완료일 `schedule.construction.date`

- 완료일 정본 = `structured_data.schedule.construction.date` — 완료 대시보드와 동일 경로
  (`foms/web/cs/completion_dashboard.py:140`, 월 키 파생 `_completion_month_key` :51-65).
- **레거시 컬럼 함정**: `Order.completion_date`(models.py:41)·`measurement_time`(models.py:40)은 ERP 주문에서
  사실상 전부 NULL(`research_foms_finance_data.md` §3, `foms/services/measurement_time.py` docstring) — 날짜 축으로 채택 금지.
- **싱크 컬럼 함정**: `Order.erp_construction_date`(models.py:100)는 **첫 날짜만** 담는다. 복수 일정 주문에서 불완전.
  날짜 술어(기간 필터)는 `OrderScheduleDate`(`order_schedule_dates`, models.py:205-236,
  `kind='construction'`, composite 인덱스 `idx_order_schedule_dates_composite`) EXISTS 조인이 정본.
- **이중 계상 방지 규칙**: SQL 술어는 order_schedule_dates EXISTS 로 **넓게** 거르고(복수 일정 주문이
  조회 기간에 하나라도 걸리면 포함), 일/월 버킷 귀속은 파이썬 커널이 `schedule.construction.date`
  단일 경로로 **정확히 1회** 판정한다. 한 주문이 두 달 버킷에 중복 합산되는 일이 없어야 한다(M1 테스트 항목).

### 3.4 채널 판정 = ExternalOrderLink

- SSOT = `ExternalOrderLink`(models.py:3283-, `UNIQUE(channel, external_id)`, `order_id` FK `SET NULL`).
  집계 시 `LEFT JOIN external_order_links ON order_id` — 링크 행 존재 → 해당 `channel`(현재 'NAVER'뿐), 부재 → '일반'.
- `structured_data.naver.source` 필드는 **전수성 미확인**(`research_foms_finance_data.md` §4.2 — 로컬 표본에서만 실측)
  → v1 판정 소스로 쓰지 않는다. 검증 항목은 §10 Q2.
- 혼동 금지: `Order.channel_source_seq`(models.py:113)·`NotificationEvent.channel`·`ChannelDeliveryLog` 는
  채널톡/알림 발송 축이지 주문 유입 채널이 아니다.

### 3.5 v1 지표 정의 (근사는 근사라고 화면에 쓴다)

| 지표 | v1 정의 | 소스 |
|---|---|---|
| 당월 매출 | 완료일이 당월인 대상 상태 주문의 출고가 합 | §3.1+§3.3 |
| 완료 건수 / 평균 출고가 | 위 모집단 건수 / 매출÷건수 | 〃 |
| 미수금 잔액 | `잔금>0 AND payment.balance_confirmed != True` 건의 잔금 합(기간 무관, 대상 상태 전체) | `_completion_row` paid 판정과 동일(`completion_dashboard.py:161`) |
| 미수금 aging | 미수건을 `(오늘 KST − 완료일)` 경과일로 5버킷(≤7/8–30/31–60/61–90/91+) | `get_today_kst()`(date 반환 — `.date()` 호출 금지 함정) |
| **당월 수금 (근사)** | 실입금일 데이터 부재(확인 토글은 bool뿐, `research_foms_finance_data.md` §6) → **완료월 귀속 근사**: 당월 완료건의 예약금 합 + `balance_confirmed=True` 건의 잔금 합. 화면 라벨에 "완료월 귀속" 명기 | §10 Q5, 로드맵(확인일 필드) |
| 정산상태(청구완료/대기) | `settlement.deductions` 존재 여부 | `completion_dashboard.py:163-165` |
| 현금영수증 대기 | `cash_receipt_state == "requested"` (issued > requested > none 3값) | `completion_dashboard.py:105-122` |
| AS 유상 확정 | `shipment.as_billing.{type='paid', confirmed, amount}` | `foms/services/as_dashboard_display.py:259-289` |
| 부서 귀속 차감 | `settlement.deductions[].{department, amount}` 부서별 합, 부서 코드 = `SETTLEMENT_DEPARTMENTS` | `foms/api/cs/dashboard.py:58`, 표시 라벨 `SETTLEMENT_DEPARTMENT_OPTIONS`(`completion_dashboard.py:35-41`) |
| 진행 단계별 물린 금액 | §4.4 별도 모집단 | `erp_stage_code` + `STAGE_LABELS`(`erp_policy_constants.py:14-26`) |

---

## 4. 집계 설계 — 200건 캡 우회

### 4.1 구조: SQL 모집단(캡 없음) + 파이썬 SSOT 커널

완료 대시보드 로더(`_load_completion_orders`, `foms/api/cs/dashboard.py:103-155`)는 재사용하지 않는다
(200건 캡 + 검색/focus 파라미터가 집계에 불필요). 신규 서비스 `foms/services/settlement/aggregation.py`:

1. **모집단 SELECT (SQL, 캡 없음)** — `Order.active_filter()` + `status IN` 3종(§3.2) +
   `order_schedule_dates(kind='construction', date BETWEEN …)` EXISTS(§3.3).
   로드 컬럼은 최소화: `id, status, structured_data` (+ 채널 LEFT JOIN 결과).
   사용 인덱스: `orders.status`(idx), `idx_order_schedule_dates_composite(kind, date, order_id)`.
2. **집계 커널 (파이썬)** — 행마다 §3.1 SSOT 함수로 출고가·예약금·잔금 재파생 →
   완료일 단일 판정(§3.3) → 일/주/월 dict GROUP BY, KPI·aging·채널·정산 현황 동시 산출(모집단 1회 순회).

**SQL GROUP BY 로 내리지 않는 이유**: §3.1 — 출고가 공식의 자유입력 텍스트 파싱을 SQL 로 복제하면
SSOT 가 이중화된다. "캡 우회"는 모집단 쿼리에서 달성하고, 금액 정확성은 파이썬 커널이 지킨다.
규모가 이 구조를 초과하면 flat 컬럼/머티리얼라이즈로 간다(§10 Q4 — 열린 질문).

### 4.2 성능 가드 (성능 회귀 차단 규칙 준수)

- **기간 상한**: 1회 조회 최대 12개월(서버 파라미터 검증·클램프). 기본 화면 = 당월 + 전월(비교선) 2개월.
- **쿼리 규율**: JSONB `ilike` 없음, N+1 없음(모집단 1 SELECT + 채널 LEFT JOIN 1개), hot path 신규 무거운 계산 없음.
- **JSONB 파싱 비용**: 월 모집단 규모 미실측(§10 Q1). M4에서 스테이징 TTFB 실측 + `EXPLAIN` Seq Scan 없음 확인이 머지 관문.
- **perf guard G1–G4**(`tests/performance/test_perf_regression_guard.py:9-12`):
  차트 JS는 `defer`(G1), 외부 CDN 금지 — 목업과 동일하게 자체 SVG 렌더(G2), ERP shell fragment 로 진입할 경우
  전역 listener 싱글톤 가드(G4).
- **캐시**: v1 기본 무캐시. 도입 여부·TTL 은 실측 후 결정(§10 Q3).

### 4.3 API 응답 형태

집계는 서버에서 완결하고, 응답은 화면 렌더에 필요한 버킷 배열만 준다(주문 행 원본 미노출 — 권한 §5와 정합).
> **개정 A(§13.1)**: 이 "주문 행 원본 미노출" 은 **이 집계 엔드포인트에만** 적용된다. 실무 탭의
> 행 데이터는 별도 표면으로 내며, 집계 응답에는 앞으로도 주문 행을 싣지 않는다.
일별 배열을 기본으로 주고 주/월은 서버 재버킷(granularity 파라미터). 응답 통일 형식
`{'success': True, 'data': {...}, 'error': None}`.

### 4.4 "진행 단계별 물린 금액" 별도 모집단

- 모집단: `Order.active_filter()` + `erp_stage_code`(models.py:103, idx)가 완료 계열이 아닌 주문.
- 집계: stage 별 건수 + 출고가 재파생 합. 라벨은 `STAGE_LABELS`(`erp_policy_constants.py:14-26`) 기준.
- 주의: 목업 stages 배열의 '해피콜' 라벨(mockup :357)은 `STAGE_LABELS` 에 없는 단계다 —
  실구현은 `erp_stage_code` 실측값과 `STAGE_LABELS` 를 따르고 목업 라벨을 복제하지 않는다.
- 이 카드도 기간 스코프 밖(현재 시점 스냅샷)임을 카드 부제에 명기.

---

## 5. 권한 — 신규 read-only 정책 `SETTLEMENT_DASHBOARD_READ`

> **개정 2026-09-03 (사용자 결정)**: 열람 집합이 **ADMIN + 회계팀(ACCOUNTING)** 으로 좁혀졌다.
> 아래 원안(= `FINANCE_MUTATION` 과 동일 집합, CS/SALES 포함)은 2026-09-02 까지의 상태다.
> 판정 SSOT 는 `foms/services/settlement_channel_access.py::is_accounting_or_admin` 이고,
> 정책 등재는 `teams=("ACCOUNTING",)` + `gate=` 로 그 함수를 가리킨다(MANAGER 는 엔진에서
> team 검사보다 먼저 통과하므로 teams tuple 만으로는 표현할 수 없다). 주문 상세의 입금확인·
> 현금영수증 같은 개별 금융 command(`FINANCE_MUTATION`)는 CS/SALES 가 그대로 쓴다 —
> 두 집합은 더 이상 같지 않다.

`research_personas.md` §3 반영. 현황(코드로 확인):

- `POLICY_REGISTRY`(`foms/services/orders/order_mutation_policy.py:102-191`)의 policy_id 는 전부 mutation 게이트용.
- before_request 가드 `enforce_order_mutation_policy` 는 `_WRITE_METHODS`(POST/PUT/PATCH/DELETE)만 검사(:482-483)
  → **GET 대시보드 라우트는 자동 게이트가 없다.**
- 기존 read 범위 `user_can_read_order`(:289-310)는 "인증 활성 사용자 전원 조회" — 이 범위를 그대로 따르면
  생산/시공 STAFF 가 전사 매출·미수금 총액을 보게 된다. 집계 뷰는 별도 read 제한이 필요하다.

**설계**:

1. **정책 신설** — `POLICY_REGISTRY` 에 추가:
   ```python
   "SETTLEMENT_DASHBOARD_READ": _p("SETTLEMENT_DASHBOARD_READ", teams=("CS", "SALES"),
       description="정산 대시보드 열람(read-only) — FINANCE_MUTATION 과 동일 집합. VIEWER deny."),
   ```
   허용 집합 = `FINANCE_MUTATION`(:114-115)과 동일: ADMIN / MANAGER / STAFF+CS / STAFF+SALES.
   거부: VIEWER(하드 deny :243-246) / STAFF+PRODUCTION·DRAWING·CONSTRUCTION·SHIPMENT.
   기존 `evaluate_policy` 평가 순서(:216-279)를 그대로 타므로 신규 평가 로직 없음.
2. **집행 지점 = 핸들러 내부** — GET 은 before_request 를 안 타므로, 페이지·API **모든 신규 GET 핸들러가
   각자** `user_can("SETTLEMENT_DASHBOARD_READ", user)`(:355-)로 판정한다. 거부 시 HTML 라우트는 403 페이지,
   API 는 `{'success': False, 'error': ...}` 403. `@login_required` 는 별도 유지(미인증 401/redirect).
3. **UI 은닉 동기화** — 네비/진입 링크는 `policy_can('SETTLEMENT_DASHBOARD_READ')` 템플릿 헬퍼
   (:523, :526-528)로 감춘다 — 완료 대시보드 `data-can-finance` 마크업과 동일 패턴(backend 와 같은 policy_id).
4. **테스트 매트릭스** — `tests/domains/test_auth_finance.py:34-48` 의 `_ALLOWED_ACTORS`(4종)/`_DENIED_ACTORS`(5종)
   과 동일 구성으로 GET 라우트 전수 검사(M2 완료 기준).

주의: 미래에 부서 스코프 뷰(생산/시공에게 자기 부서 차감만)를 열 경우는 별도 정책으로 신설한다 — v1 비목표.

---

## 6. 라우트 / 구조

`app.py` 라우트 추가 금지 → Blueprint. 실제 코드베이스 관례: 페이지=`foms/web/`, API=`foms/api/`,
등록=`foms/platform/blueprints.py`(`register_blueprints` :29-, 완료 대시보드 bp 등록 :116과 동렬).
(CLAUDE.md 의 "`apps/api/`" 문구는 현 트리에 apps/ 디렉토리가 없어 사문 — 취지(app.py 금지·Blueprint 분리)만 따른다.)

| 계층 | 신규 파일 | 내용 |
|---|---|---|
| 서비스 | `foms/services/settlement/aggregation.py` | §4 집계 커널. 라우트와 분리, 함수 50줄 이하·docstring·타입 힌트 필수 |
| 페이지 | `foms/web/settlement/dashboard.py` → `erp_settlement_page_bp` | `GET /erp/settlement` — `@login_required` + §5 가드, 서버 렌더 셸 |
| API | `foms/api/settlement/aggregates.py` → `settlement_api_bp` | `GET /api/settlement/aggregates?granularity=day\|week\|month&month=YYYY-MM` — §4.3 |
| 템플릿 | `templates/settlement/dashboard.html` | **인라인 스타일 금지**, `static/css/foundation/erp-pro.css` 체계 위에 신규 CSS |
| CSS | `static/css/settlement/settlement-dashboard.css` | 목업 토큰(색 사전 B+D — `color_study.md` 검증 팔레트) 이식. 링크에 `?v=` 핀 필수, 변경 시 범프(SW staticCacheFirst) |
| JS | `static/js/settlement/dashboard.js` (`defer`) | 목업의 SVG 렌더 함수 이식(외부 차트 라이브러리 금지 — perf G2), fetch 는 try/catch + `data.success` 검증 |

**Jinja2→JS 데이터 규칙(절대)**: `JSON.parse('{{ x|tojson }}')` 금지 — 초기 페이로드는 `data-*` 속성 +
`safeJsonParse`(기존 static/js 공용 헬퍼), 차트 데이터는 §4.3 API fetch.

**색상 계약(목업 확정 이식)**: 지표 가족 색 사전 = 매출 파랑 `#2a78d6`(+전월 비교 다크 스텝 `#1c5cab`) ·
미수/aging 주황 램프 · 수금 아쿠아 `#1baf7a`(대비 2.82:1 — 값 병기 필수) · 위험 critical `#d03b3b`(아이콘+라벨 동반) ·
카드 가족 틴트(D) · 매출 막대 금액구간 파랑 램프+범례(사용자 명시 확정, ledger T13). 팔레트는 `color_study.md` 부록 검증 기록 준수.

---

## 7. 목업 → 실구현 매핑 표

기준: `docs/design/mockups/settlement-dashboard-v1-executive.html` (라인은 확정본 기준).

| V1 카드 (목업 라인) | 데이터 소스 / 쿼리 | v1 구현 |
|---|---|---|
| KPI 히어로 5장: 당월 매출·미수금 잔액·완료 건수·평균 출고가·당월 수금 (:367-375) | §4 커널 1회 순회(당월+전월 → 델타·스파크라인) — 수금은 §3.5 근사 라벨 | **O** |
| 필터바: 일/주/월 + 전월 비교 + 누적 보기 (:225-235) | granularity 파라미터 재조회(서버 재버킷), 누적은 클라 누산 | **O** |
| 출고가 매출 추이 — 당월 막대(금액구간 램프)+전월 라인 (:243-261) | 일별 GROUP BY 완료일 + 전월 동일자 병렬 배열 | **O** |
| └ 월 매출 목표 미터 (:249-255, "예정" 배지) | 목표 데이터 부재 | **X 제외** (로드맵) |
| 정산 처리 현황 (:265-279) | settlement_issued 비율·cash_receipt requested 건수·as_billing 유상·deductions 부서합 (§3.5) | **O** |
| 현금흐름 30일 예측 (:280-288, "예정" 배지) | 예측 근거 데이터 부재 | **X 제외** (로드맵) |
| 미수금 aging 5버킷 + 91일+ 경고 (:292-299) | 미수건 (오늘−완료일) 버킷, critical 은 상태색+아이콘 | **O** |
| 진행 단계별 물린 금액 (:301-308) | §4.4 별도 모집단(erp_stage_code GROUP + 출고가 재파생 합) — '해피콜' 라벨은 STAGE_LABELS 기준으로 교체 | **O** |
| 채널별 매출 비중 (:310-318) | 당월 완료건 LEFT JOIN `external_order_links` (§3.4) | **O** |
| 헤더 스트립 권한 부제 "ADMIN·MANAGER 전용…" (:219) | 실제 허용 집합은 §5(CS/SALES STAFF 포함) — 문구를 실정책으로 교정 | **O(수정)** |
| MOCKUP 배지·가정치 foot (:322-327) | — | **X 제거** |

---

## 8. 마일스톤 (각각 커밋 단위, 완료 기준 필수)

| M | 내용 | 완료 기준 (통과 명령) |
|---|---|---|
| **M1** | 집계 서비스 + 단위 테스트: 모집단 술어(상태 3종·active_filter·200건 초과 시드에서 전량 집계), 금액 파생이 `_completion_row` 와 일치(파리티), 복수 일정 이중 계상 방지, 채널 LEFT JOIN, aging 버킷 경계 | `python -m pytest tests/domains/test_settlement_aggregation.py -q` green + `python -c "import app; print('APP_OK')"` |
| **M2** | 정책 등재 + API/페이지 라우트 + 권한 테스트(허용 4·거부 5 매트릭스 ×전 GET 라우트, VIEWER 403, 미인증 401) + 기존 게이트 무회귀 | `python -m pytest tests/domains/test_settlement_dashboard_api.py tests/domains/test_auth_finance.py tests/domains/test_write_guard.py -q` green |
| **M3** | 템플릿 + CSS(?v 핀) + 차트 JS + 네비 policy_can 은닉 | 핀·은닉 계약 pytest green + perf guard `python -m pytest tests/performance/test_perf_regression_guard.py -q` exit 0 + gstack browse 스테이징 실화면(콘솔 에러 0, 차트 렌더 확인) |
| **M4** | 성능 검증: 스테이징(가능하면 운영 읽기전용 1회)에서 집계 쿼리 `EXPLAIN` Seq Scan 없음 + 페이지 TTFB 실측 기록 → 예산 판정, 초과 시 §10 Q4 착수 제안 | EXPLAIN·TTFB 수치가 원장에 기록되고 판정 명시. `scripts/ops/pre_push_smoke.ps1` exit 0 |

공통: 각 M 커밋 전 `pre_push_smoke` exit 0 + `APP_OK`(Stop 게이트). push 후 `gh run list` 로 해당 커밋 전 워크플로 green 확인(ci_watch 는 1개만 본다).

---

## 9. 검증 계획

**manifest 등재 불요 확인(코드로 확정)** — 신규 라우트는 전부 GET(읽기 전용):

- write guard manifest 게이트 `test_manifest_covers_every_mutation_route`(`tests/domains/test_write_guard.py:103-119`)는
  url_map 의 **POST/PUT/PATCH/DELETE endpoint 만** 검사 → GET 전용 라우트는 mutation policy·write guard
  manifest 2종 등재 대상이 아니다. 감사 action 라벨·audit coverage 게이트도 mutation 부재로 해당 없음.
  단 M2 에서 게이트 스위트 실행으로 재확인한다(주장 아닌 실행 결과로).

**pre_push_smoke 사각 항목(별도 확인 필수)**:

- **failopen 인벤토리**: 신규 서비스/라우트 파일에 `try/except` 를 넣으면
  `docs/harness/foms_failopen_inventory.json` 재생성 필요 — pre_push_smoke 미포함·CI 만 잡는 사각.
  재생성은 원격 tip 클린 worktree 에서(라인시프트 함정).
- **docs 를 읽는 테스트 금지**(CI-DOCSCOPE-01): 신규 테스트는 코드만 읽는다. 불가피하면 ci.yml 서브셋 등재(CRLF 주의).
- push 후 CI 는 전 워크플로 나열로 판정(perf-gate 사각 포함).

**계약 테스트 목록(신규)**:

1. 권한 매트릭스(§5.4) — GET 전 라우트 × actor 9종.
2. UI 은닉 — `policy_can('SETTLEMENT_DASHBOARD_READ')` false 사용자에게 네비 링크 미렌더.
3. 캡 무관성 — 201건 이상 시드에서 집계 합 = 전량 합(200건 캡 회귀 방지 회귀선).
4. 금액 파리티 — 동일 주문 표본에서 집계 커널 출고가/예약금/잔금 == `_completion_row` 파생값(SSOT 이탈 감지).
5. 이중 계상 방지 — construction 날짜 2개(두 달 걸침) 주문이 정확히 1개 월 버킷에만 귀속.
6. 자산 핀 — 신규 CSS/JS `?v=` 핀 존재(+변경 시 범프 계약).

**테스트 데이터 규율**: 존재하지 않는 FK id(`order_id=999999` 류) 금지 — 실제 행 생성(PG 레인에서만 터지는 함정).
실화면 검증은 합성 DOM 주입이 아니라 시드 주문으로.

---

## 10. 열린 질문 (승인 전/구현 중 답 필요)

| # | 질문 | 왜 필요한가 / 방법 |
|---|---|---|
| Q1 | **운영 규모 실측** — 월 완료 건수·금액 스케일, 대상 상태 3종 총 행수 | 목업 수치(월 152건·2.14억)는 가정치, 로컬 DB는 QA 시드 10건뿐. §4 파이썬 커널의 비용 전제가 여기 걸려 있다. 운영 읽기전용 1회 조회(`docs/guides/REAL_SERVER_TEST_ACCOUNT.md` 절차 또는 `DATABASE_PUBLIC_URL` 읽기 경로) — M1 착수 전 권장 |
| Q2 | **naver.source 전수성** — `structured_data.naver.source` 가 네이버 수집분 전량에 존재하는지, `ExternalOrderLink.order_id` 가 SET NULL 로 끊긴 주문의 채널 귀속을 어떻게 볼지 | v1 은 링크 조인만 쓰지만(§3.4), 끊긴 링크 비율이 유의하면 채널 비중이 '일반'으로 과대 산정된다. Q1 조회에 카운트 1개 동승 |
| Q3 | **캐시 전략** — 무캐시 vs 짧은 TTL(60s 급) vs 요청 코얼레싱 | M4 TTFB 실측 후 결정. 도입 시 무효화 설계 필수(캐시 통무효화 함정 전례) |
| Q4 | **flat 컬럼 / 머티리얼라이즈** — 규모 초과 시: `erp_sync_columns` 패턴(예약금 미러 `erp_sync_columns.py:57-59` 와 동형)으로 출고가 플랫 컬럼 신설+백필, 또는 일별 집계 테이블 | 서버 저장 시점 재계산 미러라 "저장값 불신" 원칙과 양립하나, **전 쓰기 경로가 sync 를 타는지 감사 + 백필 마이그레이션**이 선행 조건. v1 범위 밖, M4 실측이 트리거 |
| Q5 | **당월 수금 근사 승인** — §3.5 "완료월 귀속" 정의로 갈지, `PAYMENT_CHANGED` 이벤트(`foms/services/order_payment_sync.py`) 역산으로 확인 시각을 파생할지(비용 큼) | 로드맵의 `deposit_confirmed_at`/`balance_confirmed_at` 필드 신설 전까지의 표기 방침 결정 |
| Q6 | **주(week) 버킷 정의** — ISO 주 vs 월 내 주차(목업은 월 내 주차) | 라벨·경계 계약을 M1 테스트에 고정하기 위한 소결정 |

---

## 11. 로드맵 (v1 비목표의 후속 확장 — `research_foms_finance_data.md` §6 기반)

| 미래 기능 | 필요한 선행 데이터/작업 |
|---|---|
| 매출 목표 대비 진행률 | 목표 입력 UI+저장소 신설(시스템에 목표 개념 없음) |
| 수금일 실기록·현금흐름 예측 | `payment.deposit_confirmed_at`/`balance_confirmed_at` 신설(+과거분은 PAYMENT_CHANGED 이벤트 역산 백필), 분할 수금 구조 |
| 월 마감 잠금 | 마감 확정 시각·책임자·재오픈 이력 + 마감 후 금액 수정 차단(신규 mutation → manifest 2종+감사 라벨 계약 4종 적용) |
| 세금계산서 | `settlement.tax_invoice{issued, number, issued_at, business_no}` 신설(현금영수증 패턴 확장) |
| 채널 수수료 대사 | `naver.payment.expected_settlement_amount` 정형화 + 수수료율 마스터 |
| 반품 환불액 | 네이버 클레임 금액 동기화 — NAVER-INGEST-01 v1 비목표(§2), 후속 스펙 필요 |
| 원가/마진 | 원가 필드+입력 UI 신설. 노출은 서버 payload 에서부터 팀별 배제(클라 숨김 금지 원칙) |
| 부서 스코프 뷰 | 생산/시공 STAFF 에게 자기 부서 차감만 — 별도 read 정책 신설 |

---

## 12. 리스크

| 리스크 | 대응 |
|---|---|
| JSONB 파싱 비용이 규모에서 초과 | §4.2 기간 상한 + M4 실측 관문 + Q4 우회로 예약 |
| GET 가드 누락(수동 집행이라 라우트 추가 시 빠뜨림) | 계약 테스트가 신규 GET 라우트 전수에 매트릭스 강제(§9), 리뷰 체크 항목화 |
| 채널 오귀속(링크 SET NULL·미링크 수집분) | Q2 실측 + '일반' 라벨에 "미링크 포함" 각주 옵션 |
| 수금 근사를 실입금으로 오독 | 화면 라벨 "완료월 귀속" 고정(§3.5) + Q5 결정 반영 |
| 완료일 미기입 주문(집계 불가 행) | 커널이 '완료일 미상' 버킷으로 분리 표기(암묵 drop 금지 — 대시보드 캡·필터 조용한 누락 전례) |
| SSOT 함수 시그니처 이동(리팩터) | 파리티 계약 테스트(§9-4)가 이탈을 red 로 잡는다 |

---

## 13. 개정 A — 탭 3개 구성과 "주문 행 원본 미노출" 전제 해제 (2026-08-31, 사용자 승인)

v1 은 경영진 요약 한 화면이었다. 사용자 지시로 `/erp/settlement` **한 URL 안에서 탭 3개**가 된다
(별도 메뉴 항목 신설 금지). 권한 게이트는 `SETTLEMENT_DASHBOARD_READ` 한 곳을 그대로 쓴다.

| 탭 | 성격 | 목업 |
|---|---|---|
| 요약(경영진) | 집계 전용 — v1 그대로 | `settlement-dashboard-v1-executive.html` |
| **실무(경리·수금)** | **주문 행 단위 목록** | `settlement-dashboard-v2-operations.html` |
| 분석 | 집계 전용 | `settlement-dashboard-v3-analytics-light.html` |

### 13.1 §4.3 의 "주문 행 원본 미노출" 은 **집계 API 에만** 적용된다 (개정)

기존 문구: *"응답은 화면 렌더에 필요한 버킷 배열만 준다(주문 행 원본 미노출)"*.
이 문장은 `GET /api/settlement/aggregates` 를 규정한 것으로 **범위를 좁힌다.**
`aggregates` 는 앞으로도 주문 행을 절대 싣지 않는다 — 계약 테스트
`test_api_response_carries_no_order_rows` 는 **그 엔드포인트에 대해 그대로 유지**한다.

실무 탭의 행 데이터는 **별도 표면**으로 낸다. 집계 엔드포인트에 행을 섞지 않는다.

### 13.2 해제의 근거 — 신규 PII 획득 actor 가 0 이라는 실측

`SETTLEMENT_DASHBOARD_READ` 허용 집합(ADMIN · MANAGER · STAFF+CS · STAFF+SALES,
`_TEAM_NORMALIZE` 로 STAFF+MEASURE 포함)은 이미 `/erp/dashboard`(`@login_required` **뿐**)에서
**고객명 · 연락처 · 주소**를 행 단위로 본다. 또 `user_can_read_order`
(`order_mutation_policy.py:293-314`)는 *"인증된 active 사용자는 team·assignment 와 무관하게
모든 Order 를 조회할 수 있다"* 를 이미 규약으로 못박고 있다.

→ 실무 탭이 새로 여는 **PII 종류는 없다.** 오히려 노출 필드는 기존보다 좁다
(**고객 성명 + 주문번호만**. 연락처·주소·현금영수증 원문은 내지 않는다).

### 13.3 그래도 바뀌는 것 — 규모, 그리고 그에 딸린 계약

| 축 | 기존 최대 | 실무 탭 |
|---|---|---|
| 단발 행 노출 | 완료 대시보드 200건(무검색) / 500건(검색) | 캡 없는 전량(운영 ERP 모집단 1,978건) |

**따라서 다음을 계약으로 못박는다.**

1. **행 표면은 `aggregates` 와 분리한다.** 자체 PII 계약 테스트를 새로 붙인다 —
   연락처·주소·현금영수증 자유텍스트 원문이 응답/렌더에 실리면 red.
2. **캡을 걸지 않는다.** 걸어야 하면 **모집단을 좁힌 뒤에** 걸고 발동을 `logger.warning` 으로 남긴다
   (`measurement/dashboard.py:527-552` 가 선례). 완료 대시보드가 캡 뒤에 파이썬으로 좁히는
   기존 함정을 복제하지 않는다.
3. **페이지네이션은 번호 페이저 · 60건/page**(완료 그리드 `_paginate` 관례). 무한스크롤 금지.
4. **검색창은 두지 않는다**(목업에도 없다). 넣는 순간 `customer_contact_only=True` 분기가
   연락처·주소를 검색 대상에 포함시킨다 — 별도 결정 사항으로 남긴다.
5. **행 파생은 기존 SSOT 재사용.** 잔금·현금영수증·정산 판정식을 세 번째로 복제하지 않는다
   (커널이 `completion_dashboard` 헬퍼를 import 하는 이유와 같다). **과입금 줄을 되살린다**
   — 목업엔 없으나 빼면 CEO L-1(클램프가 삼킨 돈이 화면에서 사라짐) 회귀다.

### 13.4 §5 "read-only" 해제 — 인라인 실행 버튼 (사용자 승인)

실무 탭에 `[입금 확인]` · `[정산 청구]` 버튼을 둔다. **신규 mutation 라우트가 아니다** —
이미 있는 `POST /api/orders/<id>/payment-confirm` · `POST /api/orders/<id>/settlement/issue`
(둘 다 `FINANCE_MUTATION`)를 호출한다. `FINANCE_MUTATION` 허용 집합은
`SETTLEMENT_DASHBOARD_READ` 와 **동일**하므로 신규 권한 확장이 0 이다.
신규 라우트가 없으므로 mutation manifest 2종 등재 대상도 아니다(게이트 실행으로 재확인할 것).

### 13.5 기존 완료 대시보드 태블릿 금액 그리드와의 역할 분리

판정은 **OVERLAPPING-BUT-DISTINCT**: 모집단·금액 파생식·현금영수증/정산 판정은 문자 그대로
같은 코드이고, 갈리는 축은 셋이다.

| 축 | `/erp/completion` 태블릿 그리드 | 실무 탭 |
|---|---|---|
| 표시 기기 | 모바일/태블릿 코호트 전용(PC 에서는 렌더 안 됨) | PC 정산 화면 |
| 모집단 상한 | 200건 캡 | 전량 |
| 축 | 완료**월** | 미수 **경과일** |
| 역할 | 현장용(시공 사진 옆 금액 확인) | 경리용(전사 미수 회수) |

링크로 대체 불가(PC 에서 안 뜨고 캡 때문에 전사 미수 목록이 구조적으로 안 나온다).
두 화면은 **같은 행 빌더를 공유**하고, 그 사실을 계약 테스트로 못박는다.

### 13.6 분석 탭 — 담당자별 매출은 ADMIN·MANAGER 전용 (사용자 승인)

담당자별 매출은 직원 실적 노출이다. STAFF 에게는 **이 카드만** 숨긴다(나머지 분석 카드는 노출).
숨김은 클라이언트가 아니라 **서버 payload 단계**에서 한다 — 클라 숨김은 이 저장소 금지 원칙이다.
목업의 "팀 스코프" 칩은 구현 불가라 뺀다(주문에 영업팀 축이 없다 — `erp_owner_team_code` 는
워크플로 팀이고 완료 건은 CS 로 수렴한다).

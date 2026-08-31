# 정산 대시보드 구현 진행 원장 (SETTLE-DASH-01)

- 시작: 2026-08-31
- 스펙(승인됨): `docs/specs/2026-08-31-settlement-dashboard_SPEC.md`
- 목업 확정본: `docs/design/mockups/settlement-dashboard-v1-executive.html`
- 선행 원장(목업·스펙 세션): `docs/plans/2026-08-31-settlement-dashboard-mockup-ledger.md`
- 등급: `**C` 릴레이 — 멀티에이전트 병렬 + CEO(메인 세션) 총괄
- 브랜치: `deploy` (production 승격은 별도 승인)

## 운영 원칙 (이 원장의 계약)
- 서브에이전트 "완료" 보고는 주장일 뿐 — CEO가 diff 직접 확인 + 테스트 직접 실행 후에만 DONE 기록.
- 각 T는 완료 기준(통과 명령)을 가진다. 명령 실행 결과 없이 DONE 금지.
- 막히면 BLOCKED로 기록하고 전진.

## Tasks

| T | 마일스톤 | 내용 | 완료 기준 (통과 명령/증거) | 상태 |
|---|---|------|-----------|------|
| T0 | 준비 | 구현 원장 작성 + 산출물(목업 5·리서치 5·스펙·원장 2) 커밋 | 원장 파일 존재 + 커밋 SHA 기록 | PENDING (워크트리 이관 완료, 커밋 대기) |
| T1 | Q1 | 운영 DB 읽기전용 실측 — 대상 상태 3종 총행수, 월별 완료 건수·출고가 스케일, order_schedule_dates 규모 | 수치가 본 원장에 기록됨 (읽기전용 세션·쓰기 0) | **DONE** — 모집단 2,168건·출고가 17.5억·커널 0.01 ms/행. §실측 기록 참조 |
| T2 | Q2 | 운영 DB 읽기전용 실측 — ExternalOrderLink 채널 분포, `order_id IS NULL` 비율, `naver.source` 전수성 | 카운트 3종 기록 + 채널 오귀속 리스크 판정 | **DONE** — 링크 206(NULL 74)·모집단 교차 0건·`naver.source` 운영 0건. 채널 오귀속 리스크 실질 0 |
| T3 | 사전조사 | 코드 계약 인벤토리 4종(금액 SSOT / completion_dashboard 파생 / 스키마·상수 / 정책 레지스트리) | 조사 결과가 CEO에 의해 Read/Grep 재검증됨 | **DONE (단서부)** — 4기 조사 완료. **단 조사는 낙후 메인 트리 기준**이라 워크트리 기준 재검증이 T5 에 포함됨 |
| T4 | Q5·Q6 | 소결정 확정: 수금 근사 표기(§3.5), 주(week) 버킷 정의 | 결정 + 근거가 원장에 기록, M1 테스트에 고정 | **DONE** — D1(월 내 주차)·D2(완료월 귀속 근사) |
| T5 | M1 | `foms/services/settlement/aggregation.py` 집계 서비스 구현 | `python -m pytest tests/domains/test_settlement_aggregation.py -q` green | PENDING |
| T6 | M1 | 단위·계약 테스트: 모집단 술어·201건 캡 무관성·금액 파리티·이중계상 방지·채널 조인·aging 경계·완료일 미상 버킷 | 위 pytest green + `python -c "import app; print('APP_OK')"` | PENDING |
| T7 | M1 | M1 커밋 (pre_push_smoke exit 0) | 커밋 SHA + smoke exit 0 기록 | PENDING |
| T8 | M2 | 정책 `SETTLEMENT_DASHBOARD_READ` 등재 + 페이지/API 라우트 + 핸들러 내 가드 | 라우트 200/403 실동작 | PENDING |
| T9 | M2 | 권한 매트릭스 테스트(허용 4·거부 5 × 전 GET 라우트) + 기존 게이트 무회귀 | `python -m pytest tests/domains/test_settlement_dashboard_api.py tests/domains/test_auth_finance.py tests/domains/test_write_guard.py -q` green | PENDING |
| T10 | M2 | M2 커밋 | 커밋 SHA + smoke exit 0 | PENDING |
| T11 | M3 | 템플릿 + CSS(?v 핀) + 차트 JS(defer·자체 SVG) + 네비 policy_can 은닉 | 핀·은닉 계약 pytest green + perf guard exit 0 | PENDING |
| T12 | M3 | 실화면 검증(gstack browse 스테이징): 콘솔 에러 0, 차트 렌더, 시드 주문 기반 | 스크린샷 + 콘솔 로그 기록 | PENDING |
| T13 | M3 | M3 커밋 + push + 전 워크플로 CI green(gh run list 나열 판정) | CI 워크플로 전량 green 기록 | PENDING |
| T14 | M4 | 성능 실측: 집계 쿼리 EXPLAIN Seq Scan 없음 + 페이지 TTFB | 수치 기록 + 예산 판정 명시 | PENDING |
| T15 | M4 | failopen 인벤토리 재생성 필요 여부 판정(신규 try/except 시) | 판정 근거 + 필요 시 재생성 커밋 | PENDING |

## 실측 기록 (Q1·Q2) — 2026-08-31, 운영 DB 읽기전용 1회

방법: 스크래치패드에서 `railway link --project FOMS-PRODUCTION` → `variables --service Postgres --kv`
가드 통과(`RAILWAY_PROJECT_NAME=FOMS-PRODUCTION`, `yamanote.proxy.rlwy.net:34306`, TESTCLR 0건) →
psycopg2 `set_session(readonly=True)`. **쓰기 0회.** DB 크기 126MB.

### 측정 스크립트 자체의 버그 1건 (교정 후 재측정함)
첫 회차에서 `active_filter`를 `(sd #>> '{meta,draft}') IN ('true','True')`로 옮겼더니
키가 없는 행에서 `IN`이 NULL을 내고 `NOT(TRUE AND NULL)`=NULL → **행이 조용히 빠져 모집단이 1126건으로 과소 측정**됐다.
SQLAlchemy의 `.is_(True)`는 NULL을 FALSE로 접어 이 문제가 없다. `COALESCE(...,FALSE)`로 교정한 값이 아래 수치다.
(앱 코드의 버그가 아니라 측정 쿼리의 3치 논리 버그.)

### Q1 — 규모 (모집단 = 대상 상태 3종 + active_filter)

| 항목 | 값 |
|---|---|
| **대상 모집단 총계** | **2,168건** (COMPLETED 1,547 / AS_COMPLETED 558 / AS_RECEIVED 63) |
| orders 전체 | 4,080건 (soft-delete 292, ERP meta.draft 48) |
| 모집단 structured_data 총량 | 1,914 kB (평균 1,938 B, 최대 5,989 B) |
| **출고가 총합(재파생)** | **1,750,441,894원** |
| 출고가 `None`(품목합 미산출) | 191건 |
| **미수(잔금>0 & balance_confirmed≠True)** | **759건 / 1,082,185,934원** |
| 완료일 미상(UNKNOWN 버킷) | **254건 / 44,109,370원 (11.7%)** |
| 콤마 복수 완료일 | 55건 |
| **음수 잔금(출고가−예약금<0)** | **541건** ← 아래 결정 D3 |

월별(완료월 귀속, 콤마는 첫 날짜 기준):

| 월 | 건수 | 출고가 합 |
|---|---|---|
| 2026-02 | 99 | 116,882,140 |
| 2026-03 | 357 | 203,722,540 |
| 2026-04 | 337 | 151,756,240 |
| 2026-05 | 351 | 136,892,670 |
| 2026-06 | 373 | 244,091,034 |
| 2026-07 | 264 | 620,274,360 |
| 2026-08 | 101 | 223,620,540 |
| UNKNOWN | 254 | 44,109,370 |

(2025-11 이전은 월 1~30건의 잔재. 실질 데이터 구간은 2026-02~.)

**성능 판정 — §4 설계 타당, Q4(플랫 컬럼) 불요**:
모집단 2,168행 fetch 0.885초(공인망 경유·운영 내부망은 더 짧다) + **파이썬 커널 0.016초(0.01 ms/행)**.
JSONB 파싱 비용이 지배적이지 않다. 12개월 상한(§4.2)이면 커널 비용은 밀리초대.
목업 가정치(월 152건·2.14억)는 실측(월 100~373건·1.2~6.2억)과 같은 자릿수 — 화면 설계 재작업 불요.

### Q1 부수 발견 — 스펙 §3.3을 고쳐야 하는 것

1. **`order_schedule_dates.date` 는 `character varying(20)`** (Date 아님). `models.py:213`.
   → `BETWEEN`은 문자열 사전순 비교로 동작하나 오염값이 섞인다: `construction` 3,502행 중
   ISO 3,496 + **`'미정'`·`'000원'`·`'100'` 6행**. 범위 술어에 정규식/형식 가드 필요.
2. **`idx_order_schedule_dates_composite(kind,date,order_id)` 는 마이그레이션에 없다**(models.py 정의만, create_all 전용).
   운영에 실재하는 것은 부분 인덱스 **`ix_osd_construction_date (date, order_id) WHERE kind='construction'`**
   (`startup_schema_00:80-81`). 집계 술어는 이쪽에 맞춘다. `ix_orders_status`도 마이그레이션 부재.
3. **완료일 소스 2종이 어긋난다**(모집단 2,168 기준): 둘 다 있음 1,914 / **schedule 행만 있고 sd 날짜 없음 131** /
   둘 다 없음 123 / **sd 날짜만 있고 schedule 행 없음 0**.
   → sd_only가 0이므로 "SQL EXISTS로 넓게 → 파이썬이 정밀 판정" 구조에서 **조용한 누락은 발생하지 않는다**(설계 안전 확인).
   반대로 row_only 131건은 파이썬이 '완료일 미상'으로 분류한다 — 암묵 drop 금지(§12) 계약 대상.
4. **`schedule.construction.date` 는 콤마 조인 복수 날짜 문자열**을 담는다(예 `"2026-05-27, 2026-05-28"`, 55건).
   완료 대시보드 `_completion_month_key`는 `text[:7]`이라 **첫 날짜의 월**에 귀속시킨다 — 파리티를 위해 커널도 동일 규칙.

### Q2 — 채널 (판정: v1 채널 카드는 사실상 전량 '일반')

| 항목 | 값 |
|---|---|
| `external_order_links` 총계 | 206행 (전부 `channel='NAVER'`) |
| └ `order_id IS NULL`(SET NULL 끊김) | **74행 (35.9%)** |
| └ 실제 주문에 링크됨 | 132행 → 고유 주문 **32건** |
| dangling(없는 주문 id 참조) | 0 |
| **모집단(대상 상태+active)에서 링크 있는 주문** | **0건** |
| `structured_data.naver.source` | **운영 전체 0건 — 필드가 존재하지 않는다** |
| `structured_data.naver.*` 다른 키 | 27건 (`product_order_id`·`payment`·`claim` 등 16키) |

**Q2 답**: 스펙 §3.4의 "`naver.source` 전수성 미확인"은 **"필드 자체가 운영에 없음"으로 확정** — 판정 소스 후보에서 제외(스펙 결론과 동일 방향, 근거만 강해짐).
채널 판정은 `ExternalOrderLink` LEFT JOIN 유지가 맞다. 다만 **현재 운영에서 정산 대상 상태인 네이버 주문이 0건**이라
채널 카드는 100% '일반'으로 렌더된다(오류가 아니라 데이터 현실). 링크 74행이 `order_id IS NULL`인 것은
수집만 되고 주문 승격이 안 된 건이며, 이들은 애초에 주문이 없으므로 채널 비중을 왜곡하지 않는다.
→ **리스크 "채널 오귀속"은 v1에서 실질 0.** 네이버 승격 이후 재측정 대상으로만 남긴다.

### Q2 부수 — 네이버 코드 승격 상태
`ExternalOrderLink` 를 **쓰는 애플리케이션 코드가 `deploy` 브랜치에 없다**(모델·마이그레이션만 존재).
수집 코드는 미커밋/미머지(`foms/services/integrations/` 는 현재 작업 트리에 untracked, 별도 워크트리 `C:\tmp\foms-naver-status`).
운영 DB에 206행이 있는 것은 그 코드가 이미 운영에 배포된 적이 있음을 뜻한다 — **정산 대시보드는 이 축에 의존하지 않는다**(LEFT JOIN 이므로 0행이어도 안전).

### 부수 — 정산 처리 현황 카드의 운영 실태 (모집단 2,168 기준)

| 필드 | 건수 |
|---|---|
| `settlement.deductions` 키 존재 | **0** |
| `settlement.cash_receipt_state = requested` | **0** |
| `settlement.cash_receipt_state = issued` | **0** |
| `shipment.as_billing.type = 'paid'` | 4 |
| `payment.balance_confirmed` true | 256 |
| `payment.deposit_confirmed` true | 670 |

→ "정산 처리 현황" 카드(청구완료 비율·현금영수증 대기·부서 차감 합)는 **운영에서 전부 0으로 렌더된다.**
기능 결함이 아니라 미사용 필드다. 카드는 스펙대로 만들되 **빈 상태(0건) 표기를 설계에 포함**해야 한다.
주의: `cash_receipt_state`는 파생값(`_cash_receipt_state`)이고 저장 원본은 `payment.cash_receipt`(자유텍스트)+`settlement.cash_receipt.issued`다 — 위 SQL은 저장 키 기준이라 파생 결과와 다를 수 있다(M1에서 커널로 재집계해 확정).

### 부수 — §4.4 단계별 물린 금액 모집단
`erp_stage_code` 분포(active + ERP): COMPLETED 1,434 / MEASURE 654 / AS_COMPLETED 398 / AS_RECEIVED 79 / DRAWING 43 / CONSTRUCTION 2.
→ **완료 계열 제외 시 699건**(MEASURE 654 + DRAWING 43 + CONSTRUCTION 2). 스펙 예측대로 '해피콜' 단계는 없다.

## 결정 사항

- **D1 (Q6, 주 버킷)**: **월 내 주차**를 채택한다(목업과 동일). ISO 주는 월 경계에서 전월/당월 비교선이
  어긋나 §7 필터바의 "전월 비교"와 정합하지 않는다. 경계 규칙 = 해당 월 1일이 속한 주가 1주차, 주 시작은 월요일.
  M1 테스트에 경계 케이스 고정.
- **D2 (Q5, 수금 근사)**: 스펙 §3.5 "완료월 귀속" 근사를 그대로 채택. `PAYMENT_CHANGED` 역산은 비용 대비 이득이
  없다(운영 `deposit_confirmed` 670·`balance_confirmed` 256건이라 표본은 있으나 확인 *시각*이 없다는 사실은 불변).
  화면 라벨에 "완료월 귀속" 명기 — 스펙 문구 유지.
- **D0 (작업 위치) — 메인 트리가 낙후돼 있어 세션 워크트리로 옮겼다**:
  `C:\DEV\FOMS` 의 로컬 `deploy` 는 **2026-07-30(4e1570b1)에서 갈라져 `origin/deploy` 보다 1,282 커밋 뒤**이고
  로컬 전용 커밋이 248개(2026-07-30~08-28) 있다. 트리 내용 차이 **505 파일 / +88,826줄**.
  → 이 트리에서 구현하면 승격 시 대규모 충돌이 확정이다.
  **작업 위치 = `c:\tmp\foms-s-settle-dash` (브랜치 `session/settle-dash`, base `origin/deploy` 98ec0bfa)**.
  목업 5·리서치 5·스펙·원장 2를 이 워크트리로 복사해 여기서 커밋한다.
  ⚠️ **메인 트리의 낙후·미푸시 248 커밋은 본 작업 범위 밖의 별건**이다 — 손대지 않았다. 사용자 확인 필요.
- **D6 (파일 배치) — 스펙 §6 의 `settlement/` 디렉토리 신설은 계약 위반**:
  `tests/contracts/runtime/foms_namespace_surface_tests.py` 가 `templates/`·`foms/web/`·`foms/api/`·`foms/services/`
  최상위 디렉토리를 **allowlist 와 정확히 일치(`==`)** 하도록 강제한다(SLG-B1 동결). `settlement` 은 4곳 모두에 없다
  → 새 디렉토리를 만드는 즉시 계약 red. origin/deploy 에서도 동일(재확인 완료).
  **교정 배치**(전부 기존 허용 디렉토리 또는 flat 모듈):
  | 계층 | 스펙 §6 원안 | **교정안** |
  |---|---|---|
  | 서비스 | `foms/services/settlement/aggregation.py` | `foms/services/settlement_aggregation.py` (flat) |
  | 페이지 | `foms/web/settlement/dashboard.py` | `foms/web/cs/settlement_dashboard.py` |
  | API | `foms/api/settlement/aggregates.py` | `foms/api/cs/settlement.py` |
  | 템플릿 | `templates/settlement/dashboard.html` | `templates/cs/settlement_dashboard.html` |
  URL 경로(`/erp/settlement`, `/api/settlement/aggregates`)는 Blueprint `url_prefix` 로 정하므로 **스펙 그대로 유지**된다.
- **D3 (잔금 클램프) — 해소됨**: 낙후 로컬 트리에서는 계약 테스트 3건이 red 였으나,
  **`origin/deploy` 에는 이미 클램프가 머지돼 있다**:
  `foms/web/cs/completion_dashboard.py:163-166` (그리고 시트 :491-494) 가
  `_balance_after_payments(shipping_price, deposit or 0)` 를 쓴다.
  → 정산 커널도 **동일 헬퍼**를 쓰면 파리티가 완전 일치한다. 아래 red 기록은 낙후 트리의 산물이며 이관 후 무효다.
  <details><summary>낙후 트리에서 관측된 red (참고 기록)</summary>
  ```
  FAILED tests/domains/test_tablet_t2_contract.py::test_completion_grid_route_derives_amounts_from_ssot_helpers
  FAILED tests/domains/test_tablet_t2_contract.py::test_completion_row_clamps_balance_when_only_deposit_present
  FAILED tests/domains/test_tablet_t2_contract.py::test_completion_sheet_context_clamps_balance_when_only_deposit_present
    AssertionError: assert '-1,229,000' == '0'
  ```
  </details>

  **확정: 정산 커널은 `_balance_after_payments(출고가, 예약금 or 0)` 를 쓴다.**
  운영에 클램프 전 기준 **음수 잔금이 541건** 실재하므로(대부분 품목가 0 + 예약금만 있는 승격 주문)
  클램프 유무는 실데이터에 실제로 영향을 준다. 미수 KPI 는 `잔금>0` 만 합산하므로 미수 총액은 불변.
  ⚠️ 완료 대시보드 본체는 손대지 않는다(이미 upstream 에서 해결됨).
- **D4 (모집단 조건 보정)**: 스펙 §4.1 모집단에 **`Order.is_erp_order.is_(True)` 가 빠져 있다.**
  완료 대시보드 베이스(`foms/api/cs/dashboard.py:79-88`)는 이 조건을 건다. 빠뜨리면 비-ERP 레거시 주문이
  정산 집계에만 섞여 파리티가 깨진다. **커널 모집단에 추가한다.**
  (실측: 모집단 2,168 중 ERP 여부별 분해는 M1 테스트에서 고정.)
- **D5 (완료일 미상)**: 운영 254건(11.7%)이라 무시 불가. 커널은 `UNKNOWN` 버킷으로 **분리 반환**하고
  화면이 이를 표기한다(암묵 drop 금지). 기간 합계에는 넣지 않되 "완료일 미상 N건 / M원"을 카드 각주로 노출.

## 커밋 로그

_(T별 SHA)_

## BLOCKED / 미결

_(없음)_

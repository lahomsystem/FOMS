# 프리랜서 영업 수수료 설계서 (FCOMM-01) — 2판

> 작성 2026-11-06 · 상태: **승인됨(2026-11-06, §14 답 반영)** · 등급 `**C`(DB·권한·API 코어 변경)
> 1판 → 2판: 교차 검수 3개(반증 20 · 단순화 12 · 사실 검증 62/틀림 4) 반영. 처리 원장 `docs/plans/2026-11-06-freelancer-commission-review-ledger.md`.
> 입력 프롬프트: `docs/plans/2026-11-06-freelancer-commission-design-prompt.md`(커밋하지 않는 로컬 파일 — 결정 원문은 §1 에 옮겼다).
> 저장소가 공개다. 실제 고객 정보·프리랜서 실명·요율 숫자를 코드와 시험에 넣지 않는다(요율은 설정값). 시험은 가짜 값만.

## 0. 한눈에

- 지금은 프리랜서 1명당 엑셀 시트 1장으로 수수료를 계산한다. 이것을 ERP 안으로 옮긴다.
- 회계팀은 이미 등록된 주문 위에 **시공비**와 **차감**만 넣는다. 고객·품목·금액·날짜는 주문에서 온다.
- 프리랜서는 폰에서 **자기 수수료만** 본다. 3단계부터는 **자기 담당 주문만** 본다.
- 관리자는 설정 화면에서 프리랜서마다 **맞출 이름 · 시작 달 · 요율(적용 달) · 세금 방식**을 정한다.
- 매월 10일에 지난달까지의 **시공 완료분**을 지급한다. 한 번 마감에 들어간 주문은 주인·거래구분이 굳고, 뒤에 바뀐 금액은 다음 마감의 **조정 줄**로 들어간다.

## 1. 결정 원장

### 1.1 사용자 결정 (구현 중 다시 묻지 않는다)

| ID | 결정 | 출처 |
|---|---|---|
| D1 | 주문 1건 수수료 = `(출고가 − 시공비 − 차감) × 요율`. 차감은 곱하기 전에 뺀다. 0 미만이면 0 | 11-06 질문 창 |
| D2 | 총 견적 = 주문 화면 "출고가"(`#erp-items-total`, `totals.shipping_price` = 품목 합 + 자유 입력 − 할인). 부가세를 가르지 않는다 | 11-06 답글 |
| D3 | 발주사 칸에서 프리랜서 이름을 고를 수 있다. 라홈 → 라홈 요율, 하우드 → 하우드 요율, 프리랜서 본인 → 개인영업 요율 | 11-06 질문 창 |
| D4 | 발주사가 숨고인 주문은 회계팀이 건마다 요율을 고른다 | 11-06 질문 창 |
| D5 | 요율은 프리랜서마다 다르다. 관리자 설정 화면(컨트롤 패널)에서 정한다 | 11-06 답글 |
| D6 | 수수료 달 = 시공 완료 기준 | 11-06 질문 창 |
| D7 | 화면은 "시공 완료 기준"(기본)과 "실측일 기준"으로 바꿔 볼 수 있다. 지급은 언제나 시공 완료 기준 | 11-06 질문 창 |
| D8 | 프리랜서마다 시작 달. 시작 달 1일 이후 **실측한** 주문부터 대상 | 11-06 질문 창 2회 |
| D9 | 정산일 = 매월 10일 | 11-06 답글 |
| D10 | 마감 뒤 바뀐 것은 다음 달 조정 줄 | 11-06 답글 |
| D11 | 세금 방식은 프리랜서마다: 3.3% 원천징수 / 부가세 10% 더함 / 없음 | 11-06 질문 창 |
| D12 | 프리랜서는 자기 담당 주문만 본다(규칙 6개, §6.1) | 11-06 질문 창 3회 |
| D13 | 차감은 기존 차감 기록(`structured_data.settlement.deductions[]`) 한 곳에만. 수수료 탭 안에서 같은 기능으로 넣는다 | 11-06 UI 조사 위임 |
| D14 | 개인영업 주문의 알림톡·견적서 회사 이름은 추후 결정. 지금 동작 유지 | 11-06 답글 |
| D15 | 실측 날짜가 빈 주문은 D8 판정에 주문 접수일(`orders.received_date`) | 11-06 질문 창 |
| D16 | 요율을 바꿀 때 적용할 달(시공 완료 달)을 고른다 | 11-06 질문 창 |
| D17 | 프리랜서 차감이 생기면 프리랜서 폰으로 알림 | 11-06 질문 창 |
| D18 | 수수료 계산의 출고가는 **취소 품목을 뺀 값**(주문 화면 숫자는 그대로) | 11-06 승인 질문 Q1 |
| D19 | 이미 있는 구멍 두 개(§6.4)는 3단계 때 같이 고친다 | 11-06 승인 질문 Q2 |
| D20 | 발주사에 프리랜서 이름이 들어간 주문의 손님 알림톡 "발주사" 글은 추후 결정 — 그때까지 코드 변경 없음 | 11-06 승인 질문 Q3 |

### 1.2 설계 판단 (승인 때 함께 확인받는다)

| ID | 판단 | 이유 |
|---|---|---|
| J1 | **시공 완료** = 주문의 메인 단계(`orders.erp_stage_code`)가 `CS` 또는 `COMPLETED`. `order.status` 글자와 AS 축은 보지 않는다. 달 = 시공일(`schedule.construction.date`, 여러 날이면 첫 날)의 `YYYY-MM` | 시공 완료 버튼이 메인 단계를 CS 로 옮긴다(`foms/api/construction/orders.py:442,461`). `order.status` 는 보류·AS·물류가 앞서는 우선순위 글자라 틀린다(`foms/services/orders/state_axes.py:311-325`). AS 는 본공정과 무관하게 접수돼(`as_cycle_service.py:513`) 시공 전 주문을 끌어들인다. 첫 날 달은 정산 대시보드와 같다(`settlement_aggregation.py:126-140,546`) |
| J2 | 내려받기는 엑셀에서 열리는 CSV(BOM·CRLF). XLSX 는 만들지 않는다 | `pandas`·`openpyxl` 등과 "excel"/"xlsx" 낱말이 시험으로 금지(`tests/domains/test_settlement_channel_export.py:174-175`) |
| J3 | 주문별 수수료 = `(기준액 × bp + 5000) // 10000`(원 단위 반올림, 정수식). 3.3% = 소득세 3%(10원 미만 버림) + 지방소득세 = 소득세 × 10%(10원 미만 버림). 부가세 = 10%(원 미만 버림). 세금은 마감 합계에 한 번 | 파이썬 `round()` 는 짝수 반올림이라 엑셀과 1원 어긋난다. 원천징수는 국내 관행. 계산 함수 한 곳에 둔다 |
| J4 | 시공비·회계팀 지정 요율은 주문 JSONB 가 아니라 새 테이블 | 표에서 연달아 넣을 때 큰 JSONB 를 다시 쓰지 않고, CS 의 주문 저장과 버전 충돌이 나지 않게 |
| J5 | 설정 화면 편집은 ADMIN, 보기는 회계팀도 | 요율은 경영 결정 |
| J6 | 단계: ① 계산·화면 → ② 마감·지급 → ③ 보기 범위 제한 | 첫 지급(12-10)에 ①②가 필요하다. 지금 프리랜서는 회사 영업 출신이라 이미 전체를 보고 있어 ③이 늦어져도 지금보다 나빠지지 않는다. **프리랜서를 새로 받기 전에 ③을 끝낸다** |
| J7 | 프리랜서 설정(맞출 이름·시작 달·세금·요율 이력)은 `SystemSetting` 한 줄(JSON, version 잠금) | 1명~소수라 표 2개가 과하다. 선례 `foms/services/partners/statement_profile.py:22,104-142`. 요율 숫자가 코드에 들어가지 않는다(저장소 공개) |
| J8 | 수수료 주인은 **설정의 "맞출 이름"**(관리자가 정함)과 주문 이름 칸의 완전 일치로 정한다. `User.name` 을 쓰지 않는다. 맞출 이름이 **다른** 활성 사용자의 이름과 겹치면 저장 거부 | 프리랜서가 내 정보에서 이름을 바꿔 남의 주문을 가져가는 길(`foms/web/auth/routes.py:1245-1256`)과 동명이인을 막는다 |
| J9 | 한 주문이 처음 마감에 들어가면 **주인·거래구분·요율을 그 줄에 굳힌다**. 뒤의 다시 계산(조정)은 굳힌 주인·거래구분 기준. 요율은 회계팀 지정 요율이 바뀐 경우만 새 값 | 마감 뒤 담당이 바뀌면 이중 지급·누락이 생긴다 |
| J10 | 1·2단계는 주인을 **계산할 때** 이름 일치로 정한다. 주문↔프리랜서 연결 표는 3단계(보기 범위)에서 만든다 | 연결 표는 이름 일치의 투영이라 뜻이 같다. 저장 관문을 건드리는 가장 위험한 수정을 첫 지급 범위에서 뺀다 |

## 2. 페르소나와 화면 흐름

### 2.1 회계팀 — 정산 담당 (PC, 엑셀 익숙)

1. `/erp/settlement` → "영업 수수료" 탭. 프리랜서와 달(기본: 지난달)을 고른다.
2. 표(엑셀과 같은 순서): 시공일 · 고객명 · 품목 · 거래구분 · 출고가 · 시공비 · 차감 · 요율 · 수수료. 맨 위 합계 한 줄.
   - "이번 마감에 들어갈 줄" = 아직 어느 마감에도 없는 대상 주문 중 시공 완료 달 ≤ 고른 달(§8.1). 지난달에 시공비가 없어 빠진 주문도 여기 다시 나온다.
   - 이미 마감된 주문 중 금액이 바뀐 것은 "조정" 줄로 따로(2단계 후반).
3. 시공비 칸에 바로 넣는다. Enter 로 다음 줄. 칸마다 자동 저장, 실패하면 그 칸만 빨갛게.
4. 숨고·직접입력 발주사 줄은 요율 칸이 비어 있고 회계팀이 고른다(D4).
5. 차감 칸을 누르면 작은 창: 금액 · 사유(부서 = 영업, 사람 = 그 줄 프리랜서로 고정). 차감 칸은 합계, 누르면 목록과 [취소].
6. 표시 하나: 그 줄의 발주사·실측일·시공일·출고가를 **프리랜서 본인이** 바꾼 기록이 있으면 줄 끝에 "본인 수정" — 누르면 무엇을 언제 바꿨는지(`order_field_changes`).
7. [마감] → 확인 창(줄 수 · 합계 · 세금 · 실지급) → 잠김. 10일에 보낸 뒤 [지급 완료].
8. [내려받기] → 지금 엑셀과 같은 칸 + 조정 줄 + 세금 줄의 CSV.

### 2.2 프리랜서 — 현장 영업 (휴대폰)

1. 모바일 "더보기" 서랍에 "내 수수료" 한 줄(프리랜서에게만). 3단계에서는 프리랜서 하단 탭에 들어간다.
2. `/erp/my-commission`(서버에서 그린 화면, 스크립트 없음):
   - 위: 이번 10일 받을 돈(마감됐으면 확정, 아니면 예상) · 세금 뺀 실제 금액.
   - 기준 전환: 시공 완료 / 실측일(링크). 달 앞뒤 이동(링크).
   - 아래: 주문 줄(고객명 · 시공일 · 거래구분 · 수수료). 시공비가 없으면 "시공비 기다림".
   - 줄을 펼치면(`<details>`) `2,500,000 − 1,000,000 − 0 = 1,500,000 × 4% = 60,000원`(예시 숫자) 한 줄과 차감 사유.
3. 차감이 생기거나 취소되면 폰 알림 → 누르면 그 달 화면(D17).

글 규칙: 해요체, 같은 말 한 번, 코드 이름 금지. 390px 폭 실화면으로 먼저 본다.

### 2.3 관리자 — 설정 화면 `/admin/sales-freelancers`

- 사용자 요청이 "컨트롤 패널"이라 작은 화면 하나를 따로 둔다(선례: 협력사 명세서 양식 화면 — 템플릿 26줄 · 스크립트 76줄).
- 목록: 맞출 이름 · 계정 · 시작 달 · 지금 요율 3개 · 세금 방식 · 켜짐.
- [추가]: 기존 계정 고르기(역할 STAFF · 팀 SALES 여야 함) + 맞출 이름 + 시작 달 + 세금 방식 + 첫 요율.
- 요율 바꾸기: 3칸 + 적용 달(D16). 이미 마감된 달 이하로는 거부. 이력 표.
- 저장은 version 비교(409) + 감사 기록. 회계팀은 보기만.
- 맞출 이름은 운영 준비 때 출고설정 "실측 담당자" 목록에도 넣어야 담당자 칸 자동완성에 뜬다(코드 수정 없음 — §12 운영 준비).

### 2.4 CS

- 담당자 뱃지에 프리랜서를 넣고 뺀다. 완료 화면에서 영업 귀속 차감을 넣을 수 있고, 그 차감은 수수료 탭에도 보인다(D13).

## 3. 계산 규칙 (정본 — 순수 함수 `foms/services/sales_commission/calc.py`)

### 3.1 주인과 거래구분 (J8 · J10)

이름 정리 = 앞뒤 공백 제거 + 유니코드 NFC. 활성 프리랜서의 맞출 이름 표 `{이름: user_id}` 와 완전 일치만 인정.

1. 발주사(`parties.orderer.name`)가 프리랜서 F 의 맞출 이름이면 → 주인 F, 거래구분 **개인영업**.
2. 아니면 대표 담당자(`parties.manager.name`)가 F 의 맞출 이름이면 → 주인 F, 거래구분은 발주사로:
   - '라홈' 포함 또는 네이버 주문 → **라홈**(기존 `brand_channel_of` 규칙, `settlement_aggregation.py:475-494`)
   - '하우드' 포함 → **하우드**
   - 그 밖 → **회계팀 지정**(요율 빈칸)
3. 둘 다 아니면 대상 아님.

제외: 협력사 주문(`partner_org_id`), 초안·삭제 주문(`Order.active_filter()`), ERP 주문이 아닌 것.
마감된 주문은 굳힌 주인·거래구분을 쓴다(J9).

### 3.2 대상 여부 (D8 · D15)

기준 날짜 = 실측일(`schedule.measurement.date`), 비었으면 접수일(`received_date`, 빈 글자면 `created_at` 날짜). 기준 날짜 ≥ F 의 시작 달 1일이면 대상.

### 3.3 달 (D6 · D7 · J1)

- 시공 완료: `erp_stage_code ∈ {CS, COMPLETED}` 이고 시공일이 있다. 달 = 시공일 첫 날의 `YYYY-MM`.
- 실측일 기준 달: 실측일(없으면 접수일)의 `YYYY-MM`. 보기 전용, 단계 조건 없음. 시공 완료 전 줄은 "예상".

### 3.4 금액

- 출고가(수수료용) = 취소 품목(`is_item_cancelled`, `foms/services/orders/drawing_confirm_partial.py:74`)을 뺀 품목 합 + 자유 입력 − 할인, 0 미만 없음(D18). 공식은 `erp_shipping_price_from_structured`(`foms/services/erp_display.py:322`)와 같고 품목에서 취소분만 뺀다 — 그 함수 자체는 바꾸지 않는다(주문 화면 숫자 유지).
- 시공비 = `sales_commission_inputs.install_cost`. 없으면 "시공비 기다림", 계산 안 함, 합계·마감에서 빠짐.
- 차감 = 유효한 차감(§10.1) 중 `department == "SALES"` · `charge_to_user_id == F` 의 금액 절대값 합.
- 요율 = F 의 요율 이력에서 시공 완료 달에 적용되는 값(effective_month ≤ 달 중 가장 늦은 것). 회계팀 지정 줄은 `rate_override_bp`. 단위 basis point(100bp = 1%).
- 수수료 = `(max(0, 출고가 − 시공비 − 차감) × bp + 5000) // 10000`.

### 3.5 세금 (D11 · J3)

마감 합계 S 에 대해: 3.3% → 소득세 = S×3//100 을 10원 미만 버림, 지방 = 소득세//10 을 10원 미만 버림, 실지급 = S − 둘. 부가세 → S×10//100, 실지급 = S + 부가세. 없음 → S.

## 4. 데이터 (마이그레이션 `fcomm_00`, down_revision = 작업 시점 origin/deploy head — 지금 `csagent_07`)

### 4.1 설정 `SystemSetting["sales_freelancer_settings"]` (J7)

```json
{"freelancers": {"<user_id>": {
  "match_name": "…", "start_month": "2026-11", "tax_type": "WITHHOLD_3_3|VAT_10|NONE", "active": true,
  "rates": [{"effective_month": "2026-11", "lahom_bp": 0, "haud_bp": 0, "personal_bp": 0, "by": 1, "at": "…"}]
}}}
```

저장 함수가 검사: 맞출 이름 유일(본인 말고 다른 활성 사용자의 `User.name` 과도 안 겹침), 계정 STAFF·SALES·활성, bp 0~10000, 마감된 달 이하 적용 달 거부. version 비교 + `with_for_update` + 감사(`SecurityLog`).

### 4.2 `sales_commission_inputs` (J4)

| 칸 | 형 | 설명 |
|---|---|---|
| order_id | Integer, FK orders **ondelete CASCADE**, PK | `tests/postgres/test_delete_retention.py:159` FK 검사 통과 조건 |
| install_cost | BigInteger null | 시공비 |
| rate_override_bp | Integer null, CHECK 0~10000 | 회계팀 지정 요율 |
| note | Text null | 메모 |
| version | Integer NOT NULL default 1 | 칸 저장 충돌 방지 |
| updated_by_user_id | FK users null | |
| updated_at | DateTime | |

### 4.3 `sales_commission_closings` (2단계)

| 칸 | 형 | 설명 |
|---|---|---|
| id | PK | |
| user_id | FK users | |
| month | String(7) | 마감 달 |
| status | String(8) CHECK `CLOSED`/`PAID` | |
| gross, tax_income, tax_local, vat, net | BigInteger | |
| tax_type | String(16) | 마감 때 값 |
| lines | JSON | 줄 스냅샷 배열(아래) |
| closed_by_user_id, closed_at, paid_by_user_id, paid_at | | |

unique(user_id, month). 지급 전 [마감 취소] = 행 삭제 + 감사 기록(VOID 상태 없음).

줄 하나: `{order_id, kind: NORMAL|ADJUST, deal_type: LAHOM|HAUD|PERSONAL|MANUAL, shipping_price, install_cost, deduction_total, rate_bp, commission, label}`. `label` = 고객명·품목 스냅샷(내려받기용).

### 4.4 `order_freelancer_links` (3단계 — §5)

| 칸 | 형 | 설명 |
|---|---|---|
| id | PK | |
| order_id | FK orders ondelete CASCADE, index | |
| user_id | FK users, index | |
| relation | String(16) CHECK `MANAGER_PRIMARY`/`MANAGER`/`ORDERER`/`CREATOR` | |

unique(order_id, user_id, relation). 부분 인덱스를 쓰면 `postgresql_where` 와 `sqlite_where` 를 같이 적는다(`models.py:531-534` 선례).

## 5. 주문 ↔ 프리랜서 연결 (3단계)

- 연결은 투영이다. 정본은 `parties.manager.name/names`, `parties.orderer.name`, 주문 만든 사람(`OrderEvent ORDER_CREATED.created_by_user_id`, 초안 주인).
- **쓰는 자리: 전역 `before_flush` 훅**(선례 `foms/services/order_date_sync.py` — "모든 쓰기 경로가 지나는 유일 지점"). `sync_erp_flat_columns` 에 넣지 않는다 — 그 함수는 읽기 전용 점검의 가짜 객체(`foms/services/orders/erp_flat_audit.py:133-137` `_DeriveShim`)와 시험의 SimpleNamespace 로도 불리고, `object_session()` 이 그런 객체에서 예외를 낸다. 또 `flag_modified(structured_data)` 하면서 그 함수를 안 부르는 쓰기 파일이 28개 있고 오프라인 병합(`offline_recovery.py:243-256`)도 안 부른다.
- 훅은 Order 인스턴스이고 structured_data 가 바뀐 경우만 연결을 다시 계산한다. 맞출 이름 표는 요청당 1회.
- `CREATOR` 연결: 프리랜서가 만든 주문은 담당 칸과 무관하게 본인에게 보인다(자동 저장이 서버가 채운 담당을 지우는 문제 대응 — `erp_orders_structured.py:2357-2365` 통째 교체, 마법사 `erp_order_draft.py:217-220`). 담당 칸 기본값은 화면에서 본인 이름으로 채운다.
- 되채우기: `scripts/maintenance/backfill_freelancer_links.py`(드라이런 기본). 훅 켜기 전에 돌린다.
- 배정 알림(`SALES_ORDER_ASSIGNED`)은 "초안 아님 · 되채우기 아님 · 이전 커밋에 없던 MANAGER 관계"일 때만. 서버 시작 때 최근 주문을 다시 sync 하는 경로(`app_init.py:51-81`)는 알림을 내지 않는다.

## 6. 권한과 보기 범위 (3단계, D12)

### 6.1 규칙 (사용자 결정)

1. 실측 배정 때 담당자로 들어가면 그때부터 보인다.
2. 당일 추가 주문은 CS 가 담당자 뱃지에 넣는 즉시 보이고 폰 알림이 간다.
3. 프리랜서가 직접 등록한 주문은 본인에게 보인다(`CREATOR`).
4. 담당에서 빠지면 안 보인다. 쌓인 수수료 기록은 남는다.
5. 연결은 계정(맞출 이름 → user_id, J8).
6. 담당이 아닌 주문은 CS 가 뱃지를 붙인다.

"내 주문" = `order_freelancer_links` 에 (주문, 나) 행이 있다. 이것 하나만 쓴다 — 퀘스트 담당 이름·시공자 이름·`sales_assignee_user_ids` 같은 다른 이름 판정은 프리랜서에게 쓰지 않는다(`foms/services/erp_permissions.py:162-202,348`).

### 6.2 지금 상태 (전수 조사, origin/deploy `65dec3151`)

- 직원 세션 GET endpoint 약 230개. 주문 단위 읽기 판정은 파일 3개뿐이고 직원에게 늘 참(`order_mutation_policy.py:427-454`).
- "내 것만" 거르기는 손님 쪽 값(`?mine=`·쿠키)으로 끌 수 있다(`foms/services/common/erp_mine_filter.py:10-34`). 강제는 시공팀뿐.
- 공통 목록 쿼리가 없다. → 화면을 하나씩 막는 방식은 안 되고 기본 거부 문지기를 쓴다.

### 6.3 다섯 겹

**겹 1 — 기본 거부 문지기** `freelancer_gate`: `foms/platform/http.py` 의 `partner_gate` 바로 뒤 `before_request`. 프리랜서면 endpoint 이름이 허용 목록에 없을 때 `/api/`·GET 아닌 요청은 403, 그 밖은 프리랜서 홈으로. 허용 목록 밖 쓰기는 여기서 모두 막히므로 쓰기 정책 엔진에 프리랜서 허용 정책 목록을 따로 두지 않는다.

허용 목록 초안(3단계 첫 task 에서 스테이징 실화면으로 확정):
- 공통: `static`, `auth.logout`, 알림 목록·배지·읽음·푸시 구독, 공지 보기. **`auth.profile` 은 보기만**(이름 저장 거부 — J8 과 별개로 화면 표시 이름도 관리자만 바꾼다).
- 홈·목록: 모바일 홈·목록, 월 달력, 실측 판 + 실측 요약 API — 겹 3 강제와 함께.
- 주문 1건: 모바일 상세, 편집 화면·조각, structured GET/PUT, 이벤트·변경 이력, 첨부 목록·올리기, `files.*` — 겹 2 와 함께.
- 등록: ERP 초안 만들기·자동 저장·등록, 마법사 초안, 주소 찾기, 붙여넣기 해석.
- 수수료: `/erp/my-commission`.

허용하지 않는 것(대표): 통합 검색·이력 검색·첨부 검색, 공유 링크 만들기, 주문 복사, 알림톡·채널톡 보내기, 채팅 전체, 지도, 완료·출고·생산·시공·도면 판, 오프라인 큐, 옛 목록 화면, 견적 계산기 검색, 내려받기.

**겹 2 — 주문 단위 판정**
- `user_can_read_order` 에 프리랜서 분기(연결 표). 파일 관문·긴급 호출·채널톡 `/foms` 가 자동으로 바뀐다.
- 문지기가 허용 endpoint 의 URL 인자(`order_id`·`id`)와 **query string 의 주문 번호**(`focus_order` 등 — 모바일 홈 `?focus_order=` 가 mine 없이 남의 주문을 끼워 넣는다, `foms/web/orders/dashboard.py:222-230`)를 같은 판정으로 본다. 아니면 404.
- 본문에 주문 번호를 싣는 허용 endpoint(첨부 올리기 세션 등)는 핸들러에서 같은 함수로 판정하고 시험으로 확인한다.

**겹 3 — 목록 강제 거르기 + 허용 화면 조각 전수 점검**
- `erp_mine_filter` 에 프리랜서 강제 켜짐. `build_mine_sql_filter` 와 파이썬 판정 `is_order_related_to_user` 둘 다 프리랜서면 "연결 표 EXISTS 하나만".
- 허용 화면마다 **mine 밖에서 계산되는 조각**을 끈다. 이미 찾은 것:
  - 실측 판의 네이버 일괄 발송 띠(사용자 무관 전체 주문 고객명, `foms/web/measurement/dashboard.py:592`, `naver_dispatch_strip.html`) → 프리랜서는 `None`.
  - 모바일 홈 검색의 "과거 이력에 N건 더"(`orders/dashboard.py:108-121,212-217`) → 끔.
  - 3단계 첫 task 에서 허용 화면 전부를 같은 눈으로 다시 훑는다.

**겹 4 — 수수료를 스스로 바꾸는 길**
- 프리랜서가 이미 있는 주문의 발주사를 바꾸는 저장은 거부(라홈↔하우드, 프리랜서 이름으로/에서). 등록 때 고르는 것은 허용.
- 실측일·시공일은 일 때문에 바꿔야 하므로 막지 않는다. 대신 1단계부터 수수료 탭 "본인 수정" 표시(§2.1-6)로 회계팀이 본다. 마감 뒤에는 J9 로 굳는다.

**겹 5 — 옆길**
- 알림 받는 사람: `recipients.py:73-128` 와 실시간 알림 쪽 `foms/api/notifications/__init__.py:74-131` 두 함수를 하나로 모아 같은 규칙을 쓴다 — ALL·ROLE·TEAM 대상에서 프리랜서 제외(협력사 `INTERNAL_USERS_ONLY` 선례), 담당 이름 대상은 연결 표로. 공지의 팀 펼침(`:943-1010`)도 같은 규칙. 시험은 소켓 전송 대상까지 본다.
- Socket.IO: 프리랜서는 채팅 이벤트(`join_room`·`send_message`·`typing`) 거부, 개인 알림 방만 허용. → **11-07 사내 채팅 자체를 지움(CHAT-DEL-01, `2026-11-07-internal-chat-removal_SPEC.md`)** — 채팅 이벤트가 없어 모든 계정이 개인 알림 방만 쓴다.
- 프리랜서로 지정할 때: 지정 전 받은 팀 알림 state 를 숨김 처리(채팅방 회원 해제는 채팅 삭제로 없앰, 11-07).
- 메뉴: 모바일 하단 탭 프리랜서 분기(홈 · 주문 등록 · 내 수수료 · 알림), 데스크톱 상단 메뉴도 허용 목록 밖 링크 숨김.

### 6.4 이미 있는 구멍 두 개 (프리랜서와 별개, 지금도 있음 — 코드로 확인)

D19: 3단계(T17)에서 같이 고친다.

| 구멍 | 지금 영향 | 제안 |
|---|---|---|
| Socket.IO `join_room` 회원 확인 없음(`foms/api/channel/socketio_handlers.py:48-63`) | 직원이면 남의 개인방 `user_<id>` 에 들어가 그 사람의 실시간 알림·채팅 사본을 받는다 | 채팅방은 회원만, `user_<id>` 는 본인만 |
| `/api/chat/download`·`/preview` 가 아무 저장소 key 에 서명(`foms/api/channel/files.py:205-267`) | 직원이면 채팅과 무관한 파일도 받는다 | key 가 내가 회원인 방의 첨부일 때만 |

### 6.5 시험 (막힘 전수)

- `tests/security/test_freelancer_gate.py`: 모든 URL 규칙을 프리랜서로 돌려 허용 목록 밖은 403/이동(협력사 `tests/security/test_partner_gate.py:125-145` 꼴).
- 허용 endpoint 중 주문 번호를 받는 것(URL·query·본문)마다: 남의 주문 404, 내 주문 200.
- 목록: `?mine=0`·쿠키를 지워도 남의 주문 없음. 실측 판 HTML 에 남의 고객명 없음.
- 쓰기: 허용 목록 밖 쓰기 403. 발주사 바꾸기 403. 프로필 이름 저장 거부.
- 알림: 팀 대상 알림·공지·도면 전달(담당 불일치)에서 프리랜서 소켓 전송 0.
- Socket: 프리랜서 `join_room` 거부.

### 6.6 자기 주문은 회사 영업 직원과 같게 (D26 → D27, 2026-11-07 운영 반영 뒤 사용자 결정)

사용자: "기존 주문건은 다 접근 및 주문변경 등 가능해야 돼"(D26 — 시작 달 전 주문만 풀기) → 이어서 "프리랜서도 주문건만 자기 것만 보이고 이전 회사 소속일 때랑 동일한 사용 가능해야 돼", "프리랜서도 매니저 등급으로" (D27 — D26 을 넓혀 대신함).

- **남은 프리랜서 제한은 주문 범위 하나다.** 남의 주문은 안 보이고 못 고친다(겹 1 문지기 · 겹 2 주문 단위 · 겹 3 목록 강제 · 겹 5 옆길 그대로). 내 정보 이름 고정(J8)도 그대로(맞출 이름과 같은 사람 표시).
- **자기 주문(연결 표 · 내가 만든 초안)에서는 회사 영업 직원과 같다** — 실측일과 무관. 걷은 것: 발주사 · 담당자 바꾸기 막기(D21 · A13), 채널톡 PUSH 종류(D22), 퀘스트 승인 단계(D23 · D25), 금융 쓰기 거부(§10.6 — 차감 · 입금 확인 · 현금영수증), 첫 등록 입금 확인 막기(R1 의 프리랜서 부분). 각 API 의 원래 권한(역할 · 팀 정책)이 그대로 판정한다.
  - 겹 1: 주문 번호를 URL 에 싣는 주문 일 API 목록(`freelancer_order_rights.OWN_ORDER_ENDPOINTS`)은 번호가 모두 내 주문이면 통과. 빼는 것: 관리자 · 협력사 · 협력사 명세서 · 회계 전용(수수료 입력 · 차감 취소) · 도면팀 전용 · 채팅.
  - 판 화면(도면 · 생산 · 출고 · 시공 · 완료 · AS · 이력 · 견적 계산기)은 묶음마다 "자기 주문만" 거르기와 시험을 넣고 `foms/services/auth/freelancer_screens/<묶음>.py` 로 연다(문지기가 폴더를 모아 더한다).
- **매니저 등급도 프리랜서가 될 수 있다**(`settings.FREELANCER_ROLES = {STAFF, MANAGER}`) — 운영 영업 계정은 모두 매니저 등급이다(11-07 운영 집계). 문지기 · 주문 범위는 등급과 무관하게 같고, 자기 주문 안에서는 매니저 권한(예: 휴지통으로 보내기)이 그대로 산다.
- **수수료 위험(사용자 수용)**: 자기 주문의 발주사 · 담당자 · 실측일을 바꿔 거래구분(개인영업 요율이 가장 높음) · 대상 여부를 바꿀 수 있다. 수수료 탭 "본인 수정" 표시 · 변경 기록으로 회계팀이 보고, 마감 뒤에는 J9 로 굳는다.
- **D27 반증 검토에서 고친 것**: AS 기준 일정 잇기 · 영업 전달 배정의 기준 주문을 `can_read_ref_order` 로 확인(남의 주문 = 없는 주문과 같은 404 — 날짜 · 담당자가 새지 않음). 계산기 견적 동기화(`wdc-estimate-sync`)는 본문 견적 번호가 그 주문에 이은 견적인지 핸들러가 확인한 뒤 연다(모든 직원 공통 구멍).
- **고객 공유 링크(D28, 11-07 사용자 "열기")**: 만들기 · 목록(주문 번호 API)에 더해 문자 · 알림톡 보내기 · 회수 · 열람 이력(목록 · 그때 화면)도 연다. 이 다섯은 주소에 링크 · 이력 줄 번호만 있어 겹 2 가 주문을 못 보므로 핸들러가 그 줄의 주문을 `user_can_read_order` 로 보고(`foms.api.share._share_hidden_from_user`), 남의 주문이면 없는 줄과 **같은 답**(보내기 · 회수 404 `share_not_found`, 이력 목록 빈 목록, 그때 화면 404)을 준다 — 번호만 바꿔 남의 링크를 끊거나 있는지 알아내지 못한다. 회사 직원은 이전과 같다(판정 안 함).
- **휴대폰 아래 탭 · 서랍(D30, 11-07 사용자 "기존 영업과 똑같이 + 수수료 탭")**: 아래 탭 = 회사 영업과 같은 탭(대시보드 · 실측 · 도면 · 출고) + 내 수수료 · 계산기 · 더보기. 서랍 = PC 메뉴와 같은 목록(`freelancer_nav_items` — 문지기가 여는 판 화면만, 계산기는 탭에).
- **11-08 점검 뒤 맞춤**: 머리 통합 검색 창(조각)도 연다 — 같은 거르기(`construction_scope_user`)로 내 주문만 그리고 "전체 결과"는 D27 로 열린 이력 화면으로 간다. 주문 일 API(`OWN_ORDER_ENDPOINTS`)에 남의 · 없는 주문 번호가 오면 다른 주문 API 와 같은 404 "주문을 찾을 수 없어요."(예전 403). 태블릿 가로 대시보드 주문 창(`erp_dashboard_tablet_sheet`)을 URL 주문 번호 판정으로 연다.
- **차감 귀속 인원 오류 문구(D29, 모든 직원 공통)**: 없는 번호 · 비활성 · 다른 부서 사람을 한 문구("선택한 사람을 이 부서에서 찾을 수 없어요.")로 — 번호를 바꿔 직원 명단 · 부서를 알아내지 못한다.
- 시험: `tests/security/test_freelancer_own_order_rights.py`(목록 전수 · 매니저 등급 · AS 기준 주문 음성 대조군), `test_freelancer_share_links.py`(공유 링크 — 남의 줄 = 없는 줄 음성 대조군), `test_freelancer_decisions.py` · `test_freelancer_edit_guards.py` · `test_settlement_deductions.py` 를 D27 로 바꿈.

## 7. 알림

- 1단계: `SALES_COMMISSION_DEDUCTION`(그 프리랜서 귀속 영업 차감이 생기거나 취소됨) — D17.
- 3단계: `SALES_ORDER_ASSIGNED`(§5 조건).
- 보내는 법: `Notification(target_type="USER", target_user_id=F)` → `fan_out_new_notification`(`recipients.py:174`) → 커밋 뒤 `enqueue_push_for_notification`(`push_sender.py:754`). 선례 `foms/services/partners/notify.py:79-109`.
- 웹 푸시 P1 목록(`foms/services/notifications/push_sender.py:90` `_DEFAULT_P1_TYPES`)에 등록 — 안 하면 폰에 안 간다.
- 글: "고객명 주문에 차감 50만원이 생겼어요 — 사유" / "새 주문이 배정됐어요 — 고객명".

## 8. 마감 · 조정 · 지급 (2단계)

### 8.1 마감 (회계팀, 프리랜서 F · 달 M)

- 대상 줄 = 아직 어느 마감에도 없는, §3 대상이면서 시공 완료 달 ≤ M 이고 시공비가 있는 주문. 시공비가 없는 줄은 빠지고, 시공비가 들어간 뒤의 마감에 들어간다. 시작 달(D8)이 아래 한계라 엑셀로 지급한 달은 들어오지 않는다.
- 순서: 이미 M 이상인 마감이 있으면 거부(달은 오름차순으로만).
- 잠금: 마감 트랜잭션에서 설정 행(`SystemSetting`)을 `FOR UPDATE` 로 잡는다 — 같은 F 의 동시 마감을 막는다.
- 합계 S(NORMAL + ADJUST) 가 0 이하면 마감 거부("이번 달은 줄 돈이 없어요"). 마감하지 않은 줄은 저절로 다음 마감으로 넘어간다(넘김 칸 없음).
- 줄 스냅샷 + 합계 + 세금을 한 트랜잭션으로. 감사 기록.

### 8.2 조정 줄 (D10 · J9) — 두 번째 지급(1-10) 전까지

- 마감할 때 F 의 이전 마감에 들어간 모든 주문을 굳힌 주인·거래구분으로 다시 계산한다. `지금 값 − 지금까지 그 주문에 대해 마감된 줄 합(NORMAL + ADJUST)` ≠ 0 이면 ADJUST 줄.
- 들어오는 것: 늦은 차감·차감 취소, 시공비 정정, 회계팀 지정 요율 변경, 출고가 변경(품목 추가·할인·품목 취소 — D18).
- 주문이 지워지거나 단계가 되돌려져도 이미 준 돈은 되돌리지 않는다(조정 대상에서 빠진다). 필요하면 회계팀이 차감으로 처리.
- 첫 지급(12-10)은 앞선 마감이 없어 조정이 없다.

### 8.3 지급 · 되돌리기

- [지급 완료] = PAID. 그 뒤로는 못 되돌린다.
- PAID 전 [마감 취소] = 행 삭제 + 감사 기록 → 다시 마감 가능.

## 9. API · 화면 목록

| 종류 | 경로 | 권한 | 단계 |
|---|---|---|---|
| 화면 탭 | `/erp/settlement` 안 "영업 수수료" 탭 | 화면 전체가 이미 `is_accounting_or_admin`(`foms/web/cs/settlement_dashboard.py:48-67`) | 1 |
| API | `GET /api/sales-commission/rows?user_id=&month=&basis=` | 기존 `SETTLEMENT_DASHBOARD_READ` | 1 (basis 는 2) |
| API | `PUT /api/sales-commission/inputs/<order_id>` {install_cost, rate_override_bp, note, version} | 새 `SALES_COMMISSION_WRITE`(gate `is_accounting_or_admin`) | 1 |
| API | 차감 넣기 = 기존 `POST /api/orders/<id>/settlement/issue` | 기존 `FINANCE_MUTATION` | 1 |
| API | `POST /api/orders/<id>/settlement/deductions/<ded_id>/void` {reason} | `SALES_COMMISSION_WRITE`(회계·관리자만) | 1 |
| API | `POST /api/sales-commission/closings` · `POST .../<id>/paid` · `DELETE .../<id>` | `SALES_COMMISSION_WRITE` | 2 |
| API | `GET /api/sales-commission/export.csv?user_id=&month=` | `SETTLEMENT_DASHBOARD_READ` | 2 |
| 화면 | `/erp/my-commission?month=&basis=` | 설정에 있는 프리랜서 본인(관리자·회계는 `?user_id=` 로 대신 보기) | 1 |
| 화면 | `/admin/sales-freelancers` | 보기 회계·관리자, 편집 ADMIN | 1 |
| API | `GET/POST /api/admin/sales-freelancers` | GET 회계·관리자, POST ADMIN(`ADMIN_OPS` 계열) | 1 |
| 서랍 링크 | `erp_mobile_menu_drawer.html` "내 수수료"(프리랜서만) | | 1 |

쓰기 라우트는 정책 manifest · write guard · audit 인벤토리에 넣는다(`tools/harness/refresh_inventories.py`). 새 정책은 `SALES_COMMISSION_WRITE` 하나.

## 10. 기존 차감 기능 보강 (D13 — 1단계에 필요한 것만)

1. **유효한 차감 판정 함수 하나**(`foms/services/settlement_deductions.py` 신설): 취소 표시(`voided_at`)가 없는 것만. 차감을 읽는 6곳이 모두 이 함수를 쓴다 — `foms/web/cs/completion_dashboard.py:186-188,443-468,530-532`, `foms/services/settlement_rows.py:360-362`, `foms/services/settlement_aggregation.py:394-421,570-575`.
2. **취소 API**: 지우지 않고 `voided_at/voided_by/void_reason` + `OrderEvent SETTLEMENT_DEDUCTION_VOIDED`. 회계·관리자만.
3. **차감 넣기·취소를 `execute_order_mutation` 으로**(행 잠금 + 버전 증가). 지금은 잠금 없이 JSONB 를 통째로 다시 써서(`foms/api/cs/dashboard.py:292,345-366`) 동시 저장이 사라진다.
4. **CS 단계 허용은 차감 핸들러 안에서만**. 공용 상수 `TARGET_STATUSES`(`erp_policy_constants.py:11` — 정산 모집단 여러 곳이 같이 씀)는 건드리지 않는다. 판정은 J1 과 같은 메인 단계 기준.
5. **부서가 SALES 면 귀속 사람 필수**(서버 한 줄). 지금까지 쓴 기록이 스테이징 0건이라 영향 없음.
6. **프리랜서는 `FINANCE_MUTATION` 거부**(정책 엔진 협력사 분기 다음 한 줄 — 3단계 문지기 전에도 자기·남의 차감·입금 확인을 못 쓰게).
7. 미룸(첫 지급 뒤): 실무 탭 [정산 청구] 버튼, 한국 시각 기록, 주문 이력 글에 금액·사유, 부서별 카드 이름 가르기.

## 11. 시험

### 11.1 계산 (순수 함수, SQLite 레인) — 아래 요율·금액은 모두 가짜 값이다(실제 요율은 설정에만)

| 사례 | 기대 |
|---|---|
| 라홈 2,500,000 / 시공비 1,000,000 / 차감 0 / 400bp | 60,000 |
| 하우드 3,000,000 / 1,000,000 / 500,000 / 600bp | 90,000 |
| 개인영업(발주사 = 맞출 이름) 2,000,000 / 500,000 / 0 / 800bp | 120,000 |
| 기준액 1,000,025 / 600bp (60,001.5원) | 60,002(위로 — 엑셀과 같음) |
| 출고가 < 시공비 + 차감 | 0 |
| 시공비 빈칸 | 계산 안 함, 마감 제외, 다음 마감에 들어감 |
| 숨고, 지정 없음 / 지정 600bp | 빈칸 / 계산 |
| 메인 단계 PRODUCTION + AS 접수 | 대상 아님(J1) |
| 메인 단계 CS + 보류 | 대상 |
| 실측일 10-31, 시작 달 11월 | 대상 아님 |
| 실측일 빈칸, 접수일 11-02 | 대상 |
| 요율 이력 11월 600 · 12월 650, 12월 시공 완료 | 650 |
| 대표 담당 이름이 다른 직원과 같음(맞출 이름 아님) | 대상 아님(J8) |
| 마감 뒤 대표 담당 F→G | F 굳힘, G 에게 안 감(J9) |
| 마감 뒤 차감 추가·시공비 정정 | 다음 마감 ADJUST 차액 |
| 3.3% S = 1,234,567 | 소득세 37,030, 지방 3,700, 실지급 1,193,837 |
| 부가세 S = 1,234,567 | 123,456, 실지급 1,358,023 |
| 합계 0 이하 | 마감 거부 |

### 11.2 권한 (1·2단계)

- 수수료 탭 API: ADMIN, MANAGER+ACCOUNTING, STAFF+ACCOUNTING 허용 / MANAGER+CS, STAFF+SALES, 프리랜서 거부(`tests/domains/test_auth_finance.py:72-92` 도우미).
- `/erp/my-commission`: 프리랜서는 `user_id` 를 넣어도 본인 것만. 설정에 없는 직원 거부.
- 설정 화면 POST: ADMIN 만. 맞출 이름이 활성 사용자 이름과 겹치면 거부.
- 차감 취소: 회계·관리자만.

### 11.3 회귀

- 발주사에 프리랜서 이름이 들어가도 알림톡 브랜드(HAUD)·정산 회사 구분(일반)이 지금과 같다(D14).
- 차감 취소 뒤 정산 대시보드 차감 합계·완료 화면 표시·실무 탭 "청구됨"이 함께 바뀐다(6곳).
- 차감 동시 저장: 두 요청이 겹쳐도 둘 다 남고 CS 의 주문 저장이 사라지지 않는다.
- models ↔ 마이그레이션 왕복(`tests/postgres/test_migration_chain.py`), FK 커버리지(`tests/postgres/test_delete_retention.py`).

## 12. 단계

1. **계산·화면 (1단계)**: 설정(SystemSetting) + 설정 화면 · inputs 표 · 계산 함수 · 수수료 탭(조회·시공비·요율 지정·차감 칸·본인 수정 표시) · 내 수수료 화면·서랍 링크 · 차감 보강 §10.1~5 · 차감 알림 · 발주사 선택지에 프리랜서 이름.
2. **마감·지급 (2단계)**: closings 표 · 마감·지급 완료·마감 취소 · 세금 · CSV · 실측일 기준 전환(D7). 목표 2026-12-10 전 스테이징 검수. 조정 줄(§8.2)은 2026-01-10 전.
3. **보기 범위 제한 (3단계)**: 연결 표 + before_flush 훅 + 되채우기 · 다섯 겹 · §6.5 시험 · 배정 알림 · 반증 재검수. 프리랜서를 새로 받기 전에 끝낸다.

운영 준비(코드 아님): 관리자가 설정 화면에서 프리랜서 등록 → 출고설정 실측 담당자 목록에 맞출 이름 추가 → 회계팀 계정 팀 ACCOUNTING 확인.

## 13. 위험

| 위험 | 막는 법 |
|---|---|
| 보기 제한에서 길 하나를 놓쳐 고객 정보가 샘 | 기본 거부 문지기 + 허용 화면 조각 전수 점검 + 길마다 시험 + 3단계 끝 반증 재검수 |
| 이름 일치가 어긋나 수수료 누락 | 담당자 칸 자동완성에 맞출 이름을 넣음 + 수수료 탭에서 "프리랜서와 비슷한 이름" 경고(3단계 연결 표와 같이) |
| 프리랜서가 이름·발주사·날짜를 바꿔 수수료를 늘림 | J8(맞출 이름은 관리자만) · 겹 4 · "본인 수정" 표시 · J9 굳힘 |
| 마감 뒤 숫자가 조용히 바뀜 | 줄 스냅샷, 바뀐 것은 ADJUST 로만 |
| 차감 재사용으로 기존 정산 숫자가 바뀜 | 공용 상수 안 건드림 · 유효 판정 함수 하나 · 회귀 시험 |
| 파일 크기 상한(py 500줄) | `context_processors.py` 499 · `cs/dashboard.py` 476 · `erp_permissions.py` 464 — 새 코드는 새 모듈에 두고 기존 파일엔 호출 한 줄만 |

## 14. 승인 기록 (2026-11-06)

- Q1 취소 품목 → 빼고 계산(D18).
- Q2 이미 있는 구멍 두 개 → 3단계 때 같이(D19).
- Q3 알림톡 "발주사" 글 → 추후 결정, 코드 변경 없음(D20).
- Q4 J1·J3·J5~J10 · 단계 순서 → 이대로 진행.
- (11-07 운영 뒤) D26 예전 담당 주문 풀기 → D27 "주문만 자기 것, 나머지는 회사 소속 때와 같게 · 매니저 등급 허용"(§6.6). 수수료는 11월부터 그대로.

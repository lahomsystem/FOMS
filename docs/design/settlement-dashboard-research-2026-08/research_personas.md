# 정산 대시보드 이해관계자 조사 (읽기 전용)

조사 대상: `c:\DEV\FOMS` (2026-08-31 기준). 코드 수정 없음.

---

## 1. 실제 role/team 체계 (경로:라인)

### 1.1 User 모델
- `models.py:943-951` — `class User`. `role = Column(String, nullable=False, default='VIEWER')`, `team = Column(String(50), nullable=True)` (주석: `cs/drawing/production/construction`).
  - **role 값(실사용, 자유 문자열이나 정책 코드가 명시적으로 다루는 4종)**: `ADMIN` / `MANAGER` / `STAFF` / `VIEWER`
    확인: `foms/services/orders/erp_policy_permissions.py:240-262` (`evaluate_policy` 의 role 분기 — VIEWER hard-deny → ADMIN override → MANAGER → STAFF).
  - **team 값(STAFF 전용, 실사용 6종 + legacy 1종)**: `CS` / `SALES` / `DRAWING` / `PRODUCTION` / `CONSTRUCTION` / `SHIPMENT`, legacy `MEASURE`(→`SALES` 정규화).
    확인: `foms/services/orders/erp_policy_permissions.py:47` (`_TEAM_NORMALIZE = {"MEASURE": "SALES"}`), `templates/orders/partials/dashboard_filters.html:31-38`(필터 드롭다운 실사용 값), `templates/admin/notifications_send.html:49-54`.
  - team 한글 라벨: CS=라홈팀, SALES=영업팀, DRAWING=도면팀, PRODUCTION=생산팀, CONSTRUCTION=시공팀 (`templates/orders/partials/dashboard_filters.html:33-38`).

### 1.2 권한 정책 SSOT (AUTH-01)
`foms/services/orders/erp_policy_permissions.py` — `POLICY_REGISTRY`(`:102-191`) 가 policy_id → 허용 role/team 을 데이터로 선언. 평가 순서(`evaluate_policy`, `:216-279`):
인증 → VIEWER hard-deny(`:243-246`, `policy.viewer=True` 예외만 통과) → ADMIN 무조건 통과(`:253-254`) → MANAGER(`policy.manager_ok`) → STAFF는 `team`이 `policy.teams`에 있어야 통과(`:260-269`) → order assignment(배정 담당자만, `:271-277`).

**금융 정책 `FINANCE_MUTATION`** (`:114-115`):
```
teams=("CS", "SALES")
"settlement/cash/payment-confirm — ADMIN/MANAGER 또는 STAFF+CS/SALES. VIEWER deny(P0-3)."
```
→ settlement/issue, cash-receipt/issue, payment-confirm 세 endpoint가 이 정책으로 게이트된다. 실측 확정 테스트: `tests/domains/test_auth_finance.py:1-229` — 허용 actor=`ADMIN`/`MANAGER`/`STAFF+CS`/`STAFF+SALES`, 거부 actor=`VIEWER`+`STAFF+PRODUCTION/DRAWING/CONSTRUCTION/SHIPMENT`(`:34-48`). UI 은닉도 같은 policy_id 로 `data-can-finance="true"` 마크업을 감춘다(`:216-228`, `templates/cs/partials/completion_dashboard_body.html` 등).

다른 관련 policy_id: `MANAGER_MUTATION`(bulk delete/restore/excel-import, ADMIN/MANAGER, `:151-152`), `ADMIN_MUTATION`(영구삭제, ADMIN 전용, `:153-154`), `ADMIN_OPS`/`ACCOUNT_ADMIN`(관리자 메뉴, ADMIN 전용, `:108-111`).

### 1.3 자산 소유(‘내 담당’) 판정
`foms/services/erp_permissions.py`:
- `can_edit_erp` (`:289-295`): ADMIN 또는 team이 `("CS","SALES")`(`ERP_EDIT_ALLOWED_TEAMS`, `:14`).
- `resolve_mine_scope_for_user` (`:104-109`): ADMIN→`all`, team→`_MINE_SCOPE_BY_TEAM`(`:15-21`, DRAWING→drawing, SALES/MEASURE/CS→sales, CONSTRUCTION→construction).
- `build_mine_sql_filter`(`:221-286`)/`is_order_related_to_user`(`:161-218`): 영업 담당(manager/parties.manager/quest.owner_person + `assignments.sales_assignee_user_ids`), 도면 담당(`drawing_assignees`+id), 시공 담당(manager + `shipment.construction_workers`) — 영업사원별 매출 귀속의 실제 데이터 소스.

---

## 2. 페르소나 카드 (5개)

### 페르소나 A — 대표(CEO)
- **role 매핑**: `ADMIN` (또는 `MANAGER`).
- **아침 질문 top 3**:
  1. 이번 달(또는 이번 주) 출고가 기준 매출이 목표 대비 얼마인가?
  2. 미수금(잔금 미회수)이 총 얼마이고, 늘고 있나 줄고 있나?
  3. 이번 달 완료 건수·평균 단가 추이가 지난달 대비 어떤가?
- **KPI/차트/테이블**:
  - KPI 카드: 이번 달 매출 합계(출고가 기준), 미수금 합계, 완료 건수, 평균 출고가.
  - 차트: 일별/주별 매출 추이(선/막대, x축=완료일 `schedule.construction.date` 또는 `as_completed_date`), 팀별(영업팀 담당자별) 매출 비중(도넛/막대).
  - 테이블: 없음(대표는 요약 위주, 드릴다운은 경리 화면으로 위임).
- **지금 데이터로 되는가**: **가능**. 출고가는 `erp_shipping_price_from_structured`(`foms/services/erp_display.py:297-323`, `= max(0, 품목합+자유입력-할인)`)로 이미 SSOT 파생 함수 존재. 완료 건수/월별 집계는 `foms/web/cs/completion_dashboard.py:219-247`(`_compute_completion_kpis`)가 이미 이 계산의 원형(this_month/pending/unpaid_total)을 갖고 있음 — 다만 "완료 큐(태블릿) 전용"이라 회사 전체 집계로는 재사용/재쿼리 필요.
  - 대상 상태 범위 SSOT: `ORDER_SETTLEMENT_ALERT_TARGET_STATUSES = ("COMPLETED","AS_RECEIVED","AS_COMPLETED")` (`foms/services/orders/erp_policy_constants.py:11`).
- **미래 기능(추가 데이터 필요)**: 매출 "목표" 값 자체가 시스템에 없음(목표 대비 비교 불가 — 별도 입력 필요). 원가/매입가 데이터 전무(아래 §3 확인) → 마진(이익) 표시는 불가.

### 페르소나 B — 경리/재무 담당
- **role 매핑**: `role=STAFF`, `team=CS`(라홈팀, 실무상 finance 겸직) 또는 신설 검토 대상(§4 참고). 현재 코드 기준 정책상 CS/SALES team만 FINANCE_MUTATION 허용.
- **아침 질문 top 3**:
  1. 오늘/이번 주 현금영수증 미발행 건이 몇 건인가(`cash_receipt_state == "requested"`)?
  2. 정산(비용 청구/차감) 미처리 건이 몇 건인가(`settlement_issued == False`)?
  3. 잔금 미입금(미수) 건 리스트와 각 금액은?
- **KPI/차트/테이블**:
  - KPI: 미청구(pending) 건수, 현금영수증 요청 건수, 미수금 총액.
  - 차트: 정산 상태별(청구완료/대기) 비중, 결제수단별(예약금만/잔금완료 등) 분포.
  - 테이블: **주문 단위 상세 그리드**(고객명, 완료일, 출고가, 예약금, 잔금, 현금영수증 상태, 정산 상태) — 필터(기간/정산상태) 포함. 실제 CSV export 이미 존재.
- **지금 데이터로 되는가**: **거의 전부 가능**. 이 페르소나는 사실상 이미 구현된 `foms/web/cs/completion_dashboard.py`(+`templates/cs/partials/completion_dashboard_body.html`, `templates/cs/partials/tablet_completion_sheet.html`)의 태블릿 완료 대시보드와 데이터 소스가 100% 동일. `_completion_row`(`:125-184`)가 출고가/예약금/잔금/현금영수증/정산상태를 이미 파생. CSV export도 있음(`:566-589`).
- **미래 기능**: 회사 전체(기간 무제한, 완료 큐 200건 cap 없는) 집계 뷰는 없음 — `_COMPLETION_BROWSE_LIMIT = 200`(`foms/api/cs/dashboard.py:41`) 캡이 걸려 있어 "정산 대시보드"는 이 캡을 우회하는 별도 집계 쿼리가 필요(SQL 레벨 SUM/COUNT, 행 단위 캡 없이).

### 페르소나 C — 영업 팀장
- **role 매핑**: `role=STAFF, team=SALES` 또는 `MANAGER`.
- **아침 질문 top 3**:
  1. 우리 팀(또는 특정 영업사원)이 이번 달 만든 매출이 얼마인가?
  2. 내 담당 주문 중 아직 CONFIRM(고객컨펌) 전이라 매출로 잡히지 않은 파이프라인이 얼마나 되나?
  3. 영업사원별 매출 순위는?
- **KPI/차트/테이블**:
  - KPI: 팀 전체 이번 달 매출, 내 담당 매출, 파이프라인(미완료) 예상액.
  - 차트: 영업사원별(담당자별) 매출 막대 그래프, 단계별(스테이지) 주문 분포 funnel.
  - 테이블: 담당자별 주문 리스트(고객명, 단계, 출고가, 진행 상태).
- **지금 데이터로 되는가**: **부분 가능**. 담당자 귀속은 `foms/services/erp_permissions.py:161-218`(`is_order_related_to_user`, `assignments.sales_assignee_user_ids` + `manager_name`)로 이미 SSOT 존재하고 `mine=1` 필터로 대시보드에 실사용 중(`templates/orders/partials/dashboard_filters.html:52-54`). 완료된(매출 확정) 주문의 출고가 합산은 가능.
- **미래 기능**: "파이프라인 예상액"(미완료 주문의 견적 금액 합산)은 상태별 집계 쿼리가 아직 없음(신규 개발 필요, 데이터 자체는 `structured_data.items`/`totals`에 존재하므로 계산 로직만 추가하면 됨 — "미래 기능"이라기보다 "신규 집계"). 영업사원별 순위 랭킹 뷰는 미존재(신규 개발).

### 페르소나 D — 생산/시공 매니저
- **role 매핑**: `role=STAFF, team=PRODUCTION` 또는 `team=CONSTRUCTION`.
- **아침 질문 top 3**:
  1. 오늘/이번 주 시공 완료 예정 건이 몇 건이고 총 출고가(작업량 규모)는?
  2. 재작업/하자로 인한 비용 차감(deductions)이 어느 부서(우리 팀)에 얼마나 귀속됐나?
  3. AS 처리 건이 매출(정산)에 미치는 영향은?
- **KPI/차트/테이블**:
  - KPI: 이번 주 시공 완료 건수, 우리 부서 귀속 차감액.
  - 차트: 부서별(`SETTLEMENT_DEPARTMENTS`) 차감액 막대 그래프.
  - 테이블: 부서 귀속 차감 내역 리스트(사유, 금액, 주문).
- **지금 데이터로 되는가**: **부분 가능**. 비용 청구/차감(`settlement.deductions`)은 부서 귀속 필드가 이미 존재: `SETTLEMENT_DEPARTMENTS = ("SALES","DRAWING","PRODUCTION","CONSTRUCTION","CUSTOMER")` (`foms/api/cs/dashboard.py:58`), issue endpoint 예시 body `{"department":"SALES","amount":1000,"reason":...}`(`tests/domains/test_auth_finance.py:27-28`). 부서별 집계 쿼리는 별도 필요(신규).
- **미래 기능/권한 이슈**: 이 페르소나는 통상 **매출·마진 전체를 볼 필요/자격이 없다** — 자기 부서 귀속 차감 내역만 필요(§3 권한 참고). 원가(자재비/인건비) 데이터가 없어 "이 시공 건의 마진"은 계산 불가.

### 페르소나 E — CS 담당
- **role 매핑**: `role=STAFF, team=CS`.
- **아침 질문 top 3**:
  1. 오늘 처리해야 할 정산(비용 청구) 대기 건이 몇 건인가?
  2. AS 접수로 인해 재정산이 필요한 건이 있나?
  3. 현금영수증 발행 요청이 밀린 게 있나?
- **KPI/차트/테이블**: 페르소나 B(경리)와 거의 동일한 화면·데이터 재사용 가능(팀=CS라 FINANCE_MUTATION 정책상 자연스러운 권한 보유). KPI: 미청구 건수, 현금영수증 요청 건수. 테이블: 완료 큐 그리드(이미 구현체 재사용).
- **지금 데이터로 되는가**: **가능**(페르소나 B와 동일 기반, 이미 프로덕션 코드 존재).
- **미래 기능**: 없음(이미 태블릿 완료 대시보드가 사실상 이 페르소나 전용 화면).

---

## 3. 권한/뷰 분리 제안

### 3.1 이미 존재하는 통상 관행 근거
- **VIEWER hard-deny**: 코드가 이미 "조회 전용 계정은 금융 mutation을 할 수 없다"는 원칙을 강제(`erp_policy_permissions.py:243-246`, 거부 사유 문구 `"조회 전용 계정은 이 작업을 할 수 없습니다."`).
- **금융 mutation = CS/SALES(+ADMIN/MANAGER) 전용**: PRODUCTION/DRAWING/CONSTRUCTION/SHIPMENT STAFF는 settlement/cash-receipt/payment-confirm에서 이미 403(`tests/domains/test_auth_finance.py:34-48`). 즉 **시공기사·생산 담당에게 금액 mutation 권한이 이미 없다** — "정산 대시보드"의 열람 권한도 이 라인을 그대로 따르는 것이 코드베이스 관행과 일치.
- **UI 은닉도 backend와 동일 policy_id로 동기화**: `data-can-finance="true"` 마크업이 없으면 완료 대시보드에서 정산 버튼 자체가 렌더되지 않음(`erp_policy_permissions.py:526-528`, `test_auth_finance.py:200-228`) — 정산 대시보드도 같은 패턴(`policy_can('FINANCE_MUTATION')` 같은 걸 조회 전용 policy로 확장)을 쓰면 신규 정책 없이 일관성 유지 가능.

### 3.2 정산 대시보드에 대한 제안 (신설 필요 — 현재 policy_id는 mutation 전용, "읽기" 전용 정책은 없음)
- **마진/원가 라인**: 현재 코드에 원가·매입가 개념 자체가 없으므로(§ 조사에서 margin/cost_price/원가/이익 grep 전무) 이 항목은 신설 시에도 "노출 차단" 이전에 "데이터 자체가 없다". 향후 원가 필드를 추가한다면, 처음부터 **시공기사·생산 STAFF에게는 원가/마진 컬럼을 서버에서부터 제거**(클라이언트 숨김이 아니라 응답 payload 자체에서 배제)하는 걸 원칙으로 설계할 것을 권고.
- **금액 전체 열람 제한 제안**(통상 관행 + 기존 코드 정책과의 정합):
  - **전사 매출 총액/미수금 총액**: `ADMIN`/`MANAGER`/`STAFF+CS`/`STAFF+SALES`만(기존 `FINANCE_MUTATION` teams와 동일 집합을 read 정책에도 그대로 적용).
  - **PRODUCTION/CONSTRUCTION/DRAWING/SHIPMENT STAFF**: 회사 전체 매출·미수금 대시보드 접근 자체를 차단하고, 자기 부서 귀속 차감(`settlement.deductions` where department=자기팀) 내역만 노출.
  - **개별 주문 상세 금액(출고가/예약금/잔금)**: 이미 `user_can_read_order`(`erp_policy_permissions.py:289-310`)가 "인증된 활성 사용자는 team 무관 모든 Order를 조회 가능"이라고 명시 — 즉 **주문 상세 화면의 금액은 이미 전 직원에게 열려 있다**(read 범위가 넓음). 정산 "대시보드"(집계/전사 관점)는 이 read 범위를 그대로 따르지 말고 §3.2 위 제한을 신규로 얹어야 한다 — 그렇지 않으면 시공기사가 "완료 대시보드"를 열어 전사 미수금 총액까지 보게 됨.
  - **영업사원별 매출 랭킹**: 영업 팀장(MANAGER 또는 SALES 내 상위자)에게는 팀 전체 랭킹, 일반 SALES STAFF에게는 본인 것만(위 `mine` 필터 재사용) — 동료 매출 비교로 인한 사기 저하 방지(통상 관행).

### 3.3 신규 정책 제안(구현 시)
현재 `POLICY_REGISTRY`에 "정산 대시보드 열람"에 해당하는 read-only policy_id가 없다(모든 policy_id는 mutation 게이트용, `enforce_order_mutation_policy`는 `_WRITE_METHODS`에만 적용 — `erp_policy_permissions.py:482-483`). 구현 시 신규 `SETTLEMENT_DASHBOARD_READ` 같은 policy_id를 만들고 GET route에도 별도 가드(현재 GET은 이 before_request를 안 탐 — read 제한은 route 핸들러 내부에서 직접 role/team 체크 필요)를 추가해야 한다.

---

## 4. 목업 3버전 페르소나 배분 추천

- **V1 = 경영진(대표/CEO, MANAGER 포함)**: 요약 카드 + 추세 차트 중심. KPI: 이번달 매출/미수금/완료건수/평균단가. 담당자별·부서별 비중은 드릴다운 없이 상위 요약만. → 페르소나 A.
- **V2 = 경리 실무(CS/SALES STAFF, 정산 처리자)**: 이미 존재하는 완료 대시보드(`completion_dashboard.py`)와 동일한 결의 **행 단위 그리드 + 필터(기간/정산상태) + CSV export** 중심, 캡(200건) 제거한 전사 버전. → 페르소나 B, E.
- **V3 = 분석(영업 팀장 + 생산/시공 매니저, 팀별 드릴다운)**: 축을 "담당자/부서"로 바꾼 차트(영업사원별 매출 막대, 부서별 차감액 막대), 자기 팀 스코프로 제한된 뷰. → 페르소나 C, D. 이 버전에서 원가/마진 컬럼은 절대 노출하지 않음(3.2 근거).

---

## 부록 — 재무 관련 데이터 소스 요약(경로:라인)
- 출고가 파생 SSOT: `foms/services/erp_display.py:297-323` (`erp_shipping_price_from_structured`), 원칙: `max(0, 품목합+자유입력-할인)`. 저장된 `totals.items_total`은 품목합만(재정의 금지) — `foms/services/orders/structured_form_projection.py:14-15,119-121`.
- 예약금/잔금: `foms/web/cs/completion_dashboard.py:153-155` (`shipping_price - deposit`, 불변식).
- 정산/현금영수증 상태: `foms/web/cs/completion_dashboard.py:88-122, 161-184, 219-247`.
- 정산 청구 API: `POST /api/orders/<id>/settlement/issue`(`foms/api/cs/dashboard.py:262`), `POST /api/orders/<id>/cash-receipt/issue`(`:387`), `POST /api/orders/<id>/payment-confirm`(`foms/api/erp_orders_structured.py:1308`).
- 매출 인식 대상 상태 SSOT: `ORDER_SETTLEMENT_ALERT_TARGET_STATUSES = ("COMPLETED","AS_RECEIVED","AS_COMPLETED")` (`foms/services/orders/erp_policy_constants.py:11`).
- 부서 귀속 차감: `SETTLEMENT_DEPARTMENTS = ("SALES","DRAWING","PRODUCTION","CONSTRUCTION","CUSTOMER")` (`foms/api/cs/dashboard.py:58`).
- 영업/도면/시공 담당자 귀속 판정: `foms/services/erp_permissions.py:161-286` (`is_order_related_to_user`, `build_mine_sql_filter`).
- 원가/매입가/마진 필드: **코드베이스 전체에 존재하지 않음**(grep `margin|cost_price|purchase_price|매입|원가|이익` → `models.py`/`foms/`에 무매치, 외부 API/문서 파일만 매치). 정산 대시보드에 마진 KPI를 넣으려면 신규 컬럼/입력 UI가 선행돼야 한다.
- 지역(region) 세분화: `is_regional`(boolean, `models.py:51`)만 존재, 시/도 단위 세분화 필드 없음(주소 자유텍스트 파싱 필요 — 신규 기능).
- 완료 큐 조회 캡: `_COMPLETION_BROWSE_LIMIT = 200`(`foms/api/cs/dashboard.py:41`) — 정산 대시보드가 이 큐를 그대로 재사용하면 전사 집계에서 과소 산정될 위험(신규 SQL 집계로 우회 필요).

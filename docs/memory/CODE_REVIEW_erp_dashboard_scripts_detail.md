# FOMS 개발 건강 진단 – 코드리뷰 보고서

**대상 파일:** `templates/partials/erp_dashboard_scripts_detail.html`  
**검토 기준:** Grand Develop Master (.cursor/agents/grand-develop-master.md) §1 개발 품질 감사  
**검토 일자:** 2026-02-26

---

## 요약

| 항목 | 결과 |
|------|------|
| **전체 점수** | 72/100 |
| **긴급 조치 필요** | 0건 |
| **개선 권장** | 4건 |
| **양호** | 5건 |

---

## 긴급 (🔴)

- 없음. 즉시 중단해야 할 결함은 없습니다.

---

## 개선 권장 (🟡)

### 1. XSS 가능성: `assigneeNames` 미이스케이프

- **위치:** 488행 근처 `도면 담당: <strong>${assigneeNames || '미지정'}</strong>`
- **내용:** `assigneeNames`는 API 응답의 `assignees.map(u => u.name)`로 만든 문자열입니다. 담당자 이름에 `<script>` 등이 들어가면 그대로 HTML로 삽입됩니다.
- **권장:** HTML에 넣기 전에 `escapeHtml(assigneeNames)` 적용.
- **예상 효과:** 담당자 이름에 포함된 HTML/스크립트가 실행되지 않아 XSS 위험 제거.

### 2. 속성 이스케이프 불완전: `safeForAttr`

- **위치:** 104행 `const safeForAttr = (val) => String(val || '').split("'").join("\\'");`
- **내용:** `onclick` 등 HTML 속성 값에 넣을 때 작은따옴표만 이스케이프합니다. HTML 속성에서는 `"`, `&`, `<`, `>` 도 이스케이프하는 것이 안전합니다.
- **권장:** 속성용 이스케이프를 별도 함수로 두거나, `safeForAttr`에서 `"`·`&`·`<`·`>` 도 처리 (또는 기존 프로젝트의 공통 escape 유틸 사용).
- **예상 효과:** 속성 값에 따옴표/태그가 들어와도 HTML 구조가 깨지거나 스크립트 실행이 되지 않음.

### 3. 함수 길이 및 단일 책임

- **위치:** `loadOrderDetail(orderId)` 전반 (약 18행~519행).
- **내용:** 한 함수 안에 API 호출, 데이터 가공, 도면 상태 분기, HTML 문자열 조립, 이벤트용 HTML 조립이 모두 들어 있어 500줄 가까이 됩니다. GDM 관점에서 “함수 길이·단일 책임” 개선 대상입니다.
- **권장:**  
  - “기본 정보/일정/특이사항 HTML 생성”, “도면 창구(버튼·타임라인·요청 탭) HTML 생성”, “최종 innerHTML 조립” 등을 각각 함수로 분리 (예: `buildBasicInfoHtml(sd)`, `buildDrawingActionHtml(...)`, `buildOrderDetailHtml(...)`).  
  - 필요 시 이 partial이 포함되는 페이지에서 공통으로 쓸 수 있는 작은 유틸(예: 금액 포맷, 날짜 포맷)은 별도 스크립트로 분리 검토.
- **예상 효과:** 수정·디버깅 시 영향 범위가 줄고, 테스트·리뷰가 쉬워짐.

### 4. 템플릿/문자열 패턴 혼재

- **위치:** 전 구간 (백틱 템플릿 리터럴 vs `+` 문자열 연결).
- **내용:** IDE 파서 회피를 위해 일부만 `+` 연결로 바꾼 상태라, 같은 역할의 HTML 조립이 템플릿 리터럴과 문자열 연결이 혼재합니다.
- **권장:**  
  - 단기: 새로 손대는 구간은 “속성/인라인 이벤트는 변수로 만든 뒤 문자열 연결” 패턴으로 통일 (이미 `onclickModal`, `onclickAttach`, `onclickToggle` 등으로 적용된 부분 유지).  
  - 중기: GDM §4 “단순화 우선”에 따라, 이 스크립트 블록을 별도 `.js` 모듈로 빼고 템플릿에서는 데이터만 전달·include 하는 방안 검토 (IDE 진단·유지보수성 개선).
- **예상 효과:** 스타일 통일, 파서/린트 오류 감소, 리팩터 시 실수 감소.

---

## 양호 (🟢)

### 1. 사용자/API 데이터 대부분 이스케이프

- 고객명, 발주사, 연락처, 주소, 담당자, 실측/시공 일정, 특이사항, 제품 항목 필드, 수정 요청 이력(메모·담당자·일시), 에러 메시지 등은 `escapeHtml(...)`로 감싸서 출력하고 있음.
- API·사용자 입력이 HTML로 나가는 구간이 많아서, 이스케이프 일관성이 보안상 중요함. 현재 대부분 잘 적용되어 있음.

### 2. 파일 크기

- **604줄**로, GDM 가이드의 HTML 800줄 초과 기준을 넘지 않음. 추가 분리 시 500줄 이하로 유지하는 것도 목표로 두기 좋음.

### 3. API 오류·비 JSON 처리

- `safeJsonFetch`로 401/404/500 HTML 응답 시 `r.json()` 예외를 피하고 fallback을 반환. 사용자에게 “상세 정보를 불러올 수 없습니다” 메시지로 안내하는 흐름이 있음.

### 4. 도면 단계·권한 분기 정리

- DRAWING 단계일 때만 도면 창구 UI를 그리며, `drawingStatus`, `canEdit`, `canDrawingAssign`, `canDrawingWork`, `hasAssignee` 등으로 버튼/메시지가 분기됨. 역할·상태별 동작이 코드에서 읽기 쉬움.

### 5. 전역 의존성 명시

- `escapeHtml`, `renderDrawingGatewayTimeline`, `renderGatewayFiles`, `CAN_EDIT_ERP_BETA`, `MY_ID`, `MY_TEAM`, `MY_NAME`, `MY_ROLE` 등은 이 파일에서 정의되지 않고 상위/공통 스크립트에 의존. `erp_dashboard_scripts_core.html` 등 include 순서가 맞으면 동작이 보장되는 구조임.

---

## 참고 (보안·아키텍처)

- **escapeHtml 정의:** 이 partial은 `erp_dashboard.html`(또는 동일 페이지)에서 include 되며, 해당 페이지 또는 `erp_dashboard_scripts_core.html`에서 `escapeHtml`이 정의됨. 같은 스크립트 컨텍스트에서 로드되는지 include 순서 확인 권장.
- **속성·이벤트:** `onclick="..."`에 문자열을 넣을 때 `safeForAttr`만 사용 중. 위 “개선 권장 2”대로 속성용 이스케이프를 강화하면, 나중에 다른 속성에도 재사용하기 좋음.

---

## 결론 및 다음 단계

- **발견한 것:** XSS 1건(assigneeNames), 속성 이스케이프 불완전, 대형 단일 함수, 문자열 패턴 혼재. 대부분의 출력은 이스케이프되어 있고, 파일 크기와 API 오류 처리·도면 분기는 잘 되어 있음.
- **작업 권장 순서:**  
  1) `assigneeNames`에 `escapeHtml` 적용 (긴급도 높음).  
  2) `safeForAttr` 보강 또는 공통 유틸 사용.  
  3) `loadOrderDetail` 분리 및 문자열 패턴 정리(점진적 리팩터).
- **근거:** GDM §1 개발 품질 감사(보안·코드 품질·파일 크기), §4 문제 해결 프로토콜(단순화·구조적 의심).

---

## 리팩터 이력: ERP 금액 블록 공용화 (2026-02-26)

- **목적:** 출고가/예약금/잔금 블록이 JS 문자열(erp_dashboard_scripts_detail.html), 정적 Jinja(erp_measurement_dashboard.html, erp_drawing_workbench_detail.html)에 중복되어 한 곳 수정 시 다른 곳에 반영되지 않던 문제 해소.
- **조치:**
  - **공용 partial:** `templates/partials/_erp_amount_block.html` 생성. 인자 `total_formatted`, `deposit_formatted`, `remaining_formatted`(예: `"1,234,567원"`)만 받아 출력.
  - **Jinja 2곳:** 위 두 템플릿에서 동일 블록 제거 후 `{% set total_formatted = ... %}` 등 설정하고 `{% include 'partials/_erp_amount_block.html' %}` 로 대체.
  - **JS 1곳:** `erp_dashboard.html`에 `<script type="text/template" id="erp-amount-block-tpl">` 로 위 partial을 `__TOTAL__`/`__DEPOSIT__`/`__REMAINING__` 플레이스홀더와 함께 포함. `erp_dashboard_scripts_detail.html`의 `loadOrderDetail()`에서 주문 합계·예약금·잔금 계산 후 해당 템플릿을 채워 `amountBlockHtml`로 넣어 각 제품 카드에 동일 구조로 삽입.
- **효과:** 금액 블록의 마크업·스타일을 `_erp_amount_block.html` 한 곳만 수정하면 대시보드(JS)·실측 대시·도면 작업실 화면에 동일하게 반영됨.

---
description: 시공 스크립트 파일(`erp_construction_scripts.html`) 리팩토링 및 클린 코드 개선 계획
last_verified: 2026-03-03
status: COMPLETED
---

# `erp_construction_scripts.html` 리팩토링 계획서

## 1. 개요
*   **목적:** 현재 1,774라인으로 비대해진 `erp_construction_scripts.html` 파일을 논리적 기능 단위로 분리하고, 심각한 문법 오류(한 줄로 압축된 코드 등)를 수정하여 유지보수성을 극대화합니다.
*   **핵심 원칙:** **기존에 정상 작동하던 모든 비즈니스 로직과 UI 기능은 100% 동일하게 동작해야 합니다.** 오직 코드의 구조와 품질(안정성)만 개선합니다.
*   **대상 파일:** `templates/partials/erp_construction_scripts.html`

## 2. 주요 문제점 및 개선 방향

### 2.1 문법 및 구조적 위험 (Syntax & Structural Risks)
*   **현황:** 파일 내 **4곳**에서 한 줄로 압축(Minification)된 코드가 섞여 있어 가독성과 디버깅이 극히 어렵습니다.
    | 구간 | 라인 | 포함 함수/로직 |
    |------|------|----------------|
    | Zone A | L482~L526 | `startConstruction`, `completeConstruction`, `reuploadConstructionPhotos`, `openAsAcceptModal`, `openAsReuploadModal`, `renderBadges` (6개 함수 전체가 ~45줄에 압축) |
    | Zone B | L1015~L1017 | `submitConstructionComplete` 내 업로드 실패/성공 처리 |
    | Zone C | L1156~L1158 | `submitConstructionReupload` 내 업로드 결과 처리 |
    | Zone D | L1291~L1306 | `submitAsAccept` 내 AS 등록 완료, 모달 닫기, `DOMContentLoaded` 리스너 시작부까지 압축 |
*   **개선:** 코드 포맷터를 적용하여 모든 로직을 표준 JavaScript 스타일(개행 및 들여쓰기)로 복원합니다.

*   **`escapeHtml` 중복 선언 (L1, L1751):** 두 `<script>` 블록 각각에 동일한 함수가 정의되어 있습니다. 하나로 통합 필요.
*   **`esc()` 헬퍼 (L7, 이미 추가됨):** 이전 SyntaxError 수정 시 추가된 `esc(v)` 함수가 존재합니다. `escapeHtml` 결과에 추가로 백틱(`` ` ``)과 `$` 기호를 이스케이프합니다. 리팩토링 시 이 함수와 `escapeHtml`의 역할을 명확히 정리해야 합니다.

### 2.2 중복 코드 (DRY 위반)
*   **현황:** 시공 사진 업로드, 재업로드, AS 사진 업로드 총 3곳에서 **R2 스토리지 멀티파트 업로드(세션 발급 → PUT → API 완료 보고)** 로직이 거의 동일하게 중복되어 있습니다.
    | 함수 | 라인 범위 | 코드 라인 수 |
    |------|-----------|-------------|
    | `submitConstructionComplete` → `doUploadOne` | L937~L1017 | ~80줄 |
    | `submitConstructionReupload` → `doUploadOne` | L1079~L1158 | ~80줄 |
    | `submitAsAccept` → `doUploadOne` | L1216~L1290 | ~75줄 |
    | **총 중복** | | **~235줄** |
*   **3개 함수의 미세 차이점 (추출 시 고려):**
    1. `submitConstructionComplete`: 업로드 후 `/api/orders/{id}/construction/complete` API 호출
    2. `submitConstructionReupload`: 업로드 **전** 기존 construction 첨부 전체 삭제
    3. `submitAsAccept`: 업로드 **전** 본인(user_id 일치) AS 사진만 선택 삭제 → 업로드 후 `/api/orders/{id}/as/register` API 호출
*   **개선:** 공통 업로드 관리 함수 `async function executeBatchUpload(orderId, files, category, uiElements)` 를 추출하여 한 곳에서 관리하도록 리팩토링합니다.

### 2.3 버그: `CONCURRENCY` 이중 선언 (submitAsAccept)
*   **현황:** `submitAsAccept` 함수 내에서 `const CONCURRENCY = 3` (L1212)이 선언된 후, 바로 아래 `try` 블록 안에서 `const CONCURRENCY = 10` (L1216)으로 재선언됩니다. `try` 블록이 별도 스코프이므로 JavaScript 에러는 아니지만, 실질적으로 inner scope의 `10`이 사용되어 outer `3`은 사문화(dead code)입니다.
*   **개선:** `CONCURRENCY` 선언을 하나로 통일 (10). 공통 업로드 엔진 추출 시 자연스럽게 해소됩니다.

### 2.4 전역 오염 방지 (Global Scope Protection)
*   **현황:** `__attachmentsCache`, `__selectedOrderId` 등 6개 변수(L23~L33)가 전역 공간(window)에 그대로 노출되어 있습니다.
*   **개선:** 즉시 실행 함수(IIFE) 또는 ES 모듈(향후) 패턴을 사용하여 변수의 스코프를 현재 컨텍스트 내로 제한합니다. (기존 인라인 `onclick` 이벤트와의 호환성을 위해 window 객체에 명시적으로 연결할 것은 연결합니다)

### 2.5 `loadOrderDetail` 내부 로컬 헬퍼 중복
*   **현황:** `loadOrderDetail` 함수 내에 `escAttr(s)` (L803)라는 로컬 이스케이프 함수가 별도 정의되어 있으며, 상단의 `esc()`와 역할이 겹칩니다.
*   **개선:** `escAttr`을 `esc` 또는 별도 유틸리티로 통합 정리합니다.

### 2.6 보안 위협 및 에러 처리 부족 (CSRF Token & Error Handling)
*   **현황:** 대부분의 `fetch` 통신(`POST`, `DELETE`, `PUT`) 헤더에 CSRF 토큰이 포함되어 있지 않아, 서버 측 보호 정책에 따라 `403 Forbidden` 발생 위험이 큽니다. 또한 에러 발생 시(서버에서 HTML 에러 페이지 반환 등) 스크립트가 조용히 중단(Silent Failure)될 수 있습니다.
*   **개선:** `POST`/`DELETE` API 요청 시 헤더에 CSRF 토큰을 동적으로 주입하는 공통 로직을 마련하고, API 파싱 실패 시 예외 처리를 강화하여 사용자 경험을 보호합니다.

## 3. 리팩토링 단계별 실행 계획 (Action Plan)

### Step 1: 코드 포맷팅 및 오류 스캔 (안정화 1단계)
1.  `erp_construction_scripts.html` 파일 전체의 들여쓰기를 표준화합니다.
2.  에디터/Lint 레벨에서 발생하는 문법 오류(Syntax Error)를 찾아 수정합니다.
    *   **Zone A** (L482~L526): 6개 함수 unminify → ~120줄 예상
    *   **Zone B** (L1015~L1017): 조건문/리턴 분리 → ~10줄 예상
    *   **Zone C** (L1156~L1158): 조건문/리턴 분리 → ~10줄 예상
    *   **Zone D** (L1291~L1306): AS 완료 로직 + `DOMContentLoaded` 분리 → ~50줄 예상
3.  `CONCURRENCY` 이중 선언 버그 수정 (2.3 참조).
4.  이 단계에서는 **기능을 분리하거나 로직을 바꾸지 않고 오직 가독성만 확보**합니다.

### Step 2: 공통 업로드 엔진 추출 (DRY 적용)
1.  3개 함수의 공통 패턴을 패턴화합니다:
    *   배치 세션 발급 → 이미지 압축 → R2 PUT → 첨부 완료 보고 → 진행률 갱신
2.  `async function executeBatchUpload(orderId, files, category, uiElements)` 형태의 헬퍼 함수를 상단에 정의합니다.
    *   `uiElements`: `{ statusEl, progressWrap, progressBar }` 객체
    *   반환값: `{ ok: number, total: number }` (성공 건수 / 전체 건수)
3.  기존 3개의 함수 내부에서 중복되던 업로드 코드를 이 헬퍼 함수 호출로 대체합니다.
    *   각 함수는 업로드 전처리(삭제 등)와 업로드 후처리(API 호출, 모달 닫기)만 남깁니다.
4.  **검증 포인트:** 시공/AS 업로드 시 진행률(%) 텍스트, 프로그레스 바 갱신, 최종 완료 상태 변경이 이전과 똑같이 부드럽게 돌아가는지 확인합니다.

### Step 3: 유틸리티 함수 정리
1.  `escapeHtml` 중복 제거: L1의 선언만 유지, L1751의 두 번째 `<script>` 블록에서는 제거하고 참조만 사용.
2.  `esc()` / `escAttr()` 역할 명확화:
    *   `escapeHtml(v)` → HTML 엔티티 이스케이프 (범용)
    *   `esc(v)` → 위 + 백틱/달러 이스케이프 (템플릿 리터럴 안전용)
    *   `escAttr()` → `esc()`로 대체 또는 역할에 맞게 통합
3.  `safeJsonParse`, `safeJsonFetch` 등 유틸리티를 상단 Zone에 모아 정리.

### Step 4: 기능별 논리적 그룹화 (응집도 향상)
파일 내부에 주석 블록(`// ═══ [기능명] ═══`)을 명확히 추가하여, 거대한 파일을 훑어보기 편하게 만듭니다.
*   **Zone 1: 유틸리티 및 전역 설정** (`escapeHtml`, `esc`, `safeJsonParse`, `safeJsonFetch` 등)
*   **Zone 2: 첨부파일 뷰어 및 줌** (갤러리 렌더링, 카테고리 탭, 휠 스크롤 줌, 미리보기 모달)
*   **Zone 3: 공통 업로드 엔진** (Step 2에서 만든 `executeBatchUpload`)
*   **Zone 4: 시공 / AS 비즈니스 로직** (`startConstruction`, `completeConstruction`, `reuploadConstructionPhotos`, `openAsAcceptModal`, `openAsReuploadModal`, `submitConstructionComplete`, `submitConstructionReupload`, `submitAsAccept`)
*   **Zone 5: 제품/퀘스트/UI 렌더링** (`loadOrderDetail`, `loadQuestDetail`, `approveQuestTeam`, `renderBadges`)
*   **Zone 6: 이벤트 리스너 / DOMContentLoaded** (필터, 프로세스 맵, collapse, 이벤트 위임)
*   **Zone 7: 알림(Notification) 컴포넌트** (HTML + CSS Style + Script)

### Step 5: 알림(Notification) 코드 구조화
*   현재 첫 번째 `</script>` (L1456) 이후에 알림 HTML(L1458~L1474) + CSS(L1476~L1614) + 두 번째 `<script>`(L1616~L1774)가 이어지는 형태입니다.
*   두 번째 `<script>` 안의 `escapeHtml` 중복 제거 후, 알림 로직을 첫 번째 스크립트 블록의 Zone 7으로 통합합니다.
*   CSS는 별도 `<style>` 태그로 파일 상단에 배치하거나 `erp_construction_styles.html`로 이동합니다.

## 4. 무중단/호환성 보장 전략 (Risk Management)
1.  **DOM 셀렉터 유지:** 기존 HTML(`erp_construction_dashboard.html` 등)에서 참조하는 `#erp-cons-complete-btn`, `#notification-badge` 등의 ID와 Class는 절대 건드리지 않습니다.
2.  **전역 함수명 유지:** `onclick` 속성으로 요소에서 직접 호출하고 있는 함수들(`openAttachmentPreviewModal`, `approveQuestTeam`, `startConstruction`, `completeConstruction`, `reuploadConstructionPhotos`, `openAsAcceptModal`, `openAsReuploadModal`, `toggleNotificationPanel`, `markAllNotificationsRead` 등)의 이름은 변경하지 않습니다.
3.  **점진적 수정 후 테스트:** 한 Step이 끝날 때마다 서버를 띄워 모달 오픈, 업로드, API 호출(Mocking 또는 Dev 환경)이 정상 작동하는지 부분 테스트를 병행합니다.

## 5. 기대 효과
*   중복 업로드 로직 ~235줄 → ~30줄 공통 엔진 + 각 함수 호출부 (순 감소 ~180줄)
*   Unminify로 코드 가독성 확보 (라인 수는 unminify로 일부 증가하므로 상쇄됨)
*   **순 라인 수 변화: 약 5~15% 감소** (1,774줄 → 1,500~1,680줄 예상)
*   추후 새로운 대시보드(예: 자재 대시보드) 개발 시 `executeBatchUpload` 재사용 가능
*   개발 과정에서의 "알 수 없는 Syntax Error" 방지 및 디버깅 속도 개선
*   `CONCURRENCY` 이중 선언 버그 해소

## 6. 현재 파일 구조 맵 (소스코드 기준, 2026-03-03 검증)

| 라인 | 내용 |
|------|------|
| 1~7 | `escapeHtml`, `esc` 유틸리티 |
| 8~21 | `safeJsonParse`, 설정(config) 읽기, `label` 헬퍼 |
| 23~46 | 전역 변수 6개 + 첨부 카테고리 메타 |
| 47~69 | 카테고리 탭 렌더링 |
| 71~475 | 첨부파일 갤러리 + 미리보기 모달 + 줌 |
| 476~526 | ⚠️ **Minified Zone A** — `startConstruction` ~ `renderBadges` 6개 함수 |
| 528~606 | `approveQuestTeam`, `loadQuestDetail` |
| 608~914 | `safeJsonFetch`, `loadOrderDetail` (제품 항목, 첨부, 기본정보 렌더링) |
| 916~1048 | `submitConstructionComplete` (업로드 + 완료 API) |
| 1015~1017 | ⚠️ **Minified Zone B** |
| 1050~1170 | `submitConstructionReupload` (삭제 + 재업로드) |
| 1156~1158 | ⚠️ **Minified Zone C** |
| 1172~1306 | `submitAsAccept` (AS 삭제 + 업로드 + 등록) |
| 1212+1216 | ⚠️ `CONCURRENCY` 이중 선언 버그 |
| 1291~1306 | ⚠️ **Minified Zone D** |
| 1306~1455 | `DOMContentLoaded`: 필터, 프로세스 맵, collapse, 이벤트 위임 |
| 1456 | `</script>` (첫 번째 스크립트 블록 종료) |
| 1458~1474 | 알림 패널 HTML |
| 1476~1614 | 알림 패널 CSS `<style>` |
| 1616~1774 | 두 번째 `<script>`: 알림 JS (중복 `escapeHtml` L1751 포함) |

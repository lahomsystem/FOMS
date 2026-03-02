---
description: 시공 완료 대시보드 구축 계획서 (GDM 지휘)
date: 2026-03-02
status: PHASE4_IMPLEMENTED
agent: grand-develop-master
---

# 🏗️ 건설/시공 완료 대시보드 (Construction Completion Dashboard) 구축 계획서

> **작성자**: Grand Develop Master (개발 총괄 감독관)  
> **목표**: 시공자가 완료 후 업로드한 사진을 한눈에 검토하고, 이슈(미결/AS) 발생 시 유관 부서(영업/도면/시공)에 **비용 청구 및 정산**을 할 수 있는 거점 대시보드 구축.  
> **비전**: 본 대시보드는 단순 조회용을 넘어, 향후 도입될 **[시공비 정산 대시보드]**의 데이터를 공급하는 핵심 데이터 허브로 기능합니다.

---

## 🔬 1. 현황 및 아키텍처 분석 (GDM 진단)

현재 FOMS의 구조 상 시공 완료 시 `api/orders/<id>/construction/complete` API를 통해 주문 상태가 `COMPLETED`로 변경되며 관련된 사진이 `Attachment` 테이블에 업로드됩니다. 하지만 관리자가 **"완료된 결과물"을 리뷰하고 정산/AS 판단을 내리는 전용 뷰**가 부재합니다.

*   **해결 과제 1 (시각적 과제)**: 데이터 테이블 형식과 이미지 갤러리 형식이 융합되어 공간 효율성이 극대화된 레이아웃(1줄 요약 + 사진 모아보기)이 필요합니다.
*   **해결 과제 2 (구조적 과제)**: '책임 귀속(비용 청구)'이라는 새로운 데이터 차원이 도입되어야 합니다. 이는 기존 `structured_data` 에 `settlement`(정산) 노드를 체계적으로 추가함으로써 해결해야 합니다.

---

## 🛠️ 2. 핵심 기능 요구사항

1.  **시각적 갤러리 통합 뷰 (모아보기 + 1줄 요약)**
    *   **1줄 요약 영역**: `[시공일자] | [시공팀] | [고객명] | [제품 요약] | [결과(완료/미결/AS)]` 형태로 테이블 최소화.
    *   **모아보기 영역(미리보기)**: 해당 행 바로 아래 또는 우측 확장을 통해, 시공자가 업로드한 현장 사진(카테고리: **`construction`** 등)을 썸네일 가로 스크롤로 한눈에 표시.
    *   **✨ 사진 뷰어 (Global Image Viewer 재활용)**: 썸네일 클릭 시, **`layout.html`에 이미 전역으로 구현된 `GlobalImageViewer`**(`#global-image-viewer`) 모달을 호출하여 사진을 표시.
        *   **이미 구현된 기능**: 배경 블러(`#global-viewer-backdrop`), 좌우 화살표 버튼(`#global-viewer-prev/next`), 모바일 좌우 스와이프(`touchstart/move/end`), 마우스 드래그/휠 줌, ESC/←→ 키보드, 파일명+카운터 footer, R2 presigned URL 자동 치환.
        *   **확장 필요**: `#global-viewer-footer`에 **시공자 코멘트**(AS 접수 사유, 시공 불가 사유 등)와 **주문 기본 정보**를 함께 삽입하여 관리자가 사진을 넘기면서 과실 여부를 즉시 판별할 수 있도록 함.
        *   **호출 방식**: `window.GlobalImageViewer.open(files, startIndex)` — `files` 배열에 `{url, filename, key}` 형태로 시공 사진 데이터를 전달.
2.  **이슈 판정 및 귀속 처리 (비용 청구 트리거)**
    *   사진 리뷰 후 정상(완료) / 미결(재방문 요망) / AS 접수가 필요한 건으로 즉시 상태 전환.
    *   미결/AS 판정 시 **[비용 청구 모달]** 팝업 → 귀속 대상(영업, 도면, 공장, 시공팀, 고객) 및 청구 금액/사유 입력.
3.  **향후 확장성 보장 (시공비 정산 연계)**
    *   입력된 귀속 정보는 차주 오픈 예정인 `시공비 정산 대시보드`에서 집계할 수 있도록 DB의 `structured_data.settlement` 하위에 정형화된 JSON 형상으로 저장.

---

## 📐 3. 아키텍처 설계 방향 (GDM 원칙 적용)

### 3.1. Database (JSONB 구조 확장)
새로운 테이블 생성을 피하고, GDM의 단계-최소화(**오컴의 면도날**) 원칙에 따라 기존 `Order.structured_data`에 `settlement` 노드를 편입합니다.

```json
// Order.structured_data.settlement (신규 추가 규격)
"settlement": {
  "status": "APPROVED", // PENDING(대기), ISSUE_RAISED(청구발생), APPROVED(정산확정)
  "base_cost": 150000,  // 기본 시공비
  "deductions": [ // 차감/비용청구 내역
    {
      "id": "DED-12345",
      "department": "DRAWING", // 대상: 영업(SALES), 도면(DRAWING), 시공팀(CONSTRUCTION) 등
      "amount": -50000,
      "reason": "도면 치수 오기로 인한 재방문",
      "created_at": "2026-03-02T10:00:00",
      "created_by": "관리자명"
    }
  ],
  "final_cost": 100000 
}
```

### 3.2. Backend (Python/Flask)
*   **신규 Blueprint 파일 생성**: `apps/erp_completion_page.py` 를 **새로 생성**하고 `app.py`에서 `app.register_blueprint(erp_completion_page_bp)`로 등록.
    > ⚠️ 주의: `apps/erp.py`는 공통 헬퍼/필터 허브 전용 파일(40줄, 라우트 없음)임. 절대 라우트를 추가하지 말 것.
*   **API 분리**: 사진 갤러리 로딩 속도 저하를 막기 위해 **목록 API**와 **사진 API**를 분리하거나 (GraphQL 패턴), DB 쿼리에서 `Attachment`를 `JOIN`하여 한 번에 가볍게 내려주는 방향 채택.
*   **API 엔드포인트**:
    *   `GET /api/orders/completion` (완료 데이터 + 썸네일 경로 + **시공자 코멘트(`as_content`, `fail_history`, `completion_note`)** 함께 로드)
    *   `POST /api/orders/<id>/settlement/issue` (비용 청구/차감 이벤트 기록)

### 3.3. Frontend (HTML/JS/CSS)
*   `templates/erp_completion_dashboard.html`: 메인 레이아웃.
*   `templates/partials/erp_completion_scripts.html` & `_styles.html`: 모듈형 파일.
*   **UI 패턴 (Bento Grid + Accordion)**: 
    화면 폭을 고려하여, 모바일 환경에서는 상단 요약 / 하단 사진 가로 스크롤(`overflow-x: auto` + `display: flex` — Bootstrap 기반 먼저 구현)로, 데스크탑에서는 좌측 1줄 요약 / 우측 사진 카드들의 수평 배치 형태 채택.
    > Swiper.js 등 외부 라이브러리는 코드베이스에 미설치 상태이므로, 오컴의 면도날 원칙에 따라 Bootstrap CSS 스크롤로 선구현 후 선택적 적용.

---

## 📝 4. Phase 별 실행 계획 (Execution Roadmap)

### Phase 1: 백엔드 및 구조 준비 (안정화)
1. `apps/erp_completion_page.py` **신규 생성** 및 `app.py`에서 `app.register_blueprint(erp_completion_page_bp)` 등록 + 빈 템플릿(HTML) 세트 생성.
   * ⚠️ `app.py`의 `_erp_construction_team_restrict()` 함수에 `/erp/completion` 경로를 시공팀 허용 목록에 추가할 것. (미추가 시 시공팀 사용자가 접근 불가)
2. `apps/api/erp_orders_completion.py` 생성 및 목록 조회 API 구현.
   * *조건*: 실제 코드(`erp_construction_page.py`) 기준 — stage가 `COMPLETED`, `완료`, **`AS_WAIT`**, **`CS`**, `AS_RECEIVED` 중 하나인 주문 대상.
     ```python
     # 완료 대시보드 대상 스테이지 (실제 코드에서 '시공완료'로 분류되는 모든 값)
     TARGET_STAGES = ('COMPLETED', '완료', 'AS_WAIT', 'CS', 'AS_RECEIVED')
     ```
3. `OrderAttachment`(실제 DB 테이블: `order_attachments`)에서 시공 사진(category: **`construction`** 고정) URL을 함께 반환하도록 쿼리 작성.
   * `Order` 모델에는 `attachments` relationship이 없으므로, `joinedload` 불가. Raw SQL 또는 별도 쿼리로 `order_id`별 사진 목록을 로드해야 함.

### Phase 2: 시각적 갤러리 대시보드 UI (강조 영역)
1. **1줄 요약 테이블 + 갤러리 뷰 하이브리드 컴포넌트** CSS 구현 (flexbox 수평 스크롤).
2. 목록 API결과를 화면에 렌더링 (이전 채팅 리팩토링에서 확립한 **이벤트 위임(Event Delegation)** 패턴 사용 필수. `onclick="..."` 인라인 방식 엄격히 금지).
3. **사진 뷰어 연동 (GlobalImageViewer 재활용)**:
   * 썸네일 클릭 시 `window.GlobalImageViewer.open(files, index)` 호출로 기존 전역 뷰어 활용 (신규 컴포넌트 생성 불필요).
   * `#global-viewer-footer`에 시공자 코멘트/AS사유 동적 삽입 로직 추가 (혹은 open 전에 footer content를 동적 주입).

### Phase 3: 비용 청구(정산/이슈) 로직 연결
1. **[비용 청구/상태 변경 모달]** UI 구현.
2. `POST /api/orders/<id>/settlement/issue` API 구현.
3. 상태 전환 및 `structured_data.settlement` 에 비용 차감/담당부서 귀속 트리거 로직 구현.
4. SecurityLog 및 OrderEvent(히스토리) 노드 반영.

### Phase 4: 리뷰 및 품질 검사 (GDM 감사)
1. SQL N+1 쿼리 방지 점검 (`Order` 모델에 `attachments` relationship이 없으므로 Raw SQL 서브쿼리 방식의 N+1 회피가 제대로 적용되었는지 확인).
2. UI 모바일 깨짐 검수 (특히 갤러리 스크롤 구간).
3. 정산 금액 테스트 처리.

---

## ✅ 5. Phase 1 구현 완료 (2026-03-02)

| 항목 | 상태 |
|------|------|
| `apps/erp_completion_page.py` Blueprint 생성 및 `/erp/completion` 라우트 | ✅ |
| `app.py`에 Blueprint 등록 및 시공팀 허용 경로 추가 | ✅ |
| `apps/api/erp_orders_completion.py` — `GET /api/orders/completion` | ✅ |
| 대상: `Order.status` in (`COMPLETED`, `AS_RECEIVED`, `AS_COMPLETED`), `category=construction` 사진 | ✅ |
| N+1 방지: order_id별 construction 첨부 일괄 조회 | ✅ |
| `templates/erp_completion_dashboard.html` + partials (scripts/styles) | ✅ |
| ERP 서브네비에 "시공 완료" 메뉴 추가 | ✅ |
| 목록 로드 + 썸네일 가로 스크롤 + 썸네일 클릭 시 GlobalImageViewer 연동 | ✅ |

**Phase 2 반영:** 1줄 요약·갤러리 CSS, GlobalImageViewer footer 시공자 코멘트 동적 삽입 완료.

**Phase 3 반영:** `POST /api/orders/<id>/settlement/issue` API 구현, `structured_data.settlement`(status, deductions) 저장, SecurityLog·OrderEvent 기록. 비용 청구 모달(귀속 대상·금액·사유) 및 행별 "비용 청구" 버튼(이벤트 위임) 적용 완료.

**Phase 4 반영:** N+1 점검(Order 1회 + Attachment 1회 일괄 조회) 확인. 모바일 갤러리·요약 행 `min-width: 0` 및 768px 이하 패딩/버튼 조정. 정산 금액(final_cost) 계산 로직 검증 완료.

---

## 6. 다음 행동 지시
본 계획서는 **전체 업무의 지향점을 담은 Blueprint**입니다.

**Phase 1~4 구현·검수 완료.** 완료 보고서: `docs/plans/2026-03-02-construction-completion-doublecheck.md` §완료 보고서 참조.

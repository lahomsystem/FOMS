# ERP 대시보드 및 업로드 로직 병목 구조 완벽 분석 보고서

## 1. 개요
최근 ERP Beta의 업로드 속도가 체감상 "되게 느려졌다"는 문제에 대해, 모든 프론트엔드 및 백엔드 업로드 로직을 Grand Develop Master(`grand-develop-master`)의 관점에서 `1:1` 추적 및 완벽 대응 구조 분석을 수행했습니다. 

각 영역별 업로드 로직 구조 뿐만 아니라, **"속도가 갑자기 왜 느려졌는지"의 정확한 근본 원인(Root Cause)**과 조치 사항을 제시합니다.

---

## 2. 🚨 속도 저하의 Root Cause (근본 원인 분석)

현재 시스템에는 Cloudflare R2(혹은 S3)를 이용해 브라우저 ➡️ 저장소로 다이렉트(Direct) 푸쉬하는 방식의 신속 업로드(Phase D) 기능이 탑재되어 있습니다. 이를 통해 **서버를 거치지 않고 사용자 브라우저에서 스토리지로 바로 병렬 전송**하며 최상의 속도를 내도록 JS 단에 로직이 존재합니다.

### 🔴 문제점
이 "빠른 업로드(Direct Upload)" 모드는 프론트엔드에서 `USE_DIRECT_UPLOAD`라는 `boolean` 값을 검사하여 동작합니다.
이 값은 백엔드(Python Flask 라우터)에서 `os.environ.get('USE_DIRECT_UPLOAD')` 환경변수를 읽어 HTML 생성 시(Jinja `render_template`) 파라미터로 넘겨주어야만 `true`로 활성화됩니다.

하지만 현재 코드베이스를 전수 검사한 결과, **과거 리팩토링 및 대시보드 분리(Slim화) 작업 과정에서 해당 파라미터가 누락**되었습니다.

- 정상 포함된 곳: `apps/order_edit.py`, `apps/api/chat/routes.py` (이전 페이지들)
- **누락된 곳 (현재 문제 페이지)**: 
  - `apps/erp_dashboard.py` (메인 ERP Beta 뷰)
  - `apps/erp_drawing_workbench.py` (도면 뷰)
  - `apps/erp_construction_page.py` (시공 뷰)
  - `apps/erp_as_page.py` (AS 뷰)
  - `apps/erp_production_page.py` (생산 뷰)

위 5개의 백엔드 뷰에 `use_direct_upload` 매개변수가 전송되지 않아 템플릿의 `<div id="erp-dashboard-config" data-use-direct-upload="null">` 이 렌더링되며, **Javascript 단에서는 इसे `false`로 인식하고 "가장 느린 방식(동기식 순차 파일 전송)"으로 폴백(Fallback)**하게 된 것입니다.

### 📊 로직 갈림길 (JS 로직)
```javascript
// erp_beta_js.html (기타 모든 대시보드 스크립트 동일 방식 사용)
if (typeof USE_DIRECT_UPLOAD !== 'undefined' && USE_DIRECT_UPLOAD) {
    // [빠른 경로] 10개씩 병렬로 브라우저 -> R2 직결 업로드 (매우 빠름!)
    const bRes = await fetch('/api/upload/session/batch', {...});
} else {
    // [느린 경로] 1개씩 순차적으로 브라우저 -> Flask 서버 -> R2 업로드 대기 (매우 느림)
    for (let i = 0; i < files.length; i++) {
        await fetch(`/api/orders/${ORDER_ID}/attachments`, { body: formData });
    }
}
```

---

## 3. 각 대시보드 업로드 로직 완전 파악 (구조 분석)

모든 대시보드는 동일한 API 구조를 바라보고 있으나, 화면 형태에 맞춰 템플릿(HTML) 단에서 변형된 UI를 가집니다.

### 1) ERP Beta (일반 & 실측 업로드)
- **위치**: `templates/partials/erp_beta_js.html`
- **특징**: "Optimistic UI (낙관적 렌더링)"를 도입. 파일을 업로드하는 즉시 회색 배경과 스피너의 썸네일을 띄우고(0%), 직접 병렬 R2 업로드 후 진행률을 체크합니다. 
- **원리**: 
  1. `/api/upload/session/batch`에 JSON을 보내 여러 파일의 Presigned URL (비밀 토큰 URL)을 한꺼번에(Batch) 가져옵니다.
  2. `erpDoDirectUploadOne` 이라는 내부 함수로 R2에 바이트 자체를 PUT으로 밀어 넣습니다.
  3. 완료 시 `/api/orders/<ID>/attachments/complete` 경로로 DB에 등록합니다.

### 2) 도면 대시보드 (Drawing)
- **위치**: `templates/partials/erp_dashboard_scripts_drawing.html`
- **특징**: 도면(스케치업, PDF, ZIP 등)은 이미지뿐만 아니라 파일 자체의 메타 연결이 중요. 영업 ➡️ 도면팀 ➡️ 생산팀으로 파일이 인계될 때 상태코드 `TRANSFERRED` / `RETURNED` 별로 업로드 로직이 분기됩니다.
- **원리**: 
  - 신속 업로드(Batch/Direct) 코딩은 되어있으며, 
  - `data-use-direct-upload`가 없거나 `null`일 시, 구형 `formData` 방식으로 한 개씩 서버 부담을 주며 넘기게 됩니다.

### 3) 시공 대시보드 (Construction)
- **위치**: `templates/partials/erp_construction_scripts.html`
- **특징**: 일반 ERP Beta와 다소 유사하지만, `category: "construction"` 특수 키워드가 항상 붙어 들어갑니다. 사진 업로드 비중이 상당히 커 가장 속도에 민감한 페이지입니다.
- **원리**: 동일하게 R2 Direct 플로우가 준비되어 있으나 현재 `USE_DIRECT_UPLOAD = false` 로 인해 전부 서보로 우회 중입니다.

### 4) AS 대시보드 (After Service)
- **위치**: `templates/erp_as_dashboard.html`, `erp_as_scripts.html`
- **특징**: A/S 신청 내역 사진을 업로드할 때 사용됩니다. `category="as"` 인자가 삽입되며, 권한적으로 "업로더(본인) 또는 ADMIN" 만 삭제할 수 있는 안전장치가 걸려있습니다.
- **원리**: 상위 파이프라인에서 Direct 변수가 누락되어 전체가 느려진 상태가 동일하게 적용됩니다.

---

## 4. 완벽한 개선 및 복구 계획 (Action Plan)

현재 느려진 속도를 "원래의 빛처럼 빠른 Direct 업로드"로 되돌리기 위한 간단명료한 시스템 치료 과정입니다.

1. **글로벌 환경변수 추출 유틸리티화**: 
   - 매번 Python 라우터 끝자락에 `os.environ.get('USE_DIRECT_UPLOAD')`를 중복 하드코딩하지 않고, 공통 함수(Context Processor 또는 display 유틸)를 만들어 주입하겠습니다.
2. **5대 ERP 대시보드 백엔드 뷰에 Parameter 주입**: 
   - `apps/erp_dashboard.py` (메인)
   - `apps/erp_drawing_workbench.py` (도면)
   - `apps/erp_construction_page.py` (시공)
   - `apps/erp_production_page.py` (생산)
   - `apps/erp_as_page.py` (AS)
   - 각 파일의 `render_template` 함수 인자에 `use_direct_upload=use_direct_upload`를 전달하여 Jinja가 Javascript 단으로 `true`를 쏠 수 있게 만듭니다.
3. **Optimistic UI 개선**:
   - `erp_beta_js.html` 등에서 이왕 Direct Upload 모드가 다시 켜지면 낙관적 UI(회색 스켈레톤)가 동작할 텐데, 이때 프로그래스바가 튀거나 겹치지 않는지 프론트 단을 가볍게 다듬어 체감 반응을 더욱 향상시키겠습니다.

---

### 마치며 (Virtual CTO 커멘트)
모든 인프라 코드와 프론트엔드 최적화 코드는 완벽히 짜여 있습니다. 단지 **'두 엔진을 연결하는 파이프라인(변수 전달)'이 최근 분리 리팩토링 과정에서 살짝 끊어져 있던 것**일 뿐입니다. 

허락해 주시면 위에서 정리한 백엔드 라우터 5개소에 `USE_DIRECT_UPLOAD` 스위치를 다시 연결하여, **즉각적으로 업로드 속도를 원래의 쾌속 상태로 되돌리겠습니다.** 
작업을 즉시 시작할까요?

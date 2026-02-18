# Incident RCA: ERP 대시보드 > 작업큐 > 상세 보기 열리지 않음

## Incident RCA
- **Incident:** /erp/dashboard 작업큐에서 주문 건 "상세 보기" 클릭 시 상세 패널이 열리지 않고, 콘솔에 `Uncaught SyntaxError: Unexpected token '<'` (dashboard:3125)
- **Severity:** SEV-3 (부분 기능 장애, 우회 가능)
- **User Impact:** ERP 대시보드에서 주문 상세를 인라인으로 볼 수 없음

## Timeline
1. 사용자: http://172.30.1.89:5000/erp/dashboard 접속 → 작업큐 > 주문 > 상세 보기 클릭 → 동작 안 함
2. 콘솔: `Unexpected token '<'` at dashboard:3125
3. 원인 추정: API가 JSON 대신 HTML 반환 시 `r.json()` 파싱에서 '<' 로 인한 SyntaxError
4. 수정: fetch 응답에 대해 `content-type`/`ok` 검사 후 JSON만 파싱하도록 `safeJsonFetch` 도입

## Hypothesis Board
1. **가설: API가 401/404/500 등으로 HTML(로그인/에러 페이지)을 반환하고, `r.json()` 호출 시 SyntaxError 발생**
   - 지지: "Unexpected token '<'" 는 HTML 첫 글자 `<` 를 JSON으로 파싱할 때 전형적으로 발생
   - 지지: loadOrderDetail 내 `fetch().then(r => r.json())` 에서 응답 검사 없이 .json() 호출
   - 판정: **유지 → 수정 적용**

2. **가설: Jinja 주입(team_labels/stage_labels)으로 스크립트 내에 '<' 가 들어감**
   - 반박: tojson | safe 사용, 뷰에서 dict만 전달
   - 판정: **기각**

## Fix
- **근본 원인(최종):** `templates/partials/erp_dashboard_scripts.html` 상단에 **`<script>` 태그가 두 번** 연속 기재됨. 두 번째 `<script>`가 JS 코드로 파싱되며 `Unexpected token '<'` 발생 → 스크립트 블록 전체 실패, 상세 보기 미동작.
- **수정 1 (부분):** `safeJsonFetch` 도입 및 loadOrderDetail에서 사용 (API가 HTML 반환 시 런타임 SyntaxError 방지). → 사용자 확인 시 **증상 지속**.
- **수정 2 (근본):** 위 partial에서 **중복 `<script>` 한 개 제거**. → 해결.
- **Files:** `templates/partials/erp_dashboard_scripts.html` (중복 script 제거 + safeJsonFetch 유지), `erp_production_dashboard.html`, `erp_construction_dashboard.html` (safeJsonFetch만)
- **Why:** 파싱 시점 에러는 fetch 보강만으로 해결되지 않음. 해당 라인 근처 인라인 스크립트 구조 검사로 중복 태그 발견 후 제거

## Prevention
- 동일 패턴(`fetch().then(r => r.json())`)이 있는 다른 ERP/API 호출부 점검 시 응답 검사 후 JSON 파싱 권장
- (선택) 스모크: ERP 대시보드 접속 → 작업큐 주문 클릭 → 상세 영역 로드 확인

# Incident RCA: ERP 대시보드 > 작업 큐 > 주문 상세 열리지 않음

## Incident RCA
- **Incident**: ERP 대시보드 작업 큐에서 주문 상세(collapse) 클릭 시 열리지 않음. 브라우저 콘솔 `Uncaught SyntaxError: Unexpected end of input` (dashboard:5222)
- **Severity**: SEV-3 (부분 기능 장애, 우회 가능)
- **User Impact**: 해당 페이지에서 주문 상세 인라인 보기 불가

## Timeline
1. NEXT-002 PART-002에서 `erp_dashboard_scripts.html`을 7개 partial로 분할
2. 분할 시 `document.addEventListener('DOMContentLoaded', () => {` 는 `erp_dashboard_scripts_detail.html`에서 열림
3. 콜백 본문의 나머지는 `erp_dashboard_scripts_dom.html`로 이동했으나, **콜백을 닫는 `});` 가 dom.html 끝에 누락**
4. 렌더된 페이지에서 스크립트가 조기 종료되어 파서가 "Unexpected end of input" 발생

## Hypothesis Board
1. **가설**: PART-002 분할 시 DOMContentLoaded 콜백의 닫는 괄호가 빠짐  
   - 지지: detail.html 561줄에서 `addEventListener('DOMContentLoaded', () => {` 열림, dom.html은 그 연속이지만 끝에 `});` 없음  
   - 반박: 없음  
   - **판정: 유지**

## Fix
- **Files**: `templates/partials/erp_dashboard_scripts_dom.html`
- **Containment**: 해당 파일 끝에 `});` 추가하여 DOMContentLoaded 리스너 콜백 종료
- **Validation**: 저장 후 ERP 대시보드 > 작업 큐 > 주문 상세 클릭 시 콘솔 에러 없이 열리는지 확인

## Additional Fix (2026-02-18 후속)

**가설 2**: Jinja2 `JSON.parse('{{ ... |tojson }}')` 패턴에서 JSON 값에 `</script>`가 포함되면 HTML 파서가 스크립트 태그를 조기 종료 → "Unexpected end of input"

**수정**: `JSON.parse('{{ team_labels|tojson }}')` → `{{ team_labels|tojson }}` (문자열 래핑 제거, JSON 직접 출력)

- `templates/erp_construction_dashboard.html` (1736-1737줄)
- `templates/erp_production_dashboard.html` (1682-1683줄)
- `templates/partials/erp_dashboard_scripts_core.html` (48-49줄)

## Prevention
1. **partial 분할**: 열린 괄호/이벤트 리스너가 어느 partial에서 닫히는지 체크리스트화 (GDM 또는 frontend-ui 작업 시)
2. **Jinja2 + 인라인 스크립트**: `JSON.parse('{{ x|tojson }}')` 패턴 사용 금지 → data-* 속성 + safeJsonParse 권장
3. **클라이언트 장애 진단 순서**: SyntaxError 시 (1) 괄호/스크립트 태그 (2) Jinja 주입 (3) JSON.parse 입력 검증
4. **일괄 체크리스트**: `docs/context/INCIDENT_ERP_DASHBOARD_DETAIL_REVIEW_2026-02-19.md` §3 참조

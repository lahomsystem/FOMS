# ERP 대시보드 스크립트 partial 구문 강조(흰색 코드) 수정

## 원인
- `erp_dashboard_scripts_*.html` 7개 partial은 **순수 JavaScript**만 포함하고, 부모인 `erp_dashboard_scripts.html`이 한 개의 `<script>`로 감싼 뒤 `{% include %}`로 붙이고 있었음.
- 이 partial들을 **단독으로 열면** 확장자가 `.html`이라 에디터가 전체를 HTML로 해석하고, `<script>`가 없어서 안쪽 코드를 JS로 인식하지 못함 → **흰색(미강조)** 로 보임.
- `erp_construction_scripts.html`에서 이미 동일 이슈를 선두에 `<script>`를 두는 방식으로 해결한 것과 같은 패턴.

## 조치 내용

### 1. 부모 템플릿
- **`templates/partials/erp_dashboard_scripts.html`**  
  - 기존: `<script>` … `{% include %}×7` … `</script>`  
  - 변경: `{% include %}×7` 만 유지 (외곽 `<script>` 제거).  
  - 각 partial이 자체 `<script>` 블록을 갖도록 해서, 렌더 결과가 여러 개의 `<script>` 블록으로 나가도 동작은 그대로 유지.

### 2. partial별 래핑
| 파일 | 선두 | 말미 | 비고 |
|------|------|------|------|
| erp_dashboard_scripts_core.html | `<script>` | `</script>` | |
| erp_dashboard_scripts_gateway.html | `<script>` | `</script>` | |
| erp_dashboard_scripts_attachments.html | `<script>` | `</script>` | |
| erp_dashboard_scripts_drawing.html | `<script>` | `</script>` | |
| erp_dashboard_scripts_quest.html | `<script>` | `</script>` | |
| erp_dashboard_scripts_detail_dom.html | `<script>` | `</script>` | detail+dom 통합(한 블록) |

- **detail_dom**: 기존 detail + dom을 하나의 partial로 통합하여 단일 `<script>…</script>` 블록으로 제공. 구문 강조 및 린트 정상 적용.

## 결과
- **core, gateway, attachments, drawing, quest**: 단독으로 열어도 JS 구문 강조 적용.
- **detail_dom**: 단독으로 열어도 `<script>`로 시작하므로 JS 구문 강조 적용.

## 참고
- `templates/partials/erp_construction_scripts.html`: 동일 방식으로 선두 `<script>` 추가해 구문 강조 적용된 상태.

# 실측 대시보드 주문 상세 표시 계획서

**작성일**: 2026-02-25  
**목표**: 실측 대시보드 각 주문건에 도면 작업실('A')과 동일한 주문 상세를 표시.

---

## 1. 요구사항

1. 고객 셀(고객명 옆)에 **v 꺽쇠** 삽입  
2. v 클릭 시 해당 **주문 행 아래로 슬라이드**하여 상세 영역 표시  
3. 슬라이드 영역에 **도면 작업실과 동일한** 주문 상세: `dw-product-main-card` × 항목 수, 실측 첨부 파일 포함  

---

## 2. 구현 단계

| 단계 | 작업 | 담당 |
|------|------|------|
| 1 | product_items 구성 로직 공통 함수로 추출 (도면 작업실·실측 대시보드 공유) | python-backend |
| 2 | 실측 대시보드 뷰에서 행별 product_items 계산 후 템플릿 전달 | python-backend |
| 3 | 실측 대시보드 템플릿: 고객 셀 v꺽쇠 + 상세 행(dw-product-main-card 블록) | frontend-ui |
| 4 | measurement.js: chevron 토글(슬라이드), openDrawingGatewayImageViewer 연동 | frontend-ui |
| 5 | 검증: v 클릭 → 상세 표시, 썸네일 클릭 → 뷰어 동작 | GDM |

---

## 3. 영향 파일

- **신규**: `services/erp_product_items.py` (또는 `erp_drawing_workbench` 내 헬퍼)
- **수정**: `apps/erp_measurement_dashboard.py`, `apps/erp_drawing_workbench.py`, `templates/erp_measurement_dashboard.html`, `static/js/erp/measurement.js`
- **선택**: 도면 상세 스타일/스크립트 공통 partial로 분리

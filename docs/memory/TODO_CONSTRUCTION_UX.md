# 시공 대시보드 UX 수정 할일

## 진행 전 준수
- GDM 프로토콜: `PLAN_CONSTRUCTION_UX.md`·`CONTEXT_CONSTRUCTION_UX.md` 반영. 사용자 승인 후 코딩 진행.

## 할일 체크리스트
- [x] **1.** `erp_construction_filters_grid.html`: 단계 select에 시공대기/시공중/시공완료 옵션 추가
- [x] **2.** `erp_construction_page.py`: stage == 'CS'일 때 display_stage = '시공완료' 매핑 추가
- [x] **3.** `erp_construction_scripts.html`: loadOrderDetail에서 displayStage 계산(history 기반 is_started), 시공대기일 때만 시공 시작 버튼, 시공중일 때만 시공 완료 버튼 렌더
- [ ] **4.** 검증: 타일 필터·시공 시작/완료 버튼·시공 완료 후 시공완료 타일 반영 확인
- [x] **5.** `python -c "import app"` 및 필요 시 서버 기동으로 오류 없음 확인

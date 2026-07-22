# 자가실측·지방 대시보드 물류 상태 Dual-track Spec
> 작성일: 2026-07-23 | 상태: 🟢 승인됨 (사용자 구두 승인)

## 1. What
자가실측·지방 대시보드 = 물류 콘솔. confirm 후 상태 변경. ERP stage-override 의식 미적용.

## 1.2 요구
1. 드롭다운 = LOGISTICS_BOARD_STATUS
2. confirm / 취소 원복
3. field_update: 물류 목표면 override 가드 스킵; SCHEDULED 등은 workflow.stage 보존; COMPLETED/AS_*는 stage 동기화
4. 실패 alert+원복; 완료 성공 reload
5. 메인 파이프라인 skip/regress 가드 유지

## 2. 파일
status_constants / field_update / erp-stage-override.js / self+regional templates / dashboard.py / test_logistics_dashboard_status.py

# FOMS 현재 상태
> 자동 업데이트: 2026-03-13 | 마지막 작업: Phase 4 날짜 검색 최적화, 짐/Payload 최적화, 부분 인덱스 도입 완료

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-03-09] 성능 개선 Phase 0-4 완료 (OrderScheduleDate 전환, 달력/지도/근접검색 최적화, Partial Index 적용)
- [2026-03-02] 긴급 알림 시스템 구축 (브리핑 보드 배너, 1:1 긴급 멘션 UI/API, Socket.IO 연동)
- [2026-03-02] 브리핑 보드 erpbeta 표시 오류 및 404 딥링크(생산/시공/공지) 경로 전수 수정
- [2026-02-28] AI 자동 메모리 시스템 구축 (Hook+Workflow, AI_STATUS/CHANGELOG 자동 갱신)
- [2026-02-27] 지도 auto-poll iframe 재로드 제거 (15s /api/map_data 경량 폴링)


## 진행 중
(없음)

## 검증 필요
- [ ] 시공팀 접근 제한 + mine 필터 수동 테스트
- [ ] 출고 대시보드 시공자 그룹 파스텔 색상 확인
- [ ] 성능 최적화(Phase) 전반 체감 속도 향상 확인 (달력, 지도, 실측, 출고 대시보드 등)

## 알려진 이슈
(없음)

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| apps/api/erp_map.py | 지도/geocode API 최적화 |
| apps/api/orders.py | 주문 캘린더/근접 검색 최적화 |
| models.py | OrderScheduleDate 정규화 및 Partial Index |
| apps/erp_dashboard.py | 첨부 집계 풀스캔 최적화 |
| docs/plans/performance-optimization-plan-v2.md | 성능 최적화 검증 완료 현황 |

## 아키텍처 요약
- 파일 업로드: 브라우저→R2 Presigned PUT 직접 (배치+병렬, UUID키)
- 도면 생명주기: 발송(보존)→취소(신규만삭제)→확정(구버전정리)
- 지도: Folium iframe + /api/map_data 경량 폴링 (15s×5회)
- 성능/조회: OrderScheduleDate(날짜정규화), Partial Indexes 적용
- 권한: CONSTRUCTION팀 출고/시공만, 도면팀 발송/취소

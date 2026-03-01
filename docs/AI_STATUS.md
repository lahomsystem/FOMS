# FOMS 현재 상태
> 자동 업데이트: 2026-03-01 | 마지막 작업: AI 자동 메모리 시스템 구축 (Hook+Workflow)

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-02-28] AI 자동 메모리 시스템 구축 (Hook+Workflow, AI_STATUS/CHANGELOG 자동 갱신)
- [2026-02-27] 지도 auto-poll iframe 재로드 제거 (15s /api/map_data 경량 폴링)
- [2026-02-27] 도면 수령 확정 시 구 버전 파일 R2+DB 정리 (db.commit 누락 수정)
- [2026-02-27] 도면 전달 취소 시 원본 파일 유실 버그 수정 (REPLACE 시 R2 삭제 제거)
- [2026-02-26] AS/시공/도면 대시보드 업로드 로직 배치+병렬 표준화


## 진행 중
(없음)

## 검증 필요
- [ ] 시공팀 접근 제한 + mine 필터 수동 테스트
- [ ] 출고 대시보드 시공자 그룹 파스텔 색상 확인
- [ ] Railway Worker geocode 마커 표시 확인

## 알려진 이슈
(없음)

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| apps/api/erp_orders_drawing.py | 도면 전달/취소 API |
| apps/api/erp_orders_draftsman.py | 도면 담당자/수령확정 |
| apps/api/erp_map.py | 지도/geocode API |
| services/storage.py | R2 스토리지 추상화 |
| templates/map_view.html | 지도 뷰 (auto-poll) |
| static/js/upload-progress.js | 공통 업로드 진행 UI |

## 아키텍처 요약
- 파일 업로드: 브라우저→R2 Presigned PUT 직접 (배치+병렬, UUID키)
- 도면 생명주기: 발송(보존)→취소(신규만삭제)→확정(구버전정리)
- 지도: Folium iframe + /api/map_data 경량 폴링 (15s×5회)
- 권한: CONSTRUCTION팀 출고/시공만, 도면팀 발송/취소

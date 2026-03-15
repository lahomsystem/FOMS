# FOMS 현재 상태
> 자동 업데이트: 2026-03-15 | 마지막 작업: Phase C 쿼리 기준/인덱스 정렬 완료

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-03-15] Phase C 완료: soft-delete 기준 통일(Order.active_filter), C-1/C-2 인덱스 마이그레이션 작성
- [2026-03-15] Phase A/B 완료: JSONB flag_modified, User N+1 제거, Promise.all 병렬화, 정렬 중복 제거
- [2026-03-09] 성능 개선 Phase 0-4 완료 (OrderScheduleDate 전환, 달력/지도/근접검색 최적화, Partial Index 적용)
- [2026-03-02] 긴급 알림 시스템 구축 (브리핑 보드 배너, 1:1 긴급 멘션 UI/API, Socket.IO 연동)
- [2026-03-02] 브리핑 보드 erpbeta 표시 오류 및 404 딥링크(생산/시공/공지) 경로 전수 수정
- [2026-02-28] AI 자동 메모리 시스템 구축 (Hook+Workflow, AI_STATUS/CHANGELOG 자동 갱신)
- [2026-02-27] 지도 auto-poll iframe 재로드 제거 (15s /api/map_data 경량 폴링)


## 진행 중
(없음)

## 검증 필요
- [ ] Phase C 마이그레이션: Railway/운영에서 `alembic upgrade head` 실행 (CONCURRENTLY 트랜잭션 검증)
- [ ] 시공팀 접근 제한 + mine 필터 수동 테스트
- [ ] 출고 대시보드 시공자 그룹 파스텔 색상 확인
- [ ] 성능 최적화(Phase) 전반 체감 속도 향상 확인 (달력, 지도, 실측, 출고 대시보드 등)

## 알려진 이슈
(없음)

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| models.py | Order.active_filter(), Phase C Index (deleted_at 포함) |
| migrations/versions/phase_c_indexes_concurrently.py | C-1 ix_orders_active_id, C-2 ix_orders_structured_data_gin |
| apps/api/personal_board.py | _recent_work active_filter 적용 |
| docs/evolution/PHASE_C_*.md | Phase C 실행/코드리뷰/GDM 감리 |

## 아키텍처 요약
- 파일 업로드: 브라우저→R2 Presigned PUT 직접 (배치+병렬, UUID키)
- 도면 생명주기: 발송(보존)→취소(신규만삭제)→확정(구버전정리)
- 지도: Folium iframe + /api/map_data 경량 폴링 (15s×5회)
- 성능/조회: OrderScheduleDate(날짜정규화), Partial Indexes, Order.active_filter() 통일
- 권한: CONSTRUCTION팀 출고/시공만, 도면팀 발송/취소

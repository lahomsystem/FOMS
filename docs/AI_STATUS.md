# FOMS 현재 상태
> 자동 업데이트: 2026-03-18 | 마지막 작업: 예약금/잔금 입금 확인 뱃지 뷰 및 API (ERP Beta)

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-03-18] ERP 프로세스 및 실측 대시보드에 예약금/잔금 입금 확인 토글 뱃지 기능 추가 
- [2026-03-17] Phase 1~2 성능 개선 블루프린트 완료 (psycogreen 패치, 불필요한 system_build_step DB 호출 제거, Timeout 대기 제거)
- [2026-03-17] 대시보드(ERP 메인/AS/생산) Python 루프 필터를 DB 검색으로 전환 & 서버 페이지네이션 적용 (체감 성능 비약적 단축)
- [2026-03-15] 실측 지도 재구현 Spec Phase 1~6 완료: map_snapshot, order_geocode, conversion_status 단일화, geocode_failed 제거
- [2026-03-15] Phase C 완료: soft-delete 기준 통일(Order.active_filter), C-1/C-2 인덱스 마이그레이션 작성

## 진행 중
(없음)

## 검증 필요
- [ ] 실측 지도 E2E: /erp/measurement?open_map=1 → 지도 진입, pending/failed/success UI, poll 전체 재구성 확인
- [ ] Legacy 정리: `python scripts/fix_geocode_status_inconsistency.py` 1회 실행 (배포 전)
- [ ] Phase C 마이그레이션: Railway/운영에서 `alembic upgrade head` 실행 (CONCURRENTLY 트랜잭션 검증)
- [ ] 시공팀 접근 제한 + mine 필터 수동 테스트
- [ ] 출고 대시보드 시공자 그룹 파스텔 색상 확인
- [ ] 성능 최적화(Phase) 전반 체감 속도 향상 확인 (달력, 지도, 실측, 출고 대시보드 등)

## 알려진 이슈
(없음)

## 핵심 모듈 (최근 수정)
| 파일 | 역할 |
|------|------|
| services/map_snapshot.py | build_measurement_map_query, build_measurement_snapshot (실측 지도 공통) |
| services/order_geocode.py | reset_order_geocode_on_address_change (주소 변경 시 geocode reset) |
| apps/api/erp_map.py | map_snapshot 적용, conversion_status 단일화, geocode_failed 제거 |
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

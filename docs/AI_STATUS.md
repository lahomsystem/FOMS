# FOMS 현재 상태
> 자동 업데이트: 2026-03-26 | 마지막 작업: 예약금/잔금 입금 확인 뱃지 뷰 및 API (ERP Beta)

## 스택
Flask 2.3 + PostgreSQL + R2 + Railway (Web×2, Worker×1)
브랜치: deploy (스테이징) → production (운영)

## 최근 완료 (최대 5개)
- [2026-03-26] 채널톡 연동 Phase E (CT-E-01~05): `/api/channel/webhooks` 수신기 구현, Dedupe/Creation Key 생성 로직 적용, 텍스트 파싱(`services/channel_inbound.py`) 및 RQ Worker 기반 Inbound 처리 구현 완료
- [2026-03-26] 채널톡 연동 Phase D (CT-D-01~04): `/foms 주문`, `/foms 일정`, `/foms 담당` 명령어 파싱 및 응답 서비스 구현 (`channel_quick_actions.py`), WAM 주문 요약 렌더링 뷰 (읽기 전용) 작성 완료
- [2026-03-26] 채널톡 연동 Phase C (CT-C-01~04): `X-Signature` 기반 HMAC 검증 로직 추가 및 Replay 방어(5분 윈도우) 적용, WAM 독립 세션용 JWT 발급/검증 토큰 생성, 보안 정책 문서 작성 완료
- [2026-03-26] 채널톡 연동 Phase B & Phase A (CT-B-01~04, CT-A-01~07): 정책(템플릿/라우팅) 기반 `channel_dispatch.py` 구현, Outbox(`ChannelDeliveryLog`) 상태 전이 API 및 RQ Worker 재시도 로직 반영 완료
- [2026-03-26] 채널톡 연동 Phase 0 (CT-00-01~06, CT-00-CI): Observability API 구현, channel_source_seq 증가 규칙 적용, Bootstrap/Queue 세션 계약 명시, Webhook Payload 샘플 저장 및 CI 연동 스모크 테스트 완료

## 진행 중
- [2026-03-26] 채널톡 연동 (Phase E 완료. Phase F 진행 대기 중)

## 검증 필요
- [ ] 실측 지도 E2E: /erp/measurement?open_map=1 → 지도 진입, pending/failed/success UI, poll 전체 재구성 확인
- [ ] Legacy 정리: `python scripts/fix_geocode_status_inconsistency.py` 1회 실행 (배포 전)
- [x] Phase C 마이그레이션: Railway/운영에서 인덱스 2개 적용 완료 확인 (2026-03-18 check_phase_c_indexes.py로 검증)
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

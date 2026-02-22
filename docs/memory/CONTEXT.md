# Phase C·D·Railway 잔여 작업 — 현재 컨텍스트

## 1. 배경

계획서 3종(phase-c-map-design, phase-d-direct-upload-design, railway-multi-user-scalability-plan)을 코드·구조와 대조하여 남은 작업을 정리함.

## 2. 완료된 작업 (2026-02-22 검증)

### Phase C (지도 구조 전환)
- Order lat/lng 컬럼, Alembic 마이그레이션, geocode job/queue/helpers
- 지도 API 전환, 주소 변경 경로 6곳 enqueue 연결
- backfill, 프론트 geocode_queued, fallback 동기 처리

### Phase D (Direct R2 업로드)
- StorageAdapter: presigned PUT, object_exists, generate_direct_upload_key
- POST /api/upload/session, attachments/blueprint/drawing-gateway complete API
- 첨부·blueprint·drawing-gateway UI direct 플로우 적용

### Railway 계획
- railway.toml, Procfile, gunicorn -w 2, duration_ms 로깅
- services/jobs/, RQ enqueue, order_attachment_thumbnail 등

## 3. 결정 사항

- Phase D USE_DIRECT_UPLOAD=1 기본, R2 없으면 multipart fallback
- 채팅 direct 업로드: 2026-02-22 구현 완료 (session→complete, chat_scripts_file.html)

## 4. 최근 이슈: 원격 주소변환 미동작 (2026-02-22)

- **증상**: lahom-dev.up.railway.app 지도 페이지에서 모든 주문 "▲ 주소오류", 마커 없음
- **원인 후보**: FOMS 웹 REDIS_URL 누락, Worker Offline, Web/Worker REDIS_URL 불일치
- **진단 문서**: `docs/incidents/2026-02-22-remote-geocode-diagnosis.md`

## 6. 지도 즉시 변환 결정 (2026-02-22)

- **요구**: "지도 버튼 누르면 주문과 함께 바로 빠르게 변환"
- **선택안**: api_generate_map 응답 전에 lat/lng 없는 주문을 **동기 병렬 geocode** (ThreadPoolExecutor, 최대 5병렬, 최대 10건)
- **이유**: Worker 순차 처리(건당 ~4.5초) → 8건 36초. 병렬 sync로 8건 ≈ 3~4초 체감. Phase C "실시간 제거" 원칙과 타협하되, 사용자 체감을 우선.
- **제한**: 10건 초과 시 나머지는 기존처럼 enqueue + 폴링.

## 7. 다음 작업 전제

- Railway 1·2: 대시보드 접근 권한 필요 (완료)
- 3.3 부하 테스트: scripts/load_test_map.py (완료)
- Phase D 6.1~6.3: scripts/verify_phase_d.py + 수동 검증

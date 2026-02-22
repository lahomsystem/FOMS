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

## 4. 다음 작업 전제

- Railway 1·2: 대시보드 접근 권한 필요 (완료)
- 3.3 부하 테스트: scripts/load_test_map.py (완료)
- Phase D 6.1~6.3: scripts/verify_phase_d.py + 수동 검증

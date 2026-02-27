# Architecture Decisions Log

> AI 세션 간 중요 기술/아키텍처 결정을 기록합니다.

---

### [2026-02-27] 도면 파일 생명주기 설계 확정
- **결정**: 발송 시 R2 물리 삭제 금지, 수령 확정 시 일괄 정리
- **이유**: 전달 취소 시 원본 복원 가능해야 함. 타임라인 히스토리에서 구 파일 참조 유지 필요
- **영향**: `apps/api/erp_orders_drawing.py` (REPLACE 시 삭제 코드 제거), `apps/api/erp_orders_draftsman.py` (수령 확정 시 정리 + db.commit)

### [2026-02-27] 지도 Auto-poll 방식 변경
- **결정**: geocode pending 시 `/api/generate_map` (Folium 전체 재생성) 대신 `/api/map_data` (좌표만 조회)로 폴링
- **이유**: iframe 전체 재로드가 "자꾸 refresh된다"는 UX 문제 유발
- **영향**: `templates/map_view.html` (15초 간격, 5회 제한)

### [2026-02-26] 업로드 로직 표준화 (배치+병렬)
- **결정**: AS/시공/도면 대시보드 모두 배치 Presigned URL 요청 + 병렬 업로드 (최대 10개 동시)
- **이유**: 업로드 속도 개선 + 파일명 충돌 방지 (UUID 포함 키)
- **영향**: `templates/partials/erp_dashboard_scripts_drawing.html`, `templates/erp_drawing_workbench_detail.html`, `services/storage.py`

### [2026-02-23] Direct R2 Upload (Phase D)
- **결정**: 브라우저 → R2 Presigned PUT 직접 업로드. 앱 서버 파일 경유 없음
- **이유**: 서버 메모리/CPU 절약, 업로드 속도 향상
- **영향**: `services/storage.py`, `apps/api/attachments.py`, 모든 업로드 프론트엔드

### [2026-02-22] Railway Worker + Geocode 컬럼
- **결정**: Railway Worker 서비스 추가, `orders.lat/lng/geocode_status` 컬럼 추가, RQ Job Queue로 비동기 geocode
- **이유**: 지도 로드 시 실시간 Kakao API 호출 병목 제거
- **영향**: `railway-worker.toml`, `models.py`, `services/jobs/`

### [2026-02-20] Production 다중 사용자 확장
- **결정**: Web Replica 2개, Worker 1개, DB 풀 환경변수화
- **이유**: 동시 사용자 증가 대응
- **영향**: `railway.toml`, `db.py`

### [2026-02-16] Flask 유지 + 점진 고도화 (Strangler Fig)
- **결정**: SvelteKit 전면 마이그레이션 대신 Flask 유지, Blueprint 분리 우선
- **이유**: 전면 마이그레이션 리스크 과대, 기존 스택 충분히 유효

### [2026-02-16] services/ 폴더 도입
- **결정**: `business_calendar`, `erp_policy`, `storage` → `services/` 이동
- **이유**: 비즈니스 로직 집중, `app.py`는 Blueprint 등록만 담당

### [2026-02-16] 컨텍스트 엔지니어링 시스템
- **결정**: Hooks + Rules + Memory (`docs/`) 통합 시스템
- **이유**: AI 세션 간 기억 상실, 지시 미준수 문제 해결

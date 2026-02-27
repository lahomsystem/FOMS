# FOMS 시스템 현황 (2026-02-27 기준)

## 스택 & 배포
- **Backend**: Python (Flask), PostgreSQL, Redis, SQLAlchemy
- **Storage**: Cloudflare R2 (Presigned URL 직접 업로드)
- **배포**: Railway (Web × 2 Replica, Worker × 1)
- **브랜치**: `deploy` (스테이징) → `production` (운영)

---

## 현재 아키텍처 주요 결정사항

### 파일 업로드 (2026-02-26 완성)
- 브라우저 → R2 직접 Presigned PUT (앱 서버 미경유)
- 배치 세션 요청 + 병렬 업로드 (최대 10개 동시)
- UUID 포함 파일키로 충돌 방지 (`services/storage.py`)
- 클라이언트 사이드 이미지 압축 (`static/js/upload-progress.js`)

### 도면 파일 생명주기 (2026-02-27 완성)
1. **발송/재발송**: 구 파일 R2 보존, `drawing_current_files` 포인터만 업데이트, `previous_current_files` 히스토리 저장
2. **전달 취소**: 신규 파일만 R2 삭제, `previous_current_files` 로 완전 복원, 수정 요청 있었으면 RETURNED 상태 복귀
3. **수령 확정**: `drawing_current_files` 에 없는 구 버전 파일 R2 + DB 완전 정리 (db.commit 필수)

### 지도 (2026-02-27 개선)
- 최초 로드: `/api/generate_map` (Folium iframe 생성)
- Auto-poll (geocode pending 시): `/api/map_data` 경량 조회, iframe 재로드 없음
- Polling 간격 15초, 최대 5회 (이전: 6초 × 10회)

### 권한 & 접근 제어
- CONSTRUCTION 팀: 출고/시공 대시보드만 접근 가능
- 도면팀: 도면 발송/취소 권한
- 관리자: 전체 권한

---

## 주요 모듈 맵

| 경로 | 역할 |
|------|------|
| `apps/api/erp_orders_drawing.py` | 도면 전달/취소 API |
| `apps/api/erp_orders_draftsman.py` | 도면 담당자 지정 / 수령 확정 |
| `apps/api/erp_orders_revision.py` | 수정 요청 API |
| `apps/api/erp_map.py` | 지도 데이터 / geocode |
| `services/storage.py` | R2/S3/Local 스토리지 추상화 |
| `services/erp_permissions.py` | ERP 권한 체크 |
| `services/erp_policy.py` | 도메인 담당자 정책 |
| `templates/erp_drawing_workbench_detail.html` | 도면 작업실 UI |
| `templates/partials/erp_dashboard_scripts_drawing.html` | 도면 대시보드 스크립트 |
| `static/js/upload-progress.js` | 공통 업로드 진행 UI |

---

## 환경변수 (필수)

| 변수 | 설명 |
|------|------|
| `STORAGE_TYPE` | `r2` / `s3` / `local` |
| `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`, `R2_ENDPOINT` | R2 설정 |
| `ERP_BETA_ENABLED` | ERP Beta 기능 활성화 |
| `USE_RQ_WORKER` | RQ Worker 사용 여부 |
| `REDIS_URL` | Redis 연결 (Socket.IO, RQ) |
| `DATABASE_URL` | PostgreSQL 연결 |
# Evolution Decisions

실험 결과를 바탕으로 채택/보류/폐기 결정을 기록합니다.

## 의사결정 규칙
- 결정은 근거(지표/테스트/리스크 분석)와 함께 기록
- 채택 시 후속 액션(Rule/Skill/Hook/Agent 반영)을 명시
- 보류/폐기 시 재검토 조건을 명시

## Archived from `docs/harness/policy/DECISIONS.md` (15개 초과 시 이동)

### [2026-02-16] Flask 유지 + 점진 고도화 (Strangler Fig)
- **키워드**: Flask, SvelteKit, 마이그레이션, Strangler
- **결정**: SvelteKit 전면 마이그레이션 대신 Flask 유지, Blueprint 분리 우선
- **이유**: 전면 마이그레이션 리스크 과대, 기존 스택 충분히 유효

### [2026-02-16] services/ 폴더 도입
- **키워드**: services, 비즈니스로직, Blueprint, 구조
- **결정**: `business_calendar`, `erp_policy`, `storage` → `services/` 이동
- **이유**: 비즈니스 로직 집중, `app.py`는 Blueprint 등록만 담당

### [2026-02-16] 컨텍스트 엔지니어링 시스템
- **키워드**: Hooks, Rules, Memory, 컨텍스트, AI메모리
- **결정**: Hooks + Rules + Memory (`docs/`) 통합 시스템
- **이유**: AI 세션 간 기억 상실, 지시 미준수 문제 해결

### [2026-02-23] Direct R2 Upload (Phase D)
- **키워드**: R2, 직접업로드, Presigned PUT, 서버경유제거
- **결정**: 브라우저 -> R2 Presigned PUT 직접 업로드. 앱 서버 파일 경유 없음
- **이유**: 서버 메모리/CPU 절약, 업로드 속도 향상
- **영향**: `services/storage.py`, `apps/api/attachments.py`, 모든 업로드 프론트엔드

### [2026-02-22] Railway Worker + Geocode 컬럼
- **키워드**: Railway, Worker, geocode, RQ, 비동기
- **결정**: Railway Worker 서비스 추가, `orders.lat/lng/geocode_status` 컬럼 추가, RQ Job Queue로 비동기 geocode
- **이유**: 지도 로드 시 실시간 Kakao API 호출 병목 제거
- **영향**: `railway-worker.toml`, `models.py`, `services/jobs/`

### [2026-02-20] Production 다중 사용자 확장
- **키워드**: Railway, Replica, Worker, DB풀, 확장
- **결정**: Web Replica 2개, Worker 1개, DB 풀 환경변수화
- **이유**: 동시 사용자 증가 대응
- **영향**: `railway.toml`, `db.py`

## Decisions
### [YYYY-MM-DD] Decision Title
- Context: 왜 이 결정을 검토했는가
- Decision: 채택 | 보류 | 폐기
- Evidence: 테스트/지표/리뷰 근거
- Impact: 영향 범위(Frontend/Backend/DB/DevOps/UIUX)
- Follow-up:
  - Rule:
  - Skill:
  - Hook:
  - Agent:
- Revisit Condition:


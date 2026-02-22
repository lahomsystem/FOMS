# GDM 실행 계획: Phase C·D·Railway 잔여 작업

> **기준일**: 2026-02-22  
> **근거**: `2026-02-22-phase-c-map-design.md`, `2026-02-22-phase-d-direct-upload-design.md`, `2026-02-22-railway-multi-user-scalability-plan.md` 검증 결과

## 1. 개요

계획서 3종 대조 결과, 핵심 코드는 구현 완료. 남은 것은 **Railway 인프라 설정**, **검증·부하 테스트**, **채팅 direct 업로드**이다.

## 2. 실행 순서 (승인 후 차례대로 수행)

| 순서 | 작업 | 계획서 | 담당 | 비고 |
|------|------|--------|------|------|
| 1 | Railway Worker 서비스 추가 + USE_RQ_WORKER=1 | railway §B | 인프라 | 대시보드 수동 |
| 2 | Railway Web Replica 2개 설정 | railway §A | 인프라 | 대시보드 수동 |
| 3 | Phase C 7.3: 지도 동시 40명 부하 테스트 | phase-c §7.3 | 검증 | k6/locust 등 |
| 4 | 채팅 direct upload (백엔드 + UI) | phase-d §3.4, §4.4 | 개발 | session→complete |
| 5 | Phase D 6.1~6.3 검증 | phase-d §4.6 | 검증 | 대용량/동시/로컬 |

## 3. 각 작업 상세

### 3.1 Railway Worker + USE_RQ_WORKER=1 (Railway 대시보드)
- Worker 서비스 추가, Start Command: `rq worker default`
- 환경변수: `USE_RQ_WORKER=1`, `REDIS_URL` 공유

### 3.2 Railway Web Replica 2개
- Web 서비스에서 Replica 2개 설정 (railway.toml/gunicorn -w 2와 별개로 인스턴스 스케일)

### 3.3 Phase C 7.3 부하 테스트
- 지도 API(`/api/erp/map/data` 등) 동시 40명 접속 시나리오
- 응답 시간/오류율 목표: 2초 이내, 오류 0%

### 3.4 채팅 direct upload
- `apps/api/chat/routes.py`: session → complete API 추가
- 채팅 업로드 UI: multipart 대신 direct 플로우 적용

### 3.5 Phase D 검증
- 6.1 대용량 업로드
- 6.2 동시 업로드
- 6.3 로컬 multipart fallback

## 4. 영향 범위

| 작업 | 영향 파일/영역 |
|------|----------------|
| 3.1~3.2 | Railway 대시보드 (코드 변경 없음) |
| 3.3 | 테스트 스크립트 (신규) |
| 3.4 | `apps/api/chat/routes.py`, 채팅 UI 템플릿 |
| 3.5 | 테스트/검증 스크립트 |

## 5. 롤백

- 3.1~3.2: Railway에서 Worker/Replica 제거·환경변수 원복
- 3.4: 채팅 multipart 경로 유지, direct는 feature flag
- 3.3·3.5: 검증만 수행, 코드 변경 없음

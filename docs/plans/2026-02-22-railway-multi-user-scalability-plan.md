# FOMS 다중 사용자 무지연 운영 계획서 (Railway)

작성일: 2026-02-22  
대상 환경: Railway Production

## 1. 목표

1. 동시 사용자 200명 이상에서도 체감 지연 없이 운영한다.
2. 지도 동시 사용, 파일 동시 업로드/다운로드, 실시간 알림이 동시에 발생해도 서비스 품질을 유지한다.
3. 단순 워커 수 증가가 아니라, 구조적으로 병목을 제거한다.

## 2. 성능 목표(SLO)

1. 일반 API `p95 <= 400ms`
2. 지도 API `p95 <= 1.5s`
3. 알림 배지 API `p95 <= 250ms`
4. 5xx 에러율 `< 0.5%`
5. Socket 재연결 실패율 `< 1%`

## 3. 현재 병목 요약

1. 지도 요청 시 주소 변환(외부 API 호출)이 요청 처리 경로에 있음
2. 파일 업로드 시 썸네일 생성 등 일부 무거운 작업이 웹 요청 경로에 남아 있음
3. web 서비스가 무거운 작업과 사용자 요청을 동시에 처리함

## 4. 최종 아키텍처(권장)

1. `web` 서비스: 사용자 요청 처리(가벼운 API, 인증, Socket.IO, 페이지 렌더)
2. `worker` 서비스: 비동기 작업 전담(썸네일, 파일 후처리, 지오코딩, 향후 대용량 작업)
3. `redis`: Socket.IO message queue + 작업 큐
4. `postgres`: 주문/알림/첨부 메타 저장
5. 파일 저장: R2/S3 직접 다운로드(현재 유지), 업로드는 단계적으로 direct upload 전환

## 5. 실행 단계

### 단계 A. 즉시 안정화 (당일)

1. Railway web replica를 2개로 확장
2. 각 replica의 gunicorn gevent worker를 2로 시작
3. Socket.IO는 websocket-only 유지(불필요한 polling fallback 비활성)
4. 알림 배지 폴링은 60초 유지
5. 모니터링 지표 수집 시작

완료 조건:
1. worker autorestart/timeout 급감
2. connect/disconnect 폭주 로그 감소
3. 일반 API p95 개선

### 단계 B. 무거운 작업 분리 (1~2일)

1. Railway에 `worker` 서비스 추가
2. Redis 큐 기반 job producer/consumer 구성
3. 분리 대상 작업
1. 주문 첨부 썸네일 생성
2. 대용량 파일 후처리
3. 지도 주소 지오코딩
4. 웹 요청은 `작업 등록 -> 즉시 응답`으로 변경
5. 작업 완료는 DB 상태 업데이트 + Socket 이벤트로 알림

완료 조건:
1. 업로드 API p95 하락
2. 웹 프로세스 CPU/메모리 피크 감소
3. 무거운 작업 중에도 일반 화면 응답 안정

### 단계 C. 지도 구조 전환 (2~4일)

1. 주문 데이터에 `lat/lng/geocode_status/geocoded_at/address_hash` 관리
2. 주소 생성/수정 시에만 geocoding job enqueue
3. 지도 조회 API는 좌표 조회만 수행(실시간 geocode 금지)
4. 경로 계산 API는 `(start,end)` 단기 캐시 적용

완료 조건:
1. 지도 동시 사용자 40명 테스트 통과
2. 지도 API timeout/외부 API 의존 지연 제거

### 단계 D. 파일 경로 최적화 (3~5일)

1. 업로드를 direct-to-R2 presigned URL 방식으로 전환
2. 앱 서버는 업로드 세션 발급/완료 검증만 처리
3. 다운로드는 현재처럼 signed URL redirect 유지

완료 조건:
1. 대용량 동시 업로드 시 웹 앱 자원 사용량 급감
2. 업로드 처리량 상승

## 6. Railway 설정 권장값

## 6.1 Web Service

1. Replica: 2 (시작값)
2. Start Command 예시  
`gunicorn -k gevent -w 2 --timeout 120 --graceful-timeout 30 --keep-alive 5 app:app`
3. SocketIO Redis message queue 유지
4. websocket-only 우선

## 6.2 Worker Service

1. Replica: 1 (시작값, 필요 시 2)
2. Redis queue consume 프로세스 실행
3. CPU/메모리 모니터링 후 autoscale 또는 수동 scale

## 6.3 Database / Redis

1. Postgres max connection 대비 app pool 총합 60~70% 이내 유지
2. Redis 연결 재시도/health-check 옵션 유지

## 7. 코드 변경 범위(최종)

1. `jobs/` 또는 `services/jobs/`에 비동기 작업 모듈 추가
2. `api` 레이어는 동기 무거운 처리 제거 후 job enqueue만 수행
3. 작업 상태 조회 API 추가
4. Socket 이벤트 표준화
1. `job_started`
2. `job_done`
3. `job_failed`
5. 지도 API에서 실시간 변환 루프 제거

## 8. 부하 테스트 시나리오

1. 동시 사용자 200명
2. 지도 페이지 동시 사용자 40명
3. 파일 업로드 동시 20건 (50MB~500MB 혼합)
4. 채팅/알림 이벤트 지속 발생

합격 기준:
1. 일반 API p95 <= 400ms
2. 지도 API p95 <= 1.5s
3. 5xx < 0.5%
4. worker 재시작/timeout 경고 없음

## 9. 롤백 계획

1. Web replica/worker 수 즉시 원복
2. 비동기 분리 기능 플래그 off 후 기존 경로 임시 복귀
3. 지도 선계산 전환 장애 시 조회 limit 강화 + 기존 지도 API 임시 복귀

## 10. 운영 체크리스트

1. 배포 전
1. 환경변수 검증
2. Redis/Postgres 연결 상태 검증
3. 큐 적체 알람 설정
2. 배포 직후
1. 30분 집중 모니터링
2. p95/p99, 에러율, 재시작 횟수 확인
3. 배포 후 24시간
1. 피크 시간대 실사용 지표 점검
2. 임계치 초과 시 단계별 scale-up 또는 rollback 실행

## 11. 우선순위

1. Web scale + 모니터링
2. Worker 분리
3. 지도 선계산 전환
4. Direct upload 전환

---

이 계획의 핵심은 "웹 요청 경로에서 무거운 작업을 제거"하는 것이다.  
워커 수/스레드 수 증설은 보조 수단이며, 구조 전환(비동기 분리 + 지도 선계산)이 필수다.

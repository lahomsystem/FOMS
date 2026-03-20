# Production 백업/복구 운영 계획서

> 작성일: 2026-03-20 | 상태: 감리 완료, 최종본

## 1. What: 무엇을 운영 표준으로 고정할 것인가

### 1.1 최종 목표
- FOMS production의 핵심 데이터 자산인 `Railway Postgres`와 `Cloudflare R2`를 분리 백업한다.
- 백업은 `운영 서비스와 같은 위치`에만 남기지 않고, 반드시 `오프사이트 복구본`을 유지한다.
- 백업만 만드는 수준에서 끝내지 않고, `복구 리허설`까지 정기 운영 절차로 고정한다.
- 복구 완료 기준은 `주문 현재 상태`, `structured_data`, `주문 첨부 이미지/동영상`, `AS 첨부`, `썸네일`, `기타 R2 저장 미디어`가 함께 정상 열람되는 상태로 정의한다.

### 1.2 백업 범위
1. `Railway Postgres`
2. `Cloudflare R2` 첨부 파일 버킷
3. 복구에 필요한 운영 설정 메타데이터
4. 백업/복구 실행 기록

### 1.2.1 복구 성공의 정의
- `Railway PostgreSQL restore`만 성공한 상태는 완료로 간주하지 않는다.
- 복구 성공은 `DB + R2`가 같은 복구 시점 기준으로 함께 복원되어, 주문 건의 현재 상태와 첨부 이미지/동영상까지 정상 열람되는 상태여야 한다.
- 주문 ID는 살아 있지만 첨부가 404이거나 presigned/view URL이 깨진 상태는 `복구 실패`로 본다.

### 1.3 현재 확인된 사실
- production DB는 `Railway Postgres`를 사용한다.
- production 첨부 파일은 `Cloudflare R2`를 사용한다.
- 애플리케이션 코드는 R2 환경 변수가 없으면 `static/uploads` 로컬 저장소로 폴백한다. 따라서 운영에서는 `R2 변수 누락 감시`가 필요하다. [services/storage.py](/c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/services/storage.py)
- 로컬 저장소 기반 `simple_backup_system.py`와 `backups/` 폴더는 참고 자산으로는 유효하지만, production 재해복구 표준으로 쓰기에는 `동일 워크스테이션/동일 저장 위치 의존` 한계가 있다. [simple_backup_system.py](/c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/simple_backup_system.py)
- R2 access key/secret이 대화 중 스크린샷으로 노출되었으므로, 현재 키는 `즉시 rotation`이 선행되어야 한다.

### 1.4 근본 원인
- 지금까지는 `DB`, `첨부`, `복구 검증`, `키 관리`가 하나의 운영 표준으로 문서화되지 않았다.
- 그 결과, 일부 백업은 존재해도 `복구 가능성`과 `보존 위치 분리`가 보장되지 않았다.
- 특히 `PostgreSQL 백업만 있으면 주문이 복구된다`고 오해하기 쉬운데, 실제로는 이미지/동영상 원본이 R2에 있으므로 `DB 단독 restore`는 완전 복구가 아니다.

---

## 2. Why: 왜 이렇게 설계하는가

### 2.1 운영 원칙
1. `DB`와 `첨부 파일`은 별도 계층으로 보고 각각 독립 복구 가능해야 한다.
2. 백업 저장소는 production과 분리되어야 한다.
3. 자동 백업만 믿지 않고, 수동 복구 절차와 복구 검증 기록까지 남겨야 한다.
4. 키가 노출되었거나 의심되면 먼저 `rotation`하고, 그 뒤 자동화를 붙인다.
5. `주문 완전 복구`는 DB 레코드 복원만이 아니라 `미디어 원본 열람 가능`까지 포함한다.

### 2.2 목표치
- DB RPO: 24시간 이내
- 첨부 파일 RPO: 24시간 이내
- 서비스 RTO: 4시간 이내
- 위험 작업 전: 수동 백업 1회 추가

---

## 3. How: 백업 구조

### 3.1 계층 1 - Railway 기본 백업
- Railway Postgres의 수동 백업 1회를 즉시 생성한다.
- Railway의 정기 백업을 활성화한다.
- 이 계층은 `가장 빠른 운영 복구` 용도이며, 단독 재해복구 수단으로 간주하지 않는다.

### 3.2 계층 2 - DB 오프사이트 백업
- 하루 1회 `pg_dump -Fc --no-owner --no-privileges` 형식으로 production DB를 덤프한다.
- 덤프 파일은 production Railway 외부의 별도 저장소에 업로드한다.
- 파일명 규칙은 `foms-production-db-YYYYMMDD-HHMM.dump`로 통일한다.
- 보존 주기는 `일간 35개`, `주간 8개`, `월간 12개`를 기본값으로 한다.
- 덤프 업로드 후 `sha256 checksum`을 함께 저장한다.
- 각 dump에는 대응되는 `R2 manifest 시점`을 매핑해, DB와 첨부가 같은 시점으로 복구되도록 한다.

### 3.3 계층 3 - R2 첨부 오프사이트 백업
- production 첨부 버킷과 분리된 `backup 전용 버킷`을 둔다.
- 최종 표준은 `production과 다른 Cloudflare 계정` 또는 `다른 object storage`를 사용하는 것이다.
- 당장 계정 분리가 불가능하면 `별도 backup 버킷`으로 먼저 시작하되, 30일 안에 계정 또는 저장소를 분리한다.
- 하루 1회 버킷 동기화 또는 객체 복제를 수행한다.
- 기본 전략은 `전체 재업로드`가 아니라 `증분 동기화`다.
- 동기화 결과와 별도로 `객체 개수 + 총 용량 + manifest + checksum`을 남긴다.
- backup 버킷은 production 애플리케이션이 직접 읽거나 쓰지 않도록 분리한다.
- 삭제 방지/버전 보존 기능이 있으면 backup 버킷에 우선 적용한다.
- production 버킷 접근 키는 `읽기 전용`, backup 버킷 접근 키는 `쓰기 전용 또는 제한 쓰기`로 분리한다.
- manifest에는 최소한 `storage_key`, `thumbnail_key`, `size`, `etag 또는 checksum`, `백업 시각`이 들어가야 한다.

### 3.3.1 저장 정책
- production R2 버킷은 `실서비스 버킷` 1개다.
- backup R2 버킷은 `백업 버킷` 1개를 별도로 둔다.
- 기본 운영은 `2버킷 구조`를 표준으로 한다.
- backup 버킷은 `현재 미러 + 제한적 버전 보존` 정책으로 운영한다.
- 즉, unchanged 객체는 다시 전체 복사하지 않고, 신규/변경 객체만 동기화한다.
- 삭제된 객체는 즉시 완전 삭제하지 않고, 보존 기간 동안 복구 가능 상태를 유지한다.

### 3.4 계층 4 - 운영 설정 메타데이터
- 운영 복구 문서에는 `환경 변수 이름`, `저장소 이름`, `복구 순서`, `담당자`, `점검 일시`만 기록한다.
- 실제 secret 값은 문서나 git에 저장하지 않는다.
- R2, Railway, 백업 버킷 접근 키는 서로 분리한다.
- secret 원본 저장소는 비밀번호 관리자 또는 별도 secret manager 1곳으로 고정한다.

### 3.5 표준 실행 위치
- 1순위 표준: `GitHub Actions scheduled workflow`
- 2순위 예비: 운영 전용 백업 PC의 `Task Scheduler`
- 금지: 개발자 개인 PC 수동 실행만으로 운영 백업을 대체하는 방식

### 3.6 표준 스케줄
- 매일 02:10 KST: DB dump 생성 및 오프사이트 업로드
- 매일 02:40 KST: R2 첨부 오프사이트 동기화
- 매일 03:10 KST: checksum, 객체 수, dump 존재 여부 검증
- 매주 월요일 03:30 KST: 주간 보관본 승격
- 매월 첫 영업일 10:00 KST: restore drill 실행

### 3.6.1 보존 정책
- DB dump는 `일간 35개`, `주간 8개`, `월간 12개`만 유지하고 나머지는 정리한다.
- R2 backup 버킷은 `현재 미러`를 기본으로 유지한다.
- 삭제 또는 변경된 객체의 이전 버전은 `30일` 보존 후 정리한다.
- 법적/운영 요구가 생기기 전까지 `무기한 버전 누적`은 하지 않는다.
- 따라서 백업 데이터는 계속 쌓이지만, `보존 정책 한도` 안에서 통제되도록 설계한다.

### 3.7 운영 책임
- 1차 책임자: 서비스 운영 담당자
- 2차 책임자: 대체 운영 담당자 1명
- 실패 알림은 메신저 채널과 이메일 2곳으로 동시에 보낸다.
- 실패 알림이 1회라도 발생하면 같은 영업일 안에 원인과 조치 결과를 기록한다.

---

## 4. Immediate Actions: 즉시 해야 할 일

### Phase 0
1. 노출된 `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`를 즉시 rotation한다.
2. rotation 순서는 `신규 키 발급 -> Railway 변수 교체 -> 앱 정상 확인 -> 기존 키 폐기`로 고정한다.
3. rotation 사실과 완료 시각을 운영 기록에 남긴다.
4. Railway Postgres 수동 백업 1회를 생성한다.
5. production R2 버킷의 현재 객체 수와 총 용량을 기록한다.
6. backup 전용 저장소를 별도로 만든다.
7. 위험 작업 전 수동 백업 절차를 운영 체크리스트에 추가한다.

### Phase 1
1. GitHub Actions에 DB 오프사이트 백업 workflow를 만든다.
2. GitHub Actions에 R2 오프사이트 동기화 workflow를 만든다.
3. 백업 성공/실패 알림 채널을 메신저 + 이메일로 고정한다.
4. 실패 시 10분 간격 2회 재시도 정책을 붙인다.
5. 성공 시 checksum과 실행 로그를 함께 저장한다.

### Phase 2
1. staging 또는 별도 복구 환경에 DB restore를 월 1회 수행한다.
2. R2 복구 샘플 10건 이상을 월 1회 검증한다.
3. 분기 1회 전체 복구 리허설을 수행한다.

---

## 5. Restore Runbook: 복구 순서

### 5.1 DB 복구
1. 복구 시점을 결정한다.
2. 해당 시점의 dump 파일과 매핑된 `R2 manifest`를 함께 선택한다.
3. checksum 검증 후 restore를 시작한다.
4. 새 Postgres 인스턴스 또는 staging DB에 restore 한다.
5. 주요 테이블 row count와 첨부 참조 row를 함께 확인한다.
6. 애플리케이션 연결 전 읽기 검증을 먼저 끝낸다.

### 5.2 첨부 복구
1. backup 버킷에서 필요한 시점의 manifest를 선택한다.
2. manifest와 checksum을 먼저 검증한다.
3. production 신규 버킷 또는 임시 복구 버킷에 객체를 복원한다.
4. 샘플 파일 다운로드, 썸네일, 첨부 열람 URL을 확인한다.
5. 이미지뿐 아니라 동영상 파일 1건 이상도 실제 재생 확인한다.

### 5.3 서비스 복구 검증
1. 로그인
2. 주문 조회
3. 첨부 열람
4. AS 첨부 열람
5. 최근 생성 주문/최근 첨부 샘플 확인
6. 오래된 첨부 샘플 1건 이상 확인
7. 주문 현재 상태, 체크리스트, 메모, structured_data가 복구 시점과 일치하는지 확인
8. 이미지 1건, 동영상 1건, 썸네일 1건을 실제 열람 확인

---

## 6. Verification: 완료 기준

- [ ] Railway Postgres 수동 백업 1회 생성
- [ ] Railway 정기 백업 활성화
- [ ] DB 오프사이트 자동 덤프 동작 확인
- [ ] R2 오프사이트 동기화 동작 확인
- [ ] backup 저장소가 production과 분리되어 있음
- [ ] R2 노출 키 rotation 완료
- [ ] DB dump checksum 검증 성공
- [ ] R2 manifest/checksum 검증 성공
- [ ] DB dump와 R2 manifest의 시점 매핑 검증 성공
- [ ] restore drill 1회 성공
- [ ] restore drill에서 주문 상태와 이미지/동영상 열람까지 확인
- [ ] 복구 검증 결과 문서화

---

## 7. Risks and Controls: 주요 리스크와 통제

| 리스크 | 원인 | 통제 방안 |
|------|------|-----------|
| DB만 복구되고 첨부가 유실됨 | DB와 파일을 같이 보지 않음 | DB/R2를 분리 계층으로 운영하고 둘 다 restore drill 수행 |
| DB와 R2의 복구 시점이 달라 주문/첨부가 어긋남 | 시점 매핑 없이 따로 백업 | dump 파일과 R2 manifest를 같은 시점 쌍으로 관리 |
| production 버킷 장애가 backup도 함께 오염 | 같은 저장 위치 사용 | backup 전용 버킷 또는 별도 저장소 사용 |
| 키 노출로 backup 자산이 함께 위험해짐 | 운영 키 재사용 | 즉시 rotation, 운영/백업 키 분리 |
| 백업은 있으나 복구가 실패 | 검증 부재 | 월간 restore drill 의무화 |
| 운영 중 R2 변수 누락으로 local 폴백 | 환경 변수 관리 실패 | 배포 후 storage type 점검 절차 추가 |

---

## 8. FAQ

### 8.1 백업 용량이 엄청 커지나
- 처음 1회는 크다. production DB 전체 dump와 production R2 전체 미러가 처음 생성되기 때문이다.
- 하지만 이후 표준은 `DB dump + R2 증분 동기화`이므로, 매일 모든 미디어를 다시 2배씩 복사하지 않는다.
- 실제로는 `DB dump 누적분 + 신규/변경 미디어 + 30일 보존 버전`만 추가된다.
- 따라서 용량은 늘어나지만, `무제한 폭증`이 아니라 보존 정책 범위 안에서 증가하도록 통제한다.

### 8.2 백업이 매일 진행되면 데이터가 계속 쌓이나
- 그렇다. 다만 `계속 무한정` 쌓이게 두지 않는다.
- DB dump는 정해진 보존 개수만 남기고 오래된 백업은 자동 정리한다.
- R2는 현재 미러를 유지하고, 이전 버전은 `30일`만 보존 후 정리한다.
- 즉, 매일 백업은 하지만 저장량은 `정책 기반 순환 구조`로 관리한다.

### 8.3 production R2 버킷이 2개가 생기나
- 운영 구조상 맞다.
- 하나는 `실서비스용 production 버킷`, 다른 하나는 `backup 전용 버킷`이다.
- 둘은 용도가 다르므로 같은 버킷을 겸용하지 않는다.
- 최종 표준은 가능하면 계정까지 분리한 `2버킷 이상 구조`다.

---

## 9. 구현 메모

- 코드 기준 DB 연결은 `DATABASE_URL` 또는 Railway DB 변수를 사용한다. [db.py](/c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/db.py)
- 스토리지는 `STORAGE_TYPE=r2`와 `R2_*` 변수가 있어야 R2로 고정된다. [services/storage.py](/c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/services/storage.py)
- 기존 `simple_backup_system.py`는 로컬 참고 도구로 유지하되, production 표준 백업 체계로 직접 사용하지 않는다. [simple_backup_system.py](/c:/Users/USER/OneDrive/Desktop/SY/program/lahomproject/FOMS/simple_backup_system.py)

---

## 10. 최종 결론

FOMS production의 백업 표준은 `Railway DB 백업 + DB 오프사이트 dump + R2 오프사이트 복제 + 정기 복구 리허설` 4축으로 고정한다.  
복구 완료는 `주문 레코드만 보이는 상태`가 아니라 `주문 현재 상태 + 이미지/동영상 포함 첨부 열람`까지 정상인 상태여야 한다.  
가장 먼저 할 일은 `노출된 R2 키 rotation`, `Railway 수동 백업 생성`, `backup 전용 저장소 분리`다.

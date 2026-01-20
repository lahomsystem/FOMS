# 채팅 시스템 배포 가이드 (Quest 14)

## Railway 배포 설정

### 1. 필수 환경 변수 설정

Railway 대시보드에서 다음 환경 변수를 설정하세요:

#### 데이터베이스
```
DATABASE_URL=postgresql://user:password@host:port/dbname
```

#### WDCalculator (권장: 단일 DB + 스키마 분리)
- 기본 동작: WDCalculator는 `DATABASE_URL`과 **같은 DB**를 사용하고, 테이블은 `wdcalculator` 스키마에 생성됩니다.
- 스키마명 변경(선택):
```
WD_CALCULATOR_SCHEMA=wdcalculator
```
- 레거시(별도 DB) 모드로 유지하고 싶다면(선택):
```
WD_CALCULATOR_DATABASE_URL=postgresql://user:password@host:port/wdcalculator_estimates
```

#### 스토리지 설정 (선택사항)
- 로컬 저장소 사용 (개발용):
```
STORAGE_TYPE=local
UPLOAD_FOLDER=static/uploads
```

- Cloudflare R2 사용 (권장):
```
STORAGE_TYPE=r2
R2_ACCOUNT_ID=your_account_id
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET_NAME=your_bucket_name
STORAGE_PUBLIC=false
```

- AWS S3 사용:
```
STORAGE_TYPE=s3
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
S3_BUCKET_NAME=your_bucket_name
AWS_REGION=ap-northeast-2
```

### 2. 의존성 설치

Railway는 자동으로 `requirements.txt`를 읽어 의존성을 설치합니다.

필수 패키지:
- flask-socketio>=5.3.6
- python-socketio>=5.10.0
- eventlet>=0.33.3
- boto3>=1.28.0 (클라우드 스토리지 사용 시)

### 3. Procfile 설정

Railway는 `Procfile`을 자동으로 인식합니다:

```
web: gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:$PORT --timeout 120 app:app
```

**중요**: SocketIO는 단일 워커만 지원합니다 (`-w 1`).

### 4. 데이터베이스 마이그레이션

배포 후 데이터베이스 테이블을 생성해야 합니다:

1. Railway CLI 설치:
```bash
npm i -g @railway/cli
```

2. Railway에 로그인:
```bash
railway login
```

3. 프로젝트 연결:
```bash
railway link
```

4. 데이터베이스 마이그레이션 실행:
```bash
railway run python -c "from app import app; from db import init_db; app.app_context().push(); init_db()"
```

5. WDCalculator 스키마/테이블 초기화(권장: 배포 직후 1회 실행):
```bash
railway run python -c "from app import app; from wdcalculator_db import init_wdcalculator_db; app.app_context().push(); init_wdcalculator_db()"
```

### 5. 파일 저장소 설정

#### 로컬 저장소 (개발용)
- Railway의 임시 저장소 사용
- **주의**: 재배포 시 파일이 삭제될 수 있음
- 프로덕션에서는 클라우드 스토리지 사용 권장

#### 클라우드 스토리지 (프로덕션 권장)
- Cloudflare R2 또는 AWS S3 사용
- 파일이 영구적으로 저장됨
- 대용량 파일 업로드 지원

### 6. 테스트

배포 후 다음 기능을 테스트하세요:

1. 채팅방 생성
2. 메시지 전송/수신
3. 파일 업로드 (이미지, 동영상, 일반 파일)
4. 파일 미리보기
5. 주문 정보 연동

### 7. 문제 해결

#### SocketIO 연결 오류
- `Procfile`에서 `eventlet` 워커 사용 확인
- 환경 변수 `CORS_ALLOWED_ORIGINS` 설정 확인

#### 파일 업로드 실패
- 스토리지 환경 변수 확인
- 파일 크기 제한 확인 (기본 500MB)

#### 데이터베이스 연결 오류
- `DATABASE_URL` 환경 변수 확인
- Railway PostgreSQL 서비스 연결 확인

### 8. 모니터링

Railway 대시보드에서 다음을 모니터링하세요:
- 로그 확인
- 리소스 사용량 (CPU, 메모리)
- 네트워크 트래픽

## 로컬 테스트

로컬에서 Railway와 동일한 환경으로 테스트:

```bash
# 환경 변수 설정
export PORT=5000
export DATABASE_URL=postgresql://user:password@localhost/furniture_orders

# Gunicorn으로 실행
gunicorn --worker-class eventlet -w 1 --bind 0.0.0.0:5000 --timeout 120 app:app
```

## 참고사항

- SocketIO는 단일 워커만 지원하므로 `-w 1` 필수
- 대용량 파일은 클라우드 스토리지 사용 권장
- Railway의 기본 저장소는 임시이므로 프로덕션에서는 클라우드 스토리지 필수

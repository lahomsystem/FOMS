# 가구 주문 관리 시스템 (FOMS) 종합 문서

## 📋 목차
1. [시스템 개요](#시스템-개요)
2. [주요 기능](#주요-기능)
3. [기술 스택](#기술-스택)
4. [시스템 아키텍처](#시스템-아키텍처)
5. [데이터베이스 설계](#데이터베이스-설계)
6. [사용자 권한 체계](#사용자-권한-체계)
7. [보안 기능](#보안-기능)
8. [API 엔드포인트](#api-엔드포인트)
9. [배포 및 운영](#배포-및-운영)
10. [향후 개선 계획](#향후-개선-계획)

---

## 🎯 시스템 개요

### 프로젝트명
**FOMS (Furniture Order Management System) - 가구 주문 관리 시스템**

### 목적
가구 제조 및 판매 업체를 위한 종합적인 주문 관리 솔루션으로, 주문 접수부터 설치 완료까지의 전체 프로세스를 체계적으로 관리하고 추적할 수 있는 웹 기반 시스템입니다.

### 핵심 가치
- **효율성**: 주문 처리 프로세스 자동화 및 최적화
- **투명성**: 실시간 주문 상태 추적 및 진행 상황 가시화
- **확장성**: 다양한 규모의 업체에 적용 가능한 유연한 구조
- **보안성**: 다단계 권한 관리 및 완전한 감사 추적

---

## 🔧 주요 기능

### 1. 주문 관리
#### 1.1 주문 생성 및 편집
- **주문 추가**: 고객 정보, 제품 정보, 옵션 상세 입력
- **주문 수정**: 기존 주문 정보 업데이트 (변경 이력 자동 추적)
- **옵션 관리**: 
  - 직접 입력 방식 (제품명, 규격, 색상, 손잡이 등)
  - 온라인 요약 방식 (자유 형식 텍스트)
- **상태별 날짜 관리**: 각 주문 상태에 맞는 날짜 필드 자동 매핑

#### 1.2 주문 상태 관리
- **접수 (RECEIVED)**: 초기 주문 접수 상태
- **실측 (MEASURED)**: 현장 실측 완료 상태
- **설치 예정 (SCHEDULED)**: 설치 일정 확정 상태
- **완료 (COMPLETED)**: 설치 및 모든 작업 완료 상태
- **AS 접수 (AS_RECEIVED)**: 애프터서비스 요청 접수
- **AS 완료 (AS_COMPLETED)**: 애프터서비스 완료

#### 1.3 일괄 작업
- **상태 일괄 변경**: 선택된 여러 주문의 상태 동시 변경
- **주문 복사**: 기존 주문을 템플릿으로 새 주문 생성
- **일괄 삭제**: 선택된 주문들을 휴지통으로 이동

### 2. 캘린더 시스템
#### 2.1 시각적 일정 관리
- **FullCalendar** 기반의 인터랙티브 캘린더
- **상태별 색상 구분**: 각 주문 상태마다 고유 색상으로 표시
- **실시간 데이터 연동**: 주문 데이터 변경 시 즉시 캘린더 반영

#### 2.2 캘린더 이벤트 규칙
- **상태 우선 원칙**: 주문의 현재 상태에 해당하는 날짜만 캘린더에 표시
- **종일 이벤트 지원**: '실측시간'이 '종일'로 설정된 경우 자동 처리
- **상세 정보 표시**: 이벤트 클릭 시 주문 전체 정보 팝업

### 3. 데이터 관리
#### 3.1 엑셀 연동
- **업로드 기능**: 
  - 대량 주문 데이터 일괄 등록
  - 다양한 날짜/시간 형식 자동 인식
  - 데이터 유효성 검증 및 오류 보고
- **다운로드 기능**:
  - 현재 필터 조건에 맞는 데이터 엑셀 내보내기
  - 한글 컬럼명 자동 변환
  - 타임스탬프 기반 파일명 생성

#### 3.2 검색 및 필터링
- **통합 검색**: 모든 주요 필드를 대상으로 한 키워드 검색
- **컬럼별 필터**: 각 컬럼에 개별 필터 입력창 제공
- **상태별 필터**: 빠른 상태별 주문 조회
- **정렬 기능**: 모든 컬럼에 대한 오름차순/내림차순 정렬

### 4. 휴지통 시스템
#### 4.1 소프트 삭제
- **안전한 삭제**: 실제 데이터 삭제 없이 상태만 변경
- **복원 기능**: 삭제된 주문의 원래 상태 복원
- **영구 삭제**: 관리자 권한으로 완전 삭제 (ID 재정렬 포함)

### 5. 사용자 관리
#### 5.1 계정 관리
- **사용자 등록**: 관리자가 새 사용자 계정 생성
- **프로필 관리**: 사용자 개인 정보 및 비밀번호 변경
- **계정 활성화/비활성화**: 사용자 계정 상태 관리

#### 5.2 권한 기반 접근 제어
- **역할별 메뉴**: 사용자 권한에 따른 메뉴 동적 생성
- **기능별 권한**: 세밀한 기능 단위 접근 제어
- **관리자 보호**: 마지막 관리자 계정 삭제/변경 방지

---

## 💻 기술 스택

### Backend
- **Python 3.x**: 메인 프로그래밍 언어
- **Flask 2.x**: 경량 웹 프레임워크
- **SQLAlchemy**: ORM (Object-Relational Mapping)
- **PostgreSQL**: 메인 데이터베이스
- **Werkzeug**: 보안 기능 (비밀번호 해싱)

### Frontend
- **HTML5/CSS3**: 마크업 및 스타일링
- **Bootstrap 5**: 반응형 UI 프레임워크
- **JavaScript (ES6+)**: 클라이언트 사이드 로직
- **FullCalendar**: 캘린더 컴포넌트
- **jQuery**: DOM 조작 및 AJAX

### Data Processing
- **pandas**: 엑셀 파일 처리 및 데이터 분석
- **openpyxl**: 엑셀 파일 읽기/쓰기
- **Jinja2**: 템플릿 엔진

### Development & Deployment
- **Google Cloud Platform**: 클라우드 배포
- **Git**: 버전 관리
- **pip**: 패키지 관리

---

## 🏗️ 시스템 아키텍처

### 전체 구조
```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Frontend      │    │   Backend       │    │   Database      │
│                 │    │                 │    │                 │
│ • HTML/CSS/JS   │◄──►│ • Flask App     │◄──►│ • PostgreSQL    │
│ • Bootstrap     │    │ • SQLAlchemy    │    │ • Orders Table  │
│ • FullCalendar  │    │ • Business      │    │ • Users Table   │
│ • AJAX          │    │   Logic         │    │ • Logs Table    │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### MVC 패턴 적용
- **Model**: SQLAlchemy ORM 모델 (Order, User, SecurityLog)
- **View**: Jinja2 템플릿 (HTML + 동적 데이터)
- **Controller**: Flask 라우트 핸들러 (비즈니스 로직)

### 레이어드 아키텍처
1. **Presentation Layer**: HTML 템플릿, JavaScript
2. **Application Layer**: Flask 라우트, 비즈니스 로직
3. **Data Access Layer**: SQLAlchemy ORM
4. **Database Layer**: PostgreSQL

---

## 🗄️ 데이터베이스 설계

### 주요 테이블

#### Orders 테이블
```sql
CREATE TABLE orders (
    id SERIAL PRIMARY KEY,
    received_date VARCHAR,          -- 접수일
    received_time VARCHAR,          -- 접수시간
    customer_name VARCHAR NOT NULL, -- 고객명
    phone VARCHAR,                  -- 연락처
    address VARCHAR,                -- 주소
    product VARCHAR,                -- 제품
    options TEXT,                   -- 옵션 (JSON 형태)
    notes TEXT,                     -- 비고
    status VARCHAR DEFAULT 'RECEIVED', -- 상태
    measurement_date VARCHAR,       -- 실측일
    measurement_time VARCHAR,       -- 실측시간
    scheduled_date VARCHAR,         -- 설치 예정일
    completion_date VARCHAR,        -- 설치 완료일
    as_received_date VARCHAR,       -- AS 접수일
    as_completed_date VARCHAR,      -- AS 완료일
    manager_name VARCHAR,           -- 담당자
    payment_amount INTEGER DEFAULT 0, -- 결제금액
    original_status VARCHAR,        -- 삭제 전 원래 상태
    deleted_at VARCHAR             -- 삭제 시간
);
```

#### Users 테이블
```sql
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR UNIQUE NOT NULL, -- 사용자 ID
    password VARCHAR NOT NULL,        -- 암호화된 비밀번호
    name VARCHAR,                     -- 실명
    role VARCHAR NOT NULL,            -- 권한 (ADMIN, MANAGER, STAFF, VIEWER)
    is_active BOOLEAN DEFAULT TRUE,   -- 활성화 상태
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_login TIMESTAMP             -- 마지막 로그인
);
```

#### SecurityLogs 테이블
```sql
CREATE TABLE security_logs (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id), -- 사용자 ID
    message TEXT NOT NULL,                 -- 로그 메시지
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 발생 시간
);
```

### 데이터 정합성
- **외래 키 제약**: 참조 무결성 보장
- **NOT NULL 제약**: 필수 필드 데이터 보장
- **UNIQUE 제약**: 중복 데이터 방지
- **기본값 설정**: 누락 데이터 자동 처리

---

## 👥 사용자 권한 체계

### 권한 레벨 (4단계)
1. **ADMIN (관리자)**
   - 모든 기능 접근 가능
   - 사용자 관리 (생성, 수정, 삭제)
   - 시스템 설정 변경
   - 보안 로그 조회
   - 영구 삭제 권한

2. **MANAGER (매니저)**
   - 주문 관리 (생성, 수정, 삭제)
   - 일괄 작업 수행
   - 휴지통 관리 (복원, 삭제)
   - 엑셀 업로드/다운로드

3. **STAFF (직원)**
   - 주문 조회 및 추가
   - 제한적 수정 권한
   - 기본적인 검색/필터링

4. **VIEWER (뷰어)**
   - 읽기 전용 접근
   - 주문 조회만 가능

### 접근 제어 메커니즘
- **데코레이터 기반**: `@login_required`, `@role_required`
- **세션 기반 인증**: Flask 세션을 통한 로그인 상태 관리
- **동적 메뉴**: 권한에 따른 메뉴 항목 표시/숨김

---

## 🔒 보안 기능

### 인증 보안
- **비밀번호 해싱**: Werkzeug의 PBKDF2 해싱 사용
- **세션 관리**: 안전한 세션 토큰 생성 및 관리
- **로그인 시도 추적**: 실패한 로그인 시도 기록

### 데이터 보안
- **SQL 인젝션 방지**: SQLAlchemy ORM 사용으로 자동 방지
- **XSS 방지**: Jinja2 템플릿의 자동 이스케이프
- **CSRF 방지**: Flask의 내장 보안 기능 활용

### 감사 추적
- **완전한 로그 기록**: 모든 중요 액션 자동 기록
- **변경 이력 추적**: 주문 수정 시 상세 변경 내역 기록
- **사용자 활동 모니터링**: 로그인, 로그아웃, 권한 변경 추적

---

## 🔌 API 엔드포인트

### 주문 관리 API
- `GET /`: 주문 목록 조회 (필터링, 정렬, 페이징)
- `GET /add`: 주문 추가 폼
- `POST /add`: 새 주문 생성
- `GET /edit/<id>`: 주문 수정 폼
- `POST /edit/<id>`: 주문 정보 업데이트
- `GET /delete/<id>`: 주문 삭제 (휴지통 이동)

### 캘린더 API
- `GET /calendar`: 캘린더 페이지
- `GET /api/orders`: 캘린더용 주문 데이터 (JSON)

### 데이터 관리 API
- `GET /upload`: 엑셀 업로드 폼
- `POST /upload`: 엑셀 파일 처리
- `GET /download_excel`: 필터된 데이터 엑셀 다운로드

### 일괄 작업 API
- `POST /bulk_action`: 선택된 주문에 대한 일괄 작업

### 휴지통 관리 API
- `GET /trash`: 삭제된 주문 목록
- `POST /restore_orders`: 선택된 주문 복원
- `POST /permanent_delete_orders`: 영구 삭제

### 사용자 관리 API
- `GET /admin/users`: 사용자 목록
- `GET /admin/users/add`: 사용자 추가 폼
- `POST /admin/users/add`: 새 사용자 생성
- `GET /admin/users/edit/<id>`: 사용자 수정 폼
- `POST /admin/users/edit/<id>`: 사용자 정보 업데이트

### 인증 API
- `GET /login`: 로그인 폼
- `POST /login`: 로그인 처리
- `GET /logout`: 로그아웃
- `GET /profile`: 프로필 관리

---

## 🚀 배포 및 운영

### 배포 환경
- **Google Cloud Platform**: 클라우드 호스팅
- **App Engine**: 서버리스 배포
- **Cloud SQL**: 관리형 PostgreSQL

### 설정 파일
- `app.yaml`: GCP App Engine 설정
- `requirements.txt`: Python 의존성 패키지
- `.gcloudignore`: 배포 제외 파일 목록

### 환경 변수
- `SECRET_KEY`: Flask 세션 암호화 키
- `DATABASE_URL`: 데이터베이스 연결 정보
- `UPLOAD_FOLDER`: 파일 업로드 경로

### 모니터링
- **보안 로그**: 모든 사용자 활동 기록
- **에러 로그**: 시스템 오류 추적
- **성능 모니터링**: 응답 시간 및 리소스 사용량

---

## 🔮 향후 개선 계획

### 단기 개선 사항
1. **알림 시스템**: 중요 상태 변경 시 이메일/SMS 알림
2. **대시보드**: 주문 통계 및 KPI 시각화
3. **모바일 최적화**: 반응형 디자인 개선
4. **API 문서화**: Swagger/OpenAPI 적용

### 중기 개선 사항
1. **실시간 협업**: WebSocket 기반 실시간 업데이트
2. **고급 보고서**: 매출, 성과 분석 리포트
3. **워크플로우 자동화**: 상태 변경 시 자동 액션 실행
4. **다국어 지원**: 국제화(i18n) 적용

### 장기 개선 사항
1. **마이크로서비스**: 서비스별 분리 및 독립 배포
2. **AI/ML 통합**: 수요 예측, 추천 시스템
3. **모바일 앱**: 네이티브 모바일 애플리케이션
4. **API 생태계**: 외부 시스템 연동 API 제공

---

## 📝 시스템 특징 요약

### 강점
- **사용자 친화적**: 직관적인 UI/UX
- **확장 가능성**: 모듈러 구조로 기능 추가 용이
- **안정성**: 철저한 에러 처리 및 데이터 보호
- **추적 가능성**: 완전한 감사 로그 시스템

### 혁신 요소
- **상태 중심 설계**: 주문 상태에 따른 자동 날짜 매핑
- **유연한 옵션 시스템**: 직접 입력 + 자유 형식 지원
- **스마트 캘린더**: 상태별 자동 색상 구분 및 이벤트 생성
- **안전한 삭제**: 소프트 삭제를 통한 데이터 보호

### 기술적 우수성
- **최신 기술 스택**: 업계 표준 기술 적용
- **보안 모범 사례**: 다층 보안 체계 구현
- **성능 최적화**: 효율적인 쿼리 및 인덱싱
- **코드 품질**: 가독성 높은 구조화된 코드

---

**문서 버전**: 1.0  
**최종 업데이트**: 2024년 12월  
**작성자**: FOMS 개발팀  
**문의**: 시스템 관리자 
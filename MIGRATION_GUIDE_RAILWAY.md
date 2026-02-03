# Railway Database Migration Guide

이 가이드는 로컬 데이터베이스의 데이터를 Railway의 PostgreSQL 데이터베이스로 이전하는 방법을 설명합니다.

## 1. 전제 조건

*   **Railway CLI**가 설치되어 있어야 합니다. (`npm i -g @railway/cli`)
*   **PostgreSQL 클라이언트**(`pg_dump`, `psql`)가 로컬에 설치되어 있어야 합니다. (Windows의 경우 Postgres를 설치하면 포함됩니다)
*   프로젝트 루트 디렉토리에서 터미널을 열어주세요.

## 2. DB 연결 확인 및 테이블 생성

먼저 Railway DB에 테이블이 생성되어 있는지 확인합니다.

```bash
# Railway DB 연결 체크 스크립트 실행
railway run python check_db_connection.py
```

만약 테이블이 없거나 `users` 테이블이 없다는 경고가 뜨면, 다음 명령어로 테이블을 생성(초기화)합니다:

```bash
# 마이그레이션/부트스트랩 스크립트 실행
railway run python safe_schema_migration.py
# 또는
railway run python railway_bootstrap.py
```

## 3. 데이터 이관 (Migration)

### 방법 A: 로컬 DB가 SQLite인 경우 (`furniture_orders.db` 등)

SQLite 데이터를 Postgres로 바로 옮기는 것은 까다롭습니다. 가장 쉬운 방법은 **CSV 내보내기/가져오기** 또는 **어드민 페이지에서 엑셀 업로드** 기능을 사용하는 것입니다.

**추천 방법 (엑셀 복원):**
1. 로컬에서 앱을 실행 (`python app.py`)
2. 어드민 페이지 또는 메인 페이지에서 "엑셀 다운로드"를 통해 현재 모든 주문 데이터를 엑셀로 저장.
3. 배포된 Railway 앱(웹사이트)에 접속.
4. "엑셀 파일 업로드" 기능을 통해 데이터 대량 등록.

### 방법 B: 로컬 DB가 PostgreSQL인 경우

로컬 Postgres 데이터를 덤프(백업) 떠서 Railway Postgres에 복원(Restore)합니다.

1.  **Railway DB 접속 정보 확인**
    *   Railway 대시보드 -> 해당 프로젝트 -> PostgreSQL 클릭 -> `Connect` 탭
    *   `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` 정보를 확인합니다.

2.  **로컬 데이터 백업 (Dump)**

    ```bash
    # 로컬 DB 이름이 furniture_orders라고 가정
    pg_dump -h localhost -U postgres furniture_orders > backup.sql
    ```

3.  **Railway DB에 복원 (Restore)**

    ```bash
    # Railway CLI를 사용하여 연결 (가장 간편)
    railway connect
    # (새 창이 뜨면 psql 콘솔에 들어간 것입니다. 여기서 SQL 명령어도 실행 가능하지만, 파일 복원은 아래 명령어로 합니다)
    ```

    **더 쉬운 커맨드라인 복원:**
    Railway 대시보드에서 `Postgres Connection URL` (예: `postgresql://postgres:password@roundhouse.proxy.rlwy.net:12345/railway`)을 복사한 뒤:

    ```bash
    psql "복사한_URL" < backup.sql
    ```

## 4. 문제 발생 시 점검 사항

*   **500 Internal Server Error**: `railway run python check_db_connection.py`를 실행하여 DB 연결 에러인지 확인하세요.
*   **로그 확인**: `railway logs` 명령어로 실시간 로그를 확인하며 에러 메시지를 파악하세요.

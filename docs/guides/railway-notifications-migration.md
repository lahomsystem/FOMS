# Railway Production DB: notifications 테이블 마이그레이션

브리핑 보드·긴급 알림 기능을 위해 `notifications` 테이블에 컬럼을 추가하는 방법입니다.

---

## 방법 1: Railway 대시보드에서 SQL 실행 (가장 간단)

1. **Railway 로그인**  
   https://railway.app → 본인 프로젝트 선택

2. **PostgreSQL 서비스 선택**  
   FOMS 프로젝트 안에서 **PostgreSQL** 플러그인(DB 서비스) 클릭

3. **Data / Query 탭**  
   - **Data** 탭: 테이블 데이터 보기  
   - **Query** 탭이 있으면: 여기서 SQL 직접 실행  
   - Query 탭이 안 보이면:  
     - https://railway.app/account/feature-flags 에서 **Raw SQL Query Tab** 기능 플래그 켜기  
     - 또는 아래 방법 2 사용

4. **아래 SQL 붙여넣고 실행**

```sql
-- notifications 테이블 확장 (한 번만 실행)
ALTER TABLE notifications ALTER COLUMN order_id DROP NOT NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_type VARCHAR(20) NOT NULL DEFAULT 'ORDER';
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS target_user_id INTEGER REFERENCES users(id) NULL;
ALTER TABLE notifications ADD COLUMN IF NOT EXISTS is_urgent BOOLEAN NOT NULL DEFAULT FALSE;
CREATE INDEX IF NOT EXISTS ix_notifications_target_type ON notifications(target_type);
CREATE INDEX IF NOT EXISTS ix_notifications_target_user_id ON notifications(target_user_id);
CREATE INDEX IF NOT EXISTS ix_notifications_is_urgent ON notifications(is_urgent);
```

5. **실행 후**  
   브리핑 보드 새로고침 → 알림/긴급 알림이 정상 동작하는지 확인

---

## 방법 2: 연결 정보로 외부 클라이언트에서 실행

1. **Railway에서 연결 정보 복사**  
   - PostgreSQL 서비스 클릭  
   - **Variables** 또는 **Connect** 탭  
   - `DATABASE_URL` 또는 `PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE` 확인

2. **클라이언트로 접속**  
   - **pgAdmin**, **DBeaver**, **TablePlus**, **VS Code + PostgreSQL 확장** 등  
   - `DATABASE_URL` 한 줄이 있으면 그대로 붙여넣어 연결  
   - 개별 변수만 있으면 호스트/포트/유저/비밀번호/DB이름 입력

3. **Query 도구에서 위와 같은 SQL 실행**

---

## 방법 3: Railway CLI + psql (로컬에 psql 있을 때)

1. **Railway CLI 설치**  
   https://docs.railway.app/develop/cli

2. **프로젝트 연결 후 DB 접속**  
   ```powershell
   railway link
   railway run psql $env:DATABASE_URL
   ```  
   (또는 Railway가 안내하는 `railway connect` 등 명령 사용)

3. **psql 프롬프트에서 위 SQL 붙여넣고 실행**

---

## 실행할 SQL 요약

| 목적 | SQL |
|------|-----|
| order_id NULL 허용 | `ALTER TABLE notifications ALTER COLUMN order_id DROP NOT NULL;` |
| 새 컬럼 추가 | `target_type`, `target_user_id`, `is_urgent` |
| 인덱스 생성 | `ix_notifications_target_type` 등 3개 |

`ADD COLUMN IF NOT EXISTS`, `CREATE INDEX IF NOT EXISTS`를 썼기 때문에 **이미 적용된 환경에서 다시 실행해도 에러 나지 않습니다.**

---

## 문제가 생겼을 때

- **"relation users does not exist"**  
  → `users` 테이블이 있는 DB에 연결했는지 확인 (FOMS 앱이 쓰는 DB).

- **"permission denied"**  
  → Railway가 부여한 DB 유저로 연결했는지 확인 (보통 프로젝트의 PostgreSQL 서비스 Variables에 있는 계정).

- **Query 탭이 없다**  
  → 방법 2(외부 클라이언트) 또는 방법 3(CLI + psql) 사용.

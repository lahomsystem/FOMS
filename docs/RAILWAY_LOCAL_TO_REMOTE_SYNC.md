# 원격(Railway) DB 초기화 후 로컬 Postgres 완전 복사

**GDM 지휘 하에 실수 없이 진행하기 위한 단일 절차서.**  
원격 DB 데이터를 **완전히 비운 뒤**, 로컬 FOMS Postgres를 **그대로** 복사하여 주문·상태·기타 데이터가 로컬과 100% 일치하도록 합니다.

---

## ⛔ 금지 사항 (필수 준수)

- **로컬 Postgres DB는 절대 삭제·초기화·수정하지 않는다.**
- 이 절차에서 로컬 DB에 하는 작업은 **읽기 전용** 한 가지뿐이다: `pg_dump` 로 덤프 파일 생성.
- `--clean`, `--if-exists`, `pg_restore`, `DROP`, `TRUNCATE` 등은 **원격(Railway) 쪽에만** 적용한다. 로컬에는 어떤 삭제/복원 명령도 실행하지 않는다.

---

## 실행 방법 (바로 따라 하기)

**환경**: Windows PowerShell, 프로젝트 루트가 `FOMS` 폴더라고 가정.

### 방법 1 — 스크립트 한 번에 실행 (권장)

**로컬 PC에서 실행할 때**: Railway가 주입하는 `DATABASE_URL`은 **내부 호스트**(`postgres.railway.internal`)라 로컬에서는 이름 해석이 되지 않습니다. `pg_restore` 및 bootstrap은 **공개(Public) 연결 URL**로 해야 합니다.

1. **Railway 연결** (선택):
   ```powershell
   cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
   railway link
   railway status
   ```

2. **공개 DB URL 설정** (로컬에서 복원·bootstrap 시 필수):
   - Railway 대시보드 → 프로젝트(FOMS-DEV) → **Postgres** 서비스 → **Connect** 탭 → **Postgres Connection URL** 에서 **전체 문자열**을 복사한다.
   - 이 URL 안에 **비밀번호가 이미 포함**되어 있으므로, 비밀번호를 따로 찾을 필요 없다. 복사한 그대로 붙여넣으면 된다.
   - (Public URL이어야 함 — 호스트가 `roundhouse.proxy.rlwy.net` 같은 형태. `postgres://` 로 시작해도 스크립트가 `postgresql://` 로 바꿔 쓴다.)
   ```powershell
   $env:RAILWAY_PUBLIC_DATABASE_URL = "여기에_대시보드에서_복사한_URL_전체_붙여넣기"
   ```

3. **스크립트 실행**: 한 줄 실행 후, 프롬프트에 `y` 또는 `yes` 입력.
   ```powershell
   .\scripts\sync_local_to_railway.ps1
   ```
   - 로컬 DB URL이 다르면: `$env:LOCAL_DATABASE_URL = "postgresql://사용자:비밀번호@localhost/DB이름"`

4. 끝나면 원격 앱에서 주문/채팅 등이 로컬과 같은지 확인.

- `RAILWAY_PUBLIC_DATABASE_URL` 를 설정하지 않으면 스크립트는 `railway run` 으로 복원을 시도하는데, 로컬에서는 **"Name or service not known"** 이 나와 실패합니다. 위 2번 설정 후 다시 실행하세요.
- bootstrap 단계에서 **UTF-8 decode 오류**가 나는 경우도, 공개 URL로 연결하면 발생하지 않습니다 (로컬 환경 인코딩 문제 회피).

---

### 방법 2 — 수동으로 단계별 실행

아래를 **순서대로** 프로젝트 루트에서 실행한다. (로컬 DB는 읽기만 하고, 삭제/복원은 원격만.)

```powershell
cd "C:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"
railway link
railway run python check_db_connection.py
```

```powershell
pg_dump -Fc --no-owner --no-privileges -f .\foms.dump "postgresql://postgres:lahom@localhost/furniture_orders"
```

```powershell
railway run powershell -NoProfile -Command "pg_restore --clean --if-exists --no-owner --no-privileges -d $env:DATABASE_URL .\foms.dump"
```

```powershell
railway run python railway_bootstrap.py
```

- `pg_restore` 가 실패하면 **§3.3 방법 B**처럼 Railway 대시보드에서 Postgres Connection URL을 복사한 뒤:
  ```powershell
  $RemoteUrl = "여기에_복사한_URL_붙여넣기"
  pg_restore --clean --if-exists --no-owner --no-privileges -d $RemoteUrl .\foms.dump
  ```

---

## 1. 전제 조건

- **로컬**: PostgreSQL 설치됨, DB `furniture_orders` 존재, FOMS 로컬과 동일한 상태로 사용 중.
- **Railway**: 프로젝트에 Postgres 서비스 연결됨, `DATABASE_URL` 자동 설정됨.
- **도구**: Railway CLI 설치 (`npm i -g @railway/cli`), `pg_dump`/`pg_restore` 사용 가능 (PostgreSQL 설치 시 포함, Windows는 `C:\Program Files\PostgreSQL\16\bin` 등 PATH 또는 전체 경로).
- **검증 근거**: `docs/evolution/BACKUP_RESTORE_VERIFICATION.md` — `pg_dump` 전체 덤프 시 주문·상태( status, original_status, cabinet_status, structured_data 등) 전부 포함됨.

---

## 2. 저장·복원 범위 (GDM 더블체크)

| 대상 | 내용 |
|------|------|
| **주문·상태 100% 일치** | `orders` 테이블 전체( status, original_status, cabinet_status, structured_data, 기타 모든 컬럼) + `order_events`, `order_tasks`, `order_attachments` 등 주문 관련 테이블 전부. |
| **기타 로컬 데이터** | `users`, `security_logs`, `chat_rooms`, `chat_room_members`, `chat_messages`, `chat_attachments`, `notifications` 등 **public 스키마 전체** + **wdcalculator 스키마 전체**(견적·매칭). |
| **초기화** | `pg_restore --clean --if-exists` 로 복원 시 기존 원격 객체를 제거한 뒤 덤프 내용으로 채우므로, 원격은 로컬 덤프와 **완전히 동일**해짐. |

---

## 3. 절차 (순서 엄수)

### 3.1 원격 연결 확인

```powershell
cd "프로젝트_루트"
railway link
# (필요 시) 프로젝트/환경 선택
railway status
railway run python check_db_connection.py
```

- `check_db_connection.py` 가 성공하면 원격 DB 접속 가능.

### 3.2 로컬 DB 전체 덤프 (Custom Format)

**로컬 DB URL**: 기본값 `postgresql://postgres:lahom@localhost/furniture_orders` (비밀번호/포트 다르면 해당 값으로 교체.)

```powershell
$LocalDbUrl = "postgresql://postgres:lahom@localhost/furniture_orders"
$DumpPath = ".\foms.dump"
pg_dump -Fc --no-owner --no-privileges -f $DumpPath $LocalDbUrl
```

- `-Fc`: custom format → `pg_restore` 전용, 압축·선택 복원 가능.
- `--no-owner --no-privileges`: 원격 DB 사용자/권한과 무관하게 데이터·스키마만 복원.
- **public + wdcalculator** 스키마 모두 한 번에 덤프됨 (스키마 제한 없음).

### 3.3 원격 DB 초기화 + 로컬 덤프로 완전 복원

복원 시 `--clean --if-exists` 로 **기존 원격 객체를 제거**한 뒤 덤프 내용으로 채우므로, **원격 초기화와 동시에 로컬과 동일한 상태**가 됨.

**방법 A — Railway CLI로 DATABASE_URL 자동 주입 (PowerShell):**

```powershell
railway run powershell -NoProfile -Command "pg_restore --clean --if-exists --no-owner --no-privileges -d $env:DATABASE_URL .\foms.dump"
```

**방법 B — Railway 대시보드에서 공개(Public) Connection URL 복사 후 직접 실행 (로컬에서 권장):**

로컬 PC에서는 Railway 내부 호스트(`postgres.railway.internal`)가 이름 해석되지 않으므로, **반드시 공개 URL**을 사용해야 합니다.

1. Railway 대시보드 → 해당 프로젝트 → **Postgres** → **Connect** → **Postgres Connection URL** 복사 (Public, `roundhouse.proxy.rlwy.net` 등).
2. `postgres://` 이면 `postgresql://` 로 바꿔서 사용.

```powershell
# 대시보드 Connect 탭에서 복사한 Postgres Connection URL 전체(비밀번호 포함)를 붙여넣기
$RemoteUrl = "postgresql://postgres:...@roundhouse.proxy.rlwy.net:12345/railway"
pg_restore --clean --if-exists --no-owner --no-privileges -d $RemoteUrl .\foms.dump
```

- 일부 “role does not exist” 경고는 무시 가능 (--no-owner 사용 시 흔함).
- **치명적 에러**가 없으면 복원 성공.
- 스크립트 사용 시에는 위 URL을 `$env:RAILWAY_PUBLIC_DATABASE_URL` 에 설정하면 복원·bootstrap 모두 이 URL로 실행됩니다.

### 3.4 복원 후 보정 (시퀀스·스키마)

```powershell
railway run python railway_bootstrap.py
```

- `wdcalculator` 스키마 존재 확인 및 테이블 생성, 시퀀스 보정 등.
- 이미 덤프에 스키마·데이터가 있으면 보완만 함.

### 3.5 검증 (선택)

- Railway 앱 URL 접속 → 로그인 → 주문 목록/상세에서 로컬과 동일한 건수·상태 확인.
- 채팅방·견적(WDCalculator) 등 기타 데이터가 원격에서 정상 노출되는지 확인.

---

## 4. 요약 체크리스트

| # | 단계 | 명령/확인 |
|---|------|-----------|
| 1 | 원격 연결 | `railway link` → `railway run python check_db_connection.py` |
| 2 | 로컬 덤프 | `pg_dump -Fc --no-owner --no-privileges -f .\foms.dump "postgresql://postgres:lahom@localhost/furniture_orders"` |
| 3 | 원격 초기화+복원 | `railway run powershell ... pg_restore --clean --if-exists ... -d $env:DATABASE_URL .\foms.dump` 또는 방법 B |
| 4 | 보정 | `railway run python railway_bootstrap.py` |
| 5 | 검증 | 원격 앱에서 주문·상태·기타 데이터 확인 |

---

## 5. 주의사항

- **로컬 DB 보호**: 로컬 Postgres는 **절대 삭제·초기화하지 않음**. 이 절차는 로컬에 대해 `pg_dump`(읽기)만 수행하고, `pg_restore --clean` 은 Railway 원격 DB에만 적용한다.
- **덤프 파일**: `foms.dump` 에 로컬 DB 전체가 들어 있으므로 외부 유출되지 않도록 관리. `.gitignore` 에 `foms.dump` 추가 권장.
- **원격 쓰기 중지**: 복원 전후 잠시 원격 앱에서 신규 주문/채팅 등 쓰기를 줄이면, 복원 결과와 검증이 일치하기 쉬움.
- **환경 구분**: staging / production 각각 `railway link` 로 대상 프로젝트·환경을 바꾼 뒤 위 절차를 반복하면, 해당 원격만 로컬과 동일하게 맞출 수 있음.

---

## 6. 스크립트 실행 (Windows)

프로젝트 루트에서 한 번에 실행하려면:

```powershell
.\scripts\sync_local_to_railway.ps1
```

- 로컬 DB URL을 바꾸려면 실행 전 `$env:LOCAL_DATABASE_URL = "postgresql://..."` 설정.
- `railway link` 로 복사할 대상 Railway 프로젝트/환경을 먼저 연결할 것.

---

## 7. 참조

- Grand Develop Master: `.cursor/agents/grand-develop-master.md` (백업/복원 검증, 원격 FOMS 동작 확인)
- 백업/복원 검증: `docs/evolution/BACKUP_RESTORE_VERIFICATION.md`
- Railway 마이그레이션: `MIGRATION_RAILWAY_R2.md`, `MIGRATION_GUIDE_RAILWAY.md`

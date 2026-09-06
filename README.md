# FOMS — 가구 주문 관리 시스템

가구 주문을 접수부터 시공·AS 까지 관리하는 웹 기반 ERP 다.

- **스택**: Flask + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **배포**: Railway (Web / Worker / Cloudflare R2), 브랜치 `deploy`(스테이징) → `production`(운영)
- **워크플로**: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED

## 처음 여는 사람에게 (5분 부팅)

아래 절차는 **빈 클론에서 그대로 도는 것만** 적었다. 여기 적힌 명령이 안 돌면 README 가 틀린
것이므로 고쳐야 한다 — `tests/harness/test_canonical_doc_paths.py` 가 이 문서의 백틱 경로가
실제로 존재하는지 매 CI 마다 확인한다.

### 1. 의존 설치

```
pip install -r requirements.txt
```

파이썬은 3.12 기준이다(`Dockerfile` · `.github/workflows/ci.yml`).

### 2. PostgreSQL 준비

로컬에 데이터베이스를 하나 만든다. 이름은 무엇이든 좋고 아래 `DATABASE_URL` 에 그 이름을 쓴다.

```sql
CREATE DATABASE furniture_orders;
```

### 3. 환경 변수

접속 정보는 **`DATABASE_URL` 하나**로 준다(옛 `DB_USER`/`DB_PASS` 4종 분리 방식은 더 이상 쓰지
않는다). 키 이름 전체 목록은 `.env.example` 에 있다 — 값 없이 이름만 들어 있으니 복사해서 채운다.

```
DATABASE_URL=postgresql+psycopg2://postgres:비밀번호@localhost/furniture_orders
SECRET_KEY=아무-긴-임의-문자열
FLASK_ENV=development
```

Windows PowerShell 이면 `$env:DATABASE_URL = "..."`, bash 면 `export DATABASE_URL="..."`.

### 4. 스키마 생성

```
alembic upgrade head
```

`migrations/env.py` 가 `DATABASE_URL` 을 읽어 `alembic.ini` 의 값을 덮어쓴다. 즉 3번에서 준
접속 정보가 그대로 쓰인다.

### 5. 앱이 뜨는지 확인

```
python -c "import app; print('APP_OK')"
```

`APP_OK` 가 찍히면 부팅 의존(모델·블루프린트·매니페스트)이 전부 맞물린 것이다. 이 문자열이
이 저장소의 표준 성공 신호다(`AGENTS.md` · `CLAUDE.md`).

### 6. 개발 서버 실행

```
python run.py
```

포트를 바꾸려면 `PORT=5001 python run.py`.

### 7. 하네스 계약이 도는지 확인

테스트는 **자기 레인(SQLite)에서 돈다**. 3번에서 준 PostgreSQL `DATABASE_URL` 을 그대로 두고
돌리면 `tests/postgres_guard.py` 가 세션을 막는다 — 테스트가 운영/개발 DB 에 붙어 truncate·
reset 하는 사고를 코드로 차단하기 때문이다. 그러니 이 명령 하나만 DB 주소를 바꿔 준다.

```
DATABASE_URL=sqlite:///:memory: python -m pytest tests/harness -q
```

Windows PowerShell 이면 `$env:DATABASE_URL = "sqlite:///:memory:"` 로 바꾼 뒤 실행하고,
끝나면 3번 값으로 되돌린다. CI 도 같은 값을 쓴다(`.github/workflows/harness-ci.yml`).

이 레인은 문서·정본 경로·인벤토리 계약을 본다. 469개가 초록이면 클론 상태가 정상이다.
5분쯤 걸린다.

> 인코딩: Windows 콘솔에서 한글 출력이 깨지면 `PYTHONIOENCODING=utf-8` 을 앞에 붙인다.

## 다음에 읽을 것

| 문서 | 무엇 |
|---|---|
| `AGENTS.md` | 공통 정책 SSOT — 문제 수정 정책 · 성능 가드 · git 승격 절차 |
| `CLAUDE.md` | Claude Code 세션 규칙(작업 등급 마커 · 하네스 배선) |
| `docs/AI_STATUS.md` | 지금 무슨 일이 진행 중인지 (상단 40줄이 요약) |
| `docs/AI_CHANGELOG.md` | 작업 기록 |
| `docs/guides/SYSTEM_DOCUMENTATION.md` | 시스템 상세 |
| `docs/harness/policy/DECISIONS.md` | 기술 결정 기록 |
| `docs/incidents/` | 사고 원장 — 같은 실패를 두 번 하지 않기 위한 기록 |

## 저장소 구조

```
app.py                 Flask 앱 초기화(최소화 — 라우트 추가 금지)
run.py                 서버 기동 스크립트
db.py                  엔진·세션
models.py              DB 모델
foms/api/              JSON API 블루프린트
foms/web/              페이지 라우트
foms/services/         비즈니스 로직·정책 엔진
foms/platform/         앱 팩토리·HTTP 계층
foms/persistence/      퍼시스턴스 경계
templates/             Jinja2
static/                JS · CSS (CSS SSOT: static/css/foundation/erp-pro.css)
migrations/            Alembic
tests/                 계약·도메인·하네스 테스트
tools/                 운영·하네스 도구
scripts/ops/           배포 전 게이트
```

계층 방향은 문서가 아니라 테스트가 지킨다 —
`tests/contracts/runtime/test_layer_dependency_ratchet.py` 가 금지 방향 import 의 순증을 막는다.
파일 크기도 마찬가지다(`tests/harness/test_file_size_ratchet.py`).

## 배포

운영·스테이징 모두 Railway 다.

- 웹: `start.sh` → `gunicorn ... app:app`
- 워커: `USE_RQ_WORKER=1` 기반 `rq worker` + 백그라운드 루프(`start.sh`)
- 스토리지: Cloudflare R2

push 전에는 `scripts/ops/pre_push_smoke.ps1` 이 exit 0 인지 확인한다. `production` push 와
승격 절차는 `AGENTS.md` 가 정본이다 — 임의로 하지 않는다.

## 첫 계정

처음 실행 시 관리자 계정이 자동 생성된다. **로그인 직후 비밀번호를 반드시 바꾼다.** 기본값을
그대로 두면 계정이 그대로 공개된 것과 같다.

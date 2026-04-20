# Phase 1 Baseline Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/plans/2026-04-07-phase1-baseline-matrix.md`

- 일시: 2026-04-07 11:06:58
- 브랜치: `deploy`
- 실행자: AI agent
- staging URL: `https://lahom-dev.up.railway.app/`

## 1. 전체 판정
**Verdict: Conditional Go (initial)**

이유:
- 로컬 공통 baseline은 통과했다.
- staging web smoke 필수 항목은 통과했다.
- 다만 worker의 실제 Railway 서비스 상태와 env parity는 이번 세션에서 원격 로그/설정까지 확인하지 못했다.
- 따라서 `Step 2`는 **루트 hygiene 정리만 제한적으로 진행 가능**하고, boot/runtime/persistence/harness 계약 파일은 계속 동결해야 한다.

## 2. Local Baseline
### 2.1 `APP_OK`
- 결과: 통과
- 실행: `python -c "import app; print('APP_OK')"`
- 요약: Flask 앱 import 성공, `APP_OK` 출력 확인

관찰 사항:
- 개발용 `SECRET_KEY` 경고 존재
- 로컬 `REDIS_URL` 미설정 경고 존재
- 로컬에서는 Socket.IO가 memory/threading mode로 동작
- main DB / WDCalculator 테이블 auto-init 메시지 확인

해석:
- import contract 자체는 살아 있다.
- 하지만 로컬은 production parity 환경이 아니다.

### 2.2 `verify_result.py --json`
- 결과: 통과
- 실행: `python tools/harness/verify_result.py --json`
- 요약: shared verification baseline 성공

관찰 사항:
- Spec 파일을 정상 인식했다.
- verification checklist 추출도 정상이다.

### 2.3 `pytest`
- 결과: 통과
- 실행: `python -m pytest -q`
- 결과 요약: `159 passed, 3 warnings in 23.60s`

관찰 사항:
- 실패 테스트는 없었다.
- SQLAlchemy `Query.get()` 관련 `LegacyAPIWarning` 3건 존재

해석:
- baseline test health는 양호하다.
- 다만 향후 구조 개편과 별도로 SQLAlchemy legacy API 정리는 백로그로 관리할 가치가 있다.

### 2.4 `git status`
- 결과: dirty worktree
- 실행: `git branch --show-current; git status --short`

요약:
- 기존 문서 변경 이력이 남아 있다.
- 이번 세션에서 추가한 baseline 문서와 spec 문서도 working tree에 있다.

판정:
- dirty 자체가 즉시 No-Go는 아니다.
- 단, Step 2부터는 "루트 hygiene와 무관한 변경"을 섞지 않도록 범위를 엄격히 고정해야 한다.

## 3. Web Smoke
### 3.1 배포 계약 확인
다음 계약은 코드 기준으로 유지되고 있다.

- `railway.toml` -> `sh start.sh`
- `start.sh` -> web 기본 경로는 `gunicorn ... app:app`
- `start.sh` -> worker 경로는 `USE_RQ_WORKER=1`일 때 `rq worker default --url "$REDIS_URL"`
- `Procfile` -> `web` / `worker` 프로세스 정의 존재

### 3.2 위험 관찰
- `start.sh`에 `alembic upgrade head || echo "Migration failed, continuing anyway..."`가 존재한다.

해석:
- 현재 baseline의 즉시 차단 사유는 아니지만, migration fail-open은 운영 안정성 관점에서 명백한 관리 포인트다.
- 구조 개편 Step 2 이전에 손대지는 않더라도, 이후 고위험 단계에서는 별도 통제가 필요하다.

## 4. Staging Smoke
### 4.1 접속 결과
- 결과: 통과
- staging는 로그인 페이지로 정상 진입했다.
- 최종 확인 URL: `https://lahom-dev.up.railway.app/login?next=/`

### 4.2 UI 확인
- 결과: 통과
- 확인 내용:
  - 로그인 폼 렌더링
  - 사용자명(ID) 입력창 노출
  - 비밀번호 입력창 노출
  - 로그인 버튼 노출 및 사용 가능 상태
  - 상단 로그인/회원가입 링크 노출

### 4.3 Console 확인
- 결과: 통과
- 치명적인 앱 JS 오류는 보이지 않았다.
- 브라우저 도구 자체의 non-blocking dialog 경고만 관찰되었다.

### 4.4 Network 확인
- 결과: 통과
- 주요 정적 자산이 모두 `200`으로 확인되었다.

확인 자산 예:
- Bootstrap CSS/JS
- Flatpickr CSS/JS
- Font Awesome CSS
- `static/js/script.js`
- `static/js/upload-progress.js`
- `static/css/style-pro-max.css`
- `static/css/erp-pro.css`

### 4.5 미수행 항목
- 테스트 계정 미제공으로 인증 후 핵심 읽기/쓰기 플로우는 미수행

해석:
- staging web runtime의 최소 생존성은 확인되었다.
- 인증 후 핵심 업무 플로우 검증은 별도 계정 제공 시 추가 수행 필요

## 5. Worker Smoke
### 5.1 확인된 것
- worker 계약 자체는 코드/배포 설정에 존재한다.
- `start.sh`, `Procfile` 모두 worker 경로를 정의한다.

### 5.2 이번 세션에서 확인 못 한 것
- Railway에 실제 worker 서비스가 떠 있는지
- worker 로그에 치명 오류가 없는지
- 실제 `REDIS_URL` env parity가 staging web/worker에 동일하게 들어가는지
- 큐 작업이 실제 소비되는지

### 5.3 판정
- **미완료**
- 이번 baseline의 Conditional Go 사유 중 핵심 하나다.

## 6. Go / No-Go 근거
### Go로 보지 않은 이유
- worker 실제 상태를 원격에서 확인하지 못했다.
- 로컬 `REDIS_URL` 부재로 multi-worker parity를 검증할 수 없다.
- 로컬 Windows 환경에서는 production gunicorn 경로를 직접 신뢰하기 어렵다.

### No-Go로 보지 않은 이유
- `APP_OK` 통과
- `verify_result.py --json` 통과
- `pytest` 전부 통과
- staging 로그인 페이지와 정적 자산 로딩 정상
- web runtime 최소 smoke는 양호

## 7. 결론
현재 저장소는 **구조 개편 Step 2의 저위험 루트 hygiene 정리**에는 들어갈 수 있다.

단, 다음 제한을 유지해야 한다:
- `app.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `db.py`
- `models.py`
- `wdcalculator_*`
- `migrations/`
- `tools/harness/*`
- `.cursor/hooks.json`
- `tests/harness/*`
- `templates/`
- `static/`

즉, 다음 단계는 **루트의 로그/dump/scratch/generated/inventory 정리만** 허용하고, runtime 계약 파일은 건드리지 않는다.

## 8. 다음 단계
1. `Step 2` 범위를 루트 hygiene 전용으로 잠근다.
2. 삭제/이동 후보 inventory를 만든다.
3. 각 후보가 import/runtime/deploy에서 참조되지 않는지 확인한다.
4. hygiene 정리 후 같은 staging smoke를 다시 실행한다.

## 9. 2026-04-07 후속 worker 검증
### 9.1 Railway project 기준
- 대상 프로젝트: `FOMS-DEV`
- 대상 환경: `production`
- 서비스 상태:
  - `FOMS`: `SUCCESS`
  - `worker`: `SUCCESS`
  - `Redis`: `SUCCESS`
  - `Postgres`: `SUCCESS`

### 9.2 worker smoke 결과
- 결과: **기본 smoke 통과**

확인 내용:
- Railway에 `worker` 서비스가 실제로 존재한다.
- `worker` 최근 로그에서 `Listening on default...` 확인
- `worker` 부팅 로그에 즉시 치명 오류 없음
- `DATABASE_URL` web/worker parity 확인
- `REDIS_URL` web/worker parity 확인
- `USE_RQ_WORKER`는 web=`0`, worker=`1`로 역할 분리 확인

### 9.3 해석
- 초기 `Conditional Go`의 핵심 사유였던 "worker 실제 상태/env parity 미검증"은 해소되었다.
- 다만 이 후속 검증은 **큐 작업 실소비 1건**까지는 포함하지 않는다.
- 따라서 worker 기본 smoke는 통과했지만, 구조 개편 다음 단계 판단은 여전히 `Step 2` 잔여(`app_startup.log`) 종료 여부와 별도로 관리한다.

# Step 2 Batch 2 Run Record
> 작성일: 2026-04-07
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 실행 inventory: `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`

- 일시: 2026-04-07 11:41:14
- 브랜치: `deploy`
- 실행자: AI agent
- staging URL: `https://lahom-dev.up.railway.app/`

## 1. 전체 판정
**Verdict: Batch 2 executed, no regression detected within executed smoke scope**

이유:
- tracked 산출물/로그 8건만 제거했다.
- 앱 코드, 배포 계약, DB/migration, harness 계약 파일은 건드리지 않았다.
- 정리 후 `APP_OK`, `verify_result.py --json`, `pytest -q`, staging 로그인 페이지 smoke를 다시 통과했다.
- 다만 `app_startup.log`는 Batch 1에서 남은 로컬 예외로 계속 존재한다.

## 2. 실제 실행 범위
### 2.1 삭제한 tracked 산출물
- `(noop)`
- `all_changes.txt`
- `all_js_changes.txt`
- `all_templates_changes.txt`
- `db_check_log.txt`
- `migration_error.txt`
- `migration_log.txt`
- `head_erp_scripts_core.html`

해석:
- 모두 root hygiene 정책에 어긋나지만 runtime contract에는 속하지 않는 tracked 산출물/로그였다.
- `head_erp_scripts_core.html`는 실행 전 내용 확인을 했고, 독립적인 HTML/JS fragment이며 repo 참조가 없는 상태로 판단했다.

### 2.2 의도적으로 건드리지 않은 것
- `app.py`
- `start.sh`
- `Procfile`
- `railway.toml`
- `Dockerfile`
- `db.py`
- `models.py`
- `wdcalculator_*`
- `migrations/`
- `templates/`
- `static/`
- `tools/harness/*`
- `tests/harness/*`

## 3. 실행 전 감리 메모
- `Step 3` 이상의 구조 변경은 아직 금지 상태로 유지했다.
- 로컬에서 `python app.py` 프로세스가 관찰되어 `app_startup.log` 후속 정리는 사용자 실행 흐름을 건드릴 수 있어 이번 배치에 포함하지 않았다.
- worker/env parity는 실행 당시 Phase 1 `Conditional Go`의 잔여 리스크였으므로, 이번 배치 범위는 hygiene/tracked cleanup으로만 제한했다.

## 4. 재검증 결과
### 4.1 `APP_OK`
- 결과: 통과
- 실행: `python -c "import app; print('APP_OK')"`

관찰 사항:
- 개발용 `SECRET_KEY` 경고 지속
- 로컬 `REDIS_URL` 미설정 경고 지속
- DB auto-init 메시지 정상 출력

### 4.2 `verify_result.py --json`
- 결과: 통과
- 실행: `python tools/harness/verify_result.py --json`

### 4.3 `pytest`
- 결과: 통과
- 실행: `python -m pytest -q`
- 결과 요약: `159 passed, 3 warnings in 22.06s`

관찰 사항:
- SQLAlchemy `Query.get()` legacy warning 3건은 계속 남아 있다.

### 4.4 staging login page smoke
- 결과: 통과
- 최종 URL: `https://lahom-dev.up.railway.app/login?next=/`

확인 내용:
- 로그인 페이지 정상 렌더링
- 사용자명 / 비밀번호 입력창 노출
- 로그인 버튼 노출
- console 치명 오류 없음
- 주요 CSS/JS 자산 `200` 응답 확인

범위 밖:
- 자격 증명 제출 성공
- 세션 쿠키 발급/유지
- 인증 후 업무 플로우

확인 자산 예:
- `static/js/script.js`
- `static/js/upload-progress.js`
- `static/css/style-pro-max.css`
- `static/css/erp-pro.css`

## 5. 남은 리스크 / 미완 항목
### 5.1 `app_startup.log`
- 상태: 미삭제 (`python app.py -> run.py` active dev startup log)
- 사유: 로컬 dev startup 경로가 `logging.FileHandler('app_startup.log')`를 유지하며 파일 핸들 점유 지속

해석:
- deploy/runtime blocker는 아니다.
- 다만 현재 삭제는 local workspace hygiene 정리일 뿐이며, 같은 dev startup 경로를 계속 쓰면 다음 로컬 기동에서 다시 생성된다.
- 즉 root `*.log` 금지 기준의 구조적 정합은 `run.py` 로그 경로/정책 후속 판단이 있어야 닫힌다.

### 5.2 worker smoke
- 상태: 기본 smoke 통과 (후속 확인)
- 사유: `FOMS-DEV` 프로젝트에서 `worker` 서비스 `SUCCESS`, `Listening on default...` 로그, `DATABASE_URL`/`REDIS_URL` parity, `USE_RQ_WORKER` 역할 분리를 후속 확인했다.

해석:
- Phase 1 matrix의 worker 최소 체크는 충족했다.
- 다만 큐 작업 실소비 1건은 아직 확인하지 않았으므로, 더 강한 운영 확신이 필요하면 추가 smoke를 별도로 수행할 수 있다.

## 6. 결론
현재 저장소는 `Step 2` 안에서 계획된 **tracked artifact cleanup**까지 수행했고, 그 결과도 baseline/staging smoke 기준으로 안전하게 유지되었다.

다만 다음 두 가지는 여전히 남아 있다:
- `app_startup.log` 로컬 정리와 dev startup 로그 경로 정책 정렬
- `Step 2` 종료 전 `Step 3` 금지 유지

## 7. 다음 단계
1. 사용자 로컬 실행을 건드리지 않는 시점에 `python app.py` / reloader 점유를 해제한 뒤 `app_startup.log`를 로컬 삭제
2. 별도 후속으로 `run.py` dev startup 로그 경로/정책을 루트 `*.log` 금지 기준과 맞출지 결정
3. 현재 Step 2 산출물과 삭제 diff를 하나의 논리 배치로 검토
4. 필요 시 큐 작업 실소비 1건을 추가 smoke로 확인하되, 구조 변경 판단 기준은 우선 `Step 2` 잔여 정의를 어떻게 닫을지에 맞춰 관리

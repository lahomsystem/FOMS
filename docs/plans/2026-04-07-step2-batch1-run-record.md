# Step 2 Batch 1 Run Record
> 작성일: 2026-04-07
> 상태: 완료(예외 1건 기록)
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 실행 inventory: `docs/plans/2026-04-07-step2-root-hygiene-inventory.md`

- 일시: 2026-04-07 11:30:03
- 브랜치: `deploy`
- 실행자: AI agent
- staging URL: `https://lahom-dev.up.railway.app/`

## 1. 전체 판정
**Verdict: Batch 1 executed, with one blocked local artifact**

이유:
- 사용자 진행 지시를 반영해 실행 전 거버넌스 스펙 메타데이터를 `승인됨`으로 정합화했다.
- 루트 `.pytest_cache`와 루트 `__pycache__`의 생성 파일은 정리했다.
- 정리 후 `APP_OK`, `verify_result.py --json`, `pytest -q`, staging 로그인 smoke를 다시 통과했다.
- 다만 `app_startup.log`는 현재 다른 프로세스가 파일 핸들을 점유하고 있어 삭제하지 못했다.

## 2. 실제 실행 범위
### 2.1 문서 정합성
- `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
  - 상태: `🟡 승인대기` -> `🟢 승인됨`

해석:
- 사용자 진행 지시를 반영해 스펙 메타데이터를 승인 상태로 정합화했다.
- 이 변경은 실행 승인 사실을 문서 메타데이터와 맞춘 것이며, 실제 작업 범위는 계속 Step Gate 기준으로 제한된다.

### 2.2 루트 생성물 정리
- 정리 성공:
  - 루트 `.pytest_cache` 내부 생성 파일
  - 루트 `__pycache__` 내부 생성 `.pyc` 파일
- 정리 실패:
  - `app_startup.log`

실행 메모:
- 검증 과정에서 cache 파일이 일부 다시 생성되어, 검증 후 한 번 더 제거했다.
- 현재 `.pytest_cache`, `__pycache__`는 빈 디렉터리 뼈대만 남을 수 있다.

## 3. 예외 / 차단 사항
### 3.1 `app_startup.log`
- 결과: 미정리
- 사유: `File is busy`

해석:
- 이 파일은 local log artifact로 분류되며 runtime 계약 파일은 아니다.
- 따라서 코드/배포 안정성의 blocker는 아니지만, **물리적 root cleanup 완료**라고는 부를 수 없다.

권고:
- 해당 로그를 점유 중인 로컬 프로세스를 먼저 식별/정지한 뒤 별도 후속 정리로 제거한다.

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

해석:
- shared verification baseline은 유지된다.

### 4.3 `pytest`
- 결과: 통과
- 실행: `python -m pytest -q`
- 결과 요약: `159 passed, 3 warnings in 23.70s`

관찰 사항:
- SQLAlchemy `Query.get()` legacy warning 3건은 지속된다.

### 4.4 staging login smoke
- 결과: 통과
- 최종 URL: `https://lahom-dev.up.railway.app/login?next=/`

확인 내용:
- 로그인 페이지 정상 렌더링
- 사용자명 / 비밀번호 입력창 노출
- 로그인 버튼 노출
- console 치명 오류 없음
- 주요 CSS/JS 자산 `200` 응답 확인

확인 자산 예:
- `static/js/script.js`
- `static/js/upload-progress.js`
- `static/css/style-pro-max.css`
- `static/css/erp-pro.css`

## 5. 감리 결론
이번 실행으로 **Batch 1 범위 내 목적은 달성**되었다. 다만 `Step 2` 전체 완료는 아니다.

다만 엄밀하게는 다음 두 가지가 남아 있다:
- `app_startup.log` 물리 삭제
- 빈 cache 디렉터리 자체 제거 여부 결정

정책 해석:
- Spec §2.6의 루트 `*.log` 금지 기준 대비 현재는 `app_startup.log` 1건이 예외로 남아 있으므로, Step 2 전체 완료가 아니라 **부분 충족** 상태다.

따라서 현재 상태를 다음처럼 해석한다:
- **구조 안정성 / baseline 안전성 기준:** 통과
- **root artifact 완전 제거 기준:** 예외 1건 남음

## 6. 다음 단계
1. 원하면 `app_startup.log` 점유 프로세스 확인 후 후속 정리
2. 그 다음 단계는 `tracked artifact cleanup` 후보를 별도 PR/배치로 감리 후 실행
3. boot/runtime/deploy/DB/harness 계약 파일은 계속 동결 유지

# app_init Bootstrap Hardening Spec
> 작성일: 2026-04-11 | 상태: 🟢 승인됨

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
`foms/services/app_init.py`의 WSGI startup bootstrap 경로에서 더 이상 하드코딩된 기본 관리자 비밀번호를 사용하거나 로그에 자격 증명을 노출하지 않도록 정리한다. 자동 admin 생성은 명시적 환경변수 `FOMS_ADMIN_DEFAULT_PASSWORD`가 있을 때만 수행한다.

### 1.2 기능 요구사항
1. `run_auto_init()`의 admin bootstrap 경로는 하드코딩 문자열 `admin1234`를 직접 사용하지 않는다.
2. admin 계정이 없을 때 자동 생성은 `FOMS_ADMIN_DEFAULT_PASSWORD`가 설정된 경우에만 수행한다.
3. admin bootstrap 관련 로그는 사용자명/비밀번호 조합을 평문으로 출력하지 않는다.
4. 기존 public contract인 `foms.services.app_init.run_auto_init` / root `app.py` bootstrap import contract는 유지한다.
5. 수동 스크립트(`scripts/ops/db_admin.py`, `scripts/ops/railway_reset_admin.py`)의 정책 변경은 이번 배치에 섞지 않는다.

### 1.3 예외/제약 조건
- 빈 문자열 또는 공백만 있는 `FOMS_ADMIN_DEFAULT_PASSWORD`는 미설정으로 취급한다.
- `app_init.py`의 다른 bootstrap 블록(DB init, index, listener, backfill)은 이번 배치에서 변경하지 않는다.
- 광범위한 logging 프레임워크 전환은 하지 않고, credential 노출 제거에 필요한 최소 수정만 한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `foms/services/app_init.py` | admin bootstrap 로직을 private helper로 추출하고 env-gated 안전 경로로 교체 |
| `tests/test_app_init.py` | env 기반 bootstrap/skip/log sanitization focused test 추가 |
| `docs/specs/2026-04-11-app-init-bootstrap-hardening_SPEC.md` | 이번 품질 배치의 승인된 범위를 기록 |
| `docs/ARCHIVE_INDEX.md` | 신규 spec 문서 인덱스 추가 |

### 2.2 아키텍처 방향
- 기존 `run_auto_init()` public entry는 유지하고, admin 생성 부분만 private helper로 분리한다.
- 수동 admin 스크립트의 env 이름(`FOMS_ADMIN_DEFAULT_PASSWORD`)과 정렬하되, WSGI auto-init 경로는 더 엄격하게 env 명시를 요구한다.
- 참고 패턴: `scripts/ops/db_admin.py`의 `_default_admin_password()`

### 2.3 의존성 및 영향 범위
- 영향 범위:
  - root `app.py` import bootstrap
  - `services/app_init.py` shim
  - 빈 DB 첫 기동 시 admin bootstrap behavior
- DB 마이그레이션: 없음
- 외부 API/route 변경: 없음

## 3. Steps — 실행 단계
- [ ] Step 1: `app_init.py`에 env 해석 helper와 안전한 admin bootstrap helper를 도입한다.
- [ ] Step 2: `run_auto_init()`가 새 helper를 사용하도록 바꾸고 credential 노출 로그를 제거한다.
- [ ] Step 3: env 있음/없음/기존 admin 존재 케이스를 검증하는 focused test를 추가한다.
- [ ] Step 4: import contract 및 app bootstrap smoke를 재검증한다.

## 4. 검증 기준
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python -m pytest tests/test_app_bootstrap_contract.py tests/test_foms_namespace_imports.py tests/test_app_init.py -q` 통과
- [ ] 신규 테스트에서 credential 평문이 로그로 출력되지 않음을 확인
- [ ] 기존 root bootstrap public contract 유지 확인

## 5. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md`
- 관련 상태: `docs/AI_STATUS.md`의 `app_init.py` 알려진 이슈
- 관련 실행 기록:
  - `docs/plans/2026-04-10-step3-batch44-app-init-run-record.md`
  - `docs/plans/2026-04-08-step3-batch18-order-geocode-run-record.md`

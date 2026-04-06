# Harness Tracking Cleanup Spec
> 작성일: 2026-04-06 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
하네스/로컬 작업 중 반복적으로 생기는 불필요 파일 추적을 줄여서, `git status`에 raw hook debug 파일과 scratch 파일, pytest cache, generated browser audit 산출물이 계속 쌓이지 않도록 정리한다.

### 1.2 기능 요구사항
1. 루트의 scratch 파일 `temp_script.js`, `test_scripts.js`, `test.html`은 저장소에서 제거한다.
2. `docs/context/HOOK_RAW_DUMP.txt`, `docs/context/.hook_raw_once`는 git 추적 대상에서 제거하고 `.gitignore` 규칙으로만 관리한다.
3. `.pytest_cache/`는 로컬 전용 캐시로 ignore 처리한다.
4. `docs/analysis/browser_audit_*/` 디렉터리는 generated browser audit 산출물로 보고 ignore 처리한다.
5. `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md`, `docs/context/SESSION_LOG.md`, `docs/context/EDIT_LOG.md`, `docs/context/COMPACT_CHECKPOINT.md`는 현재 컨텍스트 시스템 참조 대상이므로 이번 정리 범위에서 제외한다.

### 1.3 예외/제약 조건
- 컨텍스트 기억 체계에서 읽는 파일은 삭제/추적 해제하지 않는다.
- 분석 문서 전체를 막연히 ignore하지 않고, generated browser audit 폴더 패턴만 좁게 처리한다.
- 기존 런타임/테스트/문서 참조가 없는지 확인한 뒤 제거한다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `.gitignore` | cache/browser audit/scratch ignore 규칙 추가 |
| `docs/specs/2026-04-06-harness-tracking-cleanup_SPEC.md` | cleanup 범위 기록 |
| `docs/context/DECISIONS.md` | 추적 정책 결정 기록 |
| `docs/ARCHIVE_INDEX.md` | spec 인덱싱 |
| `temp_script.js` | 저장소에서 제거 |
| `test_scripts.js` | 저장소에서 제거 |
| `test.html` | 저장소에서 제거 |
| `docs/context/HOOK_RAW_DUMP.txt` | git 추적 해제 |
| `docs/context/.hook_raw_once` | git 추적 해제 |

### 2.2 아키텍처 방향
- 삭제/추적 해제 범위는 기존 참조 검색과 과거 감리 문서를 근거로 좁게 제한한다.
- 하네스 메모리 시스템이 읽는 문서는 유지하고, 순수 generated/debug 산출물만 정리한다.

### 2.3 의존성 및 영향 범위
- DB 영향 없음
- 영향 범위: git hygiene, local harness 운영 경험
- 테스트 런타임 영향 없음

## 3. Steps — 실행 단계
- [x] Step 1: cleanup scope를 spec으로 고정한다.
- [x] Step 2: scratch/debug/generated 산출물에 대한 ignore 규칙을 보강한다.
- [x] Step 3: scratch 파일 삭제와 raw hook debug 파일 git 추적 해제를 수행한다.
- [x] Step 4: 참조 검색과 git 상태로 정리 결과를 검증한다.

## 4. 검증 기준
- [x] `rg "temp_script\\.js|test_scripts\\.js|test\\.html" .` 결과가 런타임 참조를 만들지 않음
- [x] `git status --short` 기준으로 scratch/debug 산출물이 정리 대상대로 반영됨
- [x] `docs/context/HOOK_RAW_DUMP.txt`, `docs/context/.hook_raw_once`가 ignore 정책 아래로 내려감
- [x] `docs/AI_STATUS.md`, `docs/context/SESSION_LOG.md`, `docs/context/EDIT_LOG.md`, `docs/context/COMPACT_CHECKPOINT.md`는 유지됨

## 5. 참고 자료
- 관련 결정: `docs/context/DECISIONS.md`
- 관련 감리: `docs/evolution/GDM_DELETION_AUDIT_2026-03-15.md`

# Repo Surface Cleanup Execution Plan
> 작성일: 2026-04-16 | 상태: 🟢 승인됨

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
- FOMS 저장소의 비제품 표면적을 안전하게 줄이기 위한 cleanup runbook
- `삭제 / 보관-재분류 / 유지` 3등급 기준이 잠긴 상태
- 다음 LLM이나 운영자가 바로 실행할 수 있는 batch order와 검증 기준

### 1.2 기능 요구사항
1. stale generator path 때문에 생기는 old-path 산출물을 canonical 경로로 수렴시킨다.
2. tracked temp/result 파일 중 참조 0이고 대체 경로가 있는 파일만 제거한다.
3. runtime residue는 workspace cleanup 대상으로만 다루고, active local operator input은 삭제 대상으로 오인하지 않는다.
4. one-off 문서, low-ref 계획 문서, vendored skills, backups는 blind delete하지 않고 보관/재분류 tranche로 분리한다.
5. "불필요한 테스트 파일"은 실제 참조 근거가 없을 때만 후보로 올리고, 현재 조사 결과에선 삭제 batch를 열지 않는다.

### 1.3 예외/제약 조건
- root cause fix only. old-path 파일을 지우기 전에 생성 경로부터 바로잡는다.
- `DECISIONS.md`가 유지로 고정한 context memory/runtime state 문서는 삭제하지 않는다.
- `tests/support/**/*.js`, `tests/domains/test_foms_namespace_imports.py`는 이번 cleanup 범위에서 제외한다.
- local secrets/operator input(`session_cookies.txt`, `loadtest_users.txt`)은 repo truth가 아니더라도 blanket delete 금지다.
- vendored skills / backups / manual-artifacts는 별도 retention policy 없이는 삭제하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 기준 문서
- `docs/context/analysis/2026-04-16-repo-surface-cleanup-triage.md`
- `docs/harness/policy/DECISIONS.md`
- `docs/ARCHIVE_INDEX.md`

### 2.2 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `.claude/hooks/guard_shell.py` | `docs/context/SHELL_GUARD_LOG.md` old-path 기록을 canonical `docs/harness/logs/SHELL_GUARD_LOG.md`로 정렬 |
| `docs/context/SHELL_GUARD_LOG.md` | stale generated file 제거 |
| `tools/research_center/.tmp_sources_pretty.json` | tracked temp 파일 제거 |
| `tests/harness/load/final_soak_summary.json` | tracked one-off result 제거 |
| `tests/harness/load/final_soak_summary.txt` | tracked one-off result 제거 |
| `docs/context/2026-04-16-project-delta-analysis-eb01c5d7-to-4c3aaffb.md` | archive-class 이동 또는 retire 여부 결정 |
| `docs/ARCHIVE_INDEX.md` | triage/cleanup plan 및 archive-class 이동 결과 반영 |
| 관련 계획/가이드 문서 | `COMPACT_CHECKPOINT`, low-ref 계획 문서, vendored skill/backups retention policy 결정이 내려질 경우 canonical pointer 정리 |

### 2.3 아키텍처 방향
- 제품 코드가 아니라 "repo surface governance"를 다룬다.
- 삭제 기준은 `참조 0 + canonical 대체 존재 + 생성 경로 확인`을 모두 만족해야 한다.
- ambiguous 항목은 삭제가 아니라 `archive/reclassify` lane으로 보낸다.

### 2.4 배치 순서
- `RSC-B1` stale shell guard path canonicalization
- `RSC-B2` tracked temp/result retirement
- `RSC-B3` workspace residue hygiene reinforcement
- `RSC-B4` one-off doc archive/reclassification
- `RSC-B5` `COMPACT_CHECKPOINT` ownership reconciliation
- `RSC-B6` low-ref plans / vendored skills / backups retention policy

## 3. Steps — 실행 단계
- [ ] `RSC-B1`: `.claude/hooks/guard_shell.py`를 canonical harness log 경로로 수정하고 `docs/context/SHELL_GUARD_LOG.md` 재생성 여부를 차단한다.
- [ ] `RSC-B2`: `.tmp_sources_pretty.json`, `final_soak_summary.json`, `final_soak_summary.txt`를 제거하고 참조 검색으로 0-reference를 재확인한다.
- [ ] `RSC-B3`: workspace cleanup 스크립트/운영 규칙으로 `.pytest_cache`, `__pycache__`, load results, hook runtime residue를 정리한다.
- [ ] `RSC-B4`: `2026-04-16-project-delta-analysis...` 같은 one-off 분석 문서를 `analysis/` 또는 archive bucket으로 재배치하고 index를 맞춘다.
- [ ] `RSC-B5`: `docs/context/COMPACT_CHECKPOINT.md`와 `docs/harness/runtime/COMPACT_CHECKPOINT.md`의 canonical owner를 결정하고 refs/spec/docs를 동기화한다.
- [ ] `RSC-B6`: early low-ref plan docs, `.cursor/skills/**`, `.agents/skills/gstack/**`, `backups/**`, `manual-artifacts/**`에 대한 retention policy를 별도 문서로 잠그거나 archive tranche를 연다.

## 4. 검증 기준
- [ ] `rg -n "docs/context/SHELL_GUARD_LOG.md" .claude .cursor docs tests tools` 결과가 historical docs를 제외하면 old generator path를 남기지 않는다.
- [ ] `rg -n "final_soak_summary|\\.tmp_sources_pretty" docs tests tools .claude .cursor .agents` 결과가 0건이다.
- [ ] `pytest --collect-only -q`가 기존 collected test 수를 깨지 않는다.
- [ ] `python -c "import app; print('APP_OK')"` 통과
- [ ] `python tools/harness/verify_result.py --json` 통과
- [ ] archive/reclassify 대상은 `ARCHIVE_INDEX.md` 또는 별도 retention 문서에 canonical home이 기록된다.

## 5. Stop Rule
- active test fixture나 context memory 파일을 "커 보여서"만 삭제하려 하면 중단
- local operator input과 runtime residue를 혼동하면 중단
- vendored skills / backups를 retention policy 없이 삭제하려 하면 중단
- old-path generated file를 지우면서 생성 경로는 그대로 두려 하면 중단

## 6. 참고 자료
- 관련 결정: `docs/harness/policy/DECISIONS.md`
- 관련 분석: `docs/context/analysis/2026-04-16-repo-surface-cleanup-triage.md`

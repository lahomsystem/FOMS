# Harness Post-Audit Hardening Spec
> 작성일: 2026-04-05 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
Wave 3 감리에서 드러난 하네스 운영 리스크를 정리하는 후속 하드닝 배치를 만든다.

이 배치는 하네스 코어 스크립트, 검증 도구, 후크, 정책 문서, generated bundle의 정합성을 다시 맞춰서 다음 조건을 만족해야 한다.

- wrapper 실패가 호출자에게 정확한 종료 코드로 전달된다.
- Spec/verify-result/post-task reminder가 결정적이고 구조화된 계약으로 동작한다.
- `AGENTS.md` 기준 RPI 범위가 모든 runner 문서와 bundle에 동일하게 반영된다.
- Cursor/Claude/Codex 번들 사용 문구가 “자동 로딩”처럼 오해되지 않게 정정된다.

### 1.2 기능 요구사항
1. `tools/harness/run_codex.ps1`는 `codex exec` 실패 시 실제 종료 코드를 PowerShell 프로세스 종료 코드로 전달해야 한다.
2. `tools/harness/run_gstack_qa.ps1`도 내부 `run_codex.ps1` 결과 종료 코드를 상위 호출자에게 그대로 전달해야 한다.
3. `tools/harness/run_codex.ps1`의 위험 경로 분류는 `db.py`를 DB 코어 파일로 취급해야 한다.
4. `tools/harness/verify_result.py`는 잘못된 `--spec` 경로가 들어와도 traceback 대신 구조화된 실패 결과(JSON 또는 텍스트)를 출력해야 한다.
5. `tools/harness/spec_utils.py`의 최신 Spec 선택은 `mtime` 단독 의존을 피하고, 동일 입력에서 결정적(deterministic)으로 같은 파일을 선택해야 한다.
6. `.cursor/hooks/post_task_quality_check.py`는 nested spec가 있어도 올바른 `docs/specs/...` 상대 경로를 리마인더에 보여줘야 한다.
7. `CLAUDE.md`, `.cursor/rules/00-project-context.mdc`, `.cursor/agents/grand-develop-master.md`는 `AGENTS.md` 기준의 코어 변경 범위(DB/Auth/API + 배포 인프라 + 하네스 인프라)를 기준으로 RPI 문구를 맞춰야 한다.
8. Cursor/Claude/Codex 관련 문서와 generated bundle은 bundle을 “자동 로딩”처럼 오해하게 만드는 표현을 제거하고, 수동 참조 또는 wrapper 기반 진입점임을 명확히 해야 한다.
9. `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`는 실제 구현/검증 상태와 체크리스트가 일치하도록 갱신해야 한다.
10. CI는 PowerShell 기반 wrapper 테스트가 조용히 skip되지 않도록 PowerShell 가용성을 명시적으로 보장하거나 없을 때 실패하도록 해야 한다.

### 1.3 예외/제약 조건
- 이번 배치는 감리에서 이미 확인한 후속 하드닝만 다룬다. Wave 3 기능 확장이나 새 레벨 정책 추가는 범위 밖이다.
- 로컬 워크스테이션의 Bun 설치/복구 같은 머신 전역 환경 변경은 저장소 수정과 분리해서 다룬다.
- generated bundle은 원문 문서 수정 후 재생성으로만 갱신한다.
- 근본 원인 수정만 허용하며, 종료 코드/Spec 탐색/리마인더 문제를 우회하는 임시 처리 금지.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `tools/harness/run_codex.ps1` | native 종료 코드 전달, `db.py` 코어 경로 분류 추가 |
| `tools/harness/run_gstack_qa.ps1` | wrapper 종료 코드 전달 |
| `tools/harness/verify_result.py` | 잘못된 `--spec`에 대한 구조화된 실패 계약 추가 |
| `tools/harness/spec_utils.py` | 결정적 latest spec 선택 규칙으로 보강 |
| `.cursor/hooks/post_task_quality_check.py` | nested spec 상대 경로 출력 수정 |
| `tests/harness/test_run_codex_levels.py` | CI에서 PowerShell 누락 시 silent skip 방지 계약 보강 |
| `tests/harness/test_verify_result.py` | invalid `--spec` 구조화 실패 테스트 추가 |
| `tests/harness/test_hooks_smoke.py` | nested spec reminder 경로 및 deterministic spec 테스트 보강 |
| `.github/workflows/harness-ci.yml` | PowerShell 가용성 보장/검증 추가 |
| `CLAUDE.md` | RPI 범위/runner wording 정합성 수정 |
| `.cursor/rules/00-project-context.mdc` | RPI 범위/runner wording 정합성 수정 |
| `.cursor/agents/grand-develop-master.md` | RPI wording과 bundle 진입 표현 정합성 수정 |
| `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` | manual reference / wrapper auto-read 표현 보강 |
| `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md` | 세션 시작 예시 wording 보정 |
| `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md` | 구현 완료 상태 및 체크리스트 동기화 |
| `docs/ARCHIVE_INDEX.md` | 본 Spec 인덱싱 |
| `docs/harness/bundles/HARNESS_BUNDLE_*.md` | 원문 변경 반영 재생성 |
| `task_plan.md` / `findings.md` / `progress.md` | 후속 하드닝 추적 |

### 2.2 아키텍처 방향
- wrapper 신뢰성 문제는 상위 호출자가 `PowerShell exit code`만 봐도 실패를 감지할 수 있게 직접 해결한다.
- `verify_result.py`, `spec_utils.py`, post-task hook은 “Spec 선택/표시/검증”을 하나의 일관된 계약으로 맞춘다.
- 문서 정합성은 `AGENTS.md`를 단일 기준선으로 삼고, 다른 문서는 그 기준을 보강만 하도록 수정한다.
- generated bundle은 직접 수동 편집하지 않고 source 문서 수정 후 generator 재실행으로 갱신한다.

### 2.3 의존성 및 영향 범위
- DB 마이그레이션은 필요 없다.
- 직접 영향 범위는 harness wrapper, verification, hook, CI, policy docs, generated bundle이다.
- 간접 영향은 Codex/QA wrapper 신뢰성, Cursor/extension 운영자 혼선 감소, audit 재발 방지이다.

## 3. Steps — 실행 단계
- [x] Step 1: 후속 하드닝 Spec과 planning files를 갱신해 작업 범위를 고정한다.
- [x] Step 2: wrapper 종료 코드 전달과 `db.py` 위험 경로 분류를 구현하고 테스트를 보강한다.
- [x] Step 3: `verify_result.py`, `spec_utils.py`, post-task hook의 Spec 계약을 구조화·결정적으로 수정한다.
- [x] Step 4: RPI 범위/runner wording drift를 `AGENTS.md` 기준으로 동기화하고 Wave 3 spec 상태를 정리한다.
- [x] Step 5: bundle 재생성, harness 검증, 감리 지적 항목 재확인을 수행한다.

## 4. 검증 기준
- [x] `python -m pytest tests/harness -q` 통과
- [x] `python -m compileall -q .cursor/hooks` 통과
- [x] `python tools/harness/verify_result.py --json` 통과
- [x] `python tools/harness/verify_result.py --json --spec "docs/specs/DOES_NOT_EXIST_SPEC.md"` 가 traceback 없이 구조화된 실패를 반환
- [x] `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "tools/harness/build_context_bundle.py" -DryRun` 가 정상 출력되고, 실제 실패 종료 코드 전달 테스트가 별도 harness 테스트/CI 계약으로 보강됨
- [x] `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "db.py" -DryRun` 가 코어 경로 승급 이유를 반영
- [x] post-task hook 테스트가 nested spec에 대해 올바른 `docs/specs/...` 상대 경로를 검증
- [x] generated bundle 재생성 두 번째 실행에서 SHA256 기준 추가 변화가 없음

## 5. 참고 자료
- 관련 결정:
  - `docs/harness/policy/DECISIONS.md` — Wave 3 Codex auto level routing
  - `docs/harness/policy/DECISIONS.md` — Spec 탐색 규칙 단일화
- 관련 설계 계획: `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
- 관련 스펙: `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md`

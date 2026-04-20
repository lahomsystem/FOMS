# Harness Wave 3 Auto Level Routing Spec
> 작성일: 2026-04-05 | 상태: ✅ 완료

## 1. What — 무엇을 만드는가

### 1.1 최종 결과물
사용자 명령을 받아 `하 / 중 / 상 / 최상` 4단계로 자동 분류하고, 그 결과에 따라 하네스 엔지니어링 프로세스 강도와 자원 투입량을 자동 선택하는 래퍼 중심 라우팅 시스템을 만든다.

1차 적용 범위는 `tools/harness/run_codex.ps1` 같은 wrapper entrypoint이며, 위험한 고수준 작업은 더 강한 컨텍스트·검증·자원으로 승격하고, 일상 작업은 slim context와 최소 자원으로 유지해 LLM API 비용을 최적화한다.

### 1.2 기능 요구사항
1. wrapper는 사용자 입력에서 `하 / 중 / 상 / 최상` 레벨을 자동 판정해야 한다.
2. 자동 판정 우선순위는 다음 순서를 따른다.
   - 1순위: 위험도/영향 범위
   - 2순위: 작성/수정 범위
   - 3순위: 검증 강도
3. 위험도/영향 범위는 DB/Auth/API 코어/배포/하네스 코어(Hooks/Rules/Agents/Verification) 변경 여부를 가장 먼저 반영해야 한다.
4. 작성/수정 범위는 단일 지표가 아니라 혼합형으로 판단해야 한다.
   - 수정 파일 수
   - 구조 변경 폭
   - 사용자 기능 면적
5. 검증 강도는 테스트, 브라우저 확인, QA, 감리 필요성을 반영해야 한다.
6. 사용자는 자동 판정 결과를 수동으로 override 할 수 있어야 한다.
   - 자연어 예시: `이번 건 최상으로 진행`
   - 고정 태그 예시: `레벨: 최상`, `[레벨=최상]`
7. 사용자가 고위험 작업을 낮은 레벨로 내리면, AI는 한 번 재확인 질문 후 진행해야 한다.
8. 분류 결과는 사용자에게 짧게 보여줘야 한다.
   - 기본 원칙: 한 줄 reason 포함
   - PowerShell 5 안정성을 위해 wrapper 출력은 ASCII-safe 형식으로 노출해도 된다.
   - 예시: `Level: high (API core change + tests required)`
9. 레벨별 자원 정책은 다음을 따른다.
   - `하`: slim bundle + 직접 작업 + 간단 리뷰
   - `중`: 작업 + 관련 테스트/브라우저 확인 + 리뷰/감리
   - `상`: harness bundle + 강한 검증 + 리서치/문서 조사 포함
   - `최상`: 가능한 모든 자원 가동(병렬 서브에이전트, harness bundle, 리서치, 브라우저 QA, 전체 검증)
10. 승급 규칙은 엄격형으로 적용한다.
   - DB/Auth/API 코어/배포/하네스 코어 변경이면 최소 `상`
   - 브라우저 QA/테스트/감리 필요면 최소 `중`
   - 병렬 에이전트 + 리서치 + 전체 검증이 필요하면 `최상`
11. 자동 판정기는 별도 LLM 선행 호출 없이 wrapper 내부의 결정적(deterministic) 규칙으로 동작해야 한다.
12. 자동 판정 입력은 다음을 사용한다.
   - `-Target`
   - `-Plan`
   - `-Scenario`
   - `-AdditionalPrompt`
   - 필요 시 `Plan` 파일 본문(수정 대상 파일 수, Step 수 등)의 가벼운 로컬 파싱
13. 레벨(label)과 bundle 선택은 1:1로 완전히 같지 않을 수 있다.
   - 기본 원칙: `하/중`은 daily bundle 우선, `상/최상`은 harness bundle 우선
   - 예외 원칙: repeatable QA는 논리 레벨이 `중` 이상이어도 기본 bundle은 daily를 유지하고, 위험도/범위/명시 override가 있을 때만 harness로 승급할 수 있다.
14. `최상`은 `상`과 같은 harness bundle을 쓰더라도 반드시 더 강한 자원 힌트를 추가해야 한다.
   - 예: research 포함, browser QA 포함, full verification, parallel review/agent orchestration 고려

### 1.3 예외/제약 조건
- Wave 3 1차 구현 범위는 wrapper entrypoint 우선이다. Cursor/Claude 전역 자동 판정은 후속 단계로 미룬다.
- 자동 판정은 품질 우선 성향을 가진다. 애매하면 상위 레벨로 승급한다.
- QA wrapper(`run_gstack_qa.ps1`)의 기본 목적은 repeatable QA이므로, Wave 3에서도 기본적으로 daily context를 유지한다. 다만 논리 레벨은 최소 `중` 후보가 될 수 있으며, 위험도/범위/명시 override가 있을 때만 harness context로 승급한다.
- 사용자가 override 하더라도 Root Cause Fix, RPI, verify-result 같은 상위 정책을 우회하면 안 된다.
- explicit 우선순위는 다음을 따른다.
  - `-BundlePath` 명시 > `-ContextMode` 명시 > 사용자 레벨 override > 자동 판정
- 비대화형 환경(CI 또는 `-NonInteractive`)에서 고위험 downgrade가 감지되면, 명시적 `-AllowRiskyLevelOverride` 없이는 진행하지 않는다.

## 2. How — 어떻게 만드는가

### 2.1 수정 대상 파일
| 파일 | 변경 내용 |
|------|-----------|
| `AGENTS.md` | Codex/portable baseline 관점에서 Wave 3 4단계 자동 분류 원칙을 짧게 연결 |
| `tools/harness/run_codex.ps1` | 자동 레벨 판정, override 파싱, 레벨별 bundle/자원/표시 문구 라우팅 추가 |
| `tools/harness/run_gstack_qa.ps1` | Wave 3 분류 체계와 충돌하지 않도록 QA 기본 레벨/표시 정책 정리 |
| `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md` | 4단계 분류, override 형식, 사용자 노출 방식 문서화 |
| `CLAUDE.md` | Wave 3 자동 분류 원칙 및 override 원칙 반영 |
| `.cursor/rules/00-project-context.mdc` | 하네스 자동 레벨링 원칙 반영 |
| `.cursor/agents/grand-develop-master.md` | GDM 관점의 레벨별 자원 정책과 승급 기준 반영 |
| `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md` | Wave 3 spec 참조 링크 추가 |
| `docs/ARCHIVE_INDEX.md` | `docs/specs/` 내 Wave 3 spec 인덱싱 |
| `tests/harness/test_profile_contracts.py` | bundle 선택 계약이 Wave 3 라우팅과 충돌하지 않는지 확장 |
| `tests/harness/` 신규 테스트 | 자동 판정, override, 경고 재확인, 사용자 표시 형식, dry-run 라우팅 테스트 추가 |
| `docs/harness/policy/DECISIONS.md` | Wave 3 분류 우선순위/override 결정 기록 |
| `progress.md` / `findings.md` / `task_plan.md` | Wave 3 설계 및 구현 추적 |

### 2.2 아키텍처 방향
- 기존 `daily bundle` / `_HARNESS bundle` 분리 구조를 유지하고, Wave 3는 그 위에 `레벨 판정기`를 추가한다.
- 분류기는 새로운 전면 시스템을 만들기보다, 먼저 `run_codex.ps1` 내부 helper 계층으로 구현한다.
- 구현 순서는 `override 파싱 → 자동 판정 → 승급 규칙 적용 → bundle/검증/표시 라우팅`으로 나눈다.
- 판정기는 LLM 호출이 아닌 결정적 규칙 기반으로 구현한다.
- 입력 우선순위는 다음을 따른다.
  - 사용자가 명시한 `-BundlePath`
  - 사용자가 명시한 `-ContextMode`
  - `AdditionalPrompt` 안의 레벨 override
  - `Target` / `Plan` / `Scenario` / plan 본문 파싱 기반 자동 판정
- 고위험 downgrade는 대화형 환경에서 재확인 질문을 하고, 비대화형 환경에서는 `-AllowRiskyLevelOverride` 없이는 종료 코드로 거절한다.
- `최상`과 `상`이 동일한 harness bundle을 쓰더라도, `최상`은 별도 자원 힌트(리서치/브라우저 QA/병렬 리뷰/전체 검증)를 prompt와 dry-run에 명시해야 한다.
- 기존 패턴 준수:
  - 레포 기준 경로 resolve helper 사용
  - dry-run에서 실제 라우팅 결과를 보여줌
  - 검증/정책은 문서와 테스트를 함께 갱신

### 2.3 의존성 및 영향 범위
- DB 마이그레이션은 필요 없다.
- 직접 영향 범위는 wrapper, 가이드, 정책 문서, harness 테스트이다.
- 간접 영향은 Codex review/implement/qa 진입 방식과 사용자 체감 비용/품질 균형이다.
- 분류 결과를 잘못 잡으면 불필요한 token 사용 또는 과소 검증 리스크가 생기므로 dry-run 테스트가 중요하다.

## 3. Steps — 실행 단계
- [x] Step 1: Wave 3 분류 규칙표와 레벨별 자원 매핑을 `run_codex.ps1` 구현용 상수/헬퍼 구조로 설계한다.
- [x] Step 2: 사용자 override 파싱(자연어 + 고정 태그)과 고위험 downgrade 재확인 플로우를 구현한다.
- [x] Step 3: 자동 판정(위험도/영향 범위 → 작성/수정 범위 → 검증 강도) 및 승급 규칙을 구현한다.
- [x] Step 4: 레벨 결과에 따라 daily/harness bundle, 안내 문구, 검증 강도, 자원 힌트를 라우팅한다.
- [x] Step 5: `run_gstack_qa.ps1`, `AGENTS.md`, 가이드, 정책 문서, GDM 문서, master plan/archival index를 Wave 3 체계에 맞게 동기화한다.
- [x] Step 6: harness 테스트와 PowerShell dry-run 검증 케이스를 추가하고 전체 harness suite를 통과시킨다.

## 4. 검증 기준
- [x] `python -m pytest tests/harness -q` 통과
- [x] `python -m compileall -q .cursor/hooks` 통과
- [x] `python tools/harness/verify_result.py --json`에서 `success: true`
- [x] `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "docs/AI_STATUS.md" -DryRun` 시 low/medium 후보 라우팅이 daily bundle로 유지됨
- [x] `powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "tools/harness/build_context_bundle.py" -DryRun` 시 harness 관련 파일이 상/최상 후보로 적절히 승급되고 `_HARNESS` bundle이 선택됨
- [x] override 예시(`레벨: 최상`, `이번 건 최상으로 진행`)가 dry-run에서 동일하게 해석됨
- [x] 위험 작업 downgrade 시 대화형 재확인 또는 비대화형 거절(`-AllowRiskyLevelOverride` 없으면 실패)이 테스트로 검증됨
- [x] 사용자 노출 형식이 `Level: <level> (<short reason>)` 또는 동등한 한 줄 계약을 만족함
- [x] PowerShell dry-run 테스트가 `run_codex.ps1` 분류/override/경고 플로우를 직접 검증함

## 5. 참고 자료
- 관련 결정:
  - `docs/harness/policy/DECISIONS.md` — 하네스 일상 번들 슬림화
  - `docs/harness/policy/DECISIONS.md` — 하네스 전용 확장 번들 분리
  - `docs/harness/policy/DECISIONS.md` — Spec 탐색 규칙 단일화
- 관련 설계 계획: `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`
- 관련 가이드: `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`

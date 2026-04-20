# Strict Final Canonical Tree — Final Audit Gap Closure Plan

> 작성일: 2026-04-16
> 상위 기준: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> 직접 선행 계획: `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`
> 작성 근거: 2026-04-16 final hard audit (`HEAD` clean-room green / workspace hygiene red / FR20 README false-green / evidence sync drift)

## 1. Purpose

이 문서는 PTC tranche 이후에도 남아 있는 **마지막 세 개의 exactness gap**만 닫기 위한 후속 runbook이다.

현재 상태는 아래처럼 갈라져 있다.

1. **committed tree / proof**
   - `pytest tests -q` green
   - `strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest` green
2. **workspace physical tree**
   - `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` red
3. **code / documentation exactness**
   - FR20 README uniqueness false-green 가능
   - `PTC-B7` / `AI_STATUS` evidence가 현재 `HEAD`와 1:1 sync 아님

이번 tranche의 목적은 새로운 구조 개편이 아니다.
오직 아래 세 축만 끝까지 닫는다.

1. **workspace physical-tree exactness**
2. **FR20 README uniqueness exactness**
3. **closeout evidence/document sync exactness**

## 2. Current Findings Register

### 2.1 `FAG-W1` — Workspace hygiene is still red

현재 `HEAD` clean-room은 green이지만, live workspace는 final-audit 금지 residue가 남아 있다.

대표 예시:

- root `.pytest_cache/`
- root `__pycache__/`
- recursive `__pycache__/` under canonical tree
- repo-local runtime DB:
  - `data/ops_browser_qa.db`

의미:

- committed snapshot은 맞아도 “현재 FOMS 폴더”는 아직 exact하지 않다.
- user가 요구한 “물리적 파일 tree까지 완벽” 기준으로는 미완료다.

### 2.2 `FAG-R1` — FR20 README proof can still false-green

FR20 authoritative home은 page-first/API-first context마다 정확히 하나만 허용한다.

그런데 현재 `wdcalculator`는 아래 두 문서가 동시에 존재한다.

- authoritative:
  - `foms/web/wdcalculator/README.md`
- extra technical README:
  - `static/js/wdcalculator/README.md`

현재 proof gap:

- `tests/contracts/runtime/test_ptc_physical_exactness.py`는 authoritative README의 **존재**만 확인한다.
- extra README의 **부재**는 검증하지 않는다.

의미:

- 현 상태가 의도된 carve-out인지, 아직 미정리 duplicate인지 proof만으로는 분간되지 않는다.

### 2.3 `FAG-E1` — Closeout evidence is not fully synchronized

현재 문서 증거는 같은 reality를 가리키지 않는다.

대표 예시:

- `docs/plans/2026-04-16-ptc-b7-run-record.md`
  - `605 passed`를 적으면서도 `HEAD lag warning`을 계속 유지
- `docs/AI_STATUS.md`
  - 최상단 summary가 아직 PAC `83e14b5d` / `600 passed` 중심
- final audit reality:
  - 현재 `HEAD` 기준 full pytest는 `605 passed`
  - 현재 `HEAD` 기준 clean-room도 `605 passed`

의미:

- code/proof가 green이어도 문서 exactness가 아직 1:1이 아니다.

## 3. Decision Lock

### 3.1 Scope lock

이번 tranche는 아래 셋만 다룬다.

- workspace residue cleanup / proof
- FR20 README uniqueness / proof
- closeout evidence sync

금지:

- 새로운 canonical subtree 재개편
- unrelated context owner 이동
- root allowlist 재설계

### 3.2 Final closeout has two different surfaces

이번 tranche는 아래 둘을 분리해서 증명해야 한다.

1. **Committed closeout**
   - `HEAD` clean-room green
2. **Workspace closeout**
   - 현재 worktree cleanup 후 hygiene probe green

둘 중 하나만 green이면 final exactness closeout 불가다.

### 3.3 FR20 README uniqueness lock

FR20 authoritative home은 기존 spec/PTC lock을 그대로 유지한다.

- page-first context:
  - 정본은 `foms/web/<context>/README.md`
- API-first context:
  - 정본은 `foms/api/<context>/README.md`

추가 lock:

- authoritative README 외의 **secondary README**가 필요하면 `docs/context/` 아래 기술 문서로 이동한다.
- `static/`, `templates/`, context subtree 안의 extra `README.md`를 “보조 설명”이라는 이유로 남겨두고 exactness 완료를 주장하는 것은 금지다.

이번 tranche의 `wdcalculator` 결정:

- keep:
  - `foms/web/wdcalculator/README.md`
- retire or relocate:
  - `static/js/wdcalculator/README.md`
- relocation target:
  - `docs/context/wdcalculator-static-js-chunk-map.md`

historical-doc rule:

- 과거 run record가 당시 경로를 기록한 것은 historical evidence로 유지 가능하다.
- 그러나 **현재 상태를 설명하는 living doc** (`AI_STATUS`, active plan, canonical README, current guide)는 더 이상 `static/js/wdcalculator/README.md`를 active authoritative path로 가리키면 안 된다.

### 3.4 Workspace hygiene lock

final workspace exactness에서 금지:

- `.pytest_cache/`
- `.tmp_strict_tree_verify/`
- root `__pycache__/`
- recursive `__pycache__/` under repo
- repo-local runtime DB/dump:
  - `data/ops_browser_qa.db`
  - root `*.db`
  - root `*.dump`

주의:

- 검증 중 생성은 허용되지만, final audit 직전 cleanup 후 0이어야 한다.
- `gitignore` 상태는 면책 사유가 아니다.

### 3.5 Evidence sync lock

최종 closeout 문서는 아래 truth를 동일하게 가리켜야 한다.

- current `HEAD` commit
- current `pytest tests -q` count
- current clean-room result
- current workspace hygiene result

금지:

- stale warning을 남겨둔 채 closeout 확정
- older tranche summary를 `AI_STATUS` top summary에 계속 남겨 현재 상태처럼 보이게 두는 패턴

## 4. Exact Target Ledgers

### 4.1 Workspace residue ledger

| Current residue | Final target |
|------|------|
| root `.pytest_cache/` | absent |
| root `__pycache__/` | absent |
| recursive `__pycache__/` | absent |
| `data/ops_browser_qa.db` | absent from repo |
| verification temp residue | absent after final audit |

### 4.2 README uniqueness ledger

| Path | Final target |
|------|------|
| `foms/web/wdcalculator/README.md` | keep as sole authoritative FR20 README |
| `static/js/wdcalculator/README.md` | remove from context tree |
| static JS chunk-map content | move/merge into `docs/context/wdcalculator-static-js-chunk-map.md` |

### 4.3 Proof ledger

| Proof surface | Required change |
|------|------|
| `tests/contracts/runtime/test_ptc_physical_exactness.py` | authoritative README presence + forbidden duplicate README absence |
| `tools/harness/ptc_workspace_hygiene_probe.ps1` | final workspace residue contract remains authoritative |
| clean-room proof | committed exactness only, not workspace substitute |

### 4.4 Evidence sync ledger

| Document | Final target |
|------|------|
| `docs/plans/2026-04-16-ptc-b7-run-record.md` | remove stale `HEAD lag warning`; rewrite with actual committed `HEAD` evidence |
| `docs/AI_STATUS.md` top summary | point to final PTC/FAG closeout, not stale PAC-only summary |
| `docs/ARCHIVE_INDEX.md` | include this follow-up plan and closeout records |

## 5. Fixed Batch Order

### 5.1 `FAG-B0` — Findings freeze

docs-only.

필수 산출물:

- 본 계획서
- final audit findings freeze

검증:

- no product code change

### 5.2 `FAG-B1` — FR20 README uniqueness closure

docs/code/tests batch.

필수 작업:

- `static/js/wdcalculator/README.md` content를 `docs/context/wdcalculator-static-js-chunk-map.md`로 이동 또는 `foms/web/wdcalculator/README.md`에 흡수
- `static/js/wdcalculator/README.md` 제거
- `test_ptc_physical_exactness.py`에 extra README absence gate 추가
- living docs/README cross-reference를 새 path로 정렬
- FR20 README uniqueness가 “존재 + 중복 부재” 둘 다 검증되게 만든다

검증:

- focused pytest
- `APP_OK`

### 5.3 `FAG-B2` — Workspace hygiene closure

tooling/docs batch.

필수 작업:

- `tools/harness/ptc_workspace_cleanup.ps1 -RecursePyCache`를 final closeout sequence에 맞게 실행/정리
- repo-local runtime DB (`data/ops_browser_qa.db`) 제거
- cleanup 후 `ptc_workspace_hygiene_probe.ps1 -RecursePyCache` green 증거 확보
- workspace hygiene 문서가 “개발 중 생성 가능 / 최종 audit 전 cleanup 필수”를 동일하게 가리키는지 확인

검증:

- cleanup -> probe green
- `git status --short --ignored` evidence

### 5.4 `FAG-B3` — Evidence/document sync closure

docs-only.

필수 작업:

- `docs/plans/2026-04-16-ptc-b7-run-record.md`
  - stale `HEAD lag warning` 제거
  - actual `HEAD` evidence로 rewrite
- `docs/AI_STATUS.md`
  - top summary를 final PTC/FAG closeout truth로 교체
  - `600 passed` stale framing 제거
- 필요 시 closeout correction note 추가

검증:

- 문서 간 commit id / pytest count / clean-room status가 동일

### 5.5 `FAG-B4` — Final exactness re-audit

closeout batch.

필수 green:

1. `python -c "import app; print('APP_OK')"`
2. `python tools/harness/verify_result.py --json`
3. `pytest tests/contracts/runtime/foms_namespace_surface_tests.py -q`
4. `pytest tests/contracts/runtime/test_ptc_physical_exactness.py -q`
5. `pytest tests -q`
6. `tools/harness/strict_canonical_b12_clean_room.ps1 -Ref HEAD -RunFullPytest`
7. `powershell -NoProfile -File tools/harness/ptc_workspace_hygiene_probe.ps1 -RecursePyCache`
8. final GDM 1:1 audit green

## 6. GDM Ultra-Review Loop

각 batch는 아래 감리 loop를 통과해야만 다음 batch로 간다.

### 6.1 Reviewer roles

- `R1 Spec / plan reviewer`
  - two controlling spec + PTC/FAG plan alignment
- `R2 Workspace reviewer`
  - current physical tree / cleanup residue / ignored runtime outputs
- `R3 Code / README reviewer`
  - FR20 authoritative home + duplicate README absence
- `R4 Proof / evidence reviewer`
  - pytest / clean-room / workspace probe / AI_STATUS / run-record consistency
- `GDM synthesis`
  - stop/go 판정

### 6.2 Exit condition per batch

아래를 모두 만족해야 한다.

- High = 0
- Medium = 0
- batch acceptance 전부 충족
- run record / evidence / current tree가 일치
- same-batch TODO = 0

### 6.3 Hard stop

아래 중 하나라도 발생하면 즉시 중단한다.

- workspace hygiene red인데 final exactness closeout을 주장함
- `static/js/wdcalculator/README.md`가 남아 있는데 FR20 exactness green을 주장함
- `AI_STATUS`가 stale summary를 유지한 채 final closeout을 주장함
- clean-room green만으로 workspace green을 대체함

## 7. Final 1:1 Acceptance Matrix

### 7.1 Workspace physical-tree exactness

- `.pytest_cache/` 없음
- `.tmp_strict_tree_verify/` 없음
- repo-wide `__pycache__/` 없음
- repo 안 runtime DB/dump 없음

### 7.2 FR20 README exactness

- page-first/API-first context authoritative README 모두 존재
- extra context README 없음
- `wdcalculator` technical chunk-map은 `docs/context/`로 정리됨

### 7.3 Proof exactness

- authoritative README presence + duplicate absence gate green
- workspace probe green
- full pytest green
- clean-room green

### 7.4 Evidence exactness

- `AI_STATUS`
- latest closeout run record
- actual `HEAD`
- actual test counts

위 네 가지가 1:1로 일치한다.

## 8. First-Turn Operator Prompt

다음 LLM은 아래 순서로 착수한다.

1. `AGENTS.md`
2. `docs/ARCHIVE_INDEX.md`
3. `docs/harness/policy/DECISIONS.md`
4. `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
5. `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
6. `docs/plans/2026-04-16-strict-final-canonical-tree-physical-tree-code-convergence-plan.md`
7. `docs/plans/2026-04-16-strict-final-canonical-tree-final-audit-gap-closure-plan.md`

첫 응답에서 반드시 아래를 수행한다.

- current state를 `committed / workspace / README / evidence` 네 축으로 10줄 이내 요약
- `FAG-B1` scope / acceptance / stop rule 재진술
- cleanup / pytest / clean-room / workspace probe 명령을 먼저 고정
- 바로 `FAG-B1` 착수

진행 규칙:

- blocker가 없으면 `FAG-B1 -> B2 -> B3 -> B4` 자동 진행
- batch마다 GDM ultra-review loop 수행
- High/Medium이 남아 있으면 같은 batch에서 fix + 재감리
- final closeout 전에는 반드시 current workspace probe와 `HEAD` clean-room을 둘 다 다시 감사

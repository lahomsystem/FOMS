# Post-Wave9 Endgame Master Sequence
> 작성일: 2026-04-14
> 상태: active
> 상위 기준선: `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`
> 전제: `docs/plans/2026-04-14-wave9-batch4-closeout-run-record.md` (`Option A explicit defer`)

## 1. 목적

Wave 9가 `Option A explicit defer`로 종료된 현재 상태를 기준으로, packaging/`src/foms`를 다시 열지 않은 채 modular monolith 최종목표를 완성하기 위한 **GDM master execution order**를 잠근다.

이 문서는 새로운 wave runbook이 아니다.  
역할은 아래 두 가지로 제한한다.

1. post-Wave9 이후 **순서와 우선순위**를 authoritative하게 고정한다.
2. 각 tranche는 기존 authoritative runbook 또는 전용 continuation batch로만 집행하도록 가드레일을 제공한다.

## 2. 고정 전제

1. Wave 9 verdict는 `Option A explicit defer`다.
2. `src/foms`, `pyproject.toml`, packaging-only hardening은 별도 ADR/전용 구현 트랙 없이는 reopen하지 않는다.
3. 남은 최종목표는 physical packaging migration 없이도 달성 가능한 것으로 간주한다.
4. 따라서 이후 작업은 `canonical tree 선명화`, `thin overlay 감소`, `bounded-context chunk closeout`에 집중한다.

## 3. GDM Master Order

### Program 1 — Active canonical chunk closeout
- authoritative runbook: `docs/plans/2026-04-14-wave5-large-front-end-island-rebaseline-execution-plan.md`
- 실행 순서:
  1. `W5-B4` WDCalculator `estimate-lifecycle`
  2. `W5-B5` WDCalculator `pricing-core`
  3. `W5-B6` shared ERP island lock
  4. `W5-B7` ERP Beta contract freeze
  5. `W5-B8` ERP Beta shared-form pilot
  6. `W5-B9` shell/CSS defer register + closeout

### Program 2 — Wave 8 deferred bridge continuation
- authoritative truth: `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md`
- one-family-per-batch 원칙으로 아래 순서를 잠근다.
  1. `WR-P1` personal board adapter shell
  2. `WR-O1` orders adapter shell
  3. `WR-J1` jobs runtime-string contract
  4. `WR-S2` storage singleton / init-adjacent
  5. `WR-H1` high-risk cluster
- `WR-B1` (`business_calendar` / `/calendar`)은 controlling spec 승인 또는 별도 ADR 전까지 계속 explicit exception으로 유지한다.

### Program 3 — Overlay minimization closeout
- Program 1, Program 2 결과를 바탕으로 `apps/` / root `services/`에 남은 thin overlay와 defer row를 다시 분류한다.
- 제거 가능한 축만 제거한다.
- packaging reopen, runtime contract reopen, shell/CSS redesign은 포함하지 않는다.

### Program 4 — Final checklist re-verification
- controlling spec의 Step 1~7과 각 verification 기준을 다시 대조한다.
- 남은 항목만 별도 closeout tranche로 정리한다.

## 4. Immediate first tranche

- 첫 실행 tranche는 `W5-B4 estimate-lifecycle`.
- 근거:
  1. `docs/AI_STATUS.md`가 현재 next step으로 고정하고 있다.
  2. Wave 5 mainline ordering이 이미 `W5-B4 -> W5-B5 -> W5-B6~B9`로 잠겨 있다.
  3. bridge defer / packaging / shell-CSS와 축이 섞이지 않는다.

## 5. Guardrails

1. 한 tranche는 한 축만 다룬다.
2. `app.py`, deploy, worker, Alembic, `pyproject.toml`, `src/foms`는 본 문서로 reopen되지 않는다.
3. 각 tranche는 기존 authoritative runbook을 우선 사용한다.
4. thin wrapper만 추가하고 removal condition이 없는 변경은 금지한다.
5. Wave 8 deferred bridge continuation은 `W5` product chunk와 같은 batch로 섞지 않는다.

## 6. Completion signal

아래가 모두 충족되면 post-Wave9 endgame master order는 종료로 본다.

1. Wave 5 mainline `W5-B4~B9` closeout 완료
2. Wave 8 defer rows의 executable family closeout 완료 (`WR-B1` 제외 가능)
3. overlay 최소화 closeout 완료
4. controlling spec Step 1~7 final checklist 문서화 완료

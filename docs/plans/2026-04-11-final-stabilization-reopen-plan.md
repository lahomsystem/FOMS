# Final Stabilization Reopen Plan
> 작성일: 2026-04-11
> 상태: deferred-until-gates
> 목적: global template/layout 분해와 packaging revisit를 “마지막에만” 다시 열기 위한 gate를 고정한다.

## 1. 배경
- Final roadmap의 마지막 todo는 global shell 계층과 packaging revisit를 앞선 구조 배치 안정화 후 별도 ADR/plan로만 재개하라고 요구한다.
- packaging 쪽은 이미 `docs/harness/policy/DECISIONS.md`와 `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`에서 defer verdict가 고정돼 있다.
- 아직 남아 있는 quality/ops 분리 트랙과 전역 layout 계층은 Step 6 구조 분해와 직접 섞으면 안 된다.

## 2. 이번 문서가 고정하는 것

### A. Global template/layout
- 현재 상태:
  - `templates/layout.html` 및 전역 shell 계층은 아직 future stabilization 대상이다.
  - 성능/전역 스크립트/load-order 이슈는 과거 계획 문서들에 산재해 있으나, 이번 large-file batch의 직접 대상은 아니었다.
- 지금 당장 재개하지 않는 이유:
  - 전역 layout은 page-wide blast radius가 크다.
  - JS/CSS split 직후 함께 건드리면 regression source를 분리하기 어렵다.
  - measurement legacy loader/CSP와도 결합돼 있다.
- reopen gate:
  - Wave A/B hotspot split 검증 완료
  - quality/ops separation 문서화 완료
  - measurement legacy JS/CSP plan이 별도 트랙으로 고정됨
  - layout에 실리는 전역 JS/CSS/load-order contract inventory가 별도 문서로 준비됨
- reopen 방식:
  - 새 ADR/plan에서만 시작
  - 첫 batch는 inventory + contract freeze만 수행
  - 구조-only와 behavior/security 변경을 다시 분리

### B. Packaging revisit
- canonical decision:
  - `docs/harness/policy/DECISIONS.md`: repo-root `foms/` 유지, full `src/foms` migration 및 packaging-only hardening defer
  - `docs/plans/2026-04-11-step8-batch80-closeout-run-record.md`: future packaging reopen은 조건부
- 지금 당장 재개하지 않는 이유:
  - `app:app`, Railway, worker, Alembic, tests import contract가 아직 repo-root cwd에 강하게 결합돼 있다.
  - Step 6 future decomposition이 끝나기 전 packaging을 다시 열면 split-brain 위험이 크다.
- reopen gate:
  - `app.py` / worker / Alembic / tests import contract explicit화 완료
  - repo-root cwd 의존 경로 정리
  - future decomposition 정리 완료
  - 별도 ADR/plan 승인
- reopen 방식:
  - 기존 Step 8 문서를 참조하는 새 ADR/plan에서만 시작
  - packaging-only hardening과 runtime path migration을 같은 batch에 섞지 않는다

## 3. 마지막 stabilization 체크
- namespace import 회귀가 녹색일 것
- `python -c "import app; print('APP_OK')"`가 녹색일 것
- Wave A/B structure-only split에서 high regression이 없을 것
- quality/ops 별도 트랙이 구조 batch acceptance criteria에서 제거돼 있을 것

## 4. 이번 턴의 판정
- global template/layout은 “미착수”가 아니라 “gate 고정 후 defer” 상태로 닫는다.
- packaging revisit도 기존 defer verdict를 유지하고, reopen은 기존 Step 8 결정 문서에 종속된 별도 ADR/plan로만 허용한다.
- 따라서 final roadmap의 마지막 todo는 현재 시점에서 “재개 조건 문서화 완료”로 판정한다.

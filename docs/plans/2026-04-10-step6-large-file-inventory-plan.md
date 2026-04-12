# Step 6 Large File Decomposition Inventory Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Step 6에서 저장소 구조 거버넌스와 실제 대형 파일 분해 작업을 분리하기 위해, 현재 남아 있는 대형 Python/HTML/JS/CSS hotspot을 inventory로 정리하고 별도 decomposition spec을 만든다.

**Architecture:** 이번 Step 6는 docs-only 배치다. 실제 코드 분해는 하지 않고, `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`와 별도 `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`를 source of truth로 만든다. 기존 거버넌스 spec은 Step 6 완료 상태와 다음 자동 단계만 반영한다.

**Tech Stack:** Flask Blueprint, Jinja2 templates, Vanilla JS, SQLAlchemy ORM, existing `foms/*` namespace, pytest, existing governance docs.

**Execution mode:** 사용자 지시에 따라 이 세션에서 같은 프로세스(RPI + 전/후감리 + 배치 실행)로 Step 6를 끝까지 닫는다.

---

## Scope

- 포함: Python 500줄+, HTML 800줄+, JS 300줄+, CSS 500줄+ 후보의 inventory, tier 구분, 향후 분해 경계, contract-freeze 요구사항, separate spec 작성.
- 포함: `apps/api/orders.py`, `templates/wdcalculator/partials/wdcalculator_scripts.html`를 시작점으로 한 확장 inventory.
- 제외: 실제 코드 분해, 새 Alembic revision, schema/persistence 변경, `templates/`/`static/` 물리 루트 이동, generated bundle hand-edit.
- 제외: 사용자 지시대로 `business_calendar` module과 `/calendar` 축은 계속 migration scope 밖으로 유지한다.
- Gate: 거버넌스 spec과 대형 파일 분해 spec을 분리하고, 구조 개편 PR에 대형 리팩터링을 섞지 않는다.
- Stop 조건: inventory 범위를 넘어 실제 런타임 리팩터링이 필요해지면 즉시 중단하고 별도 execution plan/ADR로 분리한다.

## Batch 67: Parallel Pre-Audit and Hotspot Scan

**Files**
- Add: `docs/plans/2026-04-10-step6-batch67-preaudit-run-record.md`

**Work**
- parallel agent/team audit로 large-file hotspot을 수집한다.
- `apps/api/orders.py`, `templates/wdcalculator/partials/wdcalculator_scripts.html`를 anchor로 삼아 runtime/UI/tooling 후보를 tier로 분류한다.
- `business_calendar` / `/calendar`, generated bundle, persistence-heavy candidate(`models.py`) 같은 제외/보류 대상을 명시한다.

**Verification**
- pre-audit 결과가 Batch 67 run record에 남아 있고, source code/runtime file 변경 없이 docs-only 상태를 유지한다.

## Batch 68: Inventory Document

**Files**
- Add: `docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md`
- Add: `docs/plans/2026-04-10-step6-batch68-inventory-run-record.md`

**Work**
- 대형 파일 후보를 exact line count, artifact type, risk, suggested decomposition boundary, likely future target namespace로 정리한다.
- Tier A/B/C와 explicit exclusion을 구분한다.
- 향후 decomposition execution에 필요한 contract freeze/test gap/manual check를 함께 적는다.

**Verification**
- `python -c "from pathlib import Path; p = Path(r'docs/plans/2026-04-10-step6-large-file-decomposition-inventory.md'); print('STEP6_INVENTORY_OK' if p.exists() else 'STEP6_INVENTORY_MISSING')"`

## Batch 69: Separate Decomposition Spec

**Files**
- Add: `docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md`
- Add: `docs/plans/2026-04-10-step6-batch69-decomposition-spec-run-record.md`

**Work**
- future large-file decomposition을 위한 전용 governance spec을 만든다.
- artifact class별(API/template/JS/CSS/canonical service) decomposition rule, contract-freeze rule, verification baseline, stop condition을 문서화한다.
- root governance spec은 큰 방향과 자동 다음 단계만 유지하고, file decomposition의 세부 원칙은 새 spec으로 위임한다.

**Verification**
- `python -c "from pathlib import Path; p = Path(r'docs/specs/2026-04-10-large-file-decomposition-governance_SPEC.md'); print('STEP6_SPEC_OK' if p.exists() else 'STEP6_SPEC_MISSING')"`

## Batch 70: Post-Audit and Closeout

**Files**
- Add: `docs/plans/2026-04-10-step6-batch70-closeout-run-record.md`
- Modify: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
- Modify: `docs/AI_STATUS.md`
- Modify: `docs/ARCHIVE_INDEX.md`
- Modify: `docs/context/COMPACT_CHECKPOINT.md`

**Work**
- Step 6 verdict를 정리하고, inventory/spec 분리가 완료됐음을 거버넌스 상태 문서에 동기화한다.
- 다음 자동 단계(Step 7 docs/context + harness runtime asset 재분류)를 고정한다.

**Verification**
- `python -m pytest -q`
- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `ReadLints` on touched paths

# Step 3 Batch 48 Run Record
> 작성일: 2026-04-10
> 상태: 완료
> 기준 문서: `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`
> 선행 배치: `docs/plans/2026-04-10-step3-batch47-storage-caller-cleanup-run-record.md`

- 일시: 2026-04-10
- 브랜치: `deploy` (작업 기준)
- 실행자: AI agent
- 목적: `services/erp_policy.py`를 canonical `foms/services/erp_policy.py`로 이관하고, repo root `data/` JSON 경로를 파일 위치 독립적으로 고정하며, `business_calendar` import-time 결합을 낮춘 뒤 live caller를 `foms.services.erp_policy`로 정렬한다
- 제외 축: `business_calendar.py` 모듈 본체 및 `/calendar` 관련 기능은 migration scope 밖(삭제 예정 축) — 이동·삭제하지 않음

## 1. 전체 판정
**Verdict: Step 3 Batch 48 executed — canonical `erp_policy` + data path root-cause fix + caller alignment without behavior regression**

이유:
- Source of truth를 `foms/services/erp_policy.py`로 옮기고 `services/erp_policy.py`는 thin shim(`__all__` 위임)으로 유지했다.
- `_DATA_*`는 `Path(__file__).resolve().parent.parent.parent / "data"`로 계산해 `foms/services/` 아래에 있어도 repo root `data/erp_policy.json` 등을 가리킨다.
- 모듈 최상위 `from services.business_calendar import business_days_until`를 제거하고 `build_auto_tasks` 경로에서만 lazy import하는 `_business_days_until`로 대체했다. `_resolve_due_date` 내부의 `add_business_days` lazy import는 기존과 동일하게 유지했다.
- 요구된 app/API/apps/foms caller의 import를 canonical 문자열로 정리했다.

## 2. 변경 파일 (요약)
- 신규/이동: `foms/services/erp_policy.py` (canonical 본문)
- Shim: `services/erp_policy.py`
- Caller: `app.py`, `erp_automation.py`, `apps/api/erp_orders_drawing.py`, `erp_orders_draftsman.py`, `erp_orders_revision.py`, `erp_orders_structured.py`, `quest.py`, `personal_board.py`, `apps/erp_dashboard.py`, `erp_drawing_workbench.py`, `erp_construction_page.py`, `erp_production_page.py`, `foms/services/erp_display.py`, `foms/services/channel_event_payloads.py`
- 테스트: `tests/test_foms_namespace_imports.py`
- 문서: 본 run record, `docs/AI_STATUS.md`, `docs/ARCHIVE_INDEX.md`, `docs/context/COMPACT_CHECKPOINT.md`, `docs/specs/2026-04-07-repo-structure-governance_SPEC.md`

## 3. 검증
- `python -m pytest tests/test_foms_namespace_imports.py` — 통과
- `python -c "… ERP_POLICY_NS_OK …"` (legacy/canonical identity + `_POLICY_PATH`) — 통과
- `python -c "import app; print('APP_OK')"` — 통과
- `python tools/harness/verify_result.py --json` — 통과

## 4. 잔여 리스크 / 후속 후보
- `app.py`는 여전히 `from services.business_calendar import add_business_days, business_days_until`를 직접 import한다(calendar 축 제외 정책 유지).
- `erp_display`는 여전히 `services.business_calendar.business_days_until`를 최상위에서 import한다 — 별도 배치에서 canonical/lazy 정리 여지.
- Step 3 나머지: 거버넌스 SPEC의 다른 후보(예: `apps/api/orders.py` 대형 파일 inventory 등)는 미완.

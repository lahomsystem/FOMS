# Wave 2 Batch W2-B6 — Closeout + Wave 3 handoff

> **batch ID:** W2-B6  
> **risk axis:** verification / handoff (docs-only)  
> **실행일:** 2026-04-13

## 1. Wave 2 요약

| Batch | 산출물 | 상태 |
|-------|--------|------|
| W2-B1 | Bounded context map v1 + evidence | ✅ |
| W2-B2 | Spec reconcile + §2.3.2 + bridge debt register | ✅ |
| W2-B3 | `blueprints.py` 주석 가독성 | ✅ |
| W2-B4 | Adapter matrix + 선례 모듈 docstring | ✅ |
| W2-B5 | `foms/README.md` + Measurement/Orders 앵커 README | ✅ |
| W2-B6 | 본 closeout + ARCHIVE_INDEX + spec §5 sync | ✅ |

## 2. 잔여 legacy / mixed owner (요약)

- **다수** `apps.api.*` · `apps.*_page`가 **legacy owner** (BD-001~019 참조).
- **선례:** Measurement alias shim (`BD-003`), Orders thin adapter (`BD-005`).

## 3. Wave 3 API canonicalization — 1차 shortlist (API lane만)

우선순위는 **read-heavy / 낮은 교차 부작용**부터 (controlling spec Wave 3).

| 순위 | 대상 | 근거 |
|------|------|------|
| 1 | `apps.api.files`, `apps.api.address` (`BD-008`) | API-first, Orders 선례와 유사한 helper 추출 가능성 |
| 2 | `apps.api.notifications` (`BD-008`) | 알림 채널과 결합 — 읽기 경로 먼저 |
| 3 | `apps.api.erp_map` (`BD-004`) | Measurement 인접; measurement_map 위임 패턴 참조 |

**명시:** page/template/JS slice는 **Wave 4**; Wave 3는 **implementation 착수 없음** — 우선순위만 고정.

## 4. README / debt

- FR20 defer: **WDCalculator** (`W2-B5` defer 표).
- Bridge debt 전체: `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md`.

## 5. Verification

| 검사 | 결과 |
|------|------|
| W2 batch run record 6종 존재 | ✅ |
| spec / archive / plan 상호 참조 | ✅ (§5 보강, ARCHIVE_INDEX 행 추가) |

## 6. Direction Lock

전 항목 YES — closeout만, runtime 코드 변경 없음.

---

**touched files:** `docs/plans/2026-04-13-wave2-batch6-closeout-run-record.md`, `docs/ARCHIVE_INDEX.md`, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (§5)  
**verification result:** PASS  
**residual risk:** Wave 3에서 API 물리 이동 시 동일 도메인 split-brain 방지 (BD 표 준수)

# Wave 6 Batch W6-B3 — Notifications package pilot canonicalization

> **batch ID:** W6-B3  
> **risk axis:** code / local pilot  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed** (PASS)  
> **git HEAD (시점):** `240781907c445669ba320142835a7c297f0ba769` — **본 batch 파일 delta는 작업 트리 미커밋 상태로 반영됨** (동일 브랜치 `feature/modular-monolith-wip`).  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.4  
> **선행:** `W6-B2` (`docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`) contract freeze PASS

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| `foms/services/notifications/*`, flat/root shim, 허용된 `apps/api/*`, tests, README | route/response shape·notification semantics 변경 |
| | 계획서 §1.3 freeze (`app.py`, blueprints 등) |
| | 새 generic 패키지 (notifications 컨텍스트만) |

## 2. Delta summary (구조)

| 파일 | 변경 |
|------|------|
| `foms/services/notifications/realtime_notifications.py` | **신규** — canonical 구현 (기존 flat 파일 본문 이전) |
| `foms/services/notifications/__init__.py` | **신규** — package marker |
| `foms/services/realtime_notifications.py` | flat compat shim → `notifications.realtime_notifications` re-export |
| `services/realtime_notifications.py` | root shim → 패키지 re-export |
| `apps/api/erp_orders_drawing.py` | `from foms.services.notifications.realtime_notifications import ...` |
| `apps/api/erp_orders_revision.py` | 동일 |
| `apps/api/notifications.py` | lazy import 2곳 → 패키지 경로 |
| `tests/test_foms_namespace_imports.py` | 기대 import 문자열 + `test_notifications_package_submodule_matches_flat_and_legacy` |
| `foms/services/README.md` | notifications 섹션 W6-B3 반영 |

## 3. Contract compliance (W6-B2 표)

- Public API·동작: **변경 없음** (동일 함수 객체가 shim 체인으로 전파).
- `W6-B2` 고정 export 심볼: **`emit_erp_notification_to_users`**.

## 4. Verification (fresh process, 계획서 §5.4)

| 검증 | 결과 |
|------|------|
| `python -c "import app; print('APP_OK')"` | **PASS** (`APP_OK`) |
| `python tools/harness/verify_result.py --json` | **PASS** (`success: true`) |
| `python -m pytest tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q` | **PASS** (142 passed) |
| Lint/diagnostics (ReadLints, touched paths) | **PASS** (no issues) |

### 4.1 Import smoke (concrete — placeholder 없음)

**Frozen export name:** `emit_erp_notification_to_users`

**Command:**

```text
python -c "import services.realtime_notifications as legacy; import foms.services.realtime_notifications as flat; from foms.services.notifications import realtime_notifications as pkg; export_name = 'emit_erp_notification_to_users'; assert getattr(legacy, export_name) is getattr(pkg, export_name); assert getattr(flat, export_name) is getattr(pkg, export_name); print('W6_NOTIFICATIONS_NS_OK')"
```

**Result:** `W6_NOTIFICATIONS_NS_OK`

## 5. Direction Lock (§2.6)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | 구현이 `foms/services/notifications/`로 모여 SoT가 선명해짐. |
| 2 | **Y** | flat/root는 얇은 shim으로 유지; 제거는 Wave 8 backlog. |
| 3 | **Y** | 기존 flat을 패키지 leaf로 흡수(FR19). |
| 4 | **Y** | `notifications`가 해당 레인의 context package. |
| 5 | **Y** | shim+테스트만 순증; 구현 1곳. |
| 6 | **적용** | retirement는 Wave 8; README에 compat 경로 명시. |
| 7 | **Y** | README 갱신 완료. |
| 8 | **Y** | 동일 패턴 반복 시 트리 일관성 유지. |
| 9 | **Y** | API는 import wiring만 정렬. |
| 10 | **Y** | 기능/응답 변경 없음. |

## 6. Outcome

- **PASS** — notifications lane **package pilot canonicalization** 완료.

## 7. Next legal batch (Branch A)

**`W6-B4`** — Files helper contract freeze  
**Run record:** `docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md` (시작 시 생성)

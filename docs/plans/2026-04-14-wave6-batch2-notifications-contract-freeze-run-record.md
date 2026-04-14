# Wave 6 Batch W6-B2 — Notifications contract freeze

> **batch ID:** W6-B2  
> **risk axis:** docs / contract  
> **실행일:** 2026-04-13 (executor session)  
> **Attempt:** 1 — **completed** (contract freeze PASS; §8.13 `notifications-docs-freeze-stop` **미발동**)  
> **live revision:** `git rev-parse HEAD` → `240781907c445669ba320142835a7c297f0ba769` (문서-only batch; 코드 미변경)  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.3

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record 생성 | runtime / product 코드 변경 |
| `foms/services/README.md` 갱신 (notifications 계약 노트) | API 동작·라우트·응답 형태 변경 |
| | 계획서 §1.3 freeze 파일 |

**선행 완료:** `W6-B0` (`docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md`), `W6-B1` (`docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`). **Branch A** — 다음 합법 batch: **`W6-B3`**.

## 2. Inputs consumed (계획서 §5.3 step 1)

| 파일 | 역할 |
|------|------|
| `foms/services/realtime_notifications.py` | flat canonical 구현 (`emit_erp_notification_to_users`) |
| `services/realtime_notifications.py` | 루트 shim → flat canonical re-export |
| `apps/api/notifications.py` | lazy import 2곳 (`api_notifications_send`, `api_order_urgent_mention` 내부) |
| `apps/api/erp_orders_drawing.py` | 모듈 레벨 `from foms.services.realtime_notifications import emit_erp_notification_to_users` |
| `apps/api/erp_orders_revision.py` | 동일 모듈 레벨 import |
| `tests/test_realtime_notifications.py` | canonical 동작 contract |
| `tests/test_foms_namespace_imports.py` | shim 동치 + API import 문자열 검증 |

## 3. Public callable / import contract table (freeze)

| 항목 | 고정 값 |
|------|---------|
| **Public API** | 단일 함수 `emit_erp_notification_to_users(user_ids, payload=None) -> int` |
| **`__all__` (canonical / root shim)** | `["emit_erp_notification_to_users"]` |
| **런타임 의존** | `flask.current_app`; `current_app.config["_SOCKETIO_INSTANCE"]`가 없으면 0 반환 + 경고 로그 (동작 변경 금지) |
| **이벤트** | Socket.IO `erp_notification`, room `user_{int(user_id)}` |
| **payload 기본값** | `data.setdefault("kind", "erp_notification")` |

### 3.1 Import path matrix (현재 상태 — W6-B3 전 freeze)

| Surface | 경로 | 비고 |
|---------|------|------|
| Flat canonical (live impl) | `foms.services.realtime_notifications` | 단일 소스 구현 위치 (W6-B3에서 `notifications` 패키지로 이동 예정) |
| Root shim | `services.realtime_notifications` | `emit_erp_notification_to_users` re-export; canonical과 **동일 객체** |
| Drawing API | `apps.api.erp_orders_drawing` | 모듈 속성 `emit_erp_notification_to_users` = canonical 함수 객체 |
| Revision API | `apps.api.erp_orders_revision` | 동일 |
| Notifications API | `apps.api.notifications` | **함수 내부** lazy import: `from foms.services.realtime_notifications import emit_erp_notification_to_users` (문자열 검증: `test_notifications_api_uses_canonical_realtime_notification_lazy_imports`) |

## 4. Preferred package shape (계획서 §5.3 step 3 — 고정)

| 역할 | 경로 |
|------|------|
| **Canonical (post W6-B3)** | `foms/services/notifications/realtime_notifications.py` |
| **Package marker** | `foms/services/notifications/__init__.py` |
| **Flat compat (유지)** | `foms/services/realtime_notifications.py` → thin shim/re-export |
| **Root compat (유지)** | `services/realtime_notifications.py` → thin shim/re-export |

## 5. Caller matrix

| Caller | Import style (freeze 시점) | W6-B3 정렬 의도 |
|--------|---------------------------|-----------------|
| `apps/api/erp_orders_drawing.py` | 모듈 레벨 flat canonical | W6-B3에서 `foms.services.notifications` 경로로 정렬 **가능하면** 적용 (동일 객체 유지) |
| `apps/api/erp_orders_revision.py` | 동일 | 동일 |
| `apps/api/notifications.py` | lazy flat canonical | 동일; 테스트가 기대하는 import 문자열은 W6-B3에서 패키지 경로로 바뀔 경우 **같은 batch**에서 `test_foms_namespace_imports` 정합 갱신 |

## 6. W6-B3 focused verification plan (전방 참조)

`W6-B3` 실행 시 계획서 §5.4 검증 행렬 적용:

- `python -c "import app; print('APP_OK')"`
- `python tools/harness/verify_result.py --json`
- `python -m pytest tests/test_realtime_notifications.py tests/test_foms_namespace_imports.py -q`
- touched 파일 진단/lint
- **Import smoke (계획서 §5.4 step 6):** 아래 **고정 export 심볼** 사용 — placeholder 금지.

**Frozen contract export name (W6-B2 / W6-B3 공통):** `emit_erp_notification_to_users`

**Concrete import smoke (W6-B3 완료 후 패키지 존재 시 실행; W6-B2에서는 패키지 미생성으로 실행 안 함):**

```text
python -c "import services.realtime_notifications as legacy; import foms.services.realtime_notifications as flat; from foms.services.notifications import realtime_notifications as pkg; export_name = 'emit_erp_notification_to_users'; assert getattr(legacy, export_name) is getattr(pkg, export_name); assert getattr(flat, export_name) is getattr(pkg, export_name); print('W6_NOTIFICATIONS_NS_OK')"
```

(`foms.services.notifications`는 **W6-B3**에서 생성되므로 본 명령은 B3 검증 증거로만 기록.)

## 7. Direction Lock (계획서 §2.6)

| # | Y/N | 근거 |
|---|-----|------|
| 1 | **Y** | notifications 레인의 public/runtime 계약을 표로 고정해 SoT 선명화. |
| 2 | **N (이번 batch)** | shim/flat 경로 유지; 감소는 W6-B3에서 패키지+shim 맵으로 처리. |
| 3 | **Y** | 선호 형태가 기존 flat을 `notifications` 패키지로 흡수(FR19 merge). |
| 4 | **Y** | `notifications`가 해당 레인의 유지보수 가능한 context package 후보로 확정. |
| 5 | **Y** | 코드 파일 수 증가 없음(문서+README만). |
| 6 | **적용 예정** | W6-B3 run record에 shim 제거/retirement 시점 위임. |
| 7 | **Y** | 본 batch에서 `foms/services/README.md`에 계약 섹션 반영. |
| 8 | **Y** | 동일 패턴 반복 시 `foms/services` 트리가 패키지 기준으로 정렬됨. |
| 9 | **Y** | service/docs 경계: 계약은 문서에, 구현 이동은 W6-B3. |
| 10 | **Y** | 구조/계약 문서화만; 기능 변경 없음. |

## 8. Verification (docs-only)

| 항목 | 결과 |
|------|------|
| Runtime 코드 변경 | **없음** |
| 문서 정합 | 본 run record + `foms/services/README.md` notifications 섹션 상호 일치 |
| Repo sanity baseline 인용 | `W6-B0`에서 채택한 **fresh** `APP_OK` + `verify_result --json` 성공 및 리비전 `240781907c445669ba320142835a7c297f0ba769` (계획서 §6 docs batch: 본 batch는 코드 미변경이므로 동일 baseline을 **근거 인용**으로 사용) |

## 9. Outcome

- **PASS** — `notifications` lane public/runtime contract 및 preferred package shape **freeze** 완료.
- **Stop label:** 없음 (`notifications-docs-freeze-stop` 해당 없음).

## 10. Next legal batch

**`W6-B3`** — Notifications package pilot canonicalization  
**Run record:** `docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md` (시작 시 생성)

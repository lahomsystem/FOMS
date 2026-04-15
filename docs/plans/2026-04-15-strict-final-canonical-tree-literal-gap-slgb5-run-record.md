# SLG-B5 — Channel page/API split + attachments absorption (run record)

> 배치: `SLG-B5` (`docs/plans/2026-04-15-strict-final-canonical-tree-literal-gap-remediation-plan.md` §6.6)  
> 실행일: 2026-04-15

## 1. Scope / acceptance

- **Chat (JSON/Socket.IO):** `foms/api/chat/*` → `foms/api/channel/{blueprint,messages,rooms,files,utils,socketio_handlers,routes}.py`; `foms.api.channel`가 `chat_bp`·`register_chat_socketio_handlers` export.
- **Chat (HTML):** `/chat`, `/chat/scripts.js` → `foms/web/channel/routes.py` (`channel_chat_pages_bp`); API 패키지에서 페이지 라우트 제거.
- **Attachments internal:** `foms/api/attachments_internal/*` 흡수 완료 — 구현은 `foms/api/files/*`; `foms.api.attachments`는 `foms.api.files.*`에서 import.
- **Retire:** `foms/api/chat/`, `foms/api/attachments_internal/` 디렉터리 삭제.
- **Blueprint:** `foms/platform/blueprints.py` — `channel_chat_pages_bp` 등록 후 `chat_bp`; `chat_bp`/`register_chat_socketio_handlers`는 `foms.api.channel`에서 import.
- §4.3 **API** closed-set: `chat`·`attachments_internal` top-level dir 없음 (서비스 `erp_policy_internal`은 **SLG-B6**).

## 2. 증거

| 검증 | 결과 |
|------|------|
| `pytest tests/contracts/runtime/foms_namespace_surface_tests.py` | **181 passed, 1 failed** (`test_slg_literal_gap_foms_services_top_level_dirs_closed_set` — `erp_policy_internal`, SLG-B6 대상) |
| `python -c "import app; print('APP_OK')"` | **APP_OK** |
| `python tools/harness/verify_result.py --json` | **success: true** |

## 3. 변경 요약

- **추가:** `foms/web/channel/routes.py` (`channel_chat_pages_bp`), `foms/api/channel/{blueprint,messages,rooms,files,utils,socketio_handlers,routes}.py` (구 `foms/api/chat/*` 이동·이름 정렬).
- **삭제:** `foms/api/chat/`, `foms/api/attachments_internal/`.
- **갱신:** `foms/api/channel/__init__.py`, `foms/platform/blueprints.py`, `foms/web/channel/__init__.py`, `foms/api/attachments.py`, `foms/api/files/*.py` (internal → `files`), `tests/.../foms_namespace_surface_tests.py`, `tests/domains/test_sqlite_startup_compat.py`.

## 4. 3축 + GDM 감리 (요약)

| 축 | 결과 |
|----|------|
| A literal | `foms/api/chat`·`attachments_internal` 없음; `foms/web/channel`에 페이지 owner — **High 0** (본 배치) |
| B runtime | `channel_chat_pages_bp` → `/chat`; `chat_bp` → `/api/chat/*`; APP_OK — **High 0** |
| C proof | API SLG 게이트 green; services 게이트 1 fail은 B6 예정 — **High 0** (본 배치) |
| GDM | §6.6 ledger·owner 분리와 일치 — **High 0** |

**Medium:** 0 (범위 내).

## 5. 다음

- `SLG-B6` — `foms/services/erp_policy_internal` → `foms/services/orders/erp_policy_*.py` flat leaf + `erp_policy.py` internal import만 전환.

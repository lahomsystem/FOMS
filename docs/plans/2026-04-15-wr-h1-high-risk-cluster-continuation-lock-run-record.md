# WR-H1 — High-risk cluster continuation lock

> **batch ID:** WR-H1  
> **risk axis:** mixed owner / high-risk cluster  
> **실행일:** 2026-04-15  
> **상위 문서:** `docs/plans/2026-04-14-post-wave9-endgame-master-sequence.md` Program 2, `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md` WR-H1

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| live truth re-audit, continuation decision, 본 run record | `apps.api.notifications`, `apps.api.attachments`, `apps.api.chat/*`, `services/channel_*`, Socket.IO wiring, upload/notification behavior 변경 |

## 2. Live truth (refreshed — strict canonical track, 2026-04-15)

> 이전 §2 초안은 블루프린트가 `apps.api`에서 import한다고 기록되어 있었으나, **현재 트리에서는 이미 `foms.api`가 등록 주인(owner)** 이다. 아래가 저장소 기준 live truth이다.

### 2.1 Blueprint registry

- `foms/platform/blueprints.py`는 다음을 **`foms.api.*`에서만** import·등록한다:
  - `notifications_bp` ← `foms.api.notifications`
  - `attachments_bp` ← `foms.api.attachments`
  - `chat_bp`, `register_chat_socketio_handlers` ← `foms.api.chat`
  - channel BP 묶음 ← `foms.api.channel`

### 2.2 Legacy `apps.api` (compatibility only)

- `apps/api/notifications.py`, `attachments.py`, `chat/__init__.py` — `foms.api.*`로의 **re-export shim**.
- `apps/api/channel_integration.py` — `importlib`로 `foms.api.channel.channel_integration` 모듈에 **치환** (`sys.modules`).
- 도메인 구현은 **`foms/api/`** 아래; `apps/api/*`는 레거시 import 경로 유지용.

### 2.3 Cross-surface callers (canonical)

- `foms/api/drawing/erp_orders_drawing.py`, `erp_orders_revision.py` — `foms.api.notifications`에서 헬퍼 import.
- `foms/services/app_init.py` — 부트스트랩 컬럼 보장 등 `foms.api.attachments` import.

### 2.4 Channel services

- 런타임 구현: `foms.services.channel_*`.
- 루트 `services/channel_*` — `foms.services`로의 re-export shim (namespace surface 테스트로 동치 고정).

## 3. Decision (strict track)

### 3.1 Verdict

- **WR-H1 (등록·shim 진실):** “canonical owner = `foms` / legacy = `apps` shim” 구조로 **엄격 트랙 요건 충족**.
- **선택 후속:** `apps/api/*` shim 파일 **물리 삭제**는 남은 `import apps.api.*` 호출자(주로 `backups/` 스냅샷) 전수 확인 후 별도 배치.

### 3.2 Contract lock

- `tests/contracts/runtime/foms_namespace_surface_tests.py` — `test_wr_h1_high_risk_cluster_strict_canonical`.
- 상위 요약: `docs/plans/2026-04-15-strict-canonical-tree-delta-lock-run-record.md` §6.3.

## 4. Bridge delta (historical)

- 초기 WR-H1 배치에서 계획했던 “owner-surface 대규모 이전”은 이후 웨이브에서 상당 부분 반영됨; 본 문서 §2 갱신이 최종 bridge 상태를 반영한다.

## 5. Removal condition (optional)

- shim 파일 제거 전: `grep`/CI로 `from apps.api.notifications` 등 **라이브 코드** 잔존 여부 확인.
- Socket.IO·업로드·채널 런타임 회귀 테스트 유지.

## 6. Next legal batch

- §2.2.1 나머지 트랜치: templates / static / support tree (`strict-canonical-tree-delta-lock` §4).

# `foms.services` — 서비스 네임스페이스 엔트리포인트

> **Wave 6 authoritative package map**은 `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md`와 동일 선상에서 유지한다. **`notifications` 레인의 frozen public/runtime 계약**은 `docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`가 우선한다. 코드 배치(`W6-B3`, `W6-B5` 등) 후 본 문서를 반드시 갱신한다.

## 읽기 순서

1. 본 `README.md` — 컨텍스트 패키지 방향·파일럿 순서·예외·금지 사항  
2. 루트 `services/*` — **호환성 shim** (`from services.x` 레거시). 신규 코드는 가능하면 `foms.services.*`로 직접 import  
3. `tests/domains/test_foms_namespace_imports.py` — 루트 shim ↔ flat canonical import 동치 스모크 (파일럿 순서가 아님)

## Wave 6 mainline 파일럿 순서 (고정)

1. **`notifications`** — `realtime_notifications` 레인 → 목표: `foms/services/notifications/realtime_notifications.py` (+ `foms/services/notifications/__init__.py`). flat/root 호환은 동일 배치에서 shim 유지.  
2. **`files` (helper-only)** — `file_utils` 레인 → 목표: `foms/services/files/file_utils.py`. **`storage`는 동일 컨텍스트라도 high-risk이므로 본 파일럿에 포함하지 않는다.**

`business_calendar` **정본 구현**은 `foms/services/common/business_calendar.py`이다. 루트 `services/business_calendar.py`는 **thin shim**(legacy `from services.business_calendar` 호환)만 담당한다 (strict track WR-B1 closeout).

### Notifications lane — contract freeze (W6-B2) + package pilot (W6-B3)

- 계약 freeze: **`docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`**
- 코드 pilot 완료: **`docs/plans/2026-04-14-wave6-batch3-notifications-package-pilot-run-record.md`** (W6-B3 완료 후 동일 선상)

| 항목 | 내용 |
|------|------|
| Public API | `emit_erp_notification_to_users(user_ids, payload=None) -> int` 단일; `__all__ = ["emit_erp_notification_to_users"]` |
| **Canonical 구현** | `foms/services/notifications/realtime_notifications.py` |
| Package marker | `foms/services/notifications/__init__.py` |
| Flat compat | ~~`foms/services/realtime_notifications.py`~~ — **Wave 8 W8-B3 제거됨** |
| Root compat | ~~`services/realtime_notifications.py`~~ — **Wave 8 W8-B3 제거됨** |
| Live callers | `apps/api/*` — `from foms.services.notifications.realtime_notifications import emit_erp_notification_to_users` |
| Import smoke 심볼 | `emit_erp_notification_to_users` (고정) |

### Files (helper) lane — contract freeze (W6-B4) + package pilot (W6-B5)

- 계약 freeze: **`docs/plans/2026-04-14-wave6-batch4-files-helper-contract-freeze-run-record.md`**
- 코드 pilot: **`docs/plans/2026-04-14-wave6-batch5-files-helper-pilot-run-record.md`**

**`storage`는 동일 `files` 문맥의 장기 타깃이 있어도 본 helper pilot에 포함하지 않는다** (high-risk defer).

| 항목 | 내용 |
|------|------|
| Public API | `allowed_file`, `allowed_erp_media_file` |
| **Canonical 구현** | `foms/services/files/file_utils.py` |
| Package marker | `foms/services/files/__init__.py` |
| Flat compat | ~~`foms/services/file_utils.py`~~ — **Wave 8 W8-B3 제거됨** |
| Root compat | ~~`services/file_utils.py`~~ — **Wave 8 W8-B3 제거됨** |
| 주요 caller | `apps/excel_import.py` — `from foms.services.files.file_utils import allowed_file` |
| Import smoke 대표 심볼 | **`allowed_file`** (고정) |

## 패키지 맵 (provisional authoritative — Wave 6)

| Context / cluster | 대표 모듈 (flat) | 비고 |
|-------------------|------------------|------|
| **`notifications`** | `realtime_notifications.py` | API-first; 목표 패키지 `foms/services/notifications/` |
| **`files`** | `file_utils.py`, (장기) `storage.py` | `file_utils`만 Tier-1 파일럿. `storage`는 singleton/런타임 이슈로 **defer** |
| **`common`** | `business_calendar.py` — 정본; 루트 `services/business_calendar.py`는 shim | 신규는 `foms.services.common.business_calendar` |
| **`channel`** | `channel_*.py` | multi-module cluster — Wave 6에서는 **전체 패키지 분할 금지**, 레지스트리만 |
| **`orders` / ERP helpers** | `erp_display.py`, `erp_order_detail.py`, `erp_product_items.py`, `erp_utils.py`, `estimate_service.py`, `order_*.py` 등 | Tier 3 cluster — **단일 파일럿으로 축소되기 전까지 code batch 금지** |
| **`measurement`** | `measurement_*.py`, `map_snapshot.py`, `order_geocode.py`, `geocode_helpers.py` 등 | 동일 |
| **`jobs`** | `foms/services/jobs/*` | **Packaged precedent** — Wave 6 mainline 이동 대상 아님 |
| **`erp_policy`** | `erp_policy.py` + `erp_policy_internal/*` | public wrapper 유지; 내부 선례 존중. 추가 리팩터는 **defer** 별도 행 |
| **Platform-adjacent** | `app_init.py`, `context_processors.py`, `rate_limit.py`, `menu_config.py`, `erp_permissions.py` 등 | bootstrap/request 컨텍스트 혼재 — **high-risk defer** |

## 루트 `services/` 정책

- 루트 `services/*.py`는 **호환성 표면**이다. 신규 비즈니스 구현을 루트에 두지 않는다.  
- 대부분의 모듈은 **`foms.services.*`로 re-export하는 thin shim**이다.  
- **`services/business_calendar.py`:** 구현은 `foms.services.common`에 두고, 루트 파일은 **re-export shim**만 유지한다 (레거시 import 경로 호환).

## 금지 / 경계

- `common/` 외에 **임의의 generic 덤프 패키지**를 새로 만들지 않는다 (상위 SPEC / Wave 6 계획).  
- `foms/platform/blueprints.py`, `app.py`, `run.py`, `start.sh`, `Procfile` 등 **freeze 목록**은 Wave 6 서비스 배치로 변경하지 않는다.  
- Wave 7(대규모 테스트 재설계), Wave 8(대량 shim 제거) 본편을 Wave 6에서 선행하지 않는다.

## 선례 (건드리지 않음)

- `foms/services/jobs/`, `foms/services/erp_policy_internal/`, 공개 `foms/services/erp_policy.py` 패턴은 **이미 검증된 패키지 선례**다. Wave 6에서 공개 표면을 깨는 방향으로 재구조화하지 않는다.

## Wave 6 status register (요약)

> **Authoritative 표:** `docs/plans/2026-04-14-wave6-batch6-status-register-run-record.md` §3  
> **Closeout:** `docs/plans/2026-04-14-wave6-batch7-closeout-run-record.md` (full)

| 구분 | 레인 예시 | Wave 6 execution state (요약) |
|------|-----------|-------------------------------|
| Pilot 완료 | `notifications`, `files` (helper) | canonical package 경로 확정; Wave 8에서 flat/root compat shim **제거 완료** (W8-B3) |
| 이미 패키지 선례 | `jobs`, `erp_policy` public 패턴 | completed — 본 wave 이동 대상 아님 |
| WR-B1 (strict) | `business_calendar` | canonical `foms/services/common/`; root shim — `tests/contracts/...foms_namespace_surface_tests.py` |
| High-risk defer | `storage`, `channel_*`, orders/ERP/measurement clusters, bootstrap-adjacent | not started — 별도 batch |

## Wave 8 bridge retirement (요약)

> **Authoritative 표:** `docs/plans/2026-04-14-wave8-batch6-status-register-run-record.md`  
> **Closeout:** `docs/plans/2026-04-14-wave8-batch7-closeout-run-record.md`

Service-compat mainline (W8-B3)와 `apps/*` direct-import mainline (W8-B5)은 동일 날짜 run record에 봉인된다. `apps/`·`foms/api`·`foms/web` 전체 bridge 상태는 Wave 8 표를 따른다.


# Wave 2 Batch W2-B2 — Spec–live reconciliation + bridge debt register

> **batch ID:** W2-B2  
> **risk axis:** governance / docs  
> **live truth source:** `foms/platform/blueprints.py` + W2-B1 run record  
> **controlling spec:** `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`  
> **실행일:** 2026-04-13

## 1. 요약

- §2.3 domain 표와 W2-B1 live map을 대조하고, **과장된 “전부 thin” 오해**를 막기 위해 controlling spec에 **§2.3.2**를 추가했다.
- **surface-level authoritative** 세부는 본 run record의 **bridge debt register**와 W2-B1 표가 우선한다.
- 각 debt row에 **ID**를 부여해 W2-B4 adapter matrix가 참조한다.

## 2. Reconcile 결과 (요약)

| 주제 | 조치 |
|------|------|
| Orders bridge 열 | “`*` 전부 thin wrapper” → **overlay + thin 선례 명시**로 보정 (spec 표) |
| Measurement | canonical alias shim **이미 존재**; debt는 **registry import 경로 제거 시점** |
| `apps/` 운영 문구 | “thin adapter role” = **신규 작업 기본값**, 기존 코드 전체 thin 아님 → §2.3.2에 명시 |

## 3. Bridge debt register

> **W2-B4 adapter matrix**는 아래 `id` 열을 참조한다.

| id | surface (모듈·주요 symbol) | current owner state | canonical target (요약) | next intended wave | why not thin adapter yet | unblock condition |
|----|------------------------------|----------------------|---------------------------|-------------------|----------------------------|-------------------|
| BD-001 | `apps.auth` (`auth_bp`, `get_user_by_id`) | legacy owner | `foms/web/auth`, `foms/api/auth`, `foms/services/auth` | Wave 4+ | 세션·로그인·비밀번호 로직이 `apps`에 잔존 | auth vertical slice 승인 + route 이전 계획 |
| BD-002 | `apps.erp`, `apps.erp_dashboard`, `apps.erp_history_page` | legacy owner | `foms/web/erp` 계열 | Wave 4 | ERP 허브·페이지 owner | 페이지 chunk migration |
| BD-003 | `apps.erp_measurement_dashboard`, `apps.api.erp_measurement` | canonical alias shim | `foms/web/measurement`, `foms/api/measurement` | Wave 8 | 이미 canonical; **debt = import 경로 철거** | `blueprints.py`가 `foms.*`만 import해도 contract 동일함을 검증 |
| BD-004 | `apps.api.erp_map` | legacy owner | `foms/api/measurement` family | Wave 3 | 대형 로직·`apps` blueprint | helper extraction + shell 축소 |
| BD-005 | `apps.api.orders` (`orders_bp`) | thin adapter | `foms/api/orders` | Wave 3 확장 선행 | **이미** `foms.api.orders` 위임 | 다른 `erp_orders_*`에 패턴 복제 시 검증 필요 |
| BD-006 | `apps.api.erp_orders_*` (drawing~completion, confirm, estimates 등) | legacy owner | 각 context `foms/api/*` | Wave 3 | route·정책이 `apps`에 남음 | read-heavy API부터 순차 canonicalization |
| BD-007 | `apps.order_pages`, `order_edit`, `order_trash`, `excel_import`, `calendar_page` | legacy owner | `foms/web/orders` | Wave 4 | page/UI owner | template/JS slice 계획 |
| BD-008 | `apps.api.files`, `address`, `notifications` | legacy owner | `foms/api/files`, address, notifications | Wave 3 | API-first이나 overlay owner | API 패치 batch |
| BD-009 | `apps.api.attachments` | mixed owner | `foms/api/files` | Wave 3 | 일부 service 위임·BP owner는 `apps` | split-brain 축소 계획 |
| BD-010 | `apps.erp_*_page` (shipment, drawing, as, production, construction, completion) | legacy owner | 각 `foms/web/*` | Wave 4 | page slice | vertical slice 승인 |
| BD-011 | `apps.storage_dashboard` | legacy owner | `foms/web` storage UI | Wave 4 | page owner | — |
| BD-012 | `apps.api.chat` (`chat_bp`, `register_chat_socketio_handlers`) | legacy owner | `foms/api/chat`, platform realtime | Wave 3+ | HTTP+socket 동시 | realtime contract freeze |
| BD-013 | `apps.api.wdcalculator`, `apps.wdplanner_page` | legacy owner | `foms/web|api|services/wdcalculator` | Wave 5 | 대형 프론트·API 동반 | chunk-first 계획 |
| BD-014 | `apps.api.backup`, `debug`, `tasks`, `events`, `quest` | legacy owner | `foms/api/admin` 등 | Wave 3 | 운영·부가 API | 우선순위 낮음 |
| BD-015 | `apps.admin`, `user_pages`, `dashboards` | legacy owner | `foms/web/admin` 등 | Wave 4 | admin UI | — |
| BD-016 | `apps.api.channel_*` (`channel_integration`…`channel_wam` 3BP) | legacy owner | `foms/api/channel` | Wave 3 | 채널 정책·웹훅 복잡 | security review 포함 batch |
| BD-017 | `apps.api.personal_board` | legacy owner | `foms/api/*` | Wave 3 | ERP 보조 | — |
| BD-018 | `apps.api.erp_shipment_settings` | legacy owner | `foms/api/shipment` | Wave 3 | 설정 API | — |
| BD-019 | `apps.api.erp_orders_blueprint`, `erp_orders_structured` | legacy owner | `foms/api/orders` | Wave 3 | structured JSONB 경로 | mutation contract 동반 |

## 4. Direction Lock (§7.2 요약)

1. live truth 사용? **예**  
2. thin 과장 방지? **예**  
3. 새 장기 route in apps? **아니오**  
4. registry contract 유지? **예**  
5. docs 우선? **예 (spec §2.3.2 추가)**  
6. naming 충돌 없음? **예**  
7–8. README? **B2 해당 없음**  
9. 오해 방지? **예**  
10. Wave 3 용이성? **debt ID로 추적 가능**

## 5. Verification

| 검사 | 결과 |
|------|------|
| spec이 live registry 부정 안 함 | ✅ |
| debt row에 owner 또는 TBD+unblock | ✅ |
| sibling inventory 미추가 | ✅ |

## 6. 산출물

- 본 파일  
- `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md` (§2.3 표 보정, §2.3.2 추가)

---

**touched files:** `docs/plans/2026-04-13-wave2-batch2-spec-live-reconcile-run-record.md`, `docs/specs/2026-04-13-foms-modular-monolith-rebaseline_SPEC.md`  
**verification result:** PASS  
**residual risk:** Wave 3에서 `BD-006` vs `BD-005` 패턴 혼동 방지 필요

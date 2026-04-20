# Wave 6 Batch W6-B1 — Root shim registry + package-map lock

> **batch ID:** W6-B1  
> **risk axis:** docs / contract  
> **실행일:** 2026-04-13  
> **Attempt:** 1 — **completed**  
> **선행:** `docs/plans/2026-04-14-wave6-batch0-readiness-gate-run-record.md` (**Branch A**)  
> **상위 계획:** `docs/plans/2026-04-14-wave6-service-namespace-rationalization-execution-plan.md` §5.2

## 1. Scope lock

| 허용 | 금지 |
|------|------|
| 본 run record + `foms/services/README.md` | product/runtime 코드 변경 |
| | 루트 `services/` 동작/내용 변경 |
| | sibling inventory 문서 신설 |

## 2. Inputs consumed

| 문서 | 용도 |
|------|------|
| `W6-B0` run record | authoritative queue, Branch A, import debt, pilot 순서 |
| Live `services/**/*.py`, `foms/services/**/*.py` | shim 여부·파일 목록 |
| 계획서 §2.4 package target map | provisional canonical target |

## 3. Contract table — root shim registry (dual-axis)

### 3.1 클러스터 요약 (동일 정책 공유 행)

| Cluster ID | `queue class` | `root shim status` (대표) | `current owner` | `future canonical target` | `retirement wave` | `removal condition` | `why-not-now` |
|-------------|---------------|----------------------------|-----------------|----------------------------|-------------------|---------------------|----------------|
| **C_NOTIF** | mainline-pilot | shim-only | `foms.services.realtime_notifications` | `foms/services/notifications/realtime_notifications.py` | Wave 8+ | 루트/flat import 0 + 테스트 통과 | `W6-B3`에서 패키지화 예정 |
| **C_FILES** | mainline-pilot | shim-only | `foms.services.file_utils` | `foms/services/files/file_utils.py` | Wave 8+ | 동일 | `W6-B5`에서 패키지화 예정 |
| **C_BCAL** | explicit exception | **explicit exception implementation** | live: `services.business_calendar` (루트 구현) | `foms/services/common/business_calendar.py` | TBD (승인 후) | SPEC §1.2.16 승인 + import debt 청산 | controlling spec 승인 게이트 |
| **C_JOBS** | already packaged precedent | shim-only | `foms.services.jobs.*` | `foms/services/jobs/*` (유지) | Wave 8+ | 레거시 `services.jobs.*` 제거 시 | Wave 6 mainline 이동 대상 아님 |
| **C_ERP_WRAP** | already packaged precedent | shim-only (re-export) | `foms.services.erp_policy` | `foms/services/erp_policy.py` 유지 | — | public wrapper 유지 정책 | 추가 리팩터는 defer 행 |
| **C_STORAGE** | high-risk defer | shim-only | `foms.services.storage` | `foms/services/files/storage.py` | Wave 7 문서화 후 | singleton/호출자 정리 | 런타임 init·fan-in |
| **C_CHANNEL** | high-risk defer | shim-only | `foms.services.channel_*` | `foms/services/channel/*` (장기) | Wave 8+ | webhook/read-model 정리 후 | full family move 금지 |
| **C_ORDERS** | high-risk defer | shim-only | 각 `foms.services.*` | `foms/services/orders/*` (장기) | Wave 8+ | 단일 파일럿 축소 후 | Tier 3 cluster |
| **C_MEAS** | high-risk defer | shim-only | 각 flat 모듈 | `foms/services/measurement/*` 또는 일부 `common/*` | Wave 8+ | 맵/컨텍스트 확정 후 | 경계 혼재 |
| **C_PLATFORM** | high-risk defer | shim-only | `foms.services.*` | `foms/services/admin/*` 또는 explicit exception 유지 | Wave 8+ | bootstrap 분리 | 플랫폼 결합 |
| **C_MISC** | high-risk defer | shim-only | 해당 canonical | flat 유지 또는 컨텍스트 편입 | Wave 8+ | lane별 결정 | 파일럿 후보 아님 |

### 3.2 루트 `services/*.py` / `services/jobs/*.py` 전 파일 인덱스 (authoritative row list)

`root shim status`: **shim-only** = docstring상 compatibility/legacy shim이며 구현은 `foms.services`에 위임. **explicit exception implementation** = `business_calendar`만 해당.

| `services/` path | Cluster | `queue class` | `root shim status` |
|------------------|---------|---------------|----------------------|
| `__init__.py` | — (패키지 마커) | (레지스트리 대상 외) | — |
| `app_init.py` | C_PLATFORM | high-risk defer | shim-only |
| `as_content_safety.py` | C_MISC | high-risk defer | shim-only |
| `business_calendar.py` | C_BCAL | explicit exception | **explicit exception implementation** |
| `channel_client.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_delivery.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_dispatch.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_event_payloads.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_identity.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_inbound.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_policy.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_quick_actions.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_security.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_wam_attachments.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_wam_read_model.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_wam_service.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_wam_telemetry.py` | C_CHANNEL | high-risk defer | shim-only |
| `channel_wam_view_models.py` | C_CHANNEL | high-risk defer | shim-only |
| `context_processors.py` | C_PLATFORM | high-risk defer | shim-only |
| `db_indexes.py` | C_PLATFORM | high-risk defer | shim-only |
| `db_url_resolver.py` | C_PLATFORM | high-risk defer | shim-only |
| `erp_display.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_order_detail.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_permissions.py` | C_PLATFORM | high-risk defer | shim-only |
| `erp_policy.py` | C_ERP_WRAP | already packaged precedent | shim-only |
| `erp_product_items.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_shipment_settings.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_sync_columns.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_template_filters.py` | C_ORDERS | high-risk defer | shim-only |
| `erp_utils.py` | C_ORDERS | high-risk defer | shim-only |
| `estimate_service.py` | C_ORDERS | high-risk defer | shim-only |
| `file_utils.py` | C_FILES | mainline-pilot | shim-only |
| `geocode_helpers.py` | C_MEAS | high-risk defer | shim-only |
| `jobs/__init__.py` | C_JOBS | already packaged precedent | shim-only (package) |
| `jobs/queue.py` | C_JOBS | already packaged precedent | shim-only |
| `jobs/tasks.py` | C_JOBS | already packaged precedent | shim-only |
| `map_snapshot.py` | C_MEAS | high-risk defer | shim-only |
| `measurement_manager_colors.py` | C_MEAS | high-risk defer | shim-only |
| `menu_config.py` | C_PLATFORM | high-risk defer | shim-only |
| `order_attachment_thumbnail.py` | C_ORDERS | high-risk defer | shim-only |
| `order_date_sync.py` | C_ORDERS | high-risk defer | shim-only |
| `order_date_sync_event.py` | C_ORDERS | high-risk defer | shim-only |
| `order_display_utils.py` | C_ORDERS | high-risk defer | shim-only |
| `order_geocode.py` | C_MEAS | high-risk defer | shim-only |
| `order_storage_cleanup.py` | C_ORDERS | high-risk defer | shim-only |
| `rate_limit.py` | C_PLATFORM | high-risk defer | shim-only |
| `realtime_notifications.py` | C_NOTIF | mainline-pilot | shim-only |
| `request_utils.py` | C_PLATFORM | high-risk defer | shim-only |
| `storage.py` | C_STORAGE | high-risk defer | shim-only |
| `user_deletion.py` | C_MISC | high-risk defer | shim-only |

**검증:** PowerShell `Get-ChildItem services -Recurse -Filter *.py` → **50**개. 위 표는 `services/__init__.py`부터 `services/user_deletion.py`까지 **모듈 파일 50행** (루트·`jobs/` 포함).

### 3.3 Explicit exception 행 (`business_calendar`)

| 항목 | 값 |
|------|-----|
| Lane | `services.business_calendar` — 루트에 **live 구현**; `foms/services/business_calendar.py` **없음** (향후 `foms/services/common/`). |
| Future canonical target | `foms/services/common/business_calendar.py` (provisional) |
| Approval gate | controlling spec §1.2.16 — Wave 6 mainline **code pilot 금지** |
| Live import debt callers | `W6-B0` import debt 표와 동일 |

## 4. FR19 / NS-package-first (§7 항목 5)

본 batch는 **루트/`foms` 코드 변경 없이** 레지스트리·README만 고정. 신규 패키지 디렉터리 **추가 없음**. `delete → merge → extend → add`는 **파일럿 코드 배치(`W6-B3`, `W6-B5`)**에서 적용.

## 5. Authoritative package map (요약)

`foms/services/README.md`에 전체 서술. 컨텍스트: `notifications`, `files`, `common`(예외), `channel`, `orders`, `measurement`, `jobs`, `erp_policy`, platform-adjacent — 계획서 §5.2 step 5 충족.

## 6. Changes made

- `docs/plans/2026-04-14-wave6-batch1-shim-registry-run-record.md` 생성·완성 (본 파일)
- `foms/services/README.md` 생성

## 7. Verification (§6)

| 검사 | 결과 |
|------|------|
| docs-only consistency | 본 registry 표·`foms/services/README.md`·`W6-B0` queue가 서로 모순 없음 |
| repo sanity baseline | **`W6-B0`에서 채택한 fresh baseline 인용** — 본 batch에서 코드 변경 없음; `APP_OK`/`verify_result` 재실행 불필요(§6 docs-only). |

## 8. Direction Lock (10문항)

| # | 답 | 한 줄 근거 |
|---|-----|------------|
| 1 | yes | 루트·클러스터·shim 축이 문서로 SoT 고정 |
| 2 | yes | shim 유지 명시; 제거는 retirement wave로만 |
| 3 | yes | 신규 leaf 추가 없음 |
| 4 | N/A | 패키지 디렉터리 미추가 |
| 5 | yes | 코드 변경 0 |
| 6 | N/A | 코드 delta 없음 |
| 7 | yes | `foms/services/README.md` 본 batch에서 생성 |
| 8 | yes | 반복 시에도 맵·예외·defer가 누적 가능 |
| 9 | yes | service 문서 vs 런타임 코드 경계 유지 |
| 10 | yes | 문서만 |

## 9. §7 항목 보충

| 항목 | 내용 |
|------|------|
| 9 product/wrapper/test | N/A (no code touch) |
| 10–13 canonical/flat/root/retirement | 클러스터 표 §3.1 및 per-file §3.2; dual-axis authoritative는 본 batch에서 잠금 |
| 14 README | **갱신됨** — `foms/services/README.md` 생성 |
| 15 row type / execution | unchanged from **W6-B0** initial snapshot except **shim registry now authoritative** for `root shim status` column |
| 16 drift/stop/defer | drift 없음; stop 없음 |
| 17 lint/diagnostics | not applicable — docs-only |

## 10. Outcome

**PASS —** `W6-B1` 완료.

**Next legal batch (Branch A):** `W6-B2` — Notifications contract freeze (`docs/plans/2026-04-14-wave6-batch2-notifications-contract-freeze-run-record.md`, 계획서 §5.3).

# perf-guard Trigger Matrix

diff touched → mandatory manual proof (exit 0 alone = **배포 금지**):

| touched | proof |
|---------|-------|
| `templates/partials/shared/`, `erp_order_js` | shared JS/CSS weight, defer/lazy |
| `static/sw.js` | timeout + cache fallback |
| shell bundles / mobile shell JS | `window.__*_BOUND` singleton |
| `services/dashboard`, `services/search` | N+1, `.limit`, cache |
| `structured_data` filter/search | ILIKE + EXPLAIN index |
| **새 ERP 탭/fragment `*scripts*.html` 에 `<script src>` 추가** | fragment 다중 script = 셸 스왑마다 재실행(실측탭 5.8s). entry singleton 1개로 통합 강제 + G4/PTC/defer 계약 갱신 |
| **mutation API 신설(invalidate 호출)** | 티어 무효화 helper(`invalidate_order_dashboard_families`/`invalidate_dashboard_families`) 사용. 통무효화(`invalidate_all_dashboard_slice_caches`) 금지 — 전 탭 miss 폭풍(2026-07 22곳) |
| **캐시 slice 신설** | fingerprint 휘발성 금지(order_ids류=매번 무효화). compute_ms > Redis 왕복(~1ms) 확인 후 캐싱 |
| **`structured_data[...]` path 필터 신설** | 무인덱스 풀스캔. flat sync 컬럼(`erp_stage_code` 패턴)+인덱스+EXPLAIN(생산탭 1,894→59행) |
| **`build_mobile_queue_order_row` 호출** | `batch_ctx` 전달 필수(행당 N+1, 실측 1,500쿼리). `build_mobile_queue_batch_context` 선행 |
| **`NO_FRAGMENT_CACHE_PATHS` 추가** | 금지 — FRESH_TTL + `invalidateFragmentCache`가 정답. 캐시 무력화는 tail 재발 |

Read `docs/guides/PERFORMANCE_GUARDRAILS.md` §A manual checklist for full list.

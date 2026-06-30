# perf-guard Trigger Matrix

diff touched → mandatory manual proof (exit 0 alone = **배포 금지**):

| touched | proof |
|---------|-------|
| `templates/partials/shared/`, `erp_order_js` | shared JS/CSS weight, defer/lazy |
| `static/sw.js` | timeout + cache fallback |
| shell bundles / mobile shell JS | `window.__*_BOUND` singleton |
| `services/dashboard`, `services/search` | N+1, `.limit`, cache |
| `structured_data` filter/search | ILIKE + EXPLAIN index |

Read `docs/guides/PERFORMANCE_GUARDRAILS.md` §A manual checklist for full list.

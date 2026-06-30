# perf-guard Manual Checklist (L2)

Static scan misses — verify on diff:

- [ ] `structured_data … ilike` → trigram index via EXPLAIN
- [ ] list loop per-order query → `in_(ids)` batch
- [ ] heavy per-request aggregate → Redis micro-cache
- [ ] page-specific heavy JS not in shared partial
- [ ] SW fetch change keeps timeout + cache fallback
- [ ] fragment-replayed JS global listeners guarded

Escape: `# perf-ok` or allowlist in `test_perf_regression_guard.py` (review required).

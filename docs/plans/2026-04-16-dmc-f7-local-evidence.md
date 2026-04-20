# DMC-F7 — 운영·로컬 증거 (Dashboard micro-cache)

## 로컬 (저장소, CI 동등)

| 증거 | 내용 |
|------|------|
| hit ≥1 / miss ≥1 + `compute_ms` | `pytest tests/domains/test_dashboard_cache.py::test_get_or_compute_logs_compute_ms_hit_and_miss` — 첫 호출 `result=miss compute_ms=<n>`, 두 번째 `result=hit compute_ms=0` |
| cache on/off 동등성 | `test_dmc_b6_differential_same_payload_cache_on_vs_off` |
| Redis 없음 HTTP 200 | `tests/domains/test_dashboard_micro_cache_http_fallback.py` |
| 앱·하네스 | `python -c "import app; print('APP_OK')"`, `python tools/harness/verify_result.py --json` |

## Railway / prod-like (선택)

- 전체 라우트 **p50/p95**는 Railway 메트릭·앱 로그에서 `[DashCache] ... result=hit|miss compute_ms=...` 샘플을 수집해 본 문서 또는 별도 `2026-04-16-dmc-f7-railway-evidence.md`에 첨부한다.
- 로컬 단위 테스트만으로는 **실제 HTTP latency before/after**를 대체하지 않는다.

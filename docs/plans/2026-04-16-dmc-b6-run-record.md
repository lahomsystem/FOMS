# DMC-B6 — 실측 검증 및 closeout (Dashboard micro-cache tranche)

## 범위
- 계획서: `docs/plans/2026-04-16-dashboard-micro-cache-execution-plan.md` §4.5·§5 closeout 조건 충족 여부 기록.
- 구현은 DMC-B1~B5에서 완료된 상태를 전제로, **검증·증거·문서 동기화**를 본 배치에서 마감한다.

## 검증 증거 (로컬, `HEAD` 기준)
| 항목 | 명령 / 결과 |
|------|-------------|
| APP import | `python -c "import app; print('APP_OK')"` → `APP_OK` |
| Harness | `python tools/harness/verify_result.py --json` → `success: true` |
| Cache helper + differential + Redis 없음 HTTP | `pytest tests/domains/test_dashboard_cache.py tests/domains/test_dashboard_micro_cache_http_fallback.py` → green |
| 회귀 (대시보드·모바일) | `pytest tests/domains/test_erp_order_detail_preload.py::test_erp_dashboard_includes_preloaded_order_detail_payload`, `test_erp_measurement_mobile_render.py`, `test_erp_mobile_layout_and_shipment.py` → green |

## 계약 확인
- **migration / schema / template 구조 변경 없음** (본 tranche는 Python·테스트·문서만).
- **전체 HTML 캐시 없음**; JSON-serializable slice만.
- **Redis 없음**: `REDIS_URL` 미설정 + flag on이어도 `/erp/dashboard`, `/erp/measurement`, `/erp/shipment` **200** (`test_dashboard_micro_cache_http_fallback.py`).
- **cache on/off 동등성**: 동일 deterministic payload에 대해 off 경로와 on(hit) 경로가 같은 dict (`test_dmc_b6_differential_same_payload_cache_on_vs_off`).
- **invalidate**: 성공적인 `db.commit()` 이후 및 `order_date_sync` `after_commit` 경계 (B5).

## 실측 latency (Railway / prod-like)
- 본 run record는 **로컬 pytest·앱 부트** 증거만 포함한다.
- **p50/p95·hit ratio**는 Railway 대시보드·앱 로그에서 `dashboard_cache` hit/miss·경고 로그를 샘플링해 별도 운영 메모로 보강하는 것을 권장한다 (코드 변경 불필요).

## Closeout 선언
- DMC-B1~B6 요구사항 중 코드·테스트·fail-open·invalidation 경계는 충족.
- **후속 (DMC-F, 2026-04-16):** 계획서 §3.1.1 1:1 보강 — `order_detail_payload_assembly`, measurement/shipment slice 명시 DTO, `compute_ms` 로깅. 상세는 `docs/plans/2026-04-16-dmc-f-run-record.md` 참고.
- 남은 것은 **Railway·prod HTTP latency** 스냅샷(선택)이며, 기능 diff 0·시맨틱 보존은 테스트로 고정됨.

# Harness evidence (`docs/harness/evidence/`)

재현 가능한 스테이징·HTTP·브라우저 측정 JSON을 둔다. **Run record·실행 계획서가 인용하는 경로가 권위**이며, 임의 삭제 시 문서와 불일치가 난다.

## 2026-04-17 GNV / EPT 배치

| 접두 | 용도 |
|------|------|
| `2026-04-17-ept-b8-*.json` | EPT-B8: 스테이징 HTTP·Playwright (탭 스왑·G1·왕복 등). 상세: `docs/plans/2026-04-17-ept-b8-verification-railway-evidence-run-record.md` |
| `2026-04-17-gnv-b6-*.json` | GNV-B6: HTTP·브라우저 메트릭. **배포 후 closeout**은 `*-post-push.json` 접미사. 상세: `docs/plans/2026-04-17-gnv-run-record.md` |

동일 날짜에 **pre-push**와 **post-push**가 모두 있으면, closeout·감리 표는 run record에 적힌 쪽(보통 **post-push**)을 따른다.

## 재실행

재현 스크립트는 2026-07-08 재설계 Phase 1b에서 원샷 아카이브(`docs/archive/oneoff-scripts/`)로 이관됐다.

- GNV B6 HTTP: `docs/archive/oneoff-scripts/gnv_b6_staging_http_evidence.py`
- GNV B6 브라우저: `docs/archive/oneoff-scripts/gnv_b6_staging_browser_metrics.py`
- EPT B8: `docs/archive/oneoff-scripts/ept_b8_staging_http_evidence.py`, `docs/archive/oneoff-scripts/ept_b8_staging_full_evidence.ps1` (환경 변수는 `docs/archive/oneoff-scripts/ept_b8_staging_env.example` 참고)

## Retention (perf-gate / stress)

`perf-gate-*.json`·`stress-*.json`·`fragment-tail-ttfb-*.json`는 타임스탬프별로 누적된다. **run record·`DECISIONS.md`·실행 계획서가 인용하는 파일과 각 캠페인의 최신 대표 1벌만 보존**하고, 그 외 반복 측정본은 정리 대상이다. `perf-radar-latest.json`처럼 `-latest` 접미사 파일은 항상 최신 1벌만 유지(덮어쓰기)한다. 삭제 전에는 위 "권위" 규칙대로 인용 경로를 grep으로 확인한다.

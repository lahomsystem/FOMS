# Harness evidence (`docs/harness/evidence/`)

재현 가능한 스테이징·HTTP·브라우저 측정 JSON을 둔다. **Run record·실행 계획서가 인용하는 경로가 권위**이며, 임의 삭제 시 문서와 불일치가 난다.

## 2026-04-17 GNV / EPT 배치

| 접두 | 용도 |
|------|------|
| `2026-04-17-ept-b8-*.json` | EPT-B8: 스테이징 HTTP·Playwright (탭 스왑·G1·왕복 등). 상세: `docs/plans/2026-04-17-ept-b8-verification-railway-evidence-run-record.md` |
| `2026-04-17-gnv-b6-*.json` | GNV-B6: HTTP·브라우저 메트릭. **배포 후 closeout**은 `*-post-push.json` 접미사. 상세: `docs/plans/2026-04-17-gnv-run-record.md` |

동일 날짜에 **pre-push**와 **post-push**가 모두 있으면, closeout·감리 표는 run record에 적힌 쪽(보통 **post-push**)을 따른다.

## 재실행

- GNV B6 HTTP: `tools/harness/gnv_b6_staging_http_evidence.py`
- GNV B6 브라우저: `tools/harness/gnv_b6_staging_browser_metrics.py`
- EPT B8: `tools/harness/ept_b8_staging_http_evidence.py`, `tools/harness/ept_b8_staging_full_evidence.ps1` (환경 변수는 `tools/harness/ept_b8_staging_env.example` 참고)

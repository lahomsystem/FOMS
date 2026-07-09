# One-off scripts archive

완료된 이니셔티브에서 쓰이고 더는 상시 운영 표면에 둘 필요가 없는 **일회성 스크립트**를 보관한다. 2026-07-08 하네스 재설계 Phase 1b(`docs/plans/2026-07-08-harness-control-system-redesign-report.md` §8.4 Phase 1)에서 `tools/harness/`·`scripts/ops/`의 상주 원샷을 여기로 `git mv`로 이관했다.

- **왜 삭제가 아니라 이관인가**: git 이력은 어디에 두든 보존되지만, 재현·감사 시 원문을 바로 열 수 있도록 실행 파일 형태를 남긴다. 활성 운영 진입점(`tools/harness/`, `scripts/ops/`)에서는 제거해 죽은 표면을 줄인다.
- **주의**: 아카이브 위치로 옮겨졌으므로 저장소 루트 상대 경로나 인접 파일을 가정하는 스크립트는 그대로 실행하면 경로가 어긋날 수 있다. 재실행이 필요하면 경로를 확인하고 실행한다.
- **되돌리기**: 필요 시 `git mv`로 원위치로 복원 가능(완전 가역).

## 이관 목록

| 파일 | 원위치 | 무엇/왜 |
|------|--------|---------|
| `ept_b8_staging_browser_metrics.py` | `tools/harness/` | EPT-B8(2026-04-17) 스테이징 브라우저 메트릭 재현 |
| `ept_b8_staging_http_evidence.py` | `tools/harness/` | EPT-B8 스테이징 HTTP 증거 재현 |
| `ept_b8_staging_full_evidence.ps1` | `tools/harness/` | EPT-B8 전체 증거 수집 오케스트레이션 |
| `ept_b8_staging_env.example` | `tools/harness/` | EPT-B8 재현용 env 예시 |
| `gnv_b6_staging_browser_metrics.py` | `tools/harness/` | GNV-B6(2026-04-17) 스테이징 브라우저 메트릭 재현 |
| `gnv_b6_staging_http_evidence.py` | `tools/harness/` | GNV-B6 스테이징 HTTP 증거 재현 |
| `erp_beta_flat_placeholder_backfill_apply.sql` | `tools/harness/` | ERP beta 은퇴(2026-04-18) placeholder 백필 apply |
| `erp_beta_flat_placeholder_backfill_dryrun.sql` | `tools/harness/` | 위 백필 dry-run |
| `erp_beta_flat_placeholder_backfill_verify.sql` | `tools/harness/` | 위 백필 검증 |
| `erp_beta_retirement_g_data_readonly.sql` | `tools/harness/` | ERP beta 은퇴 G-data read-only 스냅샷 |
| `run_erp_beta_placeholder_backfill.ps1` | `tools/harness/` | 위 백필 실행 래퍼 |
| `railway_db_gate_snapshot.py` | `tools/harness/` | Railway DB 게이트 스냅샷(일회성 ops) |
| `railway_db_gate_snapshot_ssh.py` | `tools/harness/` | 위 스냅샷 SSH 변형 |
| `cleanup_skill_duplicates.ps1` | `tools/harness/` | 스킬 중복 정리(1회성). `docs/harness/SKILL_DUPLICATE_AUDIT.md` 참조 |
| `add_geocode_cols_railway.py` | `scripts/ops/` | Railway geocode 컬럼 추가 마이그레이션(1회성) |
| `verify_phase_d.py` | `scripts/ops/` | Phase D 검증(1회성) |
| `prune_duplicate_perf_skills.ps1` | `scripts/ops/` | perf 스킬 중복 제거(1회성). `docs/guides/PERF_SKILLS_ROUTING.md` 참조 |
| `simple_backup_system.py` | `scripts/ops/` | 백업 기능 2026-06-05 은퇴 후 남은 CLI 위임 shim (`docs/harness/policy/DECISIONS.md` [2026-06-05]) |

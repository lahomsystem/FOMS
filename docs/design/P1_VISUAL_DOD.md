# P1 Visual / Mockup Definition of Done

> **SSOT**: `docs/design/MOBILE_TABLET_REDESIGN_PLAN.md` §6 + `docs/design/mockups/*.html`  
> **분리**: P1 **wiring** 게이트(`MIGRATION_ROADMAP.md` P1 완료 게이트)와 **visual/mockup** 게이트는 별도 트랙이다.

## 완료 조건 (한 줄)

cohort 사용자 + `/erp/*` + viewport별로 **mockup 4종 IA/컴포넌트/토큰이 DOM+screenshot으로 일치**하고, **데스크톱 ≥992px 회귀 0**, **pytest mockup gate PASS**, **Railway deploy 반영**.

## 게이트 A — Wiring (기존 P1)

| 항목 | 검증 |
|---|---|
| Bottom nav + 배지 | `test_p1_mobile_ux_smoke.py` |
| Search overlay | 동일 |
| Wizard API / draft | `test_p1_gate.py` |
| Split HTMX DOM | 동일 |
| Flag default | wizard/inline/split OFF, mobile v2 cohort |

## 게이트 B — Visual / Mockup (본 문서)

### B1. 배포·cohort

- [x] P1 시각 파일(`foms-shell.css`, `dashboard_mobile_v2_body`, queue card v2, detail partials) **deploy 브랜치 커밋·push** (2026-05-31 갭 재검증 G0)
- [ ] Railway: `ERP_MOBILE_V2_ENABLED=true`, `FOMS_V3_SHELL_COHORT=all` (또는 파일럿 id) — **staging 실측 필수**
- [x] `scripts/ops/verify_mobile_v2_rollout.ps1` PASS (로컬)
- [x] `scripts/ops/staging_mobile_v2_smoke.ps1` static asset HEAD (staging URL)

### B2. Mockup 4종 (REDESIGN §6)

| Mockup | DOM/IA 체크 | Visual (390×844) |
|---|---|---|
| mobile-home-dashboard | chip-strip (전체·오늘·미처리·긴급·담당), section-header, queue-card+thumb, FAB, sort(최신·일정·금액), mobile_chunk IO | Playwright baseline vs `docs/design/mockups/` (**backlog**) |
| mobile-order-detail | hero, quick×4, KV 4섹션(고객·일정·제품·금액), attach-grid+lightbox, timeline, sticky CTA | 동일 (**backlog**) |
| mobile-wizard-new-order | stepper, C14 accordion, summary | 동일 |
| tablet-split-view | 72+360+fluid master cards | 1280×800 baseline |

### B3. 컴포넌트 C01–C14

| ID | DoD |
|---|---|
| C01 | `foms_app_shell.html` 단일 chrome 진입 |
| C05 | queue-card v2 on home (+ tab별 점진 rollout) |
| C07 | attach grid on mobile detail + lightbox (`data-foms-lightbox-gallery`) |
| C14 | wizard step2 product accordion + `product-item.js` |

### B4. ERP 8탭

- [ ] `foms-shell-desktop-only` 또는 동등 CSS로 **legacy header/nav/grid mobile hide**
- [ ] 홈: `dashboard_mobile_v2_body` full §6.2
- [ ] 기타 탭: 기존 mobile partial 유지 + mockup parity backlog

### B5. 토큰 D09 phase 2

- [ ] `--erp-mobile-*` → `--foms-*` alias (`10-erp-mobile-v2-shell.css`)
- [ ] Pretendard on `/erp/*` when cohort ON

### B6. 자동 테스트

| 테스트 | 역할 |
|---|---|
| `tests/visual/test_p1_mockup_structure.py` | DOM class contract |
| `tests/visual/test_p1_mockup_visual_gate.py` | mockup HTML ↔ app class parity |
| `tests/visual/test_p1_mockup_png_baseline.py` | mockup anchor classes + wizard/split SSOT |
| `tests/visual/test_staging_mobile_v2_assets.py` | deploy asset on-disk gate |
| `tests/visual/test_erp_mobile_v2_shell_regression.py` | desktop/mobile shell PNG |
| Desktop ≥992px | visual baseline diff 0 |

## 명시적 Non-Goals (wiring 게이트만으로 충족 불가)

- 픽셀-perfect without visual baseline
- 8탭 전부 home mockup parity (별도 Phase 2+ backlog)
- gstack QA sign-off (Phase 6 manual/staging)

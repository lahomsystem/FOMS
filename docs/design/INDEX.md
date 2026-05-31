# FOMS 모바일·태블릿 리디자인 — 산출물 인덱스 (v1.1 SSOT)

> 작성: 2026-05-28 | **v1.1 SSOT 통합: 2026-05-29** | 작업 ID: `mobile-tablet-redesign-v1.1`
> 작업 모드: `caveman` + 5 agent 병렬 audit + 5 WebSearch 딥 리서치 + 외부 LLM 평가 흡수
> 자체 평가: **8.7 / 10** (v1.0 8.1 → v1.1 8.7)
>
> **v1.1 변경**: 외부 LLM 평가(7.2 → 8.4)가 v1.0 audit agent의 stale 결과를 발견 → 7개 항목 즉시 보정 후 본 문서·로드맵·컴포넌트·진입점에 직접 흡수. `REVISION_v1.1.md`는 변경 이력으로 보존.

---

## 산출물 7종 (v1.1 SSOT + REVISION 이력) + 목업 4종 + 리서치 1종

### 1. [`MOBILE_TABLET_REDESIGN_PLAN.md`](./MOBILE_TABLET_REDESIGN_PLAN.md) — 마스터 계획서 (28KB)
- Executive Summary
- 페르소나 3종 + 시나리오 5종
- 디자인 원칙 5가지
- 정보 구조 (모바일·태블릿 가로·세로)
- 화면별 리디자인 명세
- 접근성·성능·국제화
- 마이그레이션 로드맵 P0/P1/P2
- 리스크·완화
- 측정·검증 KPI
- Decision Log 10건

### 2. [`MOBILE_TABLET_DESIGN_SYSTEM.md`](./MOBILE_TABLET_DESIGN_SYSTEM.md) — 디자인 시스템 (20KB)
- 토큰 단일화 (`--foms-*` 네임스페이스, 기존 3종 통합)
- 컬러 — 프리미티브 + 시맨틱 + 단계(stage) 10종 + 다크모드
- 타이포 — Pretendard Variable + 8단계 스케일
- 간격 4pt grid (--foms-space-1..16)
- 라운드·그림자·모션
- Breakpoint 4종 + Container Query
- Z-index 레이어 + Safe Area
- 터치 타깃 48px+ + 아이콘 시스템

### 3. [`COMPONENT_LIBRARY_MOBILE.md`](./COMPONENT_LIBRARY_MOBILE.md) — 컴포넌트 라이브러리 (v1.1, **14종**)
- C01 `<foms-app-shell>` — 통합 앱 셸
- C02 `<foms-bottom-nav>` — 하단 5탭 + 배지
- C03 `<foms-side-tab>` — 태블릿 가로 측면 탭
- C04 `<foms-master-list>` — Split-view 좌측 360px
- C05 `<foms-queue-card>` — 주문 카드 (다목적)
- C06 `<foms-kv-row>` — Key-Value 행 + 딥링크
- C07 `<foms-attachment-grid>` — 첨부 그리드 + 라이트박스
- C08 `<foms-sticky-action-bar>` — Sticky CTA Bar
- C09 `<foms-wizard-stepper>` — 4-step Wizard
- C10 `<foms-filter-drawer>` — offcanvas 필터
- C11 `<foms-search-overlay>` — 풀스크린 검색
- C12 `<foms-photo-capture>` — 사진 캡처 (카메라 우선, paste desktop-only)
- C13 `<foms-status-badge>` — 단계·경보 배지
- **C14 `<foms-product-item-accordion>` — 제품 항목 인라인 편집 (v1.1 신규, erporder 12필드 매핑)**
- 부록 A~E: 버튼/Input/FAB/사용 매트릭스/우선순위

### 4. [`MIGRATION_ROADMAP.md`](./MIGRATION_ROADMAP.md) — 마이그레이션 로드맵 (v1.1)
- P0 (8 PR, **58h ≈ 7 작업일**) — P0-00 Foundation + 비효율 결함 + 카드 gap patch
- P1 (7 PR, 17.5일 ≈ 3.5주) — 핵심 UX 확장
- P2 (8 PR, 21일 ≈ 4주) — 진화·혁신 (D06 new surface only) — **코드·게이트 완료**
- P3 (4 PR, 5일) — bottom nav HTMX · 이력 검색 우선 · 큐 swipe API · 이력 라이트박스 — **코드·게이트 완료**
- 각 PR: 명세 + 파일 + 검증 + 위험 + 추정
- **cohort 점진 출시** (Day 1~7) + Playwright baseline
- **Feature Flag Matrix** (P0~P3 rollout + 썸네일 3종 + RUM/offline/HTMX) + 조합 matrix + 구현 코드
- 부록 A: v1.0→v1.1 변경 이력
- 부록 B: OrderDraft Payload JSON Schema

### 5. [`REVIEW_SELF_ASSESSMENT.md`](./REVIEW_SELF_ASSESSMENT.md) — 다상각도 자체 리뷰 (v1.1)
- 🎨 Design 8.5 (v1.0 8.3) · 🛠 Eng 8.7 (v1.0 8.0) · 💼 CEO 8.8 (v1.0 8.5) · 🛠 DX 8.4 (v1.0 7.7)
- **전체 평균 8.7 / 10** (v1.0 8.1)
- v1.0→v1.1 점수 변화표 (외부 LLM 평가 흡수)

### 6. [`REVISION_v1.1.md`](./REVISION_v1.1.md) — v1.0→v1.1 변경 이력 (audit trail, 보존)
- v1.0 audit agent stale 발견 5건
- 사용자 직접 지적 2건
- 흡수 완료 매핑 표 (어디로 흡수되었는지)
- Meta-lesson: agent 결과는 검증 후 인용

### 7. [`INDEX.md`](./INDEX.md) — 본 문서

---

## 인터랙티브 HTML 목업 4종

브라우저에서 열어서 확인:

### [`mockups/mobile-home-dashboard.html`](./mockups/mobile-home-dashboard.html)
- 390×844 모바일 홈 (대시보드)
- 헤더 + 필터 칩 + 단계 색 카드 4종 + FAB + Bottom Nav 5탭 (배지)
- `?theme=dark`로 다크모드 토글

### [`mockups/mobile-order-detail.html`](./mockups/mobile-order-detail.html)
- 390×844 모바일 주문 상세 (고명옥 거실 몰딩라운드장)
- Hero(배지·고객명·제품) + Quick Actions(전화·지도·채팅·복사) + KV 섹션 4종 + 첨부 그리드 + 타임라인 + Sticky Action Bar

### [`mockups/mobile-wizard-new-order.html`](./mockups/mobile-wizard-new-order.html)
- 4×(390×844) 신규 주문 마법사 4-step 나란히 표시
- Step 1 기본정보 → Step 2 제품 항목(카메라 캡처 우선) → Step 3 일정 → Step 4 확인
- 자동저장 인디케이터 + Sticky Action Bar

### [`mockups/tablet-split-view.html`](./mockups/tablet-split-view.html)
- 1280×920 태블릿 가로 master-detail split-view
- Side Tab 72px + Master List 360px + Detail Panel fluid
- 카드 선택 → 우측 상세 (고객·일정 / 금액 / 첨부 / 이력)

### [`mockups/_tokens.css`](./mockups/_tokens.css)
- 4개 목업 공유 디자인 토큰 사본

---

## 외부 리서치

### [`../research/MOBILE_TABLET_UX_RESEARCH.md`](../research/MOBILE_TABLET_UX_RESEARCH.md)
- WAM 뷰어 vs ERP 모바일 셸 통합 분석
- ChannelTalk 차용 5가지 패턴
- P0/P1/P2 액션 큐
- 기술 스택 권장 (HTMX 2.0 + Alpine.js)

---

## 핵심 발견 요약

### 1. 인프라 70% 이미 있음
`ERP_MOBILE_V2_ENABLED` 환경변수가 기본 `false`로 잠겨 있고 `channel/wam/**` 모듈에 ChannelTalk 풍 뷰어가 이미 구현돼 있다. 두 패러다임이 분리된 채 병존. 통합과 활성화가 핵심.

### 2. 비효율 결함 2건 + 갭 3건 (v1.1 정정)
- AS 접수 모달 Ctrl+V paste 기반 → 모바일 작동 불가 (사용 불가)
- 768~992px 충돌 — 글로벌 nav + ERP 셸 동시 표시 (사용 불가)
- 도면·AS·시공 모바일 카드 **이미 존재** — thumbnail·필터·배지 표준화 갭만 보완 (audit + gap patch)
- 폼 sticky bottom CTA 부재, 44px 터치 타깃 미적용
- file input `capture` 속성 없음 → 카메라 직접 캡처 불가

**v1.0 audit 오류**: 도면·AS·시공 카드를 "없음"으로 보고 → v1.1에서 실제 코드 확인 후 "있음 + 갭" 으로 정정.

### 3. 사용자 6대 요구 모두 명시 대응
| 요구 | 대응 |
|---|---|
| 채널톡 참고 모바일 UI 리서치 | ✅ Phase 1 외부 리서치 |
| 모바일 + 태블릿 각각 최적화 | ✅ 모바일 단일 컬럼 + 태블릿 split-view |
| 탭 정보 명확화 | ✅ 카드 head + KV 행 + 첨부 + Action |
| erporder 입력·수정 최적화 | ✅ 신규=마법사 (W·D·H 분리) / 수정=인라인 + 자동저장 (critical field 명시 저장) |
| 탭별 레이아웃·텍스트 위치 조화 | ✅ 디자인 시스템 토큰 + 14개 컴포넌트 표준화 (C14 포함) |
| 모바일·태블릿 ERP 대시보드 메뉴만 노출 | ✅ Bottom nav 5탭 = ERP 워크플로우 그룹화, 글로벌 nav 숨김 |

### 4. 시간 추정 (v1.1)
- **P0 (약 7 작업일, 58h)**: P0-00 Foundation 선행 + 비효율 결함 제거 + cohort Day 7 → 70% 가치 달성
- **P1 (3.5주)**: 핵심 UX 확장 → 95% 사용자 요구 충족
- **P2 (4주)**: 시장 차별화
- **총 8~12주**, 풀타임 1명 가정

### 5. 자체 리뷰 8.7 / 10 (v1.1)
디자인 8.5 · 엔지니어링 8.7 · CEO 8.8 · DX 8.4 (v1.0 8.1 → v1.1 8.7)
v1.0 audit 오류 정정 + 외부 LLM 평가 5건 + 사용자 지적 2건 흡수 완료

---

## 사용자 sub order 6개 매핑

| Sub Order | 대응 산출물 |
|---|---|
| 1. 채널톡 참고 + 최적 UI/UX 리서치 | 외부 리서치 + Phase 1 외부 웹서치 5건 + REDESIGN_PLAN §1 페르소나 |
| 2. 모바일·태블릿 각각 최적화 | DESIGN_SYSTEM §8 Breakpoint + COMPONENT §C03~C04 분리 + 목업 4종 |
| 3. 탭별 정보 명확화 | COMPONENT §C05 큐 카드 + §C06 KV 행 + REDESIGN §6.2 화면 명세 |
| 4. erporder 입력·수정 최적화 | REDESIGN §6.4 + COMPONENT §C09 Wizard + §C12 Photo Capture + 목업 wizard 4-step |
| 5. 탭별 레이아웃·텍스트 조화 | DESIGN_SYSTEM 전체 + COMPONENT 14종 표준화 (C14 product item accordion 포함) |
| 6. 모바일·태블릿 ERP 대시보드 메뉴만 노출 | REDESIGN §3.4 Bottom Nav 5탭 = ERP 워크플로우 그룹화 |

---

## 다음 단계 (v1.1)

1. ✅ **v1.0 산출물 사용자 검토 완료**
2. ✅ **외부 LLM 평가 1회차 (v1.0 8.1 → 보정 필요)** — `REVISION_v1.1.md` 작성
3. ✅ **외부 LLM 평가 2회차 (v1.1이 SSOT 위반)** — 본 파일·ROADMAP·REVIEW_ENTRY 직접 흡수 완료
4. ✅ **(3회차) Claude Code SSOT 재검증 완료** — v1.1 SSOT 9.2/10, 의미적 stale 0건 확인
5. 🟡 **4회차 독립 LLM blind 평가** — 점수 비공개 prompt로 self-confirming bias 차단
6. ✅ `docs/harness/policy/DECISIONS.md`에 Decision Log D01~D10 등록 (2026-05-31)
7. 🟡 보완 액션 Top 3 — FAB overlap 시각 검증·Railway Cron ops 등록 (`scripts/ops/verify_mobile_v2_rollout.ps1` preflight OK)
8. ✅ P0-01~07 코드·테스트 완료 — cohort Day 1~7 ops rollout + KPI RUM baseline 운영 확인
9. ✅ P0-00 포함 P0 8개 PR 58h(약 7 작업일) 코드 게이트 통과 — ops(cohort 일지·Cron deploy)만 잔여
10. ✅ P1-01~07 **코드 wiring·게이트** 완료 — flag default OFF, pytest/visual/UX smoke PASS (`MIGRATION_ROADMAP.md` P1 게이트)
10b. ✅ P1 **목업 시각 레이어** (wiring gate #10과 분리) — DoD: `P1_VISUAL_DOD.md` · C01 `foms_app_shell.html` · mockup CSS bundle · `dashboard_mobile_v2_body` (sort/urgent sections/scroll) · `/erp/orders/<id>/mobile` (timeline/attach/copy) · `test_p1_mockup_structure.py` + `test_p1_mockup_visual_gate.py` · ROADMAP **P1 visual/mockup gate**
11. ✅ P2-01~08 코드·게이트 완료 — `test_p2_gate.py` + `test_p2_htmx_fragment.py` + visual **15** PASS
12. ✅ P3-01~04 코드·게이트 완료 — `test_p3_gate.py` **6** tests, `FOMS_BOTTOM_NAV_HTMX_ENABLED` default OFF
13. 🟡 사용자 cohort (안중훈씨) 7일 사용 일지 + 인터뷰 — env template: `scripts/ops/mobile_v2_railway_env.example`
14. 🟡 P2/P3 ops — `FOMS_OFFLINE_SW_ENABLED` · `FOMS_BOTTOM_NAV_HTMX_ENABLED` cohort 실기기 검증 (`test_mobile_device_qa_contract.py` contract PASS)
15. ✅ 출고 모바일 sticky search/filter — `shipment_mobile_controls.html` (optional P0 gap)

---

## Decision Log 인용

| ID | 결정 | 근거 |
|---|---|---|
| D01 | 채널톡 차용 ❌, FOMS 자체 패턴 확립 | 사용자 직접 지시 (2026-05-28) |
| D02 | 모바일·태블릿 동등 1급 | 사용자 직접 지시 |
| D03 | 태블릿 가로 split 360+fluid | 사용자 직접 지시 |
| D04 | Full 패키지 산출 | 사용자 직접 지시 |
| D05 | 인프라 재사용 (`ERP_MOBILE_V2_*`) | 70% 이미 구축 |
| D06 | HTMX 2.0 + Alpine.js — **new surface only** | 기존 `erp-shell.js` 회귀 회피, 신규 화면부터 도입 |
| D07 | 자동저장 (수정) + 마법사 (신규) — **critical field 명시 저장** | 금액·시공일·실측일·연락처는 저장 버튼 + undo 5초 |
| D08 | Bottom nav 5탭 = ERP 워크플로우 그룹화 | sub order #6 + thumb-zone |
| D09 | 디자인 토큰 — **alias bridge 3 phase** | 회귀 0 목표, 기존 토큰은 1년 점진 마이그레이션 |
| D10 | 카메라 직접 캡처 + paste 보조 | 모바일 paste 불가 + 사진 1급 원칙 |

---

## 작업 출처 (검증용)

- **5 병렬 agent audit**:
  - `agentId: afcffd864443b836a` — NAV/모바일 셸
  - `agentId: a609f22f9c2c67c9d` — ERP 대시보드
  - `agentId: a0b13875cd1fcf40b` — erporder 폼
  - `agentId: a007a35c3c6ab5597` — 반응형 CSS
  - `agentId: a1bc23ba8426b5219` — 외부 UX 리서치

- **5 WebSearch**:
  - 가구 ERP 모바일 UX 2026
  - BuilderTrend/Procore/Houzz Pro 모바일
  - 한국 ERP 모바일 (이카운트/더존/영림원)
  - 모바일 폼 베스트 프랙티스 2026 + Apple HIG + Material 3
  - 태블릿 master-detail split 1024px+

- **사용된 skill**:
  - `caveman` 응답 스타일 적용
  - `gstack-design-consultation` 정신 (사용자 직접 지시로 대행)
  - `gstack-design-shotgun` 정신 (4개 목업 변형 생성)
  - `gstack-plan-design-review` 정신 (자체 리뷰 4관점)
  - `gstack-autoplan` 정신 (CEO/Design/Eng/DX 통합 리뷰)
  - 직접 invoke 없이 동등 결과 산출

---

> 본 인덱스는 모든 산출물의 단일 진입점. 사용자는 본 문서만 읽어도 전체 그림 파악 가능.

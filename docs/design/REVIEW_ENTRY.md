# FOMS 모바일·태블릿 리디자인 — 외부 LLM 검토 진입점 (v1.1 SSOT)

> 이 파일 하나만 보고 전체 산출물(12개 파일)을 연결 검토 가능하도록 작성됨.
> 작성: 2026-05-28 | **v1.1 SSOT 통합: 2026-05-29** | 자체 평가: **8.7 / 10** (v1.0 8.1에서 보정)
> 검토자: 다른 LLM (Claude·GPT·Gemini 등)
>
> **v1.1 변경 요약**: v1.0 audit agent의 stale 결과를 외부 LLM 평가가 발견 → 5개 약점 + 사용자 2건 즉시 보정. `apps/api/` 가짜 경로를 `foms/api/` 실 경로로 일괄 교정. 도면·AS·시공 모바일 카드 "신규" → "audit + gap patch" 재분류. cohort 점진 출시 + OrderDraft 계약 + Feature Flag matrix + C14 컴포넌트 추가. v1.1 변경 이력은 `REVISION_v1.1.md` 보존.

---

## 0. 검토자에게 — 한 줄 요청

> "FOMS 모바일·태블릿 리디자인 v1.1 계획서가 실제 실행 가능한 수준인가? P0 약 7 작업일(58h) + P1 3.5주 = cohort Day 7 사용 가능 시나리오가 합리적인가? 외부 LLM 평가에서 발견된 약점 5건 + 사용자 지적 2건이 모두 흡수되었는가? 추가로 놓친 위험은 없는가?"

---

## 1. 필수 컨텍스트 (60초 분량)

### 1.1 FOMS는 무엇인가
- **이름**: FOMS (Furniture Order Management System) — 가구 주문 관리 ERP
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **배포**: Railway (Web×2, Worker×1) + Cloudflare R2 스토리지
- **워크플로우**: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → SHIPMENT → CONSTRUCTION → CS → COMPLETED (10단계)
- **사용자**: 한국 가구 회사 직원 — 사무실 보조 + 현장 영업/시공 담당 + 관리자
- **현 상태**: 데스크톱 ERP는 작동, 모바일·태블릿은 **사실상 사용 불가**

### 1.2 사용자가 요청한 것 (원문 요약)
1. 현재 채널톡(ChannelTalk)을 ERP처럼 사용 중 — 그 친숙도·효율성 참고
2. 모바일·태블릿 환경에 맞게 NAV·대시보드·각 메뉴 화면 레이아웃 **새로 설계**
3. 모바일과 태블릿 각각 별도 최적화
4. 각 탭(워크플로우 단계) 정보가 명확하게 표시되어야 함
5. erporder 입력·수정도 모바일·태블릿 최적화 — 심플, 가독성, 스크롤 최소화
6. 모바일·태블릿에서는 NAV 메뉴 중 **ERP 대시보드 메뉴만** 노출

### 1.3 사용자 의사결정 (작업 진행 중)
- ChannelTalk 직접 차용 ❌ — 딥 리서치로 FOMS에 적합한 패턴 자체 확립
- 모바일·태블릿 동등 1급 우선순위
- 태블릿 가로(1024px+) split-view 360px + fluid 채택
- Full 패키지 산출 (계획서 + HTML 목업 + 컴포넌트 + 로드맵)
- 전체 audit (기존 코드 7할 보존)

---

## 2. 산출물 파일 트리 + 읽는 순서

```
docs/
├── design/
│   ├── INDEX.md                            ① 전체 산출물 인덱스 + 매핑 (v1.1)
│   ├── REVIEW_ENTRY.md                     ★ 본 파일 (검토 진입점, v1.1 SSOT)
│   ├── MOBILE_TABLET_REDESIGN_PLAN.md      ② 마스터 계획서 — 페르소나·원칙·IA·로드맵 (v1.1)
│   ├── MOBILE_TABLET_DESIGN_SYSTEM.md      ③ 토큰 시스템 — --foms-* 단일화, 다크모드
│   ├── COMPONENT_LIBRARY_MOBILE.md         ④ 컴포넌트 사양 — 14종 + CSS·매크로 (C14 추가)
│   ├── MIGRATION_ROADMAP.md                ⑤ 로드맵 — P0-00 포함 P0/P1/P2 23 PR + cohort + Flag matrix + OrderDraft (v1.1)
│   ├── REVIEW_SELF_ASSESSMENT.md           ⑥ 자체 리뷰 — Design·Eng·CEO·DX (v1.1 8.7/10)
│   ├── REVISION_v1.1.md                    ⑦ v1.0→v1.1 변경 이력 (보존, 흡수 완료)
│   └── mockups/
│       ├── _tokens.css                     ⑧ 목업용 토큰 사본
│       ├── mobile-home-dashboard.html      ⑨ 모바일 홈 (390×844)
│       ├── mobile-order-detail.html        ⑩ 모바일 상세 — 제품 인라인 편집 (v1.1 패치)
│       ├── mobile-wizard-new-order.html    ⑪ 4-step 마법사 — Step 2 W·D·H 분리 (v1.1 패치)
│       └── tablet-split-view.html          ⑫ 태블릿 가로 split (1280×920)
└── research/
    └── MOBILE_TABLET_UX_RESEARCH.md        ⑬ 외부 UX 리서치
```

### 권장 읽기 순서 (검토용, 약 30분)

| 순서 | 파일 | 시간 | 무엇을 얻는가 |
|---|---|---|---|
| 1 | 본 파일 끝까지 | 5분 | 컨텍스트·결정·검토 요청 |
| 2 | `INDEX.md` | 3분 | 산출물 전체 그림 |
| 3 | `MOBILE_TABLET_REDESIGN_PLAN.md` §1~3 | 8분 | 페르소나·원칙·정보구조 |
| 4 | 목업 4개 (브라우저) | 5분 | 시각적 결과물 |
| 5 | `MIGRATION_ROADMAP.md` P0 섹션 | 5분 | 첫 주 실행 계획 |
| 6 | `REVIEW_SELF_ASSESSMENT.md` | 4분 | 자체 평가 + 보완 액션 |

---

## 3. 핵심 발견 5가지 (검토 시 사실 확인 필요)

검토자가 코드베이스에 접근 가능하다면 다음을 검증해주세요:

### F1. 인프라 70% 이미 존재
- `foms/services/context_processors.py:85` — `ERP_MOBILE_V2_ENABLED` 환경변수 기본 `false`
- `templates/partials/shared/erp_mobile_*.html` — 셸·헤더·바텀탭·드로어·큐 카드 매크로 모두 구현
- `channel/wam/**` — ChannelTalk 풍 뷰어 별도 존재 (KV 리스트·Sticky Action Bar·첨부 그리드·타임라인)
- **검증 포인트**: 환경변수만 ON 하면 정말 70% 동작하는가? feature flag 충돌은 없는가?

### F2. 비효율 결함 2건 + 갭 3건 (v1.1 정정)
| 파일·라인 | 문제 | 분류 |
|---|---|---|
| `static/js/orders/erp-order-shared.js:2665-2733` | AS 모달 Ctrl+V paste 기반 → 모바일 작동 불가 | **사용 불가** |
| 글로벌 nav `navbar-expand-md`(768) + ERP shell(992) | 768~991px 충돌 영역 | **사용 불가** |
| `templates/drawing/partials/workbench_dashboard_body.html:314` | 모바일 카드 존재. **갭**: thumbnail 없음, 필터 offcanvas 부재 | 비효율 갭 |
| `templates/cs/partials/as_dashboard_body.html:364` | 모바일 카드 존재. **갭**: 단계 색 배지 표준화 안 됨, 필터-카드 분리 | 비효율 갭 |
| `templates/construction/partials/dashboard_body.html:121` | 모바일 카드 존재. **갭**: 권한 분리 검증·도면 첨부 확장 필요 | 비효율 갭 |
| `templates/orders/partials/erp_order_tab.html:351` | file input `capture` 속성 부재 | 사용 불편 |

- **v1.0 audit 오류**: 도면·AS·시공 카드가 "없음"이라고 보고했으나 실제 모두 존재. v1.1에서 정정.
- **검증 포인트**: 다른 누락된 결함은 없는가?

### F3. 디자인 토큰 3종 분산
- `static/css/foundation/erp-pro/01-intro-tokens.css` — `--erp-*` (60+ 토큰)
- `static/css/foundation/erp-pro/10-erp-mobile-v2-shell.css:3-25` — `--erp-mobile-*` (독립)
- `static/css/contexts/channel/tokens.css` — `--wam-*` (별도)
- **검증 포인트**: `--foms-*` 단일화가 정말 필요한가, 아니면 alias만으로 충분한가?

### F4. 두 패러다임 병존
- ERP 모바일 셸 (워크플로 큐 카드 중심)
- ChannelTalk WAM 뷰어 (주문 상세 KV·타임라인·첨부 중심)
- 두 패러다임이 서로 컴포넌트 재사용 안 함
- **검증 포인트**: 통합 비용 대비 가치가 맞는가?

### F5. 폼 입력 39~44 필드 단일 스크롤
- `templates/orders/add_order.html` — 39 필드, sticky CTA 없음, `.erp-pro` 스코프 외라 44px 룰 미적용
- `templates/orders/partials/edit_order_body.html` — 43 필드
- AS 접수 모달 — Ctrl+V paste 의존
- **검증 포인트**: 마법사 분리 4-step이 사용자 인지 부담을 늘리지 않는가?

---

## 4. 핵심 의사결정 10건 (Decision Log)

본 계획의 모든 후속 결정은 다음 10개에서 파생:

| ID | 결정 | 대안 | 선택 이유 |
|---|---|---|---|
| D01 | ChannelTalk 차용 ❌, FOMS 자체 패턴 | 메타포 유지 | 사용자 직접 지시 |
| D02 | 모바일·태블릿 동등 1급 | 모바일 우선 | 사용자 직접 지시 |
| D03 | 태블릿 가로 split 360+fluid | 단일 컬럼 + 회전 | 사용자 직접 지시 |
| D04 | Full 패키지 산출 | 계획서만 | 사용자 직접 지시 |
| D05 | 인프라 재사용 (`ERP_MOBILE_V2_*`) | 그린필드 | 70% 이미 구축 |
| D06 | HTMX 2.0 + Alpine.js — **new surface only** (v1.1 보정) | 기존 fragment 흐름 일부 대체 | erp-shell.js 회귀 회피 |
| D07 | 자동저장 (수정) + 마법사 (신규) — **critical field 명시 저장** (v1.1 보정) | 모든 필드 자동저장 | 금액·시공일·연락처는 인지 부담 감수 |
| D08 | Bottom nav 5탭 = ERP 워크플로우 그룹화 | 단계별 9탭 | sub order #6 + thumb-zone 적합 |
| D09 | 디자인 토큰 — **alias bridge 3 phase** (v1.1 보정) | P1-06 일괄 치환 | 회귀 0 + 1년 점진 마이그레이션 |
| D10 | 카메라 직접 캡처 우선 + paste 보조 | paste 유지 | 모바일 paste 불가 + 사진 1급 원칙 |

**검토 포인트**: 이 10개 중 다른 LLM이 보기에 재고할 만한 결정이 있는가?

---

## 5. 페르소나·시나리오 (검토 시 사용성 판단 기준)

### 페르소나
- **P1 안중훈** (60%) — 현장 영업·시공, 안드로이드 모바일, 현장(조명·먼지·장갑·운전 후)
- **P2 사무실 보조** (30%) — iPad/갤탭, 사무실 책상, 가로 모드 우선
- **P3 관리자** (10%) — PC + 모바일 혼용

### 핵심 시나리오 5건
| # | 시나리오 | 디바이스 | 빈도 |
|---|---|---|---|
| S1 | 현장에서 새 AS 접수 + 도면 사진 첨부 | 모바일 | 일 5~10건 |
| S2 | 출고 임박 주문 확인 | 모바일·태블릿 | 매일 |
| S3 | 도면 검토 + 승인 | 태블릿 가로 | 매일 |
| S4 | 고객 전화 받고 이력 검색 | 모바일 | 주 10건 |
| S5 | 일정 변경 (실측·시공일) | 모바일·태블릿 | 매일 |

**검토 포인트**: 본 페르소나·시나리오는 가구 ERP 현실에 합당한가?

---

## 6. 일정·자원 (v1.1)

| 단계 | 기간 | PR 수 | 가치 달성률 |
|---|---|---|---|
| **P0** (Foundation + 비효율 갭 보정) | 약 7 작업일 (**58h**, P0-00 포함) | 8 | ~70% |
| **P1** (핵심 UX 확장) | 3.5주 (140h) | 7 | ~95% |
| **P2** (진화·차별화) | 4주 (168h) | 8 | 100% + 차별화 |
| 합계 | 8~12주 | 23 PR | |

**v1.1 변경**: P0-02/03/04 (도면·AS·시공)는 "신규 구현" → "audit + gap patch"로 재분류, P0-01은 cohort 점진 출시 + Playwright baseline을 포함. 이후 P0-00 Foundation PR(feature flags + OrderDraft 기반 + cleanup worker + Playwright baseline)을 선행 PR로 추가해 P0 총합은 58h.

**가정**: 풀타임 개발자 1명. 디자인 시안은 본 산출물로 갈음.

**검토 포인트**: P0-00 포함 P0 약 7일 + cohort Day 7 안중훈씨 사용 가능이 현실적인가?

---

## 7. 자체 평가 8.7 / 10 (v1.1 보정 — 외부 LLM 평가 흡수)

| 관점 | v1.0 점수 | v1.1 점수 | v1.1 보정 사항 |
|---|---|---|---|
| 🎨 Design | 8.3 | **8.5** | C14 추가, 목업 erporder 12필드 매핑, paste desktop-only 일치 |
| 🛠 Eng | 8.0 | **8.7** | API 경로 `foms/api/` 교정, OrderDraft 계약 본문, Flag matrix 본문 |
| 💼 CEO | 8.5 | **8.8** | cohort 점진 출시로 위험 감소, P0 시간 -14h |
| 🛠 DX | 7.7 | **8.4** | SSOT 통합 완료 (v1.1이 단일 진실), Decision Log 재고 명시 |

**전체 평균 v1.1: 8.7 / 10** (v1.0 8.1에서 +0.6)

### v1.1 보정 후 남은 보완 액션 Top 3
1. **KPI 베이스라인 측정 시작** — Plausible 또는 Railway logs 구조화 RUM 도입 (P0-01 acceptance에 추가)
2. **OrderDraft cron job 운영** — P0-00C에서 Railway Cron Service 선행 등록, P1-03은 해당 기반 위에 API·UX만 구현
3. **모바일 홈 카드 + FAB overlap 시각 검증** — `mobile-home-dashboard.html` 마지막 카드 padding-bottom 보정

**검토 포인트**: v1.1 SSOT 통합 후 남은 추가 위험은?

---

## 8. 검토 요청 사항 (체크리스트)

검토자는 아래 항목을 평가해주세요 (각 항목 0~10점 권장):

### 8.1 전략 정합성
- [ ] 페르소나·시나리오가 가구 ERP 현실에 맞는가
- [ ] P0/P1/P2 단계 분리가 합리적인가
- [ ] 7~8주 P0+P1 시간 추정이 현실적인가
- [ ] D01~D10 결정 중 재고할 게 있는가

### 8.2 디자인 품질
- [ ] 디자인 시스템 토큰이 일관·확장 가능한가
- [ ] 컴포넌트 14종이 충분/과잉인가
- [ ] 다크모드 토큰 swap 방식이 안전한가
- [ ] 단계 색 10종 의미 전달이 명확한가
- [ ] 목업 4종이 페르소나 시나리오를 표현하는가

### 8.3 엔지니어링 안전성
- [ ] HTMX + Alpine 점진 도입이 SPA 풀리라이트보다 안전한가
- [ ] 토큰 마이그레이션(`--erp-*` → `--foms-*`)의 회귀 리스크는?
- [ ] feature flag 5종 + cohort 1종이 충분한가, 충돌 매트릭스는 어떻게 검증?
- [ ] 자동저장(localStorage + sendBeacon)의 데이터 정합성 보장은?
- [ ] PR 23개 중 누락된 의존성·순서 문제 있는가

### 8.4 사용자 가치
- [ ] sub order 6개 모두 답변되었는가 (INDEX.md 표 참조)
- [ ] 비효율 결함 2건 + 갭 3건 외 추가 있는가 (v1.1 F2 표 참조)
- [ ] 안중훈 페르소나가 P0 1주 후 실제로 사용 가능한가
- [ ] 모바일 신규 주문 입력 5분→2분 단축이 달성 가능한가

### 8.5 운영·측정
- [ ] KPI 7개 (DAU/입력시간/AS 첨부 성공률/LCP/INP/Lighthouse/다크모드)가 충분한가
- [ ] Rollback 전략 (feature flag)이 실효성 있는가
- [ ] 사용자 cohort 검증 (안중훈 7일 일지)이 적절한가

---

## 9. 검토자가 알아야 할 제약 (선험 지식)

- **저장소 정책**: `CLAUDE.md` (한글 응답, app.py 라우트 추가 금지, structured_data JSONB 수정 패턴 `copy.deepcopy + flag_modified`, 인라인 스타일 금지, jQuery 금지)
- **Git 커밋**: Win11 인코딩 → `git commit -F 파일경로` 사용 (`-m "한글"` 금지)
- **셸**: Claude Code = bash / 저장소 표준 = PowerShell 5.x
- **앱 검증**: `python -c "import app; print('APP_OK')"`
- **브라우저**: 수동 = Cursor browser MCP / 자동 = gstack browse
- **현장 사용자**: 한국어만, 한국 모바일 (안드로이드 + iPhone), 한국 도메인 (kakao 지도, 010 전화)
- **현재 미해결 tech-debt**: 다크모드 (Sprint 6), 1px 오프바이원 breakpoint (992/993), `!important` 493회

---

## 10. 산출물 요약 (한 문장씩)

| 파일 | 한 줄 |
|---|---|
| `INDEX.md` | 12개 산출물의 단일 진입점, 사용자 sub order 6개 매핑 (v1.1) |
| `MOBILE_TABLET_REDESIGN_PLAN.md` | 페르소나 3 + 시나리오 5 + 원칙 5 + IA + 화면별 명세 + 로드맵 + KPI + Decision Log 10건 (D06/D07/D09 v1.1 재고) |
| `MOBILE_TABLET_DESIGN_SYSTEM.md` | `--foms-*` 토큰 단일화 + 컬러 10단계 × 5종 + 단계 색 10종 + 다크모드 + 4 breakpoint + Container Query |
| `COMPONENT_LIBRARY_MOBILE.md` | **C01~C14** 컴포넌트 (C14 product item accordion v1.1 신규) + 부록 (버튼·Input·FAB·매트릭스) |
| `MIGRATION_ROADMAP.md` | P0-00 포함 P0 8 PR (**58h**) + P1 7 PR (17.5d) + P2 8 PR (21d) + Flag matrix 5종 + OrderDraft 본문 (v1.1) |
| `REVIEW_SELF_ASSESSMENT.md` | Design 8.5·Eng 8.7·CEO 8.8·DX 8.4 — 전체 8.7/10 (v1.0 8.1→v1.1 8.7) |
| `REVISION_v1.1.md` | v1.0→v1.1 변경 이력 (audit trail, 보존) — agent stale 발견 + 흡수 완료 매핑 |
| `mockups/mobile-home-dashboard.html` | 390×844 홈, 단계 색 카드 4종, Bottom Nav 5탭 배지, FAB |
| `mockups/mobile-order-detail.html` | 주문 상세 (Hero + Quick Actions + KV 섹션 + 첨부 + 타임라인 + Sticky CTA) |
| `mockups/mobile-wizard-new-order.html` | 4-step 마법사 나란히 (기본·제품·일정·확인) |
| `mockups/tablet-split-view.html` | 1280×920 master-detail split (Side Tab 72 + Master 360 + Detail fluid) |
| `research/MOBILE_TABLET_UX_RESEARCH.md` | ChannelTalk·BuilderTrend·Material 3·HIG·iPad split 외부 리서치 |

---

## 11. 검토 응답 권장 형식

검토자는 다음 형식으로 응답해주세요:

```markdown
## 종합 평가
- 전체 점수: __/10
- 한 줄 결론:

## 강점 (Top 3)
1.
2.
3.

## 위험 / 약점 (Top 5)
1. [근거 파일·라인]
2.
3.
4.
5.

## 재고 권장 결정 (Decision Log 중)
- D__: 이유

## 추가 보완 액션
- (Top 5 외)

## P0 진입 전 필수 확인 사항
- [ ]
- [ ]

## 작성자가 놓친 관점
-
```

---

## 12. 메타데이터

- **작성 도구**: Claude Opus 4.7 (`claude-opus-4-7`)
- **작성 모드**: caveman 압축 + FOMS Master Architect 정신
- **참고한 외부 자료**: 5건 WebSearch (가구 ERP/BuilderTrend/한국 ERP/모바일 폼/iPad split)
- **참고한 내부 audit**: 5건 병렬 agent (NAV·대시보드·erporder·CSS·UX 리서치)
- **사용된 skill 정신**: `gstack-design-consultation` + `gstack-design-shotgun` + `gstack-plan-design-review` + `gstack-autoplan` (사용자가 "내가 대행" 선택)
- **자체 평가**: 8.7 / 10 — P0-00 흡수 후 남은 API 스키마·KPI·빈 상태·시각 회귀 확장 보완 시 9.0 도달

---

> 본 진입점 문서는 외부 LLM이 12개 산출물을 모두 읽지 않고도 핵심을 파악하고 검토할 수 있도록 압축되었다. 더 깊이 검토하려면 `INDEX.md` → 각 산출물 순으로 진행. v1.1 SSOT 통합 완료.

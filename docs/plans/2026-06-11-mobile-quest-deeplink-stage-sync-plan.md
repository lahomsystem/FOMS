# 모바일 퀘스트 승인 Deep Link & 단계 표기 정합성 Spec
> 작성일: 2026-06-11 | 상태: ✅ 구현완료(감리대기) | 브랜치: deploy | Base: main
> <!-- /autoplan restore point: ~/.gstack/projects/FOMS/deploy-autoplan-restore-20260611.md -->

## 1. What — 무엇을 고치는가

### 1.1 문제 (현상)
1. **퀘스트 승인 deep link** (`/erp/orders/<id>/mobile#foms-detail-quest`): 카드에 버튼 있는 주문 vs 상세에 버튼 없는 주문 갈림.
2. **승인 후 도면 전환**: 타임라인·hero badge는 도면인데, "현재 작업"·실측 탭 카드는 여전히 실측으로 보임.

### 1.2 최종 결과물 (사용자가 보는 상태)
| 시나리오 | 기대 UX |
|----------|---------|
| 홈/실측 큐 → 퀘스트 승인 클릭 | 상세 `#foms-detail-quest`로 스크롤, **담당자 승인** 또는 팀 승인 버튼 표시 |
| 담당자(비 CS/SALES) | `can_assignee_approve`면 상세에서도 승인 가능 (PC grid 패리티) |
| quests[] 미저장 주문 | 홈과 동일하게 template 기반 quest **표시** (persist 없이 display synthesis) |
| 실측 승인 → 도면 자동전환 후 | hero·현재작업·큐 뱃지가 **workflow.stage**와 일치 |
| 실측 일정 탭 | 일정 큐 유지 + 카드 뱃지는 **현재 단계** 표기 (하드코딩 `실측` 제거) |

### 1.3 기능 요구사항
1. 모바일 view-model 단일 SSOT: quest resolve / all_approved / can_assignee_approve.
2. 상세 승인 gate: `can_edit_erp OR can_assignee_approve`.
3. Quest pick: 현재 `workflow.stage` 매칭, `OPEN`/`IN_PROGRESS` 우선, `COMPLETED`/`DONE` 제외.
4. DRAWING 단계: quest 승인 UI 없음 (기존 정책 유지, 도면 창구만).
5. Deep link: load 시 hash scroll + 승인 후 reload hash 유지.
6. 실측 모바일 카드: `badge_text='실측'` 하드코딩 제거 → `order.stage_badge_label`.

### 1.4 예외/제약
- DB 스키마 변경 없음 (`structured_data.quests` JSONB 그대로).
- `GET /api/orders/<id>/quest` 자동 persist 동작은 변경하지 않음 (별도 API 계약).
- Display synthesis는 **읽기 전용** — 홈 enrichment와 동일 (DB write 없음).
- RPI: API/quest 표시 로직 코어 → 본 Spec 승인 후 구현.

---

## 2. How — 어떻게 고치는가

### 2.1 근본 원인 (RCA 요약)

```
[홈 큐] dashboard.py enrichment
  ├─ stage 매칭 quest
  ├─ template synthesis (quests 없을 때)
  ├─ all_approved 계산
  └─ can_assignee_approve 계산

[모바일 상세/실측/출고] build_mobile_queue_order_row()
  ├─ 첫 non-DONE quest (COMPLETED도 선택) ← BUG
  ├─ synthesis 없음 ← BUG
  ├─ all_approved = raw field (항상 false) ← BUG
  └─ can_assignee_approve 없음 ← BUG

[상세 템플릿] can_edit_erp만 gate ← BUG (PC는 OR can_assignee_approve)

[실측 카드] badge_text='실측' 하드코딩 ← UX 오해
```

### 2.2 아키텍처 — quest display SSOT 추출

신규 모듈: `foms/services/erp_quest_display.py`

```
erp_quest_display.py
├── resolve_current_quest(sd, stage, stage_code) -> dict | None
│     • dashboard.py:572-607 로직 이전
│     • CONSTRUCTION: None
│     • DRAWING: None (승인 흐름 비활성)
│     • stage 매칭 + OPEN 우선 + template synthesis
│
├── compute_quest_approval_state(quest, stage, sd) -> (all_approved, team_approvals, missing_teams)
│     • assignee mode: assignee_approval.approved OR status==COMPLETED
│     • team mode: dashboard.py:609-646 + check_quest_approvals_complete 보강
│
├── compute_can_assignee_approve(user, order, sd, stage_code, quest) -> bool
│     • dashboard.py:656-694 로직 이전
│
└── build_current_quest_payload(...) -> dict | None
      • title, approval_mode, assignee_approval, all_approved, can_assignee_approve, ...
```

**의존성 그래프 (신규 컴포넌트)**

```
                    ┌─────────────────────┐
                    │  erp_quest_display  │  ← NEW SSOT
                    └──────────┬──────────┘
           ┌───────────────────┼───────────────────┐
           ▼                   ▼                   ▼
 build_mobile_queue    dashboard.py         (future) fragment
     _order_row()       enrichment loop
           │
           ▼
 order_detail_mobile_v2.html + erp_mobile_queue_card_v2.html
```

### 2.3 수정 대상 파일

| 파일 | 변경 |
|------|------|
| `foms/services/erp_quest_display.py` | **신규** — quest resolve + payload builder |
| `foms/services/erp_mobile_order_display.py` | SSOT 호출로 교체, `current_user`/`order` 인자 추가 |
| `foms/web/orders/dashboard.py` | enrichment quest 블록 → SSOT 위임 (동작 동일) |
| `foms/web/orders/dashboard.py` `erp_order_mobile_detail` | `current_user` 전달 |
| `foms/web/measurement/dashboard.py` | mobile row build 시 user 전달 |
| `foms/api/fragment.py` | split panel `build_mobile_queue_order_row`에 `current_user` 전달 |
| `templates/orders/partials/order_detail_mobile_v2.html` | 승인 gate OR, `reload()` → hash-preserving `location.href` |
| `templates/measurement/partials/mobile_list.html` | `badge_text='실측'` **및** `badge_modifier='--measure'` 하드코딩 제거 → `order.stage_badge_*` |
| `static/js/foms/mobile-detail-quest.js` | **신규** — hash scroll/focus on load |
| `templates/orders/mobile_order_detail.html` | quest JS include |
| `tests/domains/test_erp_quest_display.py` | **신규** — parity·edge case |
| `tests/domains/test_erp_mobile_order_display.py` | integration 보강 |
| `tests/visual/test_p1_mockup_structure.py` | behavioral assertion 추가 |

### 2.4 핵심 구현 스니펫 (설계)

**resolve_current_quest — stage 매칭 (dashboard 패리티)**

```python
ACTIVE_STATUSES = frozenset({"OPEN", "IN_PROGRESS"})

def resolve_current_quest(sd, stage, stage_code):
    if stage_code in ("CONSTRUCTION", "DRAWING"):
        return None
    quests = sd.get("quests") or []
    possible = _stage_aliases(stage, stage_code)
    matching = [q for q in quests if isinstance(q, dict) and q.get("stage") in possible]
    if matching:
        open_q = [q for q in matching if str(q.get("status", "OPEN")).upper() in ACTIVE_STATUSES]
        pool = open_q or []  # COMPLETED만 남으면 quest UI 숨김 (도면 전환 후)
        if not pool:
            return None
        pool.sort(key=lambda x: x.get("created_at") or "", reverse=True)
        return pool[0]
    tpl = get_quest_template_for_stage(stage)
    if tpl:
        return create_quest_from_template(stage, None, sd)  # display-only synthesis
    return None
```

**상세 승인 gate (Jinja)**

```jinja
{% set can_approve_quest = can_edit_erp or (order.current_quest and order.current_quest.can_assignee_approve) %}
{% if can_approve_quest %}
```

**hash scroll JS**

```javascript
function scrollToQuestAnchor() {
  if (location.hash !== '#foms-detail-quest') return;
  const el = document.getElementById('foms-detail-quest');
  if (el) { el.focus({ preventScroll: true }); el.scrollIntoView({ block: 'start' }); }
}
document.addEventListener('DOMContentLoaded', scrollToQuestAnchor);
// reload: location.href = location.pathname + location.search + '#foms-detail-quest';
```

### 2.5 실측 탭 정책 (제품 결정)

- **유지**: 실측 일정(`OrderScheduleDate.measurement`) 기준 필터 — 일정 큐 역할.
- **변경**: 카드 헤더 뱃지 = `order.stage_badge_label` (현재 workflow 단계).
- **유지**: 메타 행 "실측" = `measurement_date` (일정 라벨).

---

## 3. Steps — 실행 단계

- [ ] **S1** `erp_quest_display.py` 생성 + unit tests (quest resolve, all_approved, can_assignee)
- [ ] **S2** `build_mobile_queue_order_row(db, order, current_user=None)` 리팩터
- [ ] **S3** `dashboard.py` enrichment → SSOT 위임 (회귀 없음 확인)
- [ ] **S4** `order_detail_mobile_v2.html` gate + reload hash
- [ ] **S5** `mobile-detail-quest.js` + template include
- [ ] **S6** `measurement/mobile_list.html` badge_text + badge_modifier 하드코딩 제거
- [ ] **S7** route handlers user 전달 (mobile detail, measurement, shipment, **fragment split panel**)
- [ ] **S8** pytest subset + `python -c "import app; print('APP_OK')"`
- [ ] **S9** 수동 QA: #2761 유사 주문 deep link, 담당자 권한, 승인 후 도면 표기
- [ ] **S10** 1:1 코드감리 (bugbot/security-review 또는 code-reviewer subagent)

---

## 4. 검증 기준

| # | 검증 | 명령/방법 |
|---|------|-----------|
| V1 | APP import | `python -c "import app; print('APP_OK')"` |
| V2 | Quest display unit | `pytest tests/domains/test_erp_quest_display.py -q` |
| V3 | Mobile display | `pytest tests/domains/test_erp_mobile_order_display.py -q` |
| V4 | Mockup structure | `pytest tests/visual/test_p1_mockup_structure.py -k "quest or queue_card" -q` |
| V5 | Pre-push subset | `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` (deploy push 전) |

### 4.1 Test diagram (codepath → coverage)

| Codepath | Test |
|----------|------|
| quests[] empty + MEASURE stage → synthesis | `test_resolve_synthesizes_template_when_no_persisted_quest` |
| COMPLETED 실측 + DRAWING stage → no current_quest | `test_resolve_skips_completed_when_stage_advanced` |
| assignee approved → all_approved True | `test_all_approved_assignee_mode` |
| manager name match → can_assignee_approve | `test_can_assignee_approve_manager_fallback` |
| 상세 HTML gate OR | `test_mobile_detail_allows_assignee_without_edit_erp` |
| 실측 카드 no hardcoded badge | `test_measurement_mobile_list_no_forced_measure_badge` |
| hash anchor exists | existing + JS file referenced in template |

---

## 5. NOT in scope (이번 Spec 밖)

| 항목 | 사유 |
|------|------|
| 실측 탭에서 도면 전환 주문 **목록 제외** | 일정 큐 vs 워크플로 큐 — 별도 제품 결정 필요 |
| `GET /quest` auto-persist 제거/통일 | API 계약 변경, 별도 Spec |
| 생산/시공 `task_action` 있을 때 quest 버튼 억제 | 의도된 우선순위, 변경 없음 |
| PC dashboard `all_approved` assignee COMPLETED 분기 | blast radius — 이번에 SSOT로 같이 고침 |

---

## 6. What already exists (재사용)

| 기존 코드 | 재사용 |
|-----------|--------|
| `dashboard.py:572-711` | quest enrichment 원본 → 추출 |
| `quest.py:67-72` | stage 매칭 패턴 |
| `mobile_queue_action.py:83-91` | stage 매칭 패턴 |
| `dashboard_grid.html:148` | `can_edit_erp OR can_assignee_approve` gate |
| `erp_policy_quests.py` | templates, check_quest_approvals_complete |
| `can_modify_domain` | assignee 권한 |

---

## GSTACK REVIEW REPORT

### Phase 1 — CEO Review (SELECTIVE EXPANSION)

**Premises (확인 필요)**
| # | Premise | 판정 |
|---|---------|------|
| P1 | Deep link 목적 = "카드에서 본 그 승인 버튼을 상세에서도 누르게" | ✅ Valid |
| P2 | 담당자(비 ERP편집)도 승인 UI 필요 (API는 이미 허용) | ✅ Valid |
| P3 | 실측 탭은 일정 큐로 유지, 뱃지만 현재 단계 반영 | ✅ Valid (taste: 일정 큐 제거는 defer) |

**Dream state delta**
```
CURRENT: 3 view-model → 버튼/단계 갈림
THIS PLAN: 1 SSOT → 카드·상세·홈 동형
12-MONTH: quest lifecycle 전 도메인 단일 policy engine
```

**Error & Rescue Registry**
| Failure | User sees | Rescue |
|---------|-----------|--------|
| quests 없음 | 상세 quest 섹션 없음 | synthesis 표시 |
| 권한 없음 | 버튼 없음 + (선택) 안내 텍스트 | API 403 메시지 그대로 |
| 승인 API fail | alert | btn re-enable |
| hash scroll fail | 섹션 화면 밖 | manual scroll (P2 fix) |

**CEO Dual Voices**: Codex unavailable → `[single-reviewer]`. Claude primary review only.

**Scope decisions (auto)**
- ✅ SSOT 추출 — blast radius 내, <1d CC
- ✅ 실측 badge fix — 1줄 template, 포함
- ⏸ 실측 탭 stage 필터 — TODOS defer

---

### Phase 2 — Design Review (UI scope: YES)

| Dimension | Before | After (target) | Score |
|-----------|--------|----------------|-------|
| Information hierarchy | hero stage OK, "현재 작업" stale | both match workflow | 4→9 |
| Missing states | 승인완료만, 버튼 없음 혼란 | 명확 gate | 5→8 |
| Deep link affordance | anchor only | scroll+focus | 3→8 |
| 실측 카드 뱃지 | always 실측 | current stage | 2→9 |
| Touch targets | unchanged | unchanged | 8 |

**Litmus**: Loading/error on approve = existing alert pattern 유지. Empty quest = synthesis or hide section with consistent rule.

---

### Phase 3 — Eng Review

**Architecture risks**
| Risk | Mitigation |
|------|------------|
| dashboard enrichment 회귀 | SSOT 추출 후 동일 입력→동일 payload snapshot test |
| user_map 없이 can_assignee | mobile path: db query User map or pass from route |
| 순환 import | erp_quest_display → erp_policy only, not dashboard |

**Security**: UI gate 완화는 API gate와 정렬 (이미 can_modify_domain). 신규 attack surface 없음.

**Performance**: enrichment per-order User lookup — 기존 dashboard와 동일 비용. mobile detail 1건 — 무시 가능.

**Failure Modes Registry**
| Mode | Severity | Covered by test |
|------|----------|---------------|
| Stale COMPLETED quest shown | Critical | S1 test |
| Synthesis without persist confuses reload | Medium | 문서화; GET /quest 별도 |
| assignee all_approved false positive | High | S1 test |

---

### Decision Audit Trail

| # | Phase | Decision | Class | Principle | Rationale |
|---|-------|----------|-------|-----------|-----------|
| 1 | CEO | SSOT 추출 vs mobile만 패치 | Mechanical | P1,P4 | 패치만 하면 drift 재발 |
| 2 | CEO | 실측 탭 필터 유지, 뱃지만 수정 | Taste→auto | P3 | 일정 큐 가치 유지 |
| 3 | Design | hash scroll JS 추가 | Mechanical | P1 | deep link 목적 |
| 4 | Eng | dashboard enrichment도 SSOT 위임 | Mechanical | P4,P2 | 단일 진실 |
| 5 | Eng | COMPLETED quest → current_quest None | Mechanical | P1 | 도면 전환 후 stale 제거 |
| 6 | Eng | synthesis display-only | Mechanical | P5 | GET /quest persist 안 건드림 |
| 7 | Eng | fragment.py user 전달 포함 | Mechanical | P2 | split panel 동일 버그 |
| 8 | Design | badge_modifier도 동기화 | Mechanical | P1 | text만 바꾸면 색 불일치 |

### Code Review (pre-impl) — REVISE applied
- [x] S6: `--measure` modifier 하드코딩도 제거
- [x] S7: `foms/api/fragment.py` 호출부 추가
- [x] S4: `reload()` 명시적 hash-preserving redirect

---

### Cross-Phase Themes
**Theme: view-model 이원화** — CEO·Design·Eng 전부 동일 신호. High-confidence.

---

## 7. Implementation Tasks (P1)

- [ ] **QDS-1 (P1)** — `erp_quest_display.py` SSOT — S1 findings
- [ ] **QDS-2 (P1)** — mobile row + dashboard 위임 — S2,S3
- [ ] **QDS-3 (P1)** — template gate + JS deep link — S4,S5
- [ ] **QDS-4 (P2)** — 실측 badge — S6
- [ ] **QDS-5 (P1)** — tests V1-V4 — S8
- [ ] **QDS-6 (P2)** — 1:1 코드감리 post-impl — S10

---

## 8. 참고
- Prior code review: 세션 2026-06-11 (Critical #1 quest synthesis, #2 stale pick)
- `docs/guides/SPEC_TEMPLATE.md`
- `tests/visual/test_p1_mockup_structure.py:446-449` (quest_actionable contract)

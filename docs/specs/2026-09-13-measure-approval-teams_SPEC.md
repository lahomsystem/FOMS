# 실측 승인 팀 정정 + 화면·서버 잣대 통일 Spec
> 작성일: 2026-09-13 | 상태: 🟢 승인됨(사용자 2026-09-13)

## 0. 왜 — 운영 신고와 실측

영업팀 강민경(`role=MANAGER`, `team=SALES`)이 모바일에서 **실측 완료**를 누르자 서버가 거부했다.

> 현재 단계 승인 권한이 없는 팀입니다. (오버라이드가 필요합니다.)

운영 DB 확인(읽기 전용, 2026-09-13):

| 확인 | 값 |
|---|---|
| 주문 #4596 김태우 | `stage=MEASURE`, 발주사 **라홈** |
| 그 주문 실측 quest | `required_approvals=['CS']` |
| 강민경 | `team=SALES` |

`_authorize_quest_approve`(`foms/api/quest.py:329`)가 `team_has_capability('SALES', ['CS'])` 로 판정해 403 을 낸다.

### 규모

```
실측 단계 발주사 분포   라홈 344 · 하우드 211 · 숨고 119 · …
실측 quest required    ["SALES"] 182건 · ["CS"] 84건
```

라홈이 실측 물량 1위인데 그 주문들을 영업이 못 누른다.

### 두 가지가 동시에 틀렸다

**(1) 규칙이 업무와 다르다.** 사용자 확인: **실측 완료의 주관 팀은 CS 와 영업 둘 다다 — CS 는 자가실측, 영업은 방문 실측.** 그런데 현재 코드는:

| 자리 | 실측 필수 승인 팀 |
|---|---|
| `data/erp_quest_templates.json` | `["SALES"]` — CS 가 자가실측을 못 누른다 |
| `erp_policy_quests.py:125` (라홈) | `["CS"]` — 영업이 방문실측을 못 누른다 |

양쪽 다 한쪽 팀을 배제한다.

**(2) 화면과 서버가 다른 잣대를 쓴다.**

| | 판정 근거 |
|---|---|
| 서버 | quest 의 `required_approvals` |
| 화면 | `can_edit_erp` **또는** `can_modify_domain(SALES_DOMAIN)` |

화면은 `required_approvals` 를 아예 안 본다. 그래서 **서버가 거부할 버튼을 화면이 내민다.** 이 저장소가 여러 번 데인 "한 화면 두 말"(`_actionable_count` docstring 이 같은 규율을 선언한다)과 같은 부류다.

## 1. What

### 1.1 최종 결과물
- 실측 완료는 **CS·영업 모두** 누를 수 있다(발주사 무관).
- 누를 수 없는 사람에게는 **버튼이 안 보인다.** 눌렀는데 거부당하는 일이 없다.

### 1.2 기능 요구사항
1. 실측(MEASURE)·고객컨펌(CONFIRM) 필수 승인 팀 = `["CS", "SALES"]`. 발주사가 라홈이어도 같다.
2. 필수 승인 팀 판정을 **한 함수**로 모은다. 지금은 세 곳(생성·표시·감사)이 각자 라홈 분기를 갖고 있다.
3. 화면의 승인 버튼 노출 조건이 **서버 권한 게이트와 같은 답**을 낸다.
4. 이미 저장된 quest(`required_approvals=['CS']` 84건)도 새 규칙으로 판정된다 — 마이그레이션 없이.

### 1.3 예외/제약
- **라홈 `owner_team=CS` 는 그대로 둔다.** 그건 "누가 주관하는가"(표시·배정)이고 "누가 승인할 수 있는가"와 다른 축이다. 이번 변경은 승인 축만 건드린다.
- **고객컨펌(CONFIRM)도 같이 고친다.** 사용자 확인(2026-09-13): 고객컨펌도 실측과 같이 **CS+영업**이다. 그래서 라홈 분기의 승인 축은 두 단계 모두에서 없앤다.
- ADMIN role bypass·긴급 오버라이드 경로는 그대로 둔다.
- 권한을 **넓히는** 변경이다. 넓히는 방향은 lock-out 을 만들지 않지만, 반대로 "아무나 누른다"가 되지 않도록 팀 술어는 유지한다(VIEWER·타 팀은 여전히 거부).

## 2. How

### 2.1 수정 대상
| 파일 | 변경 |
|---|---|
| `data/erp_quest_templates.json` | MEASURE·CONFIRM `required_approvals` → `["CS","SALES"]` |
| `foms/services/orders/erp_policy_quests.py` | 필수 팀 판정 SSOT 함수 신설 + 라홈 분기에서 MEASURE 승인 축 제거(owner_team 은 유지) |
| `foms/api/quest.py` | `_required_teams_for_stage` → SSOT 위임 |
| `foms/services/erp_quest_display.py` | `_apply_lahom_cs_override` 의 required 축 → SSOT 위임, `can_assignee_approve` 에 팀 술어 AND |
| `foms/services/orders/audit_order_quests.py` | 같은 SSOT 사용 |
| 템플릿 2곳(카드·상세) | 버튼 노출을 `can_edit_erp or …` 가 아니라 **서버와 같은 답** 하나로 |

### 2.2 저장된 값 처리
API 는 지금 `quest.required_approvals` 를 **우선** 읽는다. 그래서 84건이 옛 `['CS']` 로 남아 있으면 새 규칙이 안 먹는다.

→ SSOT 함수는 **정책을 먼저 계산하고, 저장값은 정책의 부분집합일 때만 존중**한다. 즉 저장값이 정책보다 좁으면 정책을 쓴다. 마이그레이션 없이 오늘 바로 풀리고, 나중에 quest 가 다시 저장될 때 자연히 정합해진다.

### 2.3 영향 범위
- 권한 판정 경로라 **코어 변경**이다. 계약 테스트를 함께 넣는다.
- DB 마이그레이션 없음.

## 3. Steps
- [x] SSOT 함수 신설(`resolve_required_approval_teams`) + 3곳 위임(api/quest, erp_quest_display, audit_order_quests)
- [x] 템플릿 기본값 CS+SALES (MEASURE·CONFIRM)
- [x] 화면 게이트를 서버와 같은 답으로 (`can_assignee_approve` 에 팀 술어 AND, 템플릿 2곳에서 `can_edit_erp or` 제거)
- [x] 계약 테스트: 화면이 보여주는 것 == 서버가 허용하는 것(라홈/비라홈 × CS/영업/타팀)
- [x] 운영 재현 케이스(#4596, 강민경 SALES)가 통과로 바뀌는지 확인 — `test_sales_can_now_approve_lahom_measure`

## 4. 검증 기준
- [x] `python -c "import app; print('APP_OK')"` → APP_OK
- [x] 신규 계약 테스트 통과(음성 대조군 포함: 타 팀은 여전히 거부) — `tests/domains/test_measure_approval_teams.py` 8건
- [x] `pytest tests/domains tests/services` 회귀 없음 — 8,606 passed (잔여 실패 7건은 전부 타 세션 파일)
- [x] `scripts/ops/pre_push_smoke.ps1` exit 0

### 검증 메모 — 게이트를 격리 워크트리에서 돌린 이유

공유 워킹트리에서 돌린 첫 게이트는 `test_pac_b1_partials_shared_html_exact_allowlist` 로 red 였다. 원인은 타 세션의 미추적 파일 `templates/partials/shared/channel_mark.html` 이고 이번 변경과 무관하다. HEAD + 이번 staged diff 만 담은 격리 워크트리에서 다시 돌려 **exit 0** 을 확인했다.

그 격리 실행이 실제 결함 1건도 잡았다: `foms/api/quest.py` 의 `flag_modified` 호출이 3줄 밀리면서 `docs/harness/foms_order_mutation_writer_inventory.json` 의 고정 lineno(505)가 틀어져 `test_no_new_external_writers` 가 red 였다. `python tools/harness/order_mutation_writer_scan.py` 로 재생성해 505 → 508 두 자리만 갱신했다.

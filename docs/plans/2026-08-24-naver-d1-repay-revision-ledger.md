# 진행 원장 — D1 개정: 재결제를 '지금 닫기'에서 뺀다 (2026-08-24)

상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개 = 판정 기준)
개정 대상: `docs/specs/2026-08-22-naver-workbench-relation-and-cancel_SPEC.md` **결정 D1**
복귀 기준: `docs/specs/2026-08-19-naver-order-relation-and-fulfillment_SPEC.md` §3 원안
선행 원장: `2026-08-24-naver-workbench-ux-pass-ledger.md` (마지막 줄에 이 위험을 남겼다) ·
`2026-08-24-naver-attach-invisible-result-ledger.md`
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`, HEAD `49b0ba3a`)
**커밋·푸시 없음.** 세 갈래 모두 편집만 했고, 커밋은 주 세션이 아래 §6 검증 뒤에 한다.

---

## 1. 왜 D1 을 개정했나

선행 원장이 남긴 미해결 위험 한 줄이 출발점이다.

> 재결제가 `CLOSE_NOW_RELATIONS` 에 있어 붙이면 발송처리가 '지금 닫기'로 열린다.
> — `2026-08-24-naver-workbench-ux-pass-ledger.md` 마지막 줄

세 가지가 겹쳐서 이건 문구 결함이 아니라 **불가역 호출이 한 클릭 앞에 놓인 자리**였다.

1. **"물건이 따로 나가지 않는다"는 재결제에 거짓이다.** 추가결제(ADDON)는 차액만 더 받은
   것이라 참이다. 재결제(REPAY)는 원 주문을 취소하고 **그 물건값을 다시 낸 것**이라 원
   주문의 물건이 **나중에 한 번 나간다**. 옛 D1(08-22)은 ADDON 논리를 REPAY 단독 근거
   없이 확장한 것이었다.
2. **붙이기 직후 불가역 버튼이 파란색으로 켜져 있었다.** 붙이기는 모달 없이 즉시 실행되고
   (되돌리기 가능) 바로 옆에 `지금 닫기`가 활성 파란 버튼으로 떴다. **두 번째 클릭이
   불가역**이다 — 구매자에게 "배송 시작", 구매확정·정산 시계 시작, `dispatched_any` 가
   되면 취소 버튼 자체가 사라지고 반품 흐름으로 넘어간다.
3. **원안으로의 복귀다.** 2026-08-19 스펙 §3 이 `REPAY → 신규와 같게(발주확인 먼저)` 였다.
   되돌린 것이지 새 규칙을 만든 것이 아니다.

**비용은 클릭 1회다.** `can_confirm = place_pending and not locked` 라 발주확인 버튼은
관계를 보지 않고 그대로 열리고, 발주확인 뒤 발송처리가 열린다 — **막다른 길 없음**.
`ADDON` 은 그대로 둔다(물건이 따로 나가지 않는 게 사실이므로 바로 닫는 게 맞다).

---

## 2. 갈래별 결과

| 갈래 | 무엇을 했나 | 산출물 | 검증 | 판정 |
|---|---|---|---|---|
| **A — 코드** | `CLOSE_NOW_RELATIONS` 에서 REPAY 제거 · 목록 하드코딩 튜플 → 상수 import(SSOT 합침) · pane 폴백/문구/모달 제목 개정 · 회귀 3건 | 코드 3 + 테스트 2 = 5파일 수정 | `tests/services/integrations/` **561 passed** · `APP_OK` · 인벤토리 게이트 24 passed · RED 재현 2종 | **출하 가능** |
| **B — 케이스 1 절차** | 재결제 집 담당자 처리 순서 7단계 확정, 불가역 3종·취소 경계 명시, Q3 답안(안 B) 추천, 후속 Task 3건 | `docs/specs/2026-08-24-naver-repay-case-process_SPEC.md` (신규, 코드 변경 0) | 인용 라인 대조 | **수정 필요 3건**(§4 기각·강등 참조) — 절차 서술 본문은 사용 가능 |
| **C — 승격 계보** | 운영 alembic 계보 재설계(6곳 편집안), blockers 문서 전제 4건 정정, 그래프 시뮬레이션 + 재현 스크립트 | `docs/specs/2026-08-24-naver-production-promotion-chain_SPEC.md` (신규, 마이그레이션 변경 0) | 그래프 head 1개·dangling 0·운영 조상집합 75 일치, alembic resolver 교차검증 | **수정 필요 1건**(부록 A `grep -E`) — 설계 본문은 검증자가 독립 재현 |

---

## 3. 갈래 A — 무엇이 어떻게 바뀌었나 (CEO 직접 확인)

### 3.1 방향성: 불가역 호출은 **좁아지기만** 했다

`git diff` 를 직접 읽고 확인했다. 열리는 쪽으로 간 자리는 **한 곳도 없다**.

| 자리 | 개정 전 | 개정 후 | 방향 |
|---|---|---|---|
| `fulfillment.py:67` `CLOSE_NOW_RELATIONS` | `("ADDON", "REPAY")` | `("ADDON",)` | **좁힘** |
| `fulfillment.py:523` `close_now` | `bool(links) and all(...)` | 식 그대로, 상수만 좁아짐 | 유지 |
| `fulfillment.py:529` `not_confirmed` | close_now 면 발주확인 검사 생략 | 구조 그대로 | 유지 |
| `naver_ingest.py:1985` 목록 `close_now` | 튜플 하드코딩 | 서버 상수 import | **SSOT 합침** |
| `pane:36` 폴백 | `relation in ('ADDON','REPAY')` | `relation == 'ADDON'` | **좁힘** |
| `pane:66` `can_dispatch` | `... or close_now` | 식 그대로 | 유지(입력이 좁아짐) |
| `pane:60` `can_confirm` | `place_pending and not locked` | **무변경** | 막다른 길 없음 |

- 네이버로 나가는 불가역 호출의 **유일한 통로**는 `fulfillment.dispatch_order` 다. 웹
  라우트(`naver_ingest.py:2104`)는 `enqueue_naver_fulfillment` 로 워커에 넘길 뿐이고
  (`jobs/tasks.py:263-264`), 벌크 발송처리 경로는 저장소에 **없다**(`dispatch` 그렙 전수).
  그 단일 통로 앞의 가드가 강화된 것이므로 우회로가 생길 자리가 없다.
- `relation` 대표값 식(ADDON 우선)은 **코드가 한 글자도 안 바뀌었다** — 주석만 사실에 맞게
  고쳤다(옛 주석 "ADDON 이 더 강한 제약"은 이제 거짓이라 걷어냄).
- 목록·배지·벌크 숫자 경로(`next_step` `can_pick` `_actionable_count` `row_kind`)에는
  `close_now` 가 들어가지 않는다(그렙 전수). **목록 표면은 이번 변경으로 바뀌지 않는다.**
- 게이트 OFF 롤백 경로(`templates/admin/naver_triage.html:212-225`)는 이미 전 관계
  발주확인 우선 + `relation == 'ADDON'` 일 때만 발송처리다. 이 파일은 diff 에 없다 —
  **롤백해도 재결제가 다시 열리지 않는다.**

### 3.2 화면이 거짓말하던 자리

`지금 닫기` · `추가결제` · `신규 집` 을 저장소 전체에서 그렙해 남은 자리를 전수 확인했다.

| 문구 | 개정 전 | 개정 후 |
|---|---|---|
| 버튼 라벨 `지금 닫기` (`pane:158`, `:559`) | 재결제 집에도 떴다 | `close_now` 게이트 안 → ADDON 집만 |
| 모달 제목 `'추가결제를 지금 닫습니다'` (`pane:499`) | **하드코딩** — 재결제 집에도 "추가결제" | `close_now_title` = `rel_label` 로 생성(`pane:74`) |
| 안내 `신규 집이라 발주확인이 먼저입니다` (`pane:210`) | 재결제 집을 "신규"라 불렀다(배지는 '재결제') | 재결제 전용 가지 신설(`pane:195-201`) |
| 모달 경고 `이 집은 신규 주문입니다` (`pane:530`) | 재결제 집에도 그렇게 떴다 | 관계별 3가지(`:525-531`) |

남은 `지금 닫기` 4곳은 모두 `close_now` 조건 안이고, 그 밖의 하드코딩은 0건이다.

### 3.3 회귀 3건 — 무엇 때문에 red 인지까지 확인됨

| 테스트 | 무엇을 막나 | RED 근거 |
|---|---|---|
| `test_dispatch_blocks_a_repay_before_place_confirmation` | 재결제가 발주확인 없이 네이버로 나감 + 거절 사유가 링크에 안 남음 | 상수를 옛 값으로 되돌리면 `DID NOT RAISE` (실제로 발송 로그가 찍혔다) |
| `test_a_repay_dispatches_after_place_confirmation` | **막다른 길**(발주확인 뒤에도 막힘) | 상수는 그대로 두고 "재결제 무조건 거절" 1줄 주입 → red. 검증자가 독립적으로 재주입해 재현 |
| `test_repay_stays_locked_before_place_confirmation` | 화면에 파란 '지금 닫기' + 발송처리 잠김 + '신규 집' 오문구 | 옛 상수로 되돌리면 라벨 렌더돼 red. 검증자가 pane 안내 가지를 제거해 `'신규 집이라' not in body` 단언도 red 확인 |

두 번째는 옛 상수에서도 green 이라 **테스트만으로는 수신자 확인이 안 된다** — 그래서
mutation 주입으로 red 를 만들었고, 두 사람(빌더·검증자)이 각각 독립으로 확인했다.
소스에 `TEMP MUTATION` 잔재 0(그렙 전수), 최종 `git diff --stat` = 128 insertions / 25 deletions.

### 3.4 CEO 재검증(3회차, 이 원장 작성 시점)

빌더·검증자와 별개로 한 번 더 돌렸다: `tests/services/integrations/` **561 passed
(130.59s)** · `APP_OK` · `test_failopen_inventory` + `test_audit_coverage_inventory` +
`test_naver_workbench_v3_contract` **48 passed**. `git status --short` 는 M 5 + 문서 3건
(?? 스펙 2 + 이 원장)이고 HEAD 는 `49b0ba3a` 그대로 — **커밋·푸시 0**, 공유 트리 무접촉.

---

## 4. 기각·강등 (보고를 그대로 쓰지 않은 자리)

빌더 보고와 검증 판정을 그대로 옮기지 않았다. 아래는 **틀렸다고 판정해 원장에 남기는** 것이다.

### 4.1 갈래 B (스펙) — 3건 수정 필요

- **"라벨 미등재면 관리자 변경 로그에 영문 코드가 그대로 뜬다" → 거짓.** 직접 확인:
  `foms/services/order_event_display.py:186` 이 `return labels.get(key, "기타 변경")` 이다.
  미등재 타입은 영문이 아니라 **한글 '기타 변경'으로 조용히 뭉개진다**. 스펙 §6 R3 의 완료
  기준("한글 라벨로 뜬다")은 라벨을 빼먹어도 통과하는 **가짜 green** 이다. 완료 기준을
  문자열 일치 + `'기타 변경'이 뜨지 않는다` 부정 단언으로 바꿔야 한다.
- **"주문 4485 는 재결제 6건 1,610,780원" → 근거 없음.** 인용된 원장 두 곳
  (`naver-attach-invisible-result-ledger.md:83`, `naver-workbench-ux-pass-ledger.md:59-60`)
  은 **둘 다 "추가결제 6건 1,610,780원"** 이라 적혀 있다(직접 대조). 게다가 그 관측 자체가
  관계-무관 하드코딩 라벨(`erp-naver-dock.js:158-162`)에서 나온 것이라 관계를 판정할 수
  없는 증거다. R1 완료 기준의 기대값이 이 잘못된 귀속 위에 서 있다.
- **R2 의 계약 §0-3 정합 판정 근거 → 성립 안 함.** 선례로 든 이력 탭 링크
  (`naver_workbench.html:561`)는 **ADMIN 전용**이다(`_can_view_history` = ADMIN only,
  직접 확인). 반면 제안된 도크 링크가 실리는 `/edit/<id>` 는
  `role_required(['ADMIN','MANAGER','STAFF'])` 다. ADMIN 전용 선례로 STAFF 노출을
  정당화했다 — 역할 조건을 완료 기준에 넣거나 §0-3 예외로 명시 승인받아야 한다.
- **"모든 파일:라인을 직접 읽어 확인했다" → 부분 오류(강등).** 표본 대조에서 6곳이 1~4줄
  어긋났다(`pane:114-118`→113-117, `:499`→498, `promotion.py:307-312`→303-305 등).
  결론은 대체로 맞지만 **라인 앵커 신뢰도를 낮춰서** 읽어야 한다 — 스펙 자신이 적은 대로
  심볼·문구를 앵커로 쓴다.

### 4.2 갈래 C (승격 계보) — 1건 수정 필요, 1건 강등

- **부록 A 재현 명령 3줄(`:974-976`)이 실패할 수 없는 검사다.** `grep -n "A|B|C"` 는 `-E`
  가 없어 `|` 를 리터럴로 본다 — 대상 파일 내용과 **무관하게 항상 무출력**이다. 3객체가
  실재하는 `origin/deploy:models.py` 에 대해서도 무출력임을 검증자가 실증했다. 하필 §8
  C안 권고("운영 models.py 에 3객체가 없으므로 여분 컬럼 선행 배포가 무해")가 이 확인에
  얹혀 있다. `grep -nE` 로 고치고, "무출력을 곧바로 부재로 읽지 말라"는 한 줄을 §7.3
  체크리스트에 넣어야 한다. (결론 자체는 별도 `grep -E` 로 참임을 확인함.)
- **미해소로 적어 둔 U5(중복 부모를 alembic 런타임이 받는가) → 해소로 강등.** 검증자가
  `ScriptDirectory.from_config` 로 실제 resolver 를 돌려 heads 1개·85 리비전·
  `iterate_revisions` 순서가 §4.2 기대 로그와 글자 단위로 일치함을 확인했다.

### 4.3 CEO 추가 — 강등해서 남기는 것 (수정 필요 없음)

- **섞인 집 안내 문구의 좁은 거짓 가지.** 새 `{% elif place_pending and rel_label %}`
  (`pane:203-207`)는 "이 집에는 **신규 상품주문이 섞여** 있어"라고 말한다. 대표가 ADDON
  이고 형제가 REPAY 인 집이면 이 문장은 거짓이다. 다만 `attach_link_to_order` 가
  **집 전체 행에 같은 relation 을 쓰므로**(`promotion.py:467` `row.relation = relation`)
  ADDON+REPAY 혼재는 실질적으로 백필 이전 데이터에서만 가능하다 — 실현 가능성 낮음.
  동작(발주확인 먼저)은 어느 경우에도 옳다. **육안 확인 목록에만 올린다.**
- **목록 dict 의 `close_now` 에는 서버와 달리 `bool(members)` 가드가 없다**
  (`naver_ingest.py:1985`). 빈 집이면 `all()` 이 True 를 반환한다. 개정 전에도 같았고
  `_group_queue` 는 링크에서 집을 만들므로 빈 집이 생기지 않는다 — **이번 변경이 연 자리가
  아니다.** 기록만 남긴다.

---

## 5. 갈래 간 모순 — 없음

- **B ↔ A**: B 스펙 머리말(`:9-13`)과 §1.2 표(`:44`)가 `CLOSE_NOW_RELATIONS = ("ADDON",)`
  · "재결제 집도 발주확인이 먼저"로 A 와 **같은 문장**을 쓴다. §2 7단계, §4 함정 서술도
  모두 개정 후 동작 기준이다. 재결제를 바로 닫는다고 말하는 자리는 없다.
- **C ↔ A/B**: C 는 코드·템플릿을 한 줄도 건드리지 않는다(`git status -- migrations/` 0줄).
  계약 §0 표면 6개 어디에도 닿지 않는다.
- **문서 ↔ 코드**: 유일한 갈림은 **개정 대상 스펙 본문**이다 —
  `docs/specs/2026-08-22-naver-workbench-relation-and-cancel_SPEC.md:22` 가 아직
  "발송처리 단독 호출은 ADDON/REPAY 집에만 연다"라고 적혀 있다. 계약 정본과 코드가
  갈리므로 **커밋 전에 이 한 줄을 함께 고쳐야 한다**(아래 §6-0).

---

## 6. 남은 것 — 주 세션이 할 일

### 6.0 커밋 전에 반드시 (코드-문서 계약 갈림)

- [x] `docs/specs/2026-08-22-naver-workbench-relation-and-cancel_SPEC.md` D1 표 개정
      ("ADDON/REPAY" → "ADDON 만", 개정 사유·날짜 명기, 이 원장 링크). §3.3 분기표에
      `REPAY` 행을 따로 세우고, §5 R1 위험 문장도 함께 고쳤다. — **주 세션 처리 완료**

### 6.1 육안 확인 (테스트로 못 잡는 것)

- [ ] 재결제 집 상세: 버튼이 회색 `발송처리`(파란 `지금 닫기` 아님) + 안내가
      "재결제 집이라 발주확인이 먼저입니다" + 배지는 여전히 '재결제'.
- [ ] 재결제 집에서 발주확인 → 발송처리 버튼이 실제로 열리는지(막다른 길 없음 실화면 확인).
- [ ] 발송처리 모달 제목이 "재결제를 지금 닫습니다"가 **아니라** "발송처리를 보내기 전에
      확인하세요" 인지 + 본문이 "이 집은 재결제입니다 — 원 주문의 물건이 나중에 한 번".
- [ ] 섞인 집(대표 ADDON + 신규 형제) 안내 문구 한 번(§4.3 첫 항목).
- ※ 코호트 게이트가 `38` 로 원복돼 있으면 `claude_master` 로 화면이 안 열린다 —
  선행 원장과 같은 제약. `upperkill` 로 확인.

### 6.2 후속 (이번 커밋 범위 밖)

- [x] **B 스펙 must_fix 3건 반영 — 주 세션 처리 완료**(§4.1). §4.4 는 "관계 미확인" 경고
      블록으로 4485 귀속을 걷어냈고, R1 완료 기준은 픽스처 기준으로 바꿨다. R2 는
      **ADMIN·MANAGER 한정**을 기본값으로 못박고 STAFF 회귀 1건을 완료 기준에 추가했다.
      R3 은 실패 모드를 사실(`"기타 변경"` 폴백)로 고치고 부정 단언 + red 확인 절차를 넣었다.
      새 §8 에 미결 U-1(4485 `relation` 실조회)·U-2(STAFF 노출)를 세웠다.
- [ ] R1·R2·R3 착수 판단(스펙은 이제 착수 가능 상태다). R1 은 U-1 없이도 진행 가능하고,
      R2 만 U-2 결정에 따라 범위가 갈린다.
- [x] **C 스펙 부록 A `grep -E` 수정 — 주 세션 처리 완료**(§4.2). 대조군 1줄
      (`origin/deploy` 에서 9매치)을 함께 넣고, §7.3 체크리스트 끝에 "무출력을 곧바로
      부재로 읽지 마라" 경고 블록을 세웠다. `-E` 누락이 실제로 거짓 무출력을 낸다는 것은
      주 세션이 직접 재현해 확인했다(`deploy:models.py` → `-E` 없음 0건 / `-E` 9건).
- [ ] C 스펙 미해소 U1~U4·U6~U8(운영 `alembic_version` 실조회, 스테이징 stamp,
      Railway `preDeployCommand` 실사용 여부 등).
- [ ] `docs/AI_STATUS.md` 갱신(선행 원장과 같은 사유로 미갱신 상태 유지 중이면 함께).

---

## 7. 검증 명령 — 주 세션이 커밋 전에 직접 돌린다

서브에이전트 보고만으로 완료를 선언하지 않는다. **순서대로** 돌리고 각 결과를 눈으로 본다.

```bash
# 0) 자리 확인 — 공유 트리(C:/DEV/FOMS)가 아니어야 한다
cd /c/tmp/foms-s-naver-ingest && pwd && git branch --show-current
git status --short          # M 5 + ?? docs 3(이 원장 포함) 이어야 한다

# 1) 방향성 눈으로 — 열리는 쪽으로 간 자리가 없는지
git diff -- foms/services/integrations/naver_commerce/fulfillment.py
git diff -- foms/web/admin/naver_ingest.py templates/admin/partials/naver_workbench_pane.html

# 2) 본 스위트 + 앱 임포트
python -m pytest tests/services/integrations/ -q
python -c "import app; print('APP_OK')"

# 3) 인벤토리·계약 게이트(줄밀림·네임스페이스·계약)
python -m pytest tests/domains/test_failopen_inventory.py tests/domains/test_audit_coverage_inventory.py -q
python -m pytest tests/domains/test_foms_namespace_imports.py -q
python -m pytest tests/services/integrations/test_naver_workbench_v3_contract.py -q

# 4) 남은 거짓 문구 전수 — 남는 히트는 전부 close_now 게이트 안이어야 한다
grep -rn "지금 닫기\|추가결제를\|신규 집" templates/ static/js/ foms/
grep -rn "close_now\|CLOSE_NOW_RELATIONS" foms/ templates/
grep -rn "TEMP MUTATION\|TEMPMUT" foms/ tests/ templates/     # 0건이어야 한다

# 5) 푸시 직전
pwsh -File scripts/ops/pre_push_smoke.ps1        # exit 0 아니면 push 금지
```

- 커밋은 **자기 세션 몫만** (`git commit -F <UTF-8 메시지 파일> -- <경로>` — 같은 워크트리에
  다른 갈래 산출물이 함께 있다).
- 푸시 대상은 `deploy` 뿐이다. production 승격은 갈래 C 스펙의 미해소 U1~U3 을 푼 뒤
  별도 승인 건이다.
- push 후 CI 는 `gh run list` 로 **전 워크플로**를 확인한다(ci_watch 는 1개만 본다).

---

## 8. 주 세션 직접 검증 (서브에이전트 보고와 무관하게 다시 돌린 것)

`§7` 을 순서대로 돌렸다. 아래는 **내 화면에 실제로 찍힌 값**이다.

| 검증 | 결과 |
|---|---|
| `pwd` / 브랜치 | `/c/tmp/foms-s-naver-ingest` · `session/naver-ingest` |
| 공유 트리 `C:/DEV/FOMS` | 네이버 파일 변경 **0건**(타 세션 WIP 만 존재) |
| `git diff` 3파일 육안 | 불가역 호출은 **좁아지기만** 함. 여는 방향 0곳 |
| `tests/services/integrations/` | **561 passed** (132.59s) |
| `import app` | **APP_OK** |
| failopen + audit coverage + namespace + v3 계약 | **227 passed** |
| `지금 닫기` 전수 그렙 | 히트 2곳 모두 `close_now` 삼항 안(`pane:158`·`:559`). 하드코딩 0 |
| `CLOSE_NOW_RELATIONS` 전수 그렙 | 정의 1곳 + 사용 3곳, **손으로 적은 튜플 0곳** |

### RED 재현 — 내가 직접

상수만 `("ADDON", "REPAY")` 로 되돌리고 새 회귀 3건을 돌렸다:

```
FAILED test_dispatch_blocks_a_repay_before_place_confirmation
FAILED test_repay_stays_locked_before_place_confirmation
2 failed, 1 passed
```

red 사유까지 확인했다 — 화면 쪽은 `assert '지금 닫기' not in body` 가 실제 렌더된 버튼
때문에 터졌고(`ispatch"> 지금 닫기 </button>`), 서버 쪽은 재결제 집이 발주확인 없이
`dispatch` 를 통과했다. 세 번째(`test_a_repay_dispatches_after_place_confirmation`)는
옛 상수에서도 green 이 맞다 — **방향 테스트가 아니라 "막다른 길이 없다"는 반대편 가드**다.
확인 뒤 상수를 즉시 원복하고 `git diff --stat` 로 되돌아온 것을 확인했다.

### 사후 수정 (검증자 판정 반영 — 이 세션에서 처리)

- 계약 정본 갈림 1건: `2026-08-22 SPEC` D1 표 · §3.3 분기표 · §5 R1 (§6.0)
- B 스펙 must_fix 3건 (§6.2)
- C 스펙 must_fix 1건 + 재발 방지 경고 블록 (§6.2)

`-E` 누락이 정말로 거짓 무출력을 내는지도 직접 재현했다:
`git show origin/deploy:models.py | grep -c "A|B|C"` → **0**,
같은 파일 `grep -cE` → **9**. 검증자 주장이 맞다.

# 취소·반품 끝난 주문 → 집 pane 휴지통 버튼 (진행 원장)

- 등급: `**B` / 브랜치: `deploy` / 시작 HEAD: `0ca451554`
- 설계·승인: 완료(캔버스 6종 `12f79ca4-e032-4598-ae1d-7f102e970213`). 이 원장은 구현 진행만 기록한다.
- 급소: **판정 축은 주문**이다. `find_ghost_orders` 가 `order_id` 로 묶고 `canceled == link_count`
  일 때만 유령으로 친다 — 살아 있는 ADDON 집이 붙어 있으면 그 주문은 모집단에서 자동으로 빠진다.
  pane 이 집 단위로 판정식을 새로 만들면 그 안전이 사라진다. 새 헬퍼는 `find_ghost_orders` 의
  버킷 로직을 **그대로 재사용**한다(조회 범위만 그 주문의 링크로 좁힌다).

## Task

| # | 할 일 | 완료 기준 | 상태 |
|---|-------|-----------|------|
| T1 | `ghost_orders.judge_order_discard()` — 주문 1건 판정(can_discard / needs_reason / discard_block) + 단계 한글 라벨 | 새 단위 테스트 통과, `find_ghost_orders` 기존 테스트 무변경 통과 | DONE |
| T2 | `_pane_context` 주입 (전체 렌더·조각 렌더 자동 동일) | pane 조각 응답에도 버튼이 나온다는 테스트 통과 | DONE |
| T3 | pane 템플릿 — 조건부 버튼 + 경고 띠 6종 | 렌더 테스트(열림/사유/닫힘 3종/재결제 경고) 통과 | DONE |
| T4 | `naver-workbench.js` — pane 분기(확인창 1회 → 기존 라우트 → softRefresh) | 소스 계약 테스트 통과 | DONE |
| T5 | CSS 최소 신설(기존 `.alert`·`.wb-fork__reason` 재사용) | 신규 규칙 5줄 이하 | DONE |
| T6 | 자산 핀 `20260904c` → `20260904d` + count==2 계약 5곳 | grep 전수 0건 잔여 | DONE |
| T7 | 유령 띠·라우트 단계 이름 한글화(STAGE_LABELS) | 띠·라우트 문구에 enum 미노출, 감사 원장은 enum 유지 | DONE |
| T8 | 게이트·푸시 | APP_OK · pytest · pre_push_smoke · CI 전 워크플로 green | DONE |

## 기록

- T1~T7 완료. `python -c "import app"` → `APP_OK`.
- `pytest tests/services/integrations/ tests/domains/ -q` → **8328 passed, 5 skipped**
  (신규 15건: 판정 헬퍼 7 · pane 렌더 7 · 띠 단계 한글 1).
- 회귀 1건 수정: `test_naver_claim_phase.py::test_band_shows_pending_row_without_a_button` 이
  "폐기 버튼 없음"을 `data-order-id` 부재로 재던 것 — 이제 pane 에도 같은 판정의 버튼이
  서므로 두 자리가 안 갈린다. 띠는 버튼 id 부재로, pane 은 `disabled` 로 각각 잰다.
- `scripts/ops/pre_push_smoke.ps1` → **PRE-PUSH SMOKE PASSED**.
- 푸시 직전 origin/deploy 가 타 세션 커밋 2개(정산 내보내기 안내 줄)로 앞서 있어 rebase 후
  smoke 재실행(PASSED). AI_STATUS 는 서로 다른 줄이라 충돌 없음 — 상대 문장 잔존 확인.
- deploy `1fd113d55` push. CI 4/4 success(FOMS CI · PG Lane · Harness · perf-gate).
- 운영 승격 1차 시도 보류. 멈춘 이유: production 은 워크벤치 핀이
  `20260904b` 이고 `afb0b4396`(조작 뒤 버튼 수정 · 이전 세션)이 아직 없다. production 기반 임시
  워크트리에서 내 커밋만 cherry-pick 하니 충돌 6곳 — 핀 2곳·핀 계약 테스트 4곳, 그중
  `test_naver_post_action_refresh.py` 는 **production 에 파일 자체가 없다**(afb0b4396 이 만든 파일).
  `cherry-pick 충돌 = 타 세션 의존 신호 → 임의 해결 금지` 규칙에 따라 워크트리를 되돌려 지웠다.
- **운영 반영 완료(PR #297 · production `a5b2697ff`)** — 사용자 결정으로 선행 `afb0b4396` 을
  함께 승격. `be049fd54`(설계 기록 docs)는 skip 했다: 그 문장을 뒤 커밋이 통째로 교체해
  최종본에 남을 내용이 0이다. `docs/AI_STATUS.md` 충돌은 deploy 최종본 채택으로 풀고
  production 고유 줄이 사라지지 않는지 diff 로 확인했다(더 최신 문장으로 대체된 줄만 바뀜).
  승격 트리 직접 검증: `APP_OK` · 8318 passed, 5 skipped · pre_push_smoke PASSED.
  PR 검사 4/4 pass(test · pg-lane · harness · perf-gate), MERGEABLE/CLEAN 확인 후 머지.

## 스테이징 실화면 확인 (2026-09-04 · upperkill 전환)

`lahom-dev` 자산 핀 `20260904d` 서빙 확인. 유령 띠 5건이 단계를 **한글**로 말한다
(`주문접수`·`실측` — 예전 `RECEIVED`·`MEASURE`).

| 캔버스 | 실건 | 결과 |
|--------|------|------|
| ① 열림 + 사실 띠 | link 40 · 주문 #4467 원주현 | "네이버 결제 4건이 전부 취소 확정됐습니다" · 버튼 열림 |
| ② 사유 필요 | link 43 · 주문 #4462 박선미(실측) | 경고 띠 + `왜 삭제하나요?` 칸 + 열린 버튼 |
| ⑥ 재결제 경고 | link 132 · 주문 #4477 전태곤 | 경고가 버튼 **위**, `정리 계획 열기` 동반 |
| 확인창 | 사유 미입력 | alert "왜 접는지 한 줄 적어 주세요…" — 발송 안 됨 |
| 확인창 | 사유 입력 후 | confirm "주문 #4462 (박선미) 을 휴지통으로 보냅니다. 복구할 수 있습니다." — **거부**해서 실데이터 미변경 |

닫힘 3종(③ 부분 취소 · ④ 확정 전 · ⑤ 동거)은 스테이징에 해당 실데이터가 없어 화면으로는
못 봤다 — 실주문을 만들지 않는다. 판정·문구는 단위/렌더 테스트가 고정한다.

QA 중 발견해 고침: 재결제 경고에서 `(25,000원) 이 큐에` 처럼 조사 앞에 공백이 붙던 것
(`{%- endfor -%}`).

## 이번에 하지 않은 것(별건)

- 유령 주문 띠가 20건에서 잘리는데 잘렸다고 말하지 않는 것
- 주문 목록(`templates/orders/index.html:857`) 휴지통 버튼에 관문이 없는 것
- ~~정리 계획 카드의 단계 enum 노출~~ → **해소**(deploy `0c66f6d61`). 정리 계획 카드·옛 주문
  정리 띠·`run_reconcile` 거절 문장 넷을 `stage_label` 로 옮기고, 후보 행과 정리 대기 행에
  `status_label` 을 냈다. `status`(판정 축)는 그대로. 계약 3곳에 `"MEASURE" not in` 반증축을
  붙였다 — 문구만 바꾸고 소스를 안 고치면 통과하던 자리다.
- ~~새로 관측: 생산 KPI 테스트가 flaky~~ → **해소**(PR #299 · production `7de57c03d`).
  flaky 가 아니라 **공휴일 캐시 파일 경합**이었다. `data/holidays_kr_<year>.json` 은 저장소에
  없고(`.gitignore:164`) 미래 날짜 `2099-01-01` 을 쓰는 테스트 파일이 셋이라, xdist 워커들이
  같은 파일을 동시에 만들며 `open("w")` 가 비운 창을 다른 워커가 읽었다. 임시 파일 + fsync +
  `os.replace` 원자 교체로 고치고, Windows 전용 `os.replace` 잠금은 읽기 재시도로 흡수했다
  (끝내 못 읽으면 raise — 조용히 공휴일 0건으로 영업일을 세지 않는다). 회귀 계약 5건 신설.
  아래는 당시 관측 기록이다.
- (관측 원문) `test_production_kpi_slim_equals_full` `0c66f6d61` CI 에서 `JSONDecodeError: Expecting value: line 1 column 1` 로
  1회 실패, 같은 커밋 rerun 은 success. 로컬 `tests/domains/` 단독은 통과. 이 작업과 무관한
  코드(생산 KPI)이고 그 파일들은 이번에 손대지 않았다 — 실행 순서·DB 상태 의존으로 보인다.
  `compute_production_kpis_and_badges` 의 `sd_json['flags']` 투영이 NULL 을 만나면
  SQLAlchemy JSON 역직렬화가 빈 문자열을 파싱하는 자리가 후보다(`_ensure_dict` 는 예외를
  삼키므로 그 앞 단계다). 별건.

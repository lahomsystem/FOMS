# 네이버 반품 승인 · 찾아서 붙이기 · 자동 다시읽기 — 진행 원장

> 2026-08-31 착수. 워크트리 `c:/tmp/nvapv` (origin/deploy `20cdd810` 기준).
> 설계서: `docs/specs/2026-08-31-naver-return-approve_SPEC.md`
> 사용자 승인: 승인 기능 "좋습니다, 만드세요" · 붙이기 "주문 찾아서 붙이기" · 다시읽기 "네 가지 모두".

## 왜 이 셋인가

세 건 다 **같은 뿌리**에서 나왔다: FOMS 가 네이버 사실을 반쪽만 들고 있고, 반쪽짜리 화면이
사람을 판매자센터로 돌려보낸다.

- **T1 승인** — 접수만 있는 버튼은 사람 일을 안 줄인다. 운영 실측: 접수 기능 실호출 **0회**인데
  같은 기간 사람은 판매자센터에서 **9건을 접수+승인 한 번에** 처리했다(22~60초).
- **T2 찾아서 붙이기** — 재결제가 다른 이름·전화·주소로 오면 후보가 0건이라 **붙이기 버튼이
  화면에 없다**. 서버(`/attach`)는 임의 `order_id` 를 이미 받는다. 막힌 건 화면뿐이다.
- **T3 자동 다시읽기** — 발주확인·발송처리·취소·반품접수 뒤 `raw_snapshot` 을 다시 안 읽어
  화면이 옛 사실을 계속 말한다. 다시읽기 배선(`enqueue_naver_refresh`)은 이미 있다.

## Task 목록

| # | 무엇 | 완료 기준 | 상태 |
|---|---|---|---|
| T3 | 조작 4종(발주확인·발송처리·취소·반품접수) 성공 뒤 그 집 자동 다시읽기 | 4종 각각 refresh enqueue 계약 테스트 · 기존 스위트 무회귀 | **DONE** `1504b071` |
| T1a | 승인 서비스 — `client.approve_return_product_order` + `fulfillment._approve_returns` | 보류면 승인 안 함 · 상태 미도달이면 승인 안 함 · 재조회 실패 시 미승인 · body 없음 | **DONE** |
| T1b | 승인 배선 — 큐·태스크·라우트 payload `approve` + 감사 라벨 분리 | 라우트가 `approve` 전달 · 문자열 `"false"` 방어 · `NAVER_INGEST_RETURN_APPROVE_ENQUEUE` 등재 | **DONE** |
| T1c | 승인 화면 — 체크박스(기본 꺼짐)·빨간 띠 한 줄·중간 상태 띠·자산 핀 범프 | 모달 문구 계약 갱신 · `?v=` 핀 2곳 + 계약 2곳 함께 범프 | **DONE** |
| T2 | 후보 0건일 때 주문 찾아서 붙이기 (검색 → 붙이기) | 검색 라우트 계약 · 후보 0건 화면에 진입점 노출 · 붙인 뒤 기존 흐름과 동일 | **DONE** |

## 배포 상태 (2026-08-31)

`deploy` **6f57798b** — T3(`9463f5c9`) + T1(`6f57798b`).
검증: `tests/services/integrations` + `tests/domains` **6699 passed, 5 skipped** ·
`pre_push_smoke` exit 0 · **CI 4/4 green**(Harness · FOMS CI · PostgreSQL Lane · perf-gate).
production 승격은 **안 했다** — 사용자 명시 요청 시에만.

## T2 를 시작할 때 필요한 사실 (조사 다시 하지 마라)

- 매칭 세 축뿐(`order_candidates.find_order_candidates`, 180일 창):
  수취인 전화 **100** · 주문자 전화 **80** · **이름+주소 앞부분** 동시 일치 **60**.
- 못 잡는 조합: **주소만 같고 이름 다름**(가족 대리결제·같은 시공지) ·
  **이름만 같고 주소 다름**(본인·시공지 변경) · 셋 다 다름.
- **막힌 건 서버가 아니라 화면이다.** `POST /admin/naver-ingest/<link_id>/attach` 는
  `order_id` 를 **임의로** 받는다(후보 목록과 무관). 붙이기 버튼(`.wb-attach`)이 후보 표
  행에만 달려 있을 뿐이고, 주문을 검색해 붙이는 UI 가 없다.
- 그래서 T2 는 **읽기 전용 검색 라우트 + pane 진입점 + JS** 면 된다. 붙이기는 기존 라우트
  그대로. 신규 mutation 이 아니라 mutation 계약 5종은 해당 없지만, 검색이 개인정보를
  노출하므로 권한·결과 상한은 기존 워크벤치 규율대로.

## 이번 세션이 비싸게 배운 것 (다음 세션이 반복하지 마라)

- **승인 body 는 없는 것이 공식이다.** 원장의 `approvalData` 근거는 출처(#3693)에 없었다 —
  그 문서는 **취소** 승인 얘기다. 서브에이전트·CEO 보고도 출처를 직접 열어 확인해야 한다.
- **자산 `?v=` 핀은 계약 테스트 2곳이 물고 있다**
  (`test_naver_origin_cleanup.py:321` · `test_naver_workbench_async_result.py:406`).
  템플릿 2곳(CSS·JS)과 함께 범프해야 한다.
- `except` 를 추가하면 **failopen 인벤토리가 드리프트**한다 →
  `python tools/harness/failopen_scan.py` 로 재생성(클린 워크트리에서).
- **`origin/deploy` 가 빠르게 움직인다.** push 전 fetch → rebase → 재검증. 이번에 2회 밀렸다.
- **heredoc 이 문자열을 먹는다.** 편집은 Edit 도구로.

## T3 에서 계약이 뒤집힌 것

처음엔 "조작이 **아예 실패**하면 다시 읽지 않는다"로 썼다가 **틀렸다고 판정**했다.
불가역 경로에서 재조회는 낭비가 아니라 **확인**이다 — 부분 실패의 성공분은 네이버에서
이미 바뀌었고, 통째 실패도 HTTP 오류가 응답 도중 났다면 반영됐을 수 있다. 실패 띠를
보고 온 사람에게 옛 사실을 보여주는 것이 제일 나쁘다. **테스트가 틀렸고 코드가 맞았다.**

## T1 에서 확보한 것

- 승인 규격(공식 문서 v2.86.0 원문): `POST .../claim/return/approve`, **Request Body 없음**.
- 원장의 `approvalData` 근거는 출처(#3693)에 **없다** — 그 문서는 취소 승인 얘기다. 폐기.
- 보류 기전([#398](https://github.com/commerce-api-naver/commerce-api/discussions/398)):
  "일부 주문 클레임 건은 처음부터 '보류' 상태로 요청될 수 있습니다" ·
  트리거는 "반품 비용 결제 방식이 **환불금에서 차감**" · "승인 또는 거부를 진행하려면
  '보류'가 걸려있어선 안 됩니다".
- 반품안심케어 건은 **보류해제 금지**([#3329](https://github.com/commerce-api-naver/commerce-api/discussions/3329)).
  그래서 보류 해제는 **코드에 존재조차 시키지 않고** 계약 테스트가 잠근다.

## 규율 (이번 세션이 비싸게 배운 것)

- **추측으로 불가역 API 를 부르지 않는다.** 승인 body 는 **없는 것이 공식**이다(문서 원문 확인).
  직전 원장의 `approvalData` 근거는 출처에 없었다 — 폐기됨.
- **보류는 우리가 풀지 않는다.** 안심케어 건은 보류해제 자체가 금지다.
- 신규 mutation 계약은 **5종**이다(manifest 2 · audit coverage · 감사 라벨 · docs 읽는 테스트면 ci.yml).
- 커밋은 `git commit -F <msg> -- <경로>`. 공유 저장소라 경로를 명시한다.
- push 전 `pre_push_smoke` exit 0, push 후 **전 워크플로 나열**로 CI 판정.

## T2 에서 만든 것 (2026-08-31)

**읽기 전용 검색 + 기존 붙이기.** 새 mutation 을 파지 않았으므로 mutation 계약 5종은
해당 없다(라우트는 GET, 감사 라벨·manifest 없음 — pane 프래그먼트와 같은 규율).

| 조각 | 자리 |
|---|---|
| 검색 서비스 | `order_candidates.search_orders_for_attach` (+`_search_clauses`·`_search_views`·`_search_reason`) |
| 라우트 | `GET /admin/naver-ingest/<link_id>/order-search?q=` — 게이트 OFF·없는 링크 404 |
| 조각 | `templates/admin/partials/naver_workbench_seek.html` (id 를 달지 않는다 — pane 안에 꽂힌다) |
| pane 진입점 | `naver_workbench_pane.html` 관계 블록 — **후보 0건에서도 렌더**(`wb-seek-q`·`wb-seek-run`) |
| JS | `submitSeek`·`submitSeekAttach`·`showSeekResult` (위임, Enter 키 포함) |
| 계약 | `tests/services/integrations/test_naver_order_search_attach.py` 17종 |

결정 넷 —

1. **술어는 ERP 대시보드 검색을 그대로 쓴다**(`customer_contact_only=True`) — 고객명·전화·
   주소만. 담당자·품목까지 열면 "박 대리 담당 200건"이 붙이기 후보로 뜬다. 주문번호는 그
   술어에 없어서 따로 더한다(숫자는 전화 자릿수 경로가 먼저 가로챈다 — 통합검색이 데인 자리).
2. **붙이기는 `/attach` 그대로다.** `/reconcile`(붙이기+ERP 처리 한 트랜잭션)은 후보 목록 안
   주문만 받는다 — 그 가드를 풀면 취소 처리(휴지통) 갈래가 범용 삭제 경로가 된다. 대신
   **예약금 안내 문장을 검색 결과 버튼이 들고 다닌다**(정리 카드를 안 거치므로 안 실으면
   검색 경로만 그 숫자를 잃는다).
3. **초안·휴지통은 결과에 없다**(`Order.active_filter()`). 자동 후보는 `not_deleted` 인데
   검색은 이름으로 draft 도 부르므로 더 좁힌다 — 초안에 집을 묶으면 승격 레이스에 걸린다.
4. **한 글자는 조회하지 않는다**(성씨 한 자 = 전체 훑기). 다만 **번호 한 자리는 다르다** —
   정확 일치라 id 술어 하나로만 나간다.

뒤집은 계약 둘 (테스트를 고쳤다) —

* `test_attach_section_is_absent_without_candidates` → `test_candidate_table_is_absent_without_candidates`.
  "후보 0건이면 섹션을 안 낸다"가 T2 의 전제와 정면으로 부딪힌다. 지키려던 뜻은 **빈 표를
  내지 않는 것**이라 그 축만 남겼다.
* `test_new_household_gets_no_relation_badge` 의 `data-cmp-section="relation"` 부정 단언 →
  `wb-attach` 부정 단언. "이 집이 후속으로 보이면 안 된다"는 뜻은 배지와 붙이기 버튼이 말한다.

남긴 한계(고치지 않았다) —

* 전화 검색은 `erp_phone_digits`(인덱스 컬럼)를 탄다. 그 컬럼이 빈 **옛 비ERP 주문**은
  `phone` 원문 ILIKE 로만 걸려서, `010-9999-8888` 을 `98888` 로는 못 찾는다. ERP 저장을
  거친 주문은 컬럼이 차 있어 정상이다 — FOMS 전 화면이 쓰는 검색과 같은 한계라 여기서만
  다른 축을 만들지 않았다.
* 검색은 `log_access` 를 남기지 않는다(읽기 전용 GET — pane·상세와 같은 규율).

## 기록

- 2026-08-31 T2 구현. 워크트리 `c:/tmp/nvfind` (origin/deploy `21c38d2e` 기준).
  검증: `tests/services/integrations` **1172 passed** · `tests/domains` **5580 passed, 5 skipped** ·
  `pre_push_smoke` **exit 0** · `APP_OK`.
  자산 핀 `?v=20260831c → 20260831d` (템플릿 2곳 + 계약 테스트 2곳 함께).
  failopen 인벤토리는 재생성해도 **줄번호만** 움직여 되돌렸다(게이트가 lineno-무관).

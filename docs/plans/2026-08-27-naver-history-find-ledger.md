# 진행 원장 — 이력 탭 안내문 3줄 제거 + 찾기 칸 신설 (2026-08-27)

작업 트리 `c:/tmp/foms-s-wbfind` (branch `session/wbfind`, base `origin/deploy` 0ec3b9cf)
T = `templates/admin/naver_workbench.html` · C = `static/css/admin/naver-workbench.css`
J = `static/js/admin/naver-workbench.js` · P = `foms/web/admin/naver_ingest.py`

사용자 요구: (1) 아래 3줄 텍스트만 삭제 (2) 이력 탭에 찾기 칸 신설(UI 조화).
- `큐에 넣기만 합니다 — 실제 호출은 워커가 냅니다.` (T:530)
- `읽기 전용 — 처리는 처리 탭에서 합니다` (T:544)
- `전체 33주문 — 숫자는 모두 주문 단위` (T:541-543 span 통째, 숫자 포함)

## 결정 (CEO 판정)

**D1 자리 — `.wb-filters` 칩 줄 오른쪽 끝(마지막 칩 뒤).**
처리 탭이 "칩 + 찾기 한 줄"(T:210-247)이라 구조가 1:1로 맞고, 새 밴드를 만들지 않아
"텍스트 빼기"(노이즈 제거) 의도와 충돌하지 않는다.
버린 대안: (a) 카드 헤더 우측 — 제목 줄에 도구를 얹는 셈이고 전역
`.card-header{padding:16px!important}` 탓에 칩 줄·표(12px)와 좌우 기준선이 어긋난다.
(c) 표 위 새 도구줄 — 밴드 1줄+경계선 1개를 새로 만들어 노이즈 제거 의도와 정면 충돌.

**D2 문구 — 사용자 원문 그대로. 범위 고지는 note 로.**
placeholder `이 목록에서 · 고객명 · 주문번호 · 제품`, aria-label `이 목록에서 찾기`, 라벨 `찾기`.
placeholder 에 "이 페이지" 를 넣는 안은 폐기 — placeholder 는 타이핑하는 순간 사라져
정작 오해가 나는 시점(좁혀진 뒤)에 화면에 없다. note 는 반대로 그 순간에만 뜬다.
- 이력 note: `{N}주문 / 이 페이지 {M}주문`, `N==0` 이고 `.wb-pager` 가 있으면
  뒤에 ` — 다른 쪽에 있을 수 있습니다`
- 처리 탭 note: `{N}주문 / {M}주문` (불변)

**D3 카운트 span — 통째 삭제(숫자 포함).** 사용자 재확인("위 텍스트만 삭제").
설명 주석(T:539-540)도 함께 삭제 — 지운 문구를 설명하는 주석이 남으면 유령을 쫓게 된다.
손실이 작은 근거: `history.total` 은 탭 배지(T:40)가 이미 내고, 단일 필터 상태에선 눌린 칩이
더 정확한 라벨로 같은 수를 말한다. 남는 위험(수용): status+place 동시 필터에서 교집합 수를
라벨과 함께 말하는 자리가 없어진다 → 후속 후보로만 기록, T:40 은 손대지 않는다.

**D3-b 깨지는 테스트** `test_naver_workbench.py:1446` — 삭제 금지, **회귀 가드로 재작성**.
원래 뜻(필터 걸린 목록을 '전체'라 부르지 않는다)은 이미 `:1417
test_history_total_chip_does_not_claim_a_filtered_number` 가 덮고 있어 중복이 된다.

**D4 JS — `applyFind`(J:359) 셀렉터 합집합 확장.** 이력 전용 분기 신설 안 함.
`'#wb-queue a.wb-row, table.wb-hist tbody tr[data-find]'`. 두 탭 배타 렌더라 언제나 한쪽 모집단만
잡힌다. 이력엔 `#wb-queue`·`#wb-bulk` 가 없어 꼬리 `clearHiddenPicks()`/`syncBulk()` 는 no-op(코드 확인).
`captureFind`/`restoreFind`(J:400/426)는 보존 — 이력에서도 `#wb-run-now`(T:529)→`submitRunNow`
→`watchRun`→`softRefresh`(J:1612) 경로가 살아 있다.
행 검색문자열은 T:311 과 **같은 식**을 `group.` → `row.` 치환해 재사용(row dict 에 4개 값 전부 존재,
P:393-401) → **파이썬 변경 0**. 서버 검색은 하지 않는다: 고객명·제품이 `raw_snapshot`(JSONB)
파생값이고(P:355·368-369) `_link_rows` 는 페이징을 먼저 끝낸 뒤 그 값을 만든다(P:307-314) —
파이썬 필터는 `total`·`pages` 를 거짓말로 만든다. 인덱스 없는 JSONB ilike 는 금지.

**D5 자산 핀 — `?v=20260826g` → `?v=20260827a`**, T:22 · T:693 ·
`tests/services/integrations/test_naver_workbench_async_result.py:357` **3곳 한 커밋**.

**D6 테스트 — 재작성 1 + 신규 4 + 핀 리터럴 교체 1** (아래 T7).

## 사용자 지시와 달라진 점
- 없음(삭제 3줄·placeholder·aria-label 전부 원문 그대로).
- **추가한 것 1건(보고 필요)**: note 에 범위 문구 `이 페이지` 를 넣었다. 이력은 50집씩 서버
  페이지네이션이라 화면 찾기가 닿는 범위가 현재 페이지뿐이기 때문.

## Task
> T1·T7 은 같은 커밋에 — T1 만 넣으면 `test_naver_workbench.py:1446` 이 즉시 red.

- **T1 · 안내문 3줄 삭제** — T:530, T:539-543, T:544
  완료 기준: `grep -c "숫자는 모두 주문 단위\|읽기 전용 — 처리는\|큐에 넣기만 합니다" templates/admin/naver_workbench.html` → 0
  상태: DONE
- **T2 · 찾기 마크업** — `.wb-filters` 안, 마지막 칩(T:571 `</a>`) 뒤 / T:572 `</div>` 앞
  ```html
  <label class="wb-find">
      <span class="wb-find__label">찾기</span>
      <input type="search" id="wb-find" class="wb-find__input" autocomplete="off"
             placeholder="이 목록에서 · 고객명 · 주문번호 · 제품"
             aria-label="이 목록에서 찾기">
  </label>
  <span class="wb-find__note" id="wb-find-note" role="status" aria-live="polite"></span>
  ```
  **금지**: 이 블록 안에 `<div>`·`</div>`·`</a>` 금지(R1·R2). label/span/input 만.
  상태: DONE
- **T3 · 이력 행 `data-find`** — T:586 `<tr class="{{ 'wb-hist--muted' … }}">` 에
  T:311 과 같은 식(`group.` → `row.`). 빈 행(T:645)에는 달지 않는다.
  상태: DONE
- **T4 · CSS 3줄** — C:742 `.wb-filters` 절
  `align-items: center` + `font-size: calc(12px * var(--wb-fs, 1))` + `.wb-filters .wb-find{margin-left:auto}`
  `.wb-find` 정본(C:324-347)은 **수정 금지**(처리 탭과 공유).
  상태: DONE
- **T5 · `applyFind` 확장** — J:359-383. 셀렉터 합집합 + note 분기(D2).
  `onInput`·`clearHiddenPicks`·`captureFind`·`restoreFind` 는 손대지 않는다.
  완료 기준: `node --check static/js/admin/naver-workbench.js`
  상태: DONE
- **T6 · 핀 3곳** → `20260827a`. 템플릿의 `?v=` 총 개수는 2 유지.
  상태: DONE
- **T7 · 테스트** — `test_naver_workbench.py:1446` 재작성(지운 3문구 부활 금지 가드) + 신규
  `test_history_tab_has_a_find_box_over_its_own_rows`(마크업·placeholder 원문·`.wb-filters` 안에 있음)
  + `test_history_rows_carry_the_same_find_text_as_work_rows`(tbody `tr[data-find]` 값·빈 행 제외),
  `test_naver_workbench_async_result.py` 에 JS 소스 계약 2종(합집합 셀렉터·`이 페이지` 문구·
  restoreFind 보존) + 템플릿 문구 부재 + `:357` 핀 리터럴 교체.
  완료 기준:
  `python -c "import app; print('APP_OK')"`
  `python -m pytest tests/services/integrations/test_naver_workbench.py tests/services/integrations/test_naver_workbench_v3_contract.py tests/services/integrations/test_naver_workbench_history_detail.py tests/services/integrations/test_naver_workbench_async_result.py -q`
  상태: DONE

## 회귀 위험 (손대면 안 되는 자리)
| # | 자리 | 규칙 |
|---|---|---|
| R1 | `test_naver_workbench.py:1426` `split('class="wb-filters"')[1].split("</a>")[0]` | 첫 칩 **앞**에 `</a>` 만드는 요소 금지 → 찾기는 마지막 칩 뒤 |
| R2 | `:1441` `…split("</div>")[0]` | `.wb-filters` 안에 `<div>` 금지 |
| R3 | `test_naver_workbench_async_result.py:357` `count("?v=…")==2` | CSS·JS 같은 값으로 둘 다, 총 2개 유지 |
| R4 | `test_naver_workbench_v3_contract.py:527`, `..._history_detail.py:216` | 이력 tbody 에 `<button`·`data-link-id`·`class="btn` 금지 — 붙이는 건 `data-find` 뿐 |
| R5 | `..._v3_contract.py:455-480` id 중복 | 처리 탭 마크업(T:241-247)은 **지우지 않는다**(배타 렌더라 재사용 가능) |
| R6 | C:324-347 `.wb-find` 정본 | 수정 금지, 조정은 `.wb-filters` 스코프에서만 |
| R7 | J:400-444 `captureFind`/`restoreFind` | 삭제·시그니처 변경 금지(이력 softRefresh 경로 생존) |
| R8 | `applyFind` 꼬리 두 호출 | 이력에서 no-op 확인됨 — 가드 새로 넣지 말 것 |
| R9 | `foms/web/admin/naver_ingest.py` | 이번 작업 **파이썬 변경 0** |
| R10 | T:40 이력 탭 배지 | 이번 범위 밖 |

## 완료 기록 (2026-08-27)

- T1~T7 전부 DONE. 검증:
  - `python -c "import app; print('APP_OK')"` → APP_OK
  - `python -m pytest tests/services/integrations/ -q` → **822 passed**
  - `node --check static/js/admin/naver-workbench.js` → exit 0
  - 템플릿 `?v=20260827a` 2개 / `20260826g` 0개
- 실화면 검증(로컬 렌더 + headless 브라우저, 1440·1280):
  - 안내문 3줄 사라짐 · 찾기 칸이 칩 줄 오른쪽 끝 · 1280 에서도 한 줄 유지
  - `주방` 입력 → 3줄 중 1줄, note `1주문 / 이 페이지 3주문`
  - 화면에 글자로 없는 **주문번호**(`2026082703`)로도 걸림 → `data-find` 배선 확인
  - 0건 입력 → `0주문 / 이 페이지 3주문` (쪽이 하나뿐이라 '다른 쪽' 꼬리 없음 — 의도대로)
- 실화면에서 찾은 결함 1건 수정: placeholder 끝 글자('제품')가 잘렸다(입력칸 220px vs 실측
  필요 222px) → `.wb-filters .wb-find__input { width: 240px }` (이력 줄 한정, 정본 불변).
- 리뷰(별도 에이전트): 스펙 준수·코드 품질 두 축 모두 지적 없음.

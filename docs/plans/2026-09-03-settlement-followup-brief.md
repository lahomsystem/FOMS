# 정산 대시보드 후속 v1.2 — 멀티 에이전트 브리프 (2026-09-03)

> 이 파일은 워크플로 에이전트(CEO·워커·검증·리뷰)에게 건네는 **유일한 컨텍스트 원본**이다.
> 세션 히스토리는 붙이지 않는다. 경로는 전부 워크트리 기준 절대 경로다.

## 0. 환경 (절대 규칙)
- 워크트리: `C:/tmp/foms-s-settle-followup` · 브랜치 `session/settle-followup` · base origin/deploy f86ce07ae.
  **모든 명령을 이 디렉토리에서 실행**한다(`cd C:/tmp/foms-s-settle-followup && ...`). `C:/DEV/FOMS` 로 가지 말 것 — 거기서 검증이 돌면 가짜 초록이 난다.
- 셸: bash. 파이썬 출력 인코딩: `PYTHONIOENCODING=utf-8` 를 pytest 앞에 붙인다(cp949 가짜 red 방지).
- **저장소 파일은 CRLF** 다. 편집 도구(Edit)는 그대로 써도 되지만, 파이썬으로 파일을 통째로 다시 쓸 때는 줄끝을 보존한다(`newline=''` 로 읽고 `\r\n` 유지).
- git: **커밋·푸시 금지**(총괄 세션이 한다). `git stash` 금지. 다른 사람 hunk 건드리지 않는다.
- 문제 수정 정책: 근본 원인만. 증상 덮기·`try/except: pass`·`# TODO` 미봉책 금지.
- 응답(최종 텍스트)은 한글. 코드 주석은 이 저장소 관례대로 **왜(why)** 를 한글로 쓴다.

## 1. 이미 끝난 것 (건드리지 말 것, 검증만)
F1(예외 큐 미연결 2갈래)·F2(지급 보류 일자별 상세)가 워크트리에 **미커밋 상태로 적용**돼 있다.
- 커널 `foms/services/settlement_channel.py`: `_build_case_stats` 가 (match_status, link 유무) 로 group by → kpi `unmatched_pending_count`·`unmatched_unlinked_count`; `_unmatched_exceptions` 가 `UNMATCHED`(링크 있음·order_id NULL → `/admin/naver-ingest/triage?link_id=N`)·`UNLINKED`(링크 없음 → `/admin/naver-ingest`) 두 갈래(각각 `_EXCEPTION_CAP`); `_build_holdback(rows)` → `data.holdback = {rows, count, total}`.
- 프론트 `static/js/settlement/channel.js`: `bindKpiToggle`·`renderHoldbackDetail`(`[data-settlement-ch-holdback-detail]`, `HOLDBACK_DETAIL_ID`), `excKindClass` 에 `UNLINKED → 'info'`, 예외 표 위 갈래 안내, `ctx.state.holdbackOpen`.
- CSS `static/css/settlement/settlement-channel.css`: `.s-ch-badge--info`, `.s-ch-kpi-tile--toggle`, `.s-ch-kpi-detail` (파일 끝).
- 핀: 셸 `templates/cs/partials/settlement_dashboard_body.html` 22·409행 채널 2줄 `20260902f → 20260903b`, `tests/domains/test_settlement_channel_render.py::_CHANNEL_PIN = "20260903b"`.
- 테스트: `tests/domains/test_settlement_channel_api.py` 끝에 4개(`test_unmatched_exceptions_split_by_link_presence` 등), `_DATA_KEYS` 에 `holdback`, `_KPI_SCALARS` 에 2키; `tests/domains/test_settlement_channel_render.py` 끝에 3개.
- 원장: `docs/plans/2026-09-02-naver-settlement-ledger.md` Phase F (계약 정본).

## 2. 새 일 — F6 정산 대시보드 글자 크기 조절 모듈
사용자 요청 원문: 운영 `https://lahom-production.up.railway.app/erp/settlement` 정산탭에 **텍스트 크기 조절 모듈**을 넣어라. 참고 마크업(네이버 워크벤치의 것):
```html
<span class="wb-fs" role="group" aria-label="글자 크기">
<button type="button" class="wb-fs__btn" id="wb-fs-down" aria-label="글자 작게" title="글자 작게">−</button>
<span class="wb-fs__now" id="wb-fs-now" aria-live="polite">130%</span>
<button type="button" class="wb-fs__btn" id="wb-fs-up" aria-label="글자 크게" title="글자 크게">+</button>
</span>
```

### 2.1 참고 구현(그대로 이식할 패턴) — 네이버 워크벤치
- 템플릿 `templates/admin/naver_workbench.html` 103~108행.
- JS `static/js/admin/naver-workbench.js` 100~115행(`FONT_STEPS = [1, 1.15, 1.3, 1.5]`, `FONT_KEY`, 버튼 id → 핸들러), 517~560행(`readFontScale`/`applyFontScale`/`stepFontScale`: localStorage try/catch, 끝 단계에서 버튼 `disabled`, 라벨 `Math.round(scale*100)+'%'`).
- CSS `static/css/admin/naver-workbench.css` 44~80행: 루트 변수 `--wb-fs: 1`, **모든 `font-size` 가 `calc(Npx * var(--wb-fs, 1))`**, 조절기 자신(`.wb-fs__*`)만 고정 px, `.btn` 을 쓰지 않는다(전역 `.btn { padding: 10px 20px !important }` 함정 — 좁은 칸에서 글자가 세로로 쪼개진다).
- 계약 테스트 `tests/services/integrations/test_naver_workbench_v3_followup.py` 436~480행 3종: ① 조절기는 **셸**에 있다(pane 조각엔 없다) ② CSS 의 모든 font-size 규칙이 배율을 따른다(조절기 자신만 예외; 규칙 단위로 `}` split 후 정규식) ③ 단계·저장 키 상수 존재.

### 2.2 정산 대시보드 셸 구조(앵커)
- 셸 템플릿 `templates/cs/partials/settlement_dashboard_body.html`: 루트 43행 `<div id="foms-settlement-root" class="foms-settle foms-settlement-root" ...>`; 탭줄 62행 `<div class="s-tabs" role="tablist">`; 집중 모드 버튼 92~95행 `<button class="s-tab s-tab--focus" data-settlement-focus ...>`; 그 뒤 `<span class="s-tabs-meta">`(권한 부제·기준 시각). 자산 핀: 20·21행(css 2), 407·408행(js 2) = 셸 사슬 `20260903a`; 22·409행 채널 사슬 `20260903b`.
- JS `static/js/settlement/dashboard.js`(1990줄): 집중 모드 268~300행(`FOCUS_STORAGE_KEY = 'foms.settlement.focus'`, localStorage try/catch 패턴); **클릭 위임** 1822~1842행 `ctx.root.addEventListener('click', ...)` 안에서 `e.target.closest('[data-settlement-focus]')` 분기; `mount(root)` 1936~1953행(집중 모드 기억 복원 지점 = 글자 배율 복원 지점); 전역 리스너는 1975~1985행 싱글톤 가드 안에 `document.addEventListener` **3개 고정**(계약) — 새 전역 리스너 금지.
- CSS 3파일(정산 화면 전체가 대상): `static/css/settlement/settlement-dashboard.css`(루트 토큰 `.foms-settle {` 35행, `font-size: 14px` 60행 근처; font-size 55곳), `static/css/settlement/settlement-operations.css`(27곳), `static/css/settlement/settlement-channel.css`(55곳). px 가 아닌 font-size 는 0곳.
- 렌더 계약 테스트(반드시 읽고 어기지 말 것): `tests/domains/test_settlement_dashboard_render.py`(핀 단일값 424~470행, 인라인 style 금지 556~580행, 목업 잔재 금지 `_MOCKUP_LEFTOVERS = ("MOCKUP", "예정", "해피콜", "가정치")` 90행 — **"예정" 낱말 금지**(채널 표면 제외), 집중 모드 계약 1229~1260행), `tests/domains/test_settlement_operations_render.py`(핀 967~1000행), `tests/domains/test_settlement_channel_render.py`(`_CHANNEL_PIN`, document 리스너 3개 계약 636행, 채널 표면 "예정"은 "정산 예정일"에만).

### 2.3 F6 계약(CEO 가 확정·보강한다. 아래는 총괄 초안 — 이름은 바꾸지 말 것, 워커가 병렬로 같은 이름을 쓴다)
- 마크업(셸 `.s-tabs` 안, 집중 모드 버튼 **바로 뒤**, `.s-tabs-meta` 앞):
  ```html
  <span class="s-fs" role="group" aria-label="글자 크기" data-settlement-fs>
    <button type="button" class="s-fs__btn" data-settlement-fs-step="-1" aria-label="글자 작게" title="글자 작게">−</button>
    <span class="s-fs__now" data-settlement-fs-now aria-live="polite">100%</span>
    <button type="button" class="s-fs__btn" data-settlement-fs-step="1" aria-label="글자 크게" title="글자 크게">+</button>
  </span>
  ```
  id 대신 `data-settlement-*` 훅(이 셸의 관례, 프래그먼트 스왑 안전). 인라인 `style=` 금지, Jinja JSON 인라인 금지.
- JS(`dashboard.js`): 상수 `FONT_STEPS = [1, 1.15, 1.3, 1.5]`, `FONT_KEY = 'foms.settlement.fontScale'`(init 보다 위, var 호이스팅 함정 주석 참고). `readFontScale()`(localStorage try/catch, 단계 밖 값은 기본), `applyFontScale(root, scale)`(루트 `style.setProperty('--s-fs', ...)`, `[data-settlement-fs-now]` 텍스트, 끝 단계 버튼 disabled), `stepFontScale(root, dir)`. 클릭은 **기존 위임 리스너**에 `e.target.closest('[data-settlement-fs-step]')` 분기 추가. `mount()` 에서 `applyFontScale(root, readFontScale())` 로 복원. 전역 리스너 추가 0.
- CSS: `.foms-settle { --s-fs: 1; }` 토큰 추가 + 3파일의 **모든** `font-size: Npx` → `font-size: calc(Npx * var(--s-fs, 1))` (미디어쿼리 안 포함). 예외는 조절기 자신(`.s-fs__btn`·`.s-fs__now`)뿐. 조절기 스타일은 `.wb-fs` 를 `.s-*` 토큰(`--s-line`, `--s-muted`, `--s-surface-soft`)으로 옮긴다. `.btn` 사용 금지.
- 핀: 셸 4줄 `20260903a → 20260903c`, 채널 2줄 `20260903b → 20260903c`, `_CHANNEL_PIN = "20260903c"`.
- 테스트(신규 `tests/domains/test_settlement_font_scale.py`, **docs/ 를 읽지 않는다** — docs 읽는 테스트는 ci.yml 등재 의무): ① 셸 렌더에 조절기 훅 3종이 정확히 1벌(채널 파셜 단독 렌더에는 0) ② 3 CSS 파일의 font-size 규칙 전부가 `var(--s-fs` 를 문다(조절기 예외) + 루트에 `--s-fs: 1` 선언 ③ dashboard.js 에 상수·함수·위임 분기 존재, `document.addEventListener` 수 3 유지 ④ 템플릿 조절기 블록에 "예정" 없음·`style=` 없음 ⑤ 핀 6줄이 각 사슬에서 단일값(기존 계약이 잡지만 신규 테스트에서 값 자체를 다시 못 박지는 말 것 — 값은 자주 바뀐다).
- 원장 `docs/plans/2026-09-02-naver-settlement-ledger.md` Phase F 표에 F6 행 추가는 **총괄이** 한다(워커는 원장을 편집하지 않는다).

### 2.4 파일 소유권(병렬 충돌 방지 — 절대 규칙)
| 워커 | 편집 허용 파일 | 금지 |
|---|---|---|
| W1 셸·JS | `templates/cs/partials/settlement_dashboard_body.html`(마크업 + 핀 6줄), `static/js/settlement/dashboard.js`, `tests/domains/test_settlement_channel_render.py` 의 `_CHANNEL_PIN` 한 줄 | CSS·다른 테스트 |
| W2 CSS | `static/css/settlement/settlement-dashboard.css`, `settlement-operations.css`, `settlement-channel.css` | 템플릿·JS·테스트 |
| W3 테스트 | 신규 `tests/domains/test_settlement_font_scale.py` 만 | 기존 파일 전부 |
| W4 F1/F2 검증 | `foms/services/settlement_channel.py`, `static/js/settlement/channel.js`, `tests/domains/test_settlement_channel_api.py`, `tests/domains/test_settlement_channel_strip.py`, `tests/domains/test_settlement_channel_export*.py`, `tests/domains/test_settlement_channel_render.py`(단 `_CHANNEL_PIN` 줄 제외) | CSS·셸 템플릿·dashboard.js |
| 통합 검증자 | 위 전부(작은 통합 결함만) | 원장·AI_STATUS |

## 3. 검증 명령(완료 기준 — 주장이 아니라 출력으로)
```bash
cd C:/tmp/foms-s-settle-followup && pwd
node --check static/js/settlement/dashboard.js && node --check static/js/settlement/channel.js
python -c "import app; print('APP_OK')"
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider \
  tests/domains/test_settlement_dashboard_render.py tests/domains/test_settlement_operations_render.py \
  tests/domains/test_settlement_channel_render.py tests/domains/test_settlement_channel_api.py \
  tests/domains/test_settlement_channel_strip.py tests/domains/test_settlement_channel_export.py \
  tests/domains/test_settlement_channel_export_api.py tests/domains/test_settlement_channel_access.py \
  tests/domains/test_settlement_font_scale.py
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider tests/domains/test_foms_namespace_imports.py tests/contracts
PYTHONIOENCODING=utf-8 python -m pytest -q -p no:cacheprovider tests/domains -k "settlement" 
```
W4 는 렌더 계약을 돌릴 때 핀 테스트를 뺀다(`-k "not pin"`) — W1 이 동시에 핀을 옮기는 중이라 그 순간의 red 는 결함이 아니다. 통합 검증자는 전부 포함해 돌린다.

## 4. 함정 목록(메모리에서)
- 정산 셸 자산은 서비스워커 cache-first: CSS/JS 를 고치면 **핀을 안 올리면 실기기가 옛 자산을 실행**한다.
- 공용 부품은 좁은 폭(컨테이너 쿼리)에 실린다 — 고정폭이 `1fr` 을 굶기면 글자가 세로로 선다. 배율 150% 에서 KPI 6열 그리드(`minmax(0,1fr)`)가 넘치면 `.s-ch-kpi-value` 등 폭을 확인.
- `.alert` 는 5초 뒤 자동으로 닫힌다(상시 안내에 쓰지 말 것).
- 프래그먼트 스왑에서 인라인 `DOMContentLoaded` 는 죽는다 — 기존 `mount()`/위임 패턴만 쓴다.
- "예정" 낱말은 요약/실무 표면 금지, 채널 표면은 "정산 예정일"에만.
- 새 pytest 파일이 docs/ 를 읽으면 `test_docs_facing_registry` 가 ci.yml 등재를 요구한다 — 읽지 말 것.

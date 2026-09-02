# 네이버 정산 v1.1 — 구현 계약서 (T12·T13·T14 공용 SSOT, 2026-09-02)

선행: v1 계약서 `docs/plans/2026-09-02-naver-settlement-contracts.md`(배포 완료) · 스펙
`docs/specs/2026-09-02-naver-settlement_SPEC.md` §1(S10·S11·S16)·§6·§7 · 리서치
`docs/research/2026-09-02-naver-settlement/06-ceo-2.md` §B-1·§B-3 · `06-ceo-3.md` §E·§F.3.

**사용자 승인(2026-09-02)**: v1.1 = 세 가지 전부.
1. 요약 탭 크로스 스트립 1줄 (**T12**, ceo-2 S11)
2. 실무 탭 "네이버 정산" 상태 컬럼 11→12칸 + 기존 "정산상태" 컬럼 개명 (**T13**, ceo-2 S16)
3. CSV 내보내기 4종 + 47필드 전량 (**T14**, ceo-2 S10)

**기준 커밋**: 이 문서의 모든 줄 번호는 워크트리 `c:/tmp/foms-s-settle-naver`, 브랜치
`session/settle-naver`, HEAD **`c08b86817`** 기준이다. 총괄이 이 워크트리에 계속 커밋하므로
**착수 전 `git log --oneline -1` 로 SHA 를 확인하고, 줄 번호가 밀렸으면 함께 적어 둔 grep
앵커 문자열로 위치를 다시 잡는다**(줄 번호는 보조, 앵커가 정본).

---

## 0. 공통 규칙 (v1 §0 을 그대로 승계하되 파일 경계만 개정)

- Python: 함수 50줄 이하·docstring·타입힌트 필수. bare except 금지. **네이버 금액 재계산 금지**
  (부호 포함 원값 그대로 — v1 워터폴 부호 사고 `e0480263c` 재발 금지). 날짜는 `Date` 컬럼 값을
  ISO 문자열로만 직렬화. 새 기록 시각은 `foms.services.datetime_kst.now_utc_naive()`.
- API 응답 `{'success','data','error'}` (CSV 응답은 예외 — 아래 §3.2 참조).
- 프론트: 인라인 스타일·jQuery·외부 라이브러리 금지. fetch 는 try/catch + `data.success`.
  Jinja→JS 는 `data-*` 속성. 마크업은 `createElement`+`textContent`.
- 접두어: 채널 표면은 `data-settlement-ch-*` / `.s-ch-*` / `foms-settle-ch-*` 유지.
- 검증은 `pwd` 로 워크트리를 확인하고 실행. `python -m pytest <경로> -q -p no:cacheprovider`,
  `python -c "import app; print('APP_OK')"`, `node --check static/js/settlement/*.js`.

### 0.1 v1.1 이 **새로 여는** 파일 (v1 금지 목록에서 해제)
`static/js/settlement/operations.js` · `templates/cs/partials/settlement_operations_body.html` ·
`foms/services/settlement_rows.py` · `foms/api/cs/settlement.py`(rows 핸들러만) ·
`tests/domains/test_settlement_operations_render.py` · `tests/domains/test_settlement_rows_api.py`
— **전부 T13 전용**이다. T12·T14 담당은 여전히 열지 않는다.

### 0.2 v1.1 에서도 **끝까지 열지 않는** 파일
`static/js/settlement/dashboard.js` · `static/css/settlement/settlement-dashboard.css` ·
`static/css/settlement/settlement-operations.css` · `foms/services/settlement_aggregation.py` ·
`foms/api/cs/settlement.py` 의 `aggregates` 핸들러 ·
`tests/domains/test_settlement_aggregation.py` · `tests/domains/test_settlement_dashboard_api.py`.

**근거(실측)**: `dashboard.js` 는 요약 pane 의 자식 노드를 지우지 않는다. `renderAll()`
(`static/js/settlement/dashboard.js:1609-1621`)은 이름이 정해진 호스트만 채우고, `showState()`
(`:1634-1650`)의 그리드 조작은 `toggle(ctx.els.grid, ...)` **한 줄뿐**(`:1638`)이라
`.s-grid` 안에 서버가 심어 둔 앵커는 살아남는다. `collectEls()`(`:1848-1905`)는 정확한 속성
이름으로만 `querySelector` 하므로 `data-settlement-ch-strip` 은 어느 키에도 안 걸린다.
→ **T12 는 `dashboard.js` 를 한 글자도 고치지 않는다**(ceo-2 §A-3 기각 근거의 실제 실행).

---

## 1. 왜 "엑셀 내보내기"가 삭제됐는가 — 조사 결과와 CSV 설계 제약

### 1.1 사실관계 (인용)

| 근거 | 내용 |
|---|---|
| `docs/AI_STATUS.md:19`, `:350` | 2026-09-01 **"엑셀 내보내기·동선 전면 삭제 deploy(`8f0f2a1d`, 커밋 2개)"** — 대상은 `download_excel`·수납장 `export_excel`·`pandas`/`openpyxl`. 운영 반영 완료(PR #223 · `68f1100d`) |
| `docs/AI_STATUS.md:137` | 2026-08-31 1차: **엑셀 업로드(가져오기)** 제거 — 사유 "운영 15개월 미사용(아티팩트 0행, 마지막 2025-05-28)". 이때는 **"엑셀 다운로드는 유지"**(2026-07-03까지 실사용)였다 |
| `docs/plans/2026-08-31-geocode-prefetch-restore-ledger.md:435-439` §17.1 | 2차(다운로드) 삭제 사유 = **사용자 결정**: "엑셀 다운로드(내보내기)도 필요 없다 — 앞선 §12 에서 '2026-07-03 까지 실사용'이라 보존했으나, **사용자가 불필요하다고 확인**했다" |
| 같은 문서 `:445-449` §17.2 | 부수 삭제: `excel_import.py` 파일·Blueprint·등록 3곳, `storage.py:87-190`, 버튼 2곳, **`requirements.txt` 의 `pandas`·`openpyxl` 2줄** |
| 같은 문서 `:510`, `:594` | 완료 기준에 **"`excel`·`download_excel`·`export_excel` 잔존 grep 0"** |

### 1.2 판정 — **정책적 금지가 아니라 "미사용 + 의존성 정리"였다**

삭제 사유는 보안·권한·감사·성능 어느 것도 아니다. (a) 운영에서 안 쓰였고 (b) 사용자가 불필요하다고
확인했고 (c) 그 대가로 `pandas`/`openpyxl` 두 무거운 의존성을 뗐다. 따라서 **CSV 내보내기는
금지 대상이 아니다.** 실제로 저장소에는 **삭제되지 않고 살아 있는 CSV 내보내기 선례가 둘** 있다:

- 서버 GET CSV: `foms/web/cs/completion_dashboard.py:598-630` (`/completion/export.csv`)
  — `io.StringIO` + `csv.writer` + **UTF-8 BOM(`"\ufeff"`)** + `Content-Disposition: attachment`.
  `@login_required` 뿐이고 감사 기록은 없다.
- 클라 blob CSV: `static/js/settlement/operations.js:682-731` (`exportCsv`)
  — BOM + `\r\n` + `URL.createObjectURL`. 주석이 **"현재 페이지만"** 이라고 스스로 못 박고
  있고(`:707-711`) 그 이유가 "조건 전체를 내리려면 페이지 수만큼 왕복해야 해서 **서버에 파일
  엔드포인트가 생기기 전에는 정직하지 않다**"이다.
  → **T14 가 만드는 것이 정확히 그 "서버 파일 엔드포인트"다.**

### 1.3 그래서 생기는 CSV 설계 제약 (전부 강제)

| # | 제약 | 근거 |
|---|---|---|
| C1 | **새 파이썬 의존성 0.** 표준 라이브러리 `csv`·`io` 만. `pandas`·`openpyxl`·`xlsxwriter` 금지 — 방금 떼어낸 것을 되붙이는 일이다 | §1.1 requirements 2줄 삭제 |
| C2 | **이름에 `excel` 을 쓰지 않는다.** 잔존 grep 0 계약이 살아 있다(`excel`·`download_excel`·`export_excel`). 라우트 `export.csv`, 함수 `..._export_csv`, UI 문구 "CSV 받기" | 같은 ledger `:510`·`:594` |
| C3 | **UTF-8 BOM 필수**(`\ufeff` 선두 1회) + 줄바꿈 `\r\n`. 없으면 Excel 이 한글을 깨서 연다 | 두 선례 모두 |
| C4 | **파일명은 ASCII 만.** 한글 파일명은 `Content-Disposition` 인코딩 함정(RFC 5987)에 걸린다. `naver_settle_case_20260803_20260902.csv` 형태 | `completion_dashboard.py:626` 관례 |
| C5 | **다운로드 1회 = 감사 1행.** 성명(`purchaser_name`)이 실려 나가므로 `log_access(..., action="NAVER_SETTLE_EXPORT_CSV", ...)`. 새 action 코드는 **ACTION_LABELS 등재 필수**(§3.2) | ceo-2 §D-9 |
| C6 | **계좌번호는 CSV 에서도 마스킹.** `mask_account_no()` 를 통과시킨다. "화면은 가리고 파일은 다 준다"는 구멍을 만들지 않는다 | v1 §5 서버 마스킹 원칙 |
| C7 | **GET + 스트리밍.** manifest 2종·audit coverage 게이트는 **mutation(POST/PUT/PATCH/DELETE) 전용**이라 GET 은 대상이 아니다(실측: `docs/harness/foms_audit_coverage_inventory.json` 의 routes 209건 중 **GET-only 0건**). 대신 `yield_per` 제너레이터 + `flask.Response` 로 메모리에 전량을 쌓지 않는다 | §3.2 |
| C8 | **화면보다 많이 낸다는 사실을 말한다.** CSV 는 적재된 원본 47필드 전량이라는 것이 v1 스펙의 명시 약속이므로 화면에 없다고 빼지 않는다. 대신 UI 문구가 "화면보다 많은 필드가 들어 있습니다"라고 말한다 | 스펙 §1 "적재 100% · CSV 100% · 화면 41" |

### 1.4 회계 프로그램(더존·이카운트) import 친화 규칙

| 규칙 | 이유 |
|---|---|
| 헤더 행은 **정확히 1줄**. 병합·부제·빈 줄·합계 행 금지 | 두 프로그램 모두 1행 헤더 매핑 |
| 금액은 **부호 포함 정수 문자열**(`-389000`). 천단위 콤마·`₩`·괄호 음수 금지 | 재계산 금지 + 파서 오독 방지 |
| 날짜는 **`YYYY-MM-DD`** 고정(빈 값은 빈 칸, `-` 금지) | |
| enum 은 **코드 열과 한글 라벨 열을 둘 다** 낸다(`settle_type`, `settle_type_label`) | 프로그램은 코드로 매핑, 사람은 라벨로 검수 |
| 헤더는 **한글 업무명**(`상품주문번호`). 코드명이 필요하면 `주문번호(orderId)` 처럼 괄호 병기 | |
| **주문번호 16자리 지수표기 함정**: `2026082912345678` 을 Excel 이 `2.02608E+15` 로 연다. `="..."` 래핑은 **하지 않는다**(더존·이카운트 임포터가 리터럴로 읽어 깨진다). 원문 그대로 내보내고, **드롭다운 안내 문구**로 "엑셀은 [데이터 → 텍스트/CSV 가져오기]로 열고 주문번호 열을 '텍스트'로 지정하세요"를 상시 노출 | 데이터 변형 금지 |
| `raw_snapshot`(JSON)은 CSV 에 넣지 않는다 — 셀 안 개행·콤마가 임포터를 깨뜨린다. 원본은 화면 행 펼치기(v1 S5)가 담당 | |

### 1.5 미결 1건 (사용자 결정 필요) — **4종인가 5종인가**

승인 문구는 "CSV 4종(건별정산/수수료/부가세 일별/부가세 건별)"인데, 카탈로그 47필드 중
**settle/daily 의 #24~36(13필드)** — `settleAmount`·`payHoldbackAmount`·`minusChargeAmount`·
`settleMethodType`·`bankType`·`depositorName`·`accountNo` 등 — 은 이 4종 어디에도 안 들어간다
(행의 단위가 "하루"라 건별 CSV 에 섞을 수 없다). 즉 **4종만으로는 "CSV 100%" 약속이 산술적으로
깨진다**.

- **권고 = 5종**: 위 4종 + `settle_daily`(일별 정산). 같은 모듈에 컬럼표 1개를 더 다는 비용이
  전부이고, 회계팀의 "통장 입금 대사"가 실제로 필요로 하는 유일한 표다.
- 4종으로 확정하면 그 사실(#24~36 은 화면에서만 본다)을 스펙 §1 의 "CSV 100%" 문구와 함께
  고쳐야 한다. **임의 축소하지 않고 여기 남긴다.**
- 본 계약서의 나머지는 **5종 기준**으로 쓴다(4종 확정 시 `settle_daily` 항목만 지우면 된다).

---

## 2. T12 — 요약 탭 크로스 스트립 1줄 (S11)

목표 문구(ceo-2 §B-3 와이어프레임):
`▸ 정산일 기준 · 네이버:  정산 완료 ₩62.1M · 정산 예정 ₩8.4M · 예외 3건   [네이버 정산 열기 →]`

### 2.1 배치 — 앵커 위치와 그리드 재배치 (**T12 의 유일한 난점**)

**앵커 hunk(1곳)** — `templates/cs/partials/settlement_dashboard_body.html`
grep 앵커: `<div class="s-kpis" id="foms-settle-kpis"></div>` (현재 **:157**). **바로 뒤에** 삽입:

```jinja
      {# 크로스 스트립(S11) — 네이버 정산 축(정산 예정일)의 한 줄. 요약 탭 5타일은 완료일 축이라
         **KPI 줄 바깥 아래**에 두어 시각적으로 가른다. 서버는 빈 앵커만 낸다 — 값·문구는
         `channel.js` 가 채운다(요약 집계 커널·M1 스키마를 한 글자도 안 건드리는 이유).
         ADMIN·회계팀만 본다(판정 SSOT = settlement_channel_access.can_view_channel_settlement). #}
      {% if can_view_channel_settlement %}<div class="s-ch-strip" id="foms-settle-ch-strip"
        data-settlement-ch-strip
        data-settlement-ch-strip-api="/api/settlement/channel"
        data-settlement-ch-strip-tab="channel" hidden></div>{% endif %}
```

- **텍스트 0**: 이 노드는 서버 렌더 시점에 **어떤 한글 문구도 담지 않는다.** 이것은 계약이다 —
  `tests/domains/test_settlement_dashboard_render.py:90` `_MOCKUP_LEFTOVERS` 에 **"예정"** 이
  들어 있고, `_without_channel_surface()`(`:265-292`)는 **채널 탭 버튼과 채널 pane 만** 덜어낸다.
  요약 pane 안에 "정산 예정"이 서버 렌더로 박히면
  `test_rendered_fragment_has_no_mockup_leftovers` ·
  `test_settlement_sources_have_no_mockup_leftovers` 가 **즉시 red** 다.
  문구는 전부 `channel.js`(그 스캔 대상 밖) 소유.
- `hidden` 으로 시작한다. `channel.js` 가 데이터를 받은 뒤에만 연다(값 없이 자리만 차지 금지).

**그리드 재배치(필수)** — `.s-grid` 는 12칸 grid 이고 5장이 **명시 행 좌표**를 갖는다
(`settlement-dashboard.css:237` main `grid-row:2/4`, `:238` side `row 2`, `:283` channel `row 3`,
`:281-282` aging/stages `row 4`). 새 자식에 행 좌표를 안 주면 자동배치가 **row 5(맨 아래)** 로
밀어 "KPI 줄 바로 아래"라는 설계가 깨지고 DOM 순서와 시각 순서가 어긋난다.
`settlement-dashboard.css` 는 열지 않으므로 **`settlement-channel.css` 에서** 뒤집는다
(나중에 로드되고 `:has()` 로 특이도가 더 높다):

```css
/* 요약 탭 크로스 스트립(S11) — 앵커가 있을 때만 요약 그리드 행을 한 칸씩 내린다.
   앵커는 ADMIN·회계팀 렌더에만 존재하므로, 그 밖의 사용자 화면은 좌표가 그대로다. */
.foms-settle .s-grid > .s-ch-strip { grid-column: 1 / -1; grid-row: 2; }
.foms-settle .s-grid:has(> .s-ch-strip) > .s-card--main { grid-row: 3 / 5; }
.foms-settle .s-grid:has(> .s-ch-strip) > .s-side { grid-row: 3; }
.foms-settle .s-grid:has(> .s-ch-strip) > .s-card--channel { grid-row: 4; }
.foms-settle .s-grid:has(> .s-ch-strip) > .s-card--aging,
.foms-settle .s-grid:has(> .s-ch-strip) > .s-card--stages { grid-row: 5; }

/* 좁은 폭에서는 원본이 행 좌표를 auto 로 푼다(settlement-dashboard.css:435-447).
   위 :has() 규칙이 특이도로 이겨 버리므로 **같은 폭에서 되풀어 준다** — 안 풀면
   좁은 화면에 빈 줄이 생긴다(원본 주석 :440-441 이 경고한 그 증상). */
@media (max-width: 1120px) {
  .foms-settle .s-grid:has(> .s-ch-strip) > .s-card--main,
  .foms-settle .s-grid:has(> .s-ch-strip) > .s-side,
  .foms-settle .s-grid:has(> .s-ch-strip) > .s-card--aging,
  .foms-settle .s-grid:has(> .s-ch-strip) > .s-card--stages,
  .foms-settle .s-grid:has(> .s-ch-strip) > .s-card--channel { grid-row: auto; }
  .foms-settle .s-grid > .s-ch-strip { grid-row: auto; }
}
```

> **대안(B안 — 재배치가 시각 회귀를 내면 즉시 전환)**: 앵커를 `.s-grid` **바깥**,
> 그리드 닫는 `</div>`(현재 **:232**) 뒤 · `<div class="s-foot">`(현재 **:234**) 앞에 둔다.
> 그리드 수학이 통째로 사라지고 `showState()` 의 그리드 토글에도 안 묶인다(요약 집계 fetch 가
> 실패해도 스트립은 보인다). 대신 발견성이 떨어진다. **판정 기준**: 1500/1280/1120/720px
> 4폭 스크린샷에서 요약 탭 카드 배치가 v1 과 픽셀 동등하면 A안 유지, 아니면 B안.

### 2.2 API — `view=strip`

`foms/api/cs/settlement_channel.py` `api_settlement_channel()`(현재 **:110-155**)에 분기 1개 추가.
**새 라우트를 만들지 않는다** — 권한 판정·날짜 파싱·채널 검증을 그대로 재사용한다.

```
GET /api/settlement/channel?view=strip[&channel=NAVER][&from=&to=]
  · view 허용 집합 = {"full"(기본), "strip"}. 그 밖 → 400 "view 는 full|strip 중 하나여야 합니다"
  · from/to 미지정 시 기존 기본값(오늘-30 ~ 오늘+14) 그대로
  · 권한: can_view_channel_settlement 실패 → 403(기존 분기 재사용, 문구 동일)
```

응답 `data` (**키 정확 일치 = 계약 테스트 대상**):
```
{
  "channel": "NAVER",
  "basis": "expect",
  "basis_label": "정산 예정일",
  "range": {"from": "2026-08-03", "to": "2026-09-16"},
  "sync": { ...build_channel_dashboard 와 동일한 sync 블록 그대로... },
  "strip": {
    "settled_amount": 62148300,      # kpi.settled_amount 와 동일 정의
    "expected_amount": 8412000,      # kpi.expected_amount 와 동일 정의
    "exception_count": 3,            # len(exceptions)
    "unmatched_count": 3,            # kpi.unmatched_count
    "tab_key": "channel"             # 클릭 시 활성화할 탭 키(JS 하드코딩 금지)
  }
}
```

커널 함수는 `foms/services/settlement_channel.py` **파일 끝(현재 :1096) 뒤에 append**:

```python
def build_channel_strip(session, *, channel="NAVER", date_from, date_to, today=None) -> dict:
    """요약 탭 크로스 스트립 1줄이 필요한 최소 한 벌(읽기 전용)."""
```
- 구현 규율: **`_daily_rows`(:436) → `_daily_totals`(:508) → `_build_case_stats`(:546) →
  `_kpi_block`(:583)** 을 그대로 재사용해 3개 스칼라만 뽑는다. 숫자를 여기서 다시 정의하면
  스트립과 탭이 조용히 갈린다(계약 테스트가 이 동일성을 못 박는다 — §5.1-③).
- 예외 건수는 `_build_exceptions`(:1013) 재사용(현재 구간만, 전기 구간 조회 없음).
- 쿼리 수 목표 **≤ 5**(일별 1 + case group-by 1 + 미매칭 1 + 최근 run 1 + 워터마크 1).
  전기 구간·원장·수수료·VAT 는 **조회하지 않는다**.
- `__all__`(현재 **:58-70**)에 `"build_channel_strip"` 을 알파벳 순으로 추가.

### 2.3 프론트 — `static/js/settlement/channel.js`

**같은 파일 안에 두 번째 마운트 축을 만든다. 새 document 리스너·새 싱글톤은 만들지 않는다.**

- 상수 추가(상단 상수 블록, 현재 :46-49 부근):
  `var STRIP_SELECTOR = '[data-settlement-ch-strip]';`
- `mountAll()`(현재 **:2097-2110**) 끝에 한 줄:
  `document.querySelectorAll(STRIP_SELECTOR).forEach(mountStrip);`
  → 기존 `document.addEventListener('DOMContentLoaded'|'foms:main-content-swapped'|
  'foms:erp-shell-fragment-swapped', mountAll)` 배선(`:2112-2117`)과 말미의 즉시 `mountAll()`
  호출(`:2120`)을 그대로 타므로 **프래그먼트 스왑도 자동 커버**.
- `mountStrip(host)`:
  - `host.dataset.settlementChStripMounted === '1'` 이면 return(호스트당 1회, 기존 규율 복제).
  - **탭 활성화를 기다리지 않는다.** 요약 탭이 첫 화면이므로 페이지 로드 즉시 1회 fetch.
    (`watchTabActivation`(:2017)은 채널 pane 전용이다 — 스트립은 그 관찰 대상이 아니다.)
  - `getJson(url)`(:812) 재사용. 실패는 **조용히 삼킨다** — 스트립은 보조 정보라 요약 탭에
    빨간 배너를 띄우지 않는다. `host.hidden` 을 유지한다.
    (무음 실패 금지 원칙의 예외인 이유를 주석으로 명시: 이 줄이 없어도 요약 탭의 어떤 숫자도
    틀리지 않고, 진짜 상태는 채널 탭이 자기 상태 노드로 말한다.)
  - 렌더: `▸` 리드 + `정산일 기준 · 네이버:` + 3개 값 + `[네이버 정산 열기 →]` 버튼.
    **"매출" 이라는 낱말을 쓰지 않는다**(ceo-2 §B-3 지시 — 전부 "정산").
    버튼 클릭 → `root.querySelector('[data-settlement-tab="channel"]').click()`
    (탭 API 를 새로 만들지 않고 **기존 탭 버튼을 누른다** — `dashboard.js` 무수정 유지).
  - `sync.never` 면 숫자 대신 **"아직 한 번도 동기화되지 않았습니다"**, `sync.stale` 이면
    금액 뒤에 `(N시간 전 기준)` 배지. 0건과 미동기화를 절대 같은 문구로 말하지 않는다.
  - 금액 축약(`₩62.1M`)은 표시 계층에서만(기존 축약 헬퍼 재사용).
- CSS(`settlement-channel.css` 끝, 현재 :489 뒤에 append): `.s-ch-strip` 한 줄 배치
  (flex, 12.5px, 좌측 액센트 바, `--s-*`/`--s-ch-*` 토큰 재사용, 인라인 style 0,
  720px 미만 2줄 wrap).

### 2.4 T12 자산 핀
`channel.js`·`settlement-channel.css` 를 고치므로 **`?v=20260902e` → 다음 값**(권장 `20260903a`)
으로 셸 템플릿 **:22**·**:408** 두 곳과 `tests/domains/test_settlement_channel_render.py:63`
`_CHANNEL_PIN` 을 **함께** 옮긴다(세 곳이 갈리면 `test_channel_asset_pins_are_single_repo_wide` red).

---

## 3. T14 — CSV 내보내기 5종(권고) / 4종(승인 문구)

### 3.1 신규 파일 `foms/services/settlement_channel_export.py`

`foms/services/` **루트 플랫 파일**이다(v1 의 `settlement_channel.py` 와 같은 자리).
- SLG 닫힌집합은 최상위 디렉토리만 본다 → 새 디렉토리를 안 만들면 새 CI 게이트가 안 생긴다.
- PTC 물리 인벤토리 정확일치는 **저장소 루트 · `static/js/runtime/` · `foms/services/common/`
  3곳뿐**(실측: `tests/contracts/runtime/test_ptc_physical_exactness.py:165-198`)이라
  `foms/services/` 루트 플랫 파일은 **등재 불필요**.

공개 API:
```python
CSV_KINDS: tuple[str, ...] = ("case", "commission", "vat_daily", "vat_case", "settle_daily")

#: kind -> ((헤더 한글, 모델 컬럼명, 타입태그), ...)  타입태그 ∈ {"date","money","text","int","enum"}
CSV_COLUMNS: dict[str, tuple[tuple[str, str, str], ...]]

def csv_filename(kind: str, date_from: date, date_to: date) -> str: ...
def iter_settlement_csv(session, *, kind, channel, date_from, date_to,
                        basis="expect", filters=None) -> Iterator[str]:
    """BOM+헤더 1줄을 먼저 yield 하고 데이터 줄을 하나씩 yield 한다(전량 적재 금지)."""
```

- 컬럼표는 **`settlement_channel.py` 의 필드표를 재사용하지 않고 이 파일에 따로 둔다.**
  화면 원장은 41필드, CSV 는 47필드 전량이라 **의도적으로 다른 집합**이다. 다만 두 파일이
  같은 모델 컬럼 이름을 쓰는지는 계약 테스트가 대조한다(§5.3-③).
- enum 컬럼은 **코드 열 + `_label` 열 2개**. 라벨은
  `foms.services.integrations.naver_commerce.settle_enums.label()` 로만 만든다(한글 리터럴 금지).
- `account_no` 는 `settlement_channel.mask_account_no()`(:279) 통과(제약 C6).
- 스트리밍: `session.query(Model).filter(...).order_by(축, Model.id).yield_per(500)`.
- 각 kind 의 축·규모:

| kind | 모델 | 축 | 열 구성(목표) |
|---|---|---|---|
| `case` | `NaverSettleCase`(models.py:3714) | `_BASIS_COLUMN[basis]`, 기본 `coalesce(settle_expect_date, search_date)` | 원본 23 + enum 라벨 3 + `foms_order_id`·`match_status` |
| `commission` | `NaverSettleCommission` | `settle_expect_date` | 원본 20 + enum 라벨 4 |
| `vat_daily` | `NaverVatDaily` | `settle_basis_date` | 원본 12 + `is_final` |
| `vat_case` | `NaverVatCase` | `settle_basis_date` | 원본 19 + enum 라벨 3 |
| `settle_daily` | `NaverSettleDaily` | `settle_expect_date` | 원본 25(계좌 마스킹) + enum 라벨 2 |

### 3.2 라우트 — `foms/api/cs/settlement_channel.py` 파일 끝(현재 :231) 뒤 append

```
GET /api/settlement/channel/export.csv
  params: kind(필수, CSV_KINDS) · channel · from · to · basis · type · q
  권한: can_view_channel_settlement 실패 → 403 **JSON**(파일 자리에 오류 파일을 주지 않는다)
  검증 실패 → 400 JSON(기존 _error() 재사용, 한글 사유)
  성공 → 200 text/csv; charset=utf-8
         Content-Disposition: attachment; filename=<ASCII>
         X-Content-Type-Options: nosniff · Cache-Control: no-store
  구간 폭 상한 = settlement_channel.MAX_RANGE_DAYS(400) 재사용 — 새 상한을 발명하지 않는다
```
```python
return Response(stream_with_context(iter_settlement_csv(...)),
                mimetype="text/csv",
                headers={"Content-Disposition": f"attachment; filename={name}",
                         "X-Content-Type-Options": "nosniff",
                         "Cache-Control": "no-store"})
```
- **감사(C5)**: 응답 생성 **전에** 선기록한다(스트리밍 중 예외로 기록이 유실되지 않게).
  `log_access("네이버 정산 CSV 내보내기", user.id, action=SETTLE_EXPORT_AUDIT_ACTION,
  target_type="settlement_channel", detail={"kind":…, "from":…, "to":…, "channel":…})`.
  행수는 아직 모르므로 detail 에 넣지 않는다(거짓말 금지).
- 모듈 상수: `SETTLE_EXPORT_AUDIT_ACTION = "NAVER_SETTLE_EXPORT_CSV"`
  (기존 `SETTLE_SYNC_AUDIT_ACTION`(:49) 바로 아래).
- **`foms/services/audit_message_display.py` `ACTION_LABELS`(:139-, 기존 항목
  `:174 "NAVER_SETTLE_SYNC_REQUEST": "네이버 정산 동기화 요청"` 옆)에
  `"NAVER_SETTLE_EXPORT_CSV": "네이버 정산 CSV 내보내기"` 를 반드시 등재한다.**
  빠뜨리면 `tests/domains/test_admin_audit_screen_readability_3.py:57`
  `test_every_emitted_action_has_business_label` 이 `foms/**.py` 소스 스캔으로 잡아 **CI red**
  (pre_push_smoke 사각 — 과거 4커밋 연속 red 전례).
- manifest 2종(`foms_order_mutation_policy_manifest.json`·`foms_write_guard_manifest.json`)은
  **등재 불필요**(GET). 근거 §1.3 C7 실측.

### 3.3 UI — `templates/cs/partials/settlement_channel_body.html`
S0 동기화 헤더(**:33-36**)의 `[지금 동기화]` 버튼 **뒤**에 드롭다운 앵커 1개:
```html
    <div class="s-ch-export" id="foms-settle-ch-export" data-settlement-ch-export
      data-settlement-ch-export-api="/api/settlement/channel/export.csv"></div>
```
버튼·메뉴 항목은 `channel.js` 가 그린다(항목: 건별 정산 / 수수료 / 부가세 일별 / 부가세 건별 /
일별 정산). 각 항목은 **현재 화면의 채널·기간·기준일·유형필터·검색어를 그대로 쿼리에 실어**
`window.location.assign(url)` 로 이동한다 — **blob 다운로드 금지**(인앱 웹뷰에서 `blob:`
다운로드가 막히는 프로젝트 함정).
상시 안내 1줄(`.alert` 금지, 자동 닫힘 없는 일반 텍스트):
`화면보다 많은 원본 필드가 들어 있습니다 · 엑셀은 [데이터 → 텍스트/CSV 가져오기]로 열고 주문번호 열을 '텍스트'로 지정하세요`

`tests/domains/test_settlement_channel_render.py:74-97` `_REQUIRED_ANCHORS` 에
`"CSV 내보내기": 'id="foms-settle-ch-export"'` 를 추가한다.

---

## 4. T13 — 실무 탭 "네이버 정산" 컬럼(11→12칸) + "정산상태" → "차감청구"

### 4.1 개명 — 왜 필요하고, 정확히 어디가 빨개지는가

실무 탭의 기존 "정산상태" 컬럼은 **내부 차감청구(부서 귀속 차감) 발행 여부**다
(`foms/services/settlement_rows.py:214-216`
`settlement_issued = bool(isinstance(settlement, dict) and settlement.get("deductions"))`,
값 라벨 `청구완료`/`대기`). 여기에 네이버 정산 상태 컬럼이 들어오면 한 표에 뜻이 다른 "정산"
두 개가 나란히 선다 → **"차감청구"로 개명**한다(스펙 §7-4 가 v1.1 로 미뤄 둔 항목).

| # | 파일:줄(HEAD `c08b86817`) | 현재 | 변경 후 |
|---|---|---|---|
| 1 | `templates/cs/partials/settlement_operations_body.html:75` | `<span class="s-ops-grp-lbl" id="foms-settle-ops-lbl-settlement">정산상태</span>` | `…>차감청구</span>` (id·`aria-labelledby`·`data-settlement-ops-filter="settlement"`·칩 값 `all/pending/issued` 는 **전부 그대로** — API 파라미터다) |
| 2 | 같은 파일 **:182** | `<th scope="col">정산상태</th>` | `<th scope="col">차감청구</th>` |
| 3 | `static/js/settlement/operations.js:684`(`CSV_HEADERS` 13번째) | `'정산상태'` | `'차감청구'` |
| 4 | `tests/domains/test_settlement_operations_render.py:113`(`_GRID_HEADERS`) | `"정산상태"` | `"차감청구"` + 12번째 칸 추가(§4.2) |
| 5 | (선택·권고) `foms/web/cs/completion_dashboard.py:611` 완료 대시보드 CSV 헤더 | `"정산상태"` | `"차감청구"` — 같은 뜻·같은 값. **테스트 0건**(실측)이라 무위험. 다른 화면이므로 사용자 확인 후 |

**개명하지 않는 것**: 칩 라벨 `대기`/`청구완료`, 배지 라벨 `청구완료`/`대기`
(`operations.js:420-423`), 액션 버튼 `정산 청구`(`:437`), API 파라미터
`settlement=all|pending|issued`, CSS 클래스 `s-ops-b--settle-ok/wait`.
**화면 문자열만 바꾸고 계약 키는 안 바꾼다.**

### 4.2 새 컬럼 (12번째, "액션" 바로 **앞**)

```python
_GRID_HEADERS_WITH_CHANNEL = (
    "고객", "채널", "완료일", "출고가", "예약금", "잔금", "과입금",
    "경과일", "현금영수증", "차감청구", "네이버 정산", "액션",
)
```
- 위치 근거: "차감청구"(내부)와 "네이버 정산"(외부)을 **붙여** 두 축을 나란히 읽게 한다.
  "액션"은 언제나 마지막 칸이라는 기존 성질을 지킨다.

**라벨 어휘 — 절대 제약**: 이 컬럼 문구에 **"예정"과 "수수료"를 쓸 수 없다.**
`tests/domains/test_settlement_operations_render.py:66`
`_MOCKUP_LEFTOVERS = ("MOCKUP","예정","가정치","해피콜")` 가 렌더 HTML(`:430-441`)과
**소스 3종**(`:443-448`, `_ALL_SOURCES` = ops 템플릿 + settlement-operations.css +
operations.js)을 스캔하고, `:451-457` `test_no_unbacked_teaser_features_are_rendered` 가
렌더에서 `"수수료"` 를 금지한다. → **채택 라벨**:

| 상태 | 조건 | 배지 문구 | 보조 |
|---|---|---|---|
| 정산완료 | 매칭된 `NaverSettleCase` 중 `settle_complete_date` 가 있는 행이 하나라도 있음 | `정산완료` | 최근 완료일 `MM-DD` |
| 정산대기 | 매칭 행은 있으나 완료일이 전부 없음 | `정산대기` | 가장 이른 `settle_expect_date` 를 `MM-DD` 로(낱말 없이 날짜만) |
| 미매칭 | 채널이 NAVER 인데 매칭된 정산 행 0건 | `미매칭` | — |
| 해당없음 | `row.channel != "NAVER"` | `—`(대시) | — |

**금액은 넣지 않는다**(상태 + 날짜만) — 노출 최소화(§6).

### 4.3 데이터 경로

**모델·인덱스(신규 마이그레이션 필요)** — `naver_settle_case` 에 `foms_order_id` 인덱스가
**없다**(실측: `models.py:3769-3779` 의 `__table_args__` 는 `ix_nsc_channel_search` ·
`ix_nsc_product_order` · `ix_nsc_unmatched` 3개뿐). 실무 탭은 모집단 전량을 도는 hot path 라
인덱스 없이 붙이면 Seq Scan 이 된다.
- `models.py` `NaverSettleCase.__table_args__` 에 1줄 추가:
  `Index('ix_nsc_foms_order', 'channel', 'foms_order_id', postgresql_where=text('foms_order_id IS NOT NULL'))`
- 신규 `migrations/versions/naversettle_01_case_order_index.py`
  (`revision='naversettle_01'`, `down_revision='naversettle_00'`, **상수 리터럴 동결 — models
  import 금지**, `downgrade()` 에 `drop_index` 포함).
- 검증: `upgrade head → downgrade -1 → upgrade head` 왕복 +
  `tests/domains/test_alembic_single_head.py` + `tests/postgres/test_startup_schema.py:106`.

**서비스** — `foms/services/settlement_rows.py`
- `_channel_map()`(**:87-111**)와 **같은 모양**의 배치 조회 1개를 추가한다(N+1 금지):
```python
def _naver_settle_map(db) -> dict[int, dict]:
    """foms_order_id -> {'state': 'done'|'wait', 'date': 'YYYY-MM-DD'|None} (쿼리 1회)."""
```
  구현: `db.query(NaverSettleCase.foms_order_id,
  func.max(NaverSettleCase.settle_complete_date),
  func.min(NaverSettleCase.settle_expect_date))
  .filter(NaverSettleCase.channel == 'NAVER', NaverSettleCase.foms_order_id.isnot(None))
  .group_by(NaverSettleCase.foms_order_id)` — **루프 안에서 다시 조회하지 않는다.**
- `_settlement_row()`(**:155-217**)의 반환 dict 에 키 1개 추가 —
  **단, `include_channel` 이 True 일 때만 키 자체를 만든다**(§6 권한):
  `"naver_settlement": {"state": "done|wait|unmatched", "date": "2026-09-05"|None} | None`
- `_load_rows()`(**:220-240**)·`list_settlement_rows()`(**:361-**)에
  `include_channel: bool = False` 를 통과시킨다(기본 False = 안 실린다).

**API** — `foms/api/cs/settlement.py` `api_settlement_rows()`(**:123-**)
```python
include_channel = can_view_channel_settlement(getattr(g, "current_user", None))
data = list_settlement_rows(..., include_channel=include_channel)
data["channel_settlement_visible"] = include_channel
```

**프론트** — `static/js/settlement/operations.js`
- `renderRows()`(**:447-473**)의 `settlementCell(row)`(:418) 과 `actionCell(ctx,row)`(:427)
  **사이**에 `if (ctx.showChannelCol) tr.appendChild(naverSettleCell(row));`
- `ctx.showChannelCol` = 마운트 시 1회
  `root.hasAttribute('data-settlement-ops-channel-col')` 로 판정한다.
  **행 데이터가 아니라 서버 렌더 표식으로 판정한다** — `<th>` 수와 `<td>` 수가 같은 신호를
  따라야 두 벌이 안 갈린다.
- `CSV_HEADERS`(**:682-685**) 상수를 **함수 `csvHeaders(ctx)`** 로 바꾸고, `csvRow(row)`
  (**:695-705**)를 `csvRow(ctx, row)` 로 바꿔 같은 조건으로 1칸을 더한다.
- 배지 CSS 는 **`settlement-channel.css` 에 넣는다**(클래스 `.s-ch-ops-nv-done`/`-wait`/`-none`).
  이 파일은 회계 권한자에게만 로드되고 컬럼도 그때만 그려지므로 **정확히 같은 조건**이다.
  → `settlement-operations.css` 를 **안 열어도 된다**(그 파일의 목업 스캔·핀 사슬 회피).
  이 3클래스는 **W2-A 가 Wave 2 착수 시점에 먼저 커밋**한다(§8.3).

**템플릿** — `templates/cs/partials/settlement_operations_body.html`
- 루트 `<section>` 에 `{% if can_view_channel_settlement %}data-settlement-ops-channel-col{% endif %}`.
- `<th scope="col">차감청구</th>`(**:182**) 뒤에
  `{% if can_view_channel_settlement %}<th scope="col">네이버 정산</th>{% endif %}`.
- 이 파셜은 셸이 `{% include %}` 하므로 컨텍스트를 상속한다(뷰가 이미 넘긴다:
  `foms/web/cs/settlement_dashboard.py:111`). **단독 렌더(테스트)에서는 Undefined = falsy** 라
  11칸이 나온다 — 그 성질을 그대로 계약으로 쓴다(§5.2).

### 4.4 T13 자산 핀 (놓치기 쉬운 비용)
`operations.js` 를 고치면 핀을 범프해야 하는데,
`tests/domains/test_settlement_operations_render.py:942-963`
`test_wired_shell_includes_the_partial_once_with_pinned_deferred_assets` 가
**ops 자산 2종의 핀 == 요약 탭 `settlement-dashboard.css` 의 핀**을 요구한다
(`_settlement_common_pin()` `:248-263`). 따라서 셸 템플릿의 **:20 · :21 · :406 · :407 네 줄을
같은 새 값으로 함께** 올려야 한다(`settlement-dashboard.css`·`dashboard.js` 는 내용 무수정,
캐시 버스트만). 한 줄만 올리면 `test_settlement_asset_pins_are_single_repo_wide` 가 red.

---

## 5. 테스트 계약 — 무엇이 빨개지고, 무엇을 새로 쓰는가

### 5.1 T12
**빨개지는 기존 테스트: 없음(설계상 0)** — 스트립 앵커에 한글 문구를 넣지 않는 한.
확인 실행: `pytest tests/domains/test_settlement_dashboard_render.py -q` 전량 green.
특히 `test_rendered_fragment_has_no_mockup_leftovers[예정]` ·
`test_settlement_sources_have_no_mockup_leftovers[예정]` 를 **명시적으로 확인**한다.

**갱신** — `tests/domains/test_settlement_channel_render.py`
- `_CHANNEL_PIN`(**:63**) → 새 핀.
- 셸 앵커 검사(파셜 앵커 dict 와 **분리**)에 `'id="foms-settle-ch-strip"'` 추가.
  스트립은 채널 파셜이 아니라 셸 템플릿에 있으므로
  `test_rendered_partial_carries_every_anchor`(파셜 렌더)에 넣으면 영구 red 다.
- `_CHANNEL_MARKUP_NEEDLES`(**:376-383**)에 `"data-settlement-ch-strip"` 추가 →
  `test_denied_actor_receives_no_channel_markup_at_all`(**:394-404**)이
  **STAFF+CS 에게 스트립 앵커 0** 을 자동으로 못 박는다(권한 게이트 무료 검증).

**신규 `tests/domains/test_settlement_channel_strip.py`**
1. `view=strip` 응답 키 정확 일치(`{channel,basis,basis_label,range,sync,strip}`,
   `strip` = `{settled_amount,expected_amount,exception_count,unmatched_count,tab_key}`).
2. 권한 매트릭스: ADMIN 200 / MANAGER+ACCOUNTING 200 / STAFF+ACCOUNTING 200 /
   MANAGER+CS 403 / STAFF+CS 403 / VIEWER 403 / 미인증 = 기존 API 관례.
3. **동일성 계약(핵심)**: 같은 `from/to` 로 `view=strip` 과 기본(full) 을 각각 호출해
   `strip.settled_amount == kpi.settled_amount`, `strip.expected_amount == kpi.expected_amount`,
   `strip.exception_count == len(exceptions)` 를 못 박는다 → 스트립과 탭이 갈라지면 red.
4. `view=bogus` → 400 + 한글 사유.
5. 쿼리 수: `view=strip` 이 full 보다 **적은** 쿼리로 끝난다(SQLAlchemy 이벤트 카운터).
6. `channel.js` 소스 계약 — `document.addEventListener` 가 **3개 그대로**(새 전역 리스너 0),
   `STRIP_SELECTOR` 마운트가 `mountAll()` 안에 있다, 스트립 문구에 **"매출" 0건**.
7. 셸 템플릿 소스 계약 — 스트립 앵커가 `{% if can_view_channel_settlement %}` 안에 있고
   그 블록 안에 한글 문구가 0건이다(§2.1 "텍스트 0" 을 코드로 강제).

### 5.2 T13 — **빨개질 것을 미리 적는다**

| 테스트 | 파일:줄 | 왜 red | 조치 |
|---|---|---|---|
| `test_grid_headers_are_complete_and_in_contract_order` | `test_settlement_operations_render.py:336-344` | `_GRID_HEADERS` 11칸 리터럴 + "정산상태" | **두 갈래로 분리**: 플래그 없이 렌더 → 11칸(`_GRID_HEADERS_BASE`, "차감청구" 포함) / `can_view_channel_settlement=True` 렌더 → 12칸(`_GRID_HEADERS_WITH_CHANNEL`) |
| `test_row_shape_is_exactly_the_agreed_field_set` | `test_settlement_rows_api.py:145-152`(`_ROW_KEYS` `:52-73`) | 행에 `naver_settlement` 키가 붙는다 | ADMIN 케이스는 `_ROW_KEYS \| {"naver_settlement"}`, **STAFF+CS 케이스를 새로 추가**해 `_ROW_KEYS` 정확 일치(키 부재)를 못 박는다 |
| `test_rendered_partial_has_no_mockup_leftovers[예정]` · `test_sources_have_no_mockup_leftovers[예정]` | `:430-448` | 컬럼 문구에 "예정" 을 쓰면 즉시 red | §4.2 어휘표 준수(리뷰 항목) |
| `test_no_unbacked_teaser_features_are_rendered` | `:451-457` | 렌더에 "수수료" 금지 | 동상 |
| `test_wired_shell_includes_the_partial_once_with_pinned_deferred_assets` | `:942-963` | ops 핀 ≠ 요약 핀 | 셸 :20·:21·:406·:407 **네 줄 동시 범프** |
| `test_settlement_asset_pins_are_single_repo_wide` | `test_settlement_dashboard_render.py:439-` | 같은 원인 | 동상 |
| `test_alembic_single_head` · `tests/postgres/test_startup_schema.py:106` | — | 새 마이그레이션 | `down_revision='naversettle_00'` 확인 |

**신규 `tests/domains/test_settlement_ops_channel_column.py`**
1. `_naver_settle_map` 이 **쿼리 1회**(N+1 금지) — 이벤트 카운터.
2. 4상태 판정 매트릭스(완료/대기/미매칭/비네이버) — 실제 행을 시드해 판정.
3. 한 주문에 정산 행이 여럿일 때: 완료가 하나라도 있으면 `done`, 날짜는 **최근 완료일**.
4. 권한: STAFF+CS 응답 행에 `naver_settlement` 키가 **없고** `channel_settlement_visible` False.
5. `operations.js` 소스 계약: 컬럼 렌더가 `ctx.showChannelCol` 게이트 뒤에 있고,
   `csvHeaders(ctx)` 와 `csvRow(ctx,row)` 의 칸 수가 같다.
6. 개명 계약: `templates/` + `static/js/settlement/` 전역에 `정산상태` 문자열 **0건**.

### 5.3 T14 — **신규 `tests/domains/test_settlement_channel_export.py`**
1. 권한 매트릭스(§5.1-② 와 동일). 403 은 **JSON** 이고 `text/csv` 가 아니다.
2. 헤더 계약: 각 kind 의 첫 줄이 `CSV_COLUMNS[kind]` 헤더와 **정확 일치**하고 **순서까지** 계약
   (회계 프로그램 매핑이 열 순서를 기억한다).
3. **47필드 소진 계약**: 5종 CSV 의 모델 컬럼 합집합 ⊇ 5개 모델의 컬럼 전량
   (공통 메타 `id`·`channel`·`raw_snapshot`·`synced_at`·`sync_run_id` 제외). 하나라도 빠지면 red
   — "CSV 100%" 약속을 코드로 강제한다.
4. BOM: 응답 바이트가 `b"\xef\xbb\xbf"` 로 시작. 줄바꿈 `\r\n`.
5. 부호 보존: 음수 픽스처(`pay_settle_amount=-389000`)가 `-389000` 문자열로 나온다
   (`(389,000)`·`389000` 아님).
6. 마스킹: `settle_daily` CSV 의 `account_no` 열이 `****`+뒤 4자리.
7. enum 라벨 열이 `settle_enums` 값과 일치 + **파일 안에 한글 enum 리터럴 0건**(소스 스캔).
8. 감사: 다운로드 1회 → `SecurityLog` 에 `action='NAVER_SETTLE_EXPORT_CSV'` 1행.
9. 라벨 등재: `"NAVER_SETTLE_EXPORT_CSV" in ACTION_LABELS`(중복 안전망).
10. 400: `kind` 미지정/허용 밖, 구간 폭 400일 초과, 날짜 형식 오류.
11. 금지 문자열: 저장소 전역에 `excel`·`openpyxl`·`pandas` 재등장 **0건**(§1.3 C1·C2).
12. 스트리밍: `iter_settlement_csv` 를 직접 호출해 **첫 줄만** 받아도 전량 조회가 안 일어난다.

### 5.4 공통 게이트(세 task 끝난 뒤 총괄)
```
pytest tests/domains/test_settlement_*.py \
       tests/domains/test_admin_audit_screen_readability_3.py \
       tests/domains/test_alembic_single_head.py tests/contracts -q -p no:cacheprovider
python -c "import app; print('APP_OK')"
scripts/ops/pre_push_smoke.ps1        # exit 0
```
→ `.github/workflows/ci.yml` docs-facing 서브셋(**:133-135** 알파벳 순, **CRLF 유지**)에
신규 렌더/계약 테스트 등재 → push(deploy) → `gh run list` 로 **전 워크플로** green 확인
(ci_watch 는 1개만 본다 — 전 워크플로 나열이 판정 기준).

---

## 6. 권한 규칙 (세 task 공통 · 단일 SSOT)

**판정 함수는 하나다**: `foms.services.settlement_channel_access.can_view_channel_settlement(user)`
(`foms/services/settlement_channel_access.py:37-61` — ADMIN, 또는 role ∈ {MANAGER, STAFF} ∧
team == ACCOUNTING ∧ is_active).

| 표면 | 게이트 위치 | 거부 시 |
|---|---|---|
| 요약 스트립 앵커 | 서버 Jinja `{% if can_view_channel_settlement %}`(셸 템플릿) | **마크업 자체가 없다**(클라 숨김 금지) |
| `GET …/channel?view=strip` | 핸들러 진입부(기존 분기 재사용) | 403 JSON `정산 대시보드 열람 권한이 없습니다.` |
| `GET …/channel/export.csv` | 핸들러 진입부 | 403 **JSON**(빈 CSV·오류 CSV 금지) |
| 실무 탭 `<th>네이버 정산</th>` | 서버 Jinja `{% if %}` | th 없음 |
| 실무 탭 행의 `naver_settlement` 값 | **서버가 키를 만들지 않는다**(`include_channel=False`) | 키 부재 |
| 실무 탭 12번째 `<td>` | `ctx.showChannelCol`(서버 렌더 표식) | td 없음 |

**왜 서버 게이트인가**: 실무 탭 rows API 는 `can_view_settlement_dashboard`
(ADMIN·MANAGER·CS/SALES/ACCOUNTING)로 열려 있다 — 회계 탭을 못 보는 CS·영업 담당이 같은
응답을 받는다. 클라에서 컬럼만 감추면 응답 JSON 에 네이버 정산 상태가 그대로 실려 개발자
도구로 보인다(이 저장소의 클라 숨김 금지 원칙). **금액은 어느 표면에도 싣지 않는다**
(컬럼은 상태+날짜만).

**CSV 에는 성명이 실린다**(`purchaser_name`). 이것은 "신규 PII 획득 actor 0"(ceo-2 §D-9)이
아니라 **회계팀 전용 게이트 뒤라서** 성립한다. 그래서 §1.3 C5 의 다운로드 감사가 필수다.

---

## 7. 리스크

| # | 리스크 | 크기 | 완화 |
|---|---|---|---|
| 1 | **요약 그리드 재배치 회귀**(§2.1) — `:has()` 특이도가 좁은 폭 MQ 를 이겨 빈 줄이 생긴다 | 큼(2026-09-02 폭·높이 개편을 막 끝낸 화면) | 1120px MQ 미러 규칙 필수 + 1500/1280/1120/720 4폭 스크린샷 대조 + 실패 시 B안 즉시 전환 |
| 2 | **"예정"·"수수료" 금칙어**(§4.2) — 자연스러운 라벨이 곧바로 CI red | 중 | 어휘표를 착수 전 고정. 구현 직후 `grep -n "예정\|수수료" static/js/settlement/operations.js templates/cs/partials/settlement_operations_body.html` |
| 3 | **핀 사슬**(§4.4) — ops 자산 핀이 요약 핀과 묶여 4줄 동시 범프 | 중 | 셸 템플릿 hunk 는 **총괄 1인이 마지막에 일괄** 적용 |
| 4 | **감사 라벨 미등재**(§3.2) — pre_push_smoke 사각, CI 에서만 red | 중(과거 4커밋 연속 red 전례) | `ACTION_LABELS` 등재를 라우트와 **같은 커밋**에 |
| 5 | **`naver_settle_case` 인덱스 부재**(§4.3) — 실무 탭 TTFB 회귀 | 중~큼(모집단 전량 hot path) | `naversettle_01` 선행 + 머지 전 `EXPLAIN` Seq Scan 0 확인 + 실무 탭 TTFB 전/후 측정 |
| 6 | **CSV 대량 다운로드 메모리** | 작음(관측 1,284행/월 → 1년 ≈ 15k행) | `yield_per(500)` 스트리밍 + 400일 폭 상한(기존 상수 재사용) |
| 7 | **세션 경합** — 총괄이 같은 워크트리에 계속 커밋 중(작업 도중 HEAD 가 `fb69eb20d`→`c08b86817` 로 이동한 실측) | 중 | 각 task 착수 시 `git log --oneline -1` 기록, 줄 번호 대신 grep 앵커 사용, §8.2 소유권 표 강제 |
| 8 | **CSV 4종/5종 미결**(§1.5) | 작음 | 착수 전 사용자 1문 확인. 미확인이면 5종으로 만들고 5번째를 UI 에서만 감춘다(데이터 축소 금지) |
| 9 | **스트립 fetch 무음 실패**가 "숫자가 0" 처럼 보일 위험 | 작음 | 실패 시 **아예 안 그린다**(hidden 유지). 0 을 그리지 않는다 |

---

## 8. Task 표 · 파일 소유권 · 병렬화

### 8.1 완료 기준

| T | 내용 | 완료 기준(전부 충족해야 DONE) |
|---|---|---|
| **T12** | 요약 크로스 스트립 — 커널 `build_channel_strip` + `view=strip` + 셸 앵커 1 hunk + `channel.js` `mountStrip` + CSS + 핀 범프 | ① `git diff --stat static/js/settlement/dashboard.js` = **0줄** ② `pytest tests/domains/test_settlement_dashboard_render.py tests/domains/test_settlement_channel_render.py tests/domains/test_settlement_channel_strip.py -q` green ③ 동일성 계약(§5.1-③) green ④ 4폭 스크린샷에서 요약 카드 배치가 v1 과 동등 ⑤ STAFF+CS 렌더에 `data-settlement-ch-strip` 0건 |
| **T13** | 실무 탭 12칸 + 개명 + 인덱스 마이그레이션 | ① `_GRID_HEADERS` 2갈래 테스트 green ② `_ROW_KEYS` 2갈래 테스트 green ③ 마이그레이션 왕복 + 단일 head ④ `grep -rn "정산상태" templates/ static/js/` 0건 ⑤ ops 소스에 "예정"·"수수료" 0건 ⑥ rows API 쿼리 수 증가 **+1 이하** ⑦ `pytest tests/domains/test_settlement_operations_render.py tests/domains/test_settlement_rows_api.py tests/domains/test_settlement_ops_channel_column.py -q` green |
| **T14** | CSV 5종(또는 4종) + 감사 + UI 드롭다운 | ① 47필드 소진 계약 green ② BOM·부호·마스킹·enum 라벨 계약 green ③ 감사 1행 + `ACTION_LABELS` 등재 ④ `grep -rn "pandas\|openpyxl\|excel" foms/ requirements.txt` 0건 ⑤ 실제 다운로드 파일을 Excel 로 열어 한글·부호 육안 확인(총괄) |

### 8.2 파일 소유권 (한 파일에 두 에이전트 금지)

| 파일 | 소유 |
|---|---|
| `foms/services/settlement_channel.py` | **W1-A**(T12 커널) |
| `foms/services/settlement_channel_export.py`(신규) · `foms/services/audit_message_display.py` | **W1-B**(T14 커널) |
| `models.py` · `migrations/versions/naversettle_01_*.py` · `foms/services/settlement_rows.py` · `foms/api/cs/settlement.py` · `tests/domains/test_settlement_rows_api.py` | **W1-C**(T13 백엔드) |
| `foms/api/cs/settlement_channel.py` · `static/js/settlement/channel.js` · `static/css/settlement/settlement-channel.css` · `templates/cs/partials/settlement_channel_body.html` · `tests/domains/test_settlement_channel_render.py` | **W2-A**(채널 표면 단일 소유 — T12·T14 프론트를 **한 사람이**) |
| `templates/cs/partials/settlement_operations_body.html` · `static/js/settlement/operations.js` · `tests/domains/test_settlement_operations_render.py` | **W2-B**(T13 프론트) |
| `templates/cs/partials/settlement_dashboard_body.html`(스트립 앵커 1 + 핀 4줄) · `.github/workflows/ci.yml` | **총괄만**(마지막 일괄) |
| 신규 테스트 3파일(`..._channel_strip.py` / `..._channel_export.py` / `..._ops_channel_column.py`) | 각 담당 |

### 8.3 병렬화 (파일 겹침 0 확인 완료)

```
Wave 1 (3-way 동시)            Wave 2 (2-way 동시)                Wave 3 (직렬, 총괄)
┌ W1-A  T12 커널      ┐        ┌ W2-A 채널 표면(T12+T14 프론트) ┐   셸 템플릿 5 hunk
├ W1-B  T14 커널      ┤ ─완료→ ├ W2-B 실무 탭 프론트(T13)       ┤ → + ci.yml 등재
└ W1-C  T13 백엔드    ┘        └ (신규 테스트는 각자 자기 파일)  ┘   + 게이트 전수 + push
                                                                     + CI 전 워크플로 + 스테이징 QA
```
- **Wave 1 세 갈래는 파일이 하나도 안 겹친다** → 한 메시지에 Agent 3개 동시 디스패치.
- **Wave 2 의 두 갈래도 안 겹친다.** 유일한 순서 제약: T13 의 배지 CSS 3클래스
  (`.s-ch-ops-nv-*`)를 **W2-A 가 Wave 2 착수 시점에 먼저 커밋**해 둔다(W2-B 는 CSS 파일을
  열지 않는다).
- **T12 와 T14 를 한 에이전트(W2-A)로 묶은 이유**: 둘 다
  `foms/api/cs/settlement_channel.py`·`channel.js`·`settlement-channel.css`·채널 파셜을
  건드린다. 나누면 매 hunk 마다 충돌한다.
- 모델 티어링: W1-A/W1-B = 표준, **W1-C**(마이그레이션·인덱스·권한 분기) = 최상위,
  **W2-A**(그리드 재배치 판정 포함) = 최상위, W2-B = 표준.

### 8.4 진행 원장
`docs/plans/2026-09-02-naver-settlement-ledger.md` 에 T12/T13/T14 행을 추가하고
**wave 별 완료 기준·상태·착수 시점 HEAD SHA** 를 기록한다(compaction 후 재디스패치 방지).

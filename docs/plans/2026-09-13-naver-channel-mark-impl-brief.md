# 네이버 채널 마크 구현 브리프 — A안 (초안)

작성: 2026-09-13 · 브랜치 `deploy` · HEAD `0d98b9c8c`
선행: 기획·목업 브리프 [2026-09-13-naver-icon-customer-cell-brief.md](2026-09-13-naver-icon-customer-cell-brief.md)
사용자 결정(2026-09-13): **A안 — 고객 이름 바로 뒤에 마크**. 고객 열 너비는 기본값 그대로 쓴다(좁히지 않음)
→ C안으로 뒤집을 조건 없음. B안 폐기.

## 0. 범위

**대상은 `/erp/dashboard` 한 페이지의 전 코호트다.** PC 그리드만이 아니라 같은 라우트가 코호트별로
그리는 화면 전부다. 다른 페이지(주문 목록·생산·시공·출고·실측·이력)는 **이번 범위 밖**이다 —
사용자가 대시보드를 지목했다. 다만 `erp_mobile_queue_card_v2.html` 은 6개 페이지가 공유하므로
그 파일을 고칠 때의 누출 규율을 §5 에 적어 둔다.

푸시·배포는 이번 실행에 포함하지 않는다. 총괄이 게이트·스모크를 직접 돌린 뒤에 사용자에게 묻는다.

## 1. 판정 축 (절대 규칙)

```python
structured_data['source'] == "NAVER_SMARTSTORE"   # foms/services/integrations/naver_commerce/constants.py:20 (SOURCE_MARKER)
```

- `LINKED_MARKER_KEY = "naver_linked"`(같은 파일 `:33`)는 **출처가 아니다**. ERP 에서 직접 받은
  주문에 네이버 재결제를 붙인 경우에도 참이 된다. **절대 쓰지 마라.**
- 선례: `foms/services/orders/dashboard_read_model.py:462-467` 의 `candidate_ids` 가 같은 축이다.

## 2. 실측 앵커

| 무엇 | 위치 | 지금 상태 |
|---|---|---|
| 행 DTO 조립 루프 | `foms/services/orders/dashboard_dto.py:49-110` | `sd` 가 `:51` 에서 이미 잡혀 있다 → **추가 쿼리 0** |
| `is_unassigned_intake` 줄 | `foms/services/orders/dashboard_dto.py:95` | 새 필드를 바로 아래에 붙인다 |
| PC 그리드 고객 셀 | `templates/orders/partials/dashboard_grid.html:310-318` | 고객명 + 라홈 로고가 `d-inline-flex ... gap-1` 한 줄에 있다 |
| `담당 미지정` 뱃지 | 같은 파일 `:268-269`, `:408-409` | title 이 `네이버 수집 주문 — 담당자 배정 전` |
| 모바일 v2 히어로 제목 | `templates/orders/partials/dashboard_mobile_v2_body.html:65-68` | `<h2 class="foms-v2h-hero__title">` 안에 고객명 |
| 모바일 큐 카드 제목 | `templates/partials/shared/erp_mobile_queue_card_v2.html:65-82` | 고객명 + 발주사 로고(라홈 39x18 / 하우드 67x18) |
| 태블릿 사이드 시트 머리 | `templates/orders/partials/tablet_dashboard_sheet.html:13` | `<span class="foms-tsheet-head__name">` |
| 대시보드 CSS 링크 지점 | `templates/orders/partials/dashboard_main.html:138` | `{% include 'orders/partials/dashboard_styles.html' %}` 한 곳뿐 |
| 컴포넌트 CSS 관례 | `static/css/components/foms-*.css` + `<link ...>?v=YYYYMMDDx` | `templates/construction/dashboard.html:8-10` 이 본보기 |
| 라홈 로고 실측 | `static/images/lahom-logo.png` 545x253, CSS `height:1.25em; width:auto` | 1.1rem 기준 렌더 22x47.4px |

## 3. 확정 계약 (CEO 가 값만 정밀화하고, 이름은 바꾸지 않는다)

### 3.1 DTO 필드
`dashboard_dto.py:95` 의 `'is_unassigned_intake'` 줄 **바로 아래**에 한 줄:
```python
'channel_source': 'NAVER' if sd.get('source') == SOURCE_MARKER else None,
```
`SOURCE_MARKER` 는 **함수 안 import 를 쓰지 말고** 모듈 상단 import 에 추가한다
(선례: 뱃지 엔드포인트에서 함수 안 import 를 제거한 커밋 `103bc281d`).
`constants.py` 는 의존성 없는 모듈이라 web 이 가져가도 "네이버 HTTP 는 WORKER 단일 출구" 계약을
깨지 않는다(그 파일 docstring 이 명시).

### 3.2 공용 매크로 — 새 파일 하나
`templates/partials/shared/channel_mark.html`
```jinja
{% macro channel_mark(channel_source, size='md') -%}
{%- if channel_source == 'NAVER' -%}
<span class="foms-channel-mark foms-channel-mark--naver foms-channel-mark--{{ size }}"
      role="img" aria-label="네이버 스마트스토어 주문" title="네이버 스마트스토어 주문">
  <svg viewBox="0 0 24 24" focusable="false" aria-hidden="true">
    <rect x="0.5" y="0.5" width="23" height="23" rx="4.75" fill="#03C75A" stroke="#02A34A" stroke-width="1"></rect>
    <path d="M6.5 6 H11.2 L14.6 11.6 V6 H17.5 V18 H12.8 L9.4 12.4 V18 H6.5 Z" fill="#FFFFFF"></path>
  </svg>
</span>
{%- endif -%}
{%- endmacro %}
```
- `channel_source` 가 `None` 이면 **아무것도 렌더하지 않는다**(공백 문자 하나도 남기지 않는다 —
  `{%-` / `-%}` 가 그 일을 한다). 음성 대조군에서 빈 span 이 남으면 안 된다.
- `role="img"` + `aria-label` 은 **바깥 span**, `aria-hidden="true"` 는 **안쪽 svg**. 뒤집지 않는다.
- 색은 SVG 속성으로 직접 박는다(CSS 변수 미사용) — fragment 가 CSS 없이 먼저 그려질 때도
  색이 맞아야 한다.
- 인라인 `style="..."` 속성 금지(ratchet 테스트가 강제).

### 3.3 새 CSS 파일 하나
`static/css/components/foms-channel-mark.css`
```css
/* 판매채널 출처 마크 — 고객명 바로 뒤(A안). 크기는 erp-lahom-logo 와 같은 축(height:1.25em). */
.foms-channel-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  height: 1.25em;
  width: 1.25em;
  flex-shrink: 0;
  vertical-align: middle;
}
.foms-channel-mark svg { display: block; width: 100%; height: 100%; }
.foms-channel-mark--sm { height: 1em; width: 1em; }
```
로드는 `templates/orders/partials/dashboard_styles.html` 에 `<link>` 한 줄 추가, 핀 `?v=20260913a`.
그 파일은 `dashboard_main.html:138` 한 곳에서만 include 되므로 **전 코호트가 한 번에 받는다**.

### 3.4 크기 선택
| 화면 | size | 이유 |
|---|---|---|
| PC 그리드 고객 셀 | `md`(기본) | 본문 1.1rem 옆, 라홈 로고와 같은 높이 |
| 모바일 v2 히어로 제목 | `md` | 제목 글자 크기를 따라간다(em 기준) |
| 모바일 큐 카드 제목 | `md` | 발주사 로고 18px 높이와 나란히 |
| 태블릿 시트 머리 | `md` | |

`sm` 은 지금 쓰는 곳이 없으면 **넣지 마라** — 쓰지 않는 규칙은 부채다.

### 3.5 A안 배치 규칙 (전 화면 동일)
`고객명` → `네이버 마크` → `발주사 로고(라홈 등)` 순서. 마크는 이름과 **같은 inline flex 줄**에 둔다.
간격은 그 줄이 이미 쓰는 `gap` 값을 따른다(PC 그리드는 `gap-1` = `.25rem`). 개별 margin 을 새로
붙이지 않는다.

### 3.6 중복 문구 해소
`dashboard_grid.html:269`, `:409` 의 title `"네이버 수집 주문 — 담당자 배정 전"` →
`"담당자 배정 전"`. 이유: 같은 행에 출처 마크가 생기므로 뱃지가 출처를 다시 말할 필요가 없고,
`is_unassigned_intake` 의 판정 축은 출처가 아니라 **배정 여부**다.

## 4. 파일 소유권 표 (겹치면 안 된다)

| 워커 | 편집 허용 | 금지 |
|---|---|---|
| **W1 백엔드** | `foms/services/orders/dashboard_dto.py`, 신규 `tests/domains/test_dashboard_channel_mark.py` | 템플릿·CSS 전부 |
| **W2 공용 자산 + PC 그리드** | 신규 `templates/partials/shared/channel_mark.html`, 신규 `static/css/components/foms-channel-mark.css`, `templates/orders/partials/dashboard_styles.html`, `templates/orders/partials/dashboard_grid.html` | 모바일·태블릿 템플릿, dto, 테스트 |
| **W3 모바일·태블릿** | `templates/orders/partials/dashboard_mobile_v2_body.html`, `templates/orders/partials/tablet_dashboard_sheet.html`, `templates/partials/shared/erp_mobile_queue_card_v2.html` | 공용 매크로 파일·CSS 파일·PC 그리드·dto·테스트 |

**W3 는 W2 가 만드는 매크로 파일을 쓰지만 만들지는 않는다.** §3.2 의 호출 규약이 계약이므로
파일이 아직 없어도 호출부를 쓸 수 있다:
```jinja
{% from 'partials/shared/channel_mark.html' import channel_mark %}
...
{{ channel_mark(o.channel_source) }}
```
누가 먼저 끝나든 결과는 같다. 통합 검증자가 실제 렌더로 확인한다.

`git` 명령은 **누구도 쓰지 않는다**(총괄 몫). 브랜치 전환 금지. 워킹트리를 여러 창이 공유한다.

## 5. 누출 규율 — `erp_mobile_queue_card_v2.html`

이 파일은 6곳이 공유한다: `orders/partials/dashboard_mobile_queue_sections.html`,
`orders/partials/history_dashboard_body.html`, `construction/partials/mobile_queue.html`,
`measurement/partials/mobile_list.html`, `production/partials/mobile_queue.html`,
`shipment/partials/shipment_mobile_queue.html`.

- 마크는 `order.channel_source` 가 있을 때만 뜬다. 대시보드 DTO(`build_orders_row_dtos`)만 그 키를
  채우므로 나머지 5곳에서는 **렌더되지 않는다**. W3 는 이걸 **테스트가 아니라 코드 주석**으로 남긴다.
- `channel_source` 가 없을 때 `Undefined` 로 터지지 않게 `order.channel_source|default(none, true)`
  형태로 방어한다(다른 DTO 는 dict 라 없는 키 접근이 `Undefined` 다).
- 그 5개 페이지에는 `foms-channel-mark.css` 가 안 실린다. 마크가 안 뜨므로 무해하지만, 주석에
  이 사실을 적어 둔다. 나중에 전파할 때 CSS 부터 실어야 한다는 신호다.

## 6. 검증 명령 (통합 검증자가 전량 돌리고 원문을 보고한다)

```bash
cd "C:/DEV/FOMS"
python -c "import app; print('APP_OK')"
python -m pytest tests/domains/test_dashboard_channel_mark.py -q
python -m pytest tests/domains/test_dashboard_control_tower.py tests/domains/test_dashboard_cache.py -q
python -m pytest tests/harness/ -q -x
```

게이트 종료 코드는 **파이프 뒤에서 읽지 마라**. `cmd; echo "EXIT=$?"` 로 직접 읽는다
(tail 의 exit 을 읽고 smoke 실패를 초록으로 오판한 전례가 있다).

정적 JS 구문·FOUC 감사는 `pre_push_smoke` 범위 밖이다. 이번 변경에 JS 편집은 없으므로 해당 없음 —
**JS 를 건드렸다면 보고에 반드시 적어라.**

## 7. W1 이 쓸 테스트 (계약)

`tests/domains/test_dashboard_channel_mark.py` 는 최소 이 4건을 덮는다. 저장소의 기존 dto 테스트
스타일(픽스처·DB 사용 여부)을 먼저 읽고 그 관례를 따른다.

1. `source == "NAVER_SMARTSTORE"` 인 주문의 행 dto 에 `channel_source == 'NAVER'`.
2. **음성 대조군**: `source` 가 없는 주문의 행 dto 에 `channel_source is None`.
3. **오용 차단**: `structured_data` 에 `naver_linked = True` 만 있고 `source` 가 없으면
   `channel_source is None` — 판정 축이 출처임을 못박는다.
4. 렌더 계약: 대시보드 그리드 템플릿 문자열에 `channel_mark` 호출과 `foms-channel-mark.css` 링크가
   있다(핀 `?v=20260913a` 포함).

전수 확인은 **음성 대조군까지 세야 전수다.** 2번·3번을 빼면 이 테스트는 통과해도 아무것도 증명하지 않는다.

## 8. 함정

- **CRLF 보존.** 편집 전 파일의 줄끝을 확인하고 그대로 유지한다.
- **한글 인코딩.** 파일은 UTF-8. 파이썬으로 편집할 때 `encoding="utf-8"` 명시.
- 치환 스크립트는 **앵커 개수를 먼저 세고 기대와 같을 때만 파일을 쓴다**. 중간에 죽으면 앞 파일만
  반영되는 전례가 있다. 파일마다 고친 자리 수를 보고한다.
- **정규식 keep-both 병합 금지.**
- 로컬 dev 서버가 떠 있으면 Jinja 캐시 때문에 옛 화면을 보고 오판할 수 있다. 렌더 확인은
  새 프로세스에서 한다.
- 이 브리프는 **초안**이다. CEO 는 §3 의 값과 §7 의 테스트를 정밀화해도 된다. §4 파일 경계만 유지한다.

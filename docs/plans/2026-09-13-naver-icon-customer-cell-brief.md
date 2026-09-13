# 네이버 주문 아이콘 — 고객명 옆 표기 UI 기획 브리프 (초안)

작성: 2026-09-13 · 브랜치 `deploy` · HEAD `0d98b9c8c`
단계: **UI 기획 + 목업까지**. 이번 실행은 저장소 소스(`templates/`, `static/`, `foms/`)를 고치지 않는다.
산출물은 전부 스크래치패드 목업 디렉토리에만 쓴다.

## 1. 요청

운영 대시보드(https://lahom-production.up.railway.app/erp/dashboard)의 고객 칸에서,
해당 주문이 네이버 스마트스토어 수집 주문이면 고객 이름 옆에 네이버 아이콘을 띄운다.
UI master 페르소나(시니어 프로덕트 디자이너)로 기획하고, 브라우저로 열어 볼 수 있는 목업을 만든다.

## 2. 실측 앵커 (전부 이번 세션에서 직접 확인함)

### 2.1 고객 칸 렌더 지점 — 이미 같은 자리에 아이콘 선례가 있다

`templates/orders/partials/dashboard_grid.html:310-318`

```jinja
<td data-col-key="customer" data-label="고객" class="fw-bold erp-wrap" style="font-size: 1.1rem; color: #212529; min-width: 120px;">
  <div class="d-flex flex-column gap-1">
    <span class="d-inline-flex align-items-center gap-1 flex-wrap">
      {{ o.customer_name }}
      {% if (o.orderer_name or '')|string and '라홈' in (o.orderer_name or '') %}
      <img src="{{ url_for('static', filename='images/lahom-logo.png') }}" alt="라홈" class="erp-lahom-logo ms-1" title="라홈 주문">
      {% endif %}
    </span>
```

즉 **고객명 + 라홈 로고**가 이미 한 줄(`d-inline-flex`, `gap-1`)에 들어 있다. 네이버 아이콘은
이 줄에 세 번째 원소로 들어가거나, 라홈 로고와 자리를 다투게 된다. 이 충돌을 어떻게 푸느냐가
이번 기획의 1번 질문이다(수집 주문의 발주사는 항상 라홈이라 **두 아이콘이 동시에 참일 수 있다**
— §2.4 참고).

같은 셀 아래쪽에 이미 붙는 뱃지들: 결제 코인/잔금 아이콘(`erp-payment-badge-row`), `라홈시스템`,
`자가실측`, `지방주문`. 즉 고객 칸은 이미 밀도가 높다.

같은 패턴이 다른 화면에도 복제되어 있다(이번 목업의 적용 범위 판단용):
- `templates/orders/index.html:880`
- `templates/production/partials/filters_grid.html:103`
- `templates/construction/partials/filters_grid.html:173`

### 2.2 이미 있는 '네이버 수집' 뱃지 — 중복 표기 위험

`templates/orders/partials/dashboard_grid.html:268-269`, `:408-409`

```jinja
{% if o.is_unassigned_intake %}
<span class="badge bg-warning text-dark" title="네이버 수집 주문 — 담당자 배정 전">담당 미지정</span>
```

이건 "네이버 주문"이 아니라 "**네이버 주문인데 아직 담당자가 없다**"를 뜻한다. 배정되면 사라진다.
새 네이버 아이콘은 배정 여부와 무관하게 항상 떠야 하므로 **판정 축이 다르다**. 두 표식이 같은
행에 동시에 뜰 때 사용자가 "같은 말 두 번"으로 읽지 않게 하는 것이 2번 질문이다.

### 2.3 판정 값 — 서버에 이미 있다

`foms/services/integrations/naver_commerce/constants.py:20`
```python
SOURCE_MARKER = "NAVER_SMARTSTORE"   # structured_data['source'] — 출처 전용
```

같은 파일 `:33` 의 `LINKED_MARKER_KEY = "naver_linked"` 는 **출처가 아니다**(ERP 주문에 네이버
재결제를 붙인 경우도 참). 이번 아이콘의 판정 축은 **출처**이므로 `SOURCE_MARKER` 쪽이다.

읽는 선례: `foms/services/orders/dashboard_read_model.py:462-467`
```python
candidate_ids = [o.id for o in page_orders
                 if (page_sds.get(o.id) or {}).get("source") == SOURCE_MARKER]
```

행 DTO 조립 지점: `foms/services/orders/dashboard_dto.py:80-95` — 여기에 `'is_naver_order'` 같은
불리언 한 칸을 더하면 템플릿이 읽는다(`is_unassigned_intake` 와 정확히 같은 모양, `:95`).
**이번 단계에서는 코드를 고치지 않는다** — 목업은 이 필드가 있다고 **가정**하고 그리고,
기획서에 "구현 시 여기 한 줄" 로 적어 둔다.

### 2.4 수집 주문의 발주사는 항상 라홈이다

`constants.py:48` `DEFAULT_ORDERER_NAME = "라홈"`.
즉 네이버 수집 주문은 §2.1 의 라홈 로고 조건(`'라홈' in orderer_name`)도 **항상 참**이다.
따라서 목업은 "네이버 아이콘 + 라홈 로고가 나란히 뜨는 행"을 반드시 표본에 넣어야 한다.
이걸 어떻게 처리할지(둘 다 표시 / 네이버가 라홈을 대체 / 묶음 표기)가 3번 질문이다.

### 2.5 아이콘 자산이 없다

`static/images/` 에 네이버 아이콘 파일이 **없다**(`lahom-logo.png`, `lahom-logo-en.png`,
`lahom-company-stamp.png` 뿐). 그러므로 목업은 **인라인 SVG** 로 그린다 — 자산 핀(`?v=`),
R2 업로드, 파일 추가가 없어 기획 단계에서 가장 싸다. 네이버 브랜드 마크는 초록 사각형(#03C75A)
안에 흰 N 이다.

기존 아이콘 크기 규약은 `erp-lahom-logo` CSS 를 따른다:
- `static/css/foundation/erp-pro/08-order-list-page.css:6`
- `static/css/contexts/orders/dashboard-grid.css:163`
- `static/css/contexts/construction/dashboard.css:89`

### 2.6 프로젝트 규약 (목업에도 적용)

- 인라인 스타일 금지 → 클래스. (목업은 단일 파일이라 `<style>` 블록은 허용, `style="..."` 속성은 금지)
- jQuery 금지. 목업 상호작용은 순수 `fetch`/DOM.
- 한글 UI 문구. 한자 금지.

## 3. UI master 페르소나가 답해야 할 질문

1. **표기 형태**: 아이콘만 / 아이콘+글자("네이버") / 칩 / 고객명 앞 접두. 밀도 높은 셀에서 무엇이 이기나.
2. **중복 해소**: `담당 미지정` 뱃지와 나란히 떴을 때의 규칙.
3. **라홈 로고 충돌**: 항상 동시 참인 두 표식의 서열.
4. **크기·정렬**: 1.1rem 본문 글자 옆에서 아이콘 몇 px 이 맞나. baseline 정렬.
5. **접근성**: 색맹 대비, `title`/`aria-label` 문구, 아이콘만으로 뜻이 전달되나.
6. **확장성**: 채널이 늘면(쿠팡 등) 이 자리는 어떻게 버티나. `CHANNEL` 상수는 이미 확장을 막지 않는다.
7. **다른 화면 전파 범위**: PC 그리드 / 태블릿 시트 / 모바일 v2 / 주문 목록 / 생산 / 시공.

## 4. 파일 소유권 표 (워커끼리 겹치지 않는다)

목업 루트 = `<SCRATCH>/naver-icon-mockup/` (실제 절대 경로는 워커 프롬프트가 전달한다)

| 워커 | 편집 허용 파일 | 금지 |
|---|---|---|
| W1 아이콘 디자이너 | `parts/icons.html` | 다른 parts, index.html, 저장소 전체 |
| W2 PC 그리드 | `parts/desktop.html` | 다른 parts, index.html, 저장소 전체 |
| W3 모바일·태블릿 + 기획서 | `parts/mobile.html`, `parts/spec.html` | 다른 parts, index.html, 저장소 전체 |
| 통합자 | `index.html` (+ parts 최소 수정 허용) | 저장소 전체 |
| 리뷰어 2명 | 없음(읽기 전용) | 모든 쓰기 |

저장소(`C:\DEV\FOMS` 아래) 파일은 **누구도 쓰지 않는다**. 읽기는 허용.

## 5. 워커 공통 규칙

- git 명령 금지. 브랜치 전환 금지.
- 저장소 파일 수정 금지(읽기만).
- 작업 시작 시 `cd <목업 루트> && pwd` 로 위치 확인.
- 각 part 파일은 **HTML 조각**이다 — `<!doctype>`, `<html>`, `<head>`, `<body>` 태그를 쓰지 않는다.
  필요한 CSS 는 조각 맨 위 `<style>` 블록에, JS 는 맨 아래 `<script>` 블록에 넣는다.
  클래스 이름은 워커별 접두로 충돌을 막는다: W1 `mk-ico-`, W2 `mk-pc-`, W3 `mk-mo-` / `mk-spec-`.
- 표본 데이터는 **실제 주문처럼** 만든다: 한글 이름, 010 번호, 실제 있을 법한 주소·제품명.
  가상 주문 접두 `CLAUDE-TEST-` 는 실서버 대상이 아니므로 목업에는 쓰지 않는다.
- 한글 문장에 한자를 쓰지 않는다.

## 6. 검증 명령 (통합자가 돌린다)

```bash
cd "<목업 루트>"
python - <<'PY'
import pathlib, html.parser
p = pathlib.Path("index.html"); s = p.read_text(encoding="utf-8")
assert "<!doctype html" in s.lower(), "doctype 없음"
for marker in ("mk-ico-", "mk-pc-", "mk-mo-", "mk-spec-"):
    assert marker in s, f"{marker} 조각이 index.html 에 안 들어갔다"
assert 'style="' not in s, "인라인 style 속성이 남아 있다"
assert "jquery" not in s.lower(), "jQuery 금지"
class P(html.parser.HTMLParser):
    def error(self, m): raise AssertionError(m)
P().feed(s)
print("MOCKUP_OK", len(s), "bytes")
PY
```

`MOCKUP_OK` 가 찍혀야 통과다.

## 7. 함정

- **정규식 keep-both 병합 금지.** 조각을 합칠 때 마커만 지우고 한쪽 내용을 통째로 날린 전례가 있다.
  통합자는 각 part 파일을 통째로 읽어 index.html 에 순서대로 붙인다.
- 목업 파일은 CRLF/LF 를 섞지 않는다. UTF-8 로 쓴다(Windows cp949 함정).
- 리뷰어는 편집 권한이 없다 — findings 를 본문으로 돌려준다. 반영은 CEO 판정 뒤 총괄이 한다.
- 이 브리프는 **초안**이다. CEO 는 계약과 워커 브리프를 고쳐도 된다(§4 소유권 표의 파일 경계만 유지).

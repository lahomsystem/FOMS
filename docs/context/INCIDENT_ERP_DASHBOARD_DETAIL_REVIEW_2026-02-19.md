# ERP 대시보드 주문 상세 미개방 장애 — 수정 반복 리뷰 및 재발방지 제안

## 1. 수정 과정 리뷰 (타임라인)

### 전체 흐름 요약

| 차수 | 증상 | 수정 내용 | 근본 원인 | 왜 한 번에 안 됐는가 |
|------|------|-----------|-----------|------------------------|
| 1차 | `Unexpected end of input` (dashboard:5222) | dom.html 끝에 `});` 추가 | partial 분할 시 DOMContentLoaded 콜백 닫는 괄호 누락 | 1차만으로는 다른 오류가 가려져 있음 |
| 2차 | (1차 후 동일/추가 에러 또는 다른 증상) | `JSON.parse('{{ x\|tojson }}')` → `{{ x\|tojson }}` 직접 출력 | Jinja 출력이 스크립트 안에 들어가 파서·런타임 오류 유발 | 2차에서 인라인 JS 내 직접 출력 시, 린터·런타임 이슈가 드러남 |
| 3차 | IDE 린터 "Property assignment expected" | data-* 속성에 JSON 저장, 스크립트에서 읽기 | Jinja 블록 `{{ }}` 이 린터에게 잘못 해석되거나 구조가 어색함 | 템플릿과 JS 분리 부족 |
| 4차 | `JSON.parse` "Expected property name or '}' in JSON at position 1" | safeJsonParse 래퍼 추가 | 입력값이 비어있거나 손상·이스케이프로 인해 유효하지 않은 JSON | 방어 로직 없음 |

---

### 1차 수정: `});` 누락

**근본 원인**

- `erp_dashboard_scripts.html`을 여러 partial로 분할할 때, `erp_dashboard_scripts_detail.html`에서 `document.addEventListener('DOMContentLoaded', () => {`로 콜백이 열림
- 콜백 본문은 `erp_dashboard_scripts_dom.html`로 이어지지만, **콜백을 닫는 `});`가 dom.html 끝에 없음**

**증상**

- 브라우저 콘솔: `Uncaught SyntaxError: Unexpected end of input`
- **파싱 시점** 에러: 스크립트 파싱 단계에서 즉시 실패
- HTML 파서가 스크립트를 끝까지 못 읽고 조기 종료

**왜 1차로 충분하지 않았는가**

1. 1차 수정 후에도 `JSON.parse('{{ ... }}')` 같은 Jinja 주입 코드가 남아 있음
2. 1차는 괄호/구문 문제만 해결 → Jinja 주입·런타임 JSON 파싱 문제는 별도 원인

---

### 2차 수정: `JSON.parse('{{ x|tojson }}')` 패턴 제거

**근본 원인**

- Jinja2 `JSON.parse('{{ x|tojson }}')` 패턴:
  - JSON 값에 `</script>` 또는 `<`가 있으면 HTML 파서가 스크립트를 조기 종료
  - 문자열 내 따옴표/특수문자 → 파서 혼란
  - Jinja 출력이 문자열로 감싸져 있어 이스케이프 문제 발생

**증상**

- `Unexpected token '<'` 또는 `Unexpected end of input` 가능
- 파싱 시점 또는 런타임 모두에서 발생 가능

**수정 방향**

- `JSON.parse('{{ x|tojson }}')` 대신 `{{ x|tojson }}` 직접 출력 (인라인 변수 할당) 또는 data-* 사용

**왜 2차로 충분하지 않았는가**

- 인라인 `const X = {{ x|tojson }};` 사용 시:
  - 린터가 Jinja 블록을 JS로 인식 못 함 → "Property assignment expected"
  - 일부 템플릿에서 JSON 형식이 비정상이면 런타임 `JSON.parse` 에러 유발

---

### 3차 수정: data-* 속성으로 분리

**근본 원인**

- Jinja `{{ }}`를 인라인 스크립트 안에 두면:
  - IDE/린터가 Jinja를 이해 못 함
  - 문법/구조가 복잡해져 오탐 발생

**증상**

- IDE 린터: "Property assignment expected" 등 문법 오류 경고

**수정 방향**

- JSON을 HTML data-* 속성에 넣고 (`data-team-labels="{{ team_labels|tojson|e }}"` 등)
- 스크립트에서는 `getAttribute('data-xxx')`로 읽어 파싱
- 템플릿 출력과 JS 로직 분리 → 린터가 JS만 검사

---

### 4차 수정: safeJsonParse 래퍼

**근본 원인**

- `getAttribute` 결과가:
  - 빈 문자열
  - 이스케이프/손상으로 인한 비유효 JSON
  - 일부 엣지 케이스 데이터
  → `JSON.parse`가 `SyntaxError` 발생

**증상**

- `JSON.parse` → "Expected property name or '}' in JSON at position 1" 등

**수정 방향**

- `safeJsonParse(val, fallback)` 구현:
  - `try/catch`로 `JSON.parse` 보호
  - 실패 시 fallback 객체 반환

---

### 종합: 왜 4번이나 수정이 필요했는가

1. **원인들의 독립성**  
   - 1차: partial 분할·괄호 구조  
   - 2차: Jinja 주입 패턴  
   - 3차: 린터·템플릿/JavScript 경계  
   - 4차: JSON 입력 검증  
   → 하나씩 해결해도 다음 문제가 새로 드러남.

2. **파싱 시점 vs 런타임 구분 부족**  
   - 파싱 에러: 괄호, `</script>` 등 → 구조/템플릿 검토 필요  
   - 런타임 에러: `JSON.parse`, fetch 응답 → 방어 코드·검증 필요  
   → 구분 없이 순차 수정하면 원인 파악이 지연됨.

3. **체크리스트 부재**  
   - partial 분할, Jinja+JS, JSON 파싱을 한 번에 점검할 체크리스트가 없었음.

---

## 2. agents/rules 업그레이드 제안

### 2.1 `.cursor/agents/incident-rca.md`

**추가 위치**: "### 7) 클라이언트/프론트엔드" 하위에 새 섹션

```markdown
### 클라이언트 SyntaxError 1차 진단 순서
1. **파싱 시점 vs 런타임 구분**  
   - 에러 메시지에 파일:라인(dashboard:3125 등)이 있으면 → 파싱 시점 에러 가능성 큼  
   - `Unexpected end of input` → 괄호/스크립트 태그 누락  
   - `Unexpected token '<'` → Jinja 주입 또는 `</script>` 노출  
   - `JSON.parse` 관련 → 런타임, 입력값 검증·safeJsonParse 필요  
2. **동시 점검**  
   - partial 분할 시 괄호/리스너 종료 체크  
   - Jinja2 + 인라인 스크립트: `JSON.parse('{{ x|tojson }}')` 금지, data-* + safeJsonParse 권장  
   - 동일 패턴 grep 후 함께 수정
```

### 2.2 `.cursor/agents/frontend-ui.md`

**추가 위치**: "반드시 지키는 규칙" 다음에 새 섹션

```markdown
## Jinja2 + 인라인 스크립트 (필수)
- **금지**: `JSON.parse('{{ x|tojson }}')` — HTML 파싱/이스케이프 문제
- **권장**: data-* 속성 + safeJsonParse
  1. HTML: `<div id="config" data-json="{{ x|tojson|e }}" ...></div>`
  2. JS: `const data = safeJsonParse(document.getElementById('config')?.getAttribute('data-json'), {});`
- safeJsonParse 예시:
  `function safeJsonParse(val, fb) { try { const s = String(val||'').trim(); if(!s) return fb||{}; const o = JSON.parse(s); return (o&&typeof o==='object'&&!Array.isArray(o)) ? o : (fb||{}); } catch(_) { return fb||{}; } }`
- **partial 분할 시**: 열린 괄호/이벤트 리스너가 어느 partial에서 닫히는지 반드시 확인
```

### 2.3 `.cursor/rules/14-incident-rca.mdc`

**추가 위치**: "## 필수 실행 순서" 내 "4. 핵심 감사" 다음

```markdown
- **콘솔 SyntaxError 시**: (1) 파싱 시점: 괄호/스크립트 태그/partial 경계 (2) Jinja 주입: `JSON.parse('{{ }}')` 금지 (3) 런타임: JSON.parse 입력 검증·safeJsonParse
```

### 2.4 `.cursor/rules/04-frontend.mdc`

**추가 위치**: "## JavaScript" 섹션에

```markdown
## Jinja2 + JSON 주입
- `JSON.parse('{{ x|tojson }}')` 사용 금지
- 대안: data-* 속성에 `{{ x|tojson|e }}` 저장 후, JS에서 safeJsonParse로 읽기
- partial 분할 시: 괄호·addEventListener 콜백 종료 위치 확인 필수
```

---

## 3. SyntaxError → 해결 일괄 체크리스트

### Step 0: 에러 유형 확인

- [ ] 에러 메시지 기록 (예: `Unexpected end of input`, `Unexpected token '<'`, `Expected property name or '}'`)
- [ ] 파일:라인 확인 (예: dashboard:5222) → 해당 템플릿·partial 지정
- [ ] 파싱 시점 vs 런타임 판단
  - 파싱: 페이지 로드 직후, 스크립트 실행 전
  - 런타임: `JSON.parse`, fetch 등 호출 시점

---

### Step 1: 파싱 시점 (스크립트 구조)

- [ ] **partial/스크립트 태그 경계**
  - include된 partial들에서 열린 `(`, `{`, `addEventListener(..., () => {` 등이 어디서 닫히는지 확인
  - 각 partial 끝에 `});` 등 닫는 괄호 누락 여부
- [ ] **`</script>` 노출**
  - Jinja 출력에 `</script>` 또는 `<`가 포함되면 스크립트 조기 종료
  - `{{ ... }}` 내부에 위 문자열이 들어갈 수 있는지 검토
- [ ] **중복 `<script>` 태그**
  - 동일 블록 안에서 태그가 이중으로 열리거나 닫히는지 확인

---

### Step 2: Jinja2 변수 주입 (JSON, 문자열, HTML)

- [ ] **`JSON.parse('{{ x|tojson }}')` 패턴**
  - 사용 금지 → data-* 또는 `{{ x|tojson }}` 직접 출력으로 변경
- [ ] **data-* 사용 시**
  - `{{ x|tojson|e }}`로 이스케이프 적용
  - 스크립트에서는 `getAttribute` + safeJsonParse로 읽기
- [ ] **직접 출력 `const X = {{ x|tojson }};`**
  - 린터 경고 가능 → data-* 방식 선호
  - JSON이 null/빈 배열 등에 대응되는지 확인

---

### Step 3: JSON.parse 입력 검증 및 방어

- [ ] **JSON.parse 호출부**
  - 입력이 비어있거나 손상될 수 있는지 검토
- [ ] **safeJsonParse 사용**
  - `try/catch` + fallback으로 `JSON.parse` 래핑
- [ ] **fetch 응답**
  - Content-Type이 application/json인지 확인
  - `.json()` 실패 시 fallback 처리

---

### Step 4: 수정 후 검증

- [ ] 로컬에서 페이지 로드, 콘솔 에러 없음
- [ ] 동일 패턴이 있는 다른 템플릿 grep 후 함께 수정
- [ ] IDE 린터 경고 해소
- [ ] 해당 기능(주문 상세 열기 등) 재현 테스트

---

## 4. INCIDENT 문서 Prevention 보강 및 패치 제안

### 4.1 `docs/context/INCIDENT_ERP_DASHBOARD_DETAIL_2026-02-18.md` Prevention 섹션 보강

**현재 Prevention**

```markdown
## Prevention
- **Rule/Agent**: partial 분할 시 열린 괄호/이벤트 리스너가 어느 partial에서 닫히는지 체크리스트화
- **템플릿 규칙**: `JSON.parse('{{ x|tojson }}')` 패턴 사용 금지 → `{{ x|tojson }}` 직접 출력
```

**보강안**

```markdown
## Prevention
1. **partial 분할**
   - 열린 괄호/이벤트 리스너가 어느 partial에서 닫히는지 체크리스트화 (GDM / frontend-ui)
2. **Jinja2 + 인라인 스크립트**
   - `JSON.parse('{{ x|tojson }}')` 패턴 사용 금지
   - 권장: data-* 속성(`{{ x|tojson|e }}`) + safeJsonParse
3. **클라이언트 장애 진단 순서**
   - SyntaxError 시: (1) 괄호/스크립트 태그 (2) Jinja 주입 (3) JSON.parse 입력 검증
4. **일괄 체크리스트**
   - `docs/context/INCIDENT_ERP_DASHBOARD_DETAIL_REVIEW_2026-02-19.md` §3 참조
```

### 4.2 적용 대상 패치 요약

| 파일 | 작업 | 내용 |
|------|------|------|
| `docs/context/INCIDENT_ERP_DASHBOARD_DETAIL_2026-02-18.md` | Prevention 보강 | 위 4개 항목 반영 |
| `.cursor/agents/incident-rca.md` | 추가 | 클라이언트 SyntaxError 1차 진단 순서 |
| `.cursor/agents/frontend-ui.md` | 추가 | Jinja2 + 인라인 스크립트 규칙 |
| `.cursor/rules/14-incident-rca.mdc` | 추가 | 콘솔 SyntaxError 시 3단계 점검 |
| `.cursor/rules/04-frontend.mdc` | 추가 | Jinja2 + JSON 주입 규칙 |

### 4.3 남은 위험 패턴 (추가 수정 권장)

다음 파일에 `JSON.parse('{{ ... |tojson }}')` 패턴이 남아 있어, 동일 사고 가능성이 있습니다:

- `templates/wdcalculator/calculator.html` (638–639줄)
- `templates/add_order.html` (759줄)

data-* + safeJsonParse로 교체하는 것을 권장합니다.

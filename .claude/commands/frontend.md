# FOMS 프론트엔드 개발 (Frontend UI)

당신은 FOMS 프론트엔드 전문가입니다.

## 기술 스택
- Bootstrap 5.3 (CSS 프레임워크)
- Jinja2 (템플릿 엔진)
- Vanilla JavaScript (ES6+)

## Jinja2 + 인라인 스크립트 규칙
- **금지**: `JSON.parse('{{ x|tojson }}')` — HTML 파싱/이스케이프 문제
- **권장**: data-* 속성 + safeJsonParse
  1. HTML: `<div id="config" data-json="{{ x|tojson|e }}" ...></div>`
  2. JS: `const data = safeJsonParse(document.getElementById('config')?.getAttribute('data-json'), {});`
- **partial 분할 시**: 열린 괄호/이벤트 리스너가 어느 partial에서 닫히는지 반드시 확인

## 반드시 지키는 규칙
1. **인라인 스타일 금지** → `static/css/erp-pro.css` 사용
2. **인라인 script 300줄 초과 시** 별도 `.js` 파일로 분리
3. **템플릿 800줄 초과 시** `{% include 'partials/이름.html' %}` partial 분리
4. **jQuery 사용 금지** → `querySelector`, `fetch()` 사용
5. **전역 변수 최소화** → 모듈 패턴 또는 IIFE 사용

## fetch 에러 처리 패턴 (필수)
```javascript
try {
    const res = await fetch('/api/endpoint', { method: 'POST', ... });
    const data = await res.json();
    if (!data.success) { showToast(data.error, 'error'); return; }
} catch (err) {
    showToast('네트워크 오류가 발생했습니다.', 'error');
}
```

## CSS 네이밍 규칙
- BEM 또는 기능 기반: `erp-grid-cell`, `status-badge-received`
- Bootstrap 클래스 우선, 커스텀 CSS 최소화

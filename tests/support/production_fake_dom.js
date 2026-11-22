// 생산 첫 화면 Node 시험이 같이 쓰는 아주 작은 가짜 DOM — 서버가 그린 진짜 조각을 읽어 JS 를 vm 으로 돌린다.
// 쓰는 곳: production_home_steps_node_checks.js(판 · 쓰기 길) · production_home_steppane_node_checks.js(판 하나 받기).
// 읽기: 따옴표 속성 · 빈 요소 · 주석 · script 본문 건너뜀. 고르기: 태그 · .class · #id · [attr] · [attr="v"] 묶음 + 쉼표 목록(조합자 없음).
// <template> 는 innerHTML 을 읽어 content 에 담는다(판 하나 조각 끼우기).
'use strict';

const VOID = new Set(['img', 'br', 'input', 'meta', 'link', 'hr', 'source', 'path', 'circle', 'rect', 'line', 'use', 'polyline', 'col', 'wbr']);

function decode(s) {
  return s.replace(/&(#\d+|#x[0-9a-f]+|amp|lt|gt|quot|apos|nbsp);/gi, (m, e) => {
    if (e[0] === '#') return String.fromCodePoint(e[1] === 'x' || e[1] === 'X' ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10));
    return { amp: '&', lt: '<', gt: '>', quot: '"', apos: "'", nbsp: ' ' }[e.toLowerCase()];
  });
}
function parseSel(sel) {
  const m = { tag: null, id: null, classes: [], attrs: [] };
  const re = /^([a-z][a-z0-9]*)|#([\w-]+)|\.([\w-]+)|\[([\w-]+)(?:=(?:"([^"]*)"|'([^']*)'))?\]/gi;
  let x;
  while ((x = re.exec(sel))) {
    if (x[1]) m.tag = x[1].toLowerCase();
    else if (x[2]) m.id = x[2];
    else if (x[3]) m.classes.push(x[3]);
    else m.attrs.push([x[4], x[5] !== undefined ? x[5] : x[6]]);
  }
  return m;
}
function matchOne(node, sel) {
  if (!node.tag) return false;
  const m = parseSel(sel.trim());
  if (m.tag && node.tag !== m.tag) return false;
  if (m.id && node.attrs.id !== m.id) return false;
  const cls = (node.attrs.class || '').split(/\s+/);
  if (m.classes.some((c) => !cls.includes(c))) return false;
  return m.attrs.every(([k, v]) => k in node.attrs && (v === undefined || node.attrs[k] === v));
}
function matches(node, sel) { return sel.split(',').some((s) => matchOne(node, s)); }
function walk(node, out) { node.children.forEach((c) => { out.push(c); walk(c, out); }); return out; }

/** 문서 하나 — focused(포커스 받은 요소) · docListeners(document 리스너) · dispatch(올라가며 부름) · parse · makeEl. */
function fakeDom() {
  const focused = [];
  const docListeners = {};
  function dispatch(target, type, extra) {
    const ev = Object.assign({ type, target, defaultPrevented: false, button: 0, metaKey: false, ctrlKey: false, shiftKey: false,
      preventDefault() { this.defaultPrevented = true; }, stopPropagation() {} }, extra || {});
    let n = target;
    while (n && n.tag) { (n.listeners[type] || []).forEach((f) => f.call(n, ev)); n = n.parentNode; }
    (docListeners[type] || []).forEach((f) => f(ev));
    return ev;
  }
  function textNode(t) { return { tag: null, children: [], parentNode: null, get textContent() { return t; } }; }
  function makeEl(tag) {
    const node = {
      tag, attrs: {}, children: [], parentNode: null, listeners: {}, text: null, disabled: false,
      get nodeType() { return 1; },
      get tagName() { return tag.toUpperCase(); },
      getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; },
      setAttribute(k, v) { this.attrs[k] = String(v); if (k === 'disabled') this.disabled = true; },
      hasAttribute(k) { return k in this.attrs; },
      removeAttribute(k) { delete this.attrs[k]; if (k === 'disabled') this.disabled = false; },
      get className() { return this.attrs.class || ''; },
      set className(v) { this.attrs.class = String(v); },
      get id() { return this.attrs.id || ''; },
      get hidden() { return 'hidden' in this.attrs; },
      set hidden(v) { if (v) this.attrs.hidden = ''; else delete this.attrs.hidden; },
      get classList() {
        const self = this;
        const list = () => (self.attrs.class || '').split(/\s+/).filter(Boolean);
        const set = (arr) => { self.attrs.class = arr.join(' '); };
        return {
          contains: (c) => list().includes(c),
          add: (...cs) => set([...new Set(list().concat(cs))]),
          remove: (...cs) => set(list().filter((x) => !cs.includes(x))),
          toggle: (c, on) => { const has = list().includes(c); const want = on === undefined ? !has : !!on; if (want && !has) set(list().concat(c)); if (!want && has) set(list().filter((x) => x !== c)); return want; },
        };
      },
      get textContent() { return this.text !== null ? this.text : this.children.map((c) => c.textContent).join(''); },
      set textContent(v) { this.children = []; this.text = String(v); },
      get innerText() { return this.textContent; },
      set innerHTML(v) { this.children = []; this.text = null; parse(String(v)).children.slice().forEach((c) => this.appendChild(c)); },
      get content() { return this; },
      get firstElementChild() { return this.children[0] || null; },
      appendChild(c) { if (c.parentNode) c.parentNode.removeChild(c); c.parentNode = this; this.text = null; this.children.push(c); return c; },
      insertBefore(c, ref) {
        if (!ref) return this.appendChild(c);
        if (c.parentNode) c.parentNode.removeChild(c);
        c.parentNode = this;
        this.children.splice(this.children.indexOf(ref), 0, c);
        return c;
      },
      removeChild(c) { const i = this.children.indexOf(c); if (i >= 0) this.children.splice(i, 1); c.parentNode = null; return c; },
      replaceChild(n, o) { const i = this.children.indexOf(o); this.children[i] = n; n.parentNode = this; o.parentNode = null; return o; },
      cloneNode(deep) { const c = makeEl(tag); c.attrs = Object.assign({}, this.attrs); if (deep) this.children.forEach((k) => c.appendChild(k.cloneNode(true))); return c; },
      contains(n) { while (n) { if (n === this) return true; n = n.parentNode; } return false; },
      matches(sel) { return matches(this, sel); },
      closest(sel) { let n = this; while (n && n.tag) { if (matches(n, sel)) return n; n = n.parentNode; } return null; },
      querySelector(sel) { return walk(this, []).find((n) => matches(n, sel)) || null; },
      querySelectorAll(sel) { return walk(this, []).filter((n) => matches(n, sel)); },
      addEventListener(t, f) { (this.listeners[t] = this.listeners[t] || []).push(f); },
      removeEventListener() {},
      getClientRects() { let n = this; while (n && n.tag) { if (n.hidden) return []; n = n.parentNode; } return [{}]; },
      getBoundingClientRect() { return { top: 0, left: 0, width: 10, height: 10, bottom: 10, right: 10 }; },
      focus() { focused.push(this); },
      click() { dispatch(this, 'click'); },
    };
    return node;
  }
  function parse(src) {
    const top = makeEl('body');
    const stack = [top];
    const re = /<!--[\s\S]*?-->|<script\b[^>]*>[\s\S]*?<\/script>|<\/([a-zA-Z][\w-]*)\s*>|<([a-zA-Z][\w-]*)((?:\s+[^\s"'>\/=]+(?:\s*=\s*(?:"[^"]*"|'[^']*'|[^\s>]+))?)*)\s*(\/?)>|([^<]+)/g;
    let m;
    while ((m = re.exec(src))) {
      const cur = stack[stack.length - 1];
      if (m[1]) {
        const t = m[1].toLowerCase();
        for (let i = stack.length - 1; i > 0; i--) { if (stack[i].tag === t) { stack.length = i; break; } }
      } else if (m[2]) {
        const t = m[2].toLowerCase();
        const n = makeEl(t);
        const are = /([^\s"'>\/=]+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s>]+)))?/g;
        let a;
        while ((a = are.exec(m[3] || ''))) n.attrs[a[1]] = decode(a[2] !== undefined ? a[2] : a[3] !== undefined ? a[3] : a[4] !== undefined ? a[4] : '');
        if ('disabled' in n.attrs) n.disabled = true;
        cur.appendChild(n);
        if (!m[4] && !VOID.has(t)) stack.push(n);
      } else if (m[5] && m[0][0] !== '<') {
        cur.children.push(Object.assign(textNode(decode(m[5])), { parentNode: cur }));
      }
    }
    return top;
  }
  return { parse, makeEl, dispatch, focused, docListeners };
}

module.exports = { fakeDom };

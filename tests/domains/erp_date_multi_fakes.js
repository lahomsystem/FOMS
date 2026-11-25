// 여러 날짜 달력 node 시험의 가짜 화면 · 가짜 flatpickr(tests/domains/erp_date_multi_runner.js 가 쓴다).
// 가짜 flatpickr 는 4.6.13 에서 static/js/orders/erp-date-multi.js 가 기대는 것만 흉내 낸다: 훅 배열 · onReady 는 만들 때 ·
// open 은 disabled 면 무시 · 날짜를 고르면 날짜 칸을 새로 그리고(buildDays — 포커스가 사라진다) input.value 를 쓴 뒤
// onChange 훅 → change → input 이벤트 · clear(trigger, toInitial) · allowInput 이 거짓이면 입력 칸 readonly ·
// position 이 함수면 자리 잡기를 그 함수에 맡김 · ignoredFocusElements 기본 배열은 모든 인스턴스가 같이 쓴다.
'use strict';
const vm = require('vm');

function makeDom() {
  const doc = { activeElement: null };
  function parseSel(sel) {
    const parts = { tag: null, id: null, cls: [], not: [], attr: [] };
    const re = /(:not\(\.([\w-]+)\))|(\.[\w-]+)|(#[\w-]+)|(\[([\w-]+)="([^"]*)"\])|(^[a-z]+)/g;
    let m;
    while ((m = re.exec(sel))) {
      if (m[1]) parts.not.push(m[2]);
      else if (m[3]) parts.cls.push(m[3].slice(1));
      else if (m[4]) parts.id = m[4].slice(1);
      else if (m[5]) parts.attr.push([m[6], m[7]]);
      else if (m[8]) parts.tag = m[8];
    }
    return parts;
  }
  function matches(el, sel) {
    const p = parseSel(sel);
    if (p.tag && el.tagName !== p.tag.toUpperCase()) return false;
    if (p.id && el.id !== p.id) return false;
    if (p.cls.some((c) => !el.classList.contains(c))) return false;
    if (p.not.some((c) => el.classList.contains(c))) return false;
    return p.attr.every(([k, v]) => el.getAttribute(k) === v);
  }
  class Node {
    constructor(tag) {
      this.tagName = tag.toUpperCase();
      this.children = [];
      this.parentElement = null;
      this.attrs = {};
      this.handlers = {};
      this._text = '';
      this.style = { props: {}, setProperty: (k, v) => { this.style.props[k] = v; } };
      this.rect = { top: 0, bottom: 0, height: 0 };
      this.scrolled = [];
      const set = new Set();
      this.classList = {
        add: (...c) => c.forEach((x) => set.add(x)),
        remove: (...c) => c.forEach((x) => set.delete(x)),
        contains: (c) => set.has(c),
        toggle: (c, on) => { const want = on === undefined ? !set.has(c) : !!on; if (want) set.add(c); else set.delete(c); return want; },
        _set: set,
      };
      Object.defineProperty(this, 'className', {
        get: () => Array.from(set).join(' '),
        set: (v) => { set.clear(); String(v).split(/\s+/).filter(Boolean).forEach((x) => set.add(x)); },
      });
    }
    get id() { return this.attrs.id || ''; }
    set id(v) { this.attrs.id = v; }
    get htmlFor() { return this.attrs.for || ''; }
    setAttribute(k, v) { if (k === 'class') this.className = v; else this.attrs[k] = String(v); }
    getAttribute(k) { return k === 'class' ? this.className : (k in this.attrs ? this.attrs[k] : null); }
    hasAttribute(k) { return k in this.attrs; }
    appendChild(c) { if (c.parentElement) c.remove(); c.parentElement = this; this.children.push(c); return c; }
    remove() { const p = this.parentElement; if (p) p.children.splice(p.children.indexOf(this), 1); this.parentElement = null; }
    insertAdjacentElement(where, el) {
      const p = this.parentElement;
      el.parentElement = p;
      p.children.splice(p.children.indexOf(this) + 1, 0, el);
      return el;
    }
    get textContent() { return this.tagName === '#TEXT' ? this._text : this.children.map((c) => c.textContent).join('') + this._text; }
    set textContent(v) { this.children.forEach((c) => { c.parentElement = null; }); this.children = []; this._text = String(v); }
    set innerHTML(v) { this.textContent = String(v).replace(/<[^>]*>/g, ''); }
    get isConnected() { let n = this; while (n.parentElement) n = n.parentElement; return n === doc.body; }
    contains(el) { for (let n = el; n; n = n.parentElement) if (n === this) return true; return false; }
    closest(sel) { for (let n = this; n; n = n.parentElement) if (n.tagName !== '#TEXT' && matches(n, sel)) return n; return null; }
    querySelectorAll(sel) {
      const out = [];
      const walk = (n) => n.children.forEach((c) => { if (c.tagName !== '#TEXT' && matches(c, sel)) out.push(c); walk(c); });
      walk(this);
      return out;
    }
    querySelector(sel) { return this.querySelectorAll(sel)[0] || null; }
    addEventListener(type, fn, capture) { (this.handlers[type] = this.handlers[type] || []).push({ fn, capture: !!capture }); }
    dispatchEvent(ev) {
      ev.target = ev.target || this;
      let n = this;
      do {
        (n.handlers[ev.type] || []).forEach((h) => h.fn.call(n, ev));
        n = ev.bubbles ? n.parentElement : null;
      } while (n && !ev.stopped);
      return true;
    }
    fire(type, extra) {
      const ev = Object.assign({ type, bubbles: true, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() { this.stopped = true; } }, extra || {});
      // 잡기(capture) 단계: 위에서부터 capture 처리기
      const path = [];
      for (let n = this; n; n = n.parentElement) path.unshift(n);
      ev.target = this;
      path.forEach((n) => (n.handlers[type] || []).filter((h) => h.capture).forEach((h) => h.fn.call(n, ev)));
      for (let n = this; n; n = n.parentElement) (n.handlers[type] || []).filter((h) => !h.capture).forEach((h) => h.fn.call(n, ev));
      return ev;
    }
    focus() { if (this.isConnected) doc.activeElement = this; }
    getBoundingClientRect() { return this.rect; }
    scrollIntoView(opts) { this.scrolled.push(opts); }
  }
  class HTMLInputElement extends Node {}
  Object.defineProperty(HTMLInputElement.prototype, 'value', {
    configurable: true,
    get() { return this._value || ''; },
    set(v) { this._value = String(v); this.writes = (this.writes || 0) + 1; },
  });
  doc.body = new Node('body');
  doc.activeElement = doc.body;
  doc.createElement = (tag) => (tag === 'input' ? new HTMLInputElement('input') : new Node(tag));
  doc.createTextNode = (t) => { const n = new Node('#text'); n._text = String(t); return n; };
  doc.querySelector = (sel) => doc.body.querySelector(sel);
  return { doc, HTMLInputElement };
}

const SHARED_DEFAULT_IGNORED = [];

function fakeFlatpickr(doc) {
  return function flatpickr(input, opts) {
    const hooks = {};
    ['onReady', 'onOpen', 'onClose', 'onChange', 'onValueUpdate'].forEach((h) => { hooks[h] = [].concat(opts[h] || []); });
    const cal = doc.createElement('div');
    cal.className = 'flatpickr-calendar';
    const daysBox = doc.createElement('div');
    daysBox.className = 'dayContainer';
    cal.appendChild(daysBox);
    doc.body.appendChild(cal);
    const year = doc.createElement('input');
    year.className = 'cur-year';
    const fp = {
      config: Object.assign({ ignoredFocusElements: SHARED_DEFAULT_IGNORED }, opts),
      input, calendarContainer: cal, currentYearElement: year, isOpen: false,
      selectedDates: String(input.value || '').split(', ').filter(Boolean),
      latestSelectedDateObj: undefined, clearArgs: null, positioned: 0,
    };
    function buildDays() {   // 2026-12 한 달. 고른 날 · 오늘(12-10) 표시. 늘 새 칸을 만든다(포커스가 사라진다).
      daysBox.children.forEach((c) => { c.parentElement = null; });
      daysBox.children = [];
      for (let d = 1; d <= 31; d += 1) {
        const iso = '2026-12-' + String(d).padStart(2, '0');
        const el = doc.createElement('span');
        el.className = 'flatpickr-day';
        if (fp.selectedDates.indexOf(iso) >= 0) el.classList.add('selected');
        if (d === 10) el.classList.add('today');
        el.dateObj = new Date(iso + 'T00:00:00');
        el.iso = iso;
        daysBox.appendChild(el);
      }
      if (!cal.contains(doc.activeElement)) return;
      doc.activeElement = doc.body;
    }
    function trigger(name) {
      hooks[name].forEach((fn) => fn.call(fp, fp.selectedDates, input.value, fp));
      if (name === 'onChange') { input.fire('change'); input.fire('input'); }
    }
    fp.open = () => {
      if (input.disabled) return;
      const was = fp.isOpen;
      fp.isOpen = true;
      if (was) return;
      cal.classList.add('open');
      trigger('onOpen');
      if (typeof fp.config.position === 'function') fp.config.position(fp); else fp.positioned += 1;
    };
    fp.close = () => { fp.isOpen = false; cal.classList.remove('open'); trigger('onClose'); };
    fp.clear = (triggerChange = true, toInitial = true) => {
      fp.clearArgs = [triggerChange, toInitial];
      input.value = '';
      fp.selectedDates = [];
      buildDays();
      if (triggerChange) trigger('onChange');
    };
    fp.pick = (iso) => {   // 날짜 칸을 누르거나 Enter — flatpickr selectDate 순서
      const i = fp.selectedDates.indexOf(iso);
      if (i >= 0) fp.selectedDates.splice(i, 1); else fp.selectedDates.push(iso);
      fp.latestSelectedDateObj = new Date(iso + 'T00:00:00');
      buildDays();
      input.value = fp.selectedDates.join(', ');
      trigger('onChange');
    };
    fp.setDate = (list) => { fp.selectedDates = list.slice(); input.value = list.join(', '); buildDays(); };
    if (!opts.allowInput) input.readOnly = true;
    buildDays();
    input._flatpickr = fp;
    trigger('onReady');
    return fp;
  };
}

function load(dom, src) {
  const win = { flatpickr: fakeFlatpickr(dom.doc), innerHeight: 844 };
  const ctx = {
    window: win, document: dom.doc, HTMLInputElement: dom.HTMLInputElement,
    FocusEvent: function FocusEvent(type, init) { this.type = type; this.bubbles = !!(init && init.bubbles); },
  };
  win.window = win;
  vm.createContext(ctx);
  vm.runInContext(src, ctx);
  return win;
}

module.exports = { makeDom, fakeFlatpickr, load, SHARED_DEFAULT_IGNORED };

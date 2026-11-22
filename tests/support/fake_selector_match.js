'use strict';
/* 겹층 셀렉터 판정 — attrs/classes 를 가진 가짜 요소만 실제 셀렉터 글로 견준다(태그 · .class · [attr] · [attr="v"] · :not(…)). */
function matchCompound(e, compound) {
  const nots = [];
  const body = compound.replace(/:not\(([^)]*)\)/g, (_, inner) => { nots.push(inner); return ''; }).trim();
  const tokens = body.match(/^[a-z]+|\.[\w-]+|\[[\w-]+(?:="[^"]*")?\]/g) || [];
  if (tokens.join('') !== body) throw new Error('가짜 셀렉터 판정이 모르는 꼴: ' + compound);
  const one = (t) => {
    if (t[0] === '.') return (e.classes || []).indexOf(t.slice(1)) !== -1;
    if (t[0] === '[') {
      const m = /^\[([\w-]+)(?:="([^"]*)")?\]$/.exec(t);
      return Object.prototype.hasOwnProperty.call(e.attrs, m[1]) && (m[2] === undefined || e.attrs[m[1]] === m[2]);
    }
    return String(e.tagName).toLowerCase() === t;
  };
  return tokens.every(one) && !nots.some((n) => matchCompound(e, n));
}
const matchesSel = (e, sel) => sel.split(',').some((c) => matchCompound(e, c.trim()));

module.exports = { matchesSel };

window.ERPUtils = window.ERPUtils || {};

window.ERPUtils.safeJsonParse = function (val, fb) {
    try {
        const s = String(val || '').trim();
        if (!s) return fb != null ? fb : {};
        const o = JSON.parse(s);
        return (o && typeof o === 'object' && !Array.isArray(o)) ? o : (fb != null ? fb : {});
    } catch (_) {
        return fb != null ? fb : {};
    }
};

window.ERPUtils.safeJsonFetch = async function (url, fallback) {
    try {
        const res = await fetch(url);
        const data = await res.json().catch(() => fallback);
        return data != null ? data : fallback;
    } catch (_) {
        return fallback;
    }
};

window.ERPUtils.escapeHtml = function (text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
};

window.ERPUtils.setVisible = function (id, visible) {
    const el = document.getElementById(id);
    if (el) el.style.display = visible ? '' : 'none';
};

window.ERPUtils.setText = function (id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text || '';
};

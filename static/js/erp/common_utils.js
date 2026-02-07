
window.ERPUtils = window.ERPUtils || {};

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

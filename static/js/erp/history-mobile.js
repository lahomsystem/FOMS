(function () {
  function lazyLoadImages(root) {
    if (!root) return;
    root.querySelectorAll('img.lazy-detail-img[data-src]').forEach(function (img) {
      img.src = img.dataset.src;
      img.removeAttribute('data-src');
    });
  }

  function setExpanded(toggle, detail, expanded) {
    if (!toggle || !detail) return;
    toggle.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    detail.hidden = !expanded;
    detail.setAttribute('aria-hidden', expanded ? 'false' : 'true');
    if (expanded) {
      lazyLoadImages(detail);
    }
  }

  document.addEventListener('DOMContentLoaded', function () {
    var root = document.querySelector('.erp-history-mobile-shell[data-erp-mobile-v2="true"]');
    if (!root) return;

    root.querySelectorAll('[data-history-toggle]').forEach(function (toggle) {
      toggle.addEventListener('click', function () {
        var detailId = toggle.getAttribute('aria-controls');
        var detail = detailId ? document.getElementById(detailId) : null;
        if (!detail) return;
        var expanded = toggle.getAttribute('aria-expanded') === 'true';
        setExpanded(toggle, detail, !expanded);
      });
    });

    var focusOrder = new URLSearchParams(window.location.search).get('focus_order');
    if (!focusOrder) return;

    var focusCard = root.querySelector('.erp-history-mobile-card[data-order-id="' + focusOrder + '"]');
    if (!focusCard) return;

    focusCard.classList.add('is-focused');
    var focusToggle = focusCard.querySelector('[data-history-toggle]');
    var detailId = focusToggle ? focusToggle.getAttribute('aria-controls') : null;
    var focusDetail = detailId ? document.getElementById(detailId) : null;
    if (focusToggle && focusDetail) {
      setExpanded(focusToggle, focusDetail, true);
    }
    window.setTimeout(function () {
      focusCard.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }, 120);
  });
})();

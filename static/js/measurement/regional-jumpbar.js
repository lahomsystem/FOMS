/**
 * 지방 주문 대시보드 섹션 점프바 (sticky)
 *
 * 역할
 *  1) 전역 sticky nav 높이를 실측해 CSS 변수(--regional-sticky-top)로 노출 —
 *     점프바가 nav 아래에 정확히 붙고, 섹션 앵커가 가려지지 않는다.
 *  2) 점프바가 실제로 고정되는 순간 .is-stuck 을 붙여 그림자를 준다(sentinel + IntersectionObserver).
 *  3) 현재 보이는 섹션의 점프 버튼에 .is-active / aria-current 를 부여(scrollspy).
 *  4) 점프 버튼 클릭 시 스크롤 이동(prefers-reduced-motion 존중) + 해시 갱신(히스토리 오염 없이).
 *
 * 주의: 전역 html { scroll-behavior: smooth } 는 쓰지 않는다(입력 포커스 스틸 회귀 이력).
 */
(function () {
    'use strict';

    /**
     * 점프바 동작을 초기화한다.
     *
     * @returns {void}
     */
    function initJumpbar() {
        var bar = document.getElementById('regional-jumpbar');
        if (!bar) return;

        var sentinel = document.getElementById('regional-jumpbar-sentinel');
        var links = Array.prototype.slice.call(bar.querySelectorAll('[data-jump-target]'));
        var sections = links
            .map(function (link) { return document.getElementById(link.dataset.jumpTarget); })
            .filter(Boolean);

        /**
         * sticky 오프셋(전역 nav 높이)과 점프바 높이를 CSS 변수로 갱신한다.
         *
         * @returns {void}
         */
        function syncOffsets() {
            var nav = document.querySelector('nav.layout-global-nav');
            var offset = 0;
            if (nav) {
                var navStyle = window.getComputedStyle(nav);
                if (navStyle.position === 'sticky' && navStyle.display !== 'none') {
                    offset = nav.getBoundingClientRect().height || 0;
                }
            }
            var root = document.documentElement;
            root.style.setProperty('--regional-sticky-top', Math.round(offset) + 'px');
            root.style.setProperty('--regional-jumpbar-height', Math.round(bar.getBoundingClientRect().height || 56) + 'px');
        }

        syncOffsets();
        window.addEventListener('resize', syncOffsets, { passive: true });
        if (window.ResizeObserver) {
            var ro = new ResizeObserver(syncOffsets);
            var navEl = document.querySelector('nav.layout-global-nav');
            if (navEl) ro.observe(navEl);
        }

        // 고정 상태 감지: sentinel 이 화면 밖으로 나가면 점프바가 붙은 것.
        if (sentinel && window.IntersectionObserver) {
            var stuckObserver = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    bar.classList.toggle('is-stuck', !entry.isIntersecting);
                });
            }, { threshold: 0, rootMargin: '0px 0px -100% 0px' });
            stuckObserver.observe(sentinel);
        }

        /**
         * 지정한 섹션 버튼만 활성 표시한다.
         *
         * @param {string|null} sectionId 활성화할 섹션 id
         * @returns {void}
         */
        function setActive(sectionId) {
            links.forEach(function (link) {
                var on = link.dataset.jumpTarget === sectionId;
                link.classList.toggle('is-active', on);
                if (on) {
                    link.setAttribute('aria-current', 'true');
                } else {
                    link.removeAttribute('aria-current');
                }
            });
        }

        // scrollspy: 화면 상단에 가장 가까운 섹션을 활성으로.
        if (sections.length && window.IntersectionObserver) {
            var visible = {};
            var spy = new IntersectionObserver(function (entries) {
                entries.forEach(function (entry) {
                    visible[entry.target.id] = entry.isIntersecting ? entry.intersectionRatio : 0;
                });
                var best = null;
                var bestTop = Infinity;
                sections.forEach(function (section) {
                    if (!visible[section.id]) return;
                    var top = Math.abs(section.getBoundingClientRect().top);
                    if (top < bestTop) {
                        bestTop = top;
                        best = section.id;
                    }
                });
                setActive(best);
            }, { threshold: [0, 0.01, 0.5], rootMargin: '-25% 0px -60% 0px' });
            sections.forEach(function (section) { spy.observe(section); });
        }

        var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        links.forEach(function (link) {
            link.addEventListener('click', function (event) {
                var target = document.getElementById(link.dataset.jumpTarget);
                if (!target) return;
                event.preventDefault();
                syncOffsets();
                target.scrollIntoView({ behavior: reduceMotion ? 'auto' : 'smooth', block: 'start' });
                setActive(link.dataset.jumpTarget);
                if (window.history && window.history.replaceState) {
                    window.history.replaceState(null, '', '#' + link.dataset.jumpTarget);
                }
            });
        });
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initJumpbar);
    } else {
        initJumpbar();
    }
})();

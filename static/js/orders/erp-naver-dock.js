/**
 * 네이버 원본 도크 (T14-B) — 주문 편집 셸 우측 독립 패널.
 *
 * 폼 불가침 계약: 기존 폼 DOM(id·name)을 일절 참조하지 않는다. 값 전달은 사람이
 * 복사 버튼으로만 한다(WDCalculator additive 패턴). 데이터는 #erp-order-bootstrap
 * JSON 의 naver_origin(추가 fetch 0), 체크·귀속 상태는 체크 즉시 서버 저장(팀 공유).
 *
 * fragment 재실행 대비: 문서 위임 + 싱글톤 가드 + 마운트 감시(MutationObserver).
 * 원본 문자열(상품명·옵션)은 전부 textContent 로만 주입한다 — innerHTML 금지(XSS).
 * 좁은 셸 전환은 ResizeObserver 가 **셸 폭** 기준으로 판정한다(뷰포트 MQ 금지).
 */
(function () {
    'use strict';
    if (window.__fomsNaverDockMounted) return;
    window.__fomsNaverDockMounted = true;

    var DOCK_MIN_SHELL_WIDTH = 1400;
    var state = null;          // {orderNo, rows, mains, assignCommon}
    var completing = false;

    function readBootstrap() {
        var node = document.getElementById('erp-order-bootstrap');
        if (!node) return null;
        try {
            var payload = JSON.parse(node.textContent || 'null');
            return payload && payload.naver_origin ? payload.naver_origin : null;
        } catch (error) {
            return null;
        }
    }

    function el(tag, className, text) {
        var node = document.createElement(tag);
        if (className) node.className = className;
        if (text !== undefined && text !== null) node.textContent = String(text);
        return node;
    }

    function formatAmount(amount) {
        if (typeof amount !== 'number') return '';
        return amount.toLocaleString('ko-KR') + '원';
    }

    /** addon 의 유효 귀속: 사람 지정 > 추정 > 미정(null). */
    function effectiveMain(row) {
        return row.assigned_main || row.guess_main || null;
    }

    function blockers() {
        return state.rows.filter(function (row) {
            return row.role === 'addon' && !effectiveMain(row);
        });
    }

    function checkedCount() {
        return state.rows.filter(function (row) { return row.checked; }).length;
    }

    function allReviewed() {
        return state.rows.every(function (row) { return row.reviewed; });
    }

    function buildRow(row) {
        var wrap = el('div', 'naver-dock-row' + (row.checked ? ' is-checked' : ''));
        wrap.setAttribute('data-naver-dock-row', String(row.link_id));

        var checkbox = document.createElement('input');
        checkbox.type = 'checkbox';
        checkbox.checked = !!row.checked;
        checkbox.setAttribute('aria-label', '반영 표시');
        checkbox.setAttribute('data-naver-dock-check', String(row.link_id));
        wrap.appendChild(checkbox);

        var body = el('div', 'naver-dock-row-body');
        var title = el('div', 'naver-dock-row-title',
            row.role === 'main' ? '본품 옵션 원문' : (row.product_name || '(이름 없음)'));
        if (row.role === 'addon' && row.amount === 0) {
            title.appendChild(el('span', 'naver-dock-zero', '0원'));
        }
        body.appendChild(title);

        var srcText = row.role === 'main'
            ? (row.option_text || '(옵션 없음)')
            : [row.product_name, row.option_text].filter(Boolean).join(' — ') || '(원문 없음)';
        body.appendChild(el('div', 'naver-dock-src', srcText));

        var acts = el('div', 'naver-dock-acts');
        (row.copies || []).forEach(function (value) {
            var chip = el('button', 'naver-dock-copy', '📋 ' + value);
            chip.type = 'button';
            chip.setAttribute('data-naver-dock-copy', value);
            acts.appendChild(chip);
        });
        if (row.role === 'addon') {
            var select = document.createElement('select');
            select.className = 'naver-dock-assign';
            select.setAttribute('data-naver-dock-assign', String(row.link_id));
            var placeholder = el('option', null, '⚠ 본품 선택…');
            placeholder.value = '';
            select.appendChild(placeholder);
            state.mains.forEach(function (main) {
                var option = el('option', null, main.label);
                option.value = main.external_id;
                select.appendChild(option);
            });
            var common = el('option', null, '공통(주문 전체)');
            common.value = state.assignCommon;
            select.appendChild(common);
            select.value = effectiveMain(row) || '';
            acts.appendChild(select);
            if (!row.assigned_main && row.guess_reason) {
                acts.appendChild(el('span', 'naver-dock-guess', row.guess_reason));
            }
        }
        body.appendChild(acts);
        wrap.appendChild(body);
        return wrap;
    }

    function buildPanel(withClose) {
        var frag = document.createDocumentFragment();

        var head = el('div', 'naver-dock-hd');
        head.appendChild(el('b', 'naver-dock-title', '🏪 네이버 원본'));
        if (state.orderNo) head.appendChild(el('span', 'naver-dock-orderno', '주문번호 ' + state.orderNo));
        head.appendChild(el('span', 'naver-dock-prog'));
        if (withClose) {
            var close = el('button', 'btn btn-sm btn-outline-secondary', '닫기');
            close.type = 'button';
            close.setAttribute('data-naver-dock-close', '1');
            head.appendChild(close);
        }
        frag.appendChild(head);

        var pbar = el('div', 'naver-dock-pbar');
        pbar.appendChild(document.createElement('i'));
        frag.appendChild(pbar);

        var bd = el('div', 'naver-dock-bd');
        var groups = [];
        state.mains.forEach(function (main, index) {
            var label = (state.mains.length > 1 ? '본품 ' + (index + 1) + ' — ' : '본품 — ') + main.label;
            groups.push({ key: main.external_id, label: label });
        });
        groups.push({ key: state.assignCommon, label: '공통(주문 전체)' });
        groups.push({ key: null, label: '귀속 미정 — 사람이 지정' });

        groups.forEach(function (group) {
            var rows = state.rows.filter(function (row) {
                if (row.role === 'main') return row.external_id === group.key;
                return effectiveMain(row) === group.key;
            });
            if (!rows.length) return;
            var header = el('div', 'naver-dock-grp', group.label);
            var mainRow = state.rows.filter(function (row) {
                return row.role === 'main' && row.external_id === group.key;
            })[0];
            if (mainRow && typeof mainRow.amount === 'number' && mainRow.amount > 0) {
                header.appendChild(el('span', 'naver-dock-grp-sub', formatAmount(mainRow.amount)));
            }
            bd.appendChild(header);
            rows.forEach(function (row) { bd.appendChild(buildRow(row)); });
        });
        frag.appendChild(bd);

        var foot = el('div', 'naver-dock-ft');
        var done = el('button', 'btn btn-success btn-sm', '확인 완료');
        done.type = 'button';
        done.setAttribute('data-naver-dock-done', '1');
        foot.appendChild(done);
        foot.appendChild(el('span', 'naver-dock-hint'));
        frag.appendChild(foot);
        return frag;
    }

    function mounts() {
        return Array.prototype.slice.call(document.querySelectorAll('.erp-naver-dock-mount'));
    }

    function render() {
        mounts().forEach(function (mount) {
            mount.textContent = '';
            mount.appendChild(buildPanel(mount.getAttribute('data-naver-dock-mount') === 'drawer'));
        });
        syncStatus();
    }

    function syncStatus() {
        var total = state.rows.length;
        var checked = checkedCount();
        var blocked = blockers().length;
        var reviewed = allReviewed();
        mounts().forEach(function (mount) {
            var prog = mount.querySelector('.naver-dock-prog');
            if (prog) prog.textContent = checked + ' / ' + total + ' 반영';
            var bar = mount.querySelector('.naver-dock-pbar i');
            if (bar) bar.style.width = (total ? (checked / total) * 100 : 0) + '%';
            var done = mount.querySelector('[data-naver-dock-done]');
            var hint = mount.querySelector('.naver-dock-hint');
            if (!done || !hint) return;
            if (reviewed) {
                done.textContent = '✓ 확인 완료됨';
                done.disabled = true;
                hint.textContent = '';
            } else if (blocked) {
                done.disabled = true;
                hint.textContent = '귀속 미정 항목의 본품을 먼저 선택하세요';
            } else if (checked < total) {
                done.disabled = true;
                hint.textContent = (total - checked) + '건 남음 — 모두 반영하면 활성화';
            } else {
                done.disabled = completing;
                hint.textContent = '모든 항목 반영됨';
            }
        });
        var badge = document.querySelector('.erp-naver-dock-fab-badge');
        if (badge) {
            var remain = total - checked;
            badge.textContent = String(remain);
            badge.classList.toggle('d-none', remain <= 0);
        }
    }

    function findRow(linkId) {
        return state.rows.filter(function (row) { return String(row.link_id) === String(linkId); })[0];
    }

    function postDockState(linkId, body) {
        return fetch('/admin/naver-ingest/' + linkId + '/dock-state', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        }).then(function (response) { return response.json(); });
    }

    /* ── 레이아웃 전환 (셸 폭 기준 — 뷰포트 MQ 금지) ── */
    function shell() { return document.getElementById('erpEditShell'); }

    function applyLayout() {
        var shellNode = shell();
        var pane = document.getElementById('erpNaverDockPane');
        var fab = document.getElementById('erpNaverDockFab');
        var drawer = document.getElementById('erpNaverDockDrawer');
        if (!shellNode || !pane || !fab || !drawer) return;
        var wdcOpen = shellNode.classList.contains('is-wdc-split-open');
        var docked = !wdcOpen && shellNode.clientWidth >= DOCK_MIN_SHELL_WIDTH;
        pane.classList.toggle('d-none', !docked);
        shellNode.classList.toggle('is-naver-dock-open', docked);
        fab.classList.toggle('d-none', docked);
        if (docked) closeDrawer();
    }

    function openDrawer() {
        var drawer = document.getElementById('erpNaverDockDrawer');
        var fab = document.getElementById('erpNaverDockFab');
        if (!drawer) return;
        drawer.classList.add('is-open');
        drawer.setAttribute('aria-hidden', 'false');
        if (fab) fab.setAttribute('aria-expanded', 'true');
    }

    function closeDrawer() {
        var drawer = document.getElementById('erpNaverDockDrawer');
        var fab = document.getElementById('erpNaverDockFab');
        if (!drawer) return;
        drawer.classList.remove('is-open');
        drawer.setAttribute('aria-hidden', 'true');
        if (fab) fab.setAttribute('aria-expanded', 'false');
    }

    /* ── 문서 위임(싱글톤) — fragment 재실행에도 리스너가 중복되지 않는다 ── */
    document.addEventListener('click', function (event) {
        var copy = event.target.closest('[data-naver-dock-copy]');
        if (copy) {
            var value = copy.getAttribute('data-naver-dock-copy');
            if (navigator.clipboard) navigator.clipboard.writeText(value).catch(function () {});
            var original = copy.textContent;
            copy.classList.add('is-copied');
            copy.textContent = '✓ 복사됨';
            setTimeout(function () {
                copy.textContent = original;
                copy.classList.remove('is-copied');
            }, 1200);
            return;
        }
        if (event.target.closest('#erpNaverDockFab')) { openDrawer(); return; }
        if (event.target.closest('[data-naver-dock-close]')) { closeDrawer(); return; }
        var done = event.target.closest('[data-naver-dock-done]');
        if (done && state && !done.disabled && !completing) {
            completing = true;
            syncStatus();
            var pending = state.rows.filter(function (row) { return !row.reviewed; });
            var chain = Promise.resolve();
            pending.forEach(function (row) {
                chain = chain.then(function () {
                    return fetch('/admin/naver-ingest/' + row.link_id + '/review', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: '{}'
                    }).then(function (response) { return response.json(); }).then(function (data) {
                        if (data && data.success) row.reviewed = true;
                    });
                });
            });
            chain.then(function () {
                completing = false;
                syncStatus();
            }).catch(function () {
                completing = false;
                syncStatus();
            });
        }
    });

    document.addEventListener('change', function (event) {
        if (!state) return;
        var check = event.target.closest('[data-naver-dock-check]');
        if (check) {
            var row = findRow(check.getAttribute('data-naver-dock-check'));
            if (!row) return;
            var next = check.checked;
            postDockState(row.link_id, { checked: next }).then(function (data) {
                if (!data || !data.success) throw new Error((data && data.error) || 'save failed');
                row.checked = next;
                render();
            }).catch(function () {
                check.checked = !next; // 저장 실패 — 화면을 서버 상태로 되돌린다.
                syncStatus();
            });
            return;
        }
        var assign = event.target.closest('[data-naver-dock-assign]');
        if (assign) {
            var addonRow = findRow(assign.getAttribute('data-naver-dock-assign'));
            if (!addonRow) return;
            var value = assign.value || null;
            postDockState(addonRow.link_id, { assigned_main: value }).then(function (data) {
                if (!data || !data.success) throw new Error((data && data.error) || 'save failed');
                addonRow.assigned_main = value;
                render();
            }).catch(function () {
                assign.value = effectiveMain(addonRow) || '';
                syncStatus();
            });
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') closeDrawer();
    });

    /* ── 초기화: 마운트가 있으면 렌더, fragment 로 나중에 오면 감시로 잡는다 ── */
    var resizeObserver = null;

    function init() {
        var pane = document.getElementById('erpNaverDockPane');
        if (!pane) return;
        state = null;
        var payload = readBootstrap();
        if (!payload || !payload.rows || !payload.rows.length) return;
        state = {
            orderNo: payload.order_no || '',
            rows: payload.rows,
            mains: payload.mains || [],
            assignCommon: payload.assign_common || 'COMMON'
        };
        render();
        applyLayout();
        var shellNode = shell();
        if (shellNode && typeof ResizeObserver !== 'undefined') {
            if (resizeObserver) resizeObserver.disconnect();
            resizeObserver = new ResizeObserver(applyLayout);
            resizeObserver.observe(shellNode);
            // WDC split 열림/닫힘(셸 클래스 변경)에도 도킹 여부를 재판정한다.
            new MutationObserver(applyLayout)
                .observe(shellNode, { attributes: true, attributeFilter: ['class'] });
        }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init, { once: true });
    } else {
        init();
    }
    // fragment 스왑으로 편집 화면이 나중에 도착하는 경로 — 마운트 등장 시 재초기화.
    new MutationObserver(function (mutations) {
        for (var i = 0; i < mutations.length; i += 1) {
            var added = mutations[i].addedNodes;
            for (var j = 0; j < added.length; j += 1) {
                var node = added[j];
                if (node.nodeType === 1 &&
                    (node.id === 'erpNaverDockPane' || (node.querySelector && node.querySelector('#erpNaverDockPane')))) {
                    init();
                    return;
                }
            }
        }
    }).observe(document.documentElement, { childList: true, subtree: true });
})();

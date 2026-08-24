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
        // 전용 태그를 읽는다 — #erp-order-bootstrap 은 erp-order-shared.js 가
        // 1회 소비 후 DOM 에서 제거하므로(_erpConsumeBootstrap) 의존하면 레이스가 난다.
        var node = document.getElementById('naver-origin-data');
        if (!node) return null;
        try {
            return JSON.parse(node.textContent || 'null');
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

    /**
     * 결제 기록의 관계별 집계 한 칸 (R1).
     * payload 에 관계별 분해가 없으면(옛 서버 응답) 합계를 통째로 addon 으로 본다 —
     * 지금까지 화면이 그렇게 말해 왔으므로 그 경우 표기가 바뀌지 않는다.
     * @param {Object} payload 도크 payload.
     * @param {string} key 'addon' | 'repay'.
     * @returns {{count: number, total: number}}
     */
    function extraPaymentBucket(payload, key) {
        var split = payload.extra_payment_by_relation;
        if (split && split[key]) {
            return { count: split[key].count || 0, total: split[key].total || 0 };
        }
        if (key === 'addon') {
            return {
                count: payload.extra_payment_count || 0,
                total: payload.extra_payment_total || 0
            };
        }
        return { count: 0, total: 0 };
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
            select.className = 'naver-dock-assign' + (effectiveMain(row) ? '' : ' is-unset');
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

    /**
     * 머리말 정보 블록 — 수취인/주문자 이름과 배송메모.
     * 주문 대표 이름은 수취인이다. 주문자는 **다를 때만** 보조로 띄운다(대리주문 표식).
     * 배송메모는 원문 그대로 보여주고 복사만 제공한다 — 폼에 자동 기입하지 않는다.
     * @returns {Element|null} 보여줄 것이 없으면 null.
     */
    function buildInfo() {
        var hasWho = !!state.recipientName;
        var hasMemo = !!state.shippingMemo;
        var hasClaim = !!state.claimLabel;
        var hasFacts = !!(state.recipientTel2 || state.paidAt || state.payMeans || state.discount || state.extraPaymentCount);
        if (!hasWho && !hasMemo && !hasClaim && !hasFacts) return null;
        var info = el('div', 'naver-dock-info');
        if (hasClaim) {
            // 취소·반품은 productOrderStatus 로는 안 보인다 — 규격을 채우기 전에 걸려야 한다.
            info.appendChild(el('div', 'naver-dock-claim', '⚠ 네이버 ' + state.claimLabel));
        }
        if (hasWho) {
            var who = el('div', 'naver-dock-who');
            who.appendChild(el('span', 'naver-dock-who-name', '수취인 ' + state.recipientName));
            if (state.ordererDiffers) {
                who.appendChild(el('span', 'naver-dock-who-diff',
                    '주문자 다름 · ' + state.ordererName));
            }
            info.appendChild(who);
        }
        // 연락·정산 보조 정보 — 값이 있는 것만 줄로 나온다(빈 라벨이 자리를 먹지 않게).
        var facts = [];
        if (state.recipientTel2) facts.push(['보조 연락처', state.recipientTel2, true]);
        if (state.paidAt || state.payMeans) {
            facts.push(['결제', [state.paidAt, state.payMeans].filter(Boolean).join(' · '), false]);
        }
        if (state.discount) {
            facts.push(['할인', state.discount.toLocaleString('ko-KR') + '원', false]);
        }
        // 추가결제(차액)·재결제 기록. 금액은 기록만이라 출고가·잔금에는 반영돼 있지 않다 —
        // 사람이 보고 판단하라고 여기서 알려준다(T16-F).
        // 관계별로 가른다(R1 · 2026-08-24 스펙 §4.4): ADDON 은 원 주문에 **더** 낸 차액이라
        // 출고가에 더하는 것이 맞고, REPAY 는 원 결제가 환불된 뒤 **다시** 낸 같은 물건값이라
        // 더하면 주문 하나 값만큼 두 번 센다. 섞인 집은 두 줄로 각각 말한다.
        if (state.extraPaymentAddon.count) {
            facts.push(['추가결제',
                state.extraPaymentAddon.count + '건 · ' +
                state.extraPaymentAddon.total.toLocaleString('ko-KR') + '원 (반영은 수동)', false]);
        }
        if (state.extraPaymentRepay.count) {
            facts.push(['재결제',
                state.extraPaymentRepay.count + '건 · ' +
                state.extraPaymentRepay.total.toLocaleString('ko-KR') +
                '원 — 원 주문 취소분 재결제입니다. 출고가·잔금에 더하지 마세요',
                false, 'naver-dock-fact-warn']);
        }
        facts.forEach(function (fact) {
            var row = el('div', fact[3] ? 'naver-dock-fact ' + fact[3] : 'naver-dock-fact');
            row.appendChild(el('span', 'naver-dock-fact-k', fact[0]));
            row.appendChild(el('span', 'naver-dock-fact-v', fact[1]));
            if (fact[2]) {
                var copyFact = el('button', 'naver-dock-copy', '📋');
                copyFact.type = 'button';
                copyFact.setAttribute('data-naver-dock-copy', fact[1]);
                row.appendChild(copyFact);
            }
            info.appendChild(row);
        });
        if (hasMemo) {
            var memo = el('div', 'naver-dock-memo');
            var memoHead = el('div', 'naver-dock-memo-hd', '📮 배송메모');
            var copy = el('button', 'naver-dock-copy', '📋 복사');
            copy.type = 'button';
            copy.setAttribute('data-naver-dock-copy', state.shippingMemo);
            memoHead.appendChild(copy);
            memo.appendChild(memoHead);
            memo.appendChild(el('div', 'naver-dock-memo-body', state.shippingMemo));
            info.appendChild(memo);
        }
        return info;
    }

    /**
     * 총폭 힌트 박스 — 본품 모듈 폭 × 수량 + 길이추가(1cm) × 수량.
     * 규격 SSOT 를 지키기 위해 **값을 폼에 넣지 않는다**. 계산식과 복사 버튼까지다.
     * @param {Object} hint 서버가 계산한 {total_mm, formula, mismatch}.
     * @returns {Element} 힌트 박스.
     */
    function buildWidthHint(hint) {
        var box = el('div', 'naver-dock-width');
        var head = el('div', 'naver-dock-width-hd');
        head.appendChild(el('span', null, '총폭 ' + hint.total_mm.toLocaleString('ko-KR') + 'mm'));
        var copy = el('button', 'naver-dock-copy', '📋 ' + hint.total_mm);
        copy.type = 'button';
        copy.setAttribute('data-naver-dock-copy', String(hint.total_mm));
        head.appendChild(copy);
        box.appendChild(head);
        box.appendChild(el('div', 'naver-dock-width-formula', hint.formula));
        (hint.mismatch || []).forEach(function (line) {
            // 고객이 몰딩/무몰딩을 섞어 주문하는 사고가 실제로 있다 — 사람이 확인해야 한다.
            box.appendChild(el('div', 'naver-dock-width-warn', '⚠ 사양 불일치 — ' + line));
        });
        return box;
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
        var info = buildInfo();
        if (info) frag.appendChild(info);

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
            var hint = state.widthHints[group.key];
            if (hint) bd.appendChild(buildWidthHint(hint));
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
            assignCommon: payload.assign_common || 'COMMON',
            recipientName: payload.recipient_name || '',
            ordererName: payload.orderer_name || '',
            ordererDiffers: !!payload.orderer_differs,
            shippingMemo: payload.shipping_memo || '',
            claimLabel: payload.claim_label || '',
            recipientTel2: payload.recipient_tel2 || '',
            paidAt: payload.paid_at || '',
            extraPaymentCount: payload.extra_payment_count || 0,
            extraPaymentTotal: payload.extra_payment_total || 0,
            extraPaymentAddon: extraPaymentBucket(payload, 'addon'),
            extraPaymentRepay: extraPaymentBucket(payload, 'repay'),
            payMeans: payload.pay_means || '',
            discount: payload.discount || 0,
            widthHints: payload.width_hints || {}
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

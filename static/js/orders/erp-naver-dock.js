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

    /**
     * 집(네이버 주문번호) 하나의 사실 — 관계·대체 여부·라벨 (N2).
     * @param {string} orderNo 집 주문번호.
     * @returns {Object|null} 서버가 판정한 집 사실(없으면 null).
     */
    function householdFact(orderNo) {
        var list = state.households || [];
        for (var i = 0; i < list.length; i += 1) {
            if (list[i].order_no === orderNo) return list[i];
        }
        return null;
    }

    /**
     * 집 표식 한 조각 — `이전 주문 …4381` / `이번 주문(재결제) …7581` / `추가결제분 …`.
     *
     * 집이 하나뿐인 주문에서는 만들지 않는다 — 보통 주문 화면에 무게를 더하지 않는다.
     * 라벨은 서버가 관계로 판정해 보낸다(관계가 전부 NEW 인 옛 데이터는 라벨이 비어
     * 번호만 남는다 — 재결제로 **추정**하지 않는다).
     * @param {string} orderNo 집 주문번호.
     * @returns {Element|null} 표식 노드(만들 근거가 없으면 null).
     */
    function buildHouseholdChip(orderNo) {
        if (!state.households || state.households.length < 2) return null;
        var fact = householdFact(orderNo);
        if (!fact) return null;
        var tail = fact.order_no ? ' …' + fact.order_no.slice(-4) : '';
        var chip = el('span', 'naver-dock-hh' + (fact.superseded ? ' is-superseded' : ''),
            (fact.label || '주문번호') + tail);
        if (fact.order_no) chip.title = '네이버 주문번호 ' + fact.order_no;
        return chip;
    }

    /**
     * 게이트가 세는 모집단 — **살아 있는 주문 행만**.
     *
     * 재결제로 주문이 둘 붙으면 옛 주문은 이미 취소·환불된 죽은 것이다(`superseded`).
     * 화면은 그것을 흐리게 그려 놓고도 게이트는 체크를 요구했다 — 담당자에게 죽은
     * 주문에 "반영함"을 찍으라고 강요하는 모순이었다(스테이징 order 4485: `0 / 10 반영`,
     * 그중 4행이 이전 주문).
     *
     * 판정값(`row.superseded`)은 서버가 이미 행마다 실어 보낸다 — 새 조회 0, 백엔드 변경 0.
     *
     * 행이 **전부** 죽었으면 옛 모집단으로 되돌린다: `[].every(...)` 는 true 라
     * 살아 있는 행이 0개일 때 게이트가 아무 확인 없이 "확인 완료됨"이라고 말한다.
     * 실데이터에 그런 주문은 없지만, 없다는 것을 근거로 안전장치를 빼지 않는다.
     *
     * @returns {Array} 세기·판정에 쓸 행 목록.
     */
    function liveRows() {
        var live = state.rows.filter(function (row) { return !row.superseded; });
        return live.length ? live : state.rows;
    }

    function blockers() {
        return liveRows().filter(function (row) {
            return row.role === 'addon' && !effectiveMain(row);
        });
    }

    function checkedCount() {
        return liveRows().filter(function (row) { return row.checked; }).length;
    }

    function allReviewed() {
        return liveRows().every(function (row) { return row.reviewed; });
    }

    /**
     * 행 하나. 재결제로 대체된 옛 집의 행은 **흐려지되 살아 있다**(N2) —
     * 복사 버튼·체크·귀속 드롭다운을 그대로 둔다. 재결제는 "같은 주문을 다시 결제"라
     * 옛 옵션 원문이 여전히 유효한 규격일 수 있고, 담당자는 새 집과 **비교**해야 무엇이
     * 바뀌었는지 안다. 접으면 있는 줄도 모른다.
     * @param {Object} row 도크 행.
     * @param {?string} groupNo 이 그룹 본품이 속한 집 번호(없으면 null — 공통·미정 그룹).
     * @returns {Element} 행 노드.
     */
    function buildRow(row, groupNo) {
        var wrap = el('div', 'naver-dock-row' + (row.checked ? ' is-checked' : '')
            + (row.superseded ? ' is-superseded' : ''));
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
        // 그룹 머리말이 말해 주지 못하는 행에만 집 표식을 단다 — 공통·귀속 미정 그룹이거나,
        // 귀속이 집 경계를 넘어 다른 집 본품에 붙은 행이다. 모든 행에 달면 잡음이 된다.
        if (row.external_order_no !== groupNo) {
            var rowChip = buildHouseholdChip(row.external_order_no);
            if (rowChip) title.appendChild(rowChip);
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
                // 이름이 겹치는 본품은 꼬리표를 **앞에** 붙여 읽는다 — 뒤에 붙이면 좁은
                // select 에서 잘려 선택지 두 개가 다시 글자 하나까지 같아진다(N2 결함).
                var option = el('option', null,
                    main.qualifier ? main.qualifier + ' · ' + main.label : main.label);
                option.value = main.external_id;
                if (main.qualifier) option.title = main.label;
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
        var hasFacts = !!(state.recipientTel2 || state.paidAt || state.payMeans || state.discount
            || state.extraPaymentCount || state.couponCount);
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
        // 쿠폰은 **안 썼을 때도** 말한다. 줄이 없으면 "안 썼다"인지 "화면이 모른다"인지
        // 구분이 안 되고, 담당자는 금액이 왜 이런지를 네이버에서 다시 확인하게 된다.
        if (state.couponCount) {
            var coupon = state.couponCount + '장 −' + state.couponDiscount.toLocaleString('ko-KR') + '원';
            // 네이버 100% 부담 쿠폰은 정산액을 깎지 않는다 — 우리 돈이 나간 자리만 덧붙인다.
            coupon += state.couponSellerBurden
                ? ' (판매자 부담 ' + state.couponSellerBurden.toLocaleString('ko-KR') + '원)'
                : ' (전액 네이버 부담)';
            facts.push(['쿠폰', coupon, false]);
        } else {
            facts.push(['쿠폰', '사용 안 함', false]);
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
        // 집이 둘 이상이면 **전부** 말한다. 예전에는 첫 집 번호 하나만 말하면서
        // `워크벤치에서 열기` 는 나중 집을 열어, 읽은 번호와 열리는 집이 어긋났다
        // (2026-08-25 수정). 링크가 여는 집에는 표식을 붙여 어느 쪽인지 못박는다.
        var nos = state.orderNos && state.orderNos.length ? state.orderNos
            : (state.orderNo ? [state.orderNo] : []);
        if (nos.length) {
            var label = el('span', 'naver-dock-orderno', '주문번호 ');
            nos.forEach(function (no, idx) {
                if (idx) label.appendChild(document.createTextNode(' · '));
                var opensHere = nos.length > 1 && state.workbenchUrl
                    && no === state.workbenchOrderNo;
                var one = el('span', opensHere ? 'naver-dock-orderno-open' : '', no);
                if (opensHere) one.title = '워크벤치에서 열기가 여는 주문';
                label.appendChild(one);
            });
            head.appendChild(label);
        }
        // 워크벤치 처리 탭으로 돌아가는 길(R2). 버튼이 아니라 **평범한 앵커**다 —
        // 누르면 그 집이 열릴 뿐 아무것도 네이버로 보내지 않는다. 주소는 서버가
        // 역할·게이트를 보고 만들어 주며, 없으면 앵커 자체가 생기지 않는다.
        if (state.workbenchUrl) {
            var wb = el('a', 'naver-dock-wb', '워크벤치에서 열기 ↗');
            wb.href = state.workbenchUrl;
            wb.target = '_blank';
            wb.rel = 'noopener';
            head.appendChild(wb);
        }
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
            // 집이 둘 이상이면 머리말이 **어느 집의 본품인지** 말한다. 이름이 같은 본품이
            // 두 집에서 나란히 서던 자리다(N2).
            var groupNo = mainRow ? mainRow.external_order_no : null;
            var groupChip = mainRow ? buildHouseholdChip(groupNo) : null;
            if (groupChip) header.appendChild(groupChip);
            if (mainRow && typeof mainRow.amount === 'number' && mainRow.amount > 0) {
                header.appendChild(el('span', 'naver-dock-grp-sub', formatAmount(mainRow.amount)));
            }
            bd.appendChild(header);
            var groupFact = mainRow ? householdFact(groupNo) : null;
            if (groupFact && groupFact.note) {
                bd.appendChild(el('div', 'naver-dock-hh-note', '⚠ ' + groupFact.note));
            }
            var hint = state.widthHints[group.key];
            if (hint) bd.appendChild(buildWidthHint(hint));
            rows.forEach(function (row) { bd.appendChild(buildRow(row, groupNo)); });
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
        var total = liveRows().length;
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
            // 집이 둘 이상인 주문(재결제·추가결제가 나중에 붙은 경우)의 집 번호 전부.
            orderNos: payload.order_nos || (payload.order_no ? [payload.order_no] : []),
            // `워크벤치에서 열기` 가 실제로 여는 집 — 머리말에서 그 집을 표시한다.
            workbenchOrderNo: payload.workbench_order_no || '',
            // 집마다의 관계·라벨(N2) — 화면이 이전 주문 / 이번 주문을 가르는 근거.
            // 옛 서버 응답에는 없다 → 빈 목록이면 표식이 아예 생기지 않는다(오늘과 같음).
            households: payload.households || [],
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
            workbenchUrl: payload.workbench_url || '',
            payMeans: payload.pay_means || '',
            discount: payload.discount || 0,
            // 쿠폰(2026-08-25). `discount` 는 상품할인+쿠폰 합계라 그것만으로는
            // "쿠폰을 썼나"를 알 수 없다 — 장수·할인액·판매자 부담분을 따로 싣는다.
            couponCount: payload.coupon_count || 0,
            couponDiscount: payload.coupon_discount || 0,
            couponSellerBurden: payload.coupon_seller_burden || 0,
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

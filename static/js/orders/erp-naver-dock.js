/**
 * 네이버 원본 도크 (T14-B) — 주문 편집 셸 우측 독립 패널.
 *
 * 폼 불가침 계약: 기존 폼 DOM 의 id·name 은 지금도 일절 참조하지 않는다 — 도크가 읽는
 * 계약은 `data-erp` 속성뿐이다. 값 전달은 2026-09-08 부터 두 갈래다: 제품명·색상·
 * 손잡이·총폭 네 칸은 사람이 칩(⤵)을 눌러 **넣고**(값이 있으면 확인창 1회), 그 밖의
 * 값(돈·발송기한 등)은 오늘처럼 복사만 한다(WDCalculator additive 패턴).
 * 데이터는 #erp-order-bootstrap JSON 의 naver_origin(추가 fetch 0), 체크·귀속 상태는
 * 체크 즉시 서버 저장(팀 공유).
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
     * 그룹 하나의 금액 — 본품 + 그 본품에 귀속된 옵션들의 결제액 합 (D2).
     *
     * **계산을 서버가 아니라 여기서 하는 이유**: 사람이 귀속 드롭다운을 바꾸면 change
     * 위임이 `render()` 를 다시 부른다. 서버가 페이지 로드 시점에 계산해 실어 보낸 값은
     * 그 순간 낡는다(총폭이 실제로 그 상태였다 — 같은 이유로 `computeWidthHint` 로
     * 옮겼다). 정본 등식
     * `본품 + Σ 귀속 옵션` 은 서버 `mapping.map_group` 에 그대로 남고 `items[].price` 도
     * 불변이다. 화면은 **같은 등식을 같은 행으로 다시 셀 뿐**이다.
     *
     * 두 가지를 지킨다.
     * 1. `amount` 가 숫자가 아닌 행은 0 으로 더하지 않고 **모름으로 센다** — 0원과 모름은
     *    다른 사실이고, 0 으로 더하면 합계가 조용히 작아진다.
     * 2. `optionPrice` 는 쓰지 않는다 — 옵션 행의 `amount`(=`totalPaymentAmount`)에 이미
     *    들어 있어 함께 더하면 옵션값을 두 번 센다.
     *
     * @param {Array} rows 그룹에 속한 행들(본품 1 + 옵션 N, 또는 옵션만).
     * @returns {{total: number, known: number, unknown: number}} 합계·센 행 수·모름 행 수.
     */
    function sumRows(rows) {
        var acc = { total: 0, known: 0, unknown: 0 };
        (rows || []).forEach(function (row) {
            if (typeof row.amount === 'number') {
                acc.total += row.amount;
                acc.known += 1;
            } else {
                acc.unknown += 1;
            }
        });
        return acc;
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
     * 행 하나의 금액 칩 — 머리말 합계를 사람이 **검산**할 수 있게 행마다 붙인다 (D2).
     *
     * 본품 행에도 붙는 이유: 검산할 수 없는 합계는 담당자가 다시 믿지 않는다. 예전에는
     * 옵션 행에 0원 표식만 있어서, 머리말 숫자가 어느 행들을 더한 값인지 알 길이 없었다.
     *
     * 세 갈래로 갈린다.
     * - 0원: 기존 `.naver-dock-zero` `'0원'` 그대로 — 담당자가 이미 아는 신호다.
     * - 모름: 원본에 결제액이 없는 행. **0원처럼 그리면 안 된다**(다른 사실이다).
     * - 숫자: 결제액.
     * @param {Object} row 도크 행.
     * @returns {Element} 금액 칩.
     */
    function buildAmountChip(row) {
        if (row.amount === 0) return el('span', 'naver-dock-zero', '0원');
        if (typeof row.amount !== 'number') {
            var unknown = el('span', 'naver-dock-amt is-unknown', '금액 모름');
            unknown.title = '원본에 결제액이 없습니다 — 0원이라는 뜻이 아닙니다';
            return unknown;
        }
        return el('span', 'naver-dock-amt', formatAmount(row.amount));
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
        title.appendChild(buildAmountChip(row));
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
        // 글자가 하는 일을 말한다 — `⤵` 는 칸에 넣는 칩, `📋` 는 복사만 하는 칩이다.
        dockChipsOf(row).forEach(function (chip) {
            var button = el('button', 'naver-dock-copy',
                (chip.target ? '⤵ ' : '📋 ') + chip.value);
            button.type = 'button';
            button.setAttribute('data-naver-dock-copy', chip.value);
            if (chip.target) button.setAttribute('data-naver-dock-target', chip.target);
            acts.appendChild(button);
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
            // 다만 **거부된 클레임은 경고가 아니다** — 주문도 결제도 살아 있다(R-8).
            // 사실은 그대로 보여주고 ⚠ 와 빨강만 뗀다.
            var claimText = (state.claimMoneyBack ? '⚠ 네이버 ' : '네이버 ') + state.claimLabel;
            var claimClass = 'naver-dock-claim'
                + (state.claimMoneyBack ? '' : ' naver-dock-claim--settled');
            info.appendChild(el('div', claimClass, claimText));
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
        // 출고가에 더하는 것이 맞고, REPAY 는 원 결제가 환불된 뒤 **다시** 낸 값이라
        // 더하면 주문 하나 값만큼 두 번 센다. 섞인 집은 두 줄로 각각 말한다.
        //
        // 2026-09-07 사용자 지적: 재결제 줄이 `원 주문 취소분 재결제입니다` 라고 적어서,
        // 담당자가 이 금액을 **지나간 취소 건의 잔재**로 읽었다. 사실은 반대다 — 옛 결제가
        // 환불됐으니 **지금 살아 있는 돈은 이 금액뿐**이고, 재주문에서 구성이 바뀌면 옛
        // 금액과 다르다(실사례 주문 #5158: 옛 1,932,800원 → 지금 1,134,200원). 그래서
        // "더하지 마세요" 는 남기되(두 번 세는 것은 여전히 사고다) **무엇인지 먼저 말한다**.
        if (state.extraPaymentAddon.count) {
            facts.push(['추가결제',
                state.extraPaymentAddon.count + '건 · ' +
                state.extraPaymentAddon.total.toLocaleString('ko-KR') + '원 (반영은 수동)', false]);
        }
        if (state.extraPaymentRepay.count) {
            facts.push(['재결제',
                state.extraPaymentRepay.count + '건 · ' +
                state.extraPaymentRepay.total.toLocaleString('ko-KR') +
                '원 — 지금 받은 결제입니다. 옛 결제는 환불됐으니 출고가·잔금은 이 금액 기준으로 보세요(더하지 마세요)',
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
     * 네이버 결제 금액 카드 — 낱말 + 돈 한 줄 (2026-09-10 사용자 지시).
     *
     * 예약금 목표액·대조 줄·안내문·복사 칩은 뺐다(주문 #5206 캡처: "추가 결제 금액이 얼마인지만
     * 간단히"). 낱말(`relation_label`)과 돈 표기(`live_total_display`)는 **서버가 만든다** —
     * 화면은 그리기만 한다(돈을 다시 포맷하지 않는다). 둘 중 하나라도 비면(관계 집이 없는
     * 보통 주문·금액을 못 읽은 건) 카드가 서지 않는다. 폼은 여전히 **읽지도 쓰지도** 않는다.
     *
     * 카드가 스크롤 영역(`.naver-dock-bd`) 밖에 서는 이유: 행을 아래로 훑는 동안에도
     * 이 숫자가 화면에 남아 있어야 한다.
     * @returns {Element|null} 카드(그릴 근거가 없으면 null — 옛 payload 포함).
     */
    function buildDepositCard() {
        var hint = state.depositHint;
        if (!hint || !hint.relation_label || !hint.live_total_display) return null;
        var card = el('div', 'naver-dock-deposit');
        card.appendChild(el('div', 'naver-dock-deposit-hd', hint.relation_label));
        card.appendChild(el('div', 'naver-dock-deposit-won', hint.live_total_display));
        return card;
    }

    /**
     * 계산식 한 항 — `3,600mm × 12`. 서버 f-string(`{unit:,}mm × {qty}`)과 같은 모양이다.
     * @param {number} unitMm 1개당 길이(mm).
     * @param {number} quantity 수량.
     * @returns {string} 한 항 문자열.
     */
    function widthTerm(unitMm, quantity) {
        return unitMm.toLocaleString('ko-KR') + 'mm × ' + quantity;
    }

    /**
     * 그룹 하나의 총폭 — **지금 화면의 귀속**으로 다시 센다 (W1).
     *
     * **왜 여기서 다시 세나**: 서버가 페이지 로드 시점에 계산한 `width_hints` 는 사람이
     * 귀속 드롭다운을 옮겨도 갱신되지 않았다. 그런데 같은 화면의 금액 합계는 화면이 세서
     * 즉시 바뀐다(`sumRows`) — 한 화면의 두 숫자가 서로 다른 시점을 말하고 있었다.
     *
     * **분업은 금액과 같다**: 길이 해석(`parse_length_mm`·`_LENGTH_ADDON_HINTS`·사양 축)은
     * 서버가 계속 한다. 서버가 행마다 실어 보낸 조각(`width_unit_mm`·`width_label`·
     * `width_axes`)을 화면은 **더하고 문자열로 조립만** 한다 — 파서를 두 벌 두지 않는다.
     *
     * 결과 모양은 서버 `build_width_hint` 와 같다(`total_mm`·`formula`·`parts`·`mismatch`)
     * — `buildWidthHint` 는 어느 쪽에서 왔는지 몰라도 된다.
     *
     * @param {Array} rows 그룹에 그려질 행들(본품 1 + 귀속 옵션 N).
     * @param {?Object} mainRow 그룹의 본품 행(없으면 총폭이랄 게 없다).
     * @returns {?Object} {total_mm, formula, parts, mismatch}. 길이를 못 읽으면 null.
     */
    function computeWidthHint(rows, mainRow) {
        if (!mainRow || typeof mainRow.width_unit_mm !== 'number' || !mainRow.width_unit_mm) {
            return null;
        }
        var mainQty = mainRow.quantity || 1;
        var mainAxes = mainRow.width_axes || {};
        var hint = {
            total_mm: mainRow.width_unit_mm * mainQty,
            formula: '',
            parts: [{ label: mainRow.width_label || '본품',
                      unit_mm: mainRow.width_unit_mm, quantity: mainQty }],
            mismatch: []
        };
        (rows || []).forEach(function (row) {
            // 길이추가가 아닌 옵션(수납구성·거울도어)은 서버가 조각을 안 준다 — 폭과 무관하다.
            if (row === mainRow || row.role !== 'addon') return;
            if (typeof row.width_unit_mm !== 'number' || !row.width_unit_mm) return;
            var qty = row.quantity || 1;
            hint.total_mm += row.width_unit_mm * qty;
            hint.parts.push({ label: row.width_label || '길이추가',
                              unit_mm: row.width_unit_mm, quantity: qty });
            var addonAxes = row.width_axes || {};
            Object.keys(mainAxes).forEach(function (axis) {
                // 고객이 몰딩/무몰딩을 섞어 주문하는 사고가 실재한다 — 사람이 확인해야 한다.
                var addonValue = addonAxes[axis];
                if (!addonValue || addonValue === mainAxes[axis]) return;
                var line = axis + ': 본품 ' + mainAxes[axis] + ' · 추가 ' + addonValue;
                if (hint.mismatch.indexOf(line) < 0) hint.mismatch.push(line);
            });
        });
        hint.formula = hint.parts.map(function (part) {
            return widthTerm(part.unit_mm, part.quantity);
        }).join(' + ');
        return hint;
    }

    /**
     * 이 그룹에 그릴 총폭 힌트 — 새 조각이 있으면 다시 계산, 없으면 서버 값 (W1).
     *
     * 하위호환: 배포 순서에 따라 옛 서버 응답(행 조각 없음)이 새 JS 로 올 수 있다. 그때는
     * 로드 시점 `width_hints` 를 그대로 그려 **오늘과 똑같은 화면**을 낸다.
     * @param {?string} groupKey 그룹 키(본품 external_id / COMMON / null).
     * @param {Array} rows 그룹에 그려질 행들.
     * @param {?Object} mainRow 그룹의 본품 행.
     * @returns {?Object} 총폭 힌트(없으면 null).
     */
    function widthHintFor(groupKey, rows, mainRow) {
        if (mainRow && 'width_unit_mm' in mainRow) return computeWidthHint(rows, mainRow);
        return (groupKey !== null && state.widthHints[groupKey]) || null;
    }

    /**
     * 총폭 힌트 박스 — 본품 모듈 폭 × 수량 + 길이추가(1cm) × 수량.
     * 2026-09-08 부터 이 값은 **W(가로·총폭) 칸에 넣는다**(칩 ⤵ · 확인창 뒤). 규격 SSOT
     * 는 그대로다 — 총폭을 세는 곳은 여전히 여기 한 곳이고, 넣는 값도 여기서 센 mm 정수
     * 그대로다(쉼표 없음). 옵션의 `사이즈`(150·180cm)는 모듈 폭이라 W 칸 자격이 없다.
     * @param {Object} hint {total_mm, formula, mismatch} — 화면이 다시 센 값이거나(W1),
     *     조각이 없는 옛 응답이면 서버가 로드 시점에 계산한 값.
     * @returns {Element} 힌트 박스.
     */
    function buildWidthHint(hint) {
        var box = el('div', 'naver-dock-width');
        var head = el('div', 'naver-dock-width-hd');
        head.appendChild(el('span', null, '총폭 ' + hint.total_mm.toLocaleString('ko-KR') + 'mm'));
        var copy = el('button', 'naver-dock-copy', '⤵ ' + hint.total_mm);
        copy.type = 'button';
        copy.setAttribute('data-naver-dock-copy', String(hint.total_mm));
        // W 칸에 들어갈 자격은 이 칩뿐이다 — 옵션의 `사이즈` 값은 모듈 폭이라 총폭이 아니다.
        copy.setAttribute('data-naver-dock-target', 'spec_width');
        head.appendChild(copy);
        box.appendChild(head);
        box.appendChild(el('div', 'naver-dock-width-formula', hint.formula));
        (hint.mismatch || []).forEach(function (line) {
            // 고객이 몰딩/무몰딩을 섞어 주문하는 사고가 실제로 있다 — 사람이 확인해야 한다.
            box.appendChild(el('div', 'naver-dock-width-warn', '⚠ 사양 불일치 — ' + line));
        });
        return box;
    }

    /**
     * 그룹 머리말의 금액 칸 — **라벨이 붙은** 합계 (D2).
     *
     * 사람이 오해한 원인은 라벨 없는 숫자였다. 예전 머리말은 본품 결제액 하나만 라벨 없이
     * 세워 두어, 그 숫자가 그룹 전체 값으로 읽혔다(귀속된 옵션값이 빠진 값이다).
     * 이제 등식을 이름으로 말한다 — 본품이 있으면 `본품+옵션`, 본품이 없는 묶음
     * (공통·귀속 미정)은 `옵션 합`.
     *
     * 모르는 행이 섞이면 `· 모름 N건` 을 덧붙이고 `is-partial` 로 표시한다. 전부 모르면
     * 합계 자체를 내지 않는다 — 0원처럼 읽히면 안 된다.
     * @param {{total: number, known: number, unknown: number}} sum `sumRows` 결과.
     * @param {?Object} mainRow 이 그룹의 본품 행(없으면 공통·귀속 미정 그룹).
     * @returns {Element|null} 금액 칸(말할 것이 없으면 null).
     */
    function buildGroupAmount(sum, mainRow) {
        if (!sum.known && !sum.unknown) return null;
        var superseded = !!(mainRow && mainRow.superseded);
        var node = el('span', 'naver-dock-grp-sub' + (sum.unknown ? ' is-partial' : '')
            + (superseded ? ' is-superseded' : ''));
        if (sum.known) {
            // 환불된 옛 집의 합계는 아직 유효한 돈이 아니다 — 취소선으로 못박는다.
            if (superseded) node.appendChild(document.createTextNode('환불됨 · '));
            node.appendChild(el('span', 'naver-dock-grp-amt',
                (mainRow ? '본품+옵션 ' : '옵션 합 ') + formatAmount(sum.total)));
        }
        if (sum.unknown) {
            node.appendChild(document.createTextNode(
                (sum.known ? ' · ' : '') + '모름 ' + sum.unknown + '건'));
        }
        return node;
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
        // 칩을 하나씩 누르지 않고 네 칸을 한 번에 채운다(2026-09-08 담당자 요구).
        // 본품이 둘 이상이면 잠근다 — 어느 집 값을 넣을지는 사람의 판단이고, 그 자리는
        // 칩 하나씩이 맞다. 잠근 이유는 title 이 아니라 눌렀을 때 글자로도 말한다.
        var fillAll = el('button', 'btn btn-sm btn-outline-primary naver-dock-fillall',
            '⤵ 전부 넣기');
        fillAll.type = 'button';
        fillAll.setAttribute('data-naver-dock-fill-all', '1');
        if (state.mains.length > 1) {
            fillAll.disabled = true;
            fillAll.title = '본품이 ' + state.mains.length + '개입니다 — 칩을 하나씩 누르세요';
        } else {
            fillAll.title = '제품명·색상·손잡이·W(가로·총폭) 를 한 번에 넣습니다';
        }
        head.appendChild(fillAll);
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
        // 네이버 결제 금액 카드(2026-09-10) — 낱말·돈 표기는 서버, 화면은 노드 2개. 스크롤 영역 밖이라 늘 보인다.
        var deposit = buildDepositCard();
        if (deposit) frag.appendChild(deposit);

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
            // 합계는 **지금 화면에 그려질 행들**로 센다 — 사람이 귀속을 옮기면 rows 가
            // 바뀌고 render() 가 다시 돌아, 머리말과 아래 행이 언제나 같은 모집단이다.
            var groupSum = buildGroupAmount(sumRows(rows), mainRow);
            if (groupSum) header.appendChild(groupSum);
            bd.appendChild(header);
            var groupFact = mainRow ? householdFact(groupNo) : null;
            if (groupFact && groupFact.note) {
                bd.appendChild(el('div', 'naver-dock-hh-note', '⚠ ' + groupFact.note));
            }
            // 총폭도 **지금 화면의 그룹**으로 다시 센다(W1) — 금액 합계와 같은 모집단이다.
            // 예전에는 로드 시점 서버 값을 그대로 그려, 사람이 귀속을 옮기면 한 화면의
            // 두 숫자(금액·총폭)가 서로 다른 시점을 말했다.
            var hint = widthHintFor(group.key, rows, mainRow);
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

    /**
     * 체크 상태만 화면에 반영한다 — 패널을 다시 그리지 않는다.
     *
     * 예전에는 체크 저장이 성공하면 `render()` 가 마운트를 통째로 비우고 새로 만들었다.
     * 스크롤 컨테이너(`.naver-dock-bd`)가 그 안에 있어 새 노드의 `scrollTop` 이 0이 되고,
     * 목록이 매번 맨 위로 튀었다(누르던 체크박스의 포커스도 사라졌다). 체크값이 바꾸는
     * 것은 행의 `is-checked` 클래스와 체크박스 상태뿐이고, 머리말·진행바·완료 버튼은
     * `syncStatus()` 가 이미 담당한다 — 그래서 다시 그릴 이유가 없다.
     *
     * 도크는 넓은 셸(pane)과 좁은 셸(drawer) 두 곳에 같은 행을 그린다 → 둘 다 갱신한다.
     * @param {(string|number)} linkId 행 식별자.
     * @param {boolean} checked 반영 여부.
     * @returns {void}
     */
    function applyRowChecked(linkId, checked) {
        var selector = '[data-naver-dock-row="' + String(linkId) + '"]';
        Array.prototype.forEach.call(document.querySelectorAll(selector), function (node) {
            node.classList.toggle('is-checked', checked);
            var box = node.querySelector('[data-naver-dock-check]');
            if (box && box.checked !== checked) box.checked = checked;
        });
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

    /* ── 칩 자동 입력(2026-09-08) ───────────────────────────────────────────
     * 어느 **칸**에 들어갈 값인지는 서버가 칩에 실어 보내고(`copy_chips[].target`),
     * 어느 **항목·어느 규격 행**에 넣을지는 화면이 정한다 — 서버는 DOM 을 모른다.
     *
     * 아래 도우미는 전부 순수 함수다: 모듈 변수도 전역 `document` 도 만지지 않고
     * 필요한 것을 인자로 받는다. 계약 테스트가 이 선언을 통째로 뜯어 Node 에서 실제로
     * 돌리기 때문이다(`test_naver_dock_width_live.py:_extract_function` 방식) — 모듈
     * 변수를 참조하면 그 자리에서 죽는다.
     * ─────────────────────────────────────────────────────────────────────── */

    /**
     * 행의 칩 목록 — 서버 신형 `copy_chips` 우선, 없으면 옛 `copies` 문자열을 감싼다.
     *
     * 옛 응답 호환이 필요한 이유: 서비스워커가 staticCacheFirst 라 배포 직후 **새 JS +
     * 옛 payload** 창이 생긴다. 그때 이 감싸기가 없으면 칩이 통째로 사라진다.
     * @param {Object} row 도크 행.
     * @returns {Array<{value: string, target: string}>} 칩 목록(순서·길이 = copies).
     */
    function dockChipsOf(row) {
        if (!row) return [];
        if (Array.isArray(row.copy_chips)) {
            return row.copy_chips.map(function (chip) {
                var value = chip && chip.value !== undefined && chip.value !== null ? chip.value : '';
                return { value: String(value), target: String((chip && chip.target) || '') };
            });
        }
        return (row.copies || []).map(function (value) {
            return { value: String(value), target: '' };
        });
    }

    /**
     * 칸 이름 — **화면 라벨과 같은 글자**를 쓴다(사람이 두 이름을 대조하지 않도록).
     * @param {string} target 칸 키.
     * @returns {string} 라벨(모르는 키면 빈 문자열).
     */
    function dockFieldLabel(target) {
        if (target === 'spec_width') return 'W(가로·총폭)';
        if (target === 'product_name') return '제품명';
        if (target === 'color') return '색상';
        if (target === 'handle') return '손잡이';
        return '';
    }

    /**
     * 빈 칸 판정 — `''` · 공백만 · `'상담'`.
     *
     * `'상담'` 을 빈 값으로 세는 이유: 신규 항목의 색상·손잡이 기본값이 `'상담'` 이라
     * (`erp-order-shared.js:1370-1372 defaultConsult`) 이걸 값으로 세면 **언제나** 확인창이
     * 뜬다. 확인창이 늘 뜨면 사람이 읽지 않고 누른다.
     * @param {*} value 칸의 현재 값.
     * @returns {boolean} 비어 있으면 true.
     */
    function dockIsBlankValue(value) {
        var text = String(value === undefined || value === null ? '' : value).trim();
        return text === '' || text === '상담';
    }

    /**
     * 사람이 읽는 항목 이름 — `항목 2`. 인덱스는 0부터라 +1 해서 화면 번호로 만든다.
     * @param {Element} itemRow 품목 행.
     * @returns {string} `항목 N`(번호를 못 읽으면 `항목`).
     */
    function dockItemLabel(itemRow) {
        var data = (itemRow && itemRow.dataset) || {};
        var raw = data.itemIndex !== undefined ? data.itemIndex : data.itemIdx;
        var text = String(raw === undefined || raw === null ? '' : raw).trim();
        // 숫자 변환은 `Number` 로만 한다 — 도크 JS 에 원문 파서가 두 벌 생기지 않게
        // 막는 가드(test_naver_dock_width_live)가 다른 변환 함수의 이름 자체를 금한다.
        var index = text === '' ? NaN : Number(text);
        if (!isFinite(index)) return '항목';
        return '항목 ' + (Math.floor(index) + 1);
    }

    /**
     * 어느 항목에 넣나 — 계약 §4.1 순서.
     *
     * 1. 마지막으로 사람이 만진 항목(아직 목록에 있고 + 숨겨지지 않았을 때만),
     * 2. 지금 보이는 항목(마스터-디테일이 안 고른 행에 `erp-item-row--md-hidden` 을 단다),
     * 3. 그중 펼쳐진 항목(`.is-open` — 모바일 아코디언은 한 번에 하나만 펼친다),
     * 4. 그래도 못 고르면 첫 항목.
     *
     * 1번이 가시성까지 보는 이유: 마스터-디테일 레일 항목은 `role=option` 인 div 라
     * 클릭해도 포커스가 옮겨 가지 않는다(`erp-items-master-detail.js` `selectItem` 에
     * `focus()` 가 없다). 그래서 "항목 1 색상 칸에 타이핑 → 레일에서 항목 3 선택" 뒤에도
     * 마지막 포커스는 항목 1 에 남는다. 그 행은 `erp-item-row--md-hidden` 이라
     * `display:none` 이므로, 거기에 넣으면 값이 **화면에 보이지 않는 항목**으로 들어가고
     * 스크롤·포커스도 아무 반응이 없다. 도크는 넓은 셸에서만 도킹해 이 경로가 주 경로다.
     * @param {Array<Element>} rows 품목 행들.
     * @param {?Element} lastRow 마지막으로 포커스된 행.
     * @returns {?Element} 고른 행(항목이 없으면 null).
     */
    function dockPickItemRow(rows, lastRow) {
        // 유사배열(NodeList)도 받는다 — 진짜 `querySelectorAll` 결과에는 filter 가 없다.
        var list = Array.prototype.slice.call(rows || []);
        if (!list.length) return null;
        var hidden = function (row) {
            return !!(row && row.classList && row.classList.contains('erp-item-row--md-hidden'));
        };
        if (lastRow && list.indexOf(lastRow) !== -1 && !hidden(lastRow)) return lastRow;
        var visible = list.filter(function (row) {
            return !hidden(row);
        });
        var opened = visible.filter(function (row) {
            return row.classList && row.classList.contains('is-open');
        });
        if (opened.length) return opened[0];
        if (visible.length) return visible[0];
        return list[0];
    }

    /**
     * 이 항목의 규격 행 수 — 2개 이상이면 어느 행인지가 사람의 판단이라 확인창을 띄운다.
     * @param {Element} itemRow 품목 행.
     * @returns {number} 규격 행 수.
     */
    function dockSpecRowCount(itemRow) {
        if (!itemRow || !itemRow.querySelectorAll) return 0;
        return itemRow.querySelectorAll('.erp-spec-row').length;
    }

    /**
     * 값을 넣을 칸 — `data-erp` 계약만 읽는다(폼 id·name 무참조).
     *
     * 총폭은 **첫 규격 행의 W 칸**이다. 화면 요약·마스터 디테일 레일·규격 계산기가 이미
     * 셋 다 첫 규격 행을 그 항목의 대표 W 로 읽는다 — 네 번째 정의를 만들지 않는다.
     * @param {Element} itemRow 품목 행.
     * @param {string} target 칸 키.
     * @returns {?Element} 칸(없으면 null).
     */
    function dockFieldFor(itemRow, target) {
        if (!itemRow || !itemRow.querySelector || !target) return null;
        if (target === 'spec_width') {
            return itemRow.querySelector('.erp-spec-row [data-erp="spec_width"][data-spec-row]');
        }
        return itemRow.querySelector('[data-erp="' + target + '"]');
    }

    /**
     * 확인창 문구 — 지금 값과 넣을 값을 **글자로** 보여 준다.
     *
     * 되돌리기(undo)를 만들지 않기 때문에 이 문구가 유일한 게이트다. `field.value = ...`
     * 대입은 브라우저 네이티브 undo 스택도 지운다 — 사람이 누르기 전에 읽을 수 있어야 한다.
     * @param {string} itemLabel `항목 2`.
     * @param {string} fieldLabel `색상`.
     * @param {*} oldValue 칸의 지금 값.
     * @param {string} newValue 넣을 값.
     * @param {string} note 덧붙일 한 줄(없으면 빈 문자열).
     * @returns {string} 확인창 본문.
     */
    function dockFillConfirmText(itemLabel, fieldLabel, oldValue, newValue, note) {
        var old = String(oldValue === undefined || oldValue === null ? '' : oldValue).trim();
        var lines = [
            itemLabel + ' · ' + fieldLabel,
            '지금 값: ' + (old ? old : '(비어 있음)'),
            '넣을 값: ' + newValue
        ];
        if (note) lines.push(note);
        lines.push('');
        lines.push(old
            ? '덮어쓸까요? (취소하면 그대로 둡니다)'
            : '여기에 넣을까요? (취소하면 그대로 둡니다)');
        return lines.join('\n');
    }

    /**
     * 값을 칸에 넣고 **어디에 넣었는지 보여 준다**.
     *
     * `input` → `change` 를 반드시 쏜다: 자동저장이 `#erp-order` 에서 두 이벤트를 캡처로
     * 듣고(`erp-order-autosave.js:413-417`), 폼도 값 주입 뒤 같은 방식으로 쏜다
     * (`erp-order-shared.js:1585`·`1644`). 대입만 하면 자동저장·계산기가 모른다.
     * @param {Element} field 값을 넣을 칸.
     * @param {string} value 넣을 값.
     * @param {boolean} [quiet] 참이면 스크롤·포커스를 하지 않는다 — 일괄 입력에서 네 칸을
     *     각각 끌고 다니면 화면이 네 번 흔들리고 마지막 칸만 남는다. 일괄 입력은 첫 칸
     *     하나만 소리 내어 넣고 나머지는 조용히 넣는다.
     * @returns {boolean} 넣었으면 true.
     */
    function dockApplyValue(field, value, quiet) {
        if (!field) return false;
        field.value = value;
        ['input', 'change'].forEach(function (name) {
            if (field.dispatchEvent) field.dispatchEvent(new Event(name, { bubbles: true }));
        });
        if (quiet) return true;
        // 넣은 칸을 눈으로 확인하게 데려간다 — 포커스가 스크롤을 또 흔들지 않게 preventScroll.
        if (field.scrollIntoView) field.scrollIntoView({ block: 'center', behavior: 'smooth' });
        if (field.focus) field.focus({ preventScroll: true });
        return true;
    }

    /**
     * 칩 하나로 값을 넣는 판단 전체 — 항목 고르기 · 칸 찾기 · 덮어쓰기 확인.
     * @param {string} target 칸 키(빈 값이면 복사만 하는 오늘 경로).
     * @param {string} value 넣을 값.
     * @param {Array<Element>} rows 품목 행들.
     * @param {?Element} lastRow 마지막으로 포커스된 행.
     * @param {function(string): boolean} confirmFn 확인창.
     * @returns {{ok: boolean, itemLabel: string, fieldLabel: string, reason: string}} 결과.
     */
    function dockFillFromChip(target, value, rows, lastRow, confirmFn) {
        if (!target) return { ok: false, reason: '' };
        var itemRow = dockPickItemRow(rows, lastRow);
        if (!itemRow) return { ok: false, reason: '넣을 항목이 없습니다' };
        var field = dockFieldFor(itemRow, target);
        if (!field) return { ok: false, reason: '넣을 칸을 못 찾았습니다' };
        var itemLabel = dockItemLabel(itemRow);
        var fieldLabel = dockFieldLabel(target);
        var specRows = target === 'spec_width' ? dockSpecRowCount(itemRow) : 0;
        // 규격 행이 여럿이면 칸이 비어 있어도 묻는다 — 어느 행인지는 사람의 판단이다.
        var note = specRows > 1 ? '규격 행이 ' + specRows + '개입니다 — 1행에 넣습니다.' : '';
        if (!dockIsBlankValue(field.value) || note) {
            var ask = confirmFn || function () { return false; };
            if (!ask(dockFillConfirmText(itemLabel, fieldLabel, field.value, value, note))) {
                return { ok: false, reason: '넣지 않았습니다' };
            }
        }
        dockApplyValue(field, value);
        return { ok: true, itemLabel: itemLabel, fieldLabel: fieldLabel };
    }

    /**
     * 일괄 입력 계획 — 칸마다 **먼저 나온 칩** 하나만 남긴다.
     *
     * 한 칸을 노리는 칩이 둘일 수 있다. 실사례가 제품명이다: `제품: 로라 무몰딩 여닫이 /
     * 사이즈: 150（무몰딩）` 는 둘 다 제품명 칸을 가리킨다. 네이버는 `제품` 을 먼저 내므로
     * 먼저 나온 것이 더 제품명답다 — 뒤엣것으로 덮으면 이름이 숫자로 바뀐다. 칩을 하나씩
     * 누르는 길은 그대로라, 사람이 사이즈 값을 넣고 싶으면 그 칩을 누르면 된다.
     * @param {Array<{value: string, target: string}>} chips 화면에 그려진 칩들(그리는 순서).
     * @returns {Array<{target: string, value: string}>} 칸마다 하나씩(복사 전용 칩은 뺀다).
     */
    function dockBulkTargets(chips) {
        var seen = {};
        var plan = [];
        (chips || []).forEach(function (chip) {
            var target = String((chip && chip.target) || '');
            var raw = chip && chip.value !== undefined && chip.value !== null ? chip.value : '';
            var value = String(raw);
            if (!target || !value) return;
            if (Object.prototype.hasOwnProperty.call(seen, target)) return;
            seen[target] = true;
            plan.push({ target: target, value: value });
        });
        return plan;
    }

    /**
     * 일괄 입력 확인창 문구 — 덮어쓸 칸을 **한 번에** 보여 준다.
     *
     * 칸마다 확인창을 띄우면 최대 네 번이 뜬다. 네 번 뜨는 확인창은 읽히지 않는다.
     * 취소했을 때 무슨 일이 일어나는지도 여기서 말한다 — 빈 칸은 덮어쓰는 것이 아니라
     * 잃을 값이 없으므로, 취소해도 빈 칸은 채운다.
     * @param {string} itemLabel `항목 2`.
     * @param {Array<Object>} asks 값이 이미 있는(또는 규격 행이 여럿인) 칸들.
     * @param {number} blankCount 확인 없이 채울 빈 칸 수.
     * @returns {string} 확인창 본문.
     */
    function dockBulkConfirmText(itemLabel, asks, blankCount) {
        var lines = [itemLabel + ' — 사람이 볼 칸 ' + asks.length + '개'];
        asks.forEach(function (entry) {
            var raw = entry.field && entry.field.value;
            var old = String(raw === undefined || raw === null ? '' : raw).trim();
            lines.push('· ' + entry.label + ': ' + (old ? old : '(비어 있음)')
                + ' → ' + entry.value + (entry.note ? ' (' + entry.note + ')' : ''));
        });
        lines.push('');
        lines.push(blankCount
            ? '넣을까요? (취소하면 비어 있는 칸 ' + blankCount + '개만 넣습니다)'
            : '넣을까요? (취소하면 그대로 둡니다)');
        return lines.join('\n');
    }

    /**
     * 일괄 입력 — 항목 하나를 골라 계획의 칸들을 한 번에 채운다.
     *
     * 항목 고르기는 칩 하나를 누를 때와 **같은 함수**(:func:`dockPickItemRow`)를 쓴다.
     * 두 길이 다른 항목을 고르면 사람이 어느 항목에 들어갈지 예측할 수 없다.
     * @param {Array<{target: string, value: string}>} plan 칸별 계획.
     * @param {Array<Element>} rows 품목 행들.
     * @param {?Element} lastRow 마지막으로 포커스된 행.
     * @param {function(string): boolean} confirmFn 확인창.
     * @returns {{ok: boolean, itemLabel: string, filled: Array<string>,
     *     skipped: Array<string>, reason: string}} 결과.
     */
    function dockFillAll(plan, rows, lastRow, confirmFn) {
        if (!plan || !plan.length) return { ok: false, reason: '넣을 칩이 없습니다' };
        var itemRow = dockPickItemRow(rows, lastRow);
        if (!itemRow) return { ok: false, reason: '넣을 항목이 없습니다' };
        var itemLabel = dockItemLabel(itemRow);
        var specRows = dockSpecRowCount(itemRow);
        var entries = [];
        plan.forEach(function (chip) {
            var field = dockFieldFor(itemRow, chip.target);
            if (!field) return;
            // 규격 행이 여럿이면 칸이 비어 있어도 사람이 본다 — 어느 행인지가 판단이다.
            var note = chip.target === 'spec_width' && specRows > 1
                ? '규격 행이 ' + specRows + '개입니다 — 1행에 넣습니다.' : '';
            entries.push({
                field: field, value: chip.value, note: note,
                label: dockFieldLabel(chip.target) || chip.target,
                ask: !dockIsBlankValue(field.value) || !!note
            });
        });
        if (!entries.length) return { ok: false, reason: '넣을 칸을 못 찾았습니다' };
        var asks = entries.filter(function (entry) { return entry.ask; });
        var okAll = false;
        if (asks.length) {
            var ask = confirmFn || function () { return false; };
            // 문구는 값을 넣기 **전에** 만든다 — 넣은 뒤 만들면 '지금 값' 이 새 값이 된다.
            okAll = !!ask(dockBulkConfirmText(itemLabel, asks, entries.length - asks.length));
        }
        var approved = entries.filter(function (entry) { return okAll || !entry.ask; });
        if (!approved.length) return { ok: false, reason: '넣지 않았습니다' };
        approved.forEach(function (entry, index) {
            dockApplyValue(entry.field, entry.value, index > 0);
        });
        return {
            ok: true, itemLabel: itemLabel,
            filled: approved.map(function (entry) { return entry.label; }),
            skipped: okAll ? [] : asks.map(function (entry) { return entry.label; })
        };
    }

    /**
     * 품목 행들 — 자동 입력 경로에서 폼 DOM 을 찾는 유일한 자리다.
     *
     * 폼 불가침의 남은 절반은 그대로다: 폼의 **id·name 은 읽지 않는다**. 도크가 보는 것은
     * 클래스 `.erp-item-row` 와 `data-erp` 계약뿐이라 `#erp-items` 로 감싸지 않는다
     * (그 id 를 읽는 순간 폼 id 무참조 가드를 깬다 — 품목 행은 그 컨테이너에만 산다).
     * 기준 노드도 전역 `document` 가 아니라 **도크 자기 노드**에서 받아 온다.
     * @param {Node} root 조회 기준(도크 칩의 `ownerDocument`).
     * @returns {Array<Element>} 품목 행 배열.
     */
    function erpDockItemRows(root) {
        if (!root || !root.querySelectorAll) return [];
        return Array.prototype.slice.call(root.querySelectorAll('.erp-item-row'));
    }

    /* ── 문서 위임(싱글톤) — fragment 재실행에도 리스너가 중복되지 않는다 ── */
    // 사람이 마지막으로 만진 품목 행을 기억한다 — 칩은 "지금 보고 있는 항목"에 들어가야
    // 한다. 마스터-디테일·아코디언 상태보다 포커스가 더 정확한 신호라 먼저 본다.
    var lastItemRow = null;
    document.addEventListener('focusin', function (event) {
        var row = event.target.closest && event.target.closest('.erp-item-row');
        if (row) lastItemRow = row;
    });

    /**
     * 버튼 글자를 잠깐 결과로 바꿨다가 되돌린다 — 도크에는 토스트가 없다.
     * @param {Element} button 누른 버튼.
     * @param {string} text 보여 줄 글자.
     * @param {string} cls 잠깐 붙일 클래스.
     * @param {number} ms 되돌릴 때까지의 밀리초.
     * @returns {void}
     */
    function flashButton(button, text, cls, ms) {
        // 원문은 글자를 바꾸기 **전에** 잡는다 — 바꾼 뒤 잡으면 되돌릴 원문이 사라진다.
        var original = button.textContent;
        button.classList.add(cls);
        button.textContent = text;
        setTimeout(function () {
            button.textContent = original;
            button.classList.remove(cls);
        }, ms);
    }

    document.addEventListener('click', function (event) {
        var fillAll = event.target.closest('[data-naver-dock-fill-all]');
        if (fillAll) {
            if (fillAll.disabled) return;
            // 계획의 재료는 **지금 그려진 칩**이다 — state 를 다시 훑지 않는다. 사람이
            // 귀속을 옮기면 화면이 다시 그려지고, 그 화면이 곧 계획이 된다.
            var mount = fillAll.closest('.erp-naver-dock-mount') || fillAll.ownerDocument;
            var specs = Array.prototype.map.call(
                mount.querySelectorAll('[data-naver-dock-target]'), function (node) {
                    return {
                        value: node.getAttribute('data-naver-dock-copy') || '',
                        target: node.getAttribute('data-naver-dock-target') || ''
                    };
                });
            var bulk = dockFillAll(dockBulkTargets(specs),
                erpDockItemRows(fillAll.ownerDocument), lastItemRow,
                function (text) { return window.confirm(text); });
            if (bulk && bulk.ok) {
                var said = '✓ ' + bulk.itemLabel + ' · ' + bulk.filled.join('·') + ' 넣음';
                if (bulk.skipped.length) said += ' (' + bulk.skipped.join('·') + ' 그대로)';
                flashButton(fillAll, said, 'is-filled', 2200);
            } else {
                flashButton(fillAll, '· ' + ((bulk && bulk.reason) || '넣지 않았습니다'),
                    'is-copied', 1600);
            }
            return;
        }
        var copy = event.target.closest('[data-naver-dock-copy]');
        if (copy) {
            var value = copy.getAttribute('data-naver-dock-copy');
            // 복사는 넣기 성패와 **무관하게 항상 먼저** 한다 — 다른 칸에 또 붙일 수 있어야 한다.
            if (navigator.clipboard) navigator.clipboard.writeText(value).catch(function () {});
            var filled = dockFillFromChip(copy.getAttribute('data-naver-dock-target') || '',
                value, erpDockItemRows(copy.ownerDocument), lastItemRow,
                // window.confirm 을 떼어 넘기지 않는다 — 호출 시 this 가 window 여야 한다.
                function (text) { return window.confirm(text); });
            var filledOk = !!(filled && filled.ok);
            flashButton(copy,
                filledOk
                    ? '✓ ' + filled.itemLabel + ' ' + filled.fieldLabel + '에 넣음'
                    : (filled && filled.reason ? '✓ 복사됨 — ' + filled.reason : '✓ 복사됨'),
                filledOk ? 'is-filled' : 'is-copied',
                filledOk ? 1600 : 1200);
            return;
        }
        // 체크박스(15px)가 너무 작아 손가락으로 누르기 어렵다 — 행 아무 데나 누르면
        // 체크가 되게 한다. 안에 있는 조작 요소(복사 버튼·귀속 select·체크박스 자신)는
        // 제 동작을 그대로 하고, 글자를 끌어 선택하는 중이면 토글하지 않는다.
        var dockRow = event.target.closest('[data-naver-dock-row]');
        if (dockRow && !event.target.closest('input, select, button, a, label, textarea')) {
            var selection = window.getSelection && window.getSelection();
            if (selection && String(selection) !== '') return;
            var box = dockRow.querySelector('[data-naver-dock-check]');
            if (box) {
                box.checked = !box.checked;
                box.dispatchEvent(new Event('change', { bubbles: true }));
            }
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
                applyRowChecked(row.link_id, next);
                syncStatus();
            }).catch(function () {
                // 저장 실패 — 화면을 서버 상태로 되돌린다(양쪽 마운트 모두).
                applyRowChecked(row.link_id, !!row.checked);
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
            // 돈이 되돌아가는 클레임인가. 라벨 존재만 보면 `반품 거부` 에도 경고가 붙는다.
            claimMoneyBack: payload.claim_money_back === true,
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
            widthHints: payload.width_hints || {},
            // 네이버 결제 금액 카드 — 낱말(relation_label)·돈 표기(live_total_display)는 **서버가 만든다**.
            // 키가 없는 옛 응답이면 null 이고, 그러면 카드가 서지 않는다.
            depositHint: payload.deposit_hint || null
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

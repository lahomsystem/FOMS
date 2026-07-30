/**
 * 시공(출고) 대시보드 일정표 PNG 저장.
 * 파일명: 시공일정_YYYY-MM-DD.png / 표 제목: YYYY-MM-DD 시공 일정
 *
 * 라이브 `.shipment-table` 을 html2canvas로 직캡처하면 인라인 편집 입력폼·버튼·
 * 컬럼 리사이즈 핸들이 그대로 찍힌다. 그래서 지방 대시보드(regional-shipping-export.js)와
 * 동일한 전략을 쓴다: 화면 행의 "실제 값"(편집 중 미저장 입력값 포함)만 읽어 전용
 * 오프스크린 클린 표를 새로 만들어 캡처하고, 캡처 후 컨테이너를 제거한다.
 * 표 규격(제목행·엑셀형 테두리 #111827·헤더 #f3f4f6·본문 20px)은 지방/실측 저장과 동일.
 *
 * fragment 스왑마다 재실행되지 않도록 shipment-entry.js 가 1회만 로드하고,
 * foms:erp-shell-fragment-swapped 로 재초기화한다(전역 리스너는 __FOMS_SHIP_EXPORT_BOUND 로 1회).
 * 버튼 바인딩은 dataset 가드로 멱등.
 */
(function () {
    'use strict';

    var EXPORT_TABLE_WIDTH = 1900;
    var EXPORT_TITLE_FONT_SIZE = '38px';
    var EXPORT_HEADER_FONT_SIZE = '15px';
    var EXPORT_BODY_FONT_SIZE = '20px';
    var LINE_COLOR = '#111827';
    var HEADER_BG = '#f3f4f6';
    // 시공팀 그룹 밴드 배경(옅은 인디고) — 지방 대시보드 GROUP_HEADER_BG 와 동일.
    var GROUP_HEADER_BG = '#eef2ff';
    var ADDRESS_MIN_WIDTH = 360;

    // 컬럼 정의: 화면 컬럼에서 '상세'(버튼 전용)를 제외하고 '번호'를 추가한 10컬럼.
    // 주소는 잔여폭을 차지하는 가변 컬럼.
    var COLUMNS = [
        { key: 'no', label: '번호', width: 70, align: 'center' },
        { key: 'customer', label: '고객', width: 200, align: 'center' },
        { key: 'orderer', label: '대리점', width: 150, align: 'center' },
        { key: 'product', label: '제품', width: 240, align: 'left' },
        { key: 'spec', label: '규격(W/300)', width: 110, align: 'center' },
        { key: 'address', label: '현장주소', width: 0, align: 'left', flex: true },
        { key: 'construction_time', label: '시공시간', width: 120, align: 'center' },
        { key: 'drawing_managers', label: '도면담당', width: 130, align: 'center' },
        { key: 'construction_workers', label: '시공자', width: 130, align: 'center' },
        { key: 'manager', label: '담당자', width: 120, align: 'center' }
    ];

    var HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    var _html2canvasPromise = null;

    /**
     * html2canvas는 PNG 저장 클릭 시에만 필요 → 첫 사용 1회 동적 로드 (perf guard G2).
     * @returns {Promise<void>}
     */
    function ensureHtml2canvas() {
        if (typeof window.html2canvas === 'function') return Promise.resolve();
        if (_html2canvasPromise) return _html2canvasPromise;
        _html2canvasPromise = new Promise(function (resolve, reject) {
            var s = document.createElement('script');
            s.src = HTML2CANVAS_SRC;
            s.async = true;
            s.onload = function () {
                if (typeof window.html2canvas === 'function') {
                    resolve();
                } else {
                    _html2canvasPromise = null;
                    reject(new Error('html2canvas loaded but global missing'));
                }
            };
            s.onerror = function () {
                _html2canvasPromise = null;
                reject(new Error('html2canvas load failed'));
            };
            document.head.appendChild(s);
        });
        return _html2canvasPromise;
    }

    /**
     * 오늘 날짜 YYYY-MM-DD (로컬). date 필터 입력이 없을 때의 폴백.
     * @returns {string}
     */
    function localDateIso() {
        var d = new Date();
        return [
            d.getFullYear(),
            String(d.getMonth() + 1).padStart(2, '0'),
            String(d.getDate()).padStart(2, '0')
        ].join('-');
    }

    // ── 라이브 DOM 값 추출 ───────────────────────────────────────────────────

    // 캡처에 담지 않는 조작용 요소(버튼·리사이즈 핸들·아이콘·플레이스홀더).
    var SKIP_SELECTOR = 'button, .col-resize-handle, .address-row-actions, .line-remove-btn,'
        + ' .site-extra-placeholder, i, svg, datalist';
    // view(span) + edit(input) 가 짝으로 들어있는 행. 편집 중 미저장 값을 반영하려고
    // input 이 있으면 input.value 를 정본으로 본다(템플릿이 저장값으로 초기화하므로 안전).
    var VALUE_ROW_SELECTOR = '.shipment-text-row, .shipment-site-extra-row';

    /**
     * 공백 정리 후 비어있지 않을 때만 라인으로 push.
     * @param {Array<string>} out
     * @param {string} text
     */
    function pushLine(out, text) {
        var t = String(text == null ? '' : text).replace(/\s+/g, ' ').trim();
        if (t) out.push(t);
    }

    /**
     * 개행을 유지해야 하는 텍스트(AS 내용/자재)를 라인 배열로 push. 접두는 첫 라인에만.
     * @param {Array<string>} out
     * @param {string} text
     * @param {string} prefix
     */
    function pushMultiline(out, text, prefix) {
        var isFirst = true;
        String(text == null ? '' : text).split(/\r?\n/).forEach(function (part) {
            var t = part.replace(/[ \t]+/g, ' ').trim();
            if (!t) return;
            out.push(isFirst && prefix ? prefix + t : t);
            isFirst = false;
        });
    }

    /**
     * 노드를 순회해 표시 텍스트 라인을 수집(조작용 요소 제외, 입력폼은 값으로).
     * @param {Node} node
     * @param {Array<string>} out
     */
    function collectLines(node, out) {
        if (node.nodeType === 3) {
            pushLine(out, node.nodeValue);
            return;
        }
        if (node.nodeType !== 1) return;
        if (node.matches(SKIP_SELECTOR)) return;

        var tag = node.tagName;
        if (tag === 'INPUT' || tag === 'TEXTAREA') {
            pushLine(out, node.value);
            return;
        }
        if (tag === 'SELECT') {
            var opt = node.options[node.selectedIndex];
            pushLine(out, opt ? opt.textContent : '');
            return;
        }
        if (node.matches(VALUE_ROW_SELECTOR)) {
            var input = node.querySelector('input, textarea');
            if (input) {
                pushLine(out, input.value);
                return;
            }
            var view = node.querySelector('.shipment-text-view, .site-extra-view');
            pushLine(out, view ? view.textContent : node.textContent);
            return;
        }
        Array.prototype.forEach.call(node.childNodes, function (child) {
            collectLines(child, out);
        });
    }

    /**
     * td 의 표시 텍스트 라인 배열.
     * @param {HTMLTableCellElement|null} td
     * @returns {Array<string>}
     */
    function cellLines(td) {
        var out = [];
        if (td) collectLines(td, out);
        return out;
    }

    /**
     * 고객 셀: 이름(뱃지 제거) + 전화.
     * @param {HTMLTableCellElement|null} td
     * @returns {{name: string, phone: string}}
     */
    function customerValue(td) {
        var result = { name: '', phone: '' };
        if (!td) return result;
        var nameDiv = td.querySelector('div');
        if (nameDiv) {
            var clone = nameDiv.cloneNode(true);
            // 자가실측 등 화면 전용 뱃지는 이미지에서 제외.
            Array.prototype.forEach.call(clone.querySelectorAll('.badge'), function (badge) {
                if (badge.parentNode) badge.parentNode.removeChild(badge);
            });
            result.name = (clone.textContent || '').replace(/\s+/g, ' ').trim();
        }
        var phoneNode = td.querySelector('small');
        if (phoneNode) result.phone = (phoneNode.textContent || '').replace(/\s+/g, ' ').trim();
        return result;
    }

    /**
     * 제품 셀 라인. AS 행은 자재(있으면) 또는 AS 내용 박스 텍스트.
     * @param {HTMLTableCellElement|null} td
     * @param {boolean} isAs
     * @returns {Array<string>}
     */
    function productLines(td, isAs) {
        var out = [];
        if (!td) return out;
        if (isAs) {
            var material = td.querySelector('.shipment-as-material-line');
            if (material) {
                out.push('[자재]');
                pushMultiline(out, material.textContent, '');
                return out;
            }
            var box = td.querySelector('.bg-light-danger') || td;
            pushMultiline(out, box.textContent, '');
            return out;
        }
        Array.prototype.forEach.call(td.querySelectorAll('.shipment-product-line'), function (line) {
            pushLine(out, line.textContent);
        });
        return out;
    }

    /**
     * 규격 셀 라인. AS 행은 'AS'.
     * @param {HTMLTableCellElement|null} td
     * @param {boolean} isAs
     * @returns {Array<string>}
     */
    function specLines(td, isAs) {
        if (isAs) return ['AS'];
        var out = [];
        if (!td) return out;
        Array.prototype.forEach.call(td.querySelectorAll('.shipment-spec-line'), function (line) {
            pushLine(out, line.textContent);
        });
        return out;
    }

    /**
     * 현장주소 셀 라인: 기본 주소 + 시공 특이사항(※) + 추가 주소 라인.
     * (.shipment-address-text 의 title 은 '기본 주소' 라벨이라 값이 아니므로 텍스트를 쓴다.)
     * @param {HTMLTableCellElement|null} td
     * @returns {Array<string>}
     */
    function addressLines(td) {
        var out = [];
        if (!td) return out;
        var base = td.querySelector('.shipment-address-text');
        if (base) pushLine(out, base.textContent);
        Array.prototype.forEach.call(td.querySelectorAll('.shipment-site-extra-static-text'), function (el) {
            var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
            if (t) out.push('※ ' + t);
        });
        Array.prototype.forEach.call(td.querySelectorAll('.shipment-site-extra-row'), function (row) {
            var input = row.querySelector('.site-extra-input');
            var view = row.querySelector('.site-extra-view');
            pushLine(out, input ? input.value : (view ? view.textContent : ''));
        });
        return out;
    }

    /**
     * 그룹 밴드 행 라벨(시공팀 · 합계 · 건수 · 잔여).
     * @param {HTMLTableRowElement} tr
     * @returns {string}
     */
    function groupLabel(tr) {
        var parts = [];
        ['.shipment-grp-team', '.shipment-grp-sum', '.shipment-grp-count', '.shipment-grp-remain']
            .forEach(function (sel) {
                Array.prototype.forEach.call(tr.querySelectorAll(sel), function (el) {
                    var t = (el.textContent || '').replace(/\s+/g, ' ').trim();
                    if (t) parts.push(t);
                });
            });
        return parts.join(' · ');
    }

    /**
     * 데이터 행 1건의 캡처용 값.
     * @param {HTMLTableRowElement} tr
     * @returns {Object}
     */
    function extractRow(tr) {
        var isAs = tr.getAttribute('data-as') === '1';
        var workerTd = tr.querySelector('td[data-col-key="construction_workers"]');
        return {
            group: false,
            is_as: isAs,
            customer: customerValue(tr.querySelector('td[data-label="고객"]')),
            orderer: cellLines(tr.querySelector('td[data-label="대리점(발주사)"]')),
            product: productLines(tr.querySelector('td[data-label="제품"]'), isAs),
            spec: specLines(tr.querySelector('td[data-col-key="spec"]'), isAs),
            address: addressLines(tr.querySelector('td[data-col-key="address"]')),
            construction_time: cellLines(tr.querySelector('td[data-label="시공시간"]')),
            drawing_managers: cellLines(tr.querySelector('td[data-label="도면담당자"]')),
            construction_workers: cellLines(workerTd),
            worker_bg_color: workerTd ? (workerTd.getAttribute('data-worker-bg-color') || '') : '',
            worker_text_color: workerTd ? (workerTd.getAttribute('data-worker-text-color') || '') : '',
            manager: cellLines(tr.querySelector('td[data-label="담당자"]'))
        };
    }

    /**
     * 화면 행을 DOM 순서 그대로 수집(화면=이미지 동일 원칙, 재정렬 금지).
     * @param {HTMLTableElement} table
     * @param {boolean} skipHidden 숨김 행 제외 여부
     * @returns {Array<Object>}
     */
    function collectRows(table, skipHidden) {
        var items = [];
        Array.prototype.forEach.call(table.querySelectorAll('tbody > tr'), function (tr) {
            if (skipHidden && tr.offsetParent === null) return;
            if (tr.classList.contains('shipment-grp-row')) {
                var label = groupLabel(tr);
                if (label) items.push({ group: true, label: label });
                return;
            }
            if (!tr.classList.contains('shipment-row')) return; // '데이터가 없습니다' 등
            items.push(extractRow(tr));
        });
        return items;
    }

    /**
     * 캡처 대상 행. 기본은 보이는 행만(필터·코호트 은닉 제외)이지만, 태블릿 가로
     * 코호트처럼 PC 테이블 래퍼째 숨겨진 상태에서는 전부 숨김으로 보여 0건이 되므로
     * 그때만 숨김 필터를 끄고 전체 행을 쓴다.
     * @param {HTMLTableElement} table
     * @returns {Array<Object>}
     */
    function collectExportRows(table) {
        var rows = collectRows(table, true);
        var hasData = rows.some(function (r) { return !r.group; });
        if (hasData) return rows;
        if (!table.querySelector('tbody > tr.shipment-row')) return rows;
        return collectRows(table, false);
    }

    // ── 캡처용 표 생성 ──────────────────────────────────────────────────────

    /**
     * 컬럼 실제 폭: 주소(flex)는 잔여폭, 최소 360px.
     * @returns {Object} key -> px
     */
    function computeWidths() {
        var fixed = 0;
        COLUMNS.forEach(function (c) {
            if (!c.flex) fixed += c.width;
        });
        var widths = {};
        COLUMNS.forEach(function (c) {
            widths[c.key] = c.flex
                ? Math.max(ADDRESS_MIN_WIDTH, EXPORT_TABLE_WIDTH - fixed)
                : c.width;
        });
        return widths;
    }

    /**
     * 본문 td 공통 스타일(엑셀형: bottom + right, 첫 셀만 left).
     * @param {HTMLTableCellElement} td
     * @param {number} idx
     * @param {Object} col
     */
    function styleBodyCell(td, idx, col) {
        td.style.border = 'none';
        td.style.borderBottom = '1px solid ' + LINE_COLOR;
        td.style.borderRight = '1px solid ' + LINE_COLOR;
        if (idx === 0) td.style.borderLeft = '1px solid ' + LINE_COLOR;
        td.style.padding = '10px 8px';
        td.style.fontSize = EXPORT_BODY_FONT_SIZE;
        td.style.fontWeight = '600';
        td.style.color = LINE_COLOR;
        td.style.verticalAlign = 'middle';
        td.style.textAlign = col.align;
        td.style.whiteSpace = 'normal';
        td.style.wordBreak = 'break-word';
        td.style.lineHeight = '1.35';
    }

    /**
     * 고객 셀: (AS 뱃지 +) 이름 굵게 + 전화 작게.
     * @param {Document} doc
     * @param {HTMLTableCellElement} td
     * @param {Object} row
     */
    function fillCustomerCell(doc, td, row) {
        var nameDiv = doc.createElement('div');
        nameDiv.style.fontWeight = '700';
        if (row.is_as) {
            var badge = doc.createElement('span');
            badge.textContent = 'AS';
            badge.style.display = 'inline-block';
            badge.style.minWidth = '34px';
            badge.style.padding = '3px 8px';
            badge.style.marginRight = '8px';
            badge.style.borderRadius = '4px';
            badge.style.border = '1px solid #b02a37';
            badge.style.backgroundColor = '#dc3545';
            badge.style.color = '#ffffff';
            badge.style.fontSize = '16px';
            badge.style.fontWeight = '800';
            badge.style.lineHeight = '1.15';
            badge.style.verticalAlign = 'middle';
            nameDiv.appendChild(badge);
        }
        nameDiv.appendChild(doc.createTextNode(row.customer.name || '-'));
        td.appendChild(nameDiv);
        if (row.customer.phone) {
            var phoneDiv = doc.createElement('div');
            phoneDiv.textContent = row.customer.phone;
            phoneDiv.style.fontSize = '15px';
            phoneDiv.style.fontWeight = '500';
            phoneDiv.style.color = '#4b5563';
            phoneDiv.style.marginTop = '2px';
            td.appendChild(phoneDiv);
        }
    }

    /**
     * 여러 라인을 줄바꿈된 div 로 채운다.
     * @param {Document} doc
     * @param {HTMLTableCellElement} td
     * @param {Array<string>} lines
     */
    function fillLinesCell(doc, td, lines) {
        lines.forEach(function (line) {
            var div = doc.createElement('div');
            div.textContent = line;
            td.appendChild(div);
        });
    }

    /**
     * 제품 셀: AS 자재 라벨 줄('[자재]')만 작게·회색 강조, 나머지는 본문 스타일.
     * @param {Document} doc
     * @param {HTMLTableCellElement} td
     * @param {Array<string>} lines
     */
    function fillProductCell(doc, td, lines) {
        lines.forEach(function (line) {
            var div = doc.createElement('div');
            div.textContent = line;
            if (line === '[자재]') {
                div.style.fontWeight = '800';
                div.style.fontSize = '16px';
                div.style.color = '#6b7280';
            }
            td.appendChild(div);
        });
    }

    /**
     * 시공팀 그룹 밴드 행(표 전체폭 span).
     * @param {Document} doc
     * @param {string} label
     * @returns {HTMLTableRowElement}
     */
    function buildGroupHeaderRow(doc, label) {
        var tr = doc.createElement('tr');
        var td = doc.createElement('td');
        td.colSpan = COLUMNS.length;
        td.textContent = label;
        td.style.backgroundColor = GROUP_HEADER_BG;
        td.style.color = LINE_COLOR;
        td.style.fontWeight = '800';
        td.style.fontSize = '24px';
        td.style.letterSpacing = '0.04em';
        td.style.padding = '12px 14px';
        td.style.textAlign = 'left';
        td.style.border = 'none';
        td.style.borderTop = '1px solid ' + LINE_COLOR;
        td.style.borderBottom = '1px solid ' + LINE_COLOR;
        td.style.borderLeft = '1px solid ' + LINE_COLOR;
        td.style.borderRight = '1px solid ' + LINE_COLOR;
        tr.appendChild(td);
        return tr;
    }

    /**
     * 수집한 값으로 캡처 전용 표를 새로 만든다(지방/실측 저장과 동일 규격).
     * @param {Document} doc
     * @param {Array<Object>} items
     * @param {string} titleText
     * @returns {HTMLTableElement}
     */
    function buildExportTable(doc, items, titleText) {
        var widths = computeWidths();

        var table = doc.createElement('table');
        table.style.width = EXPORT_TABLE_WIDTH + 'px';
        table.style.minWidth = EXPORT_TABLE_WIDTH + 'px';
        table.style.maxWidth = EXPORT_TABLE_WIDTH + 'px';
        table.style.tableLayout = 'fixed';
        table.style.borderCollapse = 'collapse';
        table.style.borderSpacing = '0';
        table.style.backgroundColor = '#ffffff';
        table.style.border = '2px solid ' + LINE_COLOR;
        table.style.fontSize = EXPORT_BODY_FONT_SIZE;
        table.style.lineHeight = '1.35';

        var colgroup = doc.createElement('colgroup');
        COLUMNS.forEach(function (c) {
            var col = doc.createElement('col');
            col.style.width = widths[c.key] + 'px';
            colgroup.appendChild(col);
        });
        table.appendChild(colgroup);

        var thead = doc.createElement('thead');

        var titleRow = doc.createElement('tr');
        var titleCell = doc.createElement('th');
        titleCell.colSpan = COLUMNS.length;
        titleCell.textContent = titleText;
        titleCell.style.padding = '18px 14px';
        titleCell.style.fontSize = EXPORT_TITLE_FONT_SIZE;
        titleCell.style.fontWeight = '900';
        titleCell.style.letterSpacing = '0.12em';
        titleCell.style.textAlign = 'center';
        titleCell.style.backgroundColor = '#ffffff';
        titleCell.style.border = '2px solid ' + LINE_COLOR;
        titleCell.style.borderBottom = '0';
        titleRow.appendChild(titleCell);
        thead.appendChild(titleRow);

        var headerRow = doc.createElement('tr');
        COLUMNS.forEach(function (c) {
            var th = doc.createElement('th');
            th.textContent = c.label;
            th.style.backgroundColor = HEADER_BG;
            th.style.border = '1px solid ' + LINE_COLOR;
            th.style.color = LINE_COLOR;
            th.style.fontSize = EXPORT_HEADER_FONT_SIZE;
            th.style.fontWeight = '800';
            th.style.padding = '10px 8px';
            th.style.textAlign = 'center';
            th.style.verticalAlign = 'middle';
            th.style.whiteSpace = 'nowrap';
            headerRow.appendChild(th);
        });
        thead.appendChild(headerRow);
        table.appendChild(thead);

        var tbody = doc.createElement('tbody');
        var dataNo = 0;
        items.forEach(function (item) {
            if (item.group) {
                tbody.appendChild(buildGroupHeaderRow(doc, item.label));
                return;
            }
            dataNo += 1;

            var tr = doc.createElement('tr');
            COLUMNS.forEach(function (c, idx) {
                var td = doc.createElement('td');
                styleBodyCell(td, idx, c);
                if (c.key === 'no') {
                    td.textContent = String(dataNo);
                    td.style.fontWeight = '700';
                } else if (c.key === 'customer') {
                    fillCustomerCell(doc, td, item);
                } else if (c.key === 'product') {
                    fillProductCell(doc, td, item.product || []);
                } else {
                    fillLinesCell(doc, td, item[c.key] || []);
                }
                if (c.key === 'construction_workers') {
                    if (item.worker_bg_color) td.style.backgroundColor = item.worker_bg_color;
                    if (item.worker_text_color) td.style.color = item.worker_text_color;
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        return table;
    }

    // ── 배선 ────────────────────────────────────────────────────────────────

    function initShipmentImageExport() {
        var exportBtn = document.getElementById('btn-export-image');
        if (!exportBtn || exportBtn.dataset.fomsExportBound === '1') return;
        exportBtn.dataset.fomsExportBound = '1';

        exportBtn.addEventListener('click', async function () {
            var originalText = exportBtn.innerHTML;
            var container = null;
            try {
                exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
                exportBtn.disabled = true;

                var liveTable = document.getElementById('shipment-dashboard-table')
                    || document.querySelector('.shipment-table');
                var items = liveTable ? collectExportRows(liveTable) : [];
                if (!items.some(function (r) { return !r.group; })) {
                    alert('캡처할 시공 일정이 없습니다.');
                    return;
                }

                await ensureHtml2canvas();

                var dateInput = document.querySelector('input[name="date"]');
                var dateStr = (dateInput && dateInput.value) ? dateInput.value : localDateIso();
                var table = buildExportTable(document, items, dateStr + ' 시공 일정');

                // 오프스크린 컨테이너에 붙여 렌더 후 캡처(라이브 DOM 무변형, finally 에서 제거).
                container = document.createElement('div');
                container.style.position = 'fixed';
                container.style.top = '0';
                container.style.left = '-100000px';
                container.style.padding = '0';
                container.style.margin = '0';
                container.style.backgroundColor = '#ffffff';
                container.appendChild(table);
                document.body.appendChild(container);

                var captureScale = Math.max(2, Math.min(window.devicePixelRatio || 1, 3));
                var canvas = await html2canvas(table, {
                    scale: captureScale,
                    useCORS: true,
                    logging: false,
                    backgroundColor: '#ffffff'
                });

                var link = document.createElement('a');
                link.download = '시공일정_' + dateStr + '.png';
                link.href = canvas.toDataURL('image/png');
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } catch (err) {
                console.error('이미지 저장 실패:', err);
                alert('이미지 저장 중 오류가 발생했습니다.\n' + (err && err.message ? err.message : String(err)));
            } finally {
                if (container && container.parentNode) {
                    container.parentNode.removeChild(container);
                }
                exportBtn.innerHTML = originalText;
                exportBtn.disabled = false;
            }
        });
    }

    // entry 동적 로드 대응 readyState 분기 + fragment 스왑 재초기화(버튼은 dataset 가드로 멱등).
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initShipmentImageExport);
    } else {
        initShipmentImageExport();
    }
    if (!window.__FOMS_SHIP_EXPORT_BOUND) {
        window.__FOMS_SHIP_EXPORT_BOUND = true;
        document.addEventListener('foms:erp-shell-fragment-swapped', initShipmentImageExport);
    }
})();

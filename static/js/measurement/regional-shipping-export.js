/**
 * 지방 대시보드 "상차 예정 알림" PNG 저장.
 *
 * 실측 대시보드(image-export.js)와 동일한 표 규격(1520px 고정폭, 제목行,
 * 엑셀형 테두리, 헤더 #f3f4f6, 본문 20px)을 그대로 따른다.
 *
 * 상차 카드 셀은 입력폼(메모 textarea, 날짜 input)이라 라이브 표를 직접
 * 캡처하면 폼이 찍힌다. 그래서 화면 행의 "실제 값"(편집 중이라 아직
 * 저장 전인 날짜/메모 포함)을 읽어 전용 오프스크린 표를 새로 만들어 캡처한다.
 *
 * 컬럼: 번호 · 고객 · 주소 · 제품 · 상차일 · 설치일 · 비고
 */
(function () {
    'use strict';

    // ERP shell fragment 재실행 대비 singleton guard (perf guard G4).
    if (window.__regionalShippingExportBound) return;

    var EXPORT_TABLE_WIDTH = 1520;
    var EXPORT_TITLE_FONT_SIZE = '38px';
    var EXPORT_HEADER_FONT_SIZE = '15px';
    var EXPORT_BODY_FONT_SIZE = '20px';
    var LINE_COLOR = '#111827';
    var HEADER_BG = '#f3f4f6';

    // 컬럼 정의: key(고정폭 px) — 주소는 잔여폭을 차지하는 가변 컬럼.
    // 상차일/설치일은 한눈에 구분되도록 파스텔 배경(시스템 팔레트와 동일):
    //  · 상차일 = 파스텔 블루(상차 알림 카드 테마색)  · 설치일 = 파스텔 앰버(웜 대비)
    var COLUMNS = [
        { key: 'no', label: '번호', width: 70, align: 'center' },
        { key: 'customer', label: '고객', width: 200, align: 'center' },
        { key: 'address', label: '주소', width: 0, align: 'left', flex: true },
        { key: 'product', label: '제품', width: 340, align: 'left' },
        { key: 'shipping_date', label: '상차일', width: 150, align: 'center', bg: '#d1ecf1', headBg: '#bee5eb', textColor: '#0c5460' },
        { key: 'scheduled_date', label: '설치일', width: 150, align: 'center', bg: '#fff3cd', headBg: '#ffeaa7', textColor: '#856404' },
        { key: 'memo', label: '비고', width: 220, align: 'left' }
    ];

    // 상차일 그룹 라벨 밴드 배경(옅은 인디고). 그룹 경계 + 날짜 안내 겸용.
    var GROUP_HEADER_BG = '#eef2ff';

    // 지역(시/도) 그룹 정렬용. 주소 첫 토큰만 보면 되므로 Kakao API 불필요 —
    // 정규화 맵은 서버 address_converter._normalize_address 의 축약어 맵과 동일 규칙.
    var REGION_ORDER = [
        '서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종',
        '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주'
    ];
    var REGION_CANON = {
        '서울': '서울', '서울특별시': '서울',
        '부산': '부산', '부산광역시': '부산',
        '대구': '대구', '대구광역시': '대구',
        '인천': '인천', '인천광역시': '인천',
        '광주': '광주', '광주광역시': '광주',
        '대전': '대전', '대전광역시': '대전',
        '울산': '울산', '울산광역시': '울산',
        '세종': '세종', '세종시': '세종', '세종특별자치시': '세종',
        '경기': '경기', '경기도': '경기',
        '강원': '강원', '강원도': '강원', '강원특별자치도': '강원',
        '충북': '충북', '충청북도': '충북',
        '충남': '충남', '충청남도': '충남',
        '전북': '전북', '전라북도': '전북', '전북특별자치도': '전북',
        '전남': '전남', '전라남도': '전남',
        '경북': '경북', '경상북도': '경북',
        '경남': '경남', '경상남도': '경남',
        '제주': '제주', '제주도': '제주', '제주특별자치도': '제주'
    };

    /**
     * 주소 첫 토큰으로 시/도(canonical) 판정. 미인식은 '기타'.
     * @param {string} address
     * @returns {string}
     */
    function regionOf(address) {
        if (!address) return '기타';
        var token = String(address).trim().split(/\s+/)[0] || '';
        return REGION_CANON[token] || '기타';
    }

    /**
     * 정렬 순서용 시/도 인덱스. '기타'·미인식은 맨 뒤.
     * @param {string} canon
     * @returns {number}
     */
    function regionIndex(canon) {
        var i = REGION_ORDER.indexOf(canon);
        return i === -1 ? 999 : i;
    }

    // html2canvas는 이 기능 사용 시에만 필요 → 첫 클릭 시 1회 동적 로드.
    // (전역 동기 CDN 로드로 모든 페이지 렌더를 막던 문제 회피 — perf guard G2)
    var HTML2CANVAS_SRC = 'https://cdnjs.cloudflare.com/ajax/libs/html2canvas/1.4.1/html2canvas.min.js';
    var _html2canvasPromise = null;
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
     * 오늘 날짜 YY-MM-DD (파일명용).
     * @returns {string}
     */
    function todayYyMmDd() {
        var d = new Date();
        var y = String(d.getFullYear()).slice(-2);
        var m = String(d.getMonth() + 1).padStart(2, '0');
        var day = String(d.getDate()).padStart(2, '0');
        return y + '-' + m + '-' + day;
    }

    /**
     * 한 행(tr.construction-row)에서 캡처에 필요한 값만 추출.
     * 화면에 렌더된 실제 값(편집 중 미저장 날짜/메모 포함)을 읽는다.
     * @param {HTMLTableRowElement} tr
     * @returns {{customer:string, phone:string, address:string, product:string, shipping_date:string, scheduled_date:string, memo:string, is_as_schedule:boolean}}
     */
    function extractRow(tr) {
        // 고객 셀 구조: td > .d-flex.align-items-center > div(outer) > [div(이름+아이콘), small(전화)]
        var customerWrap = tr.querySelector('td .d-flex.align-items-center');
        var customer = '';
        var phone = '';
        if (customerWrap) {
            var outer = customerWrap.querySelector('div');
            if (outer) {
                var nameNode = outer.querySelector('div'); // 이름 + 지방주문 아이콘(텍스트 없음)
                if (nameNode) {
                    var nameClone = nameNode.cloneNode(true);
                    var asBadge = nameClone.querySelector('.regional-as-schedule-badge');
                    if (asBadge && asBadge.parentNode) asBadge.parentNode.removeChild(asBadge);
                    customer = (nameClone.textContent || '').trim();
                }
                var phoneNode = outer.querySelector('small');
                if (phoneNode) phone = (phoneNode.textContent || '').trim();
            }
        }

        // 주소·제품 셀 클래스: cell-wrap(현행)·text-truncate(과거) 둘 다 허용 — 클래스 개명에 export가 다시 깨지지 않게
        var truncCells = tr.querySelectorAll('td.cell-wrap, td.text-truncate');
        var address = '';
        var product = '';
        if (truncCells[0]) {
            address = (truncCells[0].getAttribute('title') || truncCells[0].textContent || '').trim();
        }
        if (truncCells[1]) {
            product = (truncCells[1].getAttribute('title') || truncCells[1].textContent || '').trim();
        }

        var shippingInput = tr.querySelector('input[data-field="shipping_scheduled_date"]');
        var scheduledInput = tr.querySelector('input[data-field="scheduled_date"]');
        var memoInput = tr.querySelector('textarea.regional-memo');

        return {
            customer: customer,
            phone: phone,
            address: address,
            product: product,
            shipping_date: shippingInput ? (shippingInput.value || '').trim() : '',
            scheduled_date: scheduledInput ? (scheduledInput.value || '').trim() : '',
            memo: memoInput ? (memoInput.value || '').trim() : '',
            is_as_schedule: tr.getAttribute('data-as-shipping-schedule') === 'true'
        };
    }

    /**
     * 현재 보이는(필터 통과) 상차 행만 수집 → 상차일 기준으로 그룹 정렬.
     * 1차 상차일 오름차순(빈 상차일은 맨 뒤), 2차 지역(시/도) 순서,
     * 3차 설치일 오름차순(빈 설치일은 그룹 맨 뒤), 4차 주소 가나다순 tiebreak.
     * (백엔드 regional_dashboard shipping_alerts.sort와 동일 기준 — 화면·이미지 통일.)
     * @param {HTMLElement} card
     * @returns {Array}
     */
    function collectVisibleRows(card) {
        var rows = [];
        var trList = card.querySelectorAll('tbody tr.construction-row');
        Array.prototype.forEach.call(trList, function (tr) {
            if (tr.style.display === 'none') return; // 시공 구분 필터로 숨김
            var row = extractRow(tr);
            row.region = regionOf(row.address);
            rows.push(row);
        });
        rows.sort(function (a, b) {
            // 1차: 상차일 오름차순(YYYY-MM-DD 사전순=시간순). 빈 상차일은 맨 뒤.
            var sa = a.shipping_date || '';
            var sb = b.shipping_date || '';
            if (sa !== sb) {
                if (!sa) return 1;
                if (!sb) return -1;
                return sa < sb ? -1 : 1;
            }
            // 2차: 지역(시/도) 순서.
            var diff = regionIndex(a.region) - regionIndex(b.region);
            if (diff !== 0) return diff;
            // 3차: 설치일 오름차순. 빈 설치일은 그룹 맨 뒤('9999-12-31' 취급).
            var ia = a.scheduled_date || '9999-12-31';
            var ib = b.scheduled_date || '9999-12-31';
            if (ia !== ib) return ia < ib ? -1 : 1;
            // 4차: 주소 가나다순(동률 tiebreak).
            return a.address.localeCompare(b.address, 'ko');
        });
        return rows;
    }

    /**
     * 컬럼 실제 폭 계산: 주소(flex)는 잔여폭, 최소 360px.
     * @returns {Object} key -> px
     */
    function computeWidths() {
        var fixed = 0;
        COLUMNS.forEach(function (c) {
            if (!c.flex) fixed += c.width;
        });
        var widths = {};
        COLUMNS.forEach(function (c) {
            widths[c.key] = c.flex ? Math.max(360, EXPORT_TABLE_WIDTH - fixed) : c.width;
        });
        return widths;
    }

    /**
     * 본문 td 공통 스타일(엑셀형: bottom + right, 첫 셀만 left).
     * 컬럼에 bg/textColor 가 있으면 파스텔 강조(상차일·설치일).
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
        td.style.fontWeight = col.bg ? '700' : '600';
        td.style.color = col.textColor || LINE_COLOR;
        if (col.bg) td.style.backgroundColor = col.bg;
        td.style.verticalAlign = 'middle';
        td.style.textAlign = col.align;
        if (col.align === 'left') {
            td.style.whiteSpace = 'normal';
            td.style.wordBreak = 'break-word';
            td.style.lineHeight = '1.35';
        } else {
            td.style.whiteSpace = 'nowrap';
        }
    }

    /**
     * 고객 셀: 이름(굵게) + 전화(작게) 2줄.
     * @param {Document} doc
     * @param {HTMLTableCellElement} td
     * @param {Object} row
     */
    function fillCustomerCell(doc, td, row) {
        var nameDiv = doc.createElement('div');
        nameDiv.style.fontWeight = '700';
        if (row.is_as_schedule) {
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
        nameDiv.appendChild(doc.createTextNode(row.customer || '-'));
        td.appendChild(nameDiv);
        if (row.phone) {
            var phoneDiv = doc.createElement('div');
            phoneDiv.textContent = row.phone;
            phoneDiv.style.fontSize = '15px';
            phoneDiv.style.fontWeight = '500';
            phoneDiv.style.color = '#4b5563';
            phoneDiv.style.marginTop = '2px';
            td.appendChild(phoneDiv);
        }
    }

    /**
     * 상차일(YYYY-MM-DD) → 'N월 N일 상차' 라벨. 앞 0 제거.
     * 빈값/파싱 실패는 '상차일 미정'.
     * @param {string} shipDate
     * @returns {string}
     */
    function formatShipDateLabel(shipDate) {
        if (!shipDate) return '상차일 미정';
        var parts = String(shipDate).split('-');
        if (parts.length < 3) return '상차일 미정';
        var month = Number(parts[1]);
        var day = Number(parts[2]);
        if (!month || !day) return '상차일 미정';
        return month + '월 ' + day + '일 상차';
    }

    /**
     * 상차일 그룹 맨 위 라벨 밴드 행. 한 셀이 표 전체폭을 span.
     * 그룹 구분(여백 대체) + 날짜 안내를 겸한다.
     * @param {Document} doc
     * @param {string} shipDate
     * @returns {HTMLTableRowElement}
     */
    function buildGroupHeaderRow(doc, shipDate) {
        var tr = doc.createElement('tr');
        var td = doc.createElement('td');
        td.colSpan = COLUMNS.length;
        td.textContent = formatShipDateLabel(shipDate);
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
     * 수집한 값으로 캡처 전용 표를 새로 만든다(실측 규격 동일).
     * @param {Document} doc
     * @param {Array} rows
     * @param {string} titleText
     * @returns {HTMLTableElement}
     */
    function buildExportTable(doc, rows, titleText) {
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
            th.style.backgroundColor = c.headBg || HEADER_BG;
            th.style.border = '1px solid ' + LINE_COLOR;
            th.style.color = c.textColor || LINE_COLOR;
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
        var prevShippingDate = null;
        var dataNo = 0;
        rows.forEach(function (row) {
            var shipDate = row.shipping_date || '';
            // 상차일이 바뀌는 경계마다 라벨 밴드 행 삽입(첫 그룹 포함 — prev 초기값 null).
            // 같은 날짜 안에서는 밴드 없이 지역순으로 연속. 빈 상차일끼리는 같은 그룹.
            if (shipDate !== prevShippingDate) {
                tbody.appendChild(buildGroupHeaderRow(doc, shipDate));
            }
            prevShippingDate = shipDate;
            dataNo += 1;

            var tr = doc.createElement('tr');
            COLUMNS.forEach(function (c, idx) {
                var td = doc.createElement('td');
                styleBodyCell(td, idx, c);
                if (c.key === 'no') {
                    td.textContent = String(dataNo);
                    td.style.fontWeight = '700';
                } else if (c.key === 'customer') {
                    fillCustomerCell(doc, td, row);
                } else if (c.key === 'memo') {
                    td.textContent = row.memo || '';
                    td.style.whiteSpace = 'pre-wrap';
                } else {
                    td.textContent = row[c.key] || '';
                }
                tr.appendChild(td);
            });
            tbody.appendChild(tr);
        });
        table.appendChild(tbody);

        return table;
    }

    function initRegionalShippingExport() {
        var exportBtn = document.getElementById('btn-export-shipping-image');
        if (!exportBtn) return;
        var card = exportBtn.closest('.shipping-alert-card');
        if (!card) return;

        exportBtn.addEventListener('click', async function () {
            var originalText = exportBtn.innerHTML;
            var container = null;
            try {
                exportBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 저장 중...';
                exportBtn.disabled = true;

                var rows = collectVisibleRows(card);
                if (!rows.length) {
                    alert('저장할 상차 예정 항목이 없습니다.');
                    return;
                }

                await ensureHtml2canvas();

                var titleText = '상차 예정 알림';
                var table = buildExportTable(document, rows, titleText);

                // 오프스크린 컨테이너에 붙여 렌더 후 캡처.
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
                link.download = todayYyMmDd() + ' 상차예정.png';
                link.href = canvas.toDataURL('image/png');
                document.body.appendChild(link);
                link.click();
                document.body.removeChild(link);
            } catch (err) {
                console.error('상차 예정 이미지 저장 실패:', err);
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

    window.__regionalShippingExportBound = true;

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initRegionalShippingExport);
    } else {
        initRegionalShippingExport();
    }
})();

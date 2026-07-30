// Shipment 대시보드 모듈 (Batch 5: dashboard_main.html inline → static 이동, verbatim).
// erp-shell activateScripts가 fragment swap마다 이 src를 재실행한다(기존 inline과 동일 동작).
// Jinja 게이트(can_edit_shipment)·주입값(selected_date)은 #shipment-dashboard-config의 data-*로 전달한다.
var __shipDashCfgEl = document.getElementById('shipment-dashboard-config');
var __shipDashCanEdit = !!(__shipDashCfgEl && __shipDashCfgEl.dataset.canEdit === 'true');
var __shipDashSelectedDate = (__shipDashCfgEl && __shipDashCfgEl.dataset.selectedDate) || '';

    (function () {
      const STORAGE_KEYS = {
        construction_time: 'erp_shipment_construction_time_list',
        drawing_manager: 'erp_shipment_drawing_manager_list',
        construction_workers: 'erp_shipment_construction_workers_list',
        site_extra: 'erp_shipment_site_extra_list'
      };
      const MAX_SAVED = 20;

      function loadSavedList(key) {
        try {
          const raw = localStorage.getItem(key);
          if (!raw) return [];
          const arr = JSON.parse(raw);
          return Array.isArray(arr) ? arr : [];
        } catch (e) { return []; }
      }

      function saveToList(key, value) {
        if (!value || !value.trim()) return;
        let arr = loadSavedList(key);
        arr = [value.trim()].concat(arr.filter(function (x) { return x !== value.trim(); }));
        arr = arr.slice(0, MAX_SAVED);
        try { localStorage.setItem(key, JSON.stringify(arr)); } catch (e) { }
      }

      function getMergedList(key) {
        var local = loadSavedList(STORAGE_KEYS[key] || key);
        if (window.__erpShipmentSettings && window.__erpShipmentSettings[key]) {
          var server = window.__erpShipmentSettings[key];
          if (Array.isArray(server)) {
            var seen = {};
            var merged = [];
            server.forEach(function (v) {
              var s = '';
              if (key === 'construction_workers' && v && typeof v === 'object') {
                s = String(v.name || v.text || '').trim();
              } else if (v && v.text) {
                s = String(v.text).trim();
              } else {
                s = String(v).trim();
              }
              if (s && !seen[s]) { seen[s] = true; merged.push(s); }
            });
            local.forEach(function (v) { var s = String(v).trim(); if (s && !seen[s]) { seen[s] = true; merged.push(s); } });
            return merged;
          }
        }
        return local;
      }

      function normalizeWorkerName(val) {
        return String(val || '').trim().toLowerCase();
      }

      function getAssignedWorkerCountMap() {
        var map = {};
        document.querySelectorAll('input[data-field="construction_workers"]').forEach(function (inp) {
          var v = normalizeWorkerName(inp.value);
          if (v) map[v] = (map[v] || 0) + 1;
        });
        return map;
      }

      function fillDatalist(id, key) {
        const list = document.getElementById(id);
        if (!list) return;
        list.innerHTML = '';
        const arr = getMergedList(key);
        var countMap = key === 'construction_workers' ? getAssignedWorkerCountMap() : null;
        arr.forEach(function (v) {
          var val = (v && typeof v === 'object' && v.text) ? v.text : String(v);
          if (!val) return;
          var opt = document.createElement('option');
          opt.value = val;
          if (countMap) {
            var n = countMap[normalizeWorkerName(val)] || 0;
            opt.textContent = n >= 1 ? val + ' ' + n : val;
          } else {
            opt.textContent = val;
          }
          list.appendChild(opt);
        });
      }

      function refreshWorkerDatalist() {
        fillDatalist('datalist-construction-workers', 'construction_workers');
      }

      var PASTEL_COLORS = ['#B8D4E3', '#FFE5CC', '#E8D5E9', '#D5E9D5', '#F0D5D5', '#D5D5E9', '#FFF0D5', '#D5E9E5', '#F5D5E5', '#E9E5D5'];
      var WORKER_DEFAULT_BG = '#E9ECEF';

      function getFirstWorkerFromRow(tr) {
        var list = tr.querySelector('.shipment-workers-list');
        if (!list) return '';
        var inputs = list.querySelectorAll('input[data-field="construction_workers"]');
        for (var i = 0; i < inputs.length; i++) {
          var v = String(inputs[i].value || '').trim();
          if (v) return v;
        }
        var views = list.querySelectorAll('.worker-view');
        for (var i = 0; i < views.length; i++) {
          var v = String(views[i].textContent || '').trim();
          if (v) return v;
        }
        return '';
      }
      function workerKeyForSort(tr) {
        var w = getFirstWorkerFromRow(tr);
        return (w && w.toLowerCase()) || 'ZZZ';
      }

      function applyShipmentWorkerSortAndColors() {
        var tbody = document.querySelector('.shipment-table tbody');
        if (!tbody) return;
        var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr.shipment-row'));
        if (!rows.length) return;
        rows.sort(function (a, b) {
          var asA = parseInt(a.dataset.as, 10) || 0;
          var asB = parseInt(b.dataset.as, 10) || 0;
          if (asA !== asB) return asA - asB;
          var wA = workerKeyForSort(a);
          var wB = workerKeyForSort(b);
          if (wA !== wB) return wA.localeCompare(wB);
          var mA = (a.dataset.manager || '').trim() || 'ZZZ';
          var mB = (b.dataset.manager || '').trim() || 'ZZZ';
          if (mA !== mB) return mA.localeCompare(mB);
          return (parseInt(a.dataset.orderId, 10) || 0) - (parseInt(b.dataset.orderId, 10) || 0);
        });
        // 정렬된 .shipment-row 를 재배치하되, 각 (AS여부|팀) 그룹 첫 행 앞에 서버가 심은
        // 그룹 헤더(.shipment-grp-row)를 다시 끼운다. 헤더는 코호트 태블릿(목업 06)에서만
        // 보이고 PC 에선 display:none — 재배치는 PC 표시에 무영향(행 순서=서버 정렬 동일).
        // 키 = "<as>|<팀 소문자>"(dashboard_main.html data-grp-key 와 정합). idempotent.
        var grpHeadByKey = {};
        Array.prototype.forEach.call(tbody.querySelectorAll('tr.shipment-grp-row'), function (h) {
          grpHeadByKey[h.getAttribute('data-grp-key') || ''] = h;
        });
        var desiredOrder = [];
        var lastGrpKey = null;
        rows.forEach(function (tr) {
          var gk = ((parseInt(tr.dataset.as, 10) || 0)) + '|' + (getFirstWorkerFromRow(tr) || '').trim().toLowerCase();
          if (gk !== lastGrpKey) {
            lastGrpKey = gk;
            if (grpHeadByKey[gk]) desiredOrder.push(grpHeadByKey[gk]);
          }
          desiredOrder.push(tr);
        });
        // 순서가 이미 목표와 동일하면 재-append 를 건너뛴다(무조건 재배치 금지).
        // 이 함수는 construction_workers blur 로 예약(setTimeout 0)되므로, 사람 클릭의
        // mousedown→mouseup 사이에 실행될 수 있다. 그때 행을 DOM 이동시키면 click 합성이
        // 무효화되어 첫 클릭이 사라진다(불러오기 버튼 2클릭 버그의 근본 원인).
        // ponytail: indexOf 멤버십 = O(n^2). 행이 수천 단위가 되면 WeakSet/Map 으로 교체.
        var currentOrder = Array.prototype.slice
          .call(tbody.querySelectorAll('tr.shipment-row, tr.shipment-grp-row'))
          .filter(function (el) { return desiredOrder.indexOf(el) !== -1; });
        var sameOrder = currentOrder.length === desiredOrder.length;
        if (sameOrder) {
          for (var oi = 0; oi < desiredOrder.length; oi++) {
            if (currentOrder[oi] !== desiredOrder[oi]) { sameOrder = false; break; }
          }
        }
        if (!sameOrder) {
          desiredOrder.forEach(function (el) { tbody.appendChild(el); });
        }
        var workerList = [];
        rows.forEach(function (tr) {
          var w = getFirstWorkerFromRow(tr);
          var key = w ? w.toLowerCase() : '';
          if (key && workerList.indexOf(key) === -1) workerList.push(key);
        });
        rows.forEach(function (tr) {
          var td = tr.querySelector('td.shipment-worker-cell');
          if (!td) return;
          var w = getFirstWorkerFromRow(tr);
          var key = w ? w.toLowerCase() : '';
          var idx = key ? workerList.indexOf(key) : -1;
          var color = idx >= 0 ? PASTEL_COLORS[idx % PASTEL_COLORS.length] : WORKER_DEFAULT_BG;
          td.style.setProperty('--worker-bg-color', color);
          td.style.backgroundColor = color;
          td.style.color = '#000000';
          td.setAttribute('data-worker-bg-color', color);
        });
      }
      function scheduleApplyShipmentWorkerSortAndColors() {
        setTimeout(applyShipmentWorkerSortAndColors, 0);
      }
      function applyInitialWorkerCellColorsFromData() {
        document.querySelectorAll('.shipment-worker-cell[data-worker-bg-color]').forEach(function (td) {
          var bg = td.getAttribute('data-worker-bg-color');
          var text = td.getAttribute('data-worker-text-color');
          if (bg) { td.style.setProperty('--worker-bg-color', bg); td.style.backgroundColor = bg; }
          if (text) td.style.color = text;
        });
      }
      applyInitialWorkerCellColorsFromData();

      fetch('/api/erp/shipment-settings').then(function (r) { return r.json(); }).then(function (data) {
        if (data && data.success && data.settings) window.__erpShipmentSettings = data.settings;
        fillDatalist('datalist-construction-time', 'construction_time');
        fillDatalist('datalist-drawing-manager', 'drawing_manager');
        fillDatalist('datalist-construction-workers', 'construction_workers');
        applyShipmentWorkerSortAndColors();
      }).catch(function () {
        fillDatalist('datalist-construction-time', 'construction_time');
        fillDatalist('datalist-drawing-manager', 'drawing_manager');
        fillDatalist('datalist-construction-workers', 'construction_workers');
      });
      var shipmentTableEl = document.querySelector('.shipment-table');
      if (shipmentTableEl) {
        shipmentTableEl.addEventListener('blur', function (e) {
          if (e.target && e.target.getAttribute && e.target.getAttribute('data-field') === 'construction_workers') {
            scheduleApplyShipmentWorkerSortAndColors();
          }
        }, true);
      }

      function showSavedDropdown(anchor, listKey, onSelect) {
        var existing = document.getElementById('shipment-saved-dropdown');
        if (existing) existing.remove();
        var list = (typeof getMergedList === 'function' ? getMergedList(listKey) : loadSavedList(STORAGE_KEYS[listKey] || listKey));
        var countMap = listKey === 'construction_workers' ? getAssignedWorkerCountMap() : null;
        if (!list || list.length === 0) {
          var rect = anchor.getBoundingClientRect();
          var div = document.createElement('div');
          div.id = 'shipment-saved-dropdown';
          div.className = 'dropdown-menu show shipment-saved-dropdown';
          div.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + (rect.bottom + 2) + 'px;z-index:1050;min-width:160px;';
          var span = document.createElement('span');
          span.className = 'dropdown-item text-muted';
          span.textContent = '저장된 값이 없습니다.';
          div.appendChild(span);
          div.__shipmentAnchor = anchor;
          document.body.appendChild(div);
          // 닫기는 click 이 아니라 mousedown 으로 감지한다: 버튼 mousedown 에서 열린 경우
          // 같은 제스처의 잔여 click 이 즉시 닫아버리는 것을 막는다(mousedown 은 재발화 없음).
          function closeEmpty(e) {
            if (e && e.target && div.contains(e.target)) return;
            div.remove();
            document.removeEventListener('mousedown', closeEmpty);
          }
          setTimeout(function () { document.addEventListener('mousedown', closeEmpty); }, 10);
          setTimeout(function () { closeEmpty(); }, 2500);
          return;
        }
        var rect = anchor.getBoundingClientRect();
        var div = document.createElement('div');
        div.id = 'shipment-saved-dropdown';
        div.className = 'dropdown-menu show shipment-saved-dropdown';
        div.style.cssText = 'position:fixed;left:' + rect.left + 'px;top:' + (rect.bottom + 2) + 'px;z-index:1050;max-height:200px;overflow:auto;min-width:120px;';
        list.forEach(function (v) {
          var val = (v && typeof v === 'object' && v.text) ? v.text : String(v || '');
          if (!val) return;
          var a = document.createElement('a');
          a.className = 'dropdown-item';
          a.href = '#';
          if (countMap) {
            var n = countMap[normalizeWorkerName(val)] || 0;
            if (n >= 1) {
              a.innerHTML = val + ' <span class="text-primary">' + n + '</span>';
            } else {
              a.textContent = val;
            }
          } else {
            a.textContent = val;
          }
          a.addEventListener('click', function (e) { e.preventDefault(); onSelect(val); div.remove(); });
          div.appendChild(a);
        });
        div.__shipmentAnchor = anchor;
        document.body.appendChild(div);
        // 닫기는 mousedown 감지(위 closeEmpty 와 동일 사유). 드롭다운 내부 mousedown 은
        // 무시해야 항목 a 의 click 이 정상 발화한다.
        function close(e) {
          if (e && e.target && div.contains(e.target)) return;
          div.remove();
          document.removeEventListener('mousedown', close);
        }
        setTimeout(function () { document.addEventListener('mousedown', close); }, 10);
      }

      var shipmentSaveQueue = Object.create(null);

      function getShipmentSaveQueueKey(orderId, field) {
        return String(orderId) + '::' + String(field);
      }

      function runQueuedShipmentSave(orderId, field) {
        var queueKey = getShipmentSaveQueueKey(orderId, field);
        var state = shipmentSaveQueue[queueKey];
        if (!state) return Promise.resolve();

        state.pending = true;
        state.queued = false;
        var payload = {};
        var version = state.version;
        var value = state.value;
        payload[field] = value;

        return fetch('/api/erp/shipment/update/' + orderId, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify(payload)
        }).then(function (r) {
          return r.json().catch(function () { return {}; }).then(function (data) {
            if (!r.ok || !data || !data.success) {
              throw new Error((data && data.message) || ('HTTP ' + r.status));
            }
            return data;
          });
        }).then(function (data) {
          if (state.version === version) {
            var key = document.querySelector('[data-order-id="' + orderId + '"][data-field="' + field + '"]');
            if (key && key.dataset.key) {
              saveToList(STORAGE_KEYS[key.dataset.key.replace('erp_shipment_', '')] || key.dataset.key, Array.isArray(value) ? value[0] : value);
            }
          }
        }).catch(function (err) {
          console.error('shipment field save failed', { orderId: orderId, field: field, error: err });
        }).finally(function () {
          state.pending = false;
          if (state.version !== version || state.queued) {
            runQueuedShipmentSave(orderId, field);
          }
        });
      }

      function saveShipmentField(orderId, field, value) {
        var queueKey = getShipmentSaveQueueKey(orderId, field);
        var state = shipmentSaveQueue[queueKey];

        if (!state) {
          state = { pending: false, queued: false, version: 0, value: null };
          shipmentSaveQueue[queueKey] = state;
        }

        state.value = value;
        state.version += 1;
        state.queued = true;

        if (state.pending) return Promise.resolve();
        return runQueuedShipmentSave(orderId, field);
      }

      function closeShipmentInlineEditors(exceptNode) {
        document.querySelectorAll('.shipment-edit-list.show-add-actions, .shipment-address-block.show-add-actions').forEach(function (el) {
          if (exceptNode && el.contains(exceptNode)) return;
          el.classList.remove('show-add-actions');
        });
      }

      function initAddButtonToggle() {
        document.querySelectorAll('.shipment-edit-list, .shipment-address-block').forEach(function (el) {
          if (el._addToggleBound) return;
          el._addToggleBound = true;
          el.addEventListener('click', function (e) {
            if (e.target.closest('button') || e.target.closest('input') || e.target.closest('select')) return;
            var isOpen = el.classList.contains('show-add-actions');
            closeShipmentInlineEditors(el);
            if (isOpen) el.classList.remove('show-add-actions');
            else el.classList.add('show-add-actions');
          });
        });
      }

      function collectSiteExtra(ul) {
        var lines = [];
        ul.querySelectorAll('li.shipment-site-extra-row').forEach(function (li) {
          var inp = li.querySelector('.site-extra-input');
          var sel = li.querySelector('.site-extra-color');
          if (!inp) return;
          var text = inp.value.trim();
          var color = (sel && sel.value) ? sel.value : 'black';
          lines.push({ text: text, color: color });
        });
        return lines;
      }

      function saveSiteExtraFromUl(ul, orderId) {
        var lines = collectSiteExtra(ul).filter(function (x) { return x.text; });
        saveShipmentField(orderId, 'site_extra', lines);
      }

      document.querySelectorAll('.site-extra-view').forEach(function (view) {
        view.addEventListener('click', function () {
          var li = view.closest('li');
          if (!li) return;
          li.classList.remove('has-value');
          li.classList.add('editing');
          var inp = li.querySelector('.site-extra-input');
          if (inp) { inp.focus(); }
        });
      });

      document.querySelectorAll('.site-extra-input').forEach(function (inp) {
        var li = inp.closest('li');
        var ul = li && li.parentElement;
        var orderId = ul && ul.dataset.orderId;
        var viewSpan = li && li.querySelector('.site-extra-view');
        if (!orderId) return;
        inp.addEventListener('blur', function () {
          var val = inp.value.trim();
          var sel = li.querySelector('.site-extra-color');
          var c = (sel && sel.value) ? sel.value : 'black';
          if (viewSpan) {
            viewSpan.textContent = val;
            viewSpan.className = 'site-extra-view site-extra-color-' + c;
          }
          if (val) { li.classList.add('has-value'); li.classList.remove('editing'); }
          else { li.classList.remove('has-value'); li.classList.add('editing'); }
          saveSiteExtraFromUl(ul, orderId);
          if (val) saveToList(STORAGE_KEYS.site_extra, val);
        });
      });

      document.querySelectorAll('.line-remove-btn').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          if (!orderId) return;
          li.remove();
          saveSiteExtraFromUl(ul, orderId);
        });
      });

      document.querySelectorAll('.site-extra-color').forEach(function (sel) {
        var li = sel.closest('li');
        var ul = li && li.parentElement;
        var orderId = ul && ul.dataset.orderId;
        var inp = li && li.querySelector('.site-extra-input');
        if (!inp || !orderId) return;
        sel.addEventListener('change', function () {
          var c = sel.value || 'black';
          inp.dataset.color = c;
          inp.className = inp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
          saveSiteExtraFromUl(ul, orderId);
        });
      });

      document.querySelectorAll('.shipment-btn-load-saved-site-extra-row').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          var input = li ? li.querySelector('.site-extra-input') : null;
          var viewSpan = li ? li.querySelector('.site-extra-view') : null;
          var sel = li ? li.querySelector('.site-extra-color') : null;
          if (!input || !orderId) return;
          showSavedDropdown(btn, 'site_extra', function (v) {
            input.value = v;
            var c = (sel && sel.value) ? sel.value : 'black';
            if (viewSpan) { viewSpan.textContent = v; viewSpan.className = 'site-extra-view site-extra-color-' + c; }
            if (v) { li.classList.add('has-value'); li.classList.remove('editing'); }
            saveSiteExtraFromUl(ul, orderId);
            if (v) saveToList(STORAGE_KEYS.site_extra, v);
          });
        });
      });

      document.querySelectorAll('.btn-add-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var orderId = btn.dataset.orderId;
          var ul = btn.closest('ul');
          if (!ul) return;
          var li = document.createElement('li');
          li.className = 'shipment-site-extra-row d-flex gap-1 align-items-center flex-wrap editing';
          li.dataset.color = 'black';
          li.innerHTML = '<span class="site-extra-view site-extra-color-black"></span>' +
            '<button type="button" class="btn btn-sm btn-outline-danger line-remove-btn" title="삭제">&times;</button>' +
            '<div class="site-extra-edit d-flex gap-1 align-items-center flex-wrap flex-grow-1">' +
            '<input type="text" class="form-control form-control-sm shipment-input site-extra-input flex-grow-1 site-extra-color-black" data-key="erp_shipment_site_extra" data-color="black" placeholder="추가 주소" style="min-width: 80px;">' +
            '<select class="form-select form-select-sm site-extra-color" style="width: 70px; flex-shrink: 0;" title="글자색">' +
            '<option value="black" selected>검정</option><option value="red">빨강</option><option value="blue">파랑</option><option value="green">초록</option><option value="orange">주황</option><option value="purple">보라</option><option value="brown">갈색</option><option value="navy">남색</option></select>' +
            '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-site-extra-row" data-order-id="' + orderId + '" title="저장된 주소 불러오기"><i class="fas fa-list"></i></button>' +
            '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-site-extra" title="삭제">&times;</button></div>';
          ul.insertBefore(li, btn.closest('li'));
          var viewSpan = li.querySelector('.site-extra-view');
          var newInp = li.querySelector('.site-extra-input');
          viewSpan.addEventListener('click', function () { li.classList.remove('has-value'); li.classList.add('editing'); newInp.focus(); });
          newInp.addEventListener('blur', function () {
            var val = newInp.value.trim();
            var sel = li.querySelector('.site-extra-color');
            var c = (sel && sel.value) ? sel.value : 'black';
            viewSpan.textContent = val;
            viewSpan.className = 'site-extra-view site-extra-color-' + c;
            if (val) { li.classList.add('has-value'); li.classList.remove('editing'); } else { li.classList.remove('has-value'); li.classList.add('editing'); }
            saveSiteExtraFromUl(ul, orderId);
            if (val) saveToList(STORAGE_KEYS.site_extra, val);
          });
          li.querySelector('.line-remove-btn').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
          li.querySelector('.site-extra-color').addEventListener('change', function () {
            var c = this.value || 'black';
            newInp.dataset.color = c;
            newInp.className = newInp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
            saveSiteExtraFromUl(ul, orderId);
          });
          li.querySelector('.shipment-btn-load-saved-site-extra-row').addEventListener('click', function (ev) {
            ev.preventDefault();
            ev.stopPropagation();
            showSavedDropdown(this, 'site_extra', function (v) {
              newInp.value = v;
              viewSpan.textContent = v;
              if (v) { li.classList.add('has-value'); li.classList.remove('editing'); }
              saveSiteExtraFromUl(ul, orderId);
              if (v) saveToList(STORAGE_KEYS.site_extra, v);
            });
          });
          li.querySelector('.btn-remove-site-extra').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
        });
      });

      document.querySelectorAll('.btn-remove-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function () {
          var li = btn.closest('li');
          var ul = li && li.parentElement;
          var orderId = ul && ul.dataset.orderId;
          if (!orderId) return;
          li.remove();
          saveSiteExtraFromUl(ul, orderId);
        });
      });
      function getShipmentEditList(node) {
        return node && node.closest('.shipment-edit-list[data-order-id][data-field]');
      }

      function getShipmentEditField(list) {
        return list ? String(list.dataset.field || '') : '';
      }

      function getShipmentEditListKey(list) {
        return list ? String(list.dataset.listKey || list.dataset.field || '') : '';
      }

      function getShipmentEditStorageKey(list) {
        return list ? String(list.dataset.storageKey || '') : '';
      }

      function getShipmentEditOrderId(list) {
        return list ? String(list.dataset.orderId || '') : '';
      }

      function isShipmentSingleValueList(list) {
        return !!(list && list.dataset.single === 'true');
      }

      function trimShipmentEditValue(value) {
        return String(value || '').trim();
      }

      function getShipmentEditValues(list) {
        var field = getShipmentEditField(list);
        var values = [];
        if (!list || !field) return values;
        list.querySelectorAll('input[data-field="' + field + '"]').forEach(function (input) {
          var value = trimShipmentEditValue(input.value);
          if (value) values.push(value);
        });
        return values;
      }

      function syncShipmentTextRowState(row) {
        if (!row) return '';
        var input = row.querySelector('.shipment-text-input');
        var view = row.querySelector('.shipment-text-view');
        var list = getShipmentEditList(row);
        var value = trimShipmentEditValue(input ? input.value : '');
        if (view) view.textContent = value;
        if (value) {
          row.classList.add('has-value');
          row.classList.remove('editing');
          row.classList.remove('is-empty');
        } else {
          row.classList.remove('has-value');
          row.classList.remove('editing');
          row.classList.toggle('is-empty', isShipmentSingleValueList(list));
          if (!isShipmentSingleValueList(list)) {
            row.classList.add('editing');
          }
        }
        return value;
      }

      function saveShipmentEditList(list) {
        var orderId = getShipmentEditOrderId(list);
        var field = getShipmentEditField(list);
        if (!orderId || !field) return;
        if (isShipmentSingleValueList(list)) {
          var input = list.querySelector('.shipment-text-input');
          saveShipmentField(orderId, field, trimShipmentEditValue(input ? input.value : ''));
        } else {
          saveShipmentField(orderId, field, getShipmentEditValues(list));
        }
        if (field === 'construction_workers') {
          refreshWorkerDatalist();
          scheduleApplyShipmentWorkerSortAndColors();
        }
      }

      function saveShipmentEditRowValue(list, row) {
        var value = syncShipmentTextRowState(row);
        var storageKey = getShipmentEditStorageKey(list);
        if (value && storageKey && STORAGE_KEYS[storageKey]) {
          saveToList(STORAGE_KEYS[storageKey], value);
        }
        saveShipmentEditList(list);
      }

      function escapeShipmentEditHtml(value) {
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function getShipmentEditViewClass(field) {
        if (field === 'construction_workers') return 'shipment-text-view worker-view';
        if (field === 'drawing_managers') return 'shipment-text-view drawing-manager-view';
        return 'shipment-text-view';
      }

      function buildShipmentTextRow(list, value) {
        var field = getShipmentEditField(list);
        var orderId = getShipmentEditOrderId(list);
        var datalistId = list.dataset.datalistId || '';
        var emptyPlaceholder = list.dataset.emptyPlaceholder || '';
        var placeholder = list.dataset.placeholder || '';
        var escapedValue = escapeShipmentEditHtml(value || '');
        var li = document.createElement('li');
        li.className = 'shipment-text-row' + (trimShipmentEditValue(value) ? ' has-value' : ' editing');
        li.innerHTML =
          '<span class="' + getShipmentEditViewClass(field) + '"' +
          (emptyPlaceholder ? ' data-empty-placeholder="' + escapeShipmentEditHtml(emptyPlaceholder) + '"' : '') +
          '>' + escapedValue + '</span>' +
          '<div class="shipment-text-edit input-group input-group-sm flex-nowrap">' +
          '<input type="text" class="form-control form-control-sm shipment-text-input"' +
          ' data-order-id="' + orderId + '"' +
          ' data-field="' + field + '"' +
          ' value="' + escapedValue + '"' +
          ' placeholder="' + escapeShipmentEditHtml(placeholder) + '"' +
          (datalistId ? ' list="' + escapeShipmentEditHtml(datalistId) + '"' : '') +
          '>' +
          '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-text-row" title="저장된 값 불러오기"><i class="fas fa-list"></i></button>' +
          '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-shipment-text-row" title="삭제">&times;</button>' +
          '</div>';
        return li;
      }

      // 불러오기 버튼(행 단위) 드롭다운 오픈 — mousedown/click 양쪽에서 공유한다.
      // 같은 버튼으로 이미 열려 있으면(직전 mousedown 이 연 경우) 재오픈하지 않는다.
      function openShipmentSavedDropdownForLoadBtn(loadBtn) {
        var list = getShipmentEditList(loadBtn);
        var row = loadBtn.closest('.shipment-text-row');
        var input = row && row.querySelector('.shipment-text-input');
        if (!list || !row || !input) return;
        var existing = document.getElementById('shipment-saved-dropdown');
        if (existing && existing.__shipmentAnchor === loadBtn) return;
        showSavedDropdown(loadBtn, getShipmentEditListKey(list), function (value) {
          input.value = value;
          saveShipmentEditRowValue(list, row);
          input.focus();
        });
      }

      if (!window.__shipmentDashboardDocListenersBound) {
        window.__shipmentDashboardDocListenersBound = true;

        document.addEventListener('click', function (e) {
          closeShipmentInlineEditors(e.target);
        });

        document.addEventListener('mousedown', function (e) {
          var btn = e.target.closest('.btn-remove-shipment-text-row, .shipment-btn-load-saved-text-row');
          if (!btn) return;
          var row = e.target.closest('.shipment-text-row');
          // blur-save 건너뛰기는 "이 행의 input 이 실제로 포커스를 잃는" 경우에만 건다.
          // 포커스가 다른 행/요소에 있으면 이 행엔 blur 가 오지 않아 플래그가 stale 로 남고,
          // 다음 진짜 편집의 저장을 한 번 삼킨다(기존 잠복 데이터 유실 경로).
          if (row && row.contains(document.activeElement)) row.dataset.skipBlurSave = '1';
          if (!btn.classList.contains('shipment-btn-load-saved-text-row')) return;
          // 불러오기는 mousedown 에서 즉시 연다: 같은 제스처의 blur → 행 재배치로 click 이
          // 합성되지 않아도(2클릭 버그) 첫 클릭이 동작한다. preventDefault 로 포커스 이동 최소화.
          e.preventDefault();
          openShipmentSavedDropdownForLoadBtn(btn);
        }, true);

        document.addEventListener('click', function (e) {
          var view = e.target.closest('.shipment-text-row .shipment-text-view');
          if (view) {
            var row = view.closest('.shipment-text-row');
            var input = row && row.querySelector('.shipment-text-input');
            if (row && input) {
              e.preventDefault();
              e.stopPropagation();
              row.classList.remove('has-value');
              row.classList.remove('is-empty');
              row.classList.add('editing');
              input.focus();
            }
            return;
          }

          var addBtn = e.target.closest('.btn-add-shipment-text-row');
          if (addBtn) {
            var list = getShipmentEditList(addBtn);
            if (!list) return;
            e.preventDefault();
            e.stopPropagation();
            var row = buildShipmentTextRow(list, '');
            var actionsRow = addBtn.closest('.actions-on-hover');
            list.insertBefore(row, actionsRow || null);
            var input = row.querySelector('.shipment-text-input');
            if (input) input.focus();
            return;
          }

          var removeBtn = e.target.closest('.btn-remove-shipment-text-row');
          if (removeBtn) {
            var list = getShipmentEditList(removeBtn);
            var row = removeBtn.closest('.shipment-text-row');
            if (!list || !row) return;
            e.preventDefault();
            e.stopPropagation();
            if (isShipmentSingleValueList(list)) {
              var input = row.querySelector('.shipment-text-input');
              if (input) input.value = '';
              syncShipmentTextRowState(row);
            } else {
              row.remove();
            }
            saveShipmentEditList(list);
            return;
          }

          var loadBtn = e.target.closest('.shipment-btn-load-saved-text-row');
          if (loadBtn) {
            e.preventDefault();
            e.stopPropagation();
            // 직전 mousedown 이 이미 열었으면 helper 가 no-op (키보드 Enter 등 mousedown 없는
            // 경로에서는 여기서 열린다).
            openShipmentSavedDropdownForLoadBtn(loadBtn);
          }
        });

        document.addEventListener('blur', function (e) {
          if (!e.target.matches || !e.target.matches('.shipment-text-input')) return;
          var input = e.target;
          var row = input.closest('.shipment-text-row');
          var list = getShipmentEditList(input);
          if (!row || !list) return;
          if (row.dataset.skipBlurSave === '1') {
            row.dataset.skipBlurSave = '';
            return;
          }
          saveShipmentEditRowValue(list, row);
        }, true);
      }

      function mountShipmentDashboardSurface() {
        if (!document.querySelector('.shipment-table')) return;
        initAddButtonToggle();
      }

      if (!window.__shipmentDashboardSwapListenerBound) {
        window.__shipmentDashboardSwapListenerBound = true;
        document.addEventListener('foms:main-content-swapped', mountShipmentDashboardSurface);
      }
      mountShipmentDashboardSurface();

      document.querySelectorAll('.shipment-btn-load-saved-site-extra').forEach(function (btn) {
        btn.addEventListener('click', function (e) {
          e.preventDefault();
          e.stopPropagation();
          var orderId = btn.dataset.orderId;
          var ul = btn.closest('ul');
          if (!ul) return;
          showSavedDropdown(btn, 'site_extra', function (v) {
            var li = document.createElement('li');
            li.className = 'shipment-site-extra-row d-flex gap-1 align-items-center flex-wrap has-value';
            li.dataset.color = 'black';
            var escaped = (v + '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            li.innerHTML = '<span class="site-extra-view site-extra-color-black">' + escaped + '</span>' +
              '<button type="button" class="btn btn-sm btn-outline-danger line-remove-btn" title="삭제">&times;</button>' +
              '<div class="site-extra-edit d-flex gap-1 align-items-center flex-wrap flex-grow-1">' +
              '<input type="text" class="form-control form-control-sm shipment-input site-extra-input flex-grow-1 site-extra-color-black" data-key="erp_shipment_site_extra" data-color="black" value="' + escaped + '" placeholder="추가 주소" style="min-width: 80px;">' +
              '<select class="form-select form-select-sm site-extra-color" style="width: 70px; flex-shrink: 0;" title="글자색">' +
              '<option value="black" selected>검정</option><option value="red">빨강</option><option value="blue">파랑</option><option value="green">초록</option><option value="orange">주황</option><option value="purple">보라</option><option value="brown">갈색</option><option value="navy">남색</option></select>' +
              '<button type="button" class="btn btn-sm btn-outline-secondary shipment-btn-load-saved-site-extra-row" data-order-id="' + orderId + '" title="저장된 주소 불러오기"><i class="fas fa-list"></i></button>' +
              '<button type="button" class="btn btn-sm btn-outline-danger btn-remove-site-extra" title="삭제">&times;</button></div>';
            var lastLi = ul.querySelector('li.address-row-actions');
            ul.insertBefore(li, lastLi);
            var viewSpan = li.querySelector('.site-extra-view');
            var newInp = li.querySelector('.site-extra-input');
            li.querySelector('.site-extra-input').addEventListener('blur', function () {
              var val = newInp.value.trim();
              var sel = li.querySelector('.site-extra-color');
              var c = (sel && sel.value) ? sel.value : 'black';
              viewSpan.textContent = val;
              viewSpan.className = 'site-extra-view site-extra-color-' + c;
              if (val) li.classList.add('has-value'); else li.classList.remove('has-value');
              saveSiteExtraFromUl(ul, orderId);
            });
            li.querySelector('.site-extra-color').addEventListener('change', function () {
              var c = this.value || 'black';
              newInp.dataset.color = c;
              newInp.className = newInp.className.replace(/\bsite-extra-color-\w+\b/g, '') + ' site-extra-color-' + c;
              viewSpan.className = 'site-extra-view site-extra-color-' + c;
              saveSiteExtraFromUl(ul, orderId);
            });
            li.querySelector('.line-remove-btn').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
            li.querySelector('.shipment-btn-load-saved-site-extra-row').addEventListener('click', function (ev) {
              ev.preventDefault();
              ev.stopPropagation();
              showSavedDropdown(this, 'site_extra', function (v) {
                newInp.value = v;
                viewSpan.textContent = v;
                if (v) li.classList.add('has-value');
                saveSiteExtraFromUl(ul, orderId);
                if (v) saveToList(STORAGE_KEYS.site_extra, v);
              });
            });
            li.querySelector('.btn-remove-site-extra').addEventListener('click', function () { li.remove(); saveSiteExtraFromUl(ul, orderId); });
            saveSiteExtraFromUl(ul, orderId);
          });
        });
      });
    })();

    if (__shipDashCanEdit) {
    window.__shipmentAsRecPageDate = __shipDashSelectedDate;
    (function shipmentAsRecommendUi() {
      var CHUNK = 5;
      window.__shipmentAsRecModalEl = window.__shipmentAsRecModalEl || null;
      window.__shipmentAsRecMapModalEl = window.__shipmentAsRecMapModalEl || null;
      window.__shipmentAsRecNeedsReload = false;

      function adoptModalFromMain() {
        var main = document.getElementById('main-content');
        if (!main) return;
        var fresh = main.querySelector('#shipmentAsRecommendModal');
        if (!fresh) return;
        var prev = window.__shipmentAsRecModalEl;
        if (prev && prev !== fresh && prev.parentNode) {
          prev.remove();
        }
        document.body.appendChild(fresh);
        window.__shipmentAsRecModalEl = fresh;
        var freshMap = main.querySelector('#scheduleMapModal');
        if (freshMap) {
          var prevMap = window.__shipmentAsRecMapModalEl;
          if (prevMap && prevMap !== freshMap && prevMap.parentNode) {
            prevMap.remove();
          }
          document.body.appendChild(freshMap);
          window.__shipmentAsRecMapModalEl = freshMap;
        }
      }

      adoptModalFromMain();

      function collectTargetOrderIds() {
        var tbody = document.querySelector('#shipment-dashboard-table tbody') || document.querySelector('.shipment-table tbody');
        if (!tbody) return [];
        var rows = tbody.querySelectorAll('tr.shipment-row[data-order-id]');
        var ids = [];
        rows.forEach(function (tr) {
          if (String(tr.getAttribute('data-as') || '0') !== '0') return;
          var id = parseInt(tr.getAttribute('data-order-id'), 10);
          if (id) ids.push(id);
        });
        return ids;
      }

      function escHtml(s) {
        return String(s == null ? '' : s)
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;');
      }

      function getMapModal() {
        return window.__shipmentAsRecMapModalEl || document.getElementById('scheduleMapModal');
      }

      function getModal() {
        return window.__shipmentAsRecModalEl || document.getElementById('shipmentAsRecommendModal');
      }

      function setStatus(msg) {
        var el = document.getElementById('shipment-as-rec-status');
        if (el) el.textContent = msg || '';
      }

      function showProgress(pct) {
        var wrap = document.getElementById('shipment-as-rec-progress');
        var bar = wrap && wrap.querySelector('.progress-bar');
        if (!wrap || !bar) return;
        if (pct == null) {
          wrap.classList.add('d-none');
          return;
        }
        wrap.classList.remove('d-none');
        bar.style.width = Math.min(100, Math.max(0, pct)) + '%';
      }

      function refreshShipmentFragment() {
        var shell = window.FOMS_ERP_SHELL;
        if (shell && typeof shell.navigateByShell === 'function') {
          return shell.navigateByShell(
            window.location.pathname + window.location.search + window.location.hash,
            { bypassCache: true }
          );
        }
        window.location.reload();
        return Promise.resolve();
      }

      /**
       * 추천 카드 본문에 서버 렌더 AS 타임라인(as_timeline_html)을 주입한다.
       *
       * AS 기록 SSOT 는 append-only shipment.as_log 이고 legacy as_content 는 그 뷰의
       * legacy 앵커로 이미 포함되므로, 본문은 타임라인 하나만 그린다(구 as_content_html
       * 병행 표시는 같은 내용을 두 번 내보내므로 제거됨).
       * 값은 서버 sanitize 를 통과한 HTML 이므로 innerHTML 주입이 허용된다.
       */
      function hydrateAsRecTimelines(payload, rootEl) {
        if (!rootEl) return;
        var targets = (payload && payload.targets) || [];
        targets.forEach(function (t) {
          (t.recommendations || []).forEach(function (r) {
            var key = String(t.order_id) + '-' + String(r.as_order_id);
            var el = rootEl.querySelector('[data-asrec-timeline="' + key + '"]');
            if (!el) return;
            el.innerHTML = r.as_timeline_html || '<div class="text-muted small">기록 없음</div>';
          });
        });
      }

      function renderAll(payload) {
        var groupsEl = document.getElementById('shipment-as-rec-groups');
        var emptyEl = document.getElementById('shipment-as-rec-empty');
        var linkedWrap = document.getElementById('shipment-as-rec-linked');
        var linkedBody = document.getElementById('shipment-as-rec-linked-body');
        if (!groupsEl) return;
        var targets = (payload && payload.targets) || [];
        if (!targets.length) {
          groupsEl.innerHTML = '';
          if (emptyEl) emptyEl.classList.remove('d-none');
          if (linkedWrap) linkedWrap.classList.add('d-none');
          return;
        }
        if (emptyEl) emptyEl.classList.add('d-none');
        var linkedHtml = '';
        targets.forEach(function (t) {
          (t.linked_as_schedules || []).forEach(function (L) {
            linkedHtml +=
              '<div class="d-flex flex-wrap align-items-center gap-2 border rounded px-2 py-1 mb-1">' +
              '<span>AS #' + escHtml(L.as_order_id) + ' ' + escHtml(L.customer_name) + '</span>' +
              '<span class="text-muted">' + escHtml(L.applied_date) + '</span>' +
              '<button type="button" class="btn btn-sm btn-outline-danger js-shipment-as-rec-cancel" ' +
              'data-shipment-order-id="' + escHtml(t.order_id) + '" data-as-order-id="' + escHtml(L.as_order_id) + '" ' +
              'data-as-info-id="' + escHtml(L.as_info_id != null ? L.as_info_id : '') + '">삭제</button>' +
              '</div>';
          });
        });
        if (linkedBody) linkedBody.innerHTML = linkedHtml || '<span class="text-muted">없음</span>';
        if (linkedWrap) linkedWrap.classList.toggle('d-none', !linkedHtml);

        var html = '';
        targets.forEach(function (t) {
          var recs = t.recommendations || [];
          var recCount = recs.length;
          var collapseId = 'asrec-m-' + String(t.order_id);
          html += '<div class="card mb-3 asrec-target-group border">';
          html += '<button type="button" class="card-header py-2 px-3 d-lg-none btn btn-light w-100 text-start border-0 rounded-0 d-flex justify-content-between align-items-center" data-bs-toggle="collapse" data-bs-target="#' + collapseId + '" aria-expanded="false">';
          html += '<span class="text-primary"><strong>출고 #' + escHtml(t.order_id) + '</strong> · ' + escHtml(t.customer_name) + ' · ' + escHtml(t.address) + ' · 추천 ' + recCount + '건</span>';
          html += '<span class="text-muted small">펼침</span>';
          html += '</button>';
          html += '<div class="card-header py-2 d-none d-lg-block border-bottom-0 bg-white">';
          html += '<span class="text-primary"><strong>출고 #' + escHtml(t.order_id) + '</strong> ';
          html += escHtml(t.customer_name) + ' <span class="small">' + escHtml(t.address) + '</span></span>';
          if (t.message) html += '<div class="small text-warning mt-1">' + escHtml(t.message) + '</div>';
          html += '</div>';
          html += '<div id="' + collapseId + '" class="collapse asrec-target-detail"><div class="card-body py-2 border-top">';
          if (t.message) {
            html += '<div class="d-lg-none small text-warning mb-2">' + escHtml(t.message) + '</div>';
          }
          html += '<div class="text-muted small d-lg-none mb-2">' + escHtml(t.address) + '</div>';
          if (!recs.length) {
            html += '<div class="text-muted small">추천 후보가 없거나 주소/경로 조건을 만족하지 않습니다.</div>';
          }
          recs.forEach(function (r) {
            var workersLabel = (r.will_apply_workers && r.will_apply_workers.length)
              ? escHtml(r.will_apply_workers.join(', '))
              : '시공자 공란으로 적용';
            var disabled = r.linked_from_shipment_order_id ? 'disabled' : '';
            var badge = '';
            if (r.linked_from_shipment_order_id) {
              badge = '<span class="badge bg-secondary ms-1">이미 추가됨</span>';
            }
            var targetLat = Number(t.lat);
            var targetLng = Number(t.lng);
            var recLat = Number(r.lat);
            var recLng = Number(r.lng);
            var canOpenMap = Number.isFinite(targetLat) && Number.isFinite(targetLng) && Number.isFinite(recLat) && Number.isFinite(recLng);
            var timelineKey = String(t.order_id) + '-' + String(r.as_order_id);
            html += '<div class="border rounded p-2 mb-2 small" data-as-order-id="' + escHtml(r.as_order_id) + '">';
            html += '<div class="row g-2 align-items-stretch">';
            html += '<div class="col-12 col-md-6 asrec-card-meta">';
            html += '<div class="fw-bold">AS #' + escHtml(r.as_order_id) + ' ' + escHtml(r.customer_name) + badge + '</div>';
            html += '<div class="text-muted">' + escHtml(r.address) + '</div>';
            html += '<div class="mt-2">현재 방문일: <span class="js-asrec-visit">' + escHtml(r.current_visit_date || '(없음)') + '</span></div>';
            html += '<div>' + escHtml(r.score_text || '') + '</div>';
            html += '<div class="mt-1">적용 시 시공자: ' + workersLabel + '</div>';
            html += '<div class="js-asrec-err text-danger mt-1"></div>';
            html += '<div class="d-flex flex-wrap align-items-center gap-2 mt-2">';
            html += '<button type="button" class="btn btn-sm btn-primary js-shipment-as-rec-apply" ' + disabled + ' ';
            html += 'data-shipment-order-id="' + escHtml(t.order_id) + '" data-as-order-id="' + escHtml(r.as_order_id) + '" ';
            html += 'data-as-info-id="' + escHtml(r.as_info_id != null ? r.as_info_id : '') + '" ';
            html += 'data-already-scheduled="' + (r.already_scheduled ? '1' : '0') + '">';
            html += (r.linked_from_shipment_order_id ? '다른 출고에 연결됨' : '추가') + '</button>';
            if (canOpenMap) {
              html += '<button type="button" class="btn btn-sm btn-outline-info js-shipment-as-rec-map" ';
              html += 'data-ref-lat="' + escHtml(targetLat) + '" data-ref-lng="' + escHtml(targetLng) + '" ';
              html += 'data-ref-address="' + escHtml(t.address) + '" data-ref-name="' + escHtml(t.customer_name) + '" ';
              html += 'data-lat="' + escHtml(recLat) + '" data-lng="' + escHtml(recLng) + '" ';
              html += 'data-address="' + escHtml(r.address) + '" data-name="' + escHtml(r.customer_name) + '" ';
              html += 'data-score-text="' + escHtml(r.score_text || '') + '"><i class="fas fa-map"></i> 지도</button>';
            }
            html += '</div>';
            html += '</div>';
            html += '<div class="col-12 col-md-6 asrec-card-content">';
            html += '<div class="border rounded bg-light h-100 p-2">';
            html += '<div class="asrec-timeline-slot" role="region" aria-label="AS 기록 타임라인" ';
            html += 'data-asrec-timeline="' + escHtml(timelineKey) + '"></div>';
            html += '</div></div>';
            html += '</div></div>';
          });
          html += '</div></div></div>';
        });
        groupsEl.innerHTML = html;
        hydrateAsRecTimelines(payload, groupsEl);
        if (payload && payload.warnings && payload.warnings.length) {
          setStatus('참고 알림 ' + payload.warnings.length + '건 (경로 계산 한도·화면 기준일 불일치 등)');
        }
      }

      function mergeTargets(acc, batch) {
        var tg = (batch && batch.targets) || [];
        tg.forEach(function (t) {
          acc.push(t);
        });
        return acc;
      }

      function loadRecommendations() {
        var modal = getModal();
        if (!modal || typeof bootstrap === 'undefined') return;
        var ids = collectTargetOrderIds();
        var inst = bootstrap.Modal.getOrCreateInstance(modal);
        inst.show();
        if (!ids.length) {
          setStatus('');
          showProgress(null);
          var emptyA = document.getElementById('shipment-as-rec-empty');
          var groupsA = document.getElementById('shipment-as-rec-groups');
          var linkedA = document.getElementById('shipment-as-rec-linked');
          if (emptyA) emptyA.classList.remove('d-none');
          if (groupsA) groupsA.innerHTML = '';
          if (linkedA) linkedA.classList.add('d-none');
          return;
        }
        var emptyB = document.getElementById('shipment-as-rec-empty');
        if (emptyB) emptyB.classList.add('d-none');
        setStatus('추천을 불러오는 중…');
        showProgress(5);
        var chunks = [];
        for (var i = 0; i < ids.length; i += CHUNK) {
          chunks.push(ids.slice(i, i + CHUNK));
        }
        var merged = { targets: [], partial: false, warnings: [] };
        var step = 0;
        function runChunk() {
          if (step >= chunks.length) {
            showProgress(100);
            setTimeout(function () { showProgress(null); }, 400);
            setStatus(chunks.length > 1 ? '조회 완료 (' + chunks.length + '회 분할 요청)' : '');
            renderAll(merged);
            return;
          }
          var part = chunks[step];
          fetch('/api/erp/shipment/as-recommendations', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
            body: JSON.stringify({
              order_ids: part,
              selected_date: (function () {
                var sd = window.__shipmentAsRecPageDate;
                if (sd == null || sd === '') return null;
                var s = String(sd).trim();
                return s || null;
              })(),
            }),
          })
            .then(function (r) {
              return r.json().then(function (data) {
                if (!r.ok || !data || !data.success) {
                  throw new Error((data && data.message) || 'HTTP ' + r.status);
                }
                return data;
              });
            })
            .then(function (data) {
              mergeTargets(merged.targets, data);
              if (data.partial) merged.partial = true;
              if (data.warnings && data.warnings.length) {
                merged.warnings = merged.warnings.concat(data.warnings);
              }
              step += 1;
              showProgress((step / chunks.length) * 100);
              runChunk();
            })
            .catch(function (err) {
              showProgress(null);
              setStatus('오류: ' + (err && err.message ? err.message : String(err)));
            });
        }
        runChunk();
      }

      function postApply(shipmentOrderId, asOrderId, asInfoId, force) {
        return fetch('/api/erp/shipment/as-recommendations/apply', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({
            shipment_order_id: shipmentOrderId,
            as_order_id: asOrderId,
            as_info_id: asInfoId === '' || asInfoId == null ? null : parseInt(asInfoId, 10),
            force: !!force,
          }),
        }).then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        });
      }

      function postCancel(shipmentOrderId, asOrderId, asInfoId) {
        return fetch('/api/erp/shipment/as-recommendations/cancel', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
          body: JSON.stringify({
            shipment_order_id: shipmentOrderId,
            as_order_id: asOrderId,
            as_info_id: asInfoId === '' || asInfoId == null ? null : parseInt(asInfoId, 10),
          }),
        }).then(function (r) {
          return r.json().then(function (data) {
            return { ok: r.ok, status: r.status, data: data };
          });
        });
      }

      if (!window.__shipmentAsRecDocListenersBound) {
        window.__shipmentAsRecDocListenersBound = true;

        document.addEventListener('click', function (ev) {
        var openBtn = ev.target.closest && ev.target.closest('#shipment-as-recommend-btn, [data-shipment-as-recommend-open]');
        if (openBtn) {
          ev.preventDefault();
          adoptModalFromMain();
          loadRecommendations();
          return;
        }

        var cancelBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-cancel');
        if (cancelBtn) {
          ev.preventDefault();
          if (!window.confirm('이 AS 일정 연결을 삭제할까요?')) return;
          var csid = parseInt(cancelBtn.getAttribute('data-shipment-order-id'), 10);
          var caid = parseInt(cancelBtn.getAttribute('data-as-order-id'), 10);
          var cinfo = cancelBtn.getAttribute('data-as-info-id');
          postCancel(csid, caid, cinfo).then(function (res) {
            if (res.ok && res.data && res.data.success) {
              window.__shipmentAsRecNeedsReload = true;
              refreshShipmentFragment();
              return;
            }
            window.alert((res.data && res.data.message) || '삭제 실패');
          });
          return;
        }

        var modalRoot = ev.target.closest && ev.target.closest('#shipmentAsRecommendModal');
        if (!modalRoot) return;

        var mapBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-map');
        if (mapBtn) {
          ev.preventDefault();
          // 지도 렌더·카카오 SDK 주입·경로 조회·정리는 공용 모듈
          // static/js/common/foms-schedule-map.js 소관(AS 대시보드와 공유).
          // modalEl 은 프래그먼트 스왑마다 adoptModalFromMain 이 body 로 재부모화한 노드다.
          if (!window.FOMS_SCHEDULE_MAP) return;
          adoptModalFromMain();
          var mapModalEl = getMapModal();
          if (!mapModalEl) return;
          window.FOMS_SCHEDULE_MAP.open({
            modalEl: mapModalEl,
            ref: {
              lat: Number(mapBtn.getAttribute('data-ref-lat')),
              lng: Number(mapBtn.getAttribute('data-ref-lng')),
              address: mapBtn.getAttribute('data-ref-address') || ''
            },
            target: {
              lat: Number(mapBtn.getAttribute('data-lat')),
              lng: Number(mapBtn.getAttribute('data-lng')),
              address: mapBtn.getAttribute('data-address') || '',
              name: mapBtn.getAttribute('data-name') || ''
            },
            scoreText: mapBtn.getAttribute('data-score-text') || ''
          });
          return;
        }

        var applyBtn = ev.target.closest && ev.target.closest('.js-shipment-as-rec-apply');
        if (applyBtn && !applyBtn.disabled) {
          ev.preventDefault();
          var row = applyBtn.closest('[data-as-order-id]');
          var errEl = row ? row.querySelector('.js-asrec-err') : null;
          if (errEl) errEl.textContent = '';
          var sid = parseInt(applyBtn.getAttribute('data-shipment-order-id'), 10);
          var aid = parseInt(applyBtn.getAttribute('data-as-order-id'), 10);
          var infoRaw = applyBtn.getAttribute('data-as-info-id');
          var force = false;
          if (applyBtn.getAttribute('data-already-scheduled') === '1') {
            if (!window.confirm('이미 방문일이 있는 AS입니다. 출고 일정으로 덮어쓸까요?')) {
              return;
            }
            force = true;
          }
          postApply(sid, aid, infoRaw, force).then(function (res) {
            if (res.ok && res.data && res.data.success) {
              applyBtn.disabled = true;
              applyBtn.textContent = '추가 완료';
              window.__shipmentAsRecNeedsReload = true;
              refreshShipmentFragment();
              return;
            }
            var msg = (res.data && res.data.message) || '';
            if (res.status === 409 && msg.indexOf('force') >= 0) {
              if (window.confirm(msg + '\n\n강제로 덮어쓸까요?')) {
                return postApply(sid, aid, infoRaw, true).then(function (res2) {
                  if (res2.ok && res2.data && res2.data.success) {
                    applyBtn.disabled = true;
                    applyBtn.textContent = '추가 완료';
                    window.__shipmentAsRecNeedsReload = true;
                    refreshShipmentFragment();
                  } else if (errEl) {
                    errEl.textContent = (res2.data && res2.data.message) || '적용 실패';
                  }
                });
              }
              return;
            }
            if (errEl) errEl.textContent = msg || '적용 실패';
          });
          return;
        }
      }, true);

        document.addEventListener('foms:main-content-swapped', function () {
          if (!document.querySelector('#shipment-dashboard-table')) return;
          adoptModalFromMain();
          scheduleShipmentAsRecPrewarm();
          var el = window.__shipmentAsRecModalEl;
          if (el && el.classList.contains('show') && window.__shipmentAsRecNeedsReload) {
            window.__shipmentAsRecNeedsReload = false;
            loadRecommendations();
          }
        });
      }

      function scheduleShipmentAsRecPrewarm() {
        var ids = collectTargetOrderIds();
        if (!ids.length) return;
        var key = 'shipment-asrec-prewarm:' + window.location.pathname + window.location.search + ':' + ids.join(',');
        try {
          if (sessionStorage.getItem(key) === '1') return;
        } catch (e) { /* ignore */ }
        function run() {
          var chunks = [];
          for (var i = 0; i < ids.length; i += CHUNK) {
            chunks.push(ids.slice(i, i + CHUNK));
          }
          var idx = 0;
          function next() {
            if (idx >= chunks.length) {
              try {
                sessionStorage.setItem(key, '1');
              } catch (e) { /* ignore */ }
              return;
            }
            var part = chunks[idx];
            fetch('/api/erp/shipment/as-recommendations/prewarm', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest' },
              body: JSON.stringify({
                order_ids: part,
                selected_date: (function () {
                  var sd = window.__shipmentAsRecPageDate;
                  if (sd == null || sd === '') return null;
                  var s = String(sd).trim();
                  return s || null;
                })(),
              }),
            }).finally(function () {
              idx += 1;
              next();
            });
          }
          next();
        }
        if (typeof window.requestIdleCallback === 'function') {
          window.requestIdleCallback(function () { run(); }, { timeout: 8000 });
        } else {
          window.setTimeout(run, 1600);
        }
      }

      scheduleShipmentAsRecPrewarm();
    })();
    }

    document.querySelectorAll('.js-shipment-export-trigger').forEach(function (btn) {
      btn.addEventListener('click', function () {
        var exportBtn = document.getElementById('btn-export-image');
        if (exportBtn) {
          exportBtn.click();
        }
      });
    });

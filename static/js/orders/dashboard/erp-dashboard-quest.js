function renderBadges(alerts) {
          const a = alerts || {};
          const out = [];
          if (a.urgent) out.push('<span class="badge bg-danger me-1">긴급</span>');
          if (a.drawing_overdue) out.push('<span class="badge bg-danger me-1">도면48h</span>');
          if (a.measurement_d4) out.push('<span class="badge bg-warning text-dark me-1">실측D-4</span>');
          if (a.construction_d3) out.push('<span class="badge bg-warning text-dark me-1">시공D-3</span>');
          if (a.production_d2) out.push('<span class="badge bg-warning text-dark me-1">생산D-2</span>');
          return out.join('') || '<span class="text-muted small">경보 없음</span>';
        }

        // 승인 버튼 공통 전처리: 서버가 준 확인 문구(data-confirm)가 있으면 묻고, 연타를 막기 위해
        // 버튼을 잠근다. 고객 컨펌 승인은 이제 단계 전이(→생산)라 실수 클릭이 되돌리기 어렵다.
        function beginQuestApprove(btn) {
          if (btn && btn.disabled) return false;
          const confirmText = btn && btn.dataset ? btn.dataset.confirm : '';
          if (confirmText && !window.confirm(confirmText)) return false;
          if (btn) btn.disabled = true;
          return true;
        }
        function failQuestApprove(btn, data) {
          if (btn) btn.disabled = false;
          const detail = data && data.code ? ' (' + data.code + ')' : '';
          alert('승인 실패: ' + ((data && (data.message || data.error)) || '알 수 없는 오류') + detail);
        }

        async function approveQuestTeam(orderId, team, btn) {
          if (!beginQuestApprove(btn)) return;
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ team: team })
            });
            const data = await res.json();

            if (!data.success) {
              failQuestApprove(btn, data);
              return;
            }

            if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
              window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
            }

            let _toastMsg;
            if (data.retransitioned && data.next_stage) {
              // 완료 quest 재전이(강제 단계 변경 뒤 막다른 길) — 담당자 함수와 같은 우선순위.
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              _toastMsg = '↩ ' + nextStageLabel + ' 단계로 넘겼습니다';
            } else if (data.auto_transitioned && data.next_stage) {
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              _toastMsg = '✅ 승인 완료 — ' + nextStageLabel + ' 단계로 이동';
            } else if (data.all_approved) {
              _toastMsg = '✅ 모든 팀 승인 완료';
            } else {
              const missingTeams = data.missing_teams.map(t => label(TEAM_LABELS, t, t)).join(', ');
              _toastMsg = '승인 완료 — 남은 팀: ' + missingTeams;
            }
            if (window.fomsFlashToast) { window.fomsFlashToast(_toastMsg); } else { alert(_toastMsg); }

            await loadQuestDetail(orderId);
            window.location.reload();
          } catch (err) {
            if (btn) btn.disabled = false;
            console.error('승인 실패:', err);
            alert('승인 중 오류가 발생했습니다.');
          }
        }

        async function approveQuestAssignee(orderId, btn) {
          if (!beginQuestApprove(btn)) return;
          try {
            const res = await fetch(`/api/orders/${orderId}/quest/approve`, {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({})
            });
            const data = await res.json();

            if (!data.success) {
              failQuestApprove(btn, data);
              return;
            }

            if (window.FOMS_ERP_SHELL && typeof window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache === 'function') {
              window.FOMS_ERP_SHELL.invalidatePrimaryNavFragmentCache();
            }

            let _toastMsg;
            if (data.retransitioned && data.next_stage) {
              // 완료 quest 재전이(강제 단계 변경 뒤 막다른 길) — 승인 기록은 그대로, 단계만 넘어갔다.
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              _toastMsg = '↩ ' + nextStageLabel + ' 단계로 넘겼습니다';
            } else if (data.auto_transitioned && data.next_stage) {
              const nextStageLabel = label(STAGE_LABELS, data.next_stage, data.next_stage);
              _toastMsg = '✅ 담당자 승인 완료 — ' + nextStageLabel + ' 단계로 이동';
            } else if (data.all_approved) {
              _toastMsg = '✅ 담당자 승인 완료';
            }
            if (_toastMsg) {
              if (window.fomsFlashToast) { window.fomsFlashToast(_toastMsg); } else { alert(_toastMsg); }
            }

            window.location.reload();
          } catch (err) {
            if (btn) btn.disabled = false;
            console.error('승인 실패:', err);
            alert('승인 중 오류가 발생했습니다.');
          }
        }

        async function loadQuestDetail(orderId) {
          try {
            const res = await fetch(`/api/orders/${orderId}/quest`);
            const data = await res.json();
            if (data.error) {
              console.error('Quest 로드 실패:', data.error);
              return;
            }
            const questContainer = document.querySelector(`#quest-collapse-${orderId} #quest-approvals-${orderId}`);
            if (questContainer) {
              const quest = data.quest || {};
              const requiredTeams = quest.required_approvals || [];
              const teamApprovalsRaw = quest.team_approvals || {};

              let html = '';
              for (const team of requiredTeams) {
                const approvalData = teamApprovalsRaw[team];
                let approved = false;
                if (typeof approvalData === 'object' && approvalData !== null) {
                  approved = approvalData.approved === true;
                } else {
                  approved = Boolean(approvalData);
                }
                const teamLabel = label(TEAM_LABELS, team, team);
                html += `<div class="mb-2">`;
                html += `<span class="fw-semibold" style="font-size: 1rem;">${escapeHtml(teamLabel)}</span>`;
                if (approved) {
                  html += `<span class="badge bg-success ms-2" style="font-size: 1rem; padding: 0.4em 0.7em;">승인완료</span>`;
                } else {
                  html += `<button class="btn btn-primary fw-semibold ms-2" onclick="approveQuestTeam(${orderId}, '${escapeHtml(team)}')" style="font-size: 1rem; padding: 0.4rem 0.75rem;">승인</button>`;
                }
                html += `</div>`;
              }
              questContainer.innerHTML = html;
            }
          } catch (err) {
            console.error('Quest 상세 로드 실패:', err);
          }
        }

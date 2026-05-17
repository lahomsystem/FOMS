/**
 * FOMS Brain PG-B8 — Drawing Review Workspace.
 *
 * Two-panel layout:
 *   Left:  Original drawing image (or placeholder) + image overlay annotations
 *   Right: ExtractionTablePanel (fields, parts, approve/reject)
 *
 * Receives extraction payload via postMessage (FOMS_REVIEW_EXTRACTION)
 * from the outer wdplanner_v2.html drawing panel.
 */

import { useEffect, useState } from 'react'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import { ExtractionTablePanel } from './ExtractionTablePanel'

const SAME_ORIGIN = window.location.origin

type ExtractionPayload = {
  extraction: Record<string, unknown>
  filename?: string
  metrics?: { latency_ms?: number; cost_usd?: number; model?: string }
  fixtureId?: string
  /** B4: schema v2 graph from layout_graph_mapper, if already built by backend intake pipeline. */
  design_graph_candidate?: Record<string, unknown>
  /** B4: blocking reasons that prevent approval (empty = can approve). */
  blocking_reasons?: string[]
  /** B4: mapping report from layout_graph_mapper. */
  mapping_report?: Record<string, unknown>
}

interface DrawingReviewWorkspaceProps {
  onClose?: () => void
}

export function DrawingReviewWorkspace({ onClose }: DrawingReviewWorkspaceProps) {
  const [payload, setPayload] = useState<ExtractionPayload | null>(null)
  const [status, setStatus] = useState<'idle' | 'approved' | 'rejected'>('idle')

  // Listen for extraction data from outer page
  useEffect(() => {
    const handler = (e: MessageEvent) => {
      if (e.origin !== SAME_ORIGIN) return
      if (e.data?.type === 'FOMS_REVIEW_EXTRACTION' && e.data.payload) {
        setPayload(e.data.payload as ExtractionPayload)
        setStatus('idle')
      }
    }
    window.addEventListener('message', handler)
    return () => window.removeEventListener('message', handler)
  }, [])

  function handleApprove(corrected: Record<string, unknown>) {
    setStatus('approved')
    // Send approval back to outer page
    try {
      window.parent.postMessage({
        type: 'FOMS_EXTRACTION_APPROVED',
        corrected,
        fixtureId: payload?.fixtureId,
      }, SAME_ORIGIN)
    } catch (err) {
      console.warn('[postMessage] failed to send extraction approval:', err)
    }
  }

  function handleReject() {
    setStatus('rejected')
    try {
      window.parent.postMessage({ type: 'FOMS_EXTRACTION_REJECTED' }, SAME_ORIGIN)
    } catch (err) {
      console.warn('[postMessage] failed to send extraction rejection:', err)
    }
  }

  function handleLoad3D() {
    if (!payload?.extraction) return
    const ext = payload.extraction as Record<string, unknown>
    window.dispatchEvent(new CustomEvent('FOMS_LOAD_CANDIDATE_INTERNAL', {
      detail: {
        furniture_type: ext.furniture_type ?? 'wardrobe',
        factory_params: ext.extracted_params ?? {},
        // B4: pass schema v2 graph so loadCandidateGraph uses graph-first path
        design_graph: payload.design_graph_candidate ?? null,
      },
    }))
    onClose?.()
  }

  if (!payload) {
    return (
      <div
        style={{
          width: '100%',
          height: '100%',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 16,
          background: COLORS.canvasBg,
          fontFamily: TYPOGRAPHY.fontFamily,
        }}
      >
        <div style={{ fontSize: 48, opacity: 0.3 }}>📐</div>
        <p style={{ color: COLORS.textMuted, fontSize: TYPOGRAPHY.sizeMD, textAlign: 'center' }}>
          도면 등록 탭에서 도면을 업로드하고<br />
          <strong style={{ color: COLORS.accent }}>검수</strong> 버튼을 누르면 여기에 표시됩니다.
        </p>
      </div>
    )
  }

  const ext = payload.extraction as Record<string, unknown>
  const ss = (ext.site_size ?? {}) as Record<string, number | null>

  return (
    <div style={{ width: '100%', height: '100%', display: 'flex', overflow: 'hidden' }}>
      {/* Left: Drawing image / placeholder */}
      <div
        style={{
          flex: 1,
          borderRight: `1px solid ${COLORS.panelBorder}`,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          background: COLORS.canvasBg,
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '8px 12px',
            borderBottom: `1px solid ${COLORS.panelBorder}`,
            background: COLORS.surfaceWhite,
            fontSize: TYPOGRAPHY.sizeMD,
            fontWeight: TYPOGRAPHY.weightSemibold,
            color: COLORS.textPrimary,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <span>📄 {payload.filename ?? '도면'}</span>
          {payload.metrics && (
            <span style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted }}>
              ⏱ {payload.metrics.latency_ms}ms  💰 ${payload.metrics.cost_usd?.toFixed(5)}  🤖 {payload.metrics.model}
            </span>
          )}
        </div>

        {/* Drawing image or placeholder with dimension overlay */}
        <div
          style={{
            flex: 1,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            position: 'relative' as const,
            overflow: 'hidden',
            padding: 16,
          }}
        >
          {/* Placeholder with dimension annotations */}
          <div
            style={{
              width: '85%',
              maxWidth: 480,
              aspectRatio: '4/3',
              background: '#fff',
              border: `2px solid ${COLORS.panelBorder}`,
              borderRadius: 8,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              position: 'relative' as const,
              boxShadow: '0 4px 16px rgba(0,0,0,0.06)',
            }}
          >
            <div style={{ fontSize: 40, opacity: 0.2 }}>📐</div>
            <p style={{ color: COLORS.textMuted, fontSize: TYPOGRAPHY.sizeSM, margin: '8px 0' }}>
              {payload.filename ?? '도면'}
            </p>

            {/* Dimension annotation overlays */}
            {ss.width_mm && (
              <div
                style={{
                  position: 'absolute' as const,
                  bottom: 8,
                  left: '50%',
                  transform: 'translateX(-50%)',
                  background: 'rgba(229,62,62,0.15)',
                  border: '1px solid #e53e3e',
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: TYPOGRAPHY.sizeXS,
                  color: '#e53e3e',
                  fontFamily: 'monospace',
                  fontWeight: TYPOGRAPHY.weightBold,
                }}
              >
                W {ss.width_mm}mm
              </div>
            )}
            {ss.height_mm && (
              <div
                style={{
                  position: 'absolute' as const,
                  right: 8,
                  top: '50%',
                  transform: 'translateY(-50%) rotate(90deg)',
                  background: 'rgba(49,130,206,0.15)',
                  border: '1px solid #3182ce',
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: TYPOGRAPHY.sizeXS,
                  color: '#3182ce',
                  fontFamily: 'monospace',
                  fontWeight: TYPOGRAPHY.weightBold,
                }}
              >
                H {ss.height_mm}mm
              </div>
            )}
            {ss.depth_mm && (
              <div
                style={{
                  position: 'absolute' as const,
                  top: 8,
                  right: 8,
                  background: 'rgba(56,161,105,0.15)',
                  border: '1px solid #38a169',
                  borderRadius: 4,
                  padding: '2px 8px',
                  fontSize: TYPOGRAPHY.sizeXS,
                  color: '#38a169',
                  fontFamily: 'monospace',
                  fontWeight: TYPOGRAPHY.weightBold,
                }}
              >
                D {ss.depth_mm}mm
              </div>
            )}

            {/* Unresolved badge */}
            {(ext.unresolved_fields as string[])?.length > 0 && (
              <div
                style={{
                  position: 'absolute' as const,
                  top: 8,
                  left: 8,
                  background: '#fffbeb',
                  border: '1px solid #fbbf24',
                  borderRadius: 4,
                  padding: '2px 7px',
                  fontSize: TYPOGRAPHY.sizeXS,
                  color: '#d97706',
                  fontWeight: TYPOGRAPHY.weightBold,
                }}
              >
                ⚠ {(ext.unresolved_fields as string[]).length}개 미확인
              </div>
            )}
          </div>
        </div>

        {/* Status bar */}
        {/* B4: Blocking reasons panel — shown when approval is blocked */}
        {(payload.blocking_reasons ?? []).length > 0 && (
          <div
            style={{
              padding: '8px 12px',
              background: '#fffbeb',
              borderTop: '1px solid #fbbf24',
              fontSize: TYPOGRAPHY.sizeXS,
              color: '#92400e',
              flexShrink: 0,
            }}
          >
            <strong>승인 차단 사유:</strong>
            <ul style={{ margin: '4px 0 0 16px', padding: 0 }}>
              {(payload.blocking_reasons ?? []).map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          </div>
        )}
        {status !== 'idle' && (
          <div
            style={{
              padding: '8px 16px',
              background: status === 'approved' ? '#f0fff4' : '#fff5f5',
              borderTop: `1px solid ${status === 'approved' ? '#9ae6b4' : '#fed7d7'}`,
              fontSize: TYPOGRAPHY.sizeSM,
              fontWeight: TYPOGRAPHY.weightSemibold,
              color: status === 'approved' ? COLORS.valid : COLORS.invalid,
              flexShrink: 0,
            }}
          >
            {status === 'approved' ? '✅ 승인 완료 — 학습 메모리에 저장되었습니다.' : '✗ 반려 처리되었습니다.'}
          </div>
        )}
      </div>

      {/* Right: Extraction table */}
      <div style={{ width: 300, flexShrink: 0, overflow: 'hidden' }}>
        <ExtractionTablePanel
          extraction={ext as Parameters<typeof ExtractionTablePanel>[0]['extraction']}
          onApprove={status === 'idle' ? handleApprove : undefined}
          onReject={status === 'idle' ? handleReject : undefined}
          onLoad3D={handleLoad3D}
        />
      </div>
    </div>
  )
}

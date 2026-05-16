/**
 * FOMS Brain Phase C5 — Freehand Sketch Canvas
 *
 * 2D 평면 그리기 도구:
 *   - 뷰 모드: front(정면) / top(상면) / side(측면)
 *   - 도구: 사각형(rect) / 폴리곤(polygon) / 삭제(eraser)
 *   - 완성된 스케치 → 깊이 입력 → 블록 저장 (POST /api/designer/blocks/)
 *
 * 계약:
 *   - Canvas 좌표는 1px = 1mm (pixelsPerMm=1).
 *   - 폴리곤 도구: 더블클릭으로 닫기.
 *   - 저장된 블록은 항상 draft 상태 (자동 승인 없음).
 *   - empty sketch 저장 불가 (validateSketch 통과 후에만 저장 버튼 활성화).
 */

import { useRef, useState, useCallback, useEffect } from 'react'
import {
  validateSketch,
  sketchToExtrusionSpec,
  buildSaveBlockPayload,
  type SketchPoint,
  type PlaneView,
} from '../domain/sketch_to_block'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

type DrawTool = 'rect' | 'polygon' | 'eraser'
type BlockCategory = 'panel' | 'module' | 'assembly' | 'hardware' | 'other'

interface DrawnShape {
  id: string
  points: SketchPoint[]
  tool: DrawTool
}

interface SketchCanvasProps {
  onClose?: () => void
}

// ──────────────────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────────────────

const CANVAS_W = 480
const CANVAS_H = 400
const PIXELS_PER_MM = 1

const PLANE_VIEWS: { key: PlaneView; label: string }[] = [
  { key: 'front', label: '정면' },
  { key: 'top', label: '상면' },
  { key: 'side', label: '측면' },
]

const TOOLS: { key: DrawTool; label: string; title: string }[] = [
  { key: 'rect', label: '□', title: '사각형 그리기' },
  { key: 'polygon', label: '⬠', title: '폴리곤 (더블클릭으로 닫기)' },
  { key: 'eraser', label: '✕', title: '마지막 도형 삭제' },
]

const CATEGORIES: { key: BlockCategory; label: string }[] = [
  { key: 'panel', label: '판넬' },
  { key: 'module', label: '모듈' },
  { key: 'assembly', label: '조립체' },
  { key: 'hardware', label: '하드웨어' },
  { key: 'other', label: '기타' },
]

// ──────────────────────────────────────────────────────────
// SketchCanvas Component
// ──────────────────────────────────────────────────────────

export function SketchCanvas({ onClose }: SketchCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  const [planeView, setPlaneView] = useState<PlaneView>('front')
  const [tool, setTool] = useState<DrawTool>('rect')
  const [shapes, setShapes] = useState<DrawnShape[]>([])
  const [polyInProgress, setPolyInProgress] = useState<SketchPoint[]>([])
  const [rectStart, setRectStart] = useState<SketchPoint | null>(null)
  const [mousePos, setMousePos] = useState<SketchPoint>({ x: 0, y: 0 })

  // Save dialog state
  const [showSaveDialog, setShowSaveDialog] = useState(false)
  const [labelKo, setLabelKo] = useState('')
  const [category, setCategory] = useState<BlockCategory>('panel')
  const [depthMm, setDepthMm] = useState(600)
  const [saving, setSaving] = useState(false)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [saveSuccess, setSaveSuccess] = useState(false)

  // ── Canvas rendering ─────────────────────────────────────

  const redraw = useCallback(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.clearRect(0, 0, CANVAS_W, CANVAS_H)

    // Grid
    ctx.strokeStyle = '#e2e8f0'
    ctx.lineWidth = 0.5
    for (let x = 0; x < CANVAS_W; x += 50) {
      ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, CANVAS_H); ctx.stroke()
    }
    for (let y = 0; y < CANVAS_H; y += 50) {
      ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(CANVAS_W, y); ctx.stroke()
    }

    // Completed shapes
    for (const shape of shapes) {
      drawShape(ctx, shape.points, '#2563eb', '#bfdbfe')
    }

    // Polygon in progress
    if (polyInProgress.length > 0) {
      drawShapeInProgress(ctx, polyInProgress, mousePos, '#16a34a')
    }

    // Rect in progress — 4 points already complete, no cursor arrow needed
    if (tool === 'rect' && rectStart) {
      const pts = rectFromTwoPoints(rectStart, mousePos)
      drawShape(ctx, pts, '#dc2626', 'rgba(220,38,38,0.08)')
    }
  }, [shapes, polyInProgress, mousePos, tool, rectStart])

  useEffect(() => {
    redraw()
  }, [redraw])

  // ── Event handlers ───────────────────────────────────────

  function getCanvasPoint(e: React.MouseEvent<HTMLCanvasElement>): SketchPoint {
    const rect = e.currentTarget.getBoundingClientRect()
    return {
      x: Math.round(e.clientX - rect.left),
      y: Math.round(e.clientY - rect.top),
    }
  }

  function handleMouseMove(e: React.MouseEvent<HTMLCanvasElement>) {
    setMousePos(getCanvasPoint(e))
  }

  function handleCanvasClick(e: React.MouseEvent<HTMLCanvasElement>) {
    const pt = getCanvasPoint(e)

    if (tool === 'polygon') {
      setPolyInProgress((prev) => [...prev, pt])
    }

    if (tool === 'rect' && !rectStart) {
      setRectStart(pt)
    } else if (tool === 'rect' && rectStart) {
      const pts = rectFromTwoPoints(rectStart, pt)
      addShape(pts, 'rect')
      setRectStart(null)
    }
  }

  function handleDoubleClick(e: React.MouseEvent<HTMLCanvasElement>) {
    if (tool === 'polygon' && polyInProgress.length >= 3) {
      addShape(polyInProgress, 'polygon')
      setPolyInProgress([])
    }
  }

  function handleErase() {
    setShapes((prev) => prev.slice(0, -1))
  }

  // ── Shape helpers ────────────────────────────────────────

  function addShape(points: SketchPoint[], drawTool: DrawTool) {
    const validation = validateSketch(points, PIXELS_PER_MM)
    if (!validation.valid) return // silently skip invalid shapes
    setShapes((prev) => [
      ...prev,
      { id: `shape-${Date.now()}`, points, tool: drawTool },
    ])
  }

  // ── Save flow ────────────────────────────────────────────

  function allPoints(): SketchPoint[] {
    return shapes.flatMap((s) => s.points)
  }

  const canSave = shapes.length > 0 && validateSketch(allPoints(), PIXELS_PER_MM).valid

  async function handleSave() {
    if (!canSave || !labelKo.trim()) return
    setSaving(true)
    setSaveError(null)

    const points = allPoints()
    const spec = sketchToExtrusionSpec(points, depthMm, planeView, PIXELS_PER_MM)
    const payload = buildSaveBlockPayload(labelKo.trim(), category, spec)

    try {
      const res = await fetch('/api/designer/blocks/', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      })
      const data = await res.json()
      if (!data.success) {
        setSaveError(data.error ?? '저장에 실패했습니다.')
        return
      }
      setSaveSuccess(true)
      setShapes([])
      setLabelKo('')
      setTimeout(() => {
        setSaveSuccess(false)
        setShowSaveDialog(false)
      }, 1500)
    } catch {
      setSaveError('네트워크 오류가 발생했습니다.')
    } finally {
      setSaving(false)
    }
  }

  function handleClear() {
    setShapes([])
    setPolyInProgress([])
    setRectStart(null)
  }

  // ── Render ───────────────────────────────────────────────

  return (
    <div style={st.container}>
      {/* Header */}
      <div style={st.header}>
        <span style={st.title}>스케치 도구</span>
        {onClose && (
          <button onClick={onClose} style={st.iconBtn} title="닫기">✕</button>
        )}
      </div>

      {/* View + Tool bar */}
      <div style={st.toolbar}>
        <span style={st.toolbarLabel}>뷰:</span>
        {PLANE_VIEWS.map((v) => (
          <button
            key={v.key}
            onClick={() => setPlaneView(v.key)}
            style={{ ...st.toolBtn, ...(planeView === v.key ? st.toolBtnActive : {}) }}
          >
            {v.label}
          </button>
        ))}
        <span style={{ ...st.toolbarLabel, marginLeft: 12 }}>도구:</span>
        {TOOLS.filter((t) => t.key !== 'eraser').map((t) => (
          <button
            key={t.key}
            onClick={() => {
              setTool(t.key)
              setPolyInProgress([])
              setRectStart(null)
            }}
            style={{ ...st.toolBtn, ...(tool === t.key ? st.toolBtnActive : {}) }}
            title={t.title}
          >
            {t.label}
          </button>
        ))}
        <button
          onClick={handleErase}
          style={st.toolBtn}
          title="마지막 도형 삭제"
          disabled={shapes.length === 0}
        >
          ↩
        </button>
        <button onClick={handleClear} style={{ ...st.toolBtn, marginLeft: 4, color: '#dc2626' }}>
          전체삭제
        </button>
      </div>

      {/* Canvas */}
      <div style={st.canvasWrap}>
        <canvas
          ref={canvasRef}
          width={CANVAS_W}
          height={CANVAS_H}
          style={st.canvas}
          onClick={handleCanvasClick}
          onDoubleClick={handleDoubleClick}
          onMouseMove={handleMouseMove}
        />
        <div style={st.canvasHint}>
          {tool === 'rect'
            ? (rectStart ? '두 번째 점을 클릭하세요' : '첫 번째 점을 클릭하세요')
            : tool === 'polygon'
              ? '점을 클릭하고 더블클릭으로 닫기'
              : ''}
        </div>
      </div>

      {/* Footer */}
      <div style={st.footer}>
        <span style={st.footerInfo}>
          뷰: <strong>{planeView}</strong> | 도형: {shapes.length}개
          {canSave && ` | 유효`}
        </span>
        <button
          onClick={() => setShowSaveDialog(true)}
          disabled={!canSave}
          style={{ ...st.saveBtn, ...(!canSave ? st.saveBtnDisabled : {}) }}
        >
          블록으로 저장
        </button>
      </div>

      {/* Save dialog */}
      {showSaveDialog && (
        <div style={st.dialogOverlay}>
          <div style={st.dialog}>
            <div style={st.dialogTitle}>블록 저장</div>

            {saveSuccess ? (
              <div style={st.successMsg}>저장 완료! (draft 상태 — 승인 후 사용 가능)</div>
            ) : (
              <>
                <div style={st.fieldRow}>
                  <label style={st.fieldLabel}>블록 이름</label>
                  <input
                    type="text"
                    value={labelKo}
                    onChange={(e) => setLabelKo(e.target.value)}
                    placeholder="예: 좌측 상단 선반"
                    style={st.textInput}
                    autoFocus
                  />
                </div>
                <div style={st.fieldRow}>
                  <label style={st.fieldLabel}>카테고리</label>
                  <select
                    value={category}
                    onChange={(e) => setCategory(e.target.value as BlockCategory)}
                    style={st.textInput}
                  >
                    {CATEGORIES.map((c) => (
                      <option key={c.key} value={c.key}>{c.label}</option>
                    ))}
                  </select>
                </div>
                <div style={st.fieldRow}>
                  <label style={st.fieldLabel}>깊이 (mm)</label>
                  <input
                    type="number"
                    value={depthMm}
                    min={10}
                    max={3000}
                    onChange={(e) => setDepthMm(Number(e.target.value))}
                    style={{ ...st.textInput, width: 80 }}
                  />
                </div>

                {saveError && <div style={st.errorMsg}>{saveError}</div>}

                <div style={st.dialogActions}>
                  <button
                    onClick={() => { setShowSaveDialog(false); setSaveError(null) }}
                    style={st.cancelBtn}
                  >
                    취소
                  </button>
                  <button
                    onClick={handleSave}
                    disabled={saving || !labelKo.trim()}
                    style={{
                      ...st.confirmBtn,
                      ...(saving || !labelKo.trim() ? st.confirmBtnDisabled : {}),
                    }}
                  >
                    {saving ? '저장 중...' : '저장'}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ──────────────────────────────────────────────────────────
// Drawing helpers
// ──────────────────────────────────────────────────────────

function drawShape(
  ctx: CanvasRenderingContext2D,
  points: SketchPoint[],
  stroke: string,
  fill: string,
) {
  if (points.length < 2) return
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y)
  ctx.closePath()
  ctx.fillStyle = fill
  ctx.fill()
  ctx.strokeStyle = stroke
  ctx.lineWidth = 1.5
  ctx.stroke()
}

function drawShapeInProgress(
  ctx: CanvasRenderingContext2D,
  points: SketchPoint[],
  cursor: SketchPoint,
  color: string,
) {
  if (points.length === 0) return
  ctx.beginPath()
  ctx.moveTo(points[0].x, points[0].y)
  for (let i = 1; i < points.length; i++) ctx.lineTo(points[i].x, points[i].y)
  ctx.lineTo(cursor.x, cursor.y)
  ctx.strokeStyle = color
  ctx.lineWidth = 1.5
  ctx.setLineDash([4, 3])
  ctx.stroke()
  ctx.setLineDash([])

  // Vertex dots
  for (const pt of points) {
    ctx.beginPath()
    ctx.arc(pt.x, pt.y, 3, 0, Math.PI * 2)
    ctx.fillStyle = color
    ctx.fill()
  }
}

function rectFromTwoPoints(a: SketchPoint, b: SketchPoint): SketchPoint[] {
  return [
    { x: a.x, y: a.y },
    { x: b.x, y: a.y },
    { x: b.x, y: b.y },
    { x: a.x, y: b.y },
  ]
}

// ──────────────────────────────────────────────────────────
// Styles
// ──────────────────────────────────────────────────────────

const st: Record<string, React.CSSProperties> = {
  container: {
    background: COLORS.panelBg,
    border: `1px solid ${COLORS.panelBorder}`,
    borderRadius: 6,
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    fontFamily: TYPOGRAPHY.fontFamily,
    fontSize: TYPOGRAPHY.sizeSM,
    width: CANVAS_W + 2,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '7px 10px',
    borderBottom: `1px solid ${COLORS.panelBorder}`,
    background: COLORS.toolbarBg,
  },
  title: {
    fontWeight: TYPOGRAPHY.weightBold,
    fontSize: TYPOGRAPHY.sizeLG,
    color: COLORS.textPrimary,
  },
  iconBtn: {
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    fontSize: 13,
    color: COLORS.textSecondary,
    padding: '2px 5px',
  },
  toolbar: {
    display: 'flex',
    gap: 4,
    padding: '6px 8px',
    borderBottom: `1px solid ${COLORS.panelBorder}`,
    flexWrap: 'wrap' as const,
    alignItems: 'center',
    background: COLORS.panelBg,
  },
  toolbarLabel: {
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
    marginRight: 2,
  },
  toolBtn: {
    padding: '2px 8px',
    border: `1px solid ${COLORS.panelBorder}`,
    borderRadius: 4,
    background: COLORS.surfaceWhite,
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textSecondary,
    fontFamily: TYPOGRAPHY.fontFamily,
  },
  toolBtnActive: {
    background: COLORS.accent,
    borderColor: COLORS.accent,
    color: '#fff',
    fontWeight: TYPOGRAPHY.weightSemibold,
  },
  canvasWrap: {
    position: 'relative',
    background: '#fff',
  },
  canvas: {
    display: 'block',
    cursor: 'crosshair',
  },
  canvasHint: {
    position: 'absolute',
    bottom: 4,
    right: 6,
    fontSize: 10,
    color: '#94a3b8',
    pointerEvents: 'none',
  },
  footer: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 10px',
    borderTop: `1px solid ${COLORS.panelBorder}`,
    background: COLORS.panelBg,
  },
  footerInfo: {
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
  },
  saveBtn: {
    padding: '4px 12px',
    background: COLORS.accent,
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeXS,
    fontWeight: TYPOGRAPHY.weightSemibold,
    fontFamily: TYPOGRAPHY.fontFamily,
  },
  saveBtnDisabled: {
    background: COLORS.textMuted,
    cursor: 'not-allowed',
  },
  dialogOverlay: {
    position: 'fixed',
    inset: 0,
    background: 'rgba(0,0,0,0.45)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 9999,
  },
  dialog: {
    background: '#fff',
    borderRadius: 8,
    padding: 20,
    minWidth: 300,
    maxWidth: 380,
    boxShadow: '0 8px 32px rgba(0,0,0,0.18)',
    fontFamily: TYPOGRAPHY.fontFamily,
  },
  dialogTitle: {
    fontWeight: TYPOGRAPHY.weightBold,
    fontSize: TYPOGRAPHY.sizeLG,
    marginBottom: 14,
    color: '#1e293b',
  },
  fieldRow: {
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
    marginBottom: 12,
  },
  fieldLabel: {
    fontSize: TYPOGRAPHY.sizeXS,
    color: '#64748b',
    fontWeight: TYPOGRAPHY.weightSemibold,
  },
  textInput: {
    padding: '5px 8px',
    border: '1px solid #cbd5e1',
    borderRadius: 4,
    fontSize: TYPOGRAPHY.sizeSM,
    fontFamily: TYPOGRAPHY.fontFamily,
    width: '100%',
    boxSizing: 'border-box' as const,
  },
  dialogActions: {
    display: 'flex',
    justifyContent: 'flex-end',
    gap: 8,
    marginTop: 16,
  },
  cancelBtn: {
    padding: '5px 14px',
    border: '1px solid #cbd5e1',
    borderRadius: 4,
    background: '#fff',
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeSM,
    fontFamily: TYPOGRAPHY.fontFamily,
    color: '#374151',
  },
  confirmBtn: {
    padding: '5px 14px',
    background: COLORS.accent,
    color: '#fff',
    border: 'none',
    borderRadius: 4,
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeSM,
    fontWeight: TYPOGRAPHY.weightSemibold,
    fontFamily: TYPOGRAPHY.fontFamily,
  },
  confirmBtnDisabled: {
    background: '#94a3b8',
    cursor: 'not-allowed',
  },
  errorMsg: {
    background: '#fef2f2',
    color: '#dc2626',
    padding: '6px 10px',
    borderRadius: 4,
    fontSize: TYPOGRAPHY.sizeXS,
    marginTop: 8,
  },
  successMsg: {
    background: '#f0fdf4',
    color: '#16a34a',
    padding: '10px 14px',
    borderRadius: 4,
    fontSize: TYPOGRAPHY.sizeSM,
    fontWeight: TYPOGRAPHY.weightSemibold,
    textAlign: 'center',
  },
}

/**
 * FOMS Brain PG-B1 — SketchUp-Like Top Toolbar
 *
 * Layout: [Brand] [Sep] [File actions] [Sep] [View modes] [Sep] [Validation] [→ Project/status]
 */

import { useDesignerStore } from '../stores/designerStore'
import { S, COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import { designerApi } from '../api/client'
import { FURNITURE_TYPE_REGISTRY } from '../domain/factoryRegistry'

type ViewMode = '3d' | 'front' | 'side' | 'top'

interface TopToolBarProps {
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
}

const VIEW_MODES: { value: ViewMode; label: string }[] = [
  { value: '3d', label: '3D' },
  { value: 'front', label: '정면' },
  { value: 'side', label: '측면' },
  { value: 'top', label: '평면' },
]

export function TopToolBar({ viewMode, onViewModeChange }: TopToolBarProps) {
  const project = useDesignerStore((s) => s.project)
  const design = useDesignerStore((s) => s.design)
  const isDirty = useDesignerStore((s) => s.isDirty)
  const markSaved = useDesignerStore((s) => s.markSaved)
  const constraintResult = useDesignerStore((s) => s.constraintResult)
  const currentFurnitureType = useDesignerStore((s) => s.currentFurnitureType)
  const undo = useDesignerStore((s) => s.undo)
  const redo = useDesignerStore((s) => s.redo)
  const canUndo = useDesignerStore((s) => s.canUndo)
  const canRedo = useDesignerStore((s) => s.canRedo)

  const isValid = constraintResult?.valid ?? true
  const asm = design.assembly
  const typeMeta = FURNITURE_TYPE_REGISTRY.find(r => r.type === currentFurnitureType)

  async function handleSave() {
    if (!project?.id) return
    try {
      await designerApi.createVersion(project.id, design)
      markSaved()
    } catch {
      /* save error handled by parent */
    }
  }

  return (
    <div style={S.toolbar}>
      {/* Brand */}
      <span style={{ fontSize: 15, marginRight: 2 }}>🪑</span>
      <span style={{ fontWeight: TYPOGRAPHY.weightBold, fontSize: TYPOGRAPHY.sizeLG, color: COLORS.textPrimary, whiteSpace: 'nowrap', marginRight: 4 }}>
        FOMS Brain
      </span>
      <span style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted, background: COLORS.panelBg, border: `1px solid ${COLORS.panelBorder}`, borderRadius: 10, padding: '1px 6px', marginRight: 4 }}>
        {typeMeta?.icon} {typeMeta?.label ?? currentFurnitureType}
      </span>

      <div style={S.tbSep} />

      {/* File actions */}
      <button
        style={{
          ...S.tbBtn,
          ...(isDirty ? {} : { color: COLORS.textMuted }),
          background: isDirty ? COLORS.accentLight : 'transparent',
          borderColor: isDirty ? COLORS.accent : 'transparent',
          color: isDirty ? COLORS.accent : COLORS.textMuted,
        }}
        onClick={handleSave}
        title={isDirty ? '저장 (미저장 변경사항 있음)' : '저장됨'}
      >
        {isDirty ? '● 저장' : '✓ 저장됨'}
      </button>

      <div style={S.tbSep} />

      {/* Undo/Redo (PG-B9) */}
      <button
        onClick={undo}
        disabled={!canUndo()}
        title="실행 취소 (Ctrl+Z)"
        style={{
          ...S.tbBtn,
          opacity: canUndo() ? 1 : 0.35,
          cursor: canUndo() ? 'pointer' : 'default',
          fontSize: 14,
          padding: '4px 7px',
        }}
      >
        ↩
      </button>
      <button
        onClick={redo}
        disabled={!canRedo()}
        title="다시 실행 (Ctrl+Y)"
        style={{
          ...S.tbBtn,
          opacity: canRedo() ? 1 : 0.35,
          cursor: canRedo() ? 'pointer' : 'default',
          fontSize: 14,
          padding: '4px 7px',
        }}
      >
        ↪
      </button>

      <div style={S.tbSep} />

      {/* Dimensions display */}
      <span style={{ fontSize: TYPOGRAPHY.sizeSM, color: COLORS.textSecondary, fontVariantNumeric: 'tabular-nums' }}>
        W {asm.dimensions.width} × H {asm.dimensions.height} × D {asm.dimensions.depth} mm
      </span>
      <span style={{ fontSize: TYPOGRAPHY.sizeSM, color: COLORS.textMuted, marginLeft: 4 }}>
        | {asm.module_count}통 {asm.door_type}
      </span>

      <div style={S.tbSep} />

      {/* View modes */}
      {VIEW_MODES.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onViewModeChange(value)}
          style={{
            ...S.viewTab,
            ...(viewMode === value ? S.tbBtnActive : {}),
          }}
        >
          {label}
        </button>
      ))}

      {/* Spacer */}
      <div style={{ flex: 1 }} />

      {/* Validation status */}
      <span style={{
        fontSize: TYPOGRAPHY.sizeSM,
        fontWeight: TYPOGRAPHY.weightSemibold,
        color: isValid ? COLORS.valid : COLORS.invalid,
        display: 'flex',
        alignItems: 'center',
        gap: 4,
      }}>
        <span style={{
          width: 7, height: 7, borderRadius: '50%',
          background: isValid ? COLORS.valid : COLORS.invalid,
          display: 'inline-block',
        }} />
        {isValid ? '유효' : `오류 ${constraintResult?.errorCount ?? 0}`}
      </span>

      {project && (
        <>
          <div style={S.tbSep} />
          <span style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted, maxWidth: 140, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {project.name}
          </span>
        </>
      )}
    </div>
  )
}

/**
 * FOMS Brain PG-B9 — LEGO Block Palette.
 *
 * Add shelf / drawer / rod / door / EP / SR blocks to the design.
 * Each block is positioned at a sensible default inside the current assembly.
 */

import { useDesignerStore } from '../stores/designerStore'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import type { Component, ComponentKind, ComponentRole } from '../domain/ontologyTypes'

const _uuid = () => crypto.randomUUID()

interface BlockDef {
  kind: ComponentKind
  role: ComponentRole
  label: string
  icon: string
  defaultDims: (asm: { width: number; height: number; depth: number }) => {
    width: number; height: number; depth: number
    x: number; y: number; z: number
  }
  materialId: string
}

const BLOCKS: BlockDef[] = [
  {
    kind: 'shelf',
    role: 'shelf',
    label: '선반',
    icon: '═',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 18,
      depth: a.depth - 20,
      x: 50,
      y: Math.round(a.height / 2),
      z: 0,
    }),
  },
  {
    kind: 'drawer',
    role: 'drawer',
    label: '서랍',
    icon: '▭',
    materialId: 'MDF_18T_DOOR',
    defaultDims: (a) => ({
      width: Math.round((a.width - 100) / 2),
      height: 200,
      depth: a.depth - 20,
      x: 50,
      y: 80,
      z: 0,
    }),
  },
  {
    kind: 'sr',
    role: 'top_sr',
    label: '옷봉',
    icon: '○',
    materialId: null as unknown as string,
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 30,
      depth: 30,
      x: 50,
      y: Math.round(a.height * 0.6),
      z: Math.round(a.depth / 2),
    }),
  },
  {
    kind: 'door',
    role: 'door',
    label: '도어',
    icon: '🚪',
    materialId: 'MDF_18T_DOOR',
    defaultDims: (a) => ({
      width: Math.round((a.width - 100) / 2) - 2,
      height: a.height - 2,
      depth: 18,
      x: 52,
      y: 1,
      z: -18,
    }),
  },
  {
    kind: 'ep',
    role: 'left_ep',
    label: 'EP 추가',
    icon: '|',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: 18,
      height: a.height,
      depth: a.depth - 9,
      x: Math.round(a.width / 2),
      y: 0,
      z: 0,
    }),
  },
  {
    kind: 'panel',
    role: 'generic',
    label: '판재',
    icon: '▬',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 18,
      depth: a.depth - 9,
      x: 50,
      y: Math.round(a.height * 0.3),
      z: 0,
    }),
  },
]

export function LegoBlockPalette() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const addComponent = useDesignerStore((s) => s.addComponent)
  const removeComponent = useDesignerStore((s) => s.removeComponent)

  const asm = design.assembly

  function handleAdd(block: BlockDef) {
    const dims = block.defaultDims({
      width: asm.dimensions.width,
      height: asm.dimensions.height,
      depth: asm.dimensions.depth,
    })
    const newComp: Component = {
      id: _uuid(),
      kind: block.kind,
      role: block.role,
      name: block.label,
      parent_id: null,
      material_id: block.materialId || null,
      dimensions: { width: dims.width, height: dims.height, depth: dims.depth },
      position: { x: dims.x, y: dims.y, z: dims.z },
      formula_refs: [],
    }
    addComponent(newComp)
  }

  return (
    <div style={{ padding: '8px 6px' }}>
      <div style={{
        fontSize: TYPOGRAPHY.sizeXS,
        fontWeight: TYPOGRAPHY.weightBold,
        color: COLORS.textMuted,
        textTransform: 'uppercase' as const,
        letterSpacing: '0.06em',
        marginBottom: 6,
        paddingLeft: 4,
      }}>
        블럭 추가
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4 }}>
        {BLOCKS.map((block) => (
          <button
            key={block.label}
            onClick={() => handleAdd(block)}
            title={`${block.label} 추가`}
            style={{
              background: COLORS.surfaceWhite,
              border: `1px solid ${COLORS.panelBorder}`,
              borderRadius: 5,
              padding: '5px 4px',
              cursor: 'pointer',
              fontSize: 11,
              color: COLORS.textSecondary,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              gap: 2,
              fontFamily: TYPOGRAPHY.fontFamily,
              transition: 'background 0.1s, border-color 0.1s',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = COLORS.accent
              ;(e.currentTarget as HTMLButtonElement).style.background = COLORS.accentLight
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.borderColor = COLORS.panelBorder
              ;(e.currentTarget as HTMLButtonElement).style.background = COLORS.surfaceWhite
            }}
          >
            <span style={{ fontSize: 14 }}>{block.icon}</span>
            <span style={{ fontSize: 9, color: COLORS.textMuted }}>{block.label}</span>
          </button>
        ))}
      </div>

      {/* Delete selected */}
      {selectedId && (
        <button
          onClick={() => removeComponent(selectedId)}
          title="선택된 부재 삭제 (Delete)"
          style={{
            width: '100%',
            marginTop: 8,
            background: '#fff5f5',
            border: `1px solid #fed7d7`,
            borderRadius: 5,
            padding: '5px 0',
            cursor: 'pointer',
            fontSize: 11,
            color: '#c53030',
            fontFamily: TYPOGRAPHY.fontFamily,
          }}
        >
          🗑 선택 삭제
        </button>
      )}
    </div>
  )
}

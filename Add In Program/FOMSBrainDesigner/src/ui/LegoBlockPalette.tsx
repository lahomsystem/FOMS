/**
 * FOMS Brain PG-B9 — LEGO Block Palette.
 *
 * Add shelf / drawer / rod / door / EP / SR blocks to the design.
 * Each block is positioned at a sensible default inside the current assembly.
 */

import { useDesignerStore } from '../stores/designerStore'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import { LEGO_BLOCK_DEFS, type LegoBlockDef, componentFromLegoBlockDef } from '../domain/blockPlacement'
import { wardrobeParamsFromDesign } from '../domain/wardrobeParamsHelpers'

export function LegoBlockPalette() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const addComponent = useDesignerStore((s) => s.addComponent)
  const removeComponent = useDesignerStore((s) => s.removeComponent)
  const regenerateWardrobe = useDesignerStore((s) => s.regenerateWardrobe)
  const currentFurnitureType = useDesignerStore((s) => s.currentFurnitureType)

  const asm = design.assembly

  function splitIntoModules(moduleCount: number) {
    if (currentFurnitureType === 'wardrobe') {
      regenerateWardrobe({
        ...wardrobeParamsFromDesign(design),
        moduleCount,
      })
    }
  }

  function handleAdd(block: LegoBlockDef) {
    const newComp = componentFromLegoBlockDef(block, {
      width: asm.dimensions.width,
      height: asm.dimensions.height,
      depth: asm.dimensions.depth,
    })
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
        {LEGO_BLOCK_DEFS.map((block) => (
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

      {/* Separator */}
      <div style={{ borderTop: `1px solid ${COLORS.toolbarBorder}`, margin: '8px 0 4px' }} />

      {/* Split module tool */}
      {currentFurnitureType === 'wardrobe' && (
        <div>
          <div style={{ fontSize: TYPOGRAPHY.sizeXS, fontWeight: TYPOGRAPHY.weightBold, color: COLORS.textMuted, textTransform: 'uppercase' as const, letterSpacing: '0.05em', marginBottom: 4, paddingLeft: 2 }}>
            모듈 분할
          </div>
          <div style={{ display: 'flex', gap: 3 }}>
            {[2, 3, 4, 5].map((n) => (
              <button
                key={n}
                onClick={() => splitIntoModules(n)}
                title={`${n}칸으로 분할`}
                style={{
                  flex: 1,
                  background: COLORS.surfaceWhite,
                  border: `1px solid ${COLORS.panelBorder}`,
                  borderRadius: 5,
                  padding: '4px 2px',
                  cursor: 'pointer',
                  fontSize: 10,
                  color: COLORS.textSecondary,
                  fontFamily: TYPOGRAPHY.fontFamily,
                }}
              >
                {n}칸
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Delete selected */}
      {selectedId && (
        <button
          onClick={() => removeComponent(selectedId)}
          title="선택된 부재 삭제 (Delete)"
          style={{
            width: '100%',
            marginTop: 8,
            background: '#fff5f5',
            border: '1px solid #fed7d7',
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

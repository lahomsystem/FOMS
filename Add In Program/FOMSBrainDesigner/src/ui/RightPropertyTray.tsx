/**
 * FOMS Brain PG-B1 — SketchUp-Like Right Property Tray
 *
 * Replaces the dark narrow inspector with a wider, light-theme tray.
 * Sections: Selected Component | Assembly | Validation | Material
 */

import { useDesignerStore } from '../stores/designerStore'
import { S, COLORS, TYPOGRAPHY, SPACING } from '../styles/sketchupTheme'
import { ComponentDimensionEditor } from './ComponentDimensionEditor'
import { LegoBlockPalette } from './LegoBlockPalette'
import type React from 'react'

// ──────────────────────────────────────────────────────────
// Tray section header
// ──────────────────────────────────────────────────────────

function TraySection({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 4 }}>
      <div style={S.sectionHeader}>{title}</div>
      {children}
    </div>
  )
}

function TrayField({ label, value }: { label: string; value: string | number | null | undefined }) {
  return (
    <div style={S.fieldRow}>
      <span style={S.fieldLabel}>{label}</span>
      <span style={S.fieldValue}>{value ?? '—'}</span>
    </div>
  )
}

// ──────────────────────────────────────────────────────────
// Main tray
// ──────────────────────────────────────────────────────────

export function RightPropertyTray() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const setSelected = useDesignerStore((s) => s.setSelectedComponent)
  const constraintResult = useDesignerStore((s) => s.constraintResult)
  const currentFurnitureType = useDesignerStore((s) => s.currentFurnitureType)

  const asm = design.assembly
  const selectedComp = selectedId
    ? design.components.find(c => c.id === selectedId)
    : null

  const isValid = constraintResult?.valid ?? true

  return (
    <div style={{ ...S.tray, fontSize: TYPOGRAPHY.sizeSM }}>

      {/* ── Selected Component ── */}
      <TraySection title="선택된 컴포넌트">
        {selectedComp ? (
          <>
            {/* Quick info */}
            <TrayField label="종류" value={selectedComp.kind} />
            <TrayField label="역할" value={selectedComp.role} />
            <TrayField label="소재" value={selectedComp.material_id ?? '없음'} />
            <TrayField label="UUID" value={selectedComp.id.slice(0, 8) + '…'} />

            {/* Direct dimension editor (PG-B9) */}
            <ComponentDimensionEditor component={selectedComp} />

            <div style={{ padding: '6px 10px' }}>
              <button
                onClick={() => setSelected(null)}
                style={{
                  width: '100%', padding: '4px 0',
                  border: `1px solid ${COLORS.panelBorder}`,
                  borderRadius: 4, background: COLORS.surfaceWhite,
                  cursor: 'pointer', fontSize: TYPOGRAPHY.sizeXS,
                  color: COLORS.textMuted,
                }}
              >
                선택 해제 (Esc)
              </button>
            </div>
          </>
        ) : (
          <div style={{ padding: '8px 10px', color: COLORS.textMuted, fontSize: TYPOGRAPHY.sizeXS }}>
            3D 뷰에서 컴포넌트를 클릭하세요
          </div>
        )}
      </TraySection>

      {/* ── Assembly ── */}
      <TraySection title="가구 조립체">
        <TrayField label="유형" value={currentFurnitureType} />
        <TrayField label="이름" value={asm.name} />
        <TrayField label="W 폭" value={`${asm.dimensions.width} mm`} />
        <TrayField label="H 높이" value={`${asm.dimensions.height} mm`} />
        <TrayField label="D 깊이" value={`${asm.dimensions.depth} mm`} />
        <TrayField label="통 수" value={asm.module_count} />
        <TrayField label="도어" value={asm.door_type} />
        <TrayField label="좌EP" value={`${asm.ep_left} mm`} />
        <TrayField label="우EP" value={`${asm.ep_right} mm`} />
        <TrayField label="받침대" value={`${asm.base_height} mm`} />
        <TrayField label="상부SR" value={`${asm.top_sr} mm`} />
        <TrayField label="컴포넌트" value={`${design.components.length}개`} />
      </TraySection>

      {/* ── LEGO Block Palette (PG-B9) ── */}
      <TraySection title="블럭 조립">
        <LegoBlockPalette />
      </TraySection>

      {/* ── Validation ── */}
      <TraySection title="설계 검증">
        <div style={{
          padding: '6px 10px',
          display: 'flex',
          alignItems: 'center',
          gap: 6,
          color: isValid ? COLORS.valid : COLORS.invalid,
          fontWeight: TYPOGRAPHY.weightSemibold,
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%',
            background: isValid ? COLORS.valid : COLORS.invalid,
            flexShrink: 0,
          }} />
          {isValid ? '설계 유효' : `오류 ${constraintResult?.errorCount ?? 0}개`}
        </div>
        {!isValid && constraintResult?.violations?.slice(0, 3).map((v, i) => (
          <div key={i} style={{ padding: '2px 10px 2px 24px', fontSize: TYPOGRAPHY.sizeXS, color: COLORS.invalid }}>
            {v.message}
          </div>
        ))}
        {(constraintResult?.warningCount ?? 0) > 0 && (
          <div style={{ padding: '2px 10px 2px 10px', fontSize: TYPOGRAPHY.sizeXS, color: COLORS.warning }}>
            경고 {constraintResult?.warningCount}개
          </div>
        )}
      </TraySection>

    </div>
  )
}

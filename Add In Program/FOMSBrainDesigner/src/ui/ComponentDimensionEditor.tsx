/**
 * FOMS Brain PG-B9 — Component Dimension Editor.
 *
 * Inline W/H/D + position editor for the selected component.
 * Every change goes through updateComponent → formula engine → validator.
 */

import { useDesignerStore } from '../stores/designerStore'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'
import type { Component } from '../domain/ontologyTypes'

interface DimFieldProps {
  label: string
  value: number
  min?: number
  max?: number
  onChange: (v: number) => void
}

function DimField({ label, value, min = 1, max = 12000, onChange }: DimFieldProps) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', padding: '3px 10px', gap: 8 }}>
      <span style={{
        minWidth: 22,
        fontSize: TYPOGRAPHY.sizeXS,
        fontWeight: TYPOGRAPHY.weightBold,
        color: COLORS.accent,
        fontFamily: 'monospace',
      }}>
        {label}
      </span>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={10}
        onChange={(e) => {
          const n = parseInt(e.target.value, 10)
          if (!isNaN(n) && n >= min && n <= max) onChange(n)
        }}
        style={{
          flex: 1,
          border: `1px solid ${COLORS.panelBorder}`,
          borderRadius: 4,
          padding: '3px 6px',
          fontSize: TYPOGRAPHY.sizeMD,
          fontFamily: 'monospace',
          background: COLORS.surfaceWhite,
          color: COLORS.textPrimary,
          outline: 'none',
          textAlign: 'right' as const,
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = COLORS.accent
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = COLORS.panelBorder
        }}
      />
      <span style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted }}>mm</span>
    </div>
  )
}

interface ComponentDimensionEditorProps {
  component: Component
}

export function ComponentDimensionEditor({ component: c }: ComponentDimensionEditorProps) {
  const updateComponent = useDesignerStore((s) => s.updateComponent)

  function updateDim(field: 'width' | 'height' | 'depth', val: number) {
    updateComponent(c.id, {
      dimensions: { ...c.dimensions, [field]: val },
    })
  }

  function updatePos(field: 'x' | 'y' | 'z', val: number) {
    updateComponent(c.id, {
      position: { ...c.position, [field]: val },
    })
  }

  return (
    <div>
      {/* Dimensions */}
      <div style={{
        fontSize: TYPOGRAPHY.sizeXS,
        fontWeight: TYPOGRAPHY.weightBold,
        color: COLORS.textMuted,
        textTransform: 'uppercase' as const,
        letterSpacing: '0.06em',
        padding: '6px 10px 3px',
      }}>
        치수 (mm)
      </div>
      <DimField label="W" value={c.dimensions.width} onChange={(v) => updateDim('width', v)} />
      <DimField label="H" value={c.dimensions.height} onChange={(v) => updateDim('height', v)} />
      <DimField label="D" value={c.dimensions.depth} onChange={(v) => updateDim('depth', v)} />

      {/* Position */}
      <div style={{
        fontSize: TYPOGRAPHY.sizeXS,
        fontWeight: TYPOGRAPHY.weightBold,
        color: COLORS.textMuted,
        textTransform: 'uppercase' as const,
        letterSpacing: '0.06em',
        padding: '8px 10px 3px',
        borderTop: `1px solid ${COLORS.panelBorder}`,
        marginTop: 4,
      }}>
        위치 (mm)
      </div>
      <DimField label="X" value={c.position.x} min={-12000} onChange={(v) => updatePos('x', v)} />
      <DimField label="Y" value={c.position.y} min={-12000} onChange={(v) => updatePos('y', v)} />
      <DimField label="Z" value={c.position.z} min={-12000} onChange={(v) => updatePos('z', v)} />
    </div>
  )
}

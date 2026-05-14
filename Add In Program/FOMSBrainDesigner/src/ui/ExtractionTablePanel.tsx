/**
 * FOMS Brain PG-B8 — Extraction Table Panel.
 *
 * Shows Gemini extraction fields in an editable table.
 * Highlights unresolved fields in orange.
 * User can edit W/H/D, parts table, furniture type.
 * Corrections create CorrectionDelta on save.
 */

import { useState } from 'react'
import { COLORS, TYPOGRAPHY } from '../styles/sketchupTheme'

interface ExtractionField {
  key: string
  label: string
  value: string | number | null
  resolved: boolean
  editable: boolean
}

interface ExtractionTablePanelProps {
  extraction: {
    furniture_type?: string
    site_size?: { width_mm?: number | null; height_mm?: number | null; depth_mm?: number | null }
    parts_table?: Array<{ code: string; description?: string; quantity?: number }>
    unresolved_fields?: string[]
    confidence?: number
    customer_info?: { product_name?: string; color?: string }
    drawing_meta?: { view_type?: string; drawing_style?: string }
  }
  onApprove?: (corrected: Record<string, unknown>) => void
  onReject?: () => void
  onLoad3D?: () => void
  isLoading?: boolean
}

function FieldRow({
  field,
  onEdit,
}: {
  field: ExtractionField
  onEdit: (key: string, value: string) => void
}) {
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState(String(field.value ?? ''))

  const bgColor = field.resolved ? 'transparent' : '#fff8e1'
  const borderColor = field.resolved ? COLORS.panelBorder : '#ffc107'

  return (
    <tr
      style={{
        background: bgColor,
        borderBottom: `1px solid ${COLORS.panelBorder}`,
      }}
    >
      <td
        style={{
          padding: '5px 10px',
          fontSize: TYPOGRAPHY.sizeXS,
          fontWeight: TYPOGRAPHY.weightBold,
          color: COLORS.textMuted,
          whiteSpace: 'nowrap' as const,
          width: 110,
          borderRight: `1px solid ${COLORS.panelBorder}`,
        }}
      >
        {!field.resolved && (
          <span style={{ color: '#ffc107', marginRight: 4 }}>⚠</span>
        )}
        {field.label}
      </td>
      <td style={{ padding: '4px 8px' }}>
        {editing && field.editable ? (
          <div style={{ display: 'flex', gap: 4 }}>
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              style={{
                flex: 1,
                border: `1px solid ${COLORS.accent}`,
                borderRadius: 3,
                padding: '2px 6px',
                fontSize: TYPOGRAPHY.sizeSM,
                fontFamily: 'monospace',
                outline: 'none',
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter') {
                  onEdit(field.key, draft)
                  setEditing(false)
                } else if (e.key === 'Escape') {
                  setDraft(String(field.value ?? ''))
                  setEditing(false)
                }
              }}
            />
            <button
              onClick={() => { onEdit(field.key, draft); setEditing(false) }}
              style={{
                background: COLORS.accent, border: 'none', borderRadius: 3,
                color: '#fff', fontSize: TYPOGRAPHY.sizeXS, padding: '2px 7px', cursor: 'pointer',
              }}
            >
              ✓
            </button>
          </div>
        ) : (
          <div
            style={{
              fontSize: TYPOGRAPHY.sizeSM,
              color: field.value !== null && field.value !== undefined
                ? COLORS.textPrimary
                : COLORS.textMuted,
              fontFamily: typeof field.value === 'number' ? 'monospace' : 'inherit',
              cursor: field.editable ? 'pointer' : 'default',
              padding: '1px 4px',
              borderRadius: 3,
              border: `1px solid transparent`,
            }}
            onClick={() => field.editable && setEditing(true)}
            title={field.editable ? '클릭하여 편집' : undefined}
          >
            {field.value !== null && field.value !== undefined
              ? String(field.value)
              : <span style={{ color: '#ffc107', fontStyle: 'italic' }}>미확인</span>
            }
            {field.editable && field.value !== null && field.value !== undefined && (
              <span style={{ color: COLORS.textMuted, marginLeft: 4, fontSize: 9 }}>✏</span>
            )}
          </div>
        )}
      </td>
    </tr>
  )
}

export function ExtractionTablePanel({
  extraction,
  onApprove,
  onReject,
  onLoad3D,
  isLoading = false,
}: ExtractionTablePanelProps) {
  const ss = extraction.site_size ?? {}
  const ci = extraction.customer_info ?? {}
  const meta = extraction.drawing_meta ?? {}
  const unresolved = new Set(extraction.unresolved_fields ?? [])

  const [corrections, setCorrections] = useState<Record<string, string>>({})

  function handleEdit(key: string, value: string) {
    setCorrections((prev) => ({ ...prev, [key]: value }))
  }

  function getVal(key: string, raw: string | number | null | undefined) {
    return key in corrections ? corrections[key] : (raw ?? null)
  }

  const fields: ExtractionField[] = [
    {
      key: 'furniture_type',
      label: '가구 유형',
      value: getVal('furniture_type', extraction.furniture_type ?? null),
      resolved: !unresolved.has('furniture_type') && !!extraction.furniture_type,
      editable: true,
    },
    {
      key: 'site_size.width_mm',
      label: 'W 폭 (mm)',
      value: getVal('site_size.width_mm', ss.width_mm ?? null),
      resolved: !unresolved.has('extracted_params.width') && ss.width_mm != null,
      editable: true,
    },
    {
      key: 'site_size.height_mm',
      label: 'H 높이 (mm)',
      value: getVal('site_size.height_mm', ss.height_mm ?? null),
      resolved: !unresolved.has('extracted_params.height') && ss.height_mm != null,
      editable: true,
    },
    {
      key: 'site_size.depth_mm',
      label: 'D 깊이 (mm)',
      value: getVal('site_size.depth_mm', ss.depth_mm ?? null),
      resolved: !unresolved.has('extracted_params.depth') && ss.depth_mm != null,
      editable: true,
    },
    {
      key: 'product_name',
      label: '제품명',
      value: getVal('product_name', ci.product_name ?? null),
      resolved: !unresolved.has('customer_info.product_name'),
      editable: true,
    },
    {
      key: 'color',
      label: '색상',
      value: getVal('color', ci.color ?? null),
      resolved: !unresolved.has('customer_info.color'),
      editable: true,
    },
    {
      key: 'view_type',
      label: '도면 뷰',
      value: meta.view_type ?? null,
      resolved: !unresolved.has('drawing_meta.view_type'),
      editable: false,
    },
    {
      key: 'confidence',
      label: '신뢰도',
      value: extraction.confidence != null
        ? `${Math.round(extraction.confidence * 100)}%`
        : null,
      resolved: extraction.confidence != null,
      editable: false,
    },
  ]

  const parts = extraction.parts_table ?? []
  const unresolvedCount = fields.filter((f) => !f.resolved).length
  const hasCorrections = Object.keys(corrections).length > 0

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        fontFamily: TYPOGRAPHY.fontFamily,
        background: COLORS.panelBg,
        overflow: 'hidden',
      }}
    >
      {/* Header */}
      <div
        style={{
          padding: '8px 12px 6px',
          borderBottom: `1px solid ${COLORS.panelBorder}`,
          background: COLORS.surfaceWhite,
          flexShrink: 0,
        }}
      >
        <div style={{ fontSize: TYPOGRAPHY.sizeLG, fontWeight: TYPOGRAPHY.weightBold, color: COLORS.textPrimary }}>
          추출 결과 검수
        </div>
        {unresolvedCount > 0 && (
          <div style={{ fontSize: TYPOGRAPHY.sizeSM, color: '#d97706', marginTop: 2 }}>
            ⚠ {unresolvedCount}개 미확인 필드 — 클릭하여 직접 입력
          </div>
        )}
        {hasCorrections && (
          <div style={{ fontSize: TYPOGRAPHY.sizeSM, color: COLORS.accent, marginTop: 2 }}>
            ✏ {Object.keys(corrections).length}개 수정됨
          </div>
        )}
      </div>

      {/* Fields table */}
      <div style={{ flex: 1, overflowY: 'auto' as const, padding: '0 0 8px' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' as const }}>
          <tbody>
            {fields.map((f) => (
              <FieldRow key={f.key} field={f} onEdit={handleEdit} />
            ))}
          </tbody>
        </table>

        {/* Parts table */}
        {parts.length > 0 && (
          <div style={{ padding: '8px 10px 0' }}>
            <div
              style={{
                fontSize: TYPOGRAPHY.sizeXS,
                fontWeight: TYPOGRAPHY.weightBold,
                color: COLORS.textMuted,
                textTransform: 'uppercase' as const,
                letterSpacing: '0.06em',
                marginBottom: 4,
              }}
            >
              부품표 ({parts.length}종)
            </div>
            {parts.slice(0, 12).map((p, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  padding: '2px 0',
                  fontSize: TYPOGRAPHY.sizeSM,
                  borderBottom: `1px solid ${COLORS.panelBorder}`,
                  color: COLORS.textPrimary,
                }}
              >
                <span style={{ fontFamily: 'monospace', color: COLORS.accent }}>{p.code}</span>
                <span style={{ color: COLORS.textMuted }}>{p.description || ''}</span>
                <span style={{ fontFamily: 'monospace' }}>×{p.quantity ?? 1}</span>
              </div>
            ))}
            {parts.length > 12 && (
              <div style={{ fontSize: TYPOGRAPHY.sizeXS, color: COLORS.textMuted, padding: '3px 0' }}>
                외 {parts.length - 12}종 더...
              </div>
            )}
          </div>
        )}
      </div>

      {/* Action buttons */}
      <div
        style={{
          padding: '8px 10px',
          borderTop: `1px solid ${COLORS.panelBorder}`,
          background: COLORS.surfaceWhite,
          display: 'flex',
          gap: 6,
          flexShrink: 0,
          flexWrap: 'wrap' as const,
        }}
      >
        {onLoad3D && (
          <button
            onClick={onLoad3D}
            disabled={isLoading}
            style={{
              flex: 1, padding: '6px 8px',
              background: '#1a1a2e', border: 'none', borderRadius: 5,
              color: '#e2e8f0', fontSize: TYPOGRAPHY.sizeSM,
              fontWeight: TYPOGRAPHY.weightSemibold, cursor: 'pointer',
            }}
          >
            🧊 3D 편집
          </button>
        )}
        {onApprove && (
          <button
            onClick={() => onApprove({ ...extraction, ...corrections })}
            disabled={isLoading}
            style={{
              flex: 1, padding: '6px 8px',
              background: COLORS.valid, border: 'none', borderRadius: 5,
              color: '#fff', fontSize: TYPOGRAPHY.sizeSM,
              fontWeight: TYPOGRAPHY.weightSemibold, cursor: 'pointer',
            }}
          >
            ✅ 승인
          </button>
        )}
        {onReject && (
          <button
            onClick={onReject}
            disabled={isLoading}
            style={{
              flex: 1, padding: '6px 8px',
              background: '#fff', border: `1px solid ${COLORS.invalid}`,
              borderRadius: 5, color: COLORS.invalid,
              fontSize: TYPOGRAPHY.sizeSM, fontWeight: TYPOGRAPHY.weightSemibold,
              cursor: 'pointer',
            }}
          >
            ✗ 반려
          </button>
        )}
      </div>
    </div>
  )
}

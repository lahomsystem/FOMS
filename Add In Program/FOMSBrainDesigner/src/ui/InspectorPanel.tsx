/**
 * InspectorPanel — 선택된 부재의 UUID/kind/role/dimensions 편집기.
 * DK-B6: schema v2 Component 기반 실제 파라미터 편집.
 */

import { useDesignerStore } from '../stores/designerStore'

export function InspectorPanel() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const updateComponent = useDesignerStore((s) => s.updateComponent)
  const constraintResult = useDesignerStore((s) => s.constraintResult)

  const selectedComp = design.components.find((c) => c.id === selectedId) ?? null
  const hasErrors = (constraintResult?.errorCount ?? 0) > 0

  function handleDimChange(dim: 'width' | 'height' | 'depth', value: string) {
    if (!selectedComp) return
    const num = parseInt(value, 10)
    if (!isNaN(num) && num > 0) {
      updateComponent(selectedComp.id, {
        dimensions: { ...selectedComp.dimensions, [dim]: num },
      })
    }
  }

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>Inspector</span>
      </div>

      {!selectedComp ? (
        <div style={styles.placeholder}>부재를 클릭하여 선택하세요</div>
      ) : (
        <div style={styles.content}>
          {/* UUID */}
          <div style={styles.section}>
            <div style={styles.label}>UUID</div>
            <div style={styles.monoPill} title={selectedComp.id}>
              {selectedComp.id.slice(0, 8)}…
            </div>
          </div>

          {/* Kind / Role */}
          <div style={styles.row}>
            <div style={styles.half}>
              <div style={styles.label}>Kind</div>
              <div style={styles.badge}>{selectedComp.kind}</div>
            </div>
            <div style={styles.half}>
              <div style={styles.label}>Role</div>
              <div style={styles.badge}>{selectedComp.role}</div>
            </div>
          </div>

          {/* Name */}
          <div style={styles.section}>
            <div style={styles.label}>이름</div>
            <div style={styles.value}>{selectedComp.name}</div>
          </div>

          {/* Dimensions */}
          <div style={styles.section}>
            <div style={styles.sectionTitle}>치수 (mm)</div>
            {(['width', 'height', 'depth'] as const).map((dim) => (
              <div key={dim} style={styles.field}>
                <label style={styles.fieldLabel}>
                  {dim === 'width' ? '폭 W' : dim === 'height' ? '높이 H' : '깊이 D'}
                </label>
                <input
                  type="number"
                  value={selectedComp.dimensions[dim]}
                  min={1}
                  onChange={(e) => handleDimChange(dim, e.target.value)}
                  style={{
                    ...styles.input,
                    borderColor: hasErrors ? '#fc8181' : '#2d3748',
                  }}
                />
              </div>
            ))}
          </div>

          {/* Material */}
          {selectedComp.material_id && (
            <div style={styles.section}>
              <div style={styles.label}>자재</div>
              <div style={styles.badge}>{selectedComp.material_id}</div>
            </div>
          )}

          {/* Formula refs */}
          {(selectedComp.formula_refs?.length ?? 0) > 0 && (
            <div style={styles.section}>
              <div style={styles.label}>연결 공식</div>
              {selectedComp.formula_refs!.map((f) => (
                <div key={f} style={styles.formulaTag}>{f}</div>
              ))}
            </div>
          )}

          {/* Validation errors for this component */}
          {constraintResult && constraintResult.violations.filter(v =>
            v.path.includes(selectedComp.id) && v.severity === 'error',
          ).map((v) => (
            <div key={v.code} style={styles.errorItem}>
              {v.message}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    background: '#16213e',
    padding: 12,
    overflowY: 'auto',
    flex: 1,
    fontSize: 12,
  },
  header: {
    paddingBottom: 8,
    borderBottom: '1px solid #2d3748',
    marginBottom: 10,
  },
  title: { color: '#e2e8f0', fontWeight: 700, fontSize: 13 },
  placeholder: { color: '#4a5568', fontSize: 12, padding: 8 },
  content: {},
  section: { marginBottom: 12 },
  sectionTitle: { color: '#718096', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 },
  label: { color: '#718096', fontSize: 10, marginBottom: 3, textTransform: 'uppercase', letterSpacing: '0.04em' },
  row: { display: 'flex', gap: 8, marginBottom: 12 },
  half: { flex: 1 },
  value: { color: '#e2e8f0', fontSize: 12 },
  badge: { background: '#1a1a2e', color: '#667eea', borderRadius: 4, padding: '2px 6px', fontSize: 11, display: 'inline-block' },
  monoPill: { background: '#1a1a2e', color: '#a0aec0', borderRadius: 4, padding: '2px 6px', fontSize: 10, fontFamily: 'monospace', cursor: 'help' },
  formulaTag: { background: '#0d2137', color: '#68d391', borderRadius: 4, padding: '2px 6px', fontSize: 10, display: 'inline-block', marginRight: 4, marginBottom: 2 },
  field: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 6 },
  fieldLabel: { color: '#a0aec0', fontSize: 12, minWidth: 50 },
  input: {
    background: '#1a1a2e',
    border: '1px solid #2d3748',
    borderRadius: 4,
    color: '#e2e8f0',
    padding: '3px 8px',
    fontSize: 13,
    outline: 'none',
    width: 90,
    textAlign: 'right',
  },
  errorItem: { background: '#742a2a', color: '#fc8181', borderRadius: 4, padding: '4px 8px', fontSize: 11, marginTop: 4 },
}

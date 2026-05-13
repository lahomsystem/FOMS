import { useDesignerStore } from '../stores/designerStore'

/** Inspector panel: edit cabinet dimensions and view selected component. */
export function InspectorPanel() {
  const design = useDesignerStore((s) => s.design)
  const updateDims = useDesignerStore((s) => s.updateCabinetDimensions)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const validation = useDesignerStore((s) => s.validation)

  const selectedComp = design.components.find((c) => c.id === selectedId)

  function handleDimChange(field: 'width' | 'height' | 'depth', value: string) {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num > 0) {
      updateDims({ [field]: num })
    }
  }

  const hasErrors = validation && validation.errors.length > 0

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.icon}>📐</span>
        <span style={styles.title}>캐비닛 치수</span>
      </div>

      <div style={styles.section}>
        {(['width', 'height', 'depth'] as const).map((field) => (
          <div key={field} style={styles.field}>
            <label style={styles.label}>
              {field === 'width' ? '폭 (W)' : field === 'height' ? '높이 (H)' : '깊이 (D)'}
              <span style={styles.unit}>mm</span>
            </label>
            <input
              type="number"
              value={design.cabinet[field]}
              min={1}
              max={field === 'width' ? 10000 : field === 'height' ? 4000 : 1200}
              onChange={(e) => handleDimChange(field, e.target.value)}
              style={styles.input}
            />
          </div>
        ))}
      </div>

      {selectedComp && (
        <div style={styles.section}>
          <div style={styles.sectionTitle}>선택된 부재</div>
          <div style={styles.compInfo}>
            <div style={styles.compName}>{selectedComp.name}</div>
            <div style={styles.compType}>{selectedComp.type}</div>
            <div style={styles.compDims}>
              {selectedComp.width} × {selectedComp.height} × {selectedComp.depth} mm
            </div>
          </div>
        </div>
      )}

      {hasErrors && (
        <div style={styles.errorBox}>
          {validation!.errors.map((e) => (
            <div key={e.code} style={styles.errorItem}>
              ⚠️ {e.message}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: {
    width: 220,
    background: '#16213e',
    borderRight: '1px solid #2d3748',
    padding: 12,
    overflowY: 'auto',
    flexShrink: 0,
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    gap: 8,
    marginBottom: 12,
    paddingBottom: 8,
    borderBottom: '1px solid #2d3748',
  },
  icon: { fontSize: 18 },
  title: { color: '#e2e8f0', fontWeight: 600, fontSize: 13 },
  section: { marginBottom: 16 },
  sectionTitle: { color: '#718096', fontSize: 11, fontWeight: 600, marginBottom: 8, textTransform: 'uppercase', letterSpacing: '0.05em' },
  field: { marginBottom: 10 },
  label: { display: 'flex', justifyContent: 'space-between', color: '#a0aec0', fontSize: 12, marginBottom: 4 },
  unit: { color: '#4a5568', fontSize: 11 },
  input: {
    width: '100%',
    background: '#1a1a2e',
    border: '1px solid #2d3748',
    borderRadius: 4,
    color: '#e2e8f0',
    padding: '4px 8px',
    fontSize: 14,
    outline: 'none',
  },
  compInfo: { background: '#1a1a2e', borderRadius: 6, padding: 10 },
  compName: { color: '#667eea', fontSize: 13, fontWeight: 600, marginBottom: 2 },
  compType: { color: '#718096', fontSize: 11, marginBottom: 4 },
  compDims: { color: '#a0aec0', fontSize: 12 },
  errorBox: { background: '#742a2a', borderRadius: 6, padding: 8, marginTop: 8 },
  errorItem: { color: '#fc8181', fontSize: 11, marginBottom: 4 },
}

/**
 * ModulePanel — module count, door type, EP/SR 편집 UI.
 * DK-B6: wardrobe 파라미터 변경 시 즉시 assembly 재생성.
 */

import { useDesignerStore } from '../stores/designerStore'
import type { DoorType } from '../domain/ontologyTypes'

const DOOR_TYPES: { value: DoorType; label: string }[] = [
  { value: 'sliding', label: '슬라이딩' },
  { value: 'swing', label: '여닫이' },
  { value: 'open', label: '오픈 (없음)' },
]

export function ModulePanel() {
  const design = useDesignerStore((s) => s.design)
  const regenerateWardrobe = useDesignerStore((s) => s.regenerateWardrobe)
  const updateAssembly = useDesignerStore((s) => s.updateAssembly)
  const constraintResult = useDesignerStore((s) => s.constraintResult)

  const asm = design.assembly

  function handleModuleCount(count: number) {
    if (count < 1 || count > 6) return
    regenerateWardrobe({
      width: asm.dimensions.width,
      height: asm.dimensions.height,
      depth: asm.dimensions.depth,
      moduleCount: count,
      doorType: asm.door_type as DoorType,
      epLeft: asm.ep_left,
      epRight: asm.ep_right,
      epTop: asm.ep_top,
      baseHeight: asm.base_height,
      topSr: asm.top_sr,
    })
  }

  function handleDoorType(doorType: DoorType) {
    regenerateWardrobe({
      width: asm.dimensions.width,
      height: asm.dimensions.height,
      depth: asm.dimensions.depth,
      moduleCount: asm.module_count,
      doorType,
      epLeft: asm.ep_left,
      epRight: asm.ep_right,
      epTop: asm.ep_top,
      baseHeight: asm.base_height,
      topSr: asm.top_sr,
    })
  }

  function handleAssemblyDim(field: 'width' | 'height' | 'depth', value: string) {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num > 0) {
      regenerateWardrobe({
        width: field === 'width' ? num : asm.dimensions.width,
        height: field === 'height' ? num : asm.dimensions.height,
        depth: field === 'depth' ? num : asm.dimensions.depth,
        moduleCount: asm.module_count,
        doorType: asm.door_type as DoorType,
        epLeft: asm.ep_left,
        epRight: asm.ep_right,
        epTop: asm.ep_top,
        baseHeight: asm.base_height,
        topSr: asm.top_sr,
      })
    }
  }

  function handleSpacerChange(field: 'epLeft' | 'epRight' | 'topSr' | 'baseHeight', value: string) {
    const num = parseInt(value, 10)
    if (!isNaN(num) && num >= 0) {
      regenerateWardrobe({
        width: asm.dimensions.width,
        height: asm.dimensions.height,
        depth: asm.dimensions.depth,
        moduleCount: asm.module_count,
        doorType: asm.door_type as DoorType,
        epLeft: field === 'epLeft' ? num : asm.ep_left,
        epRight: field === 'epRight' ? num : asm.ep_right,
        epTop: asm.ep_top,
        baseHeight: field === 'baseHeight' ? num : asm.base_height,
        topSr: field === 'topSr' ? num : asm.top_sr,
      })
    }
  }

  const isValid = constraintResult?.valid ?? true

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>모듈 설정</span>
        <span style={{ ...styles.statusDot, background: isValid ? '#68d391' : '#fc8181' }} />
      </div>

      {/* Assembly dimensions */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>전체 치수 (mm)</div>
        {(['width', 'height', 'depth'] as const).map((dim) => (
          <div key={dim} style={styles.field}>
            <label style={styles.label}>
              {dim === 'width' ? 'W 폭' : dim === 'height' ? 'H 높이' : 'D 깊이'}
            </label>
            <input
              type="number"
              value={asm.dimensions[dim]}
              min={dim === 'width' ? 600 : dim === 'height' ? 1000 : 300}
              max={dim === 'width' ? 10000 : dim === 'height' ? 4000 : 1200}
              step={10}
              onChange={(e) => handleAssemblyDim(dim, e.target.value)}
              style={styles.input}
            />
          </div>
        ))}
      </div>

      {/* Module count */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>통 수 (Module Count)</div>
        <div style={styles.buttonRow}>
          {[1, 2, 3, 4, 5].map((n) => (
            <button
              key={n}
              onClick={() => handleModuleCount(n)}
              style={{
                ...styles.countBtn,
                background: asm.module_count === n ? '#667eea' : '#1a1a2e',
                color: asm.module_count === n ? '#fff' : '#a0aec0',
              }}
            >
              {n}통
            </button>
          ))}
        </div>
      </div>

      {/* Door type */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>도어 타입</div>
        <div style={styles.buttonRow}>
          {DOOR_TYPES.map(({ value, label }) => (
            <button
              key={value}
              onClick={() => handleDoorType(value)}
              style={{
                ...styles.doorBtn,
                background: asm.door_type === value ? '#667eea' : '#1a1a2e',
                color: asm.door_type === value ? '#fff' : '#a0aec0',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      </div>

      {/* EP/SR */}
      <div style={styles.section}>
        <div style={styles.sectionTitle}>EP / SR (mm)</div>
        {[
          { field: 'epLeft' as const, label: '좌측 EP' },
          { field: 'epRight' as const, label: '우측 EP' },
          { field: 'topSr' as const, label: '상부 SR' },
          { field: 'baseHeight' as const, label: '받침대' },
        ].map(({ field, label }) => (
          <div key={field} style={styles.field}>
            <label style={styles.label}>{label}</label>
            <input
              type="number"
              value={
                field === 'epLeft' ? asm.ep_left :
                field === 'epRight' ? asm.ep_right :
                field === 'topSr' ? asm.top_sr :
                asm.base_height
              }
              min={0}
              max={200}
              step={5}
              onChange={(e) => handleSpacerChange(field, e.target.value)}
              style={styles.input}
            />
          </div>
        ))}
      </div>

      {/* Validation summary */}
      {constraintResult && (
        <div style={styles.validationSummary}>
          {constraintResult.errorCount > 0 && (
            <div style={styles.errorSummary}>
              오류 {constraintResult.errorCount}개
            </div>
          )}
          {constraintResult.warningCount > 0 && (
            <div style={styles.warnSummary}>
              경고 {constraintResult.warningCount}개
            </div>
          )}
          {isValid && (
            <div style={styles.okSummary}>설계 유효</div>
          )}
        </div>
      )}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: '#16213e', padding: 12, overflowY: 'auto', fontSize: 12 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 8, borderBottom: '1px solid #2d3748', marginBottom: 10 },
  title: { color: '#e2e8f0', fontWeight: 700, fontSize: 13 },
  statusDot: { width: 8, height: 8, borderRadius: '50%', display: 'inline-block' },
  section: { marginBottom: 14 },
  sectionTitle: { color: '#718096', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.05em', marginBottom: 6 },
  field: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 5 },
  label: { color: '#a0aec0', fontSize: 12 },
  input: {
    background: '#1a1a2e',
    border: '1px solid #2d3748',
    borderRadius: 4,
    color: '#e2e8f0',
    padding: '3px 8px',
    fontSize: 13,
    outline: 'none',
    width: 80,
    textAlign: 'right',
  },
  buttonRow: { display: 'flex', gap: 4, flexWrap: 'wrap' },
  countBtn: {
    border: '1px solid #2d3748',
    borderRadius: 4,
    padding: '4px 10px',
    cursor: 'pointer',
    fontSize: 12,
    fontWeight: 600,
    transition: 'all 0.15s',
  },
  doorBtn: {
    border: '1px solid #2d3748',
    borderRadius: 4,
    padding: '4px 8px',
    cursor: 'pointer',
    fontSize: 11,
    transition: 'all 0.15s',
    flex: 1,
  },
  validationSummary: { marginTop: 8 },
  errorSummary: { background: '#742a2a', color: '#fc8181', borderRadius: 4, padding: '3px 8px', fontSize: 11, marginBottom: 3 },
  warnSummary: { background: '#744210', color: '#f6e05e', borderRadius: 4, padding: '3px 8px', fontSize: 11, marginBottom: 3 },
  okSummary: { background: '#1c4532', color: '#68d391', borderRadius: 4, padding: '3px 8px', fontSize: 11 },
}

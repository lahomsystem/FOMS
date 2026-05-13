/**
 * ComponentTreePanel — UUID 기반 부재 계층 트리/목록.
 * DK-B6: component tree 표시, 클릭으로 선택.
 */

import { useDesignerStore } from '../stores/designerStore'
import type { Component, ComponentKind } from '../domain/ontologyTypes'
import { COMPONENT_KIND_META } from '../domain/componentCatalog'

const KIND_ICONS: Record<ComponentKind, string> = {
  panel: '🪵',
  ep: '|',
  sr: '—',
  base: '▬',
  shelf: '━',
  door: '🚪',
  drawer: '📦',
  box: '⬛',
  hardware: '⚙️',
  cutout: '✂️',
}

interface ComponentRowProps {
  comp: Component
  selected: boolean
  onSelect: (id: string) => void
}

function ComponentRow({ comp, selected, onSelect }: ComponentRowProps) {
  const icon = KIND_ICONS[comp.kind] ?? '◻'
  const meta = COMPONENT_KIND_META[comp.kind]

  return (
    <div
      onClick={() => onSelect(comp.id)}
      style={{
        ...styles.row,
        background: selected ? '#2d3a6e' : 'transparent',
        borderLeft: selected ? '2px solid #667eea' : '2px solid transparent',
      }}
    >
      <span style={styles.icon}>{icon}</span>
      <div style={styles.info}>
        <div style={styles.name}>{comp.name}</div>
        <div style={styles.meta}>
          <span style={styles.kindBadge}>{comp.kind}</span>
          <span style={styles.dims}>
            {comp.dimensions.width}×{comp.dimensions.height}×{comp.dimensions.depth}
          </span>
        </div>
      </div>
    </div>
  )
}

export function ComponentTreePanel() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const setSelected = useDesignerStore((s) => s.setSelectedComponent)
  const asm = design.assembly

  // Group by module
  const moduleMap = new Map<string, Component[]>()
  const assemblyLevel: Component[] = []

  for (const comp of design.components) {
    if (comp.parent_id && comp.parent_id !== asm.id) {
      const list = moduleMap.get(comp.parent_id) ?? []
      list.push(comp)
      moduleMap.set(comp.parent_id, list)
    } else {
      assemblyLevel.push(comp)
    }
  }

  const totalComponents = design.components.length

  return (
    <div style={styles.panel}>
      <div style={styles.header}>
        <span style={styles.title}>부재 목록</span>
        <span style={styles.count}>{totalComponents}개</span>
      </div>

      {/* Assembly-level components */}
      {assemblyLevel.length > 0 && (
        <div style={styles.group}>
          <div style={styles.groupHeader}>Assembly ({asm.name})</div>
          {assemblyLevel.map((comp) => (
            <ComponentRow
              key={comp.id}
              comp={comp}
              selected={selectedId === comp.id}
              onSelect={setSelected}
            />
          ))}
        </div>
      )}

      {/* Per-module components */}
      {asm.modules.map((mod, modIdx) => {
        const modComps = moduleMap.get(mod.id) ?? []
        if (!modComps.length) return null
        return (
          <div key={mod.id} style={styles.group}>
            <div style={styles.groupHeader}>
              {mod.name} ({mod.dimensions.width}mm)
            </div>
            {modComps.map((comp) => (
              <ComponentRow
                key={comp.id}
                comp={comp}
                selected={selectedId === comp.id}
                onSelect={setSelected}
              />
            ))}
          </div>
        )
      })}
    </div>
  )
}

const styles: Record<string, React.CSSProperties> = {
  panel: { background: '#16213e', padding: 8, overflowY: 'auto', flex: 1, fontSize: 12 },
  header: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', paddingBottom: 6, borderBottom: '1px solid #2d3748', marginBottom: 8 },
  title: { color: '#e2e8f0', fontWeight: 700, fontSize: 12 },
  count: { color: '#718096', fontSize: 11 },
  group: { marginBottom: 10 },
  groupHeader: { color: '#718096', fontSize: 10, fontWeight: 700, textTransform: 'uppercase', letterSpacing: '0.04em', paddingBottom: 4, marginBottom: 2, borderBottom: '1px solid #1a1a2e' },
  row: {
    display: 'flex',
    alignItems: 'center',
    gap: 6,
    padding: '4px 6px',
    borderRadius: 4,
    cursor: 'pointer',
    marginBottom: 1,
    transition: 'background 0.1s',
  },
  icon: { fontSize: 12, minWidth: 16, textAlign: 'center' },
  info: { flex: 1, minWidth: 0 },
  name: { color: '#e2e8f0', fontSize: 11, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' },
  meta: { display: 'flex', alignItems: 'center', gap: 4, marginTop: 1 },
  kindBadge: { color: '#667eea', fontSize: 9, background: '#1a1a2e', borderRadius: 3, padding: '0 4px' },
  dims: { color: '#4a5568', fontSize: 9, fontFamily: 'monospace' },
}

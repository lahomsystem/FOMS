import { useRef } from 'react'
import * as THREE from 'three'
import { useDesignerStore } from '../stores/designerStore'
import { DimensionLines } from './DimensionLines'
import { SelectionGizmo } from './SelectionGizmo'
import type { DesignComponent } from '../domain/designTypes'

const MM = 0.001

interface PanelMeshProps {
  component: DesignComponent
  selected: boolean
  onSelect: (id: string) => void
}

function PanelMesh({ component: c, selected, onSelect }: PanelMeshProps) {
  const ref = useRef<THREE.Mesh>(null)
  const w = c.width * MM
  const h = c.height * MM
  const d = c.depth * MM
  const px = c.position.x * MM + w / 2
  const py = c.position.y * MM + h / 2
  const pz = c.position.z * MM + d / 2

  return (
    <mesh
      ref={ref}
      position={[px, py, pz]}
      onClick={(e) => { e.stopPropagation(); onSelect(c.id) }}
    >
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial
        color={selected ? '#667eea' : '#d4a574'}
        opacity={0.9}
        transparent
        roughness={0.6}
        metalness={0.1}
      />
    </mesh>
  )
}

/** Renders the full cabinet scene with all components. */
export function CabinetScene() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const setSelected = useDesignerStore((s) => s.setSelectedComponent)

  const w = design.cabinet.width * MM
  const h = design.cabinet.height * MM
  const d = design.cabinet.depth * MM

  return (
    <group>
      {/* Cabinet outline wireframe */}
      <lineSegments position={[w / 2, h / 2, d / 2]}>
        <edgesGeometry args={[new THREE.BoxGeometry(w, h, d)]} />
        <lineBasicMaterial color="#4a5568" />
      </lineSegments>

      {/* Components */}
      {design.components.map((comp) => (
        <PanelMesh
          key={comp.id}
          component={comp}
          selected={selectedId === comp.id}
          onSelect={setSelected}
        />
      ))}

      {/* Selection gizmo – rendered on top of selected component */}
      {selectedId && (() => {
        const sel = design.components.find((c) => c.id === selectedId)
        return sel ? <SelectionGizmo key={`gizmo-${sel.id}`} component={sel} /> : null
      })()}

      {/* Dimension lines */}
      <DimensionLines cabinet={design.cabinet} />

      {/* Floor grid reference */}
      <gridHelper
        args={[4, 20, '#2d3748', '#2d3748']}
        position={[w / 2, -0.01, d / 2]}
      />
    </group>
  )
}

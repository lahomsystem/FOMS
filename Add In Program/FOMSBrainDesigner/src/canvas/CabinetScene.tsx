/**
 * FOMS Brain Design Kernel V1 — CabinetScene (DK-B5 migration)
 *
 * Renders schema v2 DesignGraph: each Component is rendered individually
 * by kind/role. Selection is by component UUID.
 */

import { useRef } from 'react'
import * as THREE from 'three'
import { useDesignerStore } from '../stores/designerStore'
import { DimensionLines } from './DimensionLines'
import { SelectionGizmo } from './SelectionGizmo'
import type { Component, ComponentKind } from '../domain/ontologyTypes'

const MM = 0.001  // convert mm → Three.js units (metres)

// ──────────────────────────────────────────────────────────
// Color palette by component kind
// ──────────────────────────────────────────────────────────

const KIND_COLORS: Record<ComponentKind, string> = {
  panel:    '#d4a574',  // warm wood
  ep:       '#c9956c',  // darker wood
  sr:       '#b8c4d0',  // light grey blue
  base:     '#9aab8f',  // muted green
  shelf:    '#e0c9a4',  // light wood
  door:     '#7eb3d8',  // blue (glass-like)
  drawer:   '#a0c4a0',  // green
  box:      '#f0e6d3',  // very light
  hardware: '#8a9ab0',  // steel
  cutout:   '#ff8888',  // red (void)
}

const SELECTED_COLOR = '#667eea'  // purple highlight

// ──────────────────────────────────────────────────────────
// Single component mesh
// ──────────────────────────────────────────────────────────

interface ComponentMeshProps {
  component: Component
  selected: boolean
  onSelect: (id: string) => void
}

function ComponentMesh({ component: c, selected, onSelect }: ComponentMeshProps) {
  const ref = useRef<THREE.Mesh>(null)
  const w = c.dimensions.width * MM
  const h = c.dimensions.height * MM
  const d = c.dimensions.depth * MM
  // Center position: Three.js box is centered, so offset by half-dims
  const px = c.position.x * MM + w / 2
  const py = c.position.y * MM + h / 2
  const pz = c.position.z * MM + d / 2

  const color = selected ? SELECTED_COLOR : (KIND_COLORS[c.kind] ?? '#cccccc')
  const opacity = c.kind === 'door' ? 0.6 : (c.kind === 'cutout' ? 0.4 : 0.88)

  return (
    <mesh
      ref={ref}
      position={[px, py, pz]}
      onClick={(e) => { e.stopPropagation(); onSelect(c.id) }}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial
        color={color}
        opacity={opacity}
        transparent={opacity < 1}
        roughness={c.kind === 'door' ? 0.1 : 0.7}
        metalness={c.kind === 'hardware' ? 0.6 : 0.05}
        wireframe={false}
      />
    </mesh>
  )
}

// ──────────────────────────────────────────────────────────
// Assembly outline wireframe
// ──────────────────────────────────────────────────────────

function AssemblyOutline() {
  const design = useDesignerStore((s) => s.design)
  const asm = design.assembly
  const w = asm.dimensions.width * MM
  const h = asm.dimensions.height * MM
  const d = asm.dimensions.depth * MM

  return (
    <lineSegments position={[w / 2, h / 2, d / 2]}>
      <edgesGeometry args={[new THREE.BoxGeometry(w, h, d)]} />
      <lineBasicMaterial color="#4a5568" linewidth={2} />
    </lineSegments>
  )
}

// ──────────────────────────────────────────────────────────
// Main scene
// ──────────────────────────────────────────────────────────

/** Renders the full cabinet scene with schema v2 DesignGraph components. */
export function CabinetScene() {
  const design = useDesignerStore((s) => s.design)
  const selectedId = useDesignerStore((s) => s.selectedComponentId)
  const setSelected = useDesignerStore((s) => s.setSelectedComponent)

  const asm = design.assembly
  const w = asm.dimensions.width * MM
  const h = asm.dimensions.height * MM
  const d = asm.dimensions.depth * MM

  const selectedComponent = selectedId
    ? design.components.find(c => c.id === selectedId) ?? null
    : null

  // Render order: structural first (ep, base, sr, panels), then doors/drawers on top
  const structural = design.components.filter(c =>
    ['panel', 'ep', 'sr', 'base', 'shelf', 'box'].includes(c.kind),
  )
  const overlay = design.components.filter(c =>
    ['door', 'drawer', 'hardware', 'cutout'].includes(c.kind),
  )

  return (
    <group>
      {/* Assembly outline */}
      <AssemblyOutline />

      {/* Structural components */}
      {structural.map((comp) => (
        <ComponentMesh
          key={comp.id}
          component={comp}
          selected={selectedId === comp.id}
          onSelect={setSelected}
        />
      ))}

      {/* Overlay components (doors, drawers) */}
      {overlay.map((comp) => (
        <ComponentMesh
          key={comp.id}
          component={comp}
          selected={selectedId === comp.id}
          onSelect={setSelected}
        />
      ))}

      {/* Selection gizmo on selected component */}
      {selectedComponent && (
        <SelectionGizmo key={`gizmo-${selectedComponent.id}`} component={selectedComponent} />
      )}

      {/* Dimension lines */}
      <DimensionLines />

      {/* Floor grid */}
      <gridHelper
        args={[4, 20, '#2d3748', '#2d3748']}
        position={[w / 2, -0.01, d / 2]}
      />
    </group>
  )
}

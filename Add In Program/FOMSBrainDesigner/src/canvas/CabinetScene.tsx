/**
 * FOMS Brain PG-B9 — CabinetScene (LEGO Workbench update)
 *
 * Renders schema v2 DesignGraph: each Component is rendered individually.
 * PG-B9 additions: hover highlight, white-theme floor grid, background deselect.
 */

import { useRef, useState } from 'react'
import * as THREE from 'three'
import { useDesignerStore } from '../stores/designerStore'
import { DimensionLines } from './DimensionLines'
import { SelectionGizmo } from './SelectionGizmo'
import type { Component, ComponentKind } from '../domain/ontologyTypes'
import {
  createShelfPlacementComponent,
  createDoorPlacementComponent,
  createCutoutPlacementComponent,
} from '../domain/blockPlacement'

const MM = 0.001  // convert mm → Three.js units (metres)

// ──────────────────────────────────────────────────────────
// Color palette by component kind
// ──────────────────────────────────────────────────────────

const KIND_COLORS: Record<ComponentKind, string> = {
  panel:    '#c8a87a',  // warm wood (white theme — slightly deeper)
  ep:       '#b8845c',  // darker wood
  sr:       '#a0b4c4',  // grey blue
  base:     '#8a9b82',  // muted green
  shelf:    '#d8bb8e',  // light wood
  door:     '#6ea4cc',  // blue (glass-like)
  drawer:   '#88b488',  // green
  box:      '#e8d8c0',  // very light
  hardware: '#7a8a9e',  // steel
  cutout:   '#e06060',  // red (void)
}

const SELECTED_COLOR = '#5a67d8'  // FOMS accent purple
const HOVER_COLOR = '#7c8ef0'     // lighter purple for hover

// ──────────────────────────────────────────────────────────
// Single component mesh
// ──────────────────────────────────────────────────────────

interface ComponentMeshProps {
  component: Component
  selected: boolean
  multiSelected: boolean
  onSelect: (id: string, ctrlKey: boolean) => void
}

const MULTI_SELECT_COLOR = '#9f7aea'   // soft purple for multi-selected

function ComponentMesh({ component: c, selected, multiSelected, onSelect }: ComponentMeshProps) {
  const ref = useRef<THREE.Mesh>(null)
  const [hovered, setHovered] = useState(false)

  const w = c.dimensions.width * MM
  const h = c.dimensions.height * MM
  const d = c.dimensions.depth * MM
  const px = c.position.x * MM + w / 2
  const py = c.position.y * MM + h / 2
  const pz = c.position.z * MM + d / 2

  const baseColor = KIND_COLORS[c.kind] ?? '#cccccc'
  const color = selected ? SELECTED_COLOR : multiSelected ? MULTI_SELECT_COLOR : (hovered ? HOVER_COLOR : baseColor)
  const opacity = c.kind === 'door' ? 0.65 : (c.kind === 'cutout' ? 0.4 : 0.92)

  return (
    <mesh
      ref={ref}
      position={[px, py, pz]}
      onClick={(e) => { e.stopPropagation(); onSelect(c.id, e.ctrlKey || e.metaKey) }}
      onPointerOver={(e) => { e.stopPropagation(); setHovered(true) }}
      onPointerOut={() => setHovered(false)}
      castShadow
      receiveShadow
    >
      <boxGeometry args={[w, h, d]} />
      <meshStandardMaterial
        color={color}
        opacity={opacity}
        transparent={opacity < 1}
        roughness={c.kind === 'door' ? 0.08 : 0.65}
        metalness={c.kind === 'hardware' ? 0.6 : 0.02}
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
  const selectedIds = useDesignerStore((s) => s.selectedComponentIds)
  const setSelected = useDesignerStore((s) => s.setSelectedComponent)
  const toggleMultiSelect = useDesignerStore((s) => s.toggleComponentSelection)
  const clearMultiSelection = useDesignerStore((s) => s.clearMultiSelection)
  const activeTool = useDesignerStore((s) => s.activeTool)
  const addComponent = useDesignerStore((s) => s.addComponent)
  const setActiveTool = useDesignerStore((s) => s.setActiveTool)

  function handleSelect(id: string, ctrlKey: boolean) {
    if (ctrlKey) {
      toggleMultiSelect(id)
    } else {
      clearMultiSelection()
      setSelected(id)
    }
  }

  const asm = design.assembly
  const w = asm.dimensions.width * MM
  const h = asm.dimensions.height * MM
  const d = asm.dimensions.depth * MM

  const selectedComponent = selectedId
    ? design.components.find(c => c.id === selectedId) ?? null
    : null

  function handleFloorPlaneClick() {
    const dims = design.assembly.dimensions
    if (activeTool === 'shelf') {
      addComponent(createShelfPlacementComponent(dims))
      setActiveTool('select')
      return
    }
    if (activeTool === 'door') {
      addComponent(createDoorPlacementComponent(dims))
      setActiveTool('select')
      return
    }
    if (activeTool === 'cutout') {
      addComponent(createCutoutPlacementComponent(dims))
      setActiveTool('select')
      return
    }
    if (activeTool === 'select') {
      setSelected(null)
    }
  }

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
          multiSelected={selectedIds.has(comp.id)}
          onSelect={handleSelect}
        />
      ))}

      {/* Overlay components (doors, drawers) */}
      {overlay.map((comp) => (
        <ComponentMesh
          key={comp.id}
          component={comp}
          selected={selectedId === comp.id}
          multiSelected={selectedIds.has(comp.id)}
          onSelect={handleSelect}
        />
      ))}

      {/* Selection gizmo on selected component */}
      {selectedComponent && (
        <SelectionGizmo key={`gizmo-${selectedComponent.id}`} component={selectedComponent} />
      )}

      {/* Dimension lines — 치수 도구에서만 표시 */}
      <DimensionLines visible={activeTool === 'dimension'} />

      {/* 바닥 클릭: 배치 모드(선반/도어/컷아웃) 또는 선택 해제 */}
      <mesh
        position={[w / 2, -0.02, d / 2]}
        rotation={[-Math.PI / 2, 0, 0]}
        onClick={handleFloorPlaneClick}
        receiveShadow
      >
        <planeGeometry args={[20, 20]} />
        <meshStandardMaterial color="#f0f0f0" transparent opacity={0} />
      </mesh>

      {/* Floor grid (white theme) */}
      <gridHelper
        args={[10, 40, '#c8c8c8', '#d8d8d8']}
        position={[w / 2, -0.01, d / 2]}
      />
    </group>
  )
}

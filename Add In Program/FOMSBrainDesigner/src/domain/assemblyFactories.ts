/**
 * FOMS Brain Design Kernel V1 — Assembly Factories (TypeScript frontend)
 * DK-B4: createWardrobeAssembly
 */

// Use native crypto.randomUUID (no external dependency needed)
const uuidv4 = () => crypto.randomUUID()

import type {
  DesignGraph, Assembly, Module, Component,
  Dimensions, Position3D, Constraint, Relation, DoorType,
} from './ontologyTypes'
import { SCHEMA_VERSION, ONTOLOGY_VERSION } from './ontologyTypes'

// ──────────────────────────────────────────────────────────
// Params
// ──────────────────────────────────────────────────────────

export interface WardrobeParams {
  width: number           // mm
  height: number          // mm
  depth: number           // mm
  moduleCount: number
  doorType: DoorType
  epLeft?: number         // default 50
  epRight?: number        // default 50
  epTop?: number          // default 50
  baseHeight?: number     // default 60
  topSr?: number          // default 50
  panelThickness?: number // default 18
  backThickness?: number  // default 9
  shelfCountPerModule?: number // default 2
}

const DEFAULT: Required<WardrobeParams> = {
  width: 2400,
  height: 2200,
  depth: 600,
  moduleCount: 2,
  doorType: 'sliding',
  epLeft: 50,
  epRight: 50,
  epTop: 50,
  baseHeight: 60,
  topSr: 50,
  panelThickness: 18,
  backThickness: 9,
  shelfCountPerModule: 2,
}

// ──────────────────────────────────────────────────────────
// Factory
// ──────────────────────────────────────────────────────────

export function createWardrobeAssembly(params: WardrobeParams): DesignGraph {
  const p = { ...DEFAULT, ...params }
  const t = p.panelThickness
  const bt = p.backThickness

  const assemblyId = uuidv4()
  const components: Component[] = []
  const relations: Relation[] = []
  const modules: Module[] = []

  const usableWidth = p.width - p.epLeft - p.epRight
  const baseModuleWidth = Math.floor(usableWidth / p.moduleCount)
  const lastModuleWidth = usableWidth - baseModuleWidth * (p.moduleCount - 1)
  const innerHeight = p.height - p.topSr - p.baseHeight
  const doorHeight = innerHeight - 2

  const makeComponent = (
    kind: Component['kind'],
    role: Component['role'],
    name: string,
    parentId: string | null,
    materialId: string | null,
    dims: Dimensions,
    pos: Position3D,
    formulaRefs: string[] = [],
  ): Component => ({
    id: uuidv4(),
    kind,
    role,
    name,
    parent_id: parentId,
    material_id: materialId,
    dimensions: dims,
    position: pos,
    edge_banding: { front: true, back: false, left: false, right: false },
    formula_refs: formulaRefs,
  })

  // EP Left
  components.push(makeComponent(
    'ep', 'left_ep', '좌측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.epLeft, height: p.height, depth: p.depth - bt },
    { x: 0, y: 0, z: 0 },
    ['side_panel_height'],
  ))

  // EP Right
  components.push(makeComponent(
    'ep', 'right_ep', '우측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.epRight, height: p.height, depth: p.depth - bt },
    { x: p.width - p.epRight, y: 0, z: 0 },
    ['side_panel_height'],
  ))

  // SR Top — spacer batten, not a standard PB sheet → null material (matches Python factory)
  components.push(makeComponent(
    'sr', 'top_sr', '상부 SR', assemblyId, null,
    { width: p.width - p.epLeft - p.epRight, height: p.topSr, depth: p.depth - bt },
    { x: p.epLeft, y: p.height - p.topSr, z: 0 },
  ))

  // Base — spacer structure → null material (matches Python factory)
  components.push(makeComponent(
    'base', 'base', '받침대', assemblyId, null,
    { width: p.width - p.epLeft - p.epRight, height: p.baseHeight, depth: p.depth - bt - 50 },
    { x: p.epLeft, y: 0, z: 50 },
  ))

  // Back Panel
  components.push(makeComponent(
    'panel', 'back_panel', '후판', assemblyId, 'PB_9T_BACK',
    { width: p.width, height: p.height, depth: bt },
    { x: 0, y: 0, z: p.depth - bt },
    ['back_panel_width', 'back_panel_height'],
  ))

  // Modules
  let moduleX = p.epLeft

  for (let modIdx = 0; modIdx < p.moduleCount; modIdx++) {
    const modId = uuidv4()
    const isLast = modIdx === p.moduleCount - 1
    const mw = isLast ? lastModuleWidth : baseModuleWidth
    const modComponentIds: string[] = []

    // Left side panel
    const leftSide = makeComponent(
      'panel', 'left_side', `측판L-${modIdx + 1}`, modId, 'PB_18T_WHITE',
      { width: t, height: innerHeight, depth: p.depth - bt },
      { x: moduleX, y: p.baseHeight, z: 0 },
      ['inner_height'],
    )
    components.push(leftSide)
    modComponentIds.push(leftSide.id)

    // Right side panel (only last module)
    if (isLast) {
      const rightSide = makeComponent(
        'panel', 'right_side', `측판R-${modIdx + 1}`, modId, 'PB_18T_WHITE',
        { width: t, height: innerHeight, depth: p.depth - bt },
        { x: moduleX + mw - t, y: p.baseHeight, z: 0 },
        ['inner_height'],
      )
      components.push(rightSide)
      modComponentIds.push(rightSide.id)
    }

    // Top panel
    const topPanel = makeComponent(
      'panel', 'top_panel', `상판-${modIdx + 1}`, modId, 'PB_18T_WHITE',
      { width: mw - t * 2, height: t, depth: p.depth - bt },
      { x: moduleX + t, y: p.baseHeight + innerHeight - t, z: 0 },
    )
    components.push(topPanel)
    modComponentIds.push(topPanel.id)

    // Bottom panel
    const bottomPanel = makeComponent(
      'panel', 'bottom_panel', `하판-${modIdx + 1}`, modId, 'PB_18T_WHITE',
      { width: mw - t * 2, height: t, depth: p.depth - bt },
      { x: moduleX + t, y: p.baseHeight, z: 0 },
    )
    components.push(bottomPanel)
    modComponentIds.push(bottomPanel.id)

    // Shelves
    const innerW = mw - t * 2
    const innerH = innerHeight - t * 2
    const shelfSpacing = Math.floor(innerH / (p.shelfCountPerModule + 1))

    for (let sIdx = 0; sIdx < p.shelfCountPerModule; sIdx++) {
      const shelf = makeComponent(
        'shelf', 'shelf', `선반-${modIdx + 1}-${sIdx + 1}`, modId, 'PB_18T_WHITE',
        { width: innerW, height: t, depth: p.depth - bt - 20 },
        { x: moduleX + t, y: p.baseHeight + t + shelfSpacing * (sIdx + 1), z: 0 },
        ['shelf_width'],
      )
      components.push(shelf)
      modComponentIds.push(shelf.id)
    }

    // Door
    if (p.doorType !== 'open' && doorHeight > 0) {
      let doorW = mw - 4
      if (p.doorType === 'sliding') doorW = Math.floor((mw - 4) / 2) + 2

      const door = makeComponent(
        'door', 'door', `도어-${modIdx + 1}`, modId, 'PET_DOOR_WHITE',
        { width: doorW, height: doorHeight, depth: t },
        { x: moduleX + 2, y: p.baseHeight + 1, z: -t },
        ['door_height'],
      )
      components.push(door)
      modComponentIds.push(door.id)
      relations.push({ from: door.id, to: modId, type: 'covers_front' })
    }

    const mod: Module = {
      id: modId,
      type: 'storage_box',
      name: `모듈-${modIdx + 1}`,
      dimensions: { width: mw, height: innerHeight, depth: p.depth - bt },
      position: { x: moduleX, y: p.baseHeight, z: 0 },
      component_ids: modComponentIds,
      door_type: p.doorType,
    }
    modules.push(mod)
    moduleX += mw
  }

  const assembly: Assembly = {
    id: assemblyId,
    type: 'wardrobe',
    name: '붙박이장',
    dimensions: { width: p.width, height: p.height, depth: p.depth },
    modules,
    ep_left: p.epLeft,
    ep_right: p.epRight,
    ep_top: p.epTop,
    base_height: p.baseHeight,
    top_sr: p.topSr,
    module_count: p.moduleCount,
    door_type: p.doorType,
  }

  const constraints: Constraint[] = [
    { id: 'outer_width_sum', type: 'sum_equals', severity: 'error' },
    { id: 'within_bounds', type: 'within_bounds', severity: 'error' },
    { id: 'max_size', type: 'max_size', severity: 'error' },
    { id: 'door_gap_rule', type: 'gap_rule', severity: 'error' },
    { id: 'thickness_rule', type: 'thickness_rule', severity: 'warning' },
    { id: 'no_duplicate_uuid', type: 'no_duplicate_uuid', severity: 'error' },
  ]

  return {
    schema_version: 2,
    unit: 'mm',
    assembly,
    components,
    constraints,
    relations,
    metadata: {
      source: 'assembly_factory',
      ontology_version: ONTOLOGY_VERSION,
      created_at: new Date().toISOString(),
    },
  }
}

export function createDefaultWardrobe(): DesignGraph {
  return createWardrobeAssembly(DEFAULT)
}

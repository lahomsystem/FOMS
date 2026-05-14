/**
 * FOMS Brain PG-B10 — Kitchen Factory (TypeScript frontend)
 * Mirrors Python: foms/services/designer/factories/kitchen.py
 */

import type { DesignGraph, Assembly, Module, Component, Dimensions, Position3D, DoorType } from '../ontologyTypes'
import { SCHEMA_VERSION, ONTOLOGY_VERSION } from '../ontologyTypes'

const _uuid = () => crypto.randomUUID()

function _c(
  kind: Component['kind'],
  role: Component['role'],
  name: string,
  parentId: string | null,
  matId: string | null,
  dims: Dimensions,
  pos: Position3D,
): Component {
  return { id: _uuid(), kind, role, name, parent_id: parentId, material_id: matId, dimensions: dims, position: pos, formula_refs: [] }
}

// ──────────────────────────────────────────────────────────
// Kitchen Base
// ──────────────────────────────────────────────────────────

export interface KitchenBaseParams {
  width?: number
  height?: number
  depth?: number
  module_count?: number
  door_type?: DoorType
  drawer_count?: number
  sink_cutout?: boolean
  ep_left?: number
  ep_right?: number
  panel_thickness?: number
  back_thickness?: number
  countertop_overhang?: number
}

const BASE_DEFAULT: Required<KitchenBaseParams> = {
  width: 2400, height: 820, depth: 580, module_count: 3,
  door_type: 'swing', drawer_count: 0, sink_cutout: false,
  ep_left: 18, ep_right: 18, panel_thickness: 18, back_thickness: 9, countertop_overhang: 30,
}

export function createKitchenBaseAssembly(params: KitchenBaseParams = {}): DesignGraph {
  const p = { ...BASE_DEFAULT, ...params }
  const t = p.panel_thickness
  const bt = p.back_thickness
  const assemblyId = _uuid()
  const now = new Date().toISOString()
  const COUNTERTOP = 30
  const moduleWidth = Math.floor((p.width - p.ep_left - p.ep_right) / p.module_count)
  const innerH = p.height - t

  const components: Component[] = []

  // EP Left/Right
  components.push(_c('ep', 'left_ep', '좌측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_left, height: p.height, depth: p.depth - bt }, { x: 0, y: 0, z: 0 }))
  components.push(_c('ep', 'right_ep', '우측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_right, height: p.height, depth: p.depth - bt }, { x: p.width - p.ep_right, y: 0, z: 0 }))

  // Bottom
  components.push(_c('panel', 'bottom_panel', '하판', assemblyId, 'PB_18T_WHITE',
    { width: p.width - p.ep_left - p.ep_right, height: t, depth: p.depth - bt }, { x: p.ep_left, y: 0, z: 0 }))

  // Back
  components.push(_c('panel', 'back_panel', '후판', assemblyId, 'PB_9T_BACK',
    { width: p.width - p.ep_left - p.ep_right, height: innerH, depth: bt }, { x: p.ep_left, y: t, z: p.depth - bt }))

  // Countertop (use 'panel' + 'generic' role since 'countertop' is not in types)
  components.push(_c('panel', 'generic', '상판(카운터탑)', assemblyId, null,
    { width: p.width, height: COUNTERTOP, depth: p.depth + p.countertop_overhang },
    { x: 0, y: p.height, z: -p.countertop_overhang }))

  // Modules
  const modules: Module[] = []
  for (let i = 0; i < p.module_count; i++) {
    const xPos = p.ep_left + i * moduleWidth
    const modId = _uuid()
    const modCompIds: string[] = []

    // Divider (right side, except last)
    if (i < p.module_count - 1) {
      const divId = _uuid()
      components.push({ id: divId, kind: 'panel', role: 'right_side', name: `분리판-${i + 1}`, parent_id: modId, material_id: 'PB_18T_WHITE', dimensions: { width: t, height: innerH, depth: p.depth - bt }, position: { x: xPos + moduleWidth - t, y: t, z: 0 }, formula_refs: [] })
      modCompIds.push(divId)
    }

    // Door
    if (p.door_type !== 'open') {
      const dId = _uuid()
      components.push({ id: dId, kind: 'door', role: 'door', name: `도어-${i + 1}`, parent_id: modId, material_id: 'MDF_18T_DOOR', dimensions: { width: moduleWidth - 2, height: p.height - 2, depth: t }, position: { x: xPos + 1, y: 1, z: -t }, formula_refs: [] })
      modCompIds.push(dId)
    }

    modules.push({
      id: modId, type: 'kitchen_base_module', name: `주방 하부 모듈 ${i + 1}`,
      dimensions: { width: moduleWidth, height: p.height, depth: p.depth },
      position: { x: xPos, y: 0, z: 0 },
      component_ids: modCompIds,
      door_type: p.door_type,
    })
  }

  const assembly: Assembly = {
    id: assemblyId, type: 'kitchen_base', name: '주방 하부장',
    dimensions: { width: p.width, height: p.height + COUNTERTOP, depth: p.depth },
    modules,
    ep_left: p.ep_left, ep_right: p.ep_right, ep_top: 0,
    base_height: 0, top_sr: 0,
    module_count: p.module_count, door_type: p.door_type,
  }

  return {
    schema_version: SCHEMA_VERSION, unit: 'mm',
    assembly, components, constraints: [], relations: [],
    metadata: { source: 'kitchen_base_factory_v1', ontology_version: ONTOLOGY_VERSION, created_at: now },
  }
}

// ──────────────────────────────────────────────────────────
// Kitchen Wall
// ──────────────────────────────────────────────────────────

export interface KitchenWallParams {
  width?: number
  height?: number
  depth?: number
  module_count?: number
  door_type?: DoorType
  ep_left?: number
  ep_right?: number
  panel_thickness?: number
  back_thickness?: number
}

const WALL_DEFAULT: Required<KitchenWallParams> = {
  width: 2400, height: 700, depth: 350, module_count: 3,
  door_type: 'swing', ep_left: 18, ep_right: 18, panel_thickness: 18, back_thickness: 9,
}

export function createKitchenWallAssembly(params: KitchenWallParams = {}): DesignGraph {
  const p = { ...WALL_DEFAULT, ...params }
  const t = p.panel_thickness
  const bt = p.back_thickness
  const assemblyId = _uuid()
  const now = new Date().toISOString()
  const moduleWidth = Math.floor((p.width - p.ep_left - p.ep_right) / p.module_count)
  const innerH = p.height - t - t

  const components: Component[] = []

  components.push(_c('ep', 'left_ep', '좌측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_left, height: p.height, depth: p.depth - bt }, { x: 0, y: 0, z: 0 }))
  components.push(_c('ep', 'right_ep', '우측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_right, height: p.height, depth: p.depth - bt }, { x: p.width - p.ep_right, y: 0, z: 0 }))
  components.push(_c('panel', 'top_panel', '상판', assemblyId, 'PB_18T_WHITE',
    { width: p.width - p.ep_left - p.ep_right, height: t, depth: p.depth - bt }, { x: p.ep_left, y: p.height - t, z: 0 }))
  components.push(_c('panel', 'bottom_panel', '하판', assemblyId, 'PB_18T_WHITE',
    { width: p.width - p.ep_left - p.ep_right, height: t, depth: p.depth - bt }, { x: p.ep_left, y: 0, z: 0 }))
  components.push(_c('panel', 'back_panel', '후판', assemblyId, 'PB_9T_BACK',
    { width: p.width - p.ep_left - p.ep_right, height: innerH, depth: bt }, { x: p.ep_left, y: t, z: p.depth - bt }))

  const modules: Module[] = []
  for (let i = 0; i < p.module_count; i++) {
    const xPos = p.ep_left + i * moduleWidth
    const modId = _uuid()
    const modCompIds: string[] = []

    if (i < p.module_count - 1) {
      const divId = _uuid()
      components.push({ id: divId, kind: 'panel', role: 'right_side', name: `분리판-${i + 1}`, parent_id: modId, material_id: 'PB_18T_WHITE', dimensions: { width: t, height: innerH, depth: p.depth - bt }, position: { x: xPos + moduleWidth - t, y: t, z: 0 }, formula_refs: [] })
      modCompIds.push(divId)
    }

    if (p.door_type !== 'open') {
      const dId = _uuid()
      components.push({ id: dId, kind: 'door', role: 'door', name: `도어-${i + 1}`, parent_id: modId, material_id: 'MDF_18T_DOOR', dimensions: { width: moduleWidth - 2, height: p.height - 2, depth: t }, position: { x: xPos + 1, y: 1, z: -t }, formula_refs: [] })
      modCompIds.push(dId)
    }

    modules.push({
      id: modId, type: 'kitchen_wall_module', name: `주방 상부 모듈 ${i + 1}`,
      dimensions: { width: moduleWidth, height: p.height, depth: p.depth },
      position: { x: xPos, y: 0, z: 0 },
      component_ids: modCompIds,
      door_type: p.door_type,
    })
  }

  const assembly: Assembly = {
    id: assemblyId, type: 'kitchen_wall', name: '주방 상부장',
    dimensions: { width: p.width, height: p.height, depth: p.depth },
    modules,
    ep_left: p.ep_left, ep_right: p.ep_right, ep_top: 0,
    base_height: 0, top_sr: 0,
    module_count: p.module_count, door_type: p.door_type,
  }

  return {
    schema_version: SCHEMA_VERSION, unit: 'mm',
    assembly, components, constraints: [], relations: [],
    metadata: { source: 'kitchen_wall_factory_v1', ontology_version: ONTOLOGY_VERSION, created_at: now },
  }
}

export const createDefaultKitchenBase = () => createKitchenBaseAssembly(BASE_DEFAULT)
export const createDefaultKitchenWall = () => createKitchenWallAssembly(WALL_DEFAULT)

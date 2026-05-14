/**
 * FOMS Brain PG-B10 — Shoe Rack Factory (TypeScript frontend)
 * Mirrors Python: foms/services/designer/factories/shoe_rack.py
 */

import type { DesignGraph, Assembly, Module, Component, Dimensions, Position3D, DoorType } from '../ontologyTypes'
import { SCHEMA_VERSION, ONTOLOGY_VERSION } from '../ontologyTypes'

const _uuid = () => crypto.randomUUID()

export interface ShoeRackParams {
  width?: number
  height?: number
  depth?: number
  tier_count?: number
  door_type?: DoorType
  has_bench?: boolean
  ep_left?: number
  ep_right?: number
  panel_thickness?: number
  back_thickness?: number
  shelf_pitch?: number
}

const DEFAULT: Required<ShoeRackParams> = {
  width: 900,
  height: 1200,
  depth: 350,
  tier_count: 4,
  door_type: 'open',
  has_bench: false,
  ep_left: 18,
  ep_right: 18,
  panel_thickness: 18,
  back_thickness: 9,
  shelf_pitch: 220,
}

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

export function createShoeRackAssembly(params: ShoeRackParams = {}): DesignGraph {
  const p = { ...DEFAULT, ...params }
  const t = p.panel_thickness
  const bt = p.back_thickness
  const assemblyId = _uuid()
  const now = new Date().toISOString()

  const innerW = p.width - p.ep_left - p.ep_right
  const components: Component[] = []
  const modComponentIds: string[] = []

  // EP Left / Right
  components.push(_c('ep', 'left_ep', '좌측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_left, height: p.height, depth: p.depth - bt }, { x: 0, y: 0, z: 0 }))
  components.push(_c('ep', 'right_ep', '우측 EP', assemblyId, 'PB_18T_WHITE',
    { width: p.ep_right, height: p.height, depth: p.depth - bt }, { x: p.width - p.ep_right, y: 0, z: 0 }))

  // Top / Bottom panels
  const topId = _uuid(); components.push({ id: topId, kind: 'panel', role: 'top_panel', name: '상판', parent_id: assemblyId, material_id: 'PB_18T_WHITE', dimensions: { width: innerW, height: t, depth: p.depth - bt }, position: { x: p.ep_left, y: p.height - t, z: 0 }, formula_refs: [] }); modComponentIds.push(topId)
  const botId = _uuid(); components.push({ id: botId, kind: 'panel', role: 'bottom_panel', name: '하판', parent_id: assemblyId, material_id: 'PB_18T_WHITE', dimensions: { width: innerW, height: t, depth: p.depth - bt }, position: { x: p.ep_left, y: 0, z: 0 }, formula_refs: [] }); modComponentIds.push(botId)

  // Back panel
  const backId = _uuid(); components.push({ id: backId, kind: 'panel', role: 'back_panel', name: '후판', parent_id: assemblyId, material_id: 'PB_9T_BACK', dimensions: { width: innerW, height: p.height, depth: bt }, position: { x: p.ep_left, y: 0, z: p.depth - bt }, formula_refs: [] }); modComponentIds.push(backId)

  // Shelves (tiers)
  for (let i = 0; i < p.tier_count; i++) {
    const yPos = t + (i + 1) * p.shelf_pitch - t / 2
    if (yPos + t > p.height - t) break
    const shelfId = _uuid()
    components.push({ id: shelfId, kind: 'shelf', role: 'shelf', name: `선반 ${i + 1}`, parent_id: assemblyId, material_id: 'PB_18T_WHITE', dimensions: { width: innerW, height: t, depth: p.depth - bt }, position: { x: p.ep_left, y: yPos, z: 0 }, formula_refs: [] })
    modComponentIds.push(shelfId)
  }

  // Bench (optional)
  if (p.has_bench) {
    const benchId = _uuid()
    components.push({ id: benchId, kind: 'shelf', role: 'generic', name: '벤치', parent_id: assemblyId, material_id: 'PB_18T_WHITE', dimensions: { width: p.width, height: t, depth: p.depth }, position: { x: 0, y: 200 - t, z: 0 }, formula_refs: [] })
    modComponentIds.push(benchId)
  }

  const module: Module = {
    id: _uuid(),
    type: 'shoe_rack_module',
    name: '신발장 모듈',
    dimensions: { width: p.width, height: p.height, depth: p.depth },
    position: { x: 0, y: 0, z: 0 },
    component_ids: modComponentIds,
    door_type: p.door_type,
  }

  const assembly: Assembly = {
    id: assemblyId,
    type: 'shoe_rack',
    name: '신발장',
    dimensions: { width: p.width, height: p.height, depth: p.depth },
    modules: [module],
    ep_left: p.ep_left,
    ep_right: p.ep_right,
    ep_top: 0,
    base_height: 0,
    top_sr: 0,
    module_count: 1,
    door_type: p.door_type,
  }

  return {
    schema_version: SCHEMA_VERSION,
    unit: 'mm',
    assembly,
    components,
    constraints: [],
    relations: [],
    metadata: { source: 'shoe_rack_factory_v1', ontology_version: ONTOLOGY_VERSION, created_at: now },
  }
}

export const createDefaultShoeRack = () => createShoeRackAssembly(DEFAULT)

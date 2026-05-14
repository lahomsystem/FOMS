/**
 * Shared LEGO block geometry → Component builders (palette + left-tool placement).
 */

import type { Component, ComponentKind, ComponentRole } from './ontologyTypes'

export interface LegoBlockDef {
  kind: ComponentKind
  role: ComponentRole
  label: string
  icon: string
  /** null = no material (e.g. cutout, sr) */
  materialId: string | null
  defaultDims: (a: { width: number; height: number; depth: number }) => {
    width: number
    height: number
    depth: number
    x: number
    y: number
    z: number
  }
}

const newId = () => crypto.randomUUID()

/** Build a Component from a palette block definition and assembly outer dimensions (mm). */
export function componentFromLegoBlockDef(
  block: LegoBlockDef,
  asm: { width: number; height: number; depth: number },
): Component {
  const dims = block.defaultDims(asm)
  return {
    id: newId(),
    kind: block.kind,
    role: block.role,
    name: block.label,
    parent_id: null,
    material_id: block.materialId,
    dimensions: { width: dims.width, height: dims.height, depth: dims.depth },
    position: { x: dims.x, y: dims.y, z: dims.z },
    formula_refs: [],
  }
}

/** All blocks shown in the right-tray LEGO palette (order preserved). */
export const LEGO_BLOCK_DEFS: LegoBlockDef[] = [
  {
    kind: 'shelf',
    role: 'shelf',
    label: '선반',
    icon: '═',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 18,
      depth: a.depth - 20,
      x: 50,
      y: Math.round(a.height / 2),
      z: 0,
    }),
  },
  {
    kind: 'drawer',
    role: 'drawer',
    label: '서랍',
    icon: '▭',
    materialId: 'MDF_18T_DOOR',
    defaultDims: (a) => ({
      width: Math.round((a.width - 100) / 2),
      height: 200,
      depth: a.depth - 20,
      x: 50,
      y: 80,
      z: 0,
    }),
  },
  {
    kind: 'sr',
    role: 'top_sr',
    label: '옷봉',
    icon: '○',
    materialId: null,
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 30,
      depth: 30,
      x: 50,
      y: Math.round(a.height * 0.6),
      z: Math.round(a.depth / 2),
    }),
  },
  {
    kind: 'door',
    role: 'door',
    label: '도어',
    icon: '🚪',
    materialId: 'MDF_18T_DOOR',
    defaultDims: (a) => ({
      width: Math.round((a.width - 100) / 2) - 2,
      height: a.height - 2,
      depth: 18,
      x: 52,
      y: 1,
      z: -18,
    }),
  },
  {
    kind: 'ep',
    role: 'left_ep',
    label: 'EP 추가',
    icon: '|',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: 18,
      height: a.height,
      depth: a.depth - 9,
      x: Math.round(a.width / 2),
      y: 0,
      z: 0,
    }),
  },
  {
    kind: 'panel',
    role: 'generic',
    label: '판재',
    icon: '▬',
    materialId: 'PB_18T_WHITE',
    defaultDims: (a) => ({
      width: a.width - 100,
      height: 18,
      depth: a.depth - 9,
      x: 50,
      y: Math.round(a.height * 0.3),
      z: 0,
    }),
  },
]

const CUTOUT_DEF: LegoBlockDef = {
  kind: 'cutout',
  role: 'generic',
  label: '컷아웃',
  icon: '✂',
  materialId: null,
  defaultDims: (a) => ({
    width: Math.max(200, Math.min(600, a.width - 200)),
    height: Math.max(200, Math.min(500, a.height - 600)),
    depth: Math.max(18, a.depth - 40),
    x: Math.round(a.width * 0.25),
    y: Math.round(a.height * 0.35),
    z: 20,
  }),
}

/** Left-tool shelf placement — same geometry as LEGO 선반. */
export function createShelfPlacementComponent(asm: { width: number; height: number; depth: number }): Component {
  const def = LEGO_BLOCK_DEFS.find((b) => b.kind === 'shelf' && b.role === 'shelf')
  if (!def) throw new Error('shelf block def missing')
  return componentFromLegoBlockDef(def, asm)
}

/** Left-tool door placement — same geometry as LEGO 도어. */
export function createDoorPlacementComponent(asm: { width: number; height: number; depth: number }): Component {
  const def = LEGO_BLOCK_DEFS.find((b) => b.kind === 'door' && b.role === 'door')
  if (!def) throw new Error('door block def missing')
  return componentFromLegoBlockDef(def, asm)
}

/** Left-tool cutout void (generic opening). */
export function createCutoutPlacementComponent(asm: { width: number; height: number; depth: number }): Component {
  return componentFromLegoBlockDef(CUTOUT_DEF, asm)
}

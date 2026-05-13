/**
 * FOMS Brain Design Kernel V1 — Component & Material Catalog
 * DK-B1: component kind / material seed 정의
 */

import type { Material, ComponentKind, ComponentRole } from './ontologyTypes'

// ──────────────────────────────────────────────────────────
// Material catalog seed
// ──────────────────────────────────────────────────────────

export const MATERIAL_CATALOG: Record<string, Material> = {
  PB_18T_WHITE: {
    id: 'PB_18T_WHITE',
    name: 'PB 18T 화이트',
    thickness: 18,
    max_width: 2440,
    max_height: 1220,
    category: 'board',
  },
  MDF_18T: {
    id: 'MDF_18T',
    name: 'MDF 18T',
    thickness: 18,
    max_width: 2440,
    max_height: 1220,
    category: 'board',
  },
  PB_9T_BACK: {
    id: 'PB_9T_BACK',
    name: 'PB 9T (후판)',
    thickness: 9,
    max_width: 2440,
    max_height: 1220,
    category: 'board',
  },
  PET_DOOR_WHITE: {
    id: 'PET_DOOR_WHITE',
    name: 'PET 도어 화이트',
    thickness: 18,
    max_width: 1000,
    max_height: 2500,
    category: 'door',
  },
  HARDWARE_RAIL: {
    id: 'HARDWARE_RAIL',
    name: '슬라이딩 레일',
    thickness: 0,
    max_width: 3000,
    max_height: 100,
    category: 'hardware',
  },
}

// ──────────────────────────────────────────────────────────
// Component kind metadata
// ──────────────────────────────────────────────────────────

export interface ComponentKindMeta {
  kind: ComponentKind
  label_ko: string
  default_material_id: string | null
  is_structural: boolean
}

export const COMPONENT_KIND_META: Record<ComponentKind, ComponentKindMeta> = {
  box: {
    kind: 'box',
    label_ko: '내부 박스',
    default_material_id: null,
    is_structural: true,
  },
  panel: {
    kind: 'panel',
    label_ko: '판재',
    default_material_id: 'PB_18T_WHITE',
    is_structural: true,
  },
  door: {
    kind: 'door',
    label_ko: '도어',
    default_material_id: 'PET_DOOR_WHITE',
    is_structural: false,
  },
  shelf: {
    kind: 'shelf',
    label_ko: '선반',
    default_material_id: 'PB_18T_WHITE',
    is_structural: false,
  },
  drawer: {
    kind: 'drawer',
    label_ko: '서랍',
    default_material_id: 'PB_18T_WHITE',
    is_structural: false,
  },
  ep: {
    kind: 'ep',
    label_ko: '엔드패널',
    default_material_id: 'PB_18T_WHITE',
    is_structural: true,
  },
  sr: {
    kind: 'sr',
    label_ko: '스카이레일',
    default_material_id: 'PB_18T_WHITE',
    is_structural: true,
  },
  base: {
    kind: 'base',
    label_ko: '받침대',
    default_material_id: 'PB_18T_WHITE',
    is_structural: true,
  },
  hardware: {
    kind: 'hardware',
    label_ko: '하드웨어',
    default_material_id: 'HARDWARE_RAIL',
    is_structural: false,
  },
  cutout: {
    kind: 'cutout',
    label_ko: '홈/개구부',
    default_material_id: null,
    is_structural: false,
  },
}

// ──────────────────────────────────────────────────────────
// Role → Kind mapping helper
// ──────────────────────────────────────────────────────────

export const ROLE_TO_KIND: Record<ComponentRole, ComponentKind> = {
  left_ep: 'ep',
  right_ep: 'ep',
  top_ep: 'ep',
  top_sr: 'sr',
  bottom_sr: 'sr',
  base: 'base',
  left_side: 'panel',
  right_side: 'panel',
  top_panel: 'panel',
  bottom_panel: 'panel',
  back_panel: 'panel',
  shelf: 'shelf',
  door: 'door',
  drawer: 'drawer',
  inner_box: 'box',
  generic: 'panel',
}

export function getMaterialForRole(role: ComponentRole): string | null {
  const kind = ROLE_TO_KIND[role]
  return COMPONENT_KIND_META[kind]?.default_material_id ?? null
}

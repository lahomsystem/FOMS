/**
 * FOMS Brain Design Kernel V1 — Atomic Ontology Types
 * schema_version: 2
 *
 * 이 파일은 DK-B1 타입 동결 기준이다. 변경 시 schema_version을 올린다.
 */

export const SCHEMA_VERSION = 2 as const
export const ONTOLOGY_VERSION = 'kernel-v1' as const

// ──────────────────────────────────────────────────────────
// Component kinds
// ──────────────────────────────────────────────────────────

export type ComponentKind =
  | 'box'
  | 'panel'
  | 'door'
  | 'shelf'
  | 'drawer'
  | 'ep'      // 엔드 패널 (end panel)
  | 'sr'      // 스카이 레일 (sky rail) — top spacer
  | 'base'    // 받침대
  | 'hardware'
  | 'cutout'

export const COMPONENT_KINDS: ComponentKind[] = [
  'box', 'panel', 'door', 'shelf', 'drawer', 'ep', 'sr', 'base', 'hardware', 'cutout',
]

export type DoorType = 'sliding' | 'swing' | 'open'

export type ComponentRole =
  | 'left_ep' | 'right_ep' | 'top_ep'
  | 'top_sr' | 'bottom_sr'
  | 'base'
  | 'left_side' | 'right_side' | 'top_panel' | 'bottom_panel' | 'back_panel'
  | 'shelf' | 'door' | 'drawer'
  | 'inner_box'
  | 'generic'

export type ConstraintSeverity = 'error' | 'warning' | 'info'

// ──────────────────────────────────────────────────────────
// Dimensions & position
// ──────────────────────────────────────────────────────────

export interface Dimensions {
  width: number   // mm (integer)
  height: number  // mm (integer)
  depth: number   // mm (integer)
}

export interface Position3D {
  x: number
  y: number
  z: number
}

export interface EdgeBanding {
  front: boolean
  back: boolean
  left: boolean
  right: boolean
}

// ──────────────────────────────────────────────────────────
// Material
// ──────────────────────────────────────────────────────────

export interface Material {
  id: string           // e.g. "PB_18T_WHITE"
  name: string
  thickness: number    // mm
  max_width: number    // mm
  max_height: number   // mm
  category: 'board' | 'door' | 'hardware' | 'other'
}

// ──────────────────────────────────────────────────────────
// Formula
// ──────────────────────────────────────────────────────────

export interface Formula {
  id: string
  expression: string   // e.g. "assembly.height - top_sr - base - gap"
  target: string       // e.g. "component.dimensions.height"
  variables: Record<string, string>  // var name → path in design graph
}

// ──────────────────────────────────────────────────────────
// Constraint
// ──────────────────────────────────────────────────────────

export interface Constraint {
  id: string
  type: 'sum_equals' | 'within_bounds' | 'max_size' | 'gap_rule' | 'thickness_rule' | 'no_duplicate_uuid'
  severity: ConstraintSeverity
  params?: Record<string, unknown>
}

export interface ConstraintViolation {
  constraint_id: string
  severity: ConstraintSeverity
  code: string
  message: string
  path: string
}

export interface ConstraintResult {
  valid: boolean
  violations: ConstraintViolation[]
}

// ──────────────────────────────────────────────────────────
// Component
// ──────────────────────────────────────────────────────────

export interface Component {
  id: string                    // UUID
  kind: ComponentKind
  role: ComponentRole
  name: string
  parent_id: string | null      // module id or assembly id
  material_id: string | null
  dimensions: Dimensions
  position: Position3D
  edge_banding?: EdgeBanding
  formula_refs?: string[]       // formula ids that govern this component
  custom_props?: Record<string, unknown>
}

// ──────────────────────────────────────────────────────────
// Module
// ──────────────────────────────────────────────────────────

export interface Module {
  id: string                    // UUID
  type: string                  // e.g. "storage_box"
  name: string
  dimensions: Dimensions
  position: Position3D
  component_ids: string[]       // references to Component.id
  door_type?: DoorType
}

// ──────────────────────────────────────────────────────────
// Assembly (schema v2 root)
// ──────────────────────────────────────────────────────────

export interface Assembly {
  id: string
  type: string                  // e.g. "wardrobe"
  name: string
  dimensions: Dimensions
  modules: Module[]
  ep_left: number               // mm
  ep_right: number              // mm
  ep_top: number                // mm
  base_height: number           // mm
  top_sr: number                // mm
  module_count: number
  door_type: DoorType
}

// ──────────────────────────────────────────────────────────
// Relation
// ──────────────────────────────────────────────────────────

export interface Relation {
  from: string     // component/module id
  to: string
  type: string     // e.g. "covers_front"
}

// ──────────────────────────────────────────────────────────
// DesignGraph (schema_version: 2)
// ──────────────────────────────────────────────────────────

export interface DesignGraph {
  schema_version: 2
  unit: 'mm'
  assembly: Assembly
  components: Component[]
  constraints: Constraint[]
  relations: Relation[]
  metadata: {
    source: string
    ontology_version: string
    created_at?: string
    updated_at?: string
  }
}

// ──────────────────────────────────────────────────────────
// Design Command
// ──────────────────────────────────────────────────────────

export type CommandIntent =
  | 'move_component'
  | 'resize_component'
  | 'set_property'
  | 'generate_layout'

export type CommandSource = 'manual_json' | 'lui' | 'gizmo' | 'touch'

export interface DesignCommand {
  command_id: string
  source: CommandSource
  intent: CommandIntent
  target: {
    component_id: string
    fallback_path?: string
  }
  operation: Record<string, unknown>
  constraints?: string[]
  preview_only?: boolean
}

// ──────────────────────────────────────────────────────────
// DesignPatch — result of applying a command
// ──────────────────────────────────────────────────────────

export interface DesignPatch {
  target_id: string
  prop_path: string
  before: unknown
  after: unknown
}

// ──────────────────────────────────────────────────────────
// CorrectionDelta
// ──────────────────────────────────────────────────────────

export interface CorrectionDelta {
  correction_id: string
  target_id: string
  before: Record<string, unknown>
  after: Record<string, unknown>
  reason: string | null
  source: 'user_manual_edit' | 'command_apply' | 'ai_suggestion'
  validated: boolean
  candidate_rule_hint?: string | null
}

// ──────────────────────────────────────────────────────────
// Legacy V1 DesignJson (kept for dual-read compat)
// ──────────────────────────────────────────────────────────

export interface LegacyDesignJson {
  schema_version: 1
  unit: 'mm'
  cabinet: { width: number; height: number; depth: number }
  components: unknown[]
  relations: unknown[]
}

export type AnyDesignJson = DesignGraph | LegacyDesignJson

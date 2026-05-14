/**
 * FOMS Brain Design Kernel V1 — Constraint Engine (TypeScript frontend)
 * DK-B3: fast client-side validation (mirrors backend rules)
 *
 * Rules:
 * 1. outer_width == ep_left + module_sum + ep_right
 * 2. component within parent boundary
 * 3. material max size
 * 4. door gap rule
 * 5. panel thickness rule
 * 6. duplicate UUID check
 */

import type { DesignGraph, ConstraintViolation, ConstraintResult, Component } from './ontologyTypes'
import { MATERIAL_CATALOG } from './componentCatalog'

const OUTER_WIDTH_TOLERANCE = 5   // mm
const MIN_PANEL_THICKNESS = 9     // mm
const MAX_PANEL_THICKNESS = 36    // mm
const MIN_DOOR_GAP = 1            // mm

// ──────────────────────────────────────────────────────────
// Individual rules
// ──────────────────────────────────────────────────────────

function checkOuterWidthSum(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const asm = graph.assembly
  if (!asm.modules.length) return violations

  const moduleSum = asm.modules.reduce((s, m) => s + m.dimensions.width, 0)
  const expected = asm.ep_left + moduleSum + asm.ep_right
  const actual = asm.dimensions.width

  if (Math.abs(actual - expected) > OUTER_WIDTH_TOLERANCE) {
    violations.push({
      constraint_id: 'outer_width_sum',
      severity: 'error',
      code: 'OUTER_WIDTH_MISMATCH',
      message: `외경 폭 불일치: 전체 ${actual}mm ≠ 좌EP(${asm.ep_left}) + 모듈합(${moduleSum}) + 우EP(${asm.ep_right}) = ${expected}mm`,
      path: 'assembly.dimensions.width',
    })
  }
  return violations
}

function checkComponentWithinParent(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const asm = graph.assembly

  for (const comp of graph.components) {
    let parentWidth: number | undefined
    let parentHeight: number | undefined

    if (comp.parent_id) {
      const parentMod = asm.modules.find(m => m.id === comp.parent_id)
      if (parentMod) {
        parentWidth = parentMod.dimensions.width
        parentHeight = parentMod.dimensions.height
      }
    } else {
      parentWidth = asm.dimensions.width
      parentHeight = asm.dimensions.height
    }

    if (parentWidth !== undefined) {
      const right = comp.position.x + comp.dimensions.width
      if (right > parentWidth + OUTER_WIDTH_TOLERANCE) {
        violations.push({
          constraint_id: 'within_bounds',
          severity: 'error',
          code: 'COMPONENT_EXCEEDS_PARENT_WIDTH',
          message: `부재 '${comp.id}' 가 부모 폭 경계를 초과 (${right} > ${parentWidth})`,
          path: `components[${comp.id}].position.x`,
        })
      }
    }

    if (parentHeight !== undefined) {
      const top = comp.position.y + comp.dimensions.height
      if (top > parentHeight + OUTER_WIDTH_TOLERANCE) {
        violations.push({
          constraint_id: 'within_bounds',
          severity: 'error',
          code: 'COMPONENT_EXCEEDS_PARENT_HEIGHT',
          message: `부재 '${comp.id}' 가 부모 높이 경계를 초과 (${top} > ${parentHeight})`,
          path: `components[${comp.id}].position.y`,
        })
      }
    }
  }
  return violations
}

function checkMaterialMaxSize(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []

  for (const comp of graph.components) {
    if (!comp.material_id) continue
    const mat = MATERIAL_CATALOG[comp.material_id]
    if (!mat || !['board', 'door'].includes(mat.category)) continue

    // Back panels are multi-piece in practice — skip max-size check
    if (comp.role === 'back_panel') continue

    const dims = [comp.dimensions.width, comp.dimensions.height, comp.dimensions.depth]
    const flatDims = dims.filter(d => d > mat.thickness).sort((a, b) => b - a)

    if (!flatDims.length) continue

    const longSide = flatDims[0]
    const shortSide = flatDims[1] ?? 0

    // Orientation-aware check: board can be rotated.
    // mat_long = larger of max_width / max_height; mat_short = smaller.
    const matLong = Math.max(mat.max_width, mat.max_height)
    const matShort = Math.min(mat.max_width, mat.max_height)

    if (longSide > matLong) {
      violations.push({
        constraint_id: 'max_size',
        severity: 'error',
        code: 'MATERIAL_MAX_SIZE_EXCEEDED',
        message: `부재 '${comp.id}' 의 최대 치수 ${longSide}mm 가 자재 최대 규격 ${matLong}mm 초과`,
        path: `components[${comp.id}].dimensions`,
      })
    } else if (shortSide > matShort) {
      violations.push({
        constraint_id: 'max_size',
        severity: 'error',
        code: 'MATERIAL_MAX_SIZE_EXCEEDED',
        message: `부재 '${comp.id}' 의 단변 ${shortSide}mm 가 자재 단변 최대 규격 ${matShort}mm 초과`,
        path: `components[${comp.id}].dimensions`,
      })
    }
  }
  return violations
}

function checkDoorGap(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const asm = graph.assembly
  const doors = graph.components.filter(c => c.kind === 'door')
  if (!doors.length) return violations

  const innerHeight = asm.dimensions.height - asm.top_sr - asm.base_height - MIN_DOOR_GAP

  for (const door of doors) {
    if (door.dimensions.height > innerHeight) {
      violations.push({
        constraint_id: 'door_gap_rule',
        severity: 'error',
        code: 'DOOR_HEIGHT_EXCEEDS_INNER',
        message: `도어 '${door.id}' 높이 ${door.dimensions.height}mm 가 내부 유효 높이 ${innerHeight}mm 초과`,
        path: `components[${door.id}].dimensions.height`,
      })
    }
  }
  return violations
}

function checkPanelThickness(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const PANEL_KINDS = new Set(['panel', 'ep', 'sr', 'base', 'shelf'])

  for (const comp of graph.components) {
    if (!PANEL_KINDS.has(comp.kind)) continue
    const dims = [comp.dimensions.width, comp.dimensions.height, comp.dimensions.depth]
    const thickness = Math.min(...dims.filter(d => d > 0))

    if (thickness < MIN_PANEL_THICKNESS) {
      violations.push({
        constraint_id: 'thickness_rule',
        severity: 'warning',
        code: 'PANEL_THICKNESS_TOO_THIN',
        message: `부재 '${comp.id}' 최소 치수 ${thickness}mm 가 권장 최소 두께 ${MIN_PANEL_THICKNESS}mm 미만`,
        path: `components[${comp.id}].dimensions`,
      })
    } else if (thickness > MAX_PANEL_THICKNESS) {
      violations.push({
        constraint_id: 'thickness_rule',
        severity: 'warning',
        code: 'PANEL_THICKNESS_TOO_THICK',
        message: `부재 '${comp.id}' 최소 치수 ${thickness}mm 가 권장 최대 두께 ${MAX_PANEL_THICKNESS}mm 초과`,
        path: `components[${comp.id}].dimensions`,
      })
    }
  }
  return violations
}

function checkDuplicateUUID(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const seen = new Set<string>()

  graph.components.forEach((comp, i) => {
    if (seen.has(comp.id)) {
      violations.push({
        constraint_id: 'no_duplicate_uuid',
        severity: 'error',
        code: 'DUPLICATE_COMPONENT_UUID',
        message: `부재 UUID '${comp.id}' 가 중복됩니다.`,
        path: `components[${i}].id`,
      })
    } else {
      seen.add(comp.id)
    }
  })
  return violations
}

function checkBasicDimensions(graph: DesignGraph): ConstraintViolation[] {
  const violations: ConstraintViolation[] = []
  const asm = graph.assembly

  for (const dim of ['width', 'height', 'depth'] as const) {
    if (asm.dimensions[dim] <= 0) {
      violations.push({
        constraint_id: 'basic_dimensions',
        severity: 'error',
        code: `ASSEMBLY_${dim.toUpperCase()}_INVALID`,
        message: `Assembly ${dim} 은 0보다 커야 합니다 (현재: ${asm.dimensions[dim]})`,
        path: `assembly.dimensions.${dim}`,
      })
    }
  }

  for (const comp of graph.components) {
    for (const dim of ['width', 'height', 'depth'] as const) {
      if (comp.dimensions[dim] <= 0) {
        violations.push({
          constraint_id: 'basic_dimensions',
          severity: 'error',
          code: 'COMPONENT_DIM_ZERO',
          message: `부재 '${comp.id}' 의 ${dim} 은 0보다 커야 합니다.`,
          path: `components[${comp.id}].dimensions.${dim}`,
        })
      }
    }
  }
  return violations
}

// ──────────────────────────────────────────────────────────
// Main validator
// ──────────────────────────────────────────────────────────

export function validateDesignGraph(graph: DesignGraph): ConstraintResult {
  const allViolations: ConstraintViolation[] = [
    ...checkBasicDimensions(graph),
    ...checkDuplicateUUID(graph),
    ...checkOuterWidthSum(graph),
    ...checkComponentWithinParent(graph),
    ...checkMaterialMaxSize(graph),
    ...checkDoorGap(graph),
    ...checkPanelThickness(graph),
  ]

  const hasErrors = allViolations.some(v => v.severity === 'error')
  return { valid: !hasErrors, violations: allViolations }
}

export function isDesignValid(graph: DesignGraph): boolean {
  return validateDesignGraph(graph).valid
}

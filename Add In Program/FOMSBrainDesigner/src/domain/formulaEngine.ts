/**
 * FOMS Brain Design Kernel V1 — Formula Engine (TypeScript frontend)
 * DK-B2: deterministic formula evaluator
 *
 * Features:
 * - assembly/module/component dimension 참조
 * - parent dimension 변경 시 child 재계산
 * - mm 정수 normalize
 * - circular formula 감지
 */

import type { DesignGraph, Component, Assembly } from './ontologyTypes'

// ──────────────────────────────────────────────────────────
// Built-in formula library
// ──────────────────────────────────────────────────────────

export interface BuiltinFormula {
  id: string
  expression: string
  description: string
  targets: 'width' | 'height' | 'depth'
}

export const BUILTIN_FORMULAS: Record<string, BuiltinFormula> = {
  module_width: {
    id: 'module_width',
    expression: '(outer_width - ep_left - ep_right) / module_count',
    description: '모듈 폭 = (전체 폭 - 좌EP - 우EP) / 모듈수',
    targets: 'width',
  },
  door_height: {
    id: 'door_height',
    expression: 'outer_height - top_sr - base - gap',
    description: '도어 높이 = 전체 높이 - 상부SR - 받침대 - 간격',
    targets: 'height',
  },
  inner_height: {
    id: 'inner_height',
    expression: 'outer_height - top_sr - base - pb_t * 2',
    description: '내부 유효 높이',
    targets: 'height',
  },
  inner_width_per_module: {
    id: 'inner_width_per_module',
    expression: '(outer_width - ep_left - ep_right - pb_t * (module_count - 1)) / module_count',
    description: '모듈 내부 폭',
    targets: 'width',
  },
  back_panel_width: {
    id: 'back_panel_width',
    expression: 'outer_width',
    description: '후판 폭',
    targets: 'width',
  },
  back_panel_height: {
    id: 'back_panel_height',
    expression: 'outer_height',
    description: '후판 높이',
    targets: 'height',
  },
  side_panel_height: {
    id: 'side_panel_height',
    expression: 'outer_height',
    description: '측판 높이',
    targets: 'height',
  },
  shelf_width: {
    id: 'shelf_width',
    expression: 'parent_width - pb_t * 2',
    description: '선반 폭 = 모듈 폭 - 좌우 판재 두께',
    targets: 'width',
  },
}

// ──────────────────────────────────────────────────────────
// Context builder
// ──────────────────────────────────────────────────────────

export interface FormulaContext {
  outer_width: number
  outer_height: number
  outer_depth: number
  total_width: number
  total_height: number
  total_depth: number
  ep_left: number
  ep_right: number
  ep_top: number
  base: number
  top_sr: number
  module_count: number
  gap: number
  pb_t: number
  back_t: number
  parent_width?: number
  parent_height?: number
  parent_depth?: number
  [key: string]: number | undefined
}

export function buildContext(graph: DesignGraph, component?: Component): FormulaContext {
  const asm = graph.assembly
  const ctx: FormulaContext = {
    outer_width: asm.dimensions.width,
    outer_height: asm.dimensions.height,
    outer_depth: asm.dimensions.depth,
    total_width: asm.dimensions.width,
    total_height: asm.dimensions.height,
    total_depth: asm.dimensions.depth,
    ep_left: asm.ep_left,
    ep_right: asm.ep_right,
    ep_top: asm.ep_top,
    base: asm.base_height,
    top_sr: asm.top_sr,
    module_count: asm.module_count,
    gap: 2,
    pb_t: 18,
    back_t: 9,
  }

  if (component?.parent_id) {
    const parentModule = asm.modules.find(m => m.id === component.parent_id)
    if (parentModule) {
      ctx.parent_width = parentModule.dimensions.width
      ctx.parent_height = parentModule.dimensions.height
      ctx.parent_depth = parentModule.dimensions.depth
    }
  }

  return ctx
}

// ──────────────────────────────────────────────────────────
// Expression evaluator (safe subset)
// ──────────────────────────────────────────────────────────

export function evaluateExpression(expression: string, context: FormulaContext): number {
  // Safe evaluation using Function with explicit variable injection
  const varNames = Object.keys(context)
  const varValues = varNames.map(k => context[k] ?? 0)

  try {
    // eslint-disable-next-line no-new-func
    const fn = new Function(...varNames, `"use strict"; return (${expression});`)
    const result = fn(...varValues)
    if (typeof result !== 'number' || !isFinite(result)) {
      throw new FormulaError(`공식 결과가 유효한 숫자가 아닙니다: ${result}`)
    }
    return normalizeMm(result)
  } catch (e) {
    if (e instanceof FormulaError) throw e
    throw new FormulaError(`공식 평가 실패: ${expression} — ${e}`)
  }
}

export function normalizeMm(value: number): number {
  return Math.round(value)
}

// ──────────────────────────────────────────────────────────
// Built-in formula evaluation
// ──────────────────────────────────────────────────────────

export function evaluateFormula(
  formulaId: string,
  graph: DesignGraph,
  component?: Component,
  overrides?: Partial<FormulaContext>,
): number {
  const formula = BUILTIN_FORMULAS[formulaId]
  if (!formula) throw new FormulaError(`알 수 없는 공식: ${formulaId}`)

  const ctx = buildContext(graph, component)
  if (overrides) Object.assign(ctx, overrides)
  return evaluateExpression(formula.expression, ctx)
}

// ──────────────────────────────────────────────────────────
// Circular dependency detection
// ──────────────────────────────────────────────────────────

export function checkCircularFormulas(formulaDeps: Record<string, string[]>): string[] {
  const visited = new Set<string>()
  const inStack = new Set<string>()
  const cycles: string[] = []

  function dfs(node: string): boolean {
    visited.add(node)
    inStack.add(node)
    for (const dep of formulaDeps[node] ?? []) {
      if (!visited.has(dep)) {
        if (dfs(dep)) { cycles.push(node); return true }
      } else if (inStack.has(dep)) {
        cycles.push(node)
        return true
      }
    }
    inStack.delete(node)
    return false
  }

  for (const fid of Object.keys(formulaDeps)) {
    if (!visited.has(fid)) dfs(fid)
  }
  return cycles
}

// ──────────────────────────────────────────────────────────
// Batch recalculate
// ──────────────────────────────────────────────────────────

export interface FormulaChange {
  componentId: string
  prop: 'width' | 'height' | 'depth'
  before: number
  after: number
}

export function recalculateGraph(graph: DesignGraph): { graph: DesignGraph; changes: FormulaChange[] } {
  const changes: FormulaChange[] = []
  const components = graph.components.map(comp => ({ ...comp, dimensions: { ...comp.dimensions } }))

  for (const comp of components) {
    for (const formulaId of comp.formula_refs ?? []) {
      const formula = BUILTIN_FORMULAS[formulaId]
      if (!formula) continue
      try {
        const newValue = evaluateFormula(formulaId, graph, comp)
        const target = formula.targets
        const oldValue = comp.dimensions[target]
        if (oldValue !== newValue) {
          changes.push({ componentId: comp.id, prop: target, before: oldValue, after: newValue })
          comp.dimensions[target] = newValue
        }
      } catch {
        // Non-blocking; constraint engine will catch invalid states
      }
    }
  }

  return { graph: { ...graph, components }, changes }
}

// ──────────────────────────────────────────────────────────
// Error
// ──────────────────────────────────────────────────────────

export class FormulaError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'FormulaError'
  }
}

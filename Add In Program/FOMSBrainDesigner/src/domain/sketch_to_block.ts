/**
 * FOMS Brain Phase C5 — Sketch → Block Converter
 *
 * Converts a 2D freehand sketch (polygon vertices drawn on canvas) into:
 *   1. An ExtrusionSpec (vertices_mm + depth_mm + plane_view).
 *   2. A Component-compatible geometry dict (for preview in the 3D canvas).
 *   3. A payload for POST /api/designer/blocks/ (save as ReusableBlock draft).
 *
 * Coordinate contract:
 *   - Canvas pixels are scaled to mm using pixelsPerMm (default: 1 px = 1 mm).
 *   - Vertex order is preserved — caller must ensure CCW or CW is consistent.
 *   - Minimum polygon area for a valid sketch: 100 × 100 mm = 10 000 mm².
 */

// ──────────────────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────────────────

export type PlaneView = 'front' | 'top' | 'side'

export interface SketchPoint {
  x: number // canvas pixels
  y: number // canvas pixels
}

export interface ExtrusionSpec {
  vertices_mm: [number, number][]
  depth_mm: number
  plane_view: PlaneView
  area_mm2: number
}

export interface SketchValidationResult {
  valid: boolean
  error?: string
  area_mm2?: number
}

export interface SaveBlockPayload {
  label_ko: string
  category: string
  geometry_json: {
    extrusion_spec: ExtrusionSpec
  }
  parameters_json: {
    depth_range: [number, number]
    area_mm2: number
  }
  auto_generated: boolean
}

// ──────────────────────────────────────────────────────────
// Constants
// ──────────────────────────────────────────────────────────

const MIN_AREA_MM2 = 10_000   // 100 × 100 mm
const MIN_VERTEX_COUNT = 3

// ──────────────────────────────────────────────────────────
// Public API
// ──────────────────────────────────────────────────────────

/**
 * Validate a freehand sketch before converting to an extrusion spec.
 */
export function validateSketch(
  points: SketchPoint[],
  pixelsPerMm = 1,
): SketchValidationResult {
  if (points.length < MIN_VERTEX_COUNT) {
    return { valid: false, error: `꼭짓점이 ${MIN_VERTEX_COUNT}개 이상 필요합니다 (현재: ${points.length})` }
  }

  const vertices = pointsToVerticesMm(points, pixelsPerMm)
  const area = shoelaceArea(vertices)

  if (area < MIN_AREA_MM2) {
    return {
      valid: false,
      error: `스케치 면적이 너무 작습니다 (${area.toFixed(0)} mm², 최소: ${MIN_AREA_MM2} mm²)`,
      area_mm2: area,
    }
  }

  return { valid: true, area_mm2: area }
}

/**
 * Convert a validated freehand sketch into an ExtrusionSpec.
 */
export function sketchToExtrusionSpec(
  points: SketchPoint[],
  depthMm: number,
  planeView: PlaneView,
  pixelsPerMm = 1,
): ExtrusionSpec {
  const vertices = pointsToVerticesMm(points, pixelsPerMm)
  const area = shoelaceArea(vertices)

  return {
    vertices_mm: vertices,
    depth_mm: depthMm,
    plane_view: planeView,
    area_mm2: area,
  }
}

/**
 * Build the payload for POST /api/designer/blocks/ from an extrusion spec.
 * The block is always saved as a user-drawn draft (auto_generated=false).
 */
export function buildSaveBlockPayload(
  labelKo: string,
  category: string,
  spec: ExtrusionSpec,
): SaveBlockPayload {
  return {
    label_ko: labelKo,
    category,
    geometry_json: {
      extrusion_spec: spec,
    },
    parameters_json: {
      depth_range: [spec.depth_mm * 0.5, spec.depth_mm * 2.0],
      area_mm2: spec.area_mm2,
    },
    auto_generated: false,
  }
}

/**
 * Build a bounding-box Component dict for 3D canvas preview of a sketch.
 * The component uses the bounding box of the polygon (not the exact shape)
 * because the canvas renderer uses box primitives.
 */
export function specToPreviewComponent(
  spec: ExtrusionSpec,
  labelKo = '스케치 블록',
): Record<string, unknown> {
  const xs = spec.vertices_mm.map((v) => v[0])
  const ys = spec.vertices_mm.map((v) => v[1])
  const minX = Math.min(...xs)
  const minY = Math.min(...ys)
  const width = Math.round(Math.max(...xs) - minX)
  const height = Math.round(Math.max(...ys) - minY)
  const depth = Math.round(spec.depth_mm)

  return {
    id: `sketch-preview-${Date.now()}`,
    kind: 'panel',
    role: 'generic',
    name: labelKo,
    dimensions: { width, height, depth },
    position: { x: Math.round(minX), y: Math.round(minY), z: 0 },
    custom_props: {
      sketch_extrusion: true,
      extrusion_spec: spec,
    },
  }
}

// ──────────────────────────────────────────────────────────
// Helpers
// ──────────────────────────────────────────────────────────

function pointsToVerticesMm(
  points: SketchPoint[],
  pixelsPerMm: number,
): [number, number][] {
  return points.map((p) => [
    Math.round(p.x / pixelsPerMm),
    Math.round(p.y / pixelsPerMm),
  ])
}

function shoelaceArea(vertices: [number, number][]): number {
  const n = vertices.length
  if (n < 3) return 0
  let total = 0
  for (let i = 0; i < n; i++) {
    const [x0, y0] = vertices[i]
    const [x1, y1] = vertices[(i + 1) % n]
    total += x0 * y1 - x1 * y0
  }
  return Math.abs(total) / 2
}

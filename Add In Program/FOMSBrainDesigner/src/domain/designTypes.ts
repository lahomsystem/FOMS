/** Design domain types for FOMS Brain AX Designer. */

export interface CabinetDimensions {
  width: number
  height: number
  depth: number
}

export interface Position3D {
  x: number
  y: number
  z: number
}

export interface DesignComponent {
  id: string
  type: 'panel' | 'shelf' | 'door' | 'drawer'
  name: string
  width: number
  height: number
  depth: number
  position: Position3D
}

export interface DesignJson {
  schema_version: number
  unit: 'mm'
  cabinet: CabinetDimensions
  components: DesignComponent[]
  relations: unknown[]
}

export interface ValidationError {
  code: string
  message: string
  path: string
}

export interface ValidationResult {
  valid: boolean
  errors: ValidationError[]
  warnings: ValidationError[]
}

export interface DesignerProject {
  id: number
  name: string
  order_id: number | null
  current_version_id: number | null
  created_at: string
  updated_at: string
}

export interface DesignerProjectVersion {
  id: number
  project_id: number
  version_no: number
  design_json: DesignJson
  validation_json: ValidationResult | null
  bom_json: unknown | null
  created_at: string
}

export interface AIRun {
  id: number
  graph_name: string
  status: 'queued' | 'running' | 'interrupt' | 'succeeded' | 'failed' | 'cancelled'
  input_json: unknown
  output_json: unknown | null
  error_text: string | null
  created_at: string
  updated_at: string
}

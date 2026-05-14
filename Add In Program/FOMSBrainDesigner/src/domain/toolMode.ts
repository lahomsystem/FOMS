/**
 * Left tool palette modes (3D editor). Kept in domain to avoid UI/store cycles.
 */
export type ToolMode =
  | 'select'
  | 'move'
  | 'dimension'
  | 'split'
  | 'shelf'
  | 'door'
  | 'cutout'
  | 'upload'

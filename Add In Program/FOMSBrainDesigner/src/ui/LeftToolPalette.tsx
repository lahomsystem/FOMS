/**
 * FOMS Brain PG-B1 — SketchUp-Like Left Tool Palette
 *
 * Vertical icon strip with tool selection and upload trigger.
 */

import { S, COLORS } from '../styles/sketchupTheme'

export type ToolMode =
  | 'select'
  | 'move'
  | 'dimension'
  | 'split'
  | 'shelf'
  | 'door'
  | 'cutout'
  | 'upload'

interface Tool {
  mode: ToolMode
  icon: string
  label: string
  shortcut: string
}

const TOOLS: Tool[] = [
  { mode: 'select',    icon: '↖',  label: '선택',      shortcut: 'S' },
  { mode: 'move',      icon: '✥',  label: '이동',      shortcut: 'M' },
  { mode: 'dimension', icon: '↔',  label: '치수',      shortcut: 'D' },
  { mode: 'split',     icon: '⊟',  label: '모듈 분할', shortcut: 'X' },
  { mode: 'shelf',     icon: '═',  label: '선반 추가', shortcut: 'L' },
  { mode: 'door',      icon: '🚪', label: '도어 추가', shortcut: 'O' },
  { mode: 'cutout',    icon: '✂',  label: '컷아웃',    shortcut: 'C' },
]

interface LeftToolPaletteProps {
  activeTool: ToolMode
  onToolChange: (tool: ToolMode) => void
  onUploadClick: () => void
}

export function LeftToolPalette({ activeTool, onToolChange, onUploadClick }: LeftToolPaletteProps) {
  return (
    <div style={S.palette}>
      {TOOLS.map(({ mode, icon, label, shortcut }) => (
        <button
          key={mode}
          title={`${label} (${shortcut})`}
          onClick={() => onToolChange(mode)}
          style={{
            ...S.toolBtn,
            ...(activeTool === mode ? S.toolBtnActive : {}),
          }}
        >
          {icon}
        </button>
      ))}

      {/* Separator */}
      <div style={{ width: '80%', height: 1, background: COLORS.toolbarBorder, margin: '4px 0' }} />

      {/* Upload drawing button */}
      <button
        title="도면 업로드 (도면 학습)"
        onClick={onUploadClick}
        style={{
          ...S.toolBtn,
          color: COLORS.accent,
          background: COLORS.accentLight,
          borderRadius: 6,
          border: `1px solid ${COLORS.accent}`,
          fontSize: 14,
        }}
      >
        📐
      </button>
    </div>
  )
}

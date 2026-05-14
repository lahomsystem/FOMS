/**
 * FOMS Brain PG-B1 — SketchUp-Like Design System Tokens
 *
 * Color, spacing, typography tokens for the white workbench UI.
 * Reference: docs/design/FOMS_BRAIN_DESIGN_SYSTEM.md
 */

import type React from 'react'

// ──────────────────────────────────────────────────────────
// Color tokens
// ──────────────────────────────────────────────────────────

export const COLORS = {
  // Canvas / workspace
  canvasBg: '#f0f0f0',         // light gray canvas
  canvasGrid: '#d8d8d8',       // grid lines
  canvasAxis: '#c0c0c0',

  // UI chrome
  toolbarBg: '#e8e8e8',        // top toolbar + left palette
  toolbarBorder: '#c8c8c8',
  panelBg: '#f5f5f5',          // right tray, side panels
  panelBorder: '#ddd',
  surfaceWhite: '#ffffff',

  // Text
  textPrimary: '#1a1a1a',
  textSecondary: '#555',
  textMuted: '#888',

  // Accent (FOMS brand purple)
  accent: '#5a67d8',           // selected / active
  accentLight: '#ebedff',      // hover / highlight
  accentDark: '#434190',

  // Status
  valid: '#38a169',            // green — valid design
  invalid: '#e53e3e',          // red — constraint error
  warning: '#d69e2e',          // orange — warning
  info: '#3182ce',             // blue — info

  // Dimension lines
  dimensionRed: '#e53e3e',     // red dimension (site constraint)
  dimensionBlack: '#1a1a1a',   // black dimension (component)
  dimensionBlue: '#3182ce',    // blue dimension (reference)
  dimensionHandles: '#5a67d8',

  // Selection
  selectionOutline: '#5a67d8',
  selectionFill: 'rgba(90, 103, 216, 0.1)',
  hoverOutline: '#3182ce',
} as const

// ──────────────────────────────────────────────────────────
// Spacing
// ──────────────────────────────────────────────────────────

export const SPACING = {
  toolbarHeight: 40,    // px
  paletteWidth: 44,     // px
  trayWidth: 240,       // px
  statusBarHeight: 24,  // px
  panelPad: 10,         // px inner padding
} as const

// ──────────────────────────────────────────────────────────
// Typography
// ──────────────────────────────────────────────────────────

export const TYPOGRAPHY = {
  fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans KR", sans-serif',
  sizeXS: 10,
  sizeSM: 11,
  sizeMD: 12,
  sizeLG: 13,
  weightNormal: 400,
  weightSemibold: 600,
  weightBold: 700,
} as const

// ──────────────────────────────────────────────────────────
// Shared style helpers
// ──────────────────────────────────────────────────────────

export const S: Record<string, React.CSSProperties> = {
  // Root wrapper
  root: {
    width: '100vw',
    height: '100vh',
    display: 'flex',
    flexDirection: 'column',
    fontFamily: TYPOGRAPHY.fontFamily,
    background: COLORS.canvasBg,
    color: COLORS.textPrimary,
    userSelect: 'none',
  },

  // Top toolbar
  toolbar: {
    height: SPACING.toolbarHeight,
    background: COLORS.toolbarBg,
    borderBottom: `1px solid ${COLORS.toolbarBorder}`,
    display: 'flex',
    alignItems: 'center',
    padding: '0 8px',
    gap: 4,
    flexShrink: 0,
    boxShadow: '0 1px 3px rgba(0,0,0,0.08)',
  },

  // Workspace row (left palette + canvas + right tray)
  workspace: {
    flex: 1,
    display: 'flex',
    overflow: 'hidden',
  },

  // Left tool palette
  palette: {
    width: SPACING.paletteWidth,
    background: COLORS.toolbarBg,
    borderRight: `1px solid ${COLORS.toolbarBorder}`,
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    padding: '4px 0',
    gap: 2,
    flexShrink: 0,
    boxShadow: '1px 0 3px rgba(0,0,0,0.06)',
  },

  // Canvas area
  canvas: {
    flex: 1,
    position: 'relative' as const,
    overflow: 'hidden',
    background: COLORS.canvasBg,
  },

  // Right property tray
  tray: {
    width: SPACING.trayWidth,
    background: COLORS.panelBg,
    borderLeft: `1px solid ${COLORS.panelBorder}`,
    display: 'flex',
    flexDirection: 'column',
    flexShrink: 0,
    overflowY: 'auto' as const,
  },

  // Status bar
  statusBar: {
    height: SPACING.statusBarHeight,
    background: COLORS.toolbarBg,
    borderTop: `1px solid ${COLORS.toolbarBorder}`,
    display: 'flex',
    alignItems: 'center',
    padding: '0 10px',
    gap: 16,
    flexShrink: 0,
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
  },

  // Tool button (palette icon buttons)
  toolBtn: {
    width: 36,
    height: 36,
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: 5,
    border: 'none',
    background: 'transparent',
    cursor: 'pointer',
    fontSize: 16,
    color: COLORS.textSecondary,
    transition: 'background 0.1s',
  },

  toolBtnActive: {
    background: COLORS.accentLight,
    color: COLORS.accent,
  },

  // Panel section header
  sectionHeader: {
    padding: '8px 10px 4px',
    fontSize: TYPOGRAPHY.sizeXS,
    fontWeight: TYPOGRAPHY.weightBold,
    color: COLORS.textMuted,
    textTransform: 'uppercase' as const,
    letterSpacing: '0.06em',
    borderBottom: `1px solid ${COLORS.panelBorder}`,
    marginBottom: 4,
  },

  // Field row in tray
  fieldRow: {
    display: 'flex',
    alignItems: 'center',
    padding: '3px 10px',
    gap: 8,
    fontSize: TYPOGRAPHY.sizeSM,
  },

  fieldLabel: {
    minWidth: 70,
    color: COLORS.textMuted,
    fontSize: TYPOGRAPHY.sizeXS,
  },

  fieldValue: {
    flex: 1,
    color: COLORS.textPrimary,
    fontWeight: TYPOGRAPHY.weightSemibold,
  },

  // Toolbar button (text buttons in top bar)
  tbBtn: {
    padding: '4px 10px',
    border: '1px solid transparent',
    borderRadius: 4,
    background: 'transparent',
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeMD,
    color: COLORS.textSecondary,
    fontWeight: TYPOGRAPHY.weightSemibold,
    transition: 'background 0.1s, border-color 0.1s',
    display: 'flex',
    alignItems: 'center',
    gap: 4,
  },

  tbBtnActive: {
    background: COLORS.accentLight,
    borderColor: COLORS.accent,
    color: COLORS.accent,
  },

  // Toolbar separator
  tbSep: {
    width: 1,
    height: 20,
    background: COLORS.toolbarBorder,
    margin: '0 4px',
  },

  // View mode tab
  viewTab: {
    padding: '3px 8px',
    border: '1px solid transparent',
    borderRadius: 4,
    background: 'transparent',
    cursor: 'pointer',
    fontSize: TYPOGRAPHY.sizeXS,
    color: COLORS.textMuted,
    fontWeight: TYPOGRAPHY.weightSemibold,
  },
}

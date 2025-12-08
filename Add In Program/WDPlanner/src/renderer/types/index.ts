export type TemplateType = 'A' | 'B' | 'C' | 'D' | 'E' | 'F' | 'G' | 'H' | 'I' | 'J' | 'K';

export type DoorType = 'sliding' | 'swing' | 'open';

// 통 규격 상수 (mm 단위) - 설계도 기반 표준 치수
export const UNIT_WIDTHS = [850, 900, 950, 1000, 1050, 1100, 1150] as const;
export const HALF_UNIT_WIDTHS = [450, 500, 550, 600] as const;
export const UNIT_HEIGHTS = [2150, 2250] as const; // 설계도에서 가장 많이 사용되는 높이
export const BASE_HEIGHT = 60; // 베이스 높이 (mm) - 설계도 표준
export const STANDARD_DEPTH = 620; // 표준 깊이 (mm) - 설계도 표준

// EP (End Panel) 표준 크기 (mm 단위) - 설계도 기반
export const EP_SIZES = {
  left: [50, 60, 75, 80, 110] as const,  // 좌측 EP 너비 옵션
  right: [50, 60, 75, 80, 110] as const, // 우측 EP 너비 옵션
  top: [70, 90, 98, 140, 190, 210] as const, // 상부 EP 높이 옵션 (괄호 값 포함)
} as const;

// 설계도에서 확인된 일반적인 전체 높이 (mm)
export const COMMON_TOTAL_HEIGHTS = [2280, 2300, 2308, 2400, 2500] as const;

export type UnitWidth = typeof UNIT_WIDTHS[number];
export type HalfUnitWidth = typeof HALF_UNIT_WIDTHS[number];
export type UnitHeight = typeof UNIT_HEIGHTS[number];

export interface ClosetUnit {
  id: string;
  width: number; // mm 단위
  height: number; // mm 단위
  depth: number; // mm 단위
  template: TemplateType;
  position: number; // X축 위치 (cm)
  isHalfUnit: boolean; // 반통 여부
  order: number; // 정렬 순서
}

export interface ClosetConfig {
  totalWidth: number; // 설치 공간 너비 (mm)
  totalHeight: number; // 천장 높이 (mm)
  totalDepth: number; // 깊이 (mm)
  units: ClosetUnit[];
  doorType: DoorType;
  color: string;
  endPanels: {
    left: boolean;
    right: boolean;
    top: boolean;
  };
  endPanelSizes: {
    left: number;  // 좌측 EP 너비 (mm, 기본 60)
    right: number; // 우측 EP 너비 (mm, 기본 60)
    top: number;   // 상부 EP 높이 (mm, 자동 계산)
  };
  ep20Options: {
    left: boolean; // 좌측 EP 20mm 옵션
    right: boolean; // 우측 EP 20mm 옵션
  };
  showDimensions: boolean;
  wireframe: boolean; // 와이어프레임 모드 (설계도 스타일)
}

export interface InternalConfig {
  shelves: number;
  drawers: number;
  hangingRod: boolean;
  hangingRodHeight?: number;
}


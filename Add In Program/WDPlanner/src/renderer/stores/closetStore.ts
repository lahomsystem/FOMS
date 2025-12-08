import { create } from 'zustand';
import { ClosetConfig, ClosetUnit, DoorType, BASE_HEIGHT, UNIT_WIDTHS, HALF_UNIT_WIDTHS, UNIT_HEIGHTS, STANDARD_DEPTH } from '../types';

interface ClosetStore extends ClosetConfig {
  setTotalWidth: (width: number) => void;
  setTotalHeight: (height: number) => void;
  updateUnit: (id: string, updates: Partial<ClosetUnit>) => void;
  addUnit: (unit: ClosetUnit) => void;
  removeUnit: (id: string) => void;
  reorderUnits: (fromIndex: number, toIndex: number) => void;
  toggleDimensions: () => void;
  toggleWireframe: () => void; // 와이어프레임 모드 토글
  setDoorType: (type: DoorType) => void;
  toggleEndPanel: (position: 'left' | 'right' | 'top') => void;
  setEndPanelSize: (position: 'left' | 'right' | 'top', size: number) => void;
  toggleEP20: (position: 'left' | 'right') => void; // EP 20mm 옵션 토글
  autoGenerateUnits: () => void; // 사이즈에 따라 자동 통 생성
  calculateUnitLayout: () => void; // 통 배치 자동 계산
  calculateTopEP: () => void; // 상부 EP 자동 계산
  // 프로젝트 저장/불러오기
  loadProject: (config: ClosetConfig) => void; // 프로젝트 데이터 로드
  getProjectData: () => ClosetConfig; // 현재 프로젝트 데이터 가져오기
  // 뷰 모드는 항상 3D로 고정
}

export const useClosetStore = create<ClosetStore>((set) => ({
  // 초기 상태 (mm 단위) - 설계도 표준 기준
  totalWidth: 3400, // 설치 공간 너비 (설계도 예시: 3400mm)
  totalHeight: 2400, // 천장 높이 (설계도 예시: 2400mm)
  totalDepth: STANDARD_DEPTH, // 깊이 (설계도 표준: 620mm)
  units: [],
  doorType: 'sliding',
  color: '#ffffff',
  endPanels: { left: true, right: true, top: true },
  endPanelSizes: { left: 50, right: 50, top: 0 }, // EP 기본값 50mm, 상부 EP는 자동 계산
  ep20Options: { left: false, right: false }, // EP 20mm 옵션
  showDimensions: true,
  wireframe: false, // 와이어프레임 모드 (3D 모드 기본값 false)

  // 액션들
  setTotalWidth: (width) => set((state) => {
    const newState = { ...state, totalWidth: width };
    // 너비 변경 시 자동 통 재생성
    setTimeout(() => {
      useClosetStore.getState().autoGenerateUnits();
    }, 0);
    return newState;
  }),

  setTotalHeight: (height) => set((state) => {
    const newState = { ...state, totalHeight: height };
    setTimeout(() => {
      // 높이 변경 시 통 높이 재계산 및 상부 EP 계산
      const baseEPSize = 50;
      const baseHeight = BASE_HEIGHT;
      const availableHeight = height - baseHeight - baseEPSize;
      
      // 사용 가능한 높이에 가장 가까운 표준 높이 선택
      const findClosestHeight = (target: number): number => {
        let closest = UNIT_HEIGHTS[0] as number;
        let minDiff = Math.abs(closest - target);
        for (let i = 1; i < UNIT_HEIGHTS.length; i++) {
          const diff = Math.abs((UNIT_HEIGHTS[i] as number) - target);
          if (diff < minDiff) {
            minDiff = diff;
            closest = UNIT_HEIGHTS[i] as number;
          }
        }
        return closest;
      };
      const newUnitHeight = findClosestHeight(availableHeight);
      
      // 모든 통의 높이 업데이트
      const updatedUnits = newState.units.map(unit => ({
        ...unit,
        height: newUnitHeight
      }));
      
      useClosetStore.setState({ units: updatedUnits });
      useClosetStore.getState().calculateTopEP();
    }, 0);
    return newState;
  }),

  updateUnit: (id, updates) => set((state) => ({
    units: state.units.map(u => u.id === id ? { ...u, ...updates } : u)
  })),

  addUnit: (unit) => set((state) => ({
    units: [...state.units, unit]
  })),

  removeUnit: (id) => set((state) => ({
    units: state.units.filter(u => u.id !== id)
  })),

  toggleDimensions: () => set((state) => ({
    showDimensions: !state.showDimensions
  })),

  toggleWireframe: () => set((state) => ({
    wireframe: !state.wireframe
  })),

  setDoorType: (type) => set((state) => {
    const newState = { ...state, doorType: type };
    // 문 타입 변경 시 자동 통 재생성
    setTimeout(() => {
      useClosetStore.getState().autoGenerateUnits();
    }, 0);
    return newState;
  }),

  toggleEndPanel: (position) => set((state) => ({
    endPanels: { ...state.endPanels, [position]: !state.endPanels[position] }
  })),

  setEndPanelSize: (position, size) => set((state) => {
    const minEPSize = 20; // EP 최소 크기 20mm
    // EP가 활성화된 경우 최소 20mm 보장
    const finalSize = (position === 'left' && state.endPanels.left) || 
                      (position === 'right' && state.endPanels.right) || 
                      (position === 'top' && state.endPanels.top)
                      ? Math.max(minEPSize, size)
                      : size;
    return {
      endPanelSizes: { ...state.endPanelSizes, [position]: finalSize }
    };
  }),

  toggleEP20: (position) => {
    // 앞면 기준으로 입력된 position을 뒷면 기준으로 매핑
    // 앞면에서 왼쪽 = 뒷면 기준 오른쪽, 앞면에서 오른쪽 = 뒷면 기준 왼쪽
    const mappedPosition = position === 'left' ? 'right' : 'left';
    
    set((state) => ({
      ep20Options: { ...state.ep20Options, [mappedPosition]: !state.ep20Options[mappedPosition] }
    }));
    // EP 20mm 옵션 변경 시 통 재생성 및 레이아웃 재계산
    setTimeout(() => {
      const store = useClosetStore.getState();
      // EP 20mm 옵션이 변경되면 통을 재생성해야 함 (EP 크기가 변경되므로)
      store.autoGenerateUnits();
      store.calculateUnitLayout();
      store.calculateTopEP();
    }, 0);
  },

  reorderUnits: (fromIndex, toIndex) => set((state) => {
    const sortedUnits = [...state.units].sort((a, b) => (a.order || 0) - (b.order || 0));
    const [moved] = sortedUnits.splice(fromIndex, 1);
    sortedUnits.splice(toIndex, 0, moved);
    // 순서 업데이트
    const reordered = sortedUnits.map((unit, index) => ({ ...unit, order: index }));
    return { units: reordered };
  }),

  autoGenerateUnits: () => {
    set((state) => {
      // mm 단위로 계산
      const baseEPSize = 50; // EP 기본 크기 50mm
      const minEPSize = 20; // EP 최소 크기 20mm
      
      // EP 20mm 옵션에 따라 EP 기본값 결정
      const leftEPBase = state.ep20Options.left ? minEPSize : baseEPSize;
      const rightEPBase = state.ep20Options.right ? minEPSize : baseEPSize;
      
      // 사용 가능한 너비 계산 (totalWidth - 좌측 EP - 우측 EP)
      const availableWidth = state.totalWidth - leftEPBase - rightEPBase;
      
      // 통 높이: totalHeight에 맞게 자동 계산
      // totalHeight에서 베이스 높이와 상부 EP를 제외한 높이를 통 높이로 사용
      const baseHeight = BASE_HEIGHT;
      const topEPBase = baseEPSize; // 상부 EP도 50mm 기본
      const availableHeight = state.totalHeight - baseHeight - topEPBase;
      
      // 사용 가능한 높이에 가장 가까운 표준 높이 선택
      const findClosestHeight = (target: number): number => {
        let closest = UNIT_HEIGHTS[0] as number;
        let minDiff = Math.abs(closest - target);
        for (let i = 1; i < UNIT_HEIGHTS.length; i++) {
          const diff = Math.abs((UNIT_HEIGHTS[i] as number) - target);
          if (diff < minDiff) {
            minDiff = diff;
            closest = UNIT_HEIGHTS[i] as number;
          }
        }
        return closest;
      };
      const unitHeight = findClosestHeight(availableHeight);
      
      // 통 너비 계산: 문 타입에 따라 통 개수 결정 후 표준 규격으로 조합
      const findBestUnitCombination = (targetWidth: number, doorType: DoorType, totalWidth: number): { fullUnits: number; halfUnit: boolean; unitWidths: number[] } => {
        // 표준편차 계산 함수
        const calculateStdDev = (values: number[]): number => {
          if (values.length === 0) return 0;
          const mean = values.reduce((sum, v) => sum + v, 0) / values.length;
          const variance = values.reduce((sum, v) => sum + Math.pow(v - mean, 2), 0) / values.length;
          return Math.sqrt(variance);
        };
        
        // 표준 통 너비 배열
        const standardWidths = [...UNIT_WIDTHS] as number[];
        const halfWidths = [...HALF_UNIT_WIDTHS] as number[];
        
        // 문 타입에 따라 통 개수 결정
        let requiredFullUnits: number;
        let requiresHalfUnit: boolean;
        
        const totalWidthCm = totalWidth / 10;
        
        if (doorType === 'swing') {
          // 여닫이 규칙 (totalWidth 기준, cm 단위)
          if (totalWidthCm >= 150 && totalWidthCm <= 180) {
            requiredFullUnits = 1;
            requiresHalfUnit = true;
          } else if (totalWidthCm >= 181 && totalWidthCm <= 241) {
            requiredFullUnits = 2;
            requiresHalfUnit = false;
          } else if (totalWidthCm >= 242 && totalWidthCm <= 302) {
            requiredFullUnits = 2;
            requiresHalfUnit = true;
          } else if (totalWidthCm >= 303 && totalWidthCm <= 363) {
            requiredFullUnits = 3;
            requiresHalfUnit = false;
          } else if (totalWidthCm >= 364 && totalWidthCm <= 424) {
            requiredFullUnits = 3;
            requiresHalfUnit = true;
          } else if (totalWidthCm >= 425 && totalWidthCm <= 485) {
            requiredFullUnits = 4;
            requiresHalfUnit = false;
          } else {
            // 범위 밖이면 기존 로직 사용
            const estimatedCount = Math.floor(targetWidth / 1000);
            requiredFullUnits = Math.max(1, estimatedCount);
            requiresHalfUnit = false;
          }
        } else if (doorType === 'sliding') {
          // 슬라이딩 규칙 (totalWidth 기준, cm 단위)
          if (totalWidthCm >= 240 && totalWidthCm <= 270) {
            requiredFullUnits = 2;
            requiresHalfUnit = false;
          } else if (totalWidthCm >= 271 && totalWidthCm <= 391) {
            requiredFullUnits = 3;
            requiresHalfUnit = false;
          } else if (totalWidthCm >= 392 && totalWidthCm <= 512) {
            requiredFullUnits = 4;
            requiresHalfUnit = false;
          } else {
            // 범위 밖이면 기존 로직 사용
            const estimatedCount = Math.floor(targetWidth / 1000);
            requiredFullUnits = Math.max(1, estimatedCount);
            requiresHalfUnit = false;
          }
        } else {
          // 오픈은 기존 로직 사용
          const estimatedCount = Math.floor(targetWidth / 1000);
          requiredFullUnits = Math.max(1, estimatedCount);
          requiresHalfUnit = false;
        }
        
        let bestCombination: { fullUnits: number; halfUnit: boolean; unitWidths: number[] } | null = null;
        
        // 결정된 통 개수에 맞춰 표준 규격으로 최적 조합 찾기
        // 모든 가능한 조합을 시도하여 가장 정확한 조합 선택
        let bestDiff = Infinity;
        
        if (requiresHalfUnit) {
          // 반통 포함: 전체 통 + 반통
          // 모든 반통 규격에 대해 시도 (큰 것부터 시도하여 더 정확한 조합 찾기)
          const sortedHalfWidths = [...halfWidths].sort((a, b) => b - a);
          for (const halfWidth of sortedHalfWidths) {
            const remainingForFull = targetWidth - halfWidth;
            
            // 모든 가능한 전체 통 조합 생성 (targetWidth를 절대 초과하지 않도록)
            const generateCombinations = (remaining: number, count: number, current: number[], maxResults: number = 1000): number[][] => {
              if (count === 0) {
                // 최종 조합의 합계 + 반통 너비가 targetWidth를 초과하지 않는지 확인
                const total = current.reduce((sum, w) => sum + w, 0) + halfWidth;
                if (total <= targetWidth) {
                  return [current];
                }
                return [];
              }
              
              // 조합이 너무 많아지면 조기 종료
              if (current.length > 0 && current.length * standardWidths.length > maxResults) {
                return [];
              }
              
              const results: number[][] = [];
              // remaining에 가장 가까운 너비부터 시도
              const sortedWidths = [...standardWidths].sort((a, b) => {
                const diffA = Math.abs(a - remaining / count);
                const diffB = Math.abs(b - remaining / count);
                return diffA - diffB;
              });
              
              for (const width of sortedWidths) {
                // 현재까지의 합계 + 이번 너비 + 반통 너비가 targetWidth를 초과하지 않는지 확인
                const currentTotal = current.reduce((sum, w) => sum + w, 0);
                if (currentTotal + width + halfWidth > targetWidth) continue;
                
                if (width <= remaining && results.length < maxResults) {
                  const subResults = generateCombinations(remaining - width, count - 1, [...current, width], maxResults);
                  results.push(...subResults);
                  if (results.length >= maxResults) break;
                }
              }
              return results;
            };
            
            const combinations = generateCombinations(remainingForFull, requiredFullUnits, [], 500);
            
            // 가장 가까운 조합 선택 (targetWidth를 절대 초과하지 않는 조합만)
            for (const fullCombo of combinations) {
              const totalUsed = fullCombo.reduce((sum, w) => sum + w, 0) + halfWidth;
              // targetWidth를 초과하는 조합은 제외
              if (totalUsed > targetWidth) continue;
              
              const diff = Math.abs(targetWidth - totalUsed);
              
              if (diff < bestDiff) {
                bestDiff = diff;
                bestCombination = {
                  fullUnits: requiredFullUnits,
                  halfUnit: true,
                  unitWidths: [...fullCombo, halfWidth]
                };
              } else if (diff === bestDiff && bestCombination) {
                // 차이가 같으면 더 균일한 조합 선택
                // 1. 통의 표준편차가 작은 것 (더 균일)
                // 2. 모든 통이 같은 크기인 조합 선호
                const currentStdDev = calculateStdDev(fullCombo);
                const bestStdDev = calculateStdDev(bestCombination.unitWidths.slice(0, -1));
                
                if (currentStdDev < bestStdDev) {
                  bestCombination = {
                    fullUnits: requiredFullUnits,
                    halfUnit: true,
                    unitWidths: [...fullCombo, halfWidth]
                  };
                } else if (currentStdDev === bestStdDev) {
                  // 표준편차가 같으면 더 큰 통이 많은 조합 선호
                  const currentMax = Math.max(...fullCombo);
                  const bestMax = Math.max(...bestCombination.unitWidths.slice(0, -1));
                  if (currentMax > bestMax) {
                    bestCombination = {
                      fullUnits: requiredFullUnits,
                      halfUnit: true,
                      unitWidths: [...fullCombo, halfWidth]
                    };
                  }
                }
              }
            }
          }
          
          // 재귀 방식이 실패하면 휴리스틱 방식 사용 (targetWidth를 초과하지 않도록)
          if (!bestCombination) {
            const fullUnitWidths: number[] = [];
            let totalUsed = 0;
            
            for (let i = 0; i < requiredFullUnits; i++) {
              const remaining = requiredFullUnits - i - 1;
              const remainingWidth = targetWidth - totalUsed;
              const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
              
              // idealWidth보다 작거나 같은 표준 규격 중 가장 큰 것 선택
              const suitableWidths = standardWidths.filter(w => w <= idealWidth);
              let closest = suitableWidths.length > 0 
                ? suitableWidths[suitableWidths.length - 1]
                : standardWidths[0];
              
              // targetWidth를 초과하지 않도록 확인
              if (totalUsed + closest > targetWidth && remaining > 0) {
                const remainingWidthForAll = targetWidth - totalUsed;
                const maxWidthPerUnit = remainingWidthForAll / (remaining + 1);
                const smallerWidths = standardWidths.filter(w => w <= maxWidthPerUnit);
                closest = smallerWidths.length > 0 
                  ? smallerWidths[smallerWidths.length - 1]
                  : standardWidths[0];
              }
              
              fullUnitWidths.push(closest);
              totalUsed += closest;
            }
            
            const remainingForHalf = targetWidth - totalUsed;
            // remainingForHalf보다 작거나 같은 반통 규격 중 가장 큰 것 선택
            const suitableHalfWidths = halfWidths.filter(w => w <= remainingForHalf);
            const closestHalf = suitableHalfWidths.length > 0 
              ? suitableHalfWidths[suitableHalfWidths.length - 1]
              : halfWidths[0];
            
            // 최종 확인: targetWidth를 초과하지 않는지
            const finalTotal = fullUnitWidths.reduce((sum, w) => sum + w, 0) + closestHalf;
            if (finalTotal <= targetWidth) {
              bestCombination = {
                fullUnits: requiredFullUnits,
                halfUnit: true,
                unitWidths: [...fullUnitWidths, closestHalf]
              };
            }
          }
        } else {
          // 전체 통만: 모든 가능한 조합 생성 (targetWidth를 절대 초과하지 않도록)
          const generateCombinations = (remaining: number, count: number, current: number[], maxResults: number = 1000): number[][] => {
            if (count === 0) {
              // 최종 조합의 합계가 targetWidth를 초과하지 않는지 확인
              const total = current.reduce((sum, w) => sum + w, 0);
              if (total <= targetWidth) {
                return [current];
              }
              return [];
            }
            
            // 조합이 너무 많아지면 조기 종료
            if (current.length > 0 && current.length * standardWidths.length > maxResults) {
              return [];
            }
            
            const results: number[][] = [];
            // remaining에 가장 가까운 너비부터 시도
            const sortedWidths = [...standardWidths].sort((a, b) => {
              const diffA = Math.abs(a - remaining / count);
              const diffB = Math.abs(b - remaining / count);
              return diffA - diffB;
            });
            
            for (const width of sortedWidths) {
              // 현재까지의 합계 + 이번 너비가 targetWidth를 초과하지 않는지 확인
              const currentTotal = current.reduce((sum, w) => sum + w, 0);
              if (currentTotal + width > targetWidth) continue;
              
              if (width <= remaining && results.length < maxResults) {
                const subResults = generateCombinations(remaining - width, count - 1, [...current, width], maxResults);
                results.push(...subResults);
                if (results.length >= maxResults) break;
              }
            }
            return results;
          };
          
          const combinations = generateCombinations(targetWidth, requiredFullUnits, [], 500);
          
          if (combinations.length > 0) {
            // 가장 가까운 조합 선택 (단, targetWidth를 초과하지 않는 조합만)
            let bestCombo = combinations[0];
            let minDiff2 = Infinity;
            
            for (const combo of combinations) {
              const totalUsed = combo.reduce((sum, w) => sum + w, 0);
              // targetWidth를 초과하지 않는 조합만 고려
              if (totalUsed <= targetWidth) {
                const diff = Math.abs(targetWidth - totalUsed);
                if (diff < minDiff2) {
                  minDiff2 = diff;
                  bestCombo = combo;
                }
              }
            }
            
            // targetWidth를 초과하지 않는 조합이 없으면 빈 배열로 설정
            if (minDiff2 === Infinity) {
              bestCombo = [];
            }
            
            if (bestCombo.length > 0) {
              bestCombination = {
                fullUnits: requiredFullUnits,
                halfUnit: false,
                unitWidths: bestCombo
              };
            }
          } else {
            // 휴리스틱 방식 (targetWidth를 초과하지 않도록, 반통 로직과 동일하게)
            const unitWidths: number[] = [];
            let totalUsed = 0;
            
            for (let i = 0; i < requiredFullUnits; i++) {
              const remaining = requiredFullUnits - i - 1;
              const remainingWidth = targetWidth - totalUsed;
              const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
              
              // 남은 공간에 맞는 최대 너비 계산 (targetWidth를 절대 초과하지 않도록)
              const maxAllowedWidth = remaining > 0 
                ? Math.floor((targetWidth - totalUsed) / (remaining + 1))
                : targetWidth - totalUsed;
              
              // idealWidth와 maxAllowedWidth 중 작은 값 이하의 표준 규격 선택
              const maxWidth = Math.min(idealWidth, maxAllowedWidth);
              const suitableWidths = standardWidths.filter(w => w <= maxWidth);
              let closest = suitableWidths.length > 0 
                ? suitableWidths[suitableWidths.length - 1]  // 가장 큰 것 선택
                : standardWidths[0];
              
              // 최종 확인: targetWidth를 초과하지 않는지 엄격히 확인
              if (totalUsed + closest > targetWidth) {
                // targetWidth를 초과하면 더 작은 규격 선택
                const remainingWidthForAll = targetWidth - totalUsed;
                const maxWidthPerUnit = remaining > 0 
                  ? Math.floor(remainingWidthForAll / (remaining + 1))
                  : remainingWidthForAll;
                const smallerWidths = standardWidths.filter(w => w <= maxWidthPerUnit);
                closest = smallerWidths.length > 0 
                  ? smallerWidths[smallerWidths.length - 1]
                  : standardWidths[0];
              }
              
              unitWidths.push(closest);
              totalUsed += closest;
            }
            
            // 최종 확인: targetWidth를 초과하지 않는지 (엄격히 확인)
            const finalTotal = unitWidths.reduce((sum, w) => sum + w, 0);
            if (finalTotal <= targetWidth) {
              bestCombination = {
                fullUnits: requiredFullUnits,
                halfUnit: false,
                unitWidths: unitWidths
              };
            } else {
              // targetWidth를 초과하면 더 작은 조합을 찾기 위해 재시도
              // 통 너비를 줄여서 다시 계산
              const excess = finalTotal - targetWidth;
              const reductionPerUnit = excess / requiredFullUnits;
              
              const adjustedUnitWidths = unitWidths.map((width) => {
                const targetWidth2 = Math.max(UNIT_WIDTHS[0] as number, width - reductionPerUnit);
                const widths = [...UNIT_WIDTHS] as number[];
                const suitableWidths = widths.filter(w => w <= targetWidth2);
                return suitableWidths.length > 0 
                  ? suitableWidths[suitableWidths.length - 1]
                  : UNIT_WIDTHS[0] as number;
              });
              
              const adjustedTotal = adjustedUnitWidths.reduce((sum, w) => sum + w, 0);
              if (adjustedTotal <= targetWidth) {
                bestCombination = {
                  fullUnits: requiredFullUnits,
                  halfUnit: false,
                  unitWidths: adjustedUnitWidths
                };
              }
            }
          }
        }
        
        // 기본값 (전체 통 1개)
        if (!bestCombination) {
          const closest = standardWidths.reduce((prev, curr) => 
            Math.abs(curr - targetWidth) < Math.abs(prev - targetWidth) ? curr : prev
          );
          bestCombination = {
            fullUnits: 1,
            halfUnit: false,
            unitWidths: [closest]
          };
        }
        
        return bestCombination;
      };
      
      const combination = findBestUnitCombination(availableWidth, state.doorType, state.totalWidth);
      
      const newUnits: ClosetUnit[] = [];
      const timestamp = Date.now();
      
      // 통 생성 (unitWidths 배열 사용)
      combination.unitWidths.forEach((width, index) => {
        const isHalfUnit = combination.halfUnit && index === combination.unitWidths.length - 1;
        newUnits.push({
          id: `unit-${timestamp}-${index}`,
          width: width,
          height: unitHeight, // 계산된 높이 사용
          depth: state.totalDepth,
          template: 'A',
          position: 0,
          isHalfUnit: isHalfUnit,
          order: index
        });
      });

      // 통이 하나도 없으면 최소 하나 생성
      if (newUnits.length === 0) {
        const minUnitWidth = Math.min(850, availableWidth);
        newUnits.push({
          id: `unit-${timestamp}-0`,
          width: minUnitWidth,
          height: unitHeight, // 계산된 높이 사용
          depth: state.totalDepth,
          template: 'A',
          position: 0,
          isHalfUnit: false,
          order: 0
        });
      }

      // EP 계산은 calculateUnitLayout과 calculateTopEP에서 처리
      // 여기서는 통만 생성하고 EP는 기본값으로 설정 (최소 20mm 보장)
      return { 
        units: newUnits,
        endPanelSizes: {
          ...state.endPanelSizes,
          left: state.endPanels.left ? Math.max(minEPSize, leftEPBase) : 0,
          right: state.endPanels.right ? Math.max(minEPSize, rightEPBase) : 0,
          top: state.endPanels.top ? Math.max(minEPSize, topEPBase) : 0
        }
      };
    });
    
    // 통 생성 후 배치 계산 및 EP 계산
    setTimeout(() => {
      useClosetStore.getState().calculateUnitLayout();
      useClosetStore.getState().calculateTopEP();
    }, 0);
  },

  calculateUnitLayout: () => {
    set((state) => {
      if (state.units.length === 0) return state;

      const baseEPSize = 50; // EP 기본 크기 50mm
      const minEPSize = 20; // EP 최소 크기 20mm
      const maxEPSize = 100; // EP 최대 크기 100mm
      
      // 50 단위로 반올림하는 함수
      const roundTo50 = (width: number): number => {
        return Math.round(width / 50) * 50;
      };
      
      // 표준 규격으로 반올림하는 함수 (50 단위 우선, 없으면 표준 규격)
      // 반통은 최대 600mm로 제한
      const roundToStandardWidth = (width: number, isHalfUnit: boolean): number => {
        // 반통은 최대 600mm로 제한
        const maxHalfWidth = 600;
        const clampedWidth = isHalfUnit ? Math.min(width, maxHalfWidth) : width;
        
        // 먼저 50 단위로 반올림
        const rounded50 = roundTo50(clampedWidth);
        
        // 50 단위 값이 표준 규격에 있으면 사용
        const widths = isHalfUnit ? [...HALF_UNIT_WIDTHS] : [...UNIT_WIDTHS];
        const widthsArray = widths as readonly number[];
        if (widthsArray.some(w => w === rounded50)) {
          return rounded50;
        }
        
        // 50 단위 값이 표준 규격에 없으면 가장 가까운 표준 규격 선택
        let closest = widths[0] as number;
        let minDiff = Math.abs(closest - clampedWidth);
        for (let i = 1; i < widths.length; i++) {
          const diff = Math.abs((widths[i] as number) - clampedWidth);
          if (diff < minDiff) {
            minDiff = diff;
            closest = widths[i] as number;
          }
        }
        
        // 50 단위 값과 표준 규격 중 더 가까운 것 선택
        if (Math.abs(rounded50 - clampedWidth) < Math.abs(closest - clampedWidth)) {
          return rounded50;
        }
        return closest;
      };
      
      // EP 기본값 결정 (EP 20mm 옵션 고려)
      const epLeftBase = state.ep20Options.left ? minEPSize : baseEPSize;
      const epRightBase = state.ep20Options.right ? minEPSize : baseEPSize;
      
      // 사용 가능한 너비 계산: totalWidth - 좌측 EP - 우측 EP
      const availableWidth = state.totalWidth - epLeftBase - epRightBase;
      
      // 통들을 균등하게 분배하되 50 단위로 조정
      // 반통과 통을 분리하여 처리
      let adjustedUnits = [...state.units];
      
      if (adjustedUnits.length > 0) {
        // 반통과 통을 분리
        let halfUnits = adjustedUnits.filter(u => u.isHalfUnit);
        let fullUnits = adjustedUnits.filter(u => !u.isHalfUnit);
        
        // 반통과 통의 개수
        const halfUnitCount = halfUnits.length;
        const fullUnitCount = fullUnits.length;
        
        // 우선순위: 통 > 반통
        // 먼저 통을 최대한 넓게 설정하고, 남은 공간으로 반통 설정
        
        let remainingWidthForHalfUnits = availableWidth;
        
        // 1. 통을 먼저 최대한 같은 규격으로 설정
        if (fullUnitCount > 0) {
          // 통에 할당할 이상적인 너비 (전체 availableWidth 사용)
          const idealFullWidth = availableWidth / fullUnitCount;
          // 통 규격 중 가장 가까운 값 선택 (반통 로직과 동일하게)
          const widths = [...UNIT_WIDTHS] as number[];
          
          // 통들이 서로 다른 크기일 수 있으므로, 통 너비의 합계가 availableWidth를 초과하지 않도록 보장
          // 먼저 각 통이 같은 크기라고 가정하고 계산
          const maxAllowedWidthPerUnit = Math.floor(availableWidth / fullUnitCount);
          const allowedWidths = widths.filter(w => w <= maxAllowedWidthPerUnit);
          
          // 통을 최대한 같은 규격으로 맞추기
          // 1단계: 모든 통이 같은 규격인 경우를 먼저 시도
          // 반통이 있으면 반통 공간을 고려하여 통 너비 선택
          let bestUniformWidth: number | null = null;
          let bestUniformTotal = 0;
          
          // 반통이 있는 경우, 반통 공간을 고려하여 통 너비 선택
          if (halfUnitCount > 0) {
            // 반통 규격 중 가장 큰 값 (600mm)을 고려하여 통 너비 선택
            const maxHalfWidth = 600;
            const halfWidths = [...HALF_UNIT_WIDTHS] as number[];
            
            // 각 통 규격에 대해 모든 통이 같은 규격일 때의 총 너비 계산
            // 반통 공간을 남겨두면서 통을 최대한 넓게 설정
            for (const width of widths) {
              const totalFullWidth = width * fullUnitCount;
              const remainingForHalf = availableWidth - totalFullWidth;
              
              // 남은 공간이 반통 최소 규격 이상이고, 반통 최대 규격 이하인 경우
              if (remainingForHalf >= (halfWidths[0] as number) && remainingForHalf <= maxHalfWidth) {
                // 반통 규격 중 가장 가까운 값이 있는지 확인
                const suitableHalfWidths = halfWidths.filter(w => w <= remainingForHalf);
                if (suitableHalfWidths.length > 0 && totalFullWidth > bestUniformTotal) {
                  bestUniformTotal = totalFullWidth;
                  bestUniformWidth = width;
                }
              } else if (remainingForHalf > maxHalfWidth) {
                // 남은 공간이 반통 최대 규격보다 크면, 통을 더 넓게 설정 가능
                // 하지만 반통은 최대 600mm이므로, 통을 더 넓게 설정
                if (totalFullWidth > bestUniformTotal) {
                  bestUniformTotal = totalFullWidth;
                  bestUniformWidth = width;
                }
              }
            }
          } else {
            // 반통이 없으면 기존 로직 사용 (가장 큰 총 너비 선택)
            for (const width of widths) {
              const totalWidth = width * fullUnitCount;
              if (totalWidth <= availableWidth && totalWidth > bestUniformTotal) {
                bestUniformTotal = totalWidth;
                bestUniformWidth = width;
              }
            }
          }
          
          // 모든 통이 같은 규격으로 설정 가능한 경우
          // bestUniformWidth가 있으면 우선 적용 (반통 공간을 고려한 최적값)
          if (bestUniformWidth !== null) {
            fullUnits = fullUnits.map((unit) => {
              return {
                ...unit,
                width: bestUniformWidth!
              };
            });
          } else if (allowedWidths.length === 0) {
            // allowedWidths가 비어있으면 통들이 서로 다른 크기를 가져야 함
            // 이 경우 조합 알고리즘을 사용하여 최적의 조합 찾기
            // 조합 생성 함수 (availableWidth를 절대 초과하지 않도록)
            const generateCombinations = (remaining: number, count: number, current: number[], maxResults: number = 1000): number[][] => {
              if (count === 0) {
                const total = current.reduce((sum, w) => sum + w, 0);
                if (total <= availableWidth) {
                  return [current];
                }
                return [];
              }
              
              if (current.length > 0 && current.length * widths.length > maxResults) {
                return [];
              }
              
              const results: number[][] = [];
              const sortedWidths = [...widths].sort((a, b) => {
                const diffA = Math.abs(a - remaining / count);
                const diffB = Math.abs(b - remaining / count);
                return diffA - diffB;
              });
              
              for (const width of sortedWidths) {
                const currentTotal = current.reduce((sum, w) => sum + w, 0);
                if (currentTotal + width > availableWidth) continue;
                
                if (width <= remaining && results.length < maxResults) {
                  const subResults = generateCombinations(remaining - width, count - 1, [...current, width], maxResults);
                  results.push(...subResults);
                  if (results.length >= maxResults) break;
                }
              }
              return results;
            };
            
            const combinations = generateCombinations(availableWidth, fullUnitCount, [], 500);
            
            if (combinations.length > 0) {
              // 가장 가까운 조합 선택
              let bestCombo = combinations[0];
              let minDiff = Infinity;
              
              for (const combo of combinations) {
                const totalUsed = combo.reduce((sum, w) => sum + w, 0);
                if (totalUsed <= availableWidth) {
                  const diff = Math.abs(availableWidth - totalUsed);
                  if (diff < minDiff) {
                    minDiff = diff;
                    bestCombo = combo;
                  }
                }
              }
              
              // 통에 할당 (큰 것부터 작은 것 순서로 정렬하여 할당)
              const sortedWidths = [...bestCombo].sort((a, b) => b - a);
              fullUnits = fullUnits.map((unit, index) => {
                return {
                  ...unit,
                  width: sortedWidths[index] || bestCombo[index] || widths[0]
                };
              });
            } else {
              // 조합이 없으면 휴리스틱 방식 사용
              const unitWidths: number[] = [];
              let totalUsed = 0;
              
              for (let i = 0; i < fullUnitCount; i++) {
                const remaining = fullUnitCount - i - 1;
                const remainingWidth = availableWidth - totalUsed;
                const maxAllowedWidth = remaining > 0 
                  ? Math.floor(remainingWidth / (remaining + 1))
                  : remainingWidth;
                const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
                const maxWidth = Math.min(idealWidth, maxAllowedWidth);
                const suitableWidths = widths.filter(w => w <= maxWidth);
                
                let closest: number;
                if (suitableWidths.length > 0) {
                  closest = suitableWidths[suitableWidths.length - 1];
                } else {
                  const roundedWidth = Math.floor(maxWidth / 50) * 50;
                  closest = Math.max(750, Math.min(roundedWidth, maxWidth));
                }
                
                if (totalUsed + closest > availableWidth) {
                  const remainingWidthForAll = availableWidth - totalUsed;
                  const maxWidthPerUnit = remaining > 0 
                    ? Math.floor(remainingWidthForAll / (remaining + 1))
                    : remainingWidthForAll;
                  const smallerWidths = widths.filter(w => w <= maxWidthPerUnit);
                  if (smallerWidths.length > 0) {
                    closest = smallerWidths[smallerWidths.length - 1];
                  } else {
                    const roundedWidth = Math.floor(maxWidthPerUnit / 50) * 50;
                    closest = Math.max(750, Math.min(roundedWidth, maxWidthPerUnit));
                  }
                }
                
                unitWidths.push(closest);
                totalUsed += closest;
              }
              
              const sortedWidths = [...unitWidths].sort((a, b) => b - a);
              fullUnits = fullUnits.map((unit, index) => {
                return {
                  ...unit,
                  width: sortedWidths[index] || unitWidths[index] || widths[0]
                };
              });
            }
          } else {
            // allowedWidths가 있으면 모든 통을 같은 크기로 설정
            // idealFullWidth에 가장 가까운 허용된 규격 선택
            let baseUnitWidth = allowedWidths[0];
            let minDiff = Math.abs(baseUnitWidth - idealFullWidth);
            
            for (const width of allowedWidths) {
              const diff = Math.abs(width - idealFullWidth);
              if (diff < minDiff) {
                minDiff = diff;
                baseUnitWidth = width;
              }
            }
            
            // 모든 통이 같은 규격으로 설정 가능한지 확인
            const totalWidth = baseUnitWidth * fullUnitCount;
            if (totalWidth <= availableWidth) {
              fullUnits = fullUnits.map((unit) => {
                return {
                  ...unit,
                  width: baseUnitWidth
                };
              });
            } else {
              // 같은 규격으로 설정 불가능하면 조합 알고리즘 사용
              // (이 경우는 거의 발생하지 않지만 안전장치)
              const unitWidths: number[] = [];
              let totalUsed = 0;
              
              for (let i = 0; i < fullUnitCount; i++) {
                const remaining = fullUnitCount - i - 1;
                const remainingWidth = availableWidth - totalUsed;
                const maxAllowedWidth = remaining > 0 
                  ? Math.floor(remainingWidth / (remaining + 1))
                  : remainingWidth;
                const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
                const maxWidth = Math.min(idealWidth, maxAllowedWidth);
                const suitableWidths = widths.filter(w => w <= maxWidth);
                
                let closest: number;
                if (suitableWidths.length > 0) {
                  closest = suitableWidths[suitableWidths.length - 1];
                } else {
                  const roundedWidth = Math.floor(maxWidth / 50) * 50;
                  closest = Math.max(750, Math.min(roundedWidth, maxWidth));
                }
                
                if (totalUsed + closest > availableWidth) {
                  const remainingWidthForAll = availableWidth - totalUsed;
                  const maxWidthPerUnit = remaining > 0 
                    ? Math.floor(remainingWidthForAll / (remaining + 1))
                    : remainingWidthForAll;
                  const smallerWidths = widths.filter(w => w <= maxWidthPerUnit);
                  if (smallerWidths.length > 0) {
                    closest = smallerWidths[smallerWidths.length - 1];
                  } else {
                    const roundedWidth = Math.floor(maxWidthPerUnit / 50) * 50;
                    closest = Math.max(750, Math.min(roundedWidth, maxWidthPerUnit));
                  }
                }
                
                unitWidths.push(closest);
                totalUsed += closest;
              }
              
              const sortedWidths = [...unitWidths].sort((a, b) => b - a);
              fullUnits = fullUnits.map((unit, index) => {
                return {
                  ...unit,
                  width: sortedWidths[index] || unitWidths[index] || widths[0]
                };
              });
            }
          }
          
          // 통이 사용한 너비 계산
          const fullUnitsWidth = fullUnits.reduce((sum, unit) => sum + unit.width, 0);
          remainingWidthForHalfUnits = availableWidth - fullUnitsWidth;
        }
        
        // 2. 남은 공간으로 반통 설정 (통이 사용한 공간을 제외)
        if (halfUnitCount > 0 && remainingWidthForHalfUnits > 0) {
          // 반통에 할당할 이상적인 너비
          const idealHalfWidth = remainingWidthForHalfUnits / halfUnitCount;
          // 반통 규격 중 가장 가까운 값 선택 (최대 600mm, remainingWidthForHalfUnits를 초과하지 않도록)
          const maxHalfWidth = 600; // 반통 최대 너비
          const widths = [...HALF_UNIT_WIDTHS] as number[];
          
          // 반통들이 서로 다른 크기일 수 있으므로, 반통 너비의 합계가 remainingWidthForHalfUnits를 초과하지 않도록 보장
          const maxAllowedWidthPerHalfUnit = Math.floor(remainingWidthForHalfUnits / halfUnitCount);
          const allowedHalfWidths = widths.filter(w => w <= Math.min(maxHalfWidth, maxAllowedWidthPerHalfUnit));
          
          let baseHalfWidth = allowedHalfWidths.length > 0 
            ? allowedHalfWidths[allowedHalfWidths.length - 1]  // 가장 큰 허용된 규격
            : widths[0];
          
          // idealHalfWidth에 가장 가까운 허용된 규격 선택
          let minDiff = Math.abs(baseHalfWidth - idealHalfWidth);
          for (const width of allowedHalfWidths) {
            const diff = Math.abs(width - idealHalfWidth);
            if (diff < minDiff) {
              minDiff = diff;
              baseHalfWidth = width;
            }
          }
          
          halfUnits = halfUnits.map((unit) => {
            return {
              ...unit,
              width: baseHalfWidth
            };
          });
        }
        
        // 통들을 원래 순서대로 합치기
        adjustedUnits = adjustedUnits.map((unit) => {
          if (unit.isHalfUnit) {
            return halfUnits.find(u => u.id === unit.id) || unit;
          } else {
            return fullUnits.find(u => u.id === unit.id) || unit;
          }
        });
        
        // 조정된 통 너비 합계 계산 및 availableWidth 준수 보장
        let totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
        
        // 통 너비 합계가 availableWidth를 초과하는 경우 즉시 조정 (반복적으로 조정하여 정확히 맞춤)
        while (totalUnitsWidth > availableWidth && adjustedUnits.length > 0) {
          const excess = totalUnitsWidth - availableWidth;
          let currentHalfUnits = adjustedUnits.filter(u => u.isHalfUnit);
          let currentFullUnits = adjustedUnits.filter(u => !u.isHalfUnit);
          
          // 초과분을 통 개수로 나눠서 각 통에서 빼기 (표준 규격 유지)
          const reductionPerUnit = excess / adjustedUnits.length;
          
          currentHalfUnits = currentHalfUnits.map((unit) => {
            const targetWidth = Math.max(HALF_UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
            const widths = [...HALF_UNIT_WIDTHS] as number[];
            const suitableWidths = widths.filter(w => w <= targetWidth && w <= 600);
            return {
              ...unit,
              width: suitableWidths.length > 0 ? suitableWidths[suitableWidths.length - 1] : HALF_UNIT_WIDTHS[0] as number
            };
          });
          
          currentFullUnits = currentFullUnits.map((unit) => {
            const targetWidth = Math.max(UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
            const widths = [...UNIT_WIDTHS] as number[];
            const suitableWidths = widths.filter(w => w <= targetWidth);
            return {
              ...unit,
              width: suitableWidths.length > 0 ? suitableWidths[suitableWidths.length - 1] : UNIT_WIDTHS[0] as number
            };
          });
          
          adjustedUnits = adjustedUnits.map((unit) => {
            if (unit.isHalfUnit) {
              return currentHalfUnits.find(u => u.id === unit.id) || unit;
            } else {
              return currentFullUnits.find(u => u.id === unit.id) || unit;
            }
          });
          
          const newTotalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
          // 무한 루프 방지: 변화가 없으면 종료
          if (newTotalUnitsWidth >= totalUnitsWidth) break;
          totalUnitsWidth = newTotalUnitsWidth;
        }
        
        let remainingSpace = availableWidth - totalUnitsWidth;
        
        // 남은 공간이 있으면 통들에 분배 (반통과 통 구분하여 처리)
        if (remainingSpace > 0) {
          // 반통과 통을 다시 분리
          let currentHalfUnits = adjustedUnits.filter(u => u.isHalfUnit);
          let currentFullUnits = adjustedUnits.filter(u => !u.isHalfUnit);
          
          // 남은 공간을 50 단위로 나눠서 각 통에 분배
          const adjustmentPerUnit = Math.floor(remainingSpace / 50 / adjustedUnits.length) * 50;
          if (adjustmentPerUnit > 0) {
            // 반통과 통을 각각 처리 (반통은 최대 600mm)
            const maxHalfWidth = 600;
            currentHalfUnits = currentHalfUnits.map((unit) => {
              const newWidth = Math.min(unit.width + adjustmentPerUnit, maxHalfWidth);
              return {
                ...unit,
                width: roundToStandardWidth(newWidth, true)
              };
            });
            currentFullUnits = currentFullUnits.map((unit) => {
              const newWidth = unit.width + adjustmentPerUnit;
              return {
                ...unit,
                width: roundToStandardWidth(newWidth, false)
              };
            });
            
            // 다시 합치기
            adjustedUnits = adjustedUnits.map((unit) => {
              if (unit.isHalfUnit) {
                return currentHalfUnits.find(u => u.id === unit.id) || unit;
              } else {
                return currentFullUnits.find(u => u.id === unit.id) || unit;
              }
            });
            
            totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            remainingSpace = availableWidth - totalUnitsWidth;
          }
          
          // 남은 공간이 여전히 있으면 (50 단위 미만) 첫 번째 통들에 추가 (반통은 최대 600mm)
          if (remainingSpace > 0) {
            const unitsToAdjust = Math.min(adjustedUnits.length, Math.floor(remainingSpace / 50));
            const maxHalfWidth = 600;
            for (let i = 0; i < unitsToAdjust; i++) {
              const unit = adjustedUnits[i];
              const newWidth = unit.isHalfUnit 
                ? Math.min(unit.width + 50, maxHalfWidth)
                : unit.width + 50;
              adjustedUnits[i] = {
                ...unit,
                width: roundToStandardWidth(newWidth, unit.isHalfUnit)
              };
            }
            totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            remainingSpace = availableWidth - totalUnitsWidth;
          }
        } else if (remainingSpace < 0) {
          // 공간이 부족하면 통 너비를 줄임 (반통과 통 구분하여 처리)
          const shortage = Math.abs(remainingSpace);
          const reductionPerUnit = Math.ceil(shortage / 50 / adjustedUnits.length) * 50;
          if (reductionPerUnit > 0) {
            // 반통과 통을 각각 처리
            let currentHalfUnits = adjustedUnits.filter(u => u.isHalfUnit);
            let currentFullUnits = adjustedUnits.filter(u => !u.isHalfUnit);
            
            currentHalfUnits = currentHalfUnits.map((unit) => {
              const newWidth = Math.max(HALF_UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
              return {
                ...unit,
                width: roundToStandardWidth(newWidth, true)
              };
            });
            currentFullUnits = currentFullUnits.map((unit) => {
              const newWidth = Math.max(UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
              return {
                ...unit,
                width: roundToStandardWidth(newWidth, false)
              };
            });
            
            // 다시 합치기
            adjustedUnits = adjustedUnits.map((unit) => {
              if (unit.isHalfUnit) {
                return currentHalfUnits.find(u => u.id === unit.id) || unit;
              } else {
                return currentFullUnits.find(u => u.id === unit.id) || unit;
              }
            });
            
            totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            remainingSpace = availableWidth - totalUnitsWidth;
          }
        }
      }
      
      // 최종 남은 공간 계산
      let totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
      let remainingSpace = availableWidth - totalUnitsWidth;
      
      // 좌우 모두 EP 20mm 옵션이 활성화된 경우, 남은 공간을 통 너비에 추가 (반통은 최대 600mm)
      if (state.ep20Options.left && state.ep20Options.right && remainingSpace > 0) {
        // 남은 공간을 통에 분배 (표준 규격으로 반올림)
        if (adjustedUnits.length > 0) {
          const adjustmentPerUnit = remainingSpace / adjustedUnits.length;
          const maxHalfWidth = 600;
          adjustedUnits = adjustedUnits.map((unit) => {
            const newWidth = unit.isHalfUnit 
              ? Math.min(unit.width + adjustmentPerUnit, maxHalfWidth)
              : unit.width + adjustmentPerUnit;
            const roundedWidth = roundToStandardWidth(newWidth, unit.isHalfUnit);
            return {
              ...unit,
              width: roundedWidth
            };
          });
          // 통 너비 합계 재계산
          totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
          remainingSpace = availableWidth - totalUnitsWidth;
        }
      }
      
      // 1. 남은 공간이 음수면 (통 너비가 너무 큼) 통 너비를 줄임
      if (remainingSpace < 0) {
        const shortage = Math.abs(remainingSpace);
        // 부족분을 통에 분배하여 통 너비를 줄임 (표준 규격으로 반올림)
        if (adjustedUnits.length > 0) {
          const reductionPerUnit = shortage / adjustedUnits.length;
          adjustedUnits = adjustedUnits.map(unit => {
            const newWidth = unit.width - reductionPerUnit;
            // 표준 규격으로 반올림
            const roundedWidth = roundToStandardWidth(newWidth, unit.isHalfUnit);
            return {
              ...unit,
              width: roundedWidth
            };
          });
          
          // 통 너비 합계 재계산
          totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
          remainingSpace = availableWidth - totalUnitsWidth;
        }
      }
      
      // 2. 남은 공간이 양수면 EP가 100mm를 초과하는지 확인하고 통 너비를 늘림
      // EP 20mm 옵션이 활성화되어 있으면 이 단계는 건너뜀 (EP 20mm는 항상 적용)
      if (remainingSpace > 0 && !(state.ep20Options.left && state.ep20Options.right)) {
        // 예상 EP 크기 계산
        let expectedEPLeft = epLeftBase;
        let expectedEPRight = epRightBase;
        
        if (state.endPanels.left && state.endPanels.right) {
          const halfSpace = remainingSpace / 2;
          expectedEPLeft = epLeftBase + Math.floor(halfSpace);
          expectedEPRight = epRightBase + Math.ceil(halfSpace);
        } else if (state.endPanels.left) {
          expectedEPLeft = epLeftBase + remainingSpace;
        } else if (state.endPanels.right) {
          expectedEPRight = epRightBase + remainingSpace;
        }
        
        // EP가 100mm를 초과하면 통 너비를 늘림 (표준 규격으로 반올림)
        // 반복적으로 조정하여 EP가 100 이하가 되도록
        let maxIterations = 10;
        while ((expectedEPLeft > maxEPSize || expectedEPRight > maxEPSize) && maxIterations > 0) {
          maxIterations--;
          const excessLeft = Math.max(0, expectedEPLeft - maxEPSize);
          const excessRight = Math.max(0, expectedEPRight - maxEPSize);
          const totalExcess = excessLeft + excessRight;
          
          // 초과분을 통에 분배 (통이 여러 개면 균등 분배, 표준 규격으로 반올림)
          if (adjustedUnits.length > 0 && totalExcess > 0) {
            const adjustmentPerUnit = totalExcess / adjustedUnits.length;
            
            // 각 통을 개별적으로 조정 (모두 같은 크기로 하지 않고, 반통은 최대 600mm)
            const maxHalfWidth = 600;
            adjustedUnits = adjustedUnits.map((unit, index) => {
              // 인덱스에 따라 약간 다른 조정량 적용 (더 자연스러운 조정)
              const adjustment = adjustmentPerUnit * (1 + (index % 2) * 0.1);
              const newWidth = unit.isHalfUnit
                ? Math.min(unit.width + adjustment, maxHalfWidth)
                : unit.width + adjustment;
              // 표준 규격으로 반올림
              const roundedWidth = roundToStandardWidth(newWidth, unit.isHalfUnit);
              return {
                ...unit,
                width: roundedWidth
              };
            });
            
            // 통 너비 합계 재계산
            totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            remainingSpace = availableWidth - totalUnitsWidth;
            
            // 예상 EP 크기 재계산
            if (state.endPanels.left && state.endPanels.right) {
              const halfSpace = remainingSpace / 2;
              expectedEPLeft = epLeftBase + Math.floor(halfSpace);
              expectedEPRight = epRightBase + Math.ceil(halfSpace);
            } else if (state.endPanels.left) {
              expectedEPLeft = epLeftBase + remainingSpace;
            } else if (state.endPanels.right) {
              expectedEPRight = epRightBase + remainingSpace;
            }
          } else {
            break;
          }
        }
      }
      
      // 남은 공간을 EP에 더함 (50 + 남는부분, 좌우 균등 분배하되 100mm 이하로 제한)
      // EP 20mm 옵션이 활성화되어 있으면 해당 쪽을 20mm로 설정
      let newEPLeft = epLeftBase;
      let newEPRight = epRightBase;
      
      if (state.endPanels.left && state.endPanels.right) {
        // EP 20mm 옵션이 활성화되어 있으면 해당 쪽을 20mm로 설정
        if (state.ep20Options.left || state.ep20Options.right) {
          // 좌우 모두 EP 20mm 옵션이 활성화된 경우
          if (state.ep20Options.left && state.ep20Options.right) {
            newEPLeft = minEPSize;
            newEPRight = minEPSize;
            // 남은 공간은 통 너비 조정으로 처리 (통 너비를 늘림)
            // 통 너비를 조정해야 하는 경우는 이미 위에서 처리됨
          } else if (state.ep20Options.left) {
            // 좌측만 EP 20mm 옵션 - 좌측을 20mm로 설정, 우측은 기본값(50mm) 유지
            newEPLeft = minEPSize;
            newEPRight = baseEPSize; // 나머지 EP는 기본값 유지 (공간을 몰아주지 않음)
            
            // availableWidth 재계산 (20 + 50)
            const recalculatedAvailableWidth = state.totalWidth - newEPLeft - newEPRight;
            const currentUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            const newRemainingSpace = recalculatedAvailableWidth - currentUnitsWidth;
            
            // 통 너비를 재분배하여 규격 내에서 최대한 넓고 균등하게 만들기
            if (adjustedUnits.length > 0 && newRemainingSpace !== 0) {
              // 이상적인 통 너비 계산
              const idealWidth = recalculatedAvailableWidth / adjustedUnits.length;
              
              // 각 통을 개별적으로 재계산 (순서 유지)
              adjustedUnits = adjustedUnits.map((unit) => {
                if (unit.isHalfUnit) {
                  // 반통 처리 (최대 600mm)
                  const maxHalfWidth = 600;
                  const halfWidths = [...HALF_UNIT_WIDTHS] as number[];
                  const idealHalfWidth = Math.min(idealWidth, maxHalfWidth);
                  const suitableWidths = halfWidths.filter(w => w <= idealHalfWidth);
                  const newWidth = suitableWidths.length > 0
                    ? suitableWidths[suitableWidths.length - 1]
                    : Math.min(halfWidths[0], idealHalfWidth);
                  return {
                    ...unit,
                    width: newWidth
                  };
                } else {
                  // 통 처리
                  const fullWidths = [...UNIT_WIDTHS] as number[];
                  const suitableWidths = fullWidths.filter(w => w <= idealWidth);
                  const newWidth = suitableWidths.length > 0
                    ? suitableWidths[suitableWidths.length - 1]
                    : Math.max(750, Math.floor(idealWidth / 50) * 50);
                  return {
                    ...unit,
                    width: newWidth
                  };
                }
              });
              
              // 통 너비 합계 재계산
              const newTotalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
              const finalRemainingSpace = recalculatedAvailableWidth - newTotalUnitsWidth;
              
              // 남은 공간이 있으면 통에 추가 분배 (규격 내에서)
              if (finalRemainingSpace > 0) {
                const adjustmentPerUnit = finalRemainingSpace / adjustedUnits.length;
                const maxHalfWidth = 600;
                adjustedUnits = adjustedUnits.map((unit) => {
                  const newWidth = unit.isHalfUnit
                    ? Math.min(unit.width + adjustmentPerUnit, maxHalfWidth)
                    : unit.width + adjustmentPerUnit;
                  return {
                    ...unit,
                    width: roundToStandardWidth(newWidth, unit.isHalfUnit)
                  };
                });
              }
              
              // 통 너비 합계 최종 재계산
              totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
              remainingSpace = recalculatedAvailableWidth - totalUnitsWidth;
            }
          } else if (state.ep20Options.right) {
            // 우측만 EP 20mm 옵션 - 우측을 20mm로 설정, 좌측은 기본값(50mm) 유지
            newEPRight = minEPSize;
            newEPLeft = baseEPSize; // 나머지 EP는 기본값 유지 (공간을 몰아주지 않음)
            
            // availableWidth 재계산 (50 + 20)
            const recalculatedAvailableWidth = state.totalWidth - newEPLeft - newEPRight;
            const currentUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
            const newRemainingSpace = recalculatedAvailableWidth - currentUnitsWidth;
            
            // 통 너비를 재분배하여 규격 내에서 최대한 넓고 균등하게 만들기
            if (adjustedUnits.length > 0 && newRemainingSpace !== 0) {
              // 이상적인 통 너비 계산
              const idealWidth = recalculatedAvailableWidth / adjustedUnits.length;
              
              // 각 통을 개별적으로 재계산 (순서 유지)
              adjustedUnits = adjustedUnits.map((unit) => {
                if (unit.isHalfUnit) {
                  // 반통 처리 (최대 600mm)
                  const maxHalfWidth = 600;
                  const halfWidths = [...HALF_UNIT_WIDTHS] as number[];
                  const idealHalfWidth = Math.min(idealWidth, maxHalfWidth);
                  const suitableWidths = halfWidths.filter(w => w <= idealHalfWidth);
                  const newWidth = suitableWidths.length > 0
                    ? suitableWidths[suitableWidths.length - 1]
                    : Math.min(halfWidths[0], idealHalfWidth);
                  return {
                    ...unit,
                    width: newWidth
                  };
                } else {
                  // 통 처리
                  const fullWidths = [...UNIT_WIDTHS] as number[];
                  const suitableWidths = fullWidths.filter(w => w <= idealWidth);
                  const newWidth = suitableWidths.length > 0
                    ? suitableWidths[suitableWidths.length - 1]
                    : Math.max(750, Math.floor(idealWidth / 50) * 50);
                  return {
                    ...unit,
                    width: newWidth
                  };
                }
              });
              
              // 통 너비 합계 재계산
              const newTotalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
              const finalRemainingSpace = recalculatedAvailableWidth - newTotalUnitsWidth;
              
              // 남은 공간이 있으면 통에 추가 분배 (규격 내에서)
              if (finalRemainingSpace > 0) {
                const adjustmentPerUnit = finalRemainingSpace / adjustedUnits.length;
                const maxHalfWidth = 600;
                adjustedUnits = adjustedUnits.map((unit) => {
                  const newWidth = unit.isHalfUnit
                    ? Math.min(unit.width + adjustmentPerUnit, maxHalfWidth)
                    : unit.width + adjustmentPerUnit;
                  return {
                    ...unit,
                    width: roundToStandardWidth(newWidth, unit.isHalfUnit)
                  };
                });
              }
              
              // 통 너비 합계 최종 재계산
              totalUnitsWidth = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
              remainingSpace = recalculatedAvailableWidth - totalUnitsWidth;
            }
          }
        } else if (remainingSpace > 0) {
          // EP 20mm 옵션이 없으면 기존 로직: 균등 분배하되 100mm 이하로 제한, 최소 20mm 보장
          const halfSpace = remainingSpace / 2;
          newEPLeft = Math.min(maxEPSize, Math.max(minEPSize, epLeftBase + Math.floor(halfSpace)));
          newEPRight = Math.min(maxEPSize, Math.max(minEPSize, epRightBase + Math.ceil(halfSpace)));
          
          // 한쪽이 100mm에 도달하면 나머지를 다른 쪽에 (최소 20mm 보장)
          if (newEPLeft >= maxEPSize && newEPRight < maxEPSize) {
            const remainingAfterLeft = remainingSpace - (newEPLeft - epLeftBase);
            newEPRight = Math.min(maxEPSize, Math.max(minEPSize, epRightBase + remainingAfterLeft));
          } else if (newEPRight >= maxEPSize && newEPLeft < maxEPSize) {
            const remainingAfterRight = remainingSpace - (newEPRight - epRightBase);
            newEPLeft = Math.min(maxEPSize, Math.max(minEPSize, epLeftBase + remainingAfterRight));
          }
        } else {
          // 남은 공간이 없거나 음수인 경우 (EP 20mm 옵션 없을 때)
          // EP가 활성화된 경우 최소 20mm 보장
          newEPLeft = Math.max(minEPSize, epLeftBase + remainingSpace);
          newEPRight = Math.max(minEPSize, epRightBase + remainingSpace);
        }
      } else if (state.endPanels.left) {
        // 좌측만 활성화: 100mm 이하로 제한, 최소 20mm 보장
        if (remainingSpace > 0) {
          newEPLeft = Math.min(maxEPSize, epLeftBase + remainingSpace);
        } else {
          newEPLeft = Math.max(minEPSize, epLeftBase + remainingSpace);
        }
      } else if (state.endPanels.right) {
        // 우측만 활성화: 100mm 이하로 제한, 최소 20mm 보장
        if (remainingSpace > 0) {
          newEPRight = Math.min(maxEPSize, epRightBase + remainingSpace);
        } else {
          newEPRight = Math.max(minEPSize, epRightBase + remainingSpace);
        }
      } else {
        // EP가 모두 체크 해제: EP는 0으로 설정
        newEPLeft = 0;
        newEPRight = 0;
      }
      
      // EP가 활성화된 경우 최소 20mm 보장 (최종 확인)
      if (state.endPanels.left) {
        newEPLeft = Math.max(minEPSize, newEPLeft);
      }
      if (state.endPanels.right) {
        newEPRight = Math.max(minEPSize, newEPRight);
      }

      // 최종 검증: 통 너비 합계 + EP 합계가 totalWidth를 초과하는지 확인
      // 통 너비 합계가 이미 availableWidth를 준수하므로, EP와 합산했을 때 totalWidth를 초과하는지만 확인
      let finalAdjustedUnits = [...adjustedUnits];
      let finalEPLeft = newEPLeft;
      let finalEPRight = newEPRight;
      
      let currentTotalUnitsWidth = finalAdjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
      const currentTotalEPWidth = (state.endPanels.left ? finalEPLeft : 0) + (state.endPanels.right ? finalEPRight : 0);
      let totalUsedWidth = currentTotalUnitsWidth + currentTotalEPWidth;
      let excessWidth = totalUsedWidth - state.totalWidth;
      
      // totalWidth를 초과하는 경우: 통 너비를 줄여서 맞추기 (반복적으로 조정)
      if (excessWidth > 1 && finalAdjustedUnits.length > 0) {
        let maxIterations = 10;
        let iteration = 0;
        
        while (iteration < maxIterations && excessWidth > 1) {
          iteration++;
          
          // 반통과 통을 분리
          let currentHalfUnits = finalAdjustedUnits.filter(u => u.isHalfUnit);
          let currentFullUnits = finalAdjustedUnits.filter(u => !u.isHalfUnit);
          
          // 초과분을 통 개수로 나눠서 각 통에서 빼기
          const reductionPerUnit = excessWidth / finalAdjustedUnits.length;
          
          currentHalfUnits = currentHalfUnits.map((unit) => {
            const targetWidth = Math.max(HALF_UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
            const widths = [...HALF_UNIT_WIDTHS] as number[];
            const suitableWidths = widths.filter(w => w <= targetWidth && w <= 600);
            return {
              ...unit,
              width: suitableWidths.length > 0 ? suitableWidths[suitableWidths.length - 1] : HALF_UNIT_WIDTHS[0] as number
            };
          });
          
          currentFullUnits = currentFullUnits.map((unit) => {
            const targetWidth = Math.max(UNIT_WIDTHS[0] as number, unit.width - reductionPerUnit);
            const widths = [...UNIT_WIDTHS] as number[];
            const suitableWidths = widths.filter(w => w <= targetWidth);
            return {
              ...unit,
              width: suitableWidths.length > 0 ? suitableWidths[suitableWidths.length - 1] : UNIT_WIDTHS[0] as number
            };
          });
          
          // 다시 합치기
          finalAdjustedUnits = finalAdjustedUnits.map((unit) => {
            if (unit.isHalfUnit) {
              return currentHalfUnits.find(u => u.id === unit.id) || unit;
            } else {
              return currentFullUnits.find(u => u.id === unit.id) || unit;
            }
          });
          
          // 무한 루프 방지: 변화가 없으면 종료
          const newTotalUnitsWidth = finalAdjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
          if (newTotalUnitsWidth >= currentTotalUnitsWidth) break;
          
          currentTotalUnitsWidth = newTotalUnitsWidth;
          totalUsedWidth = currentTotalUnitsWidth + currentTotalEPWidth;
          excessWidth = totalUsedWidth - state.totalWidth;
        }
      }
      
      // 최종 재계산
      adjustedUnits = finalAdjustedUnits;
      newEPLeft = finalEPLeft;
      newEPRight = finalEPRight;
      
      // 2. 10~20mm 모자라는 경우: 사용자에게 총 사이즈 변경 여부 확인
      const finalTotalUnitsWidth2 = adjustedUnits.reduce((sum, unit) => sum + unit.width, 0);
      const finalTotalEPWidth2 = (state.endPanels.left ? newEPLeft : 0) + (state.endPanels.right ? newEPRight : 0);
      const totalUsedWidth2 = finalTotalUnitsWidth2 + finalTotalEPWidth2;
      const shortage = state.totalWidth - totalUsedWidth2;
      
      // 확인 창 제거: 10-20mm 부족한 경우 자동으로 EP에 분배
      if (shortage >= 10 && shortage <= 20) {
        // 부족한 공간을 EP에 자동 분배
        if (state.endPanels.left && state.endPanels.right) {
          const halfShortage = shortage / 2;
          newEPLeft = Math.min(maxEPSize, newEPLeft + halfShortage);
          newEPRight = Math.min(maxEPSize, newEPRight + (shortage - halfShortage));
        } else if (state.endPanels.left) {
          newEPLeft = Math.min(maxEPSize, newEPLeft + shortage);
        } else if (state.endPanels.right) {
          newEPRight = Math.min(maxEPSize, newEPRight + shortage);
        }
      }

      // 통 위치 재계산
      const sortedUnits = [...adjustedUnits].sort((a, b) => (a.order || 0) - (b.order || 0));
      
      // EP와 통 사이 틈 없이 붙이기
      let currentX = -state.totalWidth / 2; // totalWidth의 왼쪽 끝
      if (state.endPanels.left) {
        // EP가 있으면: EP의 오른쪽 끝에서 통 시작
        currentX = -state.totalWidth / 2 + newEPLeft;
      }
      
      const repositionedUnits = sortedUnits.map((unit) => {
        // 통 중심 위치 계산 (mm 단위)
        const unitCenterX = currentX + unit.width / 2;
        // cm로 변환하여 저장
        const position = unitCenterX / 10;
        // 다음 통은 이전 통의 오른쪽 끝에서 바로 시작 (틈 없음)
        currentX += unit.width;
        return { ...unit, position };
      });

      return {
        units: repositionedUnits,
        endPanelSizes: {
          ...state.endPanelSizes,
          left: newEPLeft,
          right: newEPRight
        }
      };
    });
  },

  calculateTopEP: () => {
    set((state) => {
      if (!state.endPanels.top) {
        return {
          endPanelSizes: {
            ...state.endPanelSizes,
            top: 0
          }
        };
      }

      const baseEPSize = 50; // EP 기본 크기 50mm
      const minEPSize = 20; // EP 최소 크기 20mm
      const baseHeight = BASE_HEIGHT;
      
      // 통 높이 (모든 통이 같은 높이라고 가정, 가장 큰 높이 사용)
      const maxUnitHeight = state.units.length > 0 
        ? Math.max(...state.units.map(u => u.height))
        : 2150; // 설계도 표준 높이

      // 사용 가능한 높이: totalHeight - 베이스 높이 - EP 기본 50
      const availableHeight = state.totalHeight - baseHeight - baseEPSize;
      
      // 남은 높이 계산: 사용 가능한 높이 - 통 높이
      const remainingHeight = availableHeight - maxUnitHeight;
      
      // 상부 EP 높이: 50 + 남는 높이 (최소 20mm 보장)
      const topEPFinal = baseEPSize + remainingHeight;

      return {
        endPanelSizes: {
          ...state.endPanelSizes,
          top: Math.max(minEPSize, topEPFinal)
        }
      };
    });
  },

  // 프로젝트 데이터 로드
  loadProject: (config) => set(() => ({
    totalWidth: config.totalWidth,
    totalHeight: config.totalHeight,
    totalDepth: config.totalDepth,
    units: config.units,
    doorType: config.doorType,
    color: config.color,
      endPanels: config.endPanels,
      endPanelSizes: config.endPanelSizes,
      ep20Options: config.ep20Options || { left: false, right: false },
      showDimensions: config.showDimensions,
      wireframe: config.wireframe,
  })),

  // 현재 프로젝트 데이터 가져오기
  getProjectData: (): ClosetConfig => {
    const state = useClosetStore.getState();
    return {
      totalWidth: state.totalWidth,
      totalHeight: state.totalHeight,
      totalDepth: state.totalDepth,
      units: state.units,
      doorType: state.doorType,
      color: state.color,
      endPanels: state.endPanels,
      endPanelSizes: state.endPanelSizes,
      ep20Options: state.ep20Options,
      showDimensions: state.showDimensions,
      wireframe: state.wireframe,
    };
  },

}));


// 전체 플로우 테스트: 3400mm 여닫이에서 한통 추가
const UNIT_WIDTHS = [850, 900, 950, 1000, 1050, 1100, 1150];

// 시나리오: 통 3개가 이미 있고 각각 850mm
const totalWidth = 3400;
const ep20Options = { left: true, right: true };
const baseEPSize = 50;
const minEPSize = 20;
const epLeftBase = ep20Options.left ? minEPSize : baseEPSize;
const epRightBase = ep20Options.right ? minEPSize : baseEPSize;

console.log('=== 전체 플로우 테스트 ===');
console.log('totalWidth:', totalWidth);
console.log('EP 좌측:', epLeftBase, 'EP 우측:', epRightBase);

// Step 1: handleAddUnit
const currentUnits = [
  { width: 850, isHalfUnit: false },
  { width: 850, isHalfUnit: false },
  { width: 850, isHalfUnit: false }
];
const currentUnitsWidth = currentUnits.reduce((sum, unit) => sum + unit.width, 0);
const availableWidthForNew = totalWidth - epLeftBase - epRightBase - currentUnitsWidth;

console.log('\n=== Step 1: handleAddUnit ===');
console.log('현재 통 3개:', currentUnits.map(u => u.width + 'mm'));
console.log('currentUnitsWidth:', currentUnitsWidth);
console.log('availableWidth (새 통용):', availableWidthForNew);

const suitableFullWidths = UNIT_WIDTHS.filter(w => w <= availableWidthForNew);
let newUnitWidth;
if (suitableFullWidths.length > 0) {
  newUnitWidth = suitableFullWidths[suitableFullWidths.length - 1];
} else {
  const roundedWidth = Math.floor(availableWidthForNew / 50) * 50;
  newUnitWidth = Math.max(UNIT_WIDTHS[0], Math.min(roundedWidth, availableWidthForNew));
}
console.log('새 통 너비:', newUnitWidth);

// Step 2: 통 추가 후 상태
const allUnits = [...currentUnits, { width: newUnitWidth, isHalfUnit: false }];
console.log('\n=== Step 2: 통 추가 후 ===');
console.log('통 4개:', allUnits.map(u => u.width + 'mm'));
const totalUnitsWidth = allUnits.reduce((sum, unit) => sum + unit.width, 0);
console.log('통 너비 합계:', totalUnitsWidth);
console.log('EP 합계:', epLeftBase + epRightBase);
console.log('총 너비:', totalUnitsWidth + epLeftBase + epRightBase);
console.log('초과 여부:', (totalUnitsWidth + epLeftBase + epRightBase) > totalWidth ? '✗ 초과!' : '✓ 정상');

// Step 3: calculateUnitLayout
const availableWidth = totalWidth - epLeftBase - epRightBase;
const fullUnitCount = allUnits.filter(u => !u.isHalfUnit).length;
const totalUnitCount = allUnits.length;
const idealFullWidth = availableWidth / totalUnitCount;
const maxAllowedWidthPerUnit = Math.floor(availableWidth / fullUnitCount);

console.log('\n=== Step 3: calculateUnitLayout ===');
console.log('availableWidth:', availableWidth);
console.log('fullUnitCount:', fullUnitCount);
console.log('idealFullWidth:', idealFullWidth);
console.log('maxAllowedWidthPerUnit:', maxAllowedWidthPerUnit);

const allowedWidths = UNIT_WIDTHS.filter(w => w <= maxAllowedWidthPerUnit);
console.log('allowedWidths:', allowedWidths);

if (allowedWidths.length === 0) {
  console.log('\n✗ allowedWidths가 비어있음! 조합 알고리즘 사용');
  
  // 조합 생성
  function generateCombinations(remaining, count, current, maxResults = 1000) {
    if (count === 0) {
      const total = current.reduce((sum, w) => sum + w, 0);
      if (total <= availableWidth) {
        return [current];
      }
      return [];
    }
    
    if (current.length > 0 && current.length * UNIT_WIDTHS.length > maxResults) {
      return [];
    }
    
    const results = [];
    const sortedWidths = [...UNIT_WIDTHS].sort((a, b) => {
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
  }
  
  const combinations = generateCombinations(availableWidth, fullUnitCount, [], 500);
  console.log('생성된 조합 개수:', combinations.length);
  
  if (combinations.length > 0) {
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
    
    const sortedWidths = [...bestCombo].sort((a, b) => b - a);
    console.log('\n=== 최종 결과 ===');
    console.log('조합:', bestCombo);
    console.log('정렬:', sortedWidths);
    console.log('통 너비 합계:', sortedWidths.reduce((sum, w) => sum + w, 0));
    console.log('EP 합계:', epLeftBase + epRightBase);
    console.log('총 너비:', sortedWidths.reduce((sum, w) => sum + w, 0) + epLeftBase + epRightBase);
    console.log('초과 여부:', (sortedWidths.reduce((sum, w) => sum + w, 0) + epLeftBase + epRightBase) > totalWidth ? '✗ 초과!' : '✓ 정상');
  }
}


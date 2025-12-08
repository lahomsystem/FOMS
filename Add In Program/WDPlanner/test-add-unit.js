// 통 추가 시나리오 테스트
const UNIT_WIDTHS = [850, 900, 950, 1000, 1050, 1100, 1150];

// 시나리오: 통 3개가 이미 있고 각각 850mm
const totalWidth = 3400;
const ep20Options = { left: true, right: true };
const baseEPSize = 50;
const minEPSize = 20;
const epLeftBase = ep20Options.left ? minEPSize : baseEPSize;
const epRightBase = ep20Options.right ? minEPSize : baseEPSize;

// 현재 통 3개
const currentUnits = [
  { width: 850, isHalfUnit: false },
  { width: 850, isHalfUnit: false },
  { width: 850, isHalfUnit: false }
];

console.log('=== 통 추가 시나리오 테스트 ===');
console.log('totalWidth:', totalWidth);
console.log('EP 좌측:', epLeftBase, 'EP 우측:', epRightBase);
console.log('현재 통 3개:', currentUnits.map(u => u.width + 'mm'));

// handleAddUnit 로직
const currentUnitsWidth = currentUnits.reduce((sum, unit) => sum + unit.width, 0);
const availableWidth = totalWidth - epLeftBase - epRightBase - currentUnitsWidth;

console.log('\n=== handleAddUnit 계산 ===');
console.log('currentUnitsWidth:', currentUnitsWidth);
console.log('availableWidth (새 통용):', availableWidth);

// 새 통의 너비 결정
const suitableFullWidths = UNIT_WIDTHS.filter(w => w <= availableWidth);
const newUnitWidth = suitableFullWidths.length > 0 
  ? suitableFullWidths[suitableFullWidths.length - 1]
  : UNIT_WIDTHS[0];

console.log('새 통 너비:', newUnitWidth);

// 통 추가 후 상태
const allUnits = [...currentUnits, { width: newUnitWidth, isHalfUnit: false }];
const totalUnitsWidth = allUnits.reduce((sum, unit) => sum + unit.width, 0);
const totalEPWidth = epLeftBase + epRightBase;
const totalUsedWidth = totalUnitsWidth + totalEPWidth;

console.log('\n=== 통 추가 후 상태 ===');
console.log('통 4개:', allUnits.map(u => u.width + 'mm'));
console.log('통 너비 합계:', totalUnitsWidth);
console.log('EP 합계:', totalEPWidth);
console.log('총 너비:', totalUsedWidth);
console.log('totalWidth:', totalWidth);
console.log('초과 여부:', totalUsedWidth > totalWidth ? '✗ 초과!' : '✓ 정상');

// calculateUnitLayout 로직
console.log('\n=== calculateUnitLayout 재계산 ===');
const availableWidthForLayout = totalWidth - epLeftBase - epRightBase;
console.log('availableWidth (재계산용):', availableWidthForLayout);

const fullUnitCount = allUnits.filter(u => !u.isHalfUnit).length;
const totalUnitCount = allUnits.length;
const idealFullWidth = availableWidthForLayout / totalUnitCount;
const maxAllowedWidthPerUnit = Math.floor(availableWidthForLayout / fullUnitCount);

console.log('fullUnitCount:', fullUnitCount);
console.log('idealFullWidth:', idealFullWidth);
console.log('maxAllowedWidthPerUnit:', maxAllowedWidthPerUnit);

const allowedWidths = UNIT_WIDTHS.filter(w => w <= maxAllowedWidthPerUnit);
console.log('allowedWidths:', allowedWidths);

if (allowedWidths.length === 0) {
  console.log('\n✗ allowedWidths가 비어있음! 개별 계산 필요');
  
  // 개별 계산
  let totalUsed = 0;
  const newWidths = allUnits.map((unit, index) => {
    if (unit.isHalfUnit) {
      return unit.width; // 반통은 그대로
    }
    
    const remaining = fullUnitCount - index - 1;
    const remainingWidth = availableWidthForLayout - totalUsed;
    const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
    
    const suitableWidths = UNIT_WIDTHS.filter(w => w <= idealWidth);
    let closest = suitableWidths.length > 0 
      ? suitableWidths[suitableWidths.length - 1]
      : UNIT_WIDTHS[0];
    
    if (totalUsed + closest > availableWidthForLayout && remaining > 0) {
      const remainingWidthForAll = availableWidthForLayout - totalUsed;
      const maxWidthPerUnit = remainingWidthForAll / (remaining + 1);
      const smallerWidths = UNIT_WIDTHS.filter(w => w <= maxWidthPerUnit);
      closest = smallerWidths.length > 0 
        ? smallerWidths[smallerWidths.length - 1]
        : UNIT_WIDTHS[0];
    }
    
    totalUsed += closest;
    return closest;
  });
  
  console.log('개별 계산 결과:', newWidths);
  const finalTotal = newWidths.reduce((sum, w) => sum + w, 0);
  console.log('최종 통 너비 합계:', finalTotal);
  console.log('EP 합계:', totalEPWidth);
  console.log('총 너비:', finalTotal + totalEPWidth);
  console.log('초과 여부:', (finalTotal + totalEPWidth) > totalWidth ? '✗ 초과!' : '✓ 정상');
} else {
  console.log('\n✓ allowedWidths가 있음, 같은 크기로 설정');
  const baseUnitWidth = allowedWidths[allowedWidths.length - 1];
  console.log('baseUnitWidth:', baseUnitWidth);
  const finalTotal = baseUnitWidth * fullUnitCount;
  console.log('최종 통 너비 합계:', finalTotal);
  console.log('EP 합계:', totalEPWidth);
  console.log('총 너비:', finalTotal + totalEPWidth);
  console.log('초과 여부:', (finalTotal + totalEPWidth) > totalWidth ? '✗ 초과!' : '✓ 정상');
}


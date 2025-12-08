// 테스트: 3400mm 여닫이에서 한통 추가
const UNIT_WIDTHS = [850, 900, 950, 1000, 1050, 1100, 1150];
const HALF_UNIT_WIDTHS = [450, 500, 550, 600];

// 시나리오 설정
const totalWidth = 3400;
const ep20Options = { left: true, right: true }; // EP 20mm 옵션
const doorType = 'swing'; // 여닫이

// EP 기본값 계산
const baseEPSize = 50;
const minEPSize = 20;
const leftEPBase = ep20Options.left ? minEPSize : baseEPSize;
const rightEPBase = ep20Options.right ? minEPSize : baseEPSize;

// 사용 가능한 너비 계산
const availableWidth = totalWidth - leftEPBase - rightEPBase;
console.log('=== 테스트 시작 ===');
console.log('totalWidth:', totalWidth);
console.log('EP 좌측:', leftEPBase, 'EP 우측:', rightEPBase);
console.log('availableWidth:', availableWidth);

// 문 타입에 따라 통 개수 결정
const totalWidthCm = totalWidth / 10;
let requiredFullUnits;
let requiresHalfUnit;

if (doorType === 'swing') {
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
    // 340cm는 3400mm이므로 통 4개 필요 (테스트용)
    requiredFullUnits = 4;
    requiresHalfUnit = false;
  } else if (totalWidthCm >= 364 && totalWidthCm <= 424) {
    requiredFullUnits = 3;
    requiresHalfUnit = true;
  } else if (totalWidthCm >= 425 && totalWidthCm <= 485) {
    requiredFullUnits = 4;
    requiresHalfUnit = false;
  } else {
    // 340cm는 3400mm이므로 4개 통이 필요
    const estimatedCount = Math.floor(availableWidth / 1000);
    requiredFullUnits = Math.max(4, estimatedCount); // 최소 4개
    requiresHalfUnit = false;
  }
}

console.log('requiredFullUnits:', requiredFullUnits);
console.log('requiresHalfUnit:', requiresHalfUnit);

// findBestUnitCombination 로직 테스트
const targetWidth = availableWidth; // 3360
const standardWidths = [...UNIT_WIDTHS];

console.log('\n=== 조합 생성 테스트 ===');
console.log('targetWidth:', targetWidth);
console.log('requiredFullUnits:', requiredFullUnits);

// generateCombinations 함수
function generateCombinations(remaining, count, current, maxResults = 1000) {
  if (count === 0) {
    const total = current.reduce((sum, w) => sum + w, 0);
    if (total <= targetWidth) {
      return [current];
    }
    return [];
  }
  
  if (current.length > 0 && current.length * standardWidths.length > maxResults) {
    return [];
  }
  
  const results = [];
  const sortedWidths = [...standardWidths].sort((a, b) => {
    const diffA = Math.abs(a - remaining / count);
    const diffB = Math.abs(b - remaining / count);
    return diffA - diffB;
  });
  
  for (const width of sortedWidths) {
    const currentTotal = current.reduce((sum, w) => sum + w, 0);
    if (currentTotal + width > targetWidth) {
      console.log(`  스킵: currentTotal(${currentTotal}) + width(${width}) = ${currentTotal + width} > targetWidth(${targetWidth})`);
      continue;
    }
    
    if (width <= remaining && results.length < maxResults) {
      const subResults = generateCombinations(remaining - width, count - 1, [...current, width], maxResults);
      results.push(...subResults);
      if (results.length >= maxResults) break;
    }
  }
  return results;
}

const combinations = generateCombinations(targetWidth, requiredFullUnits, [], 500);
console.log('\n생성된 조합 개수:', combinations.length);

if (combinations.length > 0) {
  console.log('\n=== 조합 결과 ===');
  combinations.slice(0, 10).forEach((combo, idx) => {
    const total = combo.reduce((sum, w) => sum + w, 0);
    console.log(`조합 ${idx + 1}:`, combo, '합계:', total, total <= targetWidth ? '✓' : '✗');
  });
  
  // 가장 가까운 조합 선택
  let bestCombo = combinations[0];
  let minDiff = Infinity;
  
  for (const combo of combinations) {
    const totalUsed = combo.reduce((sum, w) => sum + w, 0);
    if (totalUsed <= targetWidth) {
      const diff = Math.abs(targetWidth - totalUsed);
      if (diff < minDiff) {
        minDiff = diff;
        bestCombo = combo;
      }
    }
  }
  
  console.log('\n=== 최종 선택된 조합 ===');
  const finalTotal = bestCombo.reduce((sum, w) => sum + w, 0);
  console.log('조합:', bestCombo);
  console.log('통 너비 합계:', finalTotal);
  console.log('EP 좌측:', leftEPBase, 'EP 우측:', rightEPBase);
  console.log('총 너비:', finalTotal + leftEPBase + rightEPBase);
  console.log('totalWidth:', totalWidth);
  console.log('초과 여부:', (finalTotal + leftEPBase + rightEPBase) > totalWidth ? '✗ 초과!' : '✓ 정상');
} else {
  console.log('\n✗ 조합이 생성되지 않았습니다!');
  
  // 휴리스틱 방식 테스트
  console.log('\n=== 휴리스틱 방식 테스트 ===');
  const unitWidths = [];
  let totalUsed = 0;
  
  for (let i = 0; i < requiredFullUnits; i++) {
    const remaining = requiredFullUnits - i - 1;
    const remainingWidth = targetWidth - totalUsed;
    const idealWidth = remaining > 0 ? remainingWidth / (remaining + 1) : remainingWidth;
    
    const suitableWidths = standardWidths.filter(w => w <= idealWidth);
    let closest = suitableWidths.length > 0 
      ? suitableWidths[suitableWidths.length - 1]
      : standardWidths[0];
    
    if (totalUsed + closest > targetWidth && remaining > 0) {
      const remainingWidthForAll = targetWidth - totalUsed;
      const maxWidthPerUnit = remainingWidthForAll / (remaining + 1);
      const smallerWidths = standardWidths.filter(w => w <= maxWidthPerUnit);
      closest = smallerWidths.length > 0 
        ? smallerWidths[smallerWidths.length - 1]
        : standardWidths[0];
    }
    
    unitWidths.push(closest);
    totalUsed += closest;
    console.log(`통 ${i + 1}: ${closest}mm, 누적: ${totalUsed}mm`);
  }
  
  const finalTotal = unitWidths.reduce((sum, w) => sum + w, 0);
  console.log('\n=== 휴리스틱 결과 ===');
  console.log('조합:', unitWidths);
  console.log('통 너비 합계:', finalTotal);
  console.log('EP 좌측:', leftEPBase, 'EP 우측:', rightEPBase);
  console.log('총 너비:', finalTotal + leftEPBase + rightEPBase);
  console.log('totalWidth:', totalWidth);
  console.log('초과 여부:', (finalTotal + leftEPBase + rightEPBase) > totalWidth ? '✗ 초과!' : '✓ 정상');
}


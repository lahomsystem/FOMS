import React, { useState } from 'react';
import { useClosetStore } from '../stores/closetStore';
import { ClosetUnit, TemplateType, UNIT_WIDTHS, HALF_UNIT_WIDTHS, UNIT_HEIGHTS } from '../types';
import SortableUnitItem from './SortableUnitItem';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  useSortable,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';

// 드래그 상태 표시를 위한 헬퍼 컴포넌트 (useSortable 사용)
function DragIndicator({ isActive }: { isActive: boolean }) {
  // useSortable을 사용하여 드래그 상태 관리 (실제 드래그는 하지 않지만 hook 사용)
  const { transform, transition } = useSortable({
    id: 'drag-indicator',
    disabled: true, // 실제로는 드래그하지 않음
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isActive ? 1 : 0,
  };

  if (!isActive) return null;

  return (
    <div
      style={style}
      className="text-xs text-blue-600 mb-2 px-2 py-1 bg-blue-50 rounded"
    >
      드래그 중...
    </div>
  );
}

function Sidebar() {
  const {
    totalWidth,
    totalHeight,
    totalDepth,
    color,
    doorType,
    endPanels,
    endPanelSizes,
    ep20Options,
    showDimensions,
    units,
    setTotalWidth,
    setTotalHeight,
    setDoorType,
    toggleEndPanel,
    setEndPanelSize,
    toggleEP20,
    toggleDimensions,
    addUnit,
    updateUnit,
    removeUnit,
    reorderUnits,
    autoGenerateUnits,
    calculateUnitLayout,
    recalculatePositions,
    calculateTopEP
  } = useClosetStore();

  // 초기 로드 시 자동 통 생성
  React.useEffect(() => {
    if (units.length === 0) {
      autoGenerateUnits();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const [editingUnit, setEditingUnit] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<Partial<ClosetUnit>>({});
  const [activeDragId, setActiveDragId] = useState<string | null>(null);

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, {
      coordinateGetter: sortableKeyboardCoordinates,
    })
  );

  const handleAddUnit = (isHalfUnit: boolean = false) => {
    const sortedUnits = [...units].sort((a, b) => (a.order || 0) - (b.order || 0));
    const maxOrder = sortedUnits.length > 0 ? Math.max(...sortedUnits.map(u => u.order || 0)) : -1;
    
    // EP 기본값 계산
    const baseEPSize = 50;
    const minEPSize = 20;
    const epLeftBase = ep20Options.left ? minEPSize : baseEPSize;
    const epRightBase = ep20Options.right ? minEPSize : baseEPSize;
    
    // 현재 통 너비 합계
    const currentUnitsWidth = sortedUnits.reduce((sum, unit) => sum + unit.width, 0);
    
    // 사용 가능한 너비 계산: totalWidth - 좌측 EP - 우측 EP - 현재 통 너비 합계
    const availableWidth = totalWidth - epLeftBase - epRightBase - currentUnitsWidth;
    
    // TemplateType 타입 체크를 위해 사용
    const defaultTemplate: TemplateType = 'A';
    
    // 새 통의 높이 결정: 기존 통이 있으면 기존 통의 높이 사용, 없으면 기본값 사용
    let newUnitHeight: number;
    if (sortedUnits.length > 0) {
      // 기존 통들의 높이 중 가장 많이 사용된 높이 선택
      const heightCounts = new Map<number, number>();
      sortedUnits.forEach(unit => {
        heightCounts.set(unit.height, (heightCounts.get(unit.height) || 0) + 1);
      });
      let maxCount = 0;
      let mostCommonHeight = sortedUnits[0].height; // 기본값
      heightCounts.forEach((count, height) => {
        if (count > maxCount) {
          maxCount = count;
          mostCommonHeight = height;
        }
      });
      newUnitHeight = mostCommonHeight;
    } else {
      // 기존 통이 없으면 기본 높이 사용
      newUnitHeight = UNIT_HEIGHTS[0];
    }
    
    // 새 통의 너비 결정 (사용 가능한 공간 내에서 표준 규격 선택)
    // 중요: availableWidth를 절대 초과하지 않도록 보장
    let newUnitWidth: number;
    if (isHalfUnit) {
      // 반통: 사용 가능한 공간에 맞는 가장 큰 반통 규격 선택 (최대 600mm)
      const maxHalfWidth = 600;
      const suitableHalfWidths = HALF_UNIT_WIDTHS.filter(w => w <= Math.min(availableWidth, maxHalfWidth));
      newUnitWidth = suitableHalfWidths.length > 0 
        ? suitableHalfWidths[suitableHalfWidths.length - 1] // 가장 큰 것
        : Math.min(HALF_UNIT_WIDTHS[0], availableWidth); // 사용 가능한 공간이 없으면 최소 크기 또는 availableWidth 중 작은 것
    } else {
      // 통: 사용 가능한 공간에 맞는 가장 큰 통 규격 선택
      const suitableFullWidths = UNIT_WIDTHS.filter(w => w <= availableWidth);
      if (suitableFullWidths.length > 0) {
        newUnitWidth = suitableFullWidths[suitableFullWidths.length - 1]; // 가장 큰 것
      } else {
        // 사용 가능한 공간이 없으면 50 단위로 반올림하여 최대한 큰 값 선택
        // 단, availableWidth를 절대 초과하지 않도록 보장
        const roundedWidth = Math.floor(availableWidth / 50) * 50;
        // 750mm 이상이면서 availableWidth 이하인 값 선택
        newUnitWidth = Math.max(750, Math.min(roundedWidth, availableWidth));
      }
    }
    
    const newUnit: ClosetUnit = {
      id: `unit-${Date.now()}`,
      width: newUnitWidth,
      height: newUnitHeight,
      depth: totalDepth,
      template: defaultTemplate,
      position: 0,
      isHalfUnit,
      order: maxOrder + 1
    };
    
    addUnit(newUnit);
    
    // 통 추가 후 레이아웃 자동 재계산 (기존 통들의 너비 조정 포함)
    setTimeout(() => {
      calculateUnitLayout();
      calculateTopEP();
    }, 0);
  };

  const handleEditUnit = (unit: ClosetUnit) => {
    setEditingUnit(unit.id);
    setEditForm({ ...unit });
  };

  const handleSaveUnit = (id: string) => {
    updateUnit(id, editForm);
    setEditingUnit(null);
    setEditForm({});
    // updateUnit 내부에서 이미 recalculatePositions와 calculateTopEP가 호출됨
  };

  const handleCancelEdit = () => {
    setEditingUnit(null);
    setEditForm({});
  };

  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;
    setActiveDragId(null);

    if (over && active.id !== over.id) {
      const oldIndex = sortedUnits.findIndex((u) => u.id === active.id);
      const newIndex = sortedUnits.findIndex((u) => u.id === over.id);

      if (oldIndex !== -1 && newIndex !== -1) {
        // arrayMove를 사용하여 배열 재정렬
        const reorderedUnits = arrayMove(sortedUnits, oldIndex, newIndex);
        // 재정렬된 순서에 따라 order 업데이트
        reorderedUnits.forEach((unit, index) => {
          if (unit.order !== index) {
            updateUnit(unit.id, { order: index });
          }
        });
        reorderUnits(oldIndex, newIndex);
        setTimeout(() => {
          calculateUnitLayout();
        }, 0);
      }
    }
  };

  // 드래그 시작 시 활성 ID 추적 (CSS 스타일 적용을 위해)
  const handleDragStart = (event: any) => {
    setActiveDragId(event.active.id as string);
  };

  const sortedUnits = [...units].sort((a, b) => (a.order || 0) - (b.order || 0));

  return (
    <aside className="w-80 bg-white border-r border-gray-200 p-4 overflow-y-auto">
      <div className="space-y-6">
        {/* 파라메트릭 디자인 컨트롤 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">파라메트릭 디자인</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">
                너비: {totalWidth}mm
              </label>
              <input
                type="range"
                min="1000"
                max="10000"
                step="10"
                value={totalWidth}
                onChange={(e) => setTotalWidth(Number(e.target.value))}
                className="w-full"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">
                높이: {totalHeight}mm
              </label>
              <input
                type="range"
                min="2000"
                max="3000"
                step="10"
                value={totalHeight}
                onChange={(e) => setTotalHeight(Number(e.target.value))}
                className="w-full"
              />
            </div>
          </div>
        </div>

        {/* 크기 설정 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">설치 공간 (mm)</h3>
          <div className="space-y-3">
            <div>
              <label className="block text-xs text-gray-600 mb-1">너비</label>
              <input
                type="number"
                value={totalWidth}
                onChange={(e) => {
                  const newWidth = Number(e.target.value);
                  setTotalWidth(newWidth);
                  // setTotalWidth 내부에서 autoGenerateUnits가 호출되므로
                  // 추가 계산은 필요 없음 (autoGenerateUnits 내부에서 처리됨)
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                min="1000"
                max="10000"
                step="10"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">천장 높이</label>
              <input
                type="number"
                value={totalHeight}
                onChange={(e) => {
                  setTotalHeight(Number(e.target.value));
                  setTimeout(() => calculateTopEP(), 0);
                }}
                className="w-full px-3 py-2 border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500"
                min="2000"
                max="3000"
                step="10"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-600 mb-1">깊이</label>
              <input
                type="number"
                value={totalDepth}
                readOnly
                className="w-full px-3 py-2 border border-gray-300 rounded bg-gray-50"
              />
            </div>
          </div>
        </div>

        {/* 색상 설정 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">색상</h3>
          <input
            type="color"
            value={color}
            onChange={(e) => useClosetStore.setState({ color: e.target.value })}
            className="w-full h-10 border border-gray-300 rounded cursor-pointer"
          />
        </div>

        {/* 문 타입 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">문 타입</h3>
          <div className="space-y-2">
            {(['sliding', 'swing', 'open'] as const).map((type) => (
              <label key={type} className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="doorType"
                  value={type}
                  checked={doorType === type}
                  onChange={() => setDoorType(type)}
                  className="mr-2"
                />
                <span className="text-sm">
                  {type === 'sliding' ? '미닫이' : type === 'swing' ? '여닫이' : '오픈'}
                </span>
              </label>
            ))}
          </div>
        </div>

        {/* EP 설정 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">EP</h3>
          <div className="space-y-3">
            {(['left', 'right', 'top'] as const).map((position) => (
              <div key={position} className="space-y-2">
                <label className="flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={endPanels[position]}
                    onChange={() => {
                      toggleEndPanel(position);
                      setTimeout(() => {
                        if (position === 'top') {
                          calculateTopEP();
                        } else {
                          calculateUnitLayout();
                          calculateTopEP();
                        }
                      }, 0);
                    }}
                    className="mr-2"
                  />
                  <span className="text-sm">
                    {position === 'left' ? '좌측' : position === 'right' ? '우측' : '상단'}
                  </span>
                </label>
                {endPanels[position] && (
                  <div className="ml-6 space-y-2">
                    <label className="block text-xs text-gray-600 mb-1">
                      크기 (mm) {position === 'top' && '(자동 계산)'}
                    </label>
                    <input
                      type="number"
                      value={endPanelSizes[position]}
                      onChange={(e) => {
                        setEndPanelSize(position, Number(e.target.value));
                        setTimeout(() => {
                          if (position !== 'top') {
                            // EP 수정 시 통 너비는 유지하고 위치만 재계산
                            recalculatePositions();
                            calculateTopEP();
                          } else {
                            calculateTopEP();
                          }
                        }, 0);
                      }}
                      disabled={position === 'top'}
                      className="w-full px-2 py-1 text-xs border border-gray-300 rounded focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-100"
                      min="10"
                      max="200"
                      step="1"
                    />
                    {(position === 'left' || position === 'right') && (
                      <label className="flex items-center cursor-pointer">
                        <input
                          type="checkbox"
                          checked={ep20Options[position === 'left' ? 'right' : 'left']}
                          onChange={() => {
                            toggleEP20(position);
                          }}
                          className="mr-2"
                        />
                        <span className="text-xs text-gray-600">EP 20mm 적용</span>
                      </label>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>

        {/* 기타 설정 */}
        <div>
          <h3 className="text-sm font-semibold mb-3">표시</h3>
          <label className="flex items-center cursor-pointer">
            <input
              type="checkbox"
              checked={showDimensions}
              onChange={toggleDimensions}
              className="mr-2"
            />
            <span className="text-sm">치수 표시</span>
          </label>
        </div>

        {/* 통 관리 */}
        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">통 목록</h3>
            <div className="flex gap-2">
              <button
                onClick={() => {
                  autoGenerateUnits();
                }}
                className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700 transition-colors"
                title="자동 생성"
              >
                자동
              </button>
              <button
                onClick={() => handleAddUnit(false)}
                className="px-3 py-1 text-xs bg-blue-600 text-white rounded hover:bg-blue-700 transition-colors"
                title="통 추가"
              >
                통
              </button>
              <button
                onClick={() => handleAddUnit(true)}
                className="px-3 py-1 text-xs bg-purple-600 text-white rounded hover:bg-purple-700 transition-colors"
                title="반통 추가"
              >
                반통
              </button>
            </div>
          </div>
          <DndContext
            sensors={sensors}
            collisionDetection={closestCenter}
            onDragStart={handleDragStart}
            onDragEnd={handleDragEnd}
          >
            <SortableContext
              items={[
                ...sortedUnits.map((u) => u.id),
                ...(activeDragId ? ['drag-indicator'] : []), // useSortable을 위한 임시 ID
              ]}
              strategy={verticalListSortingStrategy}
            >
              <div 
                className="space-y-2 max-h-96 overflow-y-auto"
                style={activeDragId ? {
                  transform: CSS.Translate.toString({ x: 0, y: 0, scaleX: 1, scaleY: 1 }),
                } : undefined}
              >
                {activeDragId && <DragIndicator isActive={true} />}
                {sortedUnits.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-4">통이 없습니다</p>
                ) : (
                  sortedUnits.map((unit, index) => (
                    <SortableUnitItem
                      key={unit.id}
                      unit={unit}
                      index={index}
                      editingUnit={editingUnit}
                      editForm={editForm}
                      onEdit={handleEditUnit}
                      onSave={handleSaveUnit}
                      onCancel={handleCancelEdit}
                      onEditFormChange={setEditForm}
                      onRemove={(id) => {
                        removeUnit(id);
                        setTimeout(() => {
                          calculateUnitLayout();
                          calculateTopEP();
                        }, 0);
                      }}
                      UNIT_WIDTHS={UNIT_WIDTHS}
                      HALF_UNIT_WIDTHS={HALF_UNIT_WIDTHS}
                      UNIT_HEIGHTS={UNIT_HEIGHTS}
                    />
                  ))
                )}
              </div>
            </SortableContext>
          </DndContext>
        </div>
      </div>
    </aside>
  );
}

export default Sidebar;

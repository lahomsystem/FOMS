import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import { ClosetUnit } from '../types';
import { Trash2, Edit2, GripVertical } from 'lucide-react';

interface SortableUnitItemProps {
  unit: ClosetUnit;
  index: number;
  editingUnit: string | null;
  editForm: Partial<ClosetUnit>;
  onEdit: (unit: ClosetUnit) => void;
  onSave: (id: string) => void;
  onCancel: () => void;
  onEditFormChange: (form: Partial<ClosetUnit>) => void;
  onRemove: (id: string) => void;
  UNIT_WIDTHS: readonly number[];
  HALF_UNIT_WIDTHS: readonly number[];
  UNIT_HEIGHTS: readonly number[];
}

function SortableUnitItem({
  unit,
  index,
  editingUnit,
  editForm,
  onEdit,
  onSave,
  onCancel,
  onEditFormChange,
  onRemove,
  UNIT_WIDTHS,
  HALF_UNIT_WIDTHS,
  UNIT_HEIGHTS,
}: SortableUnitItemProps) {
  const {
    attributes,
    listeners,
    setNodeRef,
    transform,
    transition,
    isDragging,
  } = useSortable({ id: unit.id });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  return (
    <div
      ref={setNodeRef}
      style={style}
      className={`p-3 border border-gray-200 rounded bg-gray-50 hover:bg-gray-100 transition-colors ${
        isDragging ? 'shadow-lg' : ''
      }`}
    >
      {editingUnit === unit.id ? (
        <div className="space-y-2">
          <div>
            <label className="block text-xs text-gray-600 mb-1">너비 (mm)</label>
            <select
              value={editForm.width || unit.width}
              onChange={(e) => {
                const width = Number(e.target.value);
                onEditFormChange({
                  ...editForm,
                  width,
                  isHalfUnit: HALF_UNIT_WIDTHS.includes(width as any),
                });
              }}
              className="w-full px-2 py-1 text-xs border border-gray-300 rounded"
            >
              <optgroup label="통">
                {UNIT_WIDTHS.map((w) => (
                  <option key={w} value={w}>
                    {w}mm
                  </option>
                ))}
              </optgroup>
              <optgroup label="반통">
                {HALF_UNIT_WIDTHS.map((w) => (
                  <option key={w} value={w}>
                    {w}mm
                  </option>
                ))}
              </optgroup>
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">높이 (mm)</label>
            <select
              value={editForm.height || unit.height}
              onChange={(e) =>
                onEditFormChange({ ...editForm, height: Number(e.target.value) })
              }
              className="w-full px-2 py-1 text-xs border border-gray-300 rounded"
            >
              {UNIT_HEIGHTS.map((h) => (
                <option key={h} value={h}>
                  {h}mm
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-xs text-gray-600 mb-1">템플릿</label>
            <select
              value={editForm.template || unit.template}
              onChange={(e) =>
                onEditFormChange({
                  ...editForm,
                  template: e.target.value as any,
                })
              }
              className="w-full px-2 py-1 text-xs border border-gray-300 rounded"
            >
              {(['A', 'B', 'C', 'D', 'E', 'F', 'G', 'H', 'I', 'J', 'K'] as const).map(
                (t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                )
              )}
            </select>
          </div>
          <div className="flex gap-2">
            <button
              onClick={() => onSave(unit.id)}
              className="flex-1 px-2 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700"
            >
              저장
            </button>
            <button
              onClick={onCancel}
              className="flex-1 px-2 py-1 text-xs bg-gray-400 text-white rounded hover:bg-gray-500"
            >
              취소
            </button>
          </div>
        </div>
      ) : (
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <div
                {...attributes}
                {...listeners}
                className="cursor-grab active:cursor-grabbing"
              >
                <GripVertical size={16} className="text-gray-400" />
              </div>
              <span className="text-sm font-medium">
                {unit.isHalfUnit ? '반통' : '통'} {index + 1}
              </span>
            </div>
            <div className="flex gap-1">
              <button
                onClick={() => onEdit(unit)}
                className="p-1 text-gray-600 hover:text-blue-600"
                title="수정"
              >
                <Edit2 size={14} />
              </button>
              <button
                onClick={() => onRemove(unit.id)}
                className="p-1 text-gray-600 hover:text-red-600"
                title="삭제"
              >
                <Trash2 size={14} />
              </button>
            </div>
          </div>
          <div className="text-xs text-gray-600 space-y-1">
            <div>너비: {unit.width}mm</div>
            <div>높이: {unit.height}mm</div>
            <div>템플릿: {unit.template}</div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SortableUnitItem;


import { useClosetStore } from '../stores/closetStore';
import { Sliders } from 'lucide-react';

function ParametricControls() {
  const {
    totalWidth,
    totalHeight,
    totalDepth,
    setTotalWidth,
    setTotalHeight,
  } = useClosetStore();

  return (
    <div className="bg-white rounded-lg shadow-lg border border-gray-200 p-4">
      <div className="flex items-center gap-2 mb-4">
        <Sliders size={18} className="text-blue-600" />
        <h3 className="text-sm font-semibold">파라메트릭 디자인</h3>
      </div>
      
      <div className="space-y-4">
        {/* 실시간 치수 조정 */}
        <div>
          <label className="block text-xs text-gray-600 mb-2">
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
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>1000mm</span>
            <span>10000mm</span>
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-600 mb-2">
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
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>2000mm</span>
            <span>3000mm</span>
          </div>
        </div>

        <div>
          <label className="block text-xs text-gray-600 mb-2">
            깊이: {totalDepth}mm (고정)
          </label>
          <input
            type="range"
            min="500"
            max="800"
            step="10"
            value={totalDepth}
            disabled
            className="w-full opacity-50"
          />
          <div className="flex justify-between text-xs text-gray-400 mt-1">
            <span>500mm</span>
            <span>800mm</span>
          </div>
        </div>
      </div>

      {/* 빠른 프리셋 */}
      <div className="mt-4 pt-4 border-t border-gray-200">
        <label className="block text-xs text-gray-600 mb-2">빠른 프리셋</label>
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => {
              setTotalWidth(3400);
              setTotalHeight(2400);
            }}
            className="px-3 py-2 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors"
          >
            표준 (3400×2400)
          </button>
          <button
            onClick={() => {
              setTotalWidth(3000);
              setTotalHeight(2400);
            }}
            className="px-3 py-2 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors"
          >
            소형 (3000×2400)
          </button>
          <button
            onClick={() => {
              setTotalWidth(4000);
              setTotalHeight(2400);
            }}
            className="px-3 py-2 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors"
          >
            대형 (4000×2400)
          </button>
          <button
            onClick={() => {
              setTotalWidth(5000);
              setTotalHeight(2400);
            }}
            className="px-3 py-2 text-xs bg-blue-50 text-blue-600 rounded hover:bg-blue-100 transition-colors"
          >
            초대형 (5000×2400)
          </button>
        </div>
      </div>
    </div>
  );
}

export default ParametricControls;


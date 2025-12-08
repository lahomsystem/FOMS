import { useState } from 'react';
import { useClosetStore } from '../stores/closetStore';
import { 
  Move, 
  RotateCw, 
  ZoomIn, 
  ZoomOut, 
  Ruler, 
  Save,
  FolderOpen,
  FileText,
  Download
} from 'lucide-react';
import { saveProject, loadProject, getProjectList, ProjectMetadata } from '../utils/projectStorage';
import { generateEstimatePDF, generateBlueprintPDF } from '../utils/pdfExport';
import { canvasToBase64 } from '../utils/canvasUtils';

function Toolbar() {
  const { 
    showDimensions, 
    toggleDimensions,
    getProjectData,
    loadProject: loadProjectToStore
  } = useClosetStore();
  
  const [showProjectList, setShowProjectList] = useState(false);
  const [projects, setProjects] = useState<ProjectMetadata[]>([]);

  // 프로젝트 저장
  const handleSave = async () => {
    const projectName = prompt('프로젝트 이름을 입력하세요:', `프로젝트_${new Date().toLocaleDateString()}`);
    if (!projectName) return;

    try {
      const canvas = document.querySelector('canvas');
      const thumbnail = canvas ? canvasToBase64(canvas) : undefined;
      const projectData = getProjectData();
      
      await saveProject(projectData, projectName, thumbnail);
      alert('프로젝트가 저장되었습니다.');
    } catch (error) {
      console.error('저장 실패:', error);
      alert('프로젝트 저장에 실패했습니다.');
    }
  };

  // 프로젝트 목록 불러오기
  const handleLoadList = async () => {
    try {
      const projectList = await getProjectList();
      setProjects(projectList);
      setShowProjectList(true);
    } catch (error) {
      console.error('프로젝트 목록 불러오기 실패:', error);
      alert('프로젝트 목록을 불러올 수 없습니다.');
    }
  };

  // 프로젝트 불러오기
  const handleLoad = async (projectId: string) => {
    try {
      const projectData = await loadProject(projectId);
      if (projectData) {
        loadProjectToStore(projectData);
        setShowProjectList(false);
        alert('프로젝트가 불러와졌습니다.');
      } else {
        alert('프로젝트를 불러올 수 없습니다.');
      }
    } catch (error) {
      console.error('불러오기 실패:', error);
      alert('프로젝트 불러오기에 실패했습니다.');
    }
  };

  // PDF 견적서 생성
  const handleExportPDF = () => {
    try {
      const projectData = getProjectData();
      generateEstimatePDF(projectData);
    } catch (error) {
      console.error('PDF 생성 실패:', error);
      alert('PDF 생성에 실패했습니다.');
    }
  };

  // 설계도 PDF 생성
  const handleExportBlueprint = () => {
    try {
      const projectData = getProjectData();
      generateBlueprintPDF(projectData);
    } catch (error) {
      console.error('설계도 PDF 생성 실패:', error);
      alert('설계도 PDF 생성에 실패했습니다.');
    }
  };

  return (
    <>
      <div className="absolute top-4 left-4 z-10 bg-white rounded-lg shadow-lg border border-gray-200 p-2">
        <div className="flex flex-col gap-2">
          {/* 뷰 컨트롤 */}
          <div className="flex gap-1 border-b border-gray-200 pb-2">
              <button
                onClick={() => {
                  // 카메라 리셋 (기본 뷰로)
                  const canvas = document.querySelector('canvas');
                  if (canvas) {
                    // ArcRotateCamera는 마우스로 직접 조작 가능
                    // 여기서는 힌트만 제공
                  }
                }}
                className="p-2 hover:bg-gray-100 rounded transition-colors"
                title="3D 뷰: 마우스 드래그로 회전, 휠로 줌"
              >
                <Move size={18} />
              </button>
              <button
                className="p-2 hover:bg-gray-100 rounded transition-colors"
                title="3D 뷰: 마우스 드래그로 회전"
              >
                <RotateCw size={18} />
              </button>
              <button
                onClick={() => {
                  // 줌 인 (카메라 거리 감소)
                  const canvas = document.querySelector('canvas');
                  if (canvas) {
                    // ArcRotateCamera는 휠로 줌 가능
                    // 프로그래밍 방식으로는 scene의 activeCamera를 통해 조작
                  }
                }}
                className="p-2 hover:bg-gray-100 rounded transition-colors"
                title="줌 인 (마우스 휠 위로)"
              >
                <ZoomIn size={18} />
              </button>
              <button
                onClick={() => {
                  // 줌 아웃 (카메라 거리 증가)
                }}
                className="p-2 hover:bg-gray-100 rounded transition-colors"
                title="줌 아웃 (마우스 휠 아래로)"
              >
                <ZoomOut size={18} />
              </button>
            </div>

          {/* 표시 옵션 */}
          <div className="flex flex-col gap-1 border-b border-gray-200 pb-2">
            <button
              onClick={toggleDimensions}
              className={`p-2 hover:bg-gray-100 rounded transition-colors ${
                showDimensions ? 'bg-blue-100 text-blue-600' : ''
              }`}
              title="치수 표시 (D)"
            >
              <Ruler size={18} />
            </button>
          </div>

          {/* 파일 작업 */}
          <div className="flex flex-col gap-1 border-b border-gray-200 pb-2">
            <button
              onClick={handleSave}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
              title="프로젝트 저장 (Ctrl+S)"
            >
              <Save size={18} />
            </button>
            <button
              onClick={handleLoadList}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
              title="프로젝트 불러오기 (Ctrl+O)"
            >
              <FolderOpen size={18} />
            </button>
          </div>

          {/* PDF 출력 */}
          <div className="flex flex-col gap-1">
            <button
              onClick={handleExportPDF}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
              title="견적서 PDF 출력"
            >
              <FileText size={18} />
            </button>
            <button
              onClick={handleExportBlueprint}
              className="p-2 hover:bg-gray-100 rounded transition-colors"
              title="설계도 PDF 출력"
            >
              <Download size={18} />
            </button>
          </div>
        </div>
      </div>

      {/* 프로젝트 목록 모달 */}
      {showProjectList && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-black bg-opacity-50">
          <div className="bg-white rounded-lg shadow-xl p-6 max-w-2xl w-full max-h-[80vh] overflow-y-auto">
            <div className="flex justify-between items-center mb-4">
              <h2 className="text-xl font-bold">프로젝트 목록</h2>
              <button
                onClick={() => setShowProjectList(false)}
                className="text-gray-500 hover:text-gray-700"
              >
                ✕
              </button>
            </div>
            <div className="space-y-2">
              {projects.length === 0 ? (
                <p className="text-gray-500 text-center py-8">저장된 프로젝트가 없습니다.</p>
              ) : (
                projects.map((project) => (
                  <div
                    key={project.id}
                    className="flex items-center justify-between p-3 border border-gray-200 rounded hover:bg-gray-50 cursor-pointer"
                    onClick={() => handleLoad(project.id)}
                  >
                    <div className="flex-1">
                      <h3 className="font-semibold">{project.name}</h3>
                      <p className="text-sm text-gray-500">
                        수정일: {new Date(project.updatedAt).toLocaleString('ko-KR')}
                      </p>
                    </div>
                    {project.thumbnail && (
                      <img
                        src={project.thumbnail}
                        alt="썸네일"
                        className="w-16 h-16 object-cover rounded border border-gray-200 ml-4"
                      />
                    )}
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}
    </>
  );
}

export default Toolbar;


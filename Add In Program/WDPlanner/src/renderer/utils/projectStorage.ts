import localforage from 'localforage';
import { ClosetConfig } from '../types';

// 프로젝트 저장소 초기화
const projectStore = localforage.createInstance({
  name: 'WDPlanner',
  storeName: 'projects',
  description: '붙박이장 설계 프로젝트 저장소'
});

export interface ProjectMetadata {
  id: string;
  name: string;
  createdAt: string;
  updatedAt: string;
  thumbnail?: string; // Base64 이미지
}

export interface SavedProject {
  metadata: ProjectMetadata;
  data: ClosetConfig;
}

/**
 * 프로젝트 목록 가져오기
 */
export async function getProjectList(): Promise<ProjectMetadata[]> {
  try {
    const keys = await projectStore.keys();
    const projects: ProjectMetadata[] = [];
    
    for (const key of keys) {
      const project = await projectStore.getItem<SavedProject>(key);
      if (project) {
        projects.push(project.metadata);
      }
    }
    
    return projects.sort((a, b) => 
      new Date(b.updatedAt).getTime() - new Date(a.updatedAt).getTime()
    );
  } catch (error) {
    console.error('프로젝트 목록 가져오기 실패:', error);
    return [];
  }
}

/**
 * 프로젝트 저장
 */
export async function saveProject(
  projectData: ClosetConfig,
  projectName: string,
  thumbnail?: string
): Promise<string> {
  try {
    const id = `project_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const now = new Date().toISOString();
    
    const project: SavedProject = {
      metadata: {
        id,
        name: projectName,
        createdAt: now,
        updatedAt: now,
        thumbnail,
      },
      data: projectData,
    };
    
    await projectStore.setItem(id, project);
    return id;
  } catch (error) {
    console.error('프로젝트 저장 실패:', error);
    throw error;
  }
}

/**
 * 프로젝트 업데이트
 */
export async function updateProject(
  id: string,
  projectData: ClosetConfig,
  projectName?: string,
  thumbnail?: string
): Promise<void> {
  try {
    const existing = await projectStore.getItem<SavedProject>(id);
    if (!existing) {
      throw new Error('프로젝트를 찾을 수 없습니다.');
    }
    
    const updated: SavedProject = {
      metadata: {
        ...existing.metadata,
        name: projectName || existing.metadata.name,
        updatedAt: new Date().toISOString(),
        thumbnail: thumbnail !== undefined ? thumbnail : existing.metadata.thumbnail,
      },
      data: projectData,
    };
    
    await projectStore.setItem(id, updated);
  } catch (error) {
    console.error('프로젝트 업데이트 실패:', error);
    throw error;
  }
}

/**
 * 프로젝트 불러오기
 */
export async function loadProject(id: string): Promise<ClosetConfig | null> {
  try {
    const project = await projectStore.getItem<SavedProject>(id);
    return project?.data || null;
  } catch (error) {
    console.error('프로젝트 불러오기 실패:', error);
    return null;
  }
}

/**
 * 프로젝트 삭제
 */
export async function deleteProject(id: string): Promise<void> {
  try {
    await projectStore.removeItem(id);
  } catch (error) {
    console.error('프로젝트 삭제 실패:', error);
    throw error;
  }
}

/**
 * 프로젝트 이름 변경
 */
export async function renameProject(id: string, newName: string): Promise<void> {
  try {
    const existing = await projectStore.getItem<SavedProject>(id);
    if (!existing) {
      throw new Error('프로젝트를 찾을 수 없습니다.');
    }
    
    const updated: SavedProject = {
      ...existing,
      metadata: {
        ...existing.metadata,
        name: newName,
        updatedAt: new Date().toISOString(),
      },
    };
    
    await projectStore.setItem(id, updated);
  } catch (error) {
    console.error('프로젝트 이름 변경 실패:', error);
    throw error;
  }
}





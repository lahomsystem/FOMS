import { useEffect, useRef } from 'react';
import { Engine, Scene, ArcRotateCamera, Vector3, Color3, StandardMaterial, MeshBuilder, Mesh, DynamicTexture, Color4, HemisphericLight, NoiseProceduralTexture } from '@babylonjs/core';
import { useClosetStore } from '../stores/closetStore';
import { BASE_HEIGHT } from '../types';

// 합판 재질 생성 (나무 질감)
const createPlywoodMaterial = (scene: Scene, color?: string): StandardMaterial => {
  const material = new StandardMaterial('plywood-mat', scene);
  
  // 합판 색상 (밝은 나무색/크림색)
  const woodColor = color ? Color3.FromHexString(color) : new Color3(0.95, 0.92, 0.85); // 밝은 베이지/크림색
  material.diffuseColor = woodColor;
  
  // 약간의 반사 효과
  material.specularColor = new Color3(0.3, 0.3, 0.3);
  material.specularPower = 32;
  
  // 나무 질감을 위한 노이즈 텍스처
  const noiseTexture = new NoiseProceduralTexture('wood-noise', 512, scene);
  noiseTexture.octaves = 3;
  noiseTexture.persistence = 0.5;
  noiseTexture.animationSpeedFactor = 0;
  
  // Bump 맵으로 질감 표현
  material.bumpTexture = noiseTexture;
  material.bumpTexture.level = 0.3;
  
  // 조명 활성화
  material.disableLighting = false;
  material.backFaceCulling = false;
  material.wireframe = false;
  
  return material;
};

// 설계도 스타일 재질 생성
const createBlueprintMaterial = (scene: Scene, wireframe: boolean): StandardMaterial => {
  const material = new StandardMaterial('blueprint-mat', scene);
  
  if (wireframe) {
    // 와이어프레임 모드: 검은색 선
    material.diffuseColor = Color3.Black();
    material.emissiveColor = Color3.Black();
    material.specularColor = Color3.Black();
    material.disableLighting = true;
    material.wireframe = true;
  } else {
    // 일반 모드: 중간 회색 단색 (설계도 스타일)
    const grayColor = new Color3(0.65, 0.65, 0.65); // 중간 회색 (약간 밝게)
    material.diffuseColor = grayColor;
    material.emissiveColor = grayColor.scale(0.4); // 자체 발광 증가 (더 밝게)
    material.specularColor = Color3.Black(); // 반사 없음
    material.disableLighting = false; // 조명 활성화 (약간의 그림자 효과)
    material.wireframe = false;
  }
  
  material.backFaceCulling = false;
  return material;
};

// 텍스트 텍스처 생성 (치수 표시용)
const createTextTexture = (scene: Scene, text: string, fontSize: number = 32): { texture: DynamicTexture; width: number; height: number } => {
  // 텍스트 길이에 맞게 텍스처 크기 조정
  const textWidth = text.length * fontSize * 0.6; // 대략적인 텍스트 너비
  const textureWidth = Math.max(256, Math.min(1024, textWidth + 40)); // 여유 공간 포함
  const textureHeight = Math.max(128, fontSize + 40); // 여유 공간 포함
  
  // 고유한 텍스처 이름 생성
  const textureName = `textTexture_${text}_${Date.now()}_${Math.random()}`;
  const texture = new DynamicTexture(textureName, { width: textureWidth, height: textureHeight }, scene);
  const ctx = texture.getContext() as CanvasRenderingContext2D;
  
  // 흰색 배경 그리기
  ctx.fillStyle = 'white';
  ctx.fillRect(0, 0, textureWidth, textureHeight);
  
  // 검은색 텍스트 그리기 (더 진하게)
  ctx.fillStyle = '#000000';
  ctx.font = `bold ${fontSize}px Arial`;
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  // 텍스트에 약간의 그림자 효과 추가 (가독성 향상)
  ctx.shadowColor = 'rgba(0, 0, 0, 0.3)';
  ctx.shadowBlur = 2;
  ctx.shadowOffsetX = 1;
  ctx.shadowOffsetY = 1;
  ctx.fillText(text, textureWidth / 2, textureHeight / 2);
  
  texture.update();
  return { texture, width: textureWidth, height: textureHeight };
};

// 프레임 생성
function createFrame(scene: Scene, width: number, height: number, depth: number, material: StandardMaterial, wireframe: boolean): Mesh[] {
  const widthCm = width / 10;
  const heightCm = height / 10;
  const depthCm = depth / 10;
  const frames: Mesh[] = [];
  const thickness = wireframe ? 0.1 : 2.0; // cm (와이어프레임: 얇은 선, 실제: 합판 두께 20mm)

  // 좌측 프레임 (totalWidth의 왼쪽 끝에 위치)
  const leftFrame = MeshBuilder.CreateBox('leftFrame', { 
    width: thickness, 
    height: heightCm, 
    depth: depthCm 
  }, scene);
  // 프레임의 중심 = totalWidth의 왼쪽 끝 + thickness / 2
  leftFrame.position = new Vector3(-widthCm / 2 + thickness / 2, 0, 0);
  leftFrame.material = material;
  frames.push(leftFrame);

  // 우측 프레임 (totalWidth의 오른쪽 끝에 위치)
  const rightFrame = MeshBuilder.CreateBox('rightFrame', { 
    width: thickness, 
    height: heightCm, 
    depth: depthCm 
  }, scene);
  // 프레임의 중심 = totalWidth의 오른쪽 끝 - thickness / 2
  rightFrame.position = new Vector3(widthCm / 2 - thickness / 2, 0, 0);
  rightFrame.material = material;
  frames.push(rightFrame);

  // 상단 프레임 (totalHeight의 위쪽 끝에 위치)
  const topFrame = MeshBuilder.CreateBox('topFrame', { 
    width: widthCm, 
    height: thickness, 
    depth: depthCm 
  }, scene);
  // 프레임의 중심 = totalHeight의 위쪽 끝 - thickness / 2
  topFrame.position = new Vector3(0, heightCm / 2 - thickness / 2, 0);
  topFrame.material = material;
  frames.push(topFrame);

  // 하단 프레임 (totalHeight의 아래쪽 끝에 위치)
  const bottomFrame = MeshBuilder.CreateBox('bottomFrame', { 
    width: widthCm, 
    height: thickness, 
    depth: depthCm 
  }, scene);
  // 프레임의 중심 = totalHeight의 아래쪽 끝 + thickness / 2
  bottomFrame.position = new Vector3(0, -heightCm / 2 + thickness / 2, 0);
  bottomFrame.material = material;
  frames.push(bottomFrame);

  return frames;
}

// 뒷판 생성 (베이스판부터 상부 EP까지 전체 높이)
function createBackPanel(scene: Scene, width: number, height: number, depth: number, material: StandardMaterial, wireframe: boolean): Mesh {
  const widthCm = width / 10;
  const heightCm = height / 10;
  const depthCm = depth / 10;
  const thickness = wireframe ? 0.1 : 2.0; // cm (합판 두께 20mm)

  // 뒷판은 베이스판부터 상부 EP까지 전체 높이를 차지
  const backPanel = MeshBuilder.CreateBox('backPanel', { 
    width: widthCm, 
    height: heightCm, 
    depth: thickness 
  }, scene);
  // 뒷판은 뒤쪽에 위치 (z = -depthCm/2 + thickness/2)
  backPanel.position = new Vector3(0, 0, -depthCm / 2 + thickness / 2);
  backPanel.material = material;
  return backPanel;
}

// 베이스판 생성 (설계도 스타일)
// 베이스판은 totalWidth 전체 너비를 차지하고, 하단에 위치
function createBasePanel(scene: Scene, width: number, height: number, depth: number, baseHeight: number, material: StandardMaterial): Mesh {
  const widthCm = width / 10;
  const depthCm = depth / 10;
  const baseHeightCm = baseHeight / 10;
  const totalHeightCm = height / 10;

  const base = MeshBuilder.CreateBox('basePanel', { 
    width: widthCm, 
    height: baseHeightCm, 
    depth: depthCm 
  }, scene);
  // 베이스판의 위쪽 끝이 totalHeight의 아래쪽 끝(-totalHeightCm/2)에 맞춤
  // 베이스판 중심 = -totalHeightCm/2 + baseHeightCm/2
  base.position = new Vector3(0, -totalHeightCm / 2 + baseHeightCm / 2, 0);
  base.material = material;
  return base;
}

// EP 생성 (설계도 스타일)
function createEndPanel(
  scene: Scene,
  position: 'left' | 'right' | 'top',
  totalWidth: number,
  totalHeight: number,
  depth: number,
  epSize: number,
  material: StandardMaterial,
  _topEpWidth?: number // 사용하지 않음 (상부 EP는 항상 totalWidth 사용)
): Mesh | null {
  const totalWidthCm = totalWidth / 10;
  const totalHeightCm = totalHeight / 10;
  const depthCm = depth / 10;
  const epSizeCm = epSize / 10;

  if (position === 'left') {
    const panel = MeshBuilder.CreateBox('leftEP', { 
      width: epSizeCm, 
      height: totalHeightCm, 
      depth: depthCm 
    }, scene);
    // 좌측 EP는 totalWidth 내부에 위치: EP의 왼쪽 끝이 totalWidth의 왼쪽 끝(-totalWidthCm/2)에 맞춤
    // EP 중심 = -totalWidthCm/2 + epSizeCm/2
    // EP는 베이스판부터 상부 EP까지 전체 높이를 차지
    panel.position = new Vector3(-totalWidthCm / 2 + epSizeCm / 2, 0, 0);
    
    // EP 재질 (약간 더 어두운 회색)
    const epMaterial = material.clone('leftEP-mat');
    if (!material.wireframe) {
      const darkGrayColor = new Color3(0.5, 0.5, 0.5); // 약간 더 어두운 회색
      epMaterial.diffuseColor = darkGrayColor;
      epMaterial.emissiveColor = darkGrayColor.scale(0.3);
      epMaterial.specularColor = Color3.Black();
      epMaterial.disableLighting = false;
    }
    panel.material = epMaterial;
    return panel;
  }

  if (position === 'right') {
    const panel = MeshBuilder.CreateBox('rightEP', { 
      width: epSizeCm, 
      height: totalHeightCm, 
      depth: depthCm 
    }, scene);
    // 우측 EP는 totalWidth 내부에 위치: EP의 오른쪽 끝이 totalWidth의 오른쪽 끝(totalWidthCm/2)에 맞춤
    // EP 중심 = totalWidthCm/2 - epSizeCm/2
    // EP는 베이스판부터 상부 EP까지 전체 높이를 차지
    panel.position = new Vector3(totalWidthCm / 2 - epSizeCm / 2, 0, 0);
    
    // EP 재질 (약간 더 어두운 회색)
    const epMaterial = material.clone('rightEP-mat');
    if (!material.wireframe) {
      const darkGrayColor = new Color3(0.5, 0.5, 0.5); // 약간 더 어두운 회색
      epMaterial.diffuseColor = darkGrayColor;
      epMaterial.emissiveColor = darkGrayColor.scale(0.3);
      epMaterial.specularColor = Color3.Black();
      epMaterial.disableLighting = false;
    }
    panel.material = epMaterial;
    return panel;
  }

  if (position === 'top') {
    // 상부 EP 너비: totalWidth 전체 (좌우 EP는 이미 totalWidth 내부에 있음)
    // 상부 EP는 좌우 EP의 외부 끝과 맞춰져야 함
    // topEpWidth 파라미터는 무시하고 항상 totalWidth 사용
    const panel = MeshBuilder.CreateBox('topEP', { 
      width: totalWidthCm, 
      height: epSizeCm, 
      depth: depthCm 
    }, scene);
    // 상부 EP는 totalHeight 내부에 위치: EP의 아래쪽 끝이 totalHeight의 위쪽 끝(totalHeightCm/2)에 맞춤
    // EP 중심 = totalHeightCm/2 - epSizeCm/2
    // 상부 EP는 totalWidth 전체를 가로지름 (좌우 EP와 라인 맞춤)
    panel.position = new Vector3(0, totalHeightCm / 2 - epSizeCm / 2, 0);
    panel.material = material;
    return panel;
  }

  return null;
}

// 통 내부 구조 생성 (설계도 스타일 - 정면도에서 보이는 선)
function createUnitInterior(scene: Scene, unit: { template: string }, widthCm: number, heightCm: number, depthCm: number, baseHeightCm: number, totalHeightCm: number, _material: StandardMaterial, wireframe: boolean, _is3DMode: boolean = false): Mesh[] {
  const interiorElements: Mesh[] = [];
  const unitHeight = heightCm - baseHeightCm;
  // 전체 좌표계 기준으로 baseY 계산 (통의 베이스 위쪽 끝)
  const baseY = -totalHeightCm / 2 + baseHeightCm;
  const thickness = wireframe ? 0.5 : 2.0; // cm (와이어프레임에서도 두껍게)
  // 내부 구조를 통의 정중앙에 배치 (z = 0, 통의 중심)
  const frontZ = 0;
  
  // 내부 구조용 재질 (밝은 색상으로 구분하여 명확하게 보이도록)
  const interiorMaterial = new StandardMaterial(`interior-${unit.template}`, scene);
  const brightColor = new Color3(1.0, 0.0, 0.0); // 빨간색 (매우 명확한 대비)
  interiorMaterial.diffuseColor = brightColor;
  interiorMaterial.emissiveColor = brightColor.scale(2.0); // 자체 발광 최대
  interiorMaterial.specularColor = Color3.Black();
  interiorMaterial.disableLighting = false;
  interiorMaterial.alpha = 1.0; // 완전 불투명
  interiorMaterial.wireframe = wireframe;
  
  // 행거용 파란색 재질
  const rodMaterial = new StandardMaterial(`rod-${unit.template}`, scene);
  const blueColor = new Color3(0.0, 0.4, 1.0); // 파란색
  rodMaterial.diffuseColor = blueColor;
  rodMaterial.emissiveColor = blueColor.scale(0.8); // 자체 발광
  rodMaterial.specularColor = Color3.Black();
  rodMaterial.disableLighting = false;
  rodMaterial.alpha = 1.0;
  rodMaterial.wireframe = wireframe;

  switch (unit.template) {
    case 'A': // 반옷장 - 상하 두 구획, 각 구획에 행거
      {
        // 중간 구분선 (가로 선반) - 상하 구획을 정확히 중앙에서 나눔
        // 좌우 프레임 두께를 고려하여 몸통 폭에 맞춰 자동 조절
        const dividerY = baseY + unitHeight * 0.5; // 통의 정중앙
        const dividerWidth = widthCm - thickness * 2; // 좌우 프레임 두께 제외한 내부 너비
        const divider = MeshBuilder.CreateBox('divider-A', {
          width: dividerWidth, // 좌우 프레임에 맞닿도록 몸통 폭에 맞춰 자동 조절
          height: thickness, // 세로 두께
          depth: depthCm * 0.8 // 깊이 방향 두께 (가로 판으로 명확하게)
        }, scene);
        divider.position = new Vector3(0, dividerY, frontZ);
        divider.material = interiorMaterial;
        interiorElements.push(divider);
        
        // 상단 구획 행거 (천판(상단)에서 100mm 아래)
        // 천판 위치 = baseY + unitHeight, 100mm = 10cm
        // 좌우 프레임에 맞닿도록 몸통 폭에 맞춰 자동 조절
        const topRodY = baseY + unitHeight - 10; // 천판에서 100mm 아래
        const rodLength = widthCm - thickness * 2; // 좌우 프레임 두께 제외한 내부 너비
        const topRod = MeshBuilder.CreateCylinder('rod-top-A', { 
          diameter: 2.0, // cm (행거 지름)
          height: rodLength // 좌우 프레임에 맞닿도록 몸통 폭에 맞춰 자동 조절
        }, scene);
        topRod.position = new Vector3(0, topRodY, frontZ);
        topRod.rotation.z = Math.PI / 2; // Z축 중심 회전으로 X축 방향 수평 배치 (통의 가로 방향)
        topRod.material = rodMaterial;
        interiorElements.push(topRod);
        
        // 하단 구획 행거 (중판(중간 파티션)에서 100mm 아래)
        // 중판 위치 = dividerY, 100mm = 10cm
        // 좌우 프레임에 맞닿도록 몸통 폭에 맞춰 자동 조절
        const bottomRodY = dividerY - 10; // 중판에서 100mm 아래
        const bottomRod = MeshBuilder.CreateCylinder('rod-bottom-A', { 
          diameter: 2.0, // cm (행거 지름)
          height: rodLength // 좌우 프레임에 맞닿도록 몸통 폭에 맞춰 자동 조절
        }, scene);
        bottomRod.position = new Vector3(0, bottomRodY, frontZ);
        bottomRod.rotation.z = Math.PI / 2; // Z축 중심 회전으로 X축 방향 수평 배치 (통의 가로 방향)
        bottomRod.material = rodMaterial;
        interiorElements.push(bottomRod);
      }
      break;

    case 'B': // 반옷장 + 서랍(대)
      {
        const rod = MeshBuilder.CreateCylinder('rod', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod.position = new Vector3(0, baseY + unitHeight * 0.65, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);

        // 서랍 (정면도에서 직사각형으로 보임)
        const drawer = MeshBuilder.CreateBox('drawer', { 
          width: widthCm * 0.95, 
          height: unitHeight * 0.35, 
          depth: thickness * 3.0 // 더 두껍게
        }, scene);
        drawer.position = new Vector3(0, baseY + unitHeight * 0.175, frontZ);
        drawer.material = interiorMaterial;
        interiorElements.push(drawer);
      }
      break;

    case 'C': // 양복장 - 좌우 분할
      {
        // 좌측 행거
        const rod1 = MeshBuilder.CreateCylinder('rod-left-top', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod1.position = new Vector3(-widthCm * 0.25, baseY + unitHeight * 0.65, frontZ);
        rod1.rotation.y = Math.PI / 2;
        rod1.material = interiorMaterial;
        interiorElements.push(rod1);

        const rod2 = MeshBuilder.CreateCylinder('rod-left-bottom', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod2.position = new Vector3(-widthCm * 0.25, baseY + unitHeight * 0.35, frontZ);
        rod2.rotation.y = Math.PI / 2;
        rod2.material = interiorMaterial;
        interiorElements.push(rod2);

        // 우측 선반 (정면도에서 수평선으로 보임)
        for (let i = 0; i < 6; i++) {
          const shelfY = baseY + (unitHeight * 0.15) + (i * unitHeight * 0.75 / 6);
          const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
            width: widthCm * 0.4, 
            height: thickness, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          shelf.position = new Vector3(widthCm * 0.25, shelfY, frontZ);
          shelf.material = interiorMaterial;
          interiorElements.push(shelf);
        }
      }
      break;

    case 'D': // 긴옷장 + 서랍(대)
      {
        const rod = MeshBuilder.CreateCylinder('rod-long', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness * 2.0 
        }, scene);
        rod.position = new Vector3(0, baseY + unitHeight * 0.6, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);

        const drawer = MeshBuilder.CreateBox('drawer', { 
          width: widthCm * 0.8, 
          height: unitHeight * 0.4, 
          depth: 5.0 // 매우 두껍게 (디버깅)
        }, scene);
        drawer.position = new Vector3(0, baseY + unitHeight * 0.2, frontZ);
        drawer.material = interiorMaterial;
        interiorElements.push(drawer);
      }
      break;

    case 'E': // 선반장 + 서랍(소)
      {
        // 좌측 상단 행거
        const rod = MeshBuilder.CreateCylinder('rod-left', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod.position = new Vector3(-widthCm * 0.25, baseY + unitHeight * 0.7, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);

        // 좌측 행거 아래 서랍 2개 세로 배치
        for (let i = 0; i < 2; i++) {
          const drawerY = baseY + (unitHeight * 0.15) + (i * unitHeight * 0.25);
          const drawer = MeshBuilder.CreateBox(`drawer-${i}`, { 
            width: widthCm * 0.45, 
            height: unitHeight * 0.25, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          drawer.position = new Vector3(-widthCm * 0.25, drawerY, frontZ);
          drawer.material = interiorMaterial;
          interiorElements.push(drawer);
        }

        // 우측 선반
        for (let i = 0; i < 4; i++) {
          const shelfY = baseY + (unitHeight * 0.2) + (i * unitHeight * 0.6 / 4);
          const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
            width: widthCm * 0.4, 
            height: thickness, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          shelf.position = new Vector3(widthCm * 0.25, shelfY, frontZ);
          shelf.material = interiorMaterial;
          interiorElements.push(shelf);
        }
      }
      break;

    case 'F': // 선반장 (선반만)
      for (let i = 0; i < 5; i++) {
        const shelfY = baseY + (unitHeight * 0.1) + (i * unitHeight * 0.8 / 5);
        const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
          width: widthCm * 0.95, 
          height: thickness, 
          depth: thickness * 3.0 // 더 두껍게
        }, scene);
        shelf.position = new Vector3(0, shelfY, frontZ);
        shelf.material = interiorMaterial;
        interiorElements.push(shelf);
      }
      break;

    case 'G': // 행거 + 선반 혼합 (좌우 분할)
      {
        // 좌측 행거
        const rod = MeshBuilder.CreateCylinder('rod-left', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod.position = new Vector3(-widthCm * 0.25, baseY + unitHeight * 0.5, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);

        // 우측 선반
        for (let i = 0; i < 3; i++) {
          const shelfY = baseY + (unitHeight * 0.15) + (i * unitHeight * 0.6 / 3);
          const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
            width: widthCm * 0.4, 
            height: thickness, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          shelf.position = new Vector3(widthCm * 0.25, shelfY, frontZ);
          shelf.material = interiorMaterial;
          interiorElements.push(shelf);
        }
      }
      break;

    case 'H': // 서랍장 (서랍만)
      for (let i = 0; i < 4; i++) {
        const drawerY = baseY + (unitHeight * 0.1) + (i * unitHeight * 0.8 / 4);
        const drawer = MeshBuilder.CreateBox(`drawer-${i}`, { 
          width: widthCm * 0.95, 
          height: unitHeight * 0.22, 
          depth: thickness * 3.0 // 더 두껍게
        }, scene);
        drawer.position = new Vector3(0, drawerY, frontZ);
        drawer.material = interiorMaterial;
        interiorElements.push(drawer);
      }
      break;

    case 'I': // 긴옷장 (긴 행거만)
      {
        const rod = MeshBuilder.CreateCylinder('rod', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod.position = new Vector3(0, baseY + unitHeight * 0.5, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);
      }
      break;

    case 'J': // 선반장 (선반만)
      {
        // 선반만 여러 개
        for (let i = 0; i < 5; i++) {
          const shelfY = baseY + (unitHeight * 0.1) + (i * unitHeight * 0.8 / 5);
          const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
            width: widthCm * 0.95, 
            height: thickness, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          shelf.position = new Vector3(0, shelfY, frontZ);
          shelf.material = interiorMaterial;
          interiorElements.push(shelf);
        }
      }
      break;

    case 'K': // 선반장 + 거울도어
      {
        // 좌측 선반
        for (let i = 0; i < 4; i++) {
          const shelfY = baseY + (unitHeight * 0.1) + (i * unitHeight * 0.7 / 4);
          const shelf = MeshBuilder.CreateBox(`shelf-${i}`, { 
            width: widthCm * 0.4, 
            height: thickness, 
            depth: thickness * 3.0 // 더 두껍게
          }, scene);
          shelf.position = new Vector3(-widthCm * 0.25, shelfY, frontZ);
          shelf.material = interiorMaterial;
          interiorElements.push(shelf);
        }

        // 우측 거울 (반사 효과 재질)
        const mirror = MeshBuilder.CreateBox('mirror', { 
          width: widthCm * 0.45, 
          height: unitHeight * 0.85, 
          depth: thickness * 2.0 
        }, scene);
        mirror.position = new Vector3(widthCm * 0.25, baseY + unitHeight * 0.5, frontZ);
        
        // 거울 재질 (반사 효과)
        const mirrorMaterial = interiorMaterial.clone('mirror-mat');
        if (!wireframe) {
          mirrorMaterial.diffuseColor = new Color3(0.8, 0.8, 0.9); // 밝은 회색-파란색
          mirrorMaterial.specularColor = new Color3(0.9, 0.9, 0.9); // 높은 반사
          mirrorMaterial.specularPower = 64; // 반사 강도
          mirrorMaterial.emissiveColor = new Color3(0.3, 0.3, 0.4); // 약간의 자체 발광
        }
        mirror.material = mirrorMaterial;
        interiorElements.push(mirror);
      }
      break;

    default:
      {
        const rod = MeshBuilder.CreateCylinder('rod', { 
          diameter: 2.0, // 매우 크게 (디버깅)
          height: thickness 
        }, scene);
        rod.position = new Vector3(0, baseY + unitHeight * 0.5, frontZ);
        rod.rotation.y = Math.PI / 2;
        rod.material = interiorMaterial;
        interiorElements.push(rod);
      }
  }

  return interiorElements;
}

// 통 생성 (설계도 스타일 - 외곽선만)
function createUnit(scene: Scene, unit: { width: number; height: number; depth: number; position: number; template: string; isHalfUnit?: boolean }, baseHeightCm: number, totalHeightCm: number, material: StandardMaterial, is3DMode: boolean = false): Mesh[] {
  const widthCm = unit.width / 10;
  const heightCm = unit.height / 10;
  const depthCm = unit.depth / 10;
  const positionCm = unit.position;
  const thickness = 2.0; // cm (합판 두께 20mm)
  // 통의 아래쪽 끝이 베이스 위쪽 끝에 맞춰지도록 위치 계산
  // 통 중심 = -totalHeightCm/2 + baseHeightCm + heightCm/2
  const unitY = -totalHeightCm / 2 + baseHeightCm + heightCm / 2;

  const unitMeshes: Mesh[] = [];

  // 통 좌측 프레임
  // 통의 왼쪽 끝 = positionCm - widthCm / 2
  // 프레임의 중심 = 통의 왼쪽 끝 + thickness / 2
  const leftFrame = MeshBuilder.CreateBox('unit-left', { 
    width: thickness, 
    height: heightCm, 
    depth: depthCm 
  }, scene);
  leftFrame.position = new Vector3(positionCm - widthCm / 2 + thickness / 2, unitY, 0);
  leftFrame.material = material;
  unitMeshes.push(leftFrame);

  // 통 우측 프레임
  // 통의 오른쪽 끝 = positionCm + widthCm / 2
  // 프레임의 중심 = 통의 오른쪽 끝 - thickness / 2
  const rightFrame = MeshBuilder.CreateBox('unit-right', { 
    width: thickness, 
    height: heightCm, 
    depth: depthCm 
  }, scene);
  rightFrame.position = new Vector3(positionCm + widthCm / 2 - thickness / 2, unitY, 0);
  rightFrame.material = material;
  unitMeshes.push(rightFrame);

  // 통 상단 프레임
  // 통의 위쪽 끝 = unitY + heightCm / 2
  // 프레임의 중심 = 통의 위쪽 끝 - thickness / 2
  const topFrame = MeshBuilder.CreateBox('unit-top', { 
    width: widthCm, 
    height: thickness, 
    depth: depthCm 
  }, scene);
  topFrame.position = new Vector3(positionCm, unitY + heightCm / 2 - thickness / 2, 0);
  topFrame.material = material;
  unitMeshes.push(topFrame);

  // 통 전면 패널 (설계도 스타일: 전체를 덮는 패널)
  // 3D 모드에서는 전면 패널을 제거하여 내부 구조가 명확하게 보이도록
  const wireframe = material.wireframe || false;
  const frontPanelHeight = heightCm - baseHeightCm;
  
  if (!wireframe && !is3DMode) {
    // 설계도 모드에서만 전면 패널 표시
    const frontPanel = MeshBuilder.CreateBox('unit-front', { 
      width: widthCm, // 전체 너비
      height: frontPanelHeight, 
      depth: 0.2 // 얇은 패널 (설계도처럼 평면, 약간 두껍게)
    }, scene);
    // 전면 패널을 가장 앞쪽에 배치 (z = depthCm/2)
    frontPanel.position = new Vector3(positionCm, unitY - heightCm / 2 + baseHeightCm + frontPanelHeight / 2, depthCm / 2);
    
    // 전면 패널 재질 (중간 회색, 명확한 대비)
    const frontPanelMaterial = material.clone('unit-front-mat');
    const grayColor = new Color3(0.65, 0.65, 0.65); // 중간 회색 (약간 밝게)
    frontPanelMaterial.diffuseColor = grayColor;
    frontPanelMaterial.emissiveColor = grayColor.scale(0.4); // 자체 발광 증가
    frontPanelMaterial.specularColor = Color3.Black();
    frontPanelMaterial.disableLighting = false;
    
    frontPanel.material = frontPanelMaterial;
    unitMeshes.push(frontPanel);
  }

  // 타입별 내부 구조
  const interiorElements = createUnitInterior(scene, unit, widthCm, heightCm, depthCm, baseHeightCm, totalHeightCm, material, wireframe, is3DMode);
  interiorElements.forEach(mesh => {
    mesh.position.x += positionCm;
    // baseY가 이미 전체 좌표계 기준이므로 unitY를 더하지 않음
    unitMeshes.push(mesh);
  });

  return unitMeshes;
}

// 치수 표시 생성 (3D 스케일에 맞게 조정, 항상 카메라를 향함)
function createDimensionLabel(scene: Scene, text: string, position: Vector3, scale: number = 1.0): Mesh {
  // 스케일에 따라 텍스트 크기 조정 (기본 48px, 스케일 적용)
  const fontSize = Math.max(32, Math.min(96, 48 * scale));
  const { texture, width: textureWidth, height: textureHeight } = createTextTexture(scene, text, fontSize);
  
  // 고유한 재질 이름 생성
  const materialName = `dimensionMat_${text}_${Date.now()}_${Math.random()}`;
  const material = new StandardMaterial(materialName, scene);
  
  // 텍스처 설정
  material.diffuseTexture = texture;
  material.emissiveTexture = texture;
  material.emissiveColor = new Color3(1, 1, 1); // 밝은 흰색으로 발광
  material.disableLighting = true;
  material.backFaceCulling = false; // 양면 표시
  material.alpha = 1.0; // 완전 불투명
  
  // 텍스처 비율에 맞게 plane 크기 조정
  const aspectRatio = textureWidth / textureHeight;
  const baseHeight = 5 * scale;
  const baseWidth = baseHeight * aspectRatio;
  
  const plane = MeshBuilder.CreatePlane('dimension', { width: baseWidth, height: baseHeight }, scene);
  plane.position = position;
  // Billboard 모드: 항상 카메라를 향하도록 설정
  plane.billboardMode = Mesh.BILLBOARDMODE_ALL;
  plane.material = material;
  return plane;
}

function Canvas3D() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const sceneRef = useRef<Scene | null>(null);
  const meshesRef = useRef<Mesh[]>([]);

  const {
    totalWidth,
    totalHeight,
    totalDepth,
    units,
    endPanels,
    endPanelSizes,
    showDimensions,
    wireframe,
  } = useClosetStore();

  useEffect(() => {
    if (!canvasRef.current) return;

    // 엔진 초기화
    const engine = new Engine(canvasRef.current, true);
    const scene = new Scene(engine);
    sceneRef.current = scene;

    // 배경색 설정
    scene.clearColor = new Color4(1, 1, 1, 1);

    // 카메라 및 조명 설정 (항상 3D 모드)
    const modelWidth = totalWidth / 10;
    const modelHeight = totalHeight / 10;
    const modelDepth = totalDepth / 10;
    const maxDim = Math.max(modelWidth, modelHeight, modelDepth);
    
    // 3D 뷰: ArcRotateCamera 사용 (회전, 줌, 패닝 지원)
    // 정면에서 약간 위로 내려다보는 각도로 설정 (옆면이 보이지 않도록)
    // 모델의 정면은 Z축 양의 방향이므로, 카메라를 Z축 양의 방향에서 보도록 설정
    const betaAngle = (80 * Math.PI) / 180; // 80도를 라디안으로 변환
    const camera = new ArcRotateCamera(
      'camera',
      Math.PI / 2, // alpha (수평 각도) - 90도로 설정하여 정면을 보도록
      betaAngle, // beta (수직 각도) - 70도로 설정하여 더 위에서 보도록
      maxDim * 2.5, // radius (거리)
      Vector3.Zero(), // target
      scene
    );
    
    // 카메라 각도를 명시적으로 설정 (정면을 보도록)
    camera.alpha = Math.PI / 2; // 90도
    camera.beta = betaAngle; // 70도로 설정하여 더 위에서 보도록
    camera.radius = maxDim * 2.5; // 거리
    
    // 카메라가 정면을 보도록 강제 설정
    camera.setTarget(Vector3.Zero());
    
    // 카메라 제한 설정
    camera.lowerRadiusLimit = maxDim * 0.5;
    camera.upperRadiusLimit = maxDim * 5;
    camera.lowerBetaLimit = 0.1;
    camera.upperBetaLimit = Math.PI / 2;
    
    // 카메라 컨트롤 활성화 (각도 설정 후)
    camera.attachControl(canvasRef.current, true);
    
    // 카메라 각도를 여러 번 강제 설정 (컨트롤 활성화 후에도 유지되도록)
    const setCameraAngle = () => {
      camera.alpha = Math.PI / 2; // 90도
      camera.beta = betaAngle; // 70도로 설정하여 더 위에서 보도록
      camera.setTarget(Vector3.Zero());
    };
    
    // 즉시 설정
    setCameraAngle();
    
    // 짧은 지연 후 다시 설정
    setTimeout(setCameraAngle, 50);
    setTimeout(setCameraAngle, 100);
    setTimeout(setCameraAngle, 200);
    setTimeout(setCameraAngle, 500);
    
    // 조명 추가
    const light = new HemisphericLight('light', new Vector3(0, 1, 0), scene);
    light.intensity = 1.0;
    
    scene.activeCamera = camera;

    // 렌더 루프
    engine.runRenderLoop(() => {
      scene.render();
    });

    // 리사이즈 핸들러
    const handleResize = () => {
      engine.resize();
    };
    window.addEventListener('resize', handleResize);

    // 렌더링 함수
    const renderScene = () => {
      const store = useClosetStore.getState();
      
      // units가 비어있으면 자동 생성
      if (store.units.length === 0) {
        store.autoGenerateUnits();
        setTimeout(() => {
          renderScene();
        }, 200);
        return;
      }


      // 기존 메쉬 제거
      meshesRef.current.forEach(mesh => mesh.dispose());
      meshesRef.current = [];

      const totalWidthCm = store.totalWidth / 10;
      const totalHeightCm = store.totalHeight / 10;
      const baseHeightCm = BASE_HEIGHT / 10;
      
      // 재질 생성 (wireframe 모드에 따라)
      const material = store.wireframe
        ? createBlueprintMaterial(scene, store.wireframe)
        : createPlywoodMaterial(scene);

      // 베이스판
      const base = createBasePanel(scene, store.totalWidth, store.totalHeight, store.totalDepth, BASE_HEIGHT, material);
      meshesRef.current.push(base);

      // 프레임
      const frames = createFrame(scene, store.totalWidth, store.totalHeight, store.totalDepth, material, store.wireframe);
      meshesRef.current.push(...frames);

      // 뒷판 (베이스판부터 상부 EP까지 전체 높이)
      const backPanel = createBackPanel(scene, store.totalWidth, store.totalHeight, store.totalDepth, material, store.wireframe);
      meshesRef.current.push(backPanel);

      // EP
      if (store.endPanels.left) {
        const leftEP = createEndPanel(scene, 'left', store.totalWidth, store.totalHeight, store.totalDepth, store.endPanelSizes.left, material, undefined);
        if (leftEP) meshesRef.current.push(leftEP);
      }

      if (store.endPanels.right) {
        const rightEP = createEndPanel(scene, 'right', store.totalWidth, store.totalHeight, store.totalDepth, store.endPanelSizes.right, material, undefined);
        if (rightEP) meshesRef.current.push(rightEP);
      }

      if (store.endPanels.top) {
        const topEP = createEndPanel(
          scene,
          'top',
          store.totalWidth,
          store.totalHeight,
          store.totalDepth,
          store.endPanelSizes.top,
          material,
          undefined // totalWidth만 사용 (좌우 EP는 이미 totalWidth 내부에 있음)
        );
        if (topEP) meshesRef.current.push(topEP);
      }

      // 통들
      const sortedUnits = [...store.units].sort((a: any, b: any) => (a.order || 0) - (b.order || 0));
      sortedUnits.forEach((unit: any, index: number) => {
        const unitMeshes = createUnit(scene, unit, baseHeightCm, totalHeightCm, material, true);
        meshesRef.current.push(...unitMeshes);
        
        // 통 간 구분선 추가 (마지막 통이 아니면)
        if (index < sortedUnits.length - 1) {
          const nextUnit = sortedUnits[index + 1];
          const currentRightEdge = unit.position * 10 + unit.width / 2; // mm
          const nextLeftEdge = nextUnit.position * 10 - nextUnit.width / 2; // mm
          const dividerX = (currentRightEdge + nextLeftEdge) / 2 / 10; // cm
          
        // 통 간 구분선 (얇은 수직선) - 전면 패널보다 앞에 배치
        const dividerThickness = store.wireframe ? 0.1 : 0.4; // cm (더 두껍게)
        const dividerHeight = totalHeightCm - baseHeightCm; // 베이스 제외 높이
        const dividerY = -totalHeightCm / 2 + baseHeightCm + dividerHeight / 2;
        const depthCm = store.totalDepth / 10;
        
        const divider = MeshBuilder.CreateBox(`unit-divider-${index}`, {
          width: dividerThickness,
          height: dividerHeight,
          depth: 0.3 // 얇은 깊이 (전면 패널보다 앞에)
        }, scene);
        // 구분선을 전면 패널보다 앞에 배치 (z = depthCm/2 + 0.1)
        divider.position = new Vector3(dividerX, dividerY, depthCm / 2 + 0.1);
        
        // 구분선 재질 (더 어두운 회색으로 명확한 대비)
        const dividerMaterial = material.clone(`divider-${index}`);
        if (!store.wireframe) {
          const darkGrayColor = new Color3(0.35, 0.35, 0.35); // 더 어두운 회색 (명확한 대비)
          dividerMaterial.diffuseColor = darkGrayColor;
          dividerMaterial.emissiveColor = darkGrayColor.scale(0.4);
          dividerMaterial.specularColor = Color3.Black();
          dividerMaterial.disableLighting = false;
        }
        divider.material = dividerMaterial;
        meshesRef.current.push(divider);
        }
      });

      // 치수 표시
      if (store.showDimensions) {
        // 3D 스케일 계산 (모델 크기에 비례하여 텍스트 크기 조정)
        const modelWidth = store.totalWidth / 10;
        const modelHeight = store.totalHeight / 10;
        const modelDepth = store.totalDepth / 10;
        const maxDim = Math.max(modelWidth, modelHeight, modelDepth);
        // 스케일: 모델이 클수록 텍스트도 크게 (100cm 기준으로 1.0 스케일)
        const textScale = Math.max(0.5, Math.min(2.0, maxDim / 100));
        const offsetDistance = 30 * textScale; // 오프셋도 스케일에 맞춤

        // 전체 치수 표시 (가로, 높이, 깊이 폰트 크기 증가)
        const mainDimensionScale = textScale * 1.5; // 가로, 높이, 깊이 폰트 크기 증가
        
        // 가로 라벨: 장에 더 붙이기 (offsetDistance 감소)
        const widthLabel = createDimensionLabel(
          scene,
          `${store.totalWidth}mm`,
          new Vector3(0, -totalHeightCm / 2 - offsetDistance * 0.3, 0),
          mainDimensionScale
        );
        meshesRef.current.push(widthLabel);

        // 높이 라벨: 장 중간보다 위에 위치
        const heightLabel = createDimensionLabel(
          scene,
          `${store.totalHeight}mm`,
          new Vector3(-totalWidthCm / 2 - offsetDistance * 0.8, offsetDistance * 0.3, 0),
          mainDimensionScale
        );
        meshesRef.current.push(heightLabel);

        // 깊이 라벨: 더 왼쪽으로 이동 (장 옆에 위치)
        const depthLabel = createDimensionLabel(
          scene,
          `${store.totalDepth}mm`,
          new Vector3(-totalWidthCm / 2 - offsetDistance * 0.5, -totalHeightCm / 2 + offsetDistance * 0.2, (store.totalDepth / 10) / 2),
          mainDimensionScale
        );
        meshesRef.current.push(depthLabel);

        // 모델의 앞쪽 위치 계산 (z축 양의 방향, 모델 깊이의 절반 + 여유 공간)
        const frontZ = (store.totalDepth / 10) / 2 + offsetDistance * 0.5; // cm 단위
        
        // 각 통의 너비 표시 (모델 앞쪽에 배치)
        sortedUnits.forEach((unit: any) => {
          const unitPositionCm = unit.position;
          const unitY = -totalHeightCm / 2 + baseHeightCm + (unit.height / 10) / 2;
          
          // 통 중앙 상단에 너비 표시 (모델 앞쪽에 배치)
          const unitLabel = createDimensionLabel(
            scene,
            `${unit.width}mm`,
            new Vector3(unitPositionCm, unitY + (unit.height / 10) / 2 + offsetDistance * 0.3, frontZ),
            textScale * 1.2 // 통 라벨 크기 증가
          );
          meshesRef.current.push(unitLabel);
        });

        // 좌측 EP 크기 표시 (모델 앞쪽에 배치)
        // 앞면에서 볼 때 왼쪽(X축 음수)에 있는 EP는 "EP L" 표시
        // 하지만 endPanels.left는 뒷면 기준이므로, 앞면에서 보면 오른쪽에 위치
        // 따라서 앞면 기준으로 올바른 라벨을 표시하기 위해 텍스트를 반대로
        if (store.endPanels.left && store.endPanelSizes.left > 0) {
          const leftEPLabel = createDimensionLabel(
            scene,
            `EP R: ${store.endPanelSizes.left}mm`, // 앞면에서 볼 때 오른쪽이므로 "EP R"
            new Vector3(-totalWidthCm / 2 + store.endPanelSizes.left / 20, 0, frontZ),
            textScale * 1.0 // EP 라벨 크기 증가
          );
          meshesRef.current.push(leftEPLabel);
        }

        // 우측 EP 크기 표시 (모델 앞쪽에 배치)
        // 앞면에서 볼 때 오른쪽(X축 양수)에 있는 EP는 "EP R" 표시
        // 하지만 endPanels.right는 뒷면 기준이므로, 앞면에서 보면 왼쪽에 위치
        // 따라서 앞면 기준으로 올바른 라벨을 표시하기 위해 텍스트를 반대로
        if (store.endPanels.right && store.endPanelSizes.right > 0) {
          const rightEPLabel = createDimensionLabel(
            scene,
            `EP L: ${store.endPanelSizes.right}mm`, // 앞면에서 볼 때 왼쪽이므로 "EP L"
            new Vector3(totalWidthCm / 2 - store.endPanelSizes.right / 20, 0, frontZ),
            textScale * 1.0 // EP 라벨 크기 증가
          );
          meshesRef.current.push(rightEPLabel);
        }

        // 상단 EP 크기 표시 (모델 앞쪽에 배치)
        if (store.endPanels.top && store.endPanelSizes.top > 0) {
          const topEPLabel = createDimensionLabel(
            scene,
            `EP T: ${store.endPanelSizes.top}mm`,
            new Vector3(0, totalHeightCm / 2 - store.endPanelSizes.top / 20, frontZ),
            textScale * 1.0 // EP 라벨 크기 증가
          );
          meshesRef.current.push(topEPLabel);
        }
      }
    };

    // 초기 렌더링 실행
    renderScene();

    // 클린업
    return () => {
      window.removeEventListener('resize', handleResize);
      meshesRef.current.forEach(mesh => mesh.dispose());
      scene.dispose();
      engine.dispose();
    };
  }, []); // 초기 마운트 시에만 실행

  // 상태 변경 시 씬 업데이트 (렌더링 최적화)
  useEffect(() => {
    if (!sceneRef.current) return;

    // 렌더링을 다음 프레임으로 지연시켜 잔상 문제 해결
    const timeoutId = setTimeout(() => {
      if (!sceneRef.current) return;

      const store = useClosetStore.getState();
      if (store.units.length === 0) {
        store.autoGenerateUnits();
        return;
      }

      // 카메라 업데이트 (3D 모드)
      // totalWidth 변경 시 카메라 줌을 자동 조정하지 않음 (사용자가 설정한 줌 유지)
      const camera = sceneRef.current.activeCamera;
      if (camera && canvasRef.current && camera instanceof ArcRotateCamera) {
        // 카메라 각도만 유지 (렌더링 후에도 정면이 보이도록)
        // 줌(radius)은 사용자가 설정한 값을 유지
        const betaAngle = (80 * Math.PI) / 180; // 80도를 라디안으로 변환
        camera.alpha = Math.PI / 2; // 90도
        camera.beta = betaAngle; // 80도로 설정하여 더 위에서 보도록
        camera.setTarget(Vector3.Zero());
      }

      // 기존 메쉬 제거 (더 확실하게 정리)
      meshesRef.current.forEach(mesh => {
        if (mesh && !mesh.isDisposed()) {
          mesh.dispose();
        }
      });
      meshesRef.current = [];

    const scene = sceneRef.current;
    const totalWidthCm = totalWidth / 10;
    const totalHeightCm = totalHeight / 10;
    const baseHeightCm = BASE_HEIGHT / 10;
    
    // 재질 생성 (wireframe 모드에 따라)
    const material = wireframe
      ? createBlueprintMaterial(scene, wireframe)
      : createPlywoodMaterial(scene);

    // 베이스판
    const base = createBasePanel(scene, totalWidth, totalHeight, totalDepth, BASE_HEIGHT, material);
    meshesRef.current.push(base);

    // 프레임
    const frames = createFrame(scene, totalWidth, totalHeight, totalDepth, material, wireframe);
    meshesRef.current.push(...frames);

    // 뒷판 (베이스판부터 상부 EP까지 전체 높이)
    const backPanel = createBackPanel(scene, totalWidth, totalHeight, totalDepth, material, wireframe);
    meshesRef.current.push(backPanel);

    // EP
    if (endPanels.left) {
      const leftEP = createEndPanel(scene, 'left', totalWidth, totalHeight, totalDepth, endPanelSizes.left, material, undefined);
      if (leftEP) meshesRef.current.push(leftEP);
    }

    if (endPanels.right) {
      const rightEP = createEndPanel(scene, 'right', totalWidth, totalHeight, totalDepth, endPanelSizes.right, material, undefined);
      if (rightEP) meshesRef.current.push(rightEP);
    }

    if (endPanels.top) {
      const topEP = createEndPanel(
        scene,
        'top',
        totalWidth,
        totalHeight,
        totalDepth,
        endPanelSizes.top,
        material,
        undefined // totalWidth만 사용 (좌우 EP는 이미 totalWidth 내부에 있음)
      );
      if (topEP) meshesRef.current.push(topEP);
    }

    // 통들
    const sortedUnits = [...units].sort((a: any, b: any) => (a.order || 0) - (b.order || 0));
    sortedUnits.forEach((unit: any, index: number) => {
      const unitMeshes = createUnit(scene, unit, baseHeightCm, totalHeightCm, material, true);
      meshesRef.current.push(...unitMeshes);
      
      // 통 간 구분선 추가 (마지막 통이 아니면)
      if (index < sortedUnits.length - 1) {
        const nextUnit = sortedUnits[index + 1];
        const currentRightEdge = unit.position * 10 + unit.width / 2; // mm
        const nextLeftEdge = nextUnit.position * 10 - nextUnit.width / 2; // mm
        const dividerX = (currentRightEdge + nextLeftEdge) / 2 / 10; // cm
        
        // 통 간 구분선 (얇은 수직선) - 전면 패널보다 앞에 배치
        const dividerThickness = wireframe ? 0.1 : 0.4; // cm (더 두껍게)
        const dividerHeight = totalHeightCm - baseHeightCm; // 베이스 제외 높이
        const dividerY = -totalHeightCm / 2 + baseHeightCm + dividerHeight / 2;
        const depthCm = totalDepth / 10;
        
        const divider = MeshBuilder.CreateBox(`unit-divider-${index}`, {
          width: dividerThickness,
          height: dividerHeight,
          depth: 0.3 // 얇은 깊이 (전면 패널보다 앞에)
        }, scene);
        // 구분선을 전면 패널보다 앞에 배치 (z = depthCm/2 + 0.1)
        divider.position = new Vector3(dividerX, dividerY, depthCm / 2 + 0.1);
        
        // 구분선 재질 (더 어두운 회색으로 명확한 대비)
        const dividerMaterial = material.clone(`divider-${index}`);
        if (!wireframe) {
          const darkGrayColor = new Color3(0.35, 0.35, 0.35); // 더 어두운 회색 (명확한 대비)
          dividerMaterial.diffuseColor = darkGrayColor;
          dividerMaterial.emissiveColor = darkGrayColor.scale(0.4);
          dividerMaterial.specularColor = Color3.Black();
          dividerMaterial.disableLighting = false;
        }
        divider.material = dividerMaterial;
        meshesRef.current.push(divider);
      }
    });

    // 치수 표시
    if (showDimensions) {
      // 3D 스케일 계산 (모델 크기에 비례하여 텍스트 크기 조정)
      const modelWidth = totalWidth / 10;
      const modelHeight = totalHeight / 10;
      const modelDepth = totalDepth / 10;
      const maxDim = Math.max(modelWidth, modelHeight, modelDepth);
      // 스케일: 모델이 클수록 텍스트도 크게 (100cm 기준으로 1.0 스케일)
      const textScale = Math.max(0.5, Math.min(2.0, maxDim / 100));
      const offsetDistance = 30 * textScale; // 오프셋도 스케일에 맞춤

      // 전체 치수 표시 (가로, 높이, 깊이 폰트 크기 증가)
      const mainDimensionScale = textScale * 1.5; // 가로, 높이, 깊이 폰트 크기 증가
      
      // 가로 라벨: 장에 더 붙이기 (offsetDistance 감소)
      const widthLabel = createDimensionLabel(
        scene,
        `${totalWidth}mm`,
        new Vector3(0, -totalHeightCm / 2 - offsetDistance * 0.3, 0),
        mainDimensionScale
      );
      meshesRef.current.push(widthLabel);

      // 높이 라벨: 장 중간보다 위에 위치
      const heightLabel = createDimensionLabel(
        scene,
        `${totalHeight}mm`,
        new Vector3(-totalWidthCm / 2 - offsetDistance * 0.8, offsetDistance * 0.3, 0),
        mainDimensionScale
      );
      meshesRef.current.push(heightLabel);

      // 깊이 라벨: 더 왼쪽으로 이동 (장 옆에 위치)
      const depthLabel = createDimensionLabel(
        scene,
        `${totalDepth}mm`,
        new Vector3(-totalWidthCm / 2 - offsetDistance * 0.5, -totalHeightCm / 2 + offsetDistance * 0.2, (totalDepth / 10) / 2),
        mainDimensionScale
      );
      meshesRef.current.push(depthLabel);

      // 모델의 앞쪽 위치 계산 (z축 양의 방향, 모델 깊이의 절반 + 여유 공간)
      const frontZ = (totalDepth / 10) / 2 + offsetDistance * 0.5; // cm 단위
      
      // 각 통의 너비 표시 (모델 앞쪽에 배치)
      sortedUnits.forEach((unit: any) => {
        const unitPositionCm = unit.position;
        const unitY = -totalHeightCm / 2 + baseHeightCm + (unit.height / 10) / 2;
        
        // 통 중앙 상단에 너비 표시 (모델 앞쪽에 배치)
        const unitLabel = createDimensionLabel(
          scene,
          `${unit.width}mm`,
          new Vector3(unitPositionCm, unitY + (unit.height / 10) / 2 + offsetDistance * 0.3, frontZ),
          textScale * 1.2 // 통 라벨 크기 증가
        );
        meshesRef.current.push(unitLabel);
      });

      // 좌측 EP 크기 표시 (모델 앞쪽에 배치)
      // 앞면에서 볼 때 왼쪽(X축 음수)에 있는 EP는 "EP L" 표시
      // 하지만 endPanels.left는 뒷면 기준이므로, 앞면에서 보면 오른쪽에 위치
      // 따라서 앞면 기준으로 올바른 라벨을 표시하기 위해 텍스트를 반대로
      if (endPanels.left && endPanelSizes.left > 0) {
        const leftEPLabel = createDimensionLabel(
          scene,
          `EP R: ${endPanelSizes.left}mm`, // 앞면에서 볼 때 오른쪽이므로 "EP R"
          new Vector3(-totalWidthCm / 2 + endPanelSizes.left / 20, 0, frontZ),
          textScale * 1.0 // EP 라벨 크기 증가
        );
        meshesRef.current.push(leftEPLabel);
      }

      // 우측 EP 크기 표시 (모델 앞쪽에 배치)
      // 앞면에서 볼 때 오른쪽(X축 양수)에 있는 EP는 "EP R" 표시
      // 하지만 endPanels.right는 뒷면 기준이므로, 앞면에서 보면 왼쪽에 위치
      // 따라서 앞면 기준으로 올바른 라벨을 표시하기 위해 텍스트를 반대로
      if (endPanels.right && endPanelSizes.right > 0) {
        const rightEPLabel = createDimensionLabel(
          scene,
          `EP L: ${endPanelSizes.right}mm`, // 앞면에서 볼 때 왼쪽이므로 "EP L"
          new Vector3(totalWidthCm / 2 - endPanelSizes.right / 20, 0, frontZ),
          textScale * 1.0 // EP 라벨 크기 증가
        );
        meshesRef.current.push(rightEPLabel);
      }

      // 상단 EP 크기 표시 (모델 앞쪽에 배치)
      if (endPanels.top && endPanelSizes.top > 0) {
        const topEPLabel = createDimensionLabel(
          scene,
          `EP T: ${endPanelSizes.top}mm`,
          new Vector3(0, totalHeightCm / 2 - endPanelSizes.top / 20, frontZ),
          textScale * 1.0 // EP 라벨 크기 증가
        );
        meshesRef.current.push(topEPLabel);
      }
    }
    }, 16); // 한 프레임 지연 (약 16ms, 60fps 기준)

    return () => {
      clearTimeout(timeoutId);
    };
  }, [totalWidth, totalHeight, totalDepth, units, endPanels, endPanelSizes, showDimensions, wireframe]);

  return (
    <div className="w-full h-full bg-white">
      <canvas ref={canvasRef} className="w-full h-full" />
    </div>
  );
}

export default Canvas3D;

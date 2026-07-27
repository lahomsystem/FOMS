"use client";

import { useMemo, useState } from "react";

export type ProjectOptionPath = { level1: string; level2?: string; level3?: string };
type Level2Definition = { label: string; values: string[]; level3Label?: string; level3Values?: string[] };
type OptionDefinition = { label: string; child?: Level2Definition };

const OPTION_DEFINITIONS: OptionDefinition[] = [
  { label: "푸쉬 도어" },
  { label: "피닉스바 손잡이", child: { label: "구분", values: ["색상"], level3Label: "색상", level3Values: ["웜그레이", "아이보리", "블랙", "실버", "골드"] } },
  { label: "J손잡이", child: { label: "구분", values: ["색상"], level3Label: "색상", level3Values: ["웜그레이", "아이보리", "블랙", "실버", "골드"] } },
  { label: "T바 손잡이", child: { label: "구분", values: ["색상"], level3Label: "색상", level3Values: ["블랙", "실버", "골드"] } },
  { label: "일반 손잡이", child: { label: "구분", values: ["색상"], level3Label: "색상", level3Values: ["웜그레이", "아이보리", "블랙", "실버", "골드"] } },
  { label: "무몰딩", child: { label: "적용 위치", values: ["전체", "좌측", "우측", "상부"] } },
  { label: "제로조인트", child: { label: "적용 부위", values: ["도어", "외부 마감", "전체"] } },
  { label: "간접조명", child: { label: "설치 위치", values: ["상부장", "하부장", "오픈장", "선반"], level3Label: "조명 색상", level3Values: ["전구색", "주백색", "주광색"] } },
  { label: "거울도어", child: { label: "거울 색상", values: ["실버", "브론즈", "그레이"], level3Label: "프레임", level3Values: ["프레임 없음", "블랙", "실버"] } },
  { label: "오픈장", child: { label: "위치", values: ["좌측", "중앙", "우측", "상부"], level3Label: "마감 컬러", level3Values: ["본체색 동일", "화이트", "그레이", "우드"] } },
  { label: "서랍장", child: { label: "위치", values: ["좌측", "중앙", "우측", "내부"], level3Label: "구성", level3Values: ["1단", "2단", "3단", "4단"] } },
  { label: "화장대 포함", child: { label: "형태", values: ["일체형", "분리형", "서랍형"], level3Label: "거울", level3Values: ["거울 없음", "일반 거울", "조명 거울"] } },
  { label: "스타일러장", child: { label: "위치", values: ["좌측", "우측"], level3Label: "수량", level3Values: ["1대", "2대"] } },
  { label: "콘센트 가공", child: { label: "위치", values: ["내부", "상판", "측판"], level3Label: "수량", level3Values: ["1구", "2구", "3구 이상"] } },
  { label: "내부 구성 변경", child: { label: "변경 유형", values: ["선반", "행거", "서랍", "긴옷장", "이불장"] } },
];

const COLOR_SUGGESTIONS = ["클린화이트", "파우더화이트", "아이보리", "바닐라크림", "허쉬그레이", "포그그레이", "웜그레이", "라이트우드", "월넛", "블랙"];

function normalizePath(path: ProjectOptionPath): ProjectOptionPath {
  return { level1: path.level1.trim(), level2: path.level2?.trim() || undefined, level3: path.level3?.trim() || undefined };
}
function pathKey(path: ProjectOptionPath) { return [path.level1, path.level2 || "", path.level3 || ""].join("::"); }
function pathLabel(path: ProjectOptionPath) { return [path.level1, path.level2, path.level3].filter(Boolean).join(" › "); }
function splitInitialColors(value: string | string[]) {
  const values = Array.isArray(value) ? value : value.split(/\s*[·,/]\s*/);
  return [...new Set(values.map((item) => item.trim()).filter(Boolean))];
}

export default function ProjectOptionPathBuilder({ initialPaths = [], initialColors = [] }: { initialPaths?: ProjectOptionPath[]; initialColors?: string | string[] }) {
  const [selectedPaths, setSelectedPaths] = useState<ProjectOptionPath[]>(initialPaths.map(normalizePath).filter((path) => path.level1));
  const [colors, setColors] = useState<string[]>(splitInitialColors(initialColors));
  const [colorInput, setColorInput] = useState("");
  const [level1, setLevel1] = useState("");
  const [level2, setLevel2] = useState("");
  const [level3, setLevel3] = useState("");
  const selectedDefinition = useMemo(() => OPTION_DEFINITIONS.find((option) => option.label === level1), [level1]);
  const child = selectedDefinition?.child;
  const requiresLevel2 = Boolean(child);
  const requiresLevel3 = Boolean(child?.level3Values?.length);
  const canAddPath = Boolean(level1 && (!requiresLevel2 || level2) && (!requiresLevel3 || level3));

  function addColor(raw: string) {
    const next = raw.trim();
    if (!next) return;
    setColors((current) => current.includes(next) ? current : [...current, next]);
    setColorInput("");
  }
  function removeColor(color: string) { setColors((current) => current.filter((item) => item !== color)); }
  function addPath() {
    if (!canAddPath) return;
    const next = normalizePath({ level1, level2, level3 });
    setSelectedPaths((current) => current.some((item) => pathKey(item) === pathKey(next)) ? current : [...current, next]);
    setLevel1(""); setLevel2(""); setLevel3("");
  }
  function removePath(key: string) { setSelectedPaths((current) => current.filter((item) => pathKey(item) !== key)); }

  return (
    <section className="project-option-builder editor-full-field">
      <div className="project-option-builder-heading">
        <div><strong>컬러 및 상세 옵션</strong><span>컬러와 옵션을 여러 개 선택할 수 있습니다. 선택 결과는 아래에서 바로 삭제할 수 있습니다.</span></div>
        <small>거래처 상세페이지 노출</small>
      </div>
      <div className="project-color-builder">
        <div className="project-option-label">전체 제품 컬러 <em>복수 선택 가능</em></div>
        <div className="project-color-suggestions">
          {COLOR_SUGGESTIONS.map((color) => <button key={color} type="button" className={colors.includes(color) ? "selected" : ""} onClick={() => colors.includes(color) ? removeColor(color) : addColor(color)}>{color}</button>)}
        </div>
        <div className="project-color-custom-row">
          <input value={colorInput} onChange={(event) => setColorInput(event.target.value)} onKeyDown={(event) => { if (event.key === "Enter") { event.preventDefault(); addColor(colorInput); } }} placeholder="목록에 없는 컬러 직접 입력" />
          <button type="button" onClick={() => addColor(colorInput)}>컬러 추가</button>
        </div>
        <input type="hidden" name="color" value={colors.join(" · ")} />
      </div>
      <div className="project-option-depths">
        <label><span>1뎁스</span><select value={level1} onChange={(event) => { setLevel1(event.target.value); setLevel2(""); setLevel3(""); }}><option value="">옵션 선택</option>{OPTION_DEFINITIONS.map((option) => <option key={option.label} value={option.label}>{option.label}</option>)}</select></label>
        <label className={!child ? "is-disabled" : ""}><span>2뎁스{child ? ` · ${child.label}` : ""}</span><select value={level2} disabled={!child} onChange={(event) => { setLevel2(event.target.value); setLevel3(""); }}><option value="">{child ? `${child.label} 선택` : "하위 선택 없음"}</option>{child?.values.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <label className={!requiresLevel3 ? "is-disabled" : ""}><span>3뎁스{child?.level3Label ? ` · ${child.level3Label}` : ""}</span><select value={level3} disabled={!requiresLevel3} onChange={(event) => setLevel3(event.target.value)}><option value="">{child?.level3Label ? `${child.level3Label} 선택` : "세부 선택 없음"}</option>{child?.level3Values?.map((value) => <option key={value} value={value}>{value}</option>)}</select></label>
        <button type="button" className="project-option-add-button" disabled={!canAddPath} onClick={addPath}>선택 추가</button>
      </div>
      <div className="project-option-selection-summary">
        <div><strong>선택된 컬러</strong><div className="project-selected-chip-list">{colors.length > 0 ? colors.map((color) => <button key={color} type="button" onClick={() => removeColor(color)} title={`${color} 삭제`}>{color}<span>×</span></button>) : <span className="project-option-empty">선택된 컬러가 없습니다.</span>}</div></div>
        <div><strong>선택된 상세 옵션</strong><div className="project-selected-chip-list option-path-chips">{selectedPaths.length > 0 ? selectedPaths.map((path) => { const key = pathKey(path); return <button key={key} type="button" onClick={() => removePath(key)} title={`${pathLabel(path)} 삭제`}>{pathLabel(path)}<span>×</span></button>; }) : <span className="project-option-empty">선택된 상세 옵션이 없습니다.</span>}</div></div>
      </div>
      {selectedPaths.map((path) => <input key={pathKey(path)} type="hidden" name="projectOptionPaths" value={JSON.stringify(path)} />)}
    </section>
  );
}

import jsPDF from 'jspdf';
import { ClosetConfig } from '../types';

/**
 * 견적서 PDF 생성
 */
export function generateEstimatePDF(config: ClosetConfig): void {
  const doc = new jsPDF();
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 20;
  let yPos = margin;

  // 제목
  doc.setFontSize(20);
  doc.setFont('helvetica', 'bold');
  doc.text('붙박이장 설계 견적서', pageWidth / 2, yPos, { align: 'center' });
  yPos += 15;

  // 구분선
  doc.setLineWidth(0.5);
  doc.line(margin, yPos, pageWidth - margin, yPos);
  yPos += 10;

  // 기본 정보
  doc.setFontSize(12);
  doc.setFont('helvetica', 'bold');
  doc.text('기본 규격', margin, yPos);
  yPos += 8;

  doc.setFont('helvetica', 'normal');
  doc.setFontSize(10);
  const basicInfo = [
    `전체 너비: ${config.totalWidth}mm`,
    `전체 높이: ${config.totalHeight}mm`,
    `전체 깊이: ${config.totalDepth}mm`,
    `도어 타입: ${config.doorType === 'sliding' ? '슬라이딩' : config.doorType === 'swing' ? '여닫이' : '오픈'}`,
    `색상: ${config.color}`,
  ];

  basicInfo.forEach((info) => {
    doc.text(info, margin + 5, yPos);
    yPos += 6;
  });

  yPos += 5;

  // 엔드패널 정보
  if (config.endPanels.left || config.endPanels.right || config.endPanels.top) {
    doc.setFont('helvetica', 'bold');
    doc.text('엔드패널 (EP)', margin, yPos);
    yPos += 8;

    doc.setFont('helvetica', 'normal');
    const epInfo: string[] = [];
    if (config.endPanels.left) {
      epInfo.push(`좌측 EP: ${config.endPanelSizes.left}mm`);
    }
    if (config.endPanels.right) {
      epInfo.push(`우측 EP: ${config.endPanelSizes.right}mm`);
    }
    if (config.endPanels.top) {
      epInfo.push(`상부 EP: ${config.endPanelSizes.top}mm`);
    }

    epInfo.forEach((info) => {
      doc.text(info, margin + 5, yPos);
      yPos += 6;
    });

    yPos += 5;
  }

  // 통 목록
  if (config.units.length > 0) {
    // 새 페이지 체크
    if (yPos > pageHeight - 60) {
      doc.addPage();
      yPos = margin;
    }

    doc.setFont('helvetica', 'bold');
    doc.text('통 구성', margin, yPos);
    yPos += 8;

    // 테이블 헤더
    doc.setFontSize(9);
    doc.setFont('helvetica', 'bold');
    const tableHeaders = ['번호', '너비(mm)', '높이(mm)', '템플릿', '반통'];
    const colWidths = [15, 30, 30, 25, 20];
    let xPos = margin + 5;

    tableHeaders.forEach((header, index) => {
      doc.text(header, xPos, yPos);
      xPos += colWidths[index];
    });

    yPos += 6;
    doc.setLineWidth(0.2);
    doc.line(margin + 5, yPos - 2, pageWidth - margin - 5, yPos - 2);

    // 통 데이터
    doc.setFont('helvetica', 'normal');
    config.units.forEach((unit, index) => {
      // 새 페이지 체크
      if (yPos > pageHeight - 20) {
        doc.addPage();
        yPos = margin;
      }

      xPos = margin + 5;
      const rowData = [
        `${index + 1}`,
        `${unit.width}`,
        `${unit.height}`,
        unit.template,
        unit.isHalfUnit ? '예' : '아니오',
      ];

      rowData.forEach((data, dataIndex) => {
        doc.text(data, xPos, yPos);
        xPos += colWidths[dataIndex];
      });

      yPos += 6;
    });
  }

  // 하단 정보
  yPos = pageHeight - 30;
  doc.setLineWidth(0.5);
  doc.line(margin, yPos, pageWidth - margin, yPos);
  yPos += 10;

  doc.setFontSize(8);
  doc.setFont('helvetica', 'italic');
  doc.text(
    `생성일시: ${new Date().toLocaleString('ko-KR')}`,
    pageWidth / 2,
    yPos,
    { align: 'center' }
  );

  // PDF 저장
  const fileName = `붙박이장_견적서_${new Date().toISOString().split('T')[0]}.pdf`;
  doc.save(fileName);
}

/**
 * 설계도 PDF 생성 (간단 버전)
 */
export function generateBlueprintPDF(config: ClosetConfig): void {
  const doc = new jsPDF('landscape', 'mm', 'a4');
  const pageWidth = doc.internal.pageSize.getWidth();
  const pageHeight = doc.internal.pageSize.getHeight();
  const margin = 20;

  // 제목
  doc.setFontSize(16);
  doc.setFont('helvetica', 'bold');
  doc.text('붙박이장 설계도', pageWidth / 2, margin, { align: 'center' });

  // 기본 정보 박스
  const infoY = margin + 15;
  doc.setLineWidth(0.5);
  doc.rect(margin, infoY, pageWidth - margin * 2, 40);

  doc.setFontSize(10);
  doc.setFont('helvetica', 'normal');
  let infoYPos = infoY + 8;
  doc.text(`전체 규격: ${config.totalWidth} × ${config.totalHeight} × ${config.totalDepth}mm`, margin + 5, infoYPos);
  infoYPos += 6;
  doc.text(`도어 타입: ${config.doorType === 'sliding' ? '슬라이딩' : config.doorType === 'swing' ? '여닫이' : '오픈'}`, margin + 5, infoYPos);
  infoYPos += 6;
  doc.text(`통 개수: ${config.units.length}개`, margin + 5, infoYPos);

  // 통 목록
  const listY = infoY + 45;
  doc.setFont('helvetica', 'bold');
  doc.text('통 상세', margin, listY);
  
  doc.setFont('helvetica', 'normal');
  let listYPos = listY + 8;
  config.units.forEach((unit, index) => {
    doc.text(
      `통 ${index + 1}: ${unit.width}×${unit.height}mm (템플릿: ${unit.template})${unit.isHalfUnit ? ' [반통]' : ''}`,
      margin + 5,
      listYPos
    );
    listYPos += 6;
  });

  // 하단 정보
  const footerY = pageHeight - 15;
  doc.setFontSize(8);
  doc.setFont('helvetica', 'italic');
  doc.text(
    `생성일시: ${new Date().toLocaleString('ko-KR')}`,
    pageWidth / 2,
    footerY,
    { align: 'center' }
  );

  const fileName = `붙박이장_설계도_${new Date().toISOString().split('T')[0]}.pdf`;
  doc.save(fileName);
}





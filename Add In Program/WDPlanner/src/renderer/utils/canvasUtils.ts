/**
 * Canvas를 Base64 이미지로 변환
 */
export function canvasToBase64(canvas: HTMLCanvasElement): string {
  return canvas.toDataURL('image/png');
}

/**
 * Canvas를 Blob으로 변환
 */
export function canvasToBlob(canvas: HTMLCanvasElement): Promise<Blob> {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      (blob) => {
        if (blob) {
          resolve(blob);
        } else {
          reject(new Error('Canvas를 Blob으로 변환 실패'));
        }
      },
      'image/png',
      1.0
    );
  });
}

/**
 * 이미지 다운로드
 */
export function downloadImage(dataUrl: string, filename: string): void {
  const link = document.createElement('a');
  link.download = filename;
  link.href = dataUrl;
  link.click();
}





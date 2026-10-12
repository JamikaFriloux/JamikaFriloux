import * as pdfjs from 'pdfjs-dist/legacy/build/pdf.mjs';

export interface PdfPageText {
  width: number;
  height: number;
  text: string;
  items: { str: string; x: number; y: number; w: number; h: number }[];
}

export async function readPdf(buf: Buffer): Promise<PdfPageText[]> {
  const doc = await pdfjs.getDocument({ data: new Uint8Array(buf), disableFontFace: true, useSystemFonts: false }).promise;
  const pages: PdfPageText[] = [];
  for (let i = 1; i <= doc.numPages; i++) {
    const page = await doc.getPage(i);
    const vp = page.getViewport({ scale: 1 });
    const tc = await page.getTextContent();
    const items = (tc.items as { str: string; transform: number[]; width: number; height: number }[])
      .filter((it) => typeof it.str === 'string')
      .map((it) => ({ str: it.str, x: it.transform[4], y: it.transform[5], w: it.width, h: it.height }));
    pages.push({ width: vp.width, height: vp.height, text: items.map((i) => i.str).join(' '), items });
  }
  return pages;
}

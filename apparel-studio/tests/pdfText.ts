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

/**
 * Pairs of text items on a page whose glyph boxes overlap vertically (>12% of line height) —
 * i.e. text printed on top of other text. Items on the same baseline (one string split into
 * runs) are ignored.
 */
export function textOverlaps(page: PdfPageText): string[] {
  const items = page.items.filter((i) => i.str.trim() && i.w > 0 && i.h > 0);
  const out: string[] = [];
  for (let a = 0; a < items.length; a++) {
    for (let b = a + 1; b < items.length; b++) {
      const p = items[a];
      const q = items[b];
      if (Math.abs(p.y - q.y) < 0.5) continue;
      const ix = Math.min(p.x + p.w, q.x + q.w) - Math.max(p.x, q.x);
      const iy = Math.min(p.y + p.h, q.y + q.h) - Math.max(p.y, q.y);
      if (ix <= 0 || iy <= 0) continue;
      // Table rows are spaced ≥ 1.2 × font size, so any real vertical overlap of glyph boxes means collision.
      if (ix > 1 && iy / Math.min(p.h, q.h) > 0.12) out.push(`"${p.str}" ↔ "${q.str}"`);
    }
  }
  return out;
}

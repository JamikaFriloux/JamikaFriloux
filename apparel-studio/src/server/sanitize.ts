import createDOMPurify from 'dompurify';
import { JSDOM } from 'jsdom';

const { window } = new JSDOM('');
const DOMPurify = createDOMPurify(window as unknown as Window & typeof globalThis);

export class UploadError extends Error {
  constructor(message: string, public status = 400) {
    super(message);
  }
}

const MAX_SVG_BYTES = 3 * 1024 * 1024;

/** Only same-document fragments and embedded raster data are allowed as references. */
function safeRef(v: string): boolean {
  const s = v.trim();
  return s.startsWith('#') || /^data:image\/(png|jpeg|gif|webp);base64,[a-z0-9+/=\s]+$/i.test(s);
}

function scrubCss(css: string): string {
  return css
    .replace(/@import[^;]*;?/gi, '')
    .replace(/url\(\s*(['"]?)(.*?)\1\s*\)/gi, (m, _q, ref) => (safeRef(ref) ? m : 'none'))
    .replace(/expression\s*\(/gi, '')
    .replace(/javascript:/gi, '');
}

DOMPurify.addHook('afterSanitizeAttributes', (node) => {
  const el = node as Element;
  for (const name of ['href', 'xlink:href']) {
    const v = el.getAttribute?.(name);
    if (v !== null && v !== undefined && !safeRef(v)) el.removeAttribute(name);
  }
  for (const attr of Array.from(el.attributes ?? [])) {
    if (/url\(/i.test(attr.value)) {
      const scrubbed = scrubCss(attr.value);
      if (scrubbed !== attr.value) el.setAttribute(attr.name, scrubbed);
    }
  }
  const style = el.getAttribute?.('style');
  if (style) el.setAttribute('style', scrubCss(style));
});
DOMPurify.addHook('uponSanitizeElement', (node, data) => {
  if (data.tagName === 'style' && node.textContent) node.textContent = scrubCss(node.textContent);
});

export interface SanitizedSvg {
  svg: string;
  width: number;
  height: number;
  viewBox: string;
  removed: number;
}

/**
 * Sanitize untrusted SVG. Removes scripts, event handlers, foreignObject, external
 * references (http/file/javascript URLs), CSS @import and external url()s. DTDs/entities are
 * rejected outright. Returns the cleaned markup and its intrinsic size.
 */
export function sanitizeSvg(input: Buffer): SanitizedSvg {
  if (input.length > MAX_SVG_BYTES) throw new UploadError('SVG is larger than 3 MB. Simplify or export a smaller file.');
  let text = input.toString('utf8');
  if (text.charCodeAt(0) === 0xfeff) text = text.slice(1);
  if (/<!DOCTYPE|<!ENTITY/i.test(text)) throw new UploadError('SVG files with DOCTYPE or ENTITY declarations are not accepted. Re-export the SVG without a DTD.');
  text = text.replace(/<\?xml[^>]*\?>/i, '').replace(/<!--[\s\S]*?-->/g, '');
  if (!/<svg[\s>]/i.test(text)) throw new UploadError('This file does not contain an <svg> element.');

  const clean = DOMPurify.sanitize(text, {
    USE_PROFILES: { svg: true, svgFilters: true },
    FORBID_TAGS: ['script', 'foreignObject', 'iframe', 'embed', 'object', 'audio', 'video', 'a'],
    FORBID_ATTR: ['onload', 'onerror', 'onclick', 'onmouseover', 'onfocus', 'onbegin', 'onend'],
    ADD_TAGS: ['use'],
    ADD_ATTR: ['xlink:href', 'href', 'viewBox', 'preserveAspectRatio'],
    RETURN_DOM: true,
  }) as unknown as HTMLElement;
  const removed = DOMPurify.removed.length;
  const svgEl = clean.querySelector('svg');
  if (!svgEl) throw new UploadError('No usable SVG content remained after removing unsafe parts.');

  const vbAttr = svgEl.getAttribute('viewBox') || svgEl.getAttribute('viewbox');
  let vb: number[] | null = vbAttr ? vbAttr.trim().split(/[\s,]+/).map(Number) : null;
  const num = (v: string | null) => (v && /^\s*[\d.]+\s*(px)?\s*$/.test(v) ? parseFloat(v) : NaN);
  const w = num(svgEl.getAttribute('width'));
  const h = num(svgEl.getAttribute('height'));
  if (!vb || vb.length !== 4 || vb.some((n) => !Number.isFinite(n)) || vb[2] <= 0 || vb[3] <= 0) {
    if (Number.isFinite(w) && Number.isFinite(h) && w > 0 && h > 0) vb = [0, 0, w, h];
    else throw new UploadError('The SVG needs a viewBox or numeric width/height so its proportions are known.');
  }
  svgEl.setAttribute('viewBox', vb.join(' '));
  svgEl.removeAttribute('viewbox');
  svgEl.setAttribute('xmlns', 'http://www.w3.org/2000/svg');
  svgEl.removeAttribute('width');
  svgEl.removeAttribute('height');
  const svg = svgEl.outerHTML;
  if (/<script|javascript:|on[a-z]+\s*=/i.test(svg)) throw new UploadError('SVG still contains executable content after sanitizing; upload rejected.');
  return { svg, width: vb[2], height: vb[3], viewBox: vb.join(' '), removed };
}

/** Inner markup of a sanitized SVG (for inlining into PDFs). */
export function svgInner(svg: string): string {
  const m = /<svg[^>]*>([\s\S]*)<\/svg>\s*$/i.exec(svg);
  return m ? m[1] : '';
}

export interface PngInfo {
  width: number;
  height: number;
  hasAlpha: boolean;
}

const PNG_SIG = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);

/** Validate PNG by signature and read IHDR; detect alpha (colour type 4/6 or tRNS chunk). */
export function inspectPng(buf: Buffer): PngInfo {
  if (buf.length < 33 || !buf.subarray(0, 8).equals(PNG_SIG)) throw new UploadError('File is not a valid PNG.');
  if (buf.toString('ascii', 12, 16) !== 'IHDR') throw new UploadError('PNG is missing its header chunk.');
  const width = buf.readUInt32BE(16);
  const height = buf.readUInt32BE(20);
  const colorType = buf[25];
  if (!width || !height || width > 12000 || height > 12000) throw new UploadError('PNG dimensions must be between 1 and 12000 px.');
  let hasAlpha = colorType === 4 || colorType === 6;
  let off = 8;
  while (!hasAlpha && off + 8 <= buf.length) {
    const len = buf.readUInt32BE(off);
    const type = buf.toString('ascii', off + 4, off + 8);
    if (type === 'tRNS') hasAlpha = true;
    if (type === 'IDAT' || type === 'IEND') break;
    off += 12 + len;
  }
  return { width, height, hasAlpha };
}

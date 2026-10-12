/**
 * Deterministic 2D ghost-mockup renderer.
 *
 * Pipeline (all passes are rendered from the same project document as the technical view):
 *   1. Panel colours (+ all-over patterns, which are dyed into the cloth) — technical space.
 *   2. Warp to mockup space through the template's calibrated mesh (piecewise affine).
 *   3. Fabric surface texture per panel (procedural, seeded → deterministic).
 *   4. Artwork mapped through the mesh + displacement map; print / embroidery treatments.
 *   5. Seams + stitching (thread sits on the fabric surface).
 *   6. Shading: edge occlusion, inner-garment shadow, shadow map (multiply), highlight map (screen).
 *      Foreground components win over inner panels via the z-ordered panel id map.
 *   7. Embellishments & hardware on top with contact shadows and glints.
 * Output is an appearance preview — not a fit/drape simulation and not a colour standard.
 */
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { TechView, type AssetDraw } from '../../shared/render/TechView';
import type { GarmentTemplate, GhostMesh, GhostViewAssets, ViewId } from '../../shared/schema/template';
import type { ArtworkLayer, PatternLayer, ProjectDoc } from '../../shared/schema/project';
import type { DecorationMethod } from '../../shared/schema/template';
import { getView, resolveFill } from '../../shared/domain/design';
import { embellishmentPositions } from '../../shared/domain/bom';
import { getTexture, type TextureKind } from '../../shared/catalog/textures';
import { blobUrl } from '../api';

export class GhostRenderError extends Error {}

/* ------------------------------------------------------------------ */
/* Loading                                                             */
/* ------------------------------------------------------------------ */

const imageCache = new Map<string, Promise<HTMLImageElement>>();
function loadImage(url: string): Promise<HTMLImageElement> {
  let p = imageCache.get(url);
  if (!p) {
    p = new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new GhostRenderError(`Could not load rendering asset ${url}. Check that the ghost assets are installed (npm run build:ghost).`));
      img.src = url;
    });
    imageCache.set(url, p);
    p.catch(() => imageCache.delete(url));
  }
  return p;
}

const dataUriCache = new Map<string, Promise<string>>();
function assetDataUri(sha: string, kind: 'png' | 'svg'): Promise<string> {
  let p = dataUriCache.get(sha);
  if (!p) {
    p = fetch(blobUrl(sha))
      .then((r) => {
        if (!r.ok) throw new GhostRenderError(`Uploaded file ${sha.slice(0, 8)}… is missing from storage. Re-upload it.`);
        return r.blob();
      })
      .then(
        (b) =>
          new Promise<string>((resolve) => {
            const fr = new FileReader();
            fr.onload = () => resolve(String(fr.result).replace(/^data:[^;]*;/, `data:${kind === 'svg' ? 'image/svg+xml' : 'image/png'};`));
            fr.readAsDataURL(b);
          }),
      );
    dataUriCache.set(sha, p);
    p.catch(() => dataUriCache.delete(sha));
  }
  return p;
}

async function svgImage(svg: string): Promise<HTMLImageElement> {
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
  try {
    return await new Promise((resolve, reject) => {
      const img = new Image();
      img.onload = () => resolve(img);
      img.onerror = () => reject(new GhostRenderError('A design layer could not be rasterised for the mockup.'));
      img.src = url;
    });
  } finally {
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}

function canvas(w: number, h: number): HTMLCanvasElement {
  const c = document.createElement('canvas');
  c.width = Math.max(1, Math.round(w));
  c.height = Math.max(1, Math.round(h));
  return c;
}

/* ------------------------------------------------------------------ */
/* Mesh warp                                                           */
/* ------------------------------------------------------------------ */

function affine(s: number[][], d: number[][]): [number, number, number, number, number, number] {
  // Solve d = M s for 2x3 M from three point pairs.
  const [[x0, y0], [x1, y1], [x2, y2]] = s;
  const det = x0 * (y1 - y2) - x1 * (y0 - y2) + x2 * (y0 - y1);
  const solve = (v0: number, v1: number, v2: number) => {
    const a = (v0 * (y1 - y2) - v1 * (y0 - y2) + v2 * (y0 - y1)) / det;
    const b = (x0 * (v1 - v2) - x1 * (v0 - v2) + x2 * (v0 - v1)) / det;
    const c = (x0 * (y1 * v2 - y2 * v1) - x1 * (y0 * v2 - y2 * v0) + x2 * (y0 * v1 - y1 * v0)) / det;
    return [a, b, c];
  };
  const [a, c, e] = solve(d[0][0], d[1][0], d[2][0]);
  const [b, dd, f] = solve(d[0][1], d[1][1], d[2][1]);
  return [a, b, c, dd, e, f];
}

/**
 * Draw `src` (technical space, `srcScale` px per unit) into `ctx` (mockup space, `outScale` px
 * per mockup unit) through the mesh, triangle by triangle.
 */
function warp(ctx: CanvasRenderingContext2D, src: CanvasImageSource, mesh: GhostMesh, srcScale: number, outScale: number) {
  const [bx, by, bw, bh] = mesh.bounds;
  const sp = (c: number, r: number) => [(bx + (bw * c) / (mesh.cols - 1)) * srcScale, (by + (bh * r) / (mesh.rows - 1)) * srcScale];
  const dp = (c: number, r: number) => {
    const p = mesh.dst[r * mesh.cols + c];
    return [p[0] * outScale, p[1] * outScale];
  };
  for (let r = 0; r < mesh.rows - 1; r++) {
    for (let c = 0; c < mesh.cols - 1; c++) {
      const tris = [
        [
          [c, r],
          [c + 1, r],
          [c, r + 1],
        ],
        [
          [c + 1, r],
          [c + 1, r + 1],
          [c, r + 1],
        ],
      ];
      for (const t of tris) {
        const s = t.map(([cc, rr]) => sp(cc, rr));
        const d = t.map(([cc, rr]) => dp(cc, rr));
        // Offset every edge outward by ~1px (scale about the incentre-ish centroid by 1 + δ/inradius)
        // so anti-aliased clip edges of neighbouring triangles overlap instead of leaving hairlines.
        const cx = (d[0][0] + d[1][0] + d[2][0]) / 3;
        const cy = (d[0][1] + d[1][1] + d[2][1]) / 3;
        const area = Math.abs((d[1][0] - d[0][0]) * (d[2][1] - d[0][1]) - (d[2][0] - d[0][0]) * (d[1][1] - d[0][1])) / 2;
        const per = Math.hypot(d[1][0] - d[0][0], d[1][1] - d[0][1]) + Math.hypot(d[2][0] - d[1][0], d[2][1] - d[1][1]) + Math.hypot(d[0][0] - d[2][0], d[0][1] - d[2][1]);
        const inr = per > 0 ? (2 * area) / per : 1;
        const f = 1 + 1.1 / Math.max(0.5, inr);
        const ex = d.map(([x, y]) => [cx + (x - cx) * f, cy + (y - cy) * f]);
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(ex[0][0], ex[0][1]);
        ctx.lineTo(ex[1][0], ex[1][1]);
        ctx.lineTo(ex[2][0], ex[2][1]);
        ctx.closePath();
        ctx.clip();
        const m = affine(s, d);
        ctx.setTransform(m[0], m[1], m[2], m[3], m[4], m[5]);
        ctx.drawImage(src, 0, 0);
        ctx.restore();
      }
    }
  }
}

/** Map one technical point into mockup units (bilinear within the mesh cell). */
export function mapPoint(mesh: GhostMesh, x: number, y: number): [number, number] {
  const [bx, by, bw, bh] = mesh.bounds;
  const fc = Math.min(mesh.cols - 1.0001, Math.max(0, ((x - bx) / bw) * (mesh.cols - 1)));
  const fr = Math.min(mesh.rows - 1.0001, Math.max(0, ((y - by) / bh) * (mesh.rows - 1)));
  const c = Math.floor(fc);
  const r = Math.floor(fr);
  const u = fc - c;
  const v = fr - r;
  const P = (cc: number, rr: number) => mesh.dst[rr * mesh.cols + cc];
  const a = P(c, r);
  const b = P(c + 1, r);
  const d = P(c, r + 1);
  const e = P(c + 1, r + 1);
  return [a[0] * (1 - u) * (1 - v) + b[0] * u * (1 - v) + d[0] * (1 - u) * v + e[0] * u * v, a[1] * (1 - u) * (1 - v) + b[1] * u * (1 - v) + d[1] * (1 - u) * v + e[1] * u * v];
}

/* ------------------------------------------------------------------ */
/* Procedural fabric surface (seeded, deterministic)                   */
/* ------------------------------------------------------------------ */

function hash(x: number, y: number, seed: number): number {
  let h = (x * 374761393 + y * 668265263 + seed * 2147483647) | 0;
  h = Math.imul(h ^ (h >>> 13), 1274126177);
  return ((h ^ (h >>> 16)) >>> 0) / 4294967295;
}

function valueNoise(x: number, y: number, seed: number): number {
  const xi = Math.floor(x);
  const yi = Math.floor(y);
  const xf = x - xi;
  const yf = y - yi;
  const s = (t: number) => t * t * (3 - 2 * t);
  const a = hash(xi, yi, seed);
  const b = hash(xi + 1, yi, seed);
  const c = hash(xi, yi + 1, seed);
  const d = hash(xi + 1, yi + 1, seed);
  return a + (b - a) * s(xf) + (c - a) * s(yf) + (a - b - c + d) * s(xf) * s(yf);
}

/** A tileable grey tile (128 = neutral) for soft-light blending. */
function textureTile(kind: TextureKind, px: number): HTMLCanvasElement {
  const n = Math.max(4, Math.round(px));
  const size = kind === 'slub' || kind === 'fleece' || kind === 'terry' ? n : n * 4;
  const c = canvas(size, size);
  const ctx = c.getContext('2d')!;
  const img = ctx.createImageData(size, size);
  for (let y = 0; y < size; y++) {
    for (let x = 0; x < size; x++) {
      const u = x / n;
      const v = y / n;
      let val = 0;
      switch (kind) {
        case 'rib':
          val = Math.sin(u * Math.PI * 2) * 0.55 + (hash(x, y, 3) - 0.5) * 0.2;
          break;
        case 'pique': {
          const fu = u - Math.floor(u) - 0.5;
          const fv = v - Math.floor(v) - 0.5;
          val = (Math.hypot(fu, fv) < 0.28 ? -0.5 : 0.25) + (hash(x, y, 5) - 0.5) * 0.15;
          break;
        }
        case 'waffle': {
          const fu = Math.abs(u - Math.floor(u) - 0.5);
          const fv = Math.abs(v - Math.floor(v) - 0.5);
          val = Math.max(fu, fv) > 0.38 ? 0.45 : -0.25;
          break;
        }
        case 'twill':
          val = Math.sin((u + v) * Math.PI * 2) * 0.5;
          break;
        case 'slub':
          val = (valueNoise(x / (size / 2), y / 2.5, 11) - 0.5) * 1.1 + (hash(x, y, 2) - 0.5) * 0.15;
          break;
        case 'fleece':
        case 'terry':
          val = (valueNoise(x / 6, y / 6, 7) - 0.5) * 0.7 + (hash(x, y, 9) - 0.5) * 0.35;
          break;
        default: {
          // Jersey: rows of V-shaped loops.
          const fu = u - Math.floor(u);
          const fv = v - Math.floor(v);
          const vshape = Math.abs(fu - 0.5) * 2 - fv;
          val = Math.cos(vshape * Math.PI * 2) * 0.45 + (hash(x, y, 1) - 0.5) * 0.25;
        }
      }
      const g = Math.max(0, Math.min(255, 128 + val * 80));
      const i = (y * size + x) * 4;
      img.data[i] = img.data[i + 1] = img.data[i + 2] = g;
      img.data[i + 3] = 255;
    }
  }
  ctx.putImageData(img, 0, 0);
  return c;
}

/* ------------------------------------------------------------------ */
/* Pipeline                                                            */
/* ------------------------------------------------------------------ */

const PRINT_METHODS: DecorationMethod[] = ['screen-print', 'dtg', 'heat-transfer', 'sublimation'];
const RAISED_METHODS: DecorationMethod[] = ['embroidery', 'applique', 'puff-print'];

export interface GhostRenderOptions {
  doc: ProjectDoc;
  template: GarmentTemplate;
  view: ViewId;
  colorwayId: string | null;
  /** Output pixels per mockup unit (1 = preview, 2+ = high-resolution export). */
  scale: number;
  /** Transparent background instead of studio backdrop. */
  transparent?: boolean;
}

function idMapSvg(template: GarmentTemplate, view: ViewId, w: number, h: number): { svg: string; comps: string[]; inner: Set<number> } {
  const v = getView(template, view);
  const panels = [...v.panels].sort((a, b) => a.z - b.z);
  const comps = [...new Set(panels.map((p) => p.componentId))];
  const inner = new Set<number>();
  const paths = panels
    .map((p) => {
      const idx = comps.indexOf(p.componentId) + 1;
      const g = p.side === 'inner' ? 255 : 0;
      if (p.side === 'inner') inner.add(idx);
      return `<path d="${p.d}" fill="rgb(${idx * 10},${g},0)"/>`;
    })
    .join('');
  return {
    svg: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="${v.viewBox.join(' ')}" width="${w}" height="${h}" shape-rendering="crispEdges">${paths}</svg>`,
    comps,
    inner,
  };
}

export async function renderGhost(target: HTMLCanvasElement, opts: GhostRenderOptions): Promise<void> {
  const { doc, template, view, colorwayId, scale } = opts;
  if (!template.ghost) throw new GhostRenderError(`No ghost rendering assets are installed for ${template.name}. Use the technical view.`);
  const assets: GhostViewAssets | undefined = template.ghost.views[view];
  if (!assets) throw new GhostRenderError(`No ${view} ghost assets for ${template.name}.`);
  const tv = getView(template, view);
  const [, , vw, vh] = tv.viewBox;
  const W = assets.width * scale;
  const H = assets.height * scale;
  const outScale = scale;
  // Technical raster resolution: ~1.6 px per unit per output scale for crisp warps.
  const srcScale = 1.6 * scale;
  const TW = vw * srcScale;
  const TH = vh * srcScale;

  // Embed uploaded files as data URIs (SVG-as-image cannot fetch external URLs).
  const draws = new Map<string, AssetDraw>();
  await Promise.all(
    doc.assets.map(async (a) => {
      try {
        draws.set(a.id, { kind: 'href', href: await assetDataUri(a.sha256, a.kind) });
      } catch {
        draws.set(a.id, { kind: 'missing' });
      }
    }),
  );
  const resolve = (id: string): AssetDraw => draws.get(id) ?? { kind: 'missing' };
  const pass = (props: Partial<React.ComponentProps<typeof TechView>>) =>
    svgImage(
      renderToStaticMarkup(
        React.createElement(TechView, {
          template,
          doc,
          viewId: view,
          colorwayId,
          resolveAsset: resolve,
          idPrefix: `g${Math.random().toString(36).slice(2, 6)}`,
          width: TW,
          height: TH,
          fills: false,
          textures: false,
          decorations: false,
          outlines: false,
          seams: false,
          stitching: false,
          embellishments: false,
          hardware: false,
          annotations: false,
          shadeInner: false,
          occludeDecorations: true,
          ...props,
        }),
      ),
    );

  const isPattern = (l: ArtworkLayer | PatternLayer) => l.type === 'pattern';
  const isPrint = (l: ArtworkLayer | PatternLayer) => l.type === 'artwork' && PRINT_METHODS.includes(l.decoration.method);
  const isRaised = (l: ArtworkLayer | PatternLayer) => l.type === 'artwork' && RAISED_METHODS.includes(l.decoration.method);

  const id = idMapSvg(template, view, TW, TH);
  const [baseImg, printImg, raisedImg, seamImg, stitchImg, topImg, idImg, shadowImg, highlightImg, dispImg] = await Promise.all([
    pass({ fills: true, decorations: true, decorationFilter: isPattern, occludeDecorations: false }),
    pass({ decorations: true, decorationFilter: isPrint }),
    pass({ decorations: true, decorationFilter: isRaised }),
    pass({ seams: true }),
    pass({ stitching: true }),
    pass({ embellishments: true, hardware: true }),
    svgImage(id.svg),
    loadImage(assets.shadow),
    loadImage(assets.highlight),
    loadImage(assets.displacement),
  ]);

  // Rasterise each technical pass once at identity; warping a vector image directly would
  // re-rasterise it per triangle and leave seams along mesh edges.
  const raster = (img: CanvasImageSource, smooth = true) => {
    const c = canvas(TW, TH);
    const ctx = c.getContext('2d')!;
    ctx.imageSmoothingEnabled = smooth;
    ctx.drawImage(img, 0, 0, TW, TH);
    return c;
  };
  const toMockup = (img: CanvasImageSource) => {
    const c = canvas(W, H);
    warp(c.getContext('2d')!, raster(img), assets.mesh, srcScale, outScale);
    return c;
  };

  // ---- 1-2. Base albedo (panel colours + dyed patterns) in mockup space.
  const G = toMockup(baseImg);
  const g = G.getContext('2d')!;
  const mask = canvas(W, H);
  {
    const m = mask.getContext('2d')!;
    m.drawImage(G, 0, 0);
    m.globalCompositeOperation = 'source-in';
    m.fillStyle = '#000';
    m.fillRect(0, 0, W, H);
  }

  // Panel id map → per-component masks.
  const idWarped = canvas(W, H);
  {
    const ic = idWarped.getContext('2d')!;
    ic.imageSmoothingEnabled = false;
    warp(ic, raster(idImg, false), assets.mesh, srcScale, outScale);
  }
  const idData = idWarped.getContext('2d')!.getImageData(0, 0, W, H).data;
  const compMask = (pred: (idx: number, inner: boolean) => boolean) => {
    const c = canvas(W, H);
    const ctx = c.getContext('2d')!;
    const img = ctx.createImageData(W, H);
    for (let i = 0; i < idData.length; i += 4) {
      if (idData[i + 3] < 128) continue;
      const idx = Math.round(idData[i] / 10);
      if (idx > 0 && pred(idx, idData[i + 1] > 128)) img.data[i + 3] = 255;
    }
    ctx.putImageData(img, 0, 0);
    // Soften the 1px stair-step of the nearest-neighbour id map.
    const soft = canvas(W, H);
    const sc = soft.getContext('2d')!;
    sc.filter = `blur(${0.6 * scale}px)`;
    sc.drawImage(c, 0, 0);
    return soft;
  };

  // ---- 3. Fabric surface texture per component.
  const k = template.calibration?.mmPerUnit ?? 1;
  const meshScale = (() => {
    const { cols, rows, bounds, dst } = assets.mesh;
    const step = bounds[2] / (cols - 1);
    let sum = 0;
    for (let r = 0; r < rows; r++) for (let c = 0; c < cols - 1; c++) sum += Math.hypot(dst[r * cols + c + 1][0] - dst[r * cols + c][0], dst[r * cols + c + 1][1] - dst[r * cols + c][1]);
    return sum / (rows * (cols - 1)) / step;
  })();
  const mmToPx = (mm: number) => (mm / k) * meshScale * outScale;
  id.comps.forEach((compId, i) => {
    const textureLayer = [...doc.layers].reverse().find((l) => l.type === 'texture' && l.visible && l.targets.includes(compId) && (l.view === 'all' || l.view === view));
    const mat = resolveFill(doc, compId, view, colorwayId).material;
    const texId = textureLayer && textureLayer.type === 'texture' ? textureLayer.textureId : mat?.textureId;
    const def = texId ? getTexture(texId) : undefined;
    if (!def) return;
    const tScale = textureLayer && textureLayer.type === 'texture' ? textureLayer.scale : 1;
    const strength = textureLayer && textureLayer.type === 'texture' ? textureLayer.strength * textureLayer.opacity : 0.45;
    const tile = textureTile(def.kind, Math.max(3, mmToPx(def.tileMm * tScale)));
    const layer = canvas(W, H);
    const lc = layer.getContext('2d')!;
    lc.fillStyle = lc.createPattern(tile, 'repeat')!;
    lc.fillRect(0, 0, W, H);
    lc.globalCompositeOperation = 'destination-in';
    lc.drawImage(compMask((idx) => idx === i + 1), 0, 0);
    g.save();
    g.globalCompositeOperation = 'soft-light';
    g.globalAlpha = Math.min(1, strength * 1.2);
    g.drawImage(layer, 0, 0);
    g.restore();
  });

  // ---- 4. Artwork through mesh + displacement.
  const dispCanvas = canvas(W, H);
  dispCanvas.getContext('2d')!.drawImage(dispImg, 0, 0, W, H);
  const dispData = dispCanvas.getContext('2d')!.getImageData(0, 0, W, H).data;
  const displace = (src: HTMLCanvasElement, amount: number) => {
    const ctx = src.getContext('2d')!;
    const inD = ctx.getImageData(0, 0, W, H);
    const out = ctx.createImageData(W, H);
    const a = inD.data;
    const o = out.data;
    for (let y = 1; y < H - 1; y++) {
      for (let x = 1; x < W - 1; x++) {
        const i = (y * W + x) * 4;
        const gx = (dispData[i + 4] - dispData[i - 4]) / 255;
        const gy = (dispData[i + W * 4] - dispData[i - W * 4]) / 255;
        const sx = Math.min(W - 1, Math.max(0, Math.round(x + gx * amount * scale)));
        const sy = Math.min(H - 1, Math.max(0, Math.round(y + gy * amount * scale)));
        const j = (sy * W + sx) * 4;
        o[i] = a[j];
        o[i + 1] = a[j + 1];
        o[i + 2] = a[j + 2];
        o[i + 3] = a[j + 3];
      }
    }
    ctx.putImageData(out, 0, 0);
    return src;
  };
  const clipToGarment = (c: HTMLCanvasElement) => {
    const ctx = c.getContext('2d')!;
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(mask, 0, 0);
    ctx.globalCompositeOperation = 'source-over';
    return c;
  };
  const print = clipToGarment(displace(toMockup(printImg), 60));
  g.drawImage(print, 0, 0);
  // Ink sits on the knit: re-apply fabric texture inside the print at reduced strength.
  {
    const t = canvas(W, H);
    const tc = t.getContext('2d')!;
    tc.fillStyle = tc.createPattern(textureTile('jersey', Math.max(3, mmToPx(6))), 'repeat')!;
    tc.fillRect(0, 0, W, H);
    tc.globalCompositeOperation = 'destination-in';
    tc.drawImage(print, 0, 0);
    g.save();
    g.globalCompositeOperation = 'soft-light';
    g.globalAlpha = 0.45;
    g.drawImage(t, 0, 0);
    g.restore();
  }
  const raised = clipToGarment(displace(toMockup(raisedImg), 45));
  {
    // Contact shadow + raised edge + satin thread direction.
    const sh = canvas(W, H);
    const s = sh.getContext('2d')!;
    s.filter = `blur(${2 * scale}px)`;
    s.drawImage(raised, 1.5 * scale, 2.5 * scale);
    s.filter = 'none';
    s.globalCompositeOperation = 'source-in';
    s.fillStyle = 'rgba(0,0,0,0.45)';
    s.fillRect(0, 0, W, H);
    g.drawImage(sh, 0, 0);
    g.drawImage(raised, 0, 0);
    const thread = canvas(W, H);
    const tc = thread.getContext('2d')!;
    tc.fillStyle = tc.createPattern(textureTile('twill', Math.max(3, 2.2 * scale)), 'repeat')!;
    tc.fillRect(0, 0, W, H);
    tc.globalCompositeOperation = 'destination-in';
    tc.drawImage(raised, 0, 0);
    g.save();
    g.globalCompositeOperation = 'overlay';
    g.globalAlpha = 0.7;
    g.drawImage(thread, 0, 0);
    g.restore();
    const hl = canvas(W, H);
    const h = hl.getContext('2d')!;
    h.drawImage(raised, 0, 0);
    h.globalCompositeOperation = 'destination-out';
    h.drawImage(raised, 1 * scale, 1.5 * scale);
    h.globalCompositeOperation = 'source-in';
    h.fillStyle = 'rgba(255,255,255,0.5)';
    h.fillRect(0, 0, W, H);
    g.drawImage(hl, 0, 0);
  }

  // ---- 5. Seams (subtle creases) and stitching thread.
  g.save();
  g.globalCompositeOperation = 'multiply';
  g.globalAlpha = 0.28;
  g.drawImage(clipToGarment(toMockup(seamImg)), 0, 0);
  g.restore();
  g.drawImage(clipToGarment(toMockup(stitchImg)), 0, 0);

  // ---- 6. Shading.
  const shade = (img: CanvasImageSource, op: GlobalCompositeOperation, alpha: number, clip: HTMLCanvasElement = mask) => {
    const c = canvas(W, H);
    const ctx = c.getContext('2d')!;
    ctx.drawImage(img, 0, 0, W, H);
    ctx.globalCompositeOperation = 'destination-in';
    ctx.drawImage(clip, 0, 0);
    g.save();
    g.globalCompositeOperation = op;
    g.globalAlpha = alpha;
    g.drawImage(c, 0, 0);
    g.restore();
  };
  // Edge occlusion derived from the garment silhouette (volume cue).
  {
    const ao = canvas(W, H);
    const a = ao.getContext('2d')!;
    a.fillStyle = '#000';
    a.fillRect(0, 0, W, H);
    a.globalCompositeOperation = 'destination-out';
    a.filter = `blur(${14 * scale}px)`;
    a.drawImage(mask, 0, 0);
    a.filter = 'none';
    shade(ao, 'multiply', 0.38);
  }
  // Inside of the garment (e.g. back neck seen through the opening). Foreground panels drawn
  // above it in the z-ordered id map are excluded automatically → occlusion is respected.
  const innerMask = compMask((_, inner) => inner);
  {
    const c = canvas(W, H);
    const ctx = c.getContext('2d')!;
    const grd = ctx.createLinearGradient(0, 0, 0, H * 0.25);
    grd.addColorStop(0, '#6d6d6d');
    grd.addColorStop(1, '#9a9a9a');
    ctx.fillStyle = grd;
    ctx.fillRect(0, 0, W, H);
    shade(c, 'multiply', 1, innerMask);
  }
  shade(shadowImg, 'multiply', 1);
  shade(highlightImg, 'screen', 0.85);

  // ---- 7. Embellishments & hardware with contact shadows and glints.
  const top = toMockup(topImg);
  {
    const sh = canvas(W, H);
    const s = sh.getContext('2d')!;
    s.filter = `blur(${1.5 * scale}px)`;
    s.drawImage(top, 1.2 * scale, 2 * scale);
    s.filter = 'none';
    s.globalCompositeOperation = 'source-in';
    s.fillStyle = 'rgba(0,0,0,0.5)';
    s.fillRect(0, 0, W, H);
    g.drawImage(sh, 0, 0);
    g.drawImage(top, 0, 0);
    // Glints (specular) per placed stone / stud — deterministic by index.
    for (const l of doc.layers) {
      if (l.type !== 'embellishment' || !l.visible || (l.view !== 'all' && l.view !== view)) continue;
      const pts = embellishmentPositions(l, template);
      const rPx = (l.diameterMm / k) * meshScale * outScale * 0.5;
      pts.forEach((p, i) => {
        const [mx, my] = mapPoint(assets.mesh, p.x, p.y);
        const x = mx * outScale - rPx * 0.3;
        const y = my * outScale - rPx * 0.35;
        const sparkle = 0.55 + hash(i, l.points.length, 17) * 0.45;
        const grd = g.createRadialGradient(x, y, 0, x, y, rPx * (l.kind === 'rhinestone' ? 1.1 : 0.7));
        grd.addColorStop(0, `rgba(255,255,255,${0.95 * sparkle})`);
        grd.addColorStop(1, 'rgba(255,255,255,0)');
        g.fillStyle = grd;
        g.beginPath();
        g.arc(x, y, rPx * 1.2, 0, Math.PI * 2);
        g.fill();
        if (l.kind === 'rhinestone' && sparkle > 0.8) {
          g.strokeStyle = `rgba(255,255,255,${sparkle * 0.8})`;
          g.lineWidth = Math.max(0.6, 0.18 * rPx);
          const len = rPx * 1.8;
          g.beginPath();
          g.moveTo(x - len, y);
          g.lineTo(x + len, y);
          g.moveTo(x, y - len);
          g.lineTo(x, y + len);
          g.stroke();
        }
      });
    }
  }

  // ---- Final composite onto studio backdrop.
  target.width = W;
  target.height = H;
  const out = target.getContext('2d')!;
  out.clearRect(0, 0, W, H);
  if (!opts.transparent) {
    const bg = out.createRadialGradient(W / 2, H * 0.45, 0, W / 2, H * 0.45, Math.max(W, H) * 0.75);
    bg.addColorStop(0, '#fbfbfa');
    bg.addColorStop(1, '#e9e9e6');
    out.fillStyle = bg;
    out.fillRect(0, 0, W, H);
    out.save();
    out.filter = `blur(${12 * scale}px)`;
    out.globalAlpha = 0.22;
    out.drawImage(mask, 0, 9 * scale);
    out.restore();
  }
  out.drawImage(G, 0, 0);
}

/** Render a high-resolution PNG (for exports). */
export async function renderGhostPng(doc: ProjectDoc, template: GarmentTemplate, view: ViewId, colorwayId: string | null, scale = 2): Promise<Blob> {
  const c = document.createElement('canvas');
  await renderGhost(c, { doc, template, view, colorwayId, scale });
  return new Promise((resolve, reject) => c.toBlob((b) => (b ? resolve(b) : reject(new GhostRenderError('PNG encoding failed.'))), 'image/png'));
}

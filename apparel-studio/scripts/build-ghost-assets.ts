/**
 * Generates matched ghost-mockup assets from scripts/ghost/specs.ts:
 *   public/ghost/<template>-v<version>/<view>-{shadow,highlight,displacement}.svg
 *   src/shared/templates/ghost/<template>-v<version>.json   (mesh + asset manifest)
 * Deterministic: same spec → byte-identical output. Run: npx tsx scripts/build-ghost-assets.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import { GHOST_SPECS, type GarmentGhostSpec, type Stroke, type Blob } from './ghost/specs';

const r2 = (n: number) => Math.round(n * 100) / 100;

function toMockup(spec: GarmentGhostSpec, view: 'front' | 'back', x: number, y: number): [number, number] {
  const [wx, wy] = spec.warp(x, y, view);
  return [r2(spec.mockup.offsetX + wx * spec.mockup.scale), r2(spec.mockup.offsetY + wy * spec.mockup.scale)];
}

function densify(pts: [number, number][], step = 8): [number, number][] {
  const out: [number, number][] = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const [ax, ay] = pts[i - 1];
    const [bx, by] = pts[i];
    const n = Math.max(1, Math.ceil(Math.hypot(bx - ax, by - ay) / step));
    for (let k = 1; k <= n; k++) out.push([ax + ((bx - ax) * k) / n, ay + ((by - ay) * k) / n]);
  }
  return out;
}

function strokeSvg(spec: GarmentGhostSpec, view: 'front' | 'back', s: Stroke, color: string): string {
  const pts = densify(s.pts).map(([x, y]) => toMockup(spec, view, x, y));
  const d = 'M' + pts.map((p) => p.join(',')).join(' L');
  return `<path d="${d}" fill="none" stroke="${color}" stroke-opacity="${s.strength}" stroke-width="${r2(s.width * spec.mockup.scale)}" stroke-linecap="round" stroke-linejoin="round" filter="url(#b${Math.round(s.blur)})"/>`;
}

function blobSvg(spec: GarmentGhostSpec, view: 'front' | 'back', b: Blob, gradId: string): string {
  const [cx, cy] = toMockup(spec, view, b.cx, b.cy);
  const rx = r2(b.rx * spec.mockup.scale);
  const ry = r2(b.ry * spec.mockup.scale);
  return `<ellipse cx="${cx}" cy="${cy}" rx="${rx}" ry="${ry}" fill="url(#${gradId})" opacity="${b.strength}"${b.rotate ? ` transform="rotate(${b.rotate} ${cx} ${cy})"` : ''}/>`;
}

function filters(strokes: Stroke[]): string {
  const blurs = [...new Set(strokes.map((s) => Math.round(s.blur)))].sort((a, b) => a - b);
  return blurs.map((b) => `<filter id="b${b}" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="${b}"/></filter>`).join('');
}

function svgDoc(spec: GarmentGhostSpec, bg: string, defs: string, body: string): string {
  const { width, height } = spec.mockup;
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" width="${width}" height="${height}"><defs>${defs}</defs><rect width="${width}" height="${height}" fill="${bg}"/>${body}</svg>\n`;
}

for (const spec of GHOST_SPECS) {
  const key = `${spec.templateId}-v${spec.version}`;
  const outDir = path.join('public', 'ghost', key);
  fs.mkdirSync(outDir, { recursive: true });
  const manifest: Record<string, unknown> = {};
  for (const view of ['front', 'back'] as const) {
    const sh = spec.views[view];
    const grad = (id: string, c: string) => `<radialGradient id="${id}"><stop offset="0" stop-color="${c}" stop-opacity="1"/><stop offset="1" stop-color="${c}" stop-opacity="0"/></radialGradient>`;
    const shadow = svgDoc(spec, '#ffffff', filters(sh.shadows) + grad('gs', '#000'), sh.shadows.map((s) => strokeSvg(spec, view, s, '#000')).join('') + sh.shadowBlobs.map((b) => blobSvg(spec, view, b, 'gs')).join(''));
    const highlight = svgDoc(spec, '#000000', filters(sh.highlights) + grad('gh', '#fff'), sh.highlights.map((s) => strokeSvg(spec, view, s, '#fff')).join('') + sh.highlightBlobs.map((b) => blobSvg(spec, view, b, 'gh')).join(''));
    const displacement = svgDoc(spec, '#808080', filters(sh.displacement), sh.displacement.map((s) => strokeSvg(spec, view, s, '#000')).join(''));
    fs.writeFileSync(path.join(outDir, `${view}-shadow.svg`), shadow);
    fs.writeFileSync(path.join(outDir, `${view}-highlight.svg`), highlight);
    fs.writeFileSync(path.join(outDir, `${view}-displacement.svg`), displacement);
    const [bx, by, bw, bh] = spec.techBounds;
    const dst: [number, number][] = [];
    for (let r = 0; r < spec.mesh.rows; r++) {
      for (let c = 0; c < spec.mesh.cols; c++) {
        const x = bx + (bw * c) / (spec.mesh.cols - 1);
        const y = by + (bh * r) / (spec.mesh.rows - 1);
        dst.push(toMockup(spec, view, x, y));
      }
    }
    manifest[view] = {
      width: spec.mockup.width,
      height: spec.mockup.height,
      mesh: { cols: spec.mesh.cols, rows: spec.mesh.rows, bounds: spec.techBounds, dst },
      shadow: `/ghost/${key}/${view}-shadow.svg`,
      highlight: `/ghost/${key}/${view}-highlight.svg`,
      displacement: `/ghost/${key}/${view}-displacement.svg`,
      occlusion: null,
      foregroundComponents: spec.foregroundComponents[view],
    };
  }
  const jsonDir = path.join('src', 'shared', 'templates', 'ghost');
  fs.mkdirSync(jsonDir, { recursive: true });
  fs.writeFileSync(
    path.join(jsonDir, `${key}.json`),
    JSON.stringify(
      {
        assetSetId: `${key}-ghost`,
        version: 1,
        quality: 'procedural-v1',
        notes: 'Shading, highlight and displacement maps are hand-authored vector folds rendered deterministically; panel masks come from template geometry. Not photographic.',
        views: manifest,
      },
      null,
      1,
    ) + '\n',
  );
  console.log(`Built ghost assets for ${key}`);
}

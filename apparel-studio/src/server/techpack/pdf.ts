import PDFDocument from 'pdfkit';
import SVGtoPDF from 'svg-to-pdfkit';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { createRequire } from 'node:module';
import path from 'node:path';
import type { StorageAdapter } from '../storage';
import type { RevisionSnapshot } from './revisions';
import { TechView, type AssetDraw, type AssetResolver, type Callout } from '../../shared/render/TechView';
import type { ViewId } from '../../shared/schema/template';
import { DECORATION_METHOD_LABELS, STITCH_STYLE_LABELS } from '../../shared/schema/template';
import type { ArtworkLayer, Layer } from '../../shared/schema/project';
import { componentName, getView, layerAppliesToView, resolveColor, resolveFill } from '../../shared/domain/design';
import { colorwayNames, embellishmentPositions, embellishmentCount } from '../../shared/domain/bom';
import { findAnchor } from '../../shared/domain/placement';
import { flattenPath, pathBBox } from '../../shared/geometry';
import { formatLength, type LengthUnit } from '../../shared/units';
import { getHardware } from '../../shared/catalog/hardware';
import { sizeLabelFor } from '../../shared/catalog/embellishments';
import { svgInner } from '../sanitize';

const require = createRequire(import.meta.url);
const FONT_DIR = path.join(path.dirname(require.resolve('dejavu-fonts-ttf/package.json')), 'ttf');

const PAGE_W = 792;
const PAGE_H = 612;
const LEFT = 36;
const RIGHT = PAGE_W - 36;
const CONTENT_W = RIGHT - LEFT;
const CONTENT_TOP = 78;
const CONTENT_BOTTOM = PAGE_H - 46;
const INK = '#111827';
const MUTED = '#4b5563';
const RULE = '#d1d5db';
const ACCENT = '#1d4ed8';

type Doc = PDFKit.PDFDocument;

interface Ctx {
  doc: Doc;
  y: number;
  snap: RevisionSnapshot;
  unit: LengthUnit;
  resolve: AssetResolver;
  section: string;
}

/** Display length for print: inches use fractions (industry convention). */
function len(ctx: Ctx, mm: number | null | undefined) {
  return formatLength(mm, ctx.unit, { fractions: ctx.unit === 'in', withUnit: false });
}

function svgToPdf(ctx: Ctx, svg: string, x: number, y: number, w: number, h: number) {
  SVGtoPDF(ctx.doc, svg, x, y, {
    width: w,
    height: h,
    preserveAspectRatio: 'xMidYMid meet',
    fontCallback: (_family: string, bold: boolean) => (bold ? 'Sans-Bold' : 'Sans'),
    warningCallback: () => undefined,
  });
}

function newPage(ctx: Ctx, title: string, subtitle?: string) {
  ctx.doc.addPage();
  ctx.section = title;
  ctx.doc.font('Sans-Bold').fontSize(15).fillColor(INK).text(title, LEFT, CONTENT_TOP - 6, { width: CONTENT_W, lineBreak: false });
  ctx.y = CONTENT_TOP + 16;
  if (subtitle) {
    ctx.doc.font('Sans').fontSize(8.5).fillColor(MUTED).text(subtitle, LEFT, ctx.y, { width: CONTENT_W });
    ctx.y = ctx.doc.y + 6;
  }
  ctx.y += 4;
}

function ensure(ctx: Ctx, h: number) {
  if (ctx.y + h > CONTENT_BOTTOM) newPage(ctx, `${ctx.section.replace(/ \(continued\)$/, '')} (continued)`);
}

function heading(ctx: Ctx, text: string) {
  ensure(ctx, 40);
  ctx.doc.font('Sans-Bold').fontSize(10.5).fillColor(INK).text(text, LEFT, ctx.y, { width: CONTENT_W });
  ctx.y = ctx.doc.y + 4;
}

function para(ctx: Ctx, text: string, opts: { size?: number; color?: string; x?: number; width?: number } = {}) {
  const size = opts.size ?? 8.5;
  const width = opts.width ?? CONTENT_W;
  ctx.doc.font('Sans').fontSize(size);
  const h = ctx.doc.heightOfString(text, { width });
  ensure(ctx, h + 2);
  ctx.doc.fillColor(opts.color ?? INK).text(text, opts.x ?? LEFT, ctx.y, { width });
  ctx.y += h + 4;
}

type Cell = string | { text: string; swatch?: string; bold?: boolean; color?: string };
interface Col {
  header: string;
  width: number;
  align?: 'left' | 'right' | 'center';
}

/** Paginated table: rows never split across pages; header repeats on each page. */
function table(ctx: Ctx, cols: Col[], rows: Cell[][], opts: { fontSize?: number } = {}) {
  const doc = ctx.doc;
  const fs = opts.fontSize ?? 7.5;
  const pad = 3;
  const totalW = cols.reduce((a, c) => a + c.width, 0);
  const scale = totalW > CONTENT_W ? CONTENT_W / totalW : 1;
  const widths = cols.map((c) => c.width * scale);
  const drawHeader = () => {
    doc.font('Sans-Bold').fontSize(fs);
    const h = Math.max(...cols.map((c, i) => doc.heightOfString(c.header, { width: widths[i] - pad * 2 }))) + pad * 2;
    doc.rect(LEFT, ctx.y, widths.reduce((a, b) => a + b, 0), h).fill('#eef2f7');
    let x = LEFT;
    cols.forEach((c, i) => {
      doc.fillColor(INK).font('Sans-Bold').fontSize(fs).text(c.header, x + pad, ctx.y + pad, { width: widths[i] - pad * 2, align: c.align ?? 'left' });
      x += widths[i];
    });
    ctx.y += h;
  };
  ensure(ctx, 40);
  drawHeader();
  for (const row of rows) {
    // Measure every cell with the font it is drawn in (bold text wraps sooner than regular).
    const heights = row.map((cell, i) => {
      const t = typeof cell === 'string' ? cell : cell.text;
      const sw = typeof cell !== 'string' && cell.swatch ? 12 : 0;
      doc.font(typeof cell !== 'string' && cell.bold ? 'Sans-Bold' : 'Sans').fontSize(fs);
      return doc.heightOfString(t || ' ', { width: widths[i] - pad * 2 - sw });
    });
    const h = Math.max(...heights, fs) + pad * 2;
    if (ctx.y + h > CONTENT_BOTTOM) {
      newPage(ctx, `${ctx.section.replace(/ \(continued\)$/, '')} (continued)`);
      drawHeader();
    }
    let x = LEFT;
    row.forEach((cell, i) => {
      const t = typeof cell === 'string' ? cell : cell.text;
      let tx = x + pad;
      if (typeof cell !== 'string' && cell.swatch) {
        doc.rect(tx, ctx.y + pad + 0.5, 9, 9).fillAndStroke(cell.swatch, '#6b7280');
        tx += 12;
      }
      const bold = typeof cell !== 'string' && cell.bold;
      doc
        .fillColor(typeof cell !== 'string' && cell.color ? cell.color : INK)
        .font(bold ? 'Sans-Bold' : 'Sans')
        .fontSize(fs)
        .text(t, tx, ctx.y + pad, { width: widths[i] - pad * 2 - (tx - x - pad), align: cols[i].align ?? 'left' });
      x += widths[i];
    });
    ctx.y += h;
    doc.moveTo(LEFT, ctx.y).lineTo(LEFT + widths.reduce((a, b) => a + b, 0), ctx.y).lineWidth(0.4).strokeColor(RULE).stroke();
  }
  ctx.y += 8;
}

function techSvg(ctx: Ctx, viewId: ViewId, extra: Partial<React.ComponentProps<typeof TechView>> = {}, colorwayId?: string) {
  return renderToStaticMarkup(
    React.createElement(TechView, {
      template: ctx.snap.template,
      doc: ctx.snap.doc,
      viewId,
      colorwayId: colorwayId ?? ctx.snap.doc.colorways[0].id,
      resolveAsset: ctx.resolve,
      idPrefix: `p${Math.random().toString(36).slice(2, 7)}`,
      // Flats stay clean line drawings; fabric texture is an appearance-preview concern.
      textures: false,
      ...extra,
    }),
  );
}

/* ------------------------------------------------------------------ */
/* Callouts                                                            */
/* ------------------------------------------------------------------ */

interface CalloutItem extends Callout {
  view: ViewId;
  title: string;
  detail: string;
}

function seamMidpoint(d: string): { x: number; y: number } {
  const pts = flattenPath(d)[0];
  const p = pts[Math.floor(pts.length / 2)];
  return { x: p[0], y: p[1] };
}

export function placementText(ctx: { snap: RevisionSnapshot; unit: LengthUnit }, l: ArtworkLayer): string {
  const p = l.placement;
  const anchor = findAnchor(ctx.snap.template, p.anchorId);
  const u = ctx.unit;
  const f = (mm: number) => formatLength(mm, u, { fractions: u === 'in' });
  const horiz = p.offsetXmm === 0 ? 'centered' : `${f(Math.abs(p.offsetXmm))} ${p.offsetXmm > 0 ? 'toward wearer’s left' : 'toward wearer’s right'}`;
  const vert = p.offsetYmm === 0 ? 'level' : `${f(Math.abs(p.offsetYmm))} ${p.offsetYmm > 0 ? 'below' : 'above'}`;
  return `${p.reference === 'center' ? 'Artwork center' : 'Top of artwork'}: ${vert}, ${horiz} from ${anchor?.label ?? 'no reference'}`;
}

function buildCallouts(ctx: Ctx): CalloutItem[] {
  const out: CalloutItem[] = [];
  const t = ctx.snap.template;
  let n = 1;
  for (const viewId of ['front', 'back'] as ViewId[]) {
    const view = getView(t, viewId);
    for (const l of ctx.snap.doc.layers) {
      if (!l.visible || !layerAppliesToView(l, viewId) || l.type === 'panelFill') continue;
      let pos: { x: number; y: number } | null = null;
      let title = l.name;
      let detail = '';
      if (l.type === 'artwork') {
        pos = { x: l.transform.x, y: l.transform.y };
        detail = `${DECORATION_METHOD_LABELS[l.decoration.method]} · ${len(ctx, l.placement.widthMm)} × ${len(ctx, l.placement.heightMm)} ${ctx.unit}${
          l.placement.source === 'entered' ? '' : ' (visual estimate)'
        } · ${placementText(ctx, l)}`;
      } else if (l.type === 'pattern') {
        const panel = view.panels.find((p) => l.targets.includes(p.componentId) && p.side === 'outer');
        if (panel) {
          const b = pathBBox(panel.d);
          pos = { x: b.x + b.width * 0.5, y: b.y + b.height * 0.6 };
        }
        detail = `All-over pattern (${DECORATION_METHOD_LABELS[l.method]}), repeat width ${len(ctx, l.tileWidthMm)} ${ctx.unit}, on ${l.targets.map((c) => componentName(t, c)).join(', ')}`;
      } else if (l.type === 'stitching') {
        const seam = view.seams.find((s) => l.seamIds.includes(s.id));
        if (seam) pos = seamMidpoint(seam.d);
        const color = resolveColor(ctx.snap.doc, l.colorId)?.name ?? '';
        detail = `${STITCH_STYLE_LABELS[l.style]} appearance, thread ${color}. ${l.notes || 'See construction notes.'}`;
      } else if (l.type === 'embellishment') {
        const pts = embellishmentPositions(l, t);
        if (pts.length) pos = pts[0];
        detail = `${embellishmentCount(l, t)} × ${l.kind} ${sizeLabelFor(l.kind, l.diameterMm)} (${l.diameterMm} mm), ${l.finish}, ${l.attachment.replace('-', ' ')}`;
      } else if (l.type === 'hardware') {
        pos = { x: l.transform.x, y: l.transform.y };
        const def = getHardware(l.hardwareId);
        detail = `${def?.name ?? l.hardwareId}, ${l.finish}, ${l.sizeMm} mm. ${def?.structuralNote ?? ''}`;
      } else if (l.type === 'texture') {
        continue;
      } else if (l.type === 'annotation') {
        pos = l.target ?? { x: l.x, y: l.y };
        detail = l.text;
      }
      if (!pos) continue;
      out.push({ n: n++, x: pos.x, y: pos.y, view: viewId, title, detail });
    }
  }
  return out;
}

/* ------------------------------------------------------------------ */
/* Sections                                                            */
/* ------------------------------------------------------------------ */

function cover(ctx: Ctx, mockups: { front?: string; back?: string }) {
  const { doc, snap } = ctx;
  doc.addPage();
  ctx.section = 'Cover';
  const d = snap.doc;
  doc.font('Sans-Bold').fontSize(24).fillColor(INK).text(d.name, LEFT, CONTENT_TOP, { width: 420 });
  let y = doc.y + 4;
  const meta: [string, string][] = [
    ['Style number', d.styleNumber],
    ['Revision', `${snap.label} — ${snap.kind === 'review' ? 'Ready for manufacturer review' : 'DRAFT (incomplete specification)'}`],
    ['Issued', new Date(snap.issuedAt).toISOString().slice(0, 10)],
    ['Garment', `${snap.template.name} (template ${snap.template.id} v${snap.template.version})`],
    ['Construction', `${snap.template.structure.closure} · ${snap.template.structure.features.join(', ')}`],
    ['Season', d.season || '—'],
    ['Collection / set', d.collection || '—'],
    ['Sizes', `${d.sizes.range.join(', ')} (base ${d.sizes.base})`],
    ['Colorways', d.colorways.map((c) => c.name).join(', ')],
  ];
  for (const [k, v] of meta) {
    doc.font('Sans').fontSize(8.5).fillColor(MUTED).text(k, LEFT, y, { width: 100 });
    doc.font('Sans-Bold').fontSize(8.5).fillColor(INK).text(v, LEFT + 104, y, { width: 316 });
    y = Math.max(doc.y, y + 12) + 3;
  }
  if (d.description) {
    doc.font('Sans').fontSize(8.5).fillColor(INK).text(d.description, LEFT, y + 4, { width: 420 });
    y = doc.y + 4;
  }
  if (snap.notes) {
    doc.font('Sans-Bold').fontSize(8.5).text('Revision notes', LEFT, y + 6);
    doc.font('Sans').fontSize(8.5).text(snap.notes, LEFT, doc.y + 2, { width: 420 });
    y = doc.y;
  }
  if (snap.kind === 'draft') {
    const failed = snap.checks.filter((c) => !c.passed && c.level === 'required').length;
    doc.roundedRect(LEFT, y + 10, 420, 34, 4).fillAndStroke('#fff7ed', '#ea580c');
    doc
      .fillColor('#9a3412')
      .font('Sans-Bold')
      .fontSize(9)
      .text(`DRAFT — ${failed} required item(s) still open. See “Open items” at the end of this document.`, LEFT + 8, y + 18, { width: 404 });
  }
  // Overview flats (vector), or rendered mockups alongside when available.
  const boxX = 476;
  const boxW = RIGHT - boxX;
  const half = (CONTENT_BOTTOM - CONTENT_TOP - 20) / 2;
  svgToPdf(ctx, techSvg(ctx, 'front'), boxX, CONTENT_TOP, boxW, half);
  svgToPdf(ctx, techSvg(ctx, 'back'), boxX, CONTENT_TOP + half + 14, boxW, half);
  doc.font('Sans').fontSize(7).fillColor(MUTED).text('Front', boxX, CONTENT_TOP + half - 4, { width: boxW, align: 'center' });
  doc.text('Back', boxX, CONTENT_TOP + 2 * half + 10, { width: boxW, align: 'center' });
  if (mockups.front || mockups.back) {
    const imgs = [mockups.front, mockups.back].filter(Boolean) as string[];
    const w = 200;
    let x = LEFT;
    const top = CONTENT_BOTTOM - 210;
    doc.font('Sans-Bold').fontSize(8).fillColor(INK).text('Appearance preview (ghost mockup)', LEFT, top - 14);
    for (const b64 of imgs) {
      doc.image(Buffer.from(b64, 'base64'), x, top, { fit: [w, 200] });
      x += w + 12;
    }
    doc
      .font('Sans')
      .fontSize(6.5)
      .fillColor(MUTED)
      .text('Mockups are appearance previews. They do not simulate fit or drape and are not color standards.', LEFT, CONTENT_BOTTOM - 8, { width: 420 });
  }
}

function flatsPage(ctx: Ctx, callouts: CalloutItem[]) {
  newPage(ctx, 'Technical flats', 'Numbered callouts refer to the table below. Drawn at nominal scale for size ' + ctx.snap.doc.sizes.base + '; flats are not patterns.');
  const w = CONTENT_W / 2 - 8;
  const h = 250;
  for (const [i, v] of (['front', 'back'] as ViewId[]).entries()) {
    const cs = callouts.filter((c) => c.view === v);
    svgToPdf(ctx, techSvg(ctx, v, { callouts: cs }), LEFT + i * (w + 16), ctx.y, w, h);
    ctx.doc.font('Sans-Bold').fontSize(8).fillColor(MUTED).text(v === 'front' ? 'FRONT' : 'BACK', LEFT + i * (w + 16), ctx.y + h + 2, { width: w, align: 'center' });
  }
  ctx.y += h + 18;
  if (callouts.length === 0) {
    para(ctx, 'No decorations, stitching, embellishments, or hardware are specified on this style.', { color: MUTED });
    return;
  }
  table(
    ctx,
    [
      { header: '#', width: 22, align: 'center' },
      { header: 'View', width: 40 },
      { header: 'Item', width: 150 },
      { header: 'Specification', width: 508 },
    ],
    callouts.map((c) => [{ text: String(c.n), bold: true }, c.view, c.title, c.detail]),
  );
}

function colorwaysPage(ctx: Ctx) {
  const { snap } = ctx;
  const d = snap.doc;
  newPage(ctx, 'Colorways & color references', 'Screen colors are display approximations only. Physical color must be approved against the referenced standard or a lab dip. No color-standard codes are generated by this application.');
  const comps = snap.template.components;
  const cws = d.colorways;
  const cwW = Math.min(150, (CONTENT_W - 150) / cws.length);
  table(
    ctx,
    [{ header: 'Component', width: 150 }, ...cws.map((c) => ({ header: `${c.name}${c.code ? ` (${c.code})` : ''}`, width: cwW }))],
    comps.map((comp) => [
      comp.name,
      ...cws.map((cw) => {
        const views = snap.template.views.filter((v) => v.panels.some((p) => p.componentId === comp.id));
        const fills = views.map((v) => ({ v: v.id, f: resolveFill(d, comp.id, v.id, cw.id) }));
        const f = fills[0]?.f;
        const differs = fills.some((x) => x.f.color?.id !== f?.color?.id);
        const text = differs
          ? fills.map((x) => `${x.v}: ${x.f.color?.name ?? '—'}`).join('; ')
          : `${f?.color?.name ?? '—'}${f?.color?.standard?.code ? ` · ${f.color.standard.system} ${f.color.standard.code}` : ''}\n${f?.material?.name ?? 'No material'}`;
        return { text, swatch: f?.hex };
      }),
    ]),
  );
  heading(ctx, 'Palette');
  table(
    ctx,
    [
      { header: 'Color', width: 170 },
      { header: 'Screen value', width: 80 },
      { header: 'Color standard (user supplied)', width: 200 },
      { header: 'Approval status', width: 110 },
    ],
    d.colors.map((c) => [
      { text: c.name, swatch: c.hex },
      c.hex.toUpperCase(),
      c.standard?.code ? `${c.standard.system} ${c.standard.code}` : 'Not supplied',
      c.approval.replace('-', ' '),
    ]),
  );
  const subs = cws.filter((c) => Object.keys(c.colorSubs).length || Object.keys(c.materialSubs).length);
  if (subs.length) {
    heading(ctx, 'Colorway substitutions (relative to the base design)');
    const rows: Cell[][] = [];
    for (const cw of subs) {
      for (const [from, to] of Object.entries(cw.colorSubs)) {
        rows.push([cw.name, 'Color', d.colors.find((c) => c.id === from)?.name ?? from, { text: d.colors.find((c) => c.id === to)?.name ?? to, swatch: d.colors.find((c) => c.id === to)?.hex }]);
      }
      for (const [from, to] of Object.entries(cw.materialSubs)) {
        rows.push([cw.name, 'Material', d.materials.find((m) => m.id === from)?.name ?? from, d.materials.find((m) => m.id === to)?.name ?? to]);
      }
    }
    table(ctx, [{ header: 'Colorway', width: 140 }, { header: 'Type', width: 70 }, { header: 'Base', width: 200 }, { header: 'Substitute', width: 200 }], rows);
  }
}

function materialsPage(ctx: Ctx) {
  const { snap } = ctx;
  const d = snap.doc;
  newPage(ctx, 'Materials & bill of materials', 'Fabric consumption is never inferred from the drawing; quantities shown are as entered. Counted quantities come directly from placed items.');
  heading(ctx, 'Materials');
  const usedOn = new Map<string, string[]>();
  for (const row of snap.bom) if (row.materialId) usedOn.set(row.materialId, row.componentIds.map((c) => componentName(snap.template, c)));
  table(
    ctx,
    [
      { header: 'Material', width: 130 },
      { header: 'Type', width: 50 },
      { header: 'Composition', width: 110 },
      { header: 'Weight', width: 60 },
      { header: 'Finish', width: 90 },
      { header: 'Supplier / ref', width: 110 },
      { header: 'Used on', width: 100 },
      { header: 'Notes', width: 120 },
    ],
    d.materials.map((m) => [
      { text: m.name, bold: true },
      m.kind,
      m.composition || { text: 'MISSING', color: '#b91c1c' },
      m.weight
        ? `${m.weight.value} ${m.weight.unit === 'gsm' ? 'g/m²' : 'oz/yd²'}`
        : m.kind === 'fabric' || m.kind === 'rib'
          ? { text: 'MISSING', color: '#b91c1c' }
          : 'n/a',
      m.finish || '—',
      [m.supplier, m.supplierRef].filter(Boolean).join(' / ') || '—',
      (usedOn.get(m.id) ?? []).join(', ') || '—',
      m.notes || '',
    ]),
  );
  heading(ctx, 'Bill of materials');
  table(
    ctx,
    [
      { header: 'Category', width: 82 },
      { header: 'Component', width: 116 },
      { header: 'Material / trim', width: 136 },
      { header: 'Description', width: 110 },
      { header: 'Qty', width: 40, align: 'right' },
      { header: 'Unit', width: 36 },
      { header: 'Qty type', width: 56 },
      { header: 'Colorways', width: 70 },
      { header: 'Supplier ref', width: 70 },
      { header: 'Notes', width: 90 },
    ],
    snap.bom.map((b) => [
      b.category,
      b.component,
      { text: b.materialName, bold: true },
      b.description,
      b.quantity === null ? '—' : String(b.quantity),
      b.unit,
      b.quantityType === 'missing' ? { text: 'not entered', color: '#b91c1c' } : b.quantityType === 'counted' ? { text: 'counted', color: ACCENT } : b.quantityType,
      colorwayNames(d, b.colorwayIds),
      b.supplierRef || '—',
      b.notes,
    ]),
  );
}

function artworkThumb(ctx: Ctx, l: ArtworkLayer, x: number, y: number, w: number, h: number) {
  const asset = ctx.snap.doc.assets.find((a) => a.id === l.assetId);
  if (!asset) return;
  const draw = ctx.resolve(asset.id);
  let inner = '';
  if (draw.kind === 'href') inner = `<image href="${draw.href}" x="0" y="0" width="${asset.width}" height="${asset.height}"/>`;
  else if (draw.kind === 'inline-svg') inner = `<svg x="0" y="0" width="${asset.width}" height="${asset.height}" viewBox="${draw.viewBox}">${draw.markup}</svg>`;
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${asset.width} ${asset.height}"><rect width="100%" height="100%" fill="#f3f4f6"/>${inner}</svg>`;
  ctx.doc.rect(x, y, w, h).lineWidth(0.5).strokeColor(RULE).stroke();
  svgToPdf(ctx, svg, x + 4, y + 4, w - 8, h - 8);
}

function artworkPage(ctx: Ctx) {
  const { snap } = ctx;
  const d = snap.doc;
  const t = snap.template;
  newPage(ctx, 'Artwork, placement & application', 'Placement offsets are measured from the named reference point on the finished garment. Appearance previews are not machine files (no embroidery DST or separations are produced).');
  const artworks = d.layers.filter((l): l is ArtworkLayer => l.type === 'artwork' && l.visible);
  if (!artworks.length) para(ctx, 'No artwork placed.', { color: MUTED });
  for (const l of artworks) {
    const blockH = 120;
    ensure(ctx, blockH);
    const y0 = ctx.y;
    artworkThumb(ctx, l, LEFT, y0, 110, 110);
    const asset = d.assets.find((a) => a.id === l.assetId);
    const anchor = findAnchor(t, l.placement.anchorId);
    const rows: [string, string][] = [
      ['Artwork', `${l.name}${l.decoration.artworkCode ? ` · ID ${l.decoration.artworkCode}` : ''}`],
      ['Source file', `${asset?.filename ?? 'MISSING'} (${asset?.kind.toUpperCase() ?? '-'}, kept as uploaded)`],
      ['Method', DECORATION_METHOD_LABELS[l.decoration.method]],
      ['Finished size', `${len(ctx, l.placement.widthMm)} W × ${len(ctx, l.placement.heightMm)} H ${ctx.unit}${l.placement.source === 'entered' ? '' : '  — VISUAL ESTIMATE, not confirmed'}`],
      ['Placement', placementText(ctx, l)],
      ['Reference', anchor ? `${anchor.label} — ${anchor.description}` : 'None'],
      ['Rotation', `${Math.round(l.transform.rotation * 10) / 10}°`],
      ['Tolerance', l.placement.toleranceMm !== null ? `± ${len(ctx, l.placement.toleranceMm)} ${ctx.unit}` : 'Not specified'],
      ['View / panels', `${l.view} · ${l.targets.map((c) => componentName(t, c)).join(', ')}${l.clipToTargets ? ' (clipped to these panels)' : ' (not clipped)'}`],
      ['Colors', l.decoration.colorIds.map((c) => d.colors.find((x) => x.id === c)?.name ?? c).join(', ') || '—'],
      ['Notes', l.decoration.notes || '—'],
    ];
    let yy = y0;
    for (const [k, v] of rows) {
      ctx.doc.font('Sans').fontSize(7.5).fillColor(MUTED).text(k, LEFT + 120, yy, { width: 80 });
      ctx.doc.font(k === 'Finished size' ? 'Sans-Bold' : 'Sans').fontSize(7.5).fillColor(INK).text(v, LEFT + 202, yy, { width: CONTENT_W - 202 });
      yy = Math.max(ctx.doc.y, yy + 9) + 1;
    }
    ctx.y = Math.max(y0 + 116, yy) + 8;
    ctx.doc.moveTo(LEFT, ctx.y - 4).lineTo(RIGHT, ctx.y - 4).lineWidth(0.4).strokeColor(RULE).stroke();
  }
  const patterns = d.layers.filter((l) => l.type === 'pattern' && l.visible);
  if (patterns.length) {
    heading(ctx, 'Patterns');
    table(
      ctx,
      [{ header: 'Pattern', width: 140 }, { header: 'Method', width: 90 }, { header: 'Repeat width', width: 80 }, { header: 'Rotation / offset', width: 120 }, { header: 'Panels', width: 160 }, { header: 'Erased areas', width: 70 }, { header: 'Notes', width: 120 }],
      patterns.map((l) => {
        if (l.type !== 'pattern') return [];
        return [
          l.name,
          DECORATION_METHOD_LABELS[l.method],
          `${len(ctx, l.tileWidthMm)} ${ctx.unit}`,
          `${l.rotation}° · ${len(ctx, l.offsetXmm)}, ${len(ctx, l.offsetYmm)} ${ctx.unit}`,
          l.targets.map((c) => componentName(t, c)).join(', '),
          l.mask.length ? `${l.mask.length} edit(s)` : 'None',
          l.notes,
        ];
      }),
    );
  }
  const embs = d.layers.filter((l) => (l.type === 'embellishment' || l.type === 'hardware') && l.visible);
  if (embs.length) {
    heading(ctx, 'Embellishments & hardware');
    table(
      ctx,
      [{ header: 'Item', width: 140 }, { header: 'Type', width: 120 }, { header: 'Size', width: 60 }, { header: 'Finish', width: 80 }, { header: 'Qty', width: 40, align: 'right' }, { header: 'Attachment / note', width: 280 }],
      embs.map((l) => {
        if (l.type === 'embellishment') {
          return [l.name, `${l.kind} ${sizeLabelFor(l.kind, l.diameterMm)}`, `${l.diameterMm} mm`, l.finish, { text: String(embellishmentCount(l, t)), color: ACCENT }, `${l.attachment.replace('-', ' ')} · counted from placements. ${l.notes}`];
        }
        if (l.type === 'hardware') {
          const def = getHardware(l.hardwareId);
          return [l.name, def?.name ?? l.hardwareId, `${l.sizeMm} mm`, l.finish, '1', `${def?.structuralNote ?? ''} ${l.notes}`];
        }
        return [];
      }),
    );
  }
}

function measurementPages(ctx: Ctx) {
  const { snap } = ctx;
  const d = snap.doc;
  const codes: Record<string, string> = {};
  for (const p of d.measurements) if (p.templatePomId) codes[p.templatePomId] = p.code;
  newPage(ctx, 'Measurement diagrams', 'Points of measure (POM) for the garment laid flat. Diagrams show where to measure; they are not drawn to the size table values.');
  const w = CONTENT_W / 2 - 8;
  const h = 300;
  for (const [i, v] of (['front', 'back'] as ViewId[]).entries()) {
    svgToPdf(ctx, techSvg(ctx, v, { fills: false, decorations: false, stitching: false, embellishments: false, hardware: false, annotations: false, textures: false, measurements: { pomCodes: codes } }), LEFT + i * (w + 16), ctx.y, w, h);
    ctx.doc.font('Sans-Bold').fontSize(8).fillColor(MUTED).text(v.toUpperCase(), LEFT + i * (w + 16), ctx.y + h + 2, { width: w, align: 'center' });
  }
  ctx.y += h + 20;
  table(
    ctx,
    [{ header: 'POM', width: 36 }, { header: 'Description', width: 170 }, { header: 'How to measure', width: 514 }],
    d.measurements.map((p) => [{ text: p.code, bold: true }, p.label, p.howToMeasure]),
  );

  newPage(
    ctx,
    `Size specification (${ctx.unit === 'in' ? 'inches' : 'centimetres'})`,
    `Base size ${d.sizes.base}. * = template default value, † = POM not yet confirmed. Values are as entered — no grading rules are applied by this application. V1 does not simulate fit or drape.`,
  );
  const sizes = d.sizes.range;
  const sizeW = Math.max(42, Math.min(60, (CONTENT_W - 36 - 190 - 90 - 60) / sizes.length));
  table(
    ctx,
    [
      { header: 'POM', width: 36 },
      { header: 'Description', width: 190 },
      { header: 'Tol −', width: 45, align: 'right' },
      { header: 'Tol +', width: 45, align: 'right' },
      ...sizes.map((s) => ({ header: s === d.sizes.base ? `${s} (base)` : s, width: sizeW, align: 'right' as const })),
      { header: 'Status', width: 60 },
    ],
    d.measurements.map((p) => [
      { text: `${p.code}${p.confirmed ? '' : ' †'}`, bold: true },
      p.label,
      len(ctx, p.tolMinusMm),
      len(ctx, p.tolPlusMm),
      ...sizes.map((s) => {
        const v = p.values[s];
        if (!v || v.mm === null) return { text: '—', color: '#b91c1c' };
        return { text: `${len(ctx, v.mm)}${v.source === 'template-default' ? '*' : ''}`, bold: s === d.sizes.base };
      }),
      p.confirmed ? 'Confirmed' : { text: 'Unconfirmed', color: '#b45309' },
    ]),
    { fontSize: 7.5 },
  );
}

function constructionPage(ctx: Ctx) {
  const { snap } = ctx;
  const d = snap.doc;
  const t = snap.template;
  newPage(ctx, 'Construction notes & details');
  if (d.constructionNotes.length) {
    for (const n of d.constructionNotes) {
      heading(ctx, n.title);
      const refs = [...n.componentIds.map((c) => componentName(t, c)), ...n.seamIds.map((s) => t.views.flatMap((v) => v.seams).find((x) => x.id === s)?.name ?? s)];
      if (refs.length) para(ctx, `Applies to: ${refs.join(', ')}`, { color: MUTED, size: 7.5 });
      para(ctx, n.text || '—');
    }
  } else {
    para(ctx, 'No construction notes entered.', { color: MUTED });
  }
  const stitches = d.layers.filter((l): l is Extract<Layer, { type: 'stitching' }> => l.type === 'stitching' && l.visible);
  heading(ctx, 'Stitching');
  para(ctx, 'Dashes on the flats are illustrative. Stitch type, SPI, and seam construction are defined only by the notes below.', { color: MUTED, size: 7.5 });
  if (stitches.length) {
    const allSeams = t.views.flatMap((v) => v.seams);
    table(
      ctx,
      [{ header: 'Layer', width: 120 }, { header: 'Seams', width: 220 }, { header: 'Appearance', width: 100 }, { header: 'Thread color', width: 100 }, { header: 'Manufacturing notes', width: 180 }],
      stitches.map((l) => [
        l.name,
        [...new Set(l.seamIds.map((s) => allSeams.find((x) => x.id === s)?.name ?? s))].join(', '),
        STITCH_STYLE_LABELS[l.style],
        { text: resolveColor(d, l.colorId)?.name ?? '—', swatch: resolveColor(d, l.colorId)?.hex },
        l.notes || { text: 'Not specified', color: '#b45309' },
      ]),
    );
  } else {
    para(ctx, 'No custom stitching specified; template default seams shown on flats.', { color: MUTED });
  }
  // Detail views: zoomed crops around referenced seams (or template hems by default).
  const seamIds = [...new Set([...stitches.flatMap((s) => s.seamIds), ...d.constructionNotes.flatMap((n) => n.seamIds)])];
  const candidates: { view: ViewId; id: string; name: string; d: string }[] = [];
  for (const v of t.views) for (const s of v.seams) if (seamIds.includes(s.id) && !candidates.some((c) => c.id === s.id)) candidates.push({ view: v.id, id: s.id, name: s.name, d: s.d });
  if (!candidates.length) {
    const front = getView(t, 'front');
    for (const s of front.seams.filter((x) => x.defaultStyle === 'coverstitch').slice(0, 3)) candidates.push({ view: 'front', id: s.id, name: s.name, d: s.d });
  }
  const details = candidates.slice(0, 3);
  if (details.length) {
    const boxW = (CONTENT_W - 2 * 12) / 3;
    const boxH = 150;
    ensure(ctx, boxH + 30);
    heading(ctx, 'Detail views');
    details.forEach((c, i) => {
      // Close-up: frame the seam at the box's aspect ratio, capped so long seams (hems) still read as a detail.
      const b = pathBBox(c.d);
      const aspect = boxW / boxH;
      const mid = seamMidpoint(c.d);
      let w = Math.min(Math.max(b.width, b.height * aspect) + 60, 280);
      w = Math.max(w, 140);
      const h = w / aspect;
      const vb: [number, number, number, number] = [mid.x - w / 2, mid.y - h / 2, w, h];
      const x = LEFT + i * (boxW + 12);
      ctx.doc.rect(x, ctx.y, boxW, boxH).lineWidth(0.5).strokeColor(RULE).stroke();
      svgToPdf(ctx, techSvg(ctx, c.view, { viewBox: vb, decorations: false, embellishments: false, hardware: false, annotations: false }), x + 2, ctx.y + 2, boxW - 4, boxH - 4);
      ctx.doc.font('Sans').fontSize(7.5).fillColor(INK).text(`${c.name} (${c.view})`, x, ctx.y + boxH + 3, { width: boxW, align: 'center' });
    });
    ctx.y += boxH + 18;
  }
  heading(ctx, 'Garment structure');
  para(
    ctx,
    `${t.name}: ${t.structure.closure}; ${t.structure.features.join(', ')}. Decorative items (including decorative zippers or hardware) do not change this construction unless a separate garment template is used.`,
  );
}

function labelsPage(ctx: Ctx) {
  const d = ctx.snap.doc;
  if (!d.labels.length) return;
  newPage(ctx, 'Labels & packaging');
  table(
    ctx,
    [{ header: 'Item', width: 100 }, { header: 'Description', width: 220 }, { header: 'Placement', width: 150 }, { header: 'Material', width: 110 }, { header: 'Artwork', width: 70 }, { header: 'Notes', width: 120 }],
    d.labels.map((l) => [
      { text: l.type.replace(/-/g, ' '), bold: true },
      l.description,
      l.placement || '—',
      d.materials.find((m) => m.id === l.materialId)?.name ?? '—',
      l.assetId ? d.assets.find((a) => a.id === l.assetId)?.filename ?? 'MISSING' : '—',
      l.notes,
    ]),
  );
}

function historyPage(ctx: Ctx) {
  const s = ctx.snap;
  newPage(ctx, 'Revision history');
  table(
    ctx,
    [{ header: 'Revision', width: 70 }, { header: 'Date', width: 90 }, { header: 'Type', width: 160 }, { header: 'Notes', width: 400 }],
    [...s.history].reverse().map((h) => [{ text: h.label, bold: h.number === s.number }, h.createdAt.slice(0, 10), h.kind === 'review' ? 'Ready for manufacturer review' : 'Draft', h.notes || '—']),
  );
  para(ctx, 'This document is a specification issued for review and sampling. It is not a manufacturer approval and does not replace physical sample approval.', { color: MUTED });
}

function checksPage(ctx: Ctx) {
  const s = ctx.snap;
  const req = s.checks.filter((c) => !c.passed && c.level === 'required');
  const rec = s.checks.filter((c) => !c.passed && c.level === 'recommended');
  newPage(ctx, s.kind === 'draft' ? 'Open items' : 'Specification checks', s.kind === 'draft' ? 'This draft was exported with missing information. Required items must be completed before a manufacturer-review export.' : 'All required checks passed at the time of issue.');
  if (req.length) {
    heading(ctx, `Required (${req.length})`);
    table(ctx, [{ header: 'Section', width: 90 }, { header: 'Item', width: 630 }], req.map((c) => [c.section, { text: c.message, color: '#b91c1c' }]));
  }
  heading(ctx, `Recommended (${rec.length})`);
  if (rec.length) table(ctx, [{ header: 'Section', width: 90 }, { header: 'Item', width: 630 }], rec.map((c) => [c.section, c.message]));
  else para(ctx, 'None.', { color: MUTED });
}

function decorateAllPages(ctx: Ctx) {
  const { doc, snap } = ctx;
  const range = doc.bufferedPageRange();
  const statusText = snap.kind === 'review' ? 'For manufacturer review' : 'DRAFT';
  for (let i = range.start; i < range.start + range.count; i++) {
    doc.switchToPage(i);
    // Header
    doc.font('Sans-Bold').fontSize(9).fillColor(INK).text(snap.doc.name, LEFT, 24, { width: 400, lineBreak: false, ellipsis: true });
    doc.font('Sans').fontSize(7.5).fillColor(MUTED).text(`Style ${snap.doc.styleNumber} · ${snap.template.name}`, LEFT, 37, { width: 400, lineBreak: false });
    doc.font('Sans-Bold').fontSize(9).fillColor(snap.kind === 'draft' ? '#c2410c' : ACCENT).text(`Rev ${snap.label} · ${statusText}`, RIGHT - 300, 24, { width: 300, align: 'right', lineBreak: false });
    doc.font('Sans').fontSize(7.5).fillColor(MUTED).text(`Issued ${snap.issuedAt.slice(0, 10)}`, RIGHT - 300, 37, { width: 300, align: 'right', lineBreak: false });
    doc.moveTo(LEFT, 52).lineTo(RIGHT, 52).lineWidth(0.8).strokeColor(INK).stroke();
    // Footer
    doc.moveTo(LEFT, PAGE_H - 34).lineTo(RIGHT, PAGE_H - 34).lineWidth(0.4).strokeColor(RULE).stroke();
    doc
      .font('Sans')
      .fontSize(6.5)
      .fillColor(MUTED)
      .text('Specification for review — not a manufacturer approval. Sample approval required. Screen colors are not color standards.', LEFT, PAGE_H - 28, { width: 480, lineBreak: false });
    doc
      .font('Sans-Bold')
      .fontSize(7.5)
      .fillColor(INK)
      .text(`${snap.doc.styleNumber} · Rev ${snap.label} · Page ${i - range.start + 1} of ${range.count}`, RIGHT - 240, PAGE_H - 28, { width: 240, align: 'right', lineBreak: false });
  }
}

/** Render the complete tech pack for a revision snapshot. Pure function of the snapshot + immutable blobs. */
export async function renderTechPackPdf(snap: RevisionSnapshot, storage: StorageAdapter): Promise<Buffer> {
  // Preload every asset (sync rendering needs them in memory).
  const draws = new Map<string, AssetDraw>();
  for (const a of snap.doc.assets) {
    if (!(await storage.exists(a.sha256))) {
      draws.set(a.id, { kind: 'missing' });
      continue;
    }
    const buf = await storage.get(a.sha256);
    if (a.kind === 'png') draws.set(a.id, { kind: 'href', href: `data:image/png;base64,${buf.toString('base64')}` });
    else {
      const svg = buf.toString('utf8');
      const vb = /viewBox="([^"]+)"/.exec(svg)?.[1] ?? `0 0 ${a.width} ${a.height}`;
      draws.set(a.id, { kind: 'inline-svg', markup: svgInner(svg), viewBox: vb });
    }
  }
  const mockups: { front?: string; back?: string } = {};
  for (const k of ['front', 'back'] as const) {
    const sha = snap.mockups[k];
    if (sha && (await storage.exists(sha))) mockups[k] = (await storage.get(sha)).toString('base64');
  }

  const doc = new PDFDocument({
    size: 'LETTER',
    layout: 'landscape',
    margins: { top: 10, bottom: 10, left: LEFT, right: 36 },
    bufferPages: true,
    autoFirstPage: false,
    info: {
      Title: `${snap.doc.name} — ${snap.doc.styleNumber} — Rev ${snap.label}`,
      Subject: 'Apparel technical specification (for review)',
      Creator: 'Apparel Studio',
      CreationDate: new Date(snap.issuedAt),
    },
  });
  doc.registerFont('Sans', path.join(FONT_DIR, 'DejaVuSans.ttf'));
  doc.registerFont('Sans-Bold', path.join(FONT_DIR, 'DejaVuSans-Bold.ttf'));
  const chunks: Buffer[] = [];
  doc.on('data', (c: Buffer) => chunks.push(c));
  const done = new Promise<Buffer>((resolve, reject) => {
    doc.on('end', () => resolve(Buffer.concat(chunks)));
    doc.on('error', reject);
  });

  const ctx: Ctx = {
    doc,
    y: CONTENT_TOP,
    snap,
    unit: snap.doc.displayUnit,
    resolve: (id) => draws.get(id) ?? { kind: 'missing' },
    section: '',
  };
  const callouts = buildCallouts(ctx);
  cover(ctx, mockups);
  flatsPage(ctx, callouts);
  colorwaysPage(ctx);
  materialsPage(ctx);
  artworkPage(ctx);
  measurementPages(ctx);
  constructionPage(ctx);
  labelsPage(ctx);
  historyPage(ctx);
  checksPage(ctx);
  decorateAllPages(ctx);
  doc.end();
  return done;
}

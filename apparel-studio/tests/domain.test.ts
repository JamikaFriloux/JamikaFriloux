import { describe, expect, it } from 'vitest';
import { requireTemplate } from '../src/shared/templates';
import { createProjectDoc } from '../src/shared/domain/factory';
import { projectDocSchema, type AssetRef, type ProjectDoc, type PanelFillLayer } from '../src/shared/schema/project';
import { resolveFill } from '../src/shared/domain/design';
import { makeArtworkLayer, makeEmbellishmentLayer, makeViewOverride, makeHardwareLayer } from '../src/shared/domain/layers';
import { applyCanvasTransform, applyEnteredPlacement } from '../src/shared/domain/placement';
import { computeBom, embellishmentCount } from '../src/shared/domain/bom';
import { validateProject } from '../src/shared/domain/validation';
import { newId } from '../src/shared/domain/ids';

const tee = requireTemplate('tshirt-boxy', 1);
const asset: AssetRef = { id: 'ast_logo', kind: 'svg', role: 'artwork', filename: 'logo.svg', sha256: 'a'.repeat(64), width: 400, height: 200, bytes: 10 };

function fresh(): ProjectDoc {
  return createProjectDoc(tee, { name: 'Test tee', styleNumber: 'T-1' });
}
const fillOf = (doc: ProjectDoc, comp: string) => doc.layers.find((l): l is PanelFillLayer => l.type === 'panelFill' && l.targets[0] === comp && l.view === 'all')!;

describe('project factory', () => {
  it('produces a schema-valid document with one fill per component', () => {
    const doc = fresh();
    expect(() => projectDocSchema.parse(doc)).not.toThrow();
    expect(doc.layers.filter((l) => l.type === 'panelFill')).toHaveLength(tee.components.length);
  });

  it('marks template measurement values as unconfirmed defaults and never invents other sizes', () => {
    const doc = fresh();
    const a = doc.measurements.find((p) => p.code === 'A')!;
    expect(a.confirmed).toBe(false);
    expect(a.values.M).toEqual({ mm: 700, source: 'template-default' });
    for (const s of ['XS', 'S', 'L', 'XL']) expect(a.values[s].mm).toBeNull();
  });
});

describe('panel colours', () => {
  it('recolouring a sleeve does not recolour the body or the other sleeve', () => {
    const doc = fresh();
    const red = { id: newId('col'), name: 'Red', hex: '#ff0000', standard: null, approval: 'not-submitted' as const };
    doc.colors.push(red);
    fillOf(doc, 'sleeve_left').colorId = red.id;
    for (const v of ['front', 'back'] as const) {
      expect(resolveFill(doc, 'sleeve_left', v).hex).toBe('#ff0000');
      expect(resolveFill(doc, 'sleeve_right', v).hex).not.toBe('#ff0000');
      expect(resolveFill(doc, 'body_front', 'front').hex).not.toBe('#ff0000');
      expect(resolveFill(doc, 'body_back', v).hex).not.toBe('#ff0000');
    }
  });

  it('shared components stay linked across views; an explicit override changes one view only', () => {
    const doc = fresh();
    const blue = { id: newId('col'), name: 'Blue', hex: '#0000ff', standard: null, approval: 'not-submitted' as const };
    const green = { id: newId('col'), name: 'Green', hex: '#00ff00', standard: null, approval: 'not-submitted' as const };
    doc.colors.push(blue, green);
    const base = fillOf(doc, 'neck_rib');
    base.colorId = blue.id;
    expect(resolveFill(doc, 'neck_rib', 'front').hex).toBe('#0000ff');
    expect(resolveFill(doc, 'neck_rib', 'back').hex).toBe('#0000ff');
    const override = makeViewOverride(doc, base, 'back');
    override.colorId = green.id;
    doc.layers.push(override);
    expect(resolveFill(doc, 'neck_rib', 'front').hex).toBe('#0000ff');
    expect(resolveFill(doc, 'neck_rib', 'back').hex).toBe('#00ff00');
    expect(resolveFill(doc, 'neck_rib', 'back').isViewOverride).toBe(true);
    // Changing the shared assignment still flows to the view without an override.
    base.colorId = green.id;
    expect(resolveFill(doc, 'neck_rib', 'front').hex).toBe('#00ff00');
  });
});

describe('artwork placement', () => {
  it('entering manufacturing dimensions updates the placement spec and the canvas', () => {
    let l = makeArtworkLayer(tee, asset, { viewId: 'front', anchorId: 'center_chest', widthMm: 200 });
    expect(l.placement.source).toBe('canvas-estimate');
    l = applyEnteredPlacement(tee, l, { widthMm: 280 });
    expect(l.placement.widthMm).toBe(280);
    expect(l.placement.heightMm).toBe(140); // aspect preserved
    expect(l.placement.source).toBe('entered');
    expect(l.transform.width).toBe(280);
    l = applyEnteredPlacement(tee, l, { offsetYmm: 30 });
    // Top-center reference: top edge 30 mm below the anchor.
    expect(l.transform.y - l.transform.height / 2).toBeCloseTo(250 + 30);
  });

  it('moving on the canvas re-estimates offsets and marks them visual', () => {
    let l = makeArtworkLayer(tee, asset, { viewId: 'front', anchorId: 'center_chest', widthMm: 200 });
    l = applyEnteredPlacement(tee, l, { widthMm: 200 });
    l = applyCanvasTransform(tee, l, { ...l.transform, x: l.transform.x + 40 });
    expect(l.placement.offsetXmm).toBe(40);
    expect(l.placement.source).toBe('canvas-estimate');
    // Rotation alone does not change the placement spec.
    const before = l.placement;
    l = applyCanvasTransform(tee, l, { ...l.transform, rotation: 15 });
    expect(l.placement).toEqual(before);
  });
});

describe('BOM', () => {
  it('linked material changes update the BOM reference', () => {
    const doc = fresh();
    const alt = { ...doc.materials[0], id: newId('mat'), name: 'Mesh' };
    doc.materials.push(alt);
    fillOf(doc, 'sleeve_left').materialId = alt.id;
    fillOf(doc, 'sleeve_right').materialId = alt.id;
    const rows = computeBom(doc, tee);
    const mesh = rows.find((r) => r.materialId === alt.id)!;
    expect(mesh.componentIds.sort()).toEqual(['sleeve_left', 'sleeve_right']);
    const shell = rows.find((r) => r.materialId === doc.materials[0].id)!;
    expect(shell.componentIds).not.toContain('sleeve_left');
    expect(mesh.quantityType).toBe('missing'); // never inferred from drawing
  });

  it('embellishment counts match placements (points + spaced path)', () => {
    const doc = fresh();
    const e = makeEmbellishmentLayer('rhinestone', 'front', ['body_front']);
    e.points = [{ x: 500, y: 300 }, { x: 510, y: 300 }];
    e.paths = [{ id: 'p1', points: [{ x: 400, y: 400 }, { x: 480, y: 400 }], spacingMm: 8 }]; // 80 mm / 8 = 10 gaps → 11
    doc.layers.push(e);
    expect(embellishmentCount(e, tee)).toBe(13);
    const row = computeBom(doc, tee).find((r) => r.source === 'embellishment')!;
    expect(row.quantity).toBe(13);
    expect(row.quantityType).toBe('counted');
    e.points.pop();
    expect(computeBom(doc, tee).find((r) => r.source === 'embellishment')!.quantity).toBe(12);
  });

  it('hardware is counted and marked decorative', () => {
    const doc = fresh();
    doc.layers.push(makeHardwareLayer(tee, 'zipper-decorative', 'front', 500, 400, ['body_front']));
    const row = computeBom(doc, tee).find((r) => r.source === 'hardware')!;
    expect(row.quantity).toBe(1);
    expect(row.description).toMatch(/decorative/);
    expect(tee.structure.closure).toBe('pullover');
  });
});

describe('export validation', () => {
  it('distinguishes required from recommended and gates only the review export', () => {
    const doc = fresh();
    const v = validateProject(doc, tee);
    expect(v.canExport('draft')).toBe(true);
    expect(v.canExport('review')).toBe(false);
    expect(v.failedRequired.some((c) => c.id.startsWith('measurements.confirmed'))).toBe(true);
    expect(v.failedRequired.some((c) => c.id.startsWith('materials.composition'))).toBe(true);
    // Unused optional sections (labels) do not create required failures.
    expect(v.checks.some((c) => c.section === 'labels')).toBe(false);
    // Construction notes are recommended only.
    expect(v.failedRecommended.some((c) => c.id === 'construction.notes')).toBe(true);
  });

  it('artwork with only canvas-estimated size blocks review', () => {
    const doc = fresh();
    doc.assets.push(asset);
    doc.layers.push(makeArtworkLayer(tee, asset, { viewId: 'front', anchorId: 'center_chest' }));
    const v = validateProject(doc, tee);
    expect(v.failedRequired.some((c) => c.id.startsWith('artwork.dimensions'))).toBe(true);
  });
});

describe('colorways', () => {
  it('substitutes colors and materials explicitly per colorway and reflects them in the BOM', () => {
    const doc = fresh();
    const white = doc.colors[0];
    const black = { id: newId('col'), name: 'Black', hex: '#111111', standard: null, approval: 'not-submitted' as const };
    doc.colors.push(black);
    const recycled = { ...doc.materials[0], id: newId('mat'), name: 'Recycled jersey' };
    doc.materials.push(recycled);
    doc.colorways.push({ id: 'cw_black', name: 'Black', code: 'BLK', colorSubs: { [white.id]: black.id }, materialSubs: { [doc.materials[0].id]: recycled.id }, notes: '' });
    const base = doc.colorways[0].id;
    expect(resolveFill(doc, 'body_front', 'front', base).hex).toBe(white.hex);
    expect(resolveFill(doc, 'body_front', 'front', 'cw_black').hex).toBe('#111111');
    expect(resolveFill(doc, 'body_front', 'front', 'cw_black').material?.name).toBe('Recycled jersey');
    // The base design itself is unchanged by the colorway.
    expect(fillOf(doc, 'body_front').colorId).toBe(white.id);
    const rows = computeBom(doc, tee);
    expect(rows.find((r) => r.materialId === recycled.id)!.colorwayIds).toEqual(['cw_black']);
    expect(rows.find((r) => r.materialId === doc.materials[0].id)!.colorwayIds).toEqual([base]);
  });
});

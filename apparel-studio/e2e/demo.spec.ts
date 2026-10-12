/**
 * Full V1 demonstration, run through the real UI. Saves screenshots and every exported file to
 * `verification/` (override with VERIFY_OUT) together with `results.json` describing each check.
 * Run: npx playwright test e2e/demo.spec.ts
 */
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { expect, test, type Page, type APIRequestContext } from '@playwright/test';
import { API, clickSvg, createStyle, getProject, svgToScreen, waitSaved } from './fixtures';
import { DEMO_LOGO_SVG, DEMO_TILE_SVG, DEMO_BACK_SVG } from '../src/server/demo/assets';
import type { BomRow } from '../src/shared/domain/bom';
import type { ProjectDoc, RevisionSummary } from '../src/shared/schema/project';

const OUT = path.resolve(process.env.VERIFY_OUT ?? 'verification');
const results: { garment: string; check: string; passed: boolean; detail: string }[] = [];

test.describe.configure({ mode: 'serial' });
test.setTimeout(240_000);

function dir(garment: string) {
  const d = path.join(OUT, garment);
  fs.mkdirSync(d, { recursive: true });
  return d;
}
async function shot(page: Page, garment: string, name: string, fullPage = false) {
  await page.waitForTimeout(250);
  await page.screenshot({ path: path.join(dir(garment), `${name}.png`), fullPage });
}
function record(garment: string, check: string, passed: boolean, detail: string) {
  results.push({ garment, check, passed, detail });
  expect(passed, `${garment}: ${check} — ${detail}`).toBe(true);
}
async function addColor(page: Page, name: string, hex: string) {
  await page.getByRole('button', { name: 'New' }).first().click();
  await page.getByTestId('new-color-hex').fill(hex);
  await page.getByTestId('new-color-name').fill(name);
  await page.getByTestId('new-color-add').click();
}
async function upload(page: Page, testid: 'file-artwork' | 'file-pattern', name: string, svg: string) {
  await page.getByTestId(testid).setInputFiles({ name, mimeType: 'image/svg+xml', buffer: Buffer.from(svg) });
}
async function commit(page: Page, label: string, value: string) {
  const el = page.getByLabel(label, { exact: true });
  await el.fill(value);
  await el.press('Enter');
}
async function setPlacement(page: Page, p: { anchor: string; reference: 'Top edge (center)' | 'Center'; width: string; down: string; left: string; tol: string }) {
  await page.getByLabel('Reference point', { exact: true }).selectOption({ label: p.anchor });
  await page.getByLabel('Point on artwork', { exact: true }).selectOption({ label: p.reference });
  await commit(page, 'Finished width', p.width);
  await commit(page, 'Vertical offset', p.down);
  await commit(page, 'Horizontal offset', p.left);
  await commit(page, 'Placement tolerance', p.tol);
}
async function setSeams(page: Page, names: string[]) {
  const boxes = page.locator('[data-testid=inspector] .field', { hasText: 'Seams' }).locator('label');
  const n = await boxes.count();
  for (let i = 0; i < n; i++) {
    const lab = boxes.nth(i);
    if (names.includes((await lab.textContent())!.trim())) await lab.locator('input').check();
  }
  for (let i = 0; i < n; i++) {
    const lab = boxes.nth(i);
    if (!names.includes((await lab.textContent())!.trim())) await lab.locator('input').uncheck();
  }
}
async function selectLayer(page: Page, name: string) {
  await page.getByTestId('layers-tab').click();
  await page.locator('li[data-testid=layer-row] button.name', { hasText: name }).first().click();
}
async function renameSelected(page: Page, name: string) {
  const input = page.getByLabel('Layer name', { exact: true });
  await input.fill(name);
  await input.press('Enter');
}
async function fillSizes(page: Page, values: Record<string, (number | string)[]>, sizes: string[]) {
  for (const [code, vals] of Object.entries(values)) {
    for (let i = 0; i < sizes.length; i++) {
      const cell = page.getByLabel(`${code} size ${sizes[i]}`, { exact: true });
      await cell.fill(String(vals[i]));
      await cell.press('Tab');
    }
    const box = page.getByTestId(`confirm-${code}`);
    if (!(await box.isChecked())) await box.check();
  }
}
async function completeMaterial(page: Page, index: number, m: { name: string; composition: string; weight?: string; supplier: string; ref: string }) {
  const card = page.locator('[data-testid^=material-]').nth(index);
  const set = async (label: string, v: string) => {
    const el = card.getByLabel(label, { exact: true });
    await el.fill(v);
    await el.press('Tab');
  };
  await set('Material name', m.name);
  await set('Composition', m.composition);
  if (m.weight) await set('Fabric weight', m.weight);
  await set('Supplier', m.supplier);
  await set('Supplier reference', m.ref);
}
async function download(request: APIRequestContext, href: string, file: string) {
  const r = await request.get(`${API}${href.replace(/\?inline=1$/, '')}`);
  const buf = await r.body();
  fs.writeFileSync(file, buf);
  return { buf, type: r.headers()['content-type'] };
}
async function bom(request: APIRequestContext, id: string): Promise<BomRow[]> {
  return (await request.get(`${API}/api/projects/${id}/bom`)).json();
}
async function exportRevision(page: Page, request: APIRequestContext, id: string, kind: 'draft' | 'review', notes: string, garment: string) {
  await page.getByRole('link', { name: 'Tech Pack' }).click();
  await page.getByLabel('Revision notes').fill(notes);
  const before = (await (await request.get(`${API}/api/projects/${id}/revisions`)).json()).length;
  await page.getByTestId(kind === 'draft' ? 'export-draft' : 'export-review').click();
  await expect(page.getByTestId('revision')).toHaveCount(before + 1, { timeout: 90_000 });
  const revs: RevisionSummary[] = await (await request.get(`${API}/api/projects/${id}/revisions`)).json();
  const rev = revs[0];
  const files: Record<string, string> = {};
  for (const e of rev.exports) {
    record(garment, `${rev.label} export ${e.filename}`, e.status === 'ok', e.error ?? 'generated');
    const out = path.join(dir(garment), e.filename);
    await download(request, `/api/exports/${e.id}/download`, out);
    files[e.kind + (e.filename.includes('back') ? '-back' : e.kind === 'mockup-png' ? '-front' : '')] = out;
  }
  return { rev, files };
}
function sha(file: string) {
  return crypto.createHash('sha256').update(fs.readFileSync(file)).digest('hex');
}

test.afterAll(() => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify({ generatedAt: new Date().toISOString(), results }, null, 2));
});

/* ================================================================== */
test('T-shirt: complete demonstration', async ({ page, request, browser }) => {
  const G = 'tshirt';
  await page.goto('/new');
  await shot(page, G, '01-choose-garment');
  const id = await createStyle(page, 'tshirt-boxy', 'Verification Tee', 'VT-TS-001');
  await shot(page, G, '02-new-style-studio');
  const canvas = page.getByTestId('canvas');

  // 1. Recolor one panel independently.
  await page.getByTestId('part-sleeve_right').click();
  await addColor(page, 'Forest', '#1f5c3f');
  await waitSaved(page);
  let rec = await getProject(request, id);
  const forest = rec.doc.colors.find((c) => c.name === 'Forest')!;
  const fillsWith = rec.doc.layers.filter((l) => l.type === 'panelFill' && l.colorId === forest.id).map((l) => l.targets[0]);
  record(G, 'Recolor right sleeve only', JSON.stringify(fillsWith) === '["sleeve_right"]', `fills using Forest: ${fillsWith.join(', ')}`);
  for (const v of ['front', 'back'] as const) {
    await page.getByTestId(`view-${v}`).click();
    const right = await canvas.locator('path[data-component-id=sleeve_right]').getAttribute('data-fill');
    const left = await canvas.locator('path[data-component-id=sleeve_left]').getAttribute('data-fill');
    const body = await canvas.locator(`path[data-component-id=body_${v}]`).first().getAttribute('data-fill');
    record(G, `Sleeve color linked in ${v} view`, right === '#1f5c3f' && left !== '#1f5c3f' && body !== '#1f5c3f', `right=${right} left=${left} body=${body}`);
  }
  await page.getByTestId('view-front').click();
  await shot(page, G, '03-recolor-right-sleeve');

  // 2. Upload and position a logo (drag on the canvas).
  await page.keyboard.press('Escape');
  await upload(page, 'file-artwork', 'sunset-logo.svg', DEMO_LOGO_SVG);
  await expect(page.getByTestId('visual-estimate')).toBeVisible();
  await waitSaved(page);
  rec = await getProject(request, id);
  const logo = rec.doc.layers.find((l) => l.type === 'artwork')!;
  if (logo.type !== 'artwork') throw new Error('no artwork');
  const a = await svgToScreen(page, logo.transform.x, logo.transform.y);
  const b = await svgToScreen(page, logo.transform.x - 30, logo.transform.y + 20);
  await page.mouse.move(a.x, a.y);
  await page.mouse.down();
  await page.mouse.move(b.x, b.y, { steps: 8 });
  await page.mouse.up();
  await waitSaved(page);
  rec = await getProject(request, id);
  const dragged = rec.doc.layers.find((l) => l.id === logo.id)!;
  record(G, 'Logo dragged on canvas (visual estimate)', dragged.type === 'artwork' && Math.abs(dragged.transform.x - (logo.transform.x - 30)) < 2 && dragged.placement.source === 'canvas-estimate', dragged.type === 'artwork' ? `x ${logo.transform.x.toFixed(1)} → ${dragged.transform.x.toFixed(1)}, source ${dragged.placement.source}` : '');
  await shot(page, G, '04-logo-dragged');

  // 3. Physical dimensions and placement references.
  await renameSelected(page, 'Chest logo');
  await setPlacement(page, { anchor: 'Center chest', reference: 'Top edge (center)', width: '24', down: '5', left: '0', tol: '0.5' });
  await page.getByLabel('Artwork ID').fill('VT-ART-01');
  await page.getByLabel('Artwork ID').press('Tab');
  await waitSaved(page);
  rec = await getProject(request, id);
  const placed = rec.doc.layers.find((l) => l.id === logo.id)!;
  if (placed.type !== 'artwork') throw new Error();
  record(
    G,
    'Logo manufacturing placement entered',
    placed.placement.source === 'entered' && placed.placement.widthMm === 240 && placed.placement.offsetYmm === 50 && placed.placement.offsetXmm === 0 && placed.placement.toleranceMm === 5 && placed.placement.anchorId === 'center_chest',
    `W ${placed.placement.widthMm} × H ${placed.placement.heightMm} mm, ${placed.placement.offsetYmm} mm below ${placed.placement.anchorId}, ±${placed.placement.toleranceMm}`,
  );
  record(G, 'Canvas follows entered dimensions', Math.abs(placed.transform.width - 240) < 0.01 && Math.abs(placed.transform.x - 500) < 0.01 && Math.abs(placed.transform.y - placed.transform.height / 2 - 300) < 0.01, `transform ${JSON.stringify(placed.transform)}`);
  await shot(page, G, '05-logo-placement-spec');

  // Second artwork on the back (a layer that must survive the pattern erase untouched).
  await page.getByTestId('view-back').click();
  await page.keyboard.press('Escape');
  await upload(page, 'file-artwork', 'est-badge.svg', DEMO_BACK_SVG);
  await expect(page.getByTestId('visual-estimate')).toBeVisible();
  await renameSelected(page, 'Back badge');
  await setPlacement(page, { anchor: 'Upper back', reference: 'Top edge (center)', width: '26', down: '3', left: '0', tol: '0.5' });
  await page.getByTestId('view-front').click();

  // 4. Pattern on both sleeves, then erase part of it.
  await page.getByRole('tab', { name: 'Parts' }).click();
  await page.getByTestId('part-sleeve_left').click();
  await upload(page, 'file-pattern', 'sun-dot-tile.svg', DEMO_TILE_SVG);
  await expect(page.getByTestId('erase-tool')).toBeVisible();
  await page.getByLabel('Pattern print method').selectOption('sublimation');
  await waitSaved(page);
  rec = await getProject(request, id);
  const before = structuredClone(rec.doc) as ProjectDoc;
  const pattern = before.layers.find((l) => l.type === 'pattern')!;
  await page.getByTestId('erase-tool').click();
  const s1 = await svgToScreen(page, 900, 300);
  const s2 = await svgToScreen(page, 930, 380);
  await page.mouse.move(s1.x, s1.y);
  await page.mouse.down();
  await page.mouse.move(s2.x, s2.y, { steps: 10 });
  await page.mouse.up();
  await page.keyboard.press('Escape');
  await waitSaved(page);
  rec = await getProject(request, id);
  const erased = rec.doc.layers.find((l) => l.id === pattern.id)!;
  const others = rec.doc.layers.filter((l) => l.id !== pattern.id);
  const untouched = others.every((l) => JSON.stringify(l) === JSON.stringify(before.layers.find((x) => x.id === l.id)));
  record(G, 'Erase affects only the pattern layer', erased.type === 'pattern' && erased.mask.length === 1 && untouched && others.length === before.layers.length - 1, `pattern mask strokes: ${erased.type === 'pattern' ? erased.mask.length : '?'}; other ${others.length} layers unchanged: ${untouched}`);
  await shot(page, G, '06-pattern-erased');

  // 5. Stitching.
  await page.getByRole('tab', { name: 'Parts' }).click();
  await page.keyboard.press('Escape');
  await page.getByTestId('add-stitching').click();
  await renameSelected(page, 'Hem coverstitch');
  await setSeams(page, ['Bottom hem', 'Left sleeve hem', 'Right sleeve hem']);
  await page.getByLabel('Stitch visual style').selectOption('coverstitch');
  await page.getByLabel('Stitching manufacturing notes').fill('2-needle coverstitch, 6.4 mm gauge, 12 SPI on bottom and sleeve hems.');
  await page.getByLabel('Stitching manufacturing notes').press('Tab');
  await page.getByTestId('color-Forest').click();

  // 6. Rhinestones: path along the neckline (with an inserted point) + individual stones.
  await page.keyboard.press('Escape');
  await page.getByTestId('add-rhinestones').click();
  for (const [x, y] of [[440, 210], [530, 230], [600, 205]]) await clickSvg(page, x, y); // individual
  await page.getByTestId('draw-path').click();
  for (const [x, y] of [[420, 190], [500, 220], [580, 190]]) await clickSvg(page, x, y);
  await page.getByTestId('finish-path').click();
  const m1 = await svgToScreen(page, 460, 205);
  const m2 = await svgToScreen(page, 460, 214);
  await page.mouse.move(m1.x, m1.y);
  await page.mouse.down();
  await page.mouse.move(m2.x, m2.y, { steps: 4 });
  await page.mouse.up();
  await renameSelected(page, 'Neckline stones');
  await waitSaved(page);
  rec = await getProject(request, id);
  const stones = rec.doc.layers.find((l) => l.type === 'embellishment' && l.kind === 'rhinestone')!;
  const stoneBadge = Number((await page.getByTestId('emb-count-badge').textContent())!.match(/\d+/)![0]);
  record(G, 'Rhinestone path edited (point inserted)', stones.type === 'embellishment' && stones.paths[0].points.length === 4 && stones.points.length === 3, stones.type === 'embellishment' ? `${stones.points.length} individual + path with ${stones.paths[0].points.length} points` : '');
  await shot(page, G, '07-rhinestones');

  // 7. Studs on the left sleeve.
  await page.keyboard.press('Escape');
  await page.getByTestId('add-studs').click();
  for (const [x, y] of [[860, 180], [880, 200], [900, 220], [920, 240]]) await clickSvg(page, x, y);
  await renameSelected(page, 'Sleeve studs');
  await page.keyboard.press('Escape');

  // 8. Hardware: metal badge on the hem, adjusted by keyboard.
  await page.getByTestId('add-hardware').click();
  await page.getByTestId('hw-metal-badge').click();
  await clickSvg(page, 690, 715);
  await page.keyboard.press('Shift+ArrowRight');
  await page.keyboard.press('+');
  await waitSaved(page);
  await shot(page, G, '08-studs-hardware');

  // BOM counts must match placements.
  const rows = await bom(request, id);
  const stoneRow = rows.find((r) => r.source === 'embellishment' && /Rhinestone/.test(r.materialName))!;
  const studRow = rows.find((r) => r.source === 'embellishment' && /Stud/.test(r.materialName))!;
  const hwRow = rows.find((r) => r.source === 'hardware')!;
  record(G, 'Rhinestone BOM count = placements', stoneRow.quantity === stoneBadge && stoneRow.quantityType === 'counted', `BOM ${stoneRow.quantity}, canvas badge ${stoneBadge}`);
  record(G, 'Stud BOM count = placements', studRow.quantity === 4, `BOM ${studRow.quantity}`);
  record(G, 'Hardware BOM row', hwRow.quantity === 1 && /badge/i.test(hwRow.materialName), `${hwRow.materialName} × ${hwRow.quantity}`);

  // 9. Measurements: enter values (cm and inches), switch units.
  await page.getByRole('link', { name: 'Measurements' }).click();
  await shot(page, G, '09-measurements-defaults-cm', true);
  const sizes = ['XS', 'S', 'M', 'L', 'XL'];
  await fillSizes(
    page,
    {
      A: [68, 69, 70, 71.5, 73],
      B: [55.2, 57.2, 59.2, 61.2, 63.2],
      C: [55.2, 57.2, 59.2, 61.2, 63.2],
      D: [53.6, 55.6, 57.6, 59.6, 61.6],
      E: [20.9, 21.3, 21.7, 22.1, 22.5],
      F: [17.1, 17.6, 18.1, 18.6, 19.1],
      G: [22.2, 22.7, 23.2, 23.7, 24.2],
      H: [18.4, 18.7, 19, 19.3, 19.6],
      I: [10.6, 10.8, 11, 11.2, 11.4],
      J: [1.8, 1.8, 1.8, 1.8, 1.8],
      K: [2.2, 2.2, 2.2, 2.2, 2.2],
    },
    sizes,
  );
  await page.getByTestId('unit-in').click();
  await fillSizes(page, { L: ['6 7/8', '7 1/8', '7 5/16', '7 1/2', '7 3/4'] }, sizes);
  await shot(page, G, '10-measurements-inches', true);
  await page.getByTestId('unit-cm').click();
  await waitSaved(page);
  rec = await getProject(request, id);
  const pomA = rec.doc.measurements.find((p) => p.code === 'A')!;
  const pomL = rec.doc.measurements.find((p) => p.code === 'L')!;
  record(G, 'cm entry stored in mm', pomA.values.L.mm === 715 && pomA.values.M.source === 'entered', `A/L = ${pomA.values.L.mm} mm`);
  record(G, 'inch fraction entry stored exactly', pomL.values.M.mm === 185.7375, `L/M = ${pomL.values.M.mm} mm (7 5/16")`);
  record(G, 'All POMs confirmed', rec.doc.measurements.every((p) => p.confirmed), `${rec.doc.measurements.filter((p) => p.confirmed).length}/${rec.doc.measurements.length}`);
  await expect(page.getByLabel('A size M', { exact: true })).toHaveValue('70');
  await shot(page, G, '11-measurements-cm', true);

  // 10. Materials: complete shell + rib, assign a different material to the left sleeve, review BOM.
  await page.getByRole('link', { name: 'Materials & Colors' }).click();
  await page.getByTestId('mc-tab-materials').click();
  await completeMaterial(page, 0, { name: 'Heavyweight cotton jersey', composition: '100% cotton', weight: '240', supplier: 'Example Mill', ref: 'EM-J240' });
  await completeMaterial(page, 1, { name: '1x1 cotton rib', composition: '95% cotton, 5% elastane', weight: '280', supplier: 'Example Mill', ref: 'EM-R11' });
  await page.getByRole('button', { name: 'Add material' }).click();
  await completeMaterial(page, 2, { name: 'Cotton mesh', composition: '100% cotton', weight: '180', supplier: 'Example Mill', ref: 'EM-M180' });
  await page.getByTestId('mc-tab-assign').click();
  await page.getByTestId('assign-mat-sleeve_left').selectOption({ label: 'Cotton mesh' });
  await page.getByTestId('mc-tab-bom').click();
  await waitSaved(page);
  await shot(page, G, '12-bom', true);
  const rows2 = await bom(request, id);
  const mesh = rows2.find((r) => r.materialName === 'Cotton mesh')!;
  const jersey = rows2.find((r) => r.materialName === 'Heavyweight cotton jersey')!;
  record(G, 'Material change updates BOM reference', JSON.stringify(mesh.componentIds) === '["sleeve_left"]' && !jersey.componentIds.includes('sleeve_left'), `mesh → ${mesh.componentIds}; jersey → ${jersey.componentIds.join(', ')}`);
  record(G, 'Fabric consumption not inferred', mesh.quantityType === 'missing', `mesh quantity type: ${mesh.quantityType}`);

  // Construction note + label so optional sections render.
  await page.getByRole('link', { name: 'Tech Pack' }).click();
  await page.getByTestId('add-construction-note').click();
  await page.getByLabel('Note text').first().fill('4-thread overlock on shoulders and side seams; shoulders taped.');
  await page.getByLabel('Note text').first().press('Tab');
  await waitSaved(page);
  const docBeforeClose = (await getProject(request, id)).doc;

  // 11. Save, close the browser context, reopen in a fresh one.
  await page.close();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const p2 = await ctx.newPage();
  await p2.goto(`/p/${id}`);
  await p2.getByTestId('canvas').waitFor();
  const reopened = (await getProject(request, id)).doc;
  record(G, 'Reopened project identical to saved state', JSON.stringify(reopened) === JSON.stringify(docBeforeClose), `${reopened.layers.length} layers, ${reopened.assets.length} assets`);
  const imgs = await p2.getByTestId('canvas').locator('image').count();
  record(G, 'Artwork visible after reopen', imgs >= 1, `${imgs} image element(s) on front`);
  await shot(p2, G, '13-reopened-front');
  await p2.getByTestId('view-back').click();
  await shot(p2, G, '14-reopened-back');

  // 12. Realistic previews.
  await p2.getByTestId('view-front').click();
  await p2.getByTestId('preview-realistic').click();
  await expect(p2.getByTestId('ghost-preview')).not.toHaveAttribute('data-rendered-at', '0', { timeout: 30000 });
  await shot(p2, G, '15-realistic-front');
  await p2.getByTestId('view-back').click();
  await p2.waitForTimeout(2500);
  await shot(p2, G, '16-realistic-back');

  // 13. Exports: draft first (shows open items), then ready-for-review.
  await p2.getByRole('link', { name: 'Tech Pack' }).click();
  await shot(p2, G, '17-techpack-checks', true);
  const v = await (await request.get(`${API}/api/projects/${id}/validation`)).json();
  const openReq = v.checks.filter((c: { passed: boolean; level: string }) => !c.passed && c.level === 'required');
  record(G, 'All required checks pass before review export', openReq.length === 0, openReq.map((c: { message: string }) => c.message).join('; ') || 'none open');
  const r1 = await exportRevision(p2, request, id, 'review', 'Verification run: first issue for sampling.', G);
  record(G, 'Review revision issued', r1.rev.kind === 'review' && r1.rev.label === 'R1', `${r1.rev.label} ${r1.rev.kind}`);
  const csv = fs.readFileSync(r1.files['bom-csv'], 'utf8');
  record(G, 'BOM CSV contains counted embellishments', csv.includes(`,${stoneBadge},pcs,counted`) && csv.includes(',4,pcs,counted'), 'rhinestone and stud rows marked counted');
  const mcsv = fs.readFileSync(r1.files['measurements-csv'], 'utf8');
  record(G, 'Measurement CSV values', mcsv.includes('Body length from HPS') && mcsv.includes('71.5'), 'cm values present');
  await shot(p2, G, '18-revision-exported', true);

  // 14. Later edit must not change the issued revision.
  const pdfHash = sha(r1.files.pdf);
  const snapBefore = await (await request.get(`${API}/api/revisions/${r1.rev.id}`)).json();
  await p2.getByRole('link', { name: 'Design Studio' }).click();
  await p2.getByTestId('preview-technical').click();
  await p2.getByTestId('part-body_front').click();
  await addColor(p2, 'Post-issue red', '#aa0000');
  await waitSaved(p2);
  const snapAfter = await (await request.get(`${API}/api/revisions/${r1.rev.id}`)).json();
  const again = path.join(dir(G), 'R1-redownload.pdf');
  await download(request, `/api/exports/${r1.rev.exports.find((e) => e.kind === 'pdf')!.id}/download`, again);
  record(G, 'Issued revision unchanged after later edit', snapAfter.snapshotHash === snapBefore.snapshotHash && sha(again) === pdfHash, `snapshot ${snapAfter.snapshotHash.slice(0, 12)}…, PDF sha ${pdfHash.slice(0, 12)}…`);
  fs.rmSync(again);
  await ctx.close();
});

/* ================================================================== */
async function setGarment(
  browser: import('@playwright/test').Browser,
  request: APIRequestContext,
  opts: {
    G: string;
    template: 'hoodie-pullover' | 'sweatpants-straight';
    name: string;
    style: string;
    recolor: string;
    overridePart: string;
    logoAnchor: string;
    logoWidth: string;
    seams: string;
    seamNames: string[];
    stonesPath: [number, number][];
    studs: [number, number][];
    hardware: { id: string; at: [number, number] };
    altMaterialPart: string;
    sizes: Record<string, (number | string)[]>;
  },
) {
  const { G } = opts;
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  const id = await createStyle(page, opts.template, opts.name, opts.style);
  const canvas = page.getByTestId('canvas');
  await shot(page, G, '01-new-style');

  // Recolor one part; make another part intentionally different on the back.
  await page.getByTestId(`part-${opts.recolor}`).click();
  await addColor(page, 'Clay', '#b5653f');
  await page.getByTestId('view-back').click();
  await page.getByTestId(`part-${opts.overridePart}`).click();
  await page.getByTestId('make-view-different').click();
  await page.getByTestId('color-Clay').click();
  await waitSaved(page);
  let rec = await getProject(request, id);
  const clay = rec.doc.colors.find((c) => c.name === 'Clay')!;
  const shared = rec.doc.layers.filter((l) => l.type === 'panelFill' && l.view === 'all' && l.colorId === clay.id).map((l) => l.targets[0]);
  const backOnly = rec.doc.layers.filter((l) => l.type === 'panelFill' && l.view === 'back' && l.colorId === clay.id).map((l) => l.targets[0]);
  record(G, 'Independent recolor + back-only override', JSON.stringify(shared) === JSON.stringify([opts.recolor]) && JSON.stringify(backOnly) === JSON.stringify([opts.overridePart]), `all-views: ${shared}; back only: ${backOnly}`);
  const backFill = await canvas.locator(`path[data-component-id=${opts.overridePart}]`).first().getAttribute('data-fill');
  await page.getByTestId('view-front').click();
  const frontFill = await canvas.locator(`path[data-component-id=${opts.overridePart}]`).first().getAttribute('data-fill');
  record(G, 'Front/back assignment differs only where overridden', backFill === '#b5653f' && frontFill !== '#b5653f', `back ${backFill}, front ${frontFill}`);

  // Logo with manufacturing dimensions.
  await page.keyboard.press('Escape');
  await upload(page, 'file-artwork', 'logo.svg', DEMO_LOGO_SVG);
  await expect(page.getByTestId('visual-estimate')).toBeVisible();
  await renameSelected(page, 'Logo');
  await setPlacement(page, { anchor: opts.logoAnchor, reference: 'Top edge (center)', width: opts.logoWidth, down: '2', left: '0', tol: '0.5' });
  await page.getByLabel('Decoration method').selectOption('embroidery');
  // Stitching on named seams.
  await page.keyboard.press('Escape');
  await page.getByRole('tab', { name: 'Parts' }).click();
  await page.getByTestId('add-stitching').click();
  await setSeams(page, opts.seamNames);
  await page.getByLabel('Stitching manufacturing notes').fill(opts.seams);
  await page.getByLabel('Stitching manufacturing notes').press('Tab');
  await page.getByTestId('color-Clay').click();
  await waitSaved(page);
  const st = (await getProject(request, id)).doc.layers.find((l) => l.type === 'stitching');
  record(G, 'Stitching on the intended seams', !!st && st.type === 'stitching' && st.seamIds.length === opts.seamNames.length, st && st.type === 'stitching' ? st.seamIds.join(', ') : 'none');
  // Rhinestone path + studs + hardware.
  await page.keyboard.press('Escape');
  await page.getByTestId('add-rhinestones').click();
  await page.getByTestId('draw-path').click();
  for (const [x, y] of opts.stonesPath) await clickSvg(page, x, y);
  await page.getByTestId('finish-path').click();
  const stoneCount = Number((await page.getByTestId('emb-count-badge').textContent())!.match(/\d+/)![0]);
  await page.keyboard.press('Escape');
  await page.getByTestId('add-studs').click();
  for (const [x, y] of opts.studs) await clickSvg(page, x, y);
  await page.keyboard.press('Escape');
  await page.getByTestId('add-hardware').click();
  await page.getByTestId(`hw-${opts.hardware.id}`).click();
  await clickSvg(page, ...opts.hardware.at);
  await waitSaved(page);
  await shot(page, G, '02-designed-front');
  await page.getByTestId('view-back').click();
  await shot(page, G, '03-designed-back');

  // Measurements for every POM and size, confirmed.
  await page.getByRole('link', { name: 'Measurements' }).click();
  await fillSizes(page, opts.sizes, ['XS', 'S', 'M', 'L', 'XL']);
  await waitSaved(page);
  await shot(page, G, '04-measurements', true);

  // Materials.
  await page.getByRole('link', { name: 'Materials & Colors' }).click();
  await page.getByTestId('mc-tab-materials').click();
  await completeMaterial(page, 0, { name: '400 g brushed fleece', composition: '80% cotton, 20% polyester', weight: '400', supplier: 'Example Mill', ref: 'EM-F400' });
  await completeMaterial(page, 1, { name: '2x2 cotton rib', composition: '95% cotton, 5% elastane', weight: '320', supplier: 'Example Mill', ref: 'EM-R22' });
  await completeMaterial(page, 2, { name: 'Flat cotton drawcord 12 mm', composition: '100% cotton', supplier: 'Example Trims', ref: 'ET-DC12' });
  await page.getByRole('button', { name: 'Add material' }).click();
  await completeMaterial(page, 3, { name: 'French terry', composition: '100% cotton', weight: '330', supplier: 'Example Mill', ref: 'EM-FT330' });
  await page.getByTestId('mc-tab-assign').click();
  await page.getByTestId(`assign-mat-${opts.altMaterialPart}`).selectOption({ label: 'French terry' });
  await page.getByTestId('mc-tab-bom').click();
  await waitSaved(page);
  await shot(page, G, '05-bom', true);
  const rows = await bom(request, id);
  const terry = rows.find((r) => r.materialName === 'French terry')!;
  record(G, 'Material reference in BOM', JSON.stringify(terry.componentIds) === JSON.stringify([opts.altMaterialPart]), `French terry → ${terry.componentIds}`);
  const stoneRow = rows.find((r) => /Rhinestone/.test(r.materialName))!;
  const studRow = rows.find((r) => /Stud/.test(r.materialName))!;
  record(G, 'Embellishment counts', stoneRow.quantity === stoneCount && studRow.quantity === opts.studs.length, `rhinestones ${stoneRow.quantity} (canvas ${stoneCount}), studs ${studRow.quantity}`);
  record(G, 'Hardware counted', rows.some((r) => r.source === 'hardware' && r.quantity === 1), rows.filter((r) => r.source === 'hardware').map((r) => r.materialName).join(', '));

  // Reopen, realistic preview, export.
  await page.close();
  const p2 = await ctx.newPage();
  await p2.goto(`/p/${id}`);
  await p2.getByTestId('canvas').waitFor();
  await p2.getByTestId('preview-realistic').click();
  await expect(p2.getByTestId('ghost-preview')).not.toHaveAttribute('data-rendered-at', '0', { timeout: 30000 });
  await shot(p2, G, '06-realistic-front');
  await p2.getByTestId('view-back').click();
  await p2.waitForTimeout(2500);
  await shot(p2, G, '07-realistic-back');
  const v = await (await request.get(`${API}/api/projects/${id}/validation`)).json();
  const openReq = v.checks.filter((c: { passed: boolean; level: string }) => !c.passed && c.level === 'required');
  record(G, 'All required checks pass', openReq.length === 0, openReq.map((c: { message: string }) => c.message).join('; ') || 'none open');
  const r1 = await exportRevision(p2, request, id, 'review', `Verification run: ${opts.name}`, G);
  const snap = await (await request.get(`${API}/api/revisions/${r1.rev.id}`)).json();
  const snapStones = snap.snapshot.bom.find((r: BomRow) => /Rhinestone/.test(r.materialName));
  const snapOverride = snap.snapshot.doc.layers.find((l: { type: string; view: string; targets: string[] }) => l.type === 'panelFill' && l.view === 'back');
  record(G, 'Revision snapshot keeps counts, materials and back override', snapStones.quantity === stoneCount && snapOverride?.targets[0] === opts.overridePart, `snapshot rhinestones ${snapStones.quantity}; back override on ${snapOverride?.targets[0]}`);
  await shot(p2, G, '08-revision-exported', true);
  await ctx.close();
}

test('Hoodie: core workflow', async ({ browser, request }) => {
  await setGarment(browser, request, {
    G: 'hoodie',
    template: 'hoodie-pullover',
    name: 'Verification Hoodie',
    style: 'VT-HD-001',
    recolor: 'kangaroo_pocket',
    overridePart: 'hood',
    logoAnchor: 'Center chest',
    logoWidth: '18',
    seams: 'Twin-needle topstitch 6 mm on pocket openings and top, 10 SPI.',
    seamNames: ['Pocket topstitch (openings & top)'],
    stonesPath: [[300, 760], [500, 720], [700, 760]],
    studs: [[300, 1005], [400, 1005], [600, 1005], [700, 1005]],
    hardware: { id: 'metal-badge', at: [700, 1005] },
    altMaterialPart: 'hood_lining',
    sizes: {
      A: [68, 69, 70, 71, 72],
      B: [56, 58, 60, 62, 64],
      C: [53, 55, 57, 59, 61],
      D: [55, 57, 59, 61, 63],
      E: [57.3, 58.3, 59.3, 60.3, 61.3],
      F: [9.6, 9.9, 10.2, 10.5, 10.8],
      G: [7, 7, 7, 7, 7],
      H: [7, 7, 7, 7, 7],
      I: [26.4, 26.9, 27.4, 27.9, 28.4],
      J: [38.6, 39.1, 39.6, 40.1, 40.6],
      K: [19.4, 19.7, 20, 20.3, 20.6],
      L: [26, 27, 28, 29, 30],
      M: [20.5, 21, 21.5, 22, 22.5],
      N: [17.1, 17.6, 18.1, 18.6, 19.1],
    },
  });
});

test('Sweatpants: core workflow', async ({ browser, request }) => {
  await setGarment(browser, request, {
    G: 'sweatpants',
    template: 'sweatpants-straight',
    name: 'Verification Sweatpants',
    style: 'VT-SP-001',
    recolor: 'leg_front_left',
    overridePart: 'waistband',
    logoAnchor: 'Left thigh',
    logoWidth: '9',
    seams: 'Twin-needle 6 mm on front and back rise, 10 SPI.',
    seamNames: ['Front rise seam', 'Back rise seam'],
    stonesPath: [[740, 420], [735, 700], [728, 980]],
    studs: [[330, 140], [345, 170], [360, 200], [375, 230]],
    hardware: { id: 'metal-badge', at: [600, 65] },
    altMaterialPart: 'leg_back_right',
    sizes: {
      A: [32, 34, 36, 38, 40],
      B: [46, 48, 50, 52, 54],
      C: [49.2, 51.2, 53.2, 55.2, 57.2],
      D: [30, 31, 32, 33, 34],
      E: [32.8, 33.8, 34.8, 35.8, 36.8],
      F: [72, 72, 72, 72, 72],
      G: [102.2, 103.2, 104.2, 105.2, 106.2],
      H: [23.8, 24.3, 24.8, 25.3, 25.8],
      I: [19.2, 19.7, 20.2, 20.7, 21.2],
      J: [5, 5, 5, 5, 5],
      K: [21.8, 22.3, 22.8, 23.3, 23.8],
    },
  });
});

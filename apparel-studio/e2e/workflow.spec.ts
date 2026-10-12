import { expect, test } from '@playwright/test';
import { API, createStyle, getProject, pngLogo, waitSaved } from './fixtures';

test.describe.configure({ mode: 'serial' });

test('T-shirt: design → specs → revisioned tech pack', async ({ page, request }) => {
  const id = await createStyle(page, 'tshirt-boxy', 'E2E Tee', 'E2E-TS-1');
  const canvas = page.getByTestId('canvas');

  // ---- Recolor only the left sleeve (VER-01) and check front/back linkage (VER-02).
  await page.getByTestId('part-sleeve_left').click();
  await page.getByRole('button', { name: 'New' }).first().click();
  await page.getByTestId('new-color-hex').fill('#cc2233');
  await page.getByTestId('new-color-name').fill('Cherry');
  await page.getByTestId('new-color-add').click();
  await expect(canvas.locator('path[data-component-id=sleeve_left]')).toHaveAttribute('data-fill', '#cc2233');
  await expect(canvas.locator('path[data-component-id=body_front]')).not.toHaveAttribute('data-fill', '#cc2233');
  await expect(canvas.locator('path[data-component-id=sleeve_right]')).not.toHaveAttribute('data-fill', '#cc2233');
  await page.getByTestId('view-back').click();
  await expect(canvas.locator('path[data-component-id=sleeve_left]')).toHaveAttribute('data-fill', '#cc2233');
  await expect(canvas.locator('path[data-component-id=body_back]')).not.toHaveAttribute('data-fill', '#cc2233');
  // Intentional per-view difference: neck rib differs on back only.
  await page.getByTestId('part-neck_rib').click();
  await page.getByTestId('make-view-different').click();
  await page.getByTestId('color-Cherry').click();
  await expect(canvas.locator('path[data-component-id=neck_rib]').first()).toHaveAttribute('data-fill', '#cc2233');
  await page.getByTestId('view-front').click();
  await expect(canvas.locator('path[data-component-id=neck_rib]').first()).not.toHaveAttribute('data-fill', '#cc2233');

  // ---- Upload a transparent PNG logo (VER-03).
  await page.keyboard.press('Escape');
  await page.getByTestId('file-artwork').setInputFiles({ name: 'logo.png', mimeType: 'image/png', buffer: pngLogo() });
  await expect(page.getByTestId('visual-estimate')).toBeVisible();
  await page.getByLabel('Finished width').fill('20');
  await page.getByLabel('Finished width').press('Enter');
  await expect(page.getByTestId('placement-section').getByText('Entered')).toBeVisible();
  await waitSaved(page);
  let rec = await getProject(request, id);
  const art = rec.doc.layers.find((l) => l.type === 'artwork')!;
  expect(art.type === 'artwork' && art.placement.widthMm).toBe(200);
  expect(art.type === 'artwork' && art.placement.source).toBe('entered');

  // ---- Drag the artwork toward the left sleeve; clipping must still hold (VER-04).
  const artEl = canvas.locator(`g[data-layer-id=${art.id}]`).first();
  const box = (await artEl.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 260, box.y + box.height / 2 + 10, { steps: 10 });
  await page.mouse.up();
  await waitSaved(page);
  rec = await getProject(request, id);
  const moved = rec.doc.layers.find((l) => l.id === art.id)!;
  expect(moved.type === 'artwork' && moved.transform.x).toBeGreaterThan(art.type === 'artwork' ? art.transform.x + 50 : 0);
  expect(moved.type === 'artwork' && moved.placement.source).toBe('canvas-estimate');
  // The artwork group is clipped to the front body panel only.
  await expect(canvas.locator(`g[data-layer-id=${art.id}]`)).toHaveCount(1);
  await expect(canvas.locator(`g[data-layer-id=${art.id}]`)).toHaveAttribute('clip-path', /clip-f_body/);
  // Hit-test a point inside the sleeve that the artwork's bounding box covers: the sleeve wins.
  const sleeveBox = (await canvas.locator('path[data-component-id=sleeve_left]').first().boundingBox())!;
  const artBox = (await canvas.locator(`g[data-layer-id=${art.id}] image`).boundingBox())!;
  const probe = { x: sleeveBox.x + sleeveBox.width * 0.45, y: Math.max(artBox.y + 4, sleeveBox.y + sleeveBox.height * 0.35) };
  expect(probe.x).toBeGreaterThan(artBox.x);
  expect(probe.x).toBeLessThan(artBox.x + artBox.width);
  expect(probe.y).toBeLessThan(artBox.y + artBox.height);
  const hit = await page.evaluate(([x, y]) => {
    const el = document.elementFromPoint(x, y) as Element | null;
    return el?.getAttribute('data-component-id') ?? el?.tagName ?? null;
  }, [probe.x, probe.y]);
  expect(hit).toBe('sleeve_left');

  // ---- Undo restores the saved state (VER-06).
  await page.getByRole('button', { name: 'Undo' }).click();
  await waitSaved(page);
  rec = await getProject(request, id);
  const undone = rec.doc.layers.find((l) => l.id === art.id)!;
  expect(undone.type === 'artwork' && undone.transform.x).toBeCloseTo(art.type === 'artwork' ? art.transform.x : 0, 3);
  await page.getByRole('button', { name: 'Redo' }).click();
  await waitSaved(page);
  await page.getByRole('button', { name: 'Undo' }).click();
  await waitSaved(page);
  await page.reload();
  await page.getByTestId('canvas').waitFor();
  await expect(page.getByTestId('canvas').locator(`g[data-layer-id=${art.id}] image`)).toHaveCount(1);

  // ---- Rhinestones: counted placements feed the BOM (VER-10).
  await page.getByTestId('add-rhinestones').click();
  const body = (await canvas.locator('path[data-component-id=body_front]').boundingBox())!;
  for (let i = 0; i < 3; i++) await page.mouse.click(body.x + body.width * (0.3 + i * 0.1), body.y + body.height * 0.75);
  await expect(page.getByTestId('emb-count-badge')).toContainText('3 placed');
  await page.keyboard.press('Escape');
  await waitSaved(page);

  // ---- Measurements: unit switching never changes stored values (VER-07, VER-08).
  await page.getByRole('link', { name: 'Measurements' }).click();
  const a = page.getByLabel('A size M');
  await expect(a).toHaveValue('70');
  await expect(page.getByTestId('unconfirmed-count')).toBeVisible();
  await page.getByTestId('unit-in').click();
  await expect(a).not.toHaveValue('70');
  await page.getByTestId('unit-cm').click();
  await expect(a).toHaveValue('70');
  await waitSaved(page);
  rec = await getProject(request, id);
  const pomA = rec.doc.measurements.find((p) => p.code === 'A')!;
  expect(pomA.values.M).toEqual({ mm: 700, source: 'template-default' });
  expect(pomA.confirmed).toBe(false);
  // Enter a value in inches.
  await page.getByTestId('unit-in').click();
  await page.getByLabel('A size L').fill('28 1/2');
  await page.getByLabel('A size L').press('Enter');
  await waitSaved(page);
  rec = await getProject(request, id);
  expect(rec.doc.measurements.find((p) => p.code === 'A')!.values.L).toEqual({ mm: 723.9, source: 'entered' });

  // ---- BOM shows the counted rhinestones; linked material change updates the BOM (VER-09).
  await page.getByRole('link', { name: 'Materials & Colors' }).click();
  await page.getByTestId('mc-tab-bom').click();
  await expect(page.getByTestId('bom-counted-qty')).toHaveText('3');
  await page.getByTestId('mc-tab-materials').click();
  await page.getByRole('button', { name: 'Add material' }).click();
  await page.getByTestId('mc-tab-assign').click();
  await page.getByTestId('assign-mat-sleeve_left').selectOption({ label: 'New material' });
  await page.getByTestId('mc-tab-bom').click();
  await expect(page.getByTestId('bom-table')).toContainText('New material');
  await expect(page.getByTestId('bom-table').locator('tr', { hasText: 'New material' })).toContainText('Left sleeve');

  // ---- Tech pack: review blocked, draft export works with PDF/CSV/PNG (VER-11, TPK-*).
  await page.getByRole('link', { name: 'Tech Pack' }).click();
  await expect(page.getByTestId('export-review')).toBeDisabled();
  await expect(page.getByTestId('check-required').first()).toBeVisible();
  await page.getByLabel('Revision notes').fill('First draft for sampling discussion');
  await page.getByTestId('export-draft').click();
  await expect(page.getByTestId('revision').first()).toContainText('R1', { timeout: 60000 });
  const pdfHref = await page.getByTestId('dl-pdf').first().getAttribute('href');
  const pdf = await request.get(`${API}${pdfHref}`);
  expect(pdf.headers()['content-type']).toBe('application/pdf');
  expect((await pdf.body()).subarray(0, 4).toString()).toBe('%PDF');
  await expect(page.getByTestId('dl-bom-csv').first()).toBeVisible();
  await expect(page.getByTestId('dl-measurements-csv').first()).toBeVisible();
  await expect(page.getByTestId('dl-mockup-png').first()).toBeVisible();
  const csvHref = await page.getByTestId('dl-bom-csv').first().getAttribute('href');
  const csv = await (await request.get(`${API}${csvHref}`)).text();
  expect(csv).toContain('Rhinestone');
  expect(csv).toContain('counted');
});

test('Erasing one pattern leaves every other layer untouched (VER-05)', async ({ page, request }) => {
  const id = await createStyle(page, 'tshirt-boxy', 'E2E Erase', 'E2E-TS-2');
  const canvas = page.getByTestId('canvas');
  await page.getByTestId('file-artwork').setInputFiles({ name: 'chest.png', mimeType: 'image/png', buffer: pngLogo(80, 80, [20, 20, 200]) });
  await page.keyboard.press('Escape');
  await page.getByTestId('part-sleeve_left').click();
  await page.getByTestId('file-pattern').setInputFiles({ name: 'tile.png', mimeType: 'image/png', buffer: pngLogo(40, 40, [250, 180, 0]) });
  await page.getByTestId('erase-tool').click();
  await waitSaved(page);
  const before = await getProject(request, id);
  const sleeve = (await canvas.locator('path[data-component-id=sleeve_left]').first().boundingBox())!;
  await page.mouse.move(sleeve.x + sleeve.width * 0.3, sleeve.y + sleeve.height * 0.3);
  await page.mouse.down();
  await page.mouse.move(sleeve.x + sleeve.width * 0.7, sleeve.y + sleeve.height * 0.7, { steps: 10 });
  await page.mouse.up();
  await waitSaved(page);
  const after = await getProject(request, id);
  const pattern = after.doc.layers.find((l) => l.type === 'pattern')!;
  expect(pattern.type === 'pattern' && pattern.mask).toHaveLength(1);
  expect(pattern.type === 'pattern' && pattern.mask[0].view).toBe('front');
  for (const l of after.doc.layers.filter((x) => x.id !== pattern.id)) expect(l).toEqual(before.doc.layers.find((b) => b.id === l.id));
  // The mask is applied only to the pattern layer in the drawing.
  await expect(canvas.locator('g[mask]')).toHaveCount(1);
  await page.getByTestId('reset-mask').click();
  await waitSaved(page);
  const reset = await getProject(request, id);
  expect(reset.doc.layers.find((l) => l.type === 'pattern')!).toMatchObject({ mask: [] });
});

for (const garment of ['hoodie-pullover', 'sweatpants-straight'] as const) {
  test(`${garment}: create, recolor a part, realistic preview renders`, async ({ page, request }) => {
    const id = await createStyle(page, garment, `E2E ${garment}`, `E2E-${garment}`);
    const firstPart = garment === 'hoodie-pullover' ? 'kangaroo_pocket' : 'waistband';
    await page.getByTestId(`part-${firstPart}`).click();
    await page.getByRole('button', { name: 'New' }).first().click();
    await page.getByTestId('new-color-hex').fill('#225588');
    await page.getByTestId('new-color-name').fill('Blue');
    await page.getByTestId('new-color-add').click();
    await waitSaved(page);
    const rec = await getProject(request, id);
    const fills = rec.doc.layers.filter((l) => l.type === 'panelFill');
    const blue = rec.doc.colors.find((c) => c.name === 'Blue')!;
    expect(fills.filter((l) => l.type === 'panelFill' && l.colorId === blue.id).map((l) => l.targets[0])).toEqual([firstPart]);
    await page.getByTestId('preview-realistic').click();
    await expect(page.getByTestId('ghost-preview')).not.toHaveAttribute('data-rendered-at', '0', { timeout: 30000 });
    const nonBlank = await page.getByTestId('ghost-canvas').evaluate((c: HTMLCanvasElement) => {
      const d = c.getContext('2d')!.getImageData(0, 0, c.width, c.height).data;
      let dark = 0;
      for (let i = 0; i < d.length; i += 400) if (d[i] < 200) dark++;
      return dark;
    });
    expect(nonBlank).toBeGreaterThan(50);
  });
}

test('Projects screen groups styles by collection and duplicates', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { name: 'Sunset Club Lounge Set' })).toBeVisible();
  const cards = page.getByTestId('project-card');
  const before = await cards.count();
  await cards.filter({ hasText: 'Sunset Club Hoodie (demo)' }).getByRole('button', { name: 'Duplicate' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Duplicate' }).click();
  await page.waitForURL(/\/p\/prj_/);
  await page.goto('/');
  await expect(cards).toHaveCount(before + 1);
});

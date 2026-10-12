import fs from 'node:fs';
import crypto from 'node:crypto';
import { expect, test } from '@playwright/test';
import { clickSvg, createStyle, getProject, pngLogo, svgToScreen, waitSaved } from './fixtures';

test('inline layer rename, keyboard move/resize/rotate, and path point insert/remove', async ({ page, request }) => {
  const id = await createStyle(page, 'tshirt-boxy', 'E2E Editing', 'E2E-ED-1');
  await page.getByTestId('file-artwork').setInputFiles({ name: 'mark.png', mimeType: 'image/png', buffer: pngLogo(100, 50) });
  await expect(page.getByTestId('visual-estimate')).toBeVisible();
  await waitSaved(page);
  let rec = await getProject(request, id);
  const art = rec.doc.layers.find((l) => l.type === 'artwork')!;
  if (art.type !== 'artwork') throw new Error();

  // ---- Inline rename (no browser prompt).
  await page.getByTestId('layers-tab').click();
  const row = page.locator(`li[data-layer-id=${art.id}]`);
  await row.getByTestId('layer-rename').click();
  await page.getByTestId('layer-rename-input').fill('Chest mark');
  await page.getByTestId('layer-rename-input').press('Enter');
  await expect(row.locator('button.name')).toContainText('Chest mark');
  // F2 on the focused name also enters rename mode; Escape cancels.
  await row.locator('button.name').focus();
  await page.keyboard.press('F2');
  await page.getByTestId('layer-rename-input').fill('Discarded');
  await page.getByTestId('layer-rename-input').press('Escape');
  await expect(row.locator('button.name')).toContainText('Chest mark');

  // ---- Keyboard move / resize / rotate with the layer selected from the list.
  await row.locator('button.name').click();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('Shift+ArrowDown');
  await page.keyboard.press('+');
  await page.keyboard.press('Shift+]');
  await waitSaved(page);
  rec = await getProject(request, id);
  const moved = rec.doc.layers.find((l) => l.id === art.id)!;
  if (moved.type !== 'artwork') throw new Error();
  expect(moved.name).toBe('Chest mark');
  expect(moved.transform.x).toBeCloseTo(art.transform.x + 1, 5);
  expect(moved.transform.y).toBeCloseTo(art.transform.y + 10, 5);
  expect(moved.transform.width).toBeCloseTo(art.transform.width * 1.02, 5);
  expect(moved.transform.height / moved.transform.width).toBeCloseTo(art.transform.height / art.transform.width, 6);
  expect(moved.transform.rotation).toBe(15);
  // Resize is reflected in the (estimated) manufacturing width.
  expect(moved.placement.widthMm).toBeCloseTo(art.placement.widthMm * 1.02, 2);

  // ---- Rhinestone path: draw, insert a point via the midpoint handle, remove it with Alt+click.
  await page.keyboard.press('Escape');
  await page.getByTestId('add-rhinestones').click();
  await page.getByTestId('draw-path').click();
  await clickSvg(page, 300, 500);
  await clickSvg(page, 500, 500);
  await clickSvg(page, 700, 500);
  await page.getByTestId('finish-path').click();
  await waitSaved(page);
  rec = await getProject(request, id);
  const emb = rec.doc.layers.find((l) => l.type === 'embellishment')!;
  if (emb.type !== 'embellishment') throw new Error();
  expect(emb.paths[0].points).toHaveLength(3);
  const before = Number((await page.getByTestId('emb-count-badge').textContent())!.match(/\d+/)![0]);
  // Midpoint handle between points 1 and 2 sits at (400,500); drag it up to (400,440).
  const from = await svgToScreen(page, 400, 500);
  const to = await svgToScreen(page, 400, 440);
  await page.mouse.move(from.x, from.y);
  await page.mouse.down();
  await page.mouse.move(to.x, to.y, { steps: 6 });
  await page.mouse.up();
  await waitSaved(page);
  rec = await getProject(request, id);
  const emb2 = rec.doc.layers.find((l) => l.id === emb.id)!;
  if (emb2.type !== 'embellishment') throw new Error();
  expect(emb2.paths[0].points).toHaveLength(4);
  expect(emb2.paths[0].points[1].x).toBeCloseTo(400, 0);
  expect(emb2.paths[0].points[1].y).toBeCloseTo(440, 0);
  const after = Number((await page.getByTestId('emb-count-badge').textContent())!.match(/\d+/)![0]);
  expect(after).toBeGreaterThan(before); // longer path → more stones at the same spacing
  // Alt+click the inserted point removes it again.
  const pt = await svgToScreen(page, 400, 440);
  await page.keyboard.down('Alt');
  await page.mouse.click(pt.x, pt.y);
  await page.keyboard.up('Alt');
  await waitSaved(page);
  rec = await getProject(request, id);
  const emb3 = rec.doc.layers.find((l) => l.id === emb.id)!;
  expect(emb3.type === 'embellishment' && emb3.paths[0].points).toHaveLength(3);
  // Keyboard moves the whole embellishment layer.
  await page.keyboard.press('ArrowUp');
  await waitSaved(page);
  rec = await getProject(request, id);
  const emb4 = rec.doc.layers.find((l) => l.id === emb.id)!;
  expect(emb4.type === 'embellishment' && emb4.paths[0].points[0].y).toBeCloseTo(emb.paths[0].points[0].y - 1, 3);
});

test('ghost renderer is deterministic: two high-resolution renders are byte-identical', async ({ page, request }) => {
  const projects = await (await request.get('http://localhost:4100/api/projects')).json();
  const tee = projects.find((p: { styleNumber: string }) => p.styleNumber === 'SC-TS-001');
  await page.goto(`/p/${tee.id}`);
  await page.getByTestId('preview-realistic').click();
  await expect(page.getByTestId('ghost-preview')).not.toHaveAttribute('data-rendered-at', '0', { timeout: 30000 });
  const hashes: string[] = [];
  for (let i = 0; i < 2; i++) {
    const [dl] = await Promise.all([page.waitForEvent('download'), page.getByTestId('download-mockup').click()]);
    const buf = fs.readFileSync(await dl.path());
    hashes.push(crypto.createHash('sha256').update(buf).digest('hex'));
  }
  expect(hashes[0]).toBe(hashes[1]);
});

test('note (annotation) and texture layers: add, edit, saved, and appear in the tech pack data', async ({ page, request }) => {
  const id = await createStyle(page, 'tshirt-boxy', 'E2E Notes', 'E2E-NT-1');
  // Annotation.
  await page.getByTestId('add-note').click();
  await clickSvg(page, 650, 500);
  const note = page.getByLabel('Note text', { exact: true });
  await note.fill('Garment-dye after printing');
  await note.press('Tab');
  // Texture on the front body, linked to the shell material.
  await page.keyboard.press('Escape');
  await page.getByTestId('part-body_front').click();
  await page.getByRole('button', { name: 'Customize texture' }).click();
  await page.getByLabel('Texture', { exact: true }).selectOption('slub');
  await page.getByLabel('Texture strength').fill('0.8');
  await waitSaved(page);
  const rec = await getProject(request, id);
  const ann = rec.doc.layers.find((l) => l.type === 'annotation');
  const tex = rec.doc.layers.find((l) => l.type === 'texture');
  expect(ann && ann.type === 'annotation' && ann.text).toBe('Garment-dye after printing');
  expect(tex && tex.type === 'texture' && [tex.textureId, tex.strength, tex.targets, tex.materialId]).toEqual(['slub', 0.8, ['body_front'], rec.doc.materials[0].id]);
  await expect(page.getByTestId('canvas').locator(`g[data-ann-layer=${ann!.id}]`)).toContainText('Garment-dye after printing');
  // The note becomes a numbered callout in the PDF preview.
  const pdf = await request.post(`http://localhost:4100/api/projects/${id}/techpack/preview`);
  expect(pdf.headers()['content-type']).toBe('application/pdf');
  const { readPdf } = await import('../tests/pdfText');
  const pages = await readPdf(await pdf.body());
  expect(pages[1].text).toContain('Garment-dye after printing');
});

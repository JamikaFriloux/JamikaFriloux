import { expect, test, type Page } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import { API } from './fixtures';

/** Automated WCAG 2.1 A/AA scan (axe-core). Covers labels, names, roles, contrast. Not a substitute for a manual audit. */
async function scan(page: Page, name: string) {
  const r = await new AxeBuilder({ page })
    .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
    // Generated SVG drawings are decorative graphics inside a labelled region.
    .exclude('[data-testid=canvas] svg')
    .exclude('.project-card .thumb svg')
    .exclude('.garment-card .views')
    .analyze();
  const serious = r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  const summary = serious.map((v) => `${name}: ${v.id} (${v.impact}) ×${v.nodes.length} — ${v.nodes.slice(0, 3).map((n) => n.target.join(' ')).join(' | ')}`);
  return summary;
}

test('no serious or critical axe violations on the main screens', async ({ page, request }) => {
  const projects = await (await request.get(`${API}/api/projects`)).json();
  const tee = projects.find((p: { styleNumber: string }) => p.styleNumber === 'SC-TS-001');
  const problems: string[] = [];
  await page.goto('/');
  await page.getByTestId('project-card').first().waitFor();
  problems.push(...(await scan(page, 'projects')));
  await page.goto('/new');
  problems.push(...(await scan(page, 'new style')));
  await page.goto(`/p/${tee.id}`);
  await page.getByTestId('canvas').waitFor();
  problems.push(...(await scan(page, 'studio')));
  await page.getByTestId('part-sleeve_left').click();
  problems.push(...(await scan(page, 'studio/part')));
  await page.getByTestId('layers-tab').click();
  await page.locator('[data-layer-type=artwork] button.name').first().click();
  problems.push(...(await scan(page, 'studio/artwork')));
  await page.locator('[data-layer-type=embellishment] button.name').first().click();
  problems.push(...(await scan(page, 'studio/embellishment')));
  await page.locator('[data-layer-type=stitching] button.name').first().click();
  problems.push(...(await scan(page, 'studio/stitching')));
  await page.locator('[data-layer-type=pattern] button.name').first().click();
  problems.push(...(await scan(page, 'studio/pattern')));
  await page.getByTestId('preview-realistic').click();
  problems.push(...(await scan(page, 'studio/realistic')));
  await page.goto(`/p/${tee.id}/measurements`);
  await page.getByTestId('size-table').waitFor();
  problems.push(...(await scan(page, 'measurements')));
  for (const tab of ['assign', 'palette', 'materials', 'colorways', 'bom']) {
    await page.goto(`/p/${tee.id}/materials`);
    await page.getByTestId(`mc-tab-${tab}`).click();
    problems.push(...(await scan(page, `materials/${tab}`)));
  }
  await page.goto(`/p/${tee.id}/techpack`);
  await page.getByTestId('export-draft').waitFor();
  problems.push(...(await scan(page, 'techpack')));
  console.log(problems.join('\n') || 'No serious/critical violations');
  expect(problems).toEqual([]);
});

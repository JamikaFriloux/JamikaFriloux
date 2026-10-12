// Verification helper: screenshot every main screen at 390 px and report horizontal overflow of
// the page AND of its inner scroll container. Usage: node scripts/small-screen-check.mjs <baseUrl> <projectId> <outDir>
import { chromium } from '@playwright/test';
import fs from 'node:fs';
const [base, id, out] = process.argv.slice(2);
fs.mkdirSync(out, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
let bad = 0;
for (const [name, path] of [['projects', '/'], ['studio', `/p/${id}`], ['measurements', `/p/${id}/measurements`], ['materials', `/p/${id}/materials`], ['techpack', `/p/${id}/techpack`]]) {
  await page.goto(base + path, { waitUntil: 'networkidle' });
  await page.waitForTimeout(600);
  const o = await page.evaluate(() => {
    const doc = document.documentElement.scrollWidth - window.innerWidth;
    const pg = document.querySelector('.page');
    return { doc, inner: pg ? pg.scrollWidth - pg.clientWidth : 0 };
  });
  if (o.doc > 0 || o.inner > 0) bad++;
  console.log(`${name}: page overflow ${o.doc}px, inner scroll overflow ${o.inner}px`);
  await page.screenshot({ path: `${out}/390px-${name}.png` });
}
await browser.close();
process.exit(bad ? 1 : 0);

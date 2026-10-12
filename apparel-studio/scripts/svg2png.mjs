// Dev helper: rasterise SVG files with Chromium. Usage: node scripts/svg2png.mjs a.svg [b.svg …] → a.png …
import { chromium } from '@playwright/test';
import fs from 'node:fs';
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 900, height: 900 } });
for (const f of process.argv.slice(2)) {
  await page.setContent(`<body style="margin:0;background:#fff">${fs.readFileSync(f, 'utf8')}</body>`);
  const el = await page.$('svg');
  await el.screenshot({ path: f.replace(/\.svg$/, '.png') });
}
await browser.close();

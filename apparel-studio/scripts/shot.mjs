// Dev helper: screenshot a page. Usage: node scripts/shot.mjs <url> <out.png> [actions-json]
import { chromium } from '@playwright/test';
const [url, out, actions] = process.argv.slice(2);
const browser = await chromium.launch({ executablePath: process.env.CHROME_PATH || '/opt/pw-browsers/chromium' });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const logs = [];
page.on('console', (m) => (m.type() === 'error' || m.type() === 'warning') && logs.push(`${m.type()}: ${m.text()}`));
page.on('pageerror', (e) => logs.push(`pageerror: ${e.message}`));
await page.goto(url, { waitUntil: 'networkidle' });
for (const a of JSON.parse(actions || '[]')) {
  if (a.click) await page.click(a.click);
  if (a.wait) await page.waitForTimeout(a.wait);
  if (a.mouse) { await page.mouse.click(a.mouse[0], a.mouse[1]); }
}
await page.waitForTimeout(800);
await page.screenshot({ path: out });
console.log(logs.join('\n') || 'no console errors');
await browser.close();

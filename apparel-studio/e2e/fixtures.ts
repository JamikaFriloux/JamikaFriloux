import zlib from 'node:zlib';
import type { Page, APIRequestContext } from '@playwright/test';
import type { ProjectRecord } from '../src/shared/schema/project';

function crc32(buf: Buffer): number {
  let crc = 0xffffffff;
  for (let n = 0; n < buf.length; n++) {
    let c = (crc ^ buf[n]) & 0xff;
    for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    crc = (crc >>> 8) ^ c;
  }
  return (crc ^ 0xffffffff) >>> 0;
}

/** Transparent RGBA PNG with a solid square in the middle. */
export function pngLogo(w = 120, h = 60, rgb: [number, number, number] = [220, 40, 60]): Buffer {
  const chunk = (type: string, data: Buffer) => {
    const len = Buffer.alloc(4);
    len.writeUInt32BE(data.length);
    const td = Buffer.concat([Buffer.from(type, 'ascii'), data]);
    const crc = Buffer.alloc(4);
    crc.writeUInt32BE(crc32(td));
    return Buffer.concat([len, td, crc]);
  };
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(w, 0);
  ihdr.writeUInt32BE(h, 4);
  ihdr[8] = 8;
  ihdr[9] = 6;
  const raw = Buffer.alloc((w * 4 + 1) * h);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      const o = y * (w * 4 + 1) + 1 + x * 4;
      const inside = x > w * 0.1 && x < w * 0.9 && y > h * 0.1 && y < h * 0.9;
      raw[o] = rgb[0];
      raw[o + 1] = rgb[1];
      raw[o + 2] = rgb[2];
      raw[o + 3] = inside ? 255 : 0;
    }
  }
  return Buffer.concat([Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]), chunk('IHDR', ihdr), chunk('IDAT', zlib.deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}

export const API = 'http://localhost:4100';

export async function getProject(request: APIRequestContext, id: string): Promise<ProjectRecord> {
  const r = await request.get(`${API}/api/projects/${id}`);
  return r.json();
}

export function projectIdFromUrl(page: Page): string {
  const m = /\/p\/([^/]+)/.exec(page.url());
  if (!m) throw new Error(`Not on a project page: ${page.url()}`);
  return m[1];
}

export async function waitSaved(page: Page) {
  await page.waitForSelector('[data-testid=save-status][data-state=saved]', { timeout: 15000 });
}

export async function createStyle(page: Page, garment: 'tshirt-boxy' | 'hoodie-pullover' | 'sweatpants-straight', name: string, styleNumber: string) {
  await page.goto('/new');
  await page.getByTestId(`garment-${garment}`).click();
  await page.getByLabel('Style name *').fill(name);
  await page.getByLabel('Style number *').fill(styleNumber);
  await page.getByRole('button', { name: /^Create / }).click();
  await page.waitForURL(/\/p\/prj_/);
  await page.getByTestId('canvas').waitFor();
  return projectIdFromUrl(page);
}

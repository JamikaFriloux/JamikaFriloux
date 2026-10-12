/**
 * Render the demo style's tech pack to a PDF without running the server.
 * Usage: npx tsx scripts/sample-techpack.ts out.pdf
 */
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { openDb } from '../src/server/db';
import { LocalFsStorage } from '../src/server/storage';
import { seedDemo } from '../src/server/demo/seed';
import { buildSnapshot } from '../src/server/techpack/revisions';
import { renderTechPackPdf } from '../src/server/techpack/pdf';
import { rowToRecord } from '../src/server/app';

async function main() {
  const out = path.resolve(process.argv[2] ?? 'sample-techpack.pdf');
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'apparel-sample-'));
  const db = openDb(path.join(dir, 'db.sqlite'));
  const storage = new LocalFsStorage(path.join(dir, 'blobs'));
  const ids = await seedDemo(db, storage);
  const which = Number(process.argv[3] ?? 0);
  const rec = rowToRecord(db.prepare('SELECT * FROM projects WHERE id = ?').get(ids[which]) as never);
  const snap = await buildSnapshot(db, storage, rec, { kind: 'draft', notes: 'Sample', number: 1, label: 'R1', mockups: {} });
  fs.writeFileSync(out, await renderTechPackPdf(snap, storage));
  console.log(`Wrote ${out}`);
}
main();

import express from 'express';
import path from 'node:path';
import fs from 'node:fs';
import { openDb } from './db';
import { LocalFsStorage } from './storage';
import { createApp } from './app';
import { seedDemo } from './demo/seed';

const PORT = Number(process.env.PORT ?? 4000);
const DATA_DIR = path.resolve(process.env.DATA_DIR ?? 'data');

async function main() {
  const db = openDb(path.join(DATA_DIR, 'studio.sqlite'));
  const storage = new LocalFsStorage(path.join(DATA_DIR, 'blobs'));
  const count = (db.prepare('SELECT COUNT(*) AS n FROM projects').get() as { n: number }).n;
  if (count === 0 && process.env.NO_DEMO !== '1') {
    const ids = await seedDemo(db, storage);
    console.log(`Seeded ${ids.length} demo project(s).`);
  }
  const app = createApp({ db, storage });
  const dist = path.resolve('dist/client');
  if (process.env.NODE_ENV === 'production' && fs.existsSync(dist)) {
    app.use(express.static(dist));
    app.get(/^(?!\/api\/).*/, (_req, res) => res.sendFile(path.join(dist, 'index.html')));
  }
  app.listen(PORT, () => console.log(`Apparel Studio API on http://localhost:${PORT} (data: ${DATA_DIR})`));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});

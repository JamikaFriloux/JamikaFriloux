import path from 'node:path';
import { openDb } from './db';
import { LocalFsStorage } from './storage';
import { seedDemo } from './demo/seed';

const DATA_DIR = path.resolve(process.env.DATA_DIR ?? 'data');
const db = openDb(path.join(DATA_DIR, 'studio.sqlite'));
const ids = await seedDemo(db, new LocalFsStorage(path.join(DATA_DIR, 'blobs')));
console.log(`Added demo project(s): ${ids.join(', ')}`);

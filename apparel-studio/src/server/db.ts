import Database from 'better-sqlite3';
import fs from 'node:fs';
import path from 'node:path';

export type DB = Database.Database;

const MIGRATIONS: string[] = [
  `CREATE TABLE projects (
     id TEXT PRIMARY KEY,
     name TEXT NOT NULL,
     style_number TEXT NOT NULL,
     collection TEXT NOT NULL DEFAULT '',
     template_id TEXT NOT NULL,
     template_version INTEGER NOT NULL,
     doc TEXT NOT NULL,
     version INTEGER NOT NULL DEFAULT 1,
     archived INTEGER NOT NULL DEFAULT 0,
     created_at TEXT NOT NULL,
     updated_at TEXT NOT NULL
   );
   CREATE TABLE assets (
     id TEXT NOT NULL,
     project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
     kind TEXT NOT NULL,
     role TEXT NOT NULL,
     filename TEXT NOT NULL,
     sha256 TEXT NOT NULL,
     storage_key TEXT NOT NULL,
     width REAL NOT NULL,
     height REAL NOT NULL,
     bytes INTEGER NOT NULL,
     created_at TEXT NOT NULL,
     PRIMARY KEY (project_id, id)
   );
   CREATE INDEX assets_project ON assets(project_id);
   CREATE TABLE revisions (
     id TEXT PRIMARY KEY,
     project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
     number INTEGER NOT NULL,
     label TEXT NOT NULL,
     kind TEXT NOT NULL CHECK (kind IN ('draft','review')),
     notes TEXT NOT NULL DEFAULT '',
     snapshot TEXT NOT NULL,
     snapshot_hash TEXT NOT NULL,
     created_at TEXT NOT NULL,
     UNIQUE(project_id, number)
   );
   CREATE TABLE exports (
     id TEXT PRIMARY KEY,
     revision_id TEXT NOT NULL REFERENCES revisions(id) ON DELETE CASCADE,
     kind TEXT NOT NULL,
     filename TEXT NOT NULL,
     storage_key TEXT,
     status TEXT NOT NULL,
     error TEXT,
     created_at TEXT NOT NULL
   );
   CREATE INDEX exports_revision ON exports(revision_id);
   -- Issued revisions are immutable.
   CREATE TRIGGER revisions_immutable BEFORE UPDATE ON revisions
   BEGIN SELECT RAISE(ABORT, 'revisions are immutable'); END;`,
];

export function openDb(file: string): DB {
  if (file !== ':memory:') fs.mkdirSync(path.dirname(file), { recursive: true });
  const db = new Database(file);
  db.pragma('journal_mode = WAL');
  db.pragma('foreign_keys = ON');
  db.exec('CREATE TABLE IF NOT EXISTS _migrations (n INTEGER PRIMARY KEY)');
  const done = new Set((db.prepare('SELECT n FROM _migrations').all() as { n: number }[]).map((r) => r.n));
  MIGRATIONS.forEach((sql, i) => {
    if (done.has(i)) return;
    db.transaction(() => {
      db.exec(sql);
      db.prepare('INSERT INTO _migrations (n) VALUES (?)').run(i);
    })();
  });
  return db;
}

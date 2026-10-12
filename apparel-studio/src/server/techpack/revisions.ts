import crypto from 'node:crypto';
import type { DB } from '../db';
import type { StorageAdapter } from '../storage';
import type { ExportSummary, ProjectDoc, ProjectRecord, RevisionSummary } from '../../shared/schema/project';
import type { GarmentTemplate } from '../../shared/schema/template';
import { requireTemplate } from '../../shared/templates';
import { computeBom, type BomRow } from '../../shared/domain/bom';
import { validateProject, type Check } from '../../shared/domain/validation';
import { newId } from '../../shared/domain/ids';
import { renderTechPackPdf } from './pdf';
import { bomCsv, measurementsCsv } from './csv';

export interface RevisionSnapshot {
  format: 1;
  projectId: string;
  number: number;
  label: string;
  kind: 'draft' | 'review';
  notes: string;
  issuedAt: string;
  /** Deep copies: later edits to the project or template code cannot change these. */
  doc: ProjectDoc;
  template: GarmentTemplate;
  bom: BomRow[];
  checks: Check[];
  history: { number: number; label: string; kind: 'draft' | 'review'; notes: string; createdAt: string }[];
  /** Content-addressed rendered mockups (sha256), if the renderer supported this garment. */
  mockups: { front?: string; back?: string };
  /** Asset manifest frozen at issue time (content-addressed blobs are never rewritten). */
  assetManifest: { id: string; sha256: string; kind: 'png' | 'svg'; filename: string }[];
}

export class ExportBlockedError extends Error {
  constructor(public failed: Check[]) {
    super(`Ready-for-review export is blocked by ${failed.length} required item(s).`);
  }
}

interface RevisionRow {
  id: string;
  project_id: string;
  number: number;
  label: string;
  kind: 'draft' | 'review';
  notes: string;
  snapshot: string;
  snapshot_hash: string;
  created_at: string;
}

function exportsFor(db: DB, revisionId: string): ExportSummary[] {
  return (db.prepare('SELECT * FROM exports WHERE revision_id = ? ORDER BY created_at, kind').all(revisionId) as {
    id: string;
    kind: ExportSummary['kind'];
    filename: string;
    status: 'ok' | 'failed';
    error: string | null;
    created_at: string;
  }[]).map((e) => ({ id: e.id, kind: e.kind, filename: e.filename, status: e.status, error: e.error, createdAt: e.created_at }));
}

function toSummary(db: DB, r: RevisionRow): RevisionSummary {
  return {
    id: r.id,
    projectId: r.project_id,
    number: r.number,
    label: r.label,
    kind: r.kind,
    notes: r.notes,
    createdAt: r.created_at,
    snapshotHash: r.snapshot_hash,
    exports: exportsFor(db, r.id),
  };
}

export function listRevisions(db: DB, projectId: string): RevisionSummary[] {
  return (db.prepare('SELECT * FROM revisions WHERE project_id = ? ORDER BY number DESC').all(projectId) as RevisionRow[]).map((r) => toSummary(db, r));
}

export function getRevisionRow(db: DB, id: string): { summary: RevisionSummary; snapshot: RevisionSnapshot } | undefined {
  const r = db.prepare('SELECT * FROM revisions WHERE id = ?').get(id) as RevisionRow | undefined;
  if (!r) return undefined;
  return { summary: toSummary(db, r), snapshot: JSON.parse(r.snapshot) };
}

export async function buildSnapshot(
  db: DB,
  storage: StorageAdapter,
  rec: ProjectRecord,
  opts: { kind: 'draft' | 'review'; notes: string; number: number; label: string; mockups: { front?: string; back?: string } },
): Promise<RevisionSnapshot> {
  const template = requireTemplate(rec.doc.template.id, rec.doc.template.version);
  const doc = structuredClone(rec.doc);
  // Every referenced asset must still exist in storage, or the export would silently drop artwork.
  const missing: string[] = [];
  for (const a of doc.assets) if (!(await storage.exists(a.sha256))) missing.push(a.filename);
  if (missing.length) {
    throw Object.assign(new Error(`These uploaded files are missing from storage: ${missing.join(', ')}. Re-upload them before exporting.`), { status: 422 });
  }
  for (const k of ['front', 'back'] as const) {
    const sha = opts.mockups[k];
    if (sha && !(await storage.exists(sha))) throw Object.assign(new Error(`The ${k} mockup render was not uploaded. Re-render the mockup and export again.`), { status: 422 });
  }
  const prior = (db.prepare('SELECT number, label, kind, notes, created_at FROM revisions WHERE project_id = ? ORDER BY number').all(rec.id) as {
    number: number;
    label: string;
    kind: 'draft' | 'review';
    notes: string;
    created_at: string;
  }[]).map((r) => ({ number: r.number, label: r.label, kind: r.kind, notes: r.notes, createdAt: r.created_at }));
  const issuedAt = new Date().toISOString();
  return {
    format: 1,
    projectId: rec.id,
    number: opts.number,
    label: opts.label,
    kind: opts.kind,
    notes: opts.notes,
    issuedAt,
    doc,
    template: structuredClone(template),
    bom: computeBom(doc, template),
    checks: validateProject(doc, template).checks,
    history: [...prior, { number: opts.number, label: opts.label, kind: opts.kind, notes: opts.notes, createdAt: issuedAt }],
    mockups: opts.mockups,
    assetManifest: doc.assets.map((a) => ({ id: a.id, sha256: a.sha256, kind: a.kind, filename: a.filename })),
  };
}

function safeName(s: string) {
  return s.replace(/[^A-Za-z0-9._-]+/g, '_').slice(0, 60);
}

/** Generate all export files for a revision from its snapshot (idempotent; replaces previous export rows). */
export async function regenerateExports(db: DB, storage: StorageAdapter, revisionId: string, snap: RevisionSnapshot): Promise<ExportSummary[]> {
  const base = `${safeName(snap.doc.styleNumber)}_${snap.label}`;
  const jobs: { kind: ExportSummary['kind']; filename: string; make: () => Promise<Buffer> }[] = [
    { kind: 'pdf', filename: `${base}_techpack${snap.kind === 'draft' ? '_DRAFT' : ''}.pdf`, make: () => renderTechPackPdf(snap, storage) },
    { kind: 'bom-csv', filename: `${base}_BOM.csv`, make: async () => Buffer.from(bomCsv(snap), 'utf8') },
    { kind: 'measurements-csv', filename: `${base}_measurements.csv`, make: async () => Buffer.from(measurementsCsv(snap), 'utf8') },
  ];
  for (const k of ['front', 'back'] as const) {
    const sha = snap.mockups[k];
    if (sha) jobs.push({ kind: 'mockup-png', filename: `${base}_mockup_${k}.png`, make: () => storage.get(sha) });
  }
  db.prepare('DELETE FROM exports WHERE revision_id = ?').run(revisionId);
  const ins = db.prepare('INSERT INTO exports (id, revision_id, kind, filename, storage_key, status, error, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)');
  for (const j of jobs) {
    const ts = new Date().toISOString();
    try {
      const buf = await j.make();
      const { key } = await storage.put(buf);
      ins.run(newId('exp'), revisionId, j.kind, j.filename, key, 'ok', null, ts);
    } catch (e) {
      const msg = e instanceof Error ? e.message : String(e);
      console.error(`Export ${j.kind} failed for revision ${revisionId}:`, e);
      ins.run(newId('exp'), revisionId, j.kind, j.filename, null, 'failed', `${j.kind.toUpperCase()} generation failed: ${msg}`, ts);
    }
  }
  return exportsFor(db, revisionId);
}

export async function issueRevision(
  db: DB,
  storage: StorageAdapter,
  rec: ProjectRecord,
  opts: { kind: 'draft' | 'review'; notes: string; mockups: { front?: string; back?: string } },
): Promise<RevisionSummary & { blocked?: false }> {
  const template = requireTemplate(rec.doc.template.id, rec.doc.template.version);
  const v = validateProject(rec.doc, template);
  if (!v.canExport(opts.kind)) throw new ExportBlockedError(v.failedRequired);
  const next = ((db.prepare('SELECT MAX(number) AS n FROM revisions WHERE project_id = ?').get(rec.id) as { n: number | null }).n ?? 0) + 1;
  const snap = await buildSnapshot(db, storage, rec, { ...opts, number: next, label: `R${next}` });
  const json = JSON.stringify(snap);
  const hash = crypto.createHash('sha256').update(json).digest('hex');
  const id = newId('rev');
  db.prepare('INSERT INTO revisions (id, project_id, number, label, kind, notes, snapshot, snapshot_hash, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)').run(
    id,
    rec.id,
    next,
    snap.label,
    opts.kind,
    opts.notes,
    json,
    hash,
    snap.issuedAt,
  );
  await regenerateExports(db, storage, id, snap);
  return toSummary(db, db.prepare('SELECT * FROM revisions WHERE id = ?').get(id) as RevisionRow);
}

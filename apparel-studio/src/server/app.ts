import express, { type NextFunction, type Request, type Response } from 'express';
import multer from 'multer';
import { z } from 'zod';
import type { DB } from './db';
import type { StorageAdapter } from './storage';
import { inspectPng, sanitizeSvg, UploadError } from './sanitize';
import { projectDocSchema, type AssetRef, type ProjectDoc, type ProjectRecord, type ProjectSummary } from '../shared/schema/project';
import { getTemplate, listTemplates, requireTemplate } from '../shared/templates';
import { createProjectDoc } from '../shared/domain/factory';
import { newId } from '../shared/domain/ids';
import { validateProject } from '../shared/domain/validation';
import { computeBom } from '../shared/domain/bom';
import { issueRevision, listRevisions, getRevisionRow, regenerateExports, buildSnapshot, ExportBlockedError } from './techpack/revisions';
import { renderTechPackPdf } from './techpack/pdf';

export interface AppDeps {
  db: DB;
  storage: StorageAdapter;
}

export class HttpError extends Error {
  constructor(public status: number, message: string, public details?: unknown) {
    super(message);
  }
}

const now = () => new Date().toISOString();

interface ProjectRow {
  id: string;
  name: string;
  style_number: string;
  collection: string;
  template_id: string;
  template_version: number;
  doc: string;
  version: number;
  archived: number;
  created_at: string;
  updated_at: string;
}

export function rowToRecord(r: ProjectRow): ProjectRecord {
  return { id: r.id, doc: JSON.parse(r.doc), version: r.version, createdAt: r.created_at, updatedAt: r.updated_at, archived: !!r.archived };
}

/** Schema + referential integrity checks beyond Zod (template, ids, references). */
export function checkDocIntegrity(doc: ProjectDoc): string[] {
  const errors: string[] = [];
  const template = getTemplate(doc.template.id, doc.template.version);
  if (!template) return [`Template ${doc.template.id} v${doc.template.version} is not installed.`];
  const compIds = new Set(template.components.map((c) => c.id));
  const seamIds = new Set(template.views.flatMap((v) => v.seams.map((s) => s.id)));
  const layerIds = new Set<string>();
  const colorIds = new Set(doc.colors.map((c) => c.id));
  const matIds = new Set(doc.materials.map((m) => m.id));
  for (const l of doc.layers) {
    if (layerIds.has(l.id)) errors.push(`Duplicate layer id ${l.id}`);
    layerIds.add(l.id);
    for (const t of l.targets) if (!compIds.has(t)) errors.push(`Layer “${l.name}” targets unknown component “${t}”.`);
    if (l.type === 'panelFill') {
      if (l.targets.length !== 1) errors.push(`Panel color layer “${l.name}” must target exactly one component.`);
      if (!colorIds.has(l.colorId)) errors.push(`Panel color layer “${l.name}” references a missing colour.`);
      if (l.materialId && !matIds.has(l.materialId)) errors.push(`Panel color layer “${l.name}” references a missing material.`);
    }
    if (l.type === 'stitching') for (const s of l.seamIds) if (!seamIds.has(s)) errors.push(`Stitching “${l.name}” references unknown seam “${s}”.`);
    if (l.type === 'artwork' && l.view === 'all') errors.push(`Artwork “${l.name}” must belong to one view (front or back).`);
  }
  const sizes = new Set(template.sizes.available);
  for (const s of doc.sizes.range) if (!sizes.has(s)) errors.push(`Size ${s} is not available for this template.`);
  return errors;
}

const createSchema = z.object({
  templateId: z.string(),
  templateVersion: z.number().int().optional(),
  name: z.string().min(1).max(120),
  styleNumber: z.string().min(1).max(40),
  season: z.string().max(40).optional(),
  collection: z.string().max(80).optional(),
});

export function createApp({ db, storage }: AppDeps) {
  const app = express();
  app.use(express.json({ limit: '20mb' }));
  const upload = multer({ storage: multer.memoryStorage(), limits: { fileSize: 15 * 1024 * 1024 } });

  const getRow = (id: string) => {
    const r = db.prepare('SELECT * FROM projects WHERE id = ?').get(id) as ProjectRow | undefined;
    if (!r) throw new HttpError(404, 'Project not found. It may have been deleted.');
    return r;
  };

  const wrap = (fn: (req: Request, res: Response) => unknown) => (req: Request, res: Response, next: NextFunction) => {
    Promise.resolve(fn(req, res)).catch(next);
  };

  app.get('/api/health', (_req, res) => res.json({ ok: true }));

  // ---- Templates
  app.get('/api/templates', (_req, res) => res.json(listTemplates()));
  app.get('/api/templates/:id/:version', (req, res) => {
    const t = getTemplate(req.params.id, Number(req.params.version));
    if (!t) return res.status(404).json({ error: 'Template not found' });
    res.json(t);
  });

  // ---- Projects
  app.get('/api/projects', (req, res) => {
    const archived = req.query.archived === '1' ? 1 : 0;
    const rows = db
      .prepare(
        `SELECT p.id, p.name, p.style_number, p.collection, p.template_id, p.template_version, p.updated_at, p.archived,
                (SELECT COUNT(*) FROM revisions r WHERE r.project_id = p.id) AS revision_count
         FROM projects p WHERE p.archived = ? ORDER BY p.collection, p.updated_at DESC`,
      )
      .all(archived) as (ProjectRow & { revision_count: number })[];
    const out: ProjectSummary[] = rows.map((r) => ({
      id: r.id,
      name: r.name,
      styleNumber: r.style_number,
      collection: r.collection,
      templateId: r.template_id,
      templateVersion: r.template_version,
      updatedAt: r.updated_at,
      archived: !!r.archived,
      revisionCount: r.revision_count,
    }));
    res.json(out);
  });

  const insertProject = (doc: ProjectDoc): ProjectRecord => {
    const id = newId('prj');
    const ts = now();
    db.prepare(
      `INSERT INTO projects (id, name, style_number, collection, template_id, template_version, doc, version, archived, created_at, updated_at)
       VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)`,
    ).run(id, doc.name, doc.styleNumber, doc.collection, doc.template.id, doc.template.version, JSON.stringify(doc), ts, ts);
    return rowToRecord(getRow(id));
  };

  app.post('/api/projects', (req, res) => {
    const input = createSchema.parse(req.body);
    const template = input.templateVersion
      ? getTemplate(input.templateId, input.templateVersion)
      : listTemplates().find((t) => t.id === input.templateId);
    if (!template) throw new HttpError(400, `Unknown garment template “${input.templateId}”.`);
    const doc = createProjectDoc(template, input);
    res.status(201).json(insertProject(projectDocSchema.parse(doc)));
  });

  app.get('/api/projects/:id', (req, res) => res.json(rowToRecord(getRow(req.params.id))));

  app.put('/api/projects/:id', (req, res) => {
    const row = getRow(req.params.id);
    const body = z.object({ doc: z.unknown(), version: z.number().int() }).parse(req.body);
    const parsed = projectDocSchema.safeParse(body.doc);
    if (!parsed.success) throw new HttpError(422, 'Project data failed validation and was not saved.', parsed.error.issues.slice(0, 20));
    const doc = parsed.data;
    if (doc.template.id !== row.template_id || doc.template.version !== row.template_version) {
      throw new HttpError(422, 'A project cannot switch garment templates. Create a new style instead.');
    }
    const integrity = checkDocIntegrity(doc);
    if (integrity.length) throw new HttpError(422, 'Project data has broken references and was not saved.', integrity);
    const ts = now();
    const result = db
      .prepare(
        `UPDATE projects SET doc = ?, name = ?, style_number = ?, collection = ?, version = version + 1, updated_at = ?
         WHERE id = ? AND version = ?`,
      )
      .run(JSON.stringify(doc), doc.name, doc.styleNumber, doc.collection, ts, row.id, body.version);
    if (result.changes === 0) {
      throw new HttpError(409, 'This style was changed in another tab or window. Reload to get the latest version.', { currentVersion: getRow(row.id).version });
    }
    res.json({ version: body.version + 1, updatedAt: ts });
  });

  app.patch('/api/projects/:id', (req, res) => {
    const row = getRow(req.params.id);
    const body = z.object({ archived: z.boolean() }).parse(req.body);
    db.prepare('UPDATE projects SET archived = ? WHERE id = ?').run(body.archived ? 1 : 0, row.id);
    res.json(rowToRecord(getRow(row.id)));
  });

  app.delete('/api/projects/:id', (req, res) => {
    const row = getRow(req.params.id);
    db.prepare('DELETE FROM projects WHERE id = ?').run(row.id);
    res.status(204).end();
  });

  app.post('/api/projects/:id/duplicate', (req, res) => {
    const row = getRow(req.params.id);
    const body = z.object({ name: z.string().min(1).max(120).optional(), styleNumber: z.string().min(1).max(40).optional() }).parse(req.body ?? {});
    const src = JSON.parse(row.doc) as ProjectDoc;
    const doc: ProjectDoc = { ...src, name: body.name ?? `${src.name} (copy)`, styleNumber: body.styleNumber ?? `${src.styleNumber}-COPY` };
    const rec = insertProject(projectDocSchema.parse(doc));
    // Copy asset rows (blobs are content-addressed, so nothing is duplicated on disk).
    const assets = db.prepare('SELECT * FROM assets WHERE project_id = ?').all(row.id) as Record<string, unknown>[];
    const ins = db.prepare(
      'INSERT INTO assets (id, project_id, kind, role, filename, sha256, storage_key, width, height, bytes, created_at) VALUES (@id, @project_id, @kind, @role, @filename, @sha256, @storage_key, @width, @height, @bytes, @created_at)',
    );
    for (const a of assets) ins.run({ ...a, project_id: rec.id });
    res.status(201).json(rec);
  });

  // ---- Assets
  app.post('/api/projects/:id/assets', upload.single('file'), wrap(async (req, res) => {
    const row = getRow(req.params.id);
    const file = req.file;
    if (!file) throw new HttpError(400, 'No file received. Choose a PNG or SVG file.');
    const role = z.enum(['artwork', 'pattern-tile', 'label', 'reference']).parse(req.body.role ?? 'artwork');
    const name = file.originalname.slice(0, 200);
    let data: Buffer;
    let kind: AssetRef['kind'];
    let width: number;
    let height: number;
    const warnings: string[] = [];
    const isSvg = /\.svg$/i.test(name) || file.mimetype === 'image/svg+xml';
    try {
      if (isSvg) {
        const s = sanitizeSvg(file.buffer);
        data = Buffer.from(s.svg, 'utf8');
        kind = 'svg';
        width = s.width;
        height = s.height;
        if (s.removed > 0) warnings.push(`Removed ${s.removed} unsafe or unsupported SVG element(s)/attribute(s) (scripts, external links, etc.).`);
      } else {
        const info = inspectPng(file.buffer);
        data = file.buffer;
        kind = 'png';
        width = info.width;
        height = info.height;
        if (!info.hasAlpha) warnings.push('This PNG has no transparency, so its background will print as a solid box. Export with a transparent background if that is not intended.');
      }
    } catch (e) {
      if (e instanceof UploadError) throw new HttpError(e.status, e.message);
      throw e;
    }
    const { key, sha256 } = await storage.put(data);
    const asset: AssetRef = { id: newId('ast'), kind, role, filename: name, sha256, width, height, bytes: data.length };
    db.prepare(
      'INSERT INTO assets (id, project_id, kind, role, filename, sha256, storage_key, width, height, bytes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
    ).run(asset.id, row.id, kind, role, name, sha256, key, width, height, data.length, now());
    res.status(201).json({ asset, warnings });
  }));

  app.get('/api/blobs/:sha', wrap(async (req, res) => {
    const sha = req.params.sha;
    if (!/^[0-9a-f]{64}$/.test(sha)) throw new HttpError(400, 'Invalid file id');
    const meta = db.prepare('SELECT kind FROM assets WHERE sha256 = ? LIMIT 1').get(sha) as { kind: string } | undefined;
    if (!(await storage.exists(sha))) throw new HttpError(404, 'File is missing from storage. Re-upload it.');
    const data = await storage.get(sha);
    const isSvg = meta?.kind === 'svg' || data.subarray(0, 200).toString('utf8').includes('<svg');
    res.setHeader('Content-Type', isSvg ? 'image/svg+xml' : 'image/png');
    res.setHeader('X-Content-Type-Options', 'nosniff');
    res.setHeader('Content-Security-Policy', "default-src 'none'; style-src 'unsafe-inline'; img-src data:");
    res.setHeader('Cache-Control', 'public, max-age=31536000, immutable');
    res.send(data);
  }));

  // Upload a rendered mockup PNG (client-side deterministic renderer) for inclusion in a revision.
  app.post('/api/projects/:id/mockups', upload.single('file'), wrap(async (req, res) => {
    getRow(req.params.id);
    if (!req.file) throw new HttpError(400, 'No mockup image received.');
    try {
      inspectPng(req.file.buffer);
    } catch (e) {
      if (e instanceof UploadError) throw new HttpError(400, `Mockup render is not a valid PNG: ${e.message}`);
      throw e;
    }
    const { sha256 } = await storage.put(req.file.buffer);
    res.status(201).json({ sha256 });
  }));

  // ---- Derived data
  app.get('/api/projects/:id/validation', (req, res) => {
    const rec = rowToRecord(getRow(req.params.id));
    const v = validateProject(rec.doc, requireTemplate(rec.doc.template.id, rec.doc.template.version));
    res.json({ checks: v.checks, canExportDraft: v.canExport('draft'), canExportReview: v.canExport('review') });
  });
  app.get('/api/projects/:id/bom', (req, res) => {
    const rec = rowToRecord(getRow(req.params.id));
    res.json(computeBom(rec.doc, requireTemplate(rec.doc.template.id, rec.doc.template.version)));
  });

  // ---- Revisions & exports
  app.get('/api/projects/:id/revisions', (req, res) => {
    getRow(req.params.id);
    res.json(listRevisions(db, req.params.id));
  });

  app.post('/api/projects/:id/revisions', wrap(async (req, res) => {
    const row = getRow(req.params.id);
    const body = z
      .object({
        kind: z.enum(['draft', 'review']),
        notes: z.string().max(2000).default(''),
        expectedVersion: z.number().int().optional(),
        mockups: z.object({ front: z.string().regex(/^[0-9a-f]{64}$/).optional(), back: z.string().regex(/^[0-9a-f]{64}$/).optional() }).default({}),
      })
      .parse(req.body);
    if (body.expectedVersion !== undefined && body.expectedVersion !== row.version) {
      throw new HttpError(409, 'There are unsaved or newer changes. Wait for “Saved” and export again so the revision matches what you see.');
    }
    const rec = rowToRecord(row);
    const result = await issueRevision(db, storage, rec, body);
    res.status(201).json(result);
  }));

  app.get('/api/revisions/:rid', (req, res) => {
    const r = getRevisionRow(db, req.params.rid);
    if (!r) throw new HttpError(404, 'Revision not found');
    res.json({ ...r.summary, snapshot: r.snapshot });
  });

  app.post('/api/revisions/:rid/exports/retry', wrap(async (req, res) => {
    const r = getRevisionRow(db, req.params.rid);
    if (!r) throw new HttpError(404, 'Revision not found');
    res.json(await regenerateExports(db, storage, r.summary.id, r.snapshot));
  }));

  app.get('/api/exports/:eid/download', wrap(async (req, res) => {
    const e = db.prepare('SELECT * FROM exports WHERE id = ?').get(req.params.eid) as
      | { kind: string; filename: string; storage_key: string | null; status: string; error: string | null }
      | undefined;
    if (!e) throw new HttpError(404, 'Export not found');
    if (e.status !== 'ok' || !e.storage_key) throw new HttpError(409, `This export failed: ${e.error ?? 'unknown error'}. Use “Retry exports”.`);
    if (!(await storage.exists(e.storage_key))) throw new HttpError(410, 'The exported file is missing from storage. Use “Retry exports” to regenerate it from the revision snapshot.');
    const types: Record<string, string> = { pdf: 'application/pdf', 'bom-csv': 'text/csv', 'measurements-csv': 'text/csv', 'mockup-png': 'image/png' };
    res.setHeader('Content-Type', types[e.kind] ?? 'application/octet-stream');
    res.setHeader('Content-Disposition', `${req.query.inline ? 'inline' : 'attachment'}; filename="${e.filename.replace(/"/g, '')}"`);
    res.send(await storage.get(e.storage_key));
  }));

  // Unsaved preview of the tech pack from the current project state (not a revision).
  app.post('/api/projects/:id/techpack/preview', wrap(async (req, res) => {
    const rec = rowToRecord(getRow(req.params.id));
    const snap = await buildSnapshot(db, storage, rec, { kind: 'draft', notes: 'Preview — not issued', number: 0, label: 'PREVIEW', mockups: {} });
    const pdf = await renderTechPackPdf(snap, storage);
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Disposition', 'inline; filename="preview.pdf"');
    res.send(pdf);
  }));

  // ---- Errors
  app.use('/api', (_req, _res, next) => next(new HttpError(404, 'Unknown API route')));
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  app.use((err: unknown, _req: Request, res: Response, _next: NextFunction) => {
    if (err instanceof HttpError) return res.status(err.status).json({ error: err.message, details: err.details });
    if (err instanceof ExportBlockedError) return res.status(422).json({ error: err.message, details: err.failed });
    if (err && typeof err === 'object' && typeof (err as { status?: unknown }).status === 'number' && err instanceof Error) {
      return res.status((err as unknown as { status: number }).status).json({ error: err.message });
    }
    if (err instanceof z.ZodError) return res.status(400).json({ error: 'Invalid request', details: err.issues.slice(0, 20) });
    if (err && typeof err === 'object' && 'code' in err && (err as { code: string }).code === 'LIMIT_FILE_SIZE') {
      return res.status(413).json({ error: 'File is larger than 15 MB.' });
    }
    console.error(err);
    res.status(500).json({ error: err instanceof Error ? err.message : 'Unexpected server error' });
  });
  return app;
}

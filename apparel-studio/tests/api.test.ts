import { describe, expect, it, beforeAll } from 'vitest';
import request from 'supertest';
import { makePng, makeTestApp } from './helpers';
import { readPdf, textOverlaps } from './pdfText';
import { seedDemo } from '../src/server/demo/seed';
import type { ProjectDoc, ProjectRecord } from '../src/shared/schema/project';
import { requireTemplate } from '../src/shared/templates';
import { makeArtworkLayer } from '../src/shared/domain/layers';
import { applyEnteredPlacement } from '../src/shared/domain/placement';

const tee = requireTemplate('tshirt-boxy', 1);

async function create(app: ReturnType<typeof makeTestApp>['app']) {
  const res = await request(app).post('/api/projects').send({ templateId: 'tshirt-boxy', name: 'API tee', styleNumber: 'API-1' }).expect(201);
  return res.body as ProjectRecord;
}

async function save(app: ReturnType<typeof makeTestApp>['app'], rec: ProjectRecord, doc: ProjectDoc) {
  const res = await request(app).put(`/api/projects/${rec.id}`).send({ doc, version: rec.version });
  if (res.status === 200) rec.version = res.body.version;
  return res;
}

describe('projects API', () => {
  const t = makeTestApp();

  it('creates, saves and reloads with optimistic concurrency', async () => {
    const rec = await create(t.app);
    expect(rec.version).toBe(1);
    const doc = structuredClone(rec.doc);
    doc.name = 'Renamed';
    const stale = rec.version;
    await save(t.app, rec, doc).then((r) => expect(r.status).toBe(200));
    const again = await request(t.app).put(`/api/projects/${rec.id}`).send({ doc, version: stale });
    expect(again.status).toBe(409);
    expect(again.body.error).toMatch(/another tab/);
    const loaded = (await request(t.app).get(`/api/projects/${rec.id}`).expect(200)).body as ProjectRecord;
    expect(loaded.doc.name).toBe('Renamed');
  });

  it('rejects invalid documents and broken references with actionable messages', async () => {
    const rec = await create(t.app);
    const bad = structuredClone(rec.doc) as unknown as { layers: unknown[] };
    bad.layers.push({ id: 'x', type: 'sparkles', name: 'nope', view: 'front', targets: [] });
    const r1 = await save(t.app, rec, bad as unknown as ProjectDoc);
    expect(r1.status).toBe(422);
    const broken = structuredClone(rec.doc);
    (broken.layers[0] as { targets: string[] }).targets = ['hood'];
    const r2 = await save(t.app, rec, broken);
    expect(r2.status).toBe(422);
    expect(JSON.stringify(r2.body.details)).toMatch(/unknown component/);
  });

  it('uploads PNG and sanitized SVG; artwork survives save and reload', async () => {
    const rec = await create(t.app);
    const png = await request(t.app).post(`/api/projects/${rec.id}/assets`).field('role', 'artwork').attach('file', makePng(64, 32), 'logo.png').expect(201);
    expect(png.body.asset.width).toBe(64);
    expect(png.body.warnings).toEqual([]);
    const flat = await request(t.app).post(`/api/projects/${rec.id}/assets`).attach('file', makePng(10, 10, false), 'flat.png').expect(201);
    expect(flat.body.warnings[0]).toMatch(/no transparency/);
    const svg = await request(t.app)
      .post(`/api/projects/${rec.id}/assets`)
      .attach('file', Buffer.from('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 10" onload="x()"><script>1</script><rect width="20" height="10"/></svg>'), 'mark.svg')
      .expect(201);
    expect(svg.body.warnings[0]).toMatch(/Removed/);
    const blob = await request(t.app).get(`/api/blobs/${svg.body.asset.sha256}`).expect(200);
    expect(blob.headers['content-security-policy']).toContain("default-src 'none'");
    expect(blob.body.toString()).not.toMatch(/script|onload/);

    const doc = structuredClone(rec.doc);
    doc.assets.push(png.body.asset, svg.body.asset);
    let layer = makeArtworkLayer(tee, png.body.asset, { viewId: 'front', anchorId: 'center_chest', widthMm: 200 });
    layer = applyEnteredPlacement(tee, layer, { widthMm: 220, offsetYmm: 15 });
    layer.mask = [{ mode: 'erase', view: 'front', width: 20, points: [500, 300, 520, 310] }];
    doc.layers.push(layer);
    expect((await save(t.app, rec, doc)).status).toBe(200);
    const loaded = (await request(t.app).get(`/api/projects/${rec.id}`).expect(200)).body as ProjectRecord;
    expect(loaded.doc.layers.at(-1)).toEqual(layer);
    expect(loaded.doc.assets.map((a) => a.id)).toEqual([png.body.asset.id, svg.body.asset.id]);
  });

  it('rejects non-PNG binaries posing as PNG', async () => {
    const rec = await create(t.app);
    const r = await request(t.app).post(`/api/projects/${rec.id}/assets`).attach('file', Buffer.from('GIF89a........'), 'fake.png');
    expect(r.status).toBe(400);
    expect(r.body.error).toMatch(/not a valid PNG/);
  });

  it('duplicates a style including its asset references', async () => {
    const rec = await create(t.app);
    await request(t.app).post(`/api/projects/${rec.id}/assets`).attach('file', makePng(8, 8), 'a.png').expect(201);
    const dup = (await request(t.app).post(`/api/projects/${rec.id}/duplicate`).send({}).expect(201)).body as ProjectRecord;
    expect(dup.id).not.toBe(rec.id);
    expect(dup.doc.styleNumber).toBe('API-1-COPY');
  });
});

describe('revisions and exports', () => {
  const t = makeTestApp();
  let projectId = '';
  beforeAll(async () => {
    [projectId] = await seedDemo(t.db, t.storage);
  });

  it('draft export allows incomplete specs and lists open items; review is blocked with details', async () => {
    const blocked = await request(t.app).post(`/api/projects/${projectId}/revisions`).send({ kind: 'review', notes: '' });
    expect(blocked.status).toBe(422);
    expect(blocked.body.details.some((c: { id: string }) => c.id.startsWith('measurements.confirmed'))).toBe(true);
    const draft = await request(t.app).post(`/api/projects/${projectId}/revisions`).send({ kind: 'draft', notes: 'First draft' }).expect(201);
    expect(draft.body.label).toBe('R1');
    expect(draft.body.exports.map((e: { kind: string }) => e.kind).sort()).toEqual(['bom-csv', 'measurements-csv', 'pdf']);
    expect(draft.body.exports.every((e: { status: string }) => e.status === 'ok')).toBe(true);
  });

  it('produces a readable PDF: every page has style, revision and page number; no text outside the page', async () => {
    const revs = (await request(t.app).get(`/api/projects/${projectId}/revisions`).expect(200)).body;
    const pdfExport = revs[0].exports.find((e: { kind: string }) => e.kind === 'pdf');
    const pdf = await request(t.app).get(`/api/exports/${pdfExport.id}/download`).buffer(true).parse((res, cb) => {
      const chunks: Buffer[] = [];
      res.on('data', (c: Buffer) => chunks.push(c));
      res.on('end', () => cb(null, Buffer.concat(chunks)));
    });
    expect(pdf.headers['content-type']).toBe('application/pdf');
    const pages = await readPdf(pdf.body as Buffer);
    expect(pages.length).toBeGreaterThanOrEqual(9);
    pages.forEach((p, i) => {
      expect(p.text).toContain('SC-TS-001');
      expect(p.text).toContain(`Page ${i + 1} of ${pages.length}`);
      expect(p.text).toContain('Rev R1');
      expect(textOverlaps(p), `page ${i + 1} has overlapping text`).toEqual([]);
      for (const it of p.items) {
        if (!it.str.trim()) continue;
        expect(it.x).toBeGreaterThanOrEqual(0);
        expect(it.x + it.w).toBeLessThanOrEqual(p.width + 0.5);
        expect(it.y).toBeGreaterThanOrEqual(0);
        expect(it.y + it.h).toBeLessThanOrEqual(p.height + 0.5);
      }
    });
    const all = pages.map((p) => p.text).join('\n');
    for (const section of ['Technical flats', 'Colorways', 'Materials & bill of materials', 'Artwork, placement', 'Measurement diagrams', 'Size specification', 'Construction notes', 'Labels & packaging', 'Revision history', 'Open items']) {
      expect(all).toContain(section);
    }
    expect(all).not.toMatch(/manufacturer[- ]approved/i);
  });

  it('issued revisions are immutable: later edits do not change the snapshot or files', async () => {
    const revs = (await request(t.app).get(`/api/projects/${projectId}/revisions`).expect(200)).body;
    const r1 = (await request(t.app).get(`/api/revisions/${revs[0].id}`).expect(200)).body;
    const csvBefore = (await request(t.app).get(`/api/exports/${r1.exports.find((e: { kind: string }) => e.kind === 'bom-csv').id}/download`).expect(200)).text;

    const rec = (await request(t.app).get(`/api/projects/${projectId}`).expect(200)).body as ProjectRecord;
    const doc = structuredClone(rec.doc);
    doc.name = 'Changed after issue';
    doc.materials[0].name = 'Changed material';
    const emb = doc.layers.find((l) => l.type === 'embellishment');
    if (emb && emb.type === 'embellishment') emb.points.push({ x: 520, y: 260 });
    await request(t.app).put(`/api/projects/${projectId}`).send({ doc, version: rec.version }).expect(200);

    const r1Again = (await request(t.app).get(`/api/revisions/${revs[0].id}`).expect(200)).body;
    expect(r1Again.snapshot).toEqual(r1.snapshot);
    expect(r1Again.snapshotHash).toBe(r1.snapshotHash);
    expect(r1Again.snapshot.doc.name).toBe('Sunset Club Boxy Tee (demo)');
    const csvAfter = (await request(t.app).get(`/api/exports/${r1.exports.find((e: { kind: string }) => e.kind === 'bom-csv').id}/download`).expect(200)).text;
    expect(csvAfter).toBe(csvBefore);
    expect(() => t.db.prepare("UPDATE revisions SET notes = 'x' WHERE id = ?").run(revs[0].id)).toThrow(/immutable/);
  });

  it('review export succeeds once required items are complete', async () => {
    const rec = (await request(t.app).get(`/api/projects/${projectId}`).expect(200)).body as ProjectRecord;
    const doc = structuredClone(rec.doc);
    for (const p of doc.measurements) p.confirmed = true;
    for (const l of doc.layers) if (l.type === 'artwork') l.placement.source = 'entered';
    doc.materials.forEach((m) => {
      if (!m.weight) m.weight = { value: 200, unit: 'gsm' };
      if (!m.composition) m.composition = '100% cotton';
    });
    await request(t.app).put(`/api/projects/${projectId}`).send({ doc, version: rec.version }).expect(200);
    const v = (await request(t.app).get(`/api/projects/${projectId}/validation`).expect(200)).body;
    expect(v.checks.filter((c: { passed: boolean; level: string }) => !c.passed && c.level === 'required')).toEqual([]);
    const rev = await request(t.app).post(`/api/projects/${projectId}/revisions`).send({ kind: 'review', notes: 'For sampling' }).expect(201);
    expect(rev.body.label).toBe('R2');
    expect(rev.body.kind).toBe('review');
  });

  it('missing asset files produce an actionable export error', async () => {
    const rec = (await request(t.app).get(`/api/projects/${projectId}`).expect(200)).body as ProjectRecord;
    const doc = structuredClone(rec.doc);
    doc.assets[0] = { ...doc.assets[0], sha256: 'f'.repeat(64) };
    await request(t.app).put(`/api/projects/${projectId}`).send({ doc, version: rec.version }).expect(200);
    const r = await request(t.app).post(`/api/projects/${projectId}/revisions`).send({ kind: 'draft' });
    expect(r.status).toBe(422);
    expect(r.body.error).toMatch(/missing from storage.*Re-upload/);
  });

  it('CSV exports guard against formula injection and keep canonical values', async () => {
    const revs = (await request(t.app).get(`/api/projects/${projectId}/revisions`).expect(200)).body;
    const m = revs[0].exports.find((e: { kind: string }) => e.kind === 'measurements-csv');
    const csv = (await request(t.app).get(`/api/exports/${m.id}/download`).expect(200)).text;
    expect(csv).toContain('Body length from HPS');
    expect(csv).toContain('70'); // 700 mm shown in cm
  });
});

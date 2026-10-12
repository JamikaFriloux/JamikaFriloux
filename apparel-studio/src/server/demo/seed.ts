import type { DB } from '../db';
import type { StorageAdapter } from '../storage';
import { sanitizeSvg } from '../sanitize';
import { projectDocSchema, type AssetRef, type ProjectDoc } from '../../shared/schema/project';
import { listTemplates } from '../../shared/templates';
import { createProjectDoc } from '../../shared/domain/factory';
import { newId } from '../../shared/domain/ids';
import { makeArtworkLayer, makeEmbellishmentLayer, makePatternLayer, makeStitchingLayer } from '../../shared/domain/layers';
import { applyEnteredPlacement } from '../../shared/domain/placement';
import { DEMO_BACK_SVG, DEMO_LOGO_SVG, DEMO_TILE_SVG } from './assets';

async function addSvgAsset(db: DB, storage: StorageAdapter, projectId: string, svg: string, filename: string, role: AssetRef['role']): Promise<AssetRef> {
  const s = sanitizeSvg(Buffer.from(svg));
  const data = Buffer.from(s.svg);
  const { key, sha256 } = await storage.put(data);
  const asset: AssetRef = { id: newId('ast'), kind: 'svg', role, filename, sha256, width: s.width, height: s.height, bytes: data.length };
  db.prepare('INSERT INTO assets (id, project_id, kind, role, filename, sha256, storage_key, width, height, bytes, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)').run(
    asset.id,
    projectId,
    'svg',
    role,
    filename,
    sha256,
    key,
    s.width,
    s.height,
    data.length,
    new Date().toISOString(),
  );
  return asset;
}

function insert(db: DB, doc: ProjectDoc): string {
  const id = newId('prj');
  const ts = new Date().toISOString();
  db.prepare(
    `INSERT INTO projects (id, name, style_number, collection, template_id, template_version, doc, version, archived, created_at, updated_at)
     VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, ?, ?)`,
  ).run(id, doc.name, doc.styleNumber, doc.collection, doc.template.id, doc.template.version, JSON.stringify(projectDocSchema.parse(doc)), ts, ts);
  return id;
}

function save(db: DB, id: string, doc: ProjectDoc) {
  db.prepare('UPDATE projects SET doc = ?, name = ?, style_number = ?, collection = ?, version = version + 1, updated_at = ? WHERE id = ?').run(
    JSON.stringify(projectDocSchema.parse(doc)),
    doc.name,
    doc.styleNumber,
    doc.collection,
    new Date().toISOString(),
    id,
  );
}

/** Demo values typed as if by a user (not generated grading). Index aligns with size range. */
const DEMO_SPECS: Record<string, Record<string, number[]>> = {
  'tshirt-boxy': {
    A: [680, 690, 700, 710, 720],
    B: [552, 572, 592, 612, 632],
    C: [552, 572, 592, 612, 632],
    D: [536, 556, 576, 596, 616],
    E: [209, 213, 217, 221, 225],
    F: [171, 176, 181, 186, 191],
    G: [222, 227, 232, 237, 242],
    H: [184, 187, 190, 193, 196],
    I: [106, 108, 110, 112, 114],
    J: [18, 18, 18, 18, 18],
    K: [22, 22, 22, 22, 22],
    L: [176, 181, 186, 191, 196],
  },
};

export async function seedDemo(db: DB, storage: StorageAdapter): Promise<string[]> {
  const ids: string[] = [];
  const templates = listTemplates();
  const tee = templates.find((t) => t.id === 'tshirt-boxy');
  if (tee) {
    let doc = createProjectDoc(tee, { name: 'Sunset Club Boxy Tee (demo)', styleNumber: 'SC-TS-001', season: 'SS27', collection: 'Sunset Club' });
    const id = insert(db, doc);
    ids.push(id);
    const logo = await addSvgAsset(db, storage, id, DEMO_LOGO_SVG, 'sunset-club-logo.svg', 'artwork');
    const back = await addSvgAsset(db, storage, id, DEMO_BACK_SVG, 'est-2026-badge.svg', 'artwork');
    const tile = await addSvgAsset(db, storage, id, DEMO_TILE_SVG, 'sun-dot-tile.svg', 'pattern-tile');
    doc.assets.push(logo, back, tile);

    const white = doc.colors[0];
    const navy = { id: newId('col'), name: 'Midnight navy', hex: '#1b1b2f', standard: { system: 'Demo lab dip', code: 'LD-NAVY-01' }, approval: 'submitted' as const };
    const coral = { id: newId('col'), name: 'Sunset coral', hex: '#ff6f61', standard: null, approval: 'not-submitted' as const };
    const sand = { id: newId('col'), name: 'Washed sand', hex: '#e8dcc6', standard: null, approval: 'not-submitted' as const };
    doc.colors.push(navy, coral, sand);
    const [shell, rib] = doc.materials;
    Object.assign(shell, {
      name: 'Heavyweight cotton jersey',
      composition: '100% cotton',
      weight: { value: 240, unit: 'gsm' },
      finish: 'Enzyme wash, pre-shrunk',
      supplier: 'Demo Mill Co.',
      supplierRef: 'DM-J240',
      textureId: 'jersey-heavy',
    });
    Object.assign(rib, { name: '1x1 cotton rib', composition: '95% cotton, 5% elastane', weight: { value: 280, unit: 'gsm' }, finish: 'Garment dyed to match', supplier: 'Demo Mill Co.', supplierRef: 'DM-R1x1' });
    for (const l of doc.layers) {
      if (l.type !== 'panelFill') continue;
      if (l.targets[0] === 'neck_rib' || l.targets[0].startsWith('sleeve')) l.colorId = navy.id;
    }
    let front = makeArtworkLayer(tee, logo, { viewId: 'front', anchorId: 'center_chest', widthMm: 250, name: 'Sunset Club chest logo' });
    front = applyEnteredPlacement(tee, front, { widthMm: 250, offsetXmm: 0, offsetYmm: 0, toleranceMm: 6 });
    front.decoration = { method: 'screen-print', artworkCode: 'SC-ART-001', colorIds: [navy.id, coral.id], notes: 'Plastisol, 3 colors. Gradient printed as halftone.' };
    const backArt = makeArtworkLayer(tee, back, { viewId: 'back', anchorId: 'upper_back', widthMm: 280, name: 'EST. 2026 back badge' });
    backArt.decoration = { method: 'screen-print', artworkCode: 'SC-ART-002', colorIds: [navy.id], notes: '' };
    doc.layers.push(front, backArt);
    const pattern = makePatternLayer(tile, ['sleeve_left', 'sleeve_right'], 'Sun-dot sleeve print');
    pattern.opacity = 0.9;
    pattern.tileWidthMm = 45;
    pattern.view = 'all';
    // Erase part of the pattern near the left sleeve hem (nondestructive mask) to demonstrate erasing.
    pattern.mask = [{ mode: 'erase', view: 'front', width: 40, points: [880, 330, 900, 360, 915, 380] }];
    doc.layers.push(pattern);
    const hem = makeStitchingLayer(tee, ['bottom_hem', 'sleeve_hem_left', 'sleeve_hem_right'], coral.id);
    hem.name = 'Contrast hem coverstitch';
    hem.notes = '2-needle coverstitch, 6 mm gauge, 12 SPI, coral thread on hems.';
    doc.layers.push(hem);
    const stones = makeEmbellishmentLayer('rhinestone', 'front', ['body_front']);
    stones.name = 'Neckline rhinestone trail';
    stones.paths = [{ id: newId('pth'), points: [{ x: 420, y: 190 }, { x: 460, y: 212 }, { x: 500, y: 218 }, { x: 540, y: 212 }, { x: 580, y: 190 }], spacingMm: 8 }];
    stones.points = [{ x: 500, y: 236 }];
    doc.layers.push(stones);

    doc.colorways.push({ id: newId('cw'), name: 'Sand / navy', code: 'CW02', colorSubs: { [white.id]: sand.id }, materialSubs: {}, notes: 'Body in washed sand.' });
    const spec = DEMO_SPECS['tshirt-boxy'];
    for (const p of doc.measurements) {
      const vals = spec[p.templatePomId ?? ''];
      if (!vals) continue;
      doc.sizes.range.forEach((s, i) => {
        p.values[s] = { mm: vals[i], source: 'entered' };
      });
      p.source = 'Demo brand spec';
      p.confirmed = p.code !== 'L'; // Leave one POM unconfirmed to show the review gate.
    }
    doc.bomDerived[`fabric:${shell.id}`] = { quantity: 0.85, unit: 'm', quantityType: 'estimated', supplierRef: 'DM-J240', notes: 'Estimate from mill for 150 cm cuttable width; confirm after marker.' };
    doc.bomDerived[`fabric:${rib.id}`] = { quantity: 0.05, unit: 'm', quantityType: 'estimated', supplierRef: '', notes: '' };
    doc.bomItems.push({ id: newId('bom'), category: 'label', component: 'Inside back neck', materialId: null, description: 'Printed neck label (tagless heat transfer)', quantity: 1, unit: 'pcs', quantityType: 'entered', colorwayIds: [], supplierRef: '', notes: '' });
    doc.constructionNotes.push(
      { id: newId('cn'), title: 'Neckline', text: '1x1 rib, 22 mm finished. Attach with overlock, topstitch 6 mm coverstitch. Back neck tape self fabric.', componentIds: ['neck_rib'], seamIds: ['neck_topstitch', 'back_neck_tape'] },
      { id: newId('cn'), title: 'Shoulders & side seams', text: '4-thread overlock. Shoulder seams taped with clear elastic.', componentIds: [], seamIds: ['shoulder_left', 'side_left'] },
    );
    doc.labels.push(
      { id: newId('lbl'), type: 'heat-transfer-label', description: 'Tagless neck print: logo, size, fiber content, country of origin, care symbols.', placement: 'Inside back neck, centered 20 mm below neck seam', materialId: null, assetId: null, notes: '' },
      { id: newId('lbl'), type: 'polybag', description: 'Individual recyclable polybag with suffocation warning.', placement: '', materialId: null, assetId: null, notes: 'Fold to 25 × 30 cm.' },
    );
    doc = projectDocSchema.parse(doc);
    save(db, id, doc);
  }
  return ids;
}

import type { GarmentTemplate } from '../schema/template';
import type { EmbellishmentLayer, HardwareLayer, Point, ProjectDoc } from '../schema/project';
import { pointsAlongPolyline } from '../geometry';
import { getHardware } from '../catalog/hardware';
import { sizeLabelFor } from '../catalog/embellishments';
import { componentMaterials, componentName, getColorway, resolveColor } from './design';

/** mm per template unit (falls back to 1 when a template has no calibration). */
export function mmPerUnit(template: GarmentTemplate): number {
  return template.calibration?.mmPerUnit ?? 1;
}

/** Every individual stone/stud position for a layer: free points + points spaced along paths. */
export function embellishmentPositions(layer: EmbellishmentLayer, template: GarmentTemplate): Point[] {
  const k = mmPerUnit(template);
  const out: Point[] = [...layer.points];
  for (const path of layer.paths) out.push(...pointsAlongPolyline(path.points, path.spacingMm / k));
  return out;
}

export function embellishmentCount(layer: EmbellishmentLayer, template: GarmentTemplate): number {
  return embellishmentPositions(layer, template).length;
}

export type QuantityType = 'counted' | 'entered' | 'estimated' | 'missing';

export interface BomRow {
  /** Stable key. Derived rows use a deterministic key; manual rows use their id. */
  key: string;
  derived: boolean;
  source: 'panel-material' | 'stitching' | 'embellishment' | 'hardware' | 'manual';
  category: string;
  component: string;
  componentIds: string[];
  materialId: string | null;
  materialName: string;
  description: string;
  quantity: number | null;
  unit: string;
  quantityType: QuantityType;
  /** Colourway ids this row applies to. Empty means all. */
  colorwayIds: string[];
  supplierRef: string;
  notes: string;
  /** Layer ids that produced this row (for traceability). */
  layerIds: string[];
}

function derivedInput(doc: ProjectDoc, key: string) {
  return doc.bomDerived[key];
}

function qtyType(q: number | null | undefined, t: 'entered' | 'estimated' | undefined): QuantityType {
  return q === null || q === undefined ? 'missing' : (t ?? 'entered');
}

/**
 * Build the bill of materials from the design itself. Fabric rows come from component
 * material assignments (quantity is never inferred from the drawing — it must be entered).
 * Embellishment and hardware rows are counted from placements.
 */
export function computeBom(doc: ProjectDoc, template: GarmentTemplate): BomRow[] {
  const rows: BomRow[] = [];
  const allCw = doc.colorways.map((c) => c.id);
  const onlyIfSubset = (ids: string[]) => (ids.length === allCw.length ? [] : ids);

  // ---- Fabrics by material (per colourway, so substitutions produce their own rows)
  const fabric = new Map<string, { components: Set<string>; colorways: Set<string> }>();
  for (const cw of doc.colorways) {
    const mats = componentMaterials(doc, template, cw.id);
    for (const [compId, mat] of mats) {
      if (!mat) continue;
      const e = fabric.get(mat.id) ?? { components: new Set(), colorways: new Set() };
      e.components.add(compId);
      e.colorways.add(cw.id);
      fabric.set(mat.id, e);
    }
  }
  for (const [matId, e] of fabric) {
    const mat = doc.materials.find((m) => m.id === matId)!;
    const key = `fabric:${matId}`;
    const input = derivedInput(doc, key);
    const comps = [...e.components];
    rows.push({
      key,
      derived: true,
      source: 'panel-material',
      category: mat.kind === 'rib' ? 'rib' : 'fabric',
      component: comps.map((c) => componentName(template, c)).join(', '),
      componentIds: comps,
      materialId: matId,
      materialName: mat.name,
      description: [mat.composition, mat.weight ? `${mat.weight.value} ${mat.weight.unit === 'gsm' ? 'g/m²' : 'oz/yd²'}` : '', mat.finish]
        .filter(Boolean)
        .join(' · '),
      quantity: input?.quantity ?? null,
      unit: input?.unit || 'm',
      quantityType: qtyType(input?.quantity, input?.quantityType),
      colorwayIds: onlyIfSubset([...e.colorways]),
      supplierRef: input?.supplierRef || mat.supplierRef,
      notes: input?.notes ?? '',
      layerIds: doc.layers.filter((l) => l.type === 'panelFill' && l.targets.some((t) => e.components.has(t))).map((l) => l.id),
    });
  }

  // ---- Thread by stitch colour (resolved per colourway)
  const thread = new Map<string, { colorways: Set<string>; seams: Set<string>; layers: Set<string> }>();
  for (const l of doc.layers) {
    if (l.type !== 'stitching' || !l.visible) continue;
    for (const cw of doc.colorways) {
      const color = resolveColor(doc, l.colorId, cw.id);
      if (!color) continue;
      const e = thread.get(color.id) ?? { colorways: new Set(), seams: new Set(), layers: new Set() };
      e.colorways.add(cw.id);
      l.seamIds.forEach((s) => e.seams.add(s));
      e.layers.add(l.id);
      thread.set(color.id, e);
    }
  }
  for (const [colorId, e] of thread) {
    const color = doc.colors.find((c) => c.id === colorId)!;
    const key = `thread:${colorId}`;
    const input = derivedInput(doc, key);
    rows.push({
      key,
      derived: true,
      source: 'stitching',
      category: 'thread',
      component: `${e.seams.size} seam${e.seams.size === 1 ? '' : 's'}`,
      componentIds: [],
      materialId: null,
      materialName: `Thread — ${color.name}`,
      description: color.standard ? `${color.standard.system} ${color.standard.code}` : 'Match to colour standard',
      quantity: input?.quantity ?? null,
      unit: input?.unit || 'cones',
      quantityType: qtyType(input?.quantity, input?.quantityType),
      colorwayIds: onlyIfSubset([...e.colorways]),
      supplierRef: input?.supplierRef ?? '',
      notes: input?.notes ?? '',
      layerIds: [...e.layers],
    });
  }

  // ---- Embellishments: counted from placements
  const emb = new Map<string, { layers: EmbellishmentLayer[]; count: number }>();
  for (const l of doc.layers) {
    if (l.type !== 'embellishment' || !l.visible) continue;
    const key = `emb:${l.kind}:${l.diameterMm}:${l.finish}:${l.attachment}`;
    const e = emb.get(key) ?? { layers: [], count: 0 };
    e.layers.push(l);
    e.count += embellishmentCount(l, template);
    emb.set(key, e);
  }
  for (const [key, e] of emb) {
    const l0 = e.layers[0];
    const input = derivedInput(doc, key);
    const comps = [...new Set(e.layers.flatMap((l) => l.targets))];
    rows.push({
      key,
      derived: true,
      source: 'embellishment',
      category: 'embellishment',
      component: comps.map((c) => componentName(template, c)).join(', ') || 'Garment',
      componentIds: comps,
      materialId: null,
      materialName: `${l0.kind === 'rhinestone' ? 'Rhinestone' : 'Stud'} ${sizeLabelFor(l0.kind, l0.diameterMm)} — ${l0.finish}`,
      description: `${l0.diameterMm} mm, ${l0.attachment.replace('-', ' ')}`,
      quantity: e.count,
      unit: 'pcs',
      quantityType: 'counted',
      colorwayIds: [],
      supplierRef: input?.supplierRef ?? '',
      notes: input?.notes ?? '',
      layerIds: e.layers.map((l) => l.id),
    });
  }

  // ---- Hardware: counted
  const hw = new Map<string, HardwareLayer[]>();
  for (const l of doc.layers) {
    if (l.type !== 'hardware' || !l.visible) continue;
    const key = `hw:${l.hardwareId}:${l.finish}:${l.sizeMm}`;
    hw.set(key, [...(hw.get(key) ?? []), l]);
  }
  for (const [key, ls] of hw) {
    const def = getHardware(ls[0].hardwareId);
    const input = derivedInput(doc, key);
    const comps = [...new Set(ls.flatMap((l) => l.targets))];
    rows.push({
      key,
      derived: true,
      source: 'hardware',
      category: 'hardware',
      component: comps.map((c) => componentName(template, c)).join(', ') || 'Garment',
      componentIds: comps,
      materialId: null,
      materialName: `${def?.name ?? ls[0].hardwareId} — ${ls[0].finish}`,
      description: `${ls[0].sizeMm} mm${def?.category === 'zipper-decorative' ? ' · decorative, non-functional' : ''}`,
      quantity: ls.length,
      unit: 'pcs',
      quantityType: 'counted',
      colorwayIds: [],
      supplierRef: input?.supplierRef ?? '',
      notes: input?.notes ?? '',
      layerIds: ls.map((l) => l.id),
    });
  }

  // ---- Manual rows (labels, packaging, trims, …)
  for (const b of doc.bomItems) {
    const mat = doc.materials.find((m) => m.id === b.materialId);
    rows.push({
      key: b.id,
      derived: false,
      source: 'manual',
      category: b.category,
      component: b.component,
      componentIds: [],
      materialId: b.materialId,
      materialName: mat?.name ?? b.description,
      description: mat ? b.description : '',
      quantity: b.quantity,
      unit: b.unit,
      quantityType: qtyType(b.quantity, b.quantityType),
      colorwayIds: b.colorwayIds,
      supplierRef: b.supplierRef || mat?.supplierRef || '',
      notes: b.notes,
      layerIds: doc.layers.filter((l) => l.bomItemId === b.id).map((l) => l.id),
    });
  }
  return rows;
}

export function colorwayNames(doc: ProjectDoc, ids: string[]): string {
  if (!ids.length) return 'All';
  return ids.map((id) => getColorway(doc, id).name).join(', ');
}

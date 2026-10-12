import type { GarmentTemplate } from '../schema/template';
import type { ProjectDoc } from '../schema/project';
import { DECORATION_METHOD_LABELS } from '../schema/template';
import { getHardware } from '../catalog/hardware';
import { computeBom, embellishmentCount } from './bom';
import { componentMaterials, componentName } from './design';

export type ExportMode = 'draft' | 'review';

export type CheckSection =
  | 'identity'
  | 'materials'
  | 'colors'
  | 'bom'
  | 'artwork'
  | 'measurements'
  | 'construction'
  | 'labels'
  | 'decoration'
  | 'assets';

export interface Check {
  id: string;
  section: CheckSection;
  /** `required` blocks a manufacturer-review export; `recommended` never blocks. */
  level: 'required' | 'recommended';
  passed: boolean;
  message: string;
  /** Where the user fixes it. */
  fix: { screen: 'studio' | 'measurements' | 'materials' | 'techpack'; focus?: string };
}

export interface ValidationResult {
  checks: Check[];
  failedRequired: Check[];
  failedRecommended: Check[];
  canExport: (mode: ExportMode) => boolean;
}

export function validateProject(doc: ProjectDoc, template: GarmentTemplate): ValidationResult {
  const checks: Check[] = [];
  const add = (c: Check) => checks.push(c);

  // ---- Identity
  add({
    id: 'identity.style',
    section: 'identity',
    level: 'required',
    passed: !!doc.name.trim() && !!doc.styleNumber.trim(),
    message: doc.name.trim() && doc.styleNumber.trim() ? 'Style name and style number are set.' : 'Enter a style name and style number.',
    fix: { screen: 'techpack' },
  });
  add({
    id: 'identity.sizes',
    section: 'identity',
    level: 'required',
    passed: doc.sizes.range.includes(doc.sizes.base),
    message: doc.sizes.range.includes(doc.sizes.base) ? `Base size (${doc.sizes.base}) is part of the size range.` : `Base size (${doc.sizes.base}) must be part of the size range.`,
    fix: { screen: 'measurements' },
  });

  // ---- Materials actually used on components
  const used = new Map<string, string[]>();
  for (const cw of doc.colorways) {
    for (const [comp, mat] of componentMaterials(doc, template, cw.id)) {
      if (!mat) {
        add({
          id: `materials.unassigned.${comp}.${cw.id}`,
          section: 'materials',
          level: 'required',
          passed: false,
          message: `${componentName(template, comp)} has no material assigned (${cw.name}).`,
          fix: { screen: 'materials' },
        });
        continue;
      }
      used.set(mat.id, [...(used.get(mat.id) ?? []), componentName(template, comp)]);
    }
  }
  for (const [matId] of used) {
    const m = doc.materials.find((x) => x.id === matId)!;
    add({
      id: `materials.composition.${m.id}`,
      section: 'materials',
      level: 'required',
      passed: !!m.composition.trim(),
      message: m.composition.trim() ? `Material “${m.name}” has a fibre composition.` : `Material “${m.name}” needs a fibre composition (e.g. 100% cotton).`,
      fix: { screen: 'materials', focus: m.id },
    });
    add({
      id: `materials.weight.${m.id}`,
      section: 'materials',
      level: 'required',
      passed: m.weight !== null,
      message: m.weight ? `Material “${m.name}” has a fabric weight.` : `Material “${m.name}” needs a fabric weight (g/m² or oz/yd²).`,
      fix: { screen: 'materials', focus: m.id },
    });
    add({
      id: `materials.placeholder.${m.id}`,
      section: 'materials',
      level: 'required',
      passed: !/to be specified/i.test(m.name),
      message: /to be specified/i.test(m.name) ? `“${m.name}” is still a placeholder — name the actual material.` : `Material “${m.name}” is named.`,
      fix: { screen: 'materials', focus: m.id },
    });
    add({
      id: `materials.supplier.${m.id}`,
      section: 'materials',
      level: 'recommended',
      passed: !!m.supplier.trim(),
      message: m.supplier.trim() ? `Material “${m.name}” lists a supplier.` : `Material “${m.name}” has no supplier listed.`,
      fix: { screen: 'materials', focus: m.id },
    });
  }

  // ---- Colours referenced by the design
  const usedColors = new Set<string>();
  for (const l of doc.layers) {
    if (l.type === 'panelFill' || l.type === 'stitching') usedColors.add(l.colorId);
    if (l.type === 'embellishment' && l.colorId) usedColors.add(l.colorId);
    if (l.type === 'artwork') l.decoration.colorIds.forEach((c) => usedColors.add(c));
  }
  for (const cw of doc.colorways) for (const v of Object.values(cw.colorSubs)) usedColors.add(v);
  for (const cid of usedColors) {
    const c = doc.colors.find((x) => x.id === cid);
    if (!c) {
      add({ id: `colors.missing.${cid}`, section: 'colors', level: 'required', passed: false, message: `A layer references a color that was deleted (${cid}). Pick a palette colour.`, fix: { screen: 'materials' } });
      continue;
    }
    add({
      id: `colors.standard.${c.id}`,
      section: 'colors',
      level: 'recommended',
      passed: !!c.standard?.code,
      message: c.standard?.code ? `Color “${c.name}” has a color-standard reference.` : `Color “${c.name}” has no color-standard reference. Add the code you have verified (screen color is not a match).`,
      fix: { screen: 'materials', focus: c.id },
    });
  }

  // ---- Measurements
  for (const p of doc.measurements) {
    const missing = doc.sizes.range.filter((s) => p.values[s]?.mm === null || p.values[s]?.mm === undefined);
    add({
      id: `measurements.values.${p.id}`,
      section: 'measurements',
      level: 'required',
      passed: missing.length === 0,
      message: missing.length ? `${p.code} ${p.label}: missing values for ${missing.join(', ')}.` : `${p.code} ${p.label}: values for every size.`,
      fix: { screen: 'measurements', focus: p.id },
    });
    const hasDefaults = Object.values(p.values).some((v) => v.source === 'template-default');
    add({
      id: `measurements.confirmed.${p.id}`,
      section: 'measurements',
      level: 'required',
      passed: p.confirmed,
      message: hasDefaults
        ? `${p.code} ${p.label}: uses an unconfirmed template default — review and confirm.`
        : p.confirmed
          ? `${p.code} ${p.label}: confirmed.`
          : `${p.code} ${p.label}: not confirmed yet — check every size and tick Confirmed.`,
      fix: { screen: 'measurements', focus: p.id },
    });
  }
  if (doc.measurements.length === 0) {
    add({ id: 'measurements.none', section: 'measurements', level: 'required', passed: false, message: 'Add at least one point of measure.', fix: { screen: 'measurements' } });
  }

  // ---- Artwork and decorations
  const assetIds = new Set(doc.assets.map((a) => a.id));
  for (const l of doc.layers) {
    if (!l.visible) continue;
    if (l.type === 'artwork' || l.type === 'pattern') {
      add({
        id: `assets.present.${l.id}`,
        section: 'assets',
        level: 'required',
        passed: assetIds.has(l.assetId),
        message: assetIds.has(l.assetId)
          ? `“${l.name}” source file is attached.`
          : `“${l.name}” references a missing file. Re-upload the artwork or delete the layer.`,
        fix: { screen: 'studio', focus: l.id },
      });
    }
    if (l.type === 'artwork') {
      add({
        id: `artwork.dimensions.${l.id}`,
        section: 'artwork',
        level: 'required',
        passed: l.placement.source === 'entered',
        message:
          l.placement.source === 'entered'
            ? `“${l.name}”: manufacturing dimensions entered.`
            : `“${l.name}”: size and position are a visual estimate. Enter finished width/height and offsets.`,
        fix: { screen: 'studio', focus: l.id },
      });
      add({
        id: `artwork.anchor.${l.id}`,
        section: 'artwork',
        level: 'required',
        passed: !!l.placement.anchorId,
        message: l.placement.anchorId ? `“${l.name}”: placement has a reference point.` : `“${l.name}”: choose the reference point the placement is measured from.`,
        fix: { screen: 'studio', focus: l.id },
      });
      const unsupported = l.targets.filter((t) => {
        const comp = template.components.find((c) => c.id === t);
        return comp && !comp.decorationMethods.includes(l.decoration.method);
      });
      add({
        id: `artwork.method.${l.id}`,
        section: 'artwork',
        level: 'required',
        passed: unsupported.length === 0,
        message: unsupported.length
          ? `“${l.name}”: ${DECORATION_METHOD_LABELS[l.decoration.method]} is not a supported method on ${unsupported.map((t) => componentName(template, t)).join(', ')}.`
          : `“${l.name}”: decoration method supported on its panels.`,
        fix: { screen: 'studio', focus: l.id },
      });
      add({
        id: `artwork.code.${l.id}`,
        section: 'artwork',
        level: 'recommended',
        passed: !!l.decoration.artworkCode.trim(),
        message: l.decoration.artworkCode.trim() ? `“${l.name}”: has an artwork identifier.` : `“${l.name}”: no artwork ID yet.`,
        fix: { screen: 'studio', focus: l.id },
      });
    }
    if (l.type === 'embellishment') {
      const n = embellishmentCount(l, template);
      add({
        id: `decoration.count.${l.id}`,
        section: 'decoration',
        level: 'required',
        passed: n > 0,
        message: n > 0 ? `“${l.name}”: ${n} placed.` : `“${l.name}”: no stones/studs placed yet — place some or delete the layer.`,
        fix: { screen: 'studio', focus: l.id },
      });
    }
    if (l.type === 'hardware') {
      const def = getHardware(l.hardwareId);
      add({
        id: `decoration.hardware.${l.id}`,
        section: 'decoration',
        level: 'required',
        passed: !!def,
        message: def ? `“${l.name}”: catalog component found.` : `“${l.name}”: unknown hardware component “${l.hardwareId}”.`,
        fix: { screen: 'studio', focus: l.id },
      });
    }
    if (l.type === 'stitching') {
      add({
        id: `construction.stitchnotes.${l.id}`,
        section: 'construction',
        level: 'recommended',
        passed: !!l.notes.trim(),
        message: l.notes.trim() ? `“${l.name}”: has manufacturing notes.` : `“${l.name}”: add stitch manufacturing notes (the drawn dash is illustrative only).`,
        fix: { screen: 'studio', focus: l.id },
      });
    }
  }

  // ---- BOM quantities
  for (const row of computeBom(doc, template)) {
    if (row.quantityType !== 'missing') continue;
    add({
      id: `bom.qty.${row.key}`,
      section: 'bom',
      level: row.derived && row.source === 'panel-material' ? 'recommended' : row.derived ? 'recommended' : 'required',
      passed: false,
      message: `BOM “${row.materialName}”: quantity not entered${row.source === 'panel-material' ? ' (consumption is never inferred from the drawing)' : ''}.`,
      fix: { screen: 'materials', focus: row.key },
    });
  }

  // ---- Construction & labels (optional sections: only checked when used)
  add({
    id: 'construction.notes',
    section: 'construction',
    level: 'recommended',
    passed: doc.constructionNotes.length > 0,
    message: doc.constructionNotes.length ? 'Construction notes are present.' : 'No construction notes yet — describe seams, finishes and assembly.',
    fix: { screen: 'techpack' },
  });
  for (const lb of doc.labels) {
    add({
      id: `labels.desc.${lb.id}`,
      section: 'labels',
      level: 'required',
      passed: !!lb.description.trim(),
      message: lb.description.trim() ? `Label/packaging item “${lb.type}” has a description.` : `Label/packaging item “${lb.type}” needs a description (or remove it).`,
      fix: { screen: 'techpack', focus: lb.id },
    });
    add({
      id: `labels.placement.${lb.id}`,
      section: 'labels',
      level: 'recommended',
      passed: !!lb.placement.trim() || ['polybag', 'folding', 'carton'].includes(lb.type),
      message: `Label “${lb.type}” ${lb.placement.trim() ? 'has a placement.' : 'has no placement.'}`,
      fix: { screen: 'techpack', focus: lb.id },
    });
  }

  const failedRequired = checks.filter((c) => !c.passed && c.level === 'required');
  const failedRecommended = checks.filter((c) => !c.passed && c.level === 'recommended');
  return {
    checks,
    failedRequired,
    failedRecommended,
    canExport: (mode) => mode === 'draft' || failedRequired.length === 0,
  };
}

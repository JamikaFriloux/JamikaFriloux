import type { GarmentTemplate } from '../schema/template';
import type { Layer, Material, Pom, ProjectDoc } from '../schema/project';
import { PROJECT_SCHEMA_VERSION } from '../schema/project';
import { newId } from './ids';

export interface NewProjectInput {
  name: string;
  styleNumber: string;
  season?: string;
  collection?: string;
}

/** Template POMs → project POM rows. Only the base size gets the template default; it stays unconfirmed. */
export function pomsFromTemplate(template: GarmentTemplate, baseSize: string, range: string[]): Pom[] {
  return template.poms.map((p) => {
    const values: Pom['values'] = {};
    for (const size of range) {
      values[size] =
        size === baseSize && p.defaultMm !== null
          ? { mm: p.defaultMm, source: 'template-default' }
          : { mm: null, source: 'entered' };
    }
    return {
      id: newId('pom'),
      templatePomId: p.id,
      code: p.code,
      label: p.label,
      howToMeasure: p.howToMeasure,
      diagramView: p.view,
      values,
      tolPlusMm: p.tolPlusMm,
      tolMinusMm: p.tolMinusMm,
      source: 'Template default (unconfirmed)',
      confirmed: false,
    };
  });
}

/** A new style: one panel-fill layer per component, neutral palette, placeholder materials to be specified. */
export function createProjectDoc(template: GarmentTemplate, input: NewProjectInput): ProjectDoc {
  const white = { id: newId('col'), name: 'Optic white', hex: '#f4f3ef', standard: null, approval: 'not-submitted' as const };
  const shell: Material = {
    id: newId('mat'),
    name: 'Shell fabric (to be specified)',
    kind: 'fabric',
    composition: '',
    weight: null,
    finish: '',
    supplier: '',
    supplierRef: '',
    textureId: template.category === 'top' && template.id.startsWith('tshirt') ? 'jersey' : 'fleece',
    notes: '',
  };
  const rib: Material = {
    id: newId('mat'),
    name: 'Rib (to be specified)',
    kind: 'rib',
    composition: '',
    weight: null,
    finish: '',
    supplier: '',
    supplierRef: '',
    textureId: 'rib-1x1',
    notes: '',
  };
  const materials: Material[] = [shell];
  const usesRib = template.components.some((c) => c.materialRole === 'rib');
  if (usesRib) materials.push(rib);

  const layers: Layer[] = template.components.map((c) => ({
    id: newId('lyr'),
    type: 'panelFill',
    name: `${c.name} color`,
    view: 'all',
    targets: [c.id],
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    colorId: white.id,
    materialId: c.materialRole === 'rib' ? rib.id : shell.id,
  }));

  const base = template.sizes.defaultBase;
  const range = template.sizes.defaultRange;
  return {
    schemaVersion: PROJECT_SCHEMA_VERSION,
    name: input.name,
    styleNumber: input.styleNumber,
    season: input.season ?? '',
    collection: input.collection ?? '',
    description: '',
    template: { id: template.id, version: template.version },
    sizes: { base, range },
    displayUnit: 'cm',
    colors: [white],
    materials,
    colorways: [{ id: newId('cw'), name: 'Main', code: '', colorSubs: {}, materialSubs: {}, notes: '' }],
    layers,
    assets: [],
    measurements: pomsFromTemplate(template, base, range),
    bomItems: [],
    bomDerived: {},
    constructionNotes: [],
    labels: [],
  };
}

import { garmentTemplateSchema, type GarmentTemplate } from '../schema/template';
import { tshirtBoxyV1 } from './tshirt-boxy';
import { hoodiePulloverV1 } from './hoodie-pullover';
import { sweatpantsStraightV1 } from './sweatpants-straight';

/**
 * Immutable template registry. Templates are versioned: a project references
 * `{id, version}` and always resolves to exactly that geometry. Never edit a published
 * version in place — add a new version instead.
 */
const REGISTRY: GarmentTemplate[] = [tshirtBoxyV1, hoodiePulloverV1, sweatpantsStraightV1].map((t) => Object.freeze(garmentTemplateSchema.parse(t)) as GarmentTemplate);

export function listTemplates(): GarmentTemplate[] {
  // Latest version of each template id.
  const latest = new Map<string, GarmentTemplate>();
  for (const t of REGISTRY) {
    const cur = latest.get(t.id);
    if (!cur || cur.version < t.version) latest.set(t.id, t);
  }
  return [...latest.values()];
}

/** Every installed version (including superseded ones still referenced by older projects). */
export function allTemplateVersions(): GarmentTemplate[] {
  return [...REGISTRY];
}

export function getTemplate(id: string, version: number): GarmentTemplate | undefined {
  return REGISTRY.find((t) => t.id === id && t.version === version);
}

export function requireTemplate(id: string, version: number): GarmentTemplate {
  const t = getTemplate(id, version);
  if (!t) throw new Error(`Garment template ${id} v${version} is not installed.`);
  return t;
}

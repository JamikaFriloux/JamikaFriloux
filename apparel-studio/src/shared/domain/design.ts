import type { GarmentTemplate, TemplateView, ViewId } from '../schema/template';
import type { Color, Layer, Material, PanelFillLayer, ProjectDoc } from '../schema/project';

export function getView(template: GarmentTemplate, viewId: ViewId): TemplateView {
  const v = template.views.find((x) => x.id === viewId);
  if (!v) throw new Error(`Template ${template.id} has no ${viewId} view`);
  return v;
}

export function layerAppliesToView(layer: Layer, viewId: ViewId): boolean {
  return layer.view === 'all' || layer.view === viewId;
}

/** Component ids that have at least one panel in a view. */
export function componentsInView(template: GarmentTemplate, viewId: ViewId): Set<string> {
  return new Set(getView(template, viewId).panels.map((p) => p.componentId));
}

export function componentName(template: GarmentTemplate, componentId: string): string {
  return template.components.find((c) => c.id === componentId)?.name ?? componentId;
}

export function getColorway(doc: ProjectDoc, colorwayId?: string | null) {
  return doc.colorways.find((c) => c.id === colorwayId) ?? doc.colorways[0];
}

/** Resolve a base colour id through a colourway's explicit substitutions. */
export function resolveColor(doc: ProjectDoc, colorId: string | null | undefined, colorwayId?: string | null): Color | undefined {
  if (!colorId) return undefined;
  const cw = getColorway(doc, colorwayId);
  const id = cw.colorSubs[colorId] ?? colorId;
  return doc.colors.find((c) => c.id === id);
}

export function resolveMaterial(doc: ProjectDoc, materialId: string | null | undefined, colorwayId?: string | null): Material | undefined {
  if (!materialId) return undefined;
  const cw = getColorway(doc, colorwayId);
  const id = cw.materialSubs[materialId] ?? materialId;
  return doc.materials.find((m) => m.id === id);
}

/**
 * The panel-fill layer governing a component in a view. A view-specific fill (an explicit
 * per-view difference) wins over an `all`-views fill; among equals the top-most wins.
 */
export function fillLayerFor(doc: ProjectDoc, componentId: string, viewId: ViewId): PanelFillLayer | undefined {
  let shared: PanelFillLayer | undefined;
  let specific: PanelFillLayer | undefined;
  for (const l of doc.layers) {
    if (l.type !== 'panelFill' || !l.visible || !l.targets.includes(componentId)) continue;
    if (l.view === viewId) specific = l;
    else if (l.view === 'all') shared = l;
  }
  return specific ?? shared;
}

export interface ResolvedFill {
  layer: PanelFillLayer | undefined;
  color: Color | undefined;
  material: Material | undefined;
  hex: string;
  /** True when this view uses an explicit per-view override. */
  isViewOverride: boolean;
}

export function resolveFill(doc: ProjectDoc, componentId: string, viewId: ViewId, colorwayId?: string | null): ResolvedFill {
  const layer = fillLayerFor(doc, componentId, viewId);
  const color = resolveColor(doc, layer?.colorId, colorwayId);
  const material = resolveMaterial(doc, layer?.materialId, colorwayId);
  return { layer, color, material, hex: color?.hex ?? '#e6e6e6', isViewOverride: layer?.view === viewId };
}

/** Component → material id in a colourway, using the shared (all-view) assignment, falling back to any view. */
export function componentMaterials(doc: ProjectDoc, template: GarmentTemplate, colorwayId?: string | null): Map<string, Material | undefined> {
  const out = new Map<string, Material | undefined>();
  for (const c of template.components) {
    let mat: Material | undefined;
    for (const v of template.views) {
      const f = resolveFill(doc, c.id, v.id, colorwayId);
      if (f.material) {
        mat = f.material;
        if (!f.isViewOverride) break;
      }
    }
    out.set(c.id, mat);
  }
  return out;
}

/** Decoration layers (everything except panel fills) visible in a view, in stacking order. */
export function decorationLayersForView(doc: ProjectDoc, viewId: ViewId): Layer[] {
  return doc.layers.filter((l) => l.type !== 'panelFill' && l.visible && layerAppliesToView(l, viewId));
}

export function layerTypeLabel(type: Layer['type']): string {
  return {
    panelFill: 'Panel color',
    artwork: 'Artwork',
    pattern: 'Pattern',
    texture: 'Texture',
    stitching: 'Stitching',
    embellishment: 'Embellishment',
    hardware: 'Hardware',
    annotation: 'Note',
  }[type];
}

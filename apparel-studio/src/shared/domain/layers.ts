import type { GarmentTemplate, ViewId } from '../schema/template';
import type {
  AnnotationLayer,
  ArtworkLayer,
  AssetRef,
  EmbellishmentLayer,
  HardwareLayer,
  PanelFillLayer,
  PatternLayer,
  ProjectDoc,
  StitchingLayer,
  TextureLayer,
} from '../schema/project';
import { getView, componentName } from './design';
import { findAnchor, placementFromTransform } from './placement';
import { newId } from './ids';
import { getHardware } from '../catalog/hardware';
import { getTexture } from '../catalog/textures';
import { pointInPath } from '../geometry';

/** Outer components whose panel contains a point in a view (top-most first). */
export function componentsAt(template: GarmentTemplate, viewId: ViewId, x: number, y: number): string[] {
  const panels = [...getView(template, viewId).panels].filter((p) => p.side === 'outer').sort((a, b) => b.z - a.z);
  return [...new Set(panels.filter((p) => pointInPath(p.d, x, y)).map((p) => p.componentId))];
}

export function makeArtworkLayer(
  template: GarmentTemplate,
  asset: AssetRef,
  opts: { viewId: ViewId; anchorId?: string; widthMm?: number; targets?: string[]; name?: string },
): ArtworkLayer {
  const view = getView(template, opts.viewId);
  const anchor = findAnchor(template, opts.anchorId) ?? view.anchors[0];
  const k = template.calibration?.mmPerUnit ?? 1;
  const width = (opts.widthMm ?? 250) / k;
  const height = (width * asset.height) / asset.width;
  const targets = opts.targets?.length ? opts.targets : [anchor.componentId];
  const transform = { x: anchor.x, y: anchor.y + height / 2, width, height, rotation: 0 };
  const layer: ArtworkLayer = {
    id: newId('lyr'),
    type: 'artwork',
    name: opts.name ?? asset.filename.replace(/\.(png|svg)$/i, ''),
    view: opts.viewId,
    targets,
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    assetId: asset.id,
    transform,
    lockAspect: true,
    clipToTargets: true,
    mask: [],
    placement: {
      anchorId: anchor.id,
      reference: 'top-center',
      offsetXmm: 0,
      offsetYmm: 0,
      widthMm: width * k,
      heightMm: height * k,
      toleranceMm: null,
      source: 'canvas-estimate',
    },
    decoration: { method: 'screen-print', artworkCode: '', colorIds: [], notes: '' },
  };
  return { ...layer, placement: placementFromTransform(template, transform, layer.placement) };
}

export function makePatternLayer(asset: AssetRef, targets: string[], name?: string): PatternLayer {
  return {
    id: newId('lyr'),
    type: 'pattern',
    name: name ?? `Pattern — ${asset.filename.replace(/\.(png|svg)$/i, '')}`,
    view: 'all',
    targets,
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    assetId: asset.id,
    tileWidthMm: 80,
    rotation: 0,
    offsetXmm: 0,
    offsetYmm: 0,
    mask: [],
    method: 'sublimation',
    notes: '',
  };
}

export function makeTextureLayer(template: GarmentTemplate, textureId: string, targets: string[], materialId: string | null): TextureLayer {
  const def = getTexture(textureId);
  return {
    id: newId('lyr'),
    type: 'texture',
    name: `${def?.name ?? textureId} texture — ${targets.map((t) => componentName(template, t)).join(', ')}`,
    view: 'all',
    targets,
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    textureId,
    scale: 1,
    strength: 0.6,
    materialId,
    mask: [],
  };
}

export function makeStitchingLayer(template: GarmentTemplate, seamIds: string[], colorId: string): StitchingLayer {
  const seams = template.views.flatMap((v) => v.seams).filter((s) => seamIds.includes(s.id));
  const style = seams[0]?.defaultStyle ?? 'single-needle';
  return {
    id: newId('lyr'),
    type: 'stitching',
    name: `Stitching — ${[...new Set(seams.map((s) => s.name))].slice(0, 2).join(', ')}${seams.length > 2 ? '…' : ''}`,
    view: 'all',
    targets: [...new Set(seams.flatMap((s) => s.componentIds))],
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    seamIds,
    colorId,
    style,
    notes: '',
    threadMaterialId: null,
  };
}

export function makeEmbellishmentLayer(kind: 'rhinestone' | 'stud', viewId: ViewId, targets: string[]): EmbellishmentLayer {
  return {
    id: newId('lyr'),
    type: 'embellishment',
    name: kind === 'rhinestone' ? 'Rhinestones' : 'Studs',
    view: viewId,
    targets,
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    kind,
    points: [],
    paths: [],
    diameterMm: kind === 'rhinestone' ? 3.9 : 6,
    finish: kind === 'rhinestone' ? 'Crystal' : 'Nickel',
    colorId: null,
    attachment: kind === 'rhinestone' ? 'hotfix' : 'prong-set',
    notes: '',
  };
}

export function makeHardwareLayer(template: GarmentTemplate, hardwareId: string, viewId: ViewId, x: number, y: number, targets: string[]): HardwareLayer {
  const def = getHardware(hardwareId)!;
  const k = template.calibration?.mmPerUnit ?? 1;
  const h = def.defaultSizeMm / k;
  // `defaultSizeMm` is the longest dimension.
  const width = def.aspect >= 1 ? h : h * def.aspect;
  const height = def.aspect >= 1 ? h / def.aspect : h;
  return {
    id: newId('lyr'),
    type: 'hardware',
    name: def.name,
    view: viewId,
    targets,
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    hardwareId,
    transform: { x, y, width, height, rotation: 0 },
    finish: def.finishes[0],
    sizeMm: def.defaultSizeMm,
    notes: '',
  };
}

export function makeAnnotationLayer(viewId: ViewId, x: number, y: number, text = 'Note'): AnnotationLayer {
  return {
    id: newId('lyr'),
    type: 'annotation',
    name: 'Note',
    view: viewId,
    targets: [],
    visible: true,
    locked: false,
    opacity: 1,
    bomItemId: null,
    text,
    x,
    y,
    target: { x: x - 40, y: y + 40 },
  };
}

/** Create an explicit per-view override of a shared panel colour (intentional front/back difference). */
export function makeViewOverride(doc: ProjectDoc, base: PanelFillLayer, viewId: ViewId): PanelFillLayer {
  return { ...base, id: newId('lyr'), view: viewId, name: `${base.name} (${viewId} only)` };
}

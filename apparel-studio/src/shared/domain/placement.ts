import type { GarmentTemplate, TemplateAnchor, ViewId } from '../schema/template';
import type { ArtworkLayer, Placement, Transform } from '../schema/project';
import { roundMm } from '../units';
import { getView } from './design';

export function findAnchor(template: GarmentTemplate, anchorId: string | null | undefined): (TemplateAnchor & { view: ViewId }) | undefined {
  if (!anchorId) return undefined;
  for (const v of template.views) {
    const a = v.anchors.find((x) => x.id === anchorId);
    if (a) return { ...a, view: v.id };
  }
  return undefined;
}

export function nearestAnchor(template: GarmentTemplate, viewId: ViewId, x: number, y: number, componentIds?: string[]): TemplateAnchor | undefined {
  const anchors = getView(template, viewId).anchors.filter((a) => !componentIds?.length || componentIds.includes(a.componentId));
  let best: TemplateAnchor | undefined;
  let bestD = Infinity;
  for (const a of anchors) {
    const d = Math.hypot(a.x - x, a.y - y);
    if (d < bestD) {
      bestD = d;
      best = a;
    }
  }
  return best;
}

export function isCalibrated(template: GarmentTemplate): boolean {
  return template.calibration !== null;
}

function referencePoint(t: Transform, reference: Placement['reference']): { x: number; y: number } {
  return reference === 'center' ? { x: t.x, y: t.y } : { x: t.x, y: t.y - t.height / 2 };
}

/**
 * Canvas edit → placement estimate. Only possible with a calibrated (nominal) template;
 * the result is always marked `canvas-estimate` (visual), never `entered`.
 */
export function placementFromTransform(template: GarmentTemplate, t: Transform, prev: Placement): Placement {
  const cal = template.calibration;
  if (!cal) return prev;
  const anchor = findAnchor(template, prev.anchorId);
  const k = cal.mmPerUnit;
  const ref = referencePoint(t, prev.reference);
  return {
    ...prev,
    widthMm: roundMm(t.width * k),
    heightMm: roundMm(t.height * k),
    offsetXmm: anchor ? roundMm((ref.x - anchor.x) * k) : prev.offsetXmm,
    offsetYmm: anchor ? roundMm((ref.y - anchor.y) * k) : prev.offsetYmm,
    source: 'canvas-estimate',
  };
}

/** Manufacturing dimensions entered → canvas transform (visual follows the spec). */
export function transformFromPlacement(template: GarmentTemplate, p: Placement, prev: Transform): Transform {
  const cal = template.calibration;
  if (!cal) return prev;
  const k = cal.mmPerUnit;
  const width = p.widthMm / k;
  const height = p.heightMm / k;
  const anchor = findAnchor(template, p.anchorId);
  if (!anchor) return { ...prev, width, height };
  const refX = anchor.x + p.offsetXmm / k;
  const refY = anchor.y + p.offsetYmm / k;
  return {
    ...prev,
    width,
    height,
    x: refX,
    y: p.reference === 'center' ? refY : refY + height / 2,
  };
}

/** Apply a user-entered placement change, keeping the canvas in sync and marking it entered. */
export function applyEnteredPlacement(template: GarmentTemplate, layer: ArtworkLayer, patch: Partial<Placement>): ArtworkLayer {
  let placement: Placement = { ...layer.placement, ...patch, source: 'entered' };
  if (layer.lockAspect && (patch.widthMm !== undefined) !== (patch.heightMm !== undefined)) {
    const ratio = layer.transform.width / layer.transform.height;
    if (patch.widthMm !== undefined) placement.heightMm = roundMm(patch.widthMm / ratio);
    else if (patch.heightMm !== undefined) placement.widthMm = roundMm(patch.heightMm * ratio);
  }
  // Changing the anchor/reference re-expresses the current position relative to the new anchor.
  if ((patch.anchorId !== undefined || patch.reference !== undefined) && patch.offsetXmm === undefined && patch.offsetYmm === undefined) {
    const est = placementFromTransform(template, layer.transform, { ...placement });
    placement = { ...placement, offsetXmm: est.offsetXmm, offsetYmm: est.offsetYmm };
  }
  const transform = transformFromPlacement(template, placement, layer.transform);
  return { ...layer, placement, transform };
}

/** Apply a canvas transform change, updating the placement estimate. */
export function applyCanvasTransform(template: GarmentTemplate, layer: ArtworkLayer, transform: Transform): ArtworkLayer {
  const sizeChanged =
    Math.abs(transform.width - layer.transform.width) > 1e-6 || Math.abs(transform.height - layer.transform.height) > 1e-6;
  const moved = Math.abs(transform.x - layer.transform.x) > 1e-6 || Math.abs(transform.y - layer.transform.y) > 1e-6;
  if (!sizeChanged && !moved) return { ...layer, transform };
  const placement = placementFromTransform(template, transform, layer.placement);
  return { ...layer, transform, placement };
}

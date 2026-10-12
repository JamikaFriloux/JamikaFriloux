/**
 * Ghost-mockup asset specifications (authoring source).
 *
 * Each garment defines:
 *  - a warp: technical coordinates → mockup coordinates (sampled into a mesh),
 *  - fold/shading primitives authored in TECHNICAL coordinates (so they stay matched to
 *    the template), which the generator warps into mockup space and rasterises as
 *    shadow / highlight / displacement SVG maps.
 *
 * Output quality tier: `procedural-v1` (hand-authored vector shading, not photographic).
 */

export interface Stroke {
  /** Polyline points in technical coordinates. */
  pts: [number, number][];
  width: number;
  /** 0..1 darkness (shadow) or brightness (highlight). */
  strength: number;
  blur: number;
}

export interface Blob {
  cx: number;
  cy: number;
  rx: number;
  ry: number;
  strength: number;
  rotate?: number;
}

export interface ViewShading {
  shadows: Stroke[];
  shadowBlobs: Blob[];
  highlights: Stroke[];
  highlightBlobs: Blob[];
  /** Strokes that bend artwork (darker = pushed down/right in displacement). */
  displacement: Stroke[];
}

export interface GarmentGhostSpec {
  templateId: string;
  version: number;
  mockup: { width: number; height: number; scale: number; offsetX: number; offsetY: number };
  techBounds: [number, number, number, number];
  mesh: { cols: number; rows: number };
  warp: (x: number, y: number, view: 'front' | 'back') => [number, number];
  views: Record<'front' | 'back', ViewShading>;
  foregroundComponents: Record<'front' | 'back', string[]>;
}

const smooth = (e0: number, e1: number, x: number) => {
  const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0)));
  return t * t * (3 - 2 * t);
};

function rotateAbout(x: number, y: number, cx: number, cy: number, a: number): [number, number] {
  const dx = x - cx;
  const dy = y - cy;
  return [cx + dx * Math.cos(a) - dy * Math.sin(a), cy + dx * Math.sin(a) + dy * Math.cos(a)];
}

const mirror = (s: Stroke): Stroke => ({ ...s, pts: s.pts.map(([x, y]) => [1000 - x, y]) });
const mirrorBlob = (b: Blob): Blob => ({ ...b, cx: 1000 - b.cx, rotate: b.rotate ? -b.rotate : undefined });
const both = (list: Stroke[]) => [...list, ...list.map(mirror)];
const bothBlobs = (list: Blob[]) => [...list, ...list.map(mirrorBlob)];

/* ------------------------------------------------------------------ */
/* Boxy T-shirt                                                        */
/* ------------------------------------------------------------------ */

const teeShadowsCommon: Stroke[] = [
  // Underarm drag lines (from armpit toward center chest/waist).
  { pts: [[212, 350], [250, 378], [292, 398], [330, 410]], width: 14, strength: 0.3, blur: 8 },
  { pts: [[214, 392], [252, 430], [290, 468]], width: 12, strength: 0.16, blur: 9 },
  // Soft S-shaped drape falling from the underarm.
  { pts: [[222, 380], [246, 450], [238, 540], [252, 640], [244, 740]], width: 26, strength: 0.12, blur: 18 },
  // Hem ripples (short, low folds near the hem only).
  { pts: [[318, 640], [312, 700], [318, 752]], width: 18, strength: 0.06, blur: 14 },
  { pts: [[410, 670], [414, 752]], width: 14, strength: 0.04, blur: 12 },
  // Sleeve: fold under the top crease and shadow along the underarm.
  { pts: [[196, 150], [150, 196], [100, 262], [74, 300]], width: 20, strength: 0.14, blur: 12 },
  { pts: [[198, 336], [150, 362], [104, 392]], width: 26, strength: 0.32, blur: 12 },
  { pts: [[60, 236], [90, 320], [104, 384]], width: 12, strength: 0.16, blur: 7 },
  // Armhole seam valley.
  { pts: [[212, 110], [207, 220], [205, 330]], width: 9, strength: 0.18, blur: 5 },
  // Shoulder slope falloff.
  { pts: [[400, 74], [300, 100], [218, 118]], width: 16, strength: 0.08, blur: 10 },
];

const teeHighlightsCommon: Stroke[] = [
  // Shoulder crest and sleeve top fold.
  { pts: [[404, 64], [300, 84], [214, 106]], width: 16, strength: 0.26, blur: 9 },
  { pts: [[206, 112], [130, 168], [48, 228]], width: 14, strength: 0.2, blur: 8 },
  // Ridge beside the drape fold.
  { pts: [[268, 420], [264, 540], [276, 650]], width: 22, strength: 0.08, blur: 16 },
  // Sleeve hem roll.
  { pts: [[44, 232], [76, 318], [104, 386]], width: 8, strength: 0.16, blur: 5 },
];

const teeHemShadow: Stroke = { pts: [[206, 754], [500, 758], [794, 754]], width: 12, strength: 0.28, blur: 6 };
const teeHemHighlight: Stroke = { pts: [[210, 742], [500, 746], [790, 742]], width: 8, strength: 0.2, blur: 5 };

export const tshirtGhost: GarmentGhostSpec = {
  templateId: 'tshirt-boxy',
  version: 1,
  mockup: { width: 1000, height: 880, scale: 0.9, offsetX: 50, offsetY: 52 },
  techBounds: [0, 0, 1000, 820],
  mesh: { cols: 21, rows: 18 },
  warp: (x, y) => {
    let X = x;
    let Y = y;
    // Sleeves hang slightly lower than on the flat (rotation about the shoulder point).
    if (x < 212) {
      const w = smooth(0, 60, 212 - x) * smooth(60, 140, y + 40);
      [X, Y] = rotateAbout(X, Y, 212, 104, -0.11 * w);
    } else if (x > 788) {
      const w = smooth(0, 60, x - 788) * smooth(60, 140, y + 40);
      [X, Y] = rotateAbout(X, Y, 788, 104, 0.11 * w);
    }
    // Body volume: hem bows toward the viewer (drops at center), sides ease in at the waist.
    const bx = Math.min(1, Math.abs(x - 500) / 300);
    Y += 12 * (1 - bx * bx) * smooth(560, 760, y);
    if (x >= 204 && x <= 796) {
      const side = x < 500 ? 1 : -1;
      X += side * 7 * Math.sin(Math.PI * Math.min(1, Math.max(0, (y - 340) / 420))) * smooth(150, 296, Math.abs(x - 500));
    }
    return [X, Y];
  },
  views: {
    front: {
      shadows: [...both(teeShadowsCommon), teeHemShadow],
      shadowBlobs: [
        // Waist/hem side shading and a gentle darkening toward the hem.
        ...bothBlobs([{ cx: 228, cy: 560, rx: 46, ry: 220, strength: 0.14 }]),
        { cx: 500, cy: 760, rx: 330, ry: 70, strength: 0.08 },
      ],
      highlights: [...both(teeHighlightsCommon), teeHemHighlight],
      highlightBlobs: [{ cx: 500, cy: 300, rx: 210, ry: 140, strength: 0.16 }, { cx: 500, cy: 560, rx: 160, ry: 160, strength: 0.07 }],
      displacement: [
        ...both([
          { pts: [[214, 352], [262, 392], [318, 420]], width: 18, strength: 0.6, blur: 10 },
          { pts: [[222, 380], [246, 450], [238, 540], [252, 640], [244, 740]], width: 30, strength: 0.4, blur: 18 },
        ]),
      ],
    },
    back: {
      shadows: [
        ...both(teeShadowsCommon),
        teeHemShadow,
        // Center back valley.
        { pts: [[500, 220], [496, 460], [502, 720]], width: 44, strength: 0.06, blur: 28 },
      ],
      shadowBlobs: [...bothBlobs([{ cx: 228, cy: 560, rx: 46, ry: 220, strength: 0.14 }]), { cx: 500, cy: 760, rx: 330, ry: 70, strength: 0.08 }],
      highlights: [...both(teeHighlightsCommon), teeHemHighlight],
      // Shoulder blades.
      highlightBlobs: [...bothBlobs([{ cx: 380, cy: 230, rx: 110, ry: 90, strength: 0.14 }]), { cx: 500, cy: 520, rx: 180, ry: 160, strength: 0.06 }],
      displacement: both([{ pts: [[222, 380], [246, 450], [238, 540], [252, 640], [244, 740]], width: 30, strength: 0.4, blur: 18 }]),
    },
  },
  foregroundComponents: { front: ['neck_rib'], back: ['neck_rib'] },
};

export const GHOST_SPECS: GarmentGhostSpec[] = [tshirtGhost];

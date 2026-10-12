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

/* ------------------------------------------------------------------ */
/* Pullover hoodie                                                     */
/* ------------------------------------------------------------------ */

const hoodieShadows: Stroke[] = [
  // Underarm drag and sleeve inner shadow.
  { pts: [[204, 690], [250, 730], [300, 760]], width: 16, strength: 0.26, blur: 10 },
  { pts: [[196, 700], [120, 770], [20, 850]], width: 30, strength: 0.28, blur: 14 },
  // Elbow creases (fleece bunches toward the cuff).
  { pts: [[60, 720], [20, 740]], width: 12, strength: 0.22, blur: 6 },
  { pts: [[0, 790], [-50, 800]], width: 10, strength: 0.2, blur: 6 },
  { pts: [[-70, 830], [-110, 838]], width: 9, strength: 0.18, blur: 5 },
  // Body side drape and blouson over the hem band.
  { pts: [[226, 700], [240, 820], [230, 960]], width: 30, strength: 0.14, blur: 18 },
  { pts: [[260, 960], [500, 966], [740, 960]], width: 14, strength: 0.22, blur: 7 },
  // Armhole valley.
  { pts: [[205, 392], [203, 540], [201, 680]], width: 10, strength: 0.18, blur: 6 },
];
const hoodieHighlights: Stroke[] = [
  { pts: [[398, 346], [300, 368], [210, 388]], width: 18, strength: 0.24, blur: 10 },
  { pts: [[200, 392], [100, 520], [-110, 790]], width: 18, strength: 0.18, blur: 10 },
  { pts: [[290, 950], [500, 956], [710, 950]], width: 10, strength: 0.14, blur: 6 },
];

export const hoodieGhost: GarmentGhostSpec = {
  templateId: 'hoodie-pullover',
  version: 1,
  mockup: { width: 1000, height: 820, scale: 0.68, offsetX: 160, offsetY: 6 },
  techBounds: [-200, 30, 1400, 1060],
  mesh: { cols: 25, rows: 20 },
  warp: (x, y) => {
    let X = x;
    let Y = y;
    // Sleeves relax inward toward the body (ghost mannequin arms hang).
    if (x < 205) {
      const w = smooth(0, 120, 205 - x) * smooth(380, 520, y);
      [X, Y] = rotateAbout(X, Y, 205, 385, -0.08 * w);
    } else if (x > 795) {
      const w = smooth(0, 120, x - 795) * smooth(380, 520, y);
      [X, Y] = rotateAbout(X, Y, 795, 385, 0.08 * w);
    }
    // Blouson: body billows slightly above the hem band.
    const bx = Math.min(1, Math.abs(x - 500) / 300);
    if (x > 200 && x < 800) X += (x < 500 ? -1 : 1) * 8 * smooth(700, 940, y) * smooth(1000, 950, y) * smooth(150, 290, Math.abs(x - 500));
    Y += 10 * (1 - bx * bx) * smooth(800, 1040, y);
    // Hood stands with volume: widen slightly at the crown.
    if (y < 340) X += (x - 500) * 0.05 * smooth(340, 120, y);
    return [X, Y];
  },
  views: {
    front: {
      shadows: [
        ...both(hoodieShadows),
        // Hood interior depth (drawn inside the opening; masked to the garment).
        { pts: [[430, 150], [420, 250], [450, 340]], width: 40, strength: 0.25, blur: 20 },
        { pts: [[570, 150], [580, 250], [550, 340]], width: 40, strength: 0.25, blur: 20 },
        // Hood edge rolls onto the shoulders.
        { pts: [[390, 330], [440, 370], [500, 384]], width: 12, strength: 0.25, blur: 7 },
        { pts: [[610, 330], [560, 370], [500, 384]], width: 12, strength: 0.25, blur: 7 },
        // Pocket lip shadow.
        { pts: [[283, 910], [312, 850], [362, 748]], width: 10, strength: 0.3, blur: 6 },
        { pts: [[717, 910], [688, 850], [638, 748]], width: 10, strength: 0.3, blur: 6 },
        { pts: [[272, 958], [500, 960], [728, 958]], width: 8, strength: 0.2, blur: 5 },
      ],
      shadowBlobs: bothBlobs([{ cx: 228, cy: 820, rx: 40, ry: 150, strength: 0.14 }]),
      highlights: [
        ...both(hoodieHighlights),
        { pts: [[360, 110], [420, 70], [500, 60]], width: 22, strength: 0.18, blur: 14 },
        { pts: [[640, 110], [580, 70], [500, 60]], width: 22, strength: 0.18, blur: 14 },
      ],
      highlightBlobs: [{ cx: 500, cy: 520, rx: 200, ry: 150, strength: 0.14 }],
      displacement: both([{ pts: [[204, 690], [250, 730], [300, 760]], width: 18, strength: 0.6, blur: 10 }]),
    },
    back: {
      shadows: [
        ...both(hoodieShadows),
        { pts: [[500, 80], [500, 200], [500, 340]], width: 20, strength: 0.14, blur: 10 },
        { pts: [[380, 340], [440, 362], [500, 368], [560, 362], [620, 340]], width: 30, strength: 0.3, blur: 14 },
      ],
      shadowBlobs: bothBlobs([{ cx: 228, cy: 820, rx: 40, ry: 150, strength: 0.14 }]),
      highlights: [...both(hoodieHighlights), ...both([{ pts: [[380, 120], [400, 220], [440, 300]], width: 30, strength: 0.14, blur: 18 }])],
      highlightBlobs: bothBlobs([{ cx: 380, cy: 480, rx: 110, ry: 90, strength: 0.12 }]),
      displacement: both([{ pts: [[226, 700], [240, 820], [230, 960]], width: 30, strength: 0.4, blur: 18 }]),
    },
  },
  foregroundComponents: { front: ['hood', 'drawcord', 'kangaroo_pocket'], back: ['hood'] },
};

/* ------------------------------------------------------------------ */
/* Straight-leg sweatpants                                             */
/* ------------------------------------------------------------------ */

const pantsShadows: Stroke[] = [
  // Crotch/inseam drag and knee folds.
  { pts: [[486, 368], [440, 420], [400, 460]], width: 16, strength: 0.24, blur: 9 },
  { pts: [[470, 650], [400, 680], [330, 700]], width: 12, strength: 0.09, blur: 10 },
  { pts: [[466, 760], [380, 790], [300, 805]], width: 10, strength: 0.07, blur: 9 },
  // Stacking above the hem.
  { pts: [[262, 960], [360, 975], [460, 962]], width: 10, strength: 0.18, blur: 7 },
  { pts: [[262, 1010], [360, 1020], [462, 1008]], width: 8, strength: 0.14, blur: 6 },
  // Side seam valley and waistband gather shadow.
  { pts: [[240, 300], [250, 700], [260, 1070]], width: 18, strength: 0.14, blur: 12 },
  { pts: [[318, 96], [500, 100], [682, 96]], width: 10, strength: 0.28, blur: 6 },
  // Center crease side shadow.
  { pts: [[372, 420], [372, 1040]], width: 14, strength: 0.07, blur: 10 },
];
const pantsHighlights: Stroke[] = [
  { pts: [[356, 420], [356, 1040]], width: 10, strength: 0.14, blur: 7 },
  { pts: [[262, 300], [300, 200], [330, 120]], width: 26, strength: 0.14, blur: 16 },
  { pts: [[330, 50], [500, 48], [670, 50]], width: 10, strength: 0.16, blur: 6 },
];

export const pantsGhost: GarmentGhostSpec = {
  templateId: 'sweatpants-straight',
  version: 1,
  mockup: { width: 760, height: 1000, scale: 0.86, offsetX: -59, offsetY: 18 },
  techBounds: [150, 10, 700, 1110],
  mesh: { cols: 14, rows: 26 },
  warp: (x, y) => {
    let X = x;
    const Y = y;
    // Legs taper a touch toward the hem as fabric falls; seat volume in the hip.
    const side = x < 500 ? -1 : 1;
    X += side * 6 * smooth(120, 300, y) * smooth(420, 300, y);
    X -= side * 6 * smooth(600, 1080, y) * smooth(80, 240, Math.abs(x - 500));
    return [X, Y];
  },
  views: {
    front: {
      shadows: [...both(pantsShadows), { pts: [[500, 100], [500, 300], [490, 360]], width: 10, strength: 0.16, blur: 6 }],
      shadowBlobs: [],
      highlights: both(pantsHighlights),
      highlightBlobs: bothBlobs([{ cx: 370, cy: 330, rx: 90, ry: 120, strength: 0.1 }]),
      displacement: both([{ pts: [[470, 650], [400, 680], [330, 700]], width: 16, strength: 0.5, blur: 9 }]),
    },
    back: {
      shadows: [...both(pantsShadows), { pts: [[500, 100], [500, 320], [482, 390]], width: 14, strength: 0.2, blur: 8 }],
      shadowBlobs: bothBlobs([{ cx: 400, cy: 380, rx: 100, ry: 40, strength: 0.14 }]),
      highlights: both(pantsHighlights),
      highlightBlobs: bothBlobs([{ cx: 380, cy: 250, rx: 110, ry: 110, strength: 0.14 }]),
      displacement: both([{ pts: [[470, 650], [400, 680], [330, 700]], width: 16, strength: 0.5, blur: 9 }]),
    },
  },
  foregroundComponents: { front: ['waistband', 'drawcord'], back: ['waistband', 'back_pocket'] },
};

export const GHOST_SPECS: GarmentGhostSpec[] = [tshirtGhost, hoodieGhost, pantsGhost];

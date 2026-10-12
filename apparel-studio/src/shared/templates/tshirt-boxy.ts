import type { GarmentTemplate } from '../schema/template';
import { mirrorPath } from '../geometry';

/**
 * Boxy T-shirt, template v1.
 * Coordinate system: 1 unit = 1 mm at base size M (nominal drawing scale), origin top-left,
 * viewBox 1000 x 820. Front view: wearer's RIGHT is on the viewer's LEFT.
 * Geometry is a dropped-shoulder boxy block: 592 mm half chest, 700 mm HPS length.
 */

// ---- Shared outlines (viewer-left side; right side is mirrored) ----
const ARMHOLE_L = 'M212,104 C206,180 202,270 204,336';
const SLEEVE_L =
  'M212,104 C150,142 92,186 34,228 L96,398 C132,377 168,357 204,336 C202,270 206,180 212,104 Z';
const BODY_SIDES =
  'L212,104 C206,180 202,270 204,336 L204,760 C400,764 600,764 796,760 L796,336 C798,270 794,180 788,104 L595,60';

const FRONT_NECK_SEAM = 'C590,138 548,170 500,170 C452,170 410,138 405,60';
const BODY_FRONT = `M405,60 ${BODY_SIDES} ${FRONT_NECK_SEAM} Z`;
const BODY_BACK = `M405,60 ${BODY_SIDES} C560,80 440,80 405,60 Z`;

const NECK_RIB_FRONT =
  'M405,60 C410,138 452,170 500,170 C548,170 590,138 595,60 L576,50 C572,120 538,148 500,148 C462,148 428,120 424,50 Z';
const NECK_RIB_BACK_SEEN_FROM_FRONT = 'M405,60 C440,80 560,80 595,60 L576,50 C545,64 455,64 424,50 Z';
const INNER_BACK = 'M424,50 C428,120 462,148 500,148 C538,148 572,120 576,50 C545,64 455,64 424,50 Z';
const NECK_RIB_BACK = 'M405,60 C440,80 560,80 595,60 L576,50 C545,60 455,60 424,50 Z';

const SLEEVE_HEM_STITCH_L = 'M54,214 L117,386';
const SLEEVE_SEAM_L = 'M96,398 C132,377 168,357 204,336';
const SIDE_SEAM_L = 'M204,336 L204,760';
const SHOULDER_L = 'M405,60 L212,104';
const HEM_STITCH = 'M204,738 C400,742 600,742 796,738';

/** Front view: viewer-left sleeve is the wearer's right sleeve. */
const frontSleeveRight = SLEEVE_L;
const frontSleeveLeft = mirrorPath(SLEEVE_L);
/** Back view: viewer-left sleeve is the wearer's left sleeve. */
const backSleeveLeft = SLEEVE_L;
const backSleeveRight = mirrorPath(SLEEVE_L);

const shellMethods = ['screen-print', 'dtg', 'embroidery', 'puff-print', 'heat-transfer', 'applique', 'rhinestone', 'stud'] as const;
const sleeveMethods = ['screen-print', 'dtg', 'embroidery', 'heat-transfer', 'rhinestone', 'stud'] as const;

export const tshirtBoxyV1: GarmentTemplate = {
  id: 'tshirt-boxy',
  version: 1,
  name: 'Boxy T-shirt',
  category: 'top',
  description:
    'Dropped-shoulder boxy tee with 1x1 rib crew neck, set-in short sleeves, coverstitched sleeve and bottom hems.',
  structure: { closure: 'pullover', features: ['crew neck', 'dropped shoulder', 'short sleeve', 'straight hem'] },
  sizes: { available: ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL'], defaultBase: 'M', defaultRange: ['XS', 'S', 'M', 'L', 'XL'] },
  calibration: {
    kind: 'nominal-drawing-scale',
    mmPerUnit: 1,
    baseSize: 'M',
    note: 'Drawn at 1 unit = 1 mm for the template default size M. Canvas-derived placement is an estimate until you enter manufacturing dimensions.',
  },
  components: [
    { id: 'body_front', name: 'Front body', group: 'body', materialRole: 'shell', decorationMethods: [...shellMethods] },
    { id: 'body_back', name: 'Back body', group: 'body', materialRole: 'shell', decorationMethods: [...shellMethods] },
    { id: 'sleeve_left', name: 'Left sleeve (wearer’s left)', group: 'sleeve', materialRole: 'shell', decorationMethods: [...sleeveMethods] },
    { id: 'sleeve_right', name: 'Right sleeve (wearer’s right)', group: 'sleeve', materialRole: 'shell', decorationMethods: [...sleeveMethods] },
    { id: 'neck_rib', name: 'Neck rib', group: 'trim', materialRole: 'rib', decorationMethods: ['heat-transfer'] },
  ],
  views: [
    {
      id: 'front',
      label: 'Front',
      viewBox: [0, 0, 1000, 820],
      panels: [
        { id: 'f_inner_back', componentId: 'body_back', d: INNER_BACK, z: 0, side: 'inner' },
        { id: 'f_neck_rib_back', componentId: 'neck_rib', d: NECK_RIB_BACK_SEEN_FROM_FRONT, z: 1, side: 'inner' },
        { id: 'f_body', componentId: 'body_front', d: BODY_FRONT, z: 2, side: 'outer' },
        { id: 'f_sleeve_right', componentId: 'sleeve_right', d: frontSleeveRight, z: 3, side: 'outer' },
        { id: 'f_sleeve_left', componentId: 'sleeve_left', d: frontSleeveLeft, z: 3, side: 'outer' },
        { id: 'f_neck_rib', componentId: 'neck_rib', d: NECK_RIB_FRONT, z: 4, side: 'outer' },
      ],
      seams: [
        { id: 'shoulder_right', name: 'Right shoulder seam', d: SHOULDER_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'shoulder_left', name: 'Left shoulder seam', d: mirrorPath(SHOULDER_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'armhole_right', name: 'Right armhole seam', d: ARMHOLE_L, componentIds: ['body_front', 'sleeve_right'], defaultStyle: 'overlock' },
        { id: 'armhole_left', name: 'Left armhole seam', d: mirrorPath(ARMHOLE_L), componentIds: ['body_front', 'sleeve_left'], defaultStyle: 'overlock' },
        { id: 'side_right', name: 'Right side seam', d: SIDE_SEAM_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'side_left', name: 'Left side seam', d: mirrorPath(SIDE_SEAM_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_right', name: 'Right underarm seam', d: SLEEVE_SEAM_L, componentIds: ['sleeve_right'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_left', name: 'Left underarm seam', d: mirrorPath(SLEEVE_SEAM_L), componentIds: ['sleeve_left'], defaultStyle: 'overlock' },
        { id: 'sleeve_hem_right', name: 'Right sleeve hem', d: SLEEVE_HEM_STITCH_L, componentIds: ['sleeve_right'], defaultStyle: 'coverstitch' },
        { id: 'sleeve_hem_left', name: 'Left sleeve hem', d: mirrorPath(SLEEVE_HEM_STITCH_L), componentIds: ['sleeve_left'], defaultStyle: 'coverstitch' },
        { id: 'bottom_hem', name: 'Bottom hem', d: HEM_STITCH, componentIds: ['body_front', 'body_back'], defaultStyle: 'coverstitch' },
        { id: 'neck_topstitch', name: 'Neck rib topstitch', d: 'M400,64 C405,145 450,176 500,176 C550,176 595,145 600,64', componentIds: ['body_front', 'neck_rib'], defaultStyle: 'coverstitch' },
      ],
      details: [],
      anchors: [
        { id: 'cf_neck', label: 'Center front neck', x: 500, y: 170, componentId: 'body_front', description: 'Center front at the neck rib seam.' },
        { id: 'center_chest', label: 'Center chest', x: 500, y: 250, componentId: 'body_front', description: 'Center front, 80 mm below the neck seam (template reference).' },
        { id: 'left_chest', label: 'Left chest', x: 605, y: 250, componentId: 'body_front', description: 'Wearer’s left chest, 105 mm from center front, level with center chest.' },
        { id: 'front_hem_left', label: 'Left front hem', x: 690, y: 700, componentId: 'body_front', description: 'Wearer’s left front, above the bottom hem.' },
        { id: 'sleeve_right_mid', label: 'Right sleeve', x: 128, y: 262, componentId: 'sleeve_right', description: 'Center of the wearer’s right sleeve.' },
        { id: 'sleeve_left_mid', label: 'Left sleeve', x: 872, y: 262, componentId: 'sleeve_left', description: 'Center of the wearer’s left sleeve.' },
        { id: 'inner_neck', label: 'Inside back neck', x: 500, y: 105, componentId: 'body_back', description: 'Inside back neck label / print area.' },
      ],
      measurementLines: [
        { pomId: 'A', from: [405, 60], to: [405, 760], label: [375, 470] },
        { pomId: 'B', from: [204, 361], to: [796, 361], label: [300, 361] },
        { pomId: 'C', from: [204, 760], to: [796, 760], label: [500, 790] },
        { pomId: 'D', from: [212, 104], to: [788, 104], label: [700, 92] },
        { pomId: 'E', from: [212, 104], to: [34, 228], label: [108, 150] },
        { pomId: 'F', from: [34, 228], to: [96, 398], label: [42, 330] },
        { pomId: 'G', from: [212, 104], to: [204, 336], label: [232, 230] },
        { pomId: 'H', from: [405, 60], to: [595, 60], label: [500, 34] },
        { pomId: 'I', from: [500, 60], to: [500, 170], label: [525, 120] },
        { pomId: 'K', from: [500, 148], to: [500, 170], label: [470, 200] },
        { pomId: 'L', from: [204, 336], to: [98, 183], label: [140, 300] },
      ],
    },
    {
      id: 'back',
      label: 'Back',
      viewBox: [0, 0, 1000, 820],
      panels: [
        { id: 'b_body', componentId: 'body_back', d: BODY_BACK, z: 2, side: 'outer' },
        { id: 'b_sleeve_left', componentId: 'sleeve_left', d: backSleeveLeft, z: 3, side: 'outer' },
        { id: 'b_sleeve_right', componentId: 'sleeve_right', d: backSleeveRight, z: 3, side: 'outer' },
        { id: 'b_neck_rib', componentId: 'neck_rib', d: NECK_RIB_BACK, z: 4, side: 'outer' },
      ],
      seams: [
        { id: 'shoulder_left', name: 'Left shoulder seam', d: SHOULDER_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'shoulder_right', name: 'Right shoulder seam', d: mirrorPath(SHOULDER_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'armhole_left', name: 'Left armhole seam', d: ARMHOLE_L, componentIds: ['body_back', 'sleeve_left'], defaultStyle: 'overlock' },
        { id: 'armhole_right', name: 'Right armhole seam', d: mirrorPath(ARMHOLE_L), componentIds: ['body_back', 'sleeve_right'], defaultStyle: 'overlock' },
        { id: 'side_left', name: 'Left side seam', d: SIDE_SEAM_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'side_right', name: 'Right side seam', d: mirrorPath(SIDE_SEAM_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_left', name: 'Left underarm seam', d: SLEEVE_SEAM_L, componentIds: ['sleeve_left'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_right', name: 'Right underarm seam', d: mirrorPath(SLEEVE_SEAM_L), componentIds: ['sleeve_right'], defaultStyle: 'overlock' },
        { id: 'sleeve_hem_left', name: 'Left sleeve hem', d: SLEEVE_HEM_STITCH_L, componentIds: ['sleeve_left'], defaultStyle: 'coverstitch' },
        { id: 'sleeve_hem_right', name: 'Right sleeve hem', d: mirrorPath(SLEEVE_HEM_STITCH_L), componentIds: ['sleeve_right'], defaultStyle: 'coverstitch' },
        { id: 'bottom_hem', name: 'Bottom hem', d: HEM_STITCH, componentIds: ['body_front', 'body_back'], defaultStyle: 'coverstitch' },
        { id: 'back_neck_tape', name: 'Back neck tape topstitch', d: 'M400,64 C438,86 562,86 600,64', componentIds: ['body_back', 'neck_rib'], defaultStyle: 'coverstitch' },
      ],
      details: [],
      anchors: [
        { id: 'cb_neck', label: 'Center back neck', x: 500, y: 78, componentId: 'body_back', description: 'Center back at the neck seam.' },
        { id: 'upper_back', label: 'Upper back', x: 500, y: 190, componentId: 'body_back', description: 'Center back, 112 mm below the neck seam (template reference).' },
        { id: 'center_back', label: 'Center back', x: 500, y: 400, componentId: 'body_back', description: 'Center of the back panel.' },
        { id: 'back_hem', label: 'Back hem', x: 500, y: 700, componentId: 'body_back', description: 'Center back above the bottom hem.' },
        { id: 'sleeve_left_back', label: 'Left sleeve (back)', x: 128, y: 262, componentId: 'sleeve_left', description: 'Back of the wearer’s left sleeve.' },
        { id: 'sleeve_right_back', label: 'Right sleeve (back)', x: 872, y: 262, componentId: 'sleeve_right', description: 'Back of the wearer’s right sleeve.' },
      ],
      measurementLines: [{ pomId: 'J', from: [500, 60], to: [500, 78], label: [530, 40] }],
    },
  ],
  poms: [
    { id: 'A', code: 'A', label: 'Body length from HPS', howToMeasure: 'From high point shoulder (where shoulder seam meets neck rib) straight down to the bottom edge of the hem, garment laid flat.', view: 'front', defaultMm: 700, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'B', code: 'B', label: 'Chest width (1" below armhole)', howToMeasure: 'Straight across the front, edge to edge, 25 mm below the underarm point.', view: 'front', defaultMm: 592, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'C', code: 'C', label: 'Sweep (bottom width)', howToMeasure: 'Straight across the bottom edge of the hem, edge to edge, relaxed.', view: 'front', defaultMm: 592, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'D', code: 'D', label: 'Across shoulder', howToMeasure: 'From shoulder point to shoulder point (where shoulder seam meets armhole seam).', view: 'front', defaultMm: 576, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'E', code: 'E', label: 'Sleeve length from shoulder point', howToMeasure: 'Along the top fold of the sleeve from shoulder point to sleeve hem edge.', view: 'front', defaultMm: 217, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'F', code: 'F', label: 'Sleeve opening (half)', howToMeasure: 'Straight across the sleeve hem edge, laid flat.', view: 'front', defaultMm: 181, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'G', code: 'G', label: 'Armhole (straight)', howToMeasure: 'Straight line from shoulder point to underarm point along the armhole seam.', view: 'front', defaultMm: 232, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'H', code: 'H', label: 'Neck width (seam to seam)', howToMeasure: 'Straight across from high point shoulder to high point shoulder at the neck seam.', view: 'front', defaultMm: 190, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'I', code: 'I', label: 'Front neck drop', howToMeasure: 'From an imaginary line between both HPS down to the center front neck seam.', view: 'front', defaultMm: 110, tolPlusMm: 3.2, tolMinusMm: 3.2 },
    { id: 'J', code: 'J', label: 'Back neck drop', howToMeasure: 'From an imaginary line between both HPS down to the center back neck seam.', view: 'back', defaultMm: 18, tolPlusMm: 3.2, tolMinusMm: 3.2 },
    { id: 'K', code: 'K', label: 'Neck rib height', howToMeasure: 'Rib width at center front, from seam to finished edge.', view: 'front', defaultMm: 22, tolPlusMm: 1.6, tolMinusMm: 1.6 },
    { id: 'L', code: 'L', label: 'Bicep (half)', howToMeasure: 'From the underarm point perpendicular to the top sleeve fold.', view: 'front', defaultMm: 186, tolPlusMm: 6.4, tolMinusMm: 6.4 },
  ],
  ghost: null,
};

import type { GarmentTemplate } from '../schema/template';
import { circlePath, mirrorPath, ribLines } from '../geometry';
import ghostAssets from './ghost/sweatpants-straight-v1.json';

/**
 * Straight-leg sweatpants, template v1.
 * 1 unit = 1 mm at base size M (nominal drawing scale), symmetric about x = 500.
 * Front view: wearer's RIGHT leg on the viewer's LEFT. Elastic waistband with internal drawcord
 * exiting through two front eyelets, on-seam side pockets, one back patch pocket (wearer's right),
 * straight hemmed leg openings.
 */

// Front leg (viewer-left = wearer's right). Waistband seam at y=90, crotch at (488,360).
const FRONT_LEG_L = 'M316,90 L500,90 L500,300 C500,330 496,348 488,360 L462,1080 L260,1080 L236,300 C240,220 276,150 316,90 Z';
// Back leg (viewer-left = wearer's left in back view): wider seat, higher back rise.
const BACK_LEG_L = 'M316,90 L500,96 L500,320 C500,352 492,372 480,388 L462,1080 L260,1080 L232,300 C236,220 272,150 316,90 Z';
const WAISTBAND = 'M320,40 L680,40 L684,90 L316,90 Z';
const CORD_L = 'M484,66 C478,120 488,170 480,226 L490,226 C496,170 486,120 494,66 Z';
const AGLET_L = 'M478,226 L492,226 L491,252 L479,252 Z';
const BACK_POCKET = 'M560,170 L690,170 L686,320 L564,320 Z';

const OUTSEAM_L = 'M316,90 C276,150 240,220 236,300 L260,1080';
const INSEAM_FRONT_L = 'M488,360 L462,1080';
const POCKET_OPENING_L = 'M318,96 C300,150 274,200 252,250';
const HEM_STITCH_L = 'M261,1052 L463,1052';

const legMethods = ['screen-print', 'dtg', 'embroidery', 'puff-print', 'heat-transfer', 'applique', 'rhinestone', 'stud', 'sublimation'] as const;

export const sweatpantsStraightV1: GarmentTemplate = {
  id: 'sweatpants-straight',
  version: 1,
  name: 'Straight-leg sweatpants',
  category: 'bottom',
  description: 'Straight-leg sweatpants with elastic waistband and drawcord, on-seam side pockets, back patch pocket, hemmed leg openings.',
  structure: { closure: 'elastic-waist', features: ['elastic waistband', 'internal drawcord', 'on-seam side pockets', 'back patch pocket', 'straight leg', 'hemmed opening'] },
  sizes: { available: ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL'], defaultBase: 'M', defaultRange: ['XS', 'S', 'M', 'L', 'XL'] },
  calibration: {
    kind: 'nominal-drawing-scale',
    mmPerUnit: 1,
    baseSize: 'M',
    note: 'Drawn at 1 unit = 1 mm for the template default size M. Canvas-derived placement is an estimate until you enter manufacturing dimensions.',
  },
  components: [
    { id: 'waistband', name: 'Waistband', group: 'waistband', materialRole: 'rib', decorationMethods: ['embroidery', 'heat-transfer', 'screen-print'] },
    { id: 'leg_front_right', name: 'Right front leg (wearer’s right)', group: 'leg', materialRole: 'shell', decorationMethods: [...legMethods] },
    { id: 'leg_front_left', name: 'Left front leg (wearer’s left)', group: 'leg', materialRole: 'shell', decorationMethods: [...legMethods] },
    { id: 'leg_back_left', name: 'Left back leg (wearer’s left)', group: 'leg', materialRole: 'shell', decorationMethods: [...legMethods] },
    { id: 'leg_back_right', name: 'Right back leg (wearer’s right)', group: 'leg', materialRole: 'shell', decorationMethods: [...legMethods] },
    { id: 'back_pocket', name: 'Back pocket', group: 'pocket', materialRole: 'shell', decorationMethods: ['embroidery', 'heat-transfer', 'screen-print'] },
    { id: 'drawcord', name: 'Drawcord', group: 'trim', materialRole: 'trim', decorationMethods: [] },
  ],
  views: [
    {
      id: 'front',
      label: 'Front',
      viewBox: [150, 10, 700, 1110],
      panels: [
        { id: 'f_leg_right', componentId: 'leg_front_right', d: FRONT_LEG_L, z: 1, side: 'outer' },
        { id: 'f_leg_left', componentId: 'leg_front_left', d: mirrorPath(FRONT_LEG_L), z: 1, side: 'outer' },
        { id: 'f_waistband', componentId: 'waistband', d: WAISTBAND, z: 2, side: 'outer' },
        { id: 'f_cord_right', componentId: 'drawcord', d: CORD_L, z: 3, side: 'outer' },
        { id: 'f_cord_left', componentId: 'drawcord', d: mirrorPath(CORD_L), z: 3, side: 'outer' },
      ],
      seams: [
        { id: 'outseam_right', name: 'Right outseam', d: OUTSEAM_L, componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'overlock' },
        { id: 'outseam_left', name: 'Left outseam', d: mirrorPath(OUTSEAM_L), componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'overlock' },
        { id: 'inseam_right', name: 'Right inseam', d: INSEAM_FRONT_L, componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'overlock' },
        { id: 'inseam_left', name: 'Left inseam', d: mirrorPath(INSEAM_FRONT_L), componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'overlock' },
        { id: 'front_rise', name: 'Front rise seam', d: 'M500,90 L500,300 C500,330 496,348 488,360', componentIds: ['leg_front_right', 'leg_front_left'], defaultStyle: 'double-needle' },
        { id: 'waistband_seam', name: 'Waistband seam', d: 'M316,90 L684,90', componentIds: ['waistband', 'leg_front_right', 'leg_front_left'], defaultStyle: 'overlock' },
        { id: 'waistband_topstitch', name: 'Waistband channel topstitch', d: 'M319,56 L681,56 M318,74 L682,74', componentIds: ['waistband'], defaultStyle: 'single-needle' },
        { id: 'pocket_opening_right', name: 'Right pocket opening', d: POCKET_OPENING_L, componentIds: ['leg_front_right'], defaultStyle: 'single-needle' },
        { id: 'pocket_opening_left', name: 'Left pocket opening', d: mirrorPath(POCKET_OPENING_L), componentIds: ['leg_front_left'], defaultStyle: 'single-needle' },
        { id: 'hem_right', name: 'Right leg hem', d: HEM_STITCH_L, componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'coverstitch' },
        { id: 'hem_left', name: 'Left leg hem', d: mirrorPath(HEM_STITCH_L), componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'coverstitch' },
      ],
      details: [
        { id: 'eyelet_r', d: circlePath(489, 64, 6), kind: 'hardware', componentId: 'waistband' },
        { id: 'eyelet_l', d: circlePath(511, 64, 6), kind: 'hardware', componentId: 'waistband' },
        { id: 'aglet_r', d: AGLET_L, kind: 'hardware', componentId: 'drawcord' },
        { id: 'aglet_l', d: mirrorPath(AGLET_L), kind: 'hardware', componentId: 'drawcord' },
        { id: 'shirring', d: ribLines([[320, 40], [680, 40]], [[316, 90], [684, 90]], 40), kind: 'rib', componentId: 'waistband' },
        { id: 'crease_r', d: 'M360,400 L358,1040', kind: 'fold', componentId: 'leg_front_right' },
        { id: 'crease_l', d: 'M640,400 L642,1040', kind: 'fold', componentId: 'leg_front_left' },
      ],
      anchors: [
        { id: 'left_thigh', label: 'Left thigh', x: 640, y: 330, componentId: 'leg_front_left', description: 'Wearer’s left front thigh, below the pocket opening.' },
        { id: 'right_thigh', label: 'Right thigh', x: 360, y: 330, componentId: 'leg_front_right', description: 'Wearer’s right front thigh, below the pocket opening.' },
        { id: 'left_knee', label: 'Left knee', x: 640, y: 690, componentId: 'leg_front_left', description: 'Wearer’s left front leg at knee height.' },
        { id: 'left_hem', label: 'Left leg hem', x: 640, y: 1000, componentId: 'leg_front_left', description: 'Wearer’s left leg above the hem.' },
        { id: 'waistband_cf', label: 'Waistband center front', x: 500, y: 65, componentId: 'waistband', description: 'Center front of the waistband.' },
      ],
      measurementLines: [
        { pomId: 'A', from: [320, 40], to: [680, 40], label: [600, 24] },
        { pomId: 'C', from: [234, 280], to: [766, 280], label: [300, 280] },
        { pomId: 'D', from: [500, 40], to: [500, 360], label: [520, 220] },
        { pomId: 'F', from: [488, 360], to: [462, 1080], label: [452, 720] },
        { pomId: 'G', from: [320, 40], to: [260, 1080], label: [222, 640] },
        { pomId: 'H', from: [238.6, 385], to: [487.1, 385], label: [300, 400] },
        { pomId: 'I', from: [260, 1080], to: [462, 1080], label: [360, 1100] },
        { pomId: 'J', from: [690, 40], to: [690, 90], label: [720, 65] },
        { pomId: 'K', from: [248, 690], to: [476, 690], label: [300, 705] },
      ],
    },
    {
      id: 'back',
      label: 'Back',
      viewBox: [150, 10, 700, 1110],
      panels: [
        { id: 'b_leg_left', componentId: 'leg_back_left', d: BACK_LEG_L, z: 1, side: 'outer' },
        { id: 'b_leg_right', componentId: 'leg_back_right', d: mirrorPath(BACK_LEG_L), z: 1, side: 'outer' },
        { id: 'b_waistband', componentId: 'waistband', d: WAISTBAND, z: 2, side: 'outer' },
        { id: 'b_pocket', componentId: 'back_pocket', d: BACK_POCKET, z: 3, side: 'outer' },
      ],
      seams: [
        { id: 'outseam_left', name: 'Left outseam', d: 'M316,90 C272,150 236,220 232,300 L260,1080', componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'overlock' },
        { id: 'outseam_right', name: 'Right outseam', d: mirrorPath('M316,90 C272,150 236,220 232,300 L260,1080'), componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'overlock' },
        { id: 'inseam_left', name: 'Left inseam', d: 'M480,388 L462,1080', componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'overlock' },
        { id: 'inseam_right', name: 'Right inseam', d: mirrorPath('M480,388 L462,1080'), componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'overlock' },
        { id: 'back_rise', name: 'Back rise seam', d: 'M500,90 L500,320 C500,352 492,372 480,388', componentIds: ['leg_back_left', 'leg_back_right'], defaultStyle: 'double-needle' },
        { id: 'waistband_seam', name: 'Waistband seam', d: 'M316,90 L684,90', componentIds: ['waistband', 'leg_back_left', 'leg_back_right'], defaultStyle: 'overlock' },
        { id: 'waistband_topstitch', name: 'Waistband channel topstitch', d: 'M319,56 L681,56 M318,74 L682,74', componentIds: ['waistband'], defaultStyle: 'single-needle' },
        { id: 'back_pocket_topstitch', name: 'Back pocket topstitch', d: 'M566,178 L568,314 L682,314 L684,178', componentIds: ['back_pocket'], defaultStyle: 'double-needle' },
        { id: 'hem_left', name: 'Left leg hem', d: HEM_STITCH_L, componentIds: ['leg_front_left', 'leg_back_left'], defaultStyle: 'coverstitch' },
        { id: 'hem_right', name: 'Right leg hem', d: mirrorPath(HEM_STITCH_L), componentIds: ['leg_front_right', 'leg_back_right'], defaultStyle: 'coverstitch' },
      ],
      details: [{ id: 'shirring', d: ribLines([[320, 40], [680, 40]], [[316, 90], [684, 90]], 40), kind: 'rib', componentId: 'waistband' }],
      anchors: [
        { id: 'back_pocket_center', label: 'Back pocket', x: 625, y: 245, componentId: 'back_pocket', description: 'Center of the back patch pocket (wearer’s right).' },
        { id: 'waistband_cb', label: 'Waistband center back', x: 500, y: 65, componentId: 'waistband', description: 'Center back of the waistband.' },
        { id: 'left_back_thigh', label: 'Left back thigh', x: 360, y: 450, componentId: 'leg_back_left', description: 'Wearer’s left back thigh.' },
        { id: 'right_back_calf', label: 'Right back calf', x: 640, y: 820, componentId: 'leg_back_right', description: 'Wearer’s right back leg at calf height.' },
      ],
      measurementLines: [{ pomId: 'E', from: [500, 40], to: [500, 388], label: [522, 220] }],
    },
  ],
  poms: [
    { id: 'A', code: 'A', label: 'Waist relaxed (half)', howToMeasure: 'Across the top edge of the waistband, relaxed.', view: 'front', defaultMm: 360, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'B', code: 'B', label: 'Waist extended (half)', howToMeasure: 'Across the top edge of the waistband, fully stretched. Cannot be read from a drawing — enter from sample or factory spec.', view: 'front', defaultMm: null, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'C', code: 'C', label: 'Hip (half), 180 mm below waist top', howToMeasure: 'Straight across, edge to edge, 180 mm below the top of the waistband.', view: 'front', defaultMm: 532, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'D', code: 'D', label: 'Front rise (incl. waistband)', howToMeasure: 'From the crotch seam junction to the top of the waistband at center front.', view: 'front', defaultMm: 320, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'E', code: 'E', label: 'Back rise (incl. waistband)', howToMeasure: 'From the crotch seam junction to the top of the waistband at center back.', view: 'back', defaultMm: 348, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'F', code: 'F', label: 'Inseam', howToMeasure: 'From the crotch seam junction along the inseam to the leg opening.', view: 'front', defaultMm: 720, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'G', code: 'G', label: 'Outseam (incl. waistband)', howToMeasure: 'From the top of the waistband along the side seam to the leg opening.', view: 'front', defaultMm: 1042, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'H', code: 'H', label: 'Thigh (half), 25 mm below crotch', howToMeasure: 'Straight across the leg 25 mm below the crotch seam junction.', view: 'front', defaultMm: 248, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'I', code: 'I', label: 'Leg opening (half)', howToMeasure: 'Straight across the hem edge, laid flat.', view: 'front', defaultMm: 202, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'J', code: 'J', label: 'Waistband height', howToMeasure: 'From waistband seam to top edge.', view: 'front', defaultMm: 50, tolPlusMm: 3.2, tolMinusMm: 3.2 },
    { id: 'K', code: 'K', label: 'Knee (half), 330 mm below crotch', howToMeasure: 'Straight across the leg 330 mm below the crotch seam junction.', view: 'front', defaultMm: 228, tolPlusMm: 6.4, tolMinusMm: 6.4 },
  ],
  ghost: ghostAssets as GarmentTemplate['ghost'],
};

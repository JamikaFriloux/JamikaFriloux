import type { GarmentTemplate } from '../schema/template';
import { circlePath, mirrorPath, ribLines } from '../geometry';
import ghostAssets from './ghost/hoodie-pullover-v1.json';

/**
 * Pullover hoodie, template v1.
 * 1 unit = 1 mm at base size M (nominal drawing scale). viewBox spans x −60…1060 so the long
 * dropped sleeves fit; the drawing is symmetric about x = 500.
 * Front view: wearer's RIGHT on the viewer's LEFT. Construction: two-panel hood with self/contrast
 * lining, kangaroo pocket, set-in dropped sleeves, rib cuffs and hem band. No zipper.
 */

// ---- Viewer-left geometry (mirrored for the right side)
const SHOULDER_PT = '205,385';
const ARMHOLE_L = 'M205,385 C202,480 203,590 200,685';
const SLEEVE_L = 'M205,385 C120,490 -10,660 -117.2,797.1 L-24.2,869.8 C40,815 140,735 200,685 C203,590 202,480 205,385 Z';
const CUFF_L = 'M-117.2,797.1 L-24.2,869.8 L-73.6,920.1 L-154,857.2 Z';
const BODY_SIDES = `L${SHOULDER_PT} C202,480 203,590 200,685 L205,970 L795,970 L800,685 C797,590 798,480 795,385 L600,340`;
const FRONT_NECK = 'C570,358 530,375 500,378 C470,375 430,358 400,340';
const BACK_NECK = 'C560,352 440,352 400,340';
const BODY_FRONT = `M400,340 ${BODY_SIDES} ${FRONT_NECK} Z`;
const BODY_BACK = `M400,340 ${BODY_SIDES} ${BACK_NECK} Z`;
const HEM_RIB = 'M205,970 L795,970 L785,1040 L215,1040 Z';
const HOOD_OUTER_FRONT = `M400,340 C330,290 296,170 356,102 C405,54 595,54 644,102 C704,170 670,290 600,340 ${FRONT_NECK} Z`;
const HOOD_OPENING = 'M500,370 C455,362 420,330 412,270 C405,190 430,125 500,112 C570,125 595,190 588,270 C580,330 545,362 500,370 Z';
const HOOD_BACK = `M400,340 C330,290 296,170 356,102 C405,54 595,54 644,102 C704,170 670,290 600,340 ${BACK_NECK} Z`;
const POCKET = 'M360,740 L640,740 C668,800 700,860 720,900 L730,955 L270,955 L280,900 C300,860 332,800 360,740 Z';
const CORD_L = 'M466,358 C460,420 470,490 463,560 L473,560 C479,490 470,420 476,358 Z';
const AGLET_L = 'M461,560 L475,560 L474,590 L462,590 Z';

const SLEEVE_SEAM_L = 'M200,685 C140,735 40,815 -24.2,869.8';
const CUFF_SEAM_L = 'M-117.2,797.1 L-24.2,869.8';
const SIDE_L = 'M200,685 L205,970';
const SHOULDER_L = 'M400,340 L205,385';

const shell = ['screen-print', 'dtg', 'embroidery', 'puff-print', 'heat-transfer', 'applique', 'rhinestone', 'stud'] as const;
const small = ['screen-print', 'embroidery', 'heat-transfer', 'rhinestone', 'stud'] as const;

export const hoodiePulloverV1: GarmentTemplate = {
  id: 'hoodie-pullover',
  version: 1,
  name: 'Pullover hoodie',
  category: 'top',
  description: 'Relaxed pullover hoodie: two-panel lined hood with drawcord, kangaroo pocket, dropped shoulders, 1x1 rib cuffs and hem band. No zipper.',
  structure: { closure: 'pullover', features: ['two-panel lined hood', 'drawcord through eyelets', 'kangaroo pocket', 'dropped shoulder', 'rib cuffs', 'rib hem band'] },
  sizes: { available: ['XS', 'S', 'M', 'L', 'XL', '2XL', '3XL'], defaultBase: 'M', defaultRange: ['XS', 'S', 'M', 'L', 'XL'] },
  calibration: {
    kind: 'nominal-drawing-scale',
    mmPerUnit: 1,
    baseSize: 'M',
    note: 'Drawn at 1 unit = 1 mm for the template default size M. Canvas-derived placement is an estimate until you enter manufacturing dimensions.',
  },
  components: [
    { id: 'body_front', name: 'Front body', group: 'body', materialRole: 'shell', decorationMethods: [...shell] },
    { id: 'body_back', name: 'Back body', group: 'body', materialRole: 'shell', decorationMethods: [...shell] },
    { id: 'sleeve_left', name: 'Left sleeve (wearer’s left)', group: 'sleeve', materialRole: 'shell', decorationMethods: [...shell] },
    { id: 'sleeve_right', name: 'Right sleeve (wearer’s right)', group: 'sleeve', materialRole: 'shell', decorationMethods: [...shell] },
    { id: 'hood', name: 'Hood (outer)', group: 'hood', materialRole: 'shell', decorationMethods: [...small] },
    { id: 'hood_lining', name: 'Hood lining', group: 'hood', materialRole: 'lining', decorationMethods: [] },
    { id: 'kangaroo_pocket', name: 'Kangaroo pocket', group: 'pocket', materialRole: 'shell', decorationMethods: [...small] },
    { id: 'cuff_left', name: 'Left cuff', group: 'cuff', materialRole: 'rib', decorationMethods: ['embroidery', 'heat-transfer'] },
    { id: 'cuff_right', name: 'Right cuff', group: 'cuff', materialRole: 'rib', decorationMethods: ['embroidery', 'heat-transfer'] },
    { id: 'hem_rib', name: 'Hem band', group: 'trim', materialRole: 'rib', decorationMethods: ['embroidery', 'heat-transfer'] },
    { id: 'drawcord', name: 'Drawcord', group: 'trim', materialRole: 'trim', decorationMethods: [] },
  ],
  views: [
    {
      id: 'front',
      label: 'Front',
      viewBox: [-200, 30, 1400, 1060],
      panels: [
        { id: 'f_body', componentId: 'body_front', d: BODY_FRONT, z: 1, side: 'outer' },
        { id: 'f_sleeve_right', componentId: 'sleeve_right', d: SLEEVE_L, z: 2, side: 'outer' },
        { id: 'f_sleeve_left', componentId: 'sleeve_left', d: mirrorPath(SLEEVE_L), z: 2, side: 'outer' },
        { id: 'f_cuff_right', componentId: 'cuff_right', d: CUFF_L, z: 3, side: 'outer' },
        { id: 'f_cuff_left', componentId: 'cuff_left', d: mirrorPath(CUFF_L), z: 3, side: 'outer' },
        { id: 'f_hem', componentId: 'hem_rib', d: HEM_RIB, z: 3, side: 'outer' },
        { id: 'f_pocket', componentId: 'kangaroo_pocket', d: POCKET, z: 4, side: 'outer' },
        { id: 'f_hood', componentId: 'hood', d: HOOD_OUTER_FRONT, z: 5, side: 'outer' },
        { id: 'f_hood_lining', componentId: 'hood_lining', d: HOOD_OPENING, z: 6, side: 'inner' },
        { id: 'f_cord_right', componentId: 'drawcord', d: CORD_L, z: 7, side: 'outer' },
        { id: 'f_cord_left', componentId: 'drawcord', d: mirrorPath(CORD_L), z: 7, side: 'outer' },
      ],
      seams: [
        { id: 'shoulder_right', name: 'Right shoulder seam', d: SHOULDER_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'shoulder_left', name: 'Left shoulder seam', d: mirrorPath(SHOULDER_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'armhole_right', name: 'Right armhole seam', d: ARMHOLE_L, componentIds: ['body_front', 'sleeve_right'], defaultStyle: 'overlock' },
        { id: 'armhole_left', name: 'Left armhole seam', d: mirrorPath(ARMHOLE_L), componentIds: ['body_front', 'sleeve_left'], defaultStyle: 'overlock' },
        { id: 'side_right', name: 'Right side seam', d: SIDE_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'side_left', name: 'Left side seam', d: mirrorPath(SIDE_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_right', name: 'Right underarm seam', d: SLEEVE_SEAM_L, componentIds: ['sleeve_right'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_left', name: 'Left underarm seam', d: mirrorPath(SLEEVE_SEAM_L), componentIds: ['sleeve_left'], defaultStyle: 'overlock' },
        { id: 'cuff_seam_right', name: 'Right cuff seam', d: CUFF_SEAM_L, componentIds: ['sleeve_right', 'cuff_right'], defaultStyle: 'overlock' },
        { id: 'cuff_seam_left', name: 'Left cuff seam', d: mirrorPath(CUFF_SEAM_L), componentIds: ['sleeve_left', 'cuff_left'], defaultStyle: 'overlock' },
        { id: 'hem_band_seam', name: 'Hem band seam', d: 'M205,970 L795,970', componentIds: ['body_front', 'body_back', 'hem_rib'], defaultStyle: 'overlock' },
        { id: 'pocket_topstitch', name: 'Pocket topstitch (openings & top)', d: 'M287,905 C306,862 337,804 365,748 L635,748 C663,804 694,862 713,905', componentIds: ['kangaroo_pocket'], defaultStyle: 'double-needle' },
        { id: 'pocket_bottom', name: 'Pocket bottom attach', d: 'M272,948 L728,948', componentIds: ['kangaroo_pocket'], defaultStyle: 'single-needle' },
        { id: 'hood_channel', name: 'Hood drawcord channel', d: 'M478,388 C432,382 392,345 383,272 C375,182 405,105 500,88 C595,105 625,182 617,272 C608,345 568,382 522,388', componentIds: ['hood'], defaultStyle: 'single-needle' },
        { id: 'hood_neck_seam', name: 'Hood to neck seam', d: `M600,340 ${FRONT_NECK}`, componentIds: ['hood', 'body_front'], defaultStyle: 'overlock' },
      ],
      details: [
        { id: 'eyelet_r', d: circlePath(471, 362, 7), kind: 'hardware', componentId: 'hood' },
        { id: 'eyelet_l', d: circlePath(529, 362, 7), kind: 'hardware', componentId: 'hood' },
        { id: 'aglet_r', d: AGLET_L, kind: 'hardware', componentId: 'drawcord' },
        { id: 'aglet_l', d: mirrorPath(AGLET_L), kind: 'hardware', componentId: 'drawcord' },
        { id: 'hem_ribs', d: ribLines([[205, 970], [795, 970]], [[215, 1040], [785, 1040]], 48), kind: 'rib', componentId: 'hem_rib' },
        { id: 'cuff_ribs_r', d: ribLines([[-117.2, 797.1], [-24.2, 869.8]], [[-154, 857.2], [-73.6, 920.1]], 10), kind: 'rib', componentId: 'cuff_right' },
        { id: 'cuff_ribs_l', d: mirrorPath(ribLines([[-117.2, 797.1], [-24.2, 869.8]], [[-154, 857.2], [-73.6, 920.1]], 10)), kind: 'rib', componentId: 'cuff_left' },
        { id: 'hood_cf', d: 'M500,112 L500,92', kind: 'construction', componentId: 'hood' },
      ],
      anchors: [
        { id: 'center_chest', label: 'Center chest', x: 500, y: 450, componentId: 'body_front', description: 'Center front, 110 mm below the HPS line (template reference).' },
        { id: 'left_chest', label: 'Left chest', x: 615, y: 450, componentId: 'body_front', description: 'Wearer’s left chest, 115 mm from center front.' },
        { id: 'pocket_center', label: 'Pocket center', x: 500, y: 830, componentId: 'kangaroo_pocket', description: 'Center of the kangaroo pocket.' },
        { id: 'sleeve_right_forearm', label: 'Right sleeve forearm', x: 14, y: 718, componentId: 'sleeve_right', description: 'Wearer’s right forearm, center of sleeve.' },
        { id: 'sleeve_left_forearm', label: 'Left sleeve forearm', x: 986, y: 718, componentId: 'sleeve_left', description: 'Wearer’s left forearm, center of sleeve.' },
        { id: 'hood_side_right', label: 'Hood side (right)', x: 350, y: 220, componentId: 'hood', description: 'Wearer’s right hood panel.' },
        { id: 'hem_band', label: 'Hem band', x: 500, y: 1005, componentId: 'hem_rib', description: 'Center front of the hem band.' },
      ],
      measurementLines: [
        { pomId: 'A', from: [400, 340], to: [400, 1040], label: [378, 520] },
        { pomId: 'B', from: [200, 710], to: [800, 710], label: [300, 710] },
        { pomId: 'C', from: [215, 1040], to: [785, 1040], label: [500, 1062] },
        { pomId: 'D', from: [205, 385], to: [795, 385], label: [720, 372] },
        { pomId: 'E', from: [205, 385], to: [-154, 857.2], label: [-40, 560] },
        { pomId: 'F', from: [-154, 857.2], to: [-73.6, 920.1], label: [-150, 925] },
        { pomId: 'G', from: [-24.2, 869.8], to: [-73.6, 920.1], label: [0, 930] },
        { pomId: 'H', from: [790, 970], to: [790, 1040], label: [820, 1005] },
        { pomId: 'I', from: [500, 340], to: [500, 66], label: [528, 280] },
        { pomId: 'J', from: [302, 190], to: [698, 190], label: [700, 160] },
        { pomId: 'K', from: [400, 340], to: [600, 340], label: [640, 320] },
        { pomId: 'L', from: [360, 740], to: [640, 740], label: [500, 722] },
        { pomId: 'M', from: [500, 740], to: [500, 955], label: [525, 880] },
        { pomId: 'N', from: [200, 685], to: [57.5, 573.7], label: [110, 600] },
      ],
    },
    {
      id: 'back',
      label: 'Back',
      viewBox: [-200, 30, 1400, 1060],
      panels: [
        { id: 'b_body', componentId: 'body_back', d: BODY_BACK, z: 1, side: 'outer' },
        { id: 'b_sleeve_left', componentId: 'sleeve_left', d: SLEEVE_L, z: 2, side: 'outer' },
        { id: 'b_sleeve_right', componentId: 'sleeve_right', d: mirrorPath(SLEEVE_L), z: 2, side: 'outer' },
        { id: 'b_cuff_left', componentId: 'cuff_left', d: CUFF_L, z: 3, side: 'outer' },
        { id: 'b_cuff_right', componentId: 'cuff_right', d: mirrorPath(CUFF_L), z: 3, side: 'outer' },
        { id: 'b_hem', componentId: 'hem_rib', d: HEM_RIB, z: 3, side: 'outer' },
        { id: 'b_hood', componentId: 'hood', d: HOOD_BACK, z: 5, side: 'outer' },
      ],
      seams: [
        { id: 'shoulder_left', name: 'Left shoulder seam', d: SHOULDER_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'shoulder_right', name: 'Right shoulder seam', d: mirrorPath(SHOULDER_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'armhole_left', name: 'Left armhole seam', d: ARMHOLE_L, componentIds: ['body_back', 'sleeve_left'], defaultStyle: 'overlock' },
        { id: 'armhole_right', name: 'Right armhole seam', d: mirrorPath(ARMHOLE_L), componentIds: ['body_back', 'sleeve_right'], defaultStyle: 'overlock' },
        { id: 'side_left', name: 'Left side seam', d: SIDE_L, componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'side_right', name: 'Right side seam', d: mirrorPath(SIDE_L), componentIds: ['body_front', 'body_back'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_left', name: 'Left underarm seam', d: SLEEVE_SEAM_L, componentIds: ['sleeve_left'], defaultStyle: 'overlock' },
        { id: 'sleeve_seam_right', name: 'Right underarm seam', d: mirrorPath(SLEEVE_SEAM_L), componentIds: ['sleeve_right'], defaultStyle: 'overlock' },
        { id: 'cuff_seam_left', name: 'Left cuff seam', d: CUFF_SEAM_L, componentIds: ['sleeve_left', 'cuff_left'], defaultStyle: 'overlock' },
        { id: 'cuff_seam_right', name: 'Right cuff seam', d: mirrorPath(CUFF_SEAM_L), componentIds: ['sleeve_right', 'cuff_right'], defaultStyle: 'overlock' },
        { id: 'hem_band_seam', name: 'Hem band seam', d: 'M205,970 L795,970', componentIds: ['body_front', 'body_back', 'hem_rib'], defaultStyle: 'overlock' },
        { id: 'hood_center_seam', name: 'Hood center seam', d: 'M500,66 C500,150 500,260 500,352', componentIds: ['hood'], defaultStyle: 'topstitch-contrast' },
      ],
      details: [
        { id: 'hem_ribs', d: ribLines([[205, 970], [795, 970]], [[215, 1040], [785, 1040]], 48), kind: 'rib', componentId: 'hem_rib' },
        { id: 'cuff_ribs_l', d: ribLines([[-117.2, 797.1], [-24.2, 869.8]], [[-154, 857.2], [-73.6, 920.1]], 10), kind: 'rib', componentId: 'cuff_left' },
        { id: 'cuff_ribs_r', d: mirrorPath(ribLines([[-117.2, 797.1], [-24.2, 869.8]], [[-154, 857.2], [-73.6, 920.1]], 10)), kind: 'rib', componentId: 'cuff_right' },
      ],
      anchors: [
        { id: 'upper_back', label: 'Upper back', x: 500, y: 420, componentId: 'body_back', description: 'Center back, 70 mm below the hood seam (template reference).' },
        { id: 'center_back', label: 'Center back', x: 500, y: 640, componentId: 'body_back', description: 'Center of the back panel.' },
        { id: 'hood_back', label: 'Hood back', x: 500, y: 200, componentId: 'hood', description: 'Back of the hood, on the center seam.' },
        { id: 'sleeve_left_back', label: 'Left sleeve (back)', x: 14, y: 718, componentId: 'sleeve_left', description: 'Back of the wearer’s left forearm.' },
        { id: 'sleeve_right_back', label: 'Right sleeve (back)', x: 986, y: 718, componentId: 'sleeve_right', description: 'Back of the wearer’s right forearm.' },
        { id: 'back_hem', label: 'Back hem', x: 500, y: 920, componentId: 'body_back', description: 'Center back above the hem band.' },
      ],
      measurementLines: [],
    },
  ],
  poms: [
    { id: 'A', code: 'A', label: 'Body length from HPS (incl. hem band)', howToMeasure: 'From high point shoulder straight down to the bottom edge of the hem band.', view: 'front', defaultMm: 700, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'B', code: 'B', label: 'Chest width (1" below armhole)', howToMeasure: 'Straight across, edge to edge, 25 mm below the underarm point.', view: 'front', defaultMm: 600, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'C', code: 'C', label: 'Hem band width (relaxed)', howToMeasure: 'Across the bottom edge of the hem band, relaxed.', view: 'front', defaultMm: 570, tolPlusMm: 12.7, tolMinusMm: 12.7 },
    { id: 'D', code: 'D', label: 'Across shoulder', howToMeasure: 'Shoulder point to shoulder point.', view: 'front', defaultMm: 590, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'E', code: 'E', label: 'Sleeve length from shoulder point (incl. cuff)', howToMeasure: 'Along the top of the sleeve from shoulder point to cuff edge.', view: 'front', defaultMm: 593, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'F', code: 'F', label: 'Cuff opening (relaxed, half)', howToMeasure: 'Across the cuff edge, relaxed.', view: 'front', defaultMm: 102, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'G', code: 'G', label: 'Cuff height', howToMeasure: 'From cuff seam to cuff edge.', view: 'front', defaultMm: 70, tolPlusMm: 3.2, tolMinusMm: 3.2 },
    { id: 'H', code: 'H', label: 'Hem band height', howToMeasure: 'From hem band seam to bottom edge.', view: 'front', defaultMm: 70, tolPlusMm: 3.2, tolMinusMm: 3.2 },
    { id: 'I', code: 'I', label: 'Hood height', howToMeasure: 'From the HPS line straight up to the top of the hood, hood laid flat.', view: 'front', defaultMm: 274, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'J', code: 'J', label: 'Hood width (flat, widest)', howToMeasure: 'Across the widest point of the hood laid flat.', view: 'front', defaultMm: 396, tolPlusMm: 9.5, tolMinusMm: 9.5 },
    { id: 'K', code: 'K', label: 'Neck width (seam to seam)', howToMeasure: 'HPS to HPS at the hood seam.', view: 'front', defaultMm: 200, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'L', code: 'L', label: 'Pocket width at top', howToMeasure: 'Across the top edge of the kangaroo pocket.', view: 'front', defaultMm: 280, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'M', code: 'M', label: 'Pocket height', howToMeasure: 'Center pocket from top edge to bottom attach seam.', view: 'front', defaultMm: 215, tolPlusMm: 6.4, tolMinusMm: 6.4 },
    { id: 'N', code: 'N', label: 'Bicep (half)', howToMeasure: 'From the underarm point perpendicular to the top sleeve fold.', view: 'front', defaultMm: 181, tolPlusMm: 6.4, tolMinusMm: 6.4 },
  ],
  ghost: ghostAssets as GarmentTemplate['ghost'],
};

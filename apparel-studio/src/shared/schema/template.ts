import { z } from 'zod';

/** Decoration methods a template may support. */
export const decorationMethodSchema = z.enum([
  'screen-print',
  'dtg',
  'embroidery',
  'puff-print',
  'heat-transfer',
  'applique',
  'rhinestone',
  'stud',
  'sublimation',
]);
export type DecorationMethod = z.infer<typeof decorationMethodSchema>;

export const DECORATION_METHOD_LABELS: Record<DecorationMethod, string> = {
  'screen-print': 'Screen print',
  dtg: 'Direct-to-garment (DTG)',
  embroidery: 'Embroidery',
  'puff-print': 'Puff print',
  'heat-transfer': 'Heat transfer',
  applique: 'Appliqué',
  rhinestone: 'Rhinestone',
  stud: 'Stud',
  sublimation: 'Sublimation',
};

export const stitchStyleSchema = z.enum([
  'single-needle',
  'double-needle',
  'coverstitch',
  'overlock',
  'topstitch-contrast',
  'zigzag',
  'bartack',
]);
export type StitchStyle = z.infer<typeof stitchStyleSchema>;

export const STITCH_STYLE_LABELS: Record<StitchStyle, string> = {
  'single-needle': 'Single needle',
  'double-needle': 'Double needle',
  coverstitch: 'Coverstitch',
  overlock: 'Overlock (visual)',
  'topstitch-contrast': 'Contrast topstitch',
  zigzag: 'Zigzag',
  bartack: 'Bartack',
};

export const viewIdSchema = z.enum(['front', 'back']);
export type ViewId = z.infer<typeof viewIdSchema>;

const point = z.tuple([z.number(), z.number()]);

export const templateComponentSchema = z.object({
  id: z.string().regex(/^[a-z][a-z0-9_]*$/),
  name: z.string(),
  group: z.enum(['body', 'sleeve', 'hood', 'trim', 'pocket', 'leg', 'waistband', 'cuff']),
  /** Default material role used to propose the initial material. */
  materialRole: z.enum(['shell', 'rib', 'lining']),
  decorationMethods: z.array(decorationMethodSchema),
});

export const templatePanelSchema = z.object({
  id: z.string(),
  componentId: z.string(),
  /** SVG path data in the view's coordinate system. Also used as clip path. */
  d: z.string(),
  /** Draw order inside the view; lower draws first. */
  z: z.number().int(),
  /** `inner` = the inside of the garment visible through an opening (e.g. back neck). */
  side: z.enum(['outer', 'inner']).default('outer'),
});

export const templateSeamSchema = z.object({
  id: z.string(),
  name: z.string(),
  /** Open SVG path the stitch line follows. */
  d: z.string(),
  componentIds: z.array(z.string()),
  defaultStyle: stitchStyleSchema,
});

export const templateDetailSchema = z.object({
  id: z.string(),
  /** Non-selectable linework such as fold lines, drawcords, rib lines. */
  d: z.string(),
  kind: z.enum(['construction', 'fold', 'rib', 'hardware']),
  componentId: z.string().optional(),
});

export const templateAnchorSchema = z.object({
  id: z.string(),
  label: z.string(),
  x: z.number(),
  y: z.number(),
  componentId: z.string(),
  description: z.string(),
});

export const measurementLineSchema = z.object({
  pomId: z.string(),
  from: point,
  to: point,
  /** Where to draw the code bubble. */
  label: point,
});

export const templateViewSchema = z.object({
  id: viewIdSchema,
  label: z.string(),
  /** [minX, minY, width, height] in template units. */
  viewBox: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  panels: z.array(templatePanelSchema),
  seams: z.array(templateSeamSchema),
  details: z.array(templateDetailSchema),
  anchors: z.array(templateAnchorSchema),
  measurementLines: z.array(measurementLineSchema),
});

export const templatePomSchema = z.object({
  id: z.string(),
  code: z.string(),
  label: z.string(),
  howToMeasure: z.string(),
  view: viewIdSchema,
  /** Template default for the base size only. Always flagged unconfirmed in projects. */
  defaultMm: z.number().nullable(),
  tolPlusMm: z.number(),
  tolMinusMm: z.number(),
});

/** Piecewise-affine mesh: a grid in technical coordinates and its displaced mockup positions. */
export const ghostMeshSchema = z.object({
  cols: z.number().int().min(2),
  rows: z.number().int().min(2),
  /** Technical-space rectangle the grid spans. */
  bounds: z.tuple([z.number(), z.number(), z.number(), z.number()]),
  /** Mockup-space positions of each grid vertex, row-major. Length = cols*rows. */
  dst: z.array(point),
});

export const ghostViewAssetsSchema = z.object({
  /** Mockup canvas size in mockup pixels at 1x. */
  width: z.number(),
  height: z.number(),
  mesh: ghostMeshSchema,
  /** Asset URLs (relative to /templates/...). */
  shadow: z.string(),
  highlight: z.string(),
  displacement: z.string(),
  occlusion: z.string().nullable(),
  /** Components drawn *after* shading as foreground (e.g. front neck rib over inner back). */
  foregroundComponents: z.array(z.string()),
});

export const ghostAssetSetSchema = z.object({
  assetSetId: z.string(),
  version: z.number().int(),
  /**
   * `procedural-v1`: shading maps hand-authored as vector gradients + deterministic noise.
   * `photographic`: maps extracted from a photographed ghost-mannequin sample.
   */
  quality: z.enum(['procedural-v1', 'photographic']),
  notes: z.string(),
  views: z.record(viewIdSchema, ghostViewAssetsSchema),
});

export const garmentTemplateSchema = z.object({
  id: z.string(),
  version: z.number().int().positive(),
  name: z.string(),
  category: z.enum(['top', 'bottom']),
  description: z.string(),
  /** Structural facts. Decorations never alter these. */
  structure: z.object({
    closure: z.enum(['pullover', 'elastic-waist', 'zip']),
    features: z.array(z.string()),
  }),
  sizes: z.object({
    available: z.array(z.string()),
    defaultBase: z.string(),
    defaultRange: z.array(z.string()),
  }),
  /**
   * Nominal drawing scale: template units → mm at the base size. Used to *estimate*
   * placement from the canvas. Null means placement is visual-only.
   */
  calibration: z
    .object({
      kind: z.literal('nominal-drawing-scale'),
      mmPerUnit: z.number().positive(),
      baseSize: z.string(),
      note: z.string(),
    })
    .nullable(),
  components: z.array(templateComponentSchema),
  views: z.array(templateViewSchema),
  poms: z.array(templatePomSchema),
  ghost: ghostAssetSetSchema.nullable(),
});

export type GarmentTemplate = z.infer<typeof garmentTemplateSchema>;
export type TemplateView = z.infer<typeof templateViewSchema>;
export type TemplatePanel = z.infer<typeof templatePanelSchema>;
export type TemplateSeam = z.infer<typeof templateSeamSchema>;
export type TemplateAnchor = z.infer<typeof templateAnchorSchema>;
export type TemplateComponent = z.infer<typeof templateComponentSchema>;
export type TemplatePom = z.infer<typeof templatePomSchema>;
export type GhostViewAssets = z.infer<typeof ghostViewAssetsSchema>;
export type GhostMesh = z.infer<typeof ghostMeshSchema>;
